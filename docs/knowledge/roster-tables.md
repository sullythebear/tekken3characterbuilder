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

## Arcade opponents and the rival: patch 22 (2026-10-20, tested in game)

- **code** (Expanded `opponents_tick`, roster.c) 0x800B1FCC draws the ten Arcade / Time Attack
  opponents into 0x800AFB18, 4 bytes each (fighter, costume, stage number): stages 1-4 among the
  first ten fighters, 5-8 the rest, 9 Heihachi (Jin for a Heihachi player), 10 Ogre. Expanded
  rewrites the list once while stage 1 loads: 1-2 guests at stages 5-8, and one game in four
  Devil, Angel or Unknown at stage 9.
- **tested** (scratch `arcade.py`: t3live Arcade, P2's health written to 0 in every fight)
  KITTEST: stages 1-8 differ per run, stage 9 was 40 (a hidden boss) or Heihachi, stage 10
  Ogre (14), then True Ogre (20). Xiaoyu: stage 9 Heihachi (13).
- **T3CB-PATCH-22**: `<prefix>-rival.txt` (one ID, 0-21) puts that fighter at stage 9 for the
  custom fighter, costume 0; where the draw also had it at stages 1-8, Heihachi takes that place.
  Tested: rival Paul (0) at stage 9 in three runs, Ogre and True Ogre after it; log "Kittest has
  rival 0", "rival 0 at stage 9".
- **tested** (scratch `arcade2.py`) Stage 10 (`0x800AFB18 + 36`) written to Heihachi (13) while
  stage 1 loads: KITTEST met Heihachi at stage 10 in his own arena, then the cutscene, True
  Ogre and the ending, no crash. But the cutscene (Ogre grabs Heihachi and turns into True Ogre;
  both cutscene actors are reloaded, P1 = 13) then plays Ogre's animation on the stage 10
  fighter's model with a misplaced camera. So an own final boss is not offered; stage 10 stays
  Ogre.
