"""Render a fighter exactly as the game posed it, at high resolution (Expanded's venv).

Input: live/probe.bin from `t3live.py fight --probe` (src/tekken3_ttt1_renderer.c records, per
call of the native vertex transformer 0x80036CAC: header 8 u32 [tag, seen, m1, m2, a0..a3],
GTE control 32 u32, GTE data 32 u32, scratchpad 256, two caches 2 x 256, work 4 x 256 words).
a0 = model + 16 + row * 56 + 56 - 56... (row = (a0 - model - 16) / 56). The GTE rotation and
translation at entry put the row's own vertices in camera space.

  probe_render.py GAME model.bin out.png [--frames 6] [--size 700] [--live DIR] [--yaw DEG]
  (--live: a folder with probe.bin and game-log.txt, default <game>/character-builder/live)"""
import struct
import sys
from pathlib import Path
import numpy as np

import os
ROWS = bool(os.environ.get("ROWS"))
PAINTER = bool(os.environ.get("PAINTER"))   # draw by polygon depth order (the PS1 way)
QUADCULL = bool(os.environ.get("QUADCULL"))  # cull quads by their first triangle (the PS1 way)
REC_WORDS = 8 + 32 + 32 + 256 + 256 + 256 + 1024


def records(path):
    d = Path(path).read_bytes()
    n = len(d) // (REC_WORDS * 4)
    for i in range(n):
        w = struct.unpack_from(f"<{REC_WORDS}I", d, i * REC_WORDS * 4)
        yield {"m1": w[2], "m2": w[3], "a0": w[4], "ctrl": w[8:40]}


def gte(ctrl):
    s16 = lambda v: v - 65536 if v & 0x8000 else v
    s32 = lambda v: v - (1 << 32) if v & 0x80000000 else v
    c = ctrl
    R = np.array([[s16(c[0] & 0xFFFF), s16(c[0] >> 16), s16(c[1] & 0xFFFF)],
                  [s16(c[1] >> 16), s16(c[2] & 0xFFFF), s16(c[2] >> 16)],
                  [s16(c[3] & 0xFFFF), s16(c[3] >> 16), s16(c[4] & 0xFFFF)]], float) / 4096
    T = np.array([s32(c[5]), s32(c[6]), s32(c[7])], float)
    return R, T


def frames(path, model_addr):
    out, cur = [], {}
    for r in records(path):
        if r["m1"] != model_addr:
            continue
        row = (r["a0"] - model_addr - 16) // 56
        if not 0 <= row < 27:
            continue
        if row == 1 and cur:
            out.append(cur)
            cur = {}
        cur[row] = gte(r["ctrl"])
    if cur:
        out.append(cur)
    return out


