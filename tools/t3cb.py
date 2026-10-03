#!/usr/bin/env python3
"""Helper commands for developing the builder against a test copy of the game. Short output:
results only. Stdlib only (the import command runs Expanded's venv itself).

  python tools/t3cb.py deploy   [--game G]            copy the builder from the repo (keeps characters, logs, cache)
  python tools/t3cb.py patch    [--game G]            install the patch, prove uninstall restores the originals byte for byte, reinstall
  python tools/t3cb.py build    [--game G]            build the game, print only the outcome
  python tools/t3cb.py report   [--game G]            summarise logs/test-report.md in a few lines
  python tools/t3cb.py import   FBX|GLB --character ID --model N [--game G]  rigged model -> model.bin (deployed)
  python tools/t3cb.py setmodel FILE --character ID [--game G]            put a T3CM model file on a character

The default game folder is the user's Expanded test copy (never the working install)."""
from __future__ import annotations
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILDER = REPO / "character-builder"
DEFAULT_GAME = Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
KEEP = {"characters", "logs", "cache"}           # the test folder's own data
FOLDERS = ("workspace/ttt1-import/roster", "build-release/mods/ttt1")


def deploy(game: Path) -> None:
    target = game / "character-builder"
    changed = 0
    for src in BUILDER.rglob("*"):
        rel = src.relative_to(BUILDER)
        if rel.parts[0] in KEEP or "__pycache__" in rel.parts or src.is_dir():
            continue
        dst = target / rel
        if dst.is_file() and dst.read_bytes() == src.read_bytes():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        changed += 1
    print(f"deploy: {changed} file(s) updated in {target}")


def patch(game: Path) -> None:
    sys.path.insert(0, str(game / "character-builder" / "app"))
    import creator_patch as cp
    kind = cp.project_kind(game)
    names = list(cp.PROFILES[kind]["edits"])
    cp.install(game, kind)
    originals = {}
    for n in names:
        backup = game / (n + cp.BACKUP_SUFFIXES[0])
        originals[n] = backup.read_bytes() if backup.is_file() else None
    cp.uninstall(game, kind)
    same = sum(1 for n in names if originals[n] is not None and (game / n).read_bytes() == originals[n])
    cp.install(game, kind)
    st = cp.status(game, kind)
    rev = cp.PROFILES[kind].get("revision", "")
    print(f"patch {rev}: installed={st['installed']}, uninstall restores {same}/{len(names)} files byte for byte"
          + ("" if st["problem"] is None else f", problem: {st['problem']}"))


def build(game: Path) -> None:
    tools = sorted((game / ".setup" / "tools").glob("toolchain-*"))
    env = dict(os.environ)
    if tools:
        env["PATH"] = str(tools[0] / "bin") + os.pathsep + env["PATH"]
    cmake = shutil.which("cmake", path=env["PATH"]) or "cmake"
    r = subprocess.run([cmake, "--build", "build-release", "--target", "psx-runtime"], cwd=game, env=env,
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).splitlines()
    if r.returncode == 0:
        steps = [l for l in out if l.startswith("[")]
        print(f"build OK ({len(steps)} step(s){', ' + steps[-1].split(']', 1)[1].strip()[:60] if steps else ''})")
    else:
        errs = [l for l in out if re.search(r"error|failed", l, re.I)][:12]
        print(f"build FAILED (exit {r.returncode})")
        print("\n".join(errs))


def report(game: Path) -> None:
    p = game / "character-builder" / "logs" / "test-report.md"
    text = p.read_text(encoding="utf-8", errors="replace")
    head = [l[2:] for l in text.splitlines() if l.startswith("- ") and ":" in l][:6]
    print(" | ".join(h for h in head if not h.startswith("Builder") and not h.startswith("Game folder")))
    lines = text.splitlines()
    want = ("installed at", "texture uploaded", "has its own model", "damaged", "not used", "fights as",
            "guest is now", "own model needs")
    seen = set()
    for l in lines:
        if any(w in l for w in want) and l not in seen:
            seen.add(l)
            print("  " + l.strip()[:150])
    checks = [l for l in lines if "model check" in l]
    if checks:
        print(f"  model checks: {len(checks)}, last: {checks[-1].split('model check: ')[-1][:100]}")
    noise = sum(1 for l in lines if "is not P" in l)
    if noise:
        print(f"  ({noise} 'not P1/P2' lines: the other player uses the donor model)")
    m = re.search(r"## Errors \((\d+)\)", text)
    print(f"  errors: {m.group(1) if m else '?'}")


def prefix(character: str) -> str:
    key = "cb" + re.sub(r"[^a-z0-9]", "", character.lower())[:24]
    return key[0].upper() + key[1:] + "-T3"


def setmodel(game: Path, file: Path, character: str) -> None:
    data = file.read_bytes()
    if data[:4] != b"T3CM":
        sys.exit("not a T3CM model file")
    places = [game / "character-builder" / "characters" / character / "model.bin"]
    places += [game / f / f"{prefix(character)}-model.bin" for f in FOLDERS]
    for p in places:
        if p.parent.is_dir():
            p.write_bytes(data)
    print(f"setmodel: {len(data)} bytes on {character} ({prefix(character)}-model.bin)")


def import_fbx(game: Path, fbx: Path, character: str, model: int) -> None:
    py = game / ".setup" / "venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = game / ".setup" / "venv" / "bin" / "python"
    out = game / "character-builder" / "cache" / f"import-{character}.bin"
    # the builder's 3D model page runs the same tool (rigged .fbx/.glb over a donor model)
    r = subprocess.run([str(py), "direct_import.py", str(fbx),
                        "--model", str(model), "--root", str(game), "--out", str(out)],
                       capture_output=True, text=True, cwd=str(game / "character-builder" / "app"))
    lines = [l for l in (r.stdout + r.stderr).splitlines() if not l.startswith("{")]
    print("\n".join(lines[-6:]))
    if r.returncode == 0:
        setmodel(game, out, character)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("deploy", "patch", "build", "report", "import", "setmodel"))
    ap.add_argument("file", nargs="?", type=Path)
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--character")
    ap.add_argument("--model", type=int)
    a = ap.parse_args()
    if a.command == "deploy":
        deploy(a.game)
    elif a.command == "patch":
        patch(a.game)
    elif a.command == "build":
        build(a.game)
    elif a.command == "report":
        report(a.game)
    elif a.command == "setmodel":
        setmodel(a.game, a.file, a.character)
    elif a.command == "import":
        import_fbx(a.game, a.file, a.character, a.model)


if __name__ == "__main__":
    main()
