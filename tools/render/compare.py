"""Side by side: a stock model and an own model, same renderer (gouraud from stored normals,
textures with CLUTs, transparency), same pose, same scale."""
import sys, struct, base64, numpy as np
from pathlib import Path
sys.path.insert(0, r"D:/Tekken 3 Recompiled/tekken3-expanded-1.1.3/character-builder/app")
import model_export as X
R = Path(r"D:/Tekken 3 Recompiled/tekken3-expanded-1.1.3"); X.setup(R)
from PIL import Image
import anim_model as A
from fmt import row, block, parse_b, parse_c_ps1, parse_a

def tex_stock(mid):
    j = X.export_model(R, mid)
    band = np.frombuffer(base64.b64decode(j["band"]), "<u2").reshape(256, j["band_words"])
    vram = np.zeros((8, 1024), int)
    for k, v in j["cluts"].items():
        k = int(k); vram[k >> 6, (k & 63) * 16:(k & 63) * 16 + len(v)] = v
    return band, vram

def tex_own(f, t):
    w, h, cid, nc = struct.unpack_from("<4H", f, t + 4)
    vram = np.zeros((8, 1024), int); at = t + 12
    for r in range(nc if cid == 0xFFFF else 1):
        rid, rc = (struct.unpack_from("<2H", f, at) if cid == 0xFFFF else (cid, nc))
        if cid == 0xFFFF: at += 4
        vram[rid >> 6, (rid & 63) * 16:(rid & 63) * 16 + rc] = struct.unpack_from(f"<{rc}H", f, at); at += 2 * rc
    return np.frombuffer(f, "<u2", w * h, at).reshape(h, w), vram

def load(spec):
    if spec.isdigit():
        mid = int(spec); m = X.records(R, [X.FIRST_MODEL_RECORD + 4 * mid])[X.FIRST_MODEL_RECORD + 4 * mid]
        return m, tex_stock(mid)
    f = open(spec, "rb").read(); size, count = struct.unpack_from("<II", f, 8)
    m = f[16 + X.MODEL_HEADER:16 + X.MODEL_HEADER + size]
    return m, tex_own(f, 16 + X.MODEL_HEADER + size + 4 * count)

