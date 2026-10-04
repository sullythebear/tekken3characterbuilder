"""Mesh simplification by quadric edge collapse (Garland & Heckbert), numpy + heapq.

decimate(positions, triangles, target, keep=None) -> (vertex ids kept, new triangles, merged)
positions: (n, 3) float array; triangles: (m, 3) int array. Collapses the cheapest edge
until `target` triangles remain, never flipping a face. `merged[v]` is the kept vertex that v
was merged into (itself if kept). keep(a, b) -> bool may forbid a collapse."""
from __future__ import annotations
import heapq
import numpy as np


def _plane_quadrics(p, tris):
    a, b, c = p[tris[:, 0]], p[tris[:, 1]], p[tris[:, 2]]
    n = np.cross(b - a, c - a)
    area = np.linalg.norm(n, axis=1)
    n = n / np.maximum(area, 1e-12)[:, None]
    d = -np.einsum("ij,ij->i", n, a)
    plane = np.concatenate([n, d[:, None]], axis=1)          # (m, 4)
    K = np.einsum("ij,ik->ijk", plane, plane) * area[:, None, None]
    Q = np.zeros((len(p), 4, 4))
    for k in range(3):
        np.add.at(Q, tris[:, k], K)
    return Q


def _boundary_quadrics(p, tris, Q, weight=1000.0):
    """Edges used by one triangle (open borders, e.g. a sleeve opening) get a perpendicular
    plane so the outline keeps its shape."""
    edges = {}
    for t in tris:
        for i in range(3):
            e = (min(t[i], t[(i + 1) % 3]), max(t[i], t[(i + 1) % 3]))
            edges.setdefault(e, []).append(t)
    for (u, v), ts in edges.items():
        if len(ts) != 1:
            continue
        t = ts[0]
        a, b, c = p[t[0]], p[t[1]], p[t[2]]
        fn = np.cross(b - a, c - a)
        e = p[v] - p[u]
        n = np.cross(e, fn)
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n /= ln
        plane = np.append(n, -n @ p[u])
        K = np.outer(plane, plane) * weight * float(e @ e)
        Q[u] += K
        Q[v] += K


def decimate(positions, triangles, target: int, keep=None, importance=None, uniform=0.0, manifold=False):
    """uniform > 0 adds that much of the edge's squared length to its cost (relative to the
    mean quadric error), so short edges go first and triangles stay even (no slivers)."""
    p = np.array(positions, dtype=float).copy()
    tris = np.array(triangles, dtype=np.int64)
    Q = _plane_quadrics(p, tris)
    if importance is not None:          # per vertex: shape there costs more to lose
        Q *= np.asarray(importance, float)[:, None, None]
    _boundary_quadrics(p, tris, Q)
    faces = [list(t) for t in tris]
    alive = [True] * len(faces)
    vfaces = [set() for _ in range(len(p))]
    for f, t in enumerate(faces):
        for v in t:
            vfaces[v].add(f)
    parent = list(range(len(p)))
    version = [0] * len(p)
    # the uniform term's unit: quadric error per squared length, typical for this mesh
    tri_area = np.linalg.norm(np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]), axis=1)
    # (plane quadrics are area weighted: an error is distance^2 x area)
    scale = float(np.mean(tri_area)) / 2

    def costs(A_, B_):
        """Batched: best collapse position and its error for edges (A_[i], B_[i])."""
        q = Q[A_] + Q[B_]
        M = q.copy()
        M[:, 3] = [0, 0, 0, 1]
        pa, pb = p[A_], p[B_]
        mid = (pa + pb) / 2
        span = np.linalg.norm(pa - pb, axis=1)
        cands = [pa, pb, mid]
        det = np.linalg.det(M)
        ok = np.abs(det) > 1e-12
        opt = mid.copy()
        if ok.any():
            opt[ok] = np.linalg.solve(M[ok], np.tile([0, 0, 0, 1.0], (ok.sum(), 1))[..., None])[:, :3, 0]
        # stay near the edge: an optimum far away (flat areas) pulls spikes
        ok &= np.linalg.norm(opt - mid, axis=1) <= span
        opt[~ok] = mid[~ok]
        cands.append(opt)
        errs = []
        for x in cands:
            h = np.concatenate([x, np.ones((len(x), 1))], 1)
            errs.append(np.einsum("ni,nij,nj->n", h, q, h))
        errs = np.stack(errs, 1)
        k = np.argmin(errs, 1)
        pos = np.stack(cands, 1)[np.arange(len(k)), k]
        e = errs[np.arange(len(k)), k]
        if uniform:
            e = e + uniform * scale * span ** 2
        return e, pos

    heap = []

    def push_many(pairs):
        pairs = [(min(a, b), max(a, b)) for a, b in pairs]
        if keep is not None:
            pairs = [e for e in pairs if keep(*e)]
        if not pairs:
            return
        A_, B_ = np.array(pairs).T
        err, pos = costs(A_, B_)
        for (a, b), e, x in zip(pairs, err.tolist(), pos.tolist()):
            heapq.heappush(heap, (e, a, b, version[a], version[b], x))

    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    edges = np.unique(edges, axis=0)
    push_many([tuple(e) for e in edges.tolist()])

    count = len(faces)

    def flips(v, other, x):
        """Would moving v to x flip (or degenerate) a face of v that survives the collapse?"""
        for f in vfaces[v]:
            t = faces[f]
            if other in t:
                continue
            i = t.index(v)
            a, b, c = (p[t[0]], p[t[1]], p[t[2]])
            n0 = np.cross(b - a, c - a)
            q = [p[t[0]], p[t[1]], p[t[2]]]
            q[i] = x
            n1 = np.cross(q[1] - q[0], q[2] - q[0])
            l0 = np.linalg.norm(n0)
            if l0 < 1e-12:                   # already degenerate: anything is an improvement
                continue
            if n0 @ n1 <= 0.2 * l0 * np.linalg.norm(n1):
                return True
        return False

    while count > target and heap:
        e, a, b, va, vb, x = heapq.heappop(heap)
        if parent[a] != a or parent[b] != b or version[a] != va or version[b] != vb:
            continue
        x = np.array(x)
        if flips(a, b, x) or flips(b, a, x):
            continue
        if manifold:
            # link condition: a and b may share only the vertices opposite their common edge,
            # or the collapse glues two sheets together (edges with 3+ faces, inside-out faces)
            na = {v for f in vfaces[a] for v in faces[f]} - {a}
            nb = {v for f in vfaces[b] for v in faces[f]} - {b}
            edge = [f for f in vfaces[a] if b in faces[f]]
            if len(na & nb) != len(edge) or not edge or len(na | nb) <= 3:
                continue
        # collapse b into a
        p[a] = x
        Q[a] = Q[a] + Q[b]
        parent[b] = a
        for f in list(vfaces[b]):
            t = faces[f]
            if a in t:
                alive[f] = False
                count -= 1
                for v in t:
                    if v != b:
                        vfaces[v].discard(f)
            else:
                t[t.index(b)] = a
                vfaces[a].add(f)
        vfaces[b] = set()
        version[a] += 1
        nbrs = {v for f in vfaces[a] for v in faces[f] if v != a}
        push_many([(a, n) for n in nbrs])

    def root(v):
        while parent[v] != v:
            v = parent[v]
        return v

    out = np.array([faces[f] for f in range(len(faces)) if alive[f]], dtype=np.int64)
    used = sorted(set(out.ravel().tolist()))
    merged = [root(v) for v in range(len(p))]
    return p, used, out, merged
