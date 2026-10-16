"""Tekken 3's COMMAND LIST of a fighter, read from the player's own disc (stdlib).

The list is in each costume model's ARC record (record 71 + 4 * model + 2): one count byte,
then per move "name\\0command\\0" (the buffer the game copies to 0x800A3628, 0x1A0 bytes,
docs/knowledge/moves.md). Names and commands use one-byte word tokens, read from the game's
own COMMAND LIST screen (2026-10-16, t3live: a list of every token written to the buffer).
Commands: 0x80..0x87 directions (db d df b f ub u uf), +8 held, 0x90 neutral, 0x92.. buttons
(byte - 0x91 = mask: 1 left punch, 2 right punch, 4 left kick, 8 right kick). Written in
Tekken's own notation: "d, df, f+2" (Paul's Phoenix Smasher), held directions in capitals.
"""
from __future__ import annotations

import struct

WORDS = {
    0x01: "When Facing Right", 0x02: "[Chain Throw]", 0x03: "From", 0x04: "[Throw]", 0x05: "Break",
    0x06: "Lock", 0x07: "Arm", 0x08: "Leg", 0x09: "Neck", 0x0A: "During", 0x0B: "crouch", 0x0C: "Smash",
    0x0D: "Left", 0x0E: "Right", 0x0F: "Punch", 0x10: "Kick", 0x11: "Throw", 0x12: "Combo",
    0x13: "Somersault", 0x14: "While", 0x15: "ng Squeeze", 0x16: "Uppercut", 0x17: "After",
    0x18: "Falling", 0x19: "Deadly", 0x1A: "Power", 0x1B: "Moonsault", 0x1C: "Spin", 0x1D: "Slap",
    0x1E: "copter", 0x1F: "Windmill",
    0xA1: "Stretch", 0xA2: "opponent", 0xA3: "Nightmare", 0xA4: "Frankenste", 0xA5: "Double",
    0xA6: "Cross", 0xA7: "Handstand", 0xA8: "Snake", 0xA9: "Dragon", 0xAA: "Twist", 0xAB: "Cannon",
    0xAC: "Claw", 0xAD: "Hammer", 0xAE: "Rush", 0xAF: "Hand", 0xB0: "te Special", 0xB1: "Cut",
    0xB2: "Head", 0xB3: "Jumping", 0xB4: "Phoenix", 0xB5: "Art of", 0xB6: "stance", 0xB7: "Ends in",
    0xB8: "Roll", 0xB9: "Crush", 0xBA: "side step", 0xBB: "Fisherman", 0xBC: "Chopper",
    0xBD: "Attack", 0xBE: "Flash", 0xBF: "Elbow", 0xC0: "Betrayer", 0xC1: "Middle", 0xC2: "Triple",
    0xC3: "Skyscraper",
}
# "@#" marks a move that another entry refers to ("During @#,"): the screen draws two quote-like
# glyphs; shown as "(*)"; a second mark "\$" as "(**)" (inferred from the lists, 2026-10-16)
MARKS = ((b"@#", 1), (b"\\$", 2))
LAYOUT = (0xFB, 0xFC, 0xFD, 0xFE)          # layout codes, no text of their own
DIRECTIONS = ("db", "d", "df", "b", "f", "ub", "u", "uf")
BUTTONS = {1: "1", 2: "2", 3: "1+2", 4: "3", 5: "1+3", 6: "2+3", 7: "1+2+3", 8: "4", 9: "1+4",
           10: "2+4", 11: "1+2+4", 12: "3+4", 13: "1+3+4", 14: "2+3+4", 15: "1+2+3+4"}
BUFFER = 0x1A0


