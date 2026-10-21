"""Dizzy Character Creator (Tekken 3 Recompiled / Expanded) - local server.

Runs on the Python bundled with the Easy Setup, standard library only.
Listens on 127.0.0.1 only and accepts state-changing requests only with the
session token embedded in its own page.
"""
from __future__ import annotations

import base64, io, json, os, re, secrets, shutil, struct, subprocess, sys, threading, time, zipfile, zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

# The Easy Setup's embedded Python does not put the script folder on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import creator_patch  # noqa: E402
import custom_page  # noqa: E402
import name_call  # noqa: E402
import command_list as command_list_module  # noqa: E402   (stdlib only: struct)
import fairness  # noqa: E402

APP_VERSION = "0.8.0"
APP = Path(__file__).resolve().parent
BASE = APP.parent
UI = APP / "ui"
DATA = BASE / "characters"
LOGS = BASE / "logs"
CONFIG = BASE / "config.json"
CACHE = BASE / "cache"          # models read from the player's disc: game data, never shared
TOKEN = secrets.token_urlsafe(24)
WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0

DONOR_MIN, DONOR_MAX = 0, 20
# Letters of Tekken 3's name font (Tekken 3 Expanded draws name plates from it):
# no F or Q, and 2 is the only digit.
NAME_RE = re.compile(r"^[A-EG-PR-Z2 .\-]{1,15}$")
CUSTOM_PAGE_MAX = 12
MAX_UPLOAD = 12 * 1024 * 1024
MAX_IMPORT = 16 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

lock = threading.Lock()


# ---------------------------------------------------------------- project --

def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data: dict) -> None:
    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")


def project_root() -> Path | None:
    configured = load_config().get("root")
    candidates = [Path(configured)] if configured else []
    candidates.append(BASE.parent)
    for c in candidates:
        if (c / "game.toml").is_file():
            return c.resolve()
    return None


def toolchain(root: Path) -> Path | None:
    found = sorted((root / ".setup" / "tools").glob("toolchain-*/bin/cmake.exe"))
    return found[-1].parent.parent if found else None


def game_exe(root: Path) -> Path:
    return root / "build-release" / "Tekken_3_Recompiled.exe"


_exe_cache: dict = {}


def exe_has_support(exe: Path, kind: str) -> bool:
    try:
        stamp = (exe.stat().st_mtime, exe.stat().st_size, kind)
    except OSError:
        return False
    if _exe_cache.get("stamp") != stamp:
        data = exe.read_bytes()
        _exe_cache.update(stamp=stamp, value=creator_patch.PROFILES[kind]["tag"].encode() in data)
    return _exe_cache["value"]


def venv_python(root: Path) -> str:
    """The Expanded setup's Python (it has Pillow and numpy), else ours."""
    for candidate in (root / ".setup/venv/Scripts/python.exe", root / ".setup/venv/bin/python"):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def jun_enabled(root: Path) -> bool:
    return (root / "workspace/jun-import/jun/Jun-TTT1-combat.jmv").is_file()


def project_status() -> dict:
    root = project_root()
    if not root:
        return {"found": False}
    kind = creator_patch.project_kind(root)
    if not kind:
        return {"found": True, "root": str(root), "kind": None, "version": "", "toolchain": False, "exe": False,
                "jun": False, "patch": {"installed": False, "old_probe": False, "compatible": False,
                "problem": "This game folder is not a supported version of Tekken3Recompiled or Tekken 3 Expanded."},
                "built": False, "exe_support": False, "stale": False, "build": build.snapshot(0)["state"],
                "game": game.snapshot(), "build_phase": build.phase, "build_progress": build.progress}
    exe = game_exe(root)
    patch = creator_patch.status(root, kind)
    src = root / creator_patch.PROFILES[kind]["roster"]
    built = exe.is_file() and exe_has_support(exe, kind)
    stale = False
    if patch["installed"] and exe.is_file() and src.is_file():
        stale = src.stat().st_mtime > exe.stat().st_mtime or not built
    version = ""
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return {
        "found": True, "root": str(root), "version": version, "kind": kind,
        "toolchain": toolchain(root) is not None, "exe": exe.is_file(),
        "jun": kind == "expanded" or jun_enabled(root), "patch": patch, "built": built and not stale,
        "custom_max": CUSTOM_PAGE_MAX,
        "exe_support": built,
        "stale": stale, "build": build.snapshot(0)["state"], "game": game.snapshot(), "test": test.snapshot(),
        "build_phase": build.phase, "build_progress": build.progress,
    }


# ------------------------------------------------------------------ build --

class Build:
    def __init__(self):
        self.state, self.lines, self.started, self.finished = "idle", [], None, None
        self.phase, self.progress = "", None

    def snapshot(self, since: int) -> dict:
        with lock:
            return {"state": self.state, "lines": self.lines[since:], "total": len(self.lines),
                    "started": self.started, "finished": self.finished,
                    "phase": self.phase, "progress": self.progress}

    def log(self, text: str) -> None:
        match = re.match(r"\s*\[(\d+)/(\d+)\]", text)
        with lock:
            if match and int(match.group(2)):
                self.progress = int(match.group(1)) / int(match.group(2))
            self.lines.append(text.rstrip())
            if len(self.lines) > 5000:
                del self.lines[:1000]

    def start(self) -> str | None:
        root = project_root()
        if not root:
            return "No Tekken 3 Recompiled folder found."
        tc = toolchain(root)
        if not tc:
            return "The Easy Setup compiler is missing. Run the setup in the launcher first."
        with lock:
            if self.state == "running":
                return "A build is already running."
            self.state, self.lines, self.started, self.finished = "running", [], time.time(), None
            self.phase, self.progress = "Configure", None
        threading.Thread(target=self._run, args=(root, tc), daemon=True).start()
        return None

    def _run(self, root: Path, tc: Path) -> None:
        LOGS.mkdir(exist_ok=True)
        log_file = LOGS / "build-log.txt"
        env = dict(os.environ)
        env["PATH"] = str(tc / "bin") + os.pathsep + env.get("PATH", "")
        jobs = str(min(8, max(2, os.cpu_count() or 2)))
        env.update(PSXRECOMP_TOOLCHAIN_DIR=str(tc), RETCOMM_TOOLCHAIN_DIR=str(tc), PYTHONUTF8="1",
                   PYTHONNOUSERSITE="1", CMAKE_BUILD_PARALLEL_LEVEL=jobs)
        build_dir = root / "build-release"
        cmake = str(tc / "bin" / "cmake.exe")
        fwd = lambda p: str(p).replace("\\", "/")
        cache = build_dir / "CMakeCache.txt"
        kind = creator_patch.project_kind(root)
        try:
            if kind == "expanded":
                # Tekken 3 Expanded keeps the configuration its own setup made.
                text = cache.read_text(encoding="utf-8", errors="replace") if cache.is_file() else ""
                match = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", text, re.M)
                if not match or match.group(1).strip().lower() != fwd(root).lower():
                    raise RuntimeError("Run Tekken 3 Expanded's own setup once in this folder, then build here.")
                steps = [("Build", [cmake, "--build", fwd(build_dir), "--target", "psx-runtime", "--parallel", jobs])]
            elif cache.is_file():
                text = cache.read_text(encoding="utf-8", errors="replace")
                match = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", text, re.M)
                if match and match.group(1).strip().lower() != fwd(root).lower():
                    self.log("This folder is a copy: clearing the old CMake cache.")
                    cache.unlink()
                    shutil.rmtree(build_dir / "CMakeFiles", ignore_errors=True)
            if kind != "expanded":
              steps = [
                ("Configure", [cmake, "-S", fwd(root), "-B", fwd(build_dir), "-G", "Ninja",
                  "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SUPPRESS_REGENERATION=ON",
                  f"-DCMAKE_C_COMPILER={fwd(tc / 'bin/clang.exe')}",
                  f"-DCMAKE_CXX_COMPILER={fwd(tc / 'bin/clang++.exe')}",
                  f"-DCMAKE_MAKE_PROGRAM={fwd(tc / 'bin/ninja.exe')}",
                  f"-DPython3_EXECUTABLE={fwd(sys.executable)}",
                  "-DPSX_STATIC_RUNTIME=ON", "-DPSX_DEBUG_TOOLS=OFF", "-DPSX_DEBUG_SERVER_LITE=OFF",
                  "-DPSX_NETPLAY=OFF", "-DPSXRECOMP_BIOS_STEMS=OpenBIOS",
                  "-DPSXRECOMP_FORCE_SETUP_HOST=OFF", "-DPSXRECOMP_REQUIRE_GAME_C=ON",
                  "-DTEKKEN3_BUILD_PC_PORT=OFF",
                  "-DTEKKEN3_JUN_EXPERIMENTAL=" + ("ON" if jun_enabled(root) else "OFF")]),
                ("Build", [cmake, "--build", fwd(build_dir), "--target", "psx-runtime", "--parallel", jobs]),
              ]
            with log_file.open("w", encoding="utf-8") as out:
                for title, args in steps:
                    with lock:
                        self.phase, self.progress = title, None
                    self.log(f"== {title} ==")
                    process = subprocess.Popen(args, cwd=root, env=env, stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                               errors="replace", creationflags=NO_WINDOW)
                    for line in process.stdout:
                        out.write(line)
                        self.log(line)
                    if process.wait() != 0:
                        raise RuntimeError(f"{title} failed (code {process.returncode}).")
            with lock:
                self.state, self.progress = "success", 1.0
            self.log("Done: the game has been rebuilt.")
        except Exception as error:  # noqa: BLE001 - alles terugmelden aan de interface
            self.log(f"ERROR: {error}")
            with lock:
                self.state = "failed"
        finally:
            with lock:
                self.finished = time.time()


build = Build()


# ------------------------------------------------------------------- game --

class Game:
    def __init__(self):
        self.process, self.character, self.summary = None, None, []

    def snapshot(self) -> dict:
        running = self.process is not None and self.process.poll() is None
        return {"running": running, "character": self.character, "summary": self.summary}

    def start(self, character: dict | None) -> str | None:
        root = project_root()
        if not root:
            return "No Tekken 3 Recompiled folder found."
        exe = game_exe(root)
        if not exe.is_file():
            return "The game has not been built yet."
        if self.snapshot()["running"]:
            return "The game is already running."
        env = dict(os.environ)
        env.pop("T3CB_DONOR", None)
        env.pop("T3CB_NAME", None)
        if character and creator_patch.project_kind(root) == "expanded":
            character = None  # every custom fighter is on the CUSTOM page already
        if character:
            env["T3CB_DONOR"] = str(character["donor"])
            env["T3CB_NAME"] = character["name"]
        LOGS.mkdir(exist_ok=True)
        log_path = LOGS / "game-log.txt"
        handle = log_path.open("w", encoding="utf-8", errors="replace")
        self.process = subprocess.Popen([str(exe)], cwd=exe.parent, env=env, stdout=handle,
                                        stderr=subprocess.STDOUT)
        self.character = character["name"] if character else None
        self.summary = []
        threading.Thread(target=self._wait, args=(handle, log_path), daemon=True).start()
        return None

    def _wait(self, handle, log_path: Path) -> None:
        self.process.wait()
        handle.close()
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        keep = ("Creator slot", "Custom fighters", "Custom page", "Jun roster", "Jun import",
                "error", "fault", "failed")
        self.summary = [l for l in lines if any(k.lower() in l.lower() for k in keep)][-20:]


game = Game()


# ------------------------------------------------------------------- test --

REPORT_PREFIXES = ("Custom fighters", "Custom probe", "TTT1 characters")
REPORT_ERRORS = re.compile(r"error|fault|failed|exception|assert|crash", re.I)


class TestRun:
    """One click: check the patch, build if needed, play, then write logs/test-report.md."""

    def __init__(self):
        self.state, self.phase, self.report = "idle", "", ""
        try:  # the last report survives a restart of the builder
            self.report = (LOGS / "test-report.md").read_text(encoding="utf-8")
        except OSError:
            pass

    def snapshot(self) -> dict:
        return {"state": self.state, "phase": self.phase}

    def start(self) -> str | None:
        root = project_root()
        kind = creator_patch.project_kind(root) if root else None
        if not kind:
            return "No supported game folder found."
        patch = creator_patch.status(root, kind)
        if not patch["installed"]:
            return "The patch is not current: use Install/Update first, then test."
        with lock:
            if self.state == "running":
                return "A test is already running."
            if build.state == "running" or game.snapshot()["running"]:
                return "Wait until the build or the game has finished."
            self.state, self.phase = "running", "Checking"
        threading.Thread(target=self._run, args=(root, kind), daemon=True).start()
        return None

    def _run(self, root: Path, kind: str) -> None:
        started = datetime.now()
        built = None  # None: not needed, True/False: rebuilt and whether it succeeded
        played, problem = None, None
        try:
            if not project_status().get("built"):
                self.phase = "Building"
                problem = build.start()
                while not problem and build.snapshot(0)["state"] == "running":
                    time.sleep(1)
                built = not problem and build.snapshot(0)["state"] == "success"
            if built is not False and not problem:
                self.phase = "Playing"
                begin = time.time()
                problem = game.start(None)
                while not problem and game.snapshot()["running"]:
                    time.sleep(1)
                if not problem:
                    played = (time.time() - begin, game.process.returncode)
                    time.sleep(1)  # let the game log close
        except Exception as error:  # noqa: BLE001 - report it instead of losing the test
            problem = str(error)
        self.report = self._write(root, kind, started, built, played, problem)
        self.state, self.phase = ("done" if built is not False and not problem else "failed"), ""

    def _write(self, root: Path, kind: str, started: datetime, built, played, problem) -> str:
        p = creator_patch.PROFILES[kind]
        patch = p.get("revision") or p["version"]
        status = creator_patch.status(root, kind)
        build_line = ("not needed" if built is None else "rebuilt, succeeded" if built
                      else "rebuilt, FAILED (see logs/build-log.txt)")
        lines = ["# Test report", "",
                 f"- Date: {started:%Y-%m-%d %H:%M:%S}",
                 f"- Builder: {APP_VERSION}",
                 f"- Game folder: {root} ({kind})",
                 f"- Patch: {patch}, {'current' if status['installed'] else 'NOT current'}",
                 f"- Build: {build_line}"]
        if played:
            lines.append(f"- Game: ran {int(played[0]) // 60}m {int(played[0]) % 60:02d}s, exit code {played[1]}")
        if problem:
            lines.append(f"- Problem: {problem}")
        if kind == "expanded":
            lines += ["", "## customs.txt", ""]
            for folder in custom_page.FOLDERS:
                path = root / folder / custom_page.LIST_NAME
                text = path.read_text(encoding="ascii", errors="replace").strip() if path.is_file() else "(missing)"
                lines += [f"{folder}:", "```", text or "(empty)", "```"]
        log_lines = []
        if played:
            try:
                log_lines = (LOGS / "game-log.txt").read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                pass
        picked = [l for l in log_lines if l.startswith(REPORT_PREFIXES)]
        errors = [l for l in log_lines if REPORT_ERRORS.search(l) and not l.startswith(REPORT_PREFIXES)]
        lines += ["", f"## Game log ({len(picked)} lines)", "", "```", *(picked or ["(none)"]), "```",
                  "", f"## Errors ({len(errors)})", "", "```", *(errors[:40] or ["(none)"]), "```", ""]
        report = "\n".join(lines)
        LOGS.mkdir(exist_ok=True)
        (LOGS / "test-report.md").write_text(report, encoding="utf-8")
        return report


