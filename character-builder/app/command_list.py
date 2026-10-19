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


# ------------------------------------------------------------ basic damage --
# A style's moveset is BNS record MOVESET_FIRST + key (key: descriptor byte 9), with offsets in
# place of pointers: +4 cancel lists, +8 the 56-byte move records, +12 the alias table, whose
# entries are record numbers there. The basic inputs (direction + buttons) come from the shared
# cancel lists in the executable, which name a fixed alias slot each; the record's word 5 (low
# halfword) is the damage. Tested 2026-10-18 (knowledge/moves.md).
MOVESET_FIRST = 280
SHARED_LISTS = (0x8001823C, 0x800187D0)          # first and last entry
DESCRIPTORS = 0x80097D40                          # 16 bytes per style, pointer to its descriptor
CANCEL_BUTTONS = {1: "1", 2: "2", 4: "3", 8: "4"}
CANCEL_DIRECTIONS = {0x20: "db", 0x40: "d", 0x80: "df", 0x100: "b", 0x200: "", 0x400: "f",
                     0x800: "uf", 0x1000: "u", 0x2000: "ub"}


def notation(cmd: int) -> str | None:
    """Tekken notation of a basic cancel command, or None for special ones (0x8000 and up)."""
    if cmd >= 0x8000:
        return None
    buttons = "+".join(name for bit, name in CANCEL_BUTTONS.items() if cmd & bit)
    dirs = [name for bit, name in CANCEL_DIRECTIONS.items() if cmd & bit]
    if not buttons:
        return None
    if len(dirs) != 1:                           # no or several directions: any direction
        return buttons
    return f"{dirs[0]}+{buttons}" if dirs[0] else buttons


def _exe_word(exe: bytes, addr: int) -> int:
    return struct.unpack_from("<I", exe, addr - 0x80010000 + 0x800)[0]


def moveset_key(exe: bytes, style: int) -> int:
    """The style's moveset key (descriptor byte 9; differs from the style for Mokujin and a few)."""
    return exe[_exe_word(exe, DESCRIPTORS + 16 * style) + 9 - 0x80010000 + 0x800]


def basic_damage(moveset: bytes, exe: bytes) -> dict[str, int]:
    """{notation: damage} of the basic inputs, standing (the shared lists' unconditional entries
    first; a few styles change some inputs in stances, which this leaves out)."""
    return {name: damage for name, (_, damage) in basic_records(moveset, exe).items()}


def basic_records(moveset: bytes, exe: bytes) -> dict[str, tuple[int, int]]:
    """{notation: (record, damage)} of the basic inputs (see basic_damage)."""
    word = lambda o: struct.unpack_from("<I", moveset, o)[0]
    start, alias = word(8), word(12)
    count = (alias - start) // 56
    out, later = {}, {}
    for a in range(SHARED_LISTS[0], SHARED_LISTS[1] + 12, 12):
        cmd, cond, _, dest = struct.unpack_from("<4H", exe, a - 0x80010000 + 0x800)
        name = notation(cmd)
        if name is None or alias + 4 * dest + 4 > len(moveset):
            continue
        record = word(alias + 4 * dest)
        if not 0 <= record < count:
            continue
        damage = word(start + 56 * record + 20) & 0xFF   # high bits: flags (0x4000 on throws)
        (later if cond else out).setdefault(name, (record, damage))
    for name, damage in later.items():
        out.setdefault(name, damage)
    return out


