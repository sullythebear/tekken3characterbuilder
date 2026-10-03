#!/usr/bin/env python3
"""Live checks in the running game, without a player (stdlib only).

Uses Tekken 3 Expanded's debug build (build-opt-dbg: Release + PSX_DEBUG_TOOLS=ON) and its
debug server: load a save state, drive the pad, read memory, take screenshots.

  python tools/t3live.py setup [--game G]
      starts the debug build in a window with the live save folder; go to the character
      select screen, put P1's cursor on the fighter to test, press Shift+F8 (slot 7), close.
  python tools/t3live.py fight [--game G] [--frames 600] [--every 60] [--pages 2] [--cell 0] [--visible]
      boots the game, walks Title -> Arcade -> select screen -> CUSTOM page (R2 x pages) ->
      fighter at --cell, picks it (and the Tekken 3 moveset), waits for the fight, then takes
      a screenshot every N frames while pressing a few attacks; prints the paths.

Screenshots: <game>/character-builder/live/shots/. The save folder: <game>/character-builder/
live/saves (slot 7 = the select screen with the cursor on the fighter)."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_GAME = Path(r"D:\Tekken 3 Recompiled\tekken3-expanded-1.1.3")
PAD = {"none": 0xFFFF, "cross": 0xBFFF, "square": 0x7FFF, "triangle": 0xEFFF, "circle": 0xDFFF,
       "right": 0xFFDF, "left": 0xFF7F, "up": 0xFFEF, "down": 0xFFBF, "start": 0xFFF7, "r2": 0xFDFF}


class Game:
    def __init__(self, game: Path, visible: bool):
        self.root = game
        self.live = game / "character-builder" / "live"
        self.saves = self.live / "saves"
        self.saves.mkdir(parents=True, exist_ok=True)
        run = self.live / "run"
        if run.exists():
            shutil.rmtree(run, ignore_errors=True)
        run.mkdir(parents=True, exist_ok=True)
        dbg = game / "build-opt-dbg"
        rel = game / "build-release"
        shutil.copy2(dbg / "Tekken_3_Recompiled.exe", run / "Tekken_3_Recompiled.exe")
        for name in ("bios", "mods"):                      # mods with the builder's custom files
            shutil.copytree(rel / name, run / name, dirs_exist_ok=True)
        for name in ("keybinds.ini", "input.ini", "bios.cfg", "disc.cfg"):
            if (rel / name).is_file():
                shutil.copy2(rel / name, run / name)
        (run / "settings.toml").write_text('[video]\nrenderer="opengl"\nsupersampling=2\n'
                                           '[controller]\np1_device="keyboard"\np2_device="none"\n')
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        args = [str(run / "Tekken_3_Recompiled.exe"), "--game", str(game / "game.toml"),
                "--disc", str(game / "disc" / "Tekken 3 (USA).cue"), "--no-launcher",
                "--debug-port", str(self.port), "--memcard-dir", str(self.saves)]
        if not visible:
            args.append("--headless")
        env = {k: v for k, v in os.environ.items() if not k.startswith("TEKKEN3_")}
        env["SDL_AUDIO_DRIVER"] = "dummy" if not visible else env.get("SDL_AUDIO_DRIVER", "")
        self.log = self.live / "game-log.txt"
        self.out = self.log.open("w")
        self.proc = subprocess.Popen(args, cwd=game, stdout=self.out, stderr=self.out, env=env)
        end = time.monotonic() + 40
        while True:
            if self.proc.poll() is not None:
                raise SystemExit(f"the game exited during startup; see {self.log}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), 0.2):
                    break
            except OSError:
                if time.monotonic() > end:
                    raise SystemExit("the debug server did not start")
                time.sleep(0.2)

    def q(self, **req):
        sys.path.insert(0, str(self.root / "psxrecomp" / "tools"))
        import debug_client                                  # Expanded's client (one JSON object)
        r = debug_client.query("127.0.0.1", self.port, req)
        if r.get("ok") is False:
            raise RuntimeError((req, r))
        return r

    def word(self, addr, n=4):
        return int.from_bytes(bytes.fromhex(self.q(cmd="read_ram", addr=f"{addr:08x}", len=n)["hex"]), "little")

    def frame(self):
        return self.q(cmd="frame")["frame"]

    def press(self, name, frames=6):
        self.q(cmd="set_input", buttons=PAD[name])
        self.wait_frames(frames)
        self.q(cmd="set_input", buttons=PAD["none"])
        self.wait_frames(4)

    def wait_frames(self, n):
        end = self.frame() + n
        while self.frame() < end:
            time.sleep(0.01)

    def shot(self, path):
        self.q(cmd="screenshot", path=str(path))

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.out.close()


def setup(game: Path):
    g = Game(game, visible=True)
    print("The game is running in a window. Go to the character select screen, put P1's cursor on "
          "the fighter to test (CUSTOM page: R2), press Shift+F8, then close the game.")
    g.proc.wait()
    g.out.close()
    states = list((g.saves).rglob("*7*"))
    print("save state written" if states else "no save state found in " + str(g.saves))


def fight(game: Path, frames: int, every: int, visible: bool, pages: int = 2, cell: int = 0,
          costume_button: str = "square"):
    g = Game(game, visible)
    shots = g.live / "shots"
    shutil.rmtree(shots, ignore_errors=True)
    shots.mkdir(parents=True)
    try:
        # title -> Arcade -> character select -> CUSTOM page (R2 twice: Tag, Custom) -> the
        # first custom fighter -> moveset card (Tekken 3) -> fight
        g.wait_frames(700)
        for b, w in (("start", 200), ("start", 200)):          # title, Arcade (the default)
            g.press(b)
            g.wait_frames(w)
        for _ in range(pages):
            g.press("r2")
            g.wait_frames(60)
        for _ in range(cell):
            g.press("right")
            g.wait_frames(20)
        g.shot(shots / "select.png")
        g.press(costume_button)                     # the button picks the costume (square = 1)
        g.wait_frames(90)
        g.press(costume_button)
        end = time.monotonic() + 150
        while g.word(0x800AE204) != 8 or g.word(0x800AE224, 2) < 6:
            if time.monotonic() > end:
                g.shot(shots / "stuck.png")
                raise SystemExit("the fight did not start (see shots/stuck.png)")
            time.sleep(0.3)
        moves = ["none", "square", "none", "triangle", "none", "cross", "none", "circle", "right", "left"]
        start = g.frame()
        k = 0
        while g.frame() - start < frames:
            g.shot(shots / f"{k:02d}.png")
            k += 1
            mv = moves[k % len(moves)]
            if mv != "none":
                g.press(mv, 4)
            g.wait_frames(every)
        print(f"{k} screenshots in {shots}")
    finally:
        g.stop()
    lines = [l for l in g.log.read_text(errors="replace").splitlines() if "Custom fighters" in l]
    for l in lines[-6:]:
        print("  " + l.strip()[:150])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("setup", "fight"))
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--pages", type=int, default=2, help="R2 presses on the select screen (2 = CUSTOM page)")
    ap.add_argument("--cell", type=int, default=0, help="the fighter's place on that page (right presses)")
    a = ap.parse_args()
    if a.command == "setup":
        setup(a.game)
    else:
        fight(a.game, a.frames, a.every, a.visible, a.pages, a.cell)


if __name__ == "__main__":
    main()