test = TestRun()


# ------------------------------------------------------------- characters --

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "personage"


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,40}", value or ""):
        raise ValueError("Invalid character ID.")
    return value


def decode_wav(data_url: str | None, process: bool = False, effect: bool = False, pitch: int = 0,
               echo: str = "none") -> bytes | None:
    """A name call sound (a WAV data URL) as 44100 Hz mono WAV of at most 3 s. process: a new
    recording or file, trimmed and brought to the game's level (done once, when it is chosen;
    saving and packages keep it as it is)."""
    if not data_url:
        return None
    try:
        raw = base64.b64decode(str(data_url).split(",", 1)[-1], validate=True)
    except ValueError:
        raise ValueError("The name call sound is damaged.") from None
    if len(raw) > MAX_UPLOAD:
        raise ValueError("The name call sound is too long.")
    samples = name_call.read_wav(raw)
    if process:                               # effect: the automatic voice's announcer sound
        samples = name_call.announcer(samples) if effect else name_call.shape(samples, pitch, echo)
    else:
        samples = samples[:int(name_call.MAX_SECONDS * name_call.RATE)]
    return name_call.wav_bytes(samples)


def name_call_preview(data: dict) -> dict:
    """The name call a choice gives, as a WAV data URL for the page to play."""
    mode = data.get("mode", "auto")
    if mode == "auto":
        name = str(data.get("name", "")).upper().strip()
        if not NAME_RE.fullmatch(name):
            raise ValueError("Enter the fighter's name first.")
        voice = str(data.get("voice") or "")
        wav = name_call.wav_bytes(name_call.announcer(name_call.speak(name, voice or None)))
    elif data.get("wav"):
        try:
            pitch = int(data.get("pitch") or 0)
        except (TypeError, ValueError):
            raise ValueError("Invalid pitch.") from None
        echo = data.get("echo") if data.get("echo") in name_call.ECHOES else "none"
        wav = decode_wav(data.get("wav"), process=True, effect=bool(data.get("effect")), pitch=pitch, echo=echo)
    else:
        path = DATA / safe_id(str(data.get("id", ""))) / "namecall.wav"
        if not path.is_file():
            raise ValueError("Record or choose a sound first.")
        wav = path.read_bytes()
    return {"wav": "data:audio/wav;base64," + base64.b64encode(wav).decode()}


# Stage Lab (patch 19): the arena of each fighter's stage (descriptor byte 10, read live
# 2026-10-16) and the colour looks of stage_look.py
STAGE_ARENA = {0: 0, 1: 1, 2: 5, 3: 11, 4: 2, 5: 9, 6: 4, 7: 3, 8: 10, 9: 8, 10: 12, 11: 1, 12: 0, 13: 12,
               14: 6, 15: 2, 16: 9, 17: 13, 18: 9, 19: 14, 20: 6}
STAGE_LOOKS = ("night", "sunset", "dusk", "mono", "ice", "inferno", "custom")
# Move Lab damage keys: a COMMAND LIST command without spaces ("df+2", "D+3+4", "d,df,f+2",
# "Duringcrouch,df+1", "During(**),4"): an optional situation or stance, direction taps, then
# direction + buttons
_DIR = r"(?:u|uf|ub|f|b|d|df|db|U|UF|UB|F|B|D|DF|DB)"
_HIT = rf"(?:{_DIR}\+)?[1-4](?:\+[1-4]){{0,3}}"
MOVE_KEY = re.compile(rf"(?:(?:Duringcrouch|Whilecrouching|Whilerising|Duringsidestep|During\(\*{{1,2}}\)),)?(?:{_DIR},){{0,4}}"
                      rf"{_HIT}|(?:{_HIT},){{1,6}}{_HIT}#[2-8]"    # a string's hit 2..8
                      rf"|(?=[^#]*or)[A-Za-z0-9+,()]{{3,48}}")      # a line with alternatives ("b(or,B),1+2")
STAGE_VIEWS = ("front", "right", "back", "left", "textures")
STAGE_MODELS = 15                                        # arenas with a scenery model (stage_look.py)


def stage_look_args(look: str, tint, strength) -> tuple[list[str], str]:
    """stage_look.py arguments for a look and its cache name ("custom": tint and strength)."""
    if look != "custom":
        return ["--look", look], look
    tint = str(tint or "ff8040").lstrip("#").lower()
    if not re.fullmatch(r"[0-9a-f]{6}", tint):
        raise ValueError("The stage tint must be a colour such as #ff8040.")
    strength = max(0, min(100, int(strength if strength is not None else 60)))
    return ["--look", "custom", "--tint", tint, "--strength", str(strength)], f"custom-{tint}-{strength}"


