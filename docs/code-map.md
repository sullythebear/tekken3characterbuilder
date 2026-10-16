# Code map (`character-builder/`)

Find things here before reading code; then search (`grep -n`) instead of reading whole files.
"venv" = runs with Expanded's Python (`<game>/.setup/venv`), numpy + PIL only.

## Server and patches

- `app/server.py` (stdlib) – local web server for the UI.
  - Project: `project_root`, `project_status`, `toolchain`, `game_exe`, `exe_has_support`, `venv_python`.
  - `Build` (cmake build), `Game` (play), `TestRun` (Test button: build if needed, play, write
    `logs/test-report.md`).
  - Characters: `character_list`, `get_character`, `save_character`, `delete_character`,
    `export_character`, `import_character`, validators `validate_character/costumes/recipe`.
  - Sync to the game: `sync_customs` (customs.txt, portraits via `run_custom_tool`),
    `write_palettes` (`<Prefix>-pal.bin`), `write_own_model` (copies `characters/<id>/model.bin`
    to `<Prefix>-model.bin`), `adopt_unlinked`/`unlinked_fighters`.
  - 3D preview: `donor_models`, `model_json` (runs `model_export.py`, cache `cache/model-<n>-v7.json`).
  - Own 3D models: `check_model` (upload + rig check), `import_model`, `remove_model`, `refit_model` (style change),
    `own_model_json` (preview), `run_import_tool` (direct_import.py).
  - HTTP routes in `Handler` (`/api/...`; `/api/model/check|import|remove`, `/api/ownmodel/<id>`).
- `app/creator_patch.py` – applies/removes exact-text source patches. `PROFILES` (`recompiled`,
  `expanded`, current revision string `T3CB-PATCH-14`), `status`, `install`, `uninstall`
  (restores from `*.t3cb-backup`), `original_text`, `_plan` (checks every edit matches once).
- `app/expanded_patch_data.py` – the Expanded edits: `ROSTER` (src/tekken3_ttt1_roster.c),
  `MOD` (tekken3_ttt1_mod.c), `COMBAT`, `NATIVE`; each entry `(old, new, count)`. Sections are
  marked in the C text by `T3CB-PATCH-n` comments: 2 descriptors, 3 move diagnostics, 4/7 move
  key, 5/6 Mokujin, 8 strip tiles (`custom_strips`), 9 palettes (`custom_palette_tick`),
  10 own models (`custom_model`, `tekken3_custom_model_install`), 11 own textures
  (`custom_model_check` uploads texture + CLUT), 12 several CLUT runs per texture, 13 renderer probe options, 14 texels re-uploaded every frame.
- `app/name_call.py` (stdlib) – the announcer's name call: `speak` (Windows System.Speech),
  `announcer` (lower, echo), `own`, `read_wav`, `pack` (`<Key>-TTT1-sfx.jus`, sound 1025),
  `fighter_sound` (cached automatic call), `write`. Server: `decode_wav`, `name_call_preview`
  (`/api/namecall/preview`), `write_name_call` (in `sync_customs`), `custom_entry` (customs.txt line).
- Model Importer before/after: `source_preview` (`/api/model/source`, cached `cache/source-preview-<id>.png`), UI "Show before" in model3d.js.
- Restore points: `keep_restore_point` (in `save_character`, `characters/<id>/history/`), `restore_points` (`/api/history`), `restore_character` (`/api/history/restore`); UI `loadHistory`, `restorePoint` in app.js.
- `app/stage_look.py` (venv) – stage colour looks: `variant` (CLUT rows of record 36 + arena, recoloured), `preview` (texture sheet); server `write_stage_look` (in sync), `stage_preview` (`/api/stage/preview`), `STAGE_ARENA`.
- `app/command_list.py` (stdlib) – decodes a fighter's COMMAND LIST (ARC member 4, word tokens, Tekken notation); `model_export.py commandlist --model N`; server `command_list` (`/api/moves`); UI `movelab.js`.
- `app/custom_page.py` (stdlib) – reads customs.txt, labels, `.jui` portraits (`read_entries`,
  `read_label`, `read_portrait`, `file_prefix`).
- `app/expanded_custom.py` (venv) – writes portrait pack, name plate, customs.txt (`install`,
  `remove`, `write_list`).

## Models (venv)

