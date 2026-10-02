"""A Tekken 3 style low-poly body from a detailed character (rules: NOTES.md, "How Tekken 3's own
fighter models are built").

Every limb and the torso is a tube of rings around its bone; the head is a latitude/longitude
shell around its centre. Ring points are found by casting rays outwards onto the original mesh;
the outermost hit wins, so clothes, armour and hair give the shape. Neighbouring parts share the
ring at their joint, as Tekken 3's own models do (the ring bends with the joint). Faces are
quads where possible (GPU corner order: triangles (0, 1, 2) and (1, 3, 2)), wound so triangle
(0, 1, 2) faces outwards. Each part is one rectangular texture chart (u around, v along).

build(...) -> dict(positions (FBX space), owner row per vertex, faces [{"v", "chart", "flat"}],
normals (smooth, per vertex), chart_weight {chart: texture density factor})."""
from __future__ import annotations
import numpy as np


def ray_hits(origins, dirs, P, T, max_len):
    """Distance to the farthest triangle hit along each ray (Möller-Trumbore), nan if none."""
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    e1, e2 = b - a, c - a
    out = np.full(len(origins), np.nan)
    for i0 in range(0, len(origins), 48):
        o = origins[i0:i0 + 48, None, :]
        d = dirs[i0:i0 + 48, None, :]
        p = np.cross(d, e2[None])
        det = np.einsum("rtk,tk->rt", p, e1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = o - a[None]
        u = np.einsum("rtk,rtk->rt", s, p) * inv
        q = np.cross(s, e1[None])
        v = np.einsum("rtk,rtk->rt", np.broadcast_to(d, q.shape), q) * inv
        t = np.einsum("rtk,tk->rt", q, e2) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < max_len[i0:i0 + 48, None])
        far = np.where(hit, t, -1).max(1)
        out[i0:i0 + 48] = np.where(far > 0, far, np.nan)
    return out


def cast(origins, dirs, P, T, max_len, min_len=0.0):
    """Points on the outermost surface; rays that miss take the median distance of the batch."""
    origins = np.asarray(origins, float)
    dirs = np.asarray(dirs, float)
    ml = np.broadcast_to(np.asarray(max_len, float), (len(origins),)).copy()
    d = ray_hits(origins, dirs, P, T, ml) if len(T) else np.full(len(origins), np.nan)
    if np.isnan(d).all():
        d[:] = ml * 0.15
    med = np.nanmedian(d)
    d = np.where(np.isnan(d), med, d)
    d = np.clip(d, 0.35 * med, 2.0 * med)      # a stray far hit (a strap, a hair tip) makes no spike
    d = np.maximum(d, min_len)
    return origins + dirs * d[:, None]


def frame(axis, ref):
    a = axis / np.linalg.norm(axis)
    r = ref - a * (ref @ a)
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(a, [1.0, 0, 0])
    r /= np.linalg.norm(r)
    return a, r, np.cross(a, r)


class Body:
    def __init__(self):
        self.pos, self.owner, self.faces = [], [], []
        self.charts, self.weight = 0, {}

    def add(self, pts, owner):
        start = len(self.pos)
        self.pos += [np.asarray(p, float) for p in pts]
        self.owner += [owner] * len(pts)
        return list(range(start, start + len(pts)))

    def chart(self, weight=1.0):
        self.charts += 1
        self.weight[self.charts - 1] = weight
        return self.charts - 1

    def strip(self, rings, vs, chart, circ, ks=None):
        """Quads between consecutive rings (equal sizes); vs = v coordinate of each ring. ks: the
        sectors to make (in this order, laid side by side in the chart), default all."""
        n = len(rings[0])
        ks = list(range(n)) if ks is None else list(ks)
        for j in range(len(rings) - 1):
            A, B = rings[j], rings[j + 1]
            for i, k in enumerate(ks):
                k1 = (k + 1) % n
                u0, u1 = circ * i / n, circ * (i + 1) / n
                self.faces.append({"v": [A[k], B[k], A[k1], B[k1]], "chart": chart,
                                   "flat": [(u0, vs[j]), (u0, vs[j + 1]), (u1, vs[j]), (u1, vs[j + 1])]})

    def cap(self, ring, centre, v_ring, v_centre, chart, circ, ks=None):
        n = len(ring)
        ks = list(range(n)) if ks is None else list(ks)
        for i, k in enumerate(ks):
            k1 = (k + 1) % n
            u0, u1 = circ * i / n, circ * (i + 1) / n
            self.faces.append({"v": [ring[k], centre, ring[k1]], "chart": chart,
                               "flat": [(u0, v_ring), ((u0 + u1) / 2, v_centre), (u1, v_ring)]})


