"""High-poly rigged model -> PS1-sized model with a baked 256 x 256 texture (venv).

`reduce(src, target)` takes what direct_import.load returns (upright, per-corner UVs, bones,
weights) and returns the same kind of dict for a model of about `target` triangles:

1. a closed outer shell of the opaque surface (voxel remesh, Taubin smoothing): hidden layers
   (skin under clothes, the inside of the mouth) and see-through hair-card edges go;
2. quadric edge collapse to the target (head counts four times as much, even triangles);
3. the vertices relaxed along the surface and put back on the original;
4. skin weights from the nearest original surface point;
5. charts of similar normals, projected flat, packed into 256 x 256 (the head at three times
   the texel density, as Namco gives the face most of the page);
6. every texel baked by a short ray from just outside the new surface inwards: the first opaque
   texel of the original model it meets (cards with transparent texels are passed through)."""
from __future__ import annotations
import io
import numpy as np

import remesh as RM
import decimate as DC

ATLAS = 256
GUTTER = 2
_SHELL = {}


def _weld(P):
    key = {}
    weld = np.array([key.setdefault(tuple(np.round(p, 5)), len(key)) for p in P])
    Pw = np.zeros((len(key), 3))
    Pw[weld] = P
    return Pw, weld


def _texel(textures, mat, uv):
    """RGBA of the source textures at per-point UVs (top-down)."""
    out = np.zeros((len(uv), 4), np.uint8)
    for m in np.unique(mat):
        im = textures.get(int(m))
        if im is None:
            im = next(iter(textures.values()))
        h, w = im.shape[:2]
        k = mat == m
        out[k] = im[np.clip((uv[k, 1] * h).astype(int), 0, h - 1), (uv[k, 0] * w).astype(int) % w]
    return out


def _loose(src, T):
    """Triangles whose corners mostly hang on bones with no Tekken part (cloth, props)."""
    import model_import as MI
    bones = src.get("bones") or []
    unknown = np.array([MI._part(b["name"])[0] is None and b["parent"] >= 0 for b in bones] + [False])
    W = src.get("weights", [])
    if not len(W):
        return np.zeros(len(T), bool)
    vu = np.array([sum(w for b, w in wv.items() if unknown[b]) / max(sum(wv.values()), 1e-9) if wv else 0.0
                   for wv in W])
    return (vu[T] > 0.5).sum(1) >= 2


def _limb_groups(src, Tw, weld):
    """Per welded triangle: 0 trunk/head, 1/2 left/right arm, 3/4 left/right leg (the dominant
    bone of its corners), so the shell never fills the gap between two limbs."""
    import model_import as MI
    bones = src.get("bones") or []
    part = []
    for b in bones:
        j, p = b, MI._part(b["name"])
        while p[0] is None and j["parent"] >= 0:
            j = bones[j["parent"]]
            p = MI._part(j["name"])
        g = 0
        if p[0] in ("upper", "fore", "hand"):
            g = 1 if p[1] == "L" else 2
        elif p[0] in ("thigh", "shin", "foot"):
            g = 3 if p[1] == "L" else 4
        part.append(g)
    vg = np.zeros(weld.max() + 1, int)
    for i, w in enumerate(src.get("weights", [])):
        if w:
            vg[weld[i]] = part[max(w, key=w.get)]
    t = vg[Tw]
    out = t[:, 0].copy()                      # majority of the three corners
    out[(t[:, 1] == t[:, 2])] = t[t[:, 1] == t[:, 2], 1]
    return out


