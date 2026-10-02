# Portrait and name plate

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Portrait and name plate (code: Expanded `tools/ttt1/ui.py`, `ui_art.py`, `glyphs.py`)

- `.jui` pack: header `JUI1`, version 1, 5 TIMs (8bpp + CLUT):
  portrait 126 × 252 (shown at 168 × 252, i.e. 2:3), select tiles 32 × 68 and 32 × 58,
  loading tiles 32 × 34 and 32 × 29. The portrait uses 4 bands of 64 rows, 63 colors each
  (index 0 transparent). The builder's packs pass the runtime's checks (**code**, validated offline).
- Name plate: 4bpp, max 76 px wide, letters cut from the fighter-name bitmaps on the disc
  (`disc/SLUS_004.02`). There is no F or Q; Z, V, `-`, `.` and 2 are drawn.
