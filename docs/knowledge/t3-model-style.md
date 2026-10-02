# How Tekken 3's own fighter models are built (rules for imports)

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## How Tekken 3's own fighter models are built (study 2026-10-01, all 48 models; scratch t3study)

Rules for imported models, so they match the originals:
- **GPU packet limit (tested 2026-10-02):** every polygon becomes a GPU packet (flat tri 32,
  flat quad 40, gouraud tri 40, gouraud quad 52 bytes) in a fixed buffer per player. Stock
  models need at most 32580 bytes; Medea v15 needed 33596 and the game crashed (exit code 1) as
  the fight started, right after the model and texture were installed. The importer keeps
  models under 31000 (`MAX_PACKET_BYTES` in `model_import.py`). Prefer quads (26 bytes per
  triangle) over triangles (32-40).
- **Budget:** 1000-1150 triangles per fighter (a quad counts 2), 24-29 KB. About 40 % of the
  polygons are quads (cheaper: 8 or 12 bytes for two triangles). Mix of flat and gouraud
  polygons; gouraud on round surfaces (head, chest, arms, thighs), flat on hard ones (boots,
  hands, armour). A few models are all flat (Kuma, Gon) or nearly all gouraud (Ogre).
- **Triangles per part (human average):** head 166 + second head layer 84 (~250), torso 74 +
  second layer 56, pelvis 68 (+45), thigh 43, shin 52, foot 52, collarbone 17, upper arm 49,
  forearm 43, hand 70 (fingers are modelled: mitten plus thumb), accessories 12-24.
- **Joints:** knees, elbows, ankles and wrists share a ring of 6 vertices: the child borrows the
  parent's list (g1), averages 3 with the previous list (tail group 2) and copies 6 into the
  scratch list (group 4). The torso deposits 36-71 vertices into the cache (group 3) for the
  collarbones, head and pelvis.
- **Polygon records** (verified by normal/face agreement and slot/normal consistency over 30
  models): flat triangle u32 slots x 4 at shifts 0, 7, 14 + u32 (normal + 1) x 4 at 0; flat quad
  slots at 0, 7, 14, 23 + normal at 0; gouraud triangle slots 0, 7, 14 + normals of corners
  0, 1, 2 at shifts 0, 7, 16 of word 1; gouraud quad slots 0, 7, 14, 23 + corner 0's normal at
  word 1 shift 0, corners 1, 2, 3 at word 2 shifts 0, 7, 16. Quad corner order is the GPU's:
  triangles (0, 1, 2) and (1, 3, 2).
- **Textures:** the head (face, side of the head), the skin and often the torso are 8-bit with
  the 256-colour CLUT 0 (one skin palette); clothes, belts, boots are 4-bit tiles with their own
  16-colour CLUTs (row 1, ids 64+). Nina: 8-bit area 64 x 192 texels at the left of the page,
  4-bit tiles to its right, the page about 60 % used. The **face is half a face (32 x 64
  texels), mirrored** over the nose line, in two versions (eyes open / closed for hits); the
  side of the head is a separate 32 x 64 tile. Hair strands and fringes are extra polygons over
  the face with transparent texels (colour 0x0000).
- **Applied in the importer (v13, 2026-10-02, offline renders through Expanded's own bind):**
  `lowpoly.py` builds tubes of rings (torso/pelvis 12 sides, legs 8, arms 7) and a
  latitude/longitude head shell, shaped by rays onto the original's outermost surface (ring
  distances clamped to 0.35-2x the ring's median: no spikes), joints share their ring; gouraud
  quads with smooth normals; texture charts per part (face chart 6x density with a palette of
  its own, back of the head 1.6x, torso 1.3x), skyline packing. Colours are **baked by rays**:
  from just outside the low-poly surface inwards, the first original surface hit (nearest-point
  lookup picked eyeballs inside the sockets: white patches under the eyes). See-through source
  triangles (texture alpha < 128 at their centre: eyelash cards) are left out of shape and colour
  (they painted white bars over the eyes). Medea over Nina: 846 triangles, 19.6 KB.
- **Look:** a sculpted low-poly head (nose, brow, chin, ears) of ~250 triangles; limbs are
  6-8-sided tubes; textures are painted: flat colour areas with soft gradients and crisp
  details (armbands, straps, laces), no photographic noise; gouraud light does the shading. An imported model
  therefore has to fit the donor's size (Tekken 3 models: about 20-30 KB).
- **Proportion and colour rules added 2026-10-02 (tested in game, Medea v19):** limbs move part
  of the way (exponent 0.7, at most 1.6x, never thinner) to the donor's limb thickness (median
  distance of each limb row's vertices from its bone); textures get baked light and stains
  flattened per chart (divided by their own 6-texel blur to the power 0.5), a 3 x 3 median, then
  saturation 1.25 and contrast 1.08 (`texture_bake.flatten/paint/vivid`); the face skips the
  median and flattening.
- **Standing on the ground (tested in game 2026-10-02: v20 floated):** the animations put the
  hips at the donor's height, so an import must be scaled by its **hip height above the soles**,
  not by its leg bones (heels and thick boots put the soles far below the ankle bone). Donor
  hip height = lowest vertex of its standing pose below the hip joint. Medea over Nina: soles
  now at 1256 vs Nina's 1261 (game units below the root); she is ~11 % taller than Nina overall.