def run_stage_tool(root: Path, args: list[str]) -> str | None:
    try:
        done = subprocess.run([venv_python(root), str(APP / "stage_look.py"), "--root", str(root), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=180, creationflags=NO_WINDOW, cwd=str(APP))
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"The Stage Lab could not run: {error}"
    if done.returncode:
        lines = (done.stdout + done.stderr).strip().splitlines()
        last = lines[-1] if lines else "The Stage Lab failed."
        return last[7:] if last.startswith("ERROR: ") else last
    return None


def stage_arena(fighter: dict) -> int:
    owner = fighter.get("stage")
    return STAGE_ARENA[fighter["donor"] if owner is None else owner]


def write_moves(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-moves.bin (patches 20, 21): the fighter's changed move damage and moves on other
    buttons (or none)."""
    name = f"{custom_page.file_prefix(key)}-moves.bin"
    data = None
    if fighter.get("move_damage") or fighter.get("move_buttons") or fighter.get("poses"):
        try:
            moves = command_list(fighter["donor"])
        except ValueError as error:
            return f"Move damage: {error}"
        data = command_list_module.moves_file(moves["key"], moves["records"], fighter.get("move_damage") or {},
                                              fighter.get("move_buttons"), moves.get("slots"),
                                              command_list_module.pose_swaps(moves.get("poses", {}), moves.get("pose_slots", {}),
                                                                             fighter.get("poses")))
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if data:
                (target / name).write_bytes(data)
            else:
                (target / name).unlink(missing_ok=True)
    except OSError as error:
        return f"Move damage: {error}"
    return None


def style_lists(donor: int) -> list[bytes]:
    """The style's COMMAND LIST bytes, one per distinct costume list (cached)."""
    models = donor_models()["donors"].get(str(donor), [])
    path = CACHE / f"rawlists1-{'_'.join(map(str, models))}.json"
    if not path.is_file():
        problem, out = run_model_tool(project_root(), ["rawlists", "--models", ",".join(map(str, models))], timeout=120)
        if problem:
            raise ValueError(problem)
        CACHE.mkdir(exist_ok=True)
        path.write_text(out.strip().splitlines()[-1], encoding="utf-8")
    return [bytes.fromhex(h) for h in json.loads(path.read_text(encoding="utf-8"))]


def write_commands(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-commands.bin (patch 22): the COMMAND LIST with moved moves on their new inputs."""
    name = f"{custom_page.file_prefix(key)}-commands.bin"
    data = None
    if fighter.get("move_buttons"):
        try:
            data = command_list_module.commands_file(style_lists(fighter["donor"]), fighter["move_buttons"])
        except ValueError as error:
            return f"Command list: {error}"
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if data:
                (target / name).write_bytes(data)
            else:
                (target / name).unlink(missing_ok=True)
    except OSError as error:
        return f"Command list: {error}"
    return None


def _write_number(root: Path, key: str, suffix: str, value, what: str) -> str | None:
    """<Key>-T3<suffix> holding one number (or no file)."""
    name = f"{custom_page.file_prefix(key)}{suffix}"
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if value is None:
                (target / name).unlink(missing_ok=True)
            else:
                (target / name).write_text(f"{int(value)}\n", encoding="ascii")
    except OSError as error:
        return f"{what}: {error}"
    return None


def write_rival(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-rival.txt (patch 22): the stock fighter met at stage 9 in Arcade (or none)."""
    return _write_number(root, key, "-rival.txt", fighter.get("rival"), "Rival")


# CPU personality (patch 22): a block of the game's CPU behaviour table (difficulty * 10 + stage)
CPU_BLOCKS = {"calm": 0, "steady": 14, "fierce": 29}


def write_cpu(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-cpu.txt (patch 22): the CPU behaviour block while the CPU plays the fighter."""
    return _write_number(root, key, "-cpu.txt", CPU_BLOCKS.get(fighter.get("cpu")), "CPU personality")


def write_stage_look(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-stage.bin: the home stage's colour variant (or none), cached per stage and look."""
    name = f"{custom_page.file_prefix(key)}-stage.bin"
    look = fighter.get("stage_look")
    data = None
    if look:
        arena = stage_arena(fighter)
        args, label = stage_look_args(look, fighter.get("stage_tint"), fighter.get("stage_strength"))
        cached = CACHE / f"stage-{arena}-{label}.bin"
        if not cached.is_file():
            CACHE.mkdir(exist_ok=True)
            problem = run_stage_tool(root, ["--arena", str(arena), *args, "--out", str(cached)])
            if problem:
                return f"Stage colours: {problem}"
        data = cached.read_bytes()
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if data:
                (target / name).write_bytes(data)
            else:
                (target / name).unlink(missing_ok=True)
    except OSError as error:
        return f"Stage colours: {error}"
    return None


def stage_preview(data: dict) -> dict:
    """PNG (base64) of the stage seen from the fighters' place (view front/right/back/left), or of
    its largest textures (view "textures"), with a look or as the game colours them."""
    out, view = stage_view_file(data)
    return {"png": base64.b64encode(out.read_bytes()).decode(), "view": view}


def stage_view_file(data: dict) -> tuple[Path, str]:
    """The cached PNG of stage_preview and the view it shows."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("The Stage Lab needs Tekken 3 Expanded.")
    try:
        arena = stage_arena({"donor": int(data.get("donor")), "stage": None if data.get("stage") in (None, "") else int(data.get("stage"))})
    except (TypeError, ValueError, KeyError):
        raise ValueError("Choose a fighting style first.") from None
    look = data.get("look") or None
    if look and look not in STAGE_LOOKS:
        raise ValueError("That stage colour does not exist.")
    view = data.get("view") or "front"
    if view not in STAGE_VIEWS:
        raise ValueError("That stage view does not exist.")
    if arena >= STAGE_MODELS:                            # no scenery model known: the textures
        view = "textures"
    args, label = stage_look_args(look, data.get("tint"), data.get("strength")) if look else ([], "original")
    out = CACHE / f"stage2-{arena}-{label}-{view}.png"         # 2: with the floor
    if not out.is_file():
        CACHE.mkdir(exist_ok=True)
        extra = [] if view == "textures" else ["--view", view]
        problem = run_stage_tool(root, ["--arena", str(arena), *args, "--preview", str(out), *extra])
        if problem:
            raise ValueError(problem)
    return out, view


def write_name_call(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-TTT1-sfx.jus: the announcer's call of the fighter's name (or none)."""
    try:
        name_call.write(root, custom_page.FOLDERS, key, name_call.fighter_sound(DATA / fighter["id"], fighter))
    except (OSError, ValueError) as error:
        return f"Name call: {error}"
    return None


def decode_png(data_url: str | None) -> bytes | None:
    if not data_url:
        return None
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ValueError("Images must be sent as PNG.")
    raw = base64.b64decode(data_url[len(prefix):], validate=True)
    if len(raw) > MAX_UPLOAD or not raw.startswith(PNG_SIGNATURE):
        raise ValueError("The image is too large or not a valid PNG.")
    return raw


def validate_character(data: dict) -> dict:
    name = str(data.get("name", "")).upper().strip()
    if not NAME_RE.fullmatch(name):
        raise ValueError("Name: 1 to 15 characters: letters from Tekken 3's name font (no F or Q), space, period, hyphen or 2.")
    try:
        donor = int(data.get("donor"))
    except (TypeError, ValueError):
        raise ValueError("Choose a fighting style.") from None
    if not DONOR_MIN <= donor <= DONOR_MAX:
        raise ValueError("That donor does not exist.")
    author = re.sub(r"[^\w .\-]", "", str(data.get("author", ""))).strip()[:32]
    clean = {"name": name, "donor": donor, "author": author}
    for key in ("stage", "music", "rival"):  # the Tekken 3 fighter whose stage / music it takes, its rival
        value = data.get(key)
        if value not in (None, "", -1, "-1"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"That {key} does not exist.") from None
            if not DONOR_MIN <= value <= DONOR_MAX:
                raise ValueError(f"That {key} does not exist.")
            clean[key] = value
    guest = str(data.get("guest_style") or "").lower()   # patch 23: a TTT1 guest's style
    if guest:
        root = project_root()
        known = [g["key"] for g in custom_page.guest_styles(root)] if root else []
        if not re.fullmatch(r"[a-z0-9]{1,24}", guest) or guest.startswith("cb") or (known and guest not in known):
            raise ValueError("That TTT1 style is not in this game.")
        clean["guest_style"] = guest
    poses = data.get("poses")                 # Move Lab: intro and win pose, 1-based (patch 21 swaps)
    if isinstance(poses, dict):
        clean_poses = {k: int(v) for k, v in poses.items()
                       if k in ("intro", "win") and isinstance(v, (int, str)) and str(v).isdigit() and 1 <= int(v) <= 8}
        if clean_poses:
            clean["poses"] = clean_poses
    if data.get("cpu") in CPU_BLOCKS:         # CPU personality (patch 22)
        clean["cpu"] = data["cpu"]
    look = data.get("stage_look")           # Stage Lab colours of the home stage (patch 19)
    if look not in (None, ""):
        if look not in STAGE_LOOKS:
            raise ValueError("That stage colour does not exist.")
        clean["stage_look"] = look
        if look == "custom":                  # its colour and strength
            args, _ = stage_look_args(look, data.get("stage_tint"), data.get("stage_strength"))
            clean["stage_tint"], clean["stage_strength"] = "#" + args[3], int(args[5])
    mode = data.get("name_call", "off")     # the announcer's call: silent (default, owner 2026-10-16), automatic voice, own sound
    if mode not in name_call.MODES:
        raise ValueError("Choose how the announcer calls the name.")
    clean["name_call"] = mode
    voice = str(data.get("name_call_voice") or "").strip()
    if voice and name_call.VOICE_RE.fullmatch(voice):   # an installed Windows voice (auto mode)
        clean["name_call_voice"] = voice
    moves = data.get("move_damage")                      # Move Lab: {input: damage}
    if isinstance(moves, dict) and moves:
        clean_moves = {}
        for k, v in list(moves.items())[:command_list_module.MOVES_FILE_MAX]:
            if MOVE_KEY.fullmatch(str(k)):
                try:
                    clean_moves[str(k)] = max(0, min(200, int(v)))
                except (TypeError, ValueError):
                    raise ValueError("Invalid move damage.") from None
        if clean_moves:
            clean["move_damage"] = clean_moves
    buttons = data.get("move_buttons")                   # Move Lab: {basic input: move it starts}
    if isinstance(buttons, dict) and buttons:
        clean_buttons = {str(k): str(v) for k, v in list(buttons.items())[:command_list_module.BUTTONS_MAX]
                         if MOVE_KEY.fullmatch(str(k)) and MOVE_KEY.fullmatch(str(v)) and "#" not in str(v)
                         and k != v}
        if clean_buttons:
            clean["move_buttons"] = clean_buttons
    credits = clean_credits(data.get("credits"))
    if credits:
        clean["credits"] = credits
    return clean


# the licence register: where the player's own assets come from (ASSET_LICENSES.md categories)
CREDIT_ASSETS = ("model", "portrait", "sound")
LICENCES = {"own": "My own work", "cc0": "CC0 (public domain)", "cc-by": "CC BY (credit the author)",
            "cc-by-sa": "CC BY-SA", "permission": "The author's permission", "unknown": "Not known"}


def clean_credits(value) -> dict:
    """{asset: {source, author, licence}} for the fighter's own model, portrait image and sound;
    empty entries are left out."""
    out = {}
    for asset in CREDIT_ASSETS:
        entry = value.get(asset) if isinstance(value, dict) else None
        if not isinstance(entry, dict):
            continue
        source = "".join(ch for ch in str(entry.get("source", "")) if ch.isprintable() and ch not in "<>\"").strip()[:200]
        author = "".join(ch for ch in str(entry.get("author", "")) if ch.isprintable() and ch not in "<>\"").strip()[:60]
        licence = entry.get("licence") if entry.get("licence") in LICENCES else "unknown"
        if source or author or licence != "unknown":
            out[asset] = {"source": source, "author": author, "licence": licence}
    return out


ASSET_NAMES = {"model": "the 3D model source", "portrait": "the portrait image", "sound": "the name call recording"}


def own_assets(folder: Path, data: dict) -> dict:
    """Which of the player's own assets a fighter carries (its package holds them)."""
    return {"model": any((folder / f"source{e}").is_file() for e in MODEL_SOURCES),
            "portrait": (folder / "portrait.png").is_file(),
            "sound": data.get("name_call") == "own" and (folder / "namecall.wav").is_file()}


def licence_warnings(cid: str) -> list[str]:
    """Own assets in the fighter's package whose licence is not filled in (export check)."""
    folder = DATA / safe_id(cid)
    data = get_character(folder.name)
    credits = data.get("credits") or {}
    present = own_assets(folder, data)
    return [f"The licence of {ASSET_NAMES[a]} is not known." for a in CREDIT_ASSETS
            if present[a] and (credits.get(a) or {}).get("licence", "unknown") == "unknown"]


def asset_library() -> list[dict]:
    """Every fighter's own assets with their credits: the licence register over the library.
    Disc parts (Character Builder bodies, colour variants) are not listed: they stay on the
    player's disc and packages never carry them."""
    rows = []
    for c in character_list():
        folder = DATA / c["id"]
        credits = c.get("credits") or {}
        for asset, present in own_assets(folder, c).items():
            if not present:
                continue
            entry = credits.get(asset) or {}
            rows.append({"id": c["id"], "fighter": c["name"], "asset": asset,
                         "source": entry.get("source", ""), "author": entry.get("author", ""),
                         "licence": entry.get("licence", "unknown"),
                         "licence_name": LICENCES[entry.get("licence", "unknown")]})
    return rows


def check_library() -> dict:
    """A read-only check of every fighter against the game folder: is what the creator writes
    there present (Custom page entry, portrait, own model, name call, stage colours), and what is
    missing in the fighter itself. {"general": [...], "fighters": [{id, name, issues: [{level, text}]}]}
    with level "bad" (the game will not show it as made), "warn" or "info"."""
    root = project_root()
    general, out = [], []
    expanded = bool(root) and creator_patch.project_kind(root) == "expanded"
    if not expanded:
        general.append({"level": "bad", "text": "No Tekken 3 Expanded folder is set: the game files cannot be checked."})
    else:
        status = project_status()
        if not (status.get("patch") or {}).get("installed"):
            general.append({"level": "bad", "text": "The Custom page is not installed in the game (step 1)."})
        elif not status.get("built"):
            general.append({"level": "warn", "text": "The game has not been built with the current changes (step 2)."})
    entries = dict(custom_page.read_entries(root, {})[0]) if expanded else {}

    def game_file(key, name):
        return any((root / folder / name).is_file() for folder in custom_page.FOLDERS)

    for c in sorted(character_list(), key=lambda c: c.get("created", "")):
        folder, issues = DATA / c["id"], []
        add = lambda level, text: issues.append({"level": level, "text": text})
        if not (folder / "portrait-ps1.png").is_file():
            add("info", "No portrait yet: the select screen shows a plain tile.")
        if c.get("name_call") == "own" and not (folder / "namecall.wav").is_file():
            add("bad", "The name call is set to your own sound, but nothing is recorded.")
        for text in licence_warnings(c["id"]):
            add("warn", text)
        if expanded:
            key = game_key(c["id"])
            prefix = custom_page.file_prefix(key)
            if key not in entries:
                add("bad", "Not on the Custom page (customs.txt): save the fighter or refresh the Custom page files.")
            if not game_file(key, f"{prefix}-ui.jui"):
                add("bad", "The portrait and name plate files are missing in the game.")
            if c.get("guest_style"):                   # the guest's model and moves: nothing else to check
                out.append({"id": c["id"], "name": c["name"], "issues": issues})
                continue
            if c.get("own_model") and (folder / "model.bin").is_file() and not game_file(key, f"{prefix}-model.bin"):
                add("bad", "Its own 3D model is not in the game yet.")
            if c.get("name_call") in ("auto", "own") and not game_file(key, name_call.pack_name(key)):
                add("warn", "The name call is not in the game yet.")
            if c.get("stage_look") and not game_file(key, f"{prefix}-stage.bin"):
                add("warn", "The stage colours are not in the game yet.")
            if (c.get("move_damage") or c.get("move_buttons") or c.get("poses")) and not game_file(key, f"{prefix}-moves.bin"):
                add("warn", "The changed moves are not in the game yet.")
            if c.get("cpu") and not game_file(key, f"{prefix}-cpu.txt"):
                add("warn", "The CPU personality is not in the game yet.")
            if c.get("rival") is not None and not game_file(key, f"{prefix}-rival.txt"):
                add("warn", "The rival is not in the game yet.")
        out.append({"id": c["id"], "name": c["name"], "issues": issues})
    return {"general": general, "fighters": out}


def duplicate_character(cid: str) -> dict:
    """A copy of the fighter under the name + " 2" (Tekken 3's name font has 2 as its only digit),
    made through its package so everything travels: portraits, model, choices, credits."""
    _, package = export_character(cid)
    source = zipfile.ZipFile(io.BytesIO(package))
    out = io.BytesIO()
    with source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in source.infolist():
            raw = source.read(info)
            if info.filename == "character.json":
                data = json.loads(raw.decode("utf-8"))
                data["name"] = (data.get("name", "")[:13].rstrip() + " 2").strip()
                raw = json.dumps(data).encode("utf-8")
            z.writestr(info.filename, raw)
    return import_character(base64.b64encode(out.getvalue()).decode())


SHARE_PREFIX, SHARE_MAX = "T3C1-", 6000


def share_code(cid: str) -> str:
    """A fighter's settings as a short text to paste anywhere: name, style, stage, music, colours,
    moves, credits and a Character Builder body (its parts, rebuilt on import). No files: no
    portrait, recording or imported model."""
    info = DATA / safe_id(cid) / "character.json"
    if not info.is_file():
        raise ValueError("Character not found.")
    record = json.loads(info.read_text(encoding="utf-8"))
    keep = {k: record[k] for k in (*RESTORE_FIELDS, "stage_tint", "stage_strength", "fairness") if k in record}
    own = record.get("own_model") or {}
    if own.get("file") == "Character Builder":
        keep["own_model"] = {k: own[k] for k in ("file", "costume", "kit", "colours", "shape", "pieces") if k in own}
    if keep.get("name_call") == "own":
        keep["name_call"] = "auto"                      # the recording stays home
    raw = zlib.compress(json.dumps(keep, separators=(",", ":")).encode("utf-8"), 9)
    return SHARE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def import_share_code(code: str) -> dict:
    """A new fighter from a share code (through a package holding only its character.json)."""
    code = re.sub(r"\s+", "", str(code or ""))
    if not code.startswith(SHARE_PREFIX) or len(code) > SHARE_MAX:
        raise ValueError("This is not a Dizzy share code.")
    body = code[len(SHARE_PREFIX):]
    try:
        unzip = zlib.decompressobj()
        raw = unzip.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)), 256 * 1024)
        if unzip.unconsumed_tail:
            raise ValueError
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError):
        raise ValueError("This share code is damaged.") from None
    if not isinstance(data, dict):
        raise ValueError("This share code is damaged.")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("character.json", json.dumps(data))
    return import_character(base64.b64encode(out.getvalue()).decode())


def backup_all() -> tuple[str, bytes]:
    """Every fighter as its .t3char package, in one .t3backup zip (Import package reads it)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
        for c in character_list():
            name, data = export_character(c["id"])
            z.writestr(name, data)
    return f"fighters-{datetime.now():%Y%m%d-%H%M}.t3backup", buffer.getvalue()


COSTUME_MAX = 8
COSTUME_NAME_RE = re.compile(r"[^\w .\-]")


def validate_costumes(value) -> list[dict]:
    """Colour variants: a name, the donor costume they recolour (0..3) and the changed
    palettes as PS1 15-bit colours, keyed by CLUT id."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > COSTUME_MAX:
        raise ValueError(f"A fighter can have up to {COSTUME_MAX} colour variants.")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Invalid colour variant.")
        name = COSTUME_NAME_RE.sub("", str(item.get("name", ""))).strip()[:24] or "Variant"
        try:
            base = int(item.get("base", 0))
        except (TypeError, ValueError):
            raise ValueError("Invalid colour variant.") from None
        if not 0 <= base <= 3:
            raise ValueError("Invalid base costume.")
        cluts = {}
        for key, colours in dict(item.get("cluts") or {}).items():
            if not str(key).isdigit() or int(key) > 0x7FFF or not isinstance(colours, list)                     or len(colours) not in (16, 256) or not all(isinstance(c, int) and 0 <= c <= 0xFFFF for c in colours):
                raise ValueError("Invalid palette in a colour variant.")
            cluts[str(int(key))] = colours
        if len(cluts) > 64:
            raise ValueError("Too many palettes in a colour variant.")
        try:
            slot = int(item.get("slot", -1))
        except (TypeError, ValueError):
            slot = -1
        out.append({"name": name, "base": base, "slot": slot if 0 <= slot <= 3 else -1, "cluts": cluts,
                    "recipe": validate_recipe(item.get("recipe"))})
    return out


def validate_recipe(value) -> dict:
    """The builder's editing state for a variant (kept so it can be edited again)."""
    recipe = {"tint": {"h": 0, "s": 100, "l": 0, "keepSkin": True}, "parts": {}, "free": {}}
    if not isinstance(value, dict):
        return recipe
    tint = value.get("tint") if isinstance(value.get("tint"), dict) else {}
    for key, low, high in (("h", -180, 180), ("s", 0, 200), ("l", -40, 40)):
        try:
            recipe["tint"][key] = max(low, min(high, int(tint.get(key, recipe["tint"][key]))))
        except (TypeError, ValueError):
            pass
    recipe["tint"]["keepSkin"] = bool(tint.get("keepSkin", True))
    parts = value.get("parts") if isinstance(value.get("parts"), dict) else {}
    for key, colour in list(parts.items())[:64]:
        if re.fullmatch(r"[0-9\-]{1,200}", str(key)) and re.fullmatch(r"#[0-9a-fA-F]{6}", str(colour)):
            recipe["parts"][str(key)] = str(colour).lower()
    free = value.get("free") if isinstance(value.get("free"), dict) else {}
    for key, colour in list(free.items())[:2048]:
        if re.fullmatch(r"\d{1,5}:\d{1,3}", str(key)) and isinstance(colour, int) and 0 <= colour <= 0xFFFF:
            recipe["free"][str(key)] = colour
    return recipe


