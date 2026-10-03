"""Own 3D models (phase 2): an FBX character -> a Tekken 3 PS1 3DMK model over a donor's.

Pipeline: read the FBX (fbx.py) -> skin weights -> Tekken 3 rows -> a Tekken 3 style low-poly
body (lowpoly.py: tubes of rings and a head shell, shaped by rays onto the original) -> local
frames that match the donor's (so the donor's animations pose it the same way) -> a painted
texture baked from the original (texture_bake.py) -> the binary blocks.

Format notes (NOTES.md "Own 3D models"): a row's vertex block sits in the previous row's word 12;
own vertices 4 x s16 in the row's frame; the vertices of earlier rows are borrowed through the
cache (the owner deposits them with tail group 3, the reader lists the entry in g2; entry 0 is
never used). Polygons are gouraud triangles and quads (families 2 and 3, record layouts in
NOTES.md). A triangle faces the camera when cross(b - a, c - a) points into the body; normals
(unit 4096) point out."""
from __future__ import annotations
import struct
from pathlib import Path
import numpy as np

import model_export as X

DRAW = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]   # draw order
FRAME = {2: 1, 4: 3, 20: 19}          # second layers share their main row's frame
SECOND = {1: 2, 3: 4, 19: 20}
PAIRS = {"collar": (11, 15), "upper": (12, 16), "fore": (13, 17), "hand": (14, 18),
         "thigh": (5, 8), "shin": (6, 9), "foot": (7, 10)}
MAX_TRIS, MAX_SLOTS, MAX_NORMALS, MAX_UVS = 255, 128, 126, 255
# Texture style (see docs/knowledge/t3-model-style.md): stain flattening, flat colour areas.
# Chosen 2026-10-02 from four variants rendered beside Nina (scratch cmp.py): stains half
# flattened, up to 8 colour areas per chart, one 3 x 3 majority pass, areas closer than 40 RGB
# merged, the original light kept within +-35 %.
TEXTURE_STYLE = {"flat_radius": 8, "flat_strength": 0.4, "k": 8, "shade": 0.6, "passes": 1, "size": 3,
                 "merge": 40, "light": 0.35}
# Build the body on the donor's own model (template.py) instead of tubes (lowpoly.py).
TEMPLATE = True
# GPU packet bytes per polygon family (flat tri, flat quad, gouraud tri, gouraud quad). The game
# builds one packet per polygon in a fixed buffer per player; stock models use at most 32580
# bytes, and a model needing 33596 crashed the game when the fight started (2026-10-02).
PACKET = (32, 40, 40, 52)
MAX_PACKET_BYTES = 31000


def frame_row(r):
    return FRAME.get(r, r)


# --- bone names -> Tekken 3 rows ------------------------------------------------------------------
def _part(name: str):
    """(part, side) for a skeleton bone name (Mixamo and similar), side "L", "R" or None."""
    n = name.split(":")[-1].lower()
    side = None
    import re
    tail = re.search(r"[._ ](l|r|left|right)$", n)          # Blender style: hand.L, upper_arm_R
    if tail:
        side, n = ("L" if tail.group(1)[0] == "l" else "R"), n[:tail.start()]
    n = n.replace("_", "").replace(" ", "").replace(".", "")
    for pre, s in (("left", "L"), ("right", "R")):
        if side is None and n.startswith(pre):
            n, side = n[len(pre):], s
    order = [("upleg", "thigh"), ("thigh", "thigh"), ("toe", "foot"), ("foot", "foot"), ("ankle", "foot"),
             ("forearm", "fore"), ("lowerarm", "fore"), ("hand", "hand"), ("thumb", "hand"), ("index", "hand"),
             ("middle", "hand"), ("ring", "hand"), ("pinky", "hand"), ("finger", "hand"),
             ("shoulder", "collar"), ("clavicle", "collar"), ("upperarm", "upper"), ("arm", "upper"),
             ("leg", "shin"), ("calf", "shin"), ("knee", "shin"),
             ("hips", "pelvis"), ("pelvis", "pelvis"), ("spine", "spine"), ("chest", "spine"),
             ("neck", "head"), ("head", "head"), ("eye", "head"), ("jaw", "head")]
    for key, part in order:
        if key in n:
            return part, side
    return None, side


def bone_rows(bones, left_rows):
    """Row for every bone (by name; unknown bones follow their parent)."""
    out = []
    for i, b in enumerate(bones):
        part, side = _part(b["name"])
        if part == "pelvis":
            out.append(3)
        elif part == "spine":
            out.append(1)
        elif part == "head":
            out.append(19)
        elif part in PAIRS and side:
            out.append(left_rows[part] if side == "L" else [r for r in PAIRS[part] if r != left_rows[part]][0])
        else:
            out.append(None)
    for i, b in enumerate(bones):
        j = i
        while out[i] is None and bones[j]["parent"] >= 0:
            j = bones[j]["parent"]
            out[i] = out[j]
        if out[i] is None:
            out[i] = 1
    return out


def joint(bones, part, side=None):
    """Bind position of the first bone of a part (and side)."""
    for b in bones:
        p, s = _part(b["name"])
        if p == part and (side is None or s == side):
            return np.array([b["matrix"][k][3] for k in range(3)])
    return None


def finger_points(bones, side):
    """Knuckle line and fingertip centre of the four fingers, thumb base and tip (bind
    positions), from finger bones named like Mixamo's (HandIndex1..4, HandThumb1..4); None
    when the skeleton has no finger bones."""
    chains = {}
    for b in bones:
        n = b["name"].split(":")[-1].lower()
        if not n.startswith({"L": "left", "R": "right"}[side]):
            continue
        for f in ("thumb", "index", "middle", "ring", "pinky"):
            if f in n and n[-1].isdigit():
                chains.setdefault(f, {})[int(n[-1])] = np.array([b["matrix"][k][3] for k in range(3)])
    four = [chains[f] for f in ("index", "middle", "ring", "pinky") if f in chains]
    if len(four) < 2 or "thumb" not in chains:
        return None
    knuckle = np.mean([c[min(c)] for c in four], 0)
    tip = np.mean([c[max(c)] for c in four], 0)
    th = chains["thumb"]
    return {"knuckle": knuckle, "tip": tip, "thumb base": th[min(th)], "thumb tip": th[max(th)],
            "width": max(np.linalg.norm(a[min(a)] - b[min(b)]) for a in four for b in four)}


def first_bone(bones, key, side):
    for b in bones:
        n = b["name"].split(":")[-1].lower()
        if key in n and n.startswith({"L": "left", "R": "right"}[side]):
            return np.array([b["matrix"][k][3] for k in range(3)])
    return None


# --- the donor's standing pose: frames our model must match -----------------------------------------
def donor_frames(root: Path, m: bytes):
    stance = X.stance_pose(root)
    fight = X.world(m, stance)
    W = X.tweaked(m, stance, X.world(m, stance, X.stand_pose(m, fight)))
    return W


