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

## CPU behaviour per fighter: patch 22 (2026-10-20, tested in game)

- **code** (Expanded `tekken3_difficulty_mod.c`) 0x80061488 picks the CPU's behaviour from the
  table at 0x800231AC: 3 difficulties x 10 stages, 110-byte blocks, copied into the player's AI
  structure at +568 (the HARD / stage 10 block also at +678).
- **tested** (scratch `aiprobe.py`, full RAM dump) The AI structures are at 0x8009F318 +
  0x330 * player: in an Arcade stage 1 fight on MEDIUM, both +568 held block (1, 0), and the
  HARD / stage 10 block was at +678 of both.
- **tested** (scratch `aieffect.py`, `aieffect2.py`; Arcade stage 1, the CPU's Jun fixed with
  TEKKEN3_CPU_STAGE1) The block written to P2's +568 every 10 frames:
  - P1 standing still: the CPU dealt exactly the same (318) with EASY / stage 1 and HARD / stage
    10: the block does not change its attacks on a still opponent;
  - P1 pressing f+1 every 10 frames for 40 s: EASY / stage 1 let 46, 44 and 36 hits in and dealt
    257-335; HARD / stage 10 let 5-7 in and dealt 374-490. The block sets blocking and
    punishing.
- **T3CB-PATCH-22** `<prefix>-cpu.txt` (one block number, 0-29): while the CPU plays the custom
  fighter (the player who is not 0x800AE1F8's human), its +568 holds that block every frame of a
  fight. The builder offers Calm (0, EASY stage 1), Steady (14, MEDIUM stage 5), Fierce (29,
  HARD stage 10).
- **tested** (scratch `aicpu.py`, `aicheck.py`) KITTEST as the CPU's stage 1 opponent (Xiaoyu
  P1): P2's +568 held block (2, 9) with `-cpu.txt` 29, P1's its own (1, 0); log "Kittest has CPU
  block 29". P1's f+1 every 10 frames for 40 s: Calm let 17 and 27 hits in and dealt 314 and
  323; Fierce let 16 and 15 in and dealt 370 and 387. Smaller than with Jun, the same direction:
  how much the block changes depends on the style.
