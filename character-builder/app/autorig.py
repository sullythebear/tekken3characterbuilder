"""Automatic rig for a humanoid model without a skeleton (numpy only).

The model becomes a solid of voxels. Inside it:
1. depth: how far each voxel lies from the skin;
2. from the middle of the torso, the cheapest way to every voxel, where deep voxels cost less,
   so the ways run along the middle of the limbs;
3. the ends of the body (the voxels farthest from the torso): head, hands, feet;
4. the way from each end back to the torso: the legs part at the crotch, the arms and the
   head at the shoulders;
5. the joints along those ways, in human proportions;
6. every vertex's body part: the bone nearest to it through the body (not through the air), so
   an arm resting on the hip stays an arm.

auto_rig(P, T) -> (joints {name: point}, part per vertex) as direct_import.rig_from_skeleton.
Axes: Y up, facing +Z, the character's left at +X (direct_import turns models that way first).
Raises RigError with a reason a player can act on when the shape is not a standing humanoid.
"""
from __future__ import annotations
import numpy as np

import remesh

CELLS = 80                     # voxels over the model's height
# proportions along the arm (shoulder .. fingertip) and the head joint's height between the
# shoulders and the top of the head, fitted on 22 rigged models (tools: scratch bench_rig.py)
ELBOW, WRIST, NECK = 0.36, 0.70, 0.15
SHOULDER, DEPTH_K, RAISE = "depth", 1.55, 0.032
CHIBI_SHOULDERS = 0.58             # shoulders under this share of the height: a chibi (41-57 %; others 59 % and up)
ARM_LINE = 0.02                    # shoulder this far (share of the height) above the arm's line: put on it
TORSO_MIN = 0.12                   # shoulders at least this share of the height above the hip joints
ARMS_WIDER = 1.3                   # upper body this much wider than deep: the arms are spread, side to side
BEND = 35                          # degrees: where the arm's way turns into the torso (the shoulder)
NECK_SPLIT = (0.35, 0.15)          # spine ends / head starts this share of shoulder..head below it
HEAD_LIFT, HEAD_WIDTH = 0.03, 0.5  # all above the head joint + lift, within this share of the shoulders: head

