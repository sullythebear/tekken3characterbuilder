"""Direct import of a PS1-style model (.glb/.fbx): used as it is - its own polygons, UVs and
texture - with an automatic rig when it has no skeleton (T-pose or A-pose, facing +Z, Y up).

Every vertex belongs to one body row, as on the PlayStation (no blended bones). The texture
keeps its layout: texel (u, v) * size is the same texel in the fighter's page, 4-bit, each UV
island with a 16-colour CLUT of its own (islands grouped into as many CLUTs as the donor has
room for).

CLI: direct_import.py MODEL.fbx|.glb --model N --root GAME --out model.bin
     direct_import.py MODEL --root GAME --check     (JSON: triangles, texture, rigged, problems)"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import numpy as np

import model_export as X
import model_import as MI
import bind_pose as BP

PAIRS = MI.PAIRS


def load(path: Path) -> dict:
    out = _load(path)
    if out.get("bones"):
        _upright(out)
    return out


def _upright(src: dict) -> None:
    """Turns a rigged model into the importer's axes (Y up, facing +Z, the character's left at
    +X) from its skeleton: up = hips -> head, left = right upper arm -> left upper arm. Character
    Creator / 3ds Max exports are Z up; Mixamo and glTF already match (no change)."""
    bones = src["bones"]
    at = lambda prt, side=None: MI.joint(bones, prt, side)
    hips, head, ul, ur = at("pelvis"), at("head"), at("upper", "L"), at("upper", "R")
    if any(v is None for v in (hips, head, ul, ur)):
        return
    up = head - hips
    up /= np.linalg.norm(up)
    left = (ul - ur) - ((ul - ur) @ up) * up
    left /= np.linalg.norm(left)
    R = np.stack([left, up, np.cross(left, up)])          # rows: the new X, Y, Z
    # exports differ by whole axis swaps: snap to the nearest one, so a slightly crooked
    # skeleton does not tilt the model
    S = np.zeros((3, 3))
    for i in range(3):
        k = int(np.argmax(np.abs(R[i])))
        S[i, k] = np.sign(R[i, k])
    if abs(np.linalg.det(S)) < 0.5 or np.allclose(S, np.eye(3)):
        return
    R = S
    src["P"] = src["P"] @ R.T
    for b in bones:
        M = np.array(b["matrix"], float)
        M[:3, :] = R @ M[:3, :]
        b["matrix"] = M.tolist()


def _load(path: Path) -> dict:
    if path.suffix.lower() == ".glb":
        import glb
        g = glb.read(path)
        out = {"P": g["positions"], "T": g["triangles"], "UV": g["uv"], "MAT": g["materials"],
               "textures": g["textures"]}
        if "bones" in g:
            w = g["weights"]
            out["bones"], out["weights"] = g["bones"], w
            out["vbone"] = np.array([max(x, key=x.get) if x else -1 for x in w])
        return out
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
    out = {"P": P2, "T": T2, "UV": UV, "MAT": np.array(c["materials"]),
           "textures": {k: v for k, (n, v) in c["textures"].items()}}
    if c["bones"]:
        # a real rig (e.g. from Mixamo): joints and the strongest bone of every vertex
        w = c["weights"]
        out["bones"] = c["bones"]
        out["vbone"] = np.array([max(w[i], key=w[i].get) if w[i] else -1 for i in T.ravel()])
        out["weights"] = [w[i] for i in T.ravel()]
    return out


def auto_rig(P, T=None):
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
    # crotch: the lowest height where a ray through the centre line (front to back) meets the
    # body; below it is the gap between the legs. Rays, not vertices: a low-poly model has
    # few vertices, so "no vertex near the centre" holds almost everywhere
    import lowpoly
    crotch = 0.45
    if T is not None:
        zs = P[:, 2].min() - 0.1 * H
        hs = np.arange(0.2, 0.65, 0.004)
        o = np.array([[0.0, y0 + h * H, zs] for h in hs])
        d = np.tile([0.0, 0, 1.0], (len(hs), 1))
        hit = lowpoly.ray_hits(o, d, P, T, np.full(len(hs), 2 * H + 1))
        body = ~np.isnan(hit)
        if body.any():
            crotch = float(hs[np.argmax(body)])
    # baggy trousers or a skirt close the gap low down; a human crotch sits at 0.42-0.50 of
    # the height
    crotch = float(np.clip(crotch, 0.42, 0.5))
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


def rig_from_skeleton(bones, vbone, P):
    """Joints and per-vertex parts from a skeleton with Mixamo-like names."""
    J = {"hips": MI.joint(bones, "pelvis"), "neck": MI.joint(bones, "head")}
    for side in "LR":
        for prt in ("collar", "upper", "fore", "hand", "thigh", "shin", "foot"):
            J[prt + side] = MI.joint(bones, prt, side)
        hp = [np.array([b["matrix"][k][3] for k in range(3)]) for b in bones if MI._part(b["name"]) == ("hand", side)]
        J["handend" + side] = max(hp, key=lambda q: np.linalg.norm(q - J["hand" + side])) if hp else J["hand" + side]
        fp = [np.array([b["matrix"][k][3] for k in range(3)]) for b in bones if MI._part(b["name"]) == ("foot", side)]
        J["toe" + side] = max(fp, key=lambda q: np.linalg.norm(q - J["foot" + side])) if fp else J["foot" + side]
    for side in "LR":                        # no shoulder bone: a collar point between neck and arm
        if J["collar" + side] is None and J["upper" + side] is not None and J["neck"] is not None:
            u = J["upper" + side]
            J["collar" + side] = u + 0.65 * (np.array([J["neck"][0], u[1], u[2]]) - u)
    missing = [k for k, v in J.items() if v is None]
    if missing:
        raise ValueError("The skeleton misses bones the Tekken skeleton needs: " + ", ".join(sorted(missing)) + ".")
    J["top"] = np.array([J["neck"][0], P[:, 1].max(), J["neck"][2]])
    part = np.empty(len(P), dtype=object)
    for i, b in enumerate(vbone):
        prt, side = MI._part(bones[b]["name"]) if b >= 0 else ("spine", None)
        if prt is None:
            prt = "spine"
        part[i] = (prt, side if prt in PAIRS else None)
    return J, part


NEEDED = {"hips": ("pelvis", None), "head": ("head", None), "left upper arm": ("upper", "L"),
          "right upper arm": ("upper", "R"), "left forearm": ("fore", "L"), "right forearm": ("fore", "R"),
          "left hand": ("hand", "L"), "right hand": ("hand", "R"), "left thigh": ("thigh", "L"),
          "right thigh": ("thigh", "R"), "left shin": ("shin", "L"), "right shin": ("shin", "R"),
          "left foot": ("foot", "L"), "right foot": ("foot", "R")}


REDUCE_ABOVE = 1100          # more triangles: reduce.py makes a PS1-sized model first


def _pair_quads(faces, uvs, G=None, max_bend=12.0):
    """Neighbouring triangles with the same texels on their shared edge and the same CLUT go out
    as one quad (corners a, b, c, d: the GPU draws (a, b, c) and (b, d, c), the same two
    triangles): 52 bytes of GPU packets instead of 80, as Namco's models do."""
    edge = {}
    for i, f in enumerate(faces):
        v = f["v"]
        for k in range(3):
            edge.setdefault((v[k], v[(k + 1) % 3]), []).append((i, k))
    used = [False] * len(faces)
    out, out_uv = [], []
    for i, f in enumerate(faces):
        if used[i]:
            continue
        v = f["v"]
        best = None
        for k in range(3):
            b_, c_ = v[(k + 1) % 3], v[(k + 2) % 3]            # shared edge b -> c, opposite a
            for j, kk in edge.get((c_, b_), []):
                if j == i or used[j] or faces[j].get("chart") != f.get("chart") or faces[j]["hard"] != f["hard"]:
                    continue
                w = faces[j]["v"]
                # the same texels at b and c in both triangles
                ub, uc = uvs[i][(k + 1) % 3], uvs[i][(k + 2) % 3]
                if uvs[j][kk] != uc or uvs[j][(kk + 1) % 3] != ub:
                    continue
                # nearly flat only: the PlayStation culls a quad by its first triangle, so a bent
                # pair vanishes whole when that half turns away (holes at the crotch, the wrists)
                if G is not None:
                    n1 = np.cross(G[v[1]] - G[v[0]], G[v[2]] - G[v[0]])
                    n2 = np.cross(G[w[1]] - G[w[0]], G[w[2]] - G[w[0]])
                    c = n1 @ n2 / (np.linalg.norm(n1) * np.linalg.norm(n2) + 1e-12)
                    if c < np.cos(np.radians(max_bend)):
                        continue
                best = (k, j, (kk + 2) % 3)
                break
            if best:
                break
        if not best:
            out.append(f)
            out_uv.append(uvs[i])
            continue
        k, j, kd = best
        a, b, c = k, (k + 1) % 3, (k + 2) % 3
        used[i] = used[j] = True
        q = dict(f)
        q["v"] = [v[a], v[b], v[c], faces[j]["v"][kd]]
        q["suv"] = [f["suv"][a], f["suv"][b], f["suv"][c], faces[j]["suv"][kd]]
        out.append(q)
        out_uv.append([uvs[i][a], uvs[i][b], uvs[i][c], uvs[j][kd]])
    return out, out_uv


