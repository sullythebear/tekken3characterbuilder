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
- **tested** (2026-10-19) The stage's scenery model is disc record **56 + arena** (arenas 0..14;
  record 71 is a fighter model again, so arena 15 has none there). Format (first hint: Expanded's
  `tools/forest_hd_pack.py` for record 58):
  - header: u32 65, u32 (varies), u32 36 = piece count;
  - 36 pieces of 7 u32 at 12 + 28 * i: vertex offset, vertex count, ?, primitive count,
    primitive offset, the count again, 0 (offsets from +12). The pieces form a 6 x 6 grid of
    480-unit cells over x/z -1200..1200;
  - vertices: 4 i16 (x, y, z, 0), y up is negative (scenery up to about -860);
  - primitives: GPU packets without the tag word. 0x20/0x28 flat triangle/quad (rgb, code,
    3/4 vertex indices; 8 bytes), 0x24/0x2C textured (rgb, code, uv+clut, uv+tpage, uv, uv,
    indices; 20 bytes). Code bit 1 = semi-transparent. All 15 records parse with only these.
  - Textures: tpage/CLUT point into VRAM as the stage's TIMs (record 36 + arena) load them.
    Primitives whose UVs span one or two texels are plain colours (the sky on arena 0).
- **tested** `stage_look.arena_view` renders it (software, perspective-correct, PS1 colour 0
  see-through, the look's CLUTs): all 15 arenas look like the game's stages (street, forest,
  fair, temple, harbour, beach, ...). The Stage Lab shows it with a View choice (front, right,
  back, left, textures); browser-tested on Gon's beach with Sunset.
- **tested** The floor is not in the scenery model. Its tiles are the stage's 4-bit TIMs that
  no scenery primitive uses: 64 x 64 texels each, usually four stacked (sand on arena 13,
  grass on arena 2, one tile on arena 0). **inferred**: how the game lays them out;
  `stage_look.floor_triangles` repeats them (a tile per 240 units), which looks right on all
  15 arenas but is not the game's routine.
- **not known**: the floor routine itself and the floor/wall collision.
  New stage geometry is therefore not offered; editing the scenery within its byte size is the
  possible next step.
