# Stages

Each entry says how it is known: **tested** (seen in game), **code** (read in source), or **inferred**.

- **tested** Stage (arena) values, descriptor byte 10 per fighter: see `custom-page.md` (patch 17).
  Arena 7 is no fighter's; 15 is Crow's (Tekken Force).
- **tested** (2026-10-16) A stage's textures are disc record 36 + arena (16 records, 36..51):
  TIM images and CLUTs. During a fight the CLUTs sit in VRAM where the TIMs say (records 36 and 49
  on arenas 0 and 13: 307 of 311 / 375 of 379 rows found). Several TIMs can target one CLUT row:
  the last one is what VRAM holds. Stage data in VRAM: x 512..767 (textures, all rows) and CLUT
  rows around y 448..511 (x 0..767). No stage texture is shared between stages.
- **tested** The game keeps no copy of the stage CLUTs in RAM after loading (searched).
- **tested** Stage colour variants (T3CB-PATCH-19, `stage_look.py`): `<Key>-T3-stage.bin` holds
  the arena and per CLUT row the original and the new colours; the patch writes a row each frame
  of a fight on that arena while the fighter takes part, only if VRAM still holds the original
  (or it was already written), so other data is never overwritten. Live on Gon's beach: night and
  sunset clean; the hit spark changes colour too (its CLUT comes with the stage data). The HUD's
  name plates fade in dark at the round start with or without a variant.
- **not possible yet**: new stage geometry or objects. The stage model records (forest:
  model record 58 per Expanded's forest-hd report) and the floor/wall collision are not known.
