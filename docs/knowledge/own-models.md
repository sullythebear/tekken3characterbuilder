# Own 3D models (format, in-game replacement, FBX import)

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Own 3D models: import and auto-rig (phase 0 research, 2026-10-01, code reading only)

Goal (user): import a 3D model (glTF/FBX) that is rigged automatically and fights in the game.

- **Expanded already writes PS1 models.** `tools/ttt1/model/convert.py` turns a TTT1 3DMK
  (30 rows) into the native Tekken 3 PS1 3DMK (27 rows) and `texpack.py` packs its textures into
  the PS1 costume band. But it *translates* TTT1's own vertex-sharing layout; it does not build
  one. An imported mesh needs that layout generated from scratch.
- **3DMK file:** header u32 rows (27), u32 scale (100), magic `3DMK` (0x4B4D4433), 0, u32 0x5F8
  (= 24 + 27 * 56, header size), first block offset; then 27 rows of 14 i32. Row words:
  0 normals block, 1 polygons, 2 textures (materials + UV), 3..5 offset from the parent bone,
  6 part, 7..9 rest rotation (accessories), 10 drawn flag, 12 vertex block **of the next row**
  (row r reads row r-1's word 12), 13 hand-pose table. Block offsets are file offsets.
- **Vertex block** (`fmt.parse_d`, `simulate.vlist`): u32 head; g1 = bytes, borrows from the
  previous drawn row's slot list (b // 2 - 1); g2 = bytes, borrows from the shared cache
  (b // 2); own vertices 4 x s16 (x, y, z, pad) in the bone's frame; then five tail groups of
  9-bit fields (index & 0xFF, flag 0x100) and one of 2-bit fields: 0 = store the slot in the
  cache (flag: average with what the cache held = the 50/50 joint seam), 1 = average with the
  cache without storing, 2 = average with the previous list's slot, 3 = deposit into the cache,
  4 = copy into the next list (scratch). Slot list = g1 + g2 + own, at most 128.
- **Normals block** (word 0): same list layout as vertices (head, g1, g2, own normals).
- **Polygon block** (word 1): four families with u32 counts; GPU packet sizes 32/40/40/52 =
  0 flat textured triangle, 1 flat textured quad, 2 gouraud triangle, 3 gouraud quad. Record
  sizes 8/8/8/12 bytes. First u32: slot index x 4 in 7-bit fields at shifts 0, 7, 14 (and 23 for
  quads); top bits sometimes set (flags, not decoded). Second u32 of flat records: normal index
  x 4 in the low bits; gouraud records hold one normal per corner. Paul's legs are flat only, so a
  first own model can use flat polygons with one normal each.
- **Texture block** (word 2): `fmt.parse_c_ps1`: u16 UV-table offset, u16 materials (CLUT id,
  | 0x8000 for 8-bit, | 0x100 for the second page), u16 UVs (u | v << 8), then per family a
  count byte and per polygon a material byte plus UV indices.
- **Loading** (`src/tekken3_ttt1_mod.c` `read_model` / `install_model` / `follow_models`): a
  guest's `<prefix>-arcade-P<n>.3dm`, `.relocs` (u32 file offsets of pointer words, each
  relocated by the load address) and `.tim` (textures) from the mod folder; checks 27 rows,
  `3DMK`, header 0x5F8; the model replaces Jin's envelope in memory and is drawn with the
  fighter's animations. `follow_models` skips a fighter on native moves
  (`tekken3_native_moves_id(p) < 23` keeps its own model) - that is every builder fighter, so
  a small patch would let a custom fighter load its own model files.
- **Plan:** phase 1 = write a disc model (e.g. Paul) back out through our own writer as a
  custom fighter's `-arcade-P1` files and see it in game (proves writer, relocations, textures,
  loading); phase 2 = a simple already-rigged import (Mixamo-style bone names -> the 18 T3
  bones, one bone per vertex, flat polygons, vertex sharing at the joints); phase 3 = automatic
  rig for unrigged meshes (estimated joints, adjustable in the 3D view), decimation to the PS1
  budget (Tekken 3 models: 650-1100 triangles), textures to 16/256-colour CLUTs.

## Own 3D models: phase 1 (T3CB-PATCH-10, tested in game 2026-10-01: works)

- **Route taken:** not the guest `-arcade-P1` files (Jin's envelope, one texture page,
  `follow_models`), but an in-place overwrite of the donor's own model after the game loaded
  it. The game keeps its textures, animations and model slot; only the 3DMK bytes change.
