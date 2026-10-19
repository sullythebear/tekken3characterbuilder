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
        self.assertEqual((c["name"], c["donor"], c["stage"], c["name_call"]), ("MEDEA", 5, 17, "off"))
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


class RestorePointTests(CharacterTests):
    def test_restore_and_undo(self):
        first = server.save_character({"name": "MEDEA", "donor": 5, "costumes": []})
        server.save_character({"id": first["id"], "name": "MEDEA", "donor": 3, "stage": 17, "costumes": []})
        points = server.restore_points(first["id"])
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["donor"], 5)
        back = server.restore_character(first["id"], points[0]["id"])
        self.assertEqual((back["donor"], back.get("stage")), (5, None))
        points = server.restore_points(first["id"])               # the restore itself can be undone
        self.assertEqual(points[0]["donor"], 3)
        with self.assertRaises(ValueError):
            server.restore_character(first["id"], "../../etc")

    def test_keeps_twenty(self):
        c = server.save_character({"name": "A", "donor": 1, "costumes": []})
        for i in range(25):
            server.save_character({"id": c["id"], "name": "A", "donor": i % 21, "costumes": []})
        self.assertEqual(len(server.restore_points(c["id"])), server.RESTORE_POINTS)





class CreditsAndBackupTests(CharacterTests):
    def test_credits_kept_and_cleaned(self):
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "credits": {
            "model": {"source": "Mixamo <b>", "author": "Me", "licence": "own"},
            "portrait": {"source": "", "author": "", "licence": "bogus"}, "tail": {"licence": "cc0"}}})
        self.assertEqual(c["credits"], {"model": {"source": "Mixamo b", "author": "Me", "licence": "own"}})

    def test_licence_warning_for_own_sound(self):
        wav = "data:audio/wav;base64," + base64.b64encode(name_call.wav_bytes(name_call.own(name_call.read_wav(tone())))).decode()
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "name_call": "own", "name_call_wav": wav})
        self.assertEqual(len(server.licence_warnings(c["id"])), 1)
        server.save_character({"id": c["id"], "name": "A", "donor": 1, "costumes": [], "name_call": "own",
                               "credits": {"sound": {"licence": "own"}}})
        self.assertEqual(server.licence_warnings(c["id"]), [])

    def test_asset_library(self):
        red = PortraitVariantTests.image((255, 0, 0, 255))
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "portrait_ps1": red, "portrait_source": red,
                                   "credits": {"portrait": {"source": "drawn", "licence": "own"}}})
        server.save_character({"name": "B", "donor": 2, "costumes": []})
        rows = server.asset_library()
        self.assertEqual([(r["id"], r["asset"], r["licence"]) for r in rows], [(c["id"], "portrait", "own")])

    def test_check_without_game(self):
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "name_call": "own"})
        r = server.check_library()
        issues = [i["text"] for f in r["fighters"] for i in f["issues"] if f["id"] == c["id"]]
        self.assertTrue(any("portrait" in t for t in issues))
        self.assertEqual(server.check_library()["fighters"][0]["name"], "A")

    def test_saved_looks(self):
        server.LOOKS_FILE = server.DATA.parent / "looks-test.json"
        looks = server.save_look("Heavy blue", 5, {}, [-60, 100, 0, True], {"arms": 1.2})
        self.assertEqual([(l["name"], l["shape"]) for l in looks], [("Heavy blue", {"arms": 1.2})])
        self.assertEqual(len(server.save_look("Heavy blue", 5, {}, None, {"body": 1.1})), 1)   # same name: replaced
        with self.assertRaises(ValueError):
            server.save_look("", 5, {}, None, {"arms": 1.2})
        self.assertEqual(server.delete_look("Heavy blue"), [])

    def test_duplicate(self):
        red = PortraitVariantTests.image((255, 0, 0, 255))
        c = server.save_character({"name": "KAZAMA", "donor": 9, "costumes": [], "portrait_ps1": red, "portrait_source": red,
                                   "move_damage": {"3": 40}, "credits": {"portrait": {"licence": "own"}}})
        copy = server.duplicate_character(c["id"])
        self.assertNotEqual(copy["id"], c["id"])
        self.assertEqual((copy["name"], copy["donor"], copy["move_damage"]), ("KAZAMA 2", 9, {"3": 40}))
        self.assertTrue((server.DATA / copy["id"] / "portrait-ps1.png").is_file())
        long = server.save_character({"name": "ABCDEGHIJKLMNOP", "donor": 1, "costumes": []})
        self.assertEqual(server.duplicate_character(long["id"])["name"], "ABCDEGHIJKLMN 2")

    def test_backup_round_trip(self):
        import base64
        server.save_character({"name": "A", "donor": 1, "costumes": []})
        server.save_character({"name": "B", "donor": 2, "costumes": []})
        _, data = server.backup_all()
        packages = server.backup_packages(base64.b64encode(data).decode())
        self.assertEqual(len(packages), 2)
        _, single = server.export_character(server.character_list()[0]["id"])
        self.assertIsNone(server.backup_packages(base64.b64encode(single).decode()))



