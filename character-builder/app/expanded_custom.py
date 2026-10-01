"""Custom fighter files for Tekken 3 Expanded's CUSTOM page.

Runs with the Expanded setup's own Python (.setup/venv), which has Pillow and
numpy, and reuses Expanded's tools: ui.py for the portrait pack and glyphs.py
for the name plate, whose letters come from the player's own Tekken 3 disc.

  expanded_custom.py install --root R --key cbdizzy --label DIZZY --portrait p.png
  expanded_custom.py remove  --root R --key cbdizzy
  expanded_custom.py list    --root R --entry "cbdizzy 7" --entry "cbzed 12"

Files go to workspace/ttt1-import/roster (copied into every build) and to
build-release/mods/ttt1 (the running game's asset folder), if present.
"""
from __future__ import annotations

import argparse, re, sys
from pathlib import Path

LIST_NAME = "customs.txt"


def prefix(key: str) -> str:
    """Expanded's file prefix for a key: 'cbdizzy' -> 'Cbdizzy-T3'."""
    return key[0].upper() + key[1:].lower() + "-T3"


def targets(root: Path) -> list[Path]:
    out = [root / "workspace/ttt1-import/roster"]
    build = root / "build-release/mods/ttt1"
    if build.parent.is_dir():
        out.append(build)
    for folder in out:
        folder.mkdir(parents=True, exist_ok=True)
    return out


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(2)


def install(root: Path, key: str, label: str, portrait_path: Path | None) -> None:
    sys.path.insert(0, str(root / "tools/ttt1"))
    sys.path.insert(0, str(root / "tools"))
    try:
        from PIL import Image, ImageOps
        import glyphs, ui, ui_art
    except ImportError as error:
        fail(f"Tekken 3 Expanded's tools could not be loaded ({error}). Run its setup once first.")

    if portrait_path:
        portrait = Image.open(portrait_path).convert("RGBA")
    else:  # no portrait yet: a plain select-screen card
        portrait = Image.new("RGBA", (168, 252))
        for y in range(252):
            shade = 18 + y * 50 // 252
            portrait.paste((shade // 2, shade // 2, shade + 30, 255), (0, y, 168, y + 1))
    if portrait.size != (168, 252):  # an older save: fill the 2:3 frame
        portrait = ImageOps.fit(portrait, (168, 252), Image.LANCZOS)
    images, _ = ui_art.t3_images(portrait)
    pack, _ = ui.pack(images)

    try:
        name, _ = glyphs.name_image(label)
    except ValueError as error:
        text = str(error)
        match = re.search(r"lettre '(.)'", text)
        if match:
            fail(f"The letter {match.group(1)} does not exist in Tekken 3's name font. Choose another name.")
        if "plus que" in text:
            fail("This name is too wide for the select screen. Choose a shorter name.")
        fail(f"The name plate could not be drawn: {text}")
    except Exception as error:  # noqa: BLE001 - disc access errors come in several types
        fail(f"The name font is read from your Tekken 3 disc in the disc folder, which could not be read ({error}).")
    px = name.tobytes()
    name_bytes = bytes(px[i] | px[i + 1] << 4 for i in range(0, len(px), 2))

    for folder in targets(root):
        (folder / f"{prefix(key)}-ui.jui").write_bytes(pack)
        (folder / f"{prefix(key)}-name.4bpp").write_bytes(name_bytes)
        (folder / f"{prefix(key)}-label.txt").write_text(label + "\n", encoding="ascii")
    print(f"OK {key}: portrait pack {len(pack)} bytes, name {name.width} px")


def remove(root: Path, key: str) -> None:
    for folder in targets(root):
        for suffix in ("-ui.jui", "-name.4bpp", "-label.txt"):
            (folder / f"{prefix(key)}{suffix}").unlink(missing_ok=True)
    print(f"OK removed {key}")


def write_list(root: Path, entries: list[str]) -> None:
    lines = []
    for entry in entries:
        key, donor = entry.split()
        if not re.fullmatch(r"cb[a-z0-9]{1,24}", key) or not 0 <= int(donor) <= 20:
            fail(f"Invalid entry: {entry}")
        lines.append(f"{key} {int(donor)}")
    for folder in targets(root):
        path = folder / LIST_NAME
        if lines:
            path.write_text("\n".join(lines) + "\n", encoding="ascii")
        else:
            path.unlink(missing_ok=True)
    print(f"OK {len(lines)} custom fighters listed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("install", "remove", "list"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--key")
    parser.add_argument("--label")
    parser.add_argument("--portrait", type=Path)
    parser.add_argument("--entry", action="append", default=[])
    args = parser.parse_args()
    if args.command in ("install", "remove") and not (args.key and re.fullmatch(r"cb[a-z0-9]{1,24}", args.key)):
        fail("Invalid fighter key.")
    if args.command == "install":
        if not args.label:
            fail("A name is needed.")
        if args.portrait and not args.portrait.is_file():
            fail("The portrait file is missing.")
        install(args.root, args.key, args.label, args.portrait)
    elif args.command == "remove":
        remove(args.root, args.key)
    else:
        write_list(args.root, args.entry)


if __name__ == "__main__":
    main()
