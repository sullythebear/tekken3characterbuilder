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


def pack_faces(chart, flat, wide=()):
    """Texel coordinates per face corner (faces of any corner count): the charts' bounding
    boxes on shelves, at the highest common texel density that fits. Charts in `wide` will be
    8-bit: they take twice the columns (coordinates here stay in 4-bit columns, twice as wide),
    start on a halfword (4 columns) and are never turned."""
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
        for c in wide:
            dims[c, 0] = -(-(2 * int(np.ceil(size[c, 0] * scale)) + 2 + 8) // 4) * 4
        sky = np.zeros(ATLAS_W, dtype=int)
        at = np.zeros((n, 2), dtype=int)
        turned = np.zeros(n, dtype=bool)
        for c in np.argsort(-dims.max(1), kind="stable"):
            best = None
            for turn in ((False,) if c in wide else (False, True)):
                w, h = (dims[c][::-1] if turn else dims[c])
                if w > ATLAS_W:
                    continue
                step = 4 if c in wide else 1
                xs = range(0, ATLAS_W - w + 1, step)
                tops = np.array([sky[x:x + w].max() for x in xs])
                x = xs[int(np.argmin(tops))]
                tops = {x: sky[x:x + w].max()}
                if tops[x] + h <= ATLAS_H and (best is None or tops[x] + h < best[0]):
                    best = (tops[x] + h, x, tops[x], turn, w)
            if best is None:
                return None
            end, x, y, turn, w = best
            sky[x:x + w] = end
            at[c] = (x + (4 if c in wide else GUTTER), y + GUTTER)
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
        if c in wide:
            q = q * [2.0, 1.0]
            # even columns: the 8-bit texel is the column pair
            uv.append((np.round(q * scale / [2, 1]) * [2, 1]).astype(int) + at[c])
            continue
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


def paint(rgb, owner):
    """A painted look, as Namco's textures: a 3 x 3 median removes the speckle of photographic
    sources (dirt, pores, stitch noise) but keeps edges (straps, laces); then a light smoothing
    of what is left. Only inside each chart, so charts never bleed into each other."""
    from PIL import Image, ImageFilter
    out = rgb.copy()
    med = np.asarray(Image.fromarray(rgb).filter(ImageFilter.MedianFilter(3)))
    soft = med
    same = np.ones(owner.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            same &= np.roll(np.roll(owner, dy, 0), dx, 1) == owner
    out[same] = soft[same]
    return out


def flatten(rgb, owner, radius=8, strength=0.8):
    """Takes baked-in light and dirt out: inside each chart the brightness is divided by its own
    heavy blur (raised to `strength`), so broad shading and stains even out while edges and
    small details (seams, straps) stay. Tekken 3 textures are flat colour; the game's gouraud
    light does the shading."""
    from PIL import Image, ImageFilter
    x = rgb.astype(float)
    lum = x.mean(2)
    out = x.copy()
    for c in range(int(owner.max()) + 1):
        m = owner == c
        if m.sum() < 16:
            continue
        mean = lum[m].mean()
        fill = np.where(m, lum, mean)
        blur = np.asarray(Image.fromarray(np.clip(fill, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius)), dtype=float)
        gain = (mean / np.maximum(blur, 8)) ** strength
        out[m] = x[m] * gain[m][:, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def stylise(rgb, owner, k=6, shade=0.6, passes=2, mode=5, merge=55, light=0.2):
    """Namco's painted style: each chart's colours become a few flat areas (k-means, at most k
    colours), speckles cleaned by a 3 x 3 majority filter so the areas have crisp edges, and a
    soft version of the original light laid over them (brightness relative to the area's mean,
    blurred, kept within +-20 %, to the power `shade`)."""
    from PIL import Image, ImageFilter
    x = rgb.astype(float)
    out = x.copy()
    lum = x.mean(2)
    soft = np.asarray(Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(1.5)), dtype=float)
    rng = np.random.default_rng(2)
    for c in range(int(owner.max()) + 1):
        m = owner == c
        n = int(m.sum())
        if n < 16:
            continue
        px = x[m]
        kk = min(k, max(1, n // 24))
        centre = px[rng.choice(n, kk, replace=False)]
        for _ in range(10):
            lab = ((px[:, None] - centre[None]) ** 2).sum(2).argmin(1)
            for j in range(kk):
                if (lab == j).any():
                    centre[j] = px[lab == j].mean(0)
        # areas of nearly the same colour are one area (white and light grey armour, beige and a
        # slightly darker beige stain); each merges into the bigger one
        size = np.bincount(lab, minlength=kk)
        for j in np.argsort(size):
            near = [i for i in range(kk) if i != j and size[i] >= size[j] and size[i] > 0
                    and np.linalg.norm(centre[i] - centre[j]) < merge]
            if near and size[j] > 0:
                i = min(near, key=lambda i: np.linalg.norm(centre[i] - centre[j]))
                lab[lab == j] = i
                size[i] += size[j]
                size[j] = 0
                centre[i] = px[lab == i].mean(0)
        # colour areas under 6 % of the chart are specks at this texel size (thin painted
        # stripes, rivets): they join the nearest bigger area
        size = np.bincount(lab, minlength=kk)
        small = [j for j in range(kk) if 0 < size[j] < 0.06 * n]
        big = [j for j in range(kk) if size[j] >= 0.06 * n]
        for j in small:
            if big:
                i = min(big, key=lambda i: np.linalg.norm(centre[i] - centre[j]))
                lab[lab == j] = i
        img = np.zeros(owner.shape, dtype=np.uint8)
        img[m] = lab + 1
        # no islands: two 5 x 5 majority passes fold specks of up to ~12 texels into their
        # surroundings (lace, pores, stitches read as noise at Tekken 3's texel size)
        for _ in range(passes):
            img = np.asarray(Image.fromarray(img).filter(ImageFilter.ModeFilter(mode)))
        lab2 = np.where(img[m] > 0, img[m] - 1, lab)
        means = np.array([soft[m][lab2 == j].mean() if (lab2 == j).any() else 1 for j in range(kk)])
        rel = np.clip(soft[m] / np.maximum(means[lab2], 1), 1 - light, 1 + light) ** shade
        out[m] = centre[lab2] * rel[:, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def vivid(rgb, saturation=1.25, contrast=1.08):
    """Namco's palettes are saturated and contrasty; photographic sources look washed out under
    the game's light. More colour and a little more contrast."""
    x = rgb.astype(float)
    grey = x.mean(2, keepdims=True)
    x = grey + (x - grey) * saturation
    x = (x - 128) * contrast + 128
    return np.clip(x, 0, 255).astype(np.uint8)


def ps1_colour(r, g, b):
    c = (int(r) >> 3) | ((int(g) >> 3) << 5) | ((int(b) >> 3) << 10)
    return c or 0x0421                     # 0x0000 is transparent on the PS1


def lab(rgb):
    """sRGB (0..255) -> CIE Lab: colour distances as the eye sees them."""
    c = np.asarray(rgb, float) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def _palette16(pixels, lab_=False):
    from PIL import Image
    im = Image.fromarray(pixels.reshape(1, -1, 3).astype(np.uint8), "RGB")
    q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = list(q.getpalette()[:48])
    raw += raw[-3:] * ((48 - len(raw)) // 3) if raw else [128] * 48     # fewer than 16 colours
    pal = np.array(raw[:48], dtype=float).reshape(16, 3)
    pal = pal[np.unique(np.asarray(q))]
    pal = np.concatenate([pal, np.repeat(pal[-1:], 16 - len(pal), 0)]) if len(pal) < 16 else pal
    # Lloyd refinement of the median cut: palettes shared by charts of different colours (skin
    # and beige cloth) otherwise give one of them the other's tones
    pts = pixels.reshape(-1, 3).astype(float)
    if len(pts) > 20000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 20000, replace=False)]
    sp = lab(pts) if lab_ else pts
    for _ in range(8):
        k = ((sp[:, None, :] - (lab(pal) if lab_ else pal)[None]) ** 2).sum(2).argmin(1)
        for j in range(16):
            if (k == j).any():
                pal[j] = pts[k == j].mean(0)
    return pal


def _nearest(pixels, pal, lab_=False):
    if lab_:                                  # as the eye sees it: beige never turns salmon
        pixels, pal = lab(pixels), lab(np.asarray(pal, float))
    d = ((pixels[:, None, :] - pal[None, :, :]) ** 2).sum(2)
    return d.argmin(1), d.min(1)


def quantise_groups(rgb, owner, groups: int, own=(), lab_=False):
    """4-bit texels: charts grouped by colour, a 16-colour palette per group; the charts in `own`
    (the face) get a palette of their own, as Namco's faces do. lab_: colour distances in Lab.
    -> (indices 0..15 per texel, PS1 palette of groups x 16 colours, group of every chart)."""
    nchart = int(owner.max()) + 1
    own = [c for c in own if c < nchart][:max(0, groups - 1)]
    if own:
        rest = [c for c in range(nchart) if c not in own]
        sub = np.full(owner.shape, -1)
        for i, c in enumerate(rest):
            sub[owner == c] = i
        idx, palette, g_rest = quantise_groups(rgb, sub, groups - len(own), lab_=lab_) if rest else (np.zeros(owner.shape, np.uint8), [], [])
        g = np.zeros(nchart, dtype=int)
        for i, c in enumerate(rest):
            g[c] = g_rest[i]
        for c in own:
            sel = owner == c
            pal = _palette16(rgb[sel].astype(float), lab_) if sel.any() else np.full((16, 3), 128.0)
            g[c] = len(palette) // 16
            idx[sel] = _nearest(rgb[sel].astype(float), pal, lab_)[0]
            palette = palette + [ps1_colour(*col) for col in pal]
        return idx, palette, g
    px = [rgb[owner == c].astype(float) for c in range(nchart)]
    mean = np.array([p.mean(0) if len(p) else np.zeros(3) for p in px])
    if lab_:
        mean = lab(mean)
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
            out.append(_palette16(np.concatenate(members), lab_) if members else np.full((16, 3), 128.0))
        return out
    for _ in range(3):
        pals = palettes()
        for c in range(nchart):
            if len(px[c]):
                g[c] = int(np.argmin([_nearest(px[c], pal, lab_)[1].sum() for pal in pals]))
    pals = palettes()
    idx = np.zeros(owner.shape, dtype=np.uint8)
    for c in range(nchart):
        sel = owner == c
        if sel.any():
            idx[sel] = _nearest(rgb[sel].astype(float), pals[g[c]], lab_)[0]
    palette = [ps1_colour(*col) for pal in pals for col in pal]
    return idx, palette, g


def face8(rgb, owner, charts):
    """The 8-bit charts (stretched over column pairs in the 4-bit atlas): the pairs averaged
    into 8-bit texels, a 256-colour palette for them. -> (index per 4-bit column pair, i.e. an
    array of half the atlas width, mask of those pairs, PS1 palette of 256)."""
    from PIL import Image
    mask = np.isin(owner, list(charts))
    pair = (rgb[:, 0::2].astype(float) + rgb[:, 1::2]) / 2
    pm = mask[:, 0::2] | mask[:, 1::2]
    px = pair[pm]
    im = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8), "RGB")
    q = im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:765], dtype=float).reshape(255, 3)
    idx = np.zeros(pm.shape, dtype=np.uint8)
    idx[pm] = np.asarray(q, dtype=np.uint8).ravel() + 1          # entry 0 stays unused (black)
    palette = [0x0421] + [ps1_colour(*c) for c in pal]
    return idx, pm, palette


def band8_into(band, idx8, pm):
    """Writes 8-bit texels (one per 4-bit column pair) over the halfwords they cover."""
    h, w8 = idx8.shape
    q = idx8.astype(np.uint16)
    hw = q[:, 0::2] | q[:, 1::2] << 8                              # 2 texels per halfword
    cover = pm[:, 0::2] | pm[:, 1::2]
    band[cover] = hw[cover]
    return band


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
