"""One closed skin around a messy character mesh (overlapping clothes, hair cards, loose
pieces), numpy only: voxelise the surface, fill the inside, extract a surface-nets mesh, smooth
it and pull it back onto the original surface. The result is manifold, so edge-collapse
simplification works well on it.

remesh(positions, triangles, cells) -> dict(positions, triangles, source) where source[i] is
(original triangle, barycentric u, v) of the original surface point nearest to vertex i."""
from __future__ import annotations
import numpy as np


def surface_samples(p, t, h):
    """Points on every triangle no further than h / 2 apart: (points, triangle, u, v)."""
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    longest = np.max([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], axis=0)
    ks = np.maximum(1, np.ceil(longest / (0.5 * h)).astype(int))
    pts, tri, us, vs = [], [], [], []
    for k in np.unique(ks):
        sel = np.where(ks == k)[0]
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = i + j <= k
        u, v = (i[keep] / k), (j[keep] / k)
        w = 1 - u - v
        P = a[sel, None, :] * w[None, :, None] + b[sel, None, :] * u[None, :, None] + c[sel, None, :] * v[None, :, None]
        pts.append(P.reshape(-1, 3))
        tri.append(np.repeat(sel, len(u)))
        us.append(np.tile(u, len(sel)))
        vs.append(np.tile(v, len(sel)))
    return np.concatenate(pts), np.concatenate(tri), np.concatenate(us), np.concatenate(vs)


def _shift(a, axis, step):
    out = np.zeros_like(a)
    src = [slice(None)] * 3
    dst = [slice(None)] * 3
    if step > 0:
        src[axis], dst[axis] = slice(0, -step), slice(step, None)
    else:
        src[axis], dst[axis] = slice(-step, None), slice(0, step)
    out[tuple(dst)] = a[tuple(src)]
    return out


def _dilate(a):
    out = a.copy()
    for ax in range(3):
        out |= _shift(a, ax, 1) | _shift(a, ax, -1)
    return out


def _erode(a):
    out = a.copy()
    for ax in range(3):
        out &= _shift(a, ax, 1) & _shift(a, ax, -1)
    return out


def solid(samples, origin, h, shape, close: int = 1):
    """Voxels inside the surface: every voxel the outside cannot reach. The surface is first
    thickened by `close` voxels so small holes (a collar, a sleeve) do not let the outside in."""
    idx = np.floor((samples - origin) / h).astype(int)
    surf = np.zeros(shape, dtype=bool)
    surf[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    wall = surf
    for _ in range(close):
        wall = _dilate(wall)
    out = np.zeros(shape, dtype=bool)
    for ax in range(3):
        for end in (0, -1):
            s = [slice(None)] * 3
            s[ax] = end
            out[tuple(s)] = True
    out &= ~wall
    while True:
        grown = _dilate(out) & ~wall
        if (grown == out).all():
            break
        out = grown
    inside = ~out
    for _ in range(close):
        inside = _erode(inside)
    return inside | surf


def surface_nets(inside, origin, h):
    """Quads between inside and outside voxels -> (vertices, triangles). One vertex per dual
    cell (the cube between 8 voxel centres) that the surface crosses."""
    nx, ny, nz = inside.shape
    vid = -np.ones((nx - 1, ny - 1, nz - 1), dtype=np.int64)
    s = inside.astype(np.int8)
    corners = sum(s[dx:nx - 1 + dx, dy:ny - 1 + dy, dz:nz - 1 + dz] for dx in (0, 1) for dy in (0, 1) for dz in (0, 1))
    cells = np.argwhere((corners > 0) & (corners < 8))
    vid[cells[:, 0], cells[:, 1], cells[:, 2]] = np.arange(len(cells))
    verts = origin + (cells + 1.0) * h            # centre of the dual cell (voxel centres at +0.5)
    quads = []
    for ax in range(3):
        a1, a2 = [x for x in range(3) if x != ax]
        lo = [slice(0, -1) if k == ax else slice(None) for k in range(3)]
        hi = [slice(1, None) if k == ax else slice(None) for k in range(3)]
        A, B = inside[tuple(lo)], inside[tuple(hi)]
        for flip, mask in ((False, A & ~B), (True, ~A & B)):
            e = np.argwhere(mask)
            # the 4 dual cells around this edge: offsets -1/0 on the other two axes
            e = e[(e[:, a1] >= 1) & (e[:, a2] >= 1) & (e[:, a1] <= inside.shape[a1] - 1) & (e[:, a2] <= inside.shape[a2] - 1)]
            q = []
            for d1, d2 in ((-1, -1), (0, -1), (0, 0), (-1, 0)):
                c = e.copy()
                c[:, a1] += d1
                c[:, a2] += d2
                ok = (c >= 0).all(1) & (c[:, 0] < nx - 1) & (c[:, 1] < ny - 1) & (c[:, 2] < nz - 1)
                cc = np.where(ok[:, None], c, 0)
                q.append(np.where(ok, vid[cc[:, 0], cc[:, 1], cc[:, 2]], -1))
            q = np.stack(q, 1)
            q = q[(q >= 0).all(1)]
            if (ax == 1) ^ flip:
                q = q[:, ::-1]
            quads.append(q)
    quads = np.concatenate(quads)
    tris = np.concatenate([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]])
    return verts, tris


