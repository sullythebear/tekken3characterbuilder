"""Anatomy debug render: what the converter makes of a model (anatomy.analyse), as a PNG -
body regions from the front, the side and the back with the joints and the skeleton, the
Tekken rows, and the uncertain regions striped. The same data as the builder's anatomy view.

  anatomy_render.py MODEL out.png [--game G]
  (a character's source.*: its texture images, colours and hand-placed joints are used too)"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
GAME = Path(sys.argv[sys.argv.index("--game") + 1]) if "--game" in sys.argv else \
    Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
sys.path[:0] = [str(HERE)]
import regress  # noqa: E402  (puts the builder's app on the path, reads a character's extras)
import anatomy as AN  # noqa: E402
import direct_import as DI  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SIZE = 520


def hexrgb(h):
    return np.array([int(h[k:k + 2], 16) for k in (1, 3, 5)], float)


def panel(P, T, col, yaw, lo, hi, joints=None, links=None, stripes=None, title=""):
    a = np.radians(yaw)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    Q = P @ R.T
    sc = (SIZE - 40) / max(hi - lo, 1e-9)
    cx = (Q[:, 0].min() + Q[:, 0].max()) / 2
    X = (Q[:, 0] - cx) * sc + SIZE / 2
    Y = (hi - Q[:, 1]) * sc + 30
    img = np.zeros((SIZE, SIZE, 3))
    img[:] = (24, 26, 38)
    zb = np.full((SIZE, SIZE), -np.inf)
    n = np.cross(Q[T[:, 1]] - Q[T[:, 0]], Q[T[:, 2]] - Q[T[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    shade = 0.45 + 0.55 * np.abs(n @ np.array([0.3, 0.4, 0.86]))
    for i, t in enumerate(T):
        xs, ys = X[t], Y[t]
        x0, x1 = int(max(xs.min(), 0)), int(min(xs.max(), SIZE - 1))
        y0, y1 = int(max(ys.min(), 0)), int(min(ys.max(), SIZE - 1))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (ys[1] - ys[0]) * (xs[2] - xs[0])
        if abs(d) < 1e-9:
            continue
        l1 = ((xs[2] - gx) * (ys[0] - gy) - (ys[2] - gy) * (xs[0] - gx)) / d
        l2 = ((xs[0] - gx) * (ys[1] - gy) - (ys[0] - gy) * (xs[1] - gx)) / d
        l0 = 1 - l1 - l2
        ins = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        z = l0 * Q[t[1], 2] + l1 * Q[t[2], 2] + l2 * Q[t[0], 2]
        yy, xx = (gy[ins] - .5).astype(int), (gx[ins] - .5).astype(int)
        zz = z[ins]
        ok = zz > zb[yy, xx]
        c = col[i] * shade[i]
        if stripes is not None and stripes[i]:
            band = ((xx[ok] + yy[ok]) // 4) % 2 == 0
            cc = np.where(band[:, None], np.array([255, 0, 200.0]), c)
            img[yy[ok], xx[ok]] = cc
        else:
            img[yy[ok], xx[ok]] = c
        zb[yy[ok], xx[ok]] = zz[ok]
    im = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    if joints:
        J = {k: (np.array(v) @ R.T) for k, v in joints.items()}
        pt = lambda v: ((v[0] - cx) * sc + SIZE / 2, (hi - v[1]) * sc + 30)
        for a_, b_ in links or []:
            dr.line([pt(J[a_]), pt(J[b_])], fill=(255, 255, 255), width=2)
        for k, v in J.items():
            x, y = pt(v)
            dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 255, 255), outline=(0, 0, 0))
    dr.text((8, 8), title, fill=(230, 230, 230))
    return im


def main():
    f = Path(sys.argv[1])
    out = Path(sys.argv[2])
    regress._beside(f)
    src = DI.load(f)
    a = AN.analyse(src)
    P, T = np.array(a["P"]), np.array(a["T"])
    reg = np.array(a["region"])
    cols = np.array([hexrgb(r["colour"]) for r in a["regions"]])[reg]
    rowpal = np.array([hexrgb("#333333")] + [np.array([(r * 53) % 255, (r * 97) % 255, (r * 151) % 255], float)
                                              for r in range(1, 27)])
    rcols = rowpal[np.array(a["row"])]
    lo, hi = P[:, 1].min(), P[:, 1].max()
    unsure = np.array(a["uncertain"]).astype(bool)
    ims = [panel(P, T, cols, y, lo, hi, a["joints"], a["links"], unsure, f"regions {nm}")
           for y, nm in ((0, "front"), (90, "side"), (180, "back"))]
    ims.append(panel(P, T, rcols, 0, lo, hi, title="Tekken rows (front)"))
    W = sum(i.width for i in ims)
    sheet = Image.new("RGB", (W, SIZE + 150), (16, 16, 24))
    x = 0
    for i in ims:
        sheet.paste(i, (x, 0))
        x += i.width
    dr = ImageDraw.Draw(sheet)
    for k, r in enumerate(a["regions"]):
        x0, y0 = 10 + (k % 8) * 180, SIZE + 10 + (k // 8) * 22
        dr.rectangle([x0, y0, x0 + 14, y0 + 14], fill=tuple(int(c) for c in hexrgb(r["colour"])))
        dr.text((x0 + 20, y0 + 2), f"{r['name']} ({a['counts'][r['name']]})", fill=(220, 220, 220))
    dr.text((10, SIZE + 60), ("automatic rig" if a["auto_rig"] else "skeleton from the file") +
            " - striped: uncertain - white: joints and skeleton", fill=(200, 200, 200))
    for k, fl in enumerate(a["flags"][:4]):
        dr.text((10, SIZE + 80 + 16 * k), "! " + fl, fill=(255, 140, 120))
    sheet.save(out)
    print(out, a["counts"], a["flags"][:3])


if __name__ == "__main__":
    main()
