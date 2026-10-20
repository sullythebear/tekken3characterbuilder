# Plan: direct import of PS1-style models

Chosen 2026-10-03 (user): the user supplies a PS1-style model; the builder converts it
technically without changing its look (no remesh, no re-bake).

## Status

- `character-builder/app/glb.py` (glTF binary reader), `direct_import.py` (CLI:
  `direct_import.py MODEL.glb --model N --root GAME --out model.bin`).
- Automatic rig for models without a skeleton (`auto_rig`: T/A-pose, glTF axes Y up, facing +Z;
  joints from the silhouette: arm height from the hands, crotch from the gap between the legs;
  one row per vertex). Scale by hip height above the soles. Normals smoothed over welded
  positions; geometry on welded vertices, UVs per corner.
- Texture: the file's own layout (resized to 256 x 256 if needed), 4-bit, UV islands grouped
  into 16-colour CLUTs (ids 64+, then 128+).
- test2.glb (Tommy Dreamer, Sketchfab, 684 triangles, 256 x 256 texture) over Paul (model 0):
  19348 bytes, offline render clean.
- **Earlier offline renders were mirrored** (compare.py flipped only Y; fixed 2026-10-03: X and
  Y flip, front faces have positive screen area). Text on the shirt now reads correctly.

## Next

1. Done: TOMMY in game (v9), joint seams, bind pose; builder UI (3D model page).
2. User test 2026-10-04: TOMMY "looks very good now" (report clean: own model installed, 0 words differ, no errors). Open: a user test of the 3D model page upload; models without textures or with more
   than ~1100 triangles (warned, not reduced yet); partial seam dropping instead of all (Mokujin).

## In-game test 1 (2026-10-03): texture and face good, proportions wrong

- Cause: the auto rig's crotch came out at 0.6 of the height (a low-poly model has few
  vertices, so "no vertex on the centre line" held almost everywhere): legs reached the chest.
  Now rays along Z through the centre line (lowest hit = crotch), clamped to 0.42-0.50 (baggy
  trousers close the gap low).
- Tekken's root (row 3) sits at the waist, 0.15 of the leg above the hip sockets (Paul): the
  import's root is put at the donor's ratio, then the model is scaled by that height above the
  soles; pelvis/torso split at the new root. Tommy over Paul: scale 1754, ~13 % taller than Paul.
- v2 deployed on TOMMY (test pending).

## In-game test 2 (2026-10-03): worse (chest, thin legs, long neck, shoulders, elbows folded)

