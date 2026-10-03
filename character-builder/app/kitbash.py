"""A fighter built from parts of Tekken 3's own models (Namco's geometry and texels, untouched).

Each body part (head, torso, pelvis, each arm, each leg) comes from any of the 48 fighter models;
the result sits on the base (donor) model's skeleton. Every part keeps its own polygons, its
flat/gouraud choice and its texels: the texels are copied halfword for halfword into one new
texture page, each part with its own CLUTs. Seams between parts of different models are closed
by snapping the borrowed joint-ring vertices onto the neighbouring part's nearest vertex.

CLI: kitbash.py --root GAME --base 10 --part head=14 --part torso=18 ... --out model.bin"""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path
import numpy as np

import model_export as X

PARTS = {"head": (19, 20), "torso": (1, 2), "pelvis": (3, 4),
         "arm_l": (11, 12, 13, 14), "arm_r": (15, 16, 17, 18),
         "leg_l": (5, 6, 7), "leg_r": (8, 9, 10)}
SECOND = {2: 1, 4: 3, 20: 19}
CHILD = {5: 6, 6: 7, 8: 9, 9: 10, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18}
BAND_WORDS = 128


class Source:
    """One stock model: geometry, bind, standing frames, texture band and CLUTs."""

    def __init__(self, root: Path, model: int):
        from tim_tool import scan_tims
        import model_import as MI
        rid = X.FIRST_MODEL_RECORD + 4 * model
        data = X.records(root, [rid, rid + 2])
        self.model = model
        self.m, arc = data[rid], data[rid + 2]
        self.bind = X.bind(self.m)
        self.W = MI.donor_frames(root, self.m)
        self.band = np.zeros((256, BAND_WORDS), dtype=np.uint16)
        self.cluts = {}
        for t in scan_tims(arc):
            img = t.image
            if t.mode == 0 and (img.x, img.y, img.width_words, img.height) == (0, 0, 8, 32):
                continue
            if t.clut is not None:
                c = t.clut
                cols = np.frombuffer(arc[c.offset + 12: c.offset + 12 + c.width_words * 2], dtype="<u2")
                self.cluts[(c.y << 6) | (c.x >> 4)] = [int(x) for x in cols]
            width = min(img.width_words, BAND_WORDS - img.x)
            if width <= 0 or img.y >= 256:
                continue
            raw = arc[img.offset + 12: img.offset + 12 + img.width_words * img.height * 2]
            px = np.frombuffer(raw, dtype="<u2").reshape(img.height, img.width_words)
            rows = min(img.height, 256 - img.y)
            self.band[img.y: img.y + rows, img.x: img.x + width] = px[:rows, :width]

    def bone(self, r):
        """Length of the bone from row r to its child (the child's offset)."""
        from fmt import row
        c = CHILD.get(r)
        return float(np.linalg.norm(row(self.m, c)[3:6])) if c else None


