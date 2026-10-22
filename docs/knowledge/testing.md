# Testing

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Testing

- **Test button (builder 0.3.5):** one click checks that the patch is current (if not it stops:
  Install/Update first), builds when the exe is missing the patch or is older than the patched
  source, starts the game like Play, and when the game closes writes
  `character-builder/logs/test-report.md`: date and time, builder version, patch revision and
  whether it is current, the build result (not needed / succeeded / failed), play time and exit
  code, both copies of `customs.txt`, every game-log line starting with `Custom fighters`,
  `Custom probe` or `TTT1 characters`, and up to 40 other lines matching
  error/fault/failed/exception/assert/crash. The report shows in the UI (Test report, with Copy)
  and survives a restart of the builder. Code: `TestRun` in `server.py`, `/api/test`.
  Verified 2026-10-01: report rendered offline from a real game log; button and panel checked in
  a browser.
- **Test button tested 2026-10-01 (full click, by the user, Expanded 1.1.3 test folder):** patch
  T3CB-PATCH-4 current, build not needed, game ran 56 s (Arcade, Dizzy as P1), exit code 0,
  report written 2 s after the game log closed; 17 log lines, 0 errors, and the values match the
  0.3.3 test (`a1=3`, header `0301`, `actor+0x16 3`, model 7, no `guest in the fight`). The Copy
  button copied the report straight to the clipboard with a real click in the builder window (in
  the automated browser only the select-and-Ctrl+C fallback could be checked). Not yet seen: a
  test run that has to build first (it uses the same `build.start()` as the Build button).
- psxrecomp has a TCP debug server (`beetle_debug_server.c`, default port 4380) with
  `set_input`, `clear_input`, `pad_status`, `screenshot_file` and memory reads. Builds from the
  Easy Setup turn debug tools off (`PSX_DEBUG_TOOLS=OFF`, `PSX_DEBUG_SERVER_LITE=OFF`);
  a test build would enable them. Not tried yet.
- Expanded's `tools/*.lua` are emulator capture scripts (MAME/DuckStation) used to research the game.

## Helper scripts (`tools/t3cb.py`, stdlib, short output)

Use these instead of doing the steps by hand. Default game folder: the Expanded test copy
`D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3` (`--game` for another).

- `python tools/t3cb.py deploy` – copies `character-builder/` from the repo to the test folder;
  keeps its `characters/`, `logs/`, `cache/`. Prints how many files changed.
- `python tools/t3cb.py patch` – installs the patch, uninstalls and checks every patched file
  equals its original byte for byte, installs again. Prints e.g.
  `patch T3CB-PATCH-11: installed=True, uninstall restores 4/4 files byte for byte`.
- `python tools/t3cb.py build [--debug]` – `cmake --build build-release --target psx-runtime` with the
  toolchain on PATH (`--debug`: build-opt-dbg, which t3live runs); prints `build OK (...)` or only
  the error lines.
- `python tools/t3cb.py report` – summary of `logs/test-report.md`: date, patch, build, run time,
  the custom-fighter lines that matter (model installed, texture uploaded, last model check),
  error count.
- `python tools/t3cb.py import <fbx> --character <id> --model <donor model>` – runs
  `model_import.py` with Expanded's venv and puts the result on the character.
- `python tools/t3cb.py setmodel <file> --character <id>` – puts a T3CM model file on a character
  (`characters/<id>/model.bin` and `<Prefix>-model.bin` in both mod folders).

Tested 2026-10-02: deploy (0 changes), patch (4/4 byte for byte), build OK, report.
Offline model renders (not in tools/ yet): scratch scripts `rast7.py` (own model, gouraud,
textured), `stock.py` (a stock model with textures and wireframe).

- `tools/render/compare.py "<stock model n or T3CM file>,..." out.png [size]` (Expanded's venv):
  renders models side by side with the same renderer (stored gouraud normals, CLUT textures,
  transparency), standing and Kazuya's fight stance, front and back. Use it to judge an import
  next to its donor before asking the user to test.

## Live checks without a player (`tools/t3live.py`, 2026-10-03, works)

- Needs Expanded's debug build `build-opt-dbg` (configured from build-release's CMake cache
  with `-DPSX_DEBUG_TOOLS=ON`, built with `cmake --build build-opt-dbg --target psx-runtime`;
  rebuild it after patch changes too). Its debug server (`--debug-port`) takes JSON commands:
  `ping`, `frame`, `read_ram`, `set_input` (pad bits, 0 = pressed: cross 0xBFFF, square 0x7FFF,
  R2 0xFDFF, start 0xFFF7), `screenshot` (native 368 x 480), `savestate` (op save/load, slot).
  Client: Expanded's `psxrecomp/tools/debug_client.py`.