class VoiceShapeTests(unittest.TestCase):
    def test_shape(self):
        samples = name_call.read_wav(tone())
        plain = name_call.shape(samples)
        self.assertEqual(plain, name_call.own(samples))
        self.assertLess(len(name_call.shape(samples, 30)), len(plain))       # higher = shorter
        self.assertGreater(len(name_call.shape(samples, -30, "arena")), len(plain))
        self.assertEqual(name_call.announcer(samples), name_call.shape(samples, -18, "hall"))

    def test_voice_validated(self):
        c = server.validate_character({"name": "A", "donor": 1, "name_call": "auto", "name_call_voice": "Microsoft Zira Desktop"})
        self.assertEqual(c["name_call_voice"], "Microsoft Zira Desktop")
        c = server.validate_character({"name": "A", "donor": 1, "name_call_voice": "Zira; rm -rf"})
        self.assertNotIn("name_call_voice", c)


class BasicDamageTests(unittest.TestCase):
    def test_moves_file(self):
        import command_list as M
        records = {"3": [110, 25], "1": [99, 5]}
        self.assertIsNone(M.moves_file(5, records, {"3": 25}))           # unchanged
        b = M.moves_file(5, records, {"3": 60, "9": 1})
        self.assertEqual(b, b"T3MV" + struct.pack("<HHH", 1, 5, 1) + struct.pack("<HHH", 110, 25, 60))
        c = server.validate_character({"name": "A", "donor": 5, "move_damage": {"3": 999, "df+2": "12", "x": 3}})
        self.assertEqual(c["move_damage"], {"3": 200, "df+2": 12})
        c = server.validate_character({"name": "A", "donor": 4, "move_damage": {"D+3+4": 9, "d+1+4": 70}})
        self.assertEqual(c["move_damage"], {"D+3+4": 9, "d+1+4": 70})
        c = server.validate_character({"name": "A", "donor": 3, "move_damage": {
            "Duringcrouch,df+1": 30, "d,df,f+2": 40, "1,2": 5, "x;y": 1}})
        self.assertEqual(c["move_damage"], {"Duringcrouch,df+1": 30, "d,df,f+2": 40})

    def test_strings(self):
        import command_list as M
        moveset = bytearray(16 + 3 * 56 + 4)
        struct.pack_into("<III", moveset, 4, 0, 16, 16 + 3 * 56)
        for r, d in ((0, 12), (1, 12), (2, 15)):
            struct.pack_into("<I", moveset, 16 + 56 * r + 20, d)
        saved = M.STRINGS.get(99)
        M.STRINGS[99] = {"b+1,2,1": [0, 1, 2], "1,2": [0, 7]}
        try:
            self.assertEqual(M.string_records(bytes(moveset), 99), {"b+1,2,1": [(0, 12), (1, 12), (2, 15)]})
        finally:
            M.STRINGS.pop(99) if saved is None else M.STRINGS.__setitem__(99, saved)
        out = M.with_damage([{"name": "Combo", "command": "b+1, 2, 1"}], {}, {"b+1,2,1": [12, 12, 15]})
        self.assertEqual((out[0]["hits"], out[0]["damage"]), ([12, 12, 15], 39))
        c = server.validate_character({"name": "A", "donor": 1, "move_damage": {"b+1,2,1#2": 20, "1,2#9": 5}})
        self.assertEqual(c["move_damage"], {"b+1,2,1#2": 20})

    def test_own_records(self):
        import command_list as M
        # header: +8 records at 16, +12 alias table after 3 records; record 2 has damage 0x4060
        moveset = bytearray(16 + 3 * 56 + 4)
        struct.pack_into("<III", moveset, 4, 0, 16, 16 + 3 * 56)
        struct.pack_into("<I", moveset, 16 + 56 + 20, 60)
        struct.pack_into("<I", moveset, 16 + 2 * 56 + 20, 0x4060)
        saved = M.OWN_MOVES.get(99)
        M.OWN_MOVES[99] = {"d+1+4": 1, "b+1+4": 0, "D+3+4": 2, "f+1+2": 7}
        try:
            self.assertEqual(M.own_records(bytes(moveset), 99), {"d+1+4": (1, 60), "D+3+4": (2, 0x60)})
        finally:
            M.OWN_MOVES.pop(99) if saved is None else M.OWN_MOVES.__setitem__(99, saved)

    def test_notation(self):
        import command_list as M
        self.assertEqual(M.notation(0x0404), "f+3")
        self.assertEqual(M.notation(0x0048), "d+4")
        self.assertEqual(M.notation(0x0003), "1+2")
        self.assertEqual(M.notation(0x0201), "1")
        self.assertIsNone(M.notation(0x0410))          # a direction alone
        self.assertIsNone(M.notation(0xC00C))

    def test_basic_damage(self):
        import command_list as M
        # a moveset: header, two records (damage 0 and 12), alias table: slot 2 -> record 1
        start, count = 64, 2
        alias = start + 56 * count
        ms = bytearray(alias + 16)
        struct.pack_into("<IIII", ms, 0, 0x0701, 0x40, start, alias)
        struct.pack_into("<I", ms, start + 56 + 20, 12)
        struct.pack_into("<I", ms, alias + 8, 1)
        exe = bytearray(M.SHARED_LISTS[1] - 0x80010000 + 0x800 + 12)
        at = M.SHARED_LISTS[0] - 0x80010000 + 0x800
        struct.pack_into("<4H", exe, at, 0x0404, 0, 0, 2)      # f+3 -> slot 2
        self.assertEqual(M.basic_damage(bytes(ms), bytes(exe)), {"f+3": 12})
        rows = M.with_damage([{"name": "Kick", "command": "f+3"}, {"name": "Two", "command": "1, 2"}], {"f+3": 12})
        self.assertEqual([r.get("damage") for r in rows], [12, None])

