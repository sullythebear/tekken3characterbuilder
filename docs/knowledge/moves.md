# Move format

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Move format (code: Expanded `tools/ttt1/moves.py`, `combat_semantics.py`)

- Expanded converts whole TTT1 movesets into Tekken 3's engine: records, clips, cancel lists,
  input sequences, reaction rows, pushback curves, contact groups. Damage, attacking bones and
  active frames are preserved.
- Move records are 56 bytes (`src/tekken3_ttt1_combat.c`, `record_owner`).
- Packs: `<n>-TTT1-combat.jmv` and `<n>-TTT1-tables.jst`.
- Next step: document the record fields from these tools, then the "hello world" experiment
  (change one move's damage for one custom fighter only).

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
