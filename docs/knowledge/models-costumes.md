# Fighter models, costumes, palettes, 3D preview

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Fighter models and costumes on the disc (palettes, phase 0, tested 2026-10-01)

Goal (user): recolour costumes in the builder on a live 3D model, save colour variants as extra
costumes. Phase 0 proved the model can be shown from the user's own disc, without the game.

- `TEKKEN3.BNS` (in Track 1) has 303 records (`tools/bns_tool.py inventory|extract --source
  "disc/Tekken 3 (USA) (Track 1).bin"`). Fighter **model m** (`0x800958C4` model map, 0..51) is
  records **71 + 4m .. 74 + 4m**: `3DMK` model, `VH` (sound header), `ARC` (costume textures),
  `BIN`. The three sizes match the per-model table at `0x80095A9C` (12 bytes: 3DMK, VH, ARC size).
  King costume 1 = model 6 = records 95..98; Kuma = 159..162; Jin costume 2 = 147.
- 3DMK: `nrows` at +0, rows of 14 ints from +24 (`tools/ttt1/model/fmt.py`). Per row: `w[1]` =
  primitive block (`parse_b`), `w[2]` = **UV + material block** (`parse_c_ps1`: one entry per
  primitive, same order), `w[3..5]` offset from the parent, `w[6]` part, `w[12]` vertex block of
  the next row. A material is the PS1 **CLUT id** `(y << 6) | (x >> 4)`, `| 0x8000` for 8 bpp.
- ARC: TIMs in the player's **64 × 256 halfword band**, mostly 4 bpp tiles with their own
  16-colour CLUT (x = 16n, y = 1..2), a few 8 bpp TIMs with a 256-colour CLUT at (0, 0). The 4 bpp
  TIMs whose CLUT is at y = 0 are the 30 strip tiles uploaded by `0x8007619C`, not the model.
  King costume 1: 27 CLUTs, every material used by the model present. In game the CLUT rows land
  in rows 504.. (P1) / 508.. (P2).
- Geometry: Expanded's `anim_model.bind()` (slots and triangles per row) plus a `world()` per
  row (rotations from a 57-channel pose). Expanded's own `world()` fails on empty accessory rows
  (part -1); the phase 0 converter has a guarded copy. Pose used: frame 0 of the first clip of
  Kazuya's TTT1 moveset (`motion.decode` on the user's `bankedroms.bin`); same 18-bone skeleton.
  Y must be flipped for display. Result for King: 1095 triangles, recognisable, one accessory
  (leopard piece at the hip) possibly misplaced.
- Viewer: textures kept as **palette indices** (one 4 bpp and one 8 bpp index texture), palettes
  in a 256 × n texture, a shader looks colours up per pixel; PS1 colour 0x0000 is transparent.
  Recolouring = rewriting the palette texture, instant. Prototype: scratch `convert.py` +
  `viewer_template.html` (three.js 0.160); the page holds game data, keep it local.