class BodyShapeTests(unittest.TestCase):
    def test_clean_shape(self):
        self.assertEqual(server.clean_kit_shape({"head": 1.2, "arms": 1, "legs": 5, "tail": 2}),
                         {"head": 1.2, "legs": 1.3})
        self.assertEqual(server.clean_kit_shape(None), {})
        with self.assertRaises(ValueError):
            server.clean_kit_shape({"body": "wide"})

class PortraitVariantTests(CharacterTests):
    @staticmethod
    def image(colour):
        import base64
        import custom_page
        return "data:image/png;base64," + base64.b64encode(custom_page.png([bytes(colour) * 2] * 2)).decode()

    def test_keep_use_drop(self):
        red, blue = self.image((255, 0, 0, 255)), self.image((0, 0, 255, 255))
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "portrait_ps1": red, "portrait_source": red})
        kept = server.keep_portrait(c["id"])
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0]["current"])
        self.assertEqual(len(server.keep_portrait(c["id"])), 1)         # the same one is not kept twice
        server.save_character({"id": c["id"], "name": "A", "donor": 1, "costumes": [], "portrait_ps1": blue})
        self.assertFalse(server.portrait_variants(c["id"])[0]["current"])
        server.use_portrait(c["id"], kept[0]["id"])                       # blue is kept automatically
        variants = server.portrait_variants(c["id"])
        self.assertEqual(len(variants), 2)
        self.assertEqual(sum(v["current"] for v in variants), 1)
        folder = server.DATA / c["id"]
        self.assertEqual((folder / "portrait-ps1.png").read_bytes(), (folder / "portraits" / kept[0]["id"] / "portrait-ps1.png").read_bytes())
        left = server.drop_portrait(c["id"], kept[0]["id"])
        self.assertEqual(len(left), 1)
        with self.assertRaises(ValueError):
            server.use_portrait(c["id"], "../..")

    def test_package_carries_saved_portraits(self):
        import base64
        red = self.image((255, 0, 0, 255))
        c = server.save_character({"name": "A", "donor": 1, "costumes": [], "portrait_ps1": red, "portrait_source": red})
        kept = server.keep_portrait(c["id"])
        _, data = server.export_character(c["id"])
        back = server.import_character(base64.b64encode(data).decode())
        self.assertNotEqual(back["id"], c["id"])
        self.assertEqual([v["id"] for v in server.portrait_variants(back["id"])], [kept[0]["id"]])

    def test_needs_a_portrait(self):
        c = server.save_character({"name": "A", "donor": 1, "costumes": []})
        with self.assertRaises(ValueError):
            server.keep_portrait(c["id"])

