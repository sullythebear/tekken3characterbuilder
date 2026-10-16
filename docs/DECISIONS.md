# Decisions

Important technical choices and why. Newest last.

- **D1 (2026-10-16) Studio order.** Unit tests first, then the module structure over the
  existing code, then the modules from most to least certain (Voice/Portrait, Character
  Builder, Move Lab, Stage Lab). Reason: every later step needs a safety net, and Move/Stage
  depend on research whose outcome is open (`AUDIT.md`).
- **D2 (2026-10-16) No rewrite, no file moves.** The six modules are UI sections and small new
  Python modules next to the existing ones; `server.py` keeps the routes. Moving files would
  break the deploy/patch tools and the docs for no user benefit.
- **D3 (2026-10-16) Tests with the standard library.** `tests/` uses `unittest`, runs with any
  Python 3.10+ (`python -m unittest discover tests`), needs no game data. No pytest dependency.
- **D4 (2026-10-16) Automatic name call = Windows' classic SAPI voice.** System.Speech's desktop
  voices (here "Microsoft Zira Desktop") are rule/unit-based speech synthesis built into
  Windows, offline, no AI model and no cloud. It stays the easy default; the player can use an
  own recording or silence instead. If the project owner counts it as AI voice generation, the
  default becomes "Silent" (one line in `name_call.MODES` / `validate_character`).
- **D5 (2026-10-16) Character Builder parts.** Two sources: (a) Namco's own parts read from the
  player's disc at runtime (`kitbash.py`, never shipped, same rule as donors); (b) shippable
  third-party parts only with a licence that allows redistribution (`ASSET_LICENSES.md`).
  (a) comes first: same skeleton and PS1 look, no licence question.
- **D6 (2026-10-16) No automatic push or release.** Commits stay local until the owner asks
  (owner's instruction 2026-10-16).
- **D7 (2026-10-16) Team Battle tiles (patch 18).** Custom tiles at VRAM (384,256), page 0x96,
  palettes cut to 128 colours in C so two share a row; measured free at the selector and the
  FIGHT screen. Alternative (dynamic slots in the Tag area) was more code for no gain.
- **D8 (2026-10-16) Kitbash fit gate instead of free choice.** Parts are offered only from
  fighters within 7 % of the base's height; the server refuses the rest. Arbitrary mixes left gaps
  and torn heads; a geometric re-segmentation would be research with an open outcome.
