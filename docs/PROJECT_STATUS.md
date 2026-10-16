# Project status

Updated: 2026-10-16. Builder 0.4.0 released; patches 17-18 and the Studio foundation are local.

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
- Commits after `ce31517` are local only (no push without the owner's permission, D6).

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

## Next

1. Character Builder parts (kitbash UI).

`t3live nav` done (Practice route verified).

Module tabs done (browser pane: all six pages switch, values kept).