def donor_triangles(m: bytes, W):
    """Per frame row: (centroid in the row's frame, material, 3 UVs) of the donor's triangles."""
    import anim_model as A
    from fmt import row, block, parse_b, parse_c_ps1
    out = {}
    for r, slots in X.bind(m).items():
        w = row(m, r)
        prims = parse_c_ps1(block(m, w[2]))
        R, T = W[frame_row(r)]
        i = 0
        for k, fam in enumerate(parse_b(block(m, w[1]))):
            for rec in fam:
                corners = A.prim_verts(k, rec)
                _, mat, uv = prims[i]
                i += 1
                for a, b, c in ([(0, 1, 2)] if len(corners) == 3 else [(0, 1, 2), (1, 3, 2)]):
                    pts = [slots[corners[j]] if corners[j] < len(slots) else None for j in (a, b, c)]
                    q = [uv[j] for j in (a, b, c)]
                    if mat is None or None in pts or None in q:
                        continue
                    world = [W[s[0]][0] @ np.array(s[1], float) + W[s[0]][1] for s in pts]
                    cen = R.T @ (sum(world) / 3 - T)
                    out.setdefault(frame_row(r), []).append((cen, mat, q))
    return out


# --- the build ----------------------------------------------------------------------------------------
def pack_fields(vals, bits):
    per = {9: 3, 2: 16}[bits]
    out = struct.pack("<I", len(vals))
    for i in range(0, len(vals), per):
        w = 0
        for k, v in enumerate(vals[i:i + per]):
            w |= (v & ((1 << bits) - 1)) << (bits * k)
        out += struct.pack("<I", w)
    return out


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


class Budget(Exception):
    pass


