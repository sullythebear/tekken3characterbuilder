"""Render a fighter exactly as the game posed it, at high resolution (Expanded's venv).

Input: live/probe.bin from `t3live.py fight --probe` (src/tekken3_ttt1_renderer.c records, per
call of the native vertex transformer 0x80036CAC: header 8 u32 [tag, seen, m1, m2, a0..a3],
GTE control 32 u32, GTE data 32 u32, scratchpad 256, two caches 2 x 256, work 4 x 256 words).
a0 = model + 16 + row * 56 + 56 - 56... (row = (a0 - model - 16) / 56). The GTE rotation and
translation at entry put the row's own vertices in camera space.

  probe_render.py GAME model.bin out.png [--frames 6] [--size 700]"""
import struct
import sys
from pathlib import Path
import numpy as np

import os
ROWS = bool(os.environ.get("ROWS"))
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
    log = (game / "character-builder" / "live" / "game-log.txt").read_text(errors="replace")
    import re
    addr = int(re.findall(r"installed at ([0-9A-F]{8})", log)[-1], 16)
    fr = frames(game / "character-builder" / "live" / "probe.bin", addr)
    full = [f for f in fr if all(r in f for r in (1, 3, 5, 12, 19))]
    if "--pick" in sys.argv:
        pick = [full[int(x)] for x in sys.argv[sys.argv.index("--pick") + 1].split(",")]
    else:
        pick = [full[int(i)] for i in np.linspace(0, len(full) - 1, min(nshow, len(full)))]
    bind = X.bind(m)
    i4 = np.stack([(band >> (4 * k)) & 15 for k in range(4)], 2).reshape(band.shape[0], -1)
    i8 = np.stack([band & 255, band >> 8], 2).reshape(band.shape[0], -1)
    imgs = []
    for f in pick:
        tris = []
        for r, slots in bind.items():
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
                        cam = [f[p[0]][0] @ np.array(p[1], float) + f[p[0]][1] for p in pts]
                        tris.append((cam, [uv[j] for j in (a, b, cc)], mat, pts[0][0]))
        P = np.array([t[0] for t in tris])
        sx = P[:, :, 0] / P[:, :, 2]
        sy = P[:, :, 1] / P[:, :, 2]
        lo = np.array([sx.min(), sy.min()])
        hi = np.array([sx.max(), sy.max()])
        sc = (S - 20) / max(hi - lo)
        W_ = int((hi - lo)[0] * sc) + 20
        img = np.zeros((S, W_, 3), np.uint8)
        img[:] = (20, 25, 50)
        zb = np.full((S, W_), np.inf)
        for (cam, uvs, mt, rw) in tris:
            cam = np.array(cam)
            xy = np.stack([(cam[:, 0] / cam[:, 2] - lo[0]) * sc + 10, (cam[:, 1] / cam[:, 2] - lo[1]) * sc + 10], 1)
            a, b, cc = xy
            cross = (b[0] - a[0]) * (cc[1] - a[1]) - (b[1] - a[1]) * (cc[0] - a[0])
            if cross <= 0:                       # the game culls these (back faces)
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
            better = (z < zb[yy, xx]) & vis
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
