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
- MegaAngel's wings were missed: they hang on extra bones on the spine, and the radius pieces
  are measured against was the median over all chest vertices, wings included (0.35 vs. wing
  tips at 0.88). `protrusions.find` now takes the radius from vertices on the part's own bones.
  Newly listed and folded by default: MegaAngel's four wing halves, the tails of Buffedwolf,
  Two-Tails and Crowley's coat; Seed-san unchanged. The five re-approved after a look (speckle
  of Buffedwolf 0.40 % and Two-Tails 1.53 %, no visible change); every other model identical.

## Automatic rig v2 (2026-10-21, tested; `autorig.py`)

Models without a skeleton were locked (the first shape-based rig was dropped on 2026-10-03). Now
the importer rigs them itself and the builder shows the result (rig view), with the player able
to correct it.

- **How** (numpy only): the model becomes a solid of voxels (80 over its height); every voxel's
  depth (layers of erosion); from the deepest voxel of the torso the plain and the depth-weighted
  geodesic distance (26 neighbours, relaxation in place); the body's ends = local maxima of the
  plain distance; feet = the two lowest (else, legs joined in a dress: the lowest vertices each
  side), hands = the most mirror-like pair to the sides, ends far behind the body (wings, capes,
  tails) penalised; the weighted ways from the ends back to the torso run through the limbs'
  middles: where the legs' ways part = the crotch, the arms' = the chest. Shoulder = where the
  arm's way thins (depth <= 1.55 x the arm's), elbow / wrist at 0.36 / 0.70 of shoulder ..
  fingertip, hip sockets above the split at the thigh's middle line, ankles at 5 %, head joint
  0.15 of the way from the shoulders to the top. Body parts: bone segments (spine up to the head
  joint and out along the shoulder girdle, pelvis to both sockets, thighs from a quarter down,
  feet to the heel) grown through the solid, each vertex taking its voxel's bone.
- `autorig.orient`: up = the axis whose low end is two feet (2-4 pieces in a 2 % slice, dense
  surface samples) and high end one head, with the solid's centre of volume above the middle
  (weighted most); glTF (.glb/.vrm) keeps Y up unless the model lies (Y under 0.6 of the width).
  Front: the feet reach farther ahead of the ankles than behind; the left-right axis is the one
  the two feet stand apart along.
- `autorig.skeleton` turns the joints into a Mixamo-named skeleton with full weights per part,
  so the whole importer (reduce, protrusions, mittens, chibi gate, checks) takes the model as
  rigged. `direct_import.load` rigs every file without bones; `set_rig(joints, turn)` / CLI
  `--rig file.json` use joints placed by hand ({marker: [x, y, z]}, `autorig.MARKERS`) and a turn.
- **Benchmark** (`tools/render/autorig_bench.py --orient`, 22 rigged test models rigged again as if
  they had none, their skeleton as the truth): the old rig failed on 7 and missed by ~5 % of the
  height; v2 rigs all 22, joints 3.3 % off on average (worst: shoulders 4.6 %), 80 % of the
  vertices on the skeleton's part, 0.5-5 s per model; orient right in 113 of 132 turned copies,
  33 of 34 for glTF (Y up given). Weak: furry models with big tails (Two-Tails, MeganTheFox),
  long coats (Crowley).
- **tested** Unrigged files made from rigged ones (scratch `strip_skin.py`: skins removed, skinned
  meshes made root nodes): all six checked "rigged by the creator"; Soldier (Z up after
  stripping) stood up by itself; imported over Nina (834 triangles from 11376) and fought in
  Arcade: punches, kicks and jumps moved arms and legs with their bones, the body stayed whole.
  Its texture came out lighter than the source's (not checked whether the stripping or the bake).
