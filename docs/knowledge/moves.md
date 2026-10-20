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

### Strings (2026-10-18, tested live: Xiaoyu and Law)

Each token was pressed for 3 frames, 14 frames apart; the cursor was moved to Law through
0x80118668.
- **tested** Law 1 → record 99, 2 → 101, 4 → 106. Xiaoyu 1 → 104, 2 → 106. These are the shared
  basic slots.
- **tested** "1, 2", "2, 1", "1, 2, 1", "1, 2, 4" and "2, 1, 4" started the basic records one
  after the other: no separate string records.
- **tested** "3, 4" started only the 3 (the 4 came too late for its window). "1, 1" and "1+2, 1"
  started one move.
- So whether a string comes out depends on cancel windows that the static data alone does not
  settle. Following the record's cancel list statically gave wrong records (Law "1, 2" → 450).
  The Move Lab therefore shows damage only for single-input lines and the basic grid, not
  summed strings.
- **tested** The very first input after a fight starts is ignored (seen in every run).

## Changed damage per fighter: patch 20 (2026-10-18, tested in game)

- **tested** Word 5 sets the damage. In Practice (ATTACK DATA on), Xiaoyu's 3 showed DMG 024
  (120 %) with record 113 at 20. With the value written to 60 live, it showed DMG 072.
- **tested** In Practice the dummy is a mirror of P1. **Both players then share one moveset
  buffer**: the headers at 0x800ADC20 and 0x800ADC24 were both 0x800F9D80. In Arcade every player
  has its own (KITTEST 0x800F9D80, Jin and Paul 0x8015C6D8).
- **T3CB-PATCH-20** (roster.c, `custom_moves_tick`, every frame in state 8):
  - `<prefix>-moves.bin` = "T3MV", u16 version 1, u16 key, u16 count, then per change u16 record,
    u16 old damage, u16 new damage.
  - When the player is that custom fighter, holds a moveset of that key, and the other player
    does not share the buffer, records still at the old value get the new one (the low byte;
    the flags are kept).
  - When the buffer belongs to someone else again, the changed values go back.
- **tested** KITTEST (Nina, key 5) with 3 = 60, written by the builder from the Move Lab
  (record 110, 25 → 60):
  - Arcade: P1 record 110 = 60, the opponent untouched; log "Kittest has 1 changed moves",
    "P1 Kittest changed moves in (1)".
  - Practice mirror: left at 25 (shared buffer), as designed.
- **tested** The "goes back" path, simulated in Arcade (opponent Law):
  - KITTEST's record 110 = 60;
  - P1's character id (actor+0x18) written to 5 (stock Nina) for a few frames: 25;
  - written back to 44: 60 again.
- **tested** Mirror in Arcade too: with a CPU opponent of the same moveset key (5), both headers
  were 0x800F9D80 (one shared buffer) and the patch left it at 25. With Law (key 1) and Eddy
  (key 8) the buffers were separate and the change applied.

## "During crouch" moves (2026-10-18, partly tested; not in the app)

- **tested** King (Practice):
  - holding down goes to record 25, then 11 (crouching);
  - from the crouch, df+1 starts record 117 (21 damage), not standing df+1's 137;
  - "while rising 1" (hold d, release, 1) started 97, the standing 1.
- **tested** King's list block has df+1 entries with condition 0x0004 → record 117 (entries 215
  and 356). All 17 of King's cond-4 entries look like crouch moves.
- **tested** Xiaoyu and Law have no cond-4 entries. Their crouch variants (Xiaoyu df+1 → 254,
  d+2 → 272, measured) come from the crouch records' own lists. Cond 4 is not a general "during
  crouch" mark.
- Not in the Move Lab: finding each style's crouch record statically needs more of the state
  machine (c001/c002 entries, the transitions out of standing).

## The style's own moves (2026-10-19, measured in game)

- **tested** Statically, the first matching entry of record 0's list (with `C00C` sub-lists) is
  not reliable: Yoshimitsu d+1+4 → 285 matched, but Xiaoyu f+3+4 started 313 (an entry with
  condition 0x2400 comes first) and f+1+2 started 325, which is in no entry. The conditions
  decide, and they are not known.
- **method** (scratch `measure.py`, t3live): Practice, the cursor moved to the character (right
  along a row, down every 12 presses: the select grid wraps per row, so right alone never reaches
  ids 10 and up), the first input thrown away, then per single-input COMMAND LIST line (no
  comma, no [Throw]): wait for record 0, press direction + buttons together for 4 frames
  (upper-case direction: held 12 frames first), trace `actor + 0x54` for 30 frames.
- The record kept is the first in the trace with damage ≥ 3: damage 0 starts strings, and
  King's F+1+2 (Jaguar Lariat) begins with a record of 1 damage before the 50-damage one.
