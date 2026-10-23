"""Tekken rebuild: a big modern model rebuilt on the donor's own Namco model (rules:
docs/knowledge/t3-model-style.md, plan: docs/plans/direct-import.md "Tekken rebuild").

reduce.py makes a free shell of ~900 triangles whose edges run anywhere: across the shoulders and
elbows (they tear when the game bends a row), thin flat limbs, hair as one rigid sheet. Here the
donor's own polygons are kept instead - Namco's joint rings, its rigid rows, its head layout - and
only moved onto the import's surface (template.py); the texture is baked from the original as
reduce.py does. The result goes to direct_import._build like a reduced model.

rebuild(root, model, src) -> the same dict as reduce.reduce (per corner P, T, UV, MAT, textures,
bones, weights, vbone, reduced, face_tris)."""
from __future__ import annotations
import numpy as np

import direct_import as DI
import model_export as X
import model_import as MI
import reduce as RD
import template

# the least share of the donor's thickness a row keeps: a slim import's body may take 30 % (the
# template's default is 55 %), its arms and hands keep 60 %: Namco draws limbs fuller than life
THINNEST = {r: 0.3 for r in (1, 3, 5, 6, 7, 8, 9, 10, 11, 15, 19)}
THINNEST.update({r: 0.6 for r in (12, 13, 14, 16, 17, 18)})
FULLER = {r: 0.7 for r in (12, 13, 16, 17)}    # thin arms move part of the way to the donor's
WIDEST = {19: 3.0}    # a head may grow to 3x the donor's (an anime head with its hair; template: 1.9)
QUAD_BENDS = (30.0, 45.0, 60.0, 90.0)   # Namco's quads bend more than a free shell's pairs may
                                        # (_pair_quads: 12); more when the packets do not fit
FLAT_BELOW = (8.0, 16.0, 30.0)    # then polygons this flat are flat-shaded (cheaper GPU packets)
FEWER = (6, 12, 24)               # then the smallest polygons left out (with quads up to 90 degrees)


def _row_of(prt, side, rows_of):
    if prt in ("spine", "pelvis", "head"):
        return {"spine": 1, "pelvis": 3, "head": 19}[prt]
    if prt in MI.PAIRS and side:
        return rows_of(prt, side)
    return None


SHAPE_ROWS = {"arms": (12, 13, 16, 17), "legs": (5, 6, 8, 9)}      # thickness about the bone
SHAPE_LIMITS = (70, 150)                                            # per cent


def _shape(V, owner, shape, J, F, ends, to_fbx, rows_of, log):
    """The user's proportions (per cent, 100 = the import's own): "head" (about the neck joint),
    "arms" and "legs" (thickness about the bone; the length stays, the animations need it),
    "hands" (about the wrist) and "feet" (about the ankle)."""
    def pct(k):
        return float(np.clip(shape.get(k, 100), *SHAPE_LIMITS)) / 100
    groups = [("head", [19], None)]
    groups += [("hands", [rows_of("hand", sd)], None) for sd in "LR"]
    groups += [("feet", [rows_of("foot", sd)], None) for sd in "LR"]
    child = {5: 6, 6: 7, 8: 9, 9: 10, 12: 13, 13: 14, 16: 17, 17: 18}
    groups += [(k, [r], child[r]) for k, rows in SHAPE_ROWS.items() for r in rows]
    done = set()
    for key, rows, c in groups:
        k = pct(key)
        if abs(k - 1) < 1e-3:
            continue
        for r in rows:
            sel = owner == r
            a = to_fbx(J[r])
            if c is None:                                     # whole part about its joint
                V[sel] = a + (V[sel] - a) * k
            else:                                             # thickness about the bone line
                b = to_fbx(J[c])
                ax = (b - a) / np.linalg.norm(b - a)
                d = V[sel] - a
                along = np.outer(d @ ax, ax)
                V[sel] = a + along + (d - along) * k
        done.add(key)
    if done:
        log("proportions: " + ", ".join(f"{k} {pct(k) * 100:.0f} %" for k in sorted(done)))


