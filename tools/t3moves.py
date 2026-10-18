"""Damage of a fighter's basic moves, from a RAM dump taken in a fight (t3live nav ... dump:NAME).

    python tools/t3moves.py character-builder/live/nav/fight.ram [--player 1]

The shared input lists in the executable (0x8001823C .., 12-byte cancel entries) give each basic
command (direction + buttons) a fixed alias slot; the player's moveset maps the slot to its own
move record, whose word 5 (low halfword) is the damage. See docs/knowledge/moves.md."""
from __future__ import annotations
import argparse
import struct
from pathlib import Path

SHARED_LISTS = (0x8001823C, 0x800187D0)          # first and last entry checked (2026-10-18)
HEADERS = 0x800ADC20                             # moveset header per player
BUTTONS = {1: "1", 2: "2", 4: "3", 8: "4"}
DIRECTIONS = {0x20: "db", 0x40: "d", 0x80: "df", 0x100: "b", 0x200: "", 0x400: "f",
              0x800: "uf", 0x1000: "u", 0x2000: "ub"}


def notation(cmd: int) -> str | None:
    """Tekken notation of a basic command, or None for special entries (0x8000 and up)."""
    if cmd >= 0x8000:
        return None
    buttons = "+".join(name for bit, name in BUTTONS.items() if cmd & bit)
    dirs = [name for bit, name in DIRECTIONS.items() if cmd & bit]
    if not buttons:
        return None
    if len(dirs) != 1:                           # no or several directions: any direction
        return buttons
    return f"{dirs[0]}+{buttons}" if dirs[0] else buttons


def basic_moves(ram: bytes, player: int = 0) -> list[dict]:
    word = lambda a: struct.unpack_from("<I", ram, a - 0x80000000)[0]
    base = word(HEADERS + 4 * player)
    start, alias = word(base + 8), word(base + 12)
    out, seen = [], set()
    for a in range(SHARED_LISTS[0], SHARED_LISTS[1] + 12, 12):
        cmd, cond, _, dest = struct.unpack_from("<4H", ram, a - 0x80000000)
        name = notation(cmd)
        if name is None or dest >= 4096:
            continue
        record = word(alias + 4 * dest)
        if not (start <= record < alias and (record - start) % 56 == 0):
            continue
        index = (record - start) // 56
        key = (name, index, cond)
        if key in seen:
            continue
        seen.add(key)
        out.append({"input": name, "record": index, "damage": word(record + 20) & 0xFFFF,
                    "condition": cond})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ram", type=Path)
    ap.add_argument("--player", type=int, default=1, choices=(1, 2))
    a = ap.parse_args()
    ram = a.ram.read_bytes()
    base = struct.unpack_from("<I", ram, HEADERS + 4 * (a.player - 1) - 0x80000000)[0]
    print(f"moveset key {(struct.unpack_from('<I', ram, base - 0x80000000)[0] >> 8) & 255}")
    for m in basic_moves(ram, a.player - 1):
        note = "  (conditional)" if m["condition"] else ""
        print(f"{m['input']:8} record {m['record']:4}  damage {m['damage']}{note}")


if __name__ == "__main__":
    main()
