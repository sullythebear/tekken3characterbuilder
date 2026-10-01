"""Binary FBX reader (stdlib only): the node tree, plus meshes, skeleton, skin weights and
textures of a character model. FBX 7.x binary; versions >= 7500 use 64-bit node headers."""
from __future__ import annotations
import struct
import zlib
from pathlib import Path

MAGIC = b"Kaydara FBX Binary  \x00"


class FbxError(Exception):
    pass


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: list, children: list):
        self.name, self.props, self.children = name, props, children

    def find(self, name: str):
        return next((c for c in self.children if c.name == name), None)

    def all(self, name: str):
        return [c for c in self.children if c.name == name]

    def value(self, name: str, default=None):
        c = self.find(name)
        return c.props[0] if c and c.props else default

    def __repr__(self):
        return f"Node({self.name}, {len(self.props)} props, {len(self.children)} children)"


ARRAY = {"f": ("f", 4), "d": ("d", 8), "l": ("q", 8), "i": ("i", 4), "b": ("b", 1)}


def _prop(data: bytes, at: int):
    t = chr(data[at]); at += 1
    if t == "Y": return struct.unpack_from("<h", data, at)[0], at + 2
    if t == "C": return bool(data[at]), at + 1
    if t == "I": return struct.unpack_from("<i", data, at)[0], at + 4
    if t == "F": return struct.unpack_from("<f", data, at)[0], at + 4
    if t == "D": return struct.unpack_from("<d", data, at)[0], at + 8
    if t == "L": return struct.unpack_from("<q", data, at)[0], at + 8
    if t in "SR":
        n = struct.unpack_from("<I", data, at)[0]; raw = data[at + 4:at + 4 + n]
        return (raw.decode("utf-8", "replace") if t == "S" else raw), at + 4 + n
    if t in ARRAY:
        count, enc, size = struct.unpack_from("<III", data, at); at += 12
        raw = data[at:at + size]
        if enc == 1:
            raw = zlib.decompress(raw)
        code, width = ARRAY[t]
        return list(struct.unpack(f"<{count}{code}", raw[:count * width])), at + size
    raise FbxError(f"Unknown property type {t!r} at {at - 1}.")


def _node(data: bytes, at: int, wide: bool):
    if wide:
        end, nprops, plen = struct.unpack_from("<QQQ", data, at); at += 24
    else:
        end, nprops, plen = struct.unpack_from("<III", data, at); at += 12
    nlen = data[at]; at += 1
    if end == 0:
        return None, at + nlen
    name = data[at:at + nlen].decode("ascii", "replace"); at += nlen
    props = []
    for _ in range(nprops):
        v, at = _prop(data, at)
        props.append(v)
    children = []
    while at < end:                       # children end with a null record
        child, at = _node(data, at, wide)
        if child is None:
            break
        children.append(child)
    return Node(name, props, children), end


def read(path: Path) -> Node:
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise FbxError("Only binary FBX files are supported (export as binary FBX).")
    version = struct.unpack_from("<I", data, 23)[0]
    wide = version >= 7500
    at, top = 27, []
    while at < len(data):
        node, at = _node(data, at, wide)
        if node is None:
            break
        top.append(node)
    root = Node("", [version], top)
    return root


def _props70(node: Node) -> dict:
    out = {}
    p = node.find("Properties70")
    for c in (p.children if p else []):
        out[c.props[0]] = c.props[4:] if len(c.props) > 4 else []
    return out


def scene(path: Path) -> dict:
    """Objects (id -> node), connections (child -> [(parent, kind, property)]) and settings."""
    root = read(path)
    objects = {}
    for n in (root.find("Objects").children if root.find("Objects") else []):
        objects[n.props[0]] = n
    parents, children = {}, {}
    for c in (root.find("Connections").children if root.find("Connections") else []):
        kind, a, b = c.props[0], c.props[1], c.props[2]
        prop = c.props[3] if len(c.props) > 3 else None
        parents.setdefault(a, []).append((b, kind, prop))
        children.setdefault(b, []).append((a, kind, prop))
    settings = _props70(root.find("GlobalSettings")) if root.find("GlobalSettings") else {}
    return {"root": root, "version": root.props[0], "objects": objects, "parents": parents,
            "children": children, "settings": settings}


