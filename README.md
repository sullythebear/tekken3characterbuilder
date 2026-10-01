# Tekken 3 Character Builder

Create your own fighters for Tekken 3 on PC: a name, a portrait, a fighting style
taken from an existing fighter, and (later) colors, accessories, moves and models.

Unofficial fan project. Works with your own Tekken 3 (USA) disc and builds on:

- [Tekken3Recompiled](https://github.com/FishB0nes98/Tekken3Recompiled) by FishB0nes98
- [Tekken 3 Expanded](https://github.com/omarma/tekken3-expanded) by omarma (recommended base)

## Status

| Version | What works |
| --- | --- |
| 0.3.7 | Costumes in 3D in the builder (standing pose, read from your own disc) and colour variants on a Colours tab: recolour every piece of clothing or accessory, the whole costume, or a scheme. A variant goes into the game as a replaced costume or as costume 3 (Start). |
| 0.3.6 | Style layer: pick a fighting style (Striking, Grappling, Traditional, Special), each based on a Tekken 3 fighter. Copycat (Mokujin) draws another style each round (tested), holding the sword only with Yoshimitsu's style (patch T3CB-PATCH-6). |
| 0.3.5 | Test button: build if needed, play, then a compact test report (`logs/test-report.md`) shown in the builder. |
| 0.3.4 | The builder never drops CUSTOM page fighters it does not know: it lists them, to add to the library or remove on purpose. |
| 0.3.3 | Custom fighters fight with their donor's moves and throws (tested with King as donor on Tekken 3 Expanded 1.1.3). |
| 0.3.0 | Fighters on a third CUSTOM page in Tekken 3 Expanded, with their own portrait and name plate, fighting as a Tekken 3 donor. Not yet tested in game. |
| 0.2.x | Fighter in Jun's slot on Tekken3Recompiled 0.1.4 (donor principle proven in game). |

## Use

Copy `character-builder/` into the main folder of your game (the one with `game.toml`),
preferably a copy of it, and run `Start Character Builder.cmd`. See
`character-builder/README.txt`.

## Repository

- `character-builder/` – the app (local Python server + HTML UI) and the source patches it applies
- `docs/vision.md` – what the ultimate app should be
- `NOTES.md` – technical findings: addresses, formats, what was tested
- `CLAUDE.md` – working instructions for Claude Code in this repo
- `tools/` – earlier experiments (Dizzy probe, build script for Tekken3Recompiled)

## License

The patches modify code from projects under the PolyForm Noncommercial License 1.0.0;
this repository is meant to follow the same license. Never commit game files.
