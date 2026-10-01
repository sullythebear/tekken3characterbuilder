# Technical notes

Everything learned so far about Tekken 3 (SLUS-00402) as recompiled by Tekken3Recompiled
and extended by Tekken 3 Expanded. Each entry says how it is known: **tested** (seen in
game), **code** (read in the projects' source), or **inferred**.

## Character IDs

Internal fighter IDs, read from the game's character records (code: Expanded's
`tools/ttt1_stage_roster.py`, `T3_IDS`; True Ogre = 20 in its comments).

| ID | Fighter | ID | Fighter | ID | Fighter |
| --- | --- | --- | --- | --- | --- |
| 0 | Paul | 7 | Xiaoyu | 14 | Ogre |
| 1 | Law | 8 | Eddy / Tiger | 15 | Mokujin |
| 2 | Lei | 9 | Jin | 16 | Gun Jack |
| 3 | King | 10 | Julia | 17 | Gon |
| 4 | Yoshimitsu | 11 | Kuma / Panda | 18 | Anna |
| 5 | Nina | 12 | Bryan | 19 | Dr. B |
| 6 | Hwoarang | 13 | Heihachi | 20 | True Ogre |

21 = Tekken Force enemies, 22 = empty selection. Tekken3Recompiled adds Jun as 23;
Expanded uses 23..40 for its TTT1 guests; the builder's custom fighters use 41..52.

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

## Donor principle (tested)

Pointing a slot's model map entries at a donor's models and copying the donor's
body/CPU/radius rows plus the two remaps makes the slot fight exactly like the donor:
moves, throws, animations, CPU. Verified with Xiaoyu as donor in Jun's slot
(Dizzy probe, Tekken3Recompiled 0.1.4).

## Tekken 3 Expanded architecture (code: `src/tekken3_ttt1_roster.c`, Expanded on Recompiled 0.1.2)

- Guests come from `<asset root>/guests.txt`: `<key> <moveset> <arena owner>` per line,
  with `<Key>-T3-ui.jui`, `<Key>-T3-name.4bpp`, `<Key>-T3-label.txt` and TTT1 data beside it.
  Asset root = `build-release/mods/ttt1`; the build copies `workspace/ttt1-import/roster` into it.
- Guest `k` has ID `23 + k`; all TTT1 guests map their selections to model 52 (Jin's envelope)
  and are drawn by the TTT1 renderer.
- The cabinet selector has a Tag page (L2/R2); the VS grid (state 10) has its own pages.
- Tag tiles live in VRAM at (384,16), 8 per row, 16 × 58 halfwords each, palettes from row 480;
  two extra tiles at (384,144), palettes 498–499.
- Descriptors: 80 bytes per guest from `area + 0x30120`; the name table (64 entries) starts at `area + 0x30800`.
- CPU table and Force bosses for IDs ≥ 22 default to Jin's rows (`src/tekken3_ttt1_combat.c`).
- The guest/native split for the import pipeline is `guest_player()` in `src/tekken3_ttt1_mod.c`.

## CUSTOM page (builder 0.3.0, tested 2026-10-01 on Expanded 1.1.3 folder)

- `customs.txt` in the asset root: `<key> <donor ID>` per line, keys `cb<name>`.
- Custom fighters follow the TTT1 guests in the roster (`tag_count` marks the split), max 12
  so their IDs (41..52) keep availability bits 9..20, which the stock roster unlocks.
- They are guests on the selector but natives in combat: `tekken3_guest_native(id)` returns
  the donor, and `guest_player()` excludes them from the TTT1 import pipeline.
- Pages cycle 0 → 1 → 2 with R2 (back with L2); tiles of the shown guest page are uploaded
  into the Tag tile slots. The CHARACTER SELECT card reads CUSTOM on page 2.
- Known limits: not picked as CPU opponents, no Start costume, silent announcer name call,
  Team Battle icons may show the wrong tile.
- **Tested:** the CUSTOM page appears (R2/L2), the CHARACTER SELECT card reads CUSTOM, the
  custom portrait, select tiles and name plate show, the VS screen shows the custom name and
  portrait, and the HUD name above the life bar is the custom name plate. The fighter uses the
  donor's model (King tested).
- **Bug (0.3.0):** with King as donor the fighter had Jin/Kazuya-style moves, not King's.
  Suspect: guest descriptors are copied from the template `0x80022274` (Jin's); its bytes 6..8
  are not understood yet. 0.3.1 copies the donor's own descriptor (`0x80097d40 + donor * 16`)
  and logs both the descriptor bytes and which donor the character-data remaps return.
- **Fixed in 0.3.1:** an orange glitch above the left life bar in Arcade disappeared once custom
  fighters copied their donor's descriptor instead of Jin's.
- **Still open (0.3.1, tested):** King as donor still fights with Jin's moves. King's descriptor
  bytes 4..11 read `03 1e 03 03 03 03 0b 0a` (ID, name width, three bytes equal to the ID, ID,
  arena, music), so bytes 6..8 are now King's and are not what picks the moves. The remaps at
  `0x80052958` / `0x80052990` were never called with the custom ID 41 in that session.
  0.3.2 logs every call to those two functions and, per fight, the player's move header
  (`0x800adc20 + player * 4`, header byte 1 = the moveset's character key) plus the model map.

## Portrait and name plate (code: Expanded `tools/ttt1/ui.py`, `ui_art.py`, `glyphs.py`)

- `.jui` pack: header `JUI1`, version 1, 5 TIMs (8bpp + CLUT):
  portrait 126 × 252 (shown at 168 × 252, i.e. 2:3), select tiles 32 × 68 and 32 × 58,
  loading tiles 32 × 34 and 32 × 29. The portrait uses 4 bands of 64 rows, 63 colors each
  (index 0 transparent). The builder's packs pass the runtime's checks (**code**, validated offline).
- Name plate: 4bpp, max 76 px wide, letters cut from the fighter-name bitmaps on the disc
  (`disc/SLUS_004.02`). There is no F or Q; Z, V, `-`, `.` and 2 are drawn.

## Move format (code: Expanded `tools/ttt1/moves.py`, `combat_semantics.py`)

- Expanded converts whole TTT1 movesets into Tekken 3's engine: records, clips, cancel lists,
  input sequences, reaction rows, pushback curves, contact groups. Damage, attacking bones and
  active frames are preserved.
- Move records are 56 bytes (`src/tekken3_ttt1_combat.c`, `record_owner`).
- Packs: `<n>-TTT1-combat.jmv` and `<n>-TTT1-tables.jst`.
- Next step: document the record fields from these tools, then the "hello world" experiment
  (change one move's damage for one custom fighter only).

## Testing

- psxrecomp has a TCP debug server (`beetle_debug_server.c`, default port 4380) with
  `set_input`, `clear_input`, `pad_status`, `screenshot_file` and memory reads. Builds from the
  Easy Setup turn debug tools off (`PSX_DEBUG_TOOLS=OFF`, `PSX_DEBUG_SERVER_LITE=OFF`);
  a test build would enable them. Not tried yet.
- Expanded's `tools/*.lua` are emulator capture scripts (MAME/DuckStation) used to research the game.

## Lessons

- The first Dizzy run failed because the game was not rebuilt after patching: always check the
  build time against the patch time.
- Jun's roster in Tekken3Recompiled is ticked from her selector, which only runs once her import
  is loaded; skipping the import also removed the slot.