def inspect(path: Path) -> dict:
    """What the builder needs to know before an import: size, texture and whether the model is
    rigged (a skeleton with the bones Tekken needs and skin weights). `rigged` False locks the
    import in the builder."""
    path = Path(path)
    if path.suffix.lower() not in (".fbx", ".glb"):
        return {"ok": False, "rigged": False, "problems": ["Use an .fbx (FBX Binary) or .glb file."]}
    try:
        src = load(path)
    except Exception as error:                        # a damaged or unsupported file
        return {"ok": False, "rigged": False, "problems": [f"The file could not be read: {error}"]}
    info = {"ok": True, "triangles": int(len(src["T"])), "vertices": int(len(np.unique(np.round(src["P"], 5), axis=0))),
            "textured": bool(src.get("textures")), "bones": len(src.get("bones", [])), "problems": [], "missing": []}
    parts = {MI._part(b["name"]) for b in src.get("bones", [])}
    info["missing"] = [k for k, v in NEEDED.items() if v not in parts]
    weighted = sum(1 for w in src.get("weights", []) if w) if "weights" in src else 0
    if not src.get("bones"):
        info["problems"].append("The model is not rigged: it has no skeleton. Rig it first (for example "
                                "with Mixamo, then export FBX Binary in T-pose).")
    elif info["missing"]:
        info["problems"].append("The skeleton misses bones Tekken needs: " + ", ".join(info["missing"]) + ".")
    elif weighted < 0.95 * len(src["P"]):
        info["problems"].append("The skin weights are missing for part of the model: weight every vertex to a bone.")
    info["rigged"] = not info["problems"]
    info["notes"] = []
    if info["triangles"] > REDUCE_ABOVE:
        info["notes"].append(f"{info['triangles']} triangles: Tekken 3 fighters have 650-1100, so the builder "
                             "reduces it to PS1 size and bakes a new 256 x 256 texture (1 to 3 minutes).")
        info["reduce"] = True
    if not info["textured"]:
        info["problems"].append("The model has no embedded texture: it will be drawn without one.")
    return info