# offsets of the 26 neighbours and their lengths
OFFS = np.array([(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                 if (dx, dy, dz) != (0, 0, 0)])
LENS = np.linalg.norm(OFFS, axis=1)


class RigError(ValueError):
    pass


def _shift(a, d, fill):
    """a moved by offset d (out[x] = a[x - d]); cells moved in from outside get `fill`."""
    out = np.full_like(a, fill)
    src, dst = [], []
    for k in range(3):
        if d[k] > 0:
            src.append(slice(0, -d[k]))
            dst.append(slice(d[k], None))
        elif d[k] < 0:
            src.append(slice(-d[k], None))
            dst.append(slice(0, d[k]))
        else:
            src.append(slice(None))
            dst.append(slice(None))
    out[tuple(dst)] = a[tuple(src)]
    return out


def voxels(P, T):
    """-> (solid bool grid, origin, voxel size)."""
    lo, hi = P.min(0), P.max(0)
    h = max(float(hi[1] - lo[1]) / CELLS, float((hi - lo).max()) / (2 * CELLS))   # never a huge grid
    origin = lo - 2.5 * h
    shape = tuple(int(x) for x in np.ceil((hi - origin) / h) + 3)
    pts, _, _, _ = remesh.surface_samples(P, T, h)
    return remesh.solid(pts, origin, h, shape, close=1), origin, h


def depth(solid):
    """Layers of erosion each voxel survives (6-neighbour): its distance to the skin in voxels."""
    d = np.zeros(solid.shape, np.float32)
    cur = solid.copy()
    n = 0
    while cur.any():
        n += 1
        d[cur] = n
        nxt = cur.copy()
        for ax in range(3):
            for s in (1, -1):
                nxt &= _shift(cur, np.eye(3, dtype=int)[ax] * s, False)
        cur = nxt
    return d


def _slices(d):
    """(destination, source) slices moving a grid by offset d."""
    dst, src = [], []
    for k in d:
        if k > 0:
            dst.append(slice(k, None)); src.append(slice(0, -k))
        elif k < 0:
            dst.append(slice(0, k)); src.append(slice(-k, None))
        else:
            dst.append(slice(None)); src.append(slice(None))
    return tuple(dst), tuple(src)


SLICES = [_slices(d) for d in OFFS]


def geodesic(solid, seeds, cost):
    """Cheapest way from the seeds to every solid voxel, a step costing its length times the
    cost of the voxel it enters (relaxation over the 26 neighbours until nothing changes)."""
    D = np.full(solid.shape, np.inf, np.float32)
    D[seeds] = 0
    w = np.where(solid, cost, np.inf).astype(np.float32)
    tmp = {}
    for _ in range(4 * max(solid.shape)):
        changed = False
        for (dst, src), l in zip(SLICES, LENS):
            wd = w[dst]
            buf = tmp.get(wd.shape)
            if buf is None:
                buf = tmp[wd.shape] = np.empty(wd.shape, np.float32)
            np.multiply(wd, np.float32(l), out=buf)      # one buffer per shape: little memory
            np.add(buf, D[src], out=buf)
            view = D[dst]
            better = buf < view
            if better.any():
                np.minimum(view, buf, out=view)     # in place: later offsets see new values
                changed = True
        if not changed:
            break
    return D


def _descend(D, start, solid):
    """The way from `start` down D to a seed: voxel indices, start first."""
    path = [tuple(start)]
    cur = np.array(start)
    shape = np.array(D.shape)
    for _ in range(int(D.size)):
        if D[tuple(cur)] == 0:
            break
        nb = cur + OFFS
        ok = ((nb >= 0) & (nb < shape)).all(1)
        nb = nb[ok]
        vals = D[nb[:, 0], nb[:, 1], nb[:, 2]]
        k = int(np.argmin(vals))
        if vals[k] >= D[tuple(cur)]:
            break
        cur = nb[k]
        path.append(tuple(cur))
    return np.array(path)


def _ends(Du, solid, h, count=24):
    """Voxels farther (by Du) than all their neighbours within a radius: the body's ends."""
    finite = np.where(np.isfinite(Du), Du, -1)
    r = 3
    local = finite.copy()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            for dz in range(-r, r + 1):
                if dx or dy or dz:
                    np.maximum(local, _shift(finite, np.array([dx, dy, dz]), -1), out=local)
    peaks = np.argwhere((finite >= local) & (finite > 0.15 * finite.max()))
    peaks = peaks[np.argsort(-finite[tuple(peaks.T)])]
    chosen = []
    for p in peaks:                                   # one per end: well apart from the others
        if all(np.linalg.norm(p - q) > 6 for q in chosen):
            chosen.append(p)
        if len(chosen) >= count:
            break
    return chosen


def auto_rig(P, T):
    P = np.asarray(P, float)
    solid, origin, h = voxels(P, T)
    H = float(np.ptp(P[:, 1]))
    sole = float(P[:, 1].min())
    world = lambda v: origin + (np.asarray(v, float) + 0.5) * h
    ycell = lambda frac: int((sole + frac * H - origin[1]) / h)
    dep = depth(solid)
    # the torso's middle: the deepest voxel between 40 % and 75 % of the height, near the centre
    band = np.zeros(solid.shape, bool)
    band[:, ycell(0.4):ycell(0.75), :] = True
    xs = (np.arange(solid.shape[0]) + 0.5) * h + origin[0]
    band &= (np.abs(xs) < 0.15 * H)[:, None, None]
    cand = np.where(band & solid, dep, 0)
    if cand.max() <= 0:
        raise RigError("No body found around the middle of the model: is it a standing character, upright (Y up)?")
    root = np.unravel_index(int(np.argmax(cand)), cand.shape)
    seeds = np.zeros(solid.shape, bool)
    seeds[root] = True
    Du = geodesic(solid, seeds, np.ones(solid.shape, np.float32))            # plain distance: ends
    Dw = geodesic(solid, seeds, 1.0 / (1.0 + dep) ** 1.5)                     # through the middle
    ends = _ends(Du, solid, h)
    E = [(e, world(e)) for e in ends]
    # feet: the two lowest ends, one each side
    low = sorted(E, key=lambda e: e[1][1])
    feet = [e for e in low if e[1][1] < sole + 0.2 * H]
    footL = next((e for e in feet if e[1][0] > 0), None)
    footR = next((e for e in feet if e[1][0] < 0), None)
    if footL is None or footR is None:               # legs joined (a dress, a robe): the lowest
        for s in (1, -1):                            # vertices each side, their most forward one
            sel = P[(s * P[:, 0] > 0.02 * H) & (P[:, 1] < sole + 0.04 * H)]
            if not len(sel):
                raise RigError("Two feet were not found at the bottom: is the model a standing character, upright (Y up)?")
            toe = sel[np.argmax(sel[:, 2])]
            v = _nearest_solid(solid, origin, h, toe)
            e = (v, toe)
            if s == 1:
                footL = e
            else:
                footR = e
    rest = [e for e in E if e is not footL and e is not footR and e[1][1] > sole + 0.25 * H]
    # hands: the most mirror-like pair of ends to each side; ends far behind the body are wings,
    # capes or tails, ends far out of line with the other side a prop
    zc = world(root)[2]
    behind = lambda e: max(0.0, zc - e[1][2] - 0.08 * H) / H
    pairs = [(abs(l[1][0] + r[1][0]) / H + abs(l[1][1] - r[1][1]) / H + abs(l[1][2] - r[1][2]) / H
              + 3 * (behind(l) + behind(r)) - 0.15 * (l[1][0] - r[1][0]) / H, i, j)
             for i, l in enumerate(rest) if l[1][0] > 0.12 * H
             for j, r in enumerate(rest) if r[1][0] < -0.12 * H]
    handL = handR = None
    if pairs:
        _, i, j = min(pairs)
        handL, handR = rest[i], rest[j]
    if handL is None or handR is None:
        raise RigError("The hands were not found: the arms should stand away from the body (T-pose or A-pose).")
    head = max((e for e in rest if abs(e[1][0]) < 0.12 * H and e is not handL and e is not handR),
               key=lambda e: e[1][1], default=None)
    top_y = float(P[:, 1].max())
    if head is None or head[1][1] < sole + 0.75 * H:
        head = (None, np.array([0.0, top_y, P[P[:, 1] > top_y - 0.05 * H][:, 2].mean()]))
    paths = {k: _descend(Dw, e[0], solid) for k, e in (("handL", handL), ("handR", handR),
                                                         ("footL", footL), ("footR", footR))}
    paths = {k: np.array([world(v) for v in p]) for k, p in paths.items()}
    J = {}
    J.update(_arms(paths, P, H, dep, origin, h))
    shoulders = (J["upperL"][1] + J["upperR"][1]) / 2
    J.update(_legs(paths, sole, H, chibi=shoulders < sole + CHIBI_SHOULDERS * H, solid=(solid, origin, h)))
    if shoulders - J["thighL"][1] < TORSO_MIN * H or shoulders - J["thighR"][1] < TORSO_MIN * H:
        # the shoulders came out level with the hips: a hand hanging against the body (a flared
        # skirt, a hip) joins it in voxels, and the way from the hand runs straight in to the
        # torso's middle at the hips (the elf: shoulders at 62 %, hips at 63 % of the height).
        # Traced to the top of the head instead, the way along the arm (arm + neck) is shorter
        # than in at the hip and up the whole torso, for hanging and spread arms alike
        # The voxels cannot tell an arm hanging against a flared skirt from the skirt; the mesh
        # can: a sleeve's surface meets the body only at the shoulder. So the way is traced over
        # the surface (pieces that touch - a hand in its sleeve - joined where they touch)
        graph = _surface_graph(P, T, H)
        up = _surface_ways(graph, {k: e[1] for k, e in (("handL", handL), ("handR", handR))}, head[1])
        again = _surface_arms(up, graph, H) if up else None
        if again is None:
            again = {"upperL": J["upperL"], "upperR": J["upperR"]}
        if (again["upperL"][1] + again["upperR"][1]) / 2 - max(J["thighL"][1], J["thighR"][1]) >= TORSO_MIN * H:
            J.update(again)
            shoulders = (J["upperL"][1] + J["upperR"][1]) / 2
    J.update(_centre(J, P, H, head[1], top_y))
    J["handendL"], J["handendR"] = handL[1], handR[1]
    for s in "LR":
        J["collar" + s] = J["upper" + s] + 0.65 * (np.array([J["neck"][0], J["upper" + s][1], J["upper" + s][2]]) - J["upper" + s])
    used = [footL, footR, handL, handR] + ([head] if head[0] is not None else [])
    extra = _branches(E, used, Dw, solid, world, J, P, H)
    part = segment(P, solid, origin, h, J, extra)
    return J, part


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0, 1)
    return float(np.linalg.norm(p - (a + t * ab)))


