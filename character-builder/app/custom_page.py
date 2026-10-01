"""Reads Tekken 3 Expanded's CUSTOM page files (standard library only).

customs.txt lists `<key> <donor ID>` per line. It exists twice: in
workspace/ttt1-import/roster (copied into every build) and in
build-release/mods/ttt1 (the running game's asset folder). Entries are read
from both, so an entry that only one copy holds is never lost.

The portrait comes back out of `<Key>-T3-ui.jui` (see Expanded's
tools/ttt1/ui.py): header "JUI1", version, count, size, then (offset, length)
per TIM. TIM 0 is the portrait: 8bpp, 126 texels wide (shown 168 wide),
252 rows in four 64-row bands, each with its own 64 colors of the 256-entry
CLUT; index 0 is transparent.
"""
from __future__ import annotations

import re, struct, zlib
from pathlib import Path

LIST_NAME = "customs.txt"
KEY_RE = re.compile(r"cb[a-z0-9]{1,24}")
FOLDERS = ("workspace/ttt1-import/roster", "build-release/mods/ttt1")
PORTRAIT_W, PORTRAIT_H, SHOWN_W, BAND_ROWS = 126, 252, 168, 64


def file_prefix(key: str) -> str:
    """Expanded's file prefix for a key: 'cbdizzy' -> 'Cbdizzy-T3'."""
    return key[0].upper() + key[1:].lower() + "-T3"


def read_entries(root: Path) -> tuple[list[tuple[str, int]], list[str]]:
    """The listed (key, donor) pairs in order, and the lines that could not be read."""
    entries, seen, unreadable = [], set(), []
    for folder in FOLDERS:
        path = root / folder / LIST_NAME
        try:
            lines = path.read_text(encoding="ascii", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            if len(parts) == 2 and KEY_RE.fullmatch(parts[0]) and parts[1].isdigit() and int(parts[1]) <= 20:
                if parts[0] not in seen:
                    seen.add(parts[0])
                    entries.append((parts[0], int(parts[1])))
            elif line.strip() not in unreadable:
                unreadable.append(line.strip())
    return entries, unreadable


def find_file(root: Path, key: str, suffix: str) -> Path | None:
    for folder in FOLDERS:
        path = root / folder / f"{file_prefix(key)}{suffix}"
        if path.is_file():
            return path
    return None


def read_label(root: Path, key: str) -> str | None:
    path = find_file(root, key, "-label.txt")
    if not path:
        return None
    try:
        return path.read_text(encoding="ascii", errors="replace").strip() or None
    except OSError:
        return None


def read_portrait(root: Path, key: str) -> list[bytes] | None:
    """The portrait as 252 RGBA rows of 126 texels, or None if it cannot be read."""
    path = find_file(root, key, "-ui.jui")
    if not path:
        return None
    try:
        data = path.read_bytes()
        magic, _version, count, _size = struct.unpack_from("<4I", data, 0)
        if magic != 0x3149554A or count < 1:
            return None
        offset, length = struct.unpack_from("<2I", data, 16)
        tim = data[offset:offset + length]
        tag, flags, clut_size = struct.unpack_from("<3I", tim, 0)
        if tag != 16 or flags != 9:
            return None
        palette = struct.unpack_from("<256H", tim, 20)
        pixels_at = 8 + clut_size
        _, _, _, width_halfwords, height = struct.unpack_from("<I4H", tim, pixels_at)
        if width_halfwords * 2 != PORTRAIT_W or height != PORTRAIT_H:
            return None
        pixels = tim[pixels_at + 12:pixels_at + 12 + PORTRAIT_W * PORTRAIT_H]
        if len(pixels) != PORTRAIT_W * PORTRAIT_H:
            return None
    except (OSError, struct.error):
        return None
    expand = lambda v: (v << 3) | (v >> 2)
    rows = []
    for y in range(PORTRAIT_H):
        base = (y // BAND_ROWS) * 64
        row = bytearray()
        for i in pixels[y * PORTRAIT_W:(y + 1) * PORTRAIT_W]:
            if i == 0:
                row += b"\0\0\0\0"
            else:
                c = palette[base + i]
                row += bytes((expand(c & 31), expand(c >> 5 & 31), expand(c >> 10 & 31), 255))
        rows.append(bytes(row))
    return rows


def stretch(rows: list[bytes], width: int) -> list[bytes]:
    """Nearest-neighbour widening, the way the PS1 shows the 126-texel portrait."""
    src = len(rows[0]) // 4
    pick = [x * src // width for x in range(width)]
    return [b"".join(row[p * 4:p * 4 + 4] for p in pick) for row in rows]


def png(rows: list[bytes]) -> bytes:
    """An RGBA PNG from rows of RGBA bytes."""
    width, height = len(rows[0]) // 4, len(rows)
    chunk = lambda kind, body: (struct.pack(">I", len(body)) + kind + body
                                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    raw = b"".join(b"\0" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
