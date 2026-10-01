# Working on the Tekken 3 Character Builder

Read `NOTES.md` first: it holds every technical finding so far. Read `docs/vision.md`
for the direction. Talk to the user in Dutch; the app's UI and code comments are English.

## Layout

- `character-builder/app/server.py` – local server (stdlib only), build/launch/sync logic
- `character-builder/app/creator_patch.py` – applies/removes source patches; profiles `recompiled` and `expanded`
- `character-builder/app/expanded_patch_data.py` – the CUSTOM-page edits for Tekken 3 Expanded
- `character-builder/app/expanded_custom.py` – writes portrait pack, name plate and customs.txt (runs with Expanded's venv)
- `character-builder/app/ui/` – the interface (no build step)

## Rules

- Never commit or upload game data: no disc images, `generated/`, `workspace/`, builds or `.exe` files.
- Patches are exact-text edits that must match once; a mismatch aborts without writing. Keep them small.
- Every patch must be fully reversible (`uninstall` restores the original byte for byte).
- Test in a COPY of the game folder, never in the user's working install.
- When you learn something about the game, add it to `NOTES.md` (what, where, how it was verified).

## Build and test (Windows, game folder = Tekken 3 Expanded)

- Toolchain: `<game>/.setup/tools/toolchain-*/bin` (cmake, ninja, clang). Expanded's Python: `<game>/.setup/venv/Scripts/python.exe`.
- Rebuild after source changes: `cmake --build build-release --target psx-runtime` with the toolchain on PATH
  (the builder's Build button does the same; Expanded keeps its own CMake configuration).
- Game log: run `build-release/Tekken_3_Recompiled.exe` with stderr redirected; the builder writes `character-builder/logs/game-log.txt`.
- Custom fighter lines in the log start with `Custom fighters:`; page switches log `TTT1 characters: <page> page`.
