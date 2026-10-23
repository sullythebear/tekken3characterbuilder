"""More 3D model formats for the importer (stdlib only, for the server): a .gltf with its .bin and
images, and an .obj with its .mtl and images, become one .glb, the format the importer reads;
a .zip as models are shared online (Sketchfab, itch.io: model + textures folder) gives its model
and its images.

  to_glb(name, data, files)  -> glb bytes        files: {path in the zip or folder: bytes}
  from_zip(raw)              -> (model name, model bytes, {path: bytes} of the other files)

Textures the model names are embedded when they are among the files (matched by file name,
any folder, any case); the rest stay named, so the builder can ask for them."""
from __future__ import annotations
import base64
import io
import json
import posixpath
import struct
import zipfile
from array import array

MODELS = (".fbx", ".glb", ".vrm", ".gltf", ".obj")
IMAGES = (".png", ".jpg", ".jpeg", ".tga")
ZIP_FILES_MAX = 2000
ZIP_TOTAL_MAX = 400 * 1024 * 1024        # unpacked


def _find(files: dict, ref: str, used: set | None = None) -> bytes | None:
    """A file the model refers to: the same path, else the same file name in any folder (its key
    goes into `used`)."""
    ref = ref.replace("\\", "/")
    if ref.startswith("data:"):
        return base64.b64decode(ref.split(",", 1)[1])
    from urllib.parse import unquote
    ref = unquote(ref)
    norm = {k.replace("\\", "/").lower(): k for k in files}
    key = posixpath.normpath(ref).lstrip("./").lower()
    hit = norm.get(key) or next((k for n, k in norm.items() if posixpath.basename(n) == posixpath.basename(key)), None)
    if hit is None:
        return None
    if used is not None:
        used.add(hit)
    return files[hit]


def _mime(name: str, data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    return "image/x-tga" if name.lower().endswith(".tga") else "application/octet-stream"


def _pack(j: dict, blob: bytes) -> bytes:
    """A .glb: the JSON chunk and one binary chunk, both padded to 4 bytes."""
    text = json.dumps(j, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    blob += b"\0" * (-len(blob) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<I", len(text)) + b"JSON" + text
            + struct.pack("<I", len(blob)) + b"BIN\0" + blob)


def gltf_to_glb(data: bytes, files: dict, used: set | None = None) -> bytes:
    """A .gltf (JSON) with its buffers and images (files beside it, or data: URIs) as one .glb."""
    j = json.loads(data.decode("utf-8-sig"))
    blob = bytearray()
    starts = []
    for k, buf in enumerate(j.get("buffers", [])):
        raw = _find(files, buf["uri"], used) if "uri" in buf else b""
        if raw is None:
            raise ValueError(f"The .gltf needs {buf['uri']}, which is not among the files: upload the .zip "
                             "with all its files, or a .glb")
        blob += b"\0" * (-len(blob) % 4)
        starts.append(len(blob))
        blob += raw[:buf.get("byteLength", len(raw))]
    for v in j.get("bufferViews", []):
        v["byteOffset"] = v.get("byteOffset", 0) + starts[v.get("buffer", 0)]
        v["buffer"] = 0
    for img in j.get("images", []):
        if "uri" not in img:
            continue
        raw = _find(files, img["uri"], used)
        if raw is None:                               # stays named: the builder asks for it
            continue
        blob += b"\0" * (-len(blob) % 4)
        j.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)})
        img["bufferView"] = len(j["bufferViews"]) - 1
        img["mimeType"] = _mime(img["uri"], raw)
        img["name"] = img.get("name") or posixpath.basename(img["uri"].replace("\\", "/"))
        del img["uri"]
        blob += raw
    j["buffers"] = [{"byteLength": len(blob)}]
    return _pack(j, bytes(blob))


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _mtl(text: str) -> dict:
    """{material: {"colour": [r, g, b], "map": file name or None}} from an .mtl."""
    out, cur = {}, None
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        key = parts[0].lower()
        if key == "newmtl":
            cur = " ".join(parts[1:]) or "material"
            out[cur] = {"colour": [0.8, 0.8, 0.8], "map": None}
        elif cur is None:
            continue
        elif key == "kd" and len(parts) >= 4:
            try:
                out[cur]["colour"] = [min(1.0, max(0.0, float(x))) for x in parts[1:4]]
            except ValueError:
                pass
        elif key == "map_kd" and len(parts) >= 2:
            # options such as -s 1 1 1 come before the file name: the file is the last word(s)
            words = parts[1:]
            while len(words) > 1 and words[0].startswith("-"):
                words = words[2:] if words[0] in ("-bm", "-boost", "-mm", "-texres", "-blendu", "-blendv",
                                                   "-clamp", "-imfchan", "-type") else words[4:]
            out[cur]["map"] = " ".join(words) if words else None
    return out


