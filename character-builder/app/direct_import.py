"""Direct import of a PS1-style model (.glb/.fbx): used as it is - its own polygons, UVs and
texture - with an automatic rig when it has no skeleton (autorig.py: turned upright facing +Z,
then joints and body parts found from its shape, or placed by the player).

Every vertex belongs to one body row, as on the PlayStation (no blended bones). The texture
keeps its layout: texel (u, v) * size is the same texel in the fighter's page, 4-bit, each UV
island with a 16-colour CLUT of its own (islands grouped into as many CLUTs as the donor has
room for).

CLI: direct_import.py MODEL.fbx|.glb --model N --root GAME --out model.bin
     direct_import.py MODEL --root GAME --check     (JSON: triangles, texture, rigged, problems)"""
from __future__ import annotations
import re
import argparse
import io
import json
from pathlib import Path
import numpy as np

import model_export as X
import model_import as MI
import bind_pose as BP
import protrusions as PR

PAIRS = MI.PAIRS


# a texture image the player chose beside the model file (CLI --texture): PNG bytes for every
# material that has no texture of its own (models often ship their texture as a separate file)
EXTERNAL_TEXTURE: bytes | None = None


def set_external_texture(path: Path | None) -> None:
    """Reads any image Pillow knows, at most 1024 px, as the external texture (None: none)."""
    global EXTERNAL_TEXTURE
    if path is None:
        EXTERNAL_TEXTURE = None
        return
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    im.thumbnail((1024, 1024))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    EXTERNAL_TEXTURE = buf.getvalue()


def _external_texture(src: dict) -> None:
    """The chosen texture image on every material without a texture of its own, as long as the
    material has a UV map: one whose corners all share one UV (a colour-only material) would
    show a single texel of the image, so it keeps its own colour."""
    if EXTERNAL_TEXTURE is None:
        return
    MAT, T, UV = np.asarray(src["MAT"]), np.asarray(src["T"]), np.asarray(src["UV"], float)
    for mi in sorted(set(MAT.tolist())):
        if mi in src["textures"]:
            continue
        if src.get("missing_textures") and mi not in src["missing_textures"]:
            continue                                 # the file names its texture's materials: only those
        uv = UV[T[MAT == mi].ravel()] if len(UV) else np.zeros((0, 2))
        if len(uv) and np.ptp(uv, axis=0).max() < 1e-6:
            continue                                 # no UV map: its colour, not one texel
        src["textures"][mi] = EXTERNAL_TEXTURE


# a model without a skeleton: the joints the player placed by hand ({name: [x, y, z]}, in the
# turned model's axes) and how the model is turned ("auto", or a 3x3 rotation), else automatic
RIG_JOINTS: dict | None = None
RIG_TURN = "auto"
RIG_PAINT: list | None = None             # body parts painted by hand: [[x, y, z, part], ...]


def set_rig(joints=None, turn="auto", paint=None) -> None:
    global RIG_JOINTS, RIG_TURN, RIG_PAINT
    RIG_JOINTS, RIG_TURN, RIG_PAINT = joints or None, turn or "auto", paint or None


def load(path: Path) -> dict:
    out = _load(path)
    if out.get("bones"):
        _vrm_extras(out)
        _name_by_shape(out)
        _upright(out)
    else:
        _auto_rig(out, Path(path).suffix.lower())
    return out


def _auto_rig(out: dict, suffix: str) -> None:
    """No skeleton in the file: stand the model upright facing +Z and give it one (autorig.py),
    as a rigged file would have. A shape it cannot rig keeps its reason in "rig_error"."""
    import autorig
    P, T = np.asarray(out["P"], float), np.asarray(out["T"])
    if isinstance(RIG_TURN, (list, tuple, np.ndarray)):
        R = np.asarray(RIG_TURN, float)
    else:                                            # glTF is Y up by its standard
        R = autorig.orient(P, T, up=np.array([0.0, 1, 0]) if suffix in (".glb", ".vrm") else None)
    out["P"] = P @ R.T
    out["turn"] = R.tolist()
    try:
        autorig.rig(out, RIG_JOINTS, RIG_PAINT)
    except autorig.RigError as error:
        out["rig_error"] = str(error)


def _vrm_extras(src: dict) -> None:
    """A VRM marks its human bones. A bone that names a body part but hangs on the body through
    bones that name none (Seed-san's robot arm: "robo_hand.L" <- robo_root_pole <- bagpack <-
    chest) gets a neutral name, so it follows its parent instead of becoming a second hand.
    Twist and roll bones beside a human bone (J_Roll_L_UpperLeg) and fingers keep their names."""
    bones = src["bones"]
    if not any(b.get("human") for b in bones):
        return
    rename = []
    for i, b in enumerate(bones):
        if b.get("human") or MI._part(b["name"])[0] is None:
            continue
        up = b["parent"]
        while up >= 0 and not bones[up].get("human"):
            if MI._part(bones[up]["name"])[0] is None:
                rename.append(i)
                break
            up = bones[up]["parent"]
    for i in rename:
        bones[i]["name"] = f"extra_{i}"


