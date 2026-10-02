# Roster tables and names on screen

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Roster tables (code: `src/tekken3_jun_roster.c`, Tekken3Recompiled 0.1.4)

- A "selection" is `character * 4 + costume`; the stock game has 92 (23 × 4).
- Extending the roster copies stock tables to private memory and patches the
  immediates that bound them (e.g. 92 → 96, 22 → 24 for Jun).
- Tables a clone needs from its donor (all **tested** with the Dizzy probe):
  model map `0x800958c4` (byte per selection), body profiles `0x80096f60` (word per
  character), CPU profiles `0x80098260` (12 bytes per character), radius profiles
  `0x80096ff0` (used by the `0x8003F044` hook), and the character remaps at
  `0x80052958` / `0x80052990` (argument `a1` = character ID).
- `0x80097d40` is the metadata table: one descriptor pointer per selection (4 bytes).
  A fighter's punch-costume descriptor is `read_word(0x80097d40 + ID * 16)`.
- Character descriptor: 12 bytes (template `0x80022274`), name pointer at +0,
  character ID at +4 and +9, stage at +10, music at +11.
- Memory card stats hold 22 rows; Jun uses the Force row (21). No free row is left.
- Selector (Tekken 3 page): rows of 8, 8 and 6 cells (22); the arcade cabinet grid is 2 × 11.

## Names on screen (tested, Tekken3Recompiled Jun slot)

- The VS screen spells the name from the character descriptor's string (+0 pointer).
- The name above the life bar and on the select screen is a 4bpp bitmap from the fighter's
  interface pack, not the descriptor string.