- `app/model_export.py` – disc models for the 3D preview and model files.
  - `records(root, ids)` reads BNS records from the disc image; `donors(root)` model map.
  - Poses: `stance_pose`, `world`, `stand_pose`, `tweaked`, `facing`, `align`.
  - `bind(m)` slot lists per row (own copy of Expanded's, second layers fixed).
  - `export_model(root, model)` mesh JSON (format 7) for the preview; `_mesh` (triangles per
    pose); `export_own(root, file)` the same for a T3CM file (CLI `ownjson --file --out`).
  - Own models: `relocations`, `own_vertex_span`, `scaled_rows`, `own_model_file` (T3CM v1/v2
    with T3TX texture). CLI: `donors`, `model`, `ownmodel`.
- `app/model_import.py` – FBX -> Tekken 3 model over a donor. CLI:
  `model_import.py <fbx> --model <donor model> --root <game> --out <file>`.
  - Bones -> rows: `_part`, `bone_rows`, `joint`, `finger_points`.
  - `donor_frames`, `build` (axes, scale, frames F/J, weights -> rows, see-through and eyeball
    filtering, `lowpoly.build` + `lowpoly.add_pieces`, texture setup, size budget loop).
  - `_write` – the 3DMK writer: draw rows, spill to second layers, cache allocation, vertex /
    normal / gouraud polygon / texture blocks; GPU packet limit. `donor_cluts`, `donor_palette_size` (CLUT room).
- `app/lowpoly.py` – Tekken 3 style low-poly body: `build` (tubes of rings, head shell, hands
  with mitten + thumb, shared joint rings, smooth normals), `add_pieces` (loose clothing pieces
  outside the tubes, simplified), helpers `ray_hits`, `cast`, `frame`, `Body`.
- `app/direct_import.py` – rigged PS1-style model (.fbx/.glb) as it is over a donor: `load` (+ `_upright`: Z-up rigs turned from the skeleton),
  `rig_from_skeleton` (collar fallback), `inspect` (rig check, CLI `--check`), `build` (bind pose,
  LBS posing, rows/50-50 seams, normals, winding, texture, size fallback). CLI `--model --out`.
- `app/bind_pose.py` – the donor's bind pose from its own 50/50 seams: `seam_pairs`,
  `cross_edges`, `solve(m, W)`, `residuals`, `with_offsets` (a model's own bone lengths).
- `app/protrusions.py` – parts sticking out of head/chest/hips (a ponytail modelled straight
  back, horns, tails): `find` (far vertices of the part, grown back to the root along the piece;
  parts already hanging down are skipped), `apply(src, choices)` (fold = turned about the attach
  point to hang N degrees from down, keeping its heading, eased over the first fifth; angle None
  = steepest that clears the body; keep; remove), `preview` (side + back PNG, parts tinted).
  Used by `direct_import.inspect` (`parts`), `build(parts=)`, CLI `--parts JSON`, `--preview PNG`;
  server `/api/model/preview`, choices stored in `own_model.parts` (refit uses them); UI in
  `ui/model3d.js` (`showParts`, `partRow`, debounced preview).
- `app/reduce.py` – high-poly rigged model -> PS1 size: `reduce(src, target)` (`_shell` with
  limb-gap removal, `_charts`, `_pack` FFT bitmap packing, `_raster`, bake).
- `app/glb.py` – glTF binary reader (meshes, UVs, textures, skin bones/weights).
- `app/kitbash.py` – `build(root, base, parts)`: a fighter from parts of the stock models (Namco geometry and texels); CLI.
- `app/template.py` – `build`: the donor's own model as topology template moved onto the import (default, `model_import.TEMPLATE`).
- `app/texture_bake.py` – texture: `Source` (FBX textures, `transparent`, `colours`),
  `pack_faces` (skyline packing), `raster`, `bake` (rays from outside inwards), 
  `quantise_groups` (16-colour palette per chart group; face own palette), `face8` + `band8_into`
  (8-bit face), `paint` (median), `band4`, `ps1_colour`.
- `app/remesh.py` – `Caster` (first ray hit via grid), `Sampler` (nearest surface point),
  `surface_samples`, `snap`; older voxel `remesh` (not used by the importer now).
- `app/decimate.py` – quadric edge collapse `decimate` (`importance`, `uniform` edge-length term).
- `app/fbx.py` – binary FBX reader: `read`, `scene`, `summary`, `character` (mesh, bones,
  weights, UVs, materials, embedded textures). CLI prints a summary.

## UI (`app/ui/`, no build step)

- `index.html`, `style.css`. Editor tabs = Studio modules (`PAGES` in app.js): fighter, colours
  (Builder), model (Model Importer), portrait, voice, stage.
- `app.js` – pages, character form, donors (`renderDonors`), portrait (`drawPortrait`,
  `quantizePS1`), roster, steps/gauges, project panel.
- `model3d.js` – the 3D model page (upload, check/lock, import, remove).
- `builder.js` – Character Builder body parts (`T3Builder`: lists filtered by build, randomize, build via `/api/kit/build`).
- `arena.js` – stage, music and name call (`T3Arena`: lists, preview, record via MediaRecorder,
  `toWav` decodes any sound to 44100 Hz mono WAV in the browser).
- `costumes.js` – WebGL preview (shows the own model on its costume) (`createViewer`), `parseModel`, clothing pieces (`texelUse`,
  `groupParts`, `setPieceColour`), palettes (`computeCluts`, `paletteFor`), variants.

## Other

- `README.txt`, `Start Dizzy Character Creator.cmd` (the app is named Dizzy Character Creator since 0.3.8; the folder stays `character-builder/`).
- Repo `tools/`: helper scripts (see `docs/knowledge/testing.md`).
