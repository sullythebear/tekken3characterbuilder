"""Regression check of the model import (Expanded's venv): every character in the test folder
that has its own model and a source file is imported again, then checked the PlayStation way.

  regress.py [--game G] [--only id,id] [--approve] [--all] [--unrigged]

--all also imports the rigged files in <game>/character-builder/testmodels/ (over Nina's model
10; ids tm-<name>; locked files are listed and skipped): Michelle/Soldier/Xbot (Mixamo glb),
CesiumMan (shape-named bones), ...
--unrigged imports every test model again as if its file had no skeleton (ids ur-<name>): the
automatic rig (autorig.py), turning it upright, chibi legs and the build in one go.

Per character:
  fits     the import fitted without the flat-shading fallback (degrade)
  holes    pixels the PS1's culling opens up (background with culling, body without) in renders
           of the bind pose from 4 sides
  speckle  texels whose decoded colour (the polygon's own CLUT, as the GPU reads it) is more than
           20 Lab units from the texture the importer quantised: wrong-hue speckles
  same     the new model.bin equals the approved one byte for byte

The approved state lives in <game>/character-builder/cache/regress/<id>/ (approved.bin,
approved.json); --approve stores the new results as approved. Without an approved state the
character's current model.bin is the reference for `same`. Exit code 1 when a check got worse.
Sheets (new | approved renders) go to cache/regress/<id>/sheet.png."""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
GAME = Path(sys.argv[sys.argv.index("--game") + 1]) if "--game" in sys.argv else \
    Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
sys.path[:0] = [str(GAME / "character-builder" / "app"), str(HERE)]
import model_export as X  # noqa: E402
X.setup(GAME)
import direct_import as DI  # noqa: E402
import texture_bake as TB  # noqa: E402
from PIL import Image  # noqa: E402

SPECKLE_DE = 20.0      # Lab distance of a wrong texel
HOLE_SLACK = 20        # pixels of new holes tolerated (anti-aliasing of thin slivers)
SPECKLE_SLACK = 0.002  # share of texels


def _no_skeleton(load):
    """DI._load as for a file without a skeleton (the mesh as it stands in its bind pose)."""
    def f(path, *a, **k):
        out = load(path, *a, **k)
        for key in ("bones", "weights", "vbone"):
            out.pop(key, None)
        return out
    return f


def _beside(src_file):
    """What the builder passes with a character's source.*: its texture images (textures-source.json,
    or an older single texture-source.*), colours painted and joints placed by hand."""
    folder, stem = src_file.parent, src_file.stem
    if stem != "source":
        return
    spec = folder / f"textures-{stem}.json"
    if spec.is_file():
        data = json.loads(spec.read_text(encoding="utf-8"))
        DI.set_texture_images([{"name": i["name"], "path": folder / i["file"]} for i in data.get("images", [])],
                              data.get("assign"))
    else:
        old = next((p for p in folder.glob(f"texture-{stem}.*")), None)
        if old:
            DI.set_external_texture(old)
    colours = folder / f"colours-{stem}.json"
    if colours.is_file():
        DI.set_colours(json.loads(colours.read_text(encoding="utf-8")))
    rig = folder / f"rig-{stem}.json"
    if rig.is_file():
        r = json.loads(rig.read_text(encoding="utf-8"))
        DI.set_rig(r.get("joints"), r.get("turn", "auto"), r.get("paint"))