def tris_of(m, pose):
    stance = X.stance_pose(R); fight = X.world(m, stance)
    W = X.facing(fight) if pose == "fight" else X.facing(X.tweaked(m, stance, X.world(m, stance, X.stand_pose(m, fight))))
    out = []
    for r, slots in X.bind(m).items():
        wd = row(m, r); prims = parse_c_ps1(block(m, wd[2])); i = 0
        nb = parse_a(block(m, wd[0])); nl = [None] * (len(nb["g1"]) + len(nb["g2"])) + [np.array(v[:3]) / 4096 for v in nb["verts"]]
        Rr = W[{2: 1, 4: 3, 20: 19}.get(r, r)][0]
        for k, fam in enumerate(parse_b(block(m, wd[1]))):
            for rec in fam:
                c = A.prim_verts(k, rec); _, mat, uv = prims[i]; i += 1
                ws = struct.unpack_from(f"<{len(rec)//4}I", rec)
                if k == 2: ni = [(ws[1] >> s_) & 0x1fc for s_ in (0, 7, 16)]
                elif k == 3: ni = [ws[1] & 0x1fc] + [(ws[2] >> s_) & 0x1fc for s_ in (0, 7, 16)]
                else: ni = [ws[1] & 0x1fc] * len(c)
                ns = [Rr @ nl[x // 4 - 1] if 0 < x // 4 <= len(nl) and nl[x // 4 - 1] is not None else np.array([0, 0, 1.0]) for x in ni]
                for a, b, cc in ([(0, 1, 2)] if len(c) == 3 else [(0, 1, 2), (1, 3, 2)]):
                    if any(c[j] >= len(slots) or slots[c[j]] is None for j in (a, b, cc)) or mat is None: continue
                    pts = [slots[c[j]] for j in (a, b, cc)]
                    out.append(([W[s[0]][0] @ np.array(s[1], float) + W[s[0]][1] for s in pts], [uv[j] for j in (a, b, cc)], mat, [ns[j] for j in (a, b, cc)]))
    return out

def render(spec, pose, yaw, S, bounds=None):
    m, (band, vram) = load(spec)
    T = tris_of(m, pose)
    # the game's camera looks along +Z with Y down, so +X is screen right as seen from -Z; this
    # view is from +Z, so X turns over too (else the picture is a mirror image)
    P = np.array([t[0] for t in T], float); P[:, :, 1] *= -1; P[:, :, 0] *= -1
    N = np.array([t[3] for t in T], float); N[:, :, 1] *= -1; N[:, :, 0] *= -1
    U = np.array([t[1] for t in T], float); M = [t[2] for t in T]
    c, s = np.cos(yaw), np.sin(yaw); Rz = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    P = P @ Rz.T; N = N @ Rz.T
    mn, mx = bounds
    sc = (S - 20) / (mx[1] - mn[1]); Wd = int(S * 0.6)
    img = np.zeros((S, Wd, 3), np.uint8); img[:] = (20, 25, 50); zb = np.full((S, Wd), -1e9)
    rgbv = np.stack([(vram & 31) * 8, ((vram >> 5) & 31) * 8, ((vram >> 10) & 31) * 8], 2)
    light = np.array([0.4, 0.5, 0.75]); light /= np.linalg.norm(light)
    i4 = np.stack([(band >> (4 * k)) & 15 for k in range(4)], 2).reshape(band.shape[0], -1)
    i8 = np.stack([band & 255, band >> 8], 2).reshape(band.shape[0], -1)
    for j in range(len(P)):
        q = P[j]; xy = np.stack([(q[:, 0]) * sc + Wd / 2, (mx[1] - q[:, 1]) * sc + 10], 1)
        a, b, cc = xy; cross = (b[0]-a[0])*(cc[1]-a[1]) - (b[1]-a[1])*(cc[0]-a[0])
        if cross <= 0: continue
        x0, y0 = np.floor(xy.min(0)).astype(int); x1, y1 = np.ceil(xy.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0,0), min(x1, Wd-1)+1), np.arange(max(y0,0), min(y1, S-1)+1))
        px = np.stack([xs.ravel()+.5, ys.ravel()+.5], 1)
        l1 = ((b[0]-px[:,0])*(cc[1]-px[:,1]) - (b[1]-px[:,1])*(cc[0]-px[:,0])) / cross
        l2 = ((cc[0]-px[:,0])*(a[1]-px[:,1]) - (cc[1]-px[:,1])*(a[0]-px[:,0])) / cross
        l3 = 1-l1-l2; ins = (l1>=0)&(l2>=0)&(l3>=0)
        if not ins.any(): continue
        L = np.stack([l1,l2,l3],1)[ins]; pp = px[ins].astype(int); z = L @ q[:, 2]; uv = L @ U[j]
        mt = M[j]; vv = np.clip(uv[:, 1].astype(int), 0, band.shape[0]-1)
        page = 1 if (mt & 0x100) and spec.isdigit() else 0
        if mt & 0x8000:
            idx = i8[vv, np.clip(uv[:, 0].astype(int) + page * 128, 0, i8.shape[1]-1)]; cid = mt & 0x7eff
            raw = vram[cid >> 6, (cid & 63) * 16 + idx]
        else:
            idx = i4[vv, np.clip(uv[:, 0].astype(int) + page * 256, 0, i4.shape[1]-1)]; cid = mt & 0x7eff
            raw = vram[cid >> 6, (cid & 63) * 16 + idx]
        vis = raw != 0
        col = np.stack([(raw & 31) * 8, ((raw >> 5) & 31) * 8, ((raw >> 10) & 31) * 8], 1)
        lit = L @ (np.clip(N[j] @ light, 0, 1) * 0.75 + 0.35)
        col = np.clip(col * lit[:, None], 0, 255).astype(np.uint8)
        yy, xx = pp[:,1], pp[:,0]; better = (z > zb[yy,xx]) & vis
        zb[yy[better], xx[better]] = z[better]; img[yy[better], xx[better]] = col[better]
    return img

def bounds_of(specs, pose):
    lo, hi = np.full(3, 1e9), np.full(3, -1e9)
    for sp in specs:
        m, _ = load(sp)
        P = np.array([p for t in tris_of(m, pose) for p in t[0]]); P[:, 1] *= -1; P[:, 0] *= -1
        lo = np.minimum(lo, P.min(0)); hi = np.maximum(hi, P.max(0))
    return lo, hi

if __name__ == "__main__":
    specs = sys.argv[1].split(","); out = sys.argv[2]; S = int(sys.argv[3]) if len(sys.argv) > 3 else 600
    rows = []
    for pose in ("stand", "fight"):
        b = bounds_of(specs, pose)
        rows.append(np.concatenate([render(sp, pose, yaw, S, b) for sp in specs for yaw in (0, np.pi * 0.75)], 1))
    Image.fromarray(np.concatenate(rows, 0)).save(out)
