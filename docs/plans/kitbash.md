# Plan: kitbash (new fighters from Namco's own parts)

Chosen 2026-10-03 after the FBX import could not reach Namco's look automatically (user).

## Status

- `character-builder/app/kitbash.py` (venv): `build(root, base, parts)` with parts head, torso,
  pelvis, arm_l, arm_r, leg_l, leg_r -> any of the 48 models; base = the donor's model
  (skeleton). Own vertices placed in the base's standing frames (limbs stretched to the base's
  bone lengths); borrowed seam vertices of rows now from another model snap to that row's
  nearest vertex; polygons keep their flat/gouraud family; texels copied as whole halfwords
  into one page per (model, CLUT) cluster; 8-bit CLUT per model (ids 0, 16, 32), 4-bit CLUTs
  from id 64. Written with `model_import._write` (`tex={"ready": texture}`).
- Verified offline: base 10 alone reproduces Nina exactly (except accessory rows 21-26);
  head=20 (Julia) + torso=36 over Nina: clean, Namco look.

## Next

1. Accessory rows 21-26 (ponytail, feathers on other models) with their parts.
2. Builder UI: part pickers per body part with 3D preview, saves `characters/<id>/kit.json`
   and writes model.bin on sync.
3. In-game test (8-bit CLUT ids 16/32 when two models' skin areas are used).
4. Colour variants (existing Clothing tab) on kitbash fighters.
