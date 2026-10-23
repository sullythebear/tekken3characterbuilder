"""The converter's reading of a model's anatomy, for the anatomy debug view (builder) and the
offline render (tools/render/anatomy_render.py). Nothing here decides anything new: it collects
what the import itself uses - the body part of every vertex (direct_import.rig_from_skeleton
on the skin's heaviest bone), the Tekken row of every vertex (rebuild.vertex_rows), the joints,
the skeleton, the materials left out and the mapping's confidence (direct_import.rig_map).

analyse(src) -> {"P", "T", "region", "row", "uncertain", "joints", "links", "bones", "regions",
"rows", "flags", "rig"}: src as direct_import.load returns it (hidden materials still in)."""
from __future__ import annotations
import numpy as np

import direct_import as DI
import model_import as MI

# region ids, names and colours (the debug view's legend)
REGIONS = [("head", "#ffd84a"), ("neck", "#ffb347"), ("torso", "#6a78ff"), ("pelvis", "#b06cff"),
           ("arm L", "#ff5a5a"), ("hand L", "#ffc0b0"), ("arm R", "#e0306a"), ("hand R", "#ff9ad0"),
           ("leg L", "#4fd06a"), ("foot L", "#b8f0a0"), ("leg R", "#1f9a8a"), ("foot R", "#90e0d8"),
           ("hair", "#a0662a"), ("accessory", "#9aa0aa"), ("excluded", "#3a3a44")]
RID = {name: k for k, (name, _) in enumerate(REGIONS)}
# Tekken rows by side as the left/right rows of model_import.PAIRS (the donor decides which pair
# member is left; the view only needs the split)
SIDE_ROWS = {prt: {"L": a, "R": b} for prt, (a, b) in MI.PAIRS.items()}
# the joints rig_from_skeleton gives and how they connect (the rig view's skeleton)
LINKS = [("hips", "neck"), ("neck", "top"), ("neck", "collarL"), ("collarL", "upperL"), ("upperL", "foreL"),
         ("foreL", "handL"), ("handL", "handendL"), ("neck", "collarR"), ("collarR", "upperR"),
         ("upperR", "foreR"), ("foreR", "handR"), ("handR", "handendR"), ("hips", "thighL"),
         ("thighL", "shinL"), ("shinL", "footL"), ("footL", "toeL"), ("hips", "thighR"), ("thighR", "shinR"),
         ("shinR", "footR"), ("footR", "toeR")]
# which regions a mapping-table part stands for (rig_map -> uncertain regions)
PART_REGIONS = {"Hips": ["pelvis"], "Spine": ["torso"], "Head": ["head", "neck"]}
for _sd in "LR":
    PART_REGIONS.update({f"Collar {_sd}": [f"arm {_sd}"], f"Upper arm {_sd}": [f"arm {_sd}"],
                         f"Forearm {_sd}": [f"arm {_sd}"], f"Hand {_sd}": [f"hand {_sd}"],
                         f"Thigh {_sd}": [f"leg {_sd}"], f"Shin {_sd}": [f"leg {_sd}"], f"Foot {_sd}": [f"foot {_sd}"]})


def _bone_regions(bones) -> list:
    """The region of every bone: its body part; a bone of no part (hair, cloth, props) is hair
    when it hangs from the head, else an accessory."""
    out = []
    for b in bones:
        prt, side = MI._part(b["name"])
        nm = b["name"].split(":")[-1].lower()
        if prt == "head":
            out.append("neck" if "neck" in nm else "head")
        elif prt == "spine":
            out.append("torso")
        elif prt == "pelvis":
            out.append("pelvis")
        elif prt in ("collar", "upper", "fore"):
            out.append(f"arm {side or 'L'}")
        elif prt == "hand":
            out.append(f"hand {side or 'L'}")
        elif prt in ("thigh", "shin"):
            out.append(f"leg {side or 'L'}")
        elif prt == "foot":
            out.append(f"foot {side or 'L'}")
        else:
            out.append(None)
    for i, b in enumerate(bones):
        if out[i] is not None:
            continue
        p = b.get("parent", -1)
        while p >= 0 and MI._part(bones[p]["name"])[0] is None:
            p = bones[p].get("parent", -1)
        out[i] = "hair" if p >= 0 and MI._part(bones[p]["name"])[0] == "head" else "accessory"
    return out


def analyse(src: dict) -> dict:
    import rebuild as RB
    P = np.asarray(src["P"], float)
    T = np.asarray(src["T"])
    MAT = np.asarray(src["MAT"])
    bones = src.get("bones") or []
    region = np.full(len(T), RID["accessory"], np.uint8)
    row = np.zeros(len(T), np.uint8)
    joints, links, flags = {}, [], []
    if bones and src.get("vbone") is not None:
        breg = _bone_regions(bones)
        vb = np.asarray(src["vbone"])
        vreg = np.array([RID[breg[b]] if b >= 0 else RID["torso"] for b in vb], np.uint8)
        # a triangle takes the region most of its corners have (the first corner on a tie)
        c = vreg[T]
        region = np.where(c[:, 1] == c[:, 2], c[:, 1], c[:, 0]).astype(np.uint8)
        try:
            J0, part = DI.rig_from_skeleton(bones, vb, P)
            joints = {k: [round(float(x), 5) for x in v] for k, v in J0.items()}
            links = [[a, b] for a, b in LINKS if a in joints and b in joints]
            rows_of = lambda prt, sd: SIDE_ROWS[prt][sd or "L"]
            if src.get("weights"):
                vr = RB.vertex_rows(src, part, rows_of)
                cr = vr[T]
                row = np.where(cr[:, 1] == cr[:, 2], cr[:, 1], cr[:, 0]).astype(np.uint8)
        except ValueError as error:                       # bones Tekken needs are missing
            flags.append(str(error))
    hidden = list(src.get("hidden_materials") or [])
    if hidden:
        region[np.isin(MAT, hidden)] = RID["excluded"]
        row[np.isin(MAT, hidden)] = 0
    rmap = DI.rig_map(src) if bones else []
    unsure = {rg for r in rmap if r["confidence"] == "low" for rg in PART_REGIONS.get(r["part"], [])}
    uncertain = np.isin(region, [RID[r] for r in unsure])
    for r in rmap:
        if r["confidence"] == "low":
            flags.append(f"{r['part']}: {r['note'] or r['how']}")
    at = lambda b: [round(float(b["matrix"][k][3]), 5) for k in range(3)]
    return {"P": np.round(P, 5).tolist(), "T": T.tolist(), "region": region.tolist(), "row": row.tolist(),
            "uncertain": uncertain.astype(int).tolist(), "joints": joints, "links": links,
            "bones": [{"name": b["name"], "at": at(b), "parent": b.get("parent", -1)} for b in bones],
            "regions": [{"name": n, "colour": c} for n, c in REGIONS], "flags": flags, "rig": rmap,
            "auto_rig": bool(src.get("auto_rig")),
            "counts": {REGIONS[k][0]: int((region == k).sum()) for k in range(len(REGIONS))}}
