"""Stage Lab: a colour variant of one of Tekken 3's stages (runs with Expanded's venv).

A stage's textures are disc record 36 + arena (Paul's street 0 ... Dr. B's 14; tested 2026-10-16:
the CLUTs of records 36 and 49 sit in VRAM where their TIMs say during fights on arenas 0 and
13). The variant recolours those CLUTs; game patch 19 puts them over the stage's own colours
during a fight on that arena (<Key>-T3-stage.bin).

  stage_look.py --root R --arena 13 --look night --out Cbx-T3-stage.bin [--preview sheet.png]
  stage_look.py --root R --arena 13 [--look night] --preview view.png --view front
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np

import model_export as X

FIRST_STAGE_RECORD = 36
STAGES = 16
# (red, green, blue) multipliers and a grey mix per look
LOOKS = {"night": ((0.42, 0.5, 0.85), 0.25), "sunset": ((1.15, 0.78, 0.55), 0.0),
         "dusk": ((0.8, 0.58, 0.95), 0.15), "mono": ((1.0, 1.0, 1.0), 1.0),
         "ice": ((0.75, 0.95, 1.2), 0.35), "inferno": ((1.25, 0.6, 0.4), 0.2)}


def custom_look(tint: str, strength: int) -> tuple:
    """A look from a colour (RRGGBB) and a strength (0..100): the colours lean towards it."""
    s = max(0, min(100, int(strength))) / 100
    rgb = [int(tint[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    avg = max(sum(rgb) / 3, 0.05)
    return tuple((1 - s) + s * min(c / avg, 2.0) * (0.55 + 0.45 * avg) for c in rgb), 0.35 * s


def recolour(colours: np.ndarray, look) -> np.ndarray:
    """PS1 colours (u16) through a look (a LOOKS name or a custom_look tuple); 0 (see-through)
    and the STP bit are kept."""
    mul, grey = LOOKS[look] if isinstance(look, str) else look
    r = (colours & 31).astype(float); g = ((colours >> 5) & 31).astype(float); b = ((colours >> 10) & 31).astype(float)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    r, g, b = (lum + (c - lum) * (1 - grey) for c in (r, g, b))
    out = [np.clip(np.round(c * m), 0, 31).astype(np.uint16) for c, m in zip((r, g, b), mul)]
    new = (colours & 0x8000) | out[0] | (out[1] << 5) | (out[2] << 10)
    new = np.where(colours == 0, 0, np.where(new == 0, 0x8000 | (colours & 0x8000), new))   # black stays opaque
    return new.astype(np.uint16)


def stage_tims(root: Path, arena: int):
    from tim_tool import scan_tims
    rid = FIRST_STAGE_RECORD + arena
    data = X.records(root, [rid])[rid]
    return data, list(scan_tims(data))


def variant(root: Path, arena: int, look: str) -> bytes:
    """<Key>-T3-stage.bin: per CLUT row x, y, count, original colours, new colours."""
    data, tims = stage_tims(root, arena)
    latest = {}                       # several TIMs can load a CLUT to one place: the last one stays
    for t in tims:
        c = t.clut
        if c is None:
            continue
        cols = np.frombuffer(data[c.offset + 12:c.offset + 12 + c.width_words * c.height * 2], "<u2").reshape(c.height, c.width_words)
        for k in range(c.height):
            if c.x + c.width_words > 1024 or c.y + k >= 512:
                continue
            for s in range(0, c.width_words, 256):
                latest[(c.x + s, c.y + k)] = cols[k, s:s + 256].astype(np.uint16)
    rows = [(x, y, orig, recolour(orig, look)) for (x, y), orig in latest.items()]
    out = b"T3ST" + struct.pack("<HHH", 1, arena, len(rows))
    for x, y, orig, new in rows:
        out += struct.pack("<HHH", x, y, len(orig)) + orig.astype("<u2").tobytes() + new.astype("<u2").tobytes()
    return out


def preview(root: Path, arena: int, look: str | None, out: Path, width: int = 640) -> None:
    """A sheet of the stage's largest textures as the game colours them (with the look, if any)."""
    from PIL import Image
    data, tims = stage_tims(root, arena)
    pieces = []
    for t in tims:
        im, c = t.image, t.clut
        if c is None or t.mode not in (0, 1):
            continue
        words = np.frombuffer(data[im.offset + 12:im.offset + 12 + im.width_words * im.height * 2], "<u2").reshape(im.height, im.width_words)
        if t.mode == 0:
            idx = np.stack([(words >> (4 * k)) & 15 for k in range(4)], 2).reshape(im.height, -1)
        else:
            idx = np.stack([words & 255, words >> 8], 2).reshape(im.height, -1)
        pal = np.frombuffer(data[c.offset + 12:c.offset + 12 + c.width_words * 2], "<u2").astype(np.uint16)
        if look:
            pal = recolour(pal, look)
        px = pal[np.clip(idx, 0, len(pal) - 1)]
        rgb = np.stack([(px & 31) << 3, ((px >> 5) & 31) << 3, ((px >> 10) & 31) << 3], 2).astype(np.uint8)
        pieces.append(Image.fromarray(rgb))
    pieces.sort(key=lambda p: -p.width * p.height)
    pieces = pieces[:24]
    sheet, x, y, row_h = Image.new("RGB", (width, 2000), (20, 20, 26)), 0, 0, 0
    for p in pieces:
        if x + p.width > width:
            x, y, row_h = 0, y + row_h + 4, 0
        sheet.paste(p, (x, y))
        x, row_h = x + p.width + 4, max(row_h, p.height)
    sheet.crop((0, 0, width, min(2000, y + row_h))).save(out)


