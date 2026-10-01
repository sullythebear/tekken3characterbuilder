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

## Style layer (builder 0.3.6, layer 1 of `docs/vision.md`)

- The UI picks a fighting style; the donor stays the stored value (`donor` in `character.json`,
  `customs.txt` unchanged). Styles and groups live in `DONORS` / `STYLE_GROUPS` in `ui/app.js`;
  labels read "<Style>, based on <Donor>" in the library, the preview and the unlinked list.
- Striking: Law Jeet kune do, Nina Assassination arts, Hwoarang Taekwondo, Eddy Capoeira,
  Bryan Kickboxing, Anna Assassination arts. Grappling: Paul Judo, King Pro wrestling.
  Traditional: Lei Kung fu, Yoshimitsu Ninjutsu, Xiaoyu Baguazhang, Jin Karate, Julia Xingyiquan,
  Heihachi Mishima karate. Special: Kuma Bear style, Ogre Ancient arts, Mokujin Copycat,
  Gun Jack Heavy machine, Gon Dino power, Dr. B Unpredictable, True Ogre Ancient arts (boss).
  (The group split was the builder's choice; the user gave the styles.)

## Donor tests: Ogre, Gon, Dr. B, True Ogre (2026-10-01, patch T3CB-PATCH-6)

**Moveset key ≠ character ID (tested):** stock T3 sets `actor+0x16` from descriptor byte 9
(`0x8004F274`: `+0x18` = ID, `+0x16` = byte 9, `+0x1A` = byte 8), and byte 9 is the moveset key.
Read from `0x80097D40 + ID * 16` in SLUS: equal to the ID for 0..14 and 16, but Mokujin 15 → 9,
**Gon 17 → 19, Anna 18 → 17, Dr. B 19 → 18, True Ogre 20 → 14** (Ogre's moveset), Force 21 → 20.
So moveset 17 is Anna's: a custom fighter given its donor's *ID* in `+0x16` (T3CB-PATCH-4..6)
fought with Anna's moves on Gon. T3CB-PATCH-7: `guest_move_key()` returns the donor descriptor's
byte 9. (King, Ogre and Copycat tests were unaffected: their key equals the ID, or is drawn.)

Character checks in SLUS (code: every `lh/lhu 22|24(actor)` followed within 4 instructions by a
compare with the ID; a scan, so other forms may exist). `+0x16` is the moveset key, which custom
fighters now get from the donor; `+0x18` is the selection ID (41.. for custom fighters), so
those checks never fire for them:

- Ogre's moveset 14 (Ogre and True Ogre), on `+0x16`: `0x80042148` (fn `0x80041F6C`),
  `0x80059A54`, `0x800670B0`, `0x80067154`.
- Gon 17, on `+0x18`: `0x8002D8CC`, `0x80033DE4`, `0x80033EE8`, `0x80034058`, `0x800392B4`,
  `0x8003B18C`, `0x8003F4F4`, `0x800404E8`, `0x8006EFE8`, `0x8006F06C`.
- Gon's moveset 19, on `+0x16` (first read as "Dr. B 19"): `0x80030F08`, `0x800421F4`,
  `0x80059A90`, `0x8005F4F4`.
- True Ogre 20, on `+0x18`: `0x80034FC4`, `0x80042158` (with `+0x16 == 14`), `0x80069824`,
  `0x800708BC`; with Kuma 11, on `+0x18`: `0x80043A40`, `0x800452F0` (so Kuma-based fighters may
  miss something too).

Results (one test fighter per donor, Arcade, played by the user with the Test button):

- **Ogre (14): works perfectly** (user). Fighter DABABY = ID 41, costume 2: descriptor
  `0e 23 0e 0e 0f 0e 06 15`, `0x80052958 a1=14`, header `0e00`/`0e01` (key 14), model 29 (Ogre's
  map is `28, 29`), 0 errors.
- **Gon (17), first test (T3CB-PATCH-6): wrong moveset.** Fighter GAASTRA = ID 41: Gon's model
  (43, map `42, 43`) but Anna's moves and animations (user). Log: `a1=17`, header `1101` (key 17 =
  Anna's moveset). Cause and fix: see "Moveset key" above (T3CB-PATCH-7, built and reversible).
- **Gon (17), retest (T3CB-PATCH-7): works** (user: "alles werkte"). GAASTRA = ID 41, costume 2:
  `a1=19`, header `1301` (key 19, Gon's moveset), model 43. The ten `+0x18 == 17` checks never
  fire for a custom fighter, but the user saw no difference in size, camera, throws or sound.
  Not looked into what they do; candidates if something Gon-specific is ever missed.
- **Dr. B (19): works** (user). DR.B T = ID 42: `a1=18`, header `1200`/`1201` (key 18, Dr. B's
  moveset), model 45 (map `44, 45`), descriptor `13 43 15 02 14 12 0e 19`.
- **True Ogre (20): works** (the glitches of the first test came from ID 43, fixed by
  T3CB-PATCH-8, see "ID 43" below). T.OGRE T = ID 43 in that test:
  `a1=14`, header `0e00`/`0e01` (key 14, Ogre's moveset, as stock True Ogre), model 33 (map
  `32, 33`). The True Ogre checks below test `actor+0x18 == 20`, so none fire for a custom
  fighter; no visible effect so far:
  - `0x800697D4` (moveset loading): when request 14 loads and P1's or P2's `+0x18` (`0x800A9240`,
    `+0x18A4` for P2) is 20, it calls `0x8006C588(3)`, most likely True Ogre's extra data
    (textures). Prime suspect for the glitches.
  - `0x80034FC4` (fn `0x80034EE4`, drawing): with `+0x18 == 20` it draws with `0x8006975C(actor)`
    as a parameter.
  - `0x80042158` (fn `0x80041F6C`): with `+0x16 == 14` and `+0x18 == 20` it computes extra bone
    positions at `actor+3040/3808` and `+2428/3876` (wings).
  - `0x800708BC` (fn `0x800707F4`): effect origin from `actor+3584` instead of `+2700`.
  - Plus `0x80043A40` / `0x800452F0` (`+0x18` == 11 or 20).
- **Anna (18): works perfectly** (user, T3CB-PATCH-7). ANNA T = ID 42: `a1=17`, header
  `1100`/`1101` (key 17, Anna's moveset), model 41 (map `36, 41, 46`). Before patch 7 she would
  have loaded moveset 18 (Dr. B's).
- **True Ogre, second test (12:16): no glitches** (user). He was ID 41 then; in the first test he
  was ID 43 (see below).
- **Kuma (11): works** (user, T3CB-PATCH-8, 13:56). Moves and animations were always right
  (`a1=11`, key 11, models 22/23). The model glitches (fur drawn with black holes or white and
  torn, life bars / round text as orange blocks) were **not about Kuma but about the custom ID
  43**: KUMA T was ID 43 in every glitching test, T.OGRE T glitched only while he was ID 43, and
  after reordering `customs.txt` KUMA T (now ID 41) was perfect while ANNA T (now ID 43) got the
  same glitches.
- **ID 43 (root cause, tested 2026-10-01):**
  - The fighter loader (around `0x80036300`) calls `0x8007619C(player, actor+0x18, data)` at
    `0x800365A8`. That routine reads a 6-byte row per character ID from `0x80027950` (first
    halfword = number of 8 × 32 tiles; `0x800279EC + player * 48` gives the VRAM rectangle) and
    uploads that many tiles from `data` into the strips next to the fighter bands (x 368..383 and
    496..511, rows 0..479 in stock fights).
  - The table has 22 rows. Custom IDs read whatever follows: ID 41 → 0, 42 → 32, **43 → 256**,
    44 → 48, 45 → 352, 46 → 64, 47 → 448, 48 → 80, 49 → 288, 50 → 0, 51+ → garbage. With 256 the
    routine stamped one tile (source `0x800C13D4`) over x 376..495, rows 0..511: it wiped P1's
    textures (P2's were uploaded afterwards and survived) and the CLUT rows 480..511, which the HUD
    and the fighters' palettes use. IDs 45, 47, 49 and 51+ would have done the same.
  - **Fix T3CB-PATCH-8:** `custom_strips()` (roster tick) keeps a 64-row copy of the table in guest
    memory, rows copied live from `0x80027950` except custom IDs, which get their donor's row, and
    points `0x800761B4`/`0x800761B8` (`lui`/`addiu` of the table address) at it with `lui`/`ori`
    via Expanded's `patch()` / `psx_mod_write_code_word`. Custom fighters now also get their
    donor's 30 (or 22) strip tiles. Install → uninstall restores the sources byte for byte.
    Tested: ANNA T as ID 43 and KUMA T as ID 41 both perfect (user, 13:56).
  - How it was found (method worth reusing): a temporary diagnostic in the test folder only
    (reverted afterwards): VRAM + actor dumps at a fixed time in the fight (stock Kuma vs custom
    Kuma, same opponent), then a trace of every CPU→VRAM upload in `psxrecomp/runtime/src/gpu.c`
    (`gp0_commit_cpu_to_vram`) with a stack backtrace that keeps only words preceded by a
    `jal`/`jalr` (`debug_guest_sp()`, `psx_mod_read_word`). The display area is x 0..367,
    y 0..479. Ruled out on the way: mirror costume, name-plate / loading-card uploads, Expanded's
    outfits and HD skins, the weight-class checks below. When searching for `jal` callers, mask
    the target: `0x0C000000 | ((addr >> 2) & 0x03FFFFFF)`; several "no callers" results before
    that fix were wrong.
  - The two Kuma/True Ogre checks are gameplay, not graphics: fn `0x80045248` (callers in fn
    `0x800451B8`) and `0x80043A40` (caller `0x80043890`) subtract 40 per fighter whose `+0x18` is
    11 or 20 from a value looked up per weight class (`actor+0x1E`, table `0x8009E660`). A Kuma- or
    True Ogre-based custom fighter does not get that; no visible effect reported.
- True Ogre's own `+0x18 == 20` checks (above) are still not handled; nothing visible so far.
  If something True-Ogre-specific turns out missing: wrappers that answer for the selection ID,
  or call `0x8006C588(3)` after his moveset loads. Faking `+0x18` itself is risky: Expanded's
  own hooks use it to recognise guests.

## Mokujin's round-start draw (code, SLUS-00402)

- At round start `0x8002AA44` / `0x8002AACC` test `actor+0x18` (the selection ID) == 15 for P1 / P2
  and only then call `0x8004F2DC(actor)`. That draws a random unlocked character from the
  availability bits at `0x80097EF0` (mask `0x13FFF`, 22 IDs) and writes the drawn character's ID
  (metadata table `0x80097D40`, descriptor byte 9) to `actor+0x16`, the moves key.
- A custom fighter with Mokujin as donor has `actor+0x18` = its own ID (41..), so the draw does
  not run and the fighter loads "moveset 15" as is.
- **Tested 2026-10-01 (builder 0.3.6, patch T3CB-PATCH-4, fighter MOKU = ID 42, donor 15,
  Arcade, costume 2): Mokujin does NOT work as a donor.** Selecting works and the descriptor is
  Mokujin's (`0f 37 0f 0f 10 09 02 16`), `actor+0x16` 15, model 31 (Mokujin costume 2; stock model
  map for 15 is `30, 31`). But `0x80052958` loads `a1=15` and the moves header reads `0002`
  (key 0, not 15): slot 15 holds no real moveset, because stock Mokujin always has a drawn ID in
  `actor+0x16` before his moves load. In game the model looked squashed into one block and the
  game froze on the first attack button. The test report showed 0 errors and exit code 0 (the
  user closed the frozen game): **the report cannot detect a freeze**, ask the user.
- Consequence: a Mokujin-based fighter needs the round-start draw. That is a patch change: run
  `0x8004F2DC(actor)` at round start (`0x8002A914`, where Expanded already hooks Mokujin in
  `tekken3_ttt1_combat.c`) when `tekken3_guest_native(actor+0x18) == 15`, so `actor+0x16` gets a
  drawn ID like stock Mokujin.
- The round-start routine `0x8002A914` itself reloads the movesets after the draw: `0x80069AA8`
  (copies `actor+0x16` into the request table at `0x800A0510`), `0x80069F74` (loads),
  `0x8006A158` (moves pointers). So writing `actor+0x16` on entry of `0x8002A914` is enough.
- **0.3.6 = T3CB-PATCH-5 (built 2026-10-01, not yet tested in game):**
  `tekken3_custom_copycat_draw()` (roster.c) runs on entry of `__wrap_func_8002A914` (combat.c):
  for each player whose `actor+0x18` is a custom fighter with donor 15 it draws an unlocked
  fighter from `0x80097EF0 & 0x13FFF` (IDs 0..13 and 16, never Mokujin himself) with Expanded's
  `draw()`, writes descriptor byte 9 of `0x80097D40 + id * 16` to `actor+0x16`, and logs
  `Custom fighters: <name> copies character <id> this round`. Install → uninstall restores the
  four sources byte for byte (checked). The broken MOKU was deleted from the test folder; a new
  Copycat fighter is needed for the test. Expected in the report: one `copies character` line
  per round and `Custom probe` header keys that follow the drawn IDs.
- **Tested 2026-10-01 (T3CB-PATCH-5, MOKU = ID 42 re-created by the user, Arcade, 1m55s): works
  "very well" per the user.** Draws per round: 9, 1, 12, 2, 7 (Jin, Law, Bryan, Lei, Xiaoyu); each
  time `0x80052958` loads `a1` = the drawn ID and the header key follows (`0900`, `0100`, `0c00`,
  `0200`, `0700`). Between fights `actor+0x16` briefly reads 15 (key 0) again before the next
  draw; harmless, the draw comes before the moves load. The model moves normally.
- **Sword (found in that test):** MOKU held Mokujin's sword with every style; stock Mokujin only
  holds it with Yoshimitsu's. `0x8003615C`: `if (actor+0x18 == 15) actor+0x7C0 = (actor+0x16 == 4)`,
  the only writer of `actor+0x7C0` in SLUS (no direct `jal` caller, so it runs through a table).
  For a custom fighter `actor+0x18` is 41.., so the flag was never updated. **T3CB-PATCH-6:**
  `copycat_sword()` in the roster tick sets `actor+0x7C0 = (actor+0x16 == 4)` every frame for a
  custom fighter with donor 15. Reversible (checked).
- **Tested 2026-10-01 (T3CB-PATCH-6, MOKU, Arcade, 2m19s): works perfectly per the user.** Draws
  6, 7, 4, 13, 9 (Hwoarang, Xiaoyu, Yoshimitsu, Heihachi, Jin), header keys follow each draw;
  the sword showed only in the Yoshimitsu round. So `actor+0x7C0` is the sword flag (1 = held).
- Still open, not fixed: the sword **glow** (`0x8003172C`) runs when `actor+0x18 == 4`, or when
  `actor+0x18 == 15` and `actor+0x16 == 4`. So a custom fighter based on Yoshimitsu, and a Copycat
  fighter that drew Yoshimitsu, have no sword glow. Fixing it means faking `actor+0x18` around a
  long (sliceable) function; not done yet.
- Other `actor+0x18 == 15` checks in SLUS, not looked at yet: `0x80075450` (calls `0x80075548`)
  and `0x800787DC` (sets 246 / 1 before `0x80077724`). They may be more Mokujin-only details.
- Other donors marked "not tested" (Ogre, Gon, Dr. B, True Ogre) may have their own special
  cases; test each before calling it supported.

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

- **Test button (builder 0.3.5):** one click checks that the patch is current (if not it stops:
  Install/Update first), builds when the exe is missing the patch or is older than the patched
  source, starts the game like Play, and when the game closes writes
  `character-builder/logs/test-report.md`: date and time, builder version, patch revision and
  whether it is current, the build result (not needed / succeeded / failed), play time and exit
  code, both copies of `customs.txt`, every game-log line starting with `Custom fighters`,
  `Custom probe` or `TTT1 characters`, and up to 40 other lines matching
  error/fault/failed/exception/assert/crash. The report shows in the UI (Test report, with Copy)
  and survives a restart of the builder. Code: `TestRun` in `server.py`, `/api/test`.
  Verified 2026-10-01: report rendered offline from a real game log; button and panel checked in
  a browser.
- **Test button tested 2026-10-01 (full click, by the user, Expanded 1.1.3 test folder):** patch
  T3CB-PATCH-4 current, build not needed, game ran 56 s (Arcade, Dizzy as P1), exit code 0,
  report written 2 s after the game log closed; 17 log lines, 0 errors, and the values match the
  0.3.3 test (`a1=3`, header `0301`, `actor+0x16 3`, model 7, no `guest in the fight`). The Copy
  button copied the report straight to the clipboard with a real click in the builder window (in
  the automated browser only the select-and-Ctrl+C fallback could be checked). Not yet seen: a
  test run that has to build first (it uses the same `build.start()` as the Build button).
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