def build(root: Path, model: int, fbx_path: Path, target: int | None = None, log=print) -> tuple[bytes, bytes, dict]:
    """(stock model, new model, report)."""
    import fbx
    import remesh
    import lowpoly
    from fmt import row
    rid = X.FIRST_MODEL_RECORD + 4 * model
    m = X.records(root, [rid])[rid]
    W = donor_frames(root, m)
    ch = fbx.character(fbx_path)
    P = np.array(ch["positions"]).reshape(-1, 3)
    Tr = np.array(ch["triangles"]).reshape(-1, 3)
    bones = ch["bones"]
    if not bones:
        raise ValueError("This FBX has no skeleton (automatic rigging comes later).")

    # FBX axes (Y up, faces +Z, left = +X) -> the donor's game world (Y down)
    up = np.array([0.0, -1, 0])
    front = sum(W[r][0][:, 0] for r in (7, 10))
    front[1] = 0
    front /= np.linalg.norm(front)
    left = np.cross(up, front)
    Q = np.stack([left, up, front], 1)
    left_rows = {k: (a if (W[a][1] - W[1][1]) @ left > (W[b][1] - W[1][1]) @ left else b) for k, (a, b) in PAIRS.items()}
    L = lambda part: left_rows[part]
    R_ = lambda part: [r for r in PAIRS[part] if r != left_rows[part]][0]

    # scale: the donor's leg length
    hips = joint(bones, "pelvis")
    if hips is None:
        raise ValueError("No hips bone found in the skeleton.")
    leg_fbx = np.mean([np.linalg.norm(joint(bones, "thigh", s) - joint(bones, "shin", s)) +
                       np.linalg.norm(joint(bones, "shin", s) - joint(bones, "foot", s)) for s in "LR"])
    leg_t3 = np.mean([np.linalg.norm(W[a][1] - W[b][1]) + np.linalg.norm(W[b][1] - W[c][1])
                      for a, b, c in ((5, 6, 7), (8, 9, 10))])
    # Scale by the hips' height above the soles, not by the leg bones: the animations put the
    # hips at the donor's height, so the soles must end where the donor's do (heels, thick
    # boots). Donor: lowest vertex of its standing pose below the hip joint (game Y points down).
    floor_t3 = max((W[sl[0]][0] @ np.array(sl[1], float) + W[sl[0]][1])[1]
                   for r, slots in X.bind(m).items() if r in (5, 6, 7, 8, 9, 10) for sl in slots if sl is not None)
    hip_t3 = floor_t3 - W[3][1][1]
    hip_fbx = hips[1] - P[:, 1].min()
    s = hip_t3 / hip_fbx if hip_t3 > 0 and hip_fbx > 0 else leg_t3 / leg_fbx
    log(f"scale {s:.1f} (hip height: donor {hip_t3:.0f} game units; by leg bones it was {leg_t3 / leg_fbx:.1f})")
    g = lambda x: s * (Q @ (np.asarray(x) - hips)) + W[3][1]       # FBX -> game, hips on the root

    # joints (game) and the frames: the donor's standing frames, turned so each limb runs
    # along the imported limb (shortest rotation), e.g. T-pose arms
    J = {1: g(hips), 3: g(hips)}
    Jf = {1: hips, 3: hips}
    for side, rows in (("L", L), ("R", R_)):
        for part in ("collar", "upper", "fore", "hand", "thigh", "shin", "foot"):
            pos = joint(bones, part, side)
            if pos is None:
                raise ValueError(f"No {side} {part} bone found in the skeleton.")
            J[rows(part)], Jf[rows(part)] = g(pos), pos
    neck = joint(bones, "head")
    J[19], Jf[19] = g(neck), neck
    F = {}
    child = {1: 19, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18, 5: 6, 6: 7, 8: 9, 9: 10}
    for r in (1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19):
        Rd = W[r][0]
        if r in child:
            dd = W[child[r]][1] - W[r][1]
            df = J[child[r]] - J[r]
            A = X.align(dd / np.linalg.norm(dd), df / np.linalg.norm(df))
        elif r in (14, 18):
            A = F[r - 1] @ W[r - 1][0].T          # the hand follows its forearm
        else:
            A = np.eye(3)
        F[r] = A @ Rd
    for k, v in FRAME.items():
        F[k], J[k] = F[v], J[v]

    # every original triangle belongs to the row whose bones weigh most on it
    # Eyeballs (geometry hanging on eye bones) sit in the sockets; Tekken 3 paints eyes onto the
    # face texture, so they neither shape nor colour the model.
    eye_bones = {i for i, b in enumerate(bones) if "eye" in b["name"].split(":")[-1].lower()}
    if eye_bones:
        main_bone = np.array([max(wv, key=wv.get) if wv else -1 for wv in ch["weights"]])
        eyes = np.isin(main_bone[Tr], list(eye_bones)).all(1)
        if eyes.any():
            log(f"{int(eyes.sum())} eyeball triangles left out")
            Tr = Tr[~eyes]
            ch = dict(ch, corner_uvs=list(np.array(ch["corner_uvs"]).reshape(-1, 6)[~eyes].ravel()),
                      materials=list(np.array(ch["materials"])[~eyes]))
    source = None
    if ch["textures"]:
        import texture_bake
        source = texture_bake.Source(ch)
        solid = ~source.transparent()
        if solid.sum() > 0.5 * len(Tr):
            log(f"{int((~solid).sum())} see-through triangles left out")
            Tr_all, Tr = Tr, Tr[solid]
    rows_of_bone = bone_rows(bones, left_rows)
    vrow = []
    for wv in ch["weights"]:
        acc = {}
        for bi, w in wv.items():
            acc[rows_of_bone[bi]] = acc.get(rows_of_bone[bi], 0) + w
        vrow.append(max(acc, key=acc.get) if acc else 1)
    vrow = np.array(vrow)
    trow = np.array([max(set(rs), key=list(rs).count) for rs in vrow[Tr].tolist()])
    height = float(P[:, 1].max() - P[:, 1].min())
    cell = height / 260

    def farthest(part, side, start):
        pts = [np.array([b["matrix"][k][3] for k in range(3)]) for b in bones if _part(b["name"]) == (part, side)]
        return max(pts, key=lambda q: np.linalg.norm(q - start)) if pts else None
    ends = {"head": farthest("head", None, Jf[19])}
    if ends["head"] is None or np.linalg.norm(ends["head"] - Jf[19]) < 0.05 * height:
        ends["head"] = Jf[19] + np.array([0.0, 1, 0]) * (P[:, 1].max() - Jf[19][1])
    for side, rows in (("L", L), ("R", R_)):
        ends["toe " + side] = farthest("foot", side, Jf[rows("foot")])
        ends["hand " + side] = farthest("hand", side, Jf[rows("hand")])
        ends["fingers " + side] = finger_points(bones, side)
    limbs = {"leg": {sd: (rows("thigh"), rows("shin"), rows("foot")) for sd, rows in (("L", L), ("R", R_))},
             "arm": {sd: (rows("collar"), rows("upper"), rows("fore"), rows("hand")) for sd, rows in (("L", L), ("R", R_))}}

    to_fbx = lambda x: Q.T @ ((np.asarray(x) - W[3][1]) / s) + hips
    if TEMPLATE:
        # Pose the import into the donor's skeleton: joints where the donor's are, limbs in the
        # donor's directions and lengths (linear blend skinning with the import's own weights).
        # The donor's model then fits as it is, with Namco's joints and seams; only its volume
        # becomes the import's (template.py). From here on the model is built on the donor's
        # frames and joints.
        Fd = {r: W[r][0] for r in F}
        Jd = {r: W[r][1] for r in F}
        CH = {1: 19, 3: None, 5: 6, 6: 7, 8: 9, 9: 10, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18}

        def row_map(r):
            fr = FRAME.get(r, r)
            c = CH.get(fr)
            ax, k = None, 1.0
            if c is not None and fr != 1:
                li, ld = np.linalg.norm(J[c] - J[fr]), np.linalg.norm(Jd[c] - Jd[fr])
                ax = F[fr].T @ (J[c] - J[fr]) / max(li, 1e-9)
                k = ld / max(li, 1e-9)
            return fr, ax, k

        # the head at the donor's size, so the donor's face features (eyes, nose, mouth) land on
        # the import's: height of the head above the neck joint, donor vs import
        top_d = 0.0
        for r_, slots in X.bind(m).items():
            if r_ in (19, 20):
                for sl in slots:
                    if sl is not None:
                        p_ = W[sl[0]][0] @ np.array(sl[1], float) + W[sl[0]][1]
                        top_d = max(top_d, W[19][1][1] - p_[1])
        top_i = float(np.linalg.norm(g(ends["head"]) - J[19]))
        head_k = float(np.clip(top_d / max(top_i, 1e-6), 0.5, 1.5))
        log(f"head scaled x{head_k:.2f} to the donor's head")

        def pose(xg, r):
            fr, ax, k = row_map(r)
            loc = (np.atleast_2d(xg) - J[fr]) @ F[fr]
            if ax is not None:
                loc = loc + np.outer(loc @ ax, ax) * (k - 1)
            if fr == 19:
                loc = loc * head_k
            return loc @ Fd[fr].T + Jd[fr]
        Gv = np.array([g(p) for p in P])
        acc = np.zeros_like(Gv)
        wsum = np.zeros(len(Gv))
        rows_used = sorted(set(rows_of_bone))
        for r in rows_used:
            wr = np.array([sum(w for bi, w in wv.items() if rows_of_bone[bi] == r) for wv in ch["weights"]])
            if not wr.any():
                continue
            acc += pose(Gv, r) * wr[:, None]
            wsum += wr
        posed = np.where(wsum[:, None] > 0, acc / np.maximum(wsum, 1e-9)[:, None], Gv)
        P = np.array([to_fbx(p) for p in posed])
        ends["head"] = to_fbx(pose(g(ends["head"]), 19)[0])
        for side, rows in (("L", L), ("R", R_)):
            ends["toe " + side] = to_fbx(pose(g(ends["toe " + side]), rows("foot"))[0])
            ends["hand " + side] = to_fbx(pose(g(ends["hand " + side]), rows("hand"))[0])
        F, J = Fd, Jd
        log("import posed into the donor's skeleton")
    tex = None
    if source is not None:
        keep = np.where(solid)[0] if solid.sum() > 0.5 * len(solid) else np.arange(len(solid))
        sampler = remesh.Sampler(P, Tr, cell)
        Qi = Q.T

        def lookup(pts, sampler=sampler, keep=keep):
            src = sampler.lookup(pts)              # triangle numbers of the solid set -> original
            ok = src[:, 0] >= 0
            src[ok, 0] = keep[src[ok, 0].astype(int)]
            return src
        caster = remesh.Caster(P, Tr, height / 30)
        caster.numbers = keep                          # its triangles' numbers in the source's list
        tex = {"source": source, "lookup": lookup, "caster": caster, "reach": 0.03 * height,
               "to_source": lambda pts: (np.asarray(pts) - W[3][1]) @ Qi.T / s + hips,
               "colours": donor_palette_size(root, model), "push": cell * s * 0.75,
               "cluts": donor_cluts(root, model)}

    # the donor's head height above its neck joint (standing pose, game units)
    head_t3 = 0.0
    for r, slots in X.bind(m).items():
        if r in (19, 20):
            for sl in slots:
                if sl is not None:
                    p = W[sl[0]][0] @ np.array(sl[1], float) + W[sl[0]][1]
                    head_t3 = max(head_t3, W[19][1][1] - p[1])
    # the donor's limb thickness: median distance of each limb row's own vertices from its bone
    # (local X axis), game units
    # (the torso too: spine row 1 along hips -> neck); and the hands' reach from the wrist
    limb_child = {1: 19, 5: 6, 6: 7, 8: 9, 9: 10, 12: 13, 13: 14, 16: 17, 17: 18}
    radius_t3, hand_t3 = {}, {}
    for r, slots in X.bind(m).items():
        own_pts = [np.array(sl[1], float) for sl in slots if sl is not None and sl[0] == r]
        if r in limb_child and own_pts:
            radius_t3[r] = float(np.median([np.hypot(p[1], p[2]) for p in own_pts]))
        if r in (14, 18) and own_pts:
            hand_t3[r] = float(np.percentile([np.linalg.norm(p) for p in own_pts], 90))
    budget = len(m)
    detail = (target or 1000) / 1000
    for attempt in range(8):
        if TEMPLATE:
            # Namco's own topology: the donor's model moved onto the import's surface
            import template
            ends_game = {19: g(ends["head"])}
            for side, (collar, upper, fore, hand) in limbs["arm"].items():
                ends_game[hand] = g(ends["hand " + side])
            for side, (thigh, shin, foot) in limbs["leg"].items():
                ends_game[foot] = g(ends["toe " + side])
            body = template.build(m, X.bind(m), F, J, ends_game, to_fbx, P, Tr, trow, log if attempt == 0 else (lambda *a: None), W=W)
        else:
            body = lowpoly.build(P, Tr, trow, Jf, ends, np.array([0.0, 0, 1]), limbs, detail)
        piece_budget = int(260 * detail)
        if TEMPLATE:                       # what the GPU packet buffer has left after the template
            used_b = sum(PACKET[(1 if len(f["v"]) == 4 else 0) if f.get("hard") else (3 if len(f["v"]) == 4 else 2)]
                         for f in body["faces"])
            # two-sided sheets and the per-piece minimum add more than asked: keep a margin
            piece_budget = max(0, int((MAX_PACKET_BYTES - used_b) / PACKET[2] * 0.45 * detail ** 3))
            if attempt == 0:
                log(f"template packets {used_b} bytes, {piece_budget} triangles left for loose pieces")
        if piece_budget >= 60 and not TEMPLATE:   # (template: pieces have no place in the donor layout yet)
            lowpoly.add_pieces(body, P, Tr, vrow, piece_budget, height, log)
        # Tekken 3 heads are a little large for the body; give the import its donor's proportion
        # Tekken 3 limbs are fuller than most modern models: move each limb's thickness part of
        # the way to the donor's (never thinner, at most 1.6x)
        owners = np.array(body["owner"])
        for r, c in ({} if TEMPLATE else limb_child).items():
            sel_v = owners == r
            if r not in radius_t3 or not sel_v.any():
                continue
            a_, b_ = Jf[r], Jf[c]
            pts = body["positions"][sel_v]
            ax = b_ - a_
            tt = np.clip((pts - a_) @ ax / (ax @ ax), 0, 1)
            base = a_ + tt[:, None] * ax
            ours = s * float(np.median(np.linalg.norm(pts - base, axis=1)))
            k = float(np.clip((radius_t3[r] / max(ours, 1e-6)) ** 0.7, 1.0, 1.6))
            body["positions"][sel_v] = base + (pts - base) * k
            if attempt == 0:
                log(f"row {r}: thickness donor {radius_t3[r]:.0f}, import {ours:.0f} -> x{k:.2f}")
        # hands as big as the donor's (Namco's hands are large and readable), at most 1.5x
        for r in (() if TEMPLATE else (14, 18)):
            sel_v = owners == r
            if r not in hand_t3 or not sel_v.any():
                continue
            pts = body["positions"][sel_v]
            ours = s * float(np.percentile(np.linalg.norm(pts - Jf[r], axis=1), 90))
            k = float(np.clip(hand_t3[r] / max(ours, 1e-6), 1.0, 1.5))
            body["positions"][sel_v] = Jf[r] + (pts - Jf[r]) * k
            if attempt == 0:
                log(f"hand {r}: donor {hand_t3[r]:.0f}, import {ours:.0f} -> x{k:.2f}")
        own_head = s * np.linalg.norm(ends["head"] - Jf[19])
        k = float(np.clip(head_t3 / max(own_head, 1e-6), 1.0, 1.35))
        if attempt == 0:
            log(f"head: donor {head_t3:.0f}, import {own_head:.0f} game units, leg {leg_t3:.0f}")
        if k > 1.01 and not TEMPLATE:
            hv = np.array(body["owner"]) == 19
            body["positions"][hv] = Jf[19] + (body["positions"][hv] - Jf[19]) * k
            if attempt == 0:
                log(f"head scaled x{k:.2f} to the donor's proportion")
        G = np.array([g(p) for p in body["positions"]])
        Nrm = body["normals"] @ Q.T                          # normals to game axes
        try:
            data, report = _write(m, G, Nrm, body["faces"], body["owner"], body["chart_weight"], F, J, row, tex)
        except Budget as e:
            log(f"detail {detail:.2f}: {e}")
            detail *= 0.9
            continue
        if len(data) > budget and not __import__("os").environ.get("T3CB_NOLIMIT"):   # NOLIMIT: offline study only
            log(f"detail {detail:.2f}: {len(data)} bytes, over the donor's {budget}")
            detail *= 0.92
            continue
        report.update(bytes=len(data), budget=budget, scale=s)
        return m, data, report
    raise ValueError("Could not fit the model in the donor's size.")


