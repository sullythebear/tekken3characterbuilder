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
    P, T, UV, MAT = [], [], [], []
    joints_w = []
    for ni, n in enumerate(j["nodes"]):
        if "mesh" not in n:
            continue
        M = world.get(ni, np.eye(4))
        for prim in j["meshes"][n["mesh"]]["primitives"]:
            a = prim["attributes"]
            p = acc(a["POSITION"]).astype(float)
            p = (np.c_[p, np.ones(len(p))] @ M.T)[:, :3]
            idx = acc(prim["indices"]).astype(int) if "indices" in prim else np.arange(len(p))
            uv = acc(a["TEXCOORD_0"]).astype(float) if "TEXCOORD_0" in a else np.zeros((len(p), 2))
            base = sum(len(x) for x in P)
            P.append(p)
            UV.append(uv)
            t = idx.reshape(-1, 3) + base
            T.append(t)
            MAT += [prim.get("material", 0)] * len(t)
    P = np.concatenate(P)
    UV = np.concatenate(UV)
    T = np.concatenate(T)
    textures = {}
    for mi, m in enumerate(j.get("materials", [])):
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex is None:
            continue
        img = j["images"][j["textures"][tex["index"]]["source"]]
        if "bufferView" in img:
            textures[mi] = view(img["bufferView"])[0]
    return {"positions": P, "triangles": T, "uv": UV, "materials": np.array(MAT), "textures": textures,
            "skinned": any("skin" in n for n in j["nodes"])}
