"""Collada (.dae, 1.4 and 1.5) as a .glb (stdlib only, for the server; formats.to_glb calls it):
the scene's node tree with its transforms, meshes (triangles, polylist, polygons, tristrips,
trifans) with UVs and vertex colours, materials (diffuse colour or texture, images embedded when
they are among the files) and skins (joints, inverse bind matrices, weights; the bind shape matrix
baked into the positions, as glTF has none). A Z-up file gets a root turning it Y up. Animations
are left out."""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET
from array import array


def _strip(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _floats(text) -> list:
    return [float(x) for x in (text or "").split()]


def _ints(text) -> list:
    return [int(x) for x in (text or "").split()]


def _mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _ident():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def _rows(values):
    return [values[r * 4:r * 4 + 4] for r in range(4)]


def _node_matrix(node):
    """The node's transform elements composed in document order (row-major)."""
    M = _ident()
    for el in node:
        t = el.tag
        v = _floats(el.text)
        if t == "matrix" and len(v) == 16:
            M = _mat_mul(M, _rows(v))
        elif t == "translate" and len(v) == 3:
            M = _mat_mul(M, [[1, 0, 0, v[0]], [0, 1, 0, v[1]], [0, 0, 1, v[2]], [0, 0, 0, 1]])
        elif t == "scale" and len(v) == 3:
            M = _mat_mul(M, [[v[0], 0, 0, 0], [0, v[1], 0, 0], [0, 0, v[2], 0], [0, 0, 0, 1]])
        elif t == "rotate" and len(v) == 4:
            x, y, z, deg = v
            n = math.sqrt(x * x + y * y + z * z) or 1.0
            x, y, z = x / n, y / n, z / n
            a = math.radians(deg)
            c, s, C = math.cos(a), math.sin(a), 1 - math.cos(a)
            M = _mat_mul(M, [[c + x * x * C, x * y * C - z * s, x * z * C + y * s, 0],
                             [y * x * C + z * s, c + y * y * C, y * z * C - x * s, 0],
                             [z * x * C - y * s, z * y * C + x * s, c + z * z * C, 0], [0, 0, 0, 1]])
    return M


def _apply(M, p):
    return [M[r][0] * p[0] + M[r][1] * p[1] + M[r][2] * p[2] + M[r][3] for r in range(3)]


def _url(s):
    return (s or "").lstrip("#")


def to_glb(data: bytes, files: dict, find, pack, mime, used=None) -> bytes:
    """find(files, ref, used) -> bytes or None; pack(json, blob) -> glb; mime(name, bytes)."""
    root = _strip(ET.fromstring(data))
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}
    up = (root.findtext("asset/up_axis") or "Y_UP").strip().upper()

    def source(sid):
        """(values, stride) of a <source>, or (names, 1) for a Name/IDREF array."""
        src = by_id.get(_url(sid))
        if src is None:
            return [], 1
        acc = src.find("technique_common/accessor")
        stride = int(acc.get("stride", "1")) if acc is not None else 1
        fa = src.find("float_array")
        if fa is not None:
            return _floats(fa.text), stride
        na = src.find("Name_array") if src.find("Name_array") is not None else src.find("IDREF_array")
        if na is not None:
            return (na.text or "").split(), 1
        ia = src.find("int_array")
        return (_ints(ia.text) if ia is not None else []), stride

    # materials -> (colour, image file)
    def effect_of(material_id):
        mat = by_id.get(material_id)
        eff = by_id.get(_url(mat.find("instance_effect").get("url"))) if mat is not None and mat.find("instance_effect") is not None else None
        if eff is None:
            return [0.8, 0.8, 0.8], None
        diffuse = next((d for d in eff.iter("diffuse")), None)
        if diffuse is None:
            return [0.8, 0.8, 0.8], None
        col = diffuse.find("color")
        tex = diffuse.find("texture")
        if tex is not None:
            ref = tex.get("texture")
            params = {p.get("sid"): p for p in eff.iter("newparam")}
            image_id = ref
            if ref in params and params[ref].find("sampler2D") is not None:     # 1.4: sampler -> surface -> image
                s = params[ref].find("sampler2D")
                surf = params.get((s.findtext("source") or "").strip())
                if surf is not None and surf.find("surface") is not None:
                    image_id = (surf.find("surface").findtext("init_from") or "").strip()
                elif s.find("instance_image") is not None:                     # 1.5
                    image_id = _url(s.find("instance_image").get("url"))
            img = by_id.get(image_id)
            if img is not None:
                f = img.find("init_from")
                path = (f.findtext("ref") if f is not None and f.find("ref") is not None else f.text if f is not None else "") or ""
                return [1.0, 1.0, 1.0], path.strip()
        if col is not None:
            v = _floats(col.text)
            return (v[:3] if len(v) >= 3 else [0.8, 0.8, 0.8]), None
        return [0.8, 0.8, 0.8], None

    blob = bytearray()
    views, accessors, meshes, materials, images, textures, nodes, skins = [], [], [], [], [], [], [], []
    mat_index = {}

    def add_view(raw: bytes, target=None):
        nonlocal blob
        blob += b"\0" * (-len(blob) % 4)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)}
        if target:
            v["target"] = target
        blob += raw
        views.append(v)
        return len(views) - 1

    def add_acc(values, comp, count, typ, target=34962, minmax=None):
        a = {"bufferView": add_view(values.tobytes(), target), "componentType": comp, "count": count, "type": typ}
        if minmax:
            a["min"], a["max"] = minmax
        accessors.append(a)
        return len(accessors) - 1

    def material(material_id):
        key = material_id or ""
        if key in mat_index:
            return mat_index[key]
        colour, image = effect_of(material_id) if material_id else ([0.8, 0.8, 0.8], None)
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in colour]
        pbr = {"baseColorFactor": lin + [1.0], "metallicFactor": 0.0}
        if image:
            raw = find(files, image, used)
            img = {"name": image.replace("\\", "/").rsplit("/", 1)[-1]}
            if raw is not None:
                img.update({"bufferView": add_view(raw), "mimeType": mime(image, raw)})
            else:
                img["uri"] = image                    # stays named: the builder asks for it
            images.append(img)
            textures.append({"source": len(images) - 1})
            pbr["baseColorTexture"] = {"index": len(textures) - 1}
        name = by_id[material_id].get("name") if material_id in by_id else None
        materials.append({"name": name or material_id or "material", "pbrMetallicRoughness": pbr})
        mat_index[key] = len(materials) - 1
        return mat_index[key]

    def mesh_of(geometry_id, bind, skin=None):
        """A glTF mesh for a <geometry> (bind: material symbol -> material id; skin: per position
        index [(joint, weight)], bind shape matrix)."""
        geo = by_id.get(geometry_id)
        m = geo.find("mesh") if geo is not None else None
        if m is None:
            return None
        verts = m.find("vertices")
        vin = {i.get("semantic"): i.get("source") for i in (verts if verts is not None else [])}
        pos, pstride = source(vin.get("POSITION"))
        bsm = _rows(skin["bsm"]) if skin and skin.get("bsm") else None
        prims = []
        for prim in m:
            if prim.tag not in ("triangles", "polylist", "polygons", "tristrips", "trifans"):
                continue
            inputs = prim.findall("input")
            stride = max(int(i.get("offset", "0")) for i in inputs) + 1 if inputs else 1
            off = {}
            for i in inputs:
                sem = i.get("semantic")
                if sem == "TEXCOORD" and "TEXCOORD" in off and int(i.get("set", "0")) >= off["TEXCOORD"][2]:
                    continue                          # the lowest set only
                off[sem] = (int(i.get("offset", "0")), i.get("source"), int(i.get("set", "0")))
            if "VERTEX" not in off:
                continue
            uv, uvs = source(off["TEXCOORD"][1]) if "TEXCOORD" in off else ([], 2)
            if "TEXCOORD" not in off and "TEXCOORD" in vin:
                uv, uvs = source(vin["TEXCOORD"])
            col, cols = source(off["COLOR"][1]) if "COLOR" in off else ([], 3)
            if "COLOR" not in off and "COLOR" in vin:
                col, cols = source(vin["COLOR"])
            polys = []                                 # each polygon: a list of corner tuples
            plists = prim.findall("p")
            if prim.tag == "polylist":
                vc = _ints(prim.findtext("vcount"))
                p = _ints(plists[0].text) if plists else []
                at = 0
                for n in vc:
                    polys.append([p[(at + k) * stride:(at + k + 1) * stride] for k in range(n)])
                    at += n
            elif prim.tag == "triangles":
                p = _ints(plists[0].text) if plists else []
                for k in range(0, len(p) // stride - 2, 3):
                    polys.append([p[(k + j) * stride:(k + j + 1) * stride] for j in range(3)])
            else:                                      # polygons, tristrips, trifans: one <p> each
                for pl in plists:
                    p = _ints(pl.text)
                    corners = [p[k * stride:(k + 1) * stride] for k in range(len(p) // stride)]
                    if prim.tag == "tristrips":
                        for k in range(len(corners) - 2):
                            tri = corners[k:k + 3] if k % 2 == 0 else [corners[k + 1], corners[k], corners[k + 2]]
                            polys.append(tri)
                    else:
                        polys.append(corners)
            index, P, UV, C, J, W, idx = {}, array("f"), array("f"), array("f"), array("H"), array("f"), array("I")
            vo = off["VERTEX"][0]
            to = off["TEXCOORD"][0] if "TEXCOORD" in off else vo
            co = off["COLOR"][0] if "COLOR" in off else vo
            for poly in polys:
                for k in range(1, len(poly) - 1):     # a polygon as a fan of triangles
                    for c in (poly[0], poly[k], poly[k + 1]):
                        key = (c[vo], c[to] if uv else -1, c[co] if col else -1)
                        if key not in index:
                            index[key] = len(index)
                            pi = c[vo]
                            xyz = pos[pi * pstride:pi * pstride + 3]
                            P.extend(_apply(bsm, xyz) if bsm else xyz)
                            if uv:
                                u = uv[key[1] * uvs:key[1] * uvs + 2]
                                UV.extend((u[0], 1.0 - u[1]))
                            else:
                                UV.extend((0.0, 0.0))
                            if col:
                                rgb = col[key[2] * cols:key[2] * cols + 3]
                                C.extend(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb)
                            if skin:
                                jw = sorted(skin["weights"][pi] if pi < len(skin["weights"]) else [], key=lambda t: -t[1])[:4]
                                tot = sum(w for _, w in jw) or 1.0
                                jw += [(0, 0.0)] * (4 - len(jw))
                                J.extend(j for j, _ in jw)
                                W.extend(w / tot for _, w in jw)
                        idx.append(index[key])
            n = len(index)
            if not n:
                continue
            lo = [min(P[k::3]) for k in range(3)]
            hi = [max(P[k::3]) for k in range(3)]
            attrs = {"POSITION": add_acc(P, 5126, n, "VEC3", minmax=(lo, hi)), "TEXCOORD_0": add_acc(UV, 5126, n, "VEC2")}
            if col:
                attrs["COLOR_0"] = add_acc(C, 5126, n, "VEC3")
            if skin:
                attrs["JOINTS_0"] = add_acc(J, 5123, n, "VEC4")
                attrs["WEIGHTS_0"] = add_acc(W, 5126, n, "VEC4")
            symbol = prim.get("material")
            prims.append({"attributes": attrs, "indices": add_acc(idx, 5125, len(idx), "SCALAR", 34963),
                          "material": material(bind.get(symbol, symbol))})
        if not prims:
            return None
        meshes.append({"name": geo.get("name") or geometry_id, "primitives": prims})
        return len(meshes) - 1

    # the scene's nodes, then the skins (their joints are nodes found by sid, id or name)
    scene = by_id.get(_url(root.find("scene/instance_visual_scene").get("url"))) \
        if root.find("scene/instance_visual_scene") is not None else root.find("library_visual_scenes/visual_scene")
    if scene is None:
        raise ValueError("The .dae has no scene.")
    pending = []                                       # (glTF node, instance_controller element)
    node_of = {}

    def bind_of(inst):
        return {im.get("symbol"): _url(im.get("target")) for im in inst.iter("instance_material")}

    def walk(el):
        gi = len(nodes)
        M = _node_matrix(el)
        nodes.append({"name": el.get("name") or el.get("id") or el.get("sid") or f"node{gi}",
                      "matrix": [M[r][c] for c in range(4) for r in range(4)]})
        for key in ("sid", "id", "name"):
            if el.get(key):
                node_of.setdefault((key, el.get(key)), gi)
        kids = []
        for ig in el.findall("instance_geometry"):
            mi = mesh_of(_url(ig.get("url")), bind_of(ig))
            if mi is not None:
                kids.append({"name": f"{nodes[gi]['name']} mesh", "mesh": mi})
        for ic in el.findall("instance_controller"):
            pending.append((gi, ic))
        for ch in el.findall("node"):
            kids.append(walk(ch))
        for ref in el.findall("instance_node"):
            target = by_id.get(_url(ref.get("url")))
            if target is not None:
                kids.append(walk(target))
        child_ids = []
        for k in kids:
            if isinstance(k, dict):
                nodes.append(k)
                child_ids.append(len(nodes) - 1)
            else:
                child_ids.append(k)
        if child_ids:
            nodes[gi]["children"] = child_ids
        return gi

    roots = [walk(n) for n in scene.findall("node")]
    for gi, ic in pending:
        ctrl = by_id.get(_url(ic.get("url")))
        sk = ctrl.find("skin") if ctrl is not None else None
        if sk is None:
            continue
        jsrc = next((i.get("source") for i in sk.find("joints").findall("input") if i.get("semantic") == "JOINT"), None)
        isrc = next((i.get("source") for i in sk.find("joints").findall("input") if i.get("semantic") == "INV_BIND_MATRIX"), None)
        names, _ = source(jsrc)
        ibm, _ = source(isrc)
        vw = sk.find("vertex_weights")
        joff = woff = 0
        wsrc = None
        for i in vw.findall("input"):
            if i.get("semantic") == "JOINT":
                joff = int(i.get("offset", "0"))
            elif i.get("semantic") == "WEIGHT":
                woff, wsrc = int(i.get("offset", "0")), i.get("source")
        wvals, _ = source(wsrc)
        stride = len(vw.findall("input"))
        vc, v = _ints(vw.findtext("vcount")), _ints(vw.findtext("v"))
        weights, at = [], 0
        for n in vc:
            pairs = []
            for k in range(n):
                j, w = v[(at + k) * stride + joff], wvals[v[(at + k) * stride + woff]]
                if j >= 0 and w > 0:
                    pairs.append((j, w))
            weights.append(pairs)
            at += n
        is_idref = sk.find("joints") is not None and any(
            by_id.get(_url(i.get("source"))) is not None and by_id[_url(i.get("source"))].find("IDREF_array") is not None
            for i in sk.find("joints").findall("input"))
        joints = []
        for name in names:
            order = (("id", name), ("sid", name), ("name", name)) if is_idref else (("sid", name), ("id", name), ("name", name))
            node = next((node_of[k] for k in order if k in node_of), None)
            if node is None:
                raise ValueError(f"The skin names a joint the scene does not have: {name}")
            joints.append(node)
        # glTF matrices are column-major
        flat = array("f")
        for k in range(len(joints)):
            Mk = ibm[k * 16:k * 16 + 16]
            flat.extend(Mk[r * 4 + c] for c in range(4) for r in range(4))
        mi = mesh_of(_url(sk.get("source")), bind_of(ic), {"weights": weights, "bsm": _floats(sk.findtext("bind_shape_matrix"))})
        if mi is None:
            continue
        skins.append({"joints": joints, "inverseBindMatrices": add_acc(flat, 5126, len(joints), "MAT4", target=None)})
        nodes.append({"name": f"{nodes[gi]['name']} skin", "mesh": mi, "skin": len(skins) - 1})
        roots.append(len(nodes) - 1)                   # a skinned mesh needs no parent (glTF ignores it)
    if up == "Z_UP":                                   # turn the scene Y up: x stays, y = z, z = -y
        nodes.append({"name": "Z up to Y up", "matrix": [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1],
                      "children": [r for r in roots if "skin" not in nodes[r]]})
        roots = [len(nodes) - 1] + [r for r in roots if "skin" in nodes[r]]
    if not meshes:
        raise ValueError("The .dae has no meshes.")
    j = {"asset": {"version": "2.0", "generator": "Dizzy Character Creator (from .dae)"},
         "buffers": [{"byteLength": 0}], "bufferViews": views, "accessors": accessors, "meshes": meshes,
         "nodes": nodes, "scenes": [{"nodes": roots}], "scene": 0, "materials": materials}
    if skins:
        j["skins"] = skins
    if images:
        j["images"], j["textures"] = images, textures
    j["buffers"][0]["byteLength"] = len(blob) + (-len(blob) % 4)
    return pack(j, bytes(blob))
