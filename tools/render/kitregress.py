"""Regression of the Character Builder (kitbash): a fixed set of mixes, built as the app does and
compared with their approved results (character-builder/cache/kitregress/<name>/, game data,
never committed). --approve stores the new results. Exit code 1 when a mix that built before no
longer builds.

    python tools/t3cb.py kitregress [--approve]

The mixes cover the paths that matter: a plain style model, a whole skin, KITTEST's mix with its
shape and colours, a mix that needs areas at half size, the heavy mix near the packet limit and a
mix that needs coarser normals."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GAME = Path(sys.argv[sys.argv.index("--game") + 1]) if "--game" in sys.argv else \
    Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
sys.path.insert(0, str(REPO / "character-builder" / "app"))

MIXES = {
    "nina-plain": (10, {}, None, None),
    "xiaoyu-skin-on-nina": (10, {"head": 14, "body": 14, "arm_l": 14, "arm_r": 14, "leg_l": 14, "leg_r": 14}, None, None),
    "kittest": (10, {"head": 20, "hands": 4}, (-60.0, 100.0, 0.0, True), {"head": 1.25, "arms": 1.25, "body": 1.2}),
    "law-body-on-nina": (10, {"body": 2}, None, None),           # areas at half size
    "heavy-model3-on-nina": (10, {"head": 3, "arm_l": 3, "arm_r": 3}, None, None),   # 32464 packet bytes
    "head13-on-model7": (7, {"head": 13}, None, None),           # coarser normals for the slot
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=Path, default=GAME)
    ap.add_argument("--approve", action="store_true")
    a = ap.parse_args()
    import model_export as X
    import kitbash as K
    import model_import as MI
    X.setup(a.game)
    out_root = a.game / "character-builder" / "cache" / "kitregress"
    worse = False
    print(f"{'mix':22} {'bytes':>6} {'tris':>5} {'packets':>7} half normals same  time")
    for name, (base, parts, tint, shape) in MIXES.items():
        out = out_root / name
        out.mkdir(parents=True, exist_ok=True)
        old = json.loads((out / "approved.json").read_text()) if (out / "approved.json").is_file() else None
        lines = []
        t = time.time()
        try:
            _, data, _, report = K.build(a.game, base, parts, log=lines.append, tint=tint, shape=shape)
        except MI.Budget as error:
            print(f"{name:22} FAILS: {error}" + ("  WORSE (built before)" if old and old.get("built") else ""))
            worse |= bool(old and old.get("built"))
            continue
        res = {"built": True, "bytes": len(data), "triangles": report["triangles"],
               "packets": report.get("packet_bytes"), "half": any("half size" in l for l in lines),
               "normals": report.get("normal_steps", 8), "sha": hashlib.sha256(data).hexdigest()}
        same = bool(old) and old.get("sha") == res["sha"]
        print(f"{name:22} {res['bytes']:>6} {res['triangles']:>5} {res['packets']:>7} {str(res['half']):>5} "
              f"{res['normals']:>7} {str(same):>5} {time.time() - t:4.0f} s" + ("" if old else "  (no approved state yet)"))
        if a.approve:
            (out / "approved.json").write_text(json.dumps(res))
    sys.exit(1 if worse else 0)


if __name__ == "__main__":
    main()
