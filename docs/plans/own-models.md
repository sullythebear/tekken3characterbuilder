# Plan: own 3D models (FBX import)

Goal (user): import a 3D character that converts so well it cannot be told apart from Tekken 3's
own fighters. Rules: `docs/knowledge/t3-model-style.md`. Format: `docs/knowledge/own-models.md`.

## Status (2026-10-02)

- Pipeline works end to end, from the command line only (`model_import.py`).
- Medea (`character-builder/test.fbx` in the test folder, Mixamo) over Nina (donor 5, model 10)
  as custom fighter MEDEA: v13 tested in game (good, recognisable); **v15 deployed, not yet
  tested in game** (hands with thumb, loose pieces: collar, sleeve flap; 1108 triangles,
  26056 of 26112 bytes).
- KUMA T test folder model.bin: Medea over Kuma (old v-series test, bear animations). The
  big-head test file was saved as `%TEMP%/kuma-bighead-model.bin`.

## Next

1. Done: v15 crashed at fight start (GPU packets 33596 > stock max 32580); v16 (packet limit
   31000, 976 triangles, 23060 bytes, 6 loose pieces) tested in game 2026-10-02: no crash,
   2 m 07 s, model and texture installed, 0 words differ.
2. Done (offline): collar whole on one row, blunt toes, 8-bit face (patch 12), painted texture.
   v17 tested in game 2026-10-02: works.
3. v18 (offline, deployed, test pending): limbs moved part way to the donor's thickness
   (`radius_t3`, only forearm row 17 changed: x1.51), saturated colours (`texture_bake.vivid`),
   crotch lower (gap closed): tested in game 2026-10-02, works. v19 tested in game 2026-10-02 (works, log clean):
   baked light and dirt flattened per chart (`texture_bake.flatten`, strength 0.5); the
   'not P1's' log line now once per address (patch 12 text, rebuilt). Belt piece still a flat plate.
4. v20 tested in game 2026-10-02 (works): painted style (`texture_bake.stylise`: per chart at
   most 6 flat colour areas, majority-filtered edges, soft original light +-20 %); mirrored half
   face (face chart u folded over the nose line in `lowpoly.build`); loose pieces only when more
   than 2.8 % of the height outside the tubes (belt plate gone; collar and sleeve flap stay).
   920 triangles, 21404 bytes, 15.0 texels per unit. She floated: v21 tested in game 2026-10-02 (stands on the ground),
   scaled by hip height above the soles.
5. Texture density dropped to 14 texels/unit with 67 charts: merge the loose pieces' box
   charts, or give pieces less weight.
6. Size: v15 uses 99.8 % of Nina's slot; budget loop must keep a margin.
7. Builder UI: "Import 3D model (.fbx)" on the character page (pick donor costume, run
   `model_import.py`, preview in the 3D view, save `characters/<id>/model.bin`).
8. Automatic rigging for FBX files without a skeleton (estimate joints, adjustable in the 3D view).
9. Done: log spam fixed.
