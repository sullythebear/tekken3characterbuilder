# Tekken 3 Expanded architecture

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Tekken 3 Expanded architecture (code: `src/tekken3_ttt1_roster.c`, Expanded on Recompiled 0.1.2)

- Guests come from `<asset root>/guests.txt`: `<key> <moveset> <arena owner>` per line,
  with `<Key>-T3-ui.jui`, `<Key>-T3-name.4bpp`, `<Key>-T3-label.txt` and TTT1 data beside it.
  Asset root = `build-release/mods/ttt1`; the build copies `workspace/ttt1-import/roster` into it.
- Guest `k` has ID `23 + k`; all TTT1 guests map their selections to model 52 (Jin's envelope)
  and are drawn by the TTT1 renderer.
- The cabinet selector has a Tag page (L2/R2); the VS grid (state 10) has its own pages.
- Tag tiles live in VRAM at (384,16), 8 per row, 16 × 58 halfwords each, palettes from row 480;
  two extra tiles at (384,144), palettes 498–499.
- Descriptors: 80 bytes per guest from `area + 0x30120`; the name table (64 entries) starts at `area + 0x30800`.
- CPU table and Force bosses for IDs ≥ 22 default to Jin's rows (`src/tekken3_ttt1_combat.c`).
- The guest/native split for the import pipeline is `guest_player()` in `src/tekken3_ttt1_mod.c`.
