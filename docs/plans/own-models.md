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

1. Test v15 in game (MEDEA, costume 1).
2. Collar breaks in some poses (piece vertices on different rows): hang a whole piece on one
   row, or on the row of most of its area.
3. Toes are pointy: feet cap blunter (like the hands).
4. Face: 8-bit (256 colours, CLUT 0) when the donor has CLUT row 0 and row 1 room; or a
   mirrored half face like Namco's.
5. Texture density dropped to 14 texels/unit with 67 charts: merge the loose pieces' box
   charts, or give pieces less weight.
6. Size: v15 uses 99.8 % of Nina's slot; budget loop must keep a margin.
7. Builder UI: "Import 3D model (.fbx)" on the character page (pick donor costume, run
   `model_import.py`, preview in the 3D view, save `characters/<id>/model.bin`).
8. Automatic rigging for FBX files without a skeleton (estimate joints, adjustable in the 3D view).
9. Log spam: "model 10 at ... is not P1's" repeats ~45 times when P2 uses the donor model; log once.
