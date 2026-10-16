# Plan: kitbash (new fighters from Namco's own parts)

Chosen 2026-10-03 after the FBX import could not reach Namco's look automatically (user).

## Status (2026-10-16: in the builder, Builder tab "Body parts")

- **tested** in game (t3live, Nina base, 0 words differ, clean textures): Julia head + Jin 1
  torso; Xiaoyu 2 head/body + Lei 2 arms + Xiaoyu 2 right leg. Offline renders clean: Xiaoyu head,
  Julia head + Law body, Lei head, Law body, Lei arms, Xiaoyu legs on Nina.
- Parts are `head` (rows 19, 20), `body` (1-4), `arm_l/r`, `leg_l/r`. Row 20 must stay with the
  head: models put the back of the head or the chest in it (Heihachi), so splitting there tore heads.
- **Fit gate**: only models within 7 % of the base's standing height (`kitbash.FIT`, `--heights`,
  cached in `cache/kit-heights.json`). Heihachi (+8 %) on Nina: gaps at the waist and ankles,
  floating feet; refused with a message. 28 of 49 models fit Nina 1.
- 8-bit CLUTs: one per source CLUT (was one per model: Heihachi's torso took his head's colours).
- Texture budget: parts of many fighters may not fit one page (Bryan 1 arm + leg on Nina): refused
  with "take parts from fewer different fighters"; the randomizer uses one or two fighters.
  Random builds: 5 of 6 built.
- `model_export.own_model_file` splits CLUT runs over 256 colours (the game refused the file).
- Packages carry `own_model.kit`; import rebuilds the model (`build_kit`, no disc data shipped).

## Earlier status

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

## CLUT space (tested 2026-10-16, user report "text glitches" in fights)

- Every stock model keeps its CLUTs in its player's rows at row 0 x 0..255 (one 8-bit CLUT),
  row 1 x 0..255 and row 2 x 0..159 (Nina, King, Julia, Heihachi read from the disc). A kitbash
  model of three fighters wrote a second 8-bit CLUT at row 0 x 256..511 and 4-bit CLUTs up to
  row 1 x 527: the fight HUD's top text ("STAGE 1", timer, "CREDIT 0") turned to orange blocks.
- Now: all 8-bit areas share the one 8-bit CLUT (texels renumbered, closest colours merged when
  more than 255), identical 4-bit CLUTs once, 4-bit CLUTs only in row 1 (16) and row 2 (10). A mix
  that needs more refuses with "take parts from fewer different fighters"; the randomizer takes
  one other fighter. Live: Xiaoyu head and legs on Nina, HUD text clean, 512 colours in 2 runs.
- Limits seen: three fighters (Nina, Xiaoyu, Lei) need 33 small CLUTs; Law's body and a full
  Xiaoyu do not fit one texture page (also before this change).