- **tested** Some basic inputs start the style's own move instead of the shared basic slot:
  Law d+3+4 → 128 (12) not 136 (25); King b+4 → 322 (10) not 115 (20); Kuma f+3+4 and Jin
  b+1+2 → records without damage. `command_list.OWN_MOVES` holds these too (-1 = no damage);
  they leave the basic grid.
- The app: `OWN_MOVES` (record numbers only, no game data), `own_records` reads their damage
  from the disc, the Move Lab shows them as "the style's own moves" and patch 20 changes them
  like basic ones.
- **tested** Sequences the same way (scratch `measure2.py`): motion inputs (direction taps, then
  direction + buttons in the last token: "f, F+2", "d, df, f+2"; the same direction twice gets
  2 neutral frames between), and situations: "During crouch" / "While crouching" (down held 25
  frames first), "While rising" (down 25, release 2), "During side step" (up tapped, 6 frames).
  Leg Breaker (King, During crouch, df+1) → 117, as found before.
- Filters: a record that is another basic input's (the motion was not read: "f, f+2" gave the
  plain f+2) is left out, so is damage above 100 (flags: Kuma b, B+2+3+4 read 200), and jump
  inputs keep the basic table (their record depends on timing). Two passes: 50 sequences gave
  the same record both times and are in `OWN_MOVES`; 5 differed and are left out. With the
  single inputs: 75 entries over 20 styles. Keys are the command without spaces
  ("Duringcrouch,df+1"); the server accepts them (`server.MOVE_KEY`).
- Not measured: strings ("1, 2"), stance moves (marks such as (*)), "or" alternatives, throws.
- **tested** Patch 20 with an own move: KITTEST (Nina) Liftshot "During side step, 2" 15 → 50
  in the Move Lab wrote record 239 next to record 110 (3 = 60). Arcade against Tommy (King):
  "Kittest has 2 changed moves (moveset 5)", "P1 Kittest changed moves in (2)". Set back to
  15 afterwards (KITTEST keeps only 3 = 60). Browser: King's six own moves show with their
  names (Jaguar Lariat 50, Leg Breaker 21, Deadly Boomerang 60, ...).
- **tested** Health: `actor + 0x3F6` (halfword), 130 = full. Found by dumping both actors every
  30 frames while P1 stood still in Arcade: only P1 + 0x3F6 fell, 130 → 118 → 97 → 82 (hits of
  12, 21, 15), and the HUD bar stood at about 63 %. In Practice the dummy's reads 200 and does
  not fall (endless health), so damage is measured in Arcade.
- **method** Throws (scratch `measure4.py`): Arcade against the CPU, walk forward 45 frames, the
  throw input, then P2's lowest health over 150 frames. A try counts when the trace holds a
  record with the 0x4000 throw flag and P2's health fell; up to 5 tries. Paul: Foot Launch
  (B+2+3) 35, Twist & Shout (DF+1+2) 40.
- **tested** The throw's damage is in its follow-up record in the thrower's own moveset: Foot
  Launch traced 242 (0x4000, no damage) → 346 (35), Twist & Shout 244 → 344 (40), exactly the
  health drops. So a throw goes into `OWN_MOVES` with that follow-up record, kept only when its
  damage equals the measured drop in both passes, and patch 20 can change it like any move.
- **tested** Two passes over all styles: 20 throws in 13 styles (each kept only when its
  follow-up record's damage equals the measured drop; a pass where the CPU dodged leaves it to
  the other pass, and the passes never disagreed). `OWN_MOVES` now holds 95 entries.
- **tested** Patch 20 on a throw: KITTEST (Nina) with "df, DF+1" (record 434, 50) set to 20 in
  its moves file, Arcade: the throw traced 293 → 434 and the CPU's health fell by **20**, not
  50. The file was put back afterwards.