The shape-based auto rig cannot place joints reliably; every fix moves the error. Decision:
the user rigs the model in Mixamo (free) and exports FBX Binary (T-pose); `direct_import.py`
now uses a skeleton when the FBX has one (`rig_from_skeleton`: Mixamo names via
`model_import._part/joint`, every vertex on its strongest bone). Untested until a rigged file.
- 2026-10-03: test2.fbx (Mixamo rig, 41 bones) over Paul: same height as Paul, offline clean; v3 deployed on TOMMY (test pending).
- v3 tested in game: much better; light texture glitches (yellow on the head: overlapping UV islands with different CLUTs), hands turned, a hole at the buttocks (per-triangle winding in a crease). v4: islands with >= 6 shared core texels share a CLUT; one global winding decision. Hands: open (the model's), twist still to check.

## v5 (2026-10-04): checked in game by the live setup (probe renders)

- Patch 13: the renderer probe takes TEKKEN3_NATIVE_PROBE_START/_EVERY/_CALLS (defaults =
  Expanded's), so `t3live.py fight --probe` samples two frames out of every 1500 calls over the
  whole fight; `tools/render/probe_render.py GAME model.bin out.png [--pick i,j] [--frames n]`
  renders the import in the exact in-game poses at high resolution (ROWS=1: colour per row).
- Fix 1: the mesh is posed into the donor's standing pose with the file's smooth weights (LBS)
  before writing; the game then turns rows only a little from rest, so one-bone binding no longer
  tears shoulders (T-pose needed 90 degree turns) and hips.
- Fix 2: vertices in the blend zone of hips (thigh -> pelvis) and shoulders (collarbone ->
  torso), child weight < 70 %, stay on the parent row. Applying this at elbows/knees/ankles made
  spikes: limited to hips and shoulders.
- Probe renders of the fight stance: no wing at the shoulder, hips filled, no spikes. Deployed
  on TOMMY (v5).
- v6 (2026-10-04): vertices with two bones >= 30 % become 50/50 seams (372 on Tommy); Mixamo's
  shoulder bones go with the torso (the collarbone rows shrug the shoulder top into a point).
  Probe renders over a whole fight (stance, kick, fall): no tears, no spikes; a slight point
  remains at the rear shoulder in the stance.

## v7-v9 (2026-10-04): the real bind pose

- The standing frames W were wrong for the donor itself (collarbones/hips mirrored, head 21
  degrees): see `knowledge/own-models.md` "Bind pose". Imports are posed into
  `bind_pose.solve`; Mixamo shoulder bones on the collar rows again (as Namco). In game (probe
  renders front/side/back over whole fights): head level, shoulders and hips closed. TOMMY v9.
- Every donor imports test2.fbx (20 of 21 directly; Mokujin's slot is 18412 bytes: flat shading,
  then no 50/50 seams, until it fits). In game also on Law and Nina.

## Builder: 3D model page (2026-10-04, tested in the browser pane and in game)

- Fighter must be saved; "Choose .fbx or .glb" uploads (base64, 16 MB) -> `/api/model/check`
  stores `characters/<id>/upload.*` + `upload.json` (direct_import `--check`: triangles,
  texture, bones, missing Tekken bones, weights). Not rigged = locked (red, Import disabled;
  the server refuses too). Import (costume select = the donor's costume models) -> `model.bin`,
  `source.*`, `own_model` in character.json, synced to the game; Remove deletes them.
- The 3D view shows the own model on its costume (`/api/ownmodel/<id>`, model_export `ownjson`,
  in the bind pose). Previews were mirrored (shirt text backwards): the viewer flips x now.
- .glb with a skin (Blender export) reads bones and weights; a glb made from test2.fbx imports to
  the same model as the FBX (4 bytes of float rounding differ). Blender side names (hand.L) work.

## User test 2026-10-04: Rogue.fbx (Character Creator rig) over Nina came out huge, lying down

- Cause: the file is Z up (Character Creator / 3ds Max); the importer assumed Y up. `load` now
  turns every rigged model upright from its skeleton (up = hips -> head, left = right -> left
  upper arm), snapped to whole axis swaps (Mixamo unchanged: test2 imports byte-identical).
  Re-imported, checked in game (probe renders): right size, animations fine. Its ponytail (30
  vertices on the head bone, up to 4000 units behind) is in the file as modelled.
- A style change after an import: the game only puts an own model over the stock model it was
  made for. Saving with another style now fits the model again from `source.*` (`refit_model`);
  tested Paul -> King -> Paul.
- User test 2026-10-04 13:53: Rogue (TEST over Nina) "works better"; report clean (own model
  installed, 0 words differ, no errors).

## High-poly models: Medea (test.fbx, 17754 triangles) reduced automatically (2026-10-04)

- `reduce.py` (models over 1100 triangles): opaque triangles (texture alpha) -> one voxel shell
  (closing 1), voxels that only the closing added between two limbs removed (the thighs stay
  apart: no skirt), Taubin smoothing, quadric collapse (head x4, `uniform` edge-length term for
  even triangles), relax + project back, weights from the nearest original point, charts by
  normal (65 degrees, head and body apart), texel-exact FFT bitmap packing (84 % of the page),
  bake by 4 short rays per texel from outside inwards (passing transparent texels), gutter bleed.
- direct_import: target from the donor's budget (~28.7 bytes of GPU packets, ~25.5 bytes of
  model per triangle), 7 % fewer per failed try; triangle pairs with the same texels sent as quads
  (52 bytes instead of 80: the binding limit is the 31000-byte GPU packet budget).
- Palettes: median cut + Lloyd refinement; island ownership grown 3 texels into the gutter
  (edge texels read index 0 before: light streaks).
- Unknown bones (Medea's Sleeve1/2 on Spine2): the chain takes the row of the nearest known joint.
- **Own bone lengths** (all imports): joints in the donor's directions at the import's own
  distances; the writer's offsets carry them (Namco gives every fighter its own). Medea's long
  neck came from Nina's longer spine. Previews/renders place joints by the model's offsets
  (`bind_pose.with_offsets`).
- Result (Nina): 992 triangles, imported through the app in 87 s; checked in game (probe renders
  of stance, punches, high kick, falls, front and back; screenshots). TOMMY (King) and Rogue
  re-imported with own bone lengths and checked again.
- User test 2026-10-04 15:56 (report clean) + screenshots: face soft in close-ups, white sleeve
  shards at the arms. Fixes: the face (front of the head below the hair line) gets its own charts
  at 5x density and its own 16-colour palettes (`face_tris` -> `quantise_groups(own=...)`);
  triangles hanging on bones with no Tekken part (cloth, props: 144 on Medea) stay out of the
  shell. Re-imported through the app (992 triangles, 54 s), checked in game.
- User test 2026-10-04 16:31: textures coming and going at the crotch and in the hair, thin
  hands and forearms. Causes and fixes: the donor's face texture reload (patch 14, above);
  thin round parts shrank between surface points (vertices pushed out by their faces' mean gap)
  and are thicker on Namco's fighters too (reduced models: forearms x1.25, hands x1.35 about the
  bone). Re-imported through the app (43 s), checked in game with the rebuilt game.
- User test 2026-10-04 21:10: thin stumps for hands, see-through in many places. Causes: bent
  triangle pairs sent as quads (culled whole by their first triangle) and winding passed across
  non-manifold edges; hands collapsed to wedges (a flat hand with fingers is a thin paddle at
  this size). Fixes: flat quads only; voxel shell made manifold (`_manifold_voxels`), reduced
  models keep their per-face winding; hands replaced by mittens lofted from the wrist rim
  (`_mittens`, sized from the original hand); forearms x1.2; seams dropped weakest-first when
  more than 127 are live at once. Packet estimate 34 bytes per triangle (fits first try:
  912 triangles, 56 s through the app). Checked offline with PS1 culling/ordering emulation from
  every side and in game (stance, kicks, back views).


## Next (agreed with the user 2026-10-15)

1. Done: regression check `python tools/t3cb.py regress` (knowledge/testing.md); user approved
   Medea v19 ("ziet er nu perfect uit").
2. More model kinds: Mixamo, VRoid (.glb), Blender rigs, loose clothing, long hair. Known open
   on Rogue.fbx (not reduced, 641 triangles): holes at the side of the head (culling, so a
   winding problem of the non-reduced path). Done 2026-10-15: the ponytail (modelled straight
   back, rigid on the head bone) is found and folded down by default (`protrusions.py`); the
   3D model page lists such parts with Fold down / Keep as modelled / Remove, an angle slider
   (Auto = steepest that clears the body) and a live side/back preview (the user: "as easy as
   possible, but adjustable"). Tested in the browser pane: remove, 60 degrees, auto, import;
   Rogue re-approved in `regress` (ponytail hangs at 25 degrees).
   Done 2026-10-16 (overnight, no user input): Rogue's head holes (loose hair sheets drawn from
   both sides, see-through texels); 5 downloaded test models (three.js Michelle/Soldier/Xbot,
   Khronos CesiumMan/BrainStem; in `<game>/character-builder/testmodels/`, never committed):
   leg webs fixed, head-row retry, material colours, several textures merged, bones recognised
   by the skeleton's shape (CesiumMan). All four importable ones pass a live fight (model check
   0 words differ, no errors) and are in `regress --all`. BrainStem (a robot, 18 joints
   joint0..17, no human limbs) stays locked: right.
3. Release builder 0.3.8, renamed **Dizzy Character Creator**, restyled after the PS1 and
   Tekken 3 look (the user's wish), with model requirements explained in the app.
   Mockup approved 2026-10-15: `docs/design/mockup.template.html` (renders go in through
   `{{medea}}` etc.; the filled page is not committed). Chrome/fire titles, select grid,
   fight-HUD stage, stamps and health-bar progress; **no PlayStation button symbols**
   (the user: they confuse), plain chrome buttons instead; no real logos or fonts.
   Done 2026-10-16 (overnight): builder 0.3.8 renamed Dizzy Character Creator (UI, title,
   server messages, README, `Start Dizzy Character Creator.cmd`; the folder stays
   `character-builder/`), restyled (charcoal panels, chrome DIZZY / fire CHARACTER CREATOR logo,
   Russo One, roster as a select grid with 1P cursor, silver tabs, chrome and fire buttons,
   status lamps instead of PS symbols, costume names without button names), "What makes a model
   work well?" help on the 3D model tab; narrow screens without sideways scroll. Checked in the
   browser pane (desktop and 375 px, no console errors). Released 2026-10-16 (user: "Yes je mag het
   uitbrengen"): tag v0.3.8 pushed; zip = `git archive HEAD:character-builder` (29 files, no game
   data). Published with the GitHub CLI: https://github.com/sullythebear/tekken3characterbuilder/releases/tag/v0.3.8

## Pre-import check list (2026-10-16, tested)

`direct_import.checks` lists Geometry / Materials / Rigging lines with ok, info, warn or bad.
Run on all 12 test models and Tommy, Medea and Test:
- BrainStem: 0 of 14 needed bones (bad; the import stays locked).
- CesiumMan: bone names recognised from the skeleton's shape (warn).
- VRM_Sample: 1632 triangles with UVs outside 0-1 (warn). `merge_textures` wraps each corner on
  its own, so a repeating triangle can look smeared (inferred from the code).
- The pose warning (arms not spread, width/height < 0.5) did not trigger on any test model.
  The importer is tested only with T-pose and A-pose models.

## Separate texture image (2026-10-18, tested)

Many free models ship their texture as an image file beside the FBX or GLB. The Model Importer
now has "Choose texture image" (.png or .jpg). The image goes on every material without a
texture of its own, before the colour swatches, so the model's UVs stay as they are.
- Tested: Tommy's FBX with its embedded texture taken out, plus the same image given as the
  file, built a model byte-identical to the normal import (20172 bytes).
- Fixed on the way: a model without any texture crashed in `quantise_groups` (no UV charts). It
  now gets one plain palette.
- Browser: an upload with an image through `/api/model/texture` shows "Texture image: chosen".
- Packages carry `texture-source.*`. Undo and Remove handle it.

## More model kinds (2026-10-19, with the owner's permission to download)

Seven CC0 test models, each downloaded into its own folder `testmodels/dl-*/` (never committed;
`regress --all` now also looks one folder deep):
- 100Avatars R1 (Polygonal Mind, CC0, VRM): Rose, Lydia, Witch, HorrorNurse. All import; Rose,
  Witch (hat, skirt) and HorrorNurse fought 600 frames on KITTEST with 0 data words differing.
  Lydia is built with the hips at 71 % of her height (stilts in the source too): imported as she
  is, the check list now warns "Long legs".
- KayKit Adventurers (Kay Lousberg, CC0, glb): Mage, Rogue_Hooded, Knight. Found and fixed:
  - meshes without a skin hanging under a joint node (hats, armour) now move rigidly with that
    bone (`glb.read`), instead of "skin weights are missing";
  - meshes held on a "*slot*" bone (every weapon and shield of the pack at once) are left out;
  - bone names: "upperleg" is a thigh (it read as a shin), rig helpers (kneeIK, IK-foot,
    control-*, ik_hand_*) are no body part (`model_import._part`). The fighter "test" (Rogue)
    has Unreal ik_* helpers: its import changed by 20 bytes, renders identical, re-approved;
  - `remesh.snap`: the grid border was too narrow for a search reach of 2+ voxels (an index past
    the end: the Mage crashed the reduction; below 0 it read the far side silently).
  - In a fight the Mage came out as a stretched giant: KayKit's characters are chibis (hips at
    19-23 % of the height). Models with the hips below 30 % are now refused with a clear reason
    ("Chibi build"); 30-35 % gets a warning.
- `regress --all`: every earlier model the same, except "test" as above; the four VRMs approved.

### Round 2 (2026-10-20, with the owner's permission to download)

- VRM 1.0 samples of the VRM Consortium (`vrm-c/vrm-specification/samples`, VRM Public License
  1.0; the files' own settings allow modification and redistribution): Seed-san, and
  VRM1_Constraint_Twist_Sample, which turned out to be byte-identical to `VRM_Sample.vrm`
  already in use (the duplicate download was removed). 100Avatars R3 (CC0): Vladi (a chibi at
  25 %: refused, as designed) and Crowley (a long hooded coat: imports, fights, approved).
- Seed-san carries a robot arm on her backpack, a skin of its own with bones such as
  "robo_hand.L". Fixed:
  - `glb.read`: a skin's root that hangs on a joint of another skin is linked to it (the backpack
    was a second root);
  - `direct_import._vrm_extras`: in a VRM, a bone that names a body part but hangs on the body
    through bones that name none gets a neutral name (the robot hand had become her left hand);
    twist/roll bones beside a human bone and fingers keep their names (a first, broader rule
    changed every VRM and was replaced);
  - `protrusions`: a piece hanging down far beside the body (more than 12 % of the height) is
    listed; pieces carried by the same extra bone are one part, the whole prop, removed by
    default ("a piece in 6 parts"); folding broke it up.
  - Seed-san then: body, arms and folded ponytail clean, robot arm gone; Crowley and Seed-san
    fought 600 frames on KITTEST with 0 data words differing (KITTEST's model restored).
- `regress --all`: every earlier model the same; Crowley and Seed-san approved.

### Round 3: wings and tails (2026-10-20, with the owner's permission to download)

100Avatars R3 (CC0, licence also in each file's meta): MegaAngel, CuteMoth, MushroomFairy,
MeganTheFox, Two-Tails, Buffedwolf.
- CuteMoth: a chibi (hips at 15 %): refused, as designed.
- MushroomFairy: both wings found (two "Chest" parts) and folded down by default.
- MeganTheFox: the tail found ("Hips: a piece 66 % of the height long, pointing backwards") and
  folded down behind the legs.
- MegaAngel: the wings are not listed (they hang on the arms; only head, chest and hips are
  searched) and stay spread as modelled. Two-Tails: the scarf sticks out at the shoulders as
  modelled. Buffedwolf: clean.
- In game on KITTEST (600 frames each): MegaAngel, MeganTheFox, Buffedwolf, 0 data words
  differing; KITTEST's model restored. All five approved in `regress --all`.
- Slow imports: each try of a reduced model runs the whole shell/charts/bake pipeline (~100 s),
  and a head row over its 255 texture coordinates used to shrink the target by 7 % per try
  (MeganTheFox: six tries, 633 s). `MI._write` now counts the row's coordinates to the end and
  says "row 19 needs N texture coordinates"; `build` shrinks by 255 / N at once. MeganTheFox:
  352 s, same look (re-approved); Two-Tails' tries were the head-detail halvings (349 s, the same
  model); every other model byte-identical.
- Open: wings on the arms (MegaAngel) cannot be folded or removed yet.