def object_name(n: Node) -> str:
    return n.props[1].split("\x00\x01")[0] if len(n.props) > 1 and isinstance(n.props[1], str) else ""


def summary(path: Path) -> dict:
    s = scene(path)
    objs = s["objects"]
    kinds = {}
    for n in objs.values():
        key = n.name + ("/" + n.props[2] if len(n.props) > 2 and isinstance(n.props[2], str) else "")
        kinds[key] = kinds.get(key, 0) + 1
    meshes = []
    for i, n in objs.items():
        if n.name == "Geometry" and n.find("Vertices"):
            verts = len(n.find("Vertices").props[0]) // 3
            idx = n.find("PolygonVertexIndex").props[0]
            polys = sum(1 for v in idx if v < 0)
            tris = 0; k = 0
            for v in idx:
                k += 1
                if v < 0:
                    tris += k - 2; k = 0
            meshes.append({"id": i, "name": object_name(n), "vertices": verts, "polygons": polys, "triangles": tris,
                           "layers": [c.name for c in n.children if c.name.startswith("Layer")]})
    bones = [object_name(n) for n in objs.values() if n.name == "Model" and len(n.props) > 2 and n.props[2] == "LimbNode"]
    textures = [(object_name(n), n.value("RelativeFilename") or n.value("FileName")) for n in objs.values() if n.name == "Texture"]
    videos = [(object_name(n), len(n.value("Content") or b"")) for n in objs.values() if n.name == "Video"]
    return {"version": s["version"], "kinds": kinds, "meshes": meshes, "bones": bones,
            "textures": textures, "embedded": videos,
            "unit": s["settings"].get("UnitScaleFactor"), "up": s["settings"].get("UpAxis")}


def _matrix(values) -> list[list[float]]:
    """FBX stores 4x4 matrices with the translation in the last four values (row vectors);
    returned as rows of a column-vector matrix (translation in the last column)."""
    v = list(values)
    return [[v[c * 4 + r] for c in range(4)] for r in range(4)]


def _apply(m, p):
    return [m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3)]


def _layer(geo: Node, name: str, data: str, index: str):
    el = geo.find(name)
    if not el:
        return None
    return {"mapping": el.value("MappingInformationType", ""), "reference": el.value("ReferenceInformationType", ""),
            "data": el.value(data) or [], "index": el.value(index) or []}