class StageLabTests(unittest.TestCase):
    def test_custom_look_args(self):
        args, label = server.stage_look_args("custom", "#30FF60", 70)
        self.assertEqual(args, ["--look", "custom", "--tint", "30ff60", "--strength", "70"])
        self.assertEqual(label, "custom-30ff60-70")
        self.assertEqual(server.stage_look_args("night", None, None), (["--look", "night"], "night"))
        with self.assertRaises(ValueError):
            server.stage_look_args("custom", "red; rm", 50)

    def test_validate_keeps_tint(self):
        c = server.validate_character({"name": "A", "donor": 1, "stage_look": "custom", "stage_tint": "#00ff00",
                                       "stage_strength": 250})
        self.assertEqual((c["stage_look"], c["stage_tint"], c["stage_strength"]), ("custom", "#00ff00", 100))
        with self.assertRaises(ValueError):
            server.validate_character({"name": "A", "donor": 1, "stage_look": "disco"})


class KitColourTests(unittest.TestCase):
    def test_clean(self):
        self.assertIsNone(server.clean_kit_colours(None))
        self.assertIsNone(server.clean_kit_colours([0, 100, 0, True]))          # the parts' own colours
        self.assertEqual(server.clean_kit_colours([500, -5, 99, 0]), [180, 0, 40, False])
        with self.assertRaises(ValueError):
            server.clean_kit_colours(["red", 1, 2, 3])


class DecimateTests(unittest.TestCase):
    def test_alive_out(self):
        import numpy as np
        import decimate as D
        # a flat 4 x 4 grid of quads as triangles: collapses keep the order of what survives
        n = 5
        pos = np.array([(x, 0.0, z) for z in range(n) for x in range(n)])
        tris = []
        for z in range(n - 1):
            for x in range(n - 1):
                a = z * n + x
                tris += [[a, a + 1, a + n], [a + 1, a + n + 1, a + n]]
        alive = []
        _, _, out, _ = D.decimate(pos, np.array(tris), 20, alive_out=alive)
        self.assertEqual(len(alive), len(out))
        self.assertEqual(alive, sorted(alive))
        for k, t in zip(alive, out):                     # a surviving triangle keeps its corner order
            same = [a == b for a, b in zip(tris[k], t)]
            self.assertGreaterEqual(sum(same), 1)


class StageModelTests(unittest.TestCase):
    def test_triangles(self):
        import stage_look as S
        # one piece: 4 vertices, a flat quad (8 bytes), a textured triangle (20 bytes), then an
        # unknown packet that ends the piece
        verts = b"".join(struct.pack("<4h", x, -y, 0, 0) for x, y in ((0, 0), (10, 0), (0, 10), (10, 10)))
        flat = bytes([200, 100, 50, 0x28, 0, 1, 2, 3])
        tex = bytes([128, 128, 128, 0x26, 1, 2]) + struct.pack("<H", 0x7807) + bytes([3, 4]) + \
            struct.pack("<H", 0x1A) + bytes([5, 6, 0, 0, 3, 2, 1, 0])
        prims = flat + tex + bytes([0, 0, 0, 0x7C])
        head = struct.pack("<3I", 65, 400, 1)
        row_at = 28                                            # offsets count from +12
        model = head + struct.pack("<7I", row_at + len(prims), 4, 0, 3, row_at, 3, 0) + prims + verts
        tris = S.stage_triangles(model)
        self.assertEqual(len(tris), 3)                         # the quad as two, the triangle, not the unknown one
        self.assertEqual(tris[0][0], [(0, 0, 0), (10, 0, 0), (0, -10, 0)])
        self.assertIsNone(tris[0][1])
        self.assertEqual(tris[2][1:4], ([(1, 2), (3, 4), (5, 6)], 0x7807, 0x1A))
        self.assertTrue(tris[2][5])                            # code bit 1: semi-transparent


if __name__ == "__main__":
    unittest.main()