def character_list() -> list[dict]:
    DATA.mkdir(exist_ok=True)
    result = []
    for folder in sorted(DATA.iterdir()):
        info = folder / "character.json"
        if not info.is_file():
            continue
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
            data.update(validate_character(data))
        except (OSError, ValueError):
            continue
        data["id"] = folder.name
        # the portrait files can change without character.json (a saved portrait put back in use)
        stamp = max(int(f.stat().st_mtime_ns // 1000) for f in (info, folder / "portrait-ps1.png", folder / "portrait.png")
                    if f.is_file())
        data["portrait"] = (f"/characters/{folder.name}/portrait-ps1.png?v={stamp}"
                            if (folder / "portrait-ps1.png").is_file() else None)
        data["source"] = (f"/characters/{folder.name}/portrait.png?v={stamp}"
                          if (folder / "portrait.png").is_file() else None)
        data["has_model"] = (folder / "model.bin").is_file()
        data["model_undo"] = (folder / "model-prev.json").is_file()
        if not data["has_model"]:
            data.pop("own_model", None)
        data["name_recording"] = (folder / "namecall.wav").is_file()
        try:                                       # a checked upload waiting for its import
            data["model_upload"] = (json.loads((folder / "upload.json").read_text(encoding="utf-8"))
                                    if (folder / "upload.json").is_file() else None)
        except (OSError, ValueError):
            data["model_upload"] = None
        result.append(data)
    return result


def game_key(cid: str) -> str:
    return "cb" + re.sub(r"[^a-z0-9]", "", cid.lower())[:24]


def run_custom_tool(root: Path, args: list[str]) -> str | None:
    """Runs expanded_custom.py; returns an error message or None."""
    try:
        done = subprocess.run([venv_python(root), str(APP / "expanded_custom.py"), *args, "--root", str(root)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=180, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"The Custom page tool could not run: {error}"
    output = (done.stdout + done.stderr).strip()
    if done.returncode:
        errors = [l[7:] for l in output.splitlines() if l.startswith("ERROR: ")]
        return errors[-1] if errors else (output.splitlines()[-1] if output else "The Custom page tool failed.")
    return None


def sync_customs(changed: str | None = None, drop: str | None = None, everything: bool = False) -> list[str]:
    """Keeps Tekken 3 Expanded's CUSTOM page in line with the library.

    Fighters already in customs.txt keep their place (and so their ID), also
    those that are not in this builder's library: only `drop`, a key the user
    chose to remove, leaves the list. New library fighters are added after them.
    """
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        return []
    warnings = []
    if drop:
        problem = run_custom_tool(root, ["remove", "--key", drop])
        if problem:
            warnings.append(problem)
    fighters = sorted(character_list(), key=lambda c: c.get("created", ""))
    library = {game_key(c["id"]): c for c in fighters}
    raw_lines = {}
    existing, unreadable = custom_page.read_entries(root, raw_lines)
    for line in unreadable:
        warnings.append(f"customs.txt has a line the creator cannot read, kept out of the list: {line}")
    order = [key for key, _ in existing if key != drop]
    order += [key for key in library if key not in order and key != drop]
    donors = dict(existing)
    listed, left_out = [], 0
    for key in order:
        c = library.get(key)
        if not c:  # not in this library: keep it as the game has it
            listed.append(raw_lines.get(key) or f"{key} {donors[key]}")
            continue
        if len(listed) >= CUSTOM_PAGE_MAX:
            left_out += 1
            continue
        present = custom_page.find_file(root, key, "-ui.jui") is not None
        if everything or c["id"] == changed or not present:
            folder = DATA / c["id"]
            portrait = next((folder / n for n in ("portrait-full.png", "portrait.png") if (folder / n).is_file()), None)
            args = ["install", "--key", key, "--label", c["name"]]
            if portrait:
                args += ["--portrait", str(portrait)]
            problem = run_custom_tool(root, args)
            if problem:
                warnings.append(f"{c['name']}: {problem}")
                if not present and key not in donors:
                    continue
        listed.append(custom_entry(key, c))
        if c.get("guest_style"):                       # patch 23: the guest's model and moves
            problem = clear_tekken3_files(root, key)
            if problem:
                warnings.append(f"{c['name']}: {problem}")
            continue
        problem = write_palettes(root, key, c) or write_own_model(root, key, c)
        if problem:
            warnings.append(f"{c['name']}: {problem}")
        for problem in (write_name_call(root, key, c), write_stage_look(root, key, c), write_moves(root, key, c),
                        write_rival(root, key, c), write_commands(root, key, c), write_cpu(root, key, c)):
            if problem:
                warnings.append(f"{c['name']}: {problem}")
    if left_out:
        warnings.append(f"The Custom page holds {CUSTOM_PAGE_MAX} fighters: {left_out} of yours are left out.")
    args = ["list", *sum((["--entry", e] for e in listed), [])]
    if drop:
        args += ["--drop", drop]
    problem = run_custom_tool(root, args)
    if problem:
        warnings.append(problem)
    return warnings


GUEST_STYLE_OFF = ("-pal.bin", "-model.bin", "-stage.bin", "-moves.bin", "-rival.txt", "-commands.bin", "-cpu.txt")


def clear_tekken3_files(root: Path, key: str) -> str | None:
    """A fighter on a TTT1 guest's style uses none of the files made for Tekken 3 styles."""
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            for suffix in GUEST_STYLE_OFF:
                (target / f"{custom_page.file_prefix(key)}{suffix}").unlink(missing_ok=True)
            (target / f"{key[0].upper()}{key[1:].lower()}-TTT1-sfx.jus").unlink(missing_ok=True)
    except OSError as error:
        return f"Old files could not be removed: {error}"
    return None


def custom_entry(key: str, c: dict) -> str:
    """A customs.txt line: key and donor, then the fighters whose stage and music it takes when
    they are not the donor's (patch 17). A fighter on a TTT1 guest's style: "@<guest>" in the
    donor's place, 99 for the guest's own stage or music (patch 23)."""
    stage, music = c.get("stage"), c.get("music")
    if c.get("guest_style"):
        if stage is None and music is None:
            return f"{key} @{c['guest_style']}"
        return f"{key} @{c['guest_style']} {99 if stage is None else stage} {99 if music is None else music}"
    if stage is None and music is None:
        return f"{key} {c['donor']}"
    return f"{key} {c['donor']} {c['donor'] if stage is None else stage} {c['donor'] if music is None else music}"


def donor_costume_count(donor: int) -> int:
    info = donor_models()
    return len(info["donors"].get(str(donor), [])) if info.get("available") else 0


def write_palettes(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-pal.bin: the fighter's colour variants on their chosen costume slots.
    Format: b"T3CP", u16 version 1, u16 entries; per entry u8 slot, u8 base costume,
    u16 CLUT id, u16 colour count, then the PS1 colours (u16 each)."""
    entries, taken, own = [], set(), donor_costume_count(fighter["donor"])
    for variant in validate_costumes(fighter.get("costumes")):
        slot = variant["slot"]
        # Costume 3 (Start) is the only extra slot a player can pick; others replace a costume.
        if slot < 0 or slot in taken or not own or slot > max(own - 1, 2):
            continue
        taken.add(slot)
        if slot < own:
            variant["base"] = slot          # replacing a costume recolours that costume's model
        for cid, colours in sorted(variant["cluts"].items(), key=lambda kv: int(kv[0])):
            entries.append(struct.pack("<BBHH", slot, variant["base"], int(cid), len(colours))
                           + struct.pack(f"<{len(colours)}H", *colours))
    name = f"{custom_page.file_prefix(key)}-pal.bin"
    data = b"T3CP" + struct.pack("<HH", 1, len(entries)) + b"".join(entries)
    try:
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if entries:
                (target / name).write_bytes(data)
            else:
                (target / name).unlink(missing_ok=True)
    except OSError as error:
        return f"Colour variants could not be written: {error}"
    return None


def write_own_model(root: Path, key: str, fighter: dict) -> str | None:
    """<Key>-T3-model.bin: the fighter's own model (characters/<id>/model.bin, a "T3CM" file from
    model_export.py), copied next to its other files; removed when the fighter has none."""
    source = DATA / fighter["id"] / "model.bin"
    name = f"{custom_page.file_prefix(key)}-model.bin"
    try:
        data = source.read_bytes() if source.is_file() else None
        if data is not None and data[:4] != b"T3CM":
            return "Its own model (model.bin) is not a builder model file."
        for folder in custom_page.FOLDERS:
            target = root / folder
            if not target.is_dir():
                continue
            if data is not None:
                (target / name).write_bytes(data)
            else:
                (target / name).unlink(missing_ok=True)
    except OSError as error:
        return f"Its own model could not be written: {error}"
    return None


model_lock = threading.Lock()


def run_model_tool(root: Path, args: list[str], timeout: int = 180) -> tuple[str | None, str]:
    """Runs model_export.py; returns (error or None, stdout)."""
    try:
        done = subprocess.run([venv_python(root), str(APP / "model_export.py"), *args, "--root", str(root)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"The model tool could not run: {error}", ""
    if done.returncode:
        lines = (done.stdout + done.stderr).strip().splitlines()
        errors = [l[7:] for l in lines if l.startswith("ERROR: ")]
        return (errors[-1] if errors else (lines[-1] if lines else "The model tool failed.")), ""
    return None, done.stdout


def donor_models() -> dict:
    """{donor: [model per costume]} read from the game's model map, cached."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        return {"available": False, "reason": "The 3D preview needs Tekken 3 Expanded."}
    path = CACHE / "donors.json"
    if not path.is_file():
        problem, out = run_model_tool(root, ["donors"], timeout=60)
        if problem:
            return {"available": False, "reason": problem}
        CACHE.mkdir(exist_ok=True)
        path.write_text(out.strip(), encoding="utf-8")
    return {"available": True, "donors": json.loads(path.read_text(encoding="utf-8"))}


MODEL_SOURCES = (".fbx", ".glb", ".vrm")


# a texture image the player chose beside the model file: texture-upload.* (with upload.*),
# texture-source.* (with source.*), texture-prev.* (with source-prev.*, for Undo)
TEXTURE_TYPES = {".png": bytes([0x89]) + b"PNG", ".jpg": bytes([0xFF, 0xD8]), ".jpeg": bytes([0xFF, 0xD8])}


def model_texture(folder: Path, stem: str) -> Path | None:
    return next((folder / f"texture-{stem}{e}" for e in TEXTURE_TYPES if (folder / f"texture-{stem}{e}").is_file()), None)


def move_texture(folder: Path, src: str, dst: str) -> None:
    """texture-<src>.* becomes texture-<dst>.* (any old texture-<dst>.* goes)."""
    for old in folder.glob(f"texture-{dst}.*"):
        old.unlink()
    texture = model_texture(folder, src)
    if texture:
        texture.replace(folder / f"texture-{dst}{texture.suffix}")


def run_import_tool(root: Path, args: list[str], timeout: int = 1800, on_line=None) -> tuple[str | None, str]:
    """Runs direct_import.py (own 3D models); returns (error or None, stdout). on_line(text) gets
    every line while it runs (the import's progress). A model file upload.* or source.* gets its
    texture image (texture-upload.* / texture-source.*) when the player chose one."""
    if args and Path(args[0]).stem in ("upload", "source"):
        texture = model_texture(Path(args[0]).parent, Path(args[0]).stem)
        if texture:
            args = [*args, "--texture", str(texture)]
    cmd = [venv_python(root), str(APP / "direct_import.py"), *args, "--root", str(root)]
    try:
        if on_line is None:
            done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, creationflags=NO_WINDOW, cwd=str(APP))
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", creationflags=NO_WINDOW, cwd=str(APP),
                                    env={**os.environ, "PYTHONUNBUFFERED": "1"})
            out, start = [], time.time()
            for line in proc.stdout:
                out.append(line)
                on_line(line.rstrip())
                if time.time() - start > timeout:
                    proc.kill()
                    raise subprocess.TimeoutExpired(cmd, timeout)
            proc.wait()
            done = subprocess.CompletedProcess(cmd, proc.returncode, "".join(out), "")
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"The model import could not run: {error}", ""
    if done.returncode:
        lines = (done.stdout + done.stderr).strip().splitlines()
        errors = [l.split("ERROR", 1)[1].lstrip(": ") for l in lines if "ERROR" in l]
        return (errors[-1] if errors else (lines[-1] if lines else "The model import failed.")), ""
    return None, done.stdout


def model_upload(folder: Path) -> Path | None:
    return next((folder / f"upload{e}" for e in MODEL_SOURCES if (folder / f"upload{e}").is_file()), None)


def check_model(cid: str, name: str, payload: str) -> dict:
    """Stores an uploaded .fbx/.glb next to the character (upload.*) and reports what the import
    needs to know: triangles, texture and whether it is rigged (not rigged = locked)."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("Own 3D models need Tekken 3 Expanded.")
    folder = DATA / safe_id(cid)
    if not (folder / "character.json").is_file():
        raise ValueError("Save the character first.")
    ext = Path(str(name)).suffix.lower()
    if ext not in MODEL_SOURCES:
        raise ValueError("Use an .fbx (FBX Binary), .glb or .vrm file.")
    raw = base64.b64decode(payload, validate=True)
    if len(raw) > MAX_IMPORT:
        raise ValueError("This model file is too large (16 MB at most).")
    for old in [*folder.glob("upload.*"), *folder.glob("texture-upload.*")]:
        old.unlink()
    target = folder / f"upload{ext}"
    target.write_bytes(raw)
    return recheck_upload(root, folder, target, Path(str(name)).name[:80])


def recheck_upload(root: Path, folder: Path, target: Path, name: str) -> dict:
    problem, out = run_import_tool(root, [str(target), "--check"], timeout=180)
    if problem:
        target.unlink(missing_ok=True)
        raise ValueError(problem)
    info = json.loads(out.strip().splitlines()[-1])
    info["file"] = name
    texture = model_texture(folder, "upload")
    if texture:
        info["texture_file"] = texture.name
    (folder / "upload.json").write_text(json.dumps(info), encoding="utf-8")
    if not info.get("ok"):
        target.unlink(missing_ok=True)
    return info


def upload_texture(cid: str, name: str, payload: str) -> dict:
    """A texture image for the uploaded model (for materials without one of their own); the
    check runs again with it."""
    root = project_root()
    folder = DATA / safe_id(cid)
    upload = model_upload(folder)
    if not root or not upload:
        raise ValueError("Upload a model first.")
    ext = Path(str(name)).suffix.lower()
    raw = base64.b64decode(payload, validate=True)
    if ext not in TEXTURE_TYPES or not raw.startswith(TEXTURE_TYPES[ext]):
        raise ValueError("Use a .png or .jpg image as the texture.")
    if len(raw) > MAX_UPLOAD:
        raise ValueError("This texture image is too large.")
    for old in folder.glob("texture-upload.*"):
        old.unlink()
    (folder / f"texture-upload{ext}").write_bytes(raw)
    old = json.loads((folder / "upload.json").read_text(encoding="utf-8")) if (folder / "upload.json").is_file() else {}
    return recheck_upload(root, folder, upload, old.get("file", upload.name))


def clean_parts(parts) -> dict:
    """The user's choices for parts that stick out: {id: {mode: fold|keep|remove, angle: 0-90 or None}}."""
    out = {}
    for k, v in (parts or {}).items() if isinstance(parts, dict) else ():
        if not str(k).isdigit() or not isinstance(v, dict) or v.get("mode") not in ("fold", "keep", "remove"):
            continue
        angle = v.get("angle")
        angle = None if angle is None else max(0.0, min(90.0, float(angle)))
        out[str(int(k))] = {"mode": v["mode"], "angle": angle}
    return out


def model_preview(cid: str, parts) -> dict:
    """PNG (base64) of the uploaded model with the parts' choices applied, side and back."""
    root = project_root()
    folder = DATA / safe_id(cid)
    upload = model_upload(folder)
    if not root or not upload:
        raise ValueError("Upload a model first.")
    out = folder / "preview.png"
    problem, text = run_import_tool(root, [str(upload), "--preview", str(out), "--parts", json.dumps(clean_parts(parts))], timeout=300)
    if problem or not out.is_file():
        raise ValueError(problem or "The preview could not be made.")
    png = base64.b64encode(out.read_bytes()).decode()
    out.unlink(missing_ok=True)
    angles = json.loads(text.strip().splitlines()[-1]).get("angles", {}) if text.strip() else {}
    return {"png": png, "angles": angles}


def source_preview(cid: str) -> dict:
    """PNG (base64) of an imported model's source file with its parts' choices: the "before" of
    the Model Importer (the 3D view shows the PS1 result). Cached in the cache folder."""
    root = project_root()
    folder = DATA / safe_id(cid)
    source = next((folder / f"source{e}" for e in MODEL_SOURCES if (folder / f"source{e}").is_file()), None)
    if not root or not source:
        raise ValueError("This fighter's model has no source file (a Character Builder body has none).")
    out = CACHE / f"source-preview-{folder.name}.png"
    if not out.is_file() or out.stat().st_mtime < source.stat().st_mtime:
        CACHE.mkdir(exist_ok=True)
        own = json.loads((folder / "character.json").read_text(encoding="utf-8")).get("own_model") or {}
        problem, _ = run_import_tool(root, [str(source), "--preview", str(out), "--parts",
                                            json.dumps(clean_parts(own.get("parts")))], timeout=300)
        if problem or not out.is_file():
            raise ValueError(problem or "The preview could not be made.")
    return {"png": base64.b64encode(out.read_bytes()).decode()}


def clean_import_settings(value) -> dict:
    """Model Importer settings for big models (reduced): {"head": 4|2|1, "detail": 100|80|60};
    the defaults are left out."""
    out = {}
    if isinstance(value, dict):
        if value.get("head") in (2, 1, "2", "1"):
            out["head"] = int(value["head"])
        if value.get("detail") in (80, 60, "80", "60"):
            out["detail"] = int(value["detail"])
    return out


def import_model(cid: str, costume: int, parts=None, on_line=None, settings=None) -> dict:
    """The checked upload -> characters/<id>/model.bin over the donor's costume model."""
    parts = clean_parts(parts)
    root = project_root()
    folder = DATA / safe_id(cid)
    character = get_character(folder.name)
    upload = model_upload(folder)
    info = json.loads((folder / "upload.json").read_text(encoding="utf-8")) if (folder / "upload.json").is_file() else {}
    if not upload:
        raise ValueError("Upload a model first.")
    if not info.get("rigged"):
        raise ValueError("This model is not rigged, so it cannot be imported. " + " ".join(info.get("problems", [])))
    donors = donor_models()
    if not donors.get("available"):
        raise ValueError(donors.get("reason", "The donor models are not available."))
    models = donors["donors"].get(str(character["donor"]), [])
    if not 0 <= costume < len(models):
        raise ValueError("This donor has no such costume.")
    out = folder / "model-new.bin"
    settings = clean_import_settings(settings)
    problem, text = run_import_tool(root, [str(upload), "--model", str(models[costume]), "--out", str(out),
                                           "--parts", json.dumps(parts), "--settings", json.dumps(settings)],
                                    on_line=on_line)
    if problem or not out.is_file():
        out.unlink(missing_ok=True)
        raise ValueError(problem or "The model import failed.")
    # the model it replaces is kept for "Undo import" (model-prev.bin, source-prev.*, model-prev.json)
    for old in folder.glob("source-prev.*"):
        old.unlink()
    (folder / "model-prev.bin").unlink(missing_ok=True)
    before = json.loads((folder / "character.json").read_text(encoding="utf-8")).get("own_model")
    for old in folder.glob("texture-prev.*"):
        old.unlink()
    if (folder / "model.bin").is_file():
        (folder / "model.bin").replace(folder / "model-prev.bin")
        for old in folder.glob("source.*"):
            old.replace(folder / f"source-prev{old.suffix}")
        move_texture(folder, "source", "prev")
    kept = before if (folder / "model-prev.bin").is_file() else None
    (folder / "model-prev.json").write_text(json.dumps({"own_model": kept}), encoding="utf-8")
    out.replace(folder / "model.bin")
    for old in folder.glob("source.*"):
        old.unlink()
    upload.replace(folder / f"source{upload.suffix}")
    move_texture(folder, "upload", "source")
    (folder / "upload.json").unlink(missing_ok=True)
    data = json.loads((folder / "character.json").read_text(encoding="utf-8"))
    made = re.findall(r"(\d+) triangles", text.strip().splitlines()[-1]) if text.strip() else []
    data["own_model"] = {"file": info.get("file", upload.name), "costume": costume, "model": models[costume],
                         "triangles": int(made[-1]) if made else info.get("triangles"),
                         "source_triangles": info.get("triangles"), "textured": info.get("textured"),
                         "parts": parts, "settings": settings, "imported": datetime.now().isoformat(timespec="seconds")}
    (folder / "character.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_character(folder.name)


PORTRAIT_LOOK = {"angle": ("turned", "front", "other", "profile"), "frame": ("shoulders", "close", "chest"),
                 "light": ("left", "front", "dramatic"), "backdrop": ("warm", "cool", "red", "dark", "stage")}


def own_portrait(cid: str, look=None) -> dict:
    """A select-screen portrait made from the fighter's own 3D model (PNG, base64). look: Portrait
    Lab presets {angle, frame, light, backdrop} (model_export.PORTRAIT_*)."""
    look = look if isinstance(look, dict) else {}
    clean = {k: look[k] for k, names in PORTRAIT_LOOK.items() if look.get(k) in names}
    root = project_root()
    source = DATA / safe_id(cid) / "model.bin"
    if not root:
        raise ValueError("Set the game folder first.")
    if not source.is_file():
        # no own model: the style's first costume as Tekken 3 draws it (cached, from the disc)
        if creator_patch.project_kind(root) != "expanded":
            raise ValueError("Portraits from the 3D model need Tekken 3 Expanded.")
        character = get_character(safe_id(cid))
        models = donor_models()["donors"].get(str(character.get("donor")), [])
        if not models:
            raise ValueError("Choose a fighting style first.")
        source = CACHE / "kit" / f"{models[0]}-stock.bin"
        if not source.is_file():
            source.parent.mkdir(parents=True, exist_ok=True)
            with model_lock:
                problem, _ = run_kitbash(root, models[0], {}, source)
            if problem or not source.is_file():
                raise ValueError(problem or "The style's model could not be read.")
    if clean.get("backdrop") == "stage":                 # the fighter's home stage in its colours
        character = get_character(safe_id(cid))
        if creator_patch.project_kind(root) != "expanded" or character.get("donor") is None:
            raise ValueError("The home stage background needs Tekken 3 Expanded and a fighting style.")
        image, _ = stage_view_file({"donor": character["donor"], "stage": character.get("stage"),
                                    "look": character.get("stage_look"), "tint": character.get("stage_tint"),
                                    "strength": character.get("stage_strength"), "view": "front"})
        clean["backdrop_image"] = str(image)
    out = CACHE / f"portrait-{safe_id(cid)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with model_lock:
        problem, _ = run_model_tool(root, ["ownportrait", "--file", str(source), "--out", str(out),
                                           "--look", json.dumps(clean)])
    if problem or not out.is_file():
        raise ValueError(problem or "The portrait could not be made.")
    png = base64.b64encode(out.read_bytes()).decode()
    out.unlink(missing_ok=True)
    return {"png": png}


def own_model_json(cid: str) -> bytes:
    """Mesh JSON of characters/<id>/model.bin for the 3D preview (cached per file version)."""
    root = project_root()
    source = DATA / cid / "model.bin"
    if not root or not source.is_file():
        raise ValueError("This fighter has no own model.")
    path = CACHE / "models" / f"own-{cid}-{int(source.stat().st_mtime)}-v{MODEL_FORMAT}.json"
    with model_lock:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob(f"own-{cid}-*.json"):
                old.unlink()
            problem, _ = run_model_tool(root, ["ownjson", "--file", str(source), "--out", str(path)])
            if problem:
                raise ValueError(problem)
    return path.read_bytes()


def refit_model(cid: str) -> list[str]:
    """After a style change: the own model was fitted to the old style's skeleton and the game
    only puts it over the model it was made for, so it is imported again from its source."""
    folder = DATA / safe_id(cid)
    info_path = folder / "character.json"
    data = json.loads(info_path.read_text(encoding="utf-8"))
    own = data.get("own_model")
    if not own or not (folder / "model.bin").is_file():
        return []
    donors = donor_models()
    models = donors.get("donors", {}).get(str(data["donor"]), []) if donors.get("available") else []
    if not models:
        return []
    costume = min(int(own.get("costume", 0)), len(models) - 1)
    if own.get("model") == models[costume]:
        return []
    source = next((folder / f"source{e}" for e in MODEL_SOURCES if (folder / f"source{e}").is_file()), None)
    if not source:
        return ["The own model was made for another fighting style and has no source file to fit "
                "it again: upload it again on the 3D model page."]
    out = folder / "model-new.bin"
    with model_lock:
        problem, _ = run_import_tool(project_root(), [str(source), "--model", str(models[costume]), "--out", str(out),
                                                      "--parts", json.dumps(clean_parts(own.get("parts"))),
                                                      "--settings", json.dumps(clean_import_settings(own.get("settings")))])
    if problem or not out.is_file():
        out.unlink(missing_ok=True)
        return [f"The own model could not be fitted to the new fighting style: {problem}"]
    out.replace(folder / "model.bin")
    own.update(costume=costume, model=models[costume], imported=datetime.now().isoformat(timespec="seconds"))
    data["own_model"] = own
    info_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return []


def undo_model(cid: str) -> dict:
    """Back to the model the last import replaced (or to none, after a first import)."""
    folder = DATA / safe_id(cid)
    memo = folder / "model-prev.json"
    if not memo.is_file():
        raise ValueError("There is no import to undo.")
    before = json.loads(memo.read_text(encoding="utf-8")).get("own_model")
    if before is None or not (folder / "model-prev.bin").is_file():
        return remove_model(cid)
    (folder / "model-prev.bin").replace(folder / "model.bin")
    for old in folder.glob("source.*"):
        old.unlink()
    for old in folder.glob("source-prev.*"):
        old.replace(folder / f"source{old.suffix}")
    move_texture(folder, "prev", "source")
    memo.unlink()
    info = folder / "character.json"
    data = json.loads(info.read_text(encoding="utf-8"))
    data["own_model"] = before
    info.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_character(folder.name)


# ------------------------------------------------------------- move lab --

def command_list(donor) -> dict:
    """The style's COMMAND LIST as the game shows it, read from the player's disc (cached)."""
    try:
        donor = int(donor)
    except (TypeError, ValueError):
        raise ValueError("Choose a fighting style.") from None
    donors = donor_models()
    if not donors.get("available"):
        raise ValueError(donors.get("reason", "The fighters' data is not available."))
    models = donors["donors"].get(str(donor))
    if not models:
        raise ValueError("That style does not exist.")
    own = zlib.crc32(repr((sorted(command_list_module.OWN_MOVES.get(donor, {}).items()),
                           sorted(command_list_module.STRINGS.get(donor, {}).items()))).encode())
    path = CACHE / f"commandlist8-{models[0]}-{donor}-{own:08x}.json"   # the measured table is in the name
    if not path.is_file():
        problem, out = run_model_tool(project_root(), ["commandlist", "--model", str(models[0]), "--style", str(donor)],
                                      timeout=120)
        if problem:
            raise ValueError(problem)
        CACHE.mkdir(exist_ok=True)
        path.write_text(out.strip().splitlines()[-1], encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"donor": donor, "moves": data["moves"], "basic": data["basic"], "own": data.get("own", {}),
            "records": data["records"], "key": data["key"], "slots": data.get("slots", {}),
            "movable": data.get("movable", []), "poses": data.get("poses", {}),
            "pose_slots": data.get("pose_slots", {})}


def cast_damage() -> dict:
    """The cast's damage per style, the fairness check's yardstick (model_export cast, cached)."""
    path = CACHE / "cast1.json"
    if not path.is_file():
        root = project_root()
        if not root:
            raise ValueError("The cast's damage needs the game folder.")
        problem, out = run_model_tool(root, ["cast"], timeout=120)
        if problem:
            raise ValueError(problem)
        CACHE.mkdir(exist_ok=True)
        path.write_text(out.strip().splitlines()[-1], encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def fairness_check(donor, move_damage=None, move_buttons=None) -> dict:
    """The traffic lights of a fighter's moves (fairness.check) against Tekken 3's cast."""
    return fairness.check(cast_damage(), command_list(donor), move_damage, move_buttons)


# --------------------------------------------------- character builder --

KIT_PARTS = ("head", "body", "arm_l", "arm_r", "leg_l", "leg_r", "hands")   # kitbash.PARTS


def kit_models() -> list[int]:
    """The fighter models a body part can come from: every costume model of the 21 styles."""
    donors = donor_models()
    if not donors.get("available"):
        raise ValueError(donors.get("reason", "The fighters' models are not available."))
    return sorted({m for models in donors["donors"].values() for m in models})


KIT_FIT = 0.07                                   # kitbash.FIT: parts of a similar build only


def kit_heights() -> dict:
    """{model: standing height} of every kit model, measured once (kitbash.py --heights), cached."""
    path = CACHE / "kit-heights.json"
    if not path.is_file():
        root = project_root()
        try:
            done = subprocess.run([venv_python(root), str(APP / "kitbash.py"), "--root", str(root), "--heights",
                                   *map(str, kit_models())], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=300, creationflags=NO_WINDOW, cwd=str(APP))
            heights = json.loads(done.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            raise ValueError("The fighters' sizes could not be measured.") from None
        CACHE.mkdir(exist_ok=True)
        path.write_text(json.dumps(heights), encoding="utf-8")
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def clean_kit(parts) -> dict:
    """{part: model} for the body parts taken from another fighter (the rest stays the style's)."""
    if not isinstance(parts, dict) or not any(parts.get(name) not in (None, "", -1) for name in KIT_PARTS):
        return {}
    allowed = set(kit_models())
    out = {}
    for name in KIT_PARTS:
        value = parts.get(name)
        if value in (None, "", -1):
            continue
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Unknown model for {name}.") from None
        if value not in allowed:
            raise ValueError(f"Unknown model for {name}.")
        out[name] = value
    return out


def clean_kit_colours(value) -> list | None:
    """The mix's own colours: [hue -180..180, saturation 0..200 %, lightness -40..40, keep skin],
    or None for the parts' own colours."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        h, s_, l, keep = int(value[0]), int(value[1]), int(value[2]), bool(value[3])
    except (TypeError, ValueError):
        raise ValueError("Invalid body colours.") from None
    h, s_, l = max(-180, min(180, h)), max(0, min(200, s_)), max(-40, min(40, l))
    return None if (h, s_, l) == (0, 100, 0) else [h, s_, l, keep]


PIECES_MAX = 40


def clean_kit_pieces(value) -> dict:
    """Pieces of clothing in their own colours: {"model:clut": [hue -180..180, saturation 0..200,
    lightness -40..40]} (kitbash.list_pieces names the keys); unchanged pieces are left out."""
    out = {}
    for key, v in (value or {}).items() if isinstance(value, dict) else ():
        if not re.fullmatch(r"\d{1,2}:\d{1,3}", str(key)) or not isinstance(v, (list, tuple)) or len(v) != 3:
            continue
        try:
            h, s_, l = int(v[0]), int(v[1]), int(v[2])
        except (TypeError, ValueError):
            raise ValueError("Invalid piece colours.") from None
        h, s_, l = max(-180, min(180, h)), max(0, min(200, s_)), max(-40, min(40, l))
        if (h, s_, l) != (0, 100, 0):
            out[str(key)] = [h, s_, l]
        if len(out) >= PIECES_MAX:
            break
    return out


# body shape: {name: (lowest, highest)} factor, as kitbash.SHAPES (head on all axes; arms, legs
# and body across the bone)
KIT_SHAPES = {"head": (0.85, 1.3), "arms": (0.8, 1.3), "legs": (0.8, 1.3), "body": (0.85, 1.25)}


def clean_kit_shape(value) -> dict:
    """{name: factor} within KIT_SHAPES; factors of 1 are left out."""
    out = {}
    for name, f in (value or {}).items() if isinstance(value, dict) else ():
        if name not in KIT_SHAPES:
            continue
        try:
            f = round(float(f), 2)
        except (TypeError, ValueError):
            raise ValueError("Invalid body shape.") from None
        lo, hi = KIT_SHAPES[name]
        f = max(lo, min(hi, f))
        if f != 1:
            out[name] = f
    return out


def run_kitbash(root: Path, base: int, kit: dict, out: Path, colours: list | None = None,
                shape: dict | None = None, pieces: dict | None = None) -> tuple[str | None, str]:
    """kitbash.py: the style's model with body parts of other fighters -> own model file."""
    args = [venv_python(root), str(APP / "kitbash.py"), "--root", str(root), "--base", str(base), "--out", str(out)]
    if pieces:
        args.append("--pieces=" + json.dumps(pieces, separators=(",", ":")))
    if shape:
        args.append("--shape=" + json.dumps(shape, separators=(",", ":")))
    if colours:
        args.append(f"--colours={colours[0]},{colours[1]},{colours[2]},{int(colours[3])}")   # = : a hue can be negative
    for name, model in kit.items():
        args += ["--part", f"{name}={model}"]
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, creationflags=NO_WINDOW, cwd=str(APP))
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"The character builder could not run: {error}", ""
    if done.returncode:
        lines = (done.stdout + done.stderr).strip().splitlines()
        last = lines[-1] if lines else "The character builder failed."
        return (last[7:] if last.startswith("ERROR: ") else last), ""
    return None, done.stdout


# saved looks: a body-part mix with its colours and shape under a name, for any fighter (looks.json)
LOOKS_FILE = BASE / "looks.json"
LOOKS_MAX = 40


def list_looks() -> list[dict]:
    try:
        looks = json.loads(LOOKS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [l for l in looks if isinstance(l, dict) and isinstance(l.get("name"), str)][:LOOKS_MAX]


def save_look(name: str, donor, parts, colours=None, shape=None, pieces=None) -> list[dict]:
    name = re.sub(r"[^\w .\-]", "", str(name or "")).strip()[:32]
    if not name:
        raise ValueError("Give the look a name.")
    kit, colours, shape = clean_kit(parts), clean_kit_colours(colours), clean_kit_shape(shape)
    if not kit and not colours and not shape:
        raise ValueError("Choose body parts, colours or a body shape first.")
    look = {"name": name, "donor": donor if isinstance(donor, int) and 0 <= donor <= 20 else None,
            "kit": kit, "colours": colours, "shape": shape, "pieces": clean_kit_pieces(pieces)}
    looks = [l for l in list_looks() if l["name"] != name]
    if len(looks) >= LOOKS_MAX:
        raise ValueError(f"At most {LOOKS_MAX} saved looks: delete one first.")
    looks.append(look)
    LOOKS_FILE.write_text(json.dumps(looks, indent=1), encoding="utf-8")
    return looks


def delete_look(name: str) -> list[dict]:
    looks = [l for l in list_looks() if l["name"] != name]
    LOOKS_FILE.write_text(json.dumps(looks, indent=1), encoding="utf-8")
    return looks


def kit_preview(cid: str, costume: int, parts, colours=None, shape=None, pieces=None) -> bytes:
    """Mesh JSON of a body-part mix for the 3D view, built in the cache only: the fighter's own
    model is not touched. Refusals (build, colours, texture page) come back as the error."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("The character builder needs Tekken 3 Expanded.")
    kit, colours, shape = clean_kit(parts), clean_kit_colours(colours), clean_kit_shape(shape)
    if not kit and not colours and not shape:
        raise ValueError("Choose a body part from another fighter, colours or a body shape.")
    character = get_character(safe_id(cid))
    models = donor_models()["donors"].get(str(character["donor"]), [])
    if not 0 <= costume < len(models):
        raise ValueError("This style has no such costume.")
    pieces = clean_kit_pieces(pieces)
    key = "-".join(f"{k}{v}" for k, v in sorted(kit.items())) + ("-c" + "_".join(map(str, colours)) if colours else "")
    key += f"-p{zlib.crc32(json.dumps(pieces, sort_keys=True).encode()):08x}" if pieces else ""         + ("-s" + "_".join(f"{k}{v}" for k, v in sorted(shape.items())) if shape else "")
    out = CACHE / "kit" / f"{models[costume]}-{key}.bin"
    js = out.with_suffix(".json")
    with model_lock:
        if not js.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            problem, text = run_kitbash(root, models[costume], kit, out, colours, shape, pieces)
            if problem or not out.is_file():
                raise ValueError(problem or "The character builder failed.")
            problem, _ = run_model_tool(root, ["ownjson", "--file", str(out), "--out", str(js)])
            if problem:
                raise ValueError(problem)
            if "textures at half size" in text:       # kitbash halved some areas to fit one page
                mesh = json.loads(js.read_text(encoding="utf-8"))
                mesh["half_textures"] = True
                js.write_text(json.dumps(mesh), encoding="utf-8")
    return js.read_bytes()


def kit_pieces(cid: str, costume: int, parts) -> list[dict]:
    """The pieces of clothing of a body-part mix (kitbash --list-pieces, cached)."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("The character builder needs Tekken 3 Expanded.")
    kit = clean_kit(parts)
    character = get_character(safe_id(cid))
    models = donor_models()["donors"].get(str(character["donor"]), [])
    if not 0 <= costume < len(models):
        raise ValueError("This style has no such costume.")
    key = "-".join(f"{k}{v}" for k, v in sorted(kit.items()))
    path = CACHE / "kit" / f"pieces-{models[costume]}-{key}.json"
    if not path.is_file():
        args = [venv_python(root), str(APP / "kitbash.py"), "--root", str(root), "--base", str(models[costume]),
                "--list-pieces"] + [a for name, model in kit.items() for a in ("--part", f"{name}={model}")]
        try:
            done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=120, creationflags=NO_WINDOW, cwd=str(APP))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"The character builder could not run: {error}") from None
        if done.returncode:
            raise ValueError("The pieces of clothing could not be read.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(done.stdout.strip().splitlines()[-1], encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def build_kit(cid: str, costume: int, parts, keep_undo: bool = True, colours=None, shape=None, pieces=None) -> dict:
    """A model built from Tekken 3's own fighters' body parts (read from the player's disc) over
    the style's costume: characters/<id>/model.bin, own_model {"kit": {...}}. Like an import, the
    model it replaces can be restored with Undo."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("The character builder needs Tekken 3 Expanded.")
    kit, colours, shape = clean_kit(parts), clean_kit_colours(colours), clean_kit_shape(shape)
    if not kit and not colours and not shape:
        raise ValueError("Choose a body part from another fighter, colours or a body shape.")
    folder = DATA / safe_id(cid)
    character = get_character(folder.name)
    models = donor_models()["donors"].get(str(character["donor"]), [])
    if not 0 <= costume < len(models):
        raise ValueError("This style has no such costume.")
    out = folder / "model-new.bin"
    pieces = clean_kit_pieces(pieces)
    with model_lock:
        problem, text = run_kitbash(root, models[costume], kit, out, colours, shape, pieces)
    if problem or not out.is_file():
        out.unlink(missing_ok=True)
        raise ValueError(problem or "The character builder failed.")
    data = json.loads((folder / "character.json").read_text(encoding="utf-8"))
    if keep_undo:                                     # as import_model: the old model for Undo
        for old in folder.glob("source-prev.*"):
            old.unlink()
        (folder / "model-prev.bin").unlink(missing_ok=True)
        before = data.get("own_model")
        if (folder / "model.bin").is_file():
            (folder / "model.bin").replace(folder / "model-prev.bin")
            for old in folder.glob("source.*"):
                old.replace(folder / f"source-prev{old.suffix}")
        kept = before if (folder / "model-prev.bin").is_file() else None
        (folder / "model-prev.json").write_text(json.dumps({"own_model": kept}), encoding="utf-8")
    for old in folder.glob("source.*"):               # a built model has no source file
        old.unlink()
    out.replace(folder / "model.bin")
    made = re.findall(r"(\d+) triangles", text.strip().splitlines()[-1]) if text.strip() else []
    data["own_model"] = {"file": "Character Builder", "kit": kit, "colours": colours, "shape": shape, "pieces": pieces,
                         "half_textures": "textures at half size" in text, "costume": costume,
                         "model": models[costume],
                         "triangles": int(made[-1]) if made else None, "textured": True,
                         "imported": datetime.now().isoformat(timespec="seconds")}
    (folder / "character.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_character(folder.name)


# imports run in the background so the page can show their progress: {id: job}
IMPORT_JOBS: dict = {}


def start_import(cid: str, costume: int, parts, settings=None) -> dict:
    cid = safe_id(cid)
    job = IMPORT_JOBS.get(cid)
    if job and not job["done"]:
        raise ValueError("This fighter's model is being imported already.")
    job = IMPORT_JOBS[cid] = {"lines": [], "done": False, "error": None, "result": None, "started": time.time()}

    def run():
        try:
            with model_lock:
                saved = import_model(cid, costume, parts, on_line=lambda l: job["lines"].append(l[:200]),
                                     settings=settings)
            job["result"] = {**saved, "warnings": sync_customs(changed=saved["id"])}
        except Exception as error:                   # shown on the page, as a request error would be
            job["error"] = str(error) or "The model import failed."
        job["done"] = True
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


def import_progress(cid: str) -> dict:
    job = IMPORT_JOBS.get(safe_id(cid))
    if not job:
        raise ValueError("No import is running for this fighter.")
    return {"lines": job["lines"][-8:], "done": job["done"], "error": job["error"], "result": job["result"],
            "seconds": round(time.time() - job["started"])}


def remove_model(cid: str) -> dict:
    folder = DATA / safe_id(cid)
    for name in ("model.bin", "model-new.bin", "upload.json", "model-prev.bin", "model-prev.json"):
        (folder / name).unlink(missing_ok=True)
    for pattern in ("source.*", "upload.*", "source-prev.*", "texture-*.*"):
        for old in folder.glob(pattern):
            old.unlink()
    info = folder / "character.json"
    data = json.loads(info.read_text(encoding="utf-8"))
    data.pop("own_model", None)
    info.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_character(folder.name)


MODEL_FORMAT = 7   # model_export.py output; 7 = per-triangle body row (garment names)


def model_json(model: int) -> bytes:
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        raise ValueError("The 3D preview needs Tekken 3 Expanded.")
    if not 0 <= model < 52:
        raise ValueError("No such model.")
    path = CACHE / "models" / f"model-{model}-v{MODEL_FORMAT}.json"
    with model_lock:
        if not path.is_file():
            for old in path.parent.glob(f"model-{model}.json"):   # format 1 (one pose), replaced
                old.unlink(missing_ok=True)
            for old in path.parent.glob(f"model-{model}-v*.json"):
                old.unlink(missing_ok=True)
            problem, _ = run_model_tool(root, ["model", "--model", str(model), "--out", str(path)])
            if problem:
                raise ValueError(problem)
    return path.read_bytes()


def unlinked_fighters() -> list[dict]:
    """Fighters on the CUSTOM page that are not in this builder's library."""
    root = project_root()
    if not root or creator_patch.project_kind(root) != "expanded":
        return []
    library = {game_key(c["id"]) for c in character_list()}
    result = []
    for key, donor in custom_page.read_entries(root)[0]:
        if key in library:
            continue
        jui = custom_page.find_file(root, key, "-ui.jui")
        stamp = int(jui.stat().st_mtime) if jui else 0
        result.append({"key": key, "donor": donor, "name": custom_page.read_label(root, key) or key[2:].upper(),
                       "files": jui is not None,
                       "portrait": f"/unlinked/{key}.png?v={stamp}" if jui else None})
    return result


def unlinked_key(value: str) -> str:
    key = str(value or "")
    if not custom_page.KEY_RE.fullmatch(key) or key not in {u["key"] for u in unlinked_fighters()}:
        raise ValueError("This fighter is not on the Custom page, or it is already in your library.")
    return key


def adopt_unlinked(key: str) -> dict:
    """Adds a Custom page fighter to the library under the same key, keeping its place."""
    root = project_root()
    item = next(u for u in unlinked_fighters() if u["key"] == key)
    name = item["name"].upper().strip()
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"{item['name']} cannot be used as a name in Tekken 3's name font.")
    folder = DATA / key[2:]  # game_key(folder name) gives this key back
    if folder.exists():
        raise ValueError(f"The folder characters/{folder.name} already exists. Move it away first.")
    rows = custom_page.read_portrait(root, key)
    folder.mkdir(parents=True)
    now = datetime.now().isoformat(timespec="seconds")
    record = {"format": 1, "builder": APP_VERSION, "created": now, "updated": now, "name": name,
              "donor": item["donor"], "author": "", "slot_mode": "jun-slot-23",
              "adopted": {"key": key, "portrait": "from the game's pack" if rows else "none"}}
    if rows:
        full = custom_page.png(custom_page.stretch(rows, custom_page.SHOWN_W))
        (folder / "portrait-ps1.png").write_bytes(custom_page.png(rows))
        (folder / "portrait-full.png").write_bytes(full)
        (folder / "portrait.png").write_bytes(full)
    (folder / "character.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return get_character(folder.name)


def get_character(cid: str) -> dict:
    for c in character_list():
        if c["id"] == cid:
            return c
    raise ValueError("Character not found.")


def save_character(data: dict) -> dict:
    clean = validate_character(data)
    cid = data.get("id")
    if cid:
        folder = DATA / safe_id(cid)
        if not folder.is_dir():
            raise ValueError("Character not found.")
    else:
        base, n = slugify(clean["name"]), 1
        folder = DATA / base
        while folder.exists():
            n += 1
            folder = DATA / f"{base}-{n}"
        folder.mkdir(parents=True)
    info = folder / "character.json"
    old = {}
    if info.is_file():
        old = json.loads(info.read_text(encoding="utf-8"))
    now = datetime.now().isoformat(timespec="seconds")
    record = {"format": 1, "builder": APP_VERSION, "created": old.get("created", now),
              "updated": now, **clean, "slot_mode": "jun-slot-23",
              "costumes": validate_costumes(data["costumes"]) if "costumes" in data else old.get("costumes", [])}
    if old.get("own_model") and (folder / "model.bin").is_file():
        record["own_model"] = old["own_model"]          # set only by import_model / remove_model
    if record.get("donor") is not None:                 # the fairness status, carried in packages
        try:
            check = fairness_check(record["donor"], record.get("move_damage"), record.get("move_buttons"))
            record["fairness"] = {"light": check["light"], "label": check["label"]}
        except ValueError:
            pass                                        # no disc data: no status
    recording = decode_wav(data.get("name_call_wav"))
    if recording:
        (folder / "namecall.wav").write_bytes(recording)
    if record["name_call"] == "own" and not (folder / "namecall.wav").is_file():
        record["name_call"] = "off"                     # nothing recorded yet
    for key, filename in (("portrait_source", "portrait.png"), ("portrait_ps1", "portrait-ps1.png"),
                          ("portrait_full", "portrait-full.png")):
        png = decode_png(data.get(key))
        if png:
            (folder / filename).write_bytes(png)
    if old:                                           # the version this save replaces: a restore point
        keep_restore_point(folder, old)
    info.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return get_character(folder.name)


RESTORE_POINTS = 20
RESTORE_FIELDS = ("name", "donor", "author", "stage", "music", "name_call", "name_call_voice", "stage_look",
                  "costumes", "credits", "move_damage", "move_buttons", "rival", "cpu", "poses", "guest_style")


def keep_restore_point(folder: Path, record: dict) -> None:
    """characters/<id>/history/<time>.json: a fighter's settings before a save (the last 20).
    Settings only: the 3D model has its own Undo, files such as the portrait are not kept."""
    history = folder / "history"
    history.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    (history / f"{stamp}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    for old in sorted(history.glob("*.json"))[:-RESTORE_POINTS]:
        old.unlink()


def restore_points(cid: str) -> list[dict]:
    """The fighter's restore points, newest first: {id, saved, name, donor}."""
    history = DATA / safe_id(cid) / "history"
    out = []
    for path in sorted(history.glob("*.json"), reverse=True) if history.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": path.stem, "saved": data.get("updated", ""), "name": data.get("name", ""),
                    "donor": data.get("donor")})
    return out


def restore_character(cid: str, point: str) -> dict:
    """Saves the settings of a restore point as the fighter's current ones (the current ones
    become a restore point themselves, so a restore can be undone)."""
    folder = DATA / safe_id(cid)
    if not re.fullmatch(r"[0-9-]{8,40}", point or ""):
        raise ValueError("Unknown restore point.")
    path = folder / "history" / f"{point}.json"
    if not path.is_file():
        raise ValueError("Unknown restore point.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return save_character({"id": folder.name, **{k: data[k] for k in RESTORE_FIELDS if k in data}})


PORTRAIT_FILES = ("portrait.png", "portrait-ps1.png", "portrait-full.png")
PORTRAIT_VARIANTS = 12


def _portrait_variant_dir(folder: Path, vid: str) -> Path:
    if not re.fullmatch(r"[0-9-]{8,40}", vid or ""):
        raise ValueError("Unknown portrait.")
    path = folder / "portraits" / vid
    if not (path / "portrait-ps1.png").is_file():
        raise ValueError("Unknown portrait.")
    return path


def _same_portrait(folder: Path, variant: Path) -> bool:
    return (folder / "portrait-ps1.png").read_bytes() == (variant / "portrait-ps1.png").read_bytes()


def portrait_variants(cid: str) -> list[dict]:
    """The fighter's saved portraits, newest first: {id, image, current}."""
    folder = DATA / safe_id(cid)
    root = folder / "portraits"
    out = []
    for path in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        if (path / "portrait-ps1.png").is_file() and re.fullmatch(r"[0-9-]{8,40}", path.name):
            current = (folder / "portrait-ps1.png").is_file() and _same_portrait(folder, path)
            out.append({"id": path.name, "image": f"/characters/{folder.name}/portraits/{path.name}/portrait-ps1.png",
                        "current": current})
    return out


def keep_portrait(cid: str) -> list[dict]:
    """Saves the fighter's current portrait (all three files) as a variant, unless it is saved
    already; the oldest variants go beyond PORTRAIT_VARIANTS."""
    folder = DATA / safe_id(cid)
    if not (folder / "portrait-ps1.png").is_file():
        raise ValueError("This fighter has no portrait yet: choose an image or make one from the 3D model, then Save.")
    root = folder / "portraits"
    if root.is_dir() and any(_same_portrait(folder, p) for p in root.iterdir() if (p / "portrait-ps1.png").is_file()):
        return portrait_variants(cid)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = root / stamp
    n = 1
    while target.exists():
        n += 1
        target = root / f"{stamp}-{n}"
    target.mkdir(parents=True)
    for name in PORTRAIT_FILES:
        if (folder / name).is_file():
            shutil.copyfile(folder / name, target / name)
    for old in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)[PORTRAIT_VARIANTS:]:
        shutil.rmtree(old)
    return portrait_variants(cid)


def use_portrait(cid: str, vid: str) -> dict:
    """Makes a saved variant the fighter's portrait. The current one is saved as a variant first,
    so nothing is lost."""
    folder = DATA / safe_id(cid)
    variant = _portrait_variant_dir(folder, vid)
    if (folder / "portrait-ps1.png").is_file():
        keep_portrait(cid)
    for name in PORTRAIT_FILES:
        if (variant / name).is_file():
            shutil.copyfile(variant / name, folder / name)
        elif name == "portrait-full.png":
            (folder / name).unlink(missing_ok=True)   # the game pack falls back to portrait.png
    return get_character(folder.name)


def drop_portrait(cid: str, vid: str) -> list[dict]:
    folder = DATA / safe_id(cid)
    shutil.rmtree(_portrait_variant_dir(folder, vid))
    return portrait_variants(cid)


def delete_character(cid: str) -> None:
    folder = DATA / safe_id(cid)
    if folder.is_dir():
        shutil.rmtree(folder)


def export_character(cid: str) -> tuple[str, bytes]:
    folder = DATA / safe_id(cid)
    if not (folder / "character.json").is_file():
        raise ValueError("Character not found.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("character.json", "portrait.png", "portrait-ps1.png", "portrait-full.png", "namecall.wav"):
            if (folder / name).is_file():
                z.write(folder / name, name)
        for variant in portrait_variants(folder.name):   # saved portraits travel along
            for name in PORTRAIT_FILES:
                path = folder / "portraits" / variant["id"] / name
                if path.is_file():
                    z.write(path, f"portraits/{variant['id']}/{name}")
        # an own 3D model travels as its source file (the user's own work) with the choices in
        # character.json; model.bin holds parts of the disc's donor model and never leaves
        source = next((folder / f"source{e}" for e in MODEL_SOURCES if (folder / f"source{e}").is_file()), None)
        if source:
            z.write(source, source.name)
            texture = model_texture(folder, "source")     # its texture image, if one was chosen
            if texture:
                z.write(texture, texture.name)
    return f"{folder.name}.t3char", buffer.getvalue()


def fit_source(cid: str, source: Path, costume: int, parts: dict, label: str, settings=None) -> list[str]:
    """An own model built from a source file already next to the character (an imported package):
    model.bin over the style's costume, own_model in character.json. -> warnings."""
    root = project_root()
    folder = DATA / safe_id(cid)
    if not root or creator_patch.project_kind(root) != "expanded":
        return ["The package has its own 3D model; it is built once you use Tekken 3 Expanded."]
    data = json.loads((folder / "character.json").read_text(encoding="utf-8"))
    donors = donor_models()
    models = donors.get("donors", {}).get(str(data["donor"]), []) if donors.get("available") else []
    if not models:
        return ["The package's 3D model could not be built: " + donors.get("reason", "no donor models.")]
    costume = max(0, min(int(costume), len(models) - 1))
    out = folder / "model-new.bin"
    with model_lock:
        problem, text = run_import_tool(root, [str(source), "--model", str(models[costume]), "--out", str(out),
                                               "--parts", json.dumps(clean_parts(parts)),
                                               "--settings", json.dumps(clean_import_settings(settings))])
    if problem or not out.is_file():
        out.unlink(missing_ok=True)
        return [f"The package's 3D model could not be built: {problem or 'the import failed.'}"]
    out.replace(folder / "model.bin")
    made = re.findall(r"(\d+) triangles", text.strip().splitlines()[-1]) if text.strip() else []
    data["own_model"] = {"file": label, "costume": costume, "model": models[costume],
                         "triangles": int(made[-1]) if made else None, "textured": True,
                         "parts": clean_parts(parts), "settings": clean_import_settings(settings), "imported": datetime.now().isoformat(timespec="seconds")}
    (folder / "character.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return []


def backup_packages(payload: str) -> list[bytes] | None:
    """The .t3char packages of a .t3backup (a zip holding only packages), or None."""
    raw = base64.b64decode(payload, validate=True)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None
    with z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        if not names or not all(n.endswith(".t3char") and "/" not in n for n in names):
            return None
        if len(names) > 200 or any(i.file_size > MAX_IMPORT for i in z.infolist()):
            raise ValueError("This backup holds too many or too large packages.")
        return [z.read(n) for n in names]


def import_character(payload: str) -> dict:
    raw = base64.b64decode(payload, validate=True)
    if len(raw) > MAX_IMPORT:
        raise ValueError("This package is too large.")
    allowed = {"character.json", "portrait.png", "portrait-ps1.png", "portrait-full.png", "namecall.wav",
               "source.fbx", "source.glb", "source.vrm", *(f"texture-source{e}" for e in TEXTURE_TYPES)}
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("This is not a valid .t3char package.") from None
    files = {}
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            variant = re.fullmatch(r"portraits/([0-9-]{8,40})/(portrait|portrait-ps1|portrait-full)\.png", info.filename)
            if info.filename not in allowed and not variant:
                raise ValueError(f"Unexpected file in package: {info.filename}. "
                                 "Packages may only contain a description, images and a 3D model source.")
            if info.file_size > (MAX_IMPORT if info.filename.startswith("source.") else MAX_UPLOAD):
                raise ValueError("A file in the package is too large.")
            files[info.filename] = z.read(info)
    if sum(1 for n in files if n.startswith("portraits/")) > PORTRAIT_VARIANTS * len(PORTRAIT_FILES):
        raise ValueError("The package holds too many saved portraits.")
    if "character.json" not in files:
        raise ValueError("The package is missing character.json.")
    try:
        data = json.loads(files["character.json"].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("character.json is damaged.") from None
    for name in files:
        if name.endswith(".png") and not files[name].startswith(PNG_SIGNATURE):
            raise ValueError(f"{name} is not a valid PNG.")
    if "source.fbx" in files and not files["source.fbx"].startswith(b"Kaydara FBX Binary"):
        raise ValueError("source.fbx is not an FBX Binary file.")
    if "source.glb" in files and not files["source.glb"].startswith(b"glTF"):
        raise ValueError("source.glb is not a glTF binary file.")
    if "source.vrm" in files and not files["source.vrm"].startswith(b"glTF"):
        raise ValueError("source.vrm is not a VRM (glTF binary) file.")
    record = {**validate_character(data), "costumes": validate_costumes(data.get("costumes"))}
    if "namecall.wav" in files:
        record["name_call_wav"] = "data:audio/wav;base64," + base64.b64encode(files["namecall.wav"]).decode()
    for key, name in (("portrait_source", "portrait.png"), ("portrait_ps1", "portrait-ps1.png"),
                      ("portrait_full", "portrait-full.png")):
        if name in files:
            record[key] = "data:image/png;base64," + base64.b64encode(files[name]).decode()
    saved = save_character(record)
    for name, raw in files.items():                    # saved portraits (names checked above)
        if name.startswith("portraits/"):
            path = DATA / saved["id"] / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    name = next((n for n in ("source.fbx", "source.glb", "source.vrm") if n in files), None)
    own = data.get("own_model") if isinstance(data.get("own_model"), dict) else {}
    if not name and (own.get("kit") or own.get("colours") or own.get("shape") or own.get("pieces")):   # a Character Builder model: rebuilt from the choices
        try:
            built = build_kit(saved["id"], int(own.get("costume", 0) or 0), own.get("kit") or {}, keep_undo=False,
                              colours=own.get("colours"), shape=own.get("shape"), pieces=own.get("pieces"))
            return {**built, "model_warnings": []}
        except ValueError as error:
            return {**saved, "model_warnings": [f"The package's body parts could not be built: {error}"]}
    if not name:
        return saved
    folder = DATA / saved["id"]
    (folder / name).write_bytes(files[name])
    for ext, magic in TEXTURE_TYPES.items():              # the model's texture image (checked)
        texture = files.get(f"texture-source{ext}")
        if texture and texture.startswith(magic):
            (folder / f"texture-source{ext}").write_bytes(texture)
    own = data.get("own_model") if isinstance(data.get("own_model"), dict) else {}
    warnings = fit_source(saved["id"], folder / name, int(own.get("costume", 0) or 0), own.get("parts") or {},
                          str(own.get("file") or name)[:80], own.get("settings"))
    return {**get_character(saved["id"]), "model_warnings": warnings}


# ----------------------------------------------------------------- server --

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8", ".png": "image/png",
                 ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    server_version = "T3CharacterBuilder"

    def log_message(self, fmt, *args):  # stille console
        pass

    def _allowed_host(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _error(self, message: str, status: int = 400):
        self._json({"error": message}, status)

    def do_GET(self):
        if not self._allowed_host():
            return self._error("Forbidden host.", 403)
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            html = (UI / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN)
            html = html.replace("{{VERSION}}", APP_VERSION)
            return self._send(200, html.encode(), CONTENT_TYPES[".html"],
                              {"Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; "
                               "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                               "script-src 'self'"})
        if path.startswith("/ui/"):
            target = (UI / path[4:]).resolve()
            if UI in target.parents and target.is_file():
                return self._send(200, target.read_bytes(),
                                  CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            return self._error("Not found.", 404)
        if path.startswith("/characters/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[3] in ("portrait.png", "portrait-ps1.png") or (
                    len(parts) == 6 and parts[3] == "portraits" and re.fullmatch(r"[0-9-]{8,40}", parts[4])
                    and parts[5] == "portrait-ps1.png"):
                try:
                    target = DATA / safe_id(parts[2]) / "/".join(parts[3:])
                except ValueError:
                    return self._error("Not found.", 404)
                if target.is_file():
                    return self._send(200, target.read_bytes(), "image/png")
            return self._error("Not found.", 404)
        if path == "/api/backup":
            filename, data = backup_all()
            return self._send(200, data, "application/zip",
                              {"Content-Disposition": f'attachment; filename="{filename}"'})
        if path.startswith("/api/export/"):
            try:
                filename, data = export_character(path.rsplit("/", 1)[1])
            except ValueError as error:
                return self._error(str(error), 404)
            return self._send(200, data, "application/zip",
                              {"Content-Disposition": f'attachment; filename="{filename}"'})
        if path == "/api/status":
            return self._json({**project_status(), "app": APP_VERSION})
        if path == "/api/characters":
            return self._json(character_list())
        if path == "/api/models":
            return self._json(donor_models())
        if path.startswith("/api/ownmodel/"):
            try:
                body = own_model_json(safe_id(path.rsplit("/", 1)[1]))
            except ValueError as error:
                return self._error(str(error))
            return self._send(200, body, "application/json")
        if path.startswith("/api/model/"):
            try:
                body = model_json(int(path.rsplit("/", 1)[1]))
            except ValueError as error:
                return self._error(str(error), 404)
            return self._send(200, body, "application/json")
        if path == "/api/unlinked":
            return self._json(unlinked_fighters())
        if path.startswith("/unlinked/") and path.endswith(".png"):
            key, root = path[len("/unlinked/"):-4], project_root()
            rows = custom_page.read_portrait(root, key) if root and custom_page.KEY_RE.fullmatch(key) else None
            if rows:
                return self._send(200, custom_page.png(rows), "image/png")
            return self._error("Not found.", 404)
        if path == "/api/test":
            return self._json({**test.snapshot(), "report": test.report})
        if path == "/api/build":
            since = 0
            query = urlparse(self.path).query
            match = re.search(r"since=(\d+)", query)
            if match:
                since = int(match.group(1))
            return self._json(build.snapshot(since))
        return self._error("Not found.", 404)

    def do_POST(self):
        if not self._allowed_host() or self.headers.get("X-T3CB-Token") != TOKEN:
            return self._error("Request refused.", 403)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_IMPORT * 2:
            return self._error("Request too large.", 413)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._error("Invalid request.")
        path = urlparse(self.path).path
        try:
            if path == "/api/root":
                root = Path(str(data.get("root", ""))).expanduser()
                if not (root / "game.toml").is_file():
                    return self._error("This folder has no game.toml. Choose the Tekken 3 Recompiled main folder.")
                config = load_config()
                config["root"] = str(root.resolve())
                save_config(config)
                return self._json(project_status())
            if path == "/api/support/install":
                root = project_root()
                if not root:
                    return self._error("No Tekken 3 Recompiled folder found.")
                kind = creator_patch.project_kind(root)
                if not kind:
                    return self._error("This game folder is not a supported version.")
                if kind == "recompiled" and not jun_enabled(root):
                    return self._error("Creator support builds on Jun's slot. "
                                       "Run the Easy Setup with Include Jun Kazama checked.")
                if build.snapshot(0)["state"] == "running":
                    return self._error("Wait until the build has finished.")
                changed = creator_patch.install(root, kind)
                return self._json({"changed": changed, "warnings": sync_customs(everything=True)})
            if path == "/api/support/uninstall":
                root = project_root()
                if not root:
                    return self._error("No Tekken 3 Recompiled folder found.")
                kind = creator_patch.project_kind(root)
                if not kind:
                    return self._error("This game folder is not a supported version.")
                return self._json({"restored": creator_patch.uninstall(root, kind)})
            if path == "/api/build":
                problem = build.start()
                return self._error(problem) if problem else self._json({"ok": True})
            if path == "/api/test":
                problem = test.start()
                return self._error(problem) if problem else self._json({"ok": True})
            if path == "/api/play":
                character = get_character(safe_id(data["id"])) if data.get("id") else None
                if character and not project_status().get("built"):
                    return self._error("Build the game with creator support first.")
                problem = game.start(character)
                return self._error(problem) if problem else self._json({"ok": True})
            if path == "/api/characters":
                saved = save_character(data)
                refit = refit_model(saved["id"])             # a new style needs the model fitted again
                if refit is not None and saved.get("own_model"):
                    saved = get_character(saved["id"])
                return self._json({**saved, "warnings": refit + sync_customs(changed=saved["id"])})
            if path == "/api/characters/delete":
                cid = safe_id(str(data.get("id", "")))
                delete_character(cid)
                return self._json({"ok": True, "warnings": sync_customs(drop=game_key(cid))})
            if path == "/api/model/check":
                return self._json(check_model(str(data.get("id", "")), str(data.get("name", "")), str(data.get("file", ""))))
            if path == "/api/model/texture":
                return self._json(upload_texture(str(data.get("id", "")), str(data.get("name", "")), str(data.get("file", ""))))
            if path == "/api/model/import":
                return self._json(start_import(str(data.get("id", "")), int(data.get("costume", 0)), data.get("parts"),
                                               data.get("settings")))
            if path == "/api/model/progress":
                return self._json(import_progress(str(data.get("id", ""))))
            if path == "/api/model/undo":
                saved = undo_model(str(data.get("id", "")))
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/history":
                return self._json({"points": restore_points(str(data.get("id", "")))})
            if path == "/api/namecall/voices":
                return self._json({"voices": name_call.voices()})
            if path == "/api/check":
                return self._json(check_library())
            if path == "/api/library":
                return self._json({"assets": asset_library()})
            if path == "/api/export/check":
                return self._json({"warnings": licence_warnings(str(data.get("id", "")))})
            if path == "/api/portraits":
                return self._json({"variants": portrait_variants(str(data.get("id", "")))})
            if path == "/api/portraits/keep":
                return self._json({"variants": keep_portrait(str(data.get("id", "")))})
            if path == "/api/portraits/drop":
                return self._json({"variants": drop_portrait(str(data.get("id", "")), str(data.get("variant", "")))})
            if path == "/api/portraits/use":
                saved = use_portrait(str(data.get("id", "")), str(data.get("variant", "")))
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/history/restore":
                saved = restore_character(str(data.get("id", "")), str(data.get("point", "")))
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/stage/preview":
                return self._json(stage_preview(data))
            if path == "/api/guest-styles":
                root = project_root()
                return self._json({"styles": custom_page.guest_styles(root) if root else []})
            if path == "/api/moves":
                return self._json(command_list(data.get("donor")))
            if path == "/api/fairness":
                clean = validate_character({"name": "x", "donor": data.get("donor"),
                                            "move_damage": data.get("move_damage"),
                                            "move_buttons": data.get("move_buttons")})
                return self._json(fairness_check(clean["donor"], clean.get("move_damage"), clean.get("move_buttons")))
            if path == "/api/kit/models":
                donors = donor_models()
                if not donors.get("available"):
                    raise ValueError(donors.get("reason", "The fighters' models are not available."))
                heights = kit_heights()
                return self._json({"models": [{"model": m, "donor": int(d), "costume": c, "height": heights.get(m)}
                                              for d, ms in donors["donors"].items() for c, m in enumerate(ms)],
                                   "parts": list(KIT_PARTS), "fit": KIT_FIT})
            if path == "/api/looks":
                return self._json({"looks": list_looks()})
            if path == "/api/looks/save":
                return self._json({"looks": save_look(data.get("name"), data.get("donor"), data.get("parts"),
                                                      data.get("colours"), data.get("shape"), data.get("pieces"))})
            if path == "/api/looks/delete":
                return self._json({"looks": delete_look(str(data.get("name", "")))})
            if path == "/api/kit/preview":
                return self._send(200, kit_preview(str(data.get("id", "")), int(data.get("costume", 0)),
                                                   data.get("parts"), data.get("colours"), data.get("shape"),
                                                   data.get("pieces")),
                                  "application/json")
            if path == "/api/kit/pieces":
                return self._json({"pieces": kit_pieces(str(data.get("id", "")), int(data.get("costume", 0)),
                                                        data.get("parts"))})
            if path == "/api/kit/build":
                saved = build_kit(str(data.get("id", "")), int(data.get("costume", 0)), data.get("parts"),
                                  colours=data.get("colours"), shape=data.get("shape"), pieces=data.get("pieces"))
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/namecall/preview":
                return self._json(name_call_preview(data))
            if path == "/api/model/portrait":
                return self._json(own_portrait(str(data.get("id", "")), data.get("look")))
            if path == "/api/model/source":
                return self._json(source_preview(str(data.get("id", ""))))
            if path == "/api/model/preview":
                return self._json(model_preview(str(data.get("id", "")), data.get("parts")))
            if path == "/api/model/remove":
                saved = remove_model(str(data.get("id", "")))
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/share/code":
                return self._json({"code": share_code(str(data.get("id", "")))})
            if path == "/api/share/import":
                copy = import_share_code(data.get("code"))
                model_warnings = copy.pop("model_warnings", [])
                return self._json({**copy, "warnings": model_warnings + sync_customs(changed=copy["id"])})
            if path == "/api/duplicate":
                copy = duplicate_character(str(data.get("id", "")))
                model_warnings = copy.pop("model_warnings", [])
                return self._json({**copy, "warnings": model_warnings + sync_customs(changed=copy["id"])})
            if path == "/api/import":
                packages = backup_packages(str(data.get("file", "")))
                if packages is not None:                # a .t3backup: every fighter in it
                    done, warnings = [], []
                    for package in packages:
                        try:
                            one = import_character(base64.b64encode(package).decode())
                            done.append(one)
                            warnings += one.pop("model_warnings", [])
                        except ValueError as error:
                            warnings.append(str(error))
                    warnings += sync_customs()
                    if not done:
                        raise ValueError("No fighter in this backup could be imported.")
                    return self._json({**done[0], "imported": len(done), "warnings": warnings})
                imported = import_character(str(data.get("file", "")))
                model_warnings = imported.pop("model_warnings", [])
                return self._json({**imported, "warnings": model_warnings + sync_customs(changed=imported["id"])})
            if path == "/api/unlinked/adopt":
                adopted = adopt_unlinked(unlinked_key(data.get("key")))
                return self._json(adopted)
            if path == "/api/unlinked/remove":
                key = unlinked_key(data.get("key"))
                if data.get("confirm") is not True:
                    return self._error("Removing a fighter from the Custom page needs confirmation.")
                return self._json({"ok": True, "warnings": sync_customs(drop=key)})
            if path == "/api/sync":
                return self._json({"warnings": sync_customs(everything=True)})
        except (ValueError, KeyError, creator_patch.PatchError, OSError) as error:
            return self._error(str(error))
        return self._error("Not found.", 404)


def open_window(url: str) -> None:
    if WINDOWS:
        for edge in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                     Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe"):
            if edge.is_file():
                subprocess.Popen([str(edge), f"--app={url}", "--window-size=1280,860"])
                return
    import webbrowser
    webbrowser.open(url)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print("Dizzy Character Creator", APP_VERSION)
    print("Running at", url)
    print("Close this window to stop Dizzy Character Creator.")
    if "--no-window" not in sys.argv:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