def _name_by_shape(src: dict) -> None:
    """Skeletons whose bone names say nothing (joint0..joint17, leg_joint_L_1): the bones Tekken
    needs are found from the skeleton's shape and renamed as Mixamo's (Hips, LeftUpLeg, ...):
    the two lowest chain ends are the feet, the highest the head, the two that reach furthest
    sideways the hands; toes point forwards, which tells left from right. Nothing changes when
    the names already cover every needed bone; src["renamed"] lists what was renamed."""
    bones = src["bones"]
    have = {MI._part(b["name"]) for b in bones}
    if all(v in have for v in NEEDED.values()):
        return
    n = len(bones)
    J = np.array([[b["matrix"][k][3] for k in range(3)] for b in bones], float)
    kids = [[] for _ in range(n)]
    for i, b in enumerate(bones):
        if b["parent"] >= 0:
            kids[b["parent"]].append(i)
    def path_up(i):
        out = [i]
        while bones[out[-1]]["parent"] >= 0:
            out.append(bones[out[-1]]["parent"])
        return out
    leaves = [i for i in range(n) if not kids[i]]
    if len(leaves) < 5:
        return
    P = np.asarray(src["P"], float)
    ext = np.ptp(P, 0)
    best = None
    for ax in range(3):                               # up: the long axis, the sign with two feet
        for sgn in (1, -1):
            h = sgn * J[:, ax]
            H = ext[ax] or 1.0
            low = sorted(leaves, key=lambda i: h[i])[:2]
            top = max(leaves, key=lambda i: h[i])
            score = ext[ax] - 5 * abs(h[low[0]] - h[low[1]]) + (h[top] - h[low[1]])
            if best is None or score > best[0]:
                best = (score, ax, sgn, low, top)
    _, ax, sgn, feet, top = best
    up = np.zeros(3)
    up[ax] = sgn
    h = J @ up
    H = float(np.ptp(P @ up)) or 1.0
    # the hips: where the two feet's chains meet; the head: the top end's chain above it
    pf = [path_up(f) for f in feet]
    common = [i for i in pf[0] if i in pf[1]]
    if not common:
        return
    hips = common[0]
    leg_chains = [list(reversed(p[:p.index(hips)])) for p in pf]   # hip side first
    spine_chain = list(reversed(path_up(top)))
    if hips not in spine_chain:
        return
    spine_chain = spine_chain[spine_chain.index(hips):]
    # hands: chain ends (not feet, not head) furthest from the up axis through the hips
    axis_d = lambda i: np.linalg.norm((J[i] - J[hips]) - ((J[i] - J[hips]) @ up) * up)
    others = [i for i in leaves if i not in feet and i != top and h[i] > h[hips]]
    if len(others) < 2:
        return
    hands = sorted(others, key=axis_d)[-2:]
    arm_chains = []
    for hd in hands:
        p = list(reversed(path_up(hd)))
        on_spine = [k for k, i in enumerate(p) if i in spine_chain]
        if not on_spine:
            return
        arm_chains.append(p[on_spine[-1] + 1:])                   # shoulder side first
    # front: toes point forwards from the ankles (feet chains' last joints), else the mesh's bulk
    fwd = sum(J[c[-1]] - J[c[-2]] for c in leg_chains if len(c) >= 3) if all(len(c) >= 3 for c in leg_chains) else None
    if fwd is None or np.linalg.norm(fwd - (fwd @ up) * up) < 1e-6:
        fwd = P.mean(0) - J[hips]
    fwd = fwd - (fwd @ up) * up
    if np.linalg.norm(fwd) < 1e-9:
        return
    fwd /= np.linalg.norm(fwd)
    left = np.cross(up, fwd)                          # Y up, facing +Z: the left is +X
    side = lambda c: "Left" if (J[c[-1]] - J[hips]) @ left > 0 else "Right"
    names = {hips: "Hips"}
    for c in leg_chains:
        sd = side(c)
        if len(c) < 3:
            return
        # thigh at the hip, shin at the knee (the joint nearest half way down), foot at the ankle
        knee = min(c[1:-1], key=lambda i: abs(h[i] - (h[c[0]] + h[c[-1]]) / 2))
        ankle = c[c.index(knee) + 1]
        names.update({c[0]: f"{sd}UpLeg", knee: f"{sd}Leg", ankle: f"{sd}Foot"})
    for c in arm_chains:
        sd = side(c)
        if len(c) < 3:
            return
        # the last three joints before the fingers: upper arm, forearm, hand (a collar before them)
        reach = [axis_d(i) for i in c]
        hand = c[-1] if len(c) == 3 else max(c[2:], key=lambda i: -abs(axis_d(i) - 0.9 * max(reach)))
        k = c.index(hand)
        if k < 2:
            return
        names.update({c[k - 2]: f"{sd}Arm", c[k - 1]: f"{sd}ForeArm", hand: f"{sd}Hand"})
        if k >= 3:
            names[c[k - 3]] = f"{sd}Shoulder"
    # head: the spine joint nearest 87 % of the height; spine joints between hips and it
    rel = (h - (P @ up).min()) / H
    above = spine_chain[1:]
    if not above:
        return
    head = min(above, key=lambda i: abs(rel[i] - 0.87))
    names[head] = "Head"
    for k, i in enumerate(spine_chain[1:spine_chain.index(head)]):
        names[i] = "Spine" if k == 0 else f"Spine{k}"
    src["renamed"] = {bones[i]["name"]: nm for i, nm in names.items()}
    for i, nm in names.items():
        bones[i]["name"] = nm


