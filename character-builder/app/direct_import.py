"""Direct import of a PS1-style model (.glb/.fbx): used as it is - its own polygons, UVs and
texture - with an automatic rig when it has no skeleton (T-pose or A-pose, facing +Z, Y up).

Every vertex belongs to one body row, as on the PlayStation (no blended bones). The texture
keeps its layout: texel (u, v) * size is the same texel in the fighter's page, 4-bit, each UV
island with a 16-colour CLUT of its own (islands grouped into as many CLUTs as the donor has
room for).

CLI: direct_import.py MODEL.glb --model N --root GAME --out model.bin"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import numpy as np

import model_export as X
import model_import as MI

PAIRS = MI.PAIRS


def load(path: Path) -> dict:
    if path.suffix.lower() == ".glb":
        import glb
        g = glb.read(path)
        return {"P": g["positions"], "T": g["triangles"], "UV": g["uv"], "MAT": g["materials"],
                "textures": g["textures"]}
    import fbx
    c = fbx.character(path)
    P = np.array(c["positions"]).reshape(-1, 3)
    T = np.array(c["triangles"]).reshape(-1, 3)
    # FBX UVs are per corner: split the vertices so every corner has its own UV
    uv = np.array(c["corner_uvs"]).reshape(-1, 3, 2)
    P2 = P[T.ravel()]
    T2 = np.arange(len(P2)).reshape(-1, 3)
    UV = uv.reshape(-1, 2).copy()
    UV[:, 1] = 1 - UV[:, 1]
    return {"P": P2, "T": T2, "UV": UV, "MAT": np.array(c["materials"]),
            "textures": {k: v for k, (n, v) in c["textures"].items()}}


def auto_rig(P):
    """Joints of a T/A-posed humanoid from its shape alone (glTF axes: Y up, facing +Z, the
    character's left at +X). -> joints {name: point}, and a row for every vertex."""
    y0, y1 = P[:, 1].min(), P[:, 1].max()
    H = y1 - y0
    y = (P[:, 1] - y0) / H
    ax = np.abs(P[:, 0])
    reach = ax.max()
    hands = ax > reach - 0.03 * H
    arm_y = float(np.median(y[hands]))
    # torso half width: widest point of the body between the waist and below the arms
    band = (y > 0.5) & (y < arm_y - 0.08)
    torso_x = float(np.percentile(ax[band], 98))
    # crotch: the highest height where nothing sits on the centre line (the gap between legs)
    crotch = 0.45
    for h in np.arange(0.25, 0.6, 0.005):
        if not ((np.abs(y - h) < 0.006) & (ax < 0.02 * H)).any():
            crotch = h
    knee = crotch * 0.52 + 0.05 * 0.48
    ankle = 0.06
    neck = arm_y + 0.06
    hip_line = crotch + 0.08
    sh_x = torso_x * 0.92
    wrist_x = reach - 0.105 * H
    elbow_x = (sh_x + wrist_x) / 2
    legs = y < crotch + 0.01
    leg_x = float(np.median(ax[legs & (y > crotch - 0.15)]))
    J = {}
    for side, s in (("L", 1), ("R", -1)):
        J["collar" + side] = np.array([s * 0.035 * H, y0 + arm_y * H, 0])
        J["upper" + side] = np.array([s * sh_x, y0 + arm_y * H, 0])
        J["fore" + side] = np.array([s * elbow_x, y0 + arm_y * H, 0])
        J["hand" + side] = np.array([s * wrist_x, y0 + arm_y * H, 0])
        J["handend" + side] = np.array([s * reach, y0 + arm_y * H, 0])
        J["thigh" + side] = np.array([s * leg_x, y0 + hip_line * H - 0.03 * H, 0])
        J["shin" + side] = np.array([s * leg_x, y0 + knee * H, 0])
        J["foot" + side] = np.array([s * leg_x, y0 + ankle * H, 0])
        sel = (np.sign(P[:, 0]) == s) & (y < ankle + 0.02)
        J["toe" + side] = P[sel][np.argmax(P[sel][:, 2])] if sel.any() else J["foot" + side] + [0, 0, 0.1 * H]
    for k in ("thighL", "thighR", "shinL", "shinR", "footL", "footR"):
        J[k][2] = float(np.median(P[(np.abs(P[:, 0] - J[k][0]) < 0.05 * H) & (np.abs(P[:, 1] - J[k][1]) < 0.03 * H), 2]
                                  if ((np.abs(P[:, 0] - J[k][0]) < 0.05 * H) & (np.abs(P[:, 1] - J[k][1]) < 0.03 * H)).any() else [0]))
    J["hips"] = np.array([0, y0 + hip_line * H, float(np.median(P[np.abs(y - hip_line) < 0.02, 2]))])
    J["neck"] = np.array([0, y0 + neck * H, float(np.median(P[np.abs(y - neck) < 0.02, 2]))])
    J["top"] = np.array([0, y1, J["neck"][2]])
    # one row per vertex
    part = np.empty(len(P), dtype=object)
    for i, (p, yy, a) in enumerate(zip(P, y, ax)):
        side = "L" if p[0] >= 0 else "R"
        if a > sh_x and abs(yy - arm_y) < 0.14:
            part[i] = ("upper" if a < elbow_x else "fore" if a < wrist_x else "hand", side)
        elif yy > neck and a < torso_x:
            part[i] = ("head", None)
        elif a > 0.6 * sh_x and abs(yy - arm_y) < 0.07:
            part[i] = ("collar", side)
        elif yy < crotch + 0.01:
            part[i] = ("thigh" if yy > knee else "shin" if yy > ankle + 0.015 else "foot", side)
        elif yy < hip_line:
            part[i] = ("pelvis", None)
        else:
            part[i] = ("spine", None)
    return J, part


def build(root: Path, model: int, path: Path, log=print):
    from fmt import row
    import texture_bake as TB
    from PIL import Image
    rid = X.FIRST_MODEL_RECORD + 4 * model
    m = X.records(root, [rid])[rid]
    W = MI.donor_frames(root, m)
    src = load(path)
    P, T, UV = src["P"], src["T"], src["UV"]
    J0, part = auto_rig(P)
    # axes as model_import.build: glTF (Y up, faces +Z, left +X) -> game (Y down)
    up = np.array([0.0, -1, 0])
    front = sum(W[r][0][:, 0] for r in (7, 10))
    front[1] = 0
    front /= np.linalg.norm(front)
    left = np.cross(up, front)
    Q = np.stack([left, up, front], 1)
    left_rows = {k: (a if (W[a][1] - W[1][1]) @ left > (W[b][1] - W[1][1]) @ left else b) for k, (a, b) in PAIRS.items()}
    rows_of = lambda prt, side: left_rows[prt] if side == "L" else [r for r in PAIRS[prt] if r != left_rows[prt]][0]
    # scale: hip height above the soles, as the donor's
    floor_t3 = max((W[sl[0]][0] @ np.array(sl[1], float) + W[sl[0]][1])[1]
                   for r, slots in X.bind(m).items() if r in (5, 6, 7, 8, 9, 10) for sl in slots if sl is not None)
    s = (floor_t3 - W[3][1][1]) / (J0["hips"][1] - P[:, 1].min())
    g = lambda x: s * (Q @ (np.asarray(x) - J0["hips"])) + W[3][1]
    J = {1: g(J0["hips"]), 3: g(J0["hips"]), 19: g(J0["neck"])}
    for side in "LR":
        for prt in ("collar", "upper", "fore", "hand", "thigh", "shin", "foot"):
            J[rows_of(prt, side)] = g(J0[prt + side])
    ends = {19: g(J0["top"])}
    for side in "LR":
        ends[rows_of("hand", side)] = g(J0["handend" + side])
        ends[rows_of("foot", side)] = g(J0["toe" + side])
    # frames: the donor's standing frames turned onto the import's limbs (T-pose arms)
    child = {1: 19, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18, 5: 6, 6: 7, 8: 9, 9: 10}
    F = {}
    for r in (1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19):
        if r in child:
            dd = W[child[r]][1] - W[r][1]
            df = J[child[r]] - J[r]
            A_ = X.align(dd / np.linalg.norm(dd), df / np.linalg.norm(df))
        elif r in (14, 18):
            A_ = F[r - 1] @ W[r - 1][0].T
        else:
            A_ = np.eye(3)
        F[r] = A_ @ W[r][0]
    for k, v in MI.FRAME.items():
        F[k], J[k] = F[v], J[v]
    vrow = []
    for prt, side in part:
        vrow.append({"spine": 1, "pelvis": 3, "head": 19}.get(prt) or rows_of(prt, side))
    G = np.array([g(p) for p in P])
    # smooth normals over welded positions (the file splits vertices at UV seams)
    key = {tuple(np.round(p, 5)): i for i, p in enumerate(P)}
    weld = np.array([key[tuple(np.round(p, 5))] for p in P])
    n_acc = np.zeros_like(G)
    for t in T:
        n = np.cross(G[t[1]] - G[t[0]], G[t[2]] - G[t[0]])
        n_acc[weld[t]] += n
    Nrm = n_acc[weld]
    Nrm /= np.linalg.norm(Nrm, axis=1, keepdims=True) + 1e-12
    # winding: game Y points down (a mirror), so the file's outward triangles flip
    test = np.cross(G[T[:, 1]] - G[T[:, 0]], G[T[:, 2]] - G[T[:, 0]])
    outward = np.einsum("ij,ij->i", test, Nrm[T[:, 0]]) > 0
    faces = []
    for i, t in enumerate(T):
        v = list(t) if outward[i] else [t[0], t[2], t[1]]
        # geometry on welded vertices (UVs are kept per polygon corner)
        faces.append({"v": [int(weld[x]) for x in v], "hard": False, "suv": [tuple(UV[j]) for j in v]})
    # texture: the file's own layout, 4-bit with a CLUT per UV island (group)
    img = np.asarray(Image.open(io.BytesIO(next(iter(src["textures"].values())))).convert("RGB"))
    th, tw = img.shape[:2]
    if (tw, th) != (256, 256):
        img = np.asarray(Image.fromarray(img).resize((256, 256), Image.LANCZOS))
    # islands: faces joined by shared (welded) UV corners
    parent = list(range(len(faces)))

    def fnd(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    corner = {}
    for i, f in enumerate(faces):
        for uv in f["suv"]:
            k = (round(uv[0] * 256), round(uv[1] * 256))
            if k in corner:
                parent[fnd(i)] = fnd(corner[k])
            else:
                corner[k] = i
    isl = [fnd(i) for i in range(len(faces))]
    ids = {k: n for n, k in enumerate(sorted(set(isl)))}
    isl = [ids[k] for k in isl]
    texel = [np.clip(np.array(f["suv"]) * 256, 0, 255.99) for f in faces]
    owner = -np.ones((256, 256), dtype=int)

    def paint(i, xy, bc):
        owner[xy[:, 1], xy[:, 0]] = isl[i]
    TB.raster(texel, paint)
    cl = MI.donor_cluts(root, model)
    n_cluts = max(1, (cl["row1"] + 0) // 16 + (16 if cl["row0"] >= 256 else 0) // 1)
    n_cluts = min(n_cluts, 48)
    # group islands into CLUTs by colour
    idx, palette, group = TB.quantise_groups(img, owner, min(n_cluts, int(owner.max()) + 1))
    band = TB.band4(np.where(owner >= 0, idx, 0))
    # CLUT ids: row 1 from 64 (the donor's 4-bit row) then row 2 from 128
    cid = [64 + k if k < 16 else 128 + (k - 16) for k in range(len(palette) // 16)]
    runs = []
    for k in range(len(cid)):
        cols = palette[16 * k:16 * k + 16]
        if runs and runs[-1][0] + len(runs[-1][1]) // 16 == cid[k]:
            runs[-1] = (runs[-1][0], runs[-1][1] + cols)
        else:
            runs.append((cid[k], list(cols)))
    mats = sorted(set(int(group[i]) for i in isl))
    for i, f in enumerate(faces):
        f["chart"] = int(group[isl[i]])
    texture = {"uv": [[(int(u), int(v)) for u, v in tx] for tx in texel], "band": band, "runs": runs,
               "mats": {k: cid[k] for k in range(len(cid))}, "palette": palette, "charts": len(cid),
               "density": 0.0, "rgb": img}
    data, report = MI._write(m, G, Nrm, faces, vrow, {}, F, J, row, {"ready": texture})
    report.update(bytes=len(data), budget=len(m), islands=int(owner.max()) + 1, cluts=len(cid))
    if len(data) > len(m):
        raise MI.Budget(f"{len(data)} bytes, the donor's slot holds {len(m)}")
    return m, data, texture, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_file", type=Path)
    ap.add_argument("--model", type=int, required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    X.setup(a.root)
    stock, new, tx, report = build(a.root, a.model, a.model_file)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.model, stock, new, tx))
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "texture")}, default=str))
    print(f"OK direct import over model {a.model}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