def smooth(v, tris, rounds=4, lam=0.5):
    n = len(v)
    for _ in range(rounds):
        acc = np.zeros_like(v)
        cnt = np.zeros(n)
        for i, j in ((0, 1), (1, 2), (2, 0), (1, 0), (2, 1), (0, 2)):
            np.add.at(acc, tris[:, i], v[tris[:, j]])
            np.add.at(cnt, tris[:, i], 1)
        v = v + lam * (acc / np.maximum(cnt, 1)[:, None] - v)
    return v


def snap(v, samples, origin, h, shape, reach=2):
    """Index of the nearest surface sample to each vertex (searching `reach` voxels around)."""
    # Two representatives per voxel (the samples nearest to and farthest from its centre are
    # cheap to keep apart: first and last writer after sorting by distance).
    idx = np.floor((samples - origin) / h).astype(int)
    centre = origin + (idx + 0.5) * h
    dc = np.einsum("ij,ij->i", samples - centre, samples - centre)
    reps = []
    for order in (np.argsort(-dc), np.argsort(dc)):
        rep = -np.ones(shape, dtype=np.int64)
        rep[idx[order, 0], idx[order, 1], idx[order, 2]] = order     # the last write wins
        reps.append(rep)
    vi = np.floor((v - origin) / h).astype(int)
    best = np.full(len(v), -1)
    bestd = np.full(len(v), np.inf)
    r = range(-reach, reach + 1)
    for dx in r:
        for dy in r:
            for dz in r:
                c = vi + [dx, dy, dz]
                ok = (c >= 0).all(1) & (c[:, 0] < shape[0]) & (c[:, 1] < shape[1]) & (c[:, 2] < shape[2])
                c = np.where(ok[:, None], c, 0)
                for rep in reps:
                    s = np.where(ok, rep[c[:, 0], c[:, 1], c[:, 2]], -1)
                    d = np.where(s >= 0, np.einsum("ij,ij->i", samples[s] - v, samples[s] - v), np.inf)
                    better = d < bestd
                    best[better], bestd[better] = s[better], d[better]
    return best


def remesh(positions, triangles, cells: int = 220, close: int = 1):
    p = np.asarray(positions, dtype=float).reshape(-1, 3)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    lo, hi = p.min(0), p.max(0)
    h = float((hi - lo).max()) / cells
    origin = lo - 3 * h
    shape = tuple(np.ceil((hi - lo) / h).astype(int) + 6)
    samples, tri, us, vs = surface_samples(p, t, h)
    inside = solid(samples, origin, h, shape, close)
    v, f = surface_nets(inside, origin, h)
    v = smooth(v, f, rounds=3)
    near = snap(v, samples, origin, h, shape)
    has = near >= 0
    v[has] = samples[near[has]]
    v = smooth(v, f, rounds=1, lam=0.3)
    near = snap(v, samples, origin, h, shape)
    v[near >= 0] = samples[near[near >= 0]]
    src = np.stack([np.where(near >= 0, tri[near], -1), us[near], vs[near]], 1)
    return {"positions": v, "triangles": f, "source": src, "cell": h}