- **Rig view** (builder, `ui/rigview.js`): front and side point views with the skeleton; dots to
  drag (mirrored by default), Use these joints (`/api/model/rig` -> `rig-upload.json`, checked
  again), Rig automatically again, turns (tip over, roll, turn around), Try a pose (each point
  turned with its part's bone, forward kinematics), Colour the body parts. Browser-tested: drag,
  apply (by hand, knee moved), back to automatic, import.
- rig-upload.json travels to rig-source.json / rig-prev.json with the texture (`move_texture`) and
  in .t3char packages.

### Auto rig v2.1 (2026-10-21): branches, the head, painting

- **tested** The lighter texture of the unrigged Soldier is not the rig's: the rigged and the
  unrigged Soldier bake the same 256 x 256 page (mean RGB 123/99/77 and 120/97/75; the source's
  1024 x 1024 texture is 84/69/54 with its dark margins). The bake is the same for both.
- **Branches**: the body's other ends (tails, ears, wings, a ponytail; not hands, feet or head and
  15 % of the height from them) are followed back to where they join the skeleton; the branch
  takes that bone's part (one on a leg: the pelvis), so a tail moves stiffly with the hips.
- **The head**: every voxel above the head joint (+3 % of the height), within half the shoulders'
  width and not more than 12 % behind the head joint (a tail curling up) is the head's: snouts,
  jaws and big ears no longer go to the chest.
- Benchmark (`autorig_bench.py`): parts 79.9 % -> 82.2 % on average; Buffedwolf 59 -> 81 %,
  Crowley 55 -> 83 %, MeganTheFox 64 -> 75 %, MushroomFairy 81 -> 85 %. Two-Tails 67 -> 55 % is the
  benchmark's: her hair and ears hang on bones without part names, which the truth counts as
  chest; the rig gives them to the head, as the animation needs.
- **Painting body parts** (rig view, `autorig.paint`): pick a part on the palette, brush over the
  model in either view; strokes [x, y, z, part] go with the joints in rig-*.json ("paint", 8000 at
  most) and win over the automatic parts (each painted cell 1/60 of the height and its
  neighbours). Browser-tested: Michelle without a skeleton, part of an arm painted Head, applied:
  24 strokes stored, the server's parts as the view showed them.

### An FBX without a skeleton (2026-10-22, tested in game)

- "Stylized Low Poly Character" (CC-BY 4.0, `testmodels/dl-bps-StylizedChar`): `Low Poly
  Character.fbx` has no skeleton, `..._Rigged.fbx` is its Mixamo twin (in the benchmark as truth).
- **tested** The check rigged the FBX by itself (already Y up, no turn). Its cartoon build (big
  head, short thin torso) put the shoulders on the hips: the thickness rule fired at once. New
  rule: walking in from the fingertip the arm's way runs straight, then bends into the torso at
  the shoulder (35 degrees); when the thickness rule puts the shoulder more than 5 % of the height
  below that bend, the bend wins. Benchmark: this model 6.4 -> 3.6 %, "test" 2.8 -> 2.0 %, the rest
  unchanged; 23 models: joints 3.34 %, parts 82.7 %.
- **tested** Imported (900 triangles from 2226) and fought in Arcade against Lei: punches, kicks
  and a knock-down; arms, legs and head follow their bones.
- **tested, fixed** With Shirt.png chosen as the texture image the whole model came out one
  blue-green: the image went on all six materials, and the five colour-only ones read one texel.
  `fbx.character` now names the materials whose texture file is not in the FBX
  ("missing_textures": {1: "Shirt.png"}); the chosen image goes on those only (else, when the
  file names none, on every material without a texture that has a UV map). The check says which
  file a model asks for. After the fix: skin, hair, the patterned shirt, black trousers, in the
  builder's 3D view and in the fight. The rigged twin, imported without the image, was right
  before the fix: the colours were never the rig's.

## Chibi builds get longer legs (2026-10-22, tested in game)