# The stage's scenery model: disc record 56 + arena (arenas 0..14; tested 2026-10-19 by rendering
# all of them with their textures). u32 at +8: 36 pieces (a 6 x 6 grid over -1200..1200), each
# 7 u32 at 12 + 28 * i: vertex offset, vertex count, ?, primitive count, primitive offset, the
# count again, 0 (offsets from +12). Vertices are 4 i16 (x, y, z, 0; y up is negative). The
# primitives are GPU packets without the tag word: code 0x20/0x28 flat triangle/quad (rgb, code,
# 3/4 vertex indices; 8 bytes), 0x24/0x2C textured (rgb, code, uv+clut, uv+tpage, uv, uv,
# indices; 20 bytes). Code bit 1: semi-transparent. The floor is not part of it (floor_triangles).
FIRST_STAGE_MODEL = 56
STAGE_MODELS = 15
VIEWS = {"front": 0.0, "right": 1.5708, "back": 3.1416, "left": -1.5708}


def stage_triangles(model: bytes) -> list:
    """[(3 vertices, 3 uvs or None, clut, tpage, rgb, semi)] of a stage model."""
    tris = []
    for i in range(struct.unpack_from("<I", model, 8)[0]):
        row = struct.unpack_from("<7I", model, 12 + i * 28)
        verts = [struct.unpack_from("<4h", model, 12 + row[0] + j * 8)[:3] for j in range(row[1])]
        off = 12 + row[4]
        for _ in range(row[3]):
            code = model[off + 3] & 0xFC
            if code in (0x20, 0x28):
                k, size, uv, clut, tpage = (3 if code == 0x20 else 4), 8, None, 0, 0
                idx = list(model[off + 4:off + 4 + k])
            elif code in (0x24, 0x2C):
                k, size = (3 if code == 0x24 else 4), 20
                q = model[off:off + 20]
                idx = list(q[16:16 + k])
                uv = [(q[4], q[5]), (q[8], q[9]), (q[12], q[13]), (q[14], q[15])][:k]
                clut, tpage = struct.unpack_from("<HxxH", q, 6)
            else:
                break                                    # an unknown packet: the rest of the piece is skipped
            rgb, semi = tuple(model[off:off + 3]), bool(model[off + 3] & 2)
            off += size
            if max(idx) >= len(verts):
                continue
            for a, b, c in ((0, 1, 2),) if k == 3 else ((0, 1, 2), (1, 3, 2)):
                tris.append(([verts[idx[a]], verts[idx[b]], verts[idx[c]]],
                             None if uv is None else [uv[a], uv[b], uv[c]], clut, tpage, rgb, semi))
    return tris