def _colour_swatches(src: dict, colours: dict, linear: bool = True) -> None:
    """Materials with only a colour (no texture, as Xbot's body and joints): a small texture of
    that colour, and their triangles' UVs on it."""
    from PIL import Image
    used = set(np.asarray(src["MAT"]).tolist())
    for mi in sorted(used):
        if mi in src["textures"] or mi not in colours:
            continue
        lin = np.clip(np.array(colours[mi][:3]), 0, 1)
        srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055) if linear else lin
        buf = io.BytesIO()
        Image.new("RGBA", (8, 8), tuple(int(round(c * 255)) for c in srgb) + (255,)).save(buf, "PNG")
        src["textures"][mi] = buf.getvalue()
        src["UV"] = np.asarray(src["UV"], float).copy()
        src["UV"][np.unique(src["T"][np.asarray(src["MAT"]) == mi])] = 0.5


def merge_textures(src: dict) -> None:
    """Several textures (or colour swatches) in one: a grid of cells, every triangle's UVs moved
    into its material's cell (the PS1 model has one 256 x 256 page)."""
    from PIL import Image
    used = sorted(set(np.asarray(src["MAT"]).tolist()))
    if len(set(used) | set(src["textures"])) < 2 or len(src["textures"]) < 2 and set(used) <= set(src["textures"]):
        return
    for mi in used:                                   # no texture and no colour: plain grey
        if mi not in src["textures"]:
            buf = io.BytesIO()
            Image.new("RGBA", (8, 8), (150, 150, 150, 255)).save(buf, "PNG")
            src["textures"][mi] = buf.getvalue()
    mats = used
    if len(mats) < 2:
        return
    cols = int(np.ceil(np.sqrt(len(mats))))
    rows = int(np.ceil(len(mats) / cols))
    cell = 1024 // cols
    page = Image.new("RGBA", (cell * cols, cell * rows))
    T, MAT = src["T"], np.asarray(src["MAT"])
    P, UV = src["P"], np.asarray(src["UV"], float)
    # corners are split per material first, so a vertex shared by two materials gets two UVs
    newP, newUV, newT, newW, newB = [], [], [], [], []
    W = src.get("weights")
    VB = src.get("vbone")
    n = 0
    for i, mi in enumerate(mats):
        r, c = divmod(i, cols)
        im = Image.open(io.BytesIO(src["textures"][mi])).convert("RGBA").resize((cell, cell), Image.LANCZOS)
        page.paste(im, (c * cell, r * cell))
        sel = np.where(MAT == mi)[0]
        verts = np.unique(T[sel])
        remap = {int(v): n + k for k, v in enumerate(verts)}
        uv = UV[verts]
        uv = np.where((uv >= 0) & (uv <= 1), uv, uv % 1.0)
        newUV.append(np.stack([(c + uv[:, 0]) / cols, (r + uv[:, 1]) / rows], 1))
        newP.append(P[verts])
        if W is not None:
            newW += [W[v] for v in verts]
        if VB is not None:
            newB.append(np.asarray(VB)[verts])
        newT.append(np.vectorize(remap.get)(T[sel]))
        n += len(verts)
    buf = io.BytesIO()
    page.save(buf, "PNG")
    order = np.concatenate([np.where(MAT == mi)[0] for mi in mats])
    src.update(P=np.concatenate(newP), UV=np.concatenate(newUV), T=np.concatenate(newT),
               MAT=np.zeros(len(order), int), textures={0: buf.getvalue()})
    if W is not None:
        src["weights"] = newW
    if VB is not None:
        src["vbone"] = np.concatenate(newB)


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
    if path.suffix.lower() in (".glb", ".vrm"):            # VRM (VRoid) is glTF binary
        import glb
        g = glb.read(path)
        out = {"P": g["positions"], "T": g["triangles"], "UV": g["uv"], "MAT": g["materials"],
               "textures": g["textures"]}
        _external_texture(out)
        if "bones" in g:
            w = g["weights"]
            out["bones"], out["weights"] = g["bones"], w
            out["vbone"] = np.array([max(x, key=x.get) if x else -1 for x in w])
        _colour_swatches(out, g.get("colours", {}))
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
           "textures": {k: v for k, (n, v) in c["textures"].items()},
           "missing_textures": c.get("missing_textures") or {}}
    _external_texture(out)
    _colour_swatches(out, c.get("colours", {}), linear=False)     # FBX colours are display values
    if c["bones"]:
        # a real rig (e.g. from Mixamo): joints and the strongest bone of every vertex
        w = c["weights"]
        out["bones"] = c["bones"]
        out["vbone"] = np.array([max(w[i], key=w[i].get) if w[i] else -1 for i in T.ravel()])
        out["weights"] = [w[i] for i in T.ravel()]
    return out


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


