# Conversion engine: the project directive against what exists (2026-10-23)

The user's directive "Intelligent 3D Import & PS1 Conversion Engine" (10 sections, 6 phases),
held against the repository. Most of it exists already in the Model Importer
(`plans/direct-import.md`); this file lists per section what works, what is missing and what the
game itself limits. Facts: **tested** (seen in game), **code**, **inferred**.

## How the game takes a new character (code + tested; `knowledge/own-models.md`, `donors.md`)

- A custom fighter borrows a stock fighter's slot (the donor / fighting style): its moves, throws,
  hitboxes, animations, CPU and voice. Only the 3DMK model bytes (and its texture) are replaced.
- The model must be Namco's format: 20 rigid rows on the donor's skeleton (rows 1-20, one bone
  per vertex, joint rings shared between rows), quads and triangles in GPU packets (<= ~31000
  bytes), the donor's slot size (e.g. 26028 bytes), one 4-bit texture page with CLUTs.
- So animation retargeting from the source file is not needed to make a character playable:
  the game drives the new model with the donor's own animations (tested: every imported fighter
  fights). What matters is that the model is cut into the donor's rows at the donor's joints.
- New animations and movesets: the game reads Namco's animation and move records (`moves.md`);
  moves can be changed and moved to other buttons (patches 20, 21), but new motion data is
  undocumented. Converting another game's moveset is not possible by renaming files.

## Per section

| Directive | State | Where |
|---|---|---|
| 1. Upload model + TGA textures, skeleton optional | **done**: .fbx (binary/ASCII), .glb, .gltf, .vrm, .obj, .dae/.zae, .zip; .png/.jpg/.tga, 64 images, matched to materials automatically or by hand | `direct_import.py`, `formats.py`, `server.py` |
| 3. Analysis report | **done**: size, triangles, materials, textures (found/missing/unused), UVs, skeleton, weights, rigged / chibi / static, hidden layers, warnings | `direct_import.inspect`, `checks` |
| 3. Body regions, confidence | **done**: bones mapped by name or by the skeleton's shape, else automatic rig (`autorig.py`); mapping table per body part with sure / likely / check (`direct_import.rig_map`; candidates, swapped sides) | A, 2026-10-23 |
| 4A. Geometry | **done twice**: free reduction (`reduce.py`) and the **Tekken rebuild** on the donor's Namco topology (`rebuild.py`, default for big models) | |
| 4B. Proportions | **done for the rebuild**: head, arm and leg thickness, hands, feet (70-150 %, `rebuild._shape`, after the bake); shoulders not (the joints would move) | B, 2026-10-23 |
| 4C. Textures | **done**: baked atlas, 4-bit CLUTs as Namco's, see-through texels, originals kept | `reduce.bake_atlas`, `texture_bake.py` |
| 4D. PS1 look in the preview | **done**: the preview decodes the PS1 texture exactly (CLUTs, sharp texels); "PS1 look" switch adds vertices on the 320 x 240 grid and affine texture mapping (`costumes.js`). Lighting and the game's depth sorting are not imitated: the game draws its own | D, 2026-10-23 |
| 5. Skeleton mapping, auto rig | **done**: name mapping (Mixamo, Unreal/MetaHuman, VRM, Blender), automatic rig with a rig view to drag joints and paint parts | `autorig.py`, `rigview.js` |
| 6. Animation retargeting | not needed for play (see above); source animations are not read | game limit |
| 7. Moveset | the fighting style's moveset, move edits by patch; mapping other games' movesets: not possible without motion data | game limit |
| 8. Workflow, progress, compare | **done**: upload, check list, before/after, progress, Test button builds and plays | `model3d.js` |
| 8.10 Conversion report | **done**: `characters/<id>/import-report.md` on every import, "Conversion report" button saves it (`server.import_report`) | C, 2026-10-23 |
| 11. Quality control | **done**: `t3cb regress` (holes, speckles, fit, 30+ models), 81 unit tests, live fights with probe renders | `tools/render/` |

## Order of work

