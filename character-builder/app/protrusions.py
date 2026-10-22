"""Parts that stick out of a rigged model's head or body (a ponytail modelled straight back,
horns, a tail, wings): Tekken 3 has no hair physics and no spare joint, so such a part stays
rigid on its bone, as modelled. find() names them, apply() folds each one down from where it is
attached (the default), keeps it or removes it, preview() draws the result.

Works on the dict direct_import.load() returns (importer axes: Y up, facing +Z, left +X)."""
from __future__ import annotations
import io
import numpy as np

import model_import as MI

BODY = ("head", "spine", "pelvis")    # limbs are long by nature: only these are searched
FAR = 2.0                             # a vertex this many times the part's median radius is "out"
LONG = 3.0                            # a part must reach this far to count
DEFAULT = {"mode": "fold", "angle": None}     # angle None: as steep as clears the body
COLOURS = [(255, 80, 200), (60, 220, 255), (255, 210, 40), (120, 255, 120), (255, 120, 60), (170, 130, 255)]


def _parts_of_vertices(src):
    bones = src["bones"]
    def known(b):
        seen = 0
        while b >= 0 and seen < 64:
            p = MI._part(bones[b]["name"])[0]
            if p:
                return p
            b, seen = bones[b]["parent"], seen + 1
        return None
    cache = {}
    out = []
    for w in src["weights"]:
        if not w:
            out.append(None)
            continue
        b = max(w, key=w.get)
        if b not in cache:
            cache[b] = known(b)
        out.append(cache[b])
    return np.array(out, dtype=object)


def _weld(P):
    key = {}
    return np.array([key.setdefault(tuple(np.round(p, 5)), len(key)) for p in P])


def _components(sel, T, weld):
    """Connected groups (over shared welded corners) of the selected vertices."""
    parent = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for v in np.where(sel)[0]:
        parent.setdefault(weld[v], weld[v])
    for t in T:
        w = [weld[v] for v in t if sel[v]]
        for a, b in zip(w, w[1:]):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    groups = {}
    for v in np.where(sel)[0]:
        groups.setdefault(find(weld[v]), []).append(v)
    return [np.array(g) for g in groups.values()]


def _direction_words(d):
    words = []
    if d[1] > 0.5:
        words.append("up")
    elif d[1] < -0.5:
        words.append("down")
    if d[2] < -0.5:
        words.append("backwards")
    elif d[2] > 0.5:
        words.append("forwards")
    if abs(d[0]) > 0.5:
        words.append("to the model's left" if d[0] > 0 else "to the model's right")
    return " and ".join(words) or "outwards"