def assemble(m, f, X):
    """Camera-space slot lists per row as the PlayStation builds them (0x80036CAC): borrowed
    slots (g1: previous list, g2: cache), own vertices through the row's transform, then the
    tail groups - 0: average with the cache (flag) and store, 1: average (flag), 2: average with
    the previous list (flag), 3: deposit, 4: copy into the next list. Flagged deposits store
    half on the hardware; here the full value is kept and the flagged read averages."""
    import anim_model as A
    from fmt import row, nrows
    from simulate import vlist
    order = []
    for p in range(1, 22):
        order.append(A.P2R[p])
        for r in A.SECONDS:
            if r >= nrows(m) or r in order:
                continue
            w = row(m, r)
            if w[10] and w[1] > 2 and ((r in (25, 26) and (w[6] & 0xFF) == p) or X.SECOND_AFTER.get(r) == A.P2R[p]):
                order.append(r)
    scratch, cache, out = [None] * 128, {}, {}
    for r in order:
        w = row(m, r)
        if not w[10] or w[1] <= 2 or r not in f:
            continue
        a = vlist(m, r)
        if not a:
            continue
        R, T = f[r]
        L = [scratch[b // 2 - 1] if 0 < b // 2 <= 128 else None for b in a["g1"]]
        L += [cache.get(b // 2) for b in a["g2"]]
        s0 = len(L)
        L += [R @ np.array(v[:3], float) + T for v in a["verts"]]
        before, cache0 = list(scratch), dict(cache)
        s, copies = s0, []
        for gi, grp in enumerate(a["tails"][:5]):
            for fld in grp:
                if s >= len(L):
                    break
                e, flag = (fld & 0xFF) // 2, fld & 0x100
                if gi in (0, 1):
                    if flag and cache0.get(e) is not None and L[s] is not None:
                        L[s] = (L[s] + cache0[e]) / 2
                    if gi == 0:
                        cache[e] = L[s]
                elif gi == 2:
                    t = e - 1
                    if flag and 0 <= t < 128 and before[t] is not None and L[s] is not None:
                        L[s] = (L[s] + before[t]) / 2
                elif gi == 3:
                    cache[e] = L[s]
                elif gi == 4:
                    copies.append((e - 1, s))
                s += 1
        scratch[:len(L)] = L
        for t, sl in copies:
            if 0 <= t < 128:
                scratch[t] = L[sl]
        out[r] = list(L)
    return out


def main():
    game = Path(sys.argv[1])
    sys.path.insert(0, str(game / "character-builder" / "app"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import model_export as X
    X.setup(game)
    import compare as C                       # texture loading and the rasteriser's pieces
    import anim_model as A
    from fmt import row, block, parse_b, parse_c_ps1
    from PIL import Image
    spec, out_png = sys.argv[2], sys.argv[3]
    nshow = int(sys.argv[sys.argv.index("--frames") + 1]) if "--frames" in sys.argv else 6
    S = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 700
    m, (band, vram) = C.load(spec)
    live = Path(sys.argv[sys.argv.index("--live") + 1]) if "--live" in sys.argv else game / "character-builder" / "live"
    log = (live / "game-log.txt").read_text(errors="replace") if (live / "game-log.txt").is_file() else ""
    import re
    found = re.findall(r"installed at ([0-9A-F]{8})", log)
    # without an own model (the donor drawn) the probe holds one model: the most common
    from collections import Counter
    addr = int(found[-1], 16) if found else 0 if "--rest" in sys.argv else Counter(r["m1"] for r in records(live / "probe.bin")).most_common(1)[0][0]
    if "--rest" in sys.argv:
        # the donor's standing frames seen from the given yaws (degrees): the rest pose the
        # import was posed into, through the same slot rules
        import model_import as MI
        rid = X.FIRST_MODEL_RECORD + 4 * int(sys.argv[sys.argv.index("--donor") + 1] if "--donor" in sys.argv else 0)
        md = X.records(game, [rid])[rid]
        Wd = X.world(md, None) if "--bind" in sys.argv else MI.donor_frames(game, md)
        if "--solved" in sys.argv:                # the pose the donor was modelled in
            import bind_pose as BP
            Wd = BP.with_offsets(m, BP.solve(md, Wd))
        if "--bind" in sys.argv:                  # stand it up: feet -> head along -Y
            v = Wd[19][1] - (Wd[7][1] + Wd[10][1]) / 2
            R0 = X.align(v / np.linalg.norm(v), np.array([0, -1.0, 0]))
            Wd = {r: (R0 @ R, R0 @ T) for r, (R, T) in Wd.items()}
        fr = []
        for yaw in sys.argv[sys.argv.index("--rest") + 1].split(","):
            a = np.radians(float(yaw))
            Rc = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
            c = sum(Wd[r][1] for r in Wd) / len(Wd)
            fr.append({r: (Rc @ Wd[r][0], Rc @ (Wd[r][1] - c) + np.array([0, 0, 6000.0])) for r in Wd})
    else:
        fr = frames(live / "probe.bin", addr)
    # only frames with every drawn row (a sampling window can cut a frame: a missing row also
    # misses its cache deposits, which looks like spikes that the game never draws)
    from fmt import row as _row
    drawn = [r for r in range(1, 21) if _row(m, r)[10] and _row(m, r)[1] > 2]
    # a frame whose joints are not where their parents put them (offset (x, y, -z) of words
    # 3..5) is mixed from two moments by the sampling window
    def coherent(f):
        if np.linalg.norm(f[1][1] - f[3][1]) > 50:
            return False
        for a, b in ((2, 1), (4, 3), (20, 19)):         # second layers draw in their row's frame
            if a in f and b in f and np.linalg.norm(f[a][1] - f[b][1]) > 5:
                return False
        for r, p in A.ROW_PARENT.items():
            if p and r in f and p in f:
                off = np.array(row(m, r)[3:6], float) * [1, 1, -1]
                if np.linalg.norm(np.linalg.solve(f[p][0], f[r][1] - f[p][1]) - off) > 30:
                    return False
        return True
    full = [f for f in fr if all(r in f for r in drawn) and coherent(f)]
    if "--pick" in sys.argv:
        pick = [full[int(x)] for x in sys.argv[sys.argv.index("--pick") + 1].split(",")]
    else:
        pick = [full[int(i)] for i in np.linspace(0, len(full) - 1, min(nshow, len(full)))]
    if "--yaw" in sys.argv:                       # turn the camera around the fighter
        a = np.radians(float(sys.argv[sys.argv.index("--yaw") + 1]))
        Rc = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        turned = []
        for f in pick:
            c = sum(f[r][1] for r in f) / len(f)
            turned.append({r: (Rc @ R, Rc @ (T - c) + c) for r, (R, T) in f.items()})
        pick = turned
    bind = X.bind(m)
    i4 = np.stack([(band >> (4 * k)) & 15 for k in range(4)], 2).reshape(band.shape[0], -1)
    i8 = np.stack([band & 255, band >> 8], 2).reshape(band.shape[0], -1)
    imgs = []
    for f in pick:
        tris = []
        cams = assemble(m, f, X)
        for r, slots in bind.items():
            if r not in cams:
                continue
            w = row(m, r)
            prims = parse_c_ps1(block(m, w[2]))
            i = 0
            for k, fam in enumerate(parse_b(block(m, w[1]))):
                for rec in fam:
                    c = A.prim_verts(k, rec)
                    _, mat, uv = prims[i]
                    i += 1
                    for a, b, cc in ([(0, 1, 2)] if len(c) == 3 else [(0, 1, 2), (1, 3, 2)]):
                        pts = [slots[c[j]] if c[j] < len(slots) else None for j in (a, b, cc)]
                        if None in pts or mat is None or any(p[0] not in f for p in pts):
                            continue
                        cam = [cams[r][c[j]] for j in (a, b, cc)]
                        if any(x is None for x in cam):
                            continue
                        first = [cams[r][c[j]] for j in (0, 1, 2)]   # the quad's culling triangle
                        tris.append((cam, [uv[j] for j in (a, b, cc)], mat, pts[0][0], first))
        P = np.array([t[0] for t in tris])
        sx = P[:, :, 0] / P[:, :, 2]
        sy = P[:, :, 1] / P[:, :, 2]
        lo = np.array([sx.min(), sy.min()])
        hi = np.array([sx.max(), sy.max()])
        sc = (S - 20) / max(hi - lo)
        W_ = int((hi - lo)[0] * sc) + 20
        img = np.zeros((S, W_, 3), np.uint8)
        img[:] = (255, 0, 255) if os.environ.get("MAGENTA") else (20, 25, 50)
        zb = np.full((S, W_), np.inf)
        if PAINTER:                              # as the PlayStation: no depth buffer, polygons
            # into ordering-table slots by mean z (PAINTER = slot size in z units); a slot's list
            # is drawn last-inserted first
            b = float(os.environ.get("PAINTER", "1")) or 1.0
            order = sorted(range(len(tris)), key=lambda i: (-int(np.mean([p[2] for p in tris[i][0]]) // b), -i))
            tris = [tris[i] for i in order]
        for (cam, uvs, mt, rw, first) in tris:
            cam = np.array(cam)
            if QUADCULL:                         # cull a quad by its first triangle only
                fc = np.array(first)
                fxy = np.stack([(fc[:, 0] / fc[:, 2] - lo[0]) * sc, (fc[:, 1] / fc[:, 2] - lo[1]) * sc], 1)
                if (fxy[1, 0] - fxy[0, 0]) * (fxy[2, 1] - fxy[0, 1]) - (fxy[1, 1] - fxy[0, 1]) * (fxy[2, 0] - fxy[0, 0]) <= 0:
                    continue
            xy = np.stack([(cam[:, 0] / cam[:, 2] - lo[0]) * sc + 10, (cam[:, 1] / cam[:, 2] - lo[1]) * sc + 10], 1)
            a, b, cc = xy
            cross = (b[0] - a[0]) * (cc[1] - a[1]) - (b[1] - a[1]) * (cc[0] - a[0])
            if cross <= 0 and not QUADCULL:      # the game culls these (back faces)
                continue
            x0, y0 = np.floor(xy.min(0)).astype(int)
            x1, y1 = np.ceil(xy.max(0)).astype(int)
            xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, W_ - 1) + 1), np.arange(max(y0, 0), min(y1, S - 1) + 1))
            px = np.stack([xs.ravel() + .5, ys.ravel() + .5], 1)
            l1 = ((b[0] - px[:, 0]) * (cc[1] - px[:, 1]) - (b[1] - px[:, 1]) * (cc[0] - px[:, 0])) / cross
            l2 = ((cc[0] - px[:, 0]) * (a[1] - px[:, 1]) - (cc[1] - px[:, 1]) * (a[0] - px[:, 0])) / cross
            l3 = 1 - l1 - l2
            ins = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            if not ins.any():
                continue
            L = np.stack([l1, l2, l3], 1)[ins]
            pp = px[ins].astype(int)
            z = L @ cam[:, 2]
            uv = L @ np.array(uvs, float)
            vv = np.clip(uv[:, 1].astype(int), 0, band.shape[0] - 1)
            cid = mt & 0x7eff
            if mt & 0x8000:
                raw = vram[cid >> 6, (cid & 63) * 16 + i8[vv, np.clip(uv[:, 0].astype(int), 0, i8.shape[1] - 1)]]
            else:
                raw = vram[cid >> 6, (cid & 63) * 16 + i4[vv, np.clip(uv[:, 0].astype(int), 0, i4.shape[1] - 1)]]
            col = np.stack([(raw & 31) * 8, ((raw >> 5) & 31) * 8, ((raw >> 10) & 31) * 8], 1).astype(np.uint8)
            vis = raw != 0
            if ROWS:
                rc = np.array([(rw * 53) % 255, (rw * 97) % 255, (rw * 151) % 255], np.uint8)
                col = np.repeat(rc[None], len(col), 0)
            yy, xx = pp[:, 1], pp[:, 0]
            better = ((z < zb[yy, xx]) | PAINTER) & vis
            zb[yy[better], xx[better]] = z[better]
            img[yy[better], xx[better]] = col[better]
        imgs.append(img)
    out = Image.new("RGB", (sum(i.shape[1] for i in imgs), S))
    x = 0
    for i in imgs:
        out.paste(Image.fromarray(i), (x, 0))
        x += i.shape[1]
    out.save(out_png)
    print(f"{len(full)} full frames, {len(pick)} drawn")


if __name__ == "__main__":
    main()
