"""Render a source model (.fbx/.glb, as direct_import.load reads it) with its own textures,
orthographic, from several yaws: to see what an import should look like (Expanded's venv).

  mesh_render.py GAME MODEL out.png [--yaws 0,90,180] [--size 600] [--crop head]"""
import io
import sys
from pathlib import Path
import numpy as np


def render(P, T, UV, MAT, textures, yaws=(0,), size=600, lo_hi=None):
    from PIL import Image
    tex = {}
    for k, v in textures.items():
        tex[k] = np.asarray(Image.open(io.BytesIO(v)).convert("RGBA"))
    first = next(iter(tex.values())) if tex else np.full((4, 4, 4), 200, np.uint8)
    imgs = []
    for yaw in yaws:
        a = np.radians(yaw)
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        Q = P @ R.T
        used = Q[np.unique(T)]
        lo, hi = (used.min(0), used.max(0)) if lo_hi is None else lo_hi
        sc = (size - 20) / max(hi[1] - lo[1], hi[0] - lo[0])
        Wd = int((hi[0] - lo[0]) * sc) + 20
        img = np.zeros((size, Wd, 3), np.uint8)
        img[:] = (20, 25, 50)
        zb = np.full((size, Wd), -np.inf)
        X = (Q[:, 0] - lo[0]) * sc + 10
        Y = (hi[1] - Q[:, 1]) * sc + 10
        for ti, t in enumerate(T):
            a_, b_, c_ = t
            xy = np.array([[X[a_], Y[a_]], [X[b_], Y[b_]], [X[c_], Y[c_]]])
            cross = (xy[1, 0] - xy[0, 0]) * (xy[2, 1] - xy[0, 1]) - (xy[1, 1] - xy[0, 1]) * (xy[2, 0] - xy[0, 0])
            if abs(cross) < 1e-9:
                continue
            x0, y0 = np.floor(xy.min(0)).astype(int)
            x1, y1 = np.ceil(xy.max(0)).astype(int)
            xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, Wd - 1) + 1), np.arange(max(y0, 0), min(y1, size - 1) + 1))
            px = np.stack([xs.ravel() + .5, ys.ravel() + .5], 1)
            l1 = ((xy[1, 0] - px[:, 0]) * (xy[2, 1] - px[:, 1]) - (xy[1, 1] - px[:, 1]) * (xy[2, 0] - px[:, 0])) / cross
            l2 = ((xy[2, 0] - px[:, 0]) * (xy[0, 1] - px[:, 1]) - (xy[2, 1] - px[:, 1]) * (xy[0, 0] - px[:, 0])) / cross
            l3 = 1 - l1 - l2
            ins = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            if not ins.any():
                continue
            L = np.stack([l1, l2, l3], 1)[ins]
            pp = px[ins].astype(int)
            z = L @ Q[t, 2]
            uv = L @ UV[t]
            im = tex.get(int(MAT[ti]) if MAT is not None else 0, first)
            h, w = im.shape[:2]
            col = im[np.clip((uv[:, 1] * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int) % w, 0, w - 1)]
            ok = col[:, 3] > 128
            yy, xx = pp[:, 1], pp[:, 0]
            better = (z > zb[yy, xx]) & ok
            zb[yy[better], xx[better]] = z[better]
            img[yy[better], xx[better]] = col[better, :3]
        imgs.append(img)
    out = Image.new("RGB", (sum(i.shape[1] for i in imgs), size))
    x = 0
    for i in imgs:
        out.paste(Image.fromarray(i), (x, 0))
        x += i.shape[1]
    return out


def main():
    game = Path(sys.argv[1])
    sys.path.insert(0, str(game / "character-builder" / "app"))
    import direct_import as DI
    src = DI.load(Path(sys.argv[2]))
    yaws = [float(y) for y in sys.argv[sys.argv.index("--yaws") + 1].split(",")] if "--yaws" in sys.argv else [0, 90, 180]
    size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 600
    P, T, UV = src["P"], src["T"], src["UV"]
    if "--crop" in sys.argv:                     # the top 18 % (head)
        y1 = P[:, 1].max()
        y0 = y1 - 0.18 * np.ptp(P[:, 1])
        keep = (P[T][:, :, 1] > y0).all(1)
        T = T[keep]
        MAT = src["MAT"][keep]
    else:
        MAT = src["MAT"]
    render(P, T, UV, MAT, src["textures"], yaws, size).save(sys.argv[3])


if __name__ == "__main__":
    main()