def _seen_sides(P, T, size=256, views=64):
    """Per triangle: pixels where it is the nearest surface seen from its front and from its back,
    over `views` directions evenly around the model (orthographic, nothing culled; not only the
    axes, where a sheet of hair can be seen exactly edge-on). A triangle seen from
    behind is one the PlayStation culls where other programs show it (Rogue's temple locks)."""
    front = np.zeros(len(T))
    back = np.zeros(len(T))
    k = np.arange(views) + 0.5                        # Fibonacci sphere
    phi = np.arccos(1 - 2 * k / views)
    theta = np.pi * (1 + 5 ** 0.5) * k
    dirs = list(np.stack([np.cos(theta) * np.sin(phi), np.cos(phi), np.sin(theta) * np.sin(phi)], 1))
    c = P.mean(0)
    R = float(np.linalg.norm(P - c, axis=1).max()) or 1.0
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    for d in dirs:
        d /= np.linalg.norm(d)
        a = np.cross(d, [0, 1, 0] if abs(d[1]) < 0.9 else [1, 0, 0])
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        Q = P - c
        X = (Q @ a / R + 1) * size / 2
        Y = (Q @ b / R + 1) * size / 2
        Z = Q @ d                                    # larger = nearer the viewer at +d
        zb = np.full((size, size), -np.inf)
        idb = np.full((size, size), -1)
        for k, t in enumerate(T):
            xy = np.stack([X[t], Y[t]], 1)
            cr = (xy[1, 0] - xy[0, 0]) * (xy[2, 1] - xy[0, 1]) - (xy[1, 1] - xy[0, 1]) * (xy[2, 0] - xy[0, 0])
            if abs(cr) < 1e-9:
                continue
            x0, y0 = np.maximum(np.floor(xy.min(0)).astype(int), 0)
            x1, y1 = np.minimum(np.ceil(xy.max(0)).astype(int), size - 1)
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            px = np.stack([xs.ravel() + .5, ys.ravel() + .5], 1)
            l1 = ((xy[1, 0] - px[:, 0]) * (xy[2, 1] - px[:, 1]) - (xy[1, 1] - px[:, 1]) * (xy[2, 0] - px[:, 0])) / cr
            l2 = ((xy[2, 0] - px[:, 0]) * (xy[0, 1] - px[:, 1]) - (xy[2, 1] - px[:, 1]) * (xy[0, 0] - px[:, 0])) / cr
            ins = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
            if not ins.any():
                continue
            z = np.stack([l1, l2, 1 - l1 - l2], 1)[ins] @ Z[t]
            pp = px[ins].astype(int)
            yy, xx = pp[:, 1], pp[:, 0]
            near = z > zb[yy, xx]
            zb[yy[near], xx[near]] = z[near]
            idb[yy[near], xx[near]] = k
        ids, n = np.unique(idb[idb >= 0], return_counts=True)
        facing = fn[ids] @ d > 0
        front[ids[facing]] += n[facing]
        back[ids[~facing]] += n[~facing]
    return front, back


def _sheets(P, T, rays=3):
    """Per triangle (as wound in T): True when it is a loose sheet (a lock of hair, a strap): a
    ray backwards from it reaches open air or the front of another surface, where a triangle of
    a closed shape meets the inside (back) of its own shape. When most triangles look like
    sheets, T is wound the other way round and the answer is for the other side."""
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    e1, e2 = B - A, C - A
    n = np.cross(e1, e2)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    cen = (A + B + C) / 3
    eps = 1e-4 * (float(np.ptp(P[:, 1])) or 1.0)
    rng = np.random.default_rng(0)
    def votes(sign):
        out = np.zeros(len(T), int)
        for _ in range(rays):
            jit = rng.normal(size=3) * 0.1
            for i in range(len(T)):
                d = -sign * n[i] + jit
                d /= np.linalg.norm(d)
                o = cen[i] + d * eps
                p = np.cross(d, e2)
                det = (e1 * p).sum(1)
                ok = np.abs(det) > 1e-12
                inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
                tv = o - A
                u = (tv * p).sum(1) * inv
                q = np.cross(tv, e1)
                v = (q @ d) * inv
                t = (e2 * q).sum(1) * inv
                hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps)
                hit[i] = False
                if not hit.any():
                    out[i] += 1                       # open air behind it
                    continue
                j = np.where(hit)[0][np.argmin(t[hit])]
                out[i] += int(sign * n[j] @ d < 0)    # the front of another surface
        return out >= (rays + 1) // 2
    sheet = votes(1)
    if sheet.mean() > 0.5:
        sheet = votes(-1)
    return sheet


