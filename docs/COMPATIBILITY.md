# Compatibility per game variant

**tested** = seen in game; **code** = implemented, not seen in game; **no** = not supported.

| Feature | Tekken 3 Expanded 1.1.3 | Tekken3Recompiled 0.1.4 |
|---|---|---|
| Custom fighter in the roster | **tested** (CUSTOM page, up to 12) | **tested** (one, in Jun's slot 23) |
| Fighting style (donor moveset) | **tested** (all 21 donors) | **tested** (donor via launch setting) |
| Name on select/VS/HUD | **tested** | **tested** (VS name) |
| Portrait on the select screen | **tested** | no (saved for later) |
| Costume colour variants | **tested** (patch 9) | no |
| Own 3D model | **tested** (patches 10-14) | no |
| Body parts from Tekken 3's fighters | **tested** (similar build only, see `plans/kitbash.md`) | no |
| Home stage and music | **tested** (patch 17) | no |
| Stage colour looks | **tested** (patch 19, night and sunset on Gon's stage) | no |
| Changed move damage per fighter | **tested** (patch 20: KITTEST's 3 from 25 to 60 in its own moveset buffer, opponent untouched; skipped in a mirror match, which shares one buffer) | no |
| Rival at Arcade stage 9 per fighter | **tested** (patch 22: KITTEST's rival Paul at stage 9 in three Arcade runs, Ogre and True Ogre after it) | no |
| Moves on other buttons per fighter | **tested** (patch 21: KITTEST's f+2 alias slot 303 pointed at Liftshot, record 239, in Arcade; it hit, the opponent's slot untouched, back to 116 when the buffer is someone else's) | no |
| Name call | **tested** in log, Practice only (as Tekken 3 itself) | no |
| Move Lab: style's command list | **tested** (read from the disc) | **code** (same disc data; Recompiled not tried) |
| CPU opponents | **tested** (patch 15) | no |
| Team Battle icons, mixed teams | **tested** select, FIGHT, FIGHT 2 (grey) and results screens (patch 18) | n/a |
| `.t3char` packages | **tested** | **code** (same format) |

The patch revision in use is shown in the builder (step 1) and in every test report.