def floor_triangles(tims, scenery: list, cell: int = 120) -> list:
    """The floor (not in the scenery model) as stage_triangles tuples: the stage's 4-bit TIMs that
    no scenery primitive uses are its floor tiles (sand on Gon's beach, grass in the forest;
    tested 2026-10-19). How the game lays them out is not known: here they repeat in rows of
    cells over -1200..1200, which is only an approximation."""
    used = set()
    for _, uv, clut, tpage, _, _ in scenery:
        if uv is None:
            continue
        mode, bx, by = (tpage >> 7) & 3, (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
        for u, v in uv:
            wx = bx + (u // 4 if mode == 0 else u // 2 if mode == 1 else u)
            for i, tim in enumerate(tims):
                im = tim.image
                if im.x <= wx < im.x + im.width_words and im.y <= by + v < im.y + im.height:
                    used.add(i)
    tiles = [tim for i, tim in enumerate(tims) if i not in used and tim.mode == 0 and tim.clut is not None
             and tim.image.width_words <= 64]
    tiles.sort(key=lambda tim: (tim.image.x, tim.image.y))
    out = []
    for n, z in enumerate(range(-1200, 1200, cell)):
        if not tiles:
            break
        tim = tiles[n // 2 % len(tiles)]
        im, c = tim.image, tim.clut
        bx, by = im.x // 64 * 64, im.y // 256 * 256
        tpage, clut = (im.x // 64) | ((im.y // 256) << 4), (c.x >> 4) | (c.y << 6)
        u0, v0 = (im.x - bx) * 4, im.y - by
        tw, th = im.width_words * 4 // 2, min(im.height, 64) // 2   # a tile spans 2 x 2 cells
        vz = v0 + th * (1 - n % 2)
        for k, x in enumerate(range(-1200, 1200, cell)):
            uu = u0 + tw * (k % 2)
            a, b, d, e = (x, 0, z), (x + cell, 0, z), (x, 0, z + cell), (x + cell, 0, z + cell)
            s0, s1, t0, t1 = uu, uu + tw - 1, vz, vz + th - 1
            out.append(([a, b, d], [(s0, t1), (s1, t1), (s0, t0)], clut, tpage, (128, 128, 128), False))
            out.append(([b, e, d], [(s1, t1), (s1, t0), (s0, t0)], clut, tpage, (128, 128, 128), False))
    return out


def arena_view(root: Path, arena: int, look, out: Path, view: str = "front", size=(960, 540)) -> None:
    """PNG of the stage as seen from the fighters' place (yaw from VIEWS), with the look, if any.
    A software render in the PS1's way: textures through their CLUTs, colour 0 see-through."""
    from PIL import Image
    if not 0 <= arena < STAGE_MODELS:
        raise SystemExit("ERROR: this stage has no scenery model")
    data, tims = stage_tims(root, arena)
    mid = FIRST_STAGE_MODEL + arena
    model = X.records(root, [mid])[mid]
    vram = np.zeros((512, 1024), np.uint16)
    loaded = np.zeros((512, 1024), bool)            # texels outside the stage's TIMs are not drawn
    for t in tims:                                       # as the game loads them: the last one stays
        for b, is_clut in ((t.image, False), (t.clut, True)):
            if b is None:
                continue
            px = np.frombuffer(data, "<u2", b.width_words * b.height, b.offset + 12).reshape(b.height, b.width_words)
            if is_clut and look:
                px = recolour(px.astype(np.uint16), look)
            h, w = min(b.height, 512 - b.y), min(b.width_words, 1024 - b.x)
            vram[b.y:b.y + h, b.x:b.x + w] = px[:h, :w]
            loaded[b.y:b.y + h, b.x:b.x + w] |= not is_clut
    W, H = size
    yaw = VIEWS.get(view, 0.0)
    cy_, sy_ = np.cos(yaw), np.sin(yaw)
    pitch, focal = 0.12, 0.73 * W
    cp, sp = np.cos(pitch), np.sin(pitch)
    eye = np.array([0.0, -250.0, -700.0])
    img = np.zeros((H, W, 3))
    img[:] = (22, 22, 28)
    zb = np.full((H, W), np.inf)
    scenery = stage_triangles(model)
    for xyz, uv, clut, tpage, rgb, semi in floor_triangles(tims, scenery) + scenery:
        P = np.array(xyz, float)
        P = np.stack([cy_ * P[:, 0] - sy_ * P[:, 2], P[:, 1], sy_ * P[:, 0] + cy_ * P[:, 2]], 1) - eye
        y = P[:, 1] * cp + P[:, 2] * sp
        z = -P[:, 1] * sp + P[:, 2] * cp
        if (z < 30).any():
            continue
        xy = np.stack([W / 2 + focal * P[:, 0] / z, H / 2 + focal * y / z], 1)
        cr = (xy[1, 0] - xy[0, 0]) * (xy[2, 1] - xy[0, 1]) - (xy[1, 1] - xy[0, 1]) * (xy[2, 0] - xy[0, 0])
        if abs(cr) < 1e-9:
            continue
        x0, y0 = np.maximum(np.floor(xy.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(xy.max(0)).astype(int), [W - 1, H - 1])
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        px = np.stack([gx.ravel() + .5, gy.ravel() + .5], 1)
        l1 = ((xy[1, 0] - px[:, 0]) * (xy[2, 1] - px[:, 1]) - (xy[1, 1] - px[:, 1]) * (xy[2, 0] - px[:, 0])) / cr
        l2 = ((xy[2, 0] - px[:, 0]) * (xy[0, 1] - px[:, 1]) - (xy[2, 1] - px[:, 1]) * (xy[0, 0] - px[:, 0])) / cr
        inside = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        if not inside.any():
            continue
        L = np.stack([l1, l2, 1 - l1 - l2], 1)[inside] / z
        depth = 1 / L.sum(1)
        pp = px[inside].astype(int)
        if uv is None:
            raw = np.full(len(pp), 0x7FFF, np.uint16)
            shade = np.array(rgb, float) / 255
        else:
            U = (L @ np.array(uv, float)) * depth[:, None]   # perspective-correct texture coordinates
            if np.ptp(np.array(uv), 0).max() <= 1:            # one or two texels: a plain colour (the sky)
                U = np.repeat(np.array(uv, float).min(0)[None], len(U), 0)
            u, v = np.clip(U[:, 0].astype(int), 0, 255), np.clip(U[:, 1].astype(int), 0, 255)
            mode, bx, by = (tpage >> 7) & 3, (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
            cx, cy = (clut & 63) * 16, (clut >> 6) & 511
            wx = np.minimum(bx + (u // 4 if mode == 0 else u // 2 if mode == 1 else u), 1023)
            seen = loaded[by + v, wx]
            if mode == 0:
                ix = (vram[by + v, np.minimum(bx + u // 4, 1023)] >> ((u % 4) * 4)) & 15
                raw = vram[cy, np.minimum(cx + ix, 1023)]
            elif mode == 1:
                ix = (vram[by + v, np.minimum(bx + u // 2, 1023)] >> ((u % 2) * 8)) & 255
                raw = vram[cy, np.minimum(cx + ix, 1023)]
            else:
                raw = vram[by + v, np.minimum(bx + u, 1023)]
            raw = np.where(seen, raw, 0)
            shade = np.array(rgb, float) / 128
        colour = np.stack([raw & 31, (raw >> 5) & 31, (raw >> 10) & 31], 1) * (255 / 31) * shade
        yi, xi = pp[:, 1], pp[:, 0]
        near = (depth < zb[yi, xi]) & (raw != 0)
        if semi:                                         # half the background, half the texture
            img[yi[near], xi[near]] = (img[yi[near], xi[near]] + colour[near]) / 2
        else:
            zb[yi[near], xi[near]] = depth[near]
            img[yi[near], xi[near]] = colour[near]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--arena", type=int, required=True)
    ap.add_argument("--look", choices=sorted(LOOKS) + ["custom"])
    ap.add_argument("--tint", default="ff8040", help="custom look: RRGGBB")
    ap.add_argument("--strength", type=int, default=60, help="custom look: 0..100")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--preview", type=Path)
    ap.add_argument("--view", choices=sorted(VIEWS), help="--preview: the stage itself from this side, not its textures")
    a = ap.parse_args()
    if not 0 <= a.arena < STAGES:
        raise SystemExit("ERROR: no such stage")
    X.setup(a.root)
    if a.look == "custom":
        if not (len(a.tint) == 6 and all(c in "0123456789abcdefABCDEF" for c in a.tint)):
            raise SystemExit("ERROR: --tint is RRGGBB")
        a.look = custom_look(a.tint, a.strength)
    if a.out:
        if not a.look:
            raise SystemExit("ERROR: --out needs --look")
        a.out.write_bytes(variant(a.root, a.arena, a.look))
        print(f"OK {a.out}")
    if a.preview and a.view:
        arena_view(a.root, a.arena, a.look, a.preview, a.view)
        print(f"OK {a.preview}")
    elif a.preview:
        preview(a.root, a.arena, a.look, a.preview)
        print(f"OK {a.preview}")


if __name__ == "__main__":
    main()