def character(path: Path) -> dict:
    """The (first) skinned mesh in its bind pose, in the file's units and axes:
    positions (flat xyz), triangles (vertex indices), corner_uvs (per triangle corner),
    materials (per triangle), bones [{name, parent, matrix (bind, global)}], weights
    [{bone index: weight}] per vertex, textures {material index: (name, PNG/JPG bytes)}."""
    s = scene(path)
    objs, parents, children = s["objects"], s["parents"], s["children"]
    geo = next((n for n in objs.values() if n.name == "Geometry" and n.find("Vertices")), None)
    if geo is None:
        raise FbxError("The FBX file holds no mesh.")
    gid = geo.props[0]
    raw = geo.value("Vertices")
    idx = geo.value("PolygonVertexIndex")
    uv = _layer(geo, "LayerElementUV", "UV", "UVIndex")
    mat = _layer(geo, "LayerElementMaterial", "Materials", "")

    # skin: Geometry <- Deformer/Skin <- Deformer/Cluster <- Model/LimbNode
    clusters = []
    for skin_id, kind, _ in children.get(gid, []):
        skin = objs.get(skin_id)
        if skin is None or skin.name != "Deformer":
            continue
        for cid, _, _ in children.get(skin_id, []):
            c = objs.get(cid)
            if c is not None and c.name == "Deformer":
                bone = next((b for b, _, _ in children.get(cid, []) if b in objs and objs[b].name == "Model"), None)
                clusters.append((c, bone))
    # Cluster Transform is the bind offset (bone bind inverse x mesh); TransformLink is the bone's
    # bind matrix, so TransformLink x Transform is the mesh's matrix at bind time.
    mesh_matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    if clusters and clusters[0][0].value("TransformLink"):
        a, b = _matrix(clusters[0][0].value("TransformLink")), _matrix(clusters[0][0].value("Transform"))
        mesh_matrix = [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
    positions = []
    for i in range(0, len(raw), 3):
        positions += _apply(mesh_matrix, raw[i:i + 3])

    # bones: every LimbNode, parent = the Model it is connected to
    limb = {i: n for i, n in objs.items() if n.name == "Model" and len(n.props) > 2 and n.props[2] in ("LimbNode", "Root", "Null")}
    bind = {bone: _matrix(c.value("TransformLink")) for c, bone in clusters if bone is not None and c.value("TransformLink")}
    for pose in (n for n in objs.values() if n.name == "Pose"):
        for pn in pose.all("PoseNode"):
            node = pn.value("Node")
            if node in limb and node not in bind:
                bind[node] = _matrix(pn.find("Matrix").props[0])
    ids = [i for i in limb if i in bind]
    order = {i: k for k, i in enumerate(ids)}
    bones = []
    for i in ids:
        parent = next((p for p, _, _ in parents.get(i, []) if p in order), None)
        bones.append({"name": object_name(limb[i]).replace("mixamorig:", ""), "parent": order.get(parent, -1), "matrix": bind[i]})
    weights = [dict() for _ in range(len(raw) // 3)]
    for c, bone in clusters:
        if bone not in order:
            continue
        for v, w in zip(c.value("Indexes") or [], c.value("Weights") or []):
            if w > 0:
                weights[v][order[bone]] = weights[v].get(order[bone], 0) + w

    triangles, corner_uvs, materials = [], [], []
    poly, corner, pcount = [], 0, 0
    for k, v in enumerate(idx):
        poly.append((v if v >= 0 else ~v, k))
        if v < 0:
            m = 0
            if mat and mat["data"]:
                m = mat["data"][0] if mat["mapping"] == "AllSame" else mat["data"][pcount]
            for j in range(1, len(poly) - 1):
                tri = (poly[0], poly[j], poly[j + 1])
                triangles += [t[0] for t in tri]
                for vert, corner_at in tri:
                    if uv and uv["data"]:
                        u_at = uv["index"][corner_at] if uv["reference"] == "IndexToDirect" else corner_at
                        if uv["mapping"] == "ByControlPoint":
                            u_at = uv["index"][vert] if uv["reference"] == "IndexToDirect" else vert
                        corner_uvs += uv["data"][2 * u_at:2 * u_at + 2]
                    else:
                        corner_uvs += [0.0, 0.0]
                materials.append(m)
            poly = []; pcount += 1

    # textures: Model(mesh) <- Material <- Texture (DiffuseColor) <- Video (Content)
    mesh_model = next((p for p, _, _ in parents.get(gid, []) if p in objs and objs[p].name == "Model"), None)
    mats = [m for m, _, _ in children.get(mesh_model, []) if m in objs and objs[m].name == "Material"]
    textures = {}
    for k, mid in enumerate(mats):
        for tid, kind, prop in children.get(mid, []):
            if objs.get(tid) is None or objs[tid].name != "Texture" or (prop and "Diffuse" not in prop):
                continue
            for vid, _, _ in children.get(tid, []):
                content = objs.get(vid).value("Content") if objs.get(vid) is not None else None
                if content:
                    textures[k] = (object_name(objs[tid]), content)
    return {"positions": positions, "triangles": triangles, "corner_uvs": corner_uvs, "materials": materials,
            "material_names": [object_name(objs[m]) for m in mats], "bones": bones, "weights": weights,
            "textures": textures, "up": s["settings"].get("UpAxis", [1])[0], "unit": s["settings"].get("UnitScaleFactor", [1.0])[0]}


if __name__ == "__main__":
    import json, sys
    print(json.dumps(summary(Path(sys.argv[1])), indent=1, default=str))
