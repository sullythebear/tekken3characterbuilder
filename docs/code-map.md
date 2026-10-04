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
  `expanded`, current revision string `T3CB-PATCH-13`), `status`, `install`, `uninstall`
  (restores from `*.t3cb-backup`), `original_text`, `_plan` (checks every edit matches once).
- `app/expanded_patch_data.py` – the Expanded edits: `ROSTER` (src/tekken3_ttt1_roster.c),
  `MOD` (tekken3_ttt1_mod.c), `COMBAT`, `NATIVE`; each entry `(old, new, count)`. Sections are
  marked in the C text by `T3CB-PATCH-n` comments: 2 descriptors, 3 move diagnostics, 4/7 move
  key, 5/6 Mokujin, 8 strip tiles (`custom_strips`), 9 palettes (`custom_palette_tick`),
  10 own models (`custom_model`, `tekken3_custom_model_install`), 11 own textures
  (`custom_model_check` uploads texture + CLUT), 12 several CLUT runs per texture.
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
  `cross_edges`, `solve(m, W)`, `residuals`.
- `app/glb.py` – glTF binary reader (meshes, UVs, textures, skin bones/weights).
- `app/kitbash.py` – `build(root, base, parts)`: a fighter from parts of the stock models (Namco geometry and texels); CLI.
- `app/template.py` – `build`: the donor's own model as topology template moved onto the import (default, `model_import.TEMPLATE`).
- `app/texture_bake.py` – texture: `Source` (FBX textures, `transparent`, `colours`),
  `pack_faces` (skyline packing), `raster`, `bake` (rays from outside inwards), 
  `quantise_groups` (16-colour palette per chart group; face own palette), `face8` + `band8_into`
  (8-bit face), `paint` (median), `band4`, `ps1_colour`.
- `app/remesh.py` – `Caster` (first ray hit via grid), `Sampler` (nearest surface point),
  `surface_samples`, `snap`; older voxel `remesh` (not used by the importer now).
- `app/decimate.py` – quadric edge collapse `decimate` (used for loose pieces).
- `app/fbx.py` – binary FBX reader: `read`, `scene`, `summary`, `character` (mesh, bones,
  weights, UVs, materials, embedded textures). CLI prints a summary.

## UI (`app/ui/`, no build step)

- `index.html`, `style.css`.
- `app.js` – pages, character form, donors (`renderDonors`), portrait (`drawPortrait`,
  `quantizePS1`), roster, steps/gauges, project panel.
- `model3d.js` – the 3D model page (upload, check/lock, import, remove).
- `costumes.js` – WebGL preview (shows the own model on its costume) (`createViewer`), `parseModel`, clothing pieces (`texelUse`,
  `groupParts`, `setPieceColour`), palettes (`computeCluts`, `paletteFor`), variants.

## Other

- `README.txt`, `Start Character Builder.cmd`.
- Repo `tools/`: helper scripts (see `docs/knowledge/testing.md`).
