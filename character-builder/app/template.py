"""The donor's own Namco model as a template for an import (rules: docs/knowledge/t3-model-style.md).

Every vertex of the donor's body rows (1-20) keeps its polygons, its joint seams and its place in
Namco's topology, but moves onto the imported character's surface: placed in the import's row
frame (the donor's local coordinates, stretched along the bone to the import's bone length),
then pushed along the ray from its bone (the head: from the head's centre) to the outermost
surface of the original. So the face, shoulders, elbows and the front/back detail split stay
Namco's, the shape becomes the import's.

build(...) -> the same body dict as lowpoly.build (FBX space): positions, owner (row), faces
[{"v", "chart", "flat"}] (triangle (0, 1, 2) facing out), normals, chart_weight."""
from __future__ import annotations
import numpy as np

import anim_model as A
from fmt import row, block, parse_b, parse_c_ps1
import lowpoly

SECOND = {2: 1, 4: 3, 20: 19}
CHILD = {1: 19, 5: 6, 6: 7, 8: 9, 9: 10, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18}


def height_of(P):
    return float(P[:, 1].max() - P[:, 1].min())


def _neighbours(r):
    out = {r}
    for c, p in A.ROW_PARENT.items():
        if p == r:
            out.add(c)
        if c == r and p:
            out.add(p)
    return out


