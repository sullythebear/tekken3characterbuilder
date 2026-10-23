"""glTF 2.0 binary (.glb) reader (numpy): the meshes in world space with UVs, materials and
embedded textures, and a skeleton with skin weights when the file has one."""
from __future__ import annotations
import json
import struct
from pathlib import Path
import numpy as np

COMP = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"], float).reshape(4, 4).T
    t = np.array(n.get("translation", [0, 0, 0]), float)
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = np.array(n.get("scale", [1, 1, 1]), float)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * s
    M[:3, 3] = t
    return M


def read(path: Path) -> dict:
    d = Path(path).read_bytes()
    if d[:4] != b"glTF":
        raise ValueError("Not a binary glTF (.glb) file.")
    clen = struct.unpack_from("<I", d, 12)[0]
    j = json.loads(d[20:20 + clen])
    at = 20 + clen
    blen = struct.unpack_from("<I", d, at)[0]
    bin_ = d[at + 8: at + 8 + blen]

    def view(i):
        v = j["bufferViews"][i]
        o = v.get("byteOffset", 0)
        return bin_[o:o + v["byteLength"]], v.get("byteStride")

    def acc(i):
        a = j["accessors"][i]
        raw, stride = view(a["bufferView"])
        dt = np.dtype(COMP[a["componentType"]])
        n, k = a["count"], SIZE[a["type"]]
        off = a.get("byteOffset", 0)
        if stride and stride != dt.itemsize * k:
            out = np.array([np.frombuffer(raw, dt, k, off + q * stride) for q in range(n)])
        else:
            out = np.frombuffer(raw, dt, n * k, off).reshape(n, k) if k > 1 else np.frombuffer(raw, dt, n, off)
        if a.get("normalized") and dt.kind in "iu":
            out = out / float(np.iinfo(dt).max)
        return np.array(out)

    # world matrices of the nodes
    world = {}

    def walk(i, M):
        world[i] = M @ _matrix(j["nodes"][i])
        for c in j["nodes"][i].get("children", []):
            walk(c, world[i])
    for s in j.get("scenes", [{"nodes": list(range(len(j["nodes"])))}]):
        for i in s["nodes"]:
            walk(i, np.eye(4))
    P, T, UV, MAT, COL = [], [], [], [], []
    has_col = False
    # a skin: its joints become the bones (bind matrix = inverse of the inverse bind matrix),
    # skinned meshes are already in bind space (glTF ignores their node transform)
    bones, WTS, skin_of = [], [], {}
    human = vrm_human_bones(j)                         # VRM (VRoid) files name their humanoid bones
    for si, sk in enumerate(j.get("skins", [])):
        ibm = acc(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1) if "inverseBindMatrices" in sk             else np.tile(np.eye(4), (len(sk["joints"]), 1, 1))
        base = len(bones)
        index = {nd: base + k for k, nd in enumerate(sk["joints"])}
        parent = {c: i for i, n in enumerate(j["nodes"]) for c in n.get("children", [])}
        for k, nd in enumerate(sk["joints"]):
            up = parent.get(nd)
            while up is not None and up not in index:
                up = parent.get(up)
            bones.append({"name": human.get(nd) or j["nodes"][nd].get("name", f"joint{k}"), "parent": index.get(up, -1),
                          "human": nd in human, "node": nd,
                          "matrix": np.linalg.inv(ibm[k]).tolist()})
        skin_of[si] = base
    # a skin's root may hang on a joint of another skin (Seed-san's backpack and robot arm are a
    # skin of their own under her chest): link it there instead of leaving it a second root
    first = {}
    for i, b in enumerate(bones):
        first.setdefault(b["node"], i)
    node_up = {c: i for i, n in enumerate(j["nodes"]) for c in n.get("children", [])}
    for b in bones:
        if b["parent"] >= 0:
            continue
        up = node_up.get(b["node"])
        while up is not None and up not in first:
            up = node_up.get(up)
        if up is not None and first[up] is not bones.index(b):
            b["parent"] = first[up]
    # a mesh without a skin under a joint node (a hat or an armour piece that hangs on a bone,
    # as KayKit's characters have) moves rigidly with that bone
    node_parent = {c: i for i, n in enumerate(j["nodes"]) for c in n.get("children", [])}
    joint_bone = {nd: skin_of[si] + k for si, sk in enumerate(j.get("skins", [])) for k, nd in enumerate(sk["joints"])}

    def holder(ni):
        up = node_parent.get(ni)
        while up is not None and up not in joint_bone:
            up = node_parent.get(up)
        return joint_bone.get(up)
    for ni, n in enumerate(j["nodes"]):
        if "mesh" not in n:
            continue
        rigid = holder(ni) if "skin" not in n else None
        if rigid is not None and "slot" in bones[rigid]["name"].lower():
            continue                                    # a held item (KayKit: every weapon on the hand slots)
        M = world.get(ni, np.eye(4)) if "skin" not in n else np.eye(4)
        for prim in j["meshes"][n["mesh"]]["primitives"]:
            a = prim["attributes"]
            p = acc(a["POSITION"]).astype(float)
            p = (np.c_[p, np.ones(len(p))] @ M.T)[:, :3]
            if "skin" in n and "JOINTS_0" in a and "WEIGHTS_0" in a:
                jt = acc(a["JOINTS_0"]).astype(int) + skin_of[n["skin"]]
                wt = acc(a["WEIGHTS_0"]).astype(float)
                WTS += [{int(b): float(w) for b, w in zip(jr, wr) if w > 0} for jr, wr in zip(jt, wt)]
            else:
                WTS += [{} if rigid is None else {rigid: 1.0} for _ in range(len(p))]
            idx = acc(prim["indices"]).astype(int) if "indices" in prim else np.arange(len(p))
            uv = acc(a["TEXCOORD_0"]).astype(float) if "TEXCOORD_0" in a else np.zeros((len(p), 2))
            # vertex colours (low-poly models without a texture): linear RGB, white where none
            col = acc(a["COLOR_0"]).astype(float)[:, :3] if "COLOR_0" in a else np.ones((len(p), 3))
            has_col = has_col or "COLOR_0" in a
            base = sum(len(x) for x in P)
            P.append(p)
            UV.append(uv)
            COL.append(col)
            t = idx.reshape(-1, 3) + base
            T.append(t)
            MAT += [prim.get("material", 0)] * len(t)
    P = np.concatenate(P)
    UV = np.concatenate(UV)
    T = np.concatenate(T)
    COL = np.concatenate(COL)
    textures, colours, names, missing = {}, {}, [], {}
    for mi, m in enumerate(j.get("materials", [])):
        names.append(m.get("name") or f"Material {mi + 1}")
        pbr = m.get("pbrMetallicRoughness", {})
        colours[mi] = [float(x) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])]   # linear RGBA
        tex = pbr.get("baseColorTexture")
        if tex is None:
            continue
        img = j["images"][j["textures"][tex["index"]]["source"]]
        if "bufferView" in img:
            textures[mi] = view(img["bufferView"])[0]
        elif img.get("uri") and not str(img["uri"]).startswith("data:"):
            missing[mi] = str(img["uri"])           # an image file beside the model, not in it
    out = {"positions": P, "triangles": T, "uv": UV, "materials": np.array(MAT), "textures": textures,
           "colours": colours, "material_names": names, "missing_textures": missing,
           "vertex_colours": COL if has_col else None,
           "skinned": any("skin" in n for n in j["nodes"])}
    if bones and any(WTS):
        out["bones"], out["weights"] = bones, WTS
    return out


