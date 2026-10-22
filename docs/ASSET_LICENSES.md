# Asset licences

The builder ships **no** third-party art, models or sounds. Game data (disc, `generated/`,
`workspace/`, models, textures) is read from the player's own copy at runtime and never
committed or packaged (`CLAUDE.md`).

## Categories

1. **Shippable**: licence allows redistribution and modification (e.g. CC0). None yet.
2. **Shippable with conditions**: e.g. CC-BY (credit kept in this file and in the app). None yet.
3. **User import only**: the player brings the file; the app converts it locally and never
   redistributes it (`.t3char` carries the player's own source model, their responsibility).
4. **Unsuitable**: non-commercial/no-derivatives licences, unclear origin, game rips.

The app has a per-fighter register too (Fighter page, "Credits and licences": source, author,
licence of the own 3D model, portrait image and name call recording). Packages carry it and
Export warns when an asset in the package has no known licence.

## Register

| Asset | Source | Author | Licence | Category | Technical fit | Checked |
|---|---|---|---|---|---|---|

Test models used for the regression check (`character-builder/testmodels`, not committed) are
category 3: downloaded with the owner's permission for local testing only. Added 2026-10-19 (CC0,
each in its own `dl-*` folder): KayKit Adventurers Mage, Rogue_Hooded, Knight (Kay Lousberg,
LICENSE.txt in the KayKit GitHub repo) and 100Avatars R1 Rose, Lydia, Witch, HorrorNurse
(Polygonal Mind, licence CC0 in toxsam/open-source-avatars, files on arweave.net). Added
2026-10-20: 100Avatars R3 Vladi, Crowley (CC0, same source) and Seed-san (VirtualCast, VRM Public
License 1.0, its meta allows modification and redistribution; from vrm-c/vrm-specification).
Added 2026-10-22: "Stylized Low Poly Character" by Brett Post Script (CC-BY 4.0: attribution
required; opengameart.org/content/stylized-low-poly-character, low_poly_character_fbx_files.zip):
the FBX without a skeleton, its rigged twin and Shirt.png, in `dl-bps-StylizedChar` (local tests
of the automatic rig only, not shipped).

Candidate sources to check one by one before any download (licence per asset, not per site):
Kenney (CC0), Quaternius (CC0), Poly Haven (CC0), OpenGameArt (mixed), Sketchfab (mixed).
