# Portrait and name plate

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Portrait and name plate (code: Expanded `tools/ttt1/ui.py`, `ui_art.py`, `glyphs.py`)

- `.jui` pack: header `JUI1`, version 1, 5 TIMs (8bpp + CLUT):
  portrait 126 × 252 (shown at 168 × 252, i.e. 2:3), select tiles 32 × 68 and 32 × 58,
  loading tiles 32 × 34 and 32 × 29. The portrait uses 4 bands of 64 rows, 63 colors each
  (index 0 transparent). The builder's packs pass the runtime's checks (**code**, validated offline).
- Name plate: 4bpp, max 76 px wide, letters cut from the fighter-name bitmaps on the disc
  (`disc/SLUS_004.02`). There is no F or Q; Z, V, `-`, `.` and 2 are drawn.

## Portrait Lab presets (2026-10-16, tested offline and in the browser pane)

- `model_export.own_portrait(..., look=)`: `PORTRAIT_ANGLES` (yaw), `PORTRAIT_FRAMES` (share of
  the figure's height shown), `PORTRAIT_LIGHTS` (direction, ambient, direct), `PORTRAIT_BACKDROPS`
  (base colour, glow). CLI `ownportrait --look '{"angle":"front",...}'`; server validates names
  (`PORTRAIT_LOOK`); UI selects in the Portrait Lab tab, shown when the fighter has an own model.
- Verified: Medea in three looks (default; front/close/dramatic/red; profile/chest/flat/cool),
  KITTEST front/red from the UI. The close-up can touch the top of tall hair.

## Home stage background (2026-10-19, browser-tested)

- Background "My home stage": the server renders the fighter's home stage from the front in its
  stage colours (`server.stage_view_file`, the Stage Lab's cached picture) and passes its path
  as `backdrop_image`; `model_export.own_portrait` scales it to cover the frame, crops the
  middle and darkens it to 75 % so the fighter stands out. KITTEST on Gon's beach looked right
  after the select-screen conversion.