A. Rig mapping table with confidence in the check list (per Tekken row: source bone, how found).
B. Proportion settings for the Tekken rebuild: head size, arm and leg thickness, hand and foot
   size, shoulder width (defaults = the import's own; presets labelled as estimates).
C. Conversion report: the check list, the mapping, the build log and the numbers, as a file.
D. PS1 preview switch (nearest texels, affine mapping) in the builder's 3D view.
E. Rebuild quality: long hair and buns as swinging accessory rows, the face in Namco's layout.

## Implementation log

2026-10-23
- Inspected: docs (INDEX, own-models, t3-model-style, donors), the importer (`direct_import`,
  `reduce`, `template`, `model_import`, `server`, `ui/model3d.js`).
- Tekken rebuild (`rebuild.py`, see `direct-import.md`): default for big models; NIKKI, Michelle,
  readyplayer.me, Soldier built; NIKKI checked in live fights (probe renders, front and back).
- A: `direct_import.rig_map` + check line + table in the check list. Tried on NIKKI (head and
  shins "likely": a necklace and twist chains), Michelle, VRM_Sample (repeated skeletons no longer
  counted), Soldier, Lydia, mixamo: all sure.
- B: proportions for the rebuild (UI selects, `clean_import_settings` "shape"); NIKKI with head
  120 %, arms 120 %, legs 110 %, hands 120 % rendered.
- C: conversion report; end to end through `server.check_model` + `import_model` on PAINTTEST
  (Soldier, auto-rigged): report written and served; PAINTTEST rebuilt (1068 triangles).
- Tests: 84 unit tests OK (new: head joint, quad charts, shape settings, rig map, report);
  browser: Build/size selects and report button present, report API error text checked.
- Not verified yet: the user's own test of the new UI and of NIKKI/PAINTTEST in game.
- D: "PS1 look" switch in the 3D preview (checked in the browser pane: draws, no errors; first
  try did not link - a uniform shared by both shaders needs one precision).
- Next: E (hair as accessory rows, Namco face layout).

## End-to-end validation (2026-10-23)

Run through the builder's real HTTP API (`/api/characters`, `/api/model/check`,
`/api/model/texture`, `/api/model/import` + `/progress`, `/api/ownmodel/<id>`, `/api/model/report`,
`/api/export/<id>`, `/api/import`) by a script that only talks HTTP (scratch `e2e.py`, `rt.py`), on
new fighters E2ENIKKI and E2EELB (author "e2e test"); source files copied, originals untouched.

Where a source model becomes a converted character (code): `server.import_model` runs the import
tool, which calls `direct_import.build` and writes `characters/<id>/model.bin` (Namco 3DMK + PS1
texture page). Everything before is analysis; everything after (preview, PS1 look) only draws
that file.

| Stage | Files and functions | Real or preview |
|---|---|---|
| Reading, formats | `formats.to_glb` (.obj/.gltf/.dae/.zip), `fbx.py`, `glb.py`, `collada.py`, `direct_import._load` | real |
| Texture images (TGA) | `server.upload_texture`, `direct_import.set_texture_images`, `texture_plan`, `_apply_textures`, `_drop_hidden` | real |
| Skeleton mapping | `model_import._part`, `joint`, `direct_import._align_skeleton`, `_name_by_shape`, `rig_from_skeleton`, `rig_map` | real |
| Automatic rig | `direct_import._auto_rig`, `autorig.auto_rig` | real |
| Geometry | `rebuild.rebuild` + `template.build` (Tekken rebuild) or `reduce.reduce` (free reduction), `protrusions.apply` | real |
| Texture conversion | `reduce.bake_atlas` (256 x 256 atlas), `direct_import._build` (4-bit CLUTs, PS1 colours), `texture_bake` | real |
| Writing the game model | `direct_import._build`, `model_import._write`, `model_export.own_model_file` | real |
| Preview | `ui/costumes.js` (decodes the written file), "PS1 look" switch | preview only |
| Animation | the fighting style's own animations drive the rows; no retargeting | game route |
| In game | `t3live.py fight --probe` (debug build), `probe_render.py` | real |

