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

## Live preview (2026-10-16)

- Changing a body part (or Randomize) builds the mix in the cache (`kit_preview`,
  `/api/kit/preview`, `cache/kit/<base>-<parts>.bin/.json`) and shows it in the 3D view
  (`T3Costumes.preview`, held until the fighter or its model changes); the saved model is not
  touched. A mix that does not fit says why before Build. Browser pane: Julia head + Law body +
  Xiaoyu legs shown; Xiaoyu 2 head/body + Lei 2 arms: "28 small colour tables, room for 26".

## More fighters per mix (2026-10-16)

- 4-bit CLUTs that agree on every index their texels use share a slot (lossless; in practice
  rare: palettes use all 16 indices).
- Over 26 small CLUTs: the smallest 4-bit areas become 8-bit ("wide": twice as wide in the page,
  UV columns dst + 2 x (src - lo)) and take colours from the shared 8-bit CLUT (Ward merge to
  255). Xiaoyu 2 head/body/right leg + Lei 2 arms on Nina (was refused: 33 tables): 7 tables
  converted, offline render clean, live: HUD text clean, 672 colours in 3 CLUT runs (exactly the
  stock space), 0 words differ. What still refuses: a mix whose textures exceed one page.

## Page layout (2026-10-16)

- Each model in turn (most texels first) keeps its own page layout: its areas stay where they
  are, may overlap where they are the same texels, and its main 8-bit CLUT stays as it is (no
  renumbering; other fighters' 8-bit colours take its unused indices, else the closest colour).
  The rest is packed into the free space; if no model can keep its layout, everything is packed
  anew. Now built: a whole Xiaoyu (live: on Nina's moves, HUD clean, 496 colours in 2 runs) and a
  whole Julia on Nina; still refused: Law's body on Nina (two full pages) and Law's arms + legs
  (too many polygons: "more polygons than the game draws for one fighter").

## Hands (gloves) as a part (2026-10-16)

- `hands` = rows 14 and 18, put over the arms only when chosen (old kits unchanged). Lei's hands
  on Nina: offline render and live clean. `feet` (rows 7, 10) was tried and dropped: models split
  leg and foot differently (Nina's shin row runs into her boot), other fighters' feet floated
  under her shins.

## The body's own colours (2026-10-16)

- Hue / saturation / lightness sliders and "Keep skin tones" under Body parts; kitbash
  `--colours=h,s,l,keep` recolours every CLUT of the build (`kitbash.recolour`; skin = red the
  strongest, orange to pink, not grey: light skin reads as highly saturated in HLS, Nina's
  30,22,16 is s 0.88). Stored as `own_model.colours`, carried by packages, part of the preview
  cache key. Works without other parts too: the style's own body in new colours, which reaches
  the game (colour variants do not reach a costume with an own model). Live: KITTEST hue -60,
  blue outfit, skin kept, HUD clean.

## Body shape (2026-10-16, tested in game)

Vertices are scaled in their row's local space inside `place()`. Every bone runs along local +X.
- **Head (rows 19/20):** all axes, 0.85-1.3.
- **Arms (11-13, 15-17) and legs (5, 6, 8, 9):** Y and Z only, 0.8-1.3, so joints stay where the
  animations put them.
- **Body (rows 1-4):** Y and Z only, 0.85-1.25.
- **Hands and feet:** not scaled.

Borrowed seam vertices are scaled with the row that owns them, so no gaps open.

Tested on KITTEST (head 1.25, arms 1.25, body 1.2):
- the render before/after has no seams;
- `t3live fight` drew it with 0 of 5386 words differing, and the HUD text stays clean.

Same size in bytes and triangles as without a shape.

### Height / leg length (2026-10-18, tested: not possible this way)

Test: Nina's leg vertices were stretched 1.2x along the bone, and the knee and ankle offsets
(rows 6, 7, 9, 10, words 3..5) were scaled the same. The game drew it (0 words differ) and the
legs were longer, but the feet stood about 30 px below the floor. The pelvis (row 1) has offset
0 and its height comes from the animation, so longer legs push the feet through the floor. Taller
or shorter fighters would need changed animations: left out of the Builder.

### Texture page full: areas at half size (2026-10-18, tested)

When no layout fits the one 256 x 256 page, `kitbash.halve` rebuilds the biggest other
fighter's areas at half size (every second texel each way). They go in a band of their own,
with the same CLUTs, and their polygons' UVs are scaled to match. Then packing runs again; the
base's areas are halved last. The Builder notes "some parts' textures are at half size" in the
preview and after Build (`half_textures`).

Measured over every base x fitting source for the body part (1028 mixes):
- before: 354 failed (229 page, 92 GPU packets, 33 bytes);
- after: 141 failed (0 page, 108 GPU packets, 33 bytes). Some former page failures now stop at
  the polygon budget instead.

Tested:
- Law's body on Nina (failed before) renders right offline;
- `t3live fight` drew it with 0 of 5189 words differing and a clean HUD;
- KITTEST's own mix is unchanged (halving only runs when nothing fits).

### GPU packet limit for mixes (2026-10-18, tested in game)

The writer's 31000-byte packet limit is a margin for imports. Stock models need up to 32580
(`knowledge/t3-model-style.md`), and a model needing 33596 crashed. Mixes are Namco's own
polygons, so kitbash now writes up to `MI.STOCK_PACKET_BYTES` = 32580; direct imports keep 31000,
so the regression is unchanged.
- Stock models rebuilt by kitbash: highest 31812 (model 21).
- In game: Nina with head and arms of model 3 (32464 bytes, 1145 triangles) fought 1500 frames
  (falls, throws) with 0 of 5781 words differing and no crash.
- Body mixes after this: 52 of 1028 fail. 17 are over the packet limit (32600-33496). 35 do not
  fit the base model's slot in bytes: small slots such as 18412 bytes, overshot by 400-1400.
  Overall 354 → 52 since the start of 2026-10-18.

### Slot size: coarser normals (2026-10-18, tested offline)

A mix a little too big for the base model's slot is written again with its normals snapped in
coarser steps (6, then 4, instead of 8). Fewer normals are stored and the light barely changes.
- Head mixes: 54 of 1028 failed before this. Model 7 with head 13 went from 24568 to 24480 bytes
  (slot 24488) and now builds.
- Bigger overshoots still fail with a clear message, e.g. model 30 (slot 18412) at 19128 bytes.
- Imports keep steps of 8, so the regression is unchanged.
- Other parts after these changes (1028 mixes each): head 54 fail, arm 28 fail. All of them are
  packet-limit or slot-size cases, none is texture page.

### Randomize with two fighters (2026-10-18)

200 random mixes with parts from two other fighters (60 % chance per part) gave 184 of 193 that
build: 8 slot-size and 1 packet failures. Randomize now draws one or two other fighters. When a
random mix does not build, it draws again, at most 3 times. Browser: 3 Randomize clicks gave 3
previews, one of them from two fighters.

### Over the packet limit: triangle pairs as quads (2026-10-19, tested in game)

When a mix is over the packet limit, `direct_import._pair_quads` joins neighbouring triangles
that have the same texels on their shared edge, the same CLUT and the same shading into quads.
It only joins nearly flat pairs (at most 12 degrees bent). The GPU draws (a, b, c) + (b, d, c),
the same two triangles, for 52 bytes of packets instead of 80. Existing quads stay as they are.
It only runs when the limit is passed, so mixes that fit are byte-identical (`t3cb kitregress`:
all 6 the same).
- Law (model 2) with body 36: 33376 → fits (104 pairs); clean render, no holes. Bodies 5 on
  model 2, 36 on model 9 and 41 on model 21 build too (75-160 pairs).
- In game: KITTEST's mix forced through the pairing (limit lowered to 28500: 96 pairs, 27088
  packet bytes) fought 900 frames, falls included, with 0 of 5188 words differing.
- Body mixes with all of this (2026-10-19): 34 of 1028 fail. All are slot size (small slots
  such as 18412 bytes), none is packets or texture page.