def obj_to_glb(data: bytes, files: dict, used: set | None = None) -> bytes:
    """An .obj (with its .mtl and images among the files) as a .glb: one primitive per material,
    flat UVs per corner (v turned to glTF's top-down), the .mtl's colours and colour maps."""
    text = data.decode("utf-8", errors="replace")
    V, VT = [], []
    materials = {}                                    # name -> list of corner keys
    order, current, libs = [], "default", []
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "v" and len(parts) >= 4:
            V.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif key == "vt" and len(parts) >= 3:
            VT.append((float(parts[1]), float(parts[2])))
        elif key == "usemtl":
            current = " ".join(parts[1:]) or "default"
        elif key == "mtllib":
            libs.append(" ".join(parts[1:]))
        elif key == "f" and len(parts) >= 4:
            corners = []
            for word in parts[1:]:
                ids = word.split("/")
                vi = int(ids[0])
                ti = int(ids[1]) if len(ids) > 1 and ids[1] else 0
                vi = vi - 1 if vi > 0 else len(V) + vi
                ti = (ti - 1 if ti > 0 else len(VT) + ti) if ti else -1
                corners.append((vi, ti))
            if current not in materials:
                materials[current] = []
                order.append(current)
            for k in range(1, len(corners) - 1):      # a polygon as a fan of triangles
                materials[current] += [corners[0], corners[k], corners[k + 1]]
    if not V or not any(materials.values()):
        raise ValueError("The .obj has no faces.")
    mtl = {}
    for lib in libs:
        raw = _find(files, lib, used)
        if raw:
            mtl.update(_mtl(raw.decode("utf-8", errors="replace")))
    if not libs:                                      # no mtllib line: any .mtl among the files
        for name, raw in files.items():
            if name.lower().endswith(".mtl"):
                mtl.update(_mtl(raw.decode("utf-8", errors="replace")))
    blob = bytearray()
    views, accessors, prims, mats, images, textures = [], [], [], [], [], []

    def add_view(raw: bytes, target=None) -> int:
        nonlocal blob
        blob += b"\0" * (-len(blob) % 4)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)}
        if target:
            v["target"] = target
        blob += raw
        views.append(v)
        return len(views) - 1

    for name in order:
        corners = materials[name]
        if not corners:
            continue
        index, pos, uv, idx = {}, array("f"), array("f"), array("I")
        for c in corners:
            if c not in index:
                index[c] = len(index)
                pos.extend(V[c[0]])
                if c[1] >= 0:
                    u, v = VT[c[1]]
                    uv.extend((u, 1.0 - v))
                else:
                    uv.extend((0.0, 0.0))
            idx.append(index[c])
        n = len(index)
        lo = [min(pos[k::3]) for k in range(3)]
        hi = [max(pos[k::3]) for k in range(3)]
        accessors.append({"bufferView": add_view(pos.tobytes(), 34962), "componentType": 5126, "count": n,
                          "type": "VEC3", "min": lo, "max": hi})
        accessors.append({"bufferView": add_view(uv.tobytes(), 34962), "componentType": 5126, "count": n,
                          "type": "VEC2"})
        accessors.append({"bufferView": add_view(idx.tobytes(), 34963), "componentType": 5125, "count": len(idx),
                          "type": "SCALAR"})
        m = mtl.get(name, {"colour": [0.8, 0.8, 0.8], "map": None})
        pbr = {"baseColorFactor": [_srgb_to_linear(c) for c in m["colour"]] + [1.0], "metallicFactor": 0.0}
        if m["map"]:
            raw = _find(files, m["map"], used)
            image = {"name": posixpath.basename(m["map"].replace("\\", "/"))}
            if raw is not None:
                image.update({"bufferView": add_view(raw), "mimeType": _mime(m["map"], raw)})
            else:
                image["uri"] = m["map"]               # stays named: the builder asks for it
            images.append(image)
            textures.append({"source": len(images) - 1})
            pbr["baseColorTexture"] = {"index": len(textures) - 1}
            pbr["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]
        mats.append({"name": name, "pbrMetallicRoughness": pbr})
        prims.append({"attributes": {"POSITION": len(accessors) - 3, "TEXCOORD_0": len(accessors) - 2},
                      "indices": len(accessors) - 1, "material": len(mats) - 1})
    j = {"asset": {"version": "2.0", "generator": "Dizzy Character Creator (from .obj)"},
         "buffers": [{"byteLength": 0}], "bufferViews": views, "accessors": accessors,
         "meshes": [{"primitives": prims}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
         "materials": mats}
    if images:
        j["images"], j["textures"] = images, textures
    j["buffers"][0]["byteLength"] = len(blob) + (-len(blob) % 4)
    return _pack(j, bytes(blob))


def to_glb(name: str, data: bytes, files: dict | None = None, used: set | None = None) -> bytes:
    """A .gltf or .obj (with the files beside it) as .glb bytes; the files it took go into `used`."""
    ext = posixpath.splitext(name.lower())[1]
    if ext == ".gltf":
        return gltf_to_glb(data, files or {}, used)
    if ext == ".obj":
        return obj_to_glb(data, files or {}, used)
    raise ValueError(f"{name}: not a .gltf or .obj")


def from_zip(raw: bytes) -> tuple[str, bytes, dict]:
    """The model in a .zip (the biggest .fbx/.glb/.vrm/.gltf/.obj; a rigged format before .obj)
    and the other files, read safely (no paths outside, size and count limited)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("This is not a valid .zip file.") from None
    files, total = {}, 0
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > ZIP_FILES_MAX:
            raise ValueError("The .zip holds too many files.")
        for i in infos:
            name = i.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or name.startswith("__MACOSX/"):
                continue
            total += i.file_size
            if total > ZIP_TOTAL_MAX:
                raise ValueError("The .zip is too large unpacked.")
            files[name] = z.read(i)
    rank = {".fbx": 0, ".glb": 0, ".vrm": 0, ".gltf": 1, ".obj": 2}
    models = [n for n in files if posixpath.splitext(n.lower())[1] in MODELS]
    if not models:
        raise ValueError("No 3D model (.fbx, .glb, .vrm, .gltf or .obj) in the .zip.")
    model = min(models, key=lambda n: (rank[posixpath.splitext(n.lower())[1]], -len(files[n])))
    data = files.pop(model)
    return model, data, files