def text(raw: bytes) -> str:
    """A name or a command's text part, tokens spelled out."""
    out = []
    for mark, k in MARKS:
        raw = raw.replace(mark, bytes([k]) + bytes(1))       # mark k as two bytes: k, 0
    raw = bytearray(raw)
    i = 0
    while i < len(raw):                                       # the marks first: k is also a token
        if i + 1 < len(raw) and raw[i + 1] == 0:
            out.append(" (" + "*" * raw[i] + ") ")
            i += 2
            continue
        b = raw[i]
        i += 1
        if b in WORDS:
            out.append(WORDS[b])
        elif b in LAYOUT:
            continue
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append("?")
    return " ".join("".join(out).split())


def command(raw: bytes) -> str:
    """A command in Tekken's notation: 'f, f+2', 'During crouch, df+1'; held directions in capitals
    ('F'); a direction followed by buttons is one input ('df+1'), as the game's icons mean it."""
    steps, words = [], bytearray()

    def flush():
        if words:
            steps.append(("text", text(bytes(words))))
            words.clear()
    for b in raw:
        if 0x80 <= b <= 0x8F:
            flush()
            d = DIRECTIONS[b & 7]
            steps.append(("dir", d.upper() if b & 8 else d))
        elif b == 0x90:
            flush()
            steps.append(("dir", "N"))
        elif 0x91 <= b <= 0x9F:
            flush()
            steps.append(("button", BUTTONS.get(b - 0x91, "?")))   # mask = byte - 0x91 (Doc's One-Two: 1, 2)
        else:
            words.append(b)
    flush()
    out, previous = [], None
    for kind, value in steps:
        if kind == "button" and previous == "dir":
            out[-1] += "+" + value
        elif kind == "text":
            out.append(value.rstrip(","))
        else:
            out.append(value)
        previous = kind
    joined = ", ".join(p for p in out if p)
    for a, b in ((", (", " ("), ("(, ", "("), ("( ", "("), (", )", ")")):
        joined = joined.replace(a, b)
    return joined


def _name_ok(raw: bytes) -> bool:
    return 0 < len(raw) <= 48 and all(b in WORDS or b in LAYOUT or 0x20 <= b < 0x7F for b in raw)


def _command_ok(raw: bytes) -> bool:
    """Inputs and words, a section title ("Left Stance"), or "?" (Mokujin's random style)."""
    return 0 < len(raw) <= 40 and all(b in WORDS or b in LAYOUT or 0x20 <= b < 0x7F or 0x80 <= b <= 0x9F
                                      for b in raw)


def parse(data: bytes, at: int) -> list[tuple[bytes, bytes]] | None:
    """The list at offset `at`, or None if it is not one."""
    count = data[at]
    if not 1 <= count <= 48:
        return None
    p, out = at + 1, []
    for _ in range(count):
        n = data.find(b"\0", p, p + 50)
        if n < 0 or not _name_ok(data[p:n]):
            return None
        c = data.find(b"\0", n + 1, n + 34)
        if c < 0 or not _command_ok(data[n + 1:c]):
            return None
        out.append((data[p:n], data[n + 1:c]))
        p = c + 1
    return out if p - at <= BUFFER else None


def find(data: bytes) -> list[tuple[bytes, bytes]] | None:
    """The COMMAND LIST in a fighter's ARC record: its member 4. The record starts with the
    member count and (offset, size) per member (King 1: 5 members, member 4 at 0x17254, 0x154
    bytes: exactly the list)."""
    if len(data) < 48:
        return None
    count = struct.unpack_from("<I", data, 0)[0]
    if not 5 <= count <= 16:
        return None
    off, size = struct.unpack_from("<II", data, 4 + 8 * 4)
    if off + size > len(data) or not 1 <= size <= BUFFER:
        return None
    return parse(data[off:off + size] + bytes(1), 0)


def moves(data: bytes) -> list[dict]:
    """[{name, command}] readable, from a fighter's ARC record ({section} for a title such as
    "Left Stance"); [] if it holds no list."""
    out = []
    for n, c in find(data) or []:
        if not text(n) and not any(0x80 <= b <= 0x9F for b in c):
            out.append({"section": text(c)})
        else:
            out.append({"name": text(n), "command": command(c)})
    return out