def _branches(E, used, Dw, solid, world, J, P, H):
    """[(part, polyline)]: the body's other ends (tails, ears, wings, a ponytail) followed back to
    where they join the body; each takes the part of the bone it joins (a tail on the hips the
    pelvis, not a leg), so it moves stiffly with that part."""
    main = _bones(J, P)
    out = []
    for e in E:
        if any(e is u for u in used) or min(np.linalg.norm(e[1] - u[1]) for u in used) < 0.15 * H:
            continue
        path = np.array([world(v) for v in _descend(Dw, e[0], solid)])        # end .. torso
        near = [min(((_seg_dist(p, a, b), prt) for prt, a, b in main), key=lambda x: x[0]) for p in path]
        k = next((i for i, (d, _) in enumerate(near) if d < 0.08 * H), None)
        if k is None or k < 3:
            continue
        prt = near[k][1]
        if prt[0] in ("thigh", "shin", "foot"):      # a tail starts at the hips, not on a leg
            prt = ("pelvis", None)
        out.append((prt, path[:k + 1]))
    return out


def _nearest_solid(solid, origin, h, p):
    idx = np.argwhere(solid)
    c = origin + (idx + 0.5) * h
    return idx[int(np.argmin(np.linalg.norm(c - p, axis=1)))]


def _split(a, b):
    """Index where two ways from their ends to the same root stop running apart (from the root
    side: the first voxel they no longer share)."""
    ra, rb = a[::-1], b[::-1]
    n = 0
    while n < min(len(ra), len(rb)) and np.linalg.norm(ra[n] - rb[n]) < 1e-6:
        n += 1
    return len(a) - n, len(b) - n


def _at_length(path, length):
    """The point `length` along a polyline from its first point."""
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    if length >= cum[-1]:
        return path[-1]
    i = int(np.searchsorted(cum, length) - 1)
    t = (length - cum[i]) / max(seg[i], 1e-9)
    return path[i] + t * (path[i + 1] - path[i])


def _length(path):
    return float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())


def _joined(solid, origin, h, a, b):
    """Whether points a and b lie in one piece of the solid's horizontal slice through a."""
    va = np.floor((a - origin) / h).astype(int)
    vb = np.floor((b - origin) / h).astype(int)
    if not ((va >= 0).all() and (va < solid.shape).all() and (vb >= 0).all() and (vb < solid.shape).all()):
        return False
    sl = solid[:, va[1], :]
    if not sl[va[0], va[2]] or not sl[vb[0], vb[2]]:
        return False
    seen = np.zeros_like(sl)
    seen[va[0], va[2]] = True
    stack = [(va[0], va[2])]
    while stack:
        x, z = stack.pop()
        if (x, z) == (vb[0], vb[2]):
            return True
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, z + dz)
            if 0 <= q[0] < sl.shape[0] and 0 <= q[1] < sl.shape[1] and sl[q] and not seen[q]:
                seen[q] = True
                stack.append(q)
    return False


def _crotch(paths, solid, origin, h, sole, H):
    """The lowest height at which the two legs' ways lie in one piece of the solid's slice: where
    the legs join (a wide torso lets the ways run apart far above it)."""
    L, R = paths["footL"], paths["footR"]
    for y in np.arange(sole + 0.08 * H, sole + 0.7 * H, h):
        pa, pb = L[np.argmin(np.abs(L[:, 1] - y))], R[np.argmin(np.abs(R[:, 1] - y))]
        if abs(pa[1] - y) > h or abs(pb[1] - y) > h:
            continue
        a = np.array([pa[0], y, pa[2]])
        b = np.array([pb[0], y, pb[2]])
        if _joined(solid, origin, h, a, b):
            return float(y)
    return None