def build(cid, info, src_file):
    """Imports src_file as the app does. -> (model bytes, reference RGB, degraded?)"""
    cap = {}
    if cid.startswith("ur-"):
        load = DI._load
        DI._load = _no_skeleton(load)
        try:
            return build("x" + cid, info, src_file)
        finally:
            DI._load = load
    quant = TB.quantise_groups

    def q(rgb, owner, *a, **k):
        cap["rgb"], cap["owner"] = rgb.copy(), owner.copy()
        return quant(rgb, owner, *a, **k)
    inner = DI._build

    def b(root, model, src, log=print, degrade=True):
        cap["degrade"] = degrade if src.get("reduced") or len(src["T"]) > DI.REDUCE_ABOVE else False
        return inner(root, model, src, log, degrade)
    TB.quantise_groups, DI._build = q, b
    _beside(Path(src_file))
    try:
        stock, new, tx, rep = DI.build(GAME, info["model"], src_file, log=lambda *a: None, parts=info.get("parts"),
                                         settings=info.get("settings"))
    finally:
        TB.quantise_groups, DI._build = quant, inner
        DI.set_texture_images([])
        DI.set_colours(None)
        DI.set_rig()
    return X.own_model_file(info["model"], stock, new, tx), cap["rgb"], cap["owner"], cap.get("degrade", False)


def speckle(path, rgb, owner):
    """Share of drawn texels decoded more than SPECKLE_DE Lab units from the reference."""
    import compare as C
    from fmt import row, block, parse_c_ps1
    m, (band, vram) = C.load(str(path))
    i4 = np.stack([(band >> (4 * k)) & 15 for k in range(4)], 2).reshape(band.shape[0], -1)
    out = np.zeros(rgb.shape, float)
    hit = np.zeros(rgb.shape[:2], bool)
    for r in range(1, 21):
        try:
            wd = row(m, r)
        except Exception:
            break
        if not wd[10] or wd[1] <= 2:
            continue
        for _, mat, uv in parse_c_ps1(block(m, wd[2])):
            if mat is None or mat & 0x8000:                # 8-bit charts: not checked here
                continue
            uv = np.array(uv, float)
            for t in ([uv[[0, 1, 2]]] if len(uv) == 3 else [uv[[0, 1, 2]], uv[[1, 3, 2]]]):
                x0, y0 = np.floor(t.min(0)).astype(int)
                x1, y1 = np.ceil(t.max(0)).astype(int)
                xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
                p = np.stack([xs.ravel() + .5, ys.ravel() + .5], 1)
                a, b, c = t
                cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                if abs(cr) < 1e-9:
                    continue
                l1 = ((b[0] - p[:, 0]) * (c[1] - p[:, 1]) - (b[1] - p[:, 1]) * (c[0] - p[:, 0])) / cr
                l2 = ((c[0] - p[:, 0]) * (a[1] - p[:, 1]) - (c[1] - p[:, 1]) * (a[0] - p[:, 0])) / cr
                qq = p[(l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)].astype(int)
                qq = qq[(qq >= 0).all(1) & (qq[:, 0] < min(i4.shape[1], rgb.shape[1])) & (qq[:, 1] < min(i4.shape[0], rgb.shape[0]))]
                cid = mat & 0x7eff
                raw = vram[cid >> 6, (cid & 63) * 16 + i4[qq[:, 1], qq[:, 0]]]
                out[qq[:, 1], qq[:, 0]] = np.stack([(raw & 31) * 8, ((raw >> 5) & 31) * 8, ((raw >> 10) & 31) * 8], 1)
                hit[qq[:, 1], qq[:, 0]] = raw != 0            # colour 0: see-through on purpose
    d = np.linalg.norm(TB.lab(out[hit]) - TB.lab(rgb[hit].astype(float)), axis=1)
    return float((d > SPECKLE_DE).mean()) if len(d) else 0.0


def holes(path, model, png):
    """Pixels the PlayStation's culling opens up: background in PS1 renders (quads culled by their
    first triangle, painter's order) of the bind pose from 4 sides, body when nothing is culled."""
    def render(out, **extra):
        env = dict(os.environ, PAINTER="16", QUADCULL="1", MAGENTA="1", **extra)
        subprocess.run([sys.executable, str(HERE / "probe_render.py"), str(GAME), str(path), str(out),
                        "--rest", "0,90,180,270", "--solved", "--donor", str(model), "--size", "600"],
                       env=env, check=True, capture_output=True)
        im = np.asarray(Image.open(out).convert("RGB")).astype(int)
        return (im[..., 0] == 255) & (im[..., 1] == 0) & (im[..., 2] == 255)
    bg = render(png)
    full = render(png.with_name("nocull.png"), NOCULL="1")
    png.with_name("nocull.png").unlink()
    return int((bg & ~full).sum())