def _shell(P, T, groups, cells=180, close=1):
    """Closed surface around the triangles: a voxel solid per limb group (closed separately, so
    thighs that nearly touch stay apart), their union, surface nets, snapped back on the
    original (as remesh.remesh)."""
    lo, hi = P.min(0), P.max(0)
    h = float((hi - lo).max()) / cells
    origin = lo - 3 * h
    shape = tuple(np.ceil((hi - lo) / h).astype(int) + 6)
    samples, tri, us, vs = RM.surface_samples(P, T, h)
    inside = RM.solid(samples, origin, h, shape, close)
    # the closing also fills narrow gaps between limbs (between the thighs): voxels that only the
    # closing added and that lie next to two different limbs (or a limb and the trunk) go
    idx = np.floor((samples - origin) / h).astype(int)
    near = {}
    for g in np.unique(groups):
        m = np.zeros(shape, bool)
        k = idx[groups[tri] == g]
        m[k[:, 0], k[:, 1], k[:, 2]] = True
        for _ in range(close + 1):
            m = RM._dilate(m)
        near[g] = m
    surf = np.zeros(shape, bool)
    surf[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    count = sum(m.astype(int) for m in near.values())
    limb = sum(near[g].astype(int) for g in near if g != 0)
    bridge = inside & ~surf & (count >= 2) & (limb >= 1)
    # keep the real inside of a limb: only voxels outside every group's own closed solid
    own = np.zeros(shape, bool)
    for g in np.unique(groups):
        own |= RM.solid(samples[groups[tri] == g], origin, h, shape, close)
    inside &= ~(bridge & ~own)
    v, f = RM.surface_nets(inside, origin, h)
    v = RM.smooth(v, f, rounds=3)
    near = RM.snap(v, samples, origin, h, shape)
    v[near >= 0] = samples[near[near >= 0]]
    v = RM.smooth(v, f, rounds=1, lam=0.3)
    return v, np.asarray(f)


def _vertex_normals(V, F):
    n = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def _charts(V, F, head, limit=65.0):  # head: per-face class, never mixed in a chart
    """Faces grouped by similar normals (region growing over shared edges), at most `limit`
    degrees from the chart's first face; head and body faces never share a chart."""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    area = np.linalg.norm(fn, axis=1) / 2
    fn = fn / (np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12)
    edge_faces = {}
    for f, t in enumerate(F):
        for i in range(3):
            edge_faces.setdefault((min(t[i], t[(i + 1) % 3]), max(t[i], t[(i + 1) % 3])), []).append(f)
    nb = [[] for _ in F]
    for fs in edge_faces.values():
        for a in fs:
            nb[a] += [b for b in fs if b != a]
    chart = -np.ones(len(F), int)
    cos = np.cos(np.radians(limit))
    nc = 0
    for seed in np.argsort(-area):
        if chart[seed] >= 0:
            continue
        chart[seed] = nc
        acc = fn[seed] * area[seed]
        todo = [seed]
        while todo:
            f = todo.pop()
            for g in nb[f]:
                if chart[g] < 0 and head[g] == head[seed] and fn[g] @ (acc / np.linalg.norm(acc)) > cos \
                        and fn[g] @ fn[seed] > cos:
                    chart[g] = nc
                    acc = acc + fn[g] * area[g]
                    todo.append(g)
        nc += 1
    return chart, fn


def _mask(tri_uv, shape):
    """Texels covered by triangles (uv in texels, origin 0), grown by the gutter."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    for t in tri_uv:
        d.polygon([tuple(p) for p in t], fill=1, outline=1)
    m = np.asarray(im, bool)
    for _ in range(GUTTER):
        g = m.copy()
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        m = g
    return m


def _pack(V, F, chart, fn, density):
    """Per-corner UVs in texels (0..256): each chart projected on its mean normal's plane, scaled
    by its density, then placed texel-exact (bitmap first fit through FFT correlation, turned
    0 or 90 degrees), so irregular charts interlock; the scale is searched so all fit."""
    proj = {}
    for c in range(chart.max() + 1):
        fs = np.where(chart == c)[0]
        n = fn[fs].sum(0)
        n /= np.linalg.norm(n) + 1e-12
        e1 = np.cross(n, [0, 1, 0] if abs(n[1]) < 0.9 else [1, 0, 0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        pts = V[F[fs]]
        uv = np.stack([pts @ e1, -(pts @ e2)], -1) * density[fs][:, None, None]
        # the chart's long side along its first axis (PCA), for tidier packing
        flat = uv.reshape(-1, 2) - uv.reshape(-1, 2).mean(0)
        _, _, vt = np.linalg.svd(flat, full_matrices=False)
        uv = uv @ vt.T
        proj[c] = (fs, uv - uv.reshape(-1, 2).min(0))
    order = sorted(proj, key=lambda c: -np.ptp(proj[c][1][..., 0]) * np.ptp(proj[c][1][..., 1]))

    def place(s, final=False):
        occ = np.zeros((ATLAS, ATLAS), bool)
        spots = {}
        for c in order:
            fs, uv = proj[c]
            best = None
            for rot in (0, 1):
                u = uv * s
                if rot:
                    u = np.stack([u[..., 1], np.ptp(u[..., 0]) - u[..., 0]], -1)
                u = u + GUTTER
                h, w = int(np.ceil(u[..., 1].max())) + GUTTER + 1, int(np.ceil(u[..., 0].max())) + GUTTER + 1
                if h > ATLAS or w > ATLAS:
                    continue
                m = _mask(u, (h, w))
                # overlap count of the mask at every offset: correlation by FFT
                A = np.fft.rfft2(occ.astype(float), s=(ATLAS + h, ATLAS + w))
                B = np.fft.rfft2(m[::-1, ::-1].astype(float), s=(ATLAS + h, ATLAS + w))
                cor = np.fft.irfft2(A * B, s=(ATLAS + h, ATLAS + w))[h - 1:ATLAS, w - 1:ATLAS]
                free = np.argwhere(cor < 0.5)
                if not len(free):
                    continue
                y, x = free[np.lexsort((free[:, 1], free[:, 0]))[0]]
                if best is None or (y, x) < best[:2]:
                    best = (y, x, rot, u, m)
            if best is None:
                return None
            y, x, rot, u, m = best
            occ[y:y + m.shape[0], x:x + m.shape[1]] |= m
            spots[c] = (x, y, u)
        return spots
    # start from the scale that would fill 75 % of the page, then a short search around it
    area = sum(abs(np.cross(uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0])).sum() / 2 for _, uv in proj.values())
    s0 = np.sqrt(0.75 * ATLAS * ATLAS / max(area, 1e-12))
    lo, hi = s0 * 0.6, s0 * 1.5
    while place(lo) is None:
        lo, hi = lo * 0.8, lo
    for _ in range(6):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if place(mid) is not None else (lo, mid)
    spots = place(lo)
    UV = np.zeros((len(F), 3, 2))
    for c, (fs, _) in proj.items():
        x, y, u = spots[c]
        UV[fs] = u + np.array([x, y])
    return UV


def _raster(UV, fn_point, offset=(0.5, 0.5)):
    """Calls fn_point(face, texel_xy, barycentrics) for the texels each face covers (centres
    inside, grown by half a texel so chart edges are painted)."""
    for f, tri in enumerate(UV):
        a, b, c = tri
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) < 1e-9:
            continue
        x0, y0 = np.floor(tri.min(0) - 1).astype(int)
        x1, y1 = np.ceil(tri.max(0) + 1).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, ATLAS - 1) + 1), np.arange(max(y0, 0), min(y1, ATLAS - 1) + 1))
        px = np.stack([xs.ravel() + offset[0], ys.ravel() + offset[1]], 1)
        l1 = ((b[0] - px[:, 0]) * (c[1] - px[:, 1]) - (b[1] - px[:, 1]) * (c[0] - px[:, 0])) / cross
        l2 = ((c[0] - px[:, 0]) * (a[1] - px[:, 1]) - (c[1] - px[:, 1]) * (a[0] - px[:, 0])) / cross
        l3 = 1 - l1 - l2
        L = np.stack([l1, l2, l3], 1)
        grow = 0.75 / max(np.sqrt(abs(cross)), 1.0)
        ins = (L >= -grow).all(1)
        if ins.any():
            Lc = np.clip(L[ins], 0, None)
            fn_point(f, np.floor(px[ins]).astype(int), Lc / Lc.sum(1, keepdims=True))


def reduce(src: dict, target: int = 900, log=print) -> dict:
    import time
    t0 = time.time()
    lap = lambda what: log(f"  {what}: {time.time() - t0:.0f} s")
    from PIL import Image
    import model_import as MI
    P, T, UV, MAT = src["P"], src["T"], src["UV"], src["MAT"]
    Pw, weld = _weld(P)
    Tw = weld[T]
    H = float(np.ptp(Pw[:, 1]))
    textures = {k: np.asarray(Image.open(io.BytesIO(v)).convert("RGBA")) for k, v in src.get("textures", {}).items()}
    if not textures:
        textures = {0: np.full((4, 4, 4), 200, np.uint8)}
    # opaque triangles build the shell (hair-card edges and lashes are mostly transparent)
    c = UV[T].mean(1)
    samples = [c] + [UV[T[:, k]] * 0.6 + c * 0.4 for k in range(3)]
    alpha = np.mean([_texel(textures, MAT, s)[:, 3] for s in samples], 0) / 255
    opaque = alpha > 0.5
    # dangling cloth and props on bones Tekken has no row for (a sleeve flap on its own bone)
    # would stick out as shards: they stay out of the shell
    loose = _loose(src, T)
    if loose.any() and loose.mean() < 0.15:
        opaque &= ~loose
        log(f"{int(loose.sum())} triangles of loose cloth/props left out")
    if _SHELL.get("src") is not src:                  # the shell is the same for every target
        groups = _limb_groups(src, Tw, weld)[opaque]
        V, F = _shell(Pw, Tw[opaque], groups, cells=180)
        for _ in range(6):                            # Taubin: smooth without shrinking
            V = RM.smooth(V, F, 1, 0.5)
            V = RM.smooth(V, F, 1, -0.53)
        _SHELL.update(src=src, V=V, F=F)
    V, F = _SHELL["V"].copy(), _SHELL["F"]
    neck = MI.joint(src["bones"], "head") if src.get("bones") else None
    neck_y = neck[1] if neck is not None else Pw[:, 1].max() - 0.13 * H
    imp = np.where(V[:, 1] > neck_y, 4.0, 1.0)
    V, _, F, _ = DC.decimate(V, F, target, importance=imp, uniform=0.3)
    F = np.asarray(F)
    used = np.unique(F)
    # relax along the surface, then back onto the original
    S = RM.Sampler(Pw, Tw[opaque], H / 400)
    To = Tw[opaque]
    for _ in range(3):
        acc = np.zeros_like(V)
        cnt = np.zeros(len(V))
        for i, j in ((0, 1), (1, 2), (2, 0), (1, 0), (2, 1), (0, 2)):
            np.add.at(acc, F[:, i], V[F[:, j]])
            np.add.at(cnt, F[:, i], 1)
        n = _vertex_normals(V, F)
        d = acc / np.maximum(cnt, 1)[:, None] - V
        d -= (d * n).sum(1, keepdims=True) * n
        V[used] += 0.5 * d[used]
        hit = S.lookup(V[used])
        ok = hit[:, 0] >= 0
        tri = To[hit[ok, 0].astype(int)]
        u, v = hit[ok, 1:2], hit[ok, 2:3]
        V[used[ok]] = Pw[tri[:, 0]] * (1 - u - v) + Pw[tri[:, 1]] * u + Pw[tri[:, 2]] * v
    # compact
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    V, F = V[used], remap[F]
    lap("shell, collapse, relax")
    log(f"reduced to {len(F)} triangles (shell of the opaque surface, quadric collapse)")
    # skin weights from the nearest original point
    Ww = [dict() for _ in range(len(Pw))]
    for i, w in enumerate(src.get("weights", [])):
        if w:
            Ww[weld[i]] = w
    hit = S.lookup(V)
    weights = []
    for (t, u, v) in hit:
        if t < 0:
            weights.append({})
            continue
        acc = {}
        for vid, bw in zip(To[int(t)], (1 - u - v, u, v)):
            for b, w in Ww[vid].items():
                acc[b] = acc.get(b, 0) + w * bw
        tot = sum(acc.values()) or 1
        weights.append({b: w / tot for b, w in acc.items() if w / tot > 0.02})
    # texture atlas
    # the face (front of the head below the hair line) gets its own charts at 5x the texel density,
    # the rest of the head 2x: Namco gives the face most of the page
    cen = V[F].mean(1)
    fn0 = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn0 /= np.linalg.norm(fn0, axis=1, keepdims=True) + 1e-12
    top = V[:, 1].max()
    head = cen[:, 1] > neck_y
    face = head & (fn0[:, 2] > 0.3) & (cen[:, 1] < neck_y + 0.78 * (top - neck_y))
    kind = np.where(face, 2, np.where(head, 1, 0))
    chart, fn = _charts(V, F, kind)
    density = np.choose(kind, [1.0, 2.0, 5.0])
    UVl = _pack(V, F, chart, fn, density)
    lap("charts and packing")
    log(f"{chart.max() + 1} texture charts, face at 5x and head at 2x density")
    # bake: rays from outside inwards onto the full original (transparent texels let it through)
    # short rays (the shell lies on the original) and a fine grid: a ray's cell and its
    # neighbours cover it when the cell is over half its length
    caster_len = 0.03 * H
    caster = RM.Caster(Pw, Tw, caster_len * 0.55)
    Vn = _vertex_normals(V, F)
    pts, xys = [], []
    def collect(f, xy, bc):
        p = bc @ V[F[f]]
        n = bc @ Vn[F[f]]
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        pts.append(np.concatenate([p, n], 1))
        xys.append(xy)
    for off in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):   # 4 rays per texel
        _raster(UVl, collect, off)
    PN = np.concatenate(pts)
    XY = np.concatenate(xys)
    origin = PN[:, :3] + PN[:, 3:] * (caster_len / 2)
    dirs = -PN[:, 3:]
    col = np.zeros((len(PN), 3))
    done = np.zeros(len(PN), bool)
    start = origin.copy()
    for _ in range(6):                     # pass through transparent texels of hair cards
        todo = np.where(~done)[0]
        if not len(todo):
            break
        h = caster.first_hit(start[todo], dirs[todo], caster_len)
        got = h[:, 0] >= 0
        if not got.any():
            break
        idx = todo[got]
        tri = h[got, 0].astype(int)
        u, v = h[got, 1:2], h[got, 2:3]
        uv = UV[T[tri, 0]] * (1 - u - v) + UV[T[tri, 1]] * u + UV[T[tri, 2]] * v
        rgba = _texel(textures, MAT[tri], uv)
        solid = rgba[:, 3] > 128
        col[idx[solid]] = rgba[solid, :3]
        done[idx[solid]] = True
        start[idx[~solid]] = start[idx[~solid]] + dirs[idx[~solid]] * (h[got][~solid, 3:4] + 1e-4 * H)
    miss = np.where(~done)[0]
    if len(miss):                          # nothing opaque on the ray: the nearest surface point
        h = S.lookup(PN[miss, :3])
        ok = h[:, 0] >= 0
        tri = np.where(opaque)[0][h[ok, 0].astype(int)]
        u, v = h[ok, 1:2], h[ok, 2:3]
        uv = UV[T[tri, 0]] * (1 - u - v) + UV[T[tri, 1]] * u + UV[T[tri, 2]] * v
        col[miss[ok]] = _texel(textures, MAT[tri], uv)[:, :3]
    img = np.zeros((ATLAS, ATLAS, 3))
    cnt = np.zeros((ATLAS, ATLAS))
    np.add.at(img, (XY[:, 1], XY[:, 0]), col)
    np.add.at(cnt, (XY[:, 1], XY[:, 0]), 1)
    painted = cnt > 0
    img[painted] /= cnt[painted][:, None]
    for _ in range(GUTTER + 2):            # bleed into the gutter
        grow = np.zeros_like(img)
        n = np.zeros(cnt.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            grow += np.roll(np.roll(img * painted[..., None], dy, 0), dx, 1)
            n += np.roll(np.roll(painted, dy, 0), dx, 1)
        new = ~painted & (n > 0)
        img[new] = grow[new] / n[new][:, None]
        painted |= new
    buf = io.BytesIO()
    Image.fromarray(img.clip(0, 255).astype(np.uint8)).save(buf, "PNG")
    lap("bake")
    log(f"texture baked: {int(done.sum())} of {len(done)} samples hit the original directly")
    # per-corner model as direct_import.load returns it
    Pc = V[F.ravel()]
    Tc = np.arange(len(Pc)).reshape(-1, 3)
    W = [weights[v] for v in F.ravel()]
    out = {"P": Pc, "T": Tc, "UV": UVl.reshape(-1, 2) / ATLAS, "MAT": np.zeros(len(Tc), int),
           "textures": {0: buf.getvalue()}, "bones": src["bones"], "weights": W,
           "vbone": np.array([max(w, key=w.get) if w else -1 for w in W]), "reduced": True,
           "face_tris": np.where(face)[0].tolist()}
    return out
