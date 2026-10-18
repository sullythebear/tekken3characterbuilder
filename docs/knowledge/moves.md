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
- **tested** Resetting with the debug server's `savestate` (op load, slot 5) before each input
  does not work: after a load, `set_input` started no move (48 of 48 inputs stayed in record 0).
  Use a Practice reset or a longer wait instead.

### Input test 2 (2026-10-18, tested)

Method: Xiaoyu in Practice. Before each input, wait until `actor + 0x54` stays on record 0
for 40 frames; then the direction, then direction + button for 4 frames.
- 46 of 48 inputs started a move. Single 1 and 2 did not (not understood).
- **tested** Jump attacks are in the standing cancel lists, with the button bits above:
  - u/uf + 3 → `0004`, 25 damage;
  - u/uf + 4 → `0008`, 25 damage;
  - uf + 2 → `0002`, 18 damage;
  - 1+2 in the air → `0003`.
- **tested** Ground attacks are not plain entries of record 0's list or its `C00C` sub-lists:
  3 → record 113, 4 → 114, f+1 → 120, 1+2 → 104. Their aliases (300/309, 301/310, 302,
  295/311) show up in no 12-byte entry of the list block. Two words point straight at record 113:
  0x80108F4C and 0x80108F70, in the alias table area right after the records.
- **inferred** Ground attacks are started some other way, probably through the tables at header
  `+16 .. +44` (0x8010C978 ...) or the common moveset (key 99). Next: read those tables around
  the direct pointers.
- So the Move Lab cannot put damage next to COMMAND LIST lines yet. The records and damage values
  themselves are known (above).

## Basic moves: shared input lists in the executable (2026-10-18, tested)

- **tested** The basic moves of every fighter come from shared cancel lists in the executable's
  data, at 0x8001823C .. 0x800187D0. These are 12-byte entries, with `C00D` starting each list.
  The destination is a fixed **alias slot**, for example:
  - 300/309 = 3, 301/310 = 4, 302..305 = f+1..f+4;
  - 353..356 = d+1..d+4, 357..361 = df+1..4;
  - 3334..3399 = jump attacks.
  Each moveset's alias table points the slot at its own record.
- **tested** The command word is direction bits plus button bits:
  - buttons: 1 = 0x01, 2 = 0x02, 3 = 0x04, 4 = 0x08;
  - directions: db 0x20, d 0x40, df 0x80, b 0x100, neutral 0x200, f 0x400, uf 0x800, u 0x1000,
    ub 0x2000;
  - no direction bit means any direction.
  Checked against input test 2 (Xiaoyu): f+1..f+4 → records 120..123, d+1 → 137, d+3 → 140,
  d+4 → 141, df+2 → 144, db+4 → 149, b+3+4 → 327, uf+4 → 93, u+4 → 91.
- **tool** `python tools/t3moves.py <dump>.ram [--player 1|2]` lists each basic input with its
  record and damage. Law: 1 = 5, 2 = 12, 3 = 18, 4 = 16.
  - Damage 0 marks records that start strings, grabs or stances; their damage is in a later
    record.
  - Moves only the character has (its own lists, the `C00C` sub-lists above) are not in this tool
    yet.
- The app cannot show this without a live capture: the records are not raw on the disc. A Move
  Lab "damage" column would need a capture per style (t3live, debug build).

## Movesets on the disc (2026-10-18, tested): damage without a running game

- **code** The loader 0x80069F74 calls 0x80052958(dest, key): file `74 + key` (key -1: file 73,
  the common moveset), through 0x8006BF20 with the file table at 0x80098574 (halfword per file)
  and 0x80024400 (8 bytes: start, size). File 73 + n is **BNS record 279 + n**, so a style's
  moveset is **record 280 + key** and the common one is 279. After loading, the loader adds the
  base to header words +4..+52 (offsets become pointers).
- **tested** On the disc the moveset holds offsets, and its alias table holds **record numbers**:
  Xiaoyu alias 300 → 113, 295 → 104, 302 → 120, as measured live. Record 287 (Xiaoyu) is 326,972
  bytes with 594 records, the same as in RAM.
- **tested** Key per style = descriptor byte 9: `exe[*(0x80097D40 + 16 * style) + 9]`.
  Keys 0..14, 9, 16, 19, 17, 18, 14 for styles 0..20.
- **tested** `command_list.basic_damage` (app) reads the shared lists from SLUS_004.02 and the
  moveset record. Law matches the live dump: 1 = 5, 2 = 12, 3 = 18, 4 = 16.
  - The record of each basic input matched the measured one in 30 of 38 Xiaoyu inputs pressed
    with the direction (test 3: direction and button in the same frame).
  - The 8 misses are her stance and crouch variants, which are in her own lists (entries 1200+),
    not in the standing table.
- **tested** The damage halfword's high bits are flags: throws carry 0x4000, so the low byte is
  used.
- The Move Lab shows this: a damage column on single-input COMMAND LIST lines, and a "Basic
  moves: damage" grid (browser-tested on Nina).
