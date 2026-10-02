"""PS1 texture for an imported model: UV charts, an 8-bit atlas, colours baked from the source.

The atlas fills the first texture page of the fighter's band: 64 halfwords = 256 texels of 4
bits wide, 256 rows (VRAM x 384.. of the player). Charts are grouped by colour; each group has
its own 16-colour CLUT in CLUT row 0 (ids 0, 1, 2...), only as many as the donor's own CLUTs
fill there, so nothing outside the donor's palette space is touched.

layout(): triangles are grouped into charts per body row and facing (the six axis directions of
the row's frame) and flattened by orthographic projection; charts are packed into shelves at one
texel density, the largest that fits."""
from __future__ import annotations
import io
import numpy as np

ATLAS_W, ATLAS_H = 256, 256
GUTTER = 2


def charts(tris, G, normals, tri_frame, F):
    """chart id per triangle and per-corner 2D coordinates (game units) in the chart's plane."""
    key = []
    for i, t in enumerate(tris):
        nl = F[tri_frame[i]].T @ normals[i]
        ax = int(np.argmax(np.abs(nl)))
        key.append((tri_frame[i], ax, 1 if nl[ax] > 0 else -1))
    # connected components among triangles with the same key (shared edge)
    parent = list(range(len(tris)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    edges = {}
    for i, t in enumerate(tris):
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edges.setdefault((min(e), max(e)), []).append(i)
    for ts in edges.values():
        for a in ts:
            for b in ts:
                if a < b and key[a] == key[b]:
                    parent[find(a)] = find(b)
    roots = {}
    chart = [roots.setdefault(find(i), len(roots)) for i in range(len(tris))]
    flat = np.zeros((len(tris), 3, 2))
    for i, t in enumerate(tris):
        frame, ax, sign = key[i]
        R = F[frame]
        u_ax, v_ax = [k for k in range(3) if k != ax]
        for c in range(3):
            loc = R.T @ G[t[c]]
            # mirror one axis on the negative side so the chart is not seen from behind
            flat[i, c] = (loc[u_ax] * sign, loc[v_ax])
    return chart, flat


def pack(chart, flat):
    """Texel coordinates per triangle corner."""
    uv, scale = pack_faces(chart, list(flat))
    return np.array(uv), scale


def pack_faces(chart, flat):
    """Texel coordinates per face corner (faces of any corner count): the charts' bounding
    boxes on shelves, at the highest common texel density that fits."""
    n = max(chart) + 1
    lo = np.full((n, 2), np.inf)
    hi = np.full((n, 2), -np.inf)
    for i, c in enumerate(chart):
        lo[c] = np.minimum(lo[c], flat[i].min(0))
        hi[c] = np.maximum(hi[c], flat[i].max(0))
    size = hi - lo

    def place(scale):
        """Skyline packing, tallest charts first, each upright or on its side, wherever it ends
        lowest. -> (top-left per chart, turned per chart) or None."""
        dims = np.ceil(size * scale).astype(int) + 1 + 2 * GUTTER
        sky = np.zeros(ATLAS_W, dtype=int)
        at = np.zeros((n, 2), dtype=int)
        turned = np.zeros(n, dtype=bool)
        for c in np.argsort(-dims.max(1), kind="stable"):
            best = None
            for turn in (False, True):
                w, h = (dims[c][::-1] if turn else dims[c])
                if w > ATLAS_W:
                    continue
                tops = np.array([sky[x:x + w].max() for x in range(ATLAS_W - w + 1)])
                x = int(np.argmin(tops))
                if tops[x] + h <= ATLAS_H and (best is None or tops[x] + h < best[0]):
                    best = (tops[x] + h, x, tops[x], turn, w)
            if best is None:
                return None
            end, x, y, turn, w = best
            sky[x:x + w] = end
            at[c] = (x + GUTTER, y + GUTTER)
            turned[c] = turn
        return at, turned

    lo_s, hi_s = 0.001, 1000.0
    best = None
    for _ in range(40):
        mid = (lo_s + hi_s) / 2
        at = place(mid)
        if at is None:
            hi_s = mid
        else:
            lo_s, best = mid, (mid, at)
    scale, (at, turn) = best
    uv = []
    for i, c in enumerate(chart):
        q = np.asarray(flat[i], float) - lo[c]
        if turn[c]:
            q = q[:, ::-1]
        uv.append(np.round(q * scale).astype(int) + at[c])
    return uv, scale


def raster(uv, fn, offset=(0.5, 0.5)):
    """Calls fn(triangle, texel xy array, barycentric array) for the texels each triangle covers
    (texel centres, plus a one-texel border so edges are covered)."""
    for i, t in enumerate(uv):
        a, b, c = t.astype(float)
        x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int) - 1
        x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int) + 1
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, ATLAS_W - 1) + 1),
                             np.arange(max(y0, 0), min(y1, ATLAS_H - 1) + 1))
        P = np.stack([xs.ravel() + offset[0], ys.ravel() + offset[1]], 1)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (P[:, 0] - c[0]) + (c[0] - b[0]) * (P[:, 1] - c[1])) / d
        l2 = ((c[1] - a[1]) * (P[:, 0] - c[0]) + (a[0] - c[0]) * (P[:, 1] - c[1])) / d
        l3 = 1 - l1 - l2
        inside = (l1 >= -0.15) & (l2 >= -0.15) & (l3 >= -0.15)
        if inside.any():
            bc = np.clip(np.stack([l1, l2, l3], 1)[inside], 0, 1)
            bc /= bc.sum(1, keepdims=True)
            fn(i, np.floor(P[inside]).astype(int), bc)