- **File:** `characters/<id>/model.bin`, copied by the builder's sync to `<Prefix>-model.bin` in
  both mod folders (removed again when the character has none). Layout: `T3CM`, u16 version 1,
  u16 model number it replaces, u32 new size, u32 relocation count, the stock model's 1536-byte
  header (to recognise the loaded model in memory), the new 3DMK (file offsets), u32 relocation
  offsets (`model_export.relocations`: header +16, row words 0/1/2/12/13 when > 2, the entries of
  the word-13 tables). Written by `model_export.py ownmodel`.
- **Hook:** `tekken3_ttt1_before_init(model)` (called from the wraps of 0x80035BC0, 0x80035190,
  0x80035CE8; about 45 times per fight). Per player: the model pointer 0x8009BD28 + p * 4 must
  match, the stock header must match relocated (pointer words = model + file offset), the new
  size must fit the slot (size table 0x80095A9C + model * 12, first u32). Then the file words are
  written and the relocations added.
- **Verified:** log `own model installed at 801E9588 (P1, ...)`; a check during the fight
  (state 8) shows P1 draws 801E9588 and only 41 words differ from the file, all in the
  word-13 hand-pose table at +24008 (the game writes it at run time, so it is not data to
  compare). Kuma T with the head rows 19 and 20 scaled 1.5x looked normal in game (too subtle
  on a bear); at 2.5x the head is clearly huge (user screenshot vs Yoshimitsu). Writer,
  relocation, size check and loading all work.
- **Phase 2 first import (2026-10-01, tested in game: works).** `model_import.py` (with
  `fbx.py`, `remesh.py`, `decimate.py`; numpy only): Mixamo FBX "Medea" (69 bones, 17,754
  triangles in 202 loose pieces) -> voxel remesh (one closed skin) -> quadric simplification
  -> 810 flat triangles, 22,412 bytes over Kuma (model 22). Drawn in game by P1 with Kuma's
  animations, no crash, 0 words differ from the file. Format facts found on the way (Paul):
  flat record word 1 = (normal list index + 1) x 4; a triangle faces the camera when
  cross(b - a, c - a) points into the body, its normal (unit 4096) points out; normals block
  head = 4 x (1 + g1 + g2), ends with two empty u32 groups; stock rows hold at most 157
  polygons (138 in one family). Textures were still borrowed from the nearest donor triangle.
- **Limit:** the new model must not be larger than the donor's model slot.

## Patch 12 and Medea v17 (2026-10-02, tested in game: works, 480 colours in 2 CLUT runs)

- **T3TX with several CLUT runs (T3CB-PATCH-12):** CLUT id 0xFFFF in the T3TX header means
  "count" runs follow, each u16 id, u16 colours, then the colours; the band follows the last
  run. The patch validates and uploads each run to `504 + player * 4 + (id >> 6)`,
  x `(id & 63) * 16`. Single-run files (patch 11) still work. Install/uninstall checked 4/4 byte
  for byte; build OK.