- `python tools/t3live.py fight [--pages 2] [--cell 0] [--frames 900] [--every 75]` boots a
  private copy (character-builder/live/run, with build-release's mods), walks Title -> Arcade
  (two Start presses reach the select screen) -> R2 x pages (Tag, Custom) -> right x cell ->
  **square (costume 1; cross = costume 2)** twice (character, Tekken 3 moveset card), waits for
  state 8, then screenshots every N frames while pressing attacks. Output:
  character-builder/live/shots, game log character-builder/live/game-log.txt.
- Verified: TOMMY picked, own model installed and drawn (0 words differ), 11 screenshots.
- `python tools/t3live.py nav <steps>` (2026-10-16): step scripts after boot: buttons (incl. `l2`),
  `route:arcade|team|practice` (menu order Arcade, VS, Team Battle, Time Attack, Survival, Tekken
  Ball, Tekken Force, Practice), `wait:N`, `shot:NAME`, `vram:NAME` (whole VRAM via `vram_peek`),
  `ram:ADDR:LEN`, `film:FRAMES:EVERY` (shots named by state/phase), `log:TEXT[:SECONDS]`, `fight`;
  `--cpu KEY` as for fight. Output in live/nav. Verified: Practice name call found in state 8.
  Headless runs use the software renderer (`gl_fbo_peek` answers "GL pipeline inactive"), so CPU
  VRAM is what is drawn.
- Also: Shift+F1..F12 saves a state in the window, F1..F12 loads (`--memcard-dir` folder).

## Regression check of the model import (`python tools/t3cb.py regress`, 2026-10-15, works)

- Re-imports every character in the test folder with an own model and a `source.*` file, the
  app's way (`tools/render/regress.py`, Expanded's venv; Medea ~55 s, the others ~4 s). Run it
  after every change to `direct_import.py`, `reduce.py`, `texture_bake.py`, `model_import.py`.
- Checks: **fits** (no flat-shading fallback); **holes** = pixels that are background in PS1
  renders (QUADCULL, PAINTER) of the bind pose from 4 sides but body without culling
  (`NOCULL=1`), so gaps between arm and body do not count; **speckle** = share of texels whose
  colour decoded with the polygon's own CLUT is > 20 Lab from the quantiser's input;
  **same** = byte-equal to the approved model.
- `--unrigged` (2026-10-22): also every test model as if its file had no skeleton (ids `ur-<name>`):
  the automatic rig, turning upright, chibi legs and the build; a model that no longer imports counts
  as worse.
- Approved state: `<game>/character-builder/cache/regress/<id>/approved.{bin,json,png}`
  (`--approve` stores the current results); exit 1 and `WORSE: ...` when a check got worse
  (slack: 20 hole pixels, 0.2 % speckle). `sheet.png` = new above approved.
- **tested**: re-enabling bent quads (max_bend 180) gave `WORSE: holes` (2484 vs 95), RGB
  palettes with normal-only charts gave `WORSE: speckle` (0.97 % vs 0.17 %).
- Approved 2026-10-15: medea 95 holes (single edge pixels) / 0.17 %; test (Rogue) 709 / 1.93 %:
  real holes at the side of the head, plus a long hair strand sticking out backwards (open,
  `plans/direct-import.md`); tommy 0 / 0.24 %. 2026-10-16: test 0 holes (fixed), medea 19 / 0.08 %.
- `--all` also imports `<game>/character-builder/testmodels/*.glb|fbx` over Nina (ids `tm-<name>`;
  locked files skipped): tm-CesiumMan, tm-Michelle (~140 s), tm-Soldier (~120 s), tm-Xbot.

## Probe renders (`tools/render/probe_render.py`, Expanded's venv)

- `probe_render.py GAME MODEL out.png [--frames n] [--pick i,j] [--size px] [--yaw deg] [--live DIR]`:
  MODEL = stock model number or a T3CM file; the frames from `t3live.py fight --probe`
  (`--live` another folder with probe.bin + game-log.txt, e.g. a donor reference fight);
  `--yaw` turns the camera around the fighter; `ROWS=1` colours per row.
- `--rest 0,90,180 [--solved] [--donor N]`: the donor's frames instead of a fight (`--solved` =
  bind_pose.solve; `--donor` = the model number whose frames are used).
- Donor reference: move `build-release/mods/ttt1/<Prefix>-model.bin` aside, run the fight with
  `--probe`, copy probe.bin and game-log.txt to a folder, put the file back.