def vertex_rows(src: dict, part, rows_of) -> np.ndarray:
    """The Tekken row of every original vertex: of its heaviest bone; a bone Tekken has no row for
    (hair, cloth) takes the row of its nearest known parent (hair hangs from the head), then of
    the nearest known joint. Also what the anatomy view shows (anatomy.py)."""
    bones = src["bones"]
    brow = [_row_of(*MI._part(b["name"]), rows_of) for b in bones]
    at = lambda b: np.array([b["matrix"][k][3] for k in range(3)])
    known = [i for i, r in enumerate(brow) if r is not None]
    for i, b in enumerate(bones):
        if brow[i] is not None:
            continue
        p = b["parent"]
        while p >= 0 and _row_of(*MI._part(bones[p]["name"]), rows_of) is None:
            p = bones[p]["parent"]
        if p >= 0:
            brow[i] = _row_of(*MI._part(bones[p]["name"]), rows_of)
        elif known:
            brow[i] = brow[min(known, key=lambda k: np.linalg.norm(at(bones[k]) - at(b)))]
        else:
            brow[i] = 1
    return np.array([brow[max(w, key=w.get)] if w else _row_of(*part[i], rows_of) or 1
                     for i, w in enumerate(src["weights"])])


def rebuild(root, model: int, src: dict, log=print, shape=None, fewer=0) -> dict:
    """shape: proportions in per cent (_shape); fewer: the smallest polygons left out (a slot
    whose GPU packets the donor's polygons overflow)."""
    rid = X.FIRST_MODEL_RECORD + 4 * model
    m = X.records(root, [rid])[rid]
    fr = DI.frames(root, m, src, log=lambda *a: None)
    W, Q, s, J, F, ends, J0, part, rows_of = (fr[k] for k in ("W", "Q", "s", "J", "F", "ends", "J0", "part", "rows_of"))
    base = RD.original(src, log)
    Pw, weld, Tw, H, opaque = (base[k] for k in ("Pw", "weld", "Tw", "H", "opaque"))
    hips = J0["hips"]
    to_fbx = lambda x: Q.T @ ((np.asarray(x) - W[3][1]) / s) + hips
    # the toe from the mesh, not the skeleton: the foot's point furthest forward (a toe or ball
    # bone can sit above the ankle - NIKKI's heels - and the foot then collapsed into a spike)
    P = src["P"]
    for side in "LR":
        on = np.array([p == ("foot", side) for p in part])
        if on.sum() >= 3:
            tip = P[on][np.argmax(P[on][:, 2])]
            ends[rows_of("foot", side)] = fr["g"](np.array([J0["foot" + side][0], tip[1], tip[2]]))
    bones = src["bones"]
    vrow = vertex_rows(src, part, rows_of)
    To = Tw[opaque]
    vrow_w = np.ones(len(Pw), int)
    vrow_w[weld] = vrow
    corner = vrow_w[To]
    trow = np.where(corner[:, 1] == corner[:, 2], corner[:, 1], corner[:, 0])
    body = template.build(m, X.bind(m), F, J, ends, to_fbx, Pw, To, trow, log=log, W=W, any_page=True, thinnest=THINNEST,
                          fixed=(7, 10), fuller=FULLER, paired_only=MI.donor_frames(root, m),
                          no_head_for_body=True, fit_torso=True,
                          widest=WIDEST, fit_head=True)
    V = np.asarray(body["positions"], float)
    owner = np.asarray(body["owner"])
    face_chart = {c for c, w in body["chart_weight"].items() if w >= 4}
    if fewer:
        Vb = np.asarray(body["positions"], float)
        def area(f):
            v = Vb[f["v"]]
            a = np.linalg.norm(np.cross(v[1] - v[0], v[2] - v[0]))
            return a + (np.linalg.norm(np.cross(v[2] - v[1], v[3] - v[1])) if len(v) == 4 else 0)
        small = set(sorted(range(len(body["faces"])), key=lambda i: area(body["faces"][i]))[:fewer])
        body["faces"] = [f for i, f in enumerate(body["faces"]) if i not in small]
        log(f"the {fewer} smallest polygons left out (GPU packets)")
    tris, face, partner = [], [], []
    for f in body["faces"]:
        v = f["v"]
        n = len(tris)
        for t in [(v[0], v[1], v[2])] + ([(v[1], v[3], v[2])] if len(v) == 4 else []):
            tris.append(t)
            face.append(f["chart"] in face_chart)
        partner += [n + 1, n] if len(v) == 4 else [-1]
    Fc = np.array(tris)
    face = np.array(face)
    partner = np.array(partner)
    used = np.unique(Fc)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    V, owner, Fc = V[used], owner[used], remap[Fc]
    # feet flat, as Namco's: a high heel points the foot down and the animations keep it so
    # (the boots ended in points); the foot turns about the ankle onto the donor's foot line
    for side in "LR":
        r = rows_of("foot", side)
        sel = owner == r
        own = [np.array(sl[1], float) for sl in X.bind(m).get(r, []) if sl is not None and sl[0] == r]
        if not sel.any() or not own:
            continue
        tip_d = max(own, key=np.linalg.norm)                     # the donor's toe
        flat = to_fbx(J[r] + F[r] @ tip_d) - to_fbx(J[r])        # the donor's toe line, placed
        here = to_fbx(ends[r]) - to_fbx(J[r])                    # the import's
        ank = to_fbx(J[r])
        R = X.align(here / np.linalg.norm(here), flat / np.linalg.norm(flat))
        V[sel] = ank + (V[sel] - ank) @ R.T
    log(f"rebuilt on the donor's model: {len(Fc)} triangles, {len(V)} vertices")
    # one bone per vertex, the bone of its row (Namco's rigid rows; the joint rings are shared)
    bone_of = {}
    for bi, b in enumerate(bones):
        r = _row_of(*MI._part(b["name"]), rows_of)
        if r is not None and r not in bone_of:
            bone_of[r] = bi
    missing = sorted(set(owner.tolist()) - set(bone_of))
    if missing:
        raise ValueError(f"No bone for rows {missing}: the rebuild needs a full skeleton.")
    neck = MI.joint(bones, "head")
    neck_y = neck[1] if neck is not None else Pw[:, 1].max() - 0.13 * H
    # hair hanging below the neck covers the shoulders, chest and back of the original; the body
    # is baked from what lies under it (painted on, loose hair looked like flecks on the skin);
    # the hair stays on the head
    T = src["T"]
    tc = vrow[T]
    hair = (np.where(tc[:, 1] == tc[:, 2], tc[:, 1], tc[:, 0]) == 19) & (Pw[weld[T]].mean(1)[:, 1] < neck_y)
    body = owner[Fc].max(1) != 19
    # the face: the donor head's face polygons and every head polygon facing forward below the
    # hair line (reduce's rule): a big anime face put the elf's eyes outside the donor's face
    cen = V[Fc].mean(1)
    fn = np.cross(V[Fc[:, 1]] - V[Fc[:, 0]], V[Fc[:, 2]] - V[Fc[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    top = V[:, 1].max()
    face = face | ((owner[Fc].max(1) == 19) & (fn[:, 2] > 0.3) & (cen[:, 1] < neck_y + 0.78 * (top - neck_y))
                   & (cen[:, 1] > neck_y))
    UVl, png, face = RD.bake_atlas(V, Fc, src, base, neck_y, log=log, face=face, partner=partner,
                                   see_through=(body, hair))
    if shape:                    # after the bake: the texture was taken at the import's own shape
        _shape(V, owner, shape, J, F, ends, to_fbx, rows_of, log)
    Pc = V[Fc.ravel()]
    Tc = np.arange(len(Pc)).reshape(-1, 3)
    wts = [{bone_of[int(owner[v])]: 1.0} for v in Fc.ravel()]
    return {"P": Pc, "T": Tc, "UV": UVl.reshape(-1, 2) / RD.ATLAS, "MAT": np.zeros(len(Tc), int),
            "textures": {0: png}, "bones": bones, "weights": wts,
            "vbone": np.array([next(iter(w)) for w in wts]), "reduced": True, "quad_bend": QUAD_BENDS[0], "turn_hidden": True,
            "face_tris": np.where(face)[0].tolist()}
