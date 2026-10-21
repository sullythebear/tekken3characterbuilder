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
- Saved looks: `list_looks` / `save_look` / `delete_look` (character-builder/looks.json, max 40, git-ignored),
  routes `/api/looks`, `/save`, `/delete`; UI `builder.js` loadLooks / useLook / saveLook.
- Body shape: `kitbash.SHAPES` / `clean_shape` / `shape_scale` (applied in `build.place`, local axes: head all,
  arms/legs/body Y and Z; hands and feet kept), CLI `--shape JSON`; server `KIT_SHAPES`, `clean_kit_shape`,
  `run_kitbash(shape=)`, `own_model.shape`; UI `.kit-shape` sliders in `builder.js shape()`.
- External texture: `direct_import.set_external_texture` / `_external_texture` (CLI `--texture`); server
  `texture-upload.*` / `texture-source.*` / `texture-prev.*` (`model_texture`, `move_texture`, `upload_texture`,
  `/api/model/texture`; `run_import_tool` adds `--texture` by itself), packages carry `texture-source.*`.
  `texture_bake.quantise_groups`: a model without any texture no longer crashes (one plain palette).
- Patch 20 (changed damage): `expanded_patch_data` custom_moves / moves_put / custom_moves_tick; builder
  `command_list.moves_file` + `server.write_moves` (field `move_damage`), UI editable `#basic-list` inputs,
  `T3MoveLab.body()`.
- Move Lab damage: `command_list.basic_damage` / `moveset_key` / `with_damage` (BNS record 280 + key, shared
  lists in SLUS_004.02); `model_export commandlist --style` prints {moves, basic, own, records, key}; server
  cache `commandlist6-<model>-<style>-<crc of its OWN_MOVES>.json`; UI `movelab.js showBasic` (grids `#basic-list`, `#own-list`).
- Builder pieces: `kitbash.list_pieces` / `build(pieces=)`, server `clean_kit_pieces` `kit_pieces` (`/api/kit/pieces`), UI `builder.js loadPieces`. Accessories: `kitbash._accessories`, `_row_models`.
- Own moves: `command_list.OWN_MOVES` {style: {COMMAND LIST command: record}} measured in game (scratch
  method in `knowledge/moves.md`), `own_records` reads their damage from the disc; patch 20 changes them
  like basic ones (the keys go into `records`; server accepts upper-case held directions).
- Moves on buttons (patch 21): `command_list.basic_slots` {input: [alias slot]}, `moves_file(..., buttons,
  slots)` writes T3MV version 2 only when something moves; commandlist JSON `slots`, `movable` (no throws,
  by "[Throw]" in the name); field `move_buttons` {input: move key} (`BUTTONS_MAX` 16); UI `movelab.js showButtons`
  (`#buttons-list`). Cache `commandlist6-...`.
- Intro and win pose: `command_list.poses`, `pose_swaps`, `INTRO_SLOTS` / `WIN_SLOTS`; commandlist JSON `poses`,
  `pose_slots`; `moves_file(..., extra)`; field `poses`; UI `movelab.js showPoses` (`#poses-field`). Cache `commandlist8-...`.
- String endings: `command_list.string_slots` (in the commandlist JSON `slots` under "<string>#<hit>"), UI
  `movelab.js showButtons` (`later`); cache `commandlist7-...`.
- COMMAND LIST with moved moves (patch 22): `command_list.encode`, `commands_file`; `model_export.py rawlists
  --models` (cache `rawlists1-<models>.json`), server `style_lists`, `write_commands` (`<prefix>-commands.bin`).
- CPU personality (patch 22): field `cpu` (calm / steady / fierce), server `CPU_BLOCKS`, `write_cpu`
  (`<prefix>-cpu.txt`, `_write_number`), UI `arena.js` `#cpu`; patch `custom_cpu`, `custom_cpu_tick`.
- Rival (patch 22): field `rival` (0-20, validated with stage/music), server `write_rival` (`<prefix>-rival.txt`),
  UI `arena.js` `#rival`; patch text in `expanded_patch_data.ROSTER` (`custom_rival`, in `opponents_tick`).
- Share codes: server `share_code` / `import_share_code` (`SHARE_PREFIX` T3C1-, zlib + base64url of character.json
  fields, imported as a package holding only character.json), `/api/share/code`, `/api/share/import`; UI
  `app.js showShareCode`, `enterShareCode`, `#share-dialog`. "Surprise me": `app.js surprise`, `surpriseName`.
- Fairness: `fairness.py` (`yardstick`, `check`), `model_export.py cast` (damage per style, cache
  `cast1.json`), server `cast_damage`, `fairness_check`, `/api/fairness`, `fairness` stored by `save_character`;
  UI `movelab.js fair` (`#fair-field`).
- Voice Lab: `name_call.shape(samples, pitch, echo)` (`ECHOES`, `announcer` = shape -18 hall),
  `voices()` / `speak(name, voice)` (System.Speech, `VOICE_RE`), field `name_call_voice` (auto cache key
  name|voice), route `/api/namecall/voices`; UI `arena.js` `#name-voice`, `#name-pitch`, `#name-echo`.
- Licence register: `clean_credits` (field `credits` in character.json, `CREDIT_ASSETS`, `LICENCES`),
  `licence_warnings` (`/api/export/check`, UI `exportFighter`), UI `#credits` + `creditsBody()`.
- Check library: `check_library` (`/api/check`), UI `showCheck` + `#check-dialog` (fix = `/api/sync`).
- Asset library: `own_assets`, `asset_library` (`/api/library`), UI `showLibrary` + `#library-dialog`.
- Duplicate: `duplicate_character` (`/api/duplicate`), UI `duplicateFighter`.
- Backup: `backup_all` (GET `/api/backup`, every package in a .t3backup zip), `backup_packages` (the
  `/api/import` route imports each package of a backup).
- Saved portraits (server): `portrait_variants`, `keep_portrait`, `use_portrait` (keeps the current one first, then
  copies the variant back and syncs), `drop_portrait`; files in `characters/<id>/portraits/<stamp>/`, at most
  `PORTRAIT_VARIANTS` = 12; routes `/api/portraits`, `/keep`, `/use`, `/drop`; UI `app.js loadPortraits`.
  Packages carry them as `portraits/<stamp>/*.png` (import checks names, PNG signature, count).
  The portrait URL stamp uses the newest of character.json and the portrait files (browser cache).
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
  Used by `direct_import.inspect` (`parts`), `build(parts=, settings=)`, CLI `--parts JSON`, `--settings JSON`
  (`head` 4/2/1 face detail, `detail` 100/80/60 % triangle budget; server `clean_import_settings`, stored in
  `own_model.settings`, UI `#model-settings` shown for reduced models), `--preview PNG`;
  `checks(src, info, weighted)`: the pre-import list in `inspect()["checks"]` ({area, level ok/info/warn/bad, text}:
  triangles, flat triangles, pose spread, materials/textures, UVs outside 0-1, bones found, weights), shown grouped in `model3d.js showCheck`;
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
- Repo `tools/`: helper scripts (see `docs/knowledge/testing.md`). `tools/t3moves.py`: basic moves and damage from a RAM dump (`knowledge/moves.md`).