def build(root: Path, model: int, path: Path, log=print):
    """Imports a model file over a donor model; a high-poly file is reduced first (reduce.py),
    smaller and smaller until it fits the donor's slot."""
    src = load(Path(path))
    if len(src["T"]) <= REDUCE_ABOVE:
        return _build(root, model, src, log)
    import reduce as RD
    # a first guess from what reduced models need (flat quads included): ~35.5 bytes of GPU packets
    # and ~25.5 bytes of model per triangle; then 7 % fewer per failed try
    rid = X.FIRST_MODEL_RECORD + 4 * model
    slot = len(X.records(root, [rid])[rid])
    target = int(min(MI.MAX_PACKET_BYTES / 35.5, slot / 25.5) * 0.97)
    for k in range(6):
        low = RD.reduce(src, target, log=log)
        try:
            return _build(root, model, low, log, degrade=k == 5)
        except MI.Budget as error:
            log(f"{target} triangles do not fit ({error}); trying fewer")
            target = int(target * 0.93)
    raise MI.Budget("The model does not fit this fighting style's slot.")


def _build(root: Path, model: int, src: dict, log=print, degrade=True):
    from fmt import row
    import texture_bake as TB
    from PIL import Image
    rid = X.FIRST_MODEL_RECORD + 4 * model
    m = X.records(root, [rid])[rid]
    # the pose the donor was modelled in (its own seam vertices meet), not the builder's
    # standing frames: those mirror collarbones and hips and tilt the head (bind_pose.py)
    W = BP.solve(m, MI.donor_frames(root, m))
    P, T, UV = src["P"], src["T"], src["UV"]
    if "bones" in src:
        J0, part = rig_from_skeleton(src["bones"], src["vbone"], P)
    else:
        J0, part = auto_rig(P, T)
    log(f"auto rig: crotch at {(J0['thighL'][1] - P[:, 1].min()) / np.ptp(P[:, 1]):.2f} of the height")
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
    # Tekken's root (row 3, the pelvis) sits at the waist, above the hip sockets (rows 5/8): put
    # the import's root as far above its hip sockets as the donor's (relative to the leg), then
    # scale by that height above the soles, so the soles land on the ground and the body bends
    # where the donor's does
    thigh_t3 = floor_t3 - np.mean([W[5][1][1], W[8][1][1]])
    hip_t3 = floor_t3 - W[3][1][1]
    ratio = (hip_t3 - thigh_t3) / thigh_t3
    sole = P[:, 1].min()
    thigh_i = J0["thighL"][1] - sole
    J0["hips"] = J0["hips"].copy()
    J0["hips"][1] = sole + thigh_i * (1 + ratio)
    s = hip_t3 / (J0["hips"][1] - sole)
    log(f"scale {s:.0f}: root {ratio:.2f} of the leg above the hip sockets, as the donor's")
    for i in range(len(P)):                  # pelvis below the root, torso above
        if part[i][0] in ("pelvis", "spine"):
            part[i] = ("pelvis" if P[i, 1] < J0["hips"][1] else "spine", None)
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
        vrow.append({"spine": 1, "pelvis": 3, "head": 19}.get(prt) or rows_of(prt, side or "L"))
    G = np.array([g(p) for p in P])
    blend, blend_score = {}, {}
    if "weights" in src:
        # Pose the mesh into the donor's standing pose with the file's own smooth weights (linear
        # blend skinning): arms down, legs as the donor's. The game then only turns each row a
        # little from this rest pose, so the PlayStation's one-bone-per-vertex binding no longer
        # tears shoulders and hips (a T-pose rest needs 90 degree turns at the shoulders).
        CH = {1: 19, 5: 6, 6: 7, 8: 9, 9: 10, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18}
        Fd = {r: W[r][0] for r in F}
        Jd = {r: W[r][1] for r in F}
        # the import keeps its own bone lengths (the game reads them from the model's offsets, as
        # every Namco fighter has its own): each joint sits in the donor's direction from its
        # parent, at the import's distance; no stretching (the donor's longer spine made long necks)
        import anim_model as A
        Jp = {}
        for r in (1, 3, 19, 11, 12, 13, 14, 15, 16, 17, 18, 5, 6, 7, 8, 9, 10):
            p = A.ROW_PARENT[r]
            if p == 0 or p not in Jp:
                Jp[r] = Jd[r]
                continue
            d = Jd[r] - Jd[p]
            Jp[r] = Jp[p] + d / max(np.linalg.norm(d), 1e-9) * np.linalg.norm(J[r] - J[p])
        for k, v in MI.FRAME.items():
            Jp[k] = Jp[v]

        def pose_row(xg, r):
            fr = MI.FRAME.get(r, r)
            loc = (xg - J[fr]) @ F[fr]
            return loc @ Fd[fr].T + Jp[fr]
        bones = src["bones"]
        brow = {}
        for bi, b in enumerate(bones):
            prt, side = MI._part(b["name"])
            if prt in ("spine", "pelvis", "head"):
                brow[bi] = {"spine": 1, "pelvis": 3, "head": 19}[prt]
            elif prt in PAIRS and side:
                brow[bi] = rows_of(prt, side)
            else:
                brow[bi] = None
        # unknown bones (cloth, props): a chain takes the row of the known joint nearest to its
        # first bone (a sleeve hung from the spine next to the shoulder goes with the arm), the
        # rest of the chain follows it
        at = lambda b: np.array([b["matrix"][k][3] for k in range(3)])
        known = [bi for bi in brow if brow[bi] is not None]
        for bi, b in enumerate(bones):
            if brow[bi] is not None:
                continue
            p = b["parent"]
            if p >= 0 and p in brow and brow[p] is not None and MI._part(bones[p]["name"])[0] is None:
                brow[bi] = brow[p]
            elif known:
                near = min(known, key=lambda k: np.linalg.norm(at(bones[k]) - at(b)))
                brow[bi] = brow[near]
            else:
                brow[bi] = 1
        acc = np.zeros_like(G)
        tot = np.zeros(len(G))
        rows_needed = {}
        for i, wv in enumerate(src["weights"]):
            for bi, w in wv.items():
                rows_needed.setdefault(brow[bi], []).append((i, w))
        for r, lst in rows_needed.items():
            idx = np.array([i for i, _ in lst])
            ww = np.array([w for _, w in lst])
            np.add.at(acc, idx, pose_row(G[idx], r) * ww[:, None])
            np.add.at(tot, idx, ww)
        G = np.where(tot[:, None] > 0, acc / np.maximum(tot, 1e-9)[:, None], G)
        # rows per vertex from the weights; a vertex shared by two bones (both >= 30 %) becomes
        # a 50/50 seam vertex: owned by the later-drawn row, blended with the earlier one
        DRAW_ORDER = {r: k for k, r in enumerate(MI.DRAW)}
        for i, wv in enumerate(src["weights"]):
            rw = {}
            for bi, w in wv.items():
                rw[brow[bi]] = rw.get(brow[bi], 0) + w
            if not rw:
                continue
            tot_w = sum(rw.values())
            top = sorted(rw, key=rw.get, reverse=True)
            vrow[i] = top[0]
            if len(top) > 1 and rw[top[1]] / tot_w >= 0.3:
                a_, b_ = sorted(top[:2], key=lambda r: DRAW_ORDER.get(r, 99))
                vrow[i] = b_
                blend[i] = a_
                blend_score[i] = rw[top[1]] / tot_w
        log(f"{len(blend)} seam vertices blended 50/50 between two bones")
        F, J = Fd, Jp
        log("mesh posed into the donor's standing pose with the file's weights")
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
    # the file's winding is consistent: one decision for all (per triangle, a smoothed normal in
    # a crease - the buttocks - would flip single triangles inside out)
    # make the winding consistent first (exported files can hold flipped patches): neighbours
    # across a shared edge must run that edge in opposite directions; then per connected piece
    # one decision (the majority of its triangles against the smoothed normals)
    Tw = weld[T]
    flip = np.zeros(len(T), bool)
    seen = np.zeros(len(T), bool)
    edges = {}
    for i, t in enumerate(Tw):
        for k in range(3):
            edges.setdefault(frozenset((t[k], t[(k + 1) % 3])), []).append(i)
    def directed(i, a_, b_):
        t = list(Tw[i])
        if flip[i]:
            t = t[::-1]
        return any(t[k] == a_ and t[(k + 1) % 3] == b_ for k in range(3))
    pieces = []
    if src.get("reduced"):
        # a reduced model's faces come from a voxel surface: each already faces out (or all in);
        # passing the winding along neighbours would cross the few edges where two sheets touch
        # and turn whole patches inside out (holes on the PlayStation)
        seen[:] = True
        pieces.append(list(range(len(T))))
    for start in range(len(T)):
        if seen[start]:
            continue
        seen[start] = True
        stack, piece = [start], [start]
        while stack:
            i = stack.pop()
            t = Tw[i][::-1] if flip[i] else Tw[i]
            for k in range(3):
                a_, b_ = t[k], t[(k + 1) % 3]
                for j in edges[frozenset((a_, b_))]:
                    if j == i or seen[j]:
                        continue
                    flip[j] = directed(j, a_, b_) != flip[j] if False else False
                    # j must run the edge b_ -> a_
                    flip[j] = directed(j, a_, b_)
                    seen[j] = True
                    stack.append(j)
                    piece.append(j)
        pieces.append(piece)
    sgn = np.einsum("ij,ij->i", test, Nrm[T[:, 0]]) > 0
    outward = np.zeros(len(T), bool)
    for piece in pieces:
        pc = np.array(piece)
        good = (sgn[pc] != flip[pc]).mean() > 0.5
        outward[pc] = (~flip[pc]) if good else flip[pc]
    log(f"winding: {int(flip.sum())} triangles turned to match their neighbours, {len(pieces)} pieces")
    faces = []
    for i, t in enumerate(T):
        v = list(t) if outward[i] else [t[0], t[2], t[1]]
        # geometry on welded vertices (UVs are kept per polygon corner)
        faces.append({"v": [int(weld[x]) for x in v], "hard": False, "suv": [tuple(UV[j]) for j in v]})
    # texture: the file's own layout, 4-bit with a CLUT per UV island (group)
    if src.get("textures"):
        img = np.asarray(Image.open(io.BytesIO(next(iter(src["textures"].values())))).convert("RGB"))
    else:                                            # no texture in the file: plain grey
        img = np.full((256, 256, 3), 150, np.uint8)
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
    # islands whose texels overlap (shared or mirrored UVs) share one CLUT, or the texels would
    # be painted with the wrong palette (the yellow patch on the head)
    paint_owner = -np.ones((256, 256), dtype=int)
    texel0 = [np.clip(np.array(f["suv"]) * 256, 0, 255.99) for f in faces]

    shared = {}

    def paint0(i, xy, bc):
        core = (bc > 0.05).all(1)                 # inside the triangle, not its border texels
        xy = xy[core]
        prev = paint_owner[xy[:, 1], xy[:, 0]]
        for q in prev[prev >= 0].tolist():
            if fnd(q) != fnd(i):
                k = (min(fnd(q), fnd(i)), max(fnd(q), fnd(i)))
                shared[k] = shared.get(k, 0) + 1
        paint_owner[xy[:, 1], xy[:, 0]] = i
    TB.raster(texel0, paint0)
    for (a_, b_), n_ in shared.items():
        if n_ >= 6:                               # a real overlap, not a touching edge
            parent[fnd(a_)] = fnd(b_)
    isl = [fnd(i) for i in range(len(faces))]
    ids = {k: n for n, k in enumerate(sorted(set(isl)))}
    isl = [ids[k] for k in isl]
    texel = [np.clip(np.array(f["suv"]) * 256, 0, 255.99) for f in faces]
    owner = -np.ones((256, 256), dtype=int)

    def paint(i, xy, bc):
        owner[xy[:, 1], xy[:, 0]] = isl[i]
    TB.raster(texel, paint)
    # texels just outside an island (polygon edges sample them) join the nearest island, or they
    # would read index 0 of the polygon's palette: light streaks along the edges
    for _ in range(3):
        grow = owner.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.roll(np.roll(owner, dy, 0), dx, 1)
            take = (grow < 0) & (nb >= 0)
            grow[take] = nb[take]
        owner = grow
    cl = MI.donor_cluts(root, model)
    n_cluts = max(1, (cl["row1"] + 0) // 16 + (16 if cl["row0"] >= 256 else 0) // 1)
    n_cluts = min(n_cluts, 48)
    # group islands into CLUTs by colour
    # a reduced model's face islands get palettes of their own (16 colours each), as Namco's faces
    face_isl = sorted({isl[i] for i in src.get("face_tris", []) if i < len(isl)})[:4]
    idx, palette, group = TB.quantise_groups(img, owner, min(n_cluts, int(owner.max()) + 1), own=face_isl,
                                             lab_=bool(src.get("reduced")))
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
    if src.get("reduced"):
        faces, texture["uv"] = _pair_quads(faces, texture["uv"], G)
        log(f"{sum(1 for f in faces if len(f['v']) == 4)} triangle pairs sent as quads")
    blend_w = {}
    for v, a_ in blend.items():                      # on welded ids, as the faces
        blend_w[int(weld[v])] = a_
    vrow_w = list(vrow)
    for v in range(len(vrow)):
        vrow_w[int(weld[v])] = vrow[v] if int(weld[v]) == v else vrow_w[int(weld[v])]
    # the game keeps at most 127 seam vertices in its cache at once: when a model needs more, the
    # weakest seams (least weight on the second bone) become plain one-bone vertices
    score = {}
    for v, s_ in blend_score.items():
        score[int(weld[v])] = max(score.get(int(weld[v]), 0), s_)
    while True:
        try:
            data, report = MI._write(m, G, Nrm, faces, vrow_w, {}, F, J, row, {"ready": texture}, blend=blend_w, zsign=-1)
            break
        except MI.Budget as error:
            if "seam vertices" not in str(error) or not blend_w:
                raise
            for v in sorted(blend_w, key=lambda v: score.get(v, 0))[:max(1, len(blend_w) // 8)]:
                blend_w.pop(v)
            log(f"too many seam vertices at once: {len(blend_w)} kept")
    # too big for the donor's slot (Mokujin's is small): flat-shade the flattest polygons first
    # (one normal and a shorter record each) until it fits
    if len(data) > len(m) and degrade:
        spread = [max(float(np.degrees(np.arccos(np.clip(Nrm[a] @ Nrm[b], -1, 1))))
                      for a in f["v"] for b in f["v"]) for f in faces]
        # then the 50/50 seams go (each holds a second copy of its vertex), joints bend harder
        for seams, limit in ((True, 10), (True, 20), (True, 35), (False, 0), (False, 20), (False, 60), (False, 180)):
            for f, sp in zip(faces, spread):
                f["hard"] = sp <= limit
            data, report = MI._write(m, G, Nrm, faces, vrow_w, {}, F, J, row, {"ready": texture},
                                     blend=blend_w if seams else {}, zsign=-1)
            if len(data) <= len(m):
                log(f"to fit the donor's slot: flat shading below {limit} degrees"
                    + ("" if seams else ", no 50/50 joint seams"))
                break
    report.update(bytes=len(data), budget=len(m), islands=int(owner.max()) + 1, cluts=len(cid))
    if len(data) > len(m):
        raise MI.Budget(f"The model needs {len(data)} bytes but this fighting style's model slot holds {len(m)}: "
                        "use fewer triangles or another style.")
    return m, data, texture, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_file", type=Path)
    ap.add_argument("--model", type=int)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true", help="print what inspect() finds as JSON")
    a = ap.parse_args()
    X.setup(a.root)
    if a.check:
        print(json.dumps(inspect(a.model_file)))
        return
    if a.model is None or a.out is None:
        ap.error("--model and --out are needed for an import")
    info = inspect(a.model_file)
    if not info["rigged"]:
        raise SystemExit("ERROR " + " ".join(info["problems"]))
    stock, new, tx, report = build(a.root, a.model, a.model_file)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.model, stock, new, tx))
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "texture")}, default=str))
    print(f"OK direct import over model {a.model}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