def build(P, Tr, trow, J, ends, front, limbs, detail=1.0):
    """P, Tr: original mesh (FBX space); trow: row per original triangle; J: joint per row
    (1 = 3 = hips, 19 = neck, limbs at their bone start); ends: "head", "hand L/R", "toe L/R";
    front: the facing direction; limbs: {"leg"|"arm": {side: (rows)}}; detail scales sides."""
    up = np.array([0.0, 1, 0])
    left = np.cross(up, front)
    height = float(P[:, 1].max() - P[:, 1].min())
    body = Body()
    centre_of = []                    # per face: the axis point its outside faces away from
    sel = lambda rows: Tr[np.isin(trow, list(rows))]
    n_body = max(10, int(round(12 * detail)))
    n_leg = max(6, int(round(8 * detail)))
    n_arm = max(6, int(round(7 * detail)))

    def ring_at(c, axis, ref, n, tris, max_len, min_len=0.0, spin=1.0):
        a, r, s = frame(axis, ref)
        s = s * spin
        ang = 2 * np.pi * np.arange(n) / n
        dirs = np.cos(ang)[:, None] * r + np.sin(ang)[:, None] * s
        pts = cast(np.repeat(c[None], n, 0), dirs, P, tris, max_len, min_len)
        # no single point juts out of its ring (a pouch, a buckle, a belt end): at most 1.3x
        # the mean of its neighbours; Namco's rings are smooth outlines
        d = np.linalg.norm(pts - c, axis=1)
        for _ in range(3):
            d = np.minimum(d, 1.3 * (np.roll(d, 1) + np.roll(d, -1)) / 2)
        return c + dirs * d[:, None]

    def tube(a, b, segments, n, tris, ref, max_len, owner, first=None, cap_at=None, weight=1.0, min_len=0.0):
        rings = [first] if first is not None else []
        # turn the same way round as the shared first ring: a tube pointing the other way
        # (the pelvis down from the waist) would otherwise run its ring backwards and the
        # strip between them would cross itself
        spin = 1.0
        if first is not None:
            F0 = np.array([body.pos[i] for i in first])
            _, r0, s0 = frame(b - a, ref)
            k = 1 if len(first) > 1 else 0
            spin = 1.0 if ((F0[k] - F0.mean(0)) @ s0) >= 0 else -1.0
        for j in range(0 if first is None else 1, segments + 1):
            c = a + (b - a) * j / segments
            rings.append(body.add(ring_at(c, b - a, ref, n, tris, max_len, min_len, spin), owner))
        Pp = np.array(body.pos)
        circ = np.mean([np.linalg.norm(Pp[rg] - np.roll(Pp[rg], -1, 0), axis=1).sum() for rg in rings])
        length = np.linalg.norm(b - a)
        vs = [length * j / segments for j in range(segments + 1)]
        ch = body.chart(weight)
        before = len(body.faces)
        body.strip(rings, vs, ch, circ)
        if cap_at is not None:
            centre = body.add([cap_at], owner)[0]
            body.cap(rings[-1], centre, vs[-1], vs[-1] + circ / n, ch, circ)
        f = lambda x, a=a, b=b: _closest(x, a, b)
        centre_of.extend([f] * (len(body.faces) - before))
        return rings

    hips, neck = J[1], J[19]
    torso_tris = sel({1, 3, 11, 15})
    pelvis_tris = sel({3, 5, 8})
    knee_y = np.mean([J[r][1] for r in limbs["leg"]["L"][1:2] + limbs["leg"]["R"][1:2]])
    crotch = np.mean([J[limbs["leg"][sd][0]] for sd in ("L", "R")], 0)
    crotch = crotch - up * 0.2 * (crotch[1] - knee_y)           # pelvis down to the crotch; thighs start inside it
    waist = body.add(ring_at(hips, up, front, n_body, np.concatenate([torso_tris, pelvis_tris]), 0.2 * height), 1)
    torso = tube(hips, neck, 4, n_body, torso_tris, front, 0.2 * height, 1, first=waist, weight=1.3)
    tube(hips, crotch, 2, n_body, pelvis_tris, front, 0.2 * height, 3, first=waist, cap_at=crotch)

    # head: rings of a latitude/longitude shell around the head's centre, the neck ring shared
    top = ends["head"]
    head_tris = sel({19})
    hc = neck + (top - neck) * 0.48
    radius = np.linalg.norm(top - hc) * 2.5
    a, r, s = frame(top - neck, front)
    lats = np.radians([-50, -28, -8, 12, 34, 58, 78])
    rings = [torso[-1]]
    ang = 2 * np.pi * np.arange(n_body) / n_body
    for la in lats:
        dirs = np.cos(la) * (np.cos(ang)[:, None] * r + np.sin(ang)[:, None] * s) + np.sin(la) * a
        rings.append(body.add(cast(np.repeat(hc[None], n_body, 0), dirs, P, head_tris, radius), 19))
    crown = body.add(cast(hc[None], a[None], P, head_tris, radius), 19)[0]
    Pp = np.array(body.pos)
    circ = np.linalg.norm(Pp[rings[3]] - np.roll(Pp[rings[3]], -1, 0), axis=1).sum()
    vs = [0.0]
    for j in range(1, len(rings)):
        vs.append(vs[-1] + np.mean(np.linalg.norm(Pp[rings[j]] - Pp[rings[j - 1]], axis=1)))
    # three charts: the face (the sectors around the front, the most texels, as Namco's
    # faces), and the two halves of the back of the head
    before = len(body.faces)
    q = n_body // 6
    face = [(k % n_body) for k in range(-q - 1, q + 1)]
    rest = [k for k in range(n_body) if k not in face]
    for ks, weight in ((face, 6.0), (rest[:len(rest) // 2], 1.6), (rest[len(rest) // 2:], 1.6)):
        ch = body.chart(weight)
        first_face = len(body.faces)
        body.strip(rings, vs, ch, circ, ks)
        body.cap(rings[-1], crown, vs[-1], vs[-1] + circ / n_body, ch, circ, ks)
        if ks is face:
            # Namco's faces are half a face, mirrored over the nose line: both halves share the
            # texels, so the face gets twice the detail in the same room
            mid = circ * len(ks) / (2 * n_body)
            for f in body.faces[first_face:]:
                f["flat"] = [(mid + abs(u - mid), v) for u, v in f["flat"]]
    centre_of.extend([lambda x, hc=hc: hc] * (len(body.faces) - before))

    for side, (thigh, shin, foot) in limbs["leg"].items():
        knee, ankle, toe = J[shin], J[foot], ends["toe " + side]
        hip = J[thigh] + up * 0.3 * np.linalg.norm(J[thigh] - knee)        # starts high inside the pelvis
        rt = tube(hip, knee, 3, n_leg, sel({thigh}), left, 0.09 * height, thigh)
        rs = tube(knee, ankle, 3, n_leg, sel({shin}), left, 0.07 * height, shin, first=rt[-1])
        ar = np.mean(np.linalg.norm(np.array([body.pos[i] for i in rs[-1]]) - ankle, axis=1))
        toe = ankle + (toe - ankle) * 0.9                                  # blunt toes, like Namco's shoes
        tube(ankle, toe, 2, n_leg, sel({foot}), left, 0.06 * height, foot, first=rs[-1], cap_at=toe,
             min_len=0.45 * ar)
    for side, (upper, fore, hand) in limbs["arm"].items():
        elbow, wrist, tip = J[fore], J[hand], ends["hand " + side]
        shoulder = J[upper] + (J[upper] - elbow) * 0.2                     # starts inside the torso
        ru = tube(shoulder, elbow, 3, n_arm, sel({upper, upper - 1}), front, 0.055 * height, upper)
        rf = tube(elbow, wrist, 3, n_arm, sel({fore, upper, hand}), front, 0.045 * height, fore, first=ru[-1])
        wr = np.mean(np.linalg.norm(np.array([body.pos[i] for i in rf[-1]]) - wrist, axis=1))
        fing = ends.get("fingers " + side)
        if fing is None:
            tip = wrist + (tip - wrist) * 0.85                             # blunt fingertips
            tube(wrist, tip, 2, n_arm, sel({hand}), front, 0.04 * height, hand, first=rf[-1], cap_at=tip,
                 min_len=0.6 * wr)
            continue
        # a Tekken 3 hand: palm, the four fingers as one mitten, and a thumb
        hand_tris = sel({hand})
        thick = 0.25 * wr
        rp = tube(wrist, fing["knuckle"], 1, n_arm, hand_tris, front, 0.04 * height, hand, first=rf[-1],
                  min_len=thick)
        end = fing["knuckle"] + (fing["tip"] - fing["knuckle"]) * 0.95
        tube(fing["knuckle"], end, 2, n_arm, hand_tris, front, 0.035 * height, hand, first=rp[-1], cap_at=end,
             min_len=thick)
        tb = fing["thumb base"] + (fing["knuckle"] - fing["thumb base"]) * 0.15
        tt = fing["thumb tip"]
        tube(tb, tt, 2, 5, hand_tris, front, 0.02 * height, hand, cap_at=tt, min_len=0.6 * thick)

    # wind every face so that triangle (0, 1, 2) faces away from its part's axis
    Pp = np.array(body.pos)
    for f, centre in zip(body.faces, centre_of):
        a, b, c = Pp[f["v"][:3]]
        n = np.cross(b - a, c - a)
        m = (a + b + c) / 3
        if n @ (m - centre(m)) < 0:
            v, fl = f["v"], f["flat"]
            if len(v) == 4:      # swap corners 1 and 2: both triangles turn over
                f["v"], f["flat"] = [v[0], v[2], v[1], v[3]], [fl[0], fl[2], fl[1], fl[3]]
            else:
                f["v"], f["flat"] = [v[0], v[2], v[1]], [fl[0], fl[2], fl[1]]
    # smooth normals: area-weighted face normals summed per vertex
    normals = np.zeros_like(Pp)
    for f in body.faces:
        v = f["v"]
        for t in [(v[0], v[1], v[2])] + ([(v[1], v[3], v[2])] if len(v) == 4 else []):
            n = np.cross(Pp[t[1]] - Pp[t[0]], Pp[t[2]] - Pp[t[0]])
            for i in t:
                normals[i] += n
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    return {"positions": Pp, "owner": body.owner, "faces": body.faces, "normals": normals,
            "chart_weight": body.weight}


def _closest(p, a, b):
    d = b - a
    t = np.clip((p - a) @ d / (d @ d), 0, 1)
    return a + t * d


def add_pieces(body, P, Tr, vrow, budget, height, log=print):
    """Loose pieces the tubes do not cover (a collar, puffed sleeves, a pouch): the original's
    triangles lying clearly outside the low-poly body, grouped into connected pieces, each
    simplified on its own (as Tekken 3 adds accessories) and hung on the rows of its vertices.
    Open pieces (single sheets) get both sides. Adds faces and charts to `body` (dict from
    build); returns the number of triangles added."""
    import remesh
    import decimate
    Pp = body["positions"]
    faces = body["faces"]
    lt = []
    for f in faces:
        v = f["v"]
        lt.append(v[:3])
        if len(v) == 4:
            lt.append([v[1], v[3], v[2]])
    lt = np.array(lt)
    cell = height / 200
    smp = remesh.Sampler(Pp, lt, cell)
    cen = P[Tr].mean(1)
    src = smp.lookup(cen)
    t = src[:, 0].astype(int)
    a, b, c = Pp[lt[t, 0]], Pp[lt[t, 1]], Pp[lt[t, 2]]
    q = a * (1 - src[:, 1:2] - src[:, 2:3]) + b * src[:, 1:2] + c * src[:, 2:3]
    n = np.cross(b - a, c - a)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    out = np.einsum("ij,ij->i", cen - q, n)
    far = (out > 0.028 * height) & (t >= 0)       # clearly outside: a belt hugging the hips stays in the tube
    if not far.any():
        return 0
    sub = Tr[far]
    # connected pieces (shared vertices)
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for tri in sub:
        for k in (1, 2):
            parent[find(tri[0])] = find(tri[k])
    comp = np.array([find(tri[0]) for tri in sub])
    pieces = []
    for cid in np.unique(comp):
        tris = sub[comp == cid]
        e1 = P[tris[:, 1]] - P[tris[:, 0]]
        e2 = P[tris[:, 2]] - P[tris[:, 0]]
        area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1).sum()
        if area > (0.03 * height) ** 2:
            pieces.append((area, tris))
    if not pieces:
        return 0
    pieces.sort(key=lambda x: -x[0])
    total = sum(a for a, _ in pieces)
    added = 0
    pos = list(Pp)
    owner = list(body["owner"])
    normals = list(body["normals"])
    for area, tris in pieces:
        ctr = P[tris].reshape(-1, 3).mean(0); ext = np.ptp(P[tris].reshape(-1, 3), 0)
        log(f"  piece at height {(ctr[1] - P[:, 1].min()) / height:.2f}, {len(tris)} source triangles")
        want = int(max(4, min(48, budget * area / total)))
        verts = np.unique(tris)
        local = {v: i for i, v in enumerate(verts)}
        lt_ = np.array([[local[v] for v in tri] for tri in tris])
        qp, used, f, merged = decimate.decimate(P[verts], lt_, want)
        if len(f) == 0:
            continue
        keep = sorted(set(f.ravel().tolist()))
        idmap = {v: len(pos) + i for i, v in enumerate(keep)}
        rows_here = [int(vrow[verts[v]]) for v in keep]
        piece_row = max(set(rows_here), key=rows_here.count)   # the whole piece on one bone: it
        for v in keep:                                       # moves rigidly, never tears apart
            pos.append(qp[v])
            owner.append(piece_row)
        # smooth normals of the piece
        pn = {v: np.zeros(3) for v in keep}
        for tri in f:
            nn = np.cross(qp[tri[1]] - qp[tri[0]], qp[tri[2]] - qp[tri[0]])
            for v in tri:
                pn[v] += nn
        for v in keep:
            normals.append(pn[v] / (np.linalg.norm(pn[v]) + 1e-12))
        # open sheet? (an edge used once) -> both sides
        edges = {}
        for tri in f:
            for e in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                k = (min(e), max(e))
                edges[k] = edges.get(k, 0) + 1
        sides = (1, -1) if any(v == 1 for v in edges.values()) else (1,)
        # one chart per axis the faces mostly look along (box projection)
        for sign in sides:
            charts = {}
            for tri in f:
                nn = np.cross(qp[tri[1]] - qp[tri[0]], qp[tri[2]] - qp[tri[0]]) * sign
                ax = int(np.argmax(np.abs(nn)))
                key = (ax, nn[ax] > 0)
                if key not in charts:
                    body["chart_weight"][len(body["chart_weight"])] = 1.0
                    charts[key] = len(body["chart_weight"]) - 1
                u_ax, v_ax = [k for k in range(3) if k != ax]
                corners = [tri[0], tri[1], tri[2]] if sign > 0 else [tri[0], tri[2], tri[1]]
                faces.append({"v": [idmap[v] for v in corners], "chart": charts[key],
                              "flat": [(qp[v][u_ax], qp[v][v_ax]) for v in corners]})
                added += 1
    body["positions"] = np.array(pos)
    body["owner"] = owner
    body["normals"] = np.array(normals)
    log(f"{len(pieces)} loose pieces, {added} triangles")
    return added