- **Builder 0.3.7 (built 2026-10-01):**
  - `app/model_export.py` (Expanded venv): `donors` reads the model map from SLUS; `model --model m`
    reads records 71+4m / 73+4m straight from the disc image (`bns_tool.load_us_table`,
    `open_bns_source(...).read_at`) and writes mesh JSON. All 48 fighter models export. Strip
    tiles are recognised by image (0, 0) 8 × 32, not by CLUT row (Kuma, True Ogre and Gon have
    model CLUTs on row 0). 8 models use a few CLUT ids on rows 5..6 (320..397) that are not in
    their ARC (shared game palettes): drawn grey, not editable (Bryan costume 2: 258 of 967
    triangles, others < 80). The ARC's other members are move names (text), a "TK3pSDW" table
    and compressed data, not palettes.
  - Server: `/api/models`, `/api/model/<n>` (cached in `character-builder/cache/`, gitignored).
    `character.json` gains `costumes`: `{name, base, slot, cluts: {id: [colours]}, recipe}`.
  - UI `ui/costumes.js`: own WebGL renderer (no three.js: the builder's CSP allows only its own
    scripts and it must work offline), pick pass for clicking parts, parts grouped by colour with
    a skin guess, modes Whole / Parts / Every colour / Schemes. Tested in the browser with
    KUMA T: model shows, scheme recolours live, clicking selects a part, save and reload keep
    the variant.
  - In game, **T3CB-PATCH-9** (tested in game 2026-10-01, works): the builder writes
    `<Key>-T3-pal.bin` ("T3CP", entries slot/base/CLUT id/colours). A variant either replaces one
    of the donor's costumes or, for two-costume donors, is costume 3. The patch maps a custom
    fighter's free slot to the variant's base model (`custom_slot_model`), sets
    `third_costume` when slot 2 has a model (Expanded then lends the Start bit at 0x80097EF4 so
    Start picks costume 3; custom fighters of three-costume donors also get their donor's third
    costume now), and in state 8 writes the variant's CLUTs to rows 504 + player * 4 + row every
    frame (`custom_palette_tick`). Slot 3 has no button, so at most one extra costume.
  - **In-game test (2026-10-01 20:11, report read):** KUMA T with variant "Colour 1" (base 0,
    slot 2 = extra costume 3). Log: `Kuma T has 9 variant palettes`; at select `P1 costume 3`
    (Start); probe `model map 22` (costume 1's model, the variant's base) with moveset key 11.
    The user confirmed the recoloured Kuma in the fight ("alles werkt"); 3m31s, exit 0, no
    errors. T.OGRE T and ANNA T kept working.
  - Pose: see the numbered rounds below (standing pose built from the skeleton).
  - User's first try (screen recording, 2026-10-01): Anna, Nina, Law, Kuma render well. True
    Ogre (model 32) looks like a tilted heap: not broken triangles (no stretched edges in stance
    or rest pose, checked offline) but a skeleton Kazuya's pose does not fit; its rest pose lies
    flat with the tail out. Needs True Ogre's own stance. Clicking the model on a donor costume
    only showed a toast and the Costumes panel was off-screen, so the user never reached the
    colour tools. Fixed: a click now opens (or makes) the colour variant for that costume and
    scrolls to the part; the camera fits the model's bounding sphere to the canvas (models were
    cut off), scroll zooms relative to that, double-click resets.
  - **Pose.** Rounds with the user (2026-10-01):
    1. Kazuya's TTT1 fight stance on every model: "odd" (it is Kazuya's stance, not theirs).
    2. T-pose (each bone turned from the stance by the shortest rotation): arms straight out
       stretch the welded shoulder/armpit vertices (PS1 vertices shared between bones) into spikes.
    3. Arms down, still turned from the stance: Law's torso sat crooked on his hips (the stance
       turns the upper body against the pelvis; the shortest rotation keeps that turn) and the
       head looked over the shoulder.
    4. Now `model_export.stand_pose()`, built from the skeleton's own axes. Rest layout (all
       rotations zero): every main bone runs along local +X, sideways offsets are local Z, local Y
       is front/back. Chains: spine 1 -> head 19; pelvis 3 -> thigh 5/8 -> shin 6/9 -> foot 7/10;
       spine -> **collarbone 11/15** (139 long, must be level: hanging it down made the shoulder
       bulges) -> upper arm 12/16 -> forearm 13/17 -> hand 14/18. Spine = fixed frame (X up,
       Z sideways); pelvis = spine with a half turn about Z (as in every stance frame); thighs
       ±0.07 rad apart, shins straight; collarbones level; arms hang 0.38 rad out, forearms
       straight; hands straight on (their X runs along the hand); feet at a right angle to the
       shin about its Z (FOOT_ANGLE, toes forward, verified side-on). Head: its stance angle to
       the spine, taken against the stance spine straightened by the shortest rotation, then
       HEAD_TURN -0.785 rad about the spine (calibrated on Law: +0.785 turned it further away).
       The pose's bone rotations are the same for every model, so these constants hold for all.
    5. User (screens of Hwoarang, Bryan, Eddy, Nina, Heihachi, Jin, Law): feet upside down,
       textures missing, fight stance wrong for everyone.
       - **Missing pieces = a bind-order bug, not textures.** `anim_model.bind()` (written for
         Expanded's guest models) only draws the second layers (rows 2, 4, 20: second geometry of
         spine, pelvis, head) when word 6 holds a guest part number; Tekken 3's own models keep
         0 or 1 there. So that layer was skipped on 42 of 48 models (missing chest, hair, face
         pieces), and on Hwoarang, Bryan, True Ogre, Lei... the shoulder and head rows that borrow
         its vertices lost triangles (unresolved slots). `model_export.bind()` draws each second
         layer right after its main row (2 after 1, 4 after 3, 20 after 19): every slot of all
         48 models resolves (checked with a script over all donor models).
       - **Feet**: found by seam fitting (scratch `fit.py`): turning a joint so the triangles shared
         by two bones stretch least, one symmetric set of angles over 10 models (left mirrors
         right). Free fitting folds the body (legs splay, arms fold in), so only twists about the
         bone and a few pitches were free. Result `POSE_TWEAKS`: foot twist -2.75 rad (the sole
         was on top), foot pitch 0.39, pelvis pitch 0.06, thigh twist 0.12. Collarbone twist
         (1.96) also lowered the energy but swung the arms up forward like a zombie; keeping the
         arms' direction it gains only 1 %, so arms are not tweaked. Shoulder seams barely depend
         on arm spread or collarbone raise (±5 %): the small flaps at the shoulders (Jin) come
         from meshes built for the guard; they stay with arms down.
       - Fight stance switch removed (it was Kazuya's stance on everyone). Gon keeps the stance
         as his only pose. Own stances per fighter: Expanded's importer captures the TTT1 select
         screen in MAME (`tools/ttt1_import.py capture_select`, `tools/ttt1_select_probe.lua`,
         cursor path from Xiaoyu) and `motion.export` then writes `<Name>-TTT1-idle.poses`; its
         path table (`tools/data/ttt1_characters.json`) only lists the guests, the cells of
         Law, Paul... would have to be found first.
       Checked in the builder: Law, Hwoarang (front and side, complete model, soles down, toes
       forward), Jin. Mesh format 3 (`model-<n>-v3.json`; the server removes older files of that
       model). `facing()` turns each model so the shoulders lie along +X; the viewer looks from
       FRONT_YAW 0.35.
    6. User: feet back to front, Bryan missing textures.
       - **Feet**: FOOT_ANGLE +90° was the wrong sign. With an extra turn about the shin the ankle
         seams are least stretched at 180° (11.4 vs 17.9, 8 models); 180° about the shin plus the
         fitted half twist equals FOOT_ANGLE -90°. Now -90° with foot twist 0.15, pitch 0.29.
         Checked side-on in the builder on Nina (heels back) and Law (soles down, toes the way
         he faces).
       - **"Shared palettes" were a second texture page.** Material bit 0x100 = texture from the
         second 4-bit page (64 halfwords further on); the CLUT is the id without that bit (320 ->
         64, 329 -> 73...). The band was 64 halfwords wide, so TIMs at x >= 64 and their CLUTs were
         dropped (Law's belt, Bryan's trousers). Band now 128 halfwords (`BAND_WORDS`, sent as
         `band_words`), page-2 triangles get u + 256 (4-bit) / + 128 (8-bit). All 48 models: no
         grey left; Bryan costume 2 (model 25) checked in the builder: whole camouflage trousers.
         Mesh format 4. In game nothing changes (the tick writes the costume rows).
       - Double-click reset redrew before the browser showed it; it now redraws on the next
         animation frame (checked).
    7. **Own fight stances from TTT1 (2026-10-01, user asked).** Expanded's select probe
       (`tools/ttt1_select_probe.lua` via `ttt1_import.mame(..., at="select")`, MAME 0.289, the
       user's tektagt.zip, saved state `select.sta`) dumps RAM with the cursor on a cell; ~16 s per
       capture. All 40 cells captured (paths from Xiaoyu: R x k then U/U,U/D) and named from the
       snapshots. TTT1 moveset keys 0-13 = Tekken 3 donors 0-13 in the same order (Paul, Law, Lei,
       King, Yoshimitsu, Nina, Hwoarang, Xiaoyu, Eddy, Jin, Julia, Kuma, Bryan, Heihachi); Ogre and
       True Ogre are moveset 14 with bodies 14 / 20, Gun Jack 16, Anna 17 (body 18). Not in TTT1:
       Mokujin (Tetsujin draws a random moveset), Gon, Dr. B. Grid (row, column from Xiaoyu at
       3,1): row 3 = Xiaoyu, Yoshimitsu, Nina, Law, Hwoarang, Eddy, Paul, King, Lei, Jin; row 2
       col 4 Gun Jack, 5 Anna, 6 Bryan, 7 Heihachi, 9 Julia; row 1 col 6 Kuma; row 4 col 6 True
       Ogre, col 7 Ogre (the rest are Expanded's guests, as in `tools/data/ttt1_characters.json`).
       Idle pose = frame 0 of the clip in record `aliases[56]` (motion.IDLE_ALIAS); checked: gives
       exactly Expanded's `Kazuya-`, `Lee-`, `Jun-TTT1-idle.poses`.
       Built as `model_export.py stances` (stances.json in the cache, a Standing / Fight stance
       switch). Looked like the fighters' stances to me (Law's open hand, Anna's hand at her
       face), but the user found all of them wrong and asked to leave fight stances out: the
       switch, the export field and the command were removed again (TTT1 frame 0 on a T3 skeleton
       is not the T3 select-screen pose). The grid and key mapping above stay valid if it is ever
       picked up again (T3's own motion format would be the better source).
    8. User: every standing pose right, except Bryan missing textures.
       - **8-bit materials name their CLUT too.** The viewer assumed every 8-bit material used
         CLUT 0. Bryan costume 1 (model 24) has two 256-colour CLUTs: (0,0) and (0,1); material
         0x8040 = 8-bit with CLUT id 64. Drawn with CLUT 0 its vest showed camouflage scraps and
         holes (index 0 transparent). Now id = material & 0x7FFF for both depths; checked: the vest
         is whole, dark purple with straps. Only model 24 has a second 8-bit CLUT. Mesh format 6.
       - Tried: collarbones at their stance angle to the chest (like the head) hunched Bryan's
         shoulders; collarbones stay level. Seam-length fitting cannot decide the collarbone (the
         stretch keeps falling as it folds into the chest).
       - Still open: True Ogre/Gon tails in the standing pose.
    9. **Pieces of clothing (user: "choose every piece of clothing/accessory and recolour it").**
       The game can only swap whole palettes (CLUTs), so a piece is a set of CLUTs. Measured on
       Bryan (texels inside every UV triangle, scratch `texels.py`): nearly every 16-colour CLUT
       sits on one body part (gloves, boots, armband, each camouflage patch); the 256-colour CLUTs
       are bigger pieces (CLUT 0 = head + skin, CLUT 64 = the vest). Splitting a palette by index
       ranges is not needed. The reverse happens: one garment over several CLUTs (Bryan's trousers:
       six). So the builder groups CLUTs that share a body part and look alike:
       - exporter: `bones` = the row of each triangle (mesh format 7); viewer regions: 1-2 Torso,
         3-4 Hips, 5/6/8/9 Legs, 7/10 Feet, 11/15 Shoulders, 12/13/16/17 Arms, 14/18 Hands,
         19-20 Head, accessories Extra; a CLUT's name = its body parts with >= 25 % of its
         triangles, plus its colour.
       - colour of a CLUT = its entries weighted by texels the model uses (corners and centre of
         each triangle), not the whole palette (Bryan's vest read as "Skin" otherwise). Grey =
         chroma (max - min channel) < 0.12; HSL saturation ran high on dark camouflage tints and
         split the trousers into Red/Orange/Blue.
       - merge: same skin flag, a shared body part, and similar colour (greys: lightness within
         0.25). Bryan: head/skin, vest, armband, gloves, hands, trousers (dark and light camouflage
         patches), boots.
       UI: the "Clothing" tab replaces Parts and Every colour: a list head to feet, each piece with
       its swatches and one colour picker; opening a piece (or clicking it on the model) shows its
       colours one by one and dims the rest of the model in 3D (a 256 x 1 "chosen" texture in the
       shader). Recipes keep `parts` keyed by CLUT ids joined with "-"; older grouped keys still
       apply per id. Checked in the builder: Bryan's light camouflage turned blue alone.
  - Editor split into tabs **Fighter** (name, style, portrait, author) and **Colours** (costume
    variants); Colours switches the preview to 3D, and a click on the model opens Colours. At
    widths ≤ 1100 px the preview is no longer sticky (it covered the form below it).
