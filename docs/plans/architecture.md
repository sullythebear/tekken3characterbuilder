# Conversion architecture: where fidelity is lost, and the way forward (2026-10-23)

The goal: a modern model and its textures in, a recognisable Tekken 3 fighter out, automatically.
This note audits the converter, names the sources of information loss, compares donor-based
rebuilding with source-driven reconstruction, and sets out what the engine allows.
Facts: **tested**, **code**, **inferred**.

## What the game takes (code + tested; `knowledge/own-models.md`, `t3-model-style.md`)

| Limit | Value | Where it comes from |
|---|---|---|
| Model bytes | the donor's slot, 18-29 KB (Nina 26112, NIKKI's 26028) | the PS1 load: size table 0x80095A9C; our hook overwrites the loaded model in place |
| GPU packets | ~31000 bytes per player (flat tri 32, quad 40, gouraud tri 40, quad 52): ~1100 triangles | a fixed packet buffer in PS1 RAM per player; 33596 crashed (tested) |
| Structure | 20 rows (+ accessory rows 21-26), one bone per vertex, <= 128 vertex slots per row list, 255 texel coordinates per row | Namco's 3DMK format and the native vertex transformer 0x80036CAC |
| Texture | one 256 x 256 4-bit page (64 x 256 halfwords) + CLUTs; the face's 8-bit TIM is reloaded by the game | the donor's VRAM layout |
| Animation | the fighting style's own animations drive the rows | the game: no retargeting needed for play |

These are the original game's asset limits, not limits of the recompiled engine as such: the
recompilation runs the PS1 code natively over emulated RAM and an emulated GPU.

## Sources of information loss (tested, this week's renders)

1. **Donor topology (Tekken rebuild).** Moving the donor's ~650 polygons onto the import keeps
   Namco's joints and texture density, but the shape vocabulary is the donor's: long hair,
   buns, flared skirts, coats, tails and accessories have no polygons to land on. NIKKI and the
   elf lost their long hair, the elf her skirt's flare; every fix was a local patch (fit torso,
   fit head, fold extras, see through hair).
2. **Free shell reduction (reduce.py, before).** Keeps the silhouette (hair, skirt), but the
   collapse let triangles run across joints, so shoulders and elbows tore when rows turned.
3. **The budget.** ~1100 triangles and one 4-bit page: the face gets ~5x the texel density of the
   body; small accessories vanish; colours quantised to 16 per chart group.
4. **Rig and segmentation.** Body parts come from the skin weights or the automatic rig; a wrong
   rig misassigns geometry everywhere downstream (the elf's shoulders at the hips).
5. **One bone per vertex.** Joint seams stretch instead of bending; Namco hides this with
   designed joint rings, which a converter has to make too.

1 and 2 are architectural; 3 and 5 are the engine's asset format; 4 is analysis quality.

## Source-driven, segment-aware reconstruction (prototype, tested 2026-10-23)

`reduce.reduce(segmented=True)`, build method "segment": the voxel shell of the source (keeps
hair, skirt, accessories as silhouette), every shell point labelled with the body part of the
bone weighing most on the nearest original point (`_shell_parts`), and the quadric collapse only
merges points of one part (`decimate(keep=...)`). Seams between parts stay narrow strips (joint
rings), so no triangle crosses a joint; the face keeps its extra texel density and the bake.

Results, same donor, pose and light (renders, then live fights with probe renders):

| | Tekken rebuild (donor) | Segment-aware (source) |
|---|---|---|
| E2EELB | short bob, no skirt flare, eyes after many fixes | long blonde hair, headband, eyes, flared skirt, boots; 830 triangles |
| NIKKI | no long hair; clean face | long hair down the back, face, outfit; 866 triangles |
| Fight pose (in game, 0 words differ) | intact | intact: no torn shoulders; a small shard at NIKKI's thigh |

The source-driven converter preserves identity markedly better with fewer triangles: it keeps what
the user uploaded instead of what the donor had. It is the main path from here; the rebuild stays
as an option (its strengths: Namco joint rings and head layout).

## Approach B: the recompiled engine (code, not yet built)

Expanded already draws its own geometry: `src/tekken3_ttt1_renderer.c` wraps the native vertex
transformer per row (it has that row's GTE rotation and translation) and links its own GPU
packets (laser beam, blade) into the game's ordering table, in memory from
`psx_mod_alloc_gpu_dma_memory()` - outside the game's fixed packet buffer.

So a backward-compatible extension is possible without touching the game's data structures:
- **Extra geometry per row**: a side file with polygons per row (hair, skirts, accessories, or a
  denser body) drawn by the hook with the row's matrix, as ordinary PS1 primitives (gouraud,
  affine textures, CLUTs): the same look, no packet or slot limit. The stock model stays as it is
  (or a reduced base), so the game and the original fighters are untouched.
- **Texture space**: a second texture page needs a free VRAM area per player (to be measured).
- **Lighting** of extra polygons must reproduce the game's (the GTE colour from normals), or the
  extra parts would look different: the probe records give the light matrices to copy.
- **Risks**: depth order against the game's own polygons (ordering table slots, measurable with
  the probe), both players and mirrored fights, frame time (native code: small).
Cost: one engine patch (reversible, exact-text as every builder patch) and a writer for the side
file; the converter would put the polygons the slot cannot hold into it.

## Decision

1. Make the segment-aware source-driven converter the default (Approach A); keep rebuild and
   free reduction selectable. Fix its remaining defects as part of the method (shards, the
   elf's arm pose), measured with the regress set and the anatomy view.
2. Then build Approach B as an optional "more detail" layer on the same converter: the base model
   fits the original limits (works everywhere), the side file adds what did not fit.
