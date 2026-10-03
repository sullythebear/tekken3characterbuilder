# Lessons

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Lessons

- The first Dizzy run failed because the game was not rebuilt after patching: always check the
  build time against the patch time.
- Jun's roster in Tekken3Recompiled is ticked from her selector, which only runs once her import
  is loaded; skipping the import also removed the slot.
- **tested** A reference pose must be checked against the donor's own data before fitting an
  import to it: the builder's standing frames (W) looked fine in the preview but put the
  collarbones and hips on the wrong side (joint offsets need z negated) and tilted the head
  21 degrees; the donor's own 50/50 seam vertices (both copies meet in the bind pose) showed it.
- **tested** Compare an import with its donor in the *same* in-game frames: run a fight with the
  donor model (move the fighter's model.bin aside), then render both models with that probe
  (`probe_render.py --live DIR`). Renders of the import alone hid the head tilt.
