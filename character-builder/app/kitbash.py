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
         "leg_l": (5, 6, 7), "leg_r": (8, 9, 10),
         # a finer part, put over the arms: both hands (gloves). Feet are not one: models split
         # leg and foot differently (Nina's shin row runs into her boot), so other fighters' feet
         # floated under it (tested 2026-10-16)
         "hands": (14, 18)}
FINE = ("hands",)
# body shape: {name: factor}. The head grows on all axes (rows 19/20 scaled 1.5x and 2.5x drew
# fine in game, own-models.md); arms, legs and body only across the bone (local Y and Z: every
# bone runs along local +X), so joints stay where the animations put them. Hands and feet keep
# their size.
SHAPES = {"head": ((19,), (1, 1, 1), (0.85, 1.3)),
          "arms": ((11, 12, 13, 15, 16, 17), (0, 1, 1), (0.8, 1.3)),
          "legs": ((5, 6, 8, 9), (0, 1, 1), (0.8, 1.3)),
          "body": ((1, 3), (0, 1, 1), (0.85, 1.25))}


def clean_shape(shape) -> dict:
    """{name: factor} within each shape's range; factors of 1 are left out."""
    out = {}
    for name, value in (shape or {}).items() if isinstance(shape, dict) else ():
        if name in SHAPES:
            lo, hi = SHAPES[name][2]
            f = round(min(hi, max(lo, float(value))), 2)
            if f != 1:
                out[name] = f
    return out


def shape_scale(shape: dict) -> dict:
    """{frame row: per-axis scale} for a clean shape."""
    out = {}
    for name, f in shape.items():
        rows, axes, _ = SHAPES[name]
        for r in rows:
            out[r] = np.array([f if a else 1.0 for a in axes])
    return out
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


def recolour(colour: int, hue: float, sat: float, light: float, keep_skin: bool = True) -> int:
    """A PS1 colour shifted in HSL (hue in degrees, saturation in %, lightness in % points), as the
    builder's "Whole costume" tint; skin tones kept (warm, light or pale; tested on Nina, Julia)."""
    import colorsys
    if not colour or colour == 0x8000:
        return colour
    r, g, b = (((colour >> k) & 31) / 31 for k in (0, 5, 10))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    # skin: red strongest, orange to pink, not grey (light skin reads as highly saturated in HLS:
    # Nina's 30,22,16 is s 0.88)
    if keep_skin and r >= max(g, b) and (h <= 0.14 or h >= 0.92) and s >= 0.05 and 0.15 <= l <= 0.95:
        return colour
    h = (h + hue / 360) % 1
    s = min(1.0, max(0.0, s * sat / 100))
    l = min(1.0, max(0.0, l + light / 100))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    out = (colour & 0x8000) | round(r * 31) | round(g * 31) << 5 | round(b * 31) << 10
    return out if out & 0x7FFF else 0x8000 | (colour & 0x8000)   # black, not see-through


def build(root: Path, base: int, parts: dict, log=print, tint: tuple | None = None, shape: dict | None = None,
          pieces: dict | None = None):
    """parts: {part name: model}; missing parts come from the base. shape: body shape factors
    (SHAPES). -> (stock base model bytes, new model bytes, texture dict for own_model_file, report).
    Accessories (rows 21-26: Nina's ponytail, Julia's braid) come with the part they hang on; a
    mix that does not fit with them is built again without them. pieces: {"model:clut": [hue,
    saturation, lightness]}, one piece of clothing recoloured (list_pieces names them)."""
    import model_import as MI
    try:
        return _build(root, base, parts, log, tint, shape, accessories=True, pieces=pieces)
    except MI.Budget as error:
        if "its fighter is" in str(error):            # the height gate: accessories change nothing
            raise
        log(f"{error}: built again without the accessories (ponytails, braids)")
        return _build(root, base, parts, log, tint, shape, accessories=False, pieces=pieces)


