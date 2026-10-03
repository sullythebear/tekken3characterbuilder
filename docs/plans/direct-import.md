# Plan: direct import of PS1-style models

Chosen 2026-10-03 (user): the user supplies a PS1-style model; the builder converts it
technically without changing its look (no remesh, no re-bake).

## Status

- `character-builder/app/glb.py` (glTF binary reader), `direct_import.py` (CLI:
  `direct_import.py MODEL.glb --model N --root GAME --out model.bin`).
- Automatic rig for models without a skeleton (`auto_rig`: T/A-pose, glTF axes Y up, facing +Z;
  joints from the silhouette: arm height from the hands, crotch from the gap between the legs;
  one row per vertex). Scale by hip height above the soles. Normals smoothed over welded
  positions; geometry on welded vertices, UVs per corner.
- Texture: the file's own layout (resized to 256 x 256 if needed), 4-bit, UV islands grouped
  into 16-colour CLUTs (ids 64+, then 128+).
- test2.glb (Tommy Dreamer, Sketchfab, 684 triangles, 256 x 256 texture) over Paul (model 0):
  19348 bytes, offline render clean.
- **Earlier offline renders were mirrored** (compare.py flipped only Y; fixed 2026-10-03: X and
  Y flip, front faces have positive screen area). Text on the shirt now reads correctly.

## Next

1. A custom fighter with Paul as donor to test in game.
2. Rig check in the fight stance (hands, shoulders), joint seams.
3. Builder UI: "Import PS1 model" with donor costume choice and 3D preview.

## In-game test 1 (2026-10-03): texture and face good, proportions wrong

- Cause: the auto rig's crotch came out at 0.6 of the height (a low-poly model has few
  vertices, so "no vertex on the centre line" held almost everywhere): legs reached the chest.
  Now rays along Z through the centre line (lowest hit = crotch), clamped to 0.42-0.50 (baggy
  trousers close the gap low).
- Tekken's root (row 3) sits at the waist, 0.15 of the leg above the hip sockets (Paul): the
  import's root is put at the donor's ratio, then the model is scaled by that height above the
  soles; pelvis/torso split at the new root. Tommy over Paul: scale 1754, ~13 % taller than Paul.
- v2 deployed on TOMMY (test pending).

## In-game test 2 (2026-10-03): worse (chest, thin legs, long neck, shoulders, elbows folded)

The shape-based auto rig cannot place joints reliably; every fix moves the error. Decision:
the user rigs the model in Mixamo (free) and exports FBX Binary (T-pose); `direct_import.py`
now uses a skeleton when the FBX has one (`rig_from_skeleton`: Mixamo names via
`model_import._part/joint`, every vertex on its strongest bone). Untested until a rigged file.
- 2026-10-03: test2.fbx (Mixamo rig, 41 bones) over Paul: same height as Paul, offline clean; v3 deployed on TOMMY (test pending).
- v3 tested in game: much better; light texture glitches (yellow on the head: overlapping UV islands with different CLUTs), hands turned, a hole at the buttocks (per-triangle winding in a crease). v4: islands with >= 6 shared core texels share a CLUT; one global winding decision. Hands: open (the model's), twist still to check.

## v5 (2026-10-04): checked in game by the live setup (probe renders)

- Patch 13: the renderer probe takes TEKKEN3_NATIVE_PROBE_START/_EVERY/_CALLS (defaults =
  Expanded's), so `t3live.py fight --probe` samples two frames out of every 1500 calls over the
  whole fight; `tools/render/probe_render.py GAME model.bin out.png [--pick i,j] [--frames n]`
  renders the import in the exact in-game poses at high resolution (ROWS=1: colour per row).
- Fix 1: the mesh is posed into the donor's standing pose with the file's smooth weights (LBS)
  before writing; the game then turns rows only a little from rest, so one-bone binding no longer
  tears shoulders (T-pose needed 90 degree turns) and hips.
- Fix 2: vertices in the blend zone of hips (thigh -> pelvis) and shoulders (collarbone ->
  torso), child weight < 70 %, stay on the parent row. Applying this at elbows/knees/ankles made
  spikes: limited to hips and shoulders.
- Probe renders of the fight stance: no wing at the shoulder, hips filled, no spikes. Deployed
  on TOMMY (v5).