def inspect(path: Path) -> dict:
    """What the builder needs to know before an import: size, texture and whether the model is
    rigged (a skeleton with the bones Tekken needs and skin weights). `rigged` False locks the
    import in the builder."""
    path = Path(path)
    if path.suffix.lower() not in (".fbx", ".glb", ".vrm"):
        return {"ok": False, "rigged": False, "problems": ["Use an .fbx (FBX Binary), .glb or .vrm file."]}
    try:
        src = load(path)
    except Exception as error:                        # a damaged or unsupported file
        return {"ok": False, "rigged": False, "problems": [f"The file could not be read: {error}"]}
    info = {"ok": True, "triangles": int(len(src["T"])), "vertices": int(len(np.unique(np.round(src["P"], 5), axis=0))),
            "textured": bool(src.get("textures")), "bones": len(src.get("bones", [])), "problems": [], "missing": []}
    parts = {MI._part(b["name"]) for b in src.get("bones", [])}
    info["missing"] = [k for k, v in NEEDED.items() if v not in parts]
    weighted = sum(1 for w in src.get("weights", []) if w) if "weights" in src else 0
    if src.get("rig_error"):
        info["problems"].append(f"The automatic rig did not work: {src['rig_error']} Place the joints yourself "
                                "in the rig view, or rig the model in Mixamo (FBX Binary, T-pose).")
    elif not src.get("bones"):
        info["problems"].append("The model is not rigged: it has no skeleton. Rig it first (for example "
                                "with Mixamo, then export FBX Binary in T-pose).")
    elif info["missing"]:
        info["problems"].append("The skeleton misses bones Tekken needs: " + ", ".join(info["missing"]) + ".")
    elif weighted < 0.95 * len(src["P"]):
        info["problems"].append("The skin weights are missing for part of the model: weight every vertex to a bone.")
    elif (share := hips_share(src)) is not None and share < CHIBI_HIPS:
        info["problems"].append(f"Chibi build: the hips are at {share:.0%} of the height (Tekken 3 fighters about "
                                "50 %). Tekken's animations stretch such a model into a giant; use a model with a "
                                "human build.")
    info["rigged"] = not info["problems"]
    info["rig"] = rig_view(src)
    info["notes"] = []
    if info["triangles"] > REDUCE_ABOVE:
        info["notes"].append(f"{info['triangles']} triangles: Tekken 3 fighters have 650-1100, so the creator "
                             "reduces it to PS1 size and bakes a new 256 x 256 texture (1 to 3 minutes).")
        info["reduce"] = True
    if not info["textured"]:
        info["problems"].append("The model has no embedded texture: choose its texture image (if it came as a separate file), or it is drawn without one.")
    info["parts"] = PR.summary(PR.find(src)) if info["rigged"] else []
    info["checks"] = checks(src, info, weighted)
    return info


# hips below 30 % of the height: a chibi (KayKit's adventurers, 19-23 %); tested 2026-10-19: the
# Mage came out as a stretched giant in a fight, so such models are not imported
CHIBI_HIPS = 0.30