def _legs(paths, sole, H, chibi=False, solid=None):
    """Hip sockets, knees, ankles and toes along the legs' ways (foot end first)."""
    iL, iR = _split(paths["footL"], paths["footR"])
    joined = _crotch(paths, *solid, sole, H) if solid is not None and chibi else None    # wide, short torsos only
    J = {}
    for s, i in (("L", iL), ("R", iR)):
        leg = paths["foot" + s][:i + 1]              # toe .. crotch
        J["toe" + s] = leg[0]
        crotch_y = leg[-1][1]
        if joined is not None and joined < crotch_y:
            crotch_y = (crotch_y + joined) / 2        # a chibi: the ways part too high, the slices join
                                                      # too low (feet close, a robe); halfway fits best
        if crotch_y < sole + 0.25 * H and not chibi:  # legs touching far down (knees together under a
            crotch_y = sole + 0.46 * H                # dress): a human crotch. Higher up short legs are
                                                      # real (a chibi, a big helmet)
        # ankle: on the leg's upright part, at a human ankle's height
        up = np.where(leg[:, 1] > sole + 0.09 * H)[0]
        a = int(up[0]) if len(up) else 0
        ankle = leg[a].copy()
        ankle[1] = sole + 0.05 * H
        # hip socket: above the split, where the thigh's middle line is
        below = leg[(leg[:, 1] < crotch_y - 0.06 * H) & (leg[:, 1] > crotch_y - 0.12 * H)]
        mid = below.mean(0) if len(below) else ankle
        hip = np.array([mid[0], crotch_y + 0.02 * H, mid[2]])
        J["foot" + s] = ankle
        J["thigh" + s] = hip
        J["shin" + s] = hip + 0.52 * (ankle - hip)
    return J


def _surface_arms(ways, graph, H, slab=0.012, reach=0.12):
    """Shoulders, elbows and wrists along ways over the surface (_surface_ways, hand first). Walking
    in from the hand, a cut across the way stays as thin as the arm; where it widens to twice the
    arm's (the torso), the arm has ended: the shoulder, in the middle of the last thin cut. A cut
    holds only what lies within `reach` of the height over the surface: an arm hanging against
    the body or a skirt does not take them in (they join it only at the shoulder)."""
    import heapq
    V, nb = graph
    near_cache = {}

    def near(i0):                                       # surface distance from vertex i0, up to reach
        if i0 in near_cache:
            return near_cache[i0]
        dist = {i0: 0.0}
        heap = [(0.0, i0)]
        while heap:
            d, i = heapq.heappop(heap)
            if d > dist.get(i, np.inf):
                continue
            for j, w in nb[i].items():
                if d + w < dist.get(j, np.inf) and d + w <= reach * H:
                    dist[j] = d + w
                    heapq.heappush(heap, (d + w, j))
        near_cache[i0] = np.fromiter(dist.keys(), int)
        return near_cache[i0]
    J = {}
    for s in "LR":
        way = ways["hand" + s]
        cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(way, axis=0), axis=1))])
        if cum[-1] <= 0:
            return None
        cen, rad = [], []
        for i in range(len(way)):
            a, b = way[max(0, i - 3)], way[min(len(way) - 1, i + 3)]
            u = b - a
            u = u / max(np.linalg.norm(u), 1e-9)
            ids = near(int(np.argmin(np.linalg.norm(V - way[i], axis=1))))
            d = V[ids] - way[i]
            along = d @ u
            cut = V[ids][np.abs(along) < slab * H]
            if len(cut) < 4:
                cen.append(way[i]); rad.append(np.nan)
                continue
            c = (cut.min(0) + cut.max(0)) / 2
            cen.append(c)
            dc = cut - c
            rad.append(float(np.percentile(np.linalg.norm(dc - np.outer(dc @ u, u), axis=1), 90)))
        rad = np.array(rad)
        first = np.searchsorted(cum, 0.15 * cum[-1]), np.searchsorted(cum, 0.4 * cum[-1])
        arm_r = np.nanmedian(rad[first[0]:first[1] + 1])
        k = None
        for i in range(first[1], len(way)):
            if np.isfinite(rad[i]) and rad[i] > 2.0 * arm_r:
                k = max(i - 1, 0)
                break
        if k is None or not np.isfinite(arm_r):
            return None
        shoulder = np.array(cen[k], float)
        shoulder[1] += RAISE * H
        tail = np.array(cen[:k + 1][::-1])                 # shoulder .. hand, through the arm's middle
        tail[0] = shoulder
        L = _length(tail[::-1]) + np.linalg.norm(way[0] - tail[-1])
        J["upper" + s] = shoulder
        J["fore" + s] = _at_length(tail, ELBOW * L)
        J["hand" + s] = _at_length(tail, WRIST * L)
    return J


def _surface_graph(P, T, H, touch=0.01):
    """The mesh's surface as a graph: welded vertices V and per vertex {neighbour: length}, along
    the edges and between separate pieces where they come within `touch` of the height of each
    other (a hand in its sleeve)."""
    key = {}
    weld = np.array([key.setdefault(tuple(np.round(p, 5)), len(key)) for p in P])
    V = np.zeros((len(key), 3))
    V[weld] = P
    Tw = weld[np.asarray(T)]
    nb = [dict() for _ in range(len(V))]
    for a, b in np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]):
        if a != b:
            d = float(np.linalg.norm(V[a] - V[b]))
            nb[a][b] = nb[b][a] = d
    # touching pieces: a grid of cells `touch * H` wide; pairs of different pieces within it
    par = list(range(len(V)))
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for t in Tw:
        for b in t[1:]:
            ra, rb = find(t[0]), find(b)
            if ra != rb:
                par[rb] = ra
    piece = np.array([find(i) for i in range(len(V))])
    eps = touch * H
    cell = np.floor(V / eps).astype(int)
    grid = {}
    for i, c in enumerate(map(tuple, cell)):
        grid.setdefault(c, []).append(i)
    for (cx, cy, cz), ids in grid.items():
        near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                for j in grid.get((cx + dx, cy + dy, cz + dz), ())]
        for i in ids:
            for j in near:
                if j > i and piece[i] != piece[j]:
                    d = float(np.linalg.norm(V[i] - V[j]))
                    if d < eps:
                        nb[i][j] = nb[j][i] = d
    return V, nb


