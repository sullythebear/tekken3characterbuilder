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
      --cpu KEY: that roster fighter (e.g. cbmedea) is the CPU's stage 1 opponent (patch 15).
  python tools/t3live.py nav route:practice r2:60 r2:60 square:90 square:120 square:120 log:"announced name"
      runs a step script (buttons, waits, screenshots, VRAM dumps, log waits; see nav()).

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
       "right": 0xFFDF, "left": 0xFF7F, "up": 0xFFEF, "down": 0xFFBF, "start": 0xFFF7, "r2": 0xFDFF, "l2": 0xFEFF}


class Game:
    def __init__(self, game: Path, visible: bool, extra_env: dict | None = None):
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
        env.update(extra_env or {})
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
          costume_button: str = "square", probe: bool = False, cpu: str | None = None):
    live = game / "character-builder" / "live"
    # the renderer probe (patch 13): 64 calls (about two frames of both players) out of every
    # 1500, over the whole fight
    env = {"TEKKEN3_NATIVE_PROBE": str(live / "probe.bin"),
           "TEKKEN3_NATIVE_PROBE_START": os.environ.get("T3LIVE_PROBE_START", "300"),
           "TEKKEN3_NATIVE_PROBE_EVERY": "1500",
           "TEKKEN3_NATIVE_PROBE_CALLS": os.environ.get("T3LIVE_PROBE_CALLS", "60000")} if probe else {}
    if cpu:                                  # patch 15's test hook: this fighter at stage 1
        env["TEKKEN3_CPU_STAGE1"] = cpu
    for old in live.glob("probe.bin*"):
        old.unlink()
    g = Game(game, visible, env)
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
        print(f"stage {g.word(0x800ADC84, 2):#04x} music {g.word(0x800ADD08, 2):#04x}")   # this fight's
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


# Main menu routes from the title screen (menu order: Arcade, VS, Team Battle, Time Attack,
# Survival, Tekken Ball, Tekken Force, Practice); each ends on that mode's select screen.
ROUTES = {"arcade": "start:200 start:200", "team": "start:200 down down start:260",
          "practice": "start:200 down down down down down down down start:200"}


def vram_dump(g: Game) -> bytes:
    """The whole VRAM (1024 x 512 halfwords, big-endian as the debug server sends them)."""
    rows = []
    for ty in range(0, 512, 128):
        block = [bytearray() for _ in range(128)]
        for tx in range(0, 1024, 128):
            raw = bytes.fromhex(g.q(cmd="vram_peek", x=tx, y=ty, w=128, h=128)["hex"])
            for r in range(128):
                block[r] += raw[r * 256:(r + 1) * 256]
        rows += block
    return b"".join(rows)


def nav(game: Path, steps: list[str], env: dict | None = None):
    """Runs a step script after boot; output in live/nav. Steps:
    <button>[:frames]   press (cross square triangle circle up down left right start r2 l2), then wait
    route:<name>        a ROUTES entry (arcade, team, practice)
    wait:N  shot:NAME  vram:NAME (NAME.vram)  dump:NAME (RAM, NAME.ram)  ram:ADDR:LEN  film:FRAMES:EVERY (shots named by state)
    log:TEXT[:SECONDS]  waits until the game log has TEXT, prints the state then
    fight               waits until a fight's fighters show (state 8, phase >= 6)"""
    g = Game(game, False, env)
    out = g.live / "nav"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    expanded = []
    for s in steps:
        expanded += ROUTES[s[6:]].split() if s.startswith("route:") else [s]
    try:
        g.wait_frames(700)
        for s in expanded:
            name, _, arg = s.partition(":")
            if name == "wait":
                g.wait_frames(int(arg))
            elif name == "shot":
                g.shot(out / f"{arg}.png")
            elif name == "vram":
                (out / f"{arg}.vram").write_bytes(vram_dump(g))
            elif name == "dump":                      # the whole 2 MB of RAM, NAME.ram
                ram = bytearray()
                for at in range(0x80000000, 0x80200000, 0x4000):
                    ram += bytes.fromhex(g.q(cmd="read_ram", addr=f"{at:08x}", len=0x4000)["hex"])
                (out / f"{arg}.ram").write_bytes(ram)
            elif name == "ram":
                at, n = arg.split(":")
                print(at, g.q(cmd="read_ram", addr=at, len=int(n))["hex"])
            elif name == "film":
                total, every = map(int, arg.split(":"))
                start, k = g.frame(), 0
                while g.frame() - start < total:
                    g.shot(out / f"f{k:03d}_s{g.word(0x800AE204)}_p{g.word(0x800AE224, 2)}.png")
                    k += 1
                    g.wait_frames(every)
            elif name == "log":
                text, _, secs = arg.partition(":")
                end = time.monotonic() + float(secs or 60)
                while text not in g.log.read_text(errors="replace"):
                    if time.monotonic() > end:
                        print(f"log: no '{text}'")
                        break
                    time.sleep(0.05)
                else:
                    print(f"log: '{text}' at state {g.word(0x800AE204)}, frame {g.frame()}")
            elif name == "fight":
                end = time.monotonic() + 150
                while g.word(0x800AE204) != 8 or g.word(0x800AE224, 2) < 6:
                    if time.monotonic() > end:
                        print("fight: did not start")
                        break
                    time.sleep(0.3)
            else:
                g.press(name)
                g.wait_frames(int(arg) if arg else 20)
    finally:
        g.stop()
    print("output in", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("setup", "fight", "nav"))
    ap.add_argument("steps", nargs="*", help="nav: the step script (see nav())")
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--probe", action="store_true", help="record the renderer's per-row transforms (live/probe.bin)")
    ap.add_argument("--pages", type=int, default=2, help="R2 presses on the select screen (2 = CUSTOM page)")
    ap.add_argument("--cell", type=int, default=0, help="the fighter's place on that page (right presses)")
    ap.add_argument("--cpu", help="a roster key (customs.txt, e.g. cbmedea) for the CPU's stage 1 opponent")
    a = ap.parse_intermixed_args()
    if a.command == "setup":
        setup(a.game)
    elif a.command == "nav":
        nav(a.game, a.steps, {"TEKKEN3_CPU_STAGE1": a.cpu} if a.cpu else None)
    else:
        fight(a.game, a.frames, a.every, a.visible, a.pages, a.cell, probe=a.probe, cpu=a.cpu)


if __name__ == "__main__":
    main()