def build(root: Path, base: int, parts: dict, log=print):
    """parts: {part name: model}; missing parts come from the base. -> (stock base model bytes,
    new model bytes, texture dict for own_model_file, report)."""
    import anim_model as A
    from fmt import row, block, parse_b, parse_c_ps1
    import model_import as MI
    src = {base: Source(root, base)}
    for mdl in set(parts.values()):
        if mdl not in src:
            src[mdl] = Source(root, mdl)
    B = src[base]
    row_model = {}
    for name, rows in PARTS.items():
        for r in rows:
            row_model[r] = parts.get(name, base)
    frame_of = lambda r: SECOND.get(r, r)

    def place(sm, r, local):
        """A local point of row r of source sm, in the base's standing world."""
        fr = frame_of(r)
        loc = np.array(local, float)
        kb, ks = B.bone(fr), sm.bone(fr)
        if kb and ks:                          # stretch along the bone to the base's length
            loc = loc * [kb / ks, 1, 1]
        R, T = B.W[fr]
        return R @ loc + T

    # 1. own vertices of every row, from that row's model
    key, pos, owner = {}, [], []
    for r in range(1, 21):
        sm = src[row_model[r]]
        for sl in sm.bind.get(r, []):
            if sl is None or sl[0] != r:
                continue
            k = (sm.model, r, sl[1])
            if k not in key:
                key[k] = len(pos)
                pos.append(place(sm, r, sl[1]))
                owner.append(frame_of(r))
    pos = np.array(pos)
    owner = np.array(owner)

    def vid(sm, r_slot):
        """Vertex id of a slot (owner row, local) used by a row of model sm."""
        o, loc = r_slot
        k = (sm.model, o, loc)
        if k in key and row_model[o] == sm.model:
            return key[k]
        # borrowed from a row that now comes from another model: snap onto that row's
        # nearest vertex (closes the seam at neck, shoulder, hip, elbow...)
        p = place(sm, o, loc)
        cand = np.where(owner == frame_of(o))[0]
        if not len(cand):
            return None
        return int(cand[np.argmin(np.linalg.norm(pos[cand] - p, axis=1))])

    # 2. polygons with their own UVs and CLUTs
    faces = []
    for r in range(1, 21):
        sm = src[row_model[r]]
        w = row(sm.m, r)
        if w[1] <= 2 or r not in sm.bind:
            continue
        slots = sm.bind[r]
        prims = parse_c_ps1(block(sm.m, w[2]))
        pi = -1
        for k, fam in enumerate(parse_b(block(sm.m, w[1]))):
            for rec in fam:
                pi += 1
                c = A.prim_verts(k, rec)
                if any(i >= len(slots) or slots[i] is None for i in c):
                    continue
                _, mat, puv = prims[pi]
                if mat is None or None in puv:
                    continue
                ids = [vid(sm, slots[i]) for i in c]
                if None in ids or len(set(ids)) < len(ids):
                    continue
                v = [ids[0], ids[2], ids[1]] + ([ids[3]] if len(ids) == 4 else [])
                uv = [puv[0], puv[2], puv[1]] + ([puv[3]] if len(ids) == 4 else [])
                faces.append({"v": v, "hard": k < 2, "model": sm.model, "smat": mat, "suv": uv})

    # 3. texels: each (model, CLUT) cluster of polygons copied as whole halfwords into one page
    def cols(f):
        """Source texel coordinates in 4-bit columns of the model's band (page 2 = +256)."""
        eight = f["smat"] & 0x8000
        page = 256 if f["smat"] & 0x100 else 0
        return np.array([((u * 2 if eight else u) + page, v) for u, v in f["suv"]], float)
    groups = {}
    for i, f in enumerate(faces):
        groups.setdefault((f["model"], f["smat"]), []).append(i)
    clusters = []
    for (mdl, mat), ids in groups.items():
        boxes = {}
        for i in ids:
            c = cols(faces[i])
            lo = np.floor(c.min(0)).astype(int)
            hi = np.ceil(c.max(0)).astype(int) + (2 if mat & 0x8000 else 1)
            boxes[i] = (lo, hi)
        par = {i: i for i in ids}

        def fnd(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for a in ids:
            for b in ids:
                if a < b and (boxes[a][0] <= boxes[b][1] + 1).all() and (boxes[b][0] <= boxes[a][1] + 1).all():
                    par[fnd(a)] = fnd(b)
        cl = {}
        for i in ids:
            cl.setdefault(fnd(i), []).append(i)
        for members in cl.values():
            lo = np.min([boxes[i][0] for i in members], 0)
            hi = np.max([boxes[i][1] for i in members], 0)
            lo[0] -= lo[0] % 4                      # whole halfwords
            hi[0] += (-hi[0] - 1) % 4
            lo = np.maximum(lo, 0)
            hi = np.minimum(hi, [BAND_WORDS * 4 - 1, 255])
            clusters.append({"model": mdl, "mat": mat, "faces": members, "lo": lo, "hi": hi})
    # same texels used by two clusters (shared tiles) are copied once: identical source boxes merge
    occ = np.zeros((256, 256), bool)
    placed = {}
    clusters.sort(key=lambda c: -(c["hi"][1] - c["lo"][1] + 1) * (c["hi"][0] - c["lo"][0] + 1))
    for c in clusters:
        sk = (c["model"], c["mat"] & 0x8000, tuple(c["lo"]), tuple(c["hi"]))
        if sk in placed:
            c["dst"] = placed[sk]
            continue
        w_, h_ = c["hi"] - c["lo"] + 1
        spot = None
        for y in range(0, 256 - h_ + 1):
            for x in range(0, 256 - w_ + 1, 4):
                if not occ[y:y + h_, x:x + w_].any():
                    spot = (x, y)
                    break
            if spot:
                break
        if spot is None:
            raise MI.Budget("the parts' texels do not fit in one texture page")
        occ[spot[1]:spot[1] + h_, spot[0]:spot[0] + w_] = True
        c["dst"] = placed[sk] = spot
    band = np.zeros((256, 64), dtype=np.uint16)
    for c in clusters:
        sm = src[c["model"]]
        x0, y0 = c["lo"][0] // 4, c["lo"][1]
        x1, y1 = c["hi"][0] // 4, c["hi"][1]
        dx, dy = c["dst"][0] // 4, c["dst"][1]
        band[dy:dy + y1 - y0 + 1, dx:dx + x1 - x0 + 1] = sm.band[y0:y1 + 1, x0:x1 + 1]
    # 4. CLUTs: an 8-bit CLUT per model (the first at id 0), 4-bit CLUTs from id 64 on
    new_mat, runs8, pal4 = {}, [], {}
    next4 = 64
    eight_models = sorted({m_ for (m_, mat) in groups if mat & 0x8000})
    if len(eight_models) > 1:
        log(f"8-bit areas of {len(eight_models)} models: the extra ones get CLUTs at ids 16, 32")
    for j, mdl in enumerate(eight_models):
        cid = 16 * j
        for (m_, mat) in groups:
            if m_ == mdl and mat & 0x8000:
                new_mat[(m_, mat)] = 0x8000 | cid
                pal = src[m_].cluts.get(mat & 0x7eff, [0] * 256)
                runs8.append((cid, list(pal[:256]) + [0] * (256 - len(pal[:256]))))
                break
        for (m_, mat) in groups:                 # all of this model's 8-bit materials share it
            if m_ == mdl and mat & 0x8000:
                new_mat[(m_, mat)] = 0x8000 | cid
    for (m_, mat) in sorted(groups):
        if mat & 0x8000:
            continue
        new_mat[(m_, mat)] = next4
        pal4[next4] = list(src[m_].cluts.get(mat & 0x7eff, [0] * 16))[:16]
        pal4[next4] += [0] * (16 - len(pal4[next4]))
        next4 += 1
    if next4 > 128:
        raise MI.Budget("more than 64 four-bit CLUTs")
    runs = list(runs8)
    if pal4:
        ids = sorted(pal4)
        runs.append((ids[0], [c for i in ids for c in pal4[i]]))
    # 5. per-face texture data for the writer: corners in 4-bit columns of the new page
    mats = sorted(set(new_mat.values()))
    chart_of = {m_: i for i, m_ in enumerate(mats)}
    face_uv = [None] * len(faces)
    for c in clusters:
        off = np.array(c["dst"]) - c["lo"]
        for i in c["faces"]:
            face_uv[i] = [(int(u), int(v)) for u, v in (cols(faces[i]) + off)]
    for i, f in enumerate(faces):
        f["chart"] = chart_of[new_mat[(f["model"], f["smat"])]]
    texture = {"uv": face_uv, "band": band, "runs": runs, "mats": {chart_of[m_]: m_ for m_ in mats},
               "palette": [c for _, p in runs for c in p], "charts": len(mats), "density": 0.0,
               "rgb": np.zeros((256, 256, 3), np.uint8)}
    # 6. normals: per vertex, area-weighted
    Nrm = np.zeros_like(pos)
    for f in faces:
        v = f["v"]
        for t in [(v[0], v[1], v[2])] + ([(v[1], v[3], v[2])] if len(v) == 4 else []):
            n = np.cross(pos[t[1]] - pos[t[0]], pos[t[2]] - pos[t[0]])
            Nrm[list(t)] += n
    Nrm /= np.linalg.norm(Nrm, axis=1, keepdims=True) + 1e-12
    F = {r: B.W[r][0] for r in B.W}
    J = {r: B.W[r][1] for r in B.W}
    data, report = MI._write(B.m, pos, Nrm, faces, [int(o) for o in owner], {}, F, J, row, {"ready": texture})
    report.update(bytes=len(data), budget=len(B.m), parts=parts)
    if len(data) > len(B.m):
        raise MI.Budget(f"{len(data)} bytes, the base model's slot holds {len(B.m)}")
    return B.m, data, texture, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--base", type=int, required=True)
    ap.add_argument("--part", action="append", default=[], help="name=model, names: " + ", ".join(PARTS))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    X.setup(a.root)
    parts = {}
    for p in a.part:
        n, v = p.split("=")
        if n not in PARTS:
            raise SystemExit(f"unknown part {n}")
        parts[n] = int(v)
    stock, new, tx, report = build(a.root, a.base, parts)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.base, stock, new, tx))
    rep = {k: v for k, v in report.items() if k not in ("rows", "texture")}
    print(json.dumps(rep, default=str))
    print(f"OK kitbash over model {a.base}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