# The style's own moves (COMMAND LIST lines of one input that are not basic inputs): the record
# each one started in game, measured per style with t3live (docs/knowledge/moves.md). Their list
# entries carry conditions that the static data alone does not settle, so these are measured.
# A basic input listed here started the style's own move instead of the basic one (-1: one
# without damage in its first records); it then leaves the basic grid.
OWN_MOVES: dict[int, dict[str, int]] = {
    0: {"f+1+4": 222, "f,F+2": 198, "d,df,f+1": 145, "d,df,f+2": 191, "B+2+3": 346, "DF+1+2": 344,
        "f,F+1+2": 336},
    1: {"d+3+4": 128, "Duringcrouch,df,d,DF+3": 225, "Duringsidestep,3+4": 243, "DF+1+2": 439,
        "f,F+3+4": 435},
    2: {"f+3+4": -1, "f,F+1+2": 582, "During(*),1": 195, "During(**),4": 224},
    3: {"F+1+2": 195, "1+4": 232, "b+4": 322, "Duringsidestep,2": 208, "Duringcrouch,df+1": 117,
        "Duringsidestep,3+4": 217, "D,db,d,DB+1+2": 445, "d,db,B+1+2": 439},
    4: {"d+1+4": 285, "D+3+4": 340, "f,F+2": 126, "d,db,B+1+2": 433, "During(**),2": 230},
    5: {"Duringsidestep,4": 258, "Duringsidestep,2": 239, "f,F+2": 237, "Duringsidestep,1+2": 233,
        "b,db,d,DF+2": 124, "d,db,B+1+4": 509, "df,DF+1": 434},
    6: {"U+3": 53, "f,F+4": 264, "d,db,B+3": 483},
    7: {"f,F+3+4": 335, "f,F+3": 274, "f,F+4": 117},
    8: {"Duringcrouch,1+2": 140, "f,F+3": 237, "Duringsidestep,2": 218, "During(**),4": 256},
    9: {"b+1+2": -1, "Duringsidestep,2": 192, "DF+2+3": 381, "d,db,B+1+3": 377, "f,F+1+2": 376},
    10: {"F+1+4": 193, "Whilerising,4": 134, "DF+1+2": 342},
    11: {"f,F+2": 148, "b,db,d,DF+2": 122, "f,F+1+4": 290},
    12: {"Whilerising,2": 157, "f,f+3": 222, "Duringsidestep,2": 156, "Whilerising,1": 133,
        "f,F+2": 150, "b,B+4": 111, "Duringsidestep,1": 165},
    13: {"1+2": 223, "b+2": 209, "D+1+4": 110, "f,F+1+2": 355},
    14: {"f+1+4": 216, "f,F+2": 180, "Whilerising,2": 140, "f,F+4": 206, "df,DF+2+4": 313},
    16: {"3+4": 243, "df+2+3": 247, "Duringcrouch,1+2": 141, "b,db,d,df,f,DF+1": 239,
        "Whilerising,1": 139, "b,db,d,DF+2": 192, "Duringcrouch,DF+1+2": 123},
    17: {"D+3+4": 171, "UF+3+4": 263, "1+2": 28, "DB+3+4": 173, "Duringcrouch,DB+3+4": 173,
        "f,F+1+2": 125},
    18: {"Duringcrouch,f+2": 362, "Duringsidestep,2": 359, "Duringcrouch,f+1": 360, "f,F+2": 371,
        "Duringsidestep,1+2": 357, "df,DF+1": 500},
    19: {"B+3+4": 387, "b+1+2": 320, "d+3+4": 386, "d+1+2": -1, "f,F+1+2": 316, "f,f+3+4": 387},
    20: {"d,db+4": 208},
}


def own_records(moveset: bytes, style: int) -> dict[str, tuple[int, int]]:
    """{COMMAND LIST command: (record, damage)} of the style's measured own moves with damage."""
    word = lambda o: struct.unpack_from("<I", moveset, o)[0]
    start, alias = word(8), word(12)
    count = (alias - start) // 56
    out = {}
    for name, record in OWN_MOVES.get(style, {}).items():
        if 0 <= record < count:
            damage = word(start + 56 * record + 20) & 0xFF
            if damage:
                out[name] = (record, damage)
    return out


MOVES_FILE_MAX = 32


def moves_file(key: int, records: dict, changes: dict) -> bytes | None:
    """<prefix>-moves.bin for patch 20 ("T3MV"): {notation: new damage} over the style's basic
    records {notation: [record, damage]}; None when nothing changes."""
    rows = []
    for name, new in sorted(changes.items()):
        if name in records and 0 <= int(new) <= 200 and int(new) != records[name][1]:
            record, old = records[name]
            if (record, old, int(new)) not in rows and not any(r[0] == record for r in rows):
                rows.append((record, old, int(new)))
    if not rows:
        return None
    rows = rows[:MOVES_FILE_MAX]
    return b"T3MV" + struct.pack("<HHH", 1, key, len(rows)) + b"".join(struct.pack("<HHH", *r) for r in rows)


def with_damage(entries: list[dict], damage: dict[str, int]) -> list[dict]:
    """The COMMAND LIST with "damage" on lines whose command is one basic input."""
    for e in entries:
        key = e.get("command", "").replace(" ", "")
        if key in damage and damage[key]:
            e["damage"] = damage[key]
    return entries
