# Roadmap: Tekken 3 Studio

Six modules over one local app (`character-builder/`). Status words: **done** (tested),
**partly**, **open**, **research** (format/engine not known yet), **blocked** (with reason).

## Phase 0: foundation

| Item | Status |
|---|---|
| Audit, status docs, decisions | **done** (`AUDIT.md`, `DECISIONS.md`) |
| Offline unit tests (`tests/`) | **done** (13 tests, no game data) |
| Regression of the model import (`t3cb regress`) | **done** (needs the game folder) |
| Live checks without a player (`t3live`) | **done** (`t3live fight`, `t3live nav` with Arcade/Team/Practice routes) |

## Phase 1: Studio structure

| Item | Status |
|---|---|
| Module navigation in the UI over the existing pages | **done** (tabs Fighter, Builder, Model Importer, Portrait Lab, Voice Lab, Stage Lab, Move Lab) |
| Model Importer separate from Character Builder | **partly** (own tab "3D model") |
| Project versions / restore points per fighter | **open** (only Undo of the last import) |

## Modules

| Module | Now | Next |
|---|---|---|
| Character Builder | style (donor), name, colour variants, costumes, **body parts from the disc's fighters (similar build, randomizer)** | material/colour presets, package round trip of a kit fighter in game, kit for Recompiled? (no: own models are Expanded only) |
| Model Importer | FBX/GLB/VRM import, parts choices, progress, undo, regression | before/after preview side by side, conversion settings exposed |
| Portrait Lab | image upload + crop, portrait from the 3D model with presets: angle (turned, front, other way, profile), framing (shoulders, close-up, chest), light (front left, flat, dramatic), background (warm, cool, red, dark) | several saved variants per fighter |
| Voice Lab | name call: automatic, own sound (record/file, auto trim + level, optional announcer effect), silent | only one sound per fighter: the game calls one name |
| Stage Lab | home stage + music per fighter (patch 17); **stage colour looks (night, sunset, dusk, ice, inferno, black and white) with texture preview (patch 19)** | own colour/tint; stage geometry is research (`knowledge/stages.md`) |
| Move Lab | whole movesets (donor); **the style's COMMAND LIST read from the disc, read-only tab** | move records (damage, frames) per move; then the one-value change experiment |

## Release

0.4.1 candidate: patches 17-18, stage/music, name call, Team Battle tiles. Needs the owner's
in-game test and approval before tagging (`knowledge/testing.md` "Releases").
