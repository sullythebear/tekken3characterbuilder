# Project status

Updated: 2026-10-18.
- Released: builder 0.5.1 (tag v0.5.1).
- Pushed: `main` up to ae9d9fb, with the owner's permission (2026-10-18).
- Local commits since then are not pushed.

## Since 0.5.1 (all local unless pushed above)

**Character Builder**
- Body parts: live preview, three-fighter mixes, whole skins, hands.
- Body colours.
- Body shape: head size, plus arms, legs and body thicker or thinner, with presets (Slim,
  Athletic, Heavy, Big head) and Randomize. Tested in game.
- Height tried: the animation sets the pelvis height, so the feet go through the floor. Not
  offered.
- Saved looks, and Randomize with one or two fighters (it draws again when a mix fails).
- Mixes that did not fit now build: textures at half size, the stock packet limit, and coarser
  normals for slots that are just too small. Body mixes failing went from 354 to 52 of 1028; head
  54, arm 28.

**Model Importer**
- Face and body detail settings for big models.
- Check list before import: geometry, materials, rigging. Tested on 12 test models and 3
  fighters.
- "Choose texture image" for models whose texture is a separate file. Tested byte-identical.
  A model without any texture no longer crashes.

**Portrait Lab**
- Saved portraits: keep, use again, delete (12 per fighter). Packages carry them.
- Portrait from the style's first costume for fighters without an own model.

**Voice Lab**
- Choice of the installed Windows voice.
- Own sound: pitch -30 to +30 %, echo none/hall/arena, Announcer preset.

**Move Lab**
- Damage of every basic input, read offline from the moveset on the disc (BNS record
  280 + key).
- Damage editable per fighter: patch 20, tested in game. KITTEST's 3 does 60 instead of 25, and
  the opponent is untouched.
- Research in `knowledge/moves.md`: records, cancel lists, input bits, strings.

**Studio**
- Licence register per fighter, with a warning on Export.
- Asset library across fighters.
- Check library (against the game folder).
- Backup of all fighters (.t3backup), read back by Import.
- Duplicate a fighter.
- 0.6.0 candidate: version, README, app README; release notes in the scratch release folder.
  Not published.

## Tests last run (2026-10-18)

- Unit tests: 50 pass (`python -m unittest discover -s tests`).
- End to end: a new fighter ZETA through every module, into the game, and deleted
  (`knowledge/testing.md`).
- `t3cb regress --all`: all 11 models are the same as before (run again 2026-10-18, after the
  texture and writer changes).
- Live with `t3live`:
  - KITTEST with its body shape: model check 0 words differ.
  - Patch 20 in Arcade and in a Practice mirror match.
  - Damage in Practice's attack data: Xiaoyu 3, 024 → 072.
  - Input tests for Xiaoyu and Law.
- Browser pane: every new tab and dialog.
- Patch 20 putting values back: tested by simulation (actor id switched), see `knowledge/moves.md`.

## For the owner to check

- KITTEST (my test fighter) has:
  - a big head, thick arms and a wide body;
  - two saved portraits;
  - portrait licence "My own work";
  - 3 = 60 damage.
  Remove or change it as you like.
- Your fighters (Tommy, Medea, Test) were not changed. Check library and Asset library list
  their unknown licences.
- The game in the test folder is built with patch 20.

## Next

Module order (owner): Character Builder, Model Importer, Portrait Lab, Voice Lab, Stage Lab, Move Lab.
1. Stage Lab: stage geometry stays research (`knowledge/stages.md`).
2. Move Lab: the moves a style does differently in a stance or crouch (its own cancel lists).
3. Release 0.6.0 when the owner wants it. Push and publish only with permission.
