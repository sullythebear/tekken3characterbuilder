# Project status

Updated: 2026-10-20.
- Released: builder 0.8.0 (tag v0.8.0, 2026-10-20), 0.7.1, 0.7.0 and 0.6.0, all with the owner's permission.
- Pushed: `main` up to the 0.8.0 release (2026-10-20).

## In 0.7.0

- Stage Lab: the stage itself as a picture from the fighters' place (scenery model record
  56 + arena decoded), with the colour look and four views; the floor from the stage's own
  tiles (layout approximate). Browser-tested.
- Move Lab: the style's own moves (COMMAND LIST lines of one input, motions such as d, df, f+2,
  During crouch / While rising / During side step, 4 stance moves and 20 throws) and 10 strings, measured in game per style, damage from the disc, changeable with patch 20. A few basic inputs turned out to
  start the style's own move; they are corrected.
- Builder: a mix still too big for its slot is simplified a little (95..80 % of its triangles).
  Body, head and arm mixes: 0 of 1028 fail (body was 34 in 0.6.0). Tested in game.

## In 0.6.0

**Character Builder**
- Body parts: live preview, three-fighter mixes, whole skins, hands.
- Body colours.
- Body shape: head size, plus arms, legs and body thicker or thinner, with presets (Slim,
  Athletic, Heavy, Big head) and Randomize. Tested in game.
- Height tried: the animation sets the pelvis height, so the feet go through the floor. Not
  offered.
- Saved looks, and Randomize with one or two fighters (it draws again when a mix fails).
- Mixes that did not fit now build: textures at half size, the stock packet limit, and coarser
  normals for slots that are just too small. Body mixes failing went from 354 to 29 of 1028 (only slot size
  left, after quad pairing); head 54, arm 28 before quad pairing.

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
- Moves on other buttons per fighter ("Moves on buttons"): patch 21, tested in game. KITTEST's f+2
  starts Liftshot (the style's side-step 2).
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
- The game in the test folder is built with patch 21 (release and debug builds).

## Next

Module order (owner): Character Builder, Model Importer, Portrait Lab, Voice Lab, Stage Lab, Move Lab.
The roadmap's items with clear value are done (2026-10-20). Left:
1. A user play test of 0.8.0: KITTEST was rebuilt in the test folder (Julia head with braids, 1055 triangles; sanity fight 0 words differing).
2. Research with an uncertain result: Stage Lab floor routine and collision; Move Lab's other
   strings and chain throws (not reliable with scripted input); TTT1 styles as donors (when
   Expanded adds more).
3. Push and publish only with the owner's permission.
