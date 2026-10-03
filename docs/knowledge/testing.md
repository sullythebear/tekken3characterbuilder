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
- `python tools/t3cb.py build` – `cmake --build build-release --target psx-runtime` with the
  toolchain on PATH; prints `build OK (...)` or only the error lines.
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
- Also: Shift+F1..F12 saves a state in the window, F1..F12 loads (`--memcard-dir` folder).
