# Roadmap: Tekken 3 Studio

Six modules over one local app (`character-builder/`). Status words: **done** (tested),
**partly**, **open**, **research** (format/engine not known yet), **blocked** (with reason).

## Phase 0: foundation

| Item | Status |
|---|---|
| Audit, status docs, decisions | **done** (`AUDIT.md`, `DECISIONS.md`) |
| Offline unit tests (`tests/`) | **done** (13 tests, no game data) |
| Regression of the model import (`t3cb regress`) | **done** (needs the game folder) |
| Live checks without a player (`t3live`) | **done** (Arcade, Practice, Team Battle routes in scratch `nav.py`; to fold into t3live) |

## Phase 1: Studio structure

| Item | Status |
|---|---|
| Module navigation in the UI over the existing pages | **open** |
| Model Importer separate from Character Builder | **partly** (own tab "3D model") |
| Project versions / restore points per fighter | **open** (only Undo of the last import) |

## Modules

| Module | Now | Next |
|---|---|---|
| Character Builder | style (donor), name, colour variants, costumes | parts from the player's disc (`kitbash.py` UI), presets, randomizer |
| Model Importer | FBX/GLB/VRM import, parts choices, progress, undo, regression | before/after preview side by side, conversion settings exposed |
| Portrait Lab | image upload + crop, portrait from the 3D model | camera/light/background presets, several variants |
| Voice Lab | name call: automatic, own sound (record/file), silent | trim/volume controls, variants per costume? (research) |
| Stage Lab | home stage + music per fighter (patch 17) | **research**: stage file format before any editor |
| Move Lab | whole movesets (donor) | **research**: move list of a donor read-only, then one-value change |

## Release

0.4.1 candidate: patches 17-18, stage/music, name call, Team Battle tiles. Needs the owner's
in-game test and approval before tagging (`knowledge/testing.md` "Releases").