- Builder API from a script: GET `/` holds the token (`<meta name="t3cb-token">`), send it as
  `X-T3CB-Token` with POSTs (`/api/model/check`, `/api/model/import`, `/api/model/remove`).
- `tools/render/mesh_render.py GAME MODEL out.png [--yaws] [--size] [--crop head]`: the source
  file (.fbx/.glb) with its own textures, to compare an import with what it should look like.
- probe_render drops incoherent probe frames (joints not at their parent's offset, second layers
  off their row): those showed fake torn heads and arms.
- VRAM snapshot: `T3LIVE_PROBE_START=N T3LIVE_PROBE_CALLS=1000 python tools/t3live.py fight
  --probe` writes `live/probe.bin.0.vram` (1024 x 512 halfwords) after N + 1000 renderer calls;
  compare the player's band (x 384, y player * 256) and CLUT rows (504 + player * 4 + id >> 6)
  with the model file.
- `PAINTER=16 probe_render.py ...`: polygons drawn by ordering-table slot (mean z / 16, last
  inserted first) without a depth buffer, as the PlayStation; diff against the normal render.
- The debug build must be rebuilt after patch changes: `cmake --build build-opt-dbg --target
  psx-runtime` with the toolchain on PATH.
- `QUADCULL=1` culls each quad by its first triangle and `MAGENTA=1` paints the background
  magenta: with `PAINTER=16` this is the closest offline view of what the PlayStation draws;
  look for magenta inside the silhouette (holes).


## Releases (2026-10-16, works)

Only after the user approves. Bump `APP_VERSION` (server.py) and the READMEs, commit, then:
`git tag -a vX.Y.Z -m "Dizzy Character Creator X.Y.Z"`, `git push origin vX.Y.Z`,
`git archive --format=zip --prefix=character-builder/ -o Dizzy-Character-Creator-X.Y.Z.zip HEAD:character-builder`
(tracked files only: no game data; check the list), and
`"C:\Program Files\GitHub CLI\gh.exe" release create vX.Y.Z <zip> --repo sullythebear/tekken3characterbuilder --title "Dizzy Character Creator X.Y.Z" --notes-file <notes.md> --verify-tag`
(gh is logged in as sullythebear; from PowerShell, Git Bash does not have it on PATH).

## End-to-end test of 0.6.0 (2026-10-18, browser pane + t3live)

A new fighter ZETA (Judo, Paul) went through the whole app:
1. Save.
2. Builder: head part, Athletic shape, Build (1081 triangles).
3. Portrait from the 3D model.
4. Computer voice; stage look night; Move Lab 2: 12 → 30.
5. Save, then Check library: only "portrait licence not known".
6. Game folder: all seven files (ui, name, label, model, moves, stage, sfx) and the customs.txt
   line.
7. `t3live fight --cell 4`:
   - own model installed, 0 of 5362 words differ;
   - "Zeta has 1 changed moves (moveset 0)", "P1 Zeta changed moves in (1)";
   - "has a stage colour variant (arena 0)";
   - the fight showed the Athletic Paul.
8. Delete: all seven files gone from both folders, customs.txt back to the four fighters.

The "Zeta model: missing ...TTT1-arcade-P1.3dm / rejected" lines are Expanded's guest-model
lookup before the own model takes over. They show for every custom fighter.

## Builder regression (`t3cb kitregress`, 2026-10-18)

`python tools/t3cb.py kitregress [--approve]` builds six fixed mixes (`tools/render/kitregress.py`).
Each covers one path of kitbash: plain, whole skin, KITTEST's mix with shape and colours, areas at
half size, near the packet limit, coarser normals. It compares their SHA-256 with the approved
state in `character-builder/cache/kitregress/`. Exit 1 when a mix that built before fails.
Approved on 2026-10-18; the KITTEST mix is 23080 bytes, as installed in game. Run it after any
kitbash or writer change.

## Check after 0.7.0 (2026-10-19)

- `t3cb regress --all`: all 11 import models the same as approved (BrainStem locked, as before).
- `t3cb kitregress`: all 7 Builder mixes the same.
- Unit tests: 54 pass.
- First `--unrigged` run (2026-10-22): 26 of 27 test models import without their skeleton (the
  auto rig, turning, build; BrainStem the robot too). CesiumMan does not: stripped after loading,
  its skinned mesh stays in bind space without the node's turn (lying along Z, arms along Y, 0.75)
  and the glTF Y-up hint is kept; an unskinned export has its node transform applied. A height
  ratio cannot tell lying from standing (Buffedwolf stands at 0.55 with its tail). `build` now
  stops with the rig's reason when a model has no skeleton (was a KeyError in reduce).