def _surface_ways(graph, ends, goal):
    """The shortest ways over the surface (_surface_graph) from each end point to the goal (the
    top of the head). {name: points from the end to the goal}, {} when a way is missing."""
    import heapq
    V, nb = graph
    start = int(np.argmin(np.linalg.norm(V - goal, axis=1)))
    dist = np.full(len(V), np.inf)
    prev = -np.ones(len(V), int)
    dist[start] = 0.0
    heap = [(0.0, start)]
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i]:
            continue
        for j, w in nb[i].items():
            if d + w < dist[j]:
                dist[j], prev[j] = d + w, i
                heapq.heappush(heap, (d + w, j))
    out = {}
    for name, p in ends.items():
        i = int(np.argmin(np.linalg.norm(V - p, axis=1)))
        if not np.isfinite(dist[i]):
            return {}
        way = [i]
        while prev[way[-1]] >= 0:
            way.append(int(prev[way[-1]]))
        out[name] = V[way]
    return out


def _arms(paths, P, H, dep, origin, h):
    """Shoulders, elbows and wrists along the arms' ways (hand end first)."""
    iL, iR = _split(paths["handL"], paths["handR"])
    J = {}
    for s, i in (("L", iL), ("R", iR)):
        arm = paths["hand" + s][:i + 1]              # fingertip .. middle of the chest
        sign = 1 if s == "L" else -1
        # the shoulder: where the way leaves the torso. The torso's half width at that height:
        # the body's width just below the armpit, measured on the vertices
        L = _length(arm)
        # walk from the chest outwards until the way is outside the chest's width
        chest_y = arm[-1][1]
        near = P[(np.abs(P[:, 1] - (chest_y - 0.06 * H)) < 0.02 * H)]
        half = np.percentile(np.abs(near[:, 0]), 90) if len(near) else 0.12 * H
        rev = arm[::-1]
        out = np.where(sign * rev[:, 0] > 0.72 * half)[0]
        k = int(out[0]) if len(out) else len(rev) // 3
        if SHOULDER == "depth":                      # where the way thins from torso to arm
            idx = np.clip(np.floor((rev - origin) / h).astype(int), 0, np.array(dep.shape) - 1)
            d = dep[idx[:, 0], idx[:, 1], idx[:, 2]]
            n = len(rev)
            arm_d = np.median(d[int(0.5 * n):int(0.8 * n)]) if n > 5 else d.min()
            thin = np.where(d <= DEPTH_K * arm_d)[0]
            if len(thin):
                k = int(thin[0])
        # the bend: walking in from the fingertip the way runs straight along the arm, then turns
        # down into the torso at the shoulder; a short, thin torso fools the thickness alone
        n = len(arm)
        cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(arm, axis=0), axis=1))])
        ia = int(np.searchsorted(cum, 0.35 * cum[-1]))
        flat = np.array([1.0, 1.0, 0.0])               # seen from the front: a wiggle in depth (fur,
        d = (arm[ia] - arm[0]) * flat                  # a sleeve) is no bend
        if np.linalg.norm(d) > 1e-9 and n > 8:
            d = d / np.linalg.norm(d)
            for i in range(ia, n - 3):
                v = (arm[i + 3] - arm[i]) * flat
                if np.linalg.norm(v) > 1e-9 and np.dot(v / np.linalg.norm(v), d) < np.cos(np.radians(BEND)):
                    kb = n - 1 - i
                    below = rev[k][1] < rev[kb][1] - 0.05 * H
                    above = rev[k][1] > rev[kb][1] + 0.05 * H and v[1] > 0.7 * np.linalg.norm(v)
                    if kb > k and (below or above):
                        k = kb                          # thickness put it well below the arm, or up the
                                                        # way into a big head (a chibi's helmet): the bend
                    break
        shoulder = rev[k].copy()
        # the way drifts towards the body's deepest part (a big head pulls it up): the shoulder lies
        # on the arm's own line, carried on from the stretch between wrist and elbow
        c0, c1 = np.searchsorted(cum, 0.1 * cum[-1]), np.searchsorted(cum, 0.45 * cum[-1])
        if ARM_LINE and c1 - c0 >= 3:
            seg = arm[c0:c1 + 1]
            u = seg[-1] - seg[0]
            u = u / max(np.linalg.norm(u), 1e-9)
            cen = []                                 # the arm's middle on the mesh: the centre of the
            for q in seg:                            # vertices around each point of the way
                d = P - q
                near = P[(np.abs(d @ u) < h) & (np.linalg.norm(d - np.outer(d @ u, u), axis=1) < 0.08 * H)]
                if len(near) >= 4:
                    cen.append((near.min(0) + near.max(0)) / 2)
            seg = np.array(cen) if len(cen) >= 3 else seg
            m = seg.mean(0)
            u = np.linalg.svd(seg - m)[2][0]
            line_y = lambda q: (m + u * np.dot(q - m, u))[1]
            if shoulder[1] - line_y(shoulder) > ARM_LINE * H:  # above the line: onto it
                shoulder[1] = line_y(shoulder)
            elif line_y(shoulder) - shoulder[1] > 3 * ARM_LINE * H:
                # far below it: the way runs down into the torso before the thickness says so
                # (a fluffy arm as thick as a slim chest); out along the way to where it meets the line
                while k < len(rev) - 1 and line_y(rev[k]) - rev[k][1] > ARM_LINE * H:
                    k += 1
                shoulder = rev[k].copy()
        shoulder[1] += RAISE * H
        sh_len = _length(rev[k:])                    # shoulder .. fingertip
        tail = rev[k:]
        J["upper" + s] = shoulder
        J["fore" + s] = _at_length(tail, ELBOW * sh_len)
        J["hand" + s] = _at_length(tail, WRIST * sh_len)
    return J