def donor_cluts(root: Path, model: int) -> dict:
    """The donor's own CLUT room: halfwords filled in CLUT rows 0 and 1, and whether it has an
    8-bit (256-colour) CLUT at id 0 (most donors: the skin palette)."""
    from tim_tool import scan_tims
    rid = X.FIRST_MODEL_RECORD + 4 * model + 2
    arc = X.records(root, [rid])[rid]
    end = {0: 0, 1: 0}
    has8 = False
    for t in scan_tims(arc):
        im = t.image
        if t.mode == 0 and (im.x, im.y, im.width_words, im.height) == (0, 0, 8, 32):
            continue
        if t.clut is not None and t.clut.y in end:
            end[t.clut.y] = max(end[t.clut.y], t.clut.x + t.clut.width_words)
            has8 |= t.mode == 1 and t.clut.y == 0 and t.clut.x == 0
    return {"row0": end[0], "row1": end[1], "has8": has8}


def donor_palette_size(root: Path, model: int) -> int:
    """Colours the imported texture may use: the halfwords the donor's own CLUTs fill in CLUT
    row 0 (16-colour CLUTs at ids 0, 1, 2... then only overwrite the donor's palettes)."""
    from tim_tool import scan_tims
    rid = X.FIRST_MODEL_RECORD + 4 * model + 2
    arc = X.records(root, [rid])[rid]
    end = 0
    for t in scan_tims(arc):
        im = t.image
        if t.mode == 0 and (im.x, im.y, im.width_words, im.height) == (0, 0, 8, 32):
            continue
        if t.clut is not None and t.clut.y == 0:
            end = max(end, t.clut.x + t.clut.width_words)
    return max(16, min(256, end))