def _accessories(sm, roots) -> list:
    """[(row, main row it hangs on)] of model sm's drawn accessory rows (21-26) whose chain ends on
    one of roots (rows 21-24: word 6 is the part they hang on, 25/26 a second layer of it)."""
    import anim_model as A
    from fmt import row, nrows
    out = []
    for r in range(21, min(27, nrows(sm.m))):
        w = row(sm.m, r)
        if not (w[10] and w[1] > 2) or r not in sm.bind:
            continue
        top, seen = r, 0
        while top > 20 and seen < 8:
            part = row(sm.m, top)[6] & 0xFF
            if part >= len(A.P2R):
                top = None
                break
            top, seen = A.P2R[part], seen + 1
        if top in roots:
            out.append((r, top))
    return out


def _row_models(base: int, parts: dict) -> dict:
    """{row: model} of a mix: each part's rows from its model, the rest from the base."""
    out = {}
    for name, rows in PARTS.items():
        if name in FINE and name not in parts:
            continue                           # a finer part only when chosen
        for r in rows:
            out[r] = parts.get(name, base)
    return out


PART_OF_ROW = {r: name for name, rows in PARTS.items() if name not in FINE for r in rows}
MIN_PIECE = 4                          # fewer polygons than this: a detail, not offered as a piece
SAME_PIECE = 40                        # RGB distance under which two tables of a part are one piece


def list_pieces(root: Path, base: int, parts: dict) -> list[dict]:
    """The pieces of clothing of a mix: one per colour table of a source model, with the body part
    that uses it most, how many polygons and its average colour (#rrggbb)."""
    from fmt import row, block, parse_c_ps1
    src = {m: Source(root, m) for m in {base, *parts.values()}}
    row_model = _row_models(base, parts)
    use = {}
    rows = [(r, row_model[r], r) for r in range(1, 21)]
    for mdl in set(row_model.values()):
        mine = {r for r, m_ in row_model.items() if m_ == mdl}
        rows += [(r, mdl, top) for r, top in _accessories(src[mdl], mine)]
    for r, mdl, top in rows:
        sm = src[mdl]
        w = row(sm.m, r)
        if w[1] <= 2 or w[2] <= 2:
            continue
        for _, mat, _ in parse_c_ps1(block(sm.m, w[2])):
            if mat is None or mat & 0x8000:            # 8-bit areas: skin and faces, kept as they are
                continue
            key = (mdl, mat & 0x7EFF)
            main = SECOND.get(top, top)
            fine = next((n for n in FINE if n in parts and main in PARTS[n]), None)   # chosen gloves: "hands"
            part = fine or PART_OF_ROW.get(main, "body")
            use.setdefault(key, {})
            use[key][part] = use[key].get(part, 0) + 1
    out = []
    for (mdl, clut), by_part in use.items():
        cols = [c for c in src[mdl].cluts.get(clut, []) if c & 0x7FFF]
        if not cols or sum(by_part.values()) < MIN_PIECE:
            continue
        rgb = [round(sum((c >> k) & 31 for c in cols) / len(cols) * 255 / 31) for k in (0, 5, 10)]
        out.append({"key": f"{mdl}:{clut}", "model": mdl, "part": max(by_part, key=by_part.get),
                    "polygons": sum(by_part.values()), "colour": "#%02x%02x%02x" % tuple(rgb)})
    order = list(PARTS)
    out.sort(key=lambda p: (order.index(p["part"]) if p["part"] in order else 99, -p["polygons"]))
    # tables of one fighter with nearly the same colour are one piece for the player (the shades
    # of one jacket, the same trim on arms and legs): keys lists them all, the biggest first
    rgb = lambda h: [int(h[k:k + 2], 16) for k in (1, 3, 5)]
    merged = []
    for p in out:
        home = next((q for q in merged if q["model"] == p["model"]
                     and sum((a_ - b_) ** 2 for a_, b_ in zip(rgb(q["colour"]), rgb(p["colour"]))) < SAME_PIECE ** 2), None)
        if home:
            home["keys"].append(p["key"])
            home["polygons"] += p["polygons"]
        else:
            merged.append({**p, "keys": [p["key"]]})
    return merged


