"""Own 3D models (phase 2): an FBX character -> a Tekken 3 PS1 3DMK model over a donor's.

Pipeline: read the FBX (fbx.py) -> one closed skin (remesh.py) -> simplify to the donor's size
budget (decimate.py) -> skin weights -> Tekken 3 rows -> local frames that match the donor's
(so the donor's animations pose it the same way) -> the binary blocks.

Format notes (NOTES.md "Own 3D models"): a row's vertex block sits in the previous row's word 12;
own vertices 4 x s16 in the row's frame; the vertices of earlier rows are borrowed through the
cache (the owner deposits them with tail group 3, the reader lists the entry in g2; entry 0 is
never used). Polygons here are flat textured triangles (family 0): u32 slot x 4 at shifts 0, 7,
14; u32 (normal list index + 1) x 4. A triangle faces the camera when cross(b - a, c - a) points
into the body; its normal (unit 4096) points out."""
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
    import decimate
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
    s = leg_t3 / leg_fbx
    g = lambda x: s * (Q @ (np.asarray(x) - hips)) + W[3][1]       # FBX -> game, hips on the root

    # joints (game) and the frames: the donor's standing frames, turned so each limb runs
    # along the imported limb (shortest rotation), e.g. T-pose arms
    J = {1: g(hips), 3: g(hips)}
    for side, rows in (("L", L), ("R", R_)):
        for part, key in (("collar", "shoulder"), ("upper", "arm"), ("fore", "forearm"), ("hand", "hand"),
                          ("thigh", "upleg"), ("shin", "leg"), ("foot", "foot")):
            pos = joint(bones, part, side)
            if pos is None:
                raise ValueError(f"No {side} {part} bone found in the skeleton.")
            J[rows(part)] = g(pos)
    neck = joint(bones, "head")
    J[19] = g(neck)
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

    # one closed skin, simplified
    rm = remesh.remesh(P, Tr, 200)
    log(f"remeshed: {len(rm['positions'])} vertices")
    rows_of_bone = bone_rows(bones, left_rows)
    Wt = ch["weights"]

    def vertex_rows(src):
        out = []
        for t, u, v in src:
            acc = {}
            if t >= 0:
                a, b, c = Tr[int(t)]
                for vert, f in ((a, 1 - u - v), (b, u), (c, v)):
                    for bi, w in Wt[vert].items():
                        r = rows_of_bone[bi]
                        acc[r] = acc.get(r, 0) + w * f
            out.append(max(acc, key=acc.get) if acc else 1)
        return out

    donor_tris = donor_triangles(m, W)
    budget = len(m)
    tgt = target or 900
    for attempt in range(8):
        pos, used, tris, merged = decimate.decimate(rm["positions"], rm["triangles"], tgt)
        vrows = vertex_rows(rm["source"])
        try:
            data, report = _write(m, pos, tris, vrows, F, J, g, W, donor_tris, row)
        except Budget as e:
            log(f"{tgt} triangles: {e}")
            tgt = int(tgt * 0.9)
            continue
        if len(data) > budget:
            log(f"{tgt} triangles: {len(data)} bytes, over the donor's {budget}")
            tgt = int(tgt * min(0.95, budget / len(data)))
            continue
        report.update(triangles=len(tris), bytes=len(data), budget=budget, scale=s)
        return m, data, report
    raise ValueError("Could not fit the model in the donor's size.")