- **tested** Stance moves "During (*) , X" (scratch `measure5.py`): the entry whose name holds
  that mark is done first (Lei's Phoenix Illusion (**) = B+1+4), 14 frames, then X. Two passes,
  the same: Lei During (*), 1 → 195 (25) and During (**), 4 → 224 (70); Yoshimitsu During (**),
  2 → 230 (10); Eddy During (**), 4 → 256 (12). Eddy During (**), D+3+4 gave his basic d+3+4
  and is left out. 99 entries in `OWN_MOVES`.

## Strings (2026-10-19, measured in game)

- **method** (scratch `measure6.py`): Practice, each COMMAND LIST line whose tokens all hold
  buttons ("1, 2", "b+1, 2, 1"), pressed 3 frames each with gaps of 8, 12, 16 or 20 frames (the
  first gap that gives every hit wins), tracing the records with damage.
- From outside, two separate moves in a row look the same as a string, so a string is kept only
  when every hit after the first is a record that is no basic input's and no measured own move's
  (e.g. Law b+1, 2, 1 → 115, 209, 204; "f+2, 1" gave basic f+2 then basic 1 and is left out).
- Two passes, kept when both gave the same records: 10 strings in 8 styles
  (`command_list.STRINGS`), e.g. Bryan Hands of Doom b+2, 1, 2 → 152, 153, 151 (21 + 21 + 21),
  Xiaoyu u+1+2, 2, 1 → 242, 244, 150. The Move Lab shows "21 + 21 + 21 = 63 dmg"; hits 2 and
  later are changeable on their own (keys "b+2,1,2#2"; hit 1 is the basic or own move).

## Lines with alternatives ("or") (2026-10-19, measured in game)

- The first alternative is pressed ("b (or, B), 1+2" → b, 1+2; "A, or, B" → A); the key stays the
  whole command ("b(or,B),1+2", accepted by `server.MOVE_KEY`). Scratch `measure7.py`, two passes.
- Kept: Lei Falling Tree "uf (or, ub), 2" → 58 (15) and Turn Around "B (or, b), 3+4" → 401 (15).
- Left out: several gave a basic input's record; parries give no damage; Xiaoyu's Lower Parry gave
  record 254, her crouching df+1, so the parry did not come out.

## Chain throws (2026-10-19, tried, not in the app)

- 11 chain lines (Nina 9, Anna 2), each "From M, ..." led by the entry carrying mark M
  ((*), (**), ^%, {*, }_), built recursively (scratch `measure8.py` Arcade, `measure8p.py`
  Practice).
- **tested** Not reliable with set_input: Nina's Back Hand Slap d, df, f+1+2 comes out as her
  basic f+1+2 (record 230), so every chain led by it fails; a chain led by Betrayer
  d, db, B+1+4 gave basic moves in Practice (the throw missed). In Arcade the CPU breaks or
  wins before the long sequences finish. Left out; the chains' first throws (Betrayer 15,
  Elbow Smash 50) are in `OWN_MOVES`.

## Moves on other buttons: patch 21 (2026-10-20, tested in game)

- **tested** (scratch `combot.py`, Practice) A basic input starts the record its alias slot
  points at (`*(header + 12) + 4 * slot`, a RAM pointer). Writing another record of the same
  moveset there puts that move on the input:
  - Nina f+2 (slot 303, record 116) → 237 Panther Claw, → 239 Liftshot (a side-step move);
  - → 120 (b+2): f+2, 2 then gave 120, 121, the whole string;
  - King f+1 → 117 (his crouching df+1) went 117, then a common-moveset record, then standing;
  - every case went back to record 0; writing the old pointer back restored the input.
- Throws are left out: their records carry no flag here (the 0x4000 bit is not set on the
  measured ones), and a grab only makes sense on its own input; the app filters COMMAND LIST
  names with "[Throw]".
- **T3CB-PATCH-21**: `<prefix>-moves.bin` version 2 = version 1 + u16 swaps, then per swap u16
  slot, u16 original record, u16 new record. The same rules as patch 20 (own buffer only, not in
  a mirror match, back when the buffer is someone else's). Version 1 files are unchanged.
- **tested** Arcade, KITTEST (Nina, key 5) against Law (key 1), f+2 → Liftshot: P1's slot 303 →
  239, Law's slot 303 untouched (his 111); f+2 started 239 and hit (P2 130 → 108); P1 seen as
  stock Nina for a moment: back to 116, then 239 again. Log "Kittest has 1 changed moves,
  1 moved".
- Slots come from the shared lists' unconditional entries whose slot holds the input's record
  (`command_list.basic_slots`); inputs whose own move is measured (OWN_MOVES) have no slot.
- Moves of other styles are not possible: their records use the style's own animations.
- Note: t3live runs `build-opt-dbg`; after a patch change build both (`t3cb build` and
  `t3cb build --debug`).

## The COMMAND LIST of moved moves: patch 22 (2026-10-20, tested in game)

- **tested** (scratch `cmdlist.py`) In a fight P1's buffer at 0x800A3628 is byte for byte the
  disc's list (ARC member 4 of the costume model; Nina's models 10 and 11 share one, model 36 has
  its own, 384 bytes). A list written there (one entry more, 410 of 416 bytes) shows in the
  pause menu's COMMAND LIST, the new entry with the f+2 icons.
- **T3CB-PATCH-22** `<prefix>-commands.bin`: "T3CL", u16 version 1, u16 pairs; per pair u16
  sizes (original, new), the original list, the new one. Every frame of a fight, the custom
  fighter's buffer (0x800A3628 + 0x1A0 * player) still holding an original gets the new list.
  Built by `command_list.commands_file`: a moved move gets a second entry (same name, the new
  input) right after its own, since its old input still works; an entry whose command is the
  moved input itself is left out.
- **tested** KITTEST (f+2 → Liftshot), Arcade: log "Kittest has its own COMMAND LIST",
  "P1 Kittest COMMAND LIST in"; the pause menu shows Liftshot twice: "During side step, 2" and
  the f+2 icons.