def _centre(J, P, H, head_end, top_y):
    """Pelvis (hips), and the head joint (the base of the skull, Tekken's head row) on the
    middle line."""
    hipy = (J["thighL"][1] + J["thighR"][1]) / 2
    sh = (J["upperL"] + J["upperR"]) / 2
    pelvis = np.array([0.0, hipy + 0.027 * H, (J["thighL"][2] + J["thighR"][2]) / 2])
    neck = np.array([0.0, sh[1] + NECK * (top_y - sh[1]), sh[2]])
    return {"hips": pelvis, "neck": neck, "top": np.array([0.0, top_y, neck[2]])}


# body parts: bones as segments between joints; every voxel takes the bone nearest through the body
def _bones(J, P=None):
    """[(part, a, b)]: the line segments each body part grows from. The spine runs up to the
    head joint and out along the shoulder girdle, the pelvis to both hip sockets, the thighs
    start a little below them, the feet reach back to the heel: as the parts of a skinned rig."""
    sh = (J["upperL"] + J["upperR"]) / 2
    nk = J["neck"] - sh                              # the jaw hangs below the head joint
    out = [(("spine", None), J["hips"], J["neck"] - NECK_SPLIT[0] * nk),
           (("head", None), J["neck"] - NECK_SPLIT[1] * nk, J["top"])]
    for s in "LR":
        hip, knee, ankle = J["thigh" + s], J["shin" + s], J["foot" + s]
        heel = ankle.copy()
        if P is not None:                            # the foot's back end, at the sole
            near = P[(np.abs(P[:, 0] - ankle[0]) < 0.06 * np.ptp(P[:, 1])) & (P[:, 1] < ankle[1])]
            if len(near):
                heel = near[np.argmin(near[:, 2])]
        out += [(("spine", None), sh, sh + 0.8 * (J["upper" + s] - sh)),
                (("pelvis", None), J["hips"], hip),
                (("collar", s), sh + 0.88 * (J["upper" + s] - sh), J["upper" + s]),
                (("upper", s), J["upper" + s] + 0.15 * (J["fore" + s] - J["upper" + s]), J["fore" + s]),
                (("fore", s), J["fore" + s], J["hand" + s]),
                (("hand", s), J["hand" + s], J["handend" + s]),
                (("thigh", s), hip + 0.25 * (knee - hip), knee),
                (("shin", s), knee, ankle),
                (("foot", s), ankle, J["toe" + s]),
                (("foot", s), ankle, heel)]
    return out


def segment(P, solid, origin, h, J, extra=()):
    bones = _bones(J, P)
    lines = [(prt, np.array([a, b])) for prt, a, b in bones] + list(extra)
    label = np.full(solid.shape, -1, np.int16)
    for n, (_, line) in enumerate(lines):            # seeds: voxels along each bone and branch
        for a, b in zip(line[:-1], line[1:]):
            for t in np.linspace(0, 1, 40 if len(line) == 2 else 4):
                v = np.floor((a + t * (b - a) - origin) / h).astype(int)
                if (v >= 0).all() and (v < solid.shape).all() and solid[tuple(v)] and label[tuple(v)] < 0:
                    label[tuple(v)] = n
    # the head: everything above its joint and within the shoulders (a snout, a jaw, big ears)
    head = next(n for n, (prt, _) in enumerate(lines) if prt == ("head", None))
    centres = origin + (np.indices(solid.shape).reshape(3, -1).T + 0.5) * h
    half = HEAD_WIDTH * abs(J["upperL"][0] - J["upperR"][0]) / 2
    Hm = np.ptp(P[:, 1])
    above = ((centres[:, 1] > J["neck"][1] + HEAD_LIFT * Hm) & (np.abs(centres[:, 0] - J["neck"][0]) < half)
             & (centres[:, 2] > J["neck"][2] - 0.12 * Hm))     # not a tail curling up behind
    above = above.reshape(solid.shape) & solid & (label < 0)
    label[above] = head
    # grow the labels through the solid, one layer at a time (6-neighbours)
    for _ in range(4 * max(solid.shape)):
        free = solid & (label < 0)
        if not free.any():
            break
        grown = False
        for ax in range(3):
            for s in (1, -1):
                src = _shift(label, np.eye(3, dtype=int)[ax] * s, -1)
                take = free & (src >= 0) & (label < 0)
                if take.any():
                    label[take] = src[take]
                    grown = True
        if not grown:
            break
    idx = np.clip(np.floor((P - origin) / h).astype(int), 0, np.array(solid.shape) - 1)
    lab = label[idx[:, 0], idx[:, 1], idx[:, 2]]
    part = np.empty(len(P), dtype=object)
    for i, l in enumerate(lab):
        part[i] = lines[l][0] if l >= 0 else ("spine", None)
    # knees or thighs that touch let the growing cross from one leg to the other (the Soldier):
    # a leg's point belongs to the leg whose bones are nearest in a straight line
    chain = {s: [J["thigh" + s], J["shin" + s], J["foot" + s], J["toe" + s]] for s in "LR"}
    def dist(p, s):
        c = chain[s]
        return np.min([_seg_dist(p, a, b) for a, b in zip(c[:-1], c[1:])])
    for i, prt in enumerate(part):
        if prt[0] in ("thigh", "shin", "foot") and prt[1] in "LR":
            other = "R" if prt[1] == "L" else "L"
            if dist(P[i], other) < 0.8 * dist(P[i], prt[1]):
                part[i] = (prt[0], other)
    return part