# VRM's humanoid bone names -> the Mixamo-style names the importer reads (model_import._part)
VRM_NAMES = {"hips": "Hips", "spine": "Spine", "chest": "Spine1", "upperChest": "Spine2", "neck": "Neck",
             "head": "Head"}
for _s, _w in (("left", "Left"), ("right", "Right")):
    VRM_NAMES.update({f"{_s}Shoulder": f"{_w}Shoulder", f"{_s}UpperArm": f"{_w}Arm", f"{_s}LowerArm": f"{_w}ForeArm",
                      f"{_s}Hand": f"{_w}Hand", f"{_s}UpperLeg": f"{_w}UpLeg", f"{_s}LowerLeg": f"{_w}Leg",
                      f"{_s}Foot": f"{_w}Foot", f"{_s}Toes": f"{_w}ToeBase"})


def vrm_human_bones(j: dict) -> dict:
    """{node index: Mixamo-style name} from a VRM file's humanoid table (VRM 1.0 VRMC_vrm or 0.x VRM)."""
    ext = j.get("extensions", {})
    out = {}
    hb = ext.get("VRMC_vrm", {}).get("humanoid", {}).get("humanBones", {})
    if isinstance(hb, dict):
        for bone, v in hb.items():
            if bone in VRM_NAMES and isinstance(v, dict) and "node" in v:
                out[int(v["node"])] = VRM_NAMES[bone]
    for v in ext.get("VRM", {}).get("humanoid", {}).get("humanBones", []) or []:
        if isinstance(v, dict) and v.get("bone") in VRM_NAMES and "node" in v:
            out[int(v["node"])] = VRM_NAMES[v["bone"]]
    return out
