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
| Project versions / restore points per fighter | **done** (settings before each save, last 20, Restore on the Fighter page; restoring is itself undoable; 3D model: its own Undo) |

## Modules

| Module | Now | Next |
|---|---|---|
| Character Builder | style (donor), name, colour variants, costumes, **body parts from the disc's fighters (similar build, randomizer, live 3D preview, mixes of three fighters, whole skins, hands), body colours with presets** | body shapes (proportions); shoes not possible as a separate part (documented) |
| Model Importer | FBX/GLB/VRM import, parts choices, progress, undo, regression, **before (source render) next to after (3D view)** + **Face detail / Body detail for big models** (tested: Medea 60% = 532 triangles) + **pre-import check list: geometry, materials, rigging** (tested on all 12 test models + 3 fighters) | — |
| Portrait Lab | image upload + crop, portrait from the 3D model with presets: angle (turned, front, other way, profile), framing (shoulders, close-up, chest), light (front left, flat, dramatic), background (warm, cool, red, dark), **saved portraits: keep, use again, delete (12 per fighter; tested on KITTEST)** | saved portraits are not in exported packages |
| Voice Lab | name call: automatic, own sound (record/file, auto trim + level, optional announcer effect), silent | only one sound per fighter: the game calls one name |
| Stage Lab | home stage + music per fighter (patch 17); **stage colour looks (night, sunset, dusk, ice, inferno, black and white) with texture preview (patch 19)** | **own colour + strength** done; stage geometry is research (`knowledge/stages.md`) |
| Move Lab | whole movesets (donor); **the style's COMMAND LIST read from the disc, read-only tab** | move records (damage, frames) per move; then the one-value change experiment |

## Release

v0.5.1 released 2026-10-16 (kitbash HUD text fix); v0.5.0 the same day (patches 17-19, Studio modules, name call Silent by default) (`knowledge/testing.md` "Releases").
