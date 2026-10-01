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
- **Was open in 0.3.1 (tested; fixed in 0.3.3, see below):** King as donor still fights with Jin's moves. King's descriptor
  bytes 4..11 read `03 1e 03 03 03 03 0b 0a` (ID, name width, three bytes equal to the ID, ID,
  arena, music), so bytes 6..8 are now King's and are not what picks the moves. The remaps at
  `0x80052958` / `0x80052990` were never called with the custom ID 41 in that session.
  0.3.2 logs every call to those two functions and, per fight, the player's move header
  (`0x800adc20 + player * 4`, header byte 1 = the moveset's character key) plus the model map.
- **Probe results (0.3.2, tested 2026-10-01, Dizzy = ID 41, donor King, Expanded 1.1.3 test folder):**
  - `Custom fighters: Dizzy descriptor from character 3: 03 1e 03 03 03 03 0b 0a` – the donor
    descriptor copy works. No `character 41 reads character 3's data` line: `remap_donor` was
    never reached with ID 41.
  - `0x80052958` calls: `a0=801aea14 a1=-1 ra=80069ff0`, `a0=800f9d80 a1=9 ra=8006a014`,
    `a0=8015c6d8 a1=4 ra=8006a014`. `0x80052990` was not called.
  - P1 (ID 41) moves at `0x800f9d80` (the same `a0` as the `a1=9` call), header `0900`/`0901`
    = moveset key 9 (Jin). Model map byte 7 (donor's model; King's look was confirmed before).
  - So the caller at `ra=0x8006a014` passes 9, not 41: the ID is turned into Jin's before the
    remap, which therefore never sees a guest ID.
  - Expanded's TTT1 side also treats Dizzy as a guest: `19 guests registered as character 23 to
    41 / model 52`, `Dizzy model: missing ...Cbdizzy-TTT1-arcade-P1.3dm` / `rejected`, and
    `TTT1 characters: guest in the fight`.
- **Root cause of Jin's moves (code, 2026-10-01; disassembled from `disc/SLUS_004.02` and
  `generated/SLUS_004.02_full_28.c`, Expanded 1.1.3 sources):**
  - `func_80069F74` loads both players' movesets from a request table at `0x800A0510`:
    8 bytes per player (`+0` character ID half, `+2` pending flag, `+4` destination word), and a
    third entry at `+16` (called with `a1 = -1`, the `ra=80069ff0` call). Per player it calls
    `0x80052958(a0 = dest, a1 = ID)` (return address `0x8006A014`), then `func_8006A158` copies
    each `dest` to `0x800ADC20 + player * 4` (the moves pointer the probe reads).
  - The ID comes from the actor: `0x80069CDC` stores `actor+0x16` (actor =
    `0x800A9228 + player * 0x188C`) into `0x800A0510 + player * 8`. So there are two IDs per
    actor: `+0x18` = the selection (41 for Dizzy) and `+0x16` = the key for moves, shared move
    headers and hit rules.
  - `actor+0x16` is clamped by `0x8002D1DC` ("if ID >= 21 return 20"; Expanded raises the bound
    to 24). Expanded's `__wrap_func_8002D1DC` (`tekken3_ttt1_roster.c`) returns `GUEST_ID` (23)
    for **every** guest, custom fighters included, via the `0x8002D1F4` path.
  - With 23 in `a1`, `__wrap_func_80052958` sees guest 0 (a TTT1 guest, not custom), so
    `remap_donor` returns 9 (Jin) before the probe logs: hence `a1=9` and no `reads character 3`.
  - Fix: in `__wrap_func_8002D1DC`, give a custom fighter its donor's ID instead of 23.
- **Model hooks (code):** `0x8003626C` (model → byte from `0x8009591C`), `0x80036294` (`actor+28`
  → byte from `0x80095950`) and `0x800362C4` (`actor+28` → byte from `0x80095984`) are only
  redirected to Jin's model 18 when the model is 52 (`GUEST_MODEL`). King's model map is
  `6, 7, 255, 255` (Jin's `18, 19, 39, 255`); Dizzy's model map byte was 7 (King, costume 2) and
  `0x80095950[7] = 0x80095984[7] = 0`, King's own values. So if `actor+28` is 7 in game, the
  hooks leave Dizzy alone. **Tested** in 0.3.3: `actor+28` reads 7 in the fight.
- **TTT1 side (code):** at state 8, `tekken3_ttt1_roster_tick` calls `follow()` (sets the guest
  identity; that is what tries `Cbdizzy-TTT1-arcade-P1.3dm` and rejects it), uploads the guest's
  HUD name plate to VRAM (464, player * 256), and sets `wanted = 1`, which makes
  `tekken3_ttt1_select(1)` write control byte 1 and log `guest in the fight`. The per-player
  TTT1 paths also check `guest_player()`, which already excludes custom fighters, but the control
  byte should only be on for real TTT1 guests. Fix: custom fighters keep `follow()` and their
  name plate upload, but do not set `wanted`.
- **Fixed in 0.3.3 (T3CB-PATCH-4, tested 2026-10-01, Dizzy = ID 41, donor King, costume 2):**
  both fixes above; the probe line also logs `actor+0x16` and `actor+28`. Log: `actor+0x16 3`,
  `0x80052958 a0=800f9d80 a1=3 ra=8006a014`, header `0301` (key 3), `actor+28 model 7`, and no
  `guest in the fight` after selecting Dizzy. In game Dizzy fights with King's moves and throws,
  and the HUD name plate above the life bar still shows. Install → uninstall restores the four
  sources byte for byte (checked).
- Still seen in 0.3.3: `follow()` tries to load `Cbdizzy-TTT1-arcade-P1.3dm` and rejects it
  (harmless log noise; `follow()` stays for the name plate). Only P1's `0x80052958` call was
  logged this session; in the 0.3.2 session the CPU opponent's (`a1=4`) was too. Not explained.
- **Mixed fights (tested 2026-10-01 by the user, Expanded 1.1.3 test folder, patch
  T3CB-PATCH-4, Dizzy = King donor), both work perfectly:**
  - Dizzy vs Kazuya (VS mode): Kazuya, a TTT1 guest, keeps his own TTT1 model and moves next to
    a custom fighter. So `guest_move_key` giving Dizzy King's key and Dizzy no longer switching
    the TTT1 side on does not take the TTT1 side away from a real guest in the same fight.
  - Dizzy vs King: a custom fighter and its own donor can be in one fight together.
- **Bug (builder 0.3.2, fixed in 0.3.4):** Install/Update (`/api/support/install` in
  `server.py`) also runs `sync_customs(everything=True)`, which rewrote `customs.txt` from the
  builder's own `characters/` folder only. A builder copied into a game folder without that
  folder (or with an empty one) therefore wiped the CUSTOM page: `expanded_custom.py list` with
  no entries deletes `customs.txt` everywhere (the portrait packs stay behind). Found 2026-10-01
  when a fresh builder copy went into the Expanded 1.1.3 test folder while Dizzy lived in another
  builder copy; worked around then by calling `creator_patch.install` directly.
- **Rule since 0.3.4: the builder never silently removes a `customs.txt` entry.**
  - `custom_page.read_entries` reads both copies (`workspace/ttt1-import/roster` and
    `build-release/mods/ttt1`) and keeps every key from either, in order. Lines it cannot read
    are reported as a warning (they cannot be written back).
  - `sync_customs` keeps existing entries in their place (so their IDs 41.. do not shift) and
    appends new library fighters after them. Only `drop`, a key the user chose to remove, leaves
    the list: deleting a library fighter, or "Remove from game" (`/api/unlinked/remove`, which
    needs `confirm: true`; the UI asks first). The 12-fighter cap only leaves out new library
    fighters, never entries already in the game.
  - Safety net in the tool: `expanded_custom.py list` fails ("customs.txt would lose …") when an
    existing key is missing from `--entry` and not named with `--drop`.
  - Entries not in the library show in the UI under "On the Custom page, not in this library"
    (`/api/unlinked`; name from `<Key>-T3-label.txt`, else from the key). "Add to library"
    (`/api/unlinked/adopt`) creates `characters/<key without cb>/`, so `game_key()` gives the same
    key back and the entry keeps its place; the donor comes from `customs.txt`. The portrait is
    decoded from `<Key>-T3-ui.jui` (TIM 0: 126 × 252, four 64-row bands, CLUT entries
    `band * 64 + index`, index 0 transparent) into `portrait-ps1.png` (126 × 252) and
    `portrait-full.png` / `portrait.png` (168 × 252, nearest-neighbour). Without a readable pack
    the fighter gets no portrait files, so the next install draws the blank card.
    `character.json` records `adopted: {key, portrait}`.
- **Tested 2026-10-01** (copy `tekken3-expanded-1.1.3-installtest`, empty `characters/`,
  `customs.txt` = `cbdizzy 3`, `cbpeumel 5`, plus `cbghost 4` without any files), 22 API checks, all
  passed: Install and Refresh keep both lists and the packs byte for byte; all three listed as
  unlinked; a new library fighter is appended as the 4th entry; adopting Dizzy gives donor 3 and
  the portrait from the pack (decoded image checked by eye); adopting ghost gives no portrait and
  the next Install generates its pack; remove without confirmation and remove of a library
  fighter are refused; confirmed remove drops Peumel and its files only; deleting a library
  fighter drops only that one; the tool refuses a list without `--drop`. In the UI (browser):
  the section shows, "Remove from game" asks for confirmation (declined: nothing changed), and
  "Add to library" moved Peumel into the library with its portrait and Nina as donor.

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