# ------------------------------------------------------------------ orientation and skeleton --

def _rot(up, front):
    """Rotation taking axis `up` to +Y and `front` to +Z (rows: the new X, Y, Z in old axes)."""
    up, front = np.asarray(up, float), np.asarray(front, float)
    left = np.cross(up, front)
    return np.stack([left, up, front])


def _pieces(pts, cell):
    """Separate pieces of a slice of points (2D, joined when closer than ~2 cells)."""
    if not len(pts):
        return 0
    g = np.floor((pts - pts.min(0)) / cell).astype(int)
    occ = np.zeros(tuple(g.max(0) + 3), bool)
    occ[g[:, 0] + 1, g[:, 1] + 1] = True
    grown = occ.copy()                               # join specks of one piece
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            grown |= np.roll(np.roll(occ, dx, 0), dy, 1)
    seen = np.zeros_like(grown)
    n = 0
    for start in np.argwhere(grown):
        if seen[tuple(start)]:
            continue
        n += 1
        stack = [tuple(start)]
        seen[tuple(start)] = True
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < grown.shape[0] and 0 <= q[1] < grown.shape[1] and grown[q] and not seen[q]:
                    seen[q] = True
                    stack.append(q)
    return n


def orient(P, T=None, up=None):
    """The rotation (3x3, applied as P @ R.T) that stands a humanoid upright facing +Z. Up: the
    axis whose low end is two feet (two pieces in a thin slice) and whose high end one head;
    ties go to the tallest axis, then to the model's own +Y. Front: where the toes point."""
    P = np.asarray(P, float)
    if T is not None and len(T):                     # dense points on the surface, not only corners
        H0 = float(np.ptp(P, axis=0).max())
        S, _, _, _ = remesh.surface_samples(P, np.asarray(T), 0.006 * H0)
    else:
        S = P
    # the body's volume: a standing human's lies above the middle (torso and head, thin legs)
    vol = None
    if T is not None and len(T):
        hv = float(np.ptp(P, axis=0).max()) / 60
        lo3 = P.min(0) - 2.5 * hv
        shape = tuple(int(x) for x in np.ceil((P.max(0) - lo3) / hv) + 3)
        sv, _, _, _ = remesh.surface_samples(P, np.asarray(T), hv)
        vol = lo3 + (np.argwhere(remesh.solid(sv, lo3, hv, shape, close=1)) + 0.5) * hv
    best = None
    fixed = up
    if fixed is not None:                            # the standard's up, unless the model lies down
        others = [k for k in range(3) if abs(fixed[k]) < 0.5]
        if np.ptp(P @ fixed) < 0.6 * np.ptp(P[:, others], axis=0).max():
            fixed = None
    for ax in range(3):
        for sgn in (1, -1):
            up = np.zeros(3)
            up[ax] = sgn
            if fixed is not None and not np.allclose(up, fixed):
                continue                             # glTF files are Y up by the standard
            y = P @ up
            H = np.ptp(y)
            if H <= 0:
                continue
            lo, hi = y.min(), y.max()
            others = [k for k in range(3) if k != ax]
            tall = H / max(np.ptp(P[:, others], axis=0).max(), 1e-9)
            if tall < 0.45 and fixed is None:        # a standing figure is never thinnest upwards
                continue
            ys = S @ up
            feet = _pieces(S[ys < lo + 0.02 * H][:, others], 0.008 * H)
            head = _pieces(S[ys > hi - 0.02 * H][:, others], 0.008 * H)
            score = 1.5 * (2 <= feet <= 4) + 0.5 * (head == 1) + 0.5 * min(tall, 2.0) + 0.3 * (ax == 1 and sgn == 1)
            if vol is not None:
                c = (float(np.mean(vol @ up)) - lo) / H
                score += float(np.clip((c - 0.5) * 25, -3, 3))
            if best is None or score > best[0]:
                best = (score, up, others)
    _, up, others = best
    y = P @ up
    H = np.ptp(y)
    lo = y.min()
    # left-right: the axis the two feet stand apart along (else the wider one), front the other
    ys0 = S @ up
    low = S[ys0 < lo + 0.04 * H][:, others]
    widths = [np.ptp(P[y < lo + 0.5 * H][:, k]) for k in others]
    side_i = int(np.argmax(widths))
    # arms spread (T- or A-pose) say it best: the upper body is far wider side to side than deep;
    # the feet only when it is not (one foot ahead of the other split them front to back: the elf)
    upper = P[y > lo + 0.5 * H][:, others]
    spans = np.ptp(upper, axis=0) if len(upper) else np.zeros(2)
    if spans.min() > 0 and spans.max() / spans.min() > ARMS_WIDER:
        side_i = int(np.argmax(spans))
    elif len(low) > 20:
        c = low.mean(0)
        a, b = low[low[:, 0] < c[0]], low[low[:, 0] >= c[0]]
        for _ in range(10):                          # two clusters (2-means), seeded along each axis
            ca, cb = a.mean(0) if len(a) else c, b.mean(0) if len(b) else c
            near_a = np.linalg.norm(low - ca, axis=1) < np.linalg.norm(low - cb, axis=1)
            a, b = low[near_a], low[~near_a]
        if len(a) and len(b):
            side_i = int(np.argmax(np.abs(a.mean(0) - b.mean(0))))
    depth_ax = others[1 - side_i]
    front = np.zeros(3)
    front[depth_ax] = 1
    # front: the feet reach farther ahead of the ankles (toes) than behind them (heels)
    ys = S @ up
    vote = 0.0
    for sgn_side in (1, -1):
        side = S @ np.eye(3)[others[side_i]] * sgn_side > 0
        foot = S[side & (ys < lo + 0.04 * H)][:, depth_ax]
        ankle = S[side & (ys > lo + 0.07 * H) & (ys < lo + 0.12 * H)][:, depth_ax]
        if len(foot) > 10 and len(ankle) > 10:
            a = np.median(ankle)
            vote += (foot.max() - a) - (a - foot.min())
    if vote < -0.035 * H:
        front = -front                               # toes point the other way (a weak vote, round
                                                     # feet without toes, keeps the file's own front)
    return _rot(up, front)