def rig_view(src: dict) -> dict | None:
    """For a model without a skeleton of its own: the joints the automatic rig found (or the
    player placed), how the model was turned, and its points seen from the front (x, y) and the
    side (z, y), for the builder's rig view. None for a rigged file."""
    if not (src.get("auto_rig") or src.get("rig_error")):
        return None
    P = np.asarray(src["P"], float)
    step = max(1, len(P) // 2500)
    pick = P[::step]
    r = lambda a: np.round(a, 4).tolist()
    parts = []
    if src.get("bones") is not None and src.get("vbone") is not None:
        for b in np.asarray(src["vbone"])[::step]:   # each point's body part, for the pose preview
            prt, side = MI._part(src["bones"][int(b)]["name"]) if b >= 0 else ("spine", None)
            parts.append((prt or "spine") + (side or "" if prt in PAIRS else ""))
    return {"joints": src.get("auto_rig"), "error": src.get("rig_error"), "turn": src.get("turn"),
            "by_hand": bool(RIG_JOINTS), "turned_by_hand": not isinstance(RIG_TURN, str), "paint": RIG_PAINT or [], "front": r(pick[:, [0, 1]]), "side": r(pick[:, [2, 1]]),
            "depth": r(pick[:, 2]), "parts": parts, "markers": list(__import__("autorig").MARKERS)}


def hips_share(src: dict) -> float | None:
    """Height of the hips (the thigh bones) as a share of the model's height, or None."""
    P = np.asarray(src["P"], float)
    hips = [b["matrix"][1][3] for b in src.get("bones") or [] if MI._part(b["name"])[0] == "thigh"]
    if not hips or not len(P) or np.ptp(P[:, 1]) <= 0:
        return None
    return (float(np.mean(hips)) - P[:, 1].min()) / float(np.ptp(P[:, 1]))


def checks(src: dict, info: dict, weighted: int) -> list:
    """The pre-import check list the builder shows: geometry, materials and rigging, each line
    {"area", "level" ("ok", "info", "warn" or "bad"), "text"}. Only what the importer is known to do."""
    out = []

    def add(area, level, text):
        out.append({"area": area, "level": level, "text": text})

    P, T = np.asarray(src["P"], float), np.asarray(src["T"])
    n = len(T)
    if n > REDUCE_ABOVE:
        add("Geometry", "info", f"{n} triangles: reduced to PS1 size (see below)")
    else:
        add("Geometry", "ok", f"{n} triangles: PS1 size, kept as it is")
    e1, e2 = P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]
    area = np.linalg.norm(np.cross(e1, e2), axis=1)
    flat = int((area <= 1e-9 * max(float(area.max()), 1e-12)).sum()) if n else 0
    if flat:
        add("Geometry", "warn", f"{flat} triangles have no area (they are left out)")
    size = P.max(0) - P.min(0) if len(P) else np.zeros(3)
    if size[1] > 0:
        spread = max(size[0], size[2]) / size[1]
        if spread < 0.5:
            add("Geometry", "warn", "The arms are not spread out: the importer is tested with T-pose and "
                                    "A-pose models; arms-down models may stretch at the shoulders")
        else:
            add("Geometry", "ok", "Pose: arms spread out (T-pose or A-pose)")
        # build: Tekken 3's fighters have the hips at about half their height; the import keeps
        # the model's own build (100Avatars' Lydia: hips at 73 %, she comes out on stilts)
        share = hips_share(src)
        if share is not None:
            if share > 0.62:
                add("Geometry", "warn", f"Long legs: the hips are at {share:.0%} of the height (Tekken 3 "
                                        "fighters about 50 %); the fighter keeps this build and looks stretched")
            elif CHIBI_HIPS <= share < 0.35:
                add("Geometry", "warn", f"Short legs: the hips are at {share:.0%} of the height (Tekken 3 "
                                        "fighters about 50 %); the fighter keeps this build")
    # materials
    mats = sorted(set(np.asarray(src["MAT"]).tolist()))
    tex = src.get("textures") or {}
    bare = [m for m in mats if m not in tex]
    add("Materials", "ok" if not bare else "warn",
        f"{len(mats)} material{'s' if len(mats) != 1 else ''}, {len(tex)} embedded texture{'s' if len(tex) != 1 else ''}"
        + (f"; {len(bare)} without a texture are drawn in plain colour" if bare else ""))
    if len(mats) > 1:
        add("Materials", "ok", f"The {len(mats)} materials share one 256 x 256 texture page (each gets a cell)")
    wanted = sorted({Path(str(f).replace("\\", "/")).name for f in (src.get("missing_textures") or {}).values() if f})
    if wanted:
        add("Materials", "ok" if EXTERNAL_TEXTURE else "warn",
            ("Your texture image is used for the material" if EXTERNAL_TEXTURE else "The model asks for a texture file it does not contain")
            + f" ({', '.join(wanted)})" + ("" if EXTERNAL_TEXTURE else ": choose it as the texture image"))
    UV = np.asarray(src["UV"], float)
    if len(UV) and n:
        tri = UV[T]
        wraps = int(((tri < -1e-3) | (tri > 1 + 1e-3)).any(axis=(1, 2)).sum())
        if wraps:
            add("Materials", "warn", f"{wraps} triangles repeat their texture (UVs outside 0-1): "
                                     "they may look smeared, as the PS1 page cannot repeat")
    # rigging
    bones = src.get("bones") or []
    if src.get("rig_error"):
        add("Rigging", "bad", f"No skeleton, and the automatic rig did not work: {src['rig_error']}")
    elif src.get("auto_rig"):
        add("Rigging", "info", "No skeleton in the file: " + ("rigged with the joints you placed" if RIG_JOINTS else
                               "rigged automatically from the model's shape") + ". Check the joints in the rig view")
    elif not bones:
        add("Rigging", "bad", "No skeleton")
    if bones and not src.get("auto_rig"):
        found = len(NEEDED) - len(info.get("missing", []))
        add("Rigging", "ok" if found == len(NEEDED) else "bad",
            f"{len(bones)} bones; {found} of the {len(NEEDED)} Tekken needs found")
        share = weighted / max(len(src["P"]), 1)
        add("Rigging", "ok" if share >= 0.95 else "bad", f"Skin weights on {share:.0%} of the vertices")
        if src.get("renamed"):
            add("Rigging", "warn", f"Bone names not standard: {len(src['renamed'])} bones recognised from the skeleton's shape")
    return out