def _bake_donor_layout(faces, G, Nrm, tex, side=None):
    """Medea's colours baked into the donor's own texture layout (Namco's UVs, its 8-bit CLUT 0
    area and its 4-bit tiles with their own 16-colour CLUTs), quantised to those CLUTs."""
    import texture_bake as TB
    mats = sorted({f["dmat"] for f in faces})
    chart_of = {m_: i for i, m_ in enumerate(mats)}
    for f in faces:
        f["chart"] = chart_of[f["dmat"]]
    # texel coordinates in 4-bit columns of the page (an 8-bit texel is a column pair)
    cuv = [np.array([(u * 2 if f["dmat"] & 0x8000 else u, v) for u, v in f["duv"]], float) for f in faces]
    # mirrored texels (Namco shares texels between left and right arm, leg, half face): only
    # one side is baked, or the import's two different sides would be averaged (grey arms)
    skip = set()
    if side is not None:
        key = {}
        for i, f in enumerate(faces):
            key.setdefault((f["dmat"], tuple(sorted(map(tuple, cuv[i].round().astype(int).tolist())))), []).append(i)
        for ids in key.values():
            if len(ids) < 2:
                continue
            sd = [float((G[faces[i]["v"]].mean(0) - side[0]) @ side[1]) for i in ids]
            if max(sd) > 0 and min(sd) < 0:
                skip.update(i for i, d in zip(ids, sd) if d < 0)
    # ...unless there is room: the mirrored side gets its own copy of the texels in the page's
    # free space (Namco's layout fills about 60 % of it), so both sides keep their own colours
    if skip:
        occ = np.zeros((256, 256), bool)
        box = {}
        for i, f in enumerate(faces):
            lo = np.floor(cuv[i].min(0)).astype(int) - 1
            hi = np.ceil(cuv[i].max(0)).astype(int) + 1
            if f["dmat"] & 0x8000:
                hi[0] += 1
            box[i] = (lo, hi)
            if i not in skip:
                occ[max(lo[1], 0):hi[1] + 1, max(lo[0], 0):hi[0] + 1] = True
        # groups of mirrored faces whose texel boxes touch (one tile each)
        sk = sorted(skip)
        par = {i: i for i in sk}

        def fnd(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for a_ in sk:
            for b_ in sk:
                if a_ < b_ and faces[a_]["dmat"] == faces[b_]["dmat"]:
                    (l1, h1), (l2, h2) = box[a_], box[b_]
                    if (l1 <= h2).all() and (l2 <= h1).all():
                        par[fnd(a_)] = fnd(b_)
        groups = {}
        for i in sk:
            groups.setdefault(fnd(i), []).append(i)
        moved = 0
        new_clut = {}
        for ids in sorted(groups.values(), key=lambda g_: -len(g_)):
            lo = np.min([box[i][0] for i in ids], 0)
            hi = np.max([box[i][1] for i in ids], 0)
            w_, h_ = hi - lo + 1
            spot = None
            for y in range(0, 256 - h_ + 1, 2):
                for x in range(0, 256 - w_ + 1, 4):
                    if not occ[y:y + h_, x:x + w_].any():
                        spot = (x, y)
                        break
                if spot:
                    break
            if spot is None:
                continue
            off = np.array(spot) - lo
            occ[spot[1]:spot[1] + h_, spot[0]:spot[0] + w_] = True
            m0 = faces[ids[0]]["dmat"]
            if not m0 & 0x8000:                # a 4-bit copy gets a CLUT of its own (ids after the
                if m0 not in new_clut:         # donor's: free room in the player's CLUT row)
                    new_clut[m0] = max(f_["dmat"] for f_ in faces if not f_["dmat"] & 0x8000) + 1
            for i in ids:
                cuv[i] = cuv[i] + off
                skip.discard(i)
                if m0 in new_clut:
                    faces[i]["dmat"] = new_clut[m0]
                moved += 1
        if moved:
            print(f"mirrored side: {moved} polygons got texels of their own, {len(new_clut)} new CLUTs")
        mats = sorted({f["dmat"] for f in faces})
        chart_of = {m_: i for i, m_ in enumerate(mats)}
        for f in faces:
            f["chart"] = chart_of[f["dmat"]]
    tris, tri_uv, tri_chart = [], [], []
    for i, f in enumerate(faces):
        if i in skip:
            continue
        v = f["v"]
        for a, b, c in ([(0, 1, 2)] + ([(1, 3, 2)] if len(v) == 4 else [])):
            tris.append([v[a], v[b], v[c]])
            tri_uv.append([cuv[i][a], cuv[i][b], cuv[i][c]])
            tri_chart.append(f["chart"])
    tris = np.array(tris)
    tri_uv = np.array(tri_uv)
    if False:
        cen_uv = tri_uv.mean(1)
        sd = (G[tris].mean(1) - side[0]) @ side[1]
        drop = np.zeros(len(tris), bool)
        for i in np.where(sd < 0)[0]:
            near = np.where((np.abs(cen_uv - cen_uv[i]).max(1) < 1.5) & (sd > 0))[0]
            drop[i] = len(near) > 0
        keep_t = ~drop
        tris, tri_uv = tris[keep_t], tri_uv[keep_t]
        tri_chart = list(np.array(tri_chart)[keep_t])
    tri_n = np.cross(G[tris[:, 1]] - G[tris[:, 0]], G[tris[:, 2]] - G[tris[:, 0]])
    rgb, _, owner = TB.bake(tris, G, tri_uv, tex["to_source"], tex["lookup"], tex["source"],
                            tri_n, tri_chart, tex["push"], tex.get("caster"), tex.get("reach", 0.0), Nrm)
    st = dict(TEXTURE_STYLE)
    flat = TB.flatten(rgb, owner, st["flat_radius"], st["flat_strength"])
    styled = TB.stylise(flat, owner, st["k"], st["shade"], st["passes"], st["size"], st["merge"], st["light"])
    eight = [chart_of[m_] for m_ in mats if m_ & 0x8000]
    keep = np.isin(owner, eight)                        # 8-bit areas (face, skin) keep detail
    rgb = TB.vivid(np.where(keep[..., None], rgb, styled))
    band = np.zeros((256, 64), dtype=np.uint16)
    runs = []
    shown = np.zeros_like(rgb)
    to_rgb = lambda pal: np.array([[(c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3] for c in pal], np.uint8)
    four = [m_ for m_ in mats if not m_ & 0x8000]
    idx4 = np.zeros(owner.shape, dtype=np.uint8)
    pal4 = {}
    for m_ in four:
        sel = owner == chart_of[m_]
        pal = TB._palette16(rgb[sel].astype(float)) if sel.any() else np.full((16, 3), 128.0)
        if sel.any():
            idx4[sel] = TB._nearest(rgb[sel].astype(float), pal)[0]
        pal4[m_] = [TB.ps1_colour(*c) for c in pal]
        shown[sel] = to_rgb(pal4[m_])[idx4[sel]]
    m4 = np.isin(owner, [chart_of[m_] for m_ in four])
    band[:] = TB.band4(np.where(m4, idx4, 0))
    eight_mats = [m_ for m_ in mats if m_ & 0x8000]
    if eight_mats:
        idx8, pm, pal8 = TB.face8(rgb, owner, eight)
        band = TB.band8_into(band, idx8, pm)
        shown8 = np.repeat(to_rgb(pal8)[idx8], 2, axis=1)
        sel8 = np.repeat(pm, 2, axis=1)
        shown[sel8] = shown8[sel8]
        runs.append(((eight_mats[0] & 0x7fff), pal8))
    # 4-bit CLUTs: one run per block of consecutive ids
    ids = sorted(pal4)
    start = None
    for j, m_ in enumerate(ids):
        if start is None:
            start, colours = m_, []
        colours += pal4[m_]
        if j + 1 == len(ids) or ids[j + 1] != m_ + 1:
            runs.append((start, colours))
            start = None
    uvs = [[(u, v) for u, v in c] for c in cuv]
    return {"uv": uvs, "rgb": shown, "band": band, "runs": runs, "mats": {chart_of[m_]: m_ for m_ in mats},
            "palette": [c for _, p in runs for c in p], "charts": len(mats), "density": 0.0, "face8": bool(eight_mats)}


def _write(m, G, Nrm, faces, vrows, chart_weight, F, J, row, tex=None, blend=None, zsign=1):
    """The 3DMK model for faces (3 or 4 vertex ids, triangle (0, 1, 2) facing out) over the
    vertices G (game coordinates, T-pose), owned by rows vrows, gouraud shaded with the vertex
    normals Nrm. Each face is drawn by the latest row among its vertices; vertices of earlier rows
    are borrowed through the cache."""
    order = {r: i for i, r in enumerate(DRAW)}
    draw = [max((vrows[v] for v in f["v"]), key=lambda r: order[r]) for f in faces]
    by_row = {}
    for i, r in enumerate(draw):
        by_row.setdefault(r, []).append(i)
    texture = None
    if isinstance(tex, dict) and "ready" in tex:     # kitbash: texture already assembled
        texture = tex["ready"]
    elif tex and all("duv" in f for f in faces):
        texture = _bake_donor_layout(faces, G, Nrm, tex, side=(J[1], F[1][:, 2]))
    elif tex:
        import texture_bake as TB
        chart = [f["chart"] for f in faces]
        flat = [np.array(f["flat"], float) * chart_weight[f["chart"]] ** 0.5 for f in faces]
        face = [c for c, w in chart_weight.items() if w >= 4]
        # Namco's way when the donor has the room: the face 8-bit with the 256-colour CLUT 0
        # (row 0), everything else 4-bit with 16-colour CLUTs in row 1 (ids 64+)
        cl = tex.get("cluts", {})
        mode8 = bool(face) and cl.get("has8") and cl.get("row0", 0) >= 256 and cl.get("row1", 0) >= 32
        tuv, density = TB.pack_faces(chart, flat, wide=set(face) if mode8 else ())
        tris, tri_uv, tri_chart, tri_n = [], [], [], []
        for i, f in enumerate(faces):
            v = f["v"]
            for a, b, c in ([(0, 1, 2)] + ([(1, 3, 2)] if len(v) == 4 else [])):
                tris.append([v[a], v[b], v[c]])
                tri_uv.append([tuv[i][a], tuv[i][b], tuv[i][c]])
                tri_chart.append(f["chart"])
        tris = np.array(tris)
        tri_n = np.cross(G[tris[:, 1]] - G[tris[:, 0]], G[tris[:, 2]] - G[tris[:, 0]])
        rgb, _, owner = TB.bake(tris, G, np.array(tri_uv), tex["to_source"], tex["lookup"], tex["source"],
                                tri_n, tri_chart, tex["push"], tex.get("caster"), tex.get("reach", 0.0), Nrm)
        keep_face = np.isin(owner, face)                  # the face keeps its fine detail
        st = dict(TEXTURE_STYLE)
        import os, json
        st.update(json.loads(os.environ.get("T3CB_STYLE", "{}")))     # for comparing styles offline
        flat = TB.flatten(rgb, owner, st["flat_radius"], st["flat_strength"])
        styled = TB.stylise(flat, owner, st["k"], st["shade"], st["passes"], st["size"], st["merge"], st["light"])
        # the face crisp, as Namco paints faces: sharpened (eyes, brows, lips) and a little
        # more contrast, inside the face chart only
        from PIL import Image as _I, ImageFilter as _F
        sharp = np.asarray(_I.fromarray(rgb).filter(_F.UnsharpMask(radius=1.0, percent=60, threshold=10)))
        sharp = np.clip((sharp.astype(float) - 128) * 1.06 + 128, 0, 255).astype(np.uint8)
        rgb = np.where(keep_face[..., None], sharp, styled)
        rgb = TB.vivid(rgb)
        to_ps1 = lambda pal: np.array([[(c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3] for c in pal], dtype=np.uint8)
        if mode8:
            rest = np.where(np.isin(owner, face), -1, owner)
            idx, palette, group = TB.quantise_groups(rgb, rest, cl["row1"] // 16)
            idx8, pm, pal8 = TB.face8(rgb, owner, face)
            band = TB.band8_into(TB.band4(np.where(rest >= 0, idx, 0)), idx8, pm)
            shown = to_ps1(palette)[np.asarray(group)[np.maximum(rest, 0)] * 16 + idx] * (rest >= 0)[..., None]
            shown8 = np.repeat(to_ps1(pal8)[idx8], 2, axis=1)
            shown[np.repeat(pm, 2, axis=1)] = shown8[np.repeat(pm, 2, axis=1)]
            mats = {c: (0x8000 if c in face else 64 + int(group[c])) for c in range(max(chart) + 1)}
            runs = [(0, pal8), (64, palette)]
        else:
            idx, palette, group = TB.quantise_groups(rgb, owner, tex["colours"] // 16, own=face)
            shown = to_ps1(palette)[np.asarray(group)[np.maximum(owner, 0)] * 16 + idx] * (owner >= 0)[..., None]
            band = TB.band4(idx)
            mats = {c: int(group[c]) for c in range(max(chart) + 1)}
            runs = [(0, palette)]
        texture = {"uv": tuv, "rgb": shown.astype(np.uint8), "band": band, "runs": runs, "mats": mats,
                   "palette": [c for _, p in runs for c in p], "charts": max(chart) + 1, "density": density,
                   "face8": bool(mode8)}

    # the texture coordinates each polygon really stores (an 8-bit texel is a column pair)
    def uv_keys(i):
        if texture is None:
            return [(0, 0)]
        m8 = texture["mats"][faces[i]["chart"]] & 0x8000
        return [((int(u) // 2 if m8 else int(u)) & 255, int(v) & 255) for u, v in texture["uv"][i]]

    def uv_need(part):
        return len({k for i in part for k in uv_keys(i)})

    # the torso, pelvis and head spill into their second layer when one row cannot hold them
    for main, second in SECOND.items():
        ts = by_row.get(main, [])
        verts = {v for i in ts for v in faces[i]["v"]}
        if len(verts) > MAX_NORMALS or len(ts) > MAX_TRIS or uv_need(ts) > MAX_UVS:
            ts.sort(key=lambda i: G[faces[i]["v"]].mean(0)[1])
            # split where the two halves need about as many vertices (normals) each
            def need(part):                  # the tighter of the two per-row limits
                nv = (len({v for i in part if not faces[i].get("hard") for v in faces[i]["v"]})
                      + 0.5 * sum(1 for i in part if faces[i].get("hard"))) / MAX_NORMALS
                nu = uv_need(part) / MAX_UVS
                return max(nv, nu)
            best = min(range(1, len(ts)), key=lambda h: max(need(ts[:h]), need(ts[h:])))
            by_row[main], by_row[second] = ts[:best], ts[best:]
            if __import__("os").environ.get("T3CB_DEBUG"):
                print(f"split row {main}: {len(ts)} polys, uv {uv_need(ts[:best])}+{uv_need(ts[best:])}, need {need(ts[:best]):.2f}/{need(ts[best:]):.2f}")

    # vertex lists per row: own (owner's frame) and borrowed (cache)
    own, borrow = {}, {}
    for r, ts in by_row.items():
        for i in ts:
            for v in faces[i]["v"]:
                o = vrows[v]
                if frame_row(o) == frame_row(r):
                    lst = own.setdefault(r, [])
                else:
                    lst = borrow.setdefault(r, [])
                if v not in lst:
                    lst.append(v)
    deposit = {}
    for r, vs in borrow.items():
        for v in vs:
            o = vrows[v]
            if o not in own or v not in own[o]:
                own.setdefault(o, []).append(v)
            deposit.setdefault(o, set()).add(v)
    # Namco's 50/50 joint seams: a blend vertex v (owned by the later row b) is also placed in
    # an earlier row a, which deposits half of it (tail group 3, flag); row b reads it back with
    # tail group 0 and the flag: slot = own / 2 + stored half, the vertex halfway between the two
    # bones' transforms, and stores the full result for later rows. Only b and later draw it.
    blend = {v: a for v, a in (blend or {}).items() if order.get(a, 99) < order.get(vrows[v], -1)
             and v in own.get(vrows[v], [])}
    half = {}
    for v, a in blend.items():
        half.setdefault(a, []).append(v)
        own.setdefault(a, [])
        deposit.get(vrows[v], set()).discard(v)        # group 0 stores it, no second deposit
    first = {v: order[vrows[v]] for vs in deposit.values() for v in vs}
    for v, a in blend.items():
        first[v] = order[a]
    last = {}
    for r, vs in borrow.items():
        for v in vs:
            last[v] = max(last.get(v, -1), order[r])
    for v in blend:
        last[v] = max(last.get(v, -1), order[vrows[v]])
    entry, free_at = {}, {}
    for v in sorted(first, key=lambda v: (first[v], last[v])):
        reg = next((e for e in range(1, 128) if free_at.get(e, -1) < first[v]), None)
        if reg is None:
            raise Budget("more than 127 seam vertices in use at once")
        entry[v] = reg
        free_at[reg] = last[v]
    for r in list(own):
        by_row.setdefault(r, [])
        dep = deposit.get(r, set())
        reads = [v for v in own[r] if v in blend]
        own[r] = reads + [v for v in own[r] if v in dep and v not in blend] +             [v for v in own[r] if v not in dep and v not in blend]

    blocks = bytearray()
    header = X.MODEL_HEADER

    def put(b):
        off = header + len(blocks)
        blocks.extend(pad4(b))
        return off

    rows = [list(row(m, r)) for r in range(27)]
    for r in range(27):
        w = rows[r]
        w[0] = w[1] = w[2] = w[12] = w[13] = 0
        if r >= 1:
            w[10] = 0
        if r in (2, 4, 20) or r >= 21:
            w[3:12] = [0, 0, 0, -1, 0, 0, 0, 0, 0]
    import anim_model as A
    for r, pr in A.ROW_PARENT.items():
        if pr == 0:
            continue
        o = F[pr].T @ (J[r] - J[pr])
        o[2] *= zsign
        rows[r][3:6] = [int(round(x)) for x in o]
    rows[0][0] = put(struct.pack("<6I", 4, 0, 0, 0, 0, 0))
    rows[0][1] = put(struct.pack("<4I", 0, 0, 0, 0))
    rows[0][2] = put(struct.pack("<HH", 2, 2) + bytes(4))
    report = {"rows": {}, "polygons": 0, "triangles": 0}
    for r in DRAW:
        ts = by_row.get(r, [])
        if not ts and r not in own:
            continue
        fr = frame_row(r)
        Rf, Jf = F[fr], J[fr]
        verts = own.get(r, [])
        reads = [v for v in verts if v in blend]
        dep = [v for v in verts if v in deposit.get(r, set()) and v not in blend]
        halves = half.get(r, [])
        # own list: blend reads (group 0), full deposits then half deposits (group 3), the rest;
        # the half copies sit after the full deposits and are not drawn by this row
        verts = reads + dep + [("h", v) for v in halves] + [v for v in verts if v not in reads and v not in dep]
        slots = [("b", v) for v in borrow.get(r, [])] + [v if isinstance(v, tuple) else ("o", v) for v in verts]
        if len(slots) > MAX_SLOTS:
            raise Budget(f"row {r} needs {len(slots)} vertex slots")
        index = {sv: i for i, sv in enumerate(slots)}
        slot_of = lambda v: index.get(("b", v), index.get(("o", v)))
        pos_of = lambda v: G[v[1]] if isinstance(v, tuple) else G[v]
        local = [Rf.T @ (pos_of(v) - Jf) for v in verts]
        if any(abs(x) > 32767 for p in local for x in p):
            raise Budget(f"row {r}: vertex out of range")
        vb = struct.pack("<I", 2 * (1 + len(borrow.get(r, []))))
        vb += struct.pack("<I", 0)
        g2 = bytes(2 * entry[v] for v in borrow.get(r, []))
        vb += struct.pack("<I", len(g2)) + pad4(g2)
        vb += struct.pack("<I", len(verts)) + b"".join(struct.pack("<4h", *[int(round(x)) for x in p], 0) for p in local)
        vb += pack_fields([0x100 | 2 * entry[v] for v in reads], 9) + pack_fields([], 9) * 2
        vb += pack_fields([2 * entry[v] for v in dep] + [0x100 | 2 * entry[v] for v in halves], 9)
        vb += pack_fields([], 9) + pack_fields([], 2)
        # normals: one per vertex the row draws, in the row's frame (unit 4096), deduplicated
        # (a flat-shaded polygon, "hard", has one normal of its own: the face's)
        normals, nidx, nface = [], {}, {}

        def norm_index(nl):
            # snapped to 1/8 steps first, so nearly equal normals are stored once (the light
            # difference is invisible; it saves bytes in the donor's model slot)
            u = np.round(np.asarray(nl) / (np.linalg.norm(nl) + 1e-12) * 8) / 8
            q = tuple(int(round(x * 4096 / (np.linalg.norm(u) + 1e-12))) for x in u)
            if q not in normals:
                normals.append(q)
            return normals.index(q)
        for i in ts:
            if not faces[i].get("hard"):
                for v in faces[i]["v"]:
                    if v not in nidx:
                        nidx[v] = norm_index(Rf.T @ Nrm[v])
        for i in ts:                         # flat polygons reuse a normal within 20 degrees
            if faces[i].get("hard"):
                p3 = G[faces[i]["v"][:3]]
                nl = Rf.T @ np.cross(p3[1] - p3[0], p3[2] - p3[0])
                nl = nl / (np.linalg.norm(nl) + 1e-12)
                if normals:
                    arr = np.array(normals, float) / 4096
                    j = int(np.argmax(arr @ nl))
                    if arr[j] @ nl > 0.94:
                        nface[i] = j
                        continue
                nface[i] = norm_index(nl)
        if len(normals) > MAX_NORMALS:
            raise Budget(f"row {r} needs {len(normals)} normals")
        nb = struct.pack("<4I", 4, 0, 0, len(normals)) + b"".join(struct.pack("<4h", *q, 0) for q in normals) + bytes(8)
        # polygons: gouraud triangles (family 2) and quads (family 3). Stored mirrored, corners
        # (0, 2, 1[, 3]): the game draws a triangle whose cross(b - a, c - a) points inwards.
        fam = {0: [], 1: [], 2: [], 3: []}
        for i in ts:
            quad = len(faces[i]["v"]) == 4
            fam[(1 if quad else 0) if faces[i].get("hard") else (3 if quad else 2)].append(i)
        if max(len(x) for x in fam.values()) > MAX_TRIS:
            raise Budget(f"row {r} has too many polygons")
        pb = b""
        mats, uvs, tex_entries = [], [], {0: [], 1: [], 2: [], 3: []}
        for k in (0, 1, 2, 3):
            pb += struct.pack("<I", len(fam[k]))
            for i in fam[k]:
                v = faces[i]["v"]
                corners = [0, 2, 1] if k in (0, 2) else [0, 2, 1, 3]
                sl = [slot_of(v[c]) for c in corners]
                w0 = sl[0] * 4 | (sl[1] * 4) << 7 | (sl[2] * 4) << 14
                if k in (1, 3):
                    w0 |= (sl[3] * 4) << 23
                if k < 2:
                    pb += struct.pack("<II", w0, (nface[i] + 1) * 4)
                else:
                    nn = [(nidx[v[c]] + 1) * 4 for c in corners]
                    if k == 2:
                        pb += struct.pack("<II", w0, nn[0] | nn[1] << 7 | nn[2] << 16)
                    else:
                        pb += struct.pack("<III", w0, nn[0], nn[1] | nn[2] << 7 | nn[3] << 16)
                mat = texture["mats"][faces[i]["chart"]] if texture is not None else 0
                eight = bool(mat & 0x8000)
                if mat not in mats:
                    mats.append(mat)
                ui = []
                for c in corners:
                    u, vv = texture["uv"][i][c] if texture is not None else (0, 0)
                    if eight:
                        u = int(u) // 2                    # 8-bit texels are column pairs
                    e = (int(u) & 255) | ((int(vv) & 255) << 8)
                    if e not in uvs:
                        uvs.append(e)
                    ui.append(uvs.index(e))
                if len(uvs) > MAX_UVS:
                    raise Budget(f"row {r} needs more than {MAX_UVS} texture coordinates")
                tex_entries[k].append(bytes([mats.index(mat)] + ui))
        if len(uvs) > MAX_UVS:
            raise Budget(f"row {r} needs {len(uvs)} texture coordinates")
        cb = struct.pack("<H", 2 + 2 * len(mats)) + b"".join(struct.pack("<H", x) for x in mats)
        cb += struct.pack("<H", 2 + 2 * len(uvs)) + b"".join(struct.pack("<H", e) for e in uvs)
        for k in (0, 1, 2, 3):
            cb += bytes([len(fam[k])]) + b"".join(tex_entries[k])
        w = rows[r]
        w[0] = put(nb)
        w[1] = put(pb)
        w[2] = put(cb)
        w[10] = 1
        if r in (2, 4):
            w[6] = 0
        if r == 20:
            w[3:12] = list(rows[19][3:12])
        rows[r - 1][12] = put(vb)
        report["polygons"] += len(ts)
        report["triangles"] += len(fam[0]) + len(fam[2]) + 2 * (len(fam[1]) + len(fam[3]))
        report["rows"][r] = {"fam": [len(fam[k]) for k in range(4)], "own": len(verts),
                             "borrowed": len(borrow.get(r, [])), "normals": len(normals), "uvs": len(uvs)}
    packets = sum(sum(PACKET[k] * v["fam"][k] for k in range(4)) for v in report["rows"].values())
    if packets > MAX_PACKET_BYTES:
        raise Budget(f"{packets} bytes of GPU packets, the game allows about {MAX_PACKET_BYTES}")
    report["packet_bytes"] = packets
    hdr = struct.pack("<6I", 27, struct.unpack_from("<I", m, 4)[0], 0x4B4D4433, 0, header - 8, 0)
    body = b"".join(struct.pack("<14i", *rows[r]) for r in range(27))
    data = hdr + body + bytes(blocks)
    report["cache_entries"] = max(entry.values(), default=0)
    if texture is not None:
        report["texture"] = texture
    return data, report


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("fbx", type=Path)
    ap.add_argument("--model", type=int, required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--target", type=int)
    a = ap.parse_args()
    X.setup(a.root)
    stock, new, report = build(a.root, a.model, a.fbx, a.target)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tx = report.pop("texture", None)
    a.out.write_bytes(X.own_model_file(a.model, stock, new, tx))
    if tx is not None:
        from PIL import Image
        Image.fromarray(tx["rgb"]).save(a.out.with_suffix(".atlas.png"))
        print(f"texture: {tx['charts']} charts, {len(tx['palette'])} colours, {tx['density']:.3f} texels per unit")
    print(json.dumps(report, default=float))
    print(f"OK own model over model {a.model}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
