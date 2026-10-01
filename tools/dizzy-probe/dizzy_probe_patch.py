"""Dizzy probe v2: maakt Jun's slot (23) optioneel een Xiaoyu-kloon.

Alleen actief als TEKKEN3_DIZZY_PROBE=1 is gezet; zonder die variabele gedraagt
het spel zich precies als voorheen. Alle wijzigingen worden eerst gecontroleerd;
past er ook maar een niet, dan wordt er niets aangepast.

Gebruik:  python dizzy_probe_patch.py          (toepassen)
          python dizzy_probe_patch.py --undo   (originele bestanden terugzetten)
"""
from pathlib import Path
import shutil, sys

ROOT = Path(__file__).resolve().parent
MARKER = "tekken3_dizzy_probe"

ROSTER_HELPERS = """enum { JUN_ID=23, JUN_MODEL=52, ROSTER_COUNT=22 };
/* Dizzy probe (experimental): TEKKEN3_DIZZY_PROBE=1 turns slot 23 into a
 * Xiaoyu-based clone; Jun's import stays unloaded in that mode. */
enum { DIZZY_DONOR=7 }; /* Xiaoyu */
int tekken3_dizzy_probe(void) {
    static int probe=-1;
    if(probe<0){const char *p=getenv("TEKKEN3_DIZZY_PROBE");probe=p && *p && strcmp(p,"0");}
    return probe;
}
static unsigned slot_donor(void){return tekken3_dizzy_probe()?DIZZY_DONOR:9;}"""

EDITS = {
    "src/tekken3_jun_roster.c": [
        ("enum { JUN_ID=23, JUN_MODEL=52, ROSTER_COUNT=22 };", ROSTER_HELPERS, 1),
        ("psx_mod_read_word(0x80096f60+9*4)", "psx_mod_read_word(0x80096f60+slot_donor()*4)", 1),
        ('copy_host(desc+12,(const unsigned char*)"JUN",4);',
         'if(tekken3_dizzy_probe())copy_host(desc+12,(const unsigned char*)"DIZZY",6);\n'
         '    else copy_host(desc+12,(const unsigned char*)"JUN",4);', 1),
        ("    jun_cpu_initialize(cpu_profiles);\n",
         "    jun_cpu_initialize(cpu_profiles);\n"
         "    if(tekken3_dizzy_probe())copy_guest(cpu_profiles+23*12,0x80098260+DIZZY_DONOR*12,12);\n", 1),
        ("psx_mod_write_byte(model_map+i,JUN_MODEL+(i==95?0:i-92));",
         "psx_mod_write_byte(model_map+i,tekken3_dizzy_probe()?\n"
         "            psx_mod_read_byte(model_map+DIZZY_DONOR*4+(i-92)):JUN_MODEL+(i==95?0:i-92));", 1),
        ('    fprintf(stderr,"Jun roster: registered character 23',
         '    if(tekken3_dizzy_probe())fprintf(stderr,"Dizzy probe: slot 23 uses Xiaoyu (character 7) models and profiles\\n");\n'
         '    fprintf(stderr,"Jun roster: registered character 23', 1),
        ("cpu->gpr[5]==JUN_ID)cpu->gpr[5]=9;", "cpu->gpr[5]==JUN_ID)cpu->gpr[5]=slot_donor();", 2),
        ("psx_mod_read_word(0x80096ff0+9*4)", "psx_mod_read_word(0x80096ff0+slot_donor()*4)", 1),
    ],
    "src/tekken3_jun_mod.c": [
        ("extern int tekken3_jun_roster_enabled(void);\n",
         "extern int tekken3_jun_roster_enabled(void);\nextern int tekken3_dizzy_probe(void);\n", 1),
        ("if (!attempted) { attempted=1; load_assets(); }",
         "if (!attempted) { attempted=1;\n"
         "        if(tekken3_dizzy_probe())fprintf(stderr,\"Dizzy probe: Jun import skipped\\n\");\n"
         "        else load_assets(); }", 1),
        # The roster (slot 23) is driven by the selector tick, which normally
        # only runs once Jun's import is loaded. Keep it running in probe mode.
        ("    if(guest)tekken3_jun_selector_tick();\n",
         "    if(guest || tekken3_dizzy_probe())tekken3_jun_selector_tick();\n", 1),
    ],
}

def backup(path): return path.with_name(path.name + ".dizzy-backup")

def undo():
    for name in EDITS:
        path, saved = ROOT / name, backup(ROOT / name)
        if saved.is_file():
            shutil.copyfile(saved, path); saved.unlink()
            print("Teruggezet:", name)
        else:
            print("Geen backup gevonden voor", name)

def apply():
    if not (ROOT / "game.toml").is_file():
        sys.exit("Zet dit script in de hoofdmap van je testkopie (naast game.toml).")
    new = {}
    for name, edits in EDITS.items():
        path = ROOT / name
        if not path.is_file(): sys.exit(f"Bestand ontbreekt: {name}")
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            # Eerdere versie van deze patch: begin opnieuw vanaf de originele backup.
            if not backup(path).is_file():
                sys.exit(f"{name} is al aangepast, maar de backup ontbreekt.")
            text = backup(path).read_text(encoding="utf-8")
        for old, repl, count in edits:
            found = text.count(old)
            if found != count:
                sys.exit(f"Onverwachte code in {name}: verwachtte {count}x\n  {old!r}\n"
                         f"maar vond {found}x. Er is niets aangepast. Stuur deze melding naar Claude.")
            text = text.replace(old, repl)
        new[name] = text
    for name, text in new.items():
        path = ROOT / name
        if not backup(path).is_file(): shutil.copyfile(path, backup(path))
        path.write_text(text, encoding="utf-8", newline="")
        print("Aangepast:", name)
    print("\nKlaar. Bouw nu opnieuw met Bouw-Tekken3.cmd en start met Start-Dizzy-Probe.cmd.")

if __name__ == "__main__":
    undo() if "--undo" in sys.argv else apply()