def build(root: Path, model: int, path: Path, log=print, parts=None, settings=None):
    """Imports a model file over a donor model; a high-poly file is reduced first (reduce.py),
    smaller and smaller until it fits the donor's slot. parts: choices for the parts that stick
    out (protrusions.py; default: folded down). settings (reduced models only): {"head": 4, 2 or
    1 times the detail on the head, "detail": 100, 80 or 60 % of the most the slot holds}."""
    settings = settings or {}
    src = load(Path(path))
    PR.apply(src, parts, log=log)
    if len(src["T"]) <= REDUCE_ABOVE:
        merge_textures(src)                           # one texture page (reduce bakes its own)
        return _build(root, model, src, log)
    import reduce as RD
    # a first guess from what reduced models need (flat quads included): ~35.5 bytes of GPU packets
    # and ~25.5 bytes of model per triangle; then 7 % fewer per failed try
    rid = X.FIRST_MODEL_RECORD + 4 * model
    slot = len(X.records(root, [rid])[rid])
    target = int(min(MI.MAX_PACKET_BYTES / 35.5, slot / 25.5) * 0.97 * settings.get("detail", 100) / 100)
    head = float(settings.get("head", 4))
    for k in range(8):
        low = RD.reduce(src, target, log=log, head_detail=head)
        try:
            return _build(root, model, low, log, degrade=k == 7)
        except MI.Budget as error:
            if "texture coordinates" in str(error) and head > 1.0 and ("row 19" in str(error) or "row 20" in str(error)):
                # the head row (big hair) has more corners than its 255 texture coordinates:
                # less extra detail on the head first (the face keeps its texture density)
                head = head / 2
                log(f"{target} triangles do not fit ({error}); trying {head:g}x detail on the head")
                continue
            log(f"{target} triangles do not fit ({error}); trying fewer")
            # a row over its texture coordinates says how many it needs: shrink by that share at
            # once (MeganTheFox needed six 100 s tries of 7 % each)
            need = re.search(r"needs (\d+) texture coordinates", str(error))
            share = MI.MAX_UVS / int(need.group(1)) * 0.97 if need else 1.0
            target = int(target * min(0.93, share))
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
    if "bones" not in src:                           # load() rigs every model; this one could not be
        raise ValueError(src.get("rig_error") or "The model has no skeleton.")
    J0, part = rig_from_skeleton(src["bones"], src["vbone"], P)
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
    both = np.zeros(len(T), bool)
    if not src.get("reduced"):
        # triangles seen from behind from outside (other programs draw both sides, the
        # PlayStation culls them): seen only from behind -> turned, from both sides -> drawn twice
        # looked at in the pose the game draws (G), with the winding as it will be written; the
        # side most pixels see is the drawn side (the game's Y is a mirror)
        Tout = np.where(outward[:, None], T, T[:, [0, 2, 1]])
        front, back = _seen_sides(G, Tout)
        if back.sum() > front.sum():
            front, back = back, front
        seen = front + back
        wrong, right = back, front                       # pixels of the side the game would cull
        turn = (wrong >= 3) & (wrong > 4 * right)
        both = (wrong >= 2) & ~turn & (wrong > 0.05 * seen)
        # thin sheets (strands of hair): triangles on an open or non-manifold edge show their back
        # in some pose sooner or later
        count = {}
        for t in Tw:
            for k in range(3):
                e = (min(t[k], t[(k + 1) % 3]), max(t[k], t[(k + 1) % 3]))
                count[e] = count.get(e, 0) + 1
        loose = np.array([any(count[(min(t[k], t[(k + 1) % 3]), max(t[k], t[(k + 1) % 3]))] != 2 for k in range(3))
                          for t in Tw])
        sheet = _sheets(G, Tout)
        # a loose sheet is seen from both sides in some pose: drawn twice, never just turned
        both |= loose | sheet
        turn &= ~both
        outward = np.where(turn, ~outward, outward)
        log(f"seen from outside: {int(turn.sum())} triangles turned, {int(both.sum())} drawn from both sides")
    faces = []
    for i, t in enumerate(T):
        v = list(t) if outward[i] else [t[0], t[2], t[1]]
        # geometry on welded vertices (UVs are kept per polygon corner)
        faces.append({"v": [int(weld[x]) for x in v], "hard": False, "suv": [tuple(UV[j]) for j in v]})
        if both[i]:
            v = v[::-1]
            faces.append({"v": [int(weld[x]) for x in v], "hard": False, "suv": [tuple(UV[j]) for j in v]})
    # texture: the file's own layout, 4-bit with a CLUT per UV island (group)
    if src.get("textures"):
        rgba = Image.open(io.BytesIO(next(iter(src["textures"].values())))).convert("RGBA")
        img = np.asarray(rgba.convert("RGB"))
        clear = np.asarray(rgba.getchannel("A").resize((256, 256), Image.NEAREST)) < 128
    else:                                            # no texture in the file: plain grey
        img = np.full((256, 256, 3), 150, np.uint8)
        clear = np.zeros((256, 256), bool)
    th, tw = img.shape[:2]
    if (tw, th) != (256, 256):
        img = np.asarray(Image.fromarray(img).resize((256, 256), Image.LANCZOS))
    if src.get("reduced"):                           # the bake already looked through them
        clear[:] = False
    if clear.any():
        # see-through texels (hair strands): their colour is filled from opaque neighbours so it
        # does not take palette entries; after quantising they get PS1 colour 0 (not drawn)
        img = img.copy()
        known = ~clear
        for _ in range(64):
            if known.all():
                break
            acc = np.zeros(img.shape, float)
            n = np.zeros(known.shape)
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                acc += np.roll(np.roll(img * known[..., None], dy, 0), dx, 1)
                n += np.roll(np.roll(known, dy, 0), dx, 1)
            new = ~known & (n > 0)
            img[new] = (acc[new] / n[new][:, None]).astype(np.uint8)
            known |= new
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
    # see-through texels count only well inside the polygons: a soft alpha rim along the UV edges
    # of a painted texture is no cut-out (holes along Tommy's wrists)
    core = owner >= 0
    for _ in range(2):
        core = core & np.roll(core, 1, 0) & np.roll(core, -1, 0) & np.roll(core, 1, 1) & np.roll(core, -1, 1)
    clear &= core
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
    if len(group) < len(ids):                        # islands without a texel of their own (all covered
        group = np.concatenate([np.asarray(group, int), np.zeros(len(ids) - len(group), int)])   # by others)
    clear &= owner >= 0
    if clear.sum() > 0.25 * (owner >= 0).sum():      # alpha that is not a cut-out (an export quirk)
        log(f"texture alpha ignored: {int(clear.sum())} of {int((owner >= 0).sum())} used texels would vanish")
        clear[:] = False
    if clear.any():
        # per palette with see-through texels: its least used colour gives way to colour 0
        idx = idx.copy()
        gt = np.where(owner >= 0, np.asarray(group)[np.maximum(owner, 0)], -1)
        pal = [list(palette[16 * k:16 * k + 16]) for k in range(len(palette) // 16)]
        rgb5 = lambda c: np.array([(c & 31) * 8, ((c >> 5) & 31) * 8, ((c >> 10) & 31) * 8], float)
        for k in np.unique(gt[clear]):
            solid = (gt == k) & ~clear
            use = np.bincount(idx[solid], minlength=16)
            slot = int(np.argmin(use))
            others = [j for j in range(16) if j != slot]
            cols = np.array([rgb5(pal[k][j]) for j in others])
            move = solid & (idx == slot)
            if move.any():
                d = ((img[move].astype(float)[:, None, :] - cols[None]) ** 2).sum(2)
                idx[move] = np.array(others)[d.argmin(1)]
            pal[k][slot] = 0x0000
            idx[(gt == k) & clear] = slot
        palette = [c for p_ in pal for c in p_]
        log(f"{int(clear.sum())} see-through texels drawn as PS1 colour 0 (not drawn)")
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
    ap.add_argument("--parts", default="{}", help="JSON {part id: {mode: fold|keep|remove, angle}}")
    ap.add_argument("--preview", type=Path, help="write a PNG of the model with the parts applied")
    ap.add_argument("--texture", type=Path, help="an image for the materials without a texture of their own")
    ap.add_argument("--settings", default="{}", help='JSON {"head": 4|2|1, "detail": 100|80|60} (reduced models)')
    ap.add_argument("--rig", type=Path, help='JSON {"joints": {name: [x, y, z]}, "turn": 3x3 | "auto"} for a model without a skeleton')
    a = ap.parse_args()
    set_external_texture(a.texture)
    if a.rig and a.rig.is_file():
        r = json.loads(a.rig.read_text(encoding="utf-8"))
        set_rig(r.get("joints"), r.get("turn", "auto"), r.get("paint"))
    X.setup(a.root)
    if a.check:
        print(json.dumps(inspect(a.model_file)))
        return
    parts = json.loads(a.parts)
    if a.preview:
        src = load(a.model_file)
        found = PR.find(src)
        used = PR.apply(src, parts, log=lambda *_: None)
        a.preview.write_bytes(PR.preview(src, found))
        print(json.dumps({"angles": used}))
        return
    if a.model is None or a.out is None:
        ap.error("--model and --out are needed for an import")
    info = inspect(a.model_file)
    if not info["rigged"]:
        raise SystemExit("ERROR " + " ".join(info["problems"]))
    stock, new, tx, report = build(a.root, a.model, a.model_file, parts=parts, settings=json.loads(a.settings))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.model, stock, new, tx))
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "texture")}, default=str))
    print(f"OK direct import over model {a.model}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