def find(src) -> list[dict]:
    """The parts that stick out, longest first: id, label, where, length (share of the height),
    vertices, attach point and direction."""
    if not src.get("bones") or "weights" not in src:
        return []
    P, T = src["P"], src["T"]
    H = float(np.ptp(P[:, 1])) or 1.0
    vpart = _parts_of_vertices(src)
    # the core: vertices whose own bone is the part's (not wings or a tail on extra bones, which
    # would make the radius they are measured against as big as themselves: MegaAngel's wings)
    dom = [max(w, key=w.get) if w else -1 for w in src["weights"]]
    own = np.array([d >= 0 and MI._part(src["bones"][d]["name"])[0] == p for d, p in zip(dom, vpart)])
    weld = _weld(P)
    out = []
    for part in BODY:
        on = np.array([p == part for p in vpart])
        if on.sum() < 8:
            continue
        j = MI.joint(src["bones"], part)
        if j is None:
            continue
        d = np.linalg.norm(P - j, axis=1)
        core = on & own if (on & own).sum() >= 8 else on
        r = float(np.median(d[core]))
        sel = on & (d > FAR * r)
        nb = {}
        for t in T:
            for a_ in t:
                nb.setdefault(weld[a_], set()).update(weld[b_] for b_ in t)
        members = {}
        for v in np.where(on)[0]:
            members.setdefault(weld[v], []).append(v)
        for g in _components(sel, T, weld):
            if len(g) < 6 or d[g].max() < LONG * r:
                continue
            # grow back to the root along the piece: neighbours on the same part, outside the
            # skull/torso core and within the piece's own thickness of its line
            line = P[g[np.argmax(d[g])]] - j
            line /= np.linalg.norm(line)
            off = lambda q: np.linalg.norm((q - j) - np.outer((q - j) @ line, line), axis=1)
            thick = 1.5 * max(off(P[g]).max(), 0.05 * r)
            gw = set(weld[g].tolist())
            todo = list(gw)
            while todo:
                w_ = todo.pop()
                for n_ in nb.get(w_, ()):
                    if n_ in gw or n_ not in members:
                        continue
                    q = P[members[n_][0]]
                    if np.linalg.norm(q - j) > 1.1 * r and (q - j) @ line > 0.6 * r and off(q[None])[0] < thick:
                        gw.add(n_)
                        todo.append(n_)
            g = np.array([v for w_ in gw for v in members.get(w_, [])])
            # attached where the group meets the rest of the part; a separate piece: its corner
            # nearest the joint
            ring = [v for t in T if any(weld[x] in gw for x in t) for v in t if weld[v] not in gw]
            attach = P[ring].mean(0) if ring else P[g[np.argmin(d[g])]]
            tip = P[g[np.argmax(np.linalg.norm(P[g] - attach, axis=1))]]
            axis = tip - attach
            length = float(np.linalg.norm(axis))
            if length < 0.08 * H:
                continue
            axis /= length
            side = np.linalg.norm((P[g] - attach)[:, [0, 2]], axis=1).max()
            if axis[1] < -np.cos(np.radians(35)) and side < 0.12 * H:   # hangs down along the body: nothing to do
                continue                                 # (Seed-san's robot arm hangs far beside her: listed)
            where = {"head": "Head", "spine": "Chest", "pelvis": "Hips"}[part]
            out.append({"where": where, "vertices": g, "attach": attach, "axis": axis, "length": length / H,
                        "label": f"{where}: a piece {round(100 * length / H)} % of the height long, "
                                 f"pointing {_direction_words(axis)}"})
    out = _merge_carried(src, out, H)
    out.sort(key=lambda p: -p["length"])
    for i, p in enumerate(out):
        p["id"] = i + 1
    return out


def _carrier(bones, b):
    """The extra bone through which bone b hangs on the human skeleton (a VRM's backpack), or None
    when b is human or hangs on it directly."""
    last = None
    while b >= 0 and not bones[b].get("human"):
        last, b = b, bones[b]["parent"]
    return last if b >= 0 and last is not None and MI._part(bones[last]["name"])[0] is None else None


def _merge_carried(src, parts, H):
    """Pieces that hang on the body through the same extra bone are one part (Seed-san's robot
    arm: six separate segments on her backpack), so it can be removed at once."""
    bones = src["bones"]
    if not any(b.get("human") for b in bones):
        return parts
    dom = [max(w, key=w.get) if w else -1 for w in src["weights"]]
    groups, rest = {}, []
    for p in parts:
        cs = {_carrier(bones, dom[v]) for v in p["vertices"]} - {None}
        if len(cs) == 1:
            groups.setdefault((p["where"], cs.pop()), []).append(p)
        else:
            rest.append(p)
    P = src["P"]
    carried = {}
    for v, d in enumerate(dom):
        carried.setdefault(_carrier(bones, d) if d >= 0 else None, []).append(v)
    for (where, carrier), ps in groups.items():
        if len(ps) == 1:
            rest += ps
            continue
        g = np.array(sorted(carried[carrier]))      # the whole prop, also what stays close to the body
        attach = max(ps, key=lambda p: p["length"])["attach"]
        tip = P[g[np.argmax(np.linalg.norm(P[g] - attach, axis=1))]]
        axis = tip - attach
        length = float(np.linalg.norm(axis)) or 1e-9
        axis = axis / length
        rest.append({"where": where, "vertices": g, "attach": attach, "axis": axis, "length": length / H,
                     "default": {"mode": "remove", "angle": None},    # a carried prop: folding breaks it up
                     "label": f"{where}: a piece in {len(ps)} parts, {round(100 * length / H)} % of the height long, "
                              f"pointing {_direction_words(axis)}"})
    return rest