NAMES = {"collar": "Shoulder", "upper": "Arm", "fore": "ForeArm", "hand": "Hand", "thigh": "UpLeg",
         "shin": "Leg", "foot": "Foot"}


def skeleton(J, part):
    """A skeleton named as Mixamo's at the joints, and every vertex weighted fully to its part's
    bone: what a rigged file gives, so the rest of the importer takes the model as rigged."""
    bones = []

    def add(name, at, parent):
        m = np.eye(4)
        m[:3, 3] = at
        bones.append({"name": name, "parent": parent, "matrix": m.tolist()})
        return len(bones) - 1

    sh = (J["upperL"] + J["upperR"]) / 2
    hips = add("Hips", J["hips"], -1)
    spine = add("Spine", J["hips"] + 0.4 * (sh - J["hips"]), hips)
    chest = add("Spine2", sh - 0.1 * (sh - J["hips"]), spine)
    neck = add("Neck", J["neck"], chest)
    head = add("Head", J["neck"] + 0.35 * (J["top"] - J["neck"]), neck)
    add("HeadTop_End", J["top"], head)
    of = {("spine", None): spine, ("pelvis", None): hips, ("head", None): head}
    for s, side in (("L", "Left"), ("R", "Right")):
        prev = chest
        for prt in ("collar", "upper", "fore", "hand"):
            prev = of[(prt, s)] = add(side + NAMES[prt], J[prt + s], prev)
        add(side + "HandMiddle4", J["handend" + s], prev)
        prev = hips
        for prt in ("thigh", "shin", "foot"):
            prev = of[(prt, s)] = add(side + NAMES[prt], J[prt + s], prev)
        add(side + "Toe_End", J["toe" + s], prev)
    vbone = np.array([of.get(tuple(p), spine) for p in part])
    weights = [{int(b): 1.0} for b in vbone]
    return bones, weights, vbone


# the joints a player can place by hand (the rest follow from them)
MARKERS = ("neck", "hips", "upperL", "upperR", "foreL", "foreR", "handL", "handR", "handendL", "handendR",
           "thighL", "thighR", "shinL", "shinR", "footL", "footR", "toeL", "toeR")


def complete(J, P):
    """Joints placed by hand -> the full set auto_rig makes (collars, the top of the head)."""
    J = {k: np.asarray(v, float) for k, v in J.items()}
    top_y = float(np.asarray(P)[:, 1].max())
    J["top"] = np.array([J["neck"][0], top_y, J["neck"][2]])
    for s in "LR":
        J["collar" + s] = J["upper" + s] + 0.65 * (np.array([J["neck"][0], J["upper" + s][1], J["upper" + s][2]]) - J["upper" + s])
    return J


PAINT_PARTS = ("head", "spine", "pelvis", "collarL", "collarR", "upperL", "upperR", "foreL", "foreR", "handL",
               "handR", "thighL", "thighR", "shinL", "shinR", "footL", "footR")


def paint(P, part, strokes):
    """Body parts painted by hand: [[x, y, z, part], ...] (points of the rig view); every vertex in
    a painted cell (1/60 of the height, and its neighbours) takes the paint of that cell."""
    if not strokes:
        return part
    P = np.asarray(P, float)
    h = float(np.ptp(P[:, 1])) / 60 or 1.0
    lo = P.min(0)
    cells = {}
    for x, y, z, name in strokes:
        c = tuple(np.floor((np.array([x, y, z]) - lo) / h).astype(int))
        prt = (name[:-1], name[-1]) if name[-1] in "LR" and name not in ("head", "spine", "pelvis") else (name, None)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    cells.setdefault((c[0] + dx, c[1] + dy, c[2] + dz), prt)
        cells[c] = prt                               # its own cell over a neighbour's
    idx = np.floor((P - lo) / h).astype(int)
    out = part.copy()
    for i, c in enumerate(map(tuple, idx)):
        if c in cells:
            out[i] = cells[c]
    return out


def rig(src, joints=None, strokes=None):
    """Gives a model without a skeleton one: src (direct_import.load) gets "bones", "weights",
    "vbone" and "auto_rig" (the joints, for the builder's view). joints: placed by hand
    {name: [x, y, z]} (MARKERS), else found from the shape."""
    P, T = np.asarray(src["P"], float), np.asarray(src["T"])
    if joints:
        missing = [k for k in MARKERS if k not in joints]
        if missing:
            raise RigError("Place every joint: " + ", ".join(missing) + ".")
        J = complete(joints, P)
        solid, origin, h = voxels(P, T)
        part = segment(P, solid, origin, h, J)
    else:
        J, part = auto_rig(P, T)
    part = paint(P, part, strokes)
    src["bones"], src["weights"], src["vbone"] = skeleton(J, part)
    src["auto_rig"] = {k: [round(float(x), 5) for x in v] for k, v in J.items()}
    return src
