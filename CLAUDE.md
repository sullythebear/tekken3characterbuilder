# Working on the Tekken 3 Character Builder

Talk to the user in Dutch; the app's UI and code comments are English.

## Working method (save tokens, lose nothing)

- At the start read only `docs/INDEX.md`, then only the docs the task needs.
- Read code only when `docs/code-map.md` is not enough, and then targeted (grep, line ranges),
  never whole files.
- Never read log files whole; filter for the relevant lines (`python tools/t3cb.py report`).
- Use `tools/t3cb.py` (deploy, patch, build, report, import, setmodel) instead of manual steps.
- After every finished step update the right `docs/` files (knowledge/, plans/, done/,
  code-map.md) so a next session has nothing to find out again.
- Keep messages to the user short.

## Layout

- `character-builder/app/server.py` – local server (stdlib only), build/launch/sync logic
- `character-builder/app/creator_patch.py` – applies/removes source patches; profiles `recompiled` and `expanded`
- `character-builder/app/expanded_patch_data.py` – the CUSTOM-page edits for Tekken 3 Expanded
- `character-builder/app/custom_page.py` – reads customs.txt, labels and `.jui` portraits (stdlib)
- `character-builder/app/expanded_custom.py` – writes portrait pack, name plate and customs.txt (runs with Expanded's venv)
- `character-builder/app/model_export.py` – fighter models from the disc (BNS) as mesh JSON for the 3D preview (runs with Expanded's venv; output in `character-builder/cache/`, game data, never commit)
- `character-builder/app/ui/` – the interface (no build step); `ui/costumes.js` = WebGL preview and colour variants

## Rules

- Never commit or upload game data: no disc images, `generated/`, `workspace/`, builds or `.exe` files.
- Patches are exact-text edits that must match once; a mismatch aborts without writing. Keep them small.
- Every patch must be fully reversible (`uninstall` restores the original byte for byte).
- Test in a COPY of the game folder, never in the user's working install.
- When you learn something about the game, add it to `docs/knowledge/` (what, where, how it was verified: tested/code/inferred).

## Build and test (Windows, game folder = Tekken 3 Expanded)

- Toolchain: `<game>/.setup/tools/toolchain-*/bin` (cmake, ninja, clang). Expanded's Python: `<game>/.setup/venv/Scripts/python.exe`.
- Rebuild after source changes: `python tools/t3cb.py build` (cmake with the toolchain on PATH;
  the builder's Build button does the same). Copy the builder first: `python tools/t3cb.py deploy`,
  then `python tools/t3cb.py patch`.
- Game log: run `build-release/Tekken_3_Recompiled.exe` with stderr redirected; the builder writes `character-builder/logs/game-log.txt`.
- Custom fighter lines in the log start with `Custom fighters:`; page switches log `TTT1 characters: <page> page`.
- Testing with the user: ask them to click **Test** in the builder (it builds if needed, plays, and
  writes a report). After every test, read `<game>/character-builder/logs/test-report.md` yourself
  before answering, summarised: `python tools/t3cb.py report` (for the user's Expanded test folder:
  `D:\Tekken 3 Recompiled	ekken3-expanded-1.1.3\character-builder\logs	est-report.md`), and
  open `game-log.txt` beside it only when the report is not enough.
