# Done: versions and features

Details and test results of each feature are in `docs/knowledge/` (named per entry).

| Commit | What | Tested |
|---|---|---|
| (next) | GPU packet limit in the importer; Medea v16 | in game 2026-10-02: works (v15 crashed: packets) |
| 139c2cb | Patch 11: own textures; FBX import (lowpoly tubes, gouraud quads, ray-baked texture, hands, loose pieces); docs/ split, tools/ scripts | v13 in game: works |
| 29c383a | Patch 10: own model replaces the donor's in memory; first FBX import | in game (big head, Medea over Kuma) — `knowledge/own-models.md` |
| ae6f3a6 | Builder 0.3.7: costumes in 3D, colour variants, clothing pieces (patch 9) | in game (KUMA T costume 3) — `knowledge/models-costumes.md` |
| 0e6d7a8 | Patch 8: custom fighter graphics for ID 43 and others (strip tiles) | in game — `knowledge/donors.md` |
| 40a1841 | Donor tests: Anna works, Kuma glitches, True Ogre retest | `knowledge/donors.md` |
| 62b5671 | Donor tests Ogre, Gon, Dr. B, True Ogre; moveset key fix (patch 7) | `knowledge/donors.md` |
| dc6845d | Builder 0.3.6: style layer; Copycat (Mokujin) works (patches 5, 6) | `knowledge/donors.md`, `knowledge/mokujin.md` |
| 55c884b | Builder 0.3.5: one-click Test with compact report | `knowledge/testing.md` |
| 5cd691e | Dizzy vs Kazuya / King tested | `knowledge/custom-page.md` |
| 5d41587 | 0.3.4: never drop CUSTOM page fighters silently | `knowledge/custom-page.md` |
| 7958aa2 | 0.3.3: custom fighters fight with their donor's moves (patch 4) | `knowledge/custom-page.md` |
| 0e21804 | Install/Update wipes the CUSTOM page without a character library | `knowledge/custom-page.md` |
| a5738a4 | 0.3.2: donor descriptors and move diagnostics (patches 2, 3) | `knowledge/custom-page.md` |
| 4dd5fc6 and earlier | repository setup, .gitignore | – |
