"""Stage Lab: a colour variant of one of Tekken 3's stages (runs with Expanded's venv).

A stage's textures are disc record 36 + arena (Paul's street 0 ... Dr. B's 14; tested 2026-10-16:
the CLUTs of records 36 and 49 sit in VRAM where their TIMs say during fights on arenas 0 and
13). The variant recolours those CLUTs; game patch 19 puts them over the stage's own colours
during a fight on that arena (<Key>-T3-stage.bin).

  stage_look.py --root R --arena 13 --look night --out Cbx-T3-stage.bin [--preview sheet.png]
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


def recolour(colours: np.ndarray, look: str) -> np.ndarray:
    """PS1 colours (u16) through a look; 0 (see-through) and the STP bit are kept."""
    mul, grey = LOOKS[look]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--arena", type=int, required=True)
    ap.add_argument("--look", choices=sorted(LOOKS))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--preview", type=Path)
    a = ap.parse_args()
    if not 0 <= a.arena < STAGES:
        raise SystemExit("ERROR: no such stage")
    X.setup(a.root)
    if a.out:
        if not a.look:
            raise SystemExit("ERROR: --out needs --look")
        a.out.write_bytes(variant(a.root, a.arena, a.look))
        print(f"OK {a.out}")
    if a.preview:
        preview(a.root, a.arena, a.look, a.preview)
        print(f"OK {a.preview}")


if __name__ == "__main__":
    main()
