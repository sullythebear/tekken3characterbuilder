"""The announcer calling a custom fighter's name (stdlib only).

Tekken 3 Expanded plays a guest's name from <Key>-TTT1-sfx.jus (sound index 1025,
src/tekken3_ttt1_sfx.c) when Tekken 3's announcer calls a fighter (Practice). A custom fighter
gets a pack holding only that sound: spoken by Windows' voice with an announcer effect
(automatic), or the player's own recording.

Pack format: eight words (magic "JUS1", version 1, size, count, rate 44100, 0, 0, 0), then per
sound four words (index, offset, frames, 0), then mono 16-bit PCM.
"""
from __future__ import annotations

import io
import math
import os
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

RATE = 44100
NAME_SOUND = 1025
PEAK = 11400                 # the level of TTT1's own name calls (measured: peak ~11400)
MAX_SECONDS = 3.0
COMPRESS = 2.5               # soft compression strength
MODES = ("auto", "own", "off")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SPEAK = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100,
  [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($env:T3CB_OUT, $f)
if ($env:T3CB_VOICE) { try { $s.SelectVoice($env:T3CB_VOICE) } catch {} }
$x = [System.Security.SecurityElement]::Escape($env:T3CB_SAY)
$s.SpeakSsml('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">' +
  '<prosody pitch="x-low" rate="-15%">' + $x + '!</prosody></speak>')
$s.Dispose()
"""


class NameCallError(ValueError):
    pass


def spoken_name(name: str) -> str:
    """How the voice should say a name plate: 'DR. B' -> 'Dr. B', 'JACK-2' -> 'Jack 2'."""
    return " ".join(w.capitalize() for w in name.replace("-", " ").split())


VOICES = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name }
$s.Dispose()
"""
VOICE_RE = re.compile(r"[A-Za-z0-9 ._()-]{1,60}")


def voices() -> list[str]:
    """The speech voices installed on this computer (System.Speech), e.g. Microsoft Zira Desktop."""
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", VOICES],
                              capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [v.strip() for v in done.stdout.splitlines() if VOICE_RE.fullmatch(v.strip())]


def speak(name: str, voice: str | None = None) -> list[int]:
    """The name spoken by Windows' own voice (System.Speech), 44100 Hz mono samples. voice: an
    installed voice's name (default: the system's)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "say.wav"
        env = dict(os.environ, T3CB_SAY=spoken_name(name), T3CB_OUT=str(out),
                   T3CB_VOICE=voice if voice and VOICE_RE.fullmatch(voice) else "")
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SPEAK], env=env,
                           capture_output=True, timeout=60, creationflags=NO_WINDOW)
            return read_wav(out.read_bytes())
        except (OSError, subprocess.TimeoutExpired, NameCallError):
            raise NameCallError("This computer has no speech voice: record or choose a sound instead.") from None


def read_wav(data: bytes) -> list[int]:
    """Samples of a PCM WAV file (8/16-bit, any rate, mono or stereo) as 44100 Hz mono."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(min(w.getnframes(), rate * 30))
    except (wave.Error, EOFError, struct.error):
        raise NameCallError("The sound is not a WAV file the creator can read.") from None
    if width == 2:
        values = struct.unpack(f"<{len(raw) // 2}h", raw[:len(raw) // 2 * 2])
    elif width == 1:
        values = [(b - 128) << 8 for b in raw]
    else:
        raise NameCallError("The sound must be 8 or 16-bit PCM.")
    mono = [sum(values[i:i + channels]) // channels for i in range(0, len(values) - channels + 1, channels)]
    if not mono:
        raise NameCallError("The sound is empty.")
    return resample(mono, rate / RATE) if rate != RATE else mono


def resample(samples: list[int], step: float) -> list[int]:
    """Linear resampling: reads `step` input samples per output sample."""
    out, n, pos = [], len(samples), 0.0
    while pos < n - 1:
        i = int(pos)
        f = pos - i
        out.append(int(samples[i] * (1 - f) + samples[i + 1] * f))
        pos += step
    return out


def trim(samples: list[int]) -> list[int]:
    """Without the silence before and after (keeping 20 ms), at most MAX_SECONDS."""
    loud = max((abs(s) for s in samples), default=0)
    if loud < 300:
        raise NameCallError("The sound is silent.")
    level = loud * 0.06
    first = next(i for i, s in enumerate(samples) if abs(s) > level)
    last = len(samples) - next(i for i, s in enumerate(reversed(samples)) if abs(s) > level)
    pad = RATE // 50
    return samples[max(0, first - pad):min(len(samples), last + pad)][:int(MAX_SECONDS * RATE)]


def finish(samples: list[int]) -> list[int]:
    """Fades of 5 ms and the level of TTT1's name calls."""
    fade = min(RATE // 200, len(samples) // 2)
    out = list(samples)
    for i in range(fade):
        out[i] = out[i] * i // fade
        out[-1 - i] = out[-1 - i] * i // fade
    loud = max(abs(s) for s in out) or 1
    # soft compression: as loud as TTT1's calls (RMS ~4300 at that peak), no hard clipping
    curve = 1 - math.exp(-COMPRESS)
    return [int(math.copysign(PEAK * (1 - math.exp(-COMPRESS * abs(s) / loud)) / curve, s)) for s in out]


# echoes: (delay in seconds, gain) taps
ECHOES = {"none": (), "hall": ((0.07, 0.32), (0.13, 0.22), (0.21, 0.13)),
          "arena": ((0.11, 0.38), (0.23, 0.27), (0.37, 0.18), (0.52, 0.10))}
PITCH = (-30, 30)                                 # % higher or lower (and faster or slower: tape style)


def shape(samples: list[int], pitch: int = 0, echo: str = "none") -> list[int]:
    """Trimmed, `pitch` % higher or lower (speed changes with it), with an echo, at the game's
    level. Plain DSP, no generated voice."""
    pitch = max(PITCH[0], min(PITCH[1], int(pitch)))
    sound = trim(samples)
    if pitch:
        sound = resample(sound, 1 + pitch / 100)
    taps = [(int(RATE * d), g) for d, g in ECHOES.get(echo, ())]
    if taps:
        out = sound + [0] * taps[-1][0]
        for delay, gain in taps:
            for i, s in enumerate(sound):
                out[i + delay] += int(s * gain)
        sound = out
    return finish(sound)


def announcer(samples: list[int]) -> list[int]:
    """A deeper voice in a big hall: 18 % lower (and slower), with a short echo."""
    return shape(samples, -18, "hall")


def own(samples: list[int]) -> list[int]:
    """The player's recording: trimmed and at the game's level, otherwise as recorded."""
    return finish(trim(samples))


def wav_bytes(samples: list[int]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def pack(samples: list[int]) -> bytes:
    """<Key>-TTT1-sfx.jus with the name call as its only sound."""
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    head = 32 + 16
    return (struct.pack("<8I", 0x3153554A, 1, head + len(pcm), 1, RATE, 0, 0, 0)
            + struct.pack("<4I", NAME_SOUND, head, len(samples), 0) + pcm)


def pack_name(key: str) -> str:
    """'cbdizzy' -> 'Cbdizzy-TTT1-sfx.jus' (Expanded's data prefix, tekken3_ttt1_roster.c describe)."""
    return key[0].upper() + key[1:].lower() + "-TTT1-sfx.jus"


def fighter_sound(folder: Path, fighter: dict) -> list[int] | None:
    """The name call a fighter's choice gives (None: silent). The automatic one is cached in
    namecall-auto.wav for the name in namecall-auto.txt."""
    mode = fighter.get("name_call", "off")       # silent unless chosen (owner, 2026-10-16)
    if mode == "own" and (folder / "namecall.wav").is_file():
        return read_wav((folder / "namecall.wav").read_bytes())
    if mode != "auto":
        return None
    cache, said = folder / "namecall-auto.wav", folder / "namecall-auto.txt"
    voice = fighter.get("name_call_voice") or ""
    want = fighter["name"] + (f"|{voice}" if voice else "")    # the name (and voice) cached
    if cache.is_file() and said.is_file() and said.read_text(encoding="utf-8") == want:
        return read_wav(cache.read_bytes())
    samples = announcer(speak(fighter["name"], voice or None))
    cache.write_bytes(wav_bytes(samples))
    said.write_text(want, encoding="utf-8")
    return samples


def write(root: Path, folders, key: str, samples: list[int] | None) -> None:
    """Puts (or removes, for None) the fighter's name call pack in the game's folders."""
    data = pack(samples) if samples else None
    for folder in folders:
        target = root / folder
        if not target.is_dir():
            continue
        if data:
            (target / pack_name(key)).write_bytes(data)
        else:
            (target / pack_name(key)).unlink(missing_ok=True)
