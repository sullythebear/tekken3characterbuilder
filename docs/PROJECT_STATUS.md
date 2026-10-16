# Project status

Updated: 2026-10-16. Builder 0.5.1 released (tag v0.5.1): kitbash HUD text fix on top of 0.5.0 (Studio modules, patches 17-19).

## Done this session

- Own stage and music per fighter (patch 17), name call (automatic / own sound / silent),
  Team Battle tiles of both guest pages (patch 18). All tested live (see `COMPATIBILITY.md`).
- Studio foundation: `AUDIT.md`, `DECISIONS.md`, `ROADMAP.md`, `COMPATIBILITY.md`,
  `ASSET_LICENSES.md`, offline unit tests (`python -m unittest discover tests`: 13 pass).

## Tests last run

- Unit tests: 13/13 pass.
- Live: Arcade Medea vs CPU Tommy (own models, 0 words differ), Practice name call, Team
  Battle select/FIGHT/FIGHT 2/results with a mixed team.
- Not run: `t3cb regress` (import code unchanged since its last green run).

## Known open points

- The name call has not been heard by a person (headless runs have no audio).

## Since then

- Character Builder body parts (kitbash in the UI, fit gate, packages rebuild them): tested in
  game and in the browser pane, see `plans/kitbash.md`.
- Portrait Lab presets (angle, framing, light, background): tested offline and in the UI.
- Voice Lab: announcer effect for own recordings (unit test; browser pane: processed, playback
  blocked only by the automated browser's autoplay rule).
- `t3live nav dump:NAME` (whole RAM). Move Lab: the style's COMMAND LIST decoded for all 21
  styles (ARC member 4, word tokens read off the game's screen), shown read-only in the Move Lab
  tab (browser pane: King 20 moves).
- Regression `t3cb regress --all`: 11 models, all byte-identical (after the CLUT-run split).

- Stage Lab: stage colour looks (patch 19: night, sunset, dusk, ice, inferno, black and white)
  with a texture preview; tested in game (night, sunset on Gon's beach) and in the browser pane.
- Restore points per fighter (last 20 saves, Restore on the Fighter page): unit tests, browser pane.
- Stage Lab own colour + strength; Builder "Surprise me" scheme and a clear message for colour
  variants on an own-model costume (tested in game: such a variant never shows).
- Model Importer: "Show before" (source render) next to the 3D result (browser pane, Tommy).
- 0.5.0 candidate: README, version, `release/RELEASE-NOTES-0.5.0.md` (not published).
- Unit tests: 25 (some run twice through test-class inheritance).

## For the owner to check

- Hear the name call (Practice) and see the new tabs in the real app window.
- The test folder has my test fighter KITTEST on the Custom page (kitbash body, sunset stage);
  remove it in the builder if you do not want it. Tommy is back to its own settings.
- Name call: Silent by default (owner, 2026-10-16); auto-made packs of Tommy, Test, Medea removed.

## Character Builder round (2026-10-16, after 0.5.1, local)

- Live 3D preview of a mix before Build (cache only); mixes of three fighters (4-bit CLUTs over
  the room become 8-bit); whole skins (a model keeps its page layout and 8-bit CLUT); hands
  (gloves) as a part; feet tried and dropped (documented); the body's own colours with presets
  (works in game, unlike colour variants on an own model); randomizer with colours.
- Tested: offline renders, browser pane, live fights (KITTEST: HUD clean in every build).
- Unit tests: 26 pass.

## Next

Module order (owner, 2026-10-16): Character Builder, Model Importer, Portrait Lab, Voice Lab,
Stage Lab, Move Lab.

1. Model Importer: done for now (detail settings, pre-import check list).
2. Portrait Lab: several saved portrait variants per fighter.
3. Character Builder: body shapes (proportions) if the skeleton allows it.