def _build(root: Path, base: int, parts: dict, log=print, tint=None, shape=None, accessories=True, pieces=None):
    scale = shape_scale(clean_shape(shape))
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
    for key, (h, s_, l) in (pieces or {}).items():      # one piece of clothing in its own colours
        mdl, clut = (int(x) for x in key.split(":"))
        if mdl in src and clut in src[mdl].cluts:
            src[mdl].cluts[clut] = [recolour(c, h, s_, l, keep_skin=False) for c in src[mdl].cluts[clut]]
    row_model = _row_models(base, parts)
    frame_of = lambda r: SECOND.get(r, r)
    acc = []                                   # (model, accessory row, main row it hangs on)
    if accessories:
        for mdl in set(row_model.values()):
            mine = {r for r, m_ in row_model.items() if m_ == mdl}
            acc += [(mdl, r, top) for r, top in _accessories(src[mdl], mine)]

    def place(sm, r, local):
        """A local point of row r of source sm, in the base's standing world."""
        fr = frame_of(r)
        loc = np.array(local, float)
        kb, ks = B.bone(fr), sm.bone(fr)
        if kb and ks:                          # stretch along the bone to the base's length
            loc = loc * [kb / ks, 1, 1]
        if fr in scale:
            loc = loc * scale[fr]
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
    for mdl, r, top in acc:                    # rigid on the main row they hang on
        sm = src[mdl]
        Rs, Ts = sm.W[r]
        Rr, Tr = sm.W[frame_of(top)]
        for sl in sm.bind.get(r, []):
            if sl is None or sl[0] != r:
                continue
            k = (mdl, r, sl[1])
            if k not in key:
                local = Rr.T @ (Rs @ np.array(sl[1], float) + Ts - Tr)
                key[k] = len(pos)
                pos.append(place(sm, top, local))
                owner.append(frame_of(top))
    pos = np.array(pos)
    owner = np.array(owner)

    def vid(sm, r_slot):
        """Vertex id of a slot (owner row, local) used by a row of model sm."""
        o, loc = r_slot
        k = (sm.model, o, loc)
        if k in key and (o > 20 or row_model.get(o) == sm.model):
            return key[k]
        if o > 20:
            return None
        # borrowed from a row that now comes from another model: snap onto that row's
        # nearest vertex (closes the seam at neck, shoulder, hip, elbow...)
        p = place(sm, o, loc)
        cand = np.where(owner == frame_of(o))[0]
        if not len(cand):
            return None
        return int(cand[np.argmin(np.linalg.norm(pos[cand] - p, axis=1))])

    # 2. polygons with their own UVs and CLUTs
    faces = []
    for r, sm in [(r, src[row_model[r]]) for r in range(1, 21)] + [(r, src[mdl]) for mdl, r, _ in acc]:
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
    # 4-bit CLUTs beyond a fighter's room (26, step 4): the smallest 4-bit areas become 8-bit
    # ("wide": one 8-bit texel per 4-bit texel, twice as wide in the page) and take their colours
    # from the shared 8-bit CLUT, until the rest fits
    ROOM4 = 26
    area_of = {}
    for c in clusters:
        if not c["mat"] & 0x8000:
            key = (c["model"], c["mat"] & 0x7EFF)
            area_of[key] = area_of.get(key, 0) + int(np.prod(c["hi"] - c["lo"] + 1))
    pals4 = {}
    for key in area_of:
        pals4.setdefault(tuple((list(src[key[0]].cluts.get(key[1], [0] * 16))[:16] + [0] * 16)[:16]), []).append(key)
    wide_keys = set()
    if len(pals4) > ROOM4:
        order = sorted(pals4.values(), key=lambda keys: sum(area_of[k] for k in keys))
        for keys in order[:len(pals4) - ROOM4]:
            wide_keys.update(keys)
        log(f"4-bit areas: {len(order) - ROOM4} colour tables over the room become 8-bit")
    for c in clusters:
        c["wide"] = not c["mat"] & 0x8000 and (c["model"], c["mat"] & 0x7EFF) in wide_keys
    # placing the areas in the one page: first the model with the most texels keeps its own
    # layout (its areas may overlap where they are the same texels: same model, same 8-bit CLUT
    # or 4-bit) and the rest goes into the free space; if that fails, every area is packed anew,
    # biggest first. Identical source boxes are copied once.
    def main8(model):
        area8 = {}
        for c in clusters:
            if c["model"] == model and c["mat"] & 0x8000:
                area8[c["mat"] & 0x7EFF] = area8.get(c["mat"] & 0x7EFF, 0) + int(np.prod(c["hi"] - c["lo"] + 1))
        return (model, max(area8, key=area8.get)) if area8 else None
    keeper = keeper8 = None
    kept = False

    def size(c):
        w_, h_ = c["hi"] - c["lo"] + 1
        return (2 * w_ if c["wide"] else w_), h_

    def pack(keep):
        occ = np.zeros((256, 256), np.int32)          # 0 free, else the owner's tag
        placed, spots = {}, {}
        order = sorted(range(len(clusters)), key=lambda i: (
            not (keep and clusters[i]["model"] == keeper and not clusters[i]["wide"]),
            -size(clusters[i])[0] * size(clusters[i])[1]))
        for i in order:
            c = clusters[i]
            sk = (c["model"], 0x8000 | (c["mat"] & 0x7EFF) if c["mat"] & 0x8000 or c["wide"] else 0,
                  tuple(c["lo"]), tuple(c["hi"]))
            if sk in placed:
                spots[i] = placed[sk]
                continue
            w_, h_ = size(c)
            spot = None
            if keep and c["model"] == keeper and not c["wide"]:
                tag = 1 if not c["mat"] & 0x8000 or (keeper, c["mat"] & 0x7EFF) == keeper8 else 2 + (c["mat"] & 0x7EFF)
                x_, y_ = int(c["lo"][0]), int(c["lo"][1])
                if x_ + w_ <= 256 and y_ + h_ <= 256:
                    region = occ[y_:y_ + h_, x_:x_ + w_]
                    if ((region == 0) | (region == tag)).all():
                        spot = (x_, y_)
                        region[:] = tag
                if spot is None:
                    log(f"keeping the layout failed at model {c['model']} mat {c['mat']:#06x} box {tuple(c['lo'])}-{tuple(c['hi'])}")
                    return None
            else:
                for y in range(0, 256 - h_ + 1):
                    for x in range(0, 256 - w_ + 1, 4):
                        if not occ[y:y + h_, x:x + w_].any():
                            spot = (x, y)
                            break
                    if spot:
                        break
                if spot is None:
                    log(f"no free space for model {c['model']} mat {c['mat']:#06x} size {w_}x{h_} ({'kept' if keep else 'packed'})")
                    return None
                occ[spot[1]:spot[1] + h_, spot[0]:spot[0] + w_] = -1
            spots[i] = placed[sk] = spot
        return spots

    def fit_page(texels):
        """Each model in turn keeps its own layout, else every area is packed anew (None: no fit)."""
        nonlocal keeper, keeper8, kept
        for keeper in sorted(texels, key=texels.get, reverse=True):
            keeper8 = main8(keeper)
            spots = pack(True)
            if spots is not None:
                kept = True
                return spots
        kept = False
        keeper = keeper8 = None
        return pack(False)

    def halve(model):
        """The model's areas at half size (every second texel each way) from a band of their own,
        its polygons' UVs to match: a mix whose textures do not fit one page still builds, a
        little less sharp."""
        import copy
        for c in clusters:
            if c["model"] != model:
                continue
            sm = src[model]
            eight = bool(c["mat"] & 0x8000)
            bits = 8 if eight else 4
            per = 16 // bits
            x0, y0, x1, y1 = c["lo"][0] // 4, c["lo"][1], c["hi"][0] // 4, c["hi"][1]
            words = sm.band[y0:y1 + 1, x0:x1 + 1].astype(np.uint32)
            tex = np.stack([(words >> (bits * k)) & ((1 << bits) - 1) for k in range(per)], 2).reshape(words.shape[0], -1)
            sub = tex[::2, ::2]
            if sub.shape[1] % per:
                sub = np.pad(sub, ((0, 0), (0, per - sub.shape[1] % per)))
            sub = sub.reshape(sub.shape[0], -1, per)
            packed = np.zeros(sub.shape[:2], np.uint16)
            for k in range(per):
                packed |= (sub[:, :, k].astype(np.uint16) << (bits * k))
            nid = max(src) + 1
            syn = copy.copy(sm)                       # the same CLUTs, a band of its own
            syn.band = np.zeros_like(sm.band)
            syn.model = nid
            syn.band[y0:y0 + packed.shape[0], x0:x0 + packed.shape[1]] = packed
            src[nid] = syn
            lo = c["lo"]
            for i in c["faces"]:
                f = faces[i]
                page = 256 if f["smat"] & 0x100 else 0
                uv = []
                for u, v in f["suv"]:
                    cu = (u * 2 if eight else u) + page
                    cu = lo[0] + (cu - lo[0]) / 2
                    uv.append(((cu - page) / (2 if eight else 1), lo[1] + (v - lo[1]) / 2))
                f["suv"], f["model"] = uv, nid
            if (model, c["mat"] & 0x7EFF) in wide_keys:
                wide_keys.add((nid, c["mat"] & 0x7EFF))
            c["model"] = nid
            c["hi"] = np.array([lo[0] + 4 * packed.shape[1] - 1, y0 + packed.shape[0] - 1])
        groups.clear()
        for i, f in enumerate(faces):
            groups.setdefault((f["model"], f["smat"]), []).append(i)

    halved, synthetic = [], set()
    while True:
        texels = {}
        for c in clusters:
            texels[c["model"]] = texels.get(c["model"], 0) + int(np.prod(c["hi"] - c["lo"] + 1))
        spots = fit_page(texels)
        if spots is not None:
            break
        # the biggest other fighter's areas first, the base's last
        todo = sorted((m for m in texels if m not in synthetic), key=lambda m: (m == base, -texels[m]))
        if not todo:
            raise MI.Budget("the chosen parts' textures do not fit in one texture page: take parts from fewer different fighters")
        before = set(src)
        halve(todo[0])
        synthetic |= set(src) - before
        halved.append(todo[0])
        log(f"texture page: model {todo[0]}'s areas at half size, to fit")
    if halved:
        log(f"textures at half size: models {', '.join(map(str, halved))}")

    for i, c in enumerate(clusters):
        c["dst"] = spots[i]
    band = np.zeros((256, 64), dtype=np.uint16)
    for c in clusters:
        if c["wide"]:
            continue
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
    eight_keys = sorted({(c["model"], c["mat"] & 0x7EFF) for c in clusters if c["mat"] & 0x8000 or c["wide"]})
    lut = {}
    if eight_keys:
        used = {}
        for c in clusters:
            if not c["mat"] & 0x8000:
                continue
            x0, x1 = c["dst"][0] // 4, c["dst"][0] // 4 + (c["hi"][0] - c["lo"][0]) // 4
            y0, y1 = c["dst"][1], c["dst"][1] + c["hi"][1] - c["lo"][1]
            area = band[y0:y1 + 1, x0:x1 + 1]
            key = (c["model"], c["mat"] & 0x7EFF)
            used.setdefault(key, set()).update(np.unique(area & 255).tolist() + np.unique(area >> 8).tolist())
        for c in clusters:                             # wide areas: the 4-bit indices of their source
            if not c["wide"]:
                continue
            x0, y0, x1, y1 = c["lo"][0] // 4, c["lo"][1], c["hi"][0] // 4, c["hi"][1]
            area = src[c["model"]].band[y0:y1 + 1, x0:x1 + 1]
            key = (c["model"], c["mat"] & 0x7EFF)
            for k in range(4):
                used.setdefault(key, set()).update(np.unique((area >> (4 * k)) & 15).tolist())
        entries = []                                   # (key, index, colour)
        ident = keeper8 if kept and keeper8 in eight_keys else None
        for key in eight_keys:
            if key == ident:
                continue
            pal = list(src[key[0]].cluts.get(key[1], [0] * 256)) + [0] * 256
            for i in sorted(used.get(key, ())):
                if pal[i]:
                    entries.append((key, i, pal[i]))
        palette = [0] * 256
        if ident:
            # the kept model's 8-bit CLUT stays as it is (its texels too: its page layout is kept);
            # the others' colours take the indices it does not use, else the closest colour
            own = (list(src[ident[0]].cluts.get(ident[1], [0] * 256)) + [0] * 256)[:256]
            palette = list(own)
            lut[ident] = np.arange(256, dtype=np.uint16)
            taken = set(used.get(ident, set())) | {0}
            free = [i for i in range(1, 256) if i not in taken]
            where = {own[i]: i for i in sorted(taken) if own[i]}
            rgb = lambda c: np.array([c & 31, (c >> 5) & 31, (c >> 10) & 31], float)
            merged = 0
            for key, i, colour in entries:
                if colour not in where:
                    if free:
                        k = free.pop(0)
                        palette[k] = colour
                        where[colour] = k
                    else:
                        cands = [k for k in where.values()]
                        k = min(cands, key=lambda k: float(((rgb(palette[k]) - rgb(colour)) ** 2).sum()))
                        where[colour] = k
                        merged += 1
                lut.setdefault(key, np.zeros(256, np.uint16))[i] = where[colour]
            if merged:
                log(f"8-bit areas: {merged} colours of the other fighters merged into the kept palette")
        else:
            groups8 = {}                               # colour -> merged group of entries
            for e in entries:
                groups8.setdefault(e[2], []).append(e)
            swatch = [[(c & 31), (c >> 5) & 31, (c >> 10) & 31, len(m), c & 0x8000] for c, m in groups8.items()]
            members = [list(m) for m in groups8.values()]
            while len(swatch) > 255:                   # Ward merges of the closest colours
                arr = np.array([[c[0], c[1], c[2]] for c in swatch], float)
                n = np.array([c[3] for c in swatch], float)
                d = ((arr[:, None, :] - arr[None, :, :]) ** 2).sum(2) * (n[:, None] * n[None, :]) / (n[:, None] + n[None, :])
                np.fill_diagonal(d, np.inf)
                i, j = np.unravel_index(np.argmin(d), d.shape)
                ni, nj = n[i], n[j]
                swatch[i] = [(swatch[i][k] * ni + swatch[j][k] * nj) / (ni + nj) for k in range(3)] + [ni + nj, swatch[i][4]]
                members[i] += members[j]
                del swatch[j], members[j]
            for k, (c, m) in enumerate(zip(swatch, members), start=1):
                r, g, b_ = (int(round(v)) for v in c[:3])
                colour = c[4] | r | g << 5 | b_ << 10
                palette[k] = colour or 0x8000            # black, not see-through
                for key, i, _ in m:
                    lut.setdefault(key, np.zeros(256, np.uint16))[i] = k
            if len(swatch) and len(entries) > len(swatch):
                log(f"8-bit areas: {len(entries)} colours merged into {len(swatch)}")
        for c in clusters:                             # wide areas: 4-bit source -> 8-bit texels
            if not c["wide"]:
                continue
            x0, y0, x1, y1 = c["lo"][0] // 4, c["lo"][1], c["hi"][0] // 4, c["hi"][1]
            area = src[c["model"]].band[y0:y1 + 1, x0:x1 + 1]
            table = lut.get((c["model"], c["mat"] & 0x7EFF), np.zeros(256, np.uint16))
            nib = np.stack([(area >> (4 * k)) & 15 for k in range(4)], 2).reshape(area.shape[0], -1)
            idx = table[nib]
            words = idx[:, 0::2] | (idx[:, 1::2] << 8)
            dx, dy = c["dst"][0] // 4, c["dst"][1]
            band[dy:dy + words.shape[0], dx:dx + words.shape[1]] = words
        for c in clusters:                             # renumber the copied 8-bit texels
            if not c["mat"] & 0x8000 or (c["model"], c["mat"] & 0x7EFF) == ident:
                continue
            key = (c["model"], c["mat"] & 0x7EFF)
            x0, x1 = c["dst"][0] // 4, c["dst"][0] // 4 + (c["hi"][0] - c["lo"][0]) // 4
            y0, y1 = c["dst"][1], c["dst"][1] + c["hi"][1] - c["lo"][1]
            area = band[y0:y1 + 1, x0:x1 + 1]
            table = lut.get(key, np.zeros(256, np.uint16))
            band[y0:y1 + 1, x0:x1 + 1] = table[area & 255] | (table[area >> 8] << 8)
        for (m_, mat) in groups:
            if mat & 0x8000 or (m_, mat & 0x7EFF) in wide_keys:
                new_mat[(m_, mat)] = 0x8000
    slots4 = list(range(64, 80)) + list(range(128, 138))
    # 4-bit CLUTs share a slot when they agree on every index their texels use (lossless: the
    # texels stay as they are); the indices used come from the copied areas
    used4 = {}
    for c in clusters:
        if c["mat"] & 0x8000 or c["wide"]:
            continue
        x0, x1 = c["dst"][0] // 4, c["dst"][0] // 4 + (c["hi"][0] - c["lo"][0]) // 4
        y0, y1 = c["dst"][1], c["dst"][1] + c["hi"][1] - c["lo"][1]
        area = band[y0:y1 + 1, x0:x1 + 1]
        nib = set()
        for k in range(4):
            nib.update(np.unique((area >> (4 * k)) & 15).tolist())
        used4.setdefault((c["model"], c["mat"] & 0x7EFF), set()).update(nib)
    bins, pal4 = [], {}                               # bins: [16 colours or None]
    for (m_, mat) in sorted(groups):
        if mat & 0x8000 or (m_, mat & 0x7EFF) in wide_keys:
            continue
        key = (m_, mat & 0x7EFF)
        pal = (list(src[m_].cluts.get(mat & 0x7EFF, [0] * 16))[:16] + [0] * 16)[:16]
        need = sorted(used4.get(key, set(range(16))))
        home = None
        for j, b_ in enumerate(bins):
            if all(b_[i] is None or b_[i] == pal[i] for i in need):
                home = j
                break
        if home is None:
            if len(bins) >= len(slots4):
                raise MI.Budget(f"the chosen parts need more than {len(slots4)} small colour tables "
                                "(a fighter's room): take parts from fewer different fighters")
            bins.append([None] * 16)
            home = len(bins) - 1
        for i in need:
            bins[home][i] = pal[i]
        new_mat[(m_, mat)] = slots4[home]
    for j, b_ in enumerate(bins):
        pal4[slots4[j]] = [c if c is not None else 0 for c in b_]
    if bins:
        log(f"4-bit CLUTs: {sum(1 for k in groups if not k[1] & 0x8000)} materials in {len(bins)} tables")
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
            if c["wide"]:
                rel = cols(faces[i]) - c["lo"]
                face_uv[i] = [(int(c["dst"][0] + 2 * u), int(c["dst"][1] + v)) for u, v in rel]
            else:
                face_uv[i] = [(int(u), int(v)) for u, v in (cols(faces[i]) + off)]
    for i, f in enumerate(faces):
        f["chart"] = chart_of[new_mat[(f["model"], f["smat"])]]
    if tint and tuple(tint[:3]) != (0, 100, 0):              # the mix's own colours (hue, saturation, lightness)
        runs = [(cid, [recolour(c, *tint) for c in pal]) for cid, pal in runs]
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
    # Namco's own polygons only: up to what the stock models themselves need (imports keep a margin).
    # A model a little too big for the base's slot is written again with coarser normals (fewer
    # stored, the light barely changes)
    # Over the packet budget: neighbouring triangles with the same texels on their shared edge go
    # out as quads (the GPU draws the same two triangles, 52 bytes instead of 80)
    def pair(why):
        nonlocal faces, texture
        from direct_import import _pair_quads
        tris = [i for i, f in enumerate(faces) if len(f["v"]) == 3]
        paired, paired_uv = _pair_quads([faces[i] for i in tris], [texture["uv"][i] for i in tris], G=pos)
        keep = [i for i, f in enumerate(faces) if len(f["v"]) != 3]
        log(f"{why}: {len(tris) - len(paired)} triangle pairs as quads")
        faces = [faces[i] for i in keep] + paired
        texture = dict(texture, uv=[texture["uv"][i] for i in keep] + paired_uv, paired=True)

    # Still too big for the slot: edge collapses (decimate.py) down to keep_share of the triangles,
    # never joining two body parts; every corner keeps its texel, then pairs go out as quads again
    def simplify(keep_share, why):
        nonlocal faces, texture, pos, Nrm
        import decimate as D
        tris, src, uvs = [], [], []
        for i, f in enumerate(faces):
            corners = [(0, 1, 2)] if len(f["v"]) == 3 else [(0, 1, 2), (1, 3, 2)]
            for c in corners:
                tris.append([f["v"][k] for k in c])
                uvs.append([texture["uv"][i][k] for k in c])
                src.append(i)
        alive = []
        new_pos, _, out, _ = D.decimate(pos, np.array(tris), int(len(tris) * keep_share),
                                        keep=lambda a, b: owner[a] == owner[b], alive_out=alive)
        log(f"{why}: {len(tris)} triangles simplified to {len(out)}")
        faces = [dict(faces[src[k]], v=[int(x) for x in out[n]]) for n, k in enumerate(alive)]
        texture = dict(texture, uv=[uvs[k] for k in alive], paired=False)
        pos = new_pos
        Nrm = np.zeros_like(pos)
        for f in faces:
            v = f["v"]
            Nrm[v] += np.cross(pos[v[1]] - pos[v[0]], pos[v[2]] - pos[v[0]])
        Nrm /= np.linalg.norm(Nrm, axis=1, keepdims=True) + 1e-12
        pair("after simplifying")

    def write(steps):
        try:
            return MI._write(B.m, pos, Nrm, faces, [int(o) for o in owner], {}, F, J, row, {"ready": texture},
                             max_packets=MI.STOCK_PACKET_BYTES, normal_steps=steps)
        except MI.Budget as error:
            if "GPU packets" not in str(error) or texture.get("paired"):
                raise
            pair(str(error))
            return MI._write(B.m, pos, Nrm, faces, [int(o) for o in owner], {}, F, J, row, {"ready": texture},
                             max_packets=MI.STOCK_PACKET_BYTES, normal_steps=steps)

    for steps in (8, 6, 4):
        data, report = write(steps)
        if len(data) <= len(B.m):
            break
        log(f"{len(data)} bytes for a slot of {len(B.m)}: normals in coarser steps")
    if len(data) > len(B.m) and not texture.get("paired"):   # then: quads take fewer bytes too
        pair(f"{len(data)} bytes for a slot of {len(B.m)}")
        data, report = write(steps)
    whole = (faces, texture, pos)
    for keep_share in (0.95, 0.9, 0.85, 0.8):                   # last: a little simpler, within each body part
        if len(data) <= len(B.m):
            break
        faces, texture, pos = whole
        simplify(keep_share, f"{len(data)} bytes for a slot of {len(B.m)}")
        data, report = write(steps)
    report.update(bytes=len(data), budget=len(B.m), parts=parts, normal_steps=steps)
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
    ap.add_argument("--colours", type=lambda v: (lambda h, s, l, k: (float(h), float(s), float(l), k == "1"))(*v.split(",")),
                    help="hue,saturation,lightness,keep skin (1/0): e.g. 120,100,0,1")
    ap.add_argument("--shape", type=json.loads, default=None, help='body shape JSON, e.g. {"head": 1.2, "arms": 1.1}')
    ap.add_argument("--pieces", type=json.loads, default=None, help='piece colours JSON, e.g. {"20:64": [120, 100, 0]}')
    ap.add_argument("--list-pieces", action="store_true", help="print the mix's pieces of clothing as JSON")
    a = ap.parse_args()
    X.setup(a.root)
    if a.heights is not None:
        print(json.dumps({m: round(Source(a.root, m).height(), 1) for m in a.heights}))
        return
    if a.base is None or (a.out is None and not a.list_pieces):
        raise SystemExit("ERROR: --base and --out are needed to build")
    parts = {}
    for p in a.part:
        n, v = p.split("=")
        if n not in PARTS:
            raise SystemExit(f"unknown part {n}")
        parts[n] = int(v)
    if a.list_pieces:
        print(json.dumps(list_pieces(a.root, a.base, parts)))
        return
    import model_import as MI
    try:
        stock, new, tx, report = build(a.root, a.base, parts, tint=a.colours, shape=a.shape, pieces=a.pieces)
    except MI.Budget as error:
        text = str(error)
        if "GPU packets" in text:               # the writer's budget, said for a player
            text = "the chosen parts have more polygons than the game draws for one fighter: take a simpler part"
        raise SystemExit(f"ERROR: {text}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(X.own_model_file(a.base, stock, new, tx))
    rep = {k: v for k, v in report.items() if k not in ("rows", "texture")}
    print(json.dumps(rep, default=str))
    print(f"OK kitbash over model {a.base}: {len(new)} bytes, {report['triangles']} triangles")


if __name__ == "__main__":
    main()