def build(m, bind, F, J, ends_game, to_fbx, P, Tr, trow, log=print, W=None):
    """m: donor 3DMK; bind: model_export.bind(m); F, J: the import's row frames and joints (game
    space, T-pose); ends_game: {"head", "hand L/R" -> row 14/18 tip, "toe" per foot row} as
    {row: end point}; to_fbx: game point -> FBX point; P, Tr, trow: the original."""
    rows = [r for r in range(1, 21) if r in bind]
    frame_of = lambda r: SECOND.get(r, r)
    # 1. the donor's own vertices (one per (row, local coordinates)), placed in the import
    key_id, verts, owner = {}, [], []
    for r in rows:
        for sl in bind[r]:
            if sl is None or sl[0] != r:
                continue
            k = (r, sl[1])
            if k not in key_id:
                key_id[k] = len(verts)
                verts.append(np.array(sl[1], float))
                owner.append(frame_of(r))
    verts = np.array(verts)
    owner = np.array(owner)
    G = np.zeros_like(verts)
    for fr in sorted(set(owner.tolist())):
        sel = owner == fr
        p0 = verts[sel] @ F[fr].T + J[fr]
        if W is not None and fr in (11, 15, 2):
            # the collarbones (and the chest layer) are part of the chest: placed with the
            # torso's transform, so they join it as on the donor (their own joint sits
            # elsewhere on the import and would tear the chest apart)
            Pd = verts[sel] @ W[fr][0].T + W[fr][1]
            p0 = (Pd - W[1][1]) @ (F[1] @ W[1][0].T).T + J[1]
        end = J[CHILD[fr]] if fr in CHILD else ends_game.get(fr)
        if fr == 3:                                            # pelvis: down to between the hips
            end = (J[5] + J[8]) / 2 + (J[5] - J[1]) * 0.0
        if end is not None:
            u = end - J[fr]
            ln = np.linalg.norm(u)
            u /= ln
            along = (p0 - J[fr]) @ u
            ext = max(float(along.max()), 1e-6)
            k = float(np.clip(ln / ext, 0.6, 1.7)) if fr not in (1, 3, 11, 15, 14, 18, 19) else 1.0
            p0 = p0 + np.outer(along * (k - 1), u)
        G[sel] = p0
    # 1b. faces: the donor's polygons (stored corners d0..d3 face inwards; ours (d0, d2, d1, d3))
    faces = []
    for r in rows:
        w = row(m, r)
        if w[1] <= 2:
            continue
        slots = bind[r]
        prims = parse_c_ps1(block(m, w[2]))
        pi = -1
        for k, fam in enumerate(parse_b(block(m, w[1]))):
            for rec in fam:
                pi += 1
                c = A.prim_verts(k, rec)
                if any(i >= len(slots) or slots[i] is None for i in c):
                    continue
                _, mat, puv = prims[pi]
                if mat is None or None in puv or mat & 0x100:
                    continue
                ids = [key_id.get((slots[i][0], slots[i][1])) for i in c]
                if None in ids or len(set(ids)) < len(ids):
                    continue
                v = [ids[0], ids[2], ids[1]] + ([ids[3]] if len(ids) == 4 else [])
                # Namco's own choice of flat (families 0, 1) or gouraud (2, 3) shading
                # and Namco's texture layout: the donor's own UVs and CLUT (8-bit texel units
                # for 8-bit materials), in our corner order
                uv = [puv[0], puv[2], puv[1]] + ([puv[3]] if len(ids) == 4 else [])
                faces.append({"v": v, "row": frame_of(r), "hard": k < 2, "duv": uv, "dmat": mat})
    import os
    noproject = bool(os.environ.get("T3CB_NOPROJECT"))      # offline study: the placed template
    # 2. radial morph: every vertex keeps the donor's own detail and takes the import's
    # thickness. From its bone (the head: from the head's centre) along the line through the
    # vertex, the outermost surface of the import (R_imp) and of the placed donor model
    # (R_don) are measured; the vertex moves to ratio R_imp / R_don of its distance. The ratio
    # field is smoothed over the mesh, so bumps of the donor (nose, chest, kneecap) stay and
    # the import's volume is taken without jagged steps.
    out = np.array([to_fbx(p) for p in G])
    height = height_of(P)
    tri_of_row = {}
    for f in faces:
        v = f["v"]
        for t in [(v[0], v[1], v[2])] + ([(v[1], v[3], v[2])] if len(v) == 4 else []):
            tri_of_row.setdefault(f["row"], []).append(t)
    origin_of = np.zeros_like(out)
    for fr in sorted(set(owner.tolist())):
        sel = np.where(owner == fr)[0]
        a_ = to_fbx(J[fr])
        if fr == 19:
            top = to_fbx(ends_game[19])
            origin_of[sel] = a_ + (top - a_) * 0.45
            continue
        end = J[CHILD[fr]] if fr in CHILD else ends_game.get(fr)
        if fr == 3:
            end = (J[5] + J[8]) / 2
        if fr in (11, 15):                     # the shoulder pieces: from the spine
            a_, end = to_fbx(J[1]), J[19]
        b_ = to_fbx(end) if end is not None else a_
        d_ = b_ - a_
        t_ = np.clip((out[sel] - a_) @ d_ / max(d_ @ d_, 1e-12), 0, 1)
        origin_of[sel] = a_ + t_[:, None] * d_
    ratio = np.full(len(out), np.nan)
    if not noproject:
        for fr in sorted(set(owner.tolist())):
            sel = np.where(owner == fr)[0]
            o = origin_of[sel]
            dv = out[sel] - o
            dist = np.linalg.norm(dv, axis=1)
            ok = dist > 1e-6
            u = np.where(ok[:, None], dv / np.maximum(dist, 1e-9)[:, None], 0)
            reach = 3.0 * np.maximum(dist, 1e-3)
            rows_i = [19] if fr == 19 else list(_neighbours(fr))
            r_imp = lowpoly.ray_hits(o, u, P, Tr[np.isin(trow, rows_i)], reach)
            own = [t for r2 in ([19, 20] if fr == 19 else [fr]) for t in tri_of_row.get(r2, [])]
            r_don = lowpoly.ray_hits(o, u, out, np.array(own), reach) if own else np.full(len(sel), np.nan)
            q = r_imp / np.where(np.isnan(r_don), dist, r_don)
            ratio[sel] = np.where(ok, np.clip(q, 0.55, 1.9), np.nan)
        nb = [set() for _ in range(len(out))]
        for f in faces:
            for x in f["v"]:
                nb[x].update(y for y in f["v"] if y != x and owner[y] == owner[x])
        r_ = ratio.copy()
        for it in range(8):
            nr = r_.copy()
            for i, ns in enumerate(nb):
                vals = [r_[j] for j in ns if not np.isnan(r_[j])]
                if not vals:
                    continue
                m_ = float(np.median(vals)) if it < 2 else float(np.mean(vals))
                keep_w = 0.0 if np.isnan(r_[i]) else (0.4 if owner[i] == 19 else 0.5)
                nr[i] = m_ if np.isnan(r_[i]) else keep_w * r_[i] + (1 - keep_w) * m_
            r_ = nr
        r_ = np.where(np.isnan(r_), 1.0, r_)
        out = origin_of + (out - origin_of) * r_[:, None]
    # 3a. the donor's own extras on the head that the import has not got (Nina's ponytail):
    # head polygons hanging below the neck joint are left out
    neck_f = to_fbx(J[19])
    up_f = to_fbx(J[19] + (ends_game[19] - J[19])) - neck_f
    up_f /= np.linalg.norm(up_f)
    dropped = 0
    keep_f = []
    for f in faces:
        if owner[f["v"][0]] == 19 and all((out[i] - neck_f) @ up_f < -0.02 * height_of(P) for i in f["v"]):
            dropped += 1
            continue
        keep_f.append(f)
    faces = keep_f
    if dropped:
        log(f"template: {dropped} head polygons below the neck left out (the donor's own hair)")
    # 3b. vertices the projection put (nearly) on one spot, in the same row, become one; the
    # polygons that collapse with them were invisible anyway
    height = float(P[:, 1].max() - P[:, 1].min())
    eps = 0.004 * height
    alias = list(range(len(out)))
    for fr in sorted(set(owner.tolist())):
        ids = np.where(owner == fr)[0]
        for i_ in range(len(ids)):
            a_ = ids[i_]
            if alias[a_] != a_:
                continue
            near = ids[i_ + 1:][np.linalg.norm(out[ids[i_ + 1:]] - out[a_], axis=1) < eps]
            for b_ in near:
                if alias[b_] == b_:
                    alias[b_] = a_
    kept = []
    for f in faces:
        v = [alias[i] for i in f["v"]]
        if len(v) == 4 and len(set(v)) == 3:            # a quad with two corners merged: triangle
            seen = []
            v = [x for x in v if not (x in seen or seen.append(x))]
            v = [v[0], v[1], v[2]]
        if len(set(v)) < len(v):
            continue
        f["v"] = v
        kept.append(f)
    if len(kept) < len(faces):
        log(f"template: {len(faces) - len(kept)} polygons collapsed and left out")
    faces = kept
    # 4. texture charts: per row around its bone; the head's front (the face) planar
    Pf = out
    chart_ids, weight = {}, {}
    for f in faces:
        fr = f["row"]
        pts = Pf[f["v"]]
        a = to_fbx(J[fr])
        if fr == 19:
            top = to_fbx(ends_game[19])
            ax = top - a
            hl = np.linalg.norm(ax)
            ax /= hl
            fwd = np.array([0.0, 0, 1]) - ax * ax[2]          # FBX characters face +Z
            fwd /= np.linalg.norm(fwd)
            sd = np.cross(ax, fwd)
            cen = pts.mean(0) - a
            n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
            # by position, so the face chart's edge runs around the face, not through it
            face = cen @ fwd > 0.25 * hl and abs(cen @ sd) < 0.45 * hl and 0.15 < (cen @ ax) / hl < 0.8
            key = ("face",) if face else ("head",)
            if face:
                flat = [((p - a) @ sd, (p - a) @ ax) for p in pts]
            else:
                ang = [np.arctan2((p - a) @ sd, (p - a) @ fwd) for p in pts]
                if max(ang) - min(ang) > np.pi:
                    ang = [x + 2 * np.pi if x < 0 else x for x in ang]
                flat = [(x * 0.5 * hl, (p - a) @ ax) for x, p in zip(ang, pts)]
        else:
            end = J[CHILD[fr]] if fr in CHILD else ends_game.get(fr)
            if fr == 3:
                end = (J[5] + J[8]) / 2
            b = to_fbx(end) if end is not None else a + np.array([0, -1.0, 0])
            ax = b - a
            ax /= np.linalg.norm(ax)
            ref = np.array([0.0, 0, 1]) if abs(ax[2]) < 0.9 else np.array([1.0, 0, 0])
            r1 = ref - ax * (ref @ ax)
            r1 /= np.linalg.norm(r1)
            r2 = np.cross(ax, r1)
            ang = [np.arctan2((p - a) @ r2, (p - a) @ r1) for p in pts]
            if max(ang) - min(ang) > np.pi:
                ang = [x + 2 * np.pi if x < 0 else x for x in ang]
            rad = float(np.mean([np.linalg.norm((p - a) - ((p - a) @ ax) * ax) for p in pts])) + 1e-6
            # one chart per part, the seam at the back (angle +-pi): shared UVs, fewer bytes
            ang = [x + 2 * np.pi if x < -np.pi / 2 and max(ang) > np.pi / 2 else x for x in ang]
            key = (fr,)
            flat = [(x * rad, (p - a) @ ax) for x, p in zip(ang, pts)]
        if key not in chart_ids:
            chart_ids[key] = len(chart_ids)
            weight[chart_ids[key]] = 9.0 if key == ("face",) else (1.6 if key == ("head",) else 1.0)
        f["chart"] = chart_ids[key]
        f["flat"] = flat
        del f["row"]
    # smooth normals over the whole body (the seams are shared vertices)
    normals = np.zeros_like(Pf)
    for f in faces:
        v = f["v"]
        for t in [(v[0], v[1], v[2])] + ([(v[1], v[3], v[2])] if len(v) == 4 else []):
            n = np.cross(Pf[t[1]] - Pf[t[0]], Pf[t[2]] - Pf[t[0]])
            for i in t:
                normals[i] += n
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    log(f"template: {len(Pf)} vertices, {len(faces)} polygons from the donor")
    return {"positions": Pf, "owner": [int(x) for x in owner], "faces": faces, "normals": normals,
            "chart_weight": weight}
