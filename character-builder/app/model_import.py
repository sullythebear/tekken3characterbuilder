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
    n = name.split(":")[-1].lower().replace("_", "").replace(" ", "").replace(".", "")
    side = None
    for pre, s in (("left", "L"), ("right", "R")):
        if n.startswith(pre):
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
            to_fbx = lambda x: Q.T @ ((np.asarray(x) - W[3][1]) / s) + hips
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
        if piece_budget >= 60:            # too little room: leave the loose pieces out
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


def _write(m, G, Nrm, faces, vrows, chart_weight, F, J, row, tex=None):
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
    if tex:
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
    first = {v: order[vrows[v]] for vs in deposit.values() for v in vs}
    last = {}
    for r, vs in borrow.items():
        for v in vs:
            last[v] = max(last.get(v, -1), order[r])
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
        own[r] = [v for v in own[r] if v in dep] + [v for v in own[r] if v not in dep]

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
        slots = [("b", v) for v in borrow.get(r, [])] + [("o", v) for v in own.get(r, [])]
        if len(slots) > MAX_SLOTS:
            raise Budget(f"row {r} needs {len(slots)} vertex slots")
        index = {sv: i for i, sv in enumerate(slots)}
        slot_of = lambda v: index.get(("b", v), index.get(("o", v)))
        verts = own.get(r, [])
        local = [Rf.T @ (G[v] - Jf) for v in verts]
        if any(abs(x) > 32767 for p in local for x in p):
            raise Budget(f"row {r}: vertex out of range")
        dep = [v for v in verts if v in deposit.get(r, set())]
        vb = struct.pack("<I", 2 * (1 + len(borrow.get(r, []))))
        vb += struct.pack("<I", 0)
        g2 = bytes(2 * entry[v] for v in borrow.get(r, []))
        vb += struct.pack("<I", len(g2)) + pad4(g2)
        vb += struct.pack("<I", len(verts)) + b"".join(struct.pack("<4h", *[int(round(x)) for x in p], 0) for p in local)
        vb += pack_fields([], 9) * 3 + pack_fields([2 * entry[v] for v in dep], 9) + pack_fields([], 9) + pack_fields([], 2)
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