Chibis (KayKit, 100Avatars Vladi / CuteMoth) were refused: Tekken's animations put the pelvis at
a human height, so short legs stretched the whole model into a giant (2026-10-19).
- `direct_import._human_legs` (after the rig, own or automatic): hips under `LEGS_FROM` (33 %) of
  the height are brought to `LEGS_TO` (40 %): vertices and bones of the legs (and the pelvis below
  the hip line) stretched along Y from the soles, everything else moved up whole, so the big head
  and short arms stay. The rig view keeps the model as rigged (`P_rig`): joints placed and parts
  painted there apply before the stretch. The check says it ("Chibi build: the hips were at 19 %
  ... made longer, to 40 %") instead of refusing. Hip shares measured: Mage 19 %, Knight 21 %,
  Rogue 23 %, Vladi 25 %, CuteMoth 15 %.
- **tested** KayKit Mage (rigged) in a fighter: 846 triangles from 4509, the builder's 3D view
  right (hat, face, robe, longer boots); in Arcade against Eddy about his size, punches and kicks
  with the big hat following the head; no giant.
- Automatic rig of a chibi without a skeleton: its legs part low, so the dress rule (crotch at
  46 %) must not fire. Shoulders say it: chibis' are at 41-57 % of the height, everyone else's at
  59 % and more (25 skeletons measured) -> `CHIBI_SHOULDERS` 0.58. For a chibi the crotch is
  halfway between where the legs' ways part (too high on a wide short torso) and the lowest slice
  in which both legs' ways lie in one piece (too low: feet close, a robe): KayKit Knight / Mage /
  Rogue 19 / 17 / 25 % against their skeletons' 21 / 19 / 23 %. Unrigged copies of the Mage and the
  Knight are rigged and get their legs made longer.
- Benchmark with the chibis (28 models): joints 4.2 %, parts 79 % (without them 3.34 % / 82.7 %
  as before). Knight 21 %: his weapon end is taken for a hand (drag it in the rig view); CuteMoth
  and Vladi without a skeleton fall just outside the chibi test (shoulders 58 / 63 %), so their
  hips come out high; with their own skeleton the legs are made longer as they should.

## Auto rig v2.2 (2026-10-22): big heads, shoulders, short legs

- `_ends` keeps up to 24 body ends (was 12): a big helmet's corners (5 ends) and two ends per
  foot (toe, heel) pushed a hand out, and the helmet's corners became the hands (Knight).
- Shoulder: the bend rule also fires when the way climbs steeply into a big head after the bend
  (the torso's middle is then in the helmet). The shoulder is put on the arm's own line, measured
  on the mesh (the middle of the vertices around the way between 10 and 45 % of the arm from the
  fingertip), when the way runs more than `ARM_LINE` (2 %) of the height above it.
- The human-crotch rule (crotch at 46 % when the legs' ways join low) only fires below 25 % of the
  height (Vladi: knees together under a dress, 15 %); between 25 and 38 % short legs are real
  (Knight / Mage: their thighs 40 % in the stretched model, no longer forced to 48 %).
- Benchmark (28 models): joints 4.24 -> 3.44 %, parts 79.0 -> 81.8 %, no model worse. Knight
  21.4 -> 4.1 %, Mage 5.7 -> 5.0, Buffedwolf 7.4 -> 5.2, Crowley 4.2 -> 3.2, Rogue 4.7 -> 3.9.
  (**code**; CuteMoth's 56 % parts is the benchmark's: its skeleton has no bone named as a head, so
  the whole head counts as spine.)
- `t3cb regress --unrigged`: every test model imported again without its skeleton (ids
  `ur-<name>`), through the automatic rig, turning, chibi legs and the build.
- Turning upright: an FBX's GlobalSettings UpAxis/UpAxisSign is now the up hint (as glTF's Y):
  all 7 test FBX files (Mixamo, Samba, Low Poly, Medea, Tommy Y up; Rogue Z up) match their
  geometry. Without a hint, wings and long tails pull the volume rule to the depth axis
  (Crowley, MeganTheFox, Two-Tails come out lying), so the hint matters; the importer reads no
  OBJ, so every file has one. Front: the toe vote turns a model round only below -0.035 of the
  height; CuteMoth (round feet, -0.031) was turned backwards, MushroomFairy votes +0.038.
  Thumbs and buttocks were measured as cues too: not reliable (signs mixed). Rotated copies
  without a hint: 134 / 168 right (**code**).
- Shoulder, 2nd pass: the bend is measured in the front view only (x, y): a wiggle of the way in
  depth (Two-Tails' fur) faked a bend halfway down the upper arm. A shoulder more than 6 % of the
  height below the arm's line (the way ran down into the torso before thinning: a fluffy arm as
  thick as a slim chest) moves out along the way to where it meets the line. Benchmark 3.44 ->
  3.36 % joints, parts 81.9 %: Two-Tails 6.0 -> 4.4, Lydia 2.5 -> 2.1, MegaAngel 3.7 -> 3.5, no model
  worse (a 4 % trigger moved A-pose shoulders: Soldier 1.9 -> 3.3; a 30 degree bend fired on Low
  Poly's sloping shoulder).
- Fold-down fix (`protrusions._fold`, 2026-10-22): a part that already hangs down but is wide (the
  unrigged Knight's cape, on the hips by the auto rig, 27 % of the height) was listed, no angle
  cleared the body, and the fallback turned it to 90 degrees: straight back. Folding down now
  never lifts a part above how it hangs; such a part is "already hangs down (25 degrees), left as
  it is". **tested** KNIGHTTEST (the Knight without its skeleton, through the builder's API):
  852 triangles, live fight (t3live) with own model installed, 0 of 5607 words differ; probe
  renders: helmet, face, guard with both gauntlets up, cape on the back, sword at the hip.

## Painter: colours by hand (2026-10-22, tested in the browser pane)

Many 3D files online come without colours (or with a texture file missing). The user asked for an
easy painter. On the 3D model page, after an upload's check: **🎨 Paint the model**.
- The model in 3D (WebGL, every triangle flat in its own colour: the file's texture at the
  triangle's middle, else grey), as the rig view stands it (upright, facing +Z).
- Tools: 🖌 Paint (drag; brush size; a ring shows it), 🪣 Fill (the connected piece of about the
  same colour: a shirt, a boot), 💧 Pick (a colour from the model), ✋ Turn (also right-drag;
  wheel zooms at the pointer, Shift-drag moves). Front / Back / Left / Right views, Undo / Redo,
  "Both sides at once" (the mirrored triangle by its middle point), 20 preset colours (skin, hair,
  clothes) and any colour. Only triangles seen are painted (an ID buffer of the triangle numbers).
- Saved as `colours-upload.json` `{"colours": ["#rrggbb"], "runs": [[first, count, colour]]}` over
  the triangles as `_load` gives them; the import (`--colours`) gives each colour a plain swatch
  material (`PAINT_MATERIAL` + index) with the painted triangles' corners split off, so merging,
  reducing and baking treat it as any material. The check: "551 triangles painted by hand in 2
  colours"; a file without any colour gets the hint to paint it. Moves to `colours-source.json`
  on import and travels in `.t3char` packages.
- **tested** (browser pane, PAINTTEST with Low Poly Character.fbx): fill made the shirt blue in one
  click (sleeves too), the brush painted both knee bands at once, the painting came back after a
  reload, the import (900 triangles) shows the blue shirt and yellow bands in the PS1 renders; no
  console errors. Unit tests: `ColourPaintTests`.
- 🧍 Body part tool (one click colours a whole part by the skeleton: head, upper arm, thigh...,
  both sides with "Both sides at once"; `face_parts` sends each triangle's part): for a model in
  one grey piece, where Fill would take everything. Fill can "Stop at sharp edges" (50 degrees).
- Fix: a reduced model bakes only materials with a texture, so a colourless body took the paint's
  colours (the grey Soldier came out red). Once painted, materials without any colour get a grey
  swatch (`src["plain"]`, not counted as textures in the check). **tested**: a Soldier without
  skeleton and materials, painted head / forearms / hips by body part, imports grey with the
  three colours where painted.

## Texture images: .tga, several, automatic and by hand (2026-10-22, tested in the browser pane)

The user asked for .tga textures, added automatically and by hand. On the 3D model page
(🖼 Textures): **Add texture images** takes several files at once (.png, .jpg, .tga; 16 per model,
64 MB each (2026-10-22: was 16, too small for an uncompressed 2048 x 2048 TGA; packages up to 96 MB); TGA has no signature, so the server checks its header). Each image goes, automatically:
1. on the material that asks for it by file name (FBX RelativeFilename, glTF image uri; matched by
   name without extension or case: `Shirt.tga` fits a model asking for `Shirt.png`);
2. else on a material named like it (`hair_mat` <- `Hair.png`);
3. else, the only image, on every material without a texture but with a UV map (as before), unless
   the player put it on a material already.
A table lists every material (triangles, "asks for X") with a choice: Automatic (what it gets and
why), Its own texture, Plain colour, or any added image. Removing an image puts the materials that
had it back on automatic (other choices keep their image). Stored as `texture-<stem>-<n>.<ext>` and
`textures-<stem>.json`; they move with the model on import / undo and travel in `.t3char` packages.
The materials check now says what each wears ("6 materials: 0 with a texture in the file, 1 with
an added image, 5 in a plain colour"), which images the model asked for and got, and which added
images are on no material.
- **tested** (PAINTTEST, Low Poly Character.fbx, which asks for Shirt.png): Shirt.tga and Red.tga
  added through the file field at once; Shirt.tga went on "Cloth A" automatically; Red.tga chosen
  for "Hair" in the table; removing Shirt.tga kept Hair on Red.tga; the import gave red hair; the
  files moved to `texture-source-1.tga`; an exported package imported again built a byte-identical
  model. Unit tests `TextureImageTests`.
- NIKKI (the user's own test, 2026-10-22): an Unreal export (44112 triangles, 381 bones, 16 TGA
  maps of 16 MB: _D, _N, _M, _S, Strands, Tangent) failed with "Unable to allocate 11.1 GiB" in
  `remesh.snap`. Cause: the FBX's mesh stands Y up but its skeleton lies Z up; `_upright` turned
  the model by its skeleton and laid the mesh down (166 long along Z, 29 high), so the reduce grid
  (voxels from the height) became 1571 x 416 x 2281. Fixes: `_align_skeleton` (before `_upright`)
  measures how far the bones' joints are from their own vertices (`_skin_fit`, share of the size);
  above 0.08 it tries the 24 whole-axis turns of the skeleton alone and takes one that fits at
  least twice as well (NIKKI 0.757 -> 0.045; none of the 29 other rigged test models is turned);
  `remesh.snap` refuses a grid over 1.5e8 cells with a clear message. Texture sets: `map_kind`
  (colour by _D / BaseColor / Albedo, "other" for normal / mask / specular / roughness / AO / ...,
  never put on automatically, marked "not a colour map" in the choice list and summed up in the
  check), `_named_like` by words (CamelCase split, prefixes T_ / MI_ / M_ and map suffixes
  dropped, one name's words all in the other's): NIKKI's Body and FaceAcc get their _D maps.
- NIKKI's face came out white: her "Head" material has its own UV map but none of the 16 added
  images is its colour map (only `CargoLying_1002_N`, the normal map of UDIM tile 1002), and the
  FBX's colour is the default 0.8 grey. Body_D cannot stand in (the head's UVs fill the whole
  page). The check now warns for such a material (UV map, no texture, default light grey, >= 3 %
  of the triangles, while other materials are textured): add its colour map, choose one, or paint it.
- NIKKI, round 2: the user has the whole set (Head_D, Teeth_D_Baked_REVISED, eyelashMat_D, SRMO,
  ...; 30+ files) but only 16 images were allowed. Now 64; adding many images checks the model once,
  after the last (`recheck: false` for the others). Matching by words: noise words (Baked, REVISED,
  Mat, ...) and map words anywhere after the first word dropped, plurals made singular
  (Eyelashes ~ eyelash), and besides "all words of one in the other" a word both share counts when it
  is all the material says apart from words most images carry (the character's name): Eyelashes ->
  T_Cosmetics_eyelashMat_D, EyeTeeth -> Teeth_D (not Eye_Iris: "eye" alone is not all of
  "eye teeth"), Head -> Head_D. SRMO is not a colour map. A per-material **Leave out** (`"hide"`),
  automatic for see-through layers by name (`SEE_THROUGH`: eyeshell, cornea, tearline,
  eyeocclusion, ...; NIKKI's Eyeshell, a thin shell over the eyes, would be drawn white over them);
  their triangles are dropped in `build` only (`_drop_hidden`), so painter and paint runs keep the
  file's triangle numbers.

## More formats: .zip, .gltf, .obj (2026-10-23, tested in the browser pane)

Most free models online come as a .zip (Sketchfab: `scene.gltf` + `scene.bin` + `textures/`;
others an `.obj` + `.mtl` + images). `formats.py` (stdlib, runs in the server) turns them into a
.glb at upload, so the whole importer works on them unchanged: a .gltf gets its buffers and
images embedded (matched by path or by file name in any folder); an .obj becomes one primitive
per material with the .mtl's Kd colour (sRGB -> linear) and map_Kd image (options such as
`-s 1 1 1` skipped; v flipped to glTF's top-down); an .obj has no skeleton, so the auto rig rigs
it. A .zip gives its model (the biggest .fbx/.glb/.vrm, else .gltf, else .obj); its images the model
does not take become texture images (matched automatically as usual). Limits: a .zip 96 MB, 2000
files, 400 MB unpacked, no paths outside. The file name shown is "soldier-obj.zip (soldier.obj)".
- **tested**: Soldier.glb written out as .obj/.mtl/png and as .gltf/.bin/jpg, both zipped:
  the glTF keeps its 51 bones and both textures; the OBJ is auto rigged with both textures; the
  OBJ zip uploaded through the file field, imported (838 triangles), textures right (camo, red
  hood and belt details). Unit tests `FormatTests`.
- Leg webs of auto-rigged models: the Soldier's knees touch, so (1) the auto rig's growing let
  inner-knee points cross to the other leg -> `autorig.segment` now gives a leg point to the leg
  whose bones are nearest in a straight line; (2) after `reduce` a triangle with corners on both
  legs more than `WEB_BELOW` (12 %) of the height below the hips goes (the fighting stance stretched
  it into a web from knee to shin). Unrigged Soldier: cross-leg triangles 25 -> 10, all at the
  crotch; the rigged Soldier loses 8 (no holes in the renders). The back flap of the unrigged
  Soldier still hangs diagonally over the thighs.
- `WEB_BELOW` 0.03 -> 0.12: at 3 % NIKKI's thighs (touching just under the crotch) got holes (culling holes 99
  -> 203); at 12 % she is byte-identical and the Soldier's knee and calf webs still go (13 triangles).
- `regress.py` now builds a character the way the builder does: with its texture images
  (`textures-source.json`, or an older `texture-source.*`), colours and rig beside `source.*` (NIKKI
  came out grey before).
- ASCII FBX (2026-10-23): `fbx.read_ascii` builds the same node tree as the binary reader
  ("Class::Name" -> "Name\x00\x01Class", `*N { a: ... }` arrays read fast as one list, base64
  `Content` as bytes, comments skipped); `fbx.read` picks it by the header. FBX 6 (2010 and older,
  binary or ASCII) gets a clear message (export as FBX 2014 or newer). **tested**: Mixamo, Medea and
  Low Poly written out as ASCII FBX (13.5 / 10 / 0.5 MB) read identically to their binary files
  (mesh, UVs, materials, bones, weights, textures); the model check passes. Unit test `AsciiFbxTests`.
- Leg webs, final rule (2026-10-23): only triangles below the knees plus `WEB_ABOVE_KNEE` (25 %) of the way up
  to the hips go. The 12 % rule cut readyplayer.me's coat tails between the legs (regress: holes 95 -> 241,
  WORSE); now readyplayer.me, Soldier, Michelle and NIKKI are byte-identical (rigged models untouched) and the
  unrigged Soldier still loses its shin web (13 triangles).
- Regress 2026-10-23 (`--all --unrigged`): all approved models the same except MegaAngel (holes 52 -> 1) and
  MushroomFairy (skirt flaps), changed by the fold-down fix; both reviewed and approved. 26 of 27 unrigged
  test models import (CesiumMan: the known test artefact).