def old_ok(out):
    """An approved state exists: the character imported before."""
    return (out / "approved.json").is_file()


def main():
    root = GAME / "character-builder"
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    approve = "--approve" in sys.argv
    worse = False
    print(f"{'character':14} {'bytes':>6} {'fits':>5} {'holes':>6} {'speckle':>8} {'same':>5}  time")
    items = []
    for d in sorted((root / "characters").iterdir()):
        cfg = d / "character.json"
        if not cfg.is_file():
            continue
        info = json.loads(cfg.read_text(encoding="utf-8")).get("own_model")
        src = next((p for p in d.glob("source.*")), None)
        if info and src:
            items.append((d.name, info, src, d / "model.bin"))
    if "--all" in sys.argv:
        tm = root / "testmodels"                         # loose files, or one download per folder
        for f in sorted([*tm.glob("*"), *tm.glob("*/*")]):
            if f.suffix.lower() not in (".glb", ".fbx", ".vrm"):
                continue
            if not DI.inspect(f)["rigged"]:
                print(f"tm-{f.stem:11} locked (not rigged as Tekken needs), skipped")
                continue
            items.append((f"tm-{f.stem}", {"model": 10}, f, None))
    if "--unrigged" in sys.argv:
        tm = root / "testmodels"
        for f in sorted([*tm.glob("*"), *tm.glob("*/*")]):
            if f.suffix.lower() in (".glb", ".fbx", ".vrm"):
                items.append((f"ur-{f.stem}", {"model": 10}, f, None))
    for name, info, src, current in items:
        if only and name not in only:
            continue
        out = root / "cache" / "regress" / name
        out.mkdir(parents=True, exist_ok=True)
        t = time.time()
        try:
            data, rgb, owner, degraded = build(name, info, src)
        except Exception as e:                           # an unrigged shape autorig cannot rig
            print(f"{name:14} NOT IMPORTED: {e}")
            worse |= bool(old_ok(out))
            continue
        (out / "new.bin").write_bytes(data)
        res = {"fits": not degraded,
               "holes": holes(out / "new.bin", info["model"], out / "new.png"),
               "speckle": round(speckle(out / "new.bin", rgb, owner), 4)}
        ref = out / "approved.bin" if (out / "approved.bin").is_file() else current
        res["same"] = bool(ref) and ref.is_file() and ref.read_bytes() == data
        old = json.loads((out / "approved.json").read_text()) if (out / "approved.json").is_file() else None
        bad = []
        if old and not res["same"]:
            if old["fits"] and not res["fits"]:
                bad.append("fits")
            if res["holes"] > old["holes"] + HOLE_SLACK:
                bad.append("holes")
            if res["speckle"] > old["speckle"] + SPECKLE_SLACK:
                bad.append("speckle")
        worse |= bool(bad)
        if (out / "approved.png").is_file():
            a, n = Image.open(out / "approved.png"), Image.open(out / "new.png")
            sheet = Image.new("RGB", (a.width, a.height + n.height))
            sheet.paste(n, (0, 0)); sheet.paste(a, (0, n.height))
            sheet.save(out / "sheet.png")
        print(f"{name:14} {len(data):>6} {str(res['fits']):>5} {res['holes']:>6} {res['speckle']:>8.2%} "
              f"{str(res['same']):>5}  {time.time() - t:.0f} s" + (f"  WORSE: {', '.join(bad)}" if bad else "")
              + ("" if old else "  (no approved state yet)"))
        if approve:
            (out / "approved.bin").write_bytes(data)
            (out / "approved.json").write_text(json.dumps(res))
            (out / "new.png").replace(out / "approved.png")
    sys.exit(1 if worse else 0)


if __name__ == "__main__":
    main()
