# Repository audit (2026-10-16, builder 0.4.0 + patches 17-18)

Basis for the Tekken 3 Studio roadmap (`ROADMAP.md`). Facts are marked **tested**, **code** or
**inferred** as everywhere in `docs/`.

## What exists

| Area | Where | State |
|---|---|---|
| Local server, API, build/launch/test | `app/server.py` (stdlib, ~1500 lines) | **tested**, mature |
| Game patching (exact-text, reversible) | `creator_patch.py`, `expanded_patch_data.py` (patches 1-18) | **tested** each revision, uninstall byte-identical |
| Custom fighters on Expanded's CUSTOM page | `custom_page.py`, `expanded_custom.py`, patch | **tested** in game |
| Fighting style = donor moveset | patch 2-7, UI donor grid | **tested** for all 21 donors (`knowledge/donors.md`) |
| Costume colour variants (palettes) | `ui/costumes.js`, `write_palettes`, patch 9 | **tested** |
| Model import (FBX/GLB/VRM -> PS1 model) | `direct_import.py`, `reduce.py`, `texture_bake.py`, `protrusions.py`, patch 10-14 | **tested** with 11 regression models |
| Kitbash from the disc's own parts | `kitbash.py` | **code**, offline-verified, no UI (paused 2026-10-03) |
| Portrait (image or from the 3D model) | `ui/app.js`, `model_export.own_portrait`, `expanded_custom.py` | **tested** |
| Name call (announcer) | `name_call.py`, `ui/arena.js` | **tested** live (log), not yet heard by the user |
| Home stage and music | patch 17, `ui/arena.js` | **tested** live |
| Packages `.t3char` (no game data) | `export_character` / `import_character` | **tested** round trip |
| CPU opponents, Team Battle icons | patch 15, 18 | **tested** live |
| Tests | `tools/render/regress.py` (needs game data), `tools/t3live.py` (needs the game) | no offline unit tests |

## Gaps against the Tekken 3 Studio goal

1. **No offline unit tests**: every check needs the user's game folder. Pure-Python parts
   (customs.txt lines, packages, name-call packs, validation) can be tested without it.
2. **One editor page holds everything**; the six modules are not visible as such. Model import
   is already its own tab ("3D model"), separate from the fighter's style and colours.
3. **Character Builder from parts**: only `kitbash.py` (Namco parts read from the user's own
   disc, never shipped). No asset library of shippable parts yet.
4. **Stage Lab**: only choosing an existing stage and music works. Tekken 3's stage format is
   not researched; custom stage geometry is unknown territory.
5. **Move Lab**: only whole movesets (donor). The move record (56 bytes) is partly known from
   Expanded's TTT1 tools; no per-move editing yet.
6. **Project management**: one version of a fighter; undo only for the last model import.
7. **Asset licences**: no third-party assets ship; no register yet.

## Order chosen (see `DECISIONS.md` D1)

1. Offline unit tests for the pure-Python core (protects everything after).
2. Studio structure in the UI: module tabs (Fighter/Character Builder, Model Importer, Portrait
   Lab, Voice Lab, Stage Lab, Move Lab) over the existing code, no rewrite.
3. Voice Lab and Portrait Lab extensions (small, verifiable).
4. Character Builder from parts (kitbash UI) with a parts register.
5. Move Lab research: read-only move list of a donor, then the "change one value" experiment.
6. Stage Lab research: stage format; only what the engine allows.
