"""Offline tests of the builder's pure-Python core (no game data needed).

Run: python -m unittest discover tests
"""
import base64
import io
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "character-builder" / "app"
sys.path.insert(0, str(APP))

import custom_page  # noqa: E402
import expanded_custom  # noqa: E402
import name_call  # noqa: E402
import server  # noqa: E402


def tone(seconds=0.5, rate=22050, channels=1, amplitude=12000, silence=0.2):
    """A WAV file: silence, a 440 Hz tone, silence."""
    frames = []
    total = int((seconds + 2 * silence) * rate)
    for i in range(total):
        t = i / rate
        v = int(amplitude * math.sin(2 * math.pi * 440 * t)) if silence <= t < silence + seconds else 0
        frames += [v] * channels
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return buf.getvalue()


class NameCallTests(unittest.TestCase):
    def test_pack_layout(self):
        samples = [0, 100, -100, 32767, -32768]
        data = name_call.pack(samples)
        magic, version, size, count, rate = struct.unpack_from("<5I", data)
        self.assertEqual((magic, version, size, count, rate), (0x3153554A, 1, len(data), 1, 44100))
        index, offset, frames, _ = struct.unpack_from("<4I", data, 32)
        self.assertEqual((index, offset, frames), (1025, 48, 5))
        self.assertEqual(list(struct.unpack_from("<5h", data, offset)), samples)

    def test_read_wav_resamples_and_mixes(self):
        samples = name_call.read_wav(tone(rate=22050, channels=2))
        self.assertAlmostEqual(len(samples) / 44100, 0.9, delta=0.01)

    def test_own_trims_and_levels(self):
        out = name_call.own(name_call.read_wav(tone()))
        self.assertAlmostEqual(len(out) / 44100, 0.5 + 0.04, delta=0.03)
        self.assertLessEqual(max(abs(s) for s in out), name_call.PEAK)
        self.assertGreater(max(abs(s) for s in out), name_call.PEAK * 0.95)

    def test_silence_and_garbage_refused(self):
        with self.assertRaises(name_call.NameCallError):
            name_call.own(name_call.read_wav(tone(amplitude=0)))
        with self.assertRaises(name_call.NameCallError):
            name_call.read_wav(b"not a wav")

    def test_names(self):
        self.assertEqual(name_call.spoken_name("DR. B"), "Dr. B")
        self.assertEqual(name_call.spoken_name("JACK-2"), "Jack 2")
        self.assertEqual(name_call.pack_name("cbmedea"), "Cbmedea-TTT1-sfx.jus")


class CustomsListTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in custom_page.FOLDERS:
            (self.root / folder).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        for folder in custom_page.FOLDERS:
            (self.root / folder / "customs.txt").write_text(text, encoding="ascii")

    def test_two_and_four_columns(self):
        self.write("cbtommy 3 17 19\ncbmedea 5\nbad line\ncbx 21\n")
        lines = {}
        entries, unreadable = custom_page.read_entries(self.root, lines)
        self.assertEqual(entries, [("cbtommy", 3), ("cbmedea", 5)])
        self.assertEqual(lines["cbtommy"], "cbtommy 3 17 19")
        self.assertIn("bad line", unreadable)
        self.assertIn("cbx 21", unreadable)

    def test_write_list_keeps_columns_and_refuses_bad(self):
        expanded_custom.write_list(self.root, ["cbtommy 3 17 19", "cbmedea 5"], [])
        text = (self.root / custom_page.FOLDERS[0] / "customs.txt").read_text()
        self.assertEqual(text, "cbtommy 3 17 19\ncbmedea 5\n")
        with self.assertRaises(SystemExit):
            expanded_custom.write_list(self.root, ["cbtommy 3 99"], ["cbmedea"])

    def test_write_list_never_drops_silently(self):
        self.write("cbtommy 3\ncbmedea 5\n")
        with self.assertRaises(SystemExit):
            expanded_custom.write_list(self.root, ["cbtommy 3"], [])


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = server.DATA
        server.DATA = Path(self.tmp.name)

    def tearDown(self):
        server.DATA = self.saved
        self.tmp.cleanup()

    def test_validate(self):
        c = server.validate_character({"name": "medea", "donor": 5, "stage": "17", "music": None})
        self.assertEqual((c["name"], c["donor"], c["stage"], c["name_call"]), ("MEDEA", 5, 17, "auto"))
        self.assertNotIn("music", c)
        for bad in ({"name": "FQ", "donor": 1}, {"name": "A", "donor": 21}, {"name": "A", "donor": 1, "stage": 30},
                    {"name": "A", "donor": 1, "name_call": "robot"}):
            with self.assertRaises(ValueError):
                server.validate_character(bad)

    def test_customs_line(self):
        self.assertEqual(server.custom_entry("cbx", {"donor": 3}), "cbx 3")
        self.assertEqual(server.custom_entry("cbx", {"donor": 3, "music": 19}), "cbx 3 3 19")
        self.assertEqual(server.custom_entry("cbx", {"donor": 3, "stage": 17, "music": 19}), "cbx 3 17 19")

    def test_package_round_trip(self):
        wav = "data:audio/wav;base64," + base64.b64encode(name_call.wav_bytes(name_call.own(name_call.read_wav(tone())))).decode()
        saved = server.save_character({"name": "MEDEA", "donor": 5, "stage": 17, "music": 19,
                                       "name_call": "own", "name_call_wav": wav, "costumes": []})
        name, data = server.export_character(saved["id"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(sorted(z.namelist()), ["character.json", "namecall.wav"])
        copy = server.import_character(base64.b64encode(data).decode())
        self.assertNotEqual(copy["id"], saved["id"])
        self.assertEqual((copy["stage"], copy["music"], copy["name_call"]), (17, 19, "own"))
        a = (server.DATA / saved["id"] / "namecall.wav").read_bytes()
        b = (server.DATA / copy["id"] / "namecall.wav").read_bytes()
        self.assertEqual(a, b)

    def test_package_refuses_foreign_files(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("character.json", json.dumps({"name": "A", "donor": 1}))
            z.writestr("model.bin", b"disc data")
        with self.assertRaises(ValueError):
            server.import_character(base64.b64encode(buf.getvalue()).decode())


class PatchDataTests(unittest.TestCase):
    def test_edits_well_formed(self):
        import expanded_patch_data as d
        lists = [v for k, v in vars(d).items() if k.isupper() and isinstance(v, list)]
        self.assertTrue(lists)
        for edits in lists:
            for edit in edits:
                self.assertEqual(len(edit), 3)
                old, new, count = edit
                self.assertIsInstance(old, str); self.assertIsInstance(new, str)
                self.assertNotEqual(old, new)
                self.assertTrue(old)
                self.assertIsInstance(count, int); self.assertGreaterEqual(count, 1)


class CharacterBuilderTests(unittest.TestCase):
    def test_parts_match_kitbash(self):
        import ast
        tree = ast.parse((APP / "kitbash.py").read_text(encoding="utf-8"))
        parts = next(n.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "PARTS")
        names = [k.value for k in parts.keys]
        self.assertEqual(tuple(names), server.KIT_PARTS)
        fit = next(n.value.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "FIT")
        self.assertEqual(fit, server.KIT_FIT)


class VoiceLabTests(unittest.TestCase):
    def test_effect_is_deeper_and_longer(self):
        url = "data:audio/wav;base64," + base64.b64encode(tone()).decode()
        plain = name_call.read_wav(server.decode_wav(url, process=True))
        effect = name_call.read_wav(server.decode_wav(url, process=True, effect=True))
        self.assertGreater(len(effect), len(plain) * 1.15)      # 18 % lower and an echo tail
        kept = name_call.read_wav(server.decode_wav(url))        # saving keeps it as it is
        self.assertAlmostEqual(len(kept) / 44100, 0.9, delta=0.01)


class MoveLabTests(unittest.TestCase):
    def test_command_list_from_arc_member_4(self):
        import command_list as M
        entries = [b"Phoenix Smasher", bytes([0x81, 0x82, 0x84, 0x93]),          # d df f 2
                   b"Doc's One-Two", bytes([0x92, 0x93]),                          # 1 2
                   bytes([0xBF]) + b" Rush", bytes([0x84, 0x8C, 0x94]),            # token Elbow; f F 1+2
                   bytes([0xFC]), bytes([0x0D]) + b" Stance",                     # section title
                   b"Mokujinken", b"?"]
        body = bytes([5]) + b"".join(e + bytes(1) for e in entries)
        members = [b"x" * 8, b"y" * 8, b"z" * 8, b"w" * 8, body]
        offset, table, blob = 4 + 8 * 5, b"", b""
        for m in members:
            table += struct.pack("<II", offset + len(blob), len(m))
            blob += m
        arc = struct.pack("<I", 5) + table + blob
        got = M.moves(arc)
        self.assertEqual(got, [{"name": "Phoenix Smasher", "command": "d, df, f+2"},
                               {"name": "Doc's One-Two", "command": "1, 2"},
                               {"name": "Elbow Rush", "command": "f, F+1+2"},
                               {"section": "Left Stance"},
                               {"name": "Mokujinken", "command": "?"}])

    def test_marks(self):
        import command_list as M
        self.assertEqual(M.text(b"Flamingo @#"), "Flamingo (*)")
        self.assertEqual(M.text(bytes([0x0A]) + b" @#,"), "During (*) ,")


if __name__ == "__main__":
    unittest.main()
