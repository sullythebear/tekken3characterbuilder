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

# Parts are groups of rows. Row 20 (neck, shoulders, sometimes chest or the back of the head)
# belongs with the head: a head without it lost its back on other models (tested 2026-10-16).
PARTS = {"head": (19, 20), "body": (1, 2, 3, 4),
         "arm_l": (11, 12, 13, 14), "arm_r": (15, 16, 17, 18),
         "leg_l": (5, 6, 7), "leg_r": (8, 9, 10)}
SECOND = {2: 1, 4: 3, 20: 19}
CHILD = {5: 6, 6: 7, 8: 9, 9: 10, 11: 12, 12: 13, 13: 14, 15: 16, 16: 17, 17: 18}
BAND_WORDS = 128
# Parts only fit models of a similar build: within 7 % of the base's height (Julia, Law, Lei,
# Xiaoyu parts on Nina clean; Heihachi, 8 % taller, left gaps at the waist and the ankles).
FIT = 0.07


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

    def height(self) -> float:
        """Standing height (vertical extent of all own vertices)."""
        ys = [(self.W[SECOND.get(r, r)][0] @ np.array(sl[1], float) + self.W[SECOND.get(r, r)][1])[1]
              for r, slots in self.bind.items() for sl in slots if sl is not None and sl[0] == r]
        return float(max(ys) - min(ys))

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
    for name, mdl in parts.items():
        ratio = src[mdl].height() / B.height()
        if abs(ratio - 1) > FIT:
            raise MI.Budget(f"the {name} of model {mdl} does not fit: its fighter is {ratio * 100 - 100:+.0f} % "
                            f"of the base's height (at most {FIT * 100:.0f} %)")
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
        # 8-bit texels are renumbered per source CLUT (step 4), so those copies stay apart
        sk = (c["model"], 0x8000 | (c["mat"] & 0x7EFF) if c["mat"] & 0x8000 else 0, tuple(c["lo"]), tuple(c["hi"]))
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
            raise MI.Budget("the chosen parts' textures do not fit in one texture page: take parts from fewer different fighters")
        occ[spot[1]:spot[1] + h_, spot[0]:spot[0] + w_] = True
        c["dst"] = placed[sk] = spot
    band = np.zeros((256, 64), dtype=np.uint16)
    for c in clusters:
        sm = src[c["model"]]
        x0, y0 = c["lo"][0] // 4, c["lo"][1]
        x1, y1 = c["hi"][0] // 4, c["hi"][1]
        dx, dy = c["dst"][0] // 4, c["dst"][1]
        band[dy:dy + y1 - y0 + 1, dx:dx + x1 - x0 + 1] = sm.band[y0:y1 + 1, x0:x1 + 1]
    # 4. CLUTs, only where Tekken 3's own models keep theirs (tested 2026-10-16: every stock model
    # uses row 0 x 0..255, row 1 x 0..255, row 2 x 0..159 of its player's CLUT rows; CLUTs past
    # that overwrote the fight HUD's text palette). All 8-bit areas share the one 8-bit CLUT
    # (id 0): their texels are renumbered into one palette, the closest colours merged if more
    # than 255; 4-bit CLUTs (identical ones once) go to row 1 (ids 64..79) and row 2 (128..137).
    new_mat = {}
    eight_keys = sorted({(c["model"], c["mat"] & 0x7EFF) for c in clusters if c["mat"] & 0x8000})
    lut = {}
    if eight_keys:
        used, colours = {}, []
        for c in clusters:
            if not c["mat"] & 0x8000:
                continue
            x0, x1 = c["dst"][0] // 4, c["dst"][0] // 4 + (c["hi"][0] - c["lo"][0]) // 4
            y0, y1 = c["dst"][1], c["dst"][1] + c["hi"][1] - c["lo"][1]
            area = band[y0:y1 + 1, x0:x1 + 1]
            key = (c["model"], c["mat"] & 0x7EFF)
            used.setdefault(key, set()).update(np.unique(area & 255).tolist() + np.unique(area >> 8).tolist())
        entries = []                                   # (key, index, colour)
        for key in eight_keys:
            pal = list(src[key[0]].cluts.get(key[1], [0] * 256)) + [0] * 256
            for i in sorted(used.get(key, ())):
                if pal[i]:
                    entries.append((key, i, pal[i]))
        groups8 = {}                                   # colour -> merged group of entries
        for e in entries:
            groups8.setdefault(e[2], []).append(e)
        swatch = [[(c & 31), (c >> 5) & 31, (c >> 10) & 31, len(m), c & 0x8000] for c, m in groups8.items()]
        members = [list(m) for m in groups8.values()]
        while len(swatch) > 255:                         # Ward merges of the closest colours
            arr = np.array([[c[0], c[1], c[2]] for c in swatch], float)
            n = np.array([c[3] for c in swatch], float)
            d = ((arr[:, None, :] - arr[None, :, :]) ** 2).sum(2) * (n[:, None] * n[None, :]) / (n[:, None] + n[None, :])
            np.fill_diagonal(d, np.inf)
            i, j = np.unravel_index(np.argmin(d), d.shape)
            ni, nj = n[i], n[j]
            swatch[i] = [(swatch[i][k] * ni + swatch[j][k] * nj) / (ni + nj) for k in range(3)] + [ni + nj, swatch[i][4]]
            members[i] += members[j]
            del swatch[j], members[j]
        palette = [0] * 256
        for k, (c, m) in enumerate(zip(swatch, members), start=1):
            r, g, b_ = (int(round(v)) for v in c[:3])
            colour = c[4] | r | g << 5 | b_ << 10
            palette[k] = colour or 0x8000                # black, not see-through
            for key, i, _ in m:
                lut.setdefault(key, np.zeros(256, np.uint16))[i] = k
        if len(swatch) and len(entries) > len(swatch):
            log(f"8-bit areas: {len(entries)} colours merged into {len(swatch)}")
        for c in clusters:                             # renumber the copied 8-bit texels
            if not c["mat"] & 0x8000:
                continue
            key = (c["model"], c["mat"] & 0x7EFF)
            x0, x1 = c["dst"][0] // 4, c["dst"][0] // 4 + (c["hi"][0] - c["lo"][0]) // 4
            y0, y1 = c["dst"][1], c["dst"][1] + c["hi"][1] - c["lo"][1]
            area = band[y0:y1 + 1, x0:x1 + 1]
            table = lut.get(key, np.zeros(256, np.uint16))
            band[y0:y1 + 1, x0:x1 + 1] = table[area & 255] | (table[area >> 8] << 8)
        for (m_, mat) in groups:
            if mat & 0x8000:
                new_mat[(m_, mat)] = 0x8000
    slots4 = list(range(64, 80)) + list(range(128, 138))
    pal4, by_colours = {}, {}
    for (m_, mat) in sorted(groups):
        if mat & 0x8000:
            continue
        pal = (list(src[m_].cluts.get(mat & 0x7EFF, [0] * 16))[:16] + [0] * 16)[:16]
        key = tuple(pal)
        if key not in by_colours:
            if len(by_colours) >= len(slots4):
                need = len({tuple((list(src[m2].cluts.get(t & 0x7EFF, [0] * 16))[:16] + [0] * 16)[:16])
                            for (m2, t) in groups if not t & 0x8000})
                raise MI.Budget(f"the chosen parts need {need} small colour tables, a fighter has room for "
                                f"{len(slots4)}: take parts from fewer different fighters")
            by_colours[key] = slots4[len(by_colours)]
            pal4[by_colours[key]] = pal
        new_mat[(m_, mat)] = by_colours[key]
    runs = [(0, palette)] if eight_keys else []
    for first, last in ((64, 80), (128, 138)):
        ids = [i for i in sorted(pal4) if first <= i < last]
        if ids:
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
    ap.add_argument("--base", type=int)
    ap.add_argument("--part", action="append", default=[], help="name=model, names: " + ", ".join(PARTS))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--heights", nargs="*", type=int, help="print {model: standing height} as JSON")
    a = ap.parse_args()
    X.setup(a.root)
    if a.heights is not None:
        print(json.dumps({m: round(Source(a.root, m).height(), 1) for m in a.heights}))
        return
    if a.base is None or a.out is None:
        raise SystemExit("ERROR: --base and --out are needed to build")
    parts = {}
    for p in a.part:
        n, v = p.split("=")
        if n not in PARTS:
            raise SystemExit(f"unknown part {n}")
        parts[n] = int(v)
    import model_import as MI
    try:
        stock, new, tx, report = build(a.root, a.base, parts)
    except MI.Budget as error:
        raise SystemExit(f"ERROR: {error}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.base, stock, new, tx))
    rep = {k: v for k, v in report.items() if k not in ("rows", "texture")}
    print(json.dumps(rep, default=str))
    print(f"OK kitbash over model {a.base}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
