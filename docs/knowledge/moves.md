# Move format

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Move format (code: Expanded `tools/ttt1/moves.py`, `combat_semantics.py`)

- Expanded converts whole TTT1 movesets into Tekken 3's engine: records, clips, cancel lists,
  input sequences, reaction rows, pushback curves, contact groups. Damage, attacking bones and
  active frames are preserved.
- Move records are 56 bytes (`src/tekken3_ttt1_combat.c`, `record_owner`).
- Packs: `<n>-TTT1-combat.jmv` and `<n>-TTT1-tables.jst`.
- Next step: map command list entries to records (cancel lists: input -> record), then the
  "hello world" experiment (change one move's damage for one custom fighter only).

## Native move records in RAM (tested 2026-10-16, `t3live nav` dump, Xiaoyu vs Law)

- **tested** `*(0x800ADC20 + 4 * player)` is the player's moveset header:
  - word 0: `1 | key << 8` (Xiaoyu 7, Law 1, as the moveset keys);
  - `+4`: a cancel list;
  - `+8`: the first move record;
  - `+12`: the alias table, which starts right after the last record.
  So the record count is `(+12 - +8) / 56`: Xiaoyu 594, Law 459.
- **tested** Alias 3 (and the actor's record pointer `actor + 0x54` at rest) is record 0, the
  standing record.
- **tested** Record word 5, low halfword = damage. Xiaoyu has 280 records with damage, Law 262.
  The values are the usual Tekken ones (5, 7, 10, 12, 15, 25, 30). The high halfword is the speed
  of the airborne window (Expanded `moves.py`).
- **code** The other words, from Expanded's converter:
  - w0: animation;
  - w3: cancel list;
  - w7: sounds;
  - w8: timed properties;
  - w9: flags;
  - w10: hit descriptor pointer (native).
- **tested** The records are not on the disc as they are in RAM. 8- and 20-byte runs of them are
  in neither the BNS records nor the raw Track 1 image, so the loader (0x80069F74) builds or
  unpacks them (inferred). The Move Lab can only show them from a live capture for now.


## COMMAND LIST (tested 2026-10-16)

- **tested** Each costume model's ARC record (record 71 + 4 * model + 2) starts with a member
  table: u32 count (5), then (offset, size) per member. Member 4 is the fighter's COMMAND LIST,
  exactly the bytes the game copies to 0x800A3628 (P1, 0x1A0 per player; King 1: 0x17254,
  0x154 bytes). Format: count byte, then "name\0command\0" per entry.
- **tested** Word tokens (read off the game's own COMMAND LIST screen: a list of every byte
  value written to the buffer with t3live `write_ram`): 0x01-0x1F and 0xA1-0xC3 are words
  (`command_list.WORDS`; e.g. 0x0A During, 0x0B crouch, 0x04 [Throw], 0xB2 Head, 0xBD Attack,
  0xC3 Skyscraper); 0xC4-0xDD draw nothing/garbage; 0xA0 is an icon; 0xFB-0xFE are layout codes.
  "@#" and "\$" draw quote-like glyph pairs: marks that other entries refer to ("During @#,").
- **tested** Commands: 0x80-0x87 directions db d df b f ub u uf (+8 held), 0x90 neutral,
  0x92-0x9F buttons, mask = byte - 0x91 (1 LP, 2 RP, 4 LK, 8 RK): Paul's Phoenix Smasher reads
  d, df, f+2; Dr. B's Doc's One-Two 1, 2; King's Frankensteiner df+3+4.
- All 21 styles decode (Mokujin: one entry "Mokujinken ?"; Hwoarang 22 entries with stance
  titles). The builder shows it read-only in the Move Lab tab (`command_list.py`,
  `model_export.py commandlist`, `/api/moves`, cached per model).
- Fonts: words are not stored as text in RAM; the screen draws them from its own data.

## Native cancel lists (2026-10-16, live RAM; partly tested)

- **tested** A record's word 3 points to its cancel list. An entry is 12 bytes
  (`<4H4B`): command, condition (high byte), parameter, destination alias (alias 3 = standing),
  transition, window, end (2 bytes). `0xC000` ends the list; its destination is the end-of-clip
  link.
- **tested** `0xC00C` with destination N jumps to entry N of the fighter's own list block
  (header `+4`): shared sub-lists. Record 0's list starts at entry 0 of that block.
- **tested** The common moveset (`*(0x800ADC28)`, key 99) has the same header layout.
- **tested** The command's low nibble holds the buttons:
  - 1 = 0x01, 2 = 0x02, 3 = 0x04, 4 = 0x08;
  - Xiaoyu u+4 started the record behind command `0008` (25 damage), 1+2 started `0003`.
- **inferred** The high byte is the direction; low byte 0x10 means a direction alone. `0410` is
  forward (it starts walking forward) and `0110` is back. Commands `0x8000+` and `0xE000+` are
  special or input sequences (Expanded `moves.py`).
- **open** Mapping every COMMAND LIST line to its record. Most single presses in the Xiaoyu test
  did not land on a standing-list entry: she changes stance, and the 110-frame recovery wait was
  too short.

Next test: Paul (no stances), one input per Practice reset, 240-frame wait. Script pattern:
scratch `inputs.py`, using `t3live.Game` with `set_input` and read `actor + 0x54`.
