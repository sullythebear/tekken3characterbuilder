"""Benchmark of the automatic rig (Expanded's venv): every rigged test model is rigged again as if
it had no skeleton, and compared with its own.

  autorig_bench.py [--game G] [--only name] [--orient]

Per model: the joints' mean distance from the skeleton's (% of the height), the worst joint, and
the share of vertices given the skeleton's body part. At the end the mean offset per joint (to
tune autorig's proportions) and the parts most often confused. --orient also turns every model
six ways (Z up, facing -Z, upside down, ...) and checks that autorig.orient stands it up again.
Test models: <game>/character-builder/testmodels/ and the fighters' source.fbx (chibis skipped)."""
import sys
import time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
GAME = Path(sys.argv[sys.argv.index("--game") + 1]) if "--game" in sys.argv else \
    Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
ONLY = sys.argv[sys.argv.index("--only") + 1].lower() if "--only" in sys.argv else ""
sys.path[:0] = [str(HERE.parent.parent / "character-builder" / "app")]
import model_export as X  # noqa: E402
X.setup(GAME)
import direct_import as DI  # noqa: E402
import autorig as A  # noqa: E402

SKIP = ("Knight", "Mage", "Rogue", "Vladi", "CuteMoth", "BrainStem")      # chibis, no usable skeleton
JOINTS = ["hips", "neck"] + [p + s for p in ("upper", "fore", "hand", "thigh", "shin", "foot") for s in "LR"]


def files():
    out = sorted(p for p in (GAME / "character-builder" / "testmodels").rglob("*")
                 if p.suffix.lower() in (".glb", ".fbx", ".vrm"))
    out += sorted((GAME / "character-builder" / "characters").glob("*/source.fbx"))
    for f in out:
        name = f.parent.name if f.name == "source.fbx" else f.stem
        if any(s in name for s in SKIP) or (ONLY and ONLY not in name.lower()):
            continue
        yield name, f


def rot(axis, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


TURNS = {"as is": np.eye(3), "Z up": rot("x", -90), "facing -Z": rot("y", 180), "upside down": rot("x", 180),
         "lying X": rot("z", 90), "Z up back": rot("x", 90)}


def main():
    rows, off, conf, turns_ok, turns = [], {}, {}, 0, 0
    for name, f in files():
        src = DI.load(f)
        if not src.get("bones") or src.get("auto_rig"):
            continue
        P, T = src["P"], src["T"]
        H = float(np.ptp(P[:, 1]))
        try:
            Jt, pt = DI.rig_from_skeleton(src["bones"], src["vbone"], P)
        except ValueError:
            continue
        t0 = time.time()
        try:
            Ja, pa = A.auto_rig(P, T)
        except A.RigError as e:
            print(f"{name:22s} NOT RIGGED: {e}")
            rows.append(None)
            continue
        err = {k: float(np.linalg.norm(Ja[k] - Jt[k])) / H * 100 for k in JOINTS}
        for k in JOINTS:
            off.setdefault(k, []).append((Ja[k] - Jt[k]) / H * 100)
        same = lambda a, b: a == b or (a[0] in ("spine", "pelvis") and b[0] in ("spine", "pelvis"))
        acc = float(np.mean([same(a, b) for a, b in zip(pa, pt)])) * 100
        for a, b in zip(pa, pt):
            if not same(a, b):
                key = (b[0] + (b[1] or ""), a[0] + (a[1] or ""))
                conf[key] = conf.get(key, 0) + 100 / len(pa)
        worst = max(err, key=err.get)
        rows.append((float(np.mean(list(err.values()))), acc))
        line = (f"{name:22s} joints {rows[-1][0]:5.1f}%  worst {worst:7s} {err[worst]:5.1f}%  parts {acc:5.1f}%"
                f"  {time.time() - t0:4.1f}s")
        if "--orient" in sys.argv:
            wrong = []
            for tn, Q in TURNS.items():
                P2 = P @ Q.T
                P3 = P2 @ A.orient(P2, T).T
                M = np.linalg.lstsq(P - P.mean(0), P3 - P3.mean(0), rcond=None)[0]
                turns += 1
                if M[1, 1] > 0.9 and M[2, 2] > 0.9:
                    turns_ok += 1
                else:
                    wrong.append(tn)
            line += "  orient " + ("ok" if not wrong else "WRONG " + ", ".join(wrong))
        print(line, flush=True)
    good = [r for r in rows if r]
    print(f"MEAN over {len(good)}: joints {np.mean([r[0] for r in good]):.2f}%  parts {np.mean([r[1] for r in good]):.1f}%"
          f"  not rigged {len(rows) - len(good)}" + (f"  orient {turns_ok}/{turns}" if turns else ""))
    print("joint     mean|err|   mean offset x y z (% of the height)")
    for k, v in off.items():
        v = np.array(v)
        print(f"{k:8s} {np.linalg.norm(v, axis=1).mean():6.2f}   {v[:, 0].mean():6.2f} {v[:, 1].mean():6.2f} {v[:, 2].mean():6.2f}")
    print("parts most often confused (skeleton -> auto, summed % of vertices):")
    for k, v in sorted(conf.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {k[0]:8s} -> {k[1]:8s} {v:6.1f}")


if __name__ == "__main__":
    main()
