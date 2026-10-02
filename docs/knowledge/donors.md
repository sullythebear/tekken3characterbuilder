# Donors: principle, style layer, donor tests

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

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
