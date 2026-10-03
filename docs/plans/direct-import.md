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