- **8-bit face (code: `model_import._write`, `texture_bake.face8/band8_into`):** when the donor
  has an 8-bit CLUT at id 0 and at least 32 halfwords in CLUT row 1 (`donor_cluts`), the face
  chart is 8-bit with a 256-colour palette in CLUT 0 (row 0, like Namco's skin palette) and all
  other charts are 4-bit with 16-colour CLUTs in row 1 (ids 64+, as many as the donor fills).
  The face chart is packed over column pairs (twice the 4-bit columns, on a halfword boundary,
  never turned); polygon UVs are 8-bit texels (column / 2), material 0x8000. Nina: 256 + 14 x 16
  = 480 colours.
- **Painted look:** `texture_bake.paint` (3 x 3 median inside each chart) removes photo speckle;
  the face is left out of it (keeps eyes and brows).
- **Loose pieces hang whole on one row** (the row of most of their vertices): the collar no
  longer tears. Toes blunt (cap at 90 %, minimum radius). Head proportion check vs the donor
  (donor 217, Medea 288 game units above the neck joint: no scaling needed).
- Medea v17 over Nina: 1032 triangles, 24148 bytes, GPU packets under 31000.

## 50/50 joint seams in the writer (2026-10-04, verified against the hardware)

- `model_import._write(..., blend={vertex: earlier row})`: the earlier row also holds the vertex
  and deposits it with tail group 3 + flag (the hardware stores half: that slot itself becomes
  half and is not drawn); the owning later row reads it with tail group 0 + flag: slot = own / 2
  + stored half = halfway between the two bones' transforms, and stores the full result for
  later rows. Own list order per row: group-0 reads, full deposits, half deposits, the rest.
- Verified with the renderer probe: re-assembling the slot lists from the recorded per-row GTE
  transforms (`probe_render.assemble`) and projecting with the GTE's H/OFX/OFY matches the
  game's screen coordinates in the scratchpad within 2 px for every drawn slot; only the half
  copies differ (they are halved, as expected).
- Probe frames can be cut by the sampling window (a missing row also misses its cache deposits):
  probe_render only uses frames with every drawn row.

## Bind pose and joint offsets (2026-10-04, tested in game)

- **Joint offsets:** the game places a child row at (x, y, -z) of its words 3..5 in the parent's
  vertex frame (probe: Paul's row 11 sits at (350, 0, -101) for words (349, 0, 100); rows 5/8,
  15 alike). `model_export.world` uses +z: its standing frames W mirror collarbones and hips onto
  the other side. The writer (`_write(..., zsign=-1)` from direct_import) writes offsets with z
  negated; verified: an import's in-game offsets equal Paul's.
- **Bind pose:** in the pose a fighter was modelled in, both copies of every 50/50 seam vertex
  meet. `bind_pose.solve(m, W)` turns each row (parents first) about its joint so its seam
  copies meet the parent's (orthogonal Procrustes, pulled lightly towards W); a row with only one
  or two seam points (upper arms) is turned about the free axis so the polygons towards the
  parent are least stretched. Result: median seam mismatch 3-30 units on 20 donors (Ogre's arm
  180: wings); Paul arms down, Law and Julia T-pose, Jin A-pose, head 21 degrees forward of W.
- direct_import poses the mesh (LBS with the file's weights) into this bind pose; the head no
  longer looks up, shoulders and hips follow like the donor's. Accessory rows (21+) are not used.

## Budgets and bone lengths (2026-10-04, tested in game)

- The binding limit for big imports is the GPU packet budget (~31000 bytes: gouraud triangle 40,
  gouraud quad 52); a quad is drawn as (a, b, c) + (b, d, c), so two triangles sharing an edge
  with the same texels cost 52 instead of 80 at no visual change.
- The game takes joint offsets from the model (words 3..5, z negated), so an import may keep its
  own bone lengths: verified with Medea (Nina) and TOMMY (King) in game.
- Probe frames can mix two moments across the sampling window even when torso and pelvis agree:
  check every joint against its parent's offset and second layers (2/4/20) against their rows.
- **The game reloads the donor's 8-bit face texture into the band during the fight** (tested
  2026-10-04: VRAM snapshot of Medea over Nina at call 2000 had 16 x 64 halfwords at VRAM
  (384, 64) replaced by Nina's face TIM, `x 0 y 64 w 16 h 64 mode 1` in her ARC; every donor
  checked has that TIM). Own textures were re-uploaded once a second, so whatever an import kept
  there flickered (Medea's crotch and hair). T3CB-PATCH-14 uploads the texels every frame;
  snapshots at calls 1200, 2000 and 3500 then match the file texel for texel.
- **A quad is culled by its first triangle** (inferred from the user's screenshots, reproduced
  offline: `QUADCULL=1 probe_render.py` shows the same holes at the crotch and the wrists of
  Medea v12; gone with flat quads, checked in game). Only nearly flat triangle pairs (bend
  <= 12 degrees) may be sent as quads; Namco's quads are flat too.
- A reduced model keeps the winding of its voxel surface per face (one global in/out decision):
  passing the winding along neighbours crossed edges where two sheets touch (a thin collar) and
  turned patches inside out (a hole on top of the hair).
- **tested** (offline decode of model.bin, live fight renders; user report 2026-10-05) A chart has
  one 16-colour palette (CLUT per polygon, palette per UV island). Charts split by normal only
  spanned trousers, knee pad, boot and calf: the trousers got orange/red speckles and pink bands
  that looked like holes (right thigh, knees), although the bake itself was clean. Found by
  decoding the game texture per polygon (`cache/medea/uvdecode.py`: matches the bake in UV
  space) and rendering it on the reduced mesh. Fix: faces get a material label (k-means of
  their source colour in Lab, k=8, neighbour majority twice) and charts never mix labels (the
  face keeps its charts whole); reduced models quantise in Lab (`quantise_groups(lab_=True)`).
  UVs live per polygon corner, so more charts cost no vertex slots, only gutter space (~220
  charts, fewer quads: 35.5 bytes of GPU packets per triangle). The packer's FFTs use sizes
  rounded to 32 (odd sizes were 4x slower): packing 28 s -> 8 s.

