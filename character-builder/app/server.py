"""Tekken 3 Recompiled Character Builder - local server.

Runs on the Python bundled with the Easy Setup, standard library only.
Listens on 127.0.0.1 only and accepts state-changing requests only with the
session token embedded in its own page.
"""
from __future__ import annotations

import base64, io, json, os, re, secrets, shutil, subprocess, sys, threading, time, zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

# The Easy Setup's embedded Python does not put the script folder on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import creator_patch  # noqa: E402
import custom_page  # noqa: E402

APP_VERSION = "0.3.4"
APP = Path(__file__).resolve().parent
BASE = APP.parent
UI = APP / "ui"
DATA = BASE / "characters"
LOGS = BASE / "logs"
CONFIG = BASE / "config.json"
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
        "stale": stale, "build": build.snapshot(0)["state"], "game": game.snapshot(),
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


# ------------------------------------------------------------- characters --

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "personage"


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,40}", value or ""):
        raise ValueError("Invalid character ID.")
    return value


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
        raise ValueError("Choose a donor.") from None
    if not DONOR_MIN <= donor <= DONOR_MAX:
        raise ValueError("That donor does not exist.")
    author = re.sub(r"[^\w .\-]", "", str(data.get("author", ""))).strip()[:32]
    return {"name": name, "donor": donor, "author": author}


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
        stamp = int(info.stat().st_mtime)
        data["portrait"] = (f"/characters/{folder.name}/portrait-ps1.png?v={stamp}"
                            if (folder / "portrait-ps1.png").is_file() else None)
        data["source"] = (f"/characters/{folder.name}/portrait.png?v={stamp}"
                          if (folder / "portrait.png").is_file() else None)
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
    existing, unreadable = custom_page.read_entries(root)
    for line in unreadable:
        warnings.append(f"customs.txt has a line the builder cannot read, kept out of the list: {line}")
    order = [key for key, _ in existing if key != drop]
    order += [key for key in library if key not in order and key != drop]
    donors = dict(existing)
    listed, left_out = [], 0
    for key in order:
        c = library.get(key)
        if not c:  # not in this library: keep it as the game has it
            listed.append(f"{key} {donors[key]}")
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
        listed.append(f"{key} {c['donor']}")
    if left_out:
        warnings.append(f"The Custom page holds {CUSTOM_PAGE_MAX} fighters: {left_out} of yours are left out.")
    args = ["list", *sum((["--entry", e] for e in listed), [])]
    if drop:
        args += ["--drop", drop]
    problem = run_custom_tool(root, args)
    if problem:
        warnings.append(problem)
    return warnings


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
              "updated": now, **clean, "slot_mode": "jun-slot-23"}
    for key, filename in (("portrait_source", "portrait.png"), ("portrait_ps1", "portrait-ps1.png"),
                          ("portrait_full", "portrait-full.png")):
        png = decode_png(data.get(key))
        if png:
            (folder / filename).write_bytes(png)
    info.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return get_character(folder.name)


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
        for name in ("character.json", "portrait.png", "portrait-ps1.png", "portrait-full.png"):
            if (folder / name).is_file():
                z.write(folder / name, name)
    return f"{folder.name}.t3char", buffer.getvalue()


def import_character(payload: str) -> dict:
    raw = base64.b64decode(payload, validate=True)
    if len(raw) > MAX_IMPORT:
        raise ValueError("This package is too large.")
    allowed = {"character.json", "portrait.png", "portrait-ps1.png", "portrait-full.png"}
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("This is not a valid .t3char package.") from None
    files = {}
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if info.filename not in allowed:
                raise ValueError(f"Unexpected file in package: {info.filename}. "
                                 "Packages may only contain a description and images.")
            if info.file_size > MAX_UPLOAD:
                raise ValueError("A file in the package is too large.")
            files[info.filename] = z.read(info)
    if "character.json" not in files:
        raise ValueError("The package is missing character.json.")
    try:
        data = json.loads(files["character.json"].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("character.json is damaged.") from None
    for name in ("portrait.png", "portrait-ps1.png", "portrait-full.png"):
        if name in files and not files[name].startswith(PNG_SIGNATURE):
            raise ValueError(f"{name} is not a valid PNG.")
    record = {**validate_character(data)}
    for key, name in (("portrait_source", "portrait.png"), ("portrait_ps1", "portrait-ps1.png"),
                      ("portrait_full", "portrait-full.png")):
        if name in files:
            record[key] = "data:image/png;base64," + base64.b64encode(files[name]).decode()
    return save_character(record)


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
            if len(parts) == 4 and parts[3] in ("portrait.png", "portrait-ps1.png"):
                try:
                    target = DATA / safe_id(parts[2]) / parts[3]
                except ValueError:
                    return self._error("Not found.", 404)
                if target.is_file():
                    return self._send(200, target.read_bytes(), "image/png")
            return self._error("Not found.", 404)
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
        if path == "/api/unlinked":
            return self._json(unlinked_fighters())
        if path.startswith("/unlinked/") and path.endswith(".png"):
            key, root = path[len("/unlinked/"):-4], project_root()
            rows = custom_page.read_portrait(root, key) if root and custom_page.KEY_RE.fullmatch(key) else None
            if rows:
                return self._send(200, custom_page.png(rows), "image/png")
            return self._error("Not found.", 404)
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
            if path == "/api/play":
                character = get_character(safe_id(data["id"])) if data.get("id") else None
                if character and not project_status().get("built"):
                    return self._error("Build the game with creator support first.")
                problem = game.start(character)
                return self._error(problem) if problem else self._json({"ok": True})
            if path == "/api/characters":
                saved = save_character(data)
                return self._json({**saved, "warnings": sync_customs(changed=saved["id"])})
            if path == "/api/characters/delete":
                cid = safe_id(str(data.get("id", "")))
                delete_character(cid)
                return self._json({"ok": True, "warnings": sync_customs(drop=game_key(cid))})
            if path == "/api/import":
                imported = import_character(str(data.get("file", "")))
                return self._json({**imported, "warnings": sync_customs(changed=imported["id"])})
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
    print("Tekken 3 Recompiled Character Builder", APP_VERSION)
    print("Running at", url)
    print("Close this window to stop the builder.")
    if "--no-window" not in sys.argv:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
