"""The pose a stock fighter was modelled in (venv), solved from its own 50/50 joint seams.

Namco exported a seam vertex by writing its position in both bones' local frames, so in the
bind pose both copies land on the same point. Under the builder's standing frames (W from
model_import.donor_frames) that already holds at knees, elbows and wrists, but not at the
collarbones, hips, head and ankles (35-480 units off on Paul), so a model posed into W gets a
tilted head and torn shoulders in game. `solve(m, W)` turns each row, parents first, so its seam
copies meet its parent's (orthogonal Procrustes about the joint, pulled lightly towards W);
rows without seams keep their turn relative to the parent."""
from __future__ import annotations
import numpy as np


def seam_pairs(m):
    """[((row, xyz), (row, xyz))]: the source copy (parent row) and the reading copy of every
    flagged average (tail group 0/1: with the cache, group 2: with the previous list)."""
    import anim_model as A
    from fmt import row
    from simulate import vlist
    import model_export as X
    from fmt import nrows
    order = []                                   # draw order with the second layers (as probe_render)
    for p in range(1, 22):
        order.append(A.P2R[p])
        for r in A.SECONDS:
            if r >= nrows(m) or r in order:
                continue
            w = row(m, r)
            if w[10] and w[1] > 2 and ((r in (25, 26) and (w[6] & 0xFF) == p) or X.SECOND_AFTER.get(r) == A.P2R[p]):
                order.append(r)
    cache, scratch, out = {}, [None] * 128, []
    for r in order:
        w = row(m, r)
        if not w[10] or w[1] <= 2:
            continue
        a = vlist(m, r)
        if not a:
            continue
        L = [scratch[b // 2 - 1] if 0 < b // 2 <= 128 else None for b in a["g1"]]
        L += [cache.get(b // 2) for b in a["g2"]]
        s0 = len(L)
        L += [(r, np.array(v[:3], float)) for v in a["verts"]]
        before, c0, s, copies = list(scratch), dict(cache), s0, []
        for gi, grp in enumerate(a["tails"][:5]):
            for fld in grp:
                if s >= len(L):
                    break
                e, flag = (fld & 0xFF) // 2, fld & 0x100
                if gi in (0, 1) and flag and c0.get(e) and s >= s0:
                    out.append((c0[e], L[s]))
                if gi == 2 and flag and 0 <= e - 1 < 128 and before[e - 1] and s >= s0:
                    out.append((before[e - 1], L[s]))
                if gi in (0, 3):
                    cache[e] = L[s]
                if gi == 4:
                    copies.append((e - 1, s))
                s += 1
        scratch[:len(L)] = L
        for t, sl in copies:
            if 0 <= t < 128:
                scratch[t] = L[sl]
    return out


def solve(m, W, prior=0.05):
    import anim_model as A
    from fmt import row, nrows
    pairs = seam_pairs(m)
    B = {0: W[0]}
    order = [1, 3, 19, 11, 12, 13, 14, 15, 16, 17, 18, 5, 6, 7, 8, 9, 10]
    for r in order:
        p = A.ROW_PARENT[r]
        Rp0, Tp0 = W[p]
        Rp, Tp = B[p]
        Rr0, Tr0 = W[r]
        # the joint: the parent's frame plus the row's offset with z negated (seen in the probe:
        # the game places every child at (x, y, -z) of words 3..5 in its parent's vertex frame;
        # model_export.world uses +z, which mirrors collarbones and hips onto the other side)
        T = Tp + Rp @ (np.array(row(m, r)[3:6], float) * [1, 1, -1]) if p else Tr0
        R = Rp @ Rp0.T @ Rr0                          # turn relative to the parent kept
        X_, Y_ = [], []
        for (ra, va), (rb, vb) in pairs:
            if rb == r and ra in B and ra != r:
                X_.append(vb)
                Y_.append(B[ra][0] @ va + B[ra][1] - T)
            elif ra == r and rb in B and rb != r:
                X_.append(va)
                Y_.append(B[rb][0] @ vb + B[rb][1] - T)
        if X_:
            Xa, Ya = np.array(X_), np.array(Y_)
            scale = np.sqrt((Xa ** 2).sum(1).mean()) + 1.0
            w = np.sqrt(prior * len(Xa)) * scale       # a few seam points: stay near R
            Xa = np.vstack([Xa, np.eye(3) * w])
            Ya = np.vstack([Ya, R.T * w])               # R @ e_k = column k = row k of R.T
            U, _, Vt = np.linalg.svd(Ya.T @ Xa)
            D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
            R = U @ D @ Vt
        B[r] = (R, T)
    # second layers and accessories follow their host row
    for r in range(nrows(m)):
        if r in B or r not in W:
            continue
        h = {2: 1, 4: 3, 20: 19}.get(r)
        if h is None and r >= 21:
            part = row(m, r)[6] & 0xFF
            h = A.P2R[part] if part < len(A.P2R) else 0
        if h is None or h not in B:
            B[r] = W[r]
            continue
        Rh0, Th0 = W[h]
        Rh, Th = B[h]
        M = Rh @ Rh0.T
        B[r] = (M @ W[r][0], M @ (W[r][1] - Th0) + Th)
    return B


def residuals(m, W):
    """{(source row, reader row): [distance]} of the seam copies under the frames W."""
    out = {}
    for (ra, va), (rb, vb) in seam_pairs(m):
        d = np.linalg.norm(W[ra][0] @ va + W[ra][1] - W[rb][0] @ vb - W[rb][1])
        out.setdefault((ra, rb), []).append(float(d))
    return out
