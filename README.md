# Dizzy Character Creator

Create your own fighters for Tekken 3 on PC: a name, a portrait, a fighting style
taken from an existing fighter, colour variants and your own rigged 3D model.

Unofficial fan project. Works with your own Tekken 3 (USA) disc and builds on:

- [Tekken3Recompiled](https://github.com/FishB0nes98/Tekken3Recompiled) by FishB0nes98
- [Tekken 3 Expanded](https://github.com/omarma/tekken3-expanded) by omarma (recommended base)

## Status

| Version | What works |
| --- | --- |
| 0.6.0 | **Studio round.** Builder: body shape (head, arms, legs, body; presets), saved looks, mixes that did not fit now build (textures at half size; body mixes failing 354 → 34 of 1028). Model Importer: face/body detail for big models, a check list before import, a separate texture image. Portrait Lab: saved portraits. Voice Lab: choice of Windows voice, pitch and echo. Move Lab: damage of every basic input read from your disc, and **changed damage per fighter** (patch T3CB-PATCH-20, tested in game). Licence register, asset library, check library, backup of all fighters. |
| 0.5.1 | Body parts keep their colours where Tekken 3's own fighters keep theirs (fight HUD text stays clean). |
| 0.5.0 | Studio modules: Builder (body parts from Tekken 3's fighters, body colours), Model Importer, Portrait Lab, Voice Lab (name call), Stage Lab (own stage and music, stage colour looks; patches 17-19), Move Lab (command list), restore points. |
| 0.4.0 | Model import runs in the background with step-by-step progress, shows the result in 3D and can be undone ("Undo import"). Team Battle shows a generic icon instead of a wrong tile for mixed teams (patch T3CB-PATCH-16). FBX files with several meshes (body, hair, clothes) are read whole; material colours from FBX; VRoid/VRM (.vrm) and Ready Player Me models work; imports about 30 % faster. |
| 0.3.9 | Portrait made from the fighter's own 3D model. Packages (.t3char) share a fighter with its own 3D model (the source file and choices; rebuilt on import). Custom fighters are CPU opponents (Arcade/Time Attack stages 5-8, Survival, Team Battle, Tekken Ball; patch T3CB-PATCH-15). |
| 0.3.8 | Renamed Dizzy Character Creator, restyled after the PS1 and Tekken 3. Own 3D models: upload a rigged .fbx/.glb (locked when not rigged), big models reduced to PS1 size with a baked texture, parts that stick out folded down (adjustable), bones recognised by shape, material colours. Tested in game with TOMMY, MEDEA and Rogue, plus Mixamo/glTF sample models. |
| 0.3.7 | Costumes in 3D in the builder (standing pose, read from your own disc) and colour variants on a Colours tab: recolour every piece of clothing or accessory, the whole costume, or a scheme. A variant goes into the game as a replaced costume or as costume 3 (Start). |
| 0.3.6 | Style layer: pick a fighting style (Striking, Grappling, Traditional, Special), each based on a Tekken 3 fighter. Copycat (Mokujin) draws another style each round (tested), holding the sword only with Yoshimitsu's style (patch T3CB-PATCH-6). |
| 0.3.5 | Test button: build if needed, play, then a compact test report (`logs/test-report.md`) shown in the builder. |
| 0.3.4 | The builder never drops CUSTOM page fighters it does not know: it lists them, to add to the library or remove on purpose. |
| 0.3.3 | Custom fighters fight with their donor's moves and throws (tested with King as donor on Tekken 3 Expanded 1.1.3). |
| 0.3.0 | Fighters on a third CUSTOM page in Tekken 3 Expanded, with their own portrait and name plate, fighting as a Tekken 3 donor. Not yet tested in game. |
| 0.2.x | Fighter in Jun's slot on Tekken3Recompiled 0.1.4 (donor principle proven in game). |

## Use

Copy `character-builder/` into the main folder of your game (the one with `game.toml`),
preferably a copy of it, and run `Start Dizzy Character Creator.cmd`. See
`character-builder/README.txt`.

## Repository

- `character-builder/` – the app (local Python server + HTML UI) and the source patches it applies
- `docs/vision.md` – what the ultimate app should be
- `docs/` – documentation: start at `docs/INDEX.md` (knowledge, plans, done, code map); `NOTES.md` points there
- `tools/t3cb.py` – helper commands for the test copy (deploy, patch, build, report, import)
- `tools/t3live.py` – live checks: boots the debug build, picks a custom fighter, screenshots the fight
- `CLAUDE.md` – working instructions for Claude Code in this repo
- `tools/` – earlier experiments (Dizzy probe, build script for Tekken3Recompiled)

## License

The patches modify code from projects under the PolyForm Noncommercial License 1.0.0;
this repository is meant to follow the same license. Never commit game files.