def summary(parts) -> list[dict]:
    """What the builder shows (JSON-safe)."""
    return [{"id": p["id"], "label": p["label"], "where": p["where"], "length": round(p["length"], 3),
             "colour": "#%02x%02x%02x" % COLOURS[(p["id"] - 1) % len(COLOURS)], **DEFAULT, **p.get("default", {})}
            for p in parts]


def _rotate(V, centre, axis, angle):
    k = axis / (np.linalg.norm(axis) + 1e-12)
    c, s = np.cos(angle), np.sin(angle)
    v = V - centre
    return centre + v * c + np.cross(k, v) * s + np.outer(v @ k, k) * (1 - c)


def _fold(P, part, angle_deg, body_P, body_N):
    """The part turned about its attach point so it hangs `angle_deg` from straight down, keeping
    its heading (back stays back, a side tail stays on its side); turning eases in over the first
    fifth of its length so the root does not tear. angle None: the steepest that clears the body."""
    g, a, ax = part["vertices"], part["attach"], part["axis"]
    flat = np.array([ax[0], 0.0, ax[2]])
    flat = flat / np.linalg.norm(flat) if np.linalg.norm(flat) > 1e-6 else np.array([0, 0, -1.0])
    along = (P[g] - a) @ ax
    L = max(along.max(), 1e-9)
    ease = np.clip(along / (0.2 * L), 0, 1)[:, None]
    def turned(deg):
        t = np.radians(deg)
        target = np.array([0, -np.cos(t), 0]) + flat * np.sin(t)
        rot_axis = np.cross(ax, target)
        if np.linalg.norm(rot_axis) < 1e-9:
            return P[g].copy()
        full = np.arccos(np.clip(ax @ target, -1, 1))
        out = np.empty((len(g), 3))
        for i, (p, e) in enumerate(zip(P[g], ease[:, 0])):
            out[i] = _rotate(p[None], a, rot_axis, full * e)[0]
        return out
    if angle_deg is not None:
        return turned(float(angle_deg)), float(angle_deg)
    # folding down never lifts a part: it already hangs this far from straight down
    now = float(np.degrees(np.arccos(np.clip(-ax[1], -1, 1))))
    # the steepest hang whose points stay outside the body (in front of the nearest body point)
    for deg in range(10, 91, 5):
        if deg >= now:                                 # nothing steeper clears it: as it hangs
            return P[g].copy(), now
        Q = turned(deg)
        sample = Q[:: max(1, len(Q) // 150)]
        d2 = ((sample[:, None, :] - body_P[None]) ** 2).sum(2)
        k = d2.argmin(1)
        inside = ((sample - body_P[k]) * body_N[k]).sum(1) < 0
        if inside.mean() < 0.03:
            return Q, float(deg)
    return turned(90.0), 90.0


def apply(src, choices: dict | None = None, log=print) -> dict:
    """Folds (default), keeps or removes the parts find() reports; choices: {id: {mode, angle}}.
    Changes src in place; returns {id: angle used} for folded parts."""
    parts = find(src)
    if not parts:
        return {}
    choices = {int(k): v for k, v in (choices or {}).items()}
    P, T = src["P"], src["T"]
    taken = np.zeros(len(P), bool)
    for p in parts:
        taken[p["vertices"]] = True
    # body points for the clearance test: everything that is not a part (sampled)
    rest = np.where(~taken)[0]
    rest = rest[:: max(1, len(rest) // 4000)]
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    N = np.zeros_like(P)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    used, drop = {}, np.zeros(len(P), bool)
    for p in parts:
        c = {**DEFAULT, **p.get("default", {}), **choices.get(p["id"], {})}
        if c["mode"] == "remove":
            drop[p["vertices"]] = True
            log(f"part {p['id']} ({p['label']}): removed")
        elif c["mode"] == "fold":
            before = P[p["vertices"]].copy()
            P[p["vertices"]], used[p["id"]] = _fold(P, p, c.get("angle"), P[rest], N[rest])
            if np.array_equal(before, P[p["vertices"]]):
                log(f"part {p['id']} ({p['label']}): already hangs down ({used[p['id']]:.0f} degrees), left as it is")
            else:
                log(f"part {p['id']} ({p['label']}): folded down, {used[p['id']]:.0f} degrees from straight down")
        else:
            log(f"part {p['id']} ({p['label']}): kept as modelled")
    if drop.any():
        keep = ~drop[T].all(1)
        src["T"] = T[keep]
        for k in ("MAT",):
            if k in src:
                src[k] = np.asarray(src[k])[keep]
    return used


def preview(src, parts, size=360) -> bytes:
    """PNG: the model from the side and the back, the parts tinted in their colours."""
    from PIL import Image
    P, T, UV = src["P"], src["T"], src["UV"]
    tex = {k: np.asarray(Image.open(io.BytesIO(v)).convert("RGBA")) for k, v in src.get("textures", {}).items()}
    first = next(iter(tex.values())) if tex else np.full((4, 4, 4), 190, np.uint8)
    tint = np.full(len(P), -1)
    for p in parts:
        tint[p["vertices"]] = (p["id"] - 1) % len(COLOURS)
    imgs = []
    lo_all, hi_all = P[np.unique(T)].min(0), P[np.unique(T)].max(0)
    for yaw in (90, 180):
        a = np.radians(yaw)
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        Q = P @ R.T
        used = Q[np.unique(T)]
        lo, hi = used.min(0), used.max(0)
        sc = (size - 20) / max(hi[1] - lo[1], 1e-9)
        W = int((hi[0] - lo[0]) * sc) + 20
        img = np.zeros((size, W, 3), np.uint8)
        img[:] = (18, 20, 29)
        zb = np.full((size, W), -np.inf)
        X = (Q[:, 0] - lo[0]) * sc + 10
        Y = (hi[1] - Q[:, 1]) * sc + 10
        for ti, t in enumerate(T):
            xy = np.stack([X[t], Y[t]], 1)
            cr = (xy[1, 0] - xy[0, 0]) * (xy[2, 1] - xy[0, 1]) - (xy[1, 1] - xy[0, 1]) * (xy[2, 0] - xy[0, 0])
            if abs(cr) < 1e-9:
                continue
            x0, y0 = np.floor(xy.min(0)).astype(int)
            x1, y1 = np.ceil(xy.max(0)).astype(int)
            xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, W - 1) + 1), np.arange(max(y0, 0), min(y1, size - 1) + 1))
            px = np.stack([xs.ravel() + .5, ys.ravel() + .5], 1)
            l1 = ((xy[1, 0] - px[:, 0]) * (xy[2, 1] - px[:, 1]) - (xy[1, 1] - px[:, 1]) * (xy[2, 0] - px[:, 0])) / cr
            l2 = ((xy[2, 0] - px[:, 0]) * (xy[0, 1] - px[:, 1]) - (xy[2, 1] - px[:, 1]) * (xy[0, 0] - px[:, 0])) / cr
            ins = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
            if not ins.any():
                continue
            L = np.stack([l1, l2, 1 - l1 - l2], 1)[ins]
            pp = px[ins].astype(int)
            z = L @ Q[t, 2]
            uv = L @ UV[t]
            im = tex.get(int(src["MAT"][ti]) if "MAT" in src else 0, first)
            h, w = im.shape[:2]
            col = im[np.clip((uv[:, 1] * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int) % w, 0, w - 1)]
            rgb = col[:, :3].astype(float)
            tn = tint[t]
            if (tn >= 0).any():
                rgb = rgb * 0.35 + np.array(COLOURS[int(tn[tn >= 0][0])]) * 0.65
            ok = col[:, 3] > 128
            yy, xx = pp[:, 1], pp[:, 0]
            better = (z > zb[yy, xx]) & ok
            zb[yy[better], xx[better]] = z[better]
            img[yy[better], xx[better]] = rgb[better].astype(np.uint8)
        imgs.append(img)
    out = Image.new("RGB", (sum(i.shape[1] for i in imgs) + 10, size), (18, 20, 29))
    x = 0
    for i in imgs:
        out.paste(Image.fromarray(i), (x, 0))
        x += i.shape[1] + 10
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