Measured (both rebuilt; 3DMK = the game's model bytes):

| | E2ENIKKI (NIKKI, Unreal FBX) | E2EELB (elf, Collada, no skeleton) |
|---|---|---|
| Source | 44112 triangles, 132336 vertices, 6 materials, 381 bones | 14208 triangles, 42624 vertices, 4 materials, auto rig (24 bones) |
| TGA images | 23 (256-2048 px, RGBA): 5 materials matched by name, eye shell left out, 15 normal/mask maps left out | 4 (1024 px; the DAE asks for .jpg, matched by stem); the base plate left out |
| Converted | 1052 triangles = 194 triangles + 429 quads, 18 rows, 25708 of 26028 bytes | 1073 triangles = 219 + 427 quads, 18 rows, 25792 of 26112 bytes |
| Texture | one 256 x 256 page, 4-bit, 512 colours in 32 CLUTs | the same |
| In game | installed, drawn, 0 of 6043 words differ (fight vs Lei) | installed, drawn, 0 of 6064 words differ (fight vs Yoshimitsu) |
| Round trip | package export -> import (source + TGAs, not the model): rebuilt byte-identical (SHA-1 match) | - |

Failures found and fixed on the way:
1. A hole in the back of a thigh: the one-sided-extras filter dropped every polygon touching
   a holster vertex, also the thigh's own. Keeping them brought the flap back. Now each
   one-sided vertex is moved onto the mirrored vertex of the other leg: the holster folds flat
   onto the thigh and its empty polygons merge away (`template`, `flat_to`); no hole, no flap.
2. A few donor faces folded over by the projection faced inwards: turned (`turn_hidden`).
3. The elf did not fit Nina's GPU packets (31152 of ~31000) and the import stopped: quads up to
   90 degrees, flat shading, the 6 smallest polygons out (`FLAT_BELOW`, `FEWER`), and as a last
   resort the free reduction, said in the log and the report.
4. The elf's base plate was kept because its material asked for an image that was there; the
   stand check now comes first (`texture_plan`). Its automatic rig was built on the plate.
5. The elf's automatic rig is still wrong (torso 4 % of the height, spine below the hips): now
   flagged "check" in the mapping table and the check list (`_rig_sense`); the rebuilt elf has a
   black head and thin arms - it depends on the joints more than the free reduction does.

Verdict: NIKKI (a rigged modern model with separate TGAs) converts into a recognisable Tekken 3
style character that plays in game. The elf (no skeleton) imports and plays, but looks wrong
because the automatic rig misplaces the torso; the app now says so instead of hiding it.

## Anatomy phase: debug view, automatic rig, E2EELB (2026-10-23)

Tools (code): `anatomy.analyse(src)` collects the converter's own reading - region per triangle
from the skin's heaviest bone (the same bones and weights the build uses), the Tekken row per
triangle (`rebuild.vertex_rows`, shared with the build), joints and skeleton
(`direct_import.rig_from_skeleton`), the file's bones, materials left out, uncertain regions
(`rig_map` "check"). Shown by the builder's "Anatomy debug view (for developers)" (WebGL, layer
switches; `/api/model/anatomy`, `ui/anatomy.js`, checked in the browser pane) and by
`tools/render/anatomy_render.py MODEL out.png` (front, side, back, rows; used for every step).

Root causes found on the elf (tested, renders and numbers):
1. Its base plate was used (fixed before: stand check first).
2. Shoulders at 62 %, hips at 63 % of the height: the arm's way runs from the hand to the
   torso's middle through voxels; the elf's hands hang against a flared pleated skirt (x up to
   +-1.0, the hands at +-1.4), so in voxels the way runs straight in over the skirt at hip height.
   More voxels did not cure it (160: one side right; 240: 46 s and still 80 % / 88 %), nor a
   stronger pull to deep voxels (no change; benchmark mixed). The mesh can tell: the hands are
   pieces of their own inside the sleeves, and a sleeve's surface meets the body only at the
   shoulder. Fix (`autorig`): when the shoulders come out within 12 % of the height of the hips,
   the arms are traced again over the surface (`_surface_graph`: welded edges + joins where
   pieces touch, `_surface_ways` to the top of the head) and the shoulder is where a cut across
   the way, taken over the surface only, widens to twice the arm's (`_surface_arms`). Elf:
   shoulders 75 %, elbows 65 %, wrists 57 %, neck 79 %. The rig benchmark (30 rigged models) is
   identical: the second pass never runs on them.
3. The torso row covered the face: the torso was fitted to its neighbours' triangles, the head
   with all its long hair among them (NIKKI's "fur collar" too); and it kept the donor's length,
   while a long-legged import has a short upper body (the scale follows the hips). Fixes
   (`template`): body rows ignore the head's triangles (`no_head_for_body`); the torso and
   collarbones to the import's hips .. neck (`fit_torso`, elf x0.50).
4. No eyes: the donor head stayed at Nina's size (rays and smoothing from the donor's size, ratio
   0.79) and below the face; the eyes landed on the top of the low head. Fixes: the head first
   scaled to the import's neck .. top (`fit_head`, elf x1.57, NIKKI x0.85), a head may take 3x
   the donor's thickness (`WIDEST`), the face is also every forward head polygon below the hair
   line, and samples the bake's short ray misses get a longer one (`reduce.FAR_RAY`): elf
   61 % -> 80 % of the samples hit the original.

Result (E2EELB through the HTTP API, donor 5): 1083 triangles, in game (0 of 5852 words differ),
recognisable: blonde hair, green eyes, headband, white sweater with sleeves, green skirt,
stockings and boots. NIKKI improved too (no fur collar, clean shoulders), PAINTTEST unchanged.

Still wrong on the elf: the long hair is not there (left out on purpose: no room in the slot
yet), one eye comes out pale (a strand of hair in front of it?), skin patches on one thigh, the
skirt is smaller than the original's; the right arm takes a piece of the skirt behind the hand
(the anatomy view shows it). Next: hair as a piece within the budget, then those.