class Source:
    """Colours of the original model: its textures, sampled at (triangle, u, v) points."""

    def __init__(self, ch):
        from PIL import Image
        self.uv = np.array(ch["corner_uvs"]).reshape(-1, 3, 2)
        self.mat = np.array(ch["materials"])
        self.images = {}
        for k, (_, data) in ch["textures"].items():
            im = Image.open(io.BytesIO(data))
            self.alpha = getattr(self, "alpha", {})
            if im.mode in ("RGBA", "LA", "P"):
                self.alpha[k] = np.asarray(im.convert("RGBA"))[..., 3]
            self.images[k] = np.asarray(im.convert("RGB"))

    def transparent(self):
        """Per original triangle: is its texture see-through at its centre (eyelash cards, hair
        cards)? Such triangles neither shape the model nor colour it."""
        out = np.zeros(len(self.mat), dtype=bool)
        centre = self.uv.mean(1)
        for k, a in getattr(self, "alpha", {}).items():
            sel = self.mat == k
            h, w = a.shape
            y = ((1 - np.mod(centre[sel, 1], 1.0)) * h).astype(int).clip(0, h - 1)
            x = (np.mod(centre[sel, 0], 1.0) * w).astype(int).clip(0, w - 1)
            out[sel] = a[y, x] < 128
        return out

    def colours(self, src):
        out = np.full((len(src), 3), 128, dtype=np.uint8)
        t = src[:, 0].astype(int)
        ok = t >= 0
        u, v = src[:, 1], src[:, 2]
        tt = np.where(ok, t, 0)
        w = np.stack([1 - u - v, u, v], 1)
        uv = np.einsum("nk,nkj->nj", w, self.uv[tt])
        for k, img in self.images.items():
            sel = ok & (self.mat[tt] == k)
            if not sel.any():
                continue
            h, wd = img.shape[:2]
            x = (np.mod(uv[sel, 0], 1.0) * wd).astype(int).clip(0, wd - 1)
            y = ((1 - np.mod(uv[sel, 1], 1.0)) * h).astype(int).clip(0, h - 1)
            out[sel] = img[y, x]
        return out


def bake(tris, G, uv, to_source, lookup, source, normals, chart, push=0.0, caster=None, reach=0.0, vnormals=None):
    """RGB atlas, a mask of painted texels and the chart of every texel (-1: none). Each texel
    averages 3 x 3 points; each point is pushed `push` outwards first, so the outermost layer
    of the original (armour over skin) gives the colour. to_source maps game points to the
    original model's space, lookup gives the nearest original surface point."""
    rgb = np.zeros((ATLAS_H, ATLAS_W, 3), dtype=np.float64)
    count = np.zeros((ATLAS_H, ATLAS_W))
    owner = -np.ones((ATLAS_H, ATLAS_W), dtype=int)
    unit = normals / (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12)
    pts, where, tri_of, nrm = [], [], [], []

    def collect(i, xy, bc):
        n = bc @ vnormals[tris[i]] if vnormals is not None else np.repeat(unit[i][None], len(bc), 0)
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        pts.append(bc @ G[tris[i]] + (0 if caster is not None else push) * n)
        nrm.append(n)
        where.append(xy)
        tri_of.append(np.full(len(xy), i))
    for oy in (1 / 6, 0.5, 5 / 6):
        for ox in (1 / 6, 0.5, 5 / 6):
            raster(uv, collect, (ox, oy))
    P = np.concatenate(pts)
    XY = np.concatenate(where)
    TI = np.concatenate(tri_of)
    if caster is not None:
        # bake as a camera would see it: a ray from just outside the low-poly surface inwards,
        # the first surface of the original it meets gives the colour (eyes in their sockets,
        # skin around them); rays that meet nothing fall back to the nearest surface point
        Nn = np.concatenate(nrm)
        a, b = to_source(P), to_source(P + Nn)
        dirs = a - b
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-12
        hit = caster.first_hit(a - dirs * reach, dirs, 2 * reach)
        src = hit[:, :3].copy()
        miss = hit[:, 0] < 0
        if getattr(caster, "numbers", None) is not None:     # the caster's mesh is a subset
            src[~miss, 0] = caster.numbers[src[~miss, 0].astype(int)]
        if miss.any():
            src[miss] = lookup(a[miss])
    else:
        src = lookup(to_source(P))
    col = source.colours(src).astype(float)
    np.add.at(rgb, (XY[:, 1], XY[:, 0]), col)
    np.add.at(count, (XY[:, 1], XY[:, 0]), 1)
    owner[XY[:, 1], XY[:, 0]] = np.asarray(chart)[TI]
    painted = count > 0
    rgb[painted] /= count[painted][:, None]
    # bleed colours into the gutter so filtering at chart edges never shows black
    for _ in range(GUTTER + 1):
        grow = np.zeros_like(rgb)
        n = np.zeros(count.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            s = np.roll(np.roll(rgb * painted[..., None], dy, 0), dx, 1)
            m = np.roll(np.roll(painted, dy, 0), dx, 1)
            grow += s
            n += m
        new = ~painted & (n > 0)
        rgb[new] = grow[new] / n[new][:, None]
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            o = np.roll(np.roll(owner, dy, 0), dx, 1)
            take = new & (owner < 0) & (o >= 0)
            owner[take] = o[take]
        painted = painted | new
    return rgb.astype(np.uint8), painted, owner


def ps1_colour(r, g, b):
    c = (int(r) >> 3) | ((int(g) >> 3) << 5) | ((int(b) >> 3) << 10)
    return c or 0x0421                     # 0x0000 is transparent on the PS1


def _palette16(pixels):
    from PIL import Image
    im = Image.fromarray(pixels.reshape(1, -1, 3).astype(np.uint8), "RGB")
    q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:48], dtype=float).reshape(16, 3)
    pal = pal[np.unique(np.asarray(q))]
    return np.concatenate([pal, np.repeat(pal[-1:], 16 - len(pal), 0)]) if len(pal) < 16 else pal