def _write(m, pos, tris, vrows, F, J, g, W, donor_tris, row):
    order = {r: i for i, r in enumerate(DRAW)}
    G = np.array([g(p) for p in pos])                 # game coordinates (T-pose)
    # outward normals: the remesh winding is consistent; find which way it points
    a, b, c = G[tris[:, 0]], G[tris[:, 1]], G[tris[:, 2]]
    n = np.cross(b - a, c - a)
    centre = G[np.unique(tris)].mean(0)
    if (np.einsum("ij,ij->i", n, (a + b + c) / 3 - centre) > 0).mean() < 0.5:
        tris = tris[:, [0, 2, 1]]
        n = -n
    # each triangle is drawn by the latest row among its vertices
    draw = [max((vrows[v] for v in t), key=lambda r: order[r]) for t in tris]
    by_row = {}
    for i, r in enumerate(draw):
        by_row.setdefault(r, []).append(i)
    # spill the torso, pelvis and head into their second layer when one row cannot hold them
    for main, second in SECOND.items():
        ts = by_row.get(main, [])
        if len(ts) > MAX_TRIS or len({v for i in ts for v in tris[i]}) > MAX_SLOTS - 8:
            ts.sort(key=lambda i: G[tris[i]].mean(0)[1])
            half = len(ts) // 2
            by_row[main], by_row[second] = ts[:half], ts[half:]
    # vertex lists per row: own (owner's frame) and borrowed (cache)
    own, borrow = {}, {}
    for r, ts in by_row.items():
        for i in ts:
            for v in tris[i]:
                o = vrows[v]
                if frame_row(o) == frame_row(r):
                    own.setdefault(r, [])
                    if v not in own[r]:
                        own[r].append(v)
                else:
                    borrow.setdefault(r, [])
                    if v not in borrow[r]:
                        borrow[r].append(v)
    # vertices owned by a row but only used elsewhere still have to be deposited by their owner
    deposit = {}
    for r, vs in borrow.items():
        for v in vs:
            o = vrows[v]
            if o not in own or v not in own[o]:
                own.setdefault(o, []).append(v)
            deposit.setdefault(o, set()).add(v)
    # cache entries (1..127) by live range: deposit time -> last reader
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
    for r in by_row:
        dep = deposit.get(r, set())
        own[r] = [v for v in own.get(r, []) if v in dep] + [v for v in own.get(r, []) if v not in dep]
    for r in own:
        if r not in by_row:
            by_row[r] = []
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
    # offsets from the parent, in the parent's frame
    import anim_model as A
    for r, pr in A.ROW_PARENT.items():
        if pr == 0:
            continue
        o = F[pr].T @ (J[r] - J[pr])
        rows[r][3:6] = [int(round(x)) for x in o]
    # row 0: empty blocks, as in every stock model
    rows[0][0] = put(struct.pack("<6I", 4, 0, 0, 0, 0, 0))
    rows[0][1] = put(struct.pack("<4I", 0, 0, 0, 0))
    rows[0][2] = put(struct.pack("<HH", 2, 2) + bytes(4))
    report = {"rows": {}}
    for r in DRAW:
        ts = by_row.get(r, [])
        if not ts and r not in own:
            continue
        fr = frame_row(r)
        Rf, Jf = F[fr], J[fr]
        slots = [("b", v) for v in borrow.get(r, [])] + [("o", v) for v in own.get(r, [])]
        if len(slots) > MAX_SLOTS:
            raise Budget(f"row {r} needs {len(slots)} vertex slots")
        if len(ts) > MAX_TRIS:
            raise Budget(f"row {r} has {len(ts)} triangles")
        index = {sv: i for i, sv in enumerate(slots)}
        slot_of = lambda v: index.get(("b", v), index.get(("o", v)))
        # vertices
        verts = own.get(r, [])
        local = [Rf.T @ (G[v] - Jf) for v in verts]
        if any(abs(x) > 32767 for p in local for x in p):
            raise Budget(f"row {r}: vertex out of range")
        dep = [v for v in verts if v in deposit.get(r, set())]
        vb = struct.pack("<I", 2 * (1 + 0 + len(borrow.get(r, []))))
        vb += struct.pack("<I", 0)
        g2 = bytes(2 * entry[v] for v in borrow.get(r, []))
        vb += struct.pack("<I", len(g2)) + pad4(g2)
        vb += struct.pack("<I", len(verts)) + b"".join(struct.pack("<4h", *[int(round(x)) for x in p], 0) for p in local)
        vb += pack_fields([], 9) * 3 + pack_fields([2 * entry[v] for v in dep], 9) + pack_fields([], 9) + pack_fields([], 2)
        # normals (local, outward, deduplicated)
        normals, nidx = [], []
        for i in ts:
            nn = Rf.T @ n[i]
            nn = nn / (np.linalg.norm(nn) + 1e-12)
            q = tuple(int(round(x * 4096)) for x in nn)
            key = tuple(int(round(x * 6)) for x in nn)
            found = next((k for k, (kk, _) in enumerate(normals) if kk == key), None)
            if found is None:
                normals.append((key, q))
                found = len(normals) - 1
            nidx.append(found)
        if len(normals) > MAX_NORMALS:
            raise Budget(f"row {r} needs {len(normals)} normals")
        nb = struct.pack("<4I", 4, 0, 0, len(normals)) + b"".join(struct.pack("<4h", *q, 0) for _, q in normals) + bytes(8)
        # polygons: stored corner order (a, c, b) so that cross(b - a, c - a) points inwards
        pb = struct.pack("<I", len(ts))
        mats, uvs, tex = [], [], []
        cands = donor_tris.get(fr, []) or [t for v in donor_tris.values() for t in v]
        cen_d = np.array([c for c, _, _ in cands])
        for k, i in enumerate(ts):
            t0, t1, t2 = tris[i]
            corners = [t0, t2, t1]
            sl = [slot_of(v) for v in corners]
            pb += struct.pack("<II", (sl[0] * 4) | (sl[1] * 4) << 7 | (sl[2] * 4) << 14, (nidx[k] + 1) * 4)
            cen = Rf.T @ (G[[t0, t1, t2]].mean(0) - Jf)
            _, mat, uv = cands[int(np.argmin(np.linalg.norm(cen_d - cen, axis=1)))]
            if mat not in mats:
                mats.append(mat)
            ui = []
            for u, v in uv:
                e = (u & 255) | ((v & 255) << 8)
                if e not in uvs:
                    uvs.append(e)
                ui.append(uvs.index(e))
            tex.append(bytes([mats.index(mat)] + ui))
        pb += struct.pack("<3I", 0, 0, 0)
        if len(uvs) > MAX_UVS:
            raise Budget(f"row {r} needs {len(uvs)} texture coordinates")
        cb = struct.pack("<H", 2 + 2 * len(mats)) + b"".join(struct.pack("<H", x) for x in mats)
        cb += struct.pack("<H", 2 + 2 * len(uvs)) + b"".join(struct.pack("<H", e) for e in uvs)
        cb += bytes([len(ts)]) + b"".join(tex) + bytes([0, 0, 0])
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
        report["rows"][r] = {"triangles": len(ts), "own": len(verts), "borrowed": len(borrow.get(r, [])),
                             "deposits": len(dep), "normals": len(normals), "uvs": len(uvs)}
    hdr = struct.pack("<6I", 27, struct.unpack_from("<I", m, 4)[0], 0x4B4D4433, 0, header - 8, 0)
    body = b"".join(struct.pack("<14i", *rows[r]) for r in range(27))
    data = hdr + body + bytes(blocks)
    report["cache_entries"] = max(entry.values(), default=0)
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
    a.out.write_bytes(X.own_model_file(a.model, stock, new))
    print(json.dumps(report, default=float))
    print(f"OK own model over model {a.model}: {len(new)} bytes")


if __name__ == "__main__":
    main()
