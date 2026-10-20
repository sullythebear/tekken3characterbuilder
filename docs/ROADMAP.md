# Roadmap: Tekken 3 Studio

Six modules over one local app (`character-builder/`). Status words: **done** (tested),
**partly**, **open**, **research** (format/engine not known yet), **blocked** (with reason).

## Phase 0: foundation

| Item | Status |
|---|---|
| Audit, status docs, decisions | **done** (`AUDIT.md`, `DECISIONS.md`) |
| Offline unit tests (`tests/`) | **done** (13 tests, no game data) |
| Regression of the model import (`t3cb regress`) | **done** (needs the game folder) |
| Regression of the Character Builder (`t3cb kitregress`) | **done** (7 mixes: plain, whole skin, KITTEST, half-size areas, heavy packets, coarser normals, simplified; approved 2026-10-19) |
| Live checks without a player (`t3live`) | **done** (`t3live fight`, `t3live nav` with Arcade/Team/Practice routes) |

## Phase 1: Studio structure

| Item | Status |
|---|---|
| Module navigation in the UI over the existing pages | **done** (tabs Fighter, Builder, Model Importer, Portrait Lab, Voice Lab, Stage Lab, Move Lab) |
| Model Importer separate from Character Builder | **done** (own "Model Importer" tab; Builder body parts on the Builder tab) |
| Licence register per fighter (own model, portrait image, recording) + export warning | **done** (Fighter page "Credits and licences", in packages and restore points; Export warns when a carried asset's licence is not known; tested in the browser) |
| Check library: every fighter against the game folder (Custom page entry, portrait, own model, name call, stage colours) and against itself | **done** (menu "Check library", read-only, "Write the game files again" when files are missing; negative test: hiding KITTEST's model file was reported) |
| Asset library: one view of every fighter's own assets with source, author and licence | **done** (menu "Asset library", unknown licences marked, click opens the fighter; browser-tested) |
| Duplicate a fighter (name + 2, through its package: everything travels) | **done** (unit test; browser: KITTEST 2 got parts, shape, damage, credits, 2 saved portraits; deleted again) |
| Backup of all fighters (.t3backup, read back by Import package) | **done** (download tested: 4 fighters, 7.2 MB; import round trip unit-tested; the import takes up to ~24 MB) |
| Project versions / restore points per fighter | **done** (settings before each save, last 20, Restore on the Fighter page; restoring is itself undoable; 3D model: its own Undo) |
| Share codes: a fighter's settings as text (T3C1-..., no files) and a new fighter from one | **done** (browser: KITTEST's code, 960 characters, made a copy whose rebuilt Builder body was byte-identical; deleted again; unit test with a pasted line break and damaged codes) |
| "Surprise me": a new fighter with a random name, style, stage, music and stage colours | **done** (browser-tested, not saved; the body: Builder tab, Randomize) |

## Modules

| Module | Now | Next |
|---|---|---|
| Character Builder | style (donor), name, colour variants, costumes, **body parts from the disc's fighters (similar build, randomizer, live 3D preview, mixes of three fighters, whole skins, hands), body colours with presets, body shape: head size, arms, legs, body (tested in game on KITTEST); textures at half size when a mix does not fit one page and the stock models' own packet limit (body mixes failing 354 → 0 of 1028; head and arm 0 too: the last ones are simplified a little, tested in game); saved looks (parts, colours, shape under a name, for any fighter); accessories (ponytails, braids, rows 21-26) come with their part (tested in game); pieces of clothing each in their own hue and lightness (tested in game)** | taller/shorter tested: feet go through the floor (the animation sets the pelvis height), not offered; shoes not possible as a separate part (documented) |
| Model Importer | FBX/GLB/VRM import, parts choices, progress, undo, regression, **before (source render) next to after (3D view)** + **Face detail / Body detail for big models** (tested: Medea 60% = 532 triangles) + **pre-import check list: geometry, materials, rigging** (tested on all 12 test models + 3 fighters) + **a separate texture image for models whose texture is not embedded** (Tommy with its texture taken out + the same image as a file: byte-identical model; packages carry it) + **more model kinds: VRoid-style VRMs with skirts, hats and long hair (100Avatars), rigid props on bones, rig helper bones, a build check (long legs warned, chibis refused), VRM 1.0, props on a separate skin (Seed-san's robot arm: one removable part)** (`plans/direct-import.md`) | — |
| Portrait Lab | image upload + crop, portrait from the 3D model with presets: angle (turned, front, other way, profile), framing (shoulders, close-up, chest), light (front left, flat, dramatic), background (warm, cool, red, dark), **saved portraits: keep, use again, delete (12 per fighter; tested on KITTEST), carried in .t3char packages; portrait from the style's first costume for fighters without an own model (browser: Law style); background "My home stage" (the Stage Lab render of the fighter's home stage in its colours; browser-tested)** | — |
| Voice Lab | name call: automatic, own sound (record/file, auto trim + level), silent; **choice of the installed Windows voice; own sound: pitch -30..+30 %, echo none/hall/arena, Announcer preset (tested in the browser)** | only one sound per fighter: the game calls one name |
| Stage Lab | home stage + music per fighter (patch 17); **rival at Arcade stage 9 (patch 22, tested in game)**; **stage colour looks (night, sunset, dusk, ice, inferno, black and white) with texture preview (patch 19)** | **own colour + strength** done; **the stage itself as a picture from the fighters' place (scenery model record 56 + arena decoded, View front/right/back/left; browser-tested)**; floor and collision not known (`knowledge/stages.md`) |
| Move Lab | whole movesets (donor); **the style's COMMAND LIST read from the disc, read-only tab; damage of the basic inputs read from the moveset on the disc (column + grid)** | **research:** native move records found in RAM (header 0x800ADC20, 56-byte records, damage = word 5 low; `knowledge/moves.md`), not raw on the disc; **damage of basic inputs editable per fighter (patch 20, tested in game)**; **the style's own moves: 99 records measured in game (single inputs, motions, during crouch / while rising / side step, stances, 20 throws) and 10 strings with damage per hit, damage editable (patch 20, a throw tested in game)**; **moves on other buttons: any of the style's moves (not throws) on a basic input, strings come along (patch 21, tested in game)**; **fairness check: traffic lights against the cast's damage, Fair / Just for fun saved with the fighter (browser-tested; `DECISIONS.md` D10)**; not measured: most strings (indistinguishable from separate moves), chain throws |

## Release

v0.8.0 released 2026-10-20 (Builder accessories, pieces of clothing); v0.7.1 the same day (Model Importer: more model kinds); v0.7.0 and v0.6.0 released 2026-10-19; v0.5.1 released 2026-10-16 (kitbash HUD text fix); v0.5.0 the same day (patches 17-19, Studio modules, name call Silent by default) (`knowledge/testing.md` "Releases").