def _nearest(pixels, pal):
    d = ((pixels[:, None, :] - pal[None, :, :]) ** 2).sum(2)
    return d.argmin(1), d.min(1)


def quantise_groups(rgb, owner, groups: int, own=()):
    """4-bit texels: charts grouped by colour, a 16-colour palette per group; the charts in `own`
    (the face) get a palette of their own, as Namco's faces do.
    -> (indices 0..15 per texel, PS1 palette of groups x 16 colours, group of every chart)."""
    nchart = int(owner.max()) + 1
    own = [c for c in own if c < nchart][:max(0, groups - 1)]
    if own:
        rest = [c for c in range(nchart) if c not in own]
        sub = np.full(owner.shape, -1)
        for i, c in enumerate(rest):
            sub[owner == c] = i
        idx, palette, g_rest = quantise_groups(rgb, sub, groups - len(own)) if rest else (np.zeros(owner.shape, np.uint8), [], [])
        g = np.zeros(nchart, dtype=int)
        for i, c in enumerate(rest):
            g[c] = g_rest[i]
        for c in own:
            sel = owner == c
            pal = _palette16(rgb[sel].astype(float)) if sel.any() else np.full((16, 3), 128.0)
            g[c] = len(palette) // 16
            idx[sel] = _nearest(rgb[sel].astype(float), pal)[0]
            palette = palette + [ps1_colour(*col) for col in pal]
        return idx, palette, g
    px = [rgb[owner == c].astype(float) for c in range(nchart)]
    mean = np.array([p.mean(0) if len(p) else np.zeros(3) for p in px])
    weight = np.array([len(p) for p in px], dtype=float)
    groups = max(1, min(groups, int((weight > 0).sum())))
    # k-means on the charts' mean colours, then refined on the real palettes
    rng = np.random.default_rng(1)
    centre = mean[rng.choice(nchart, groups, replace=False, p=weight / weight.sum())]
    g = np.zeros(nchart, dtype=int)
    for _ in range(12):
        g = ((mean[:, None] - centre[None]) ** 2).sum(2).argmin(1)
        for k in range(groups):
            if (g == k).any():
                centre[k] = np.average(mean[g == k], axis=0, weights=weight[g == k] + 1e-9)

    def palettes():
        out = []
        for k in range(groups):
            members = [px[c] for c in range(nchart) if g[c] == k and len(px[c])]
            out.append(_palette16(np.concatenate(members)) if members else np.full((16, 3), 128.0))
        return out
    for _ in range(3):
        pals = palettes()
        for c in range(nchart):
            if len(px[c]):
                g[c] = int(np.argmin([_nearest(px[c], pal)[1].sum() for pal in pals]))
    pals = palettes()
    idx = np.zeros(owner.shape, dtype=np.uint8)
    for c in range(nchart):
        sel = owner == c
        if sel.any():
            idx[sel] = _nearest(rgb[sel].astype(float), pals[g[c]])[0]
    palette = [ps1_colour(*col) for pal in pals for col in pal]
    return idx, palette, g


def band4(idx):
    """4-bit texels -> halfwords (4 texels each, the leftmost in the low bits)."""
    q = idx.astype(np.uint16)
    return q[:, 0::4] | q[:, 1::4] << 4 | q[:, 2::4] << 8 | q[:, 3::4] << 12


def quantise(rgb, colours):
    """(indices, PS1 palette) with at most `colours` entries."""
    from PIL import Image
    im = Image.fromarray(rgb, "RGB").quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = im.getpalette()[:3 * colours]
    idx = np.asarray(im, dtype=np.uint8)
    used = int(idx.max()) + 1
    palette = [ps1_colour(*pal[3 * k:3 * k + 3]) for k in range(used)]
    return idx, palette
