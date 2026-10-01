"""Creator support for Tekken 3 Recompiled.

Patches Jun's roster code so that slot 23 can be a clone of any donor while
playing. The donor and name are chosen at launch through environment variables
(T3CB_DONOR, T3CB_NAME), so after one build you can switch characters without
rebuilding. Without T3CB_DONOR the game behaves exactly like the original.
"""
from __future__ import annotations
from pathlib import Path

MARKER = "tekken3_creator_slot"
OLD_MARKERS = ("tekken3_dizzy_probe",)
BACKUP_SUFFIXES = (".t3cb-backup", ".dizzy-backup")  # own backup first, then the Dizzy probe's
LOG_TAG = "Creator slot:"

ROSTER = "src/tekken3_jun_roster.c"
MOD = "src/tekken3_jun_mod.c"

HELPERS = r'''enum { JUN_ID=23, JUN_MODEL=52, ROSTER_COUNT=22 };
/* Tekken 3 Character Builder: T3CB_DONOR=<0..20> turns slot 23 into a clone
 * of that fighter and T3CB_NAME sets its internal name. Jun's import stays
 * unloaded in that mode. Without T3CB_DONOR nothing changes. */
static int creator_donor_id(void) {
    static int donor=-2;
    if(donor==-2) {
        const char *p=getenv("T3CB_DONOR");char *end=NULL;long v=-1;
        if(p && *p)v=strtol(p,&end,10);
        donor=(p && *p && end && !*end && v>=0 && v<=20)?(int)v:-1;
    }
    return donor;
}
int tekken3_creator_slot(void) {return creator_donor_id()>=0;}
static unsigned slot_donor(void) {return tekken3_creator_slot()?(unsigned)creator_donor_id():9;}
static void creator_name(char out[16]) {
    const char *p=getenv("T3CB_NAME");unsigned n=0;
    for(;p && *p && n<15;p++) {
        char c=*p;if(c>='a' && c<='z')c=(char)(c-32);
        if((c>='A' && c<='Z') || (c>='0' && c<='9') || c==' ' || c=='-' || c=='.')out[n++]=c;
    }
    if(!n){memcpy(out,"CUSTOM",6);n=6;}
    out[n]=0;
}'''

ROSTER_EDITS = [
    ("enum { JUN_ID=23, JUN_MODEL=52, ROSTER_COUNT=22 };", HELPERS, 1),
    ("psx_mod_read_word(0x80096f60+9*4)", "psx_mod_read_word(0x80096f60+slot_donor()*4)", 1),
    ('copy_host(desc+12,(const unsigned char*)"JUN",4);',
     'if(tekken3_creator_slot()) {\n'
     '        char name[16];creator_name(name);\n'
     '        copy_host(desc+12,(const unsigned char*)name,(unsigned)strlen(name)+1);\n'
     '    } else copy_host(desc+12,(const unsigned char*)"JUN",4);', 1),
    ("    jun_cpu_initialize(cpu_profiles);\n",
     "    jun_cpu_initialize(cpu_profiles);\n"
     "    if(tekken3_creator_slot())copy_guest(cpu_profiles+23*12,0x80098260+slot_donor()*12,12);\n", 1),
    ("psx_mod_write_byte(model_map+i,JUN_MODEL+(i==95?0:i-92));",
     "psx_mod_write_byte(model_map+i,tekken3_creator_slot()?\n"
     "            psx_mod_read_byte(model_map+slot_donor()*4+(i-92)):JUN_MODEL+(i==95?0:i-92));", 1),
    ('    fprintf(stderr,"Jun roster: registered character 23',
     '    if(tekken3_creator_slot()) {\n'
     '        char name[16];creator_name(name);\n'
     '        fprintf(stderr,"Creator slot: slot 23 is %s, cloned from character %u\\n",name,slot_donor());\n'
     '    }\n'
     '    fprintf(stderr,"Jun roster: registered character 23', 1),
    ("cpu->gpr[5]==JUN_ID)cpu->gpr[5]=9;", "cpu->gpr[5]==JUN_ID)cpu->gpr[5]=slot_donor();", 2),
    ("psx_mod_read_word(0x80096ff0+9*4)", "psx_mod_read_word(0x80096ff0+slot_donor()*4)", 1),
]

MOD_EDITS = [
    ("extern int tekken3_jun_roster_enabled(void);\n",
     "extern int tekken3_jun_roster_enabled(void);\nextern int tekken3_creator_slot(void);\n", 1),
    ("if (!attempted) { attempted=1; load_assets(); }",
     "if (!attempted) { attempted=1;\n"
     "        if(tekken3_creator_slot())fprintf(stderr,\"Creator slot: Jun import skipped\\n\");\n"
     "        else load_assets(); }", 1),
    ("    if(guest)tekken3_jun_selector_tick();\n",
     "    if(guest || tekken3_creator_slot())tekken3_jun_selector_tick();\n", 1),
]

EDITS = {ROSTER: ROSTER_EDITS, MOD: MOD_EDITS}

from expanded_patch_data import EXPANDED_EDITS, EXPANDED_ROSTER  # noqa: E402

# Supported projects. "recompiled": FishB0nes98's Tekken3Recompiled (Jun's slot
# becomes the fighter at launch). "expanded": omarma's Tekken 3 Expanded (a
# CUSTOM page of fighters read from customs.txt).
PROFILES = {
    "recompiled": {"edits": EDITS, "marker": MARKER, "old": OLD_MARKERS, "tag": LOG_TAG,
                   "roster": ROSTER, "version": "v0.1.4"},
    "expanded": {"edits": EXPANDED_EDITS, "marker": "tekken3_guest_native", "old": (),
                 "tag": "Custom fighters:", "roster": EXPANDED_ROSTER, "version": "0.1.2",
                 "revision": "T3CB-PATCH-3"},
}


def project_kind(root: Path) -> str | None:
    if (root / EXPANDED_ROSTER).is_file():
        return "expanded"
    if (root / ROSTER).is_file():
        return "recompiled"
    return None


class PatchError(Exception):
    pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _backups(path: Path):
    return [path.with_name(path.name + s) for s in BACKUP_SUFFIXES]


def _is_modified(text: str, kind: str = "recompiled") -> bool:
    p = PROFILES[kind]
    return p["marker"] in text or any(m in text for m in p["old"])


def original_text(path: Path, kind: str = "recompiled") -> str:
    """The unmodified source: from a backup if the file has already been patched."""
    text = _read(path)
    if not _is_modified(text, kind):
        return text
    for b in _backups(path):
        if b.is_file():
            original = _read(b)
            if not _is_modified(original, kind):
                return original
    raise PatchError(f"{path.name} has been modified, but no original backup was found. "
                     "Copy your Easy Setup folder again to restore it.")


def status(root: Path, kind: str = "recompiled") -> dict:
    p = PROFILES[kind]
    result = {"installed": False, "old_probe": False, "outdated": False, "compatible": False, "problem": None}
    try:
        texts = {name: _read(root / name) for name in p["edits"]}
    except OSError:
        result["problem"] = "The source files this builder patches are missing from this folder."
        return result
    result["installed"] = all(p["marker"] in t for t in texts.values())
    revision = p.get("revision")
    if result["installed"] and revision and revision not in texts[p["roster"]]:
        result["installed"], result["outdated"] = False, True
    result["old_probe"] = any(any(m in t for m in p["old"]) for t in texts.values())
    try:
        _plan(root, kind)
        result["compatible"] = True
    except PatchError as error:
        result["problem"] = str(error)
    return result


def _plan(root: Path, kind: str = "recompiled") -> dict:
    new = {}
    for name, edits in PROFILES[kind]["edits"].items():
        path = root / name
        if not path.is_file():
            raise PatchError(f"File missing: {name}")
        text = original_text(path, kind)
        for old, repl, count in edits:
            found = text.count(old)
            if found != count:
                raise PatchError(f"This Tekken 3 Recompiled version differs in {name} "
                                 f"(expected a known piece of code {count}x, found it {found}x). "
                                 f"The builder supports version {PROFILES[kind]['version']} of this project.")
            text = text.replace(old, repl)
        new[name] = text
    return new


def install(root: Path, kind: str = "recompiled") -> list[str]:
    new = _plan(root, kind)  # checks everything before anything is written
    changed = []
    for name, text in new.items():
        path = root / name
        own_backup = path.with_name(path.name + BACKUP_SUFFIXES[0])
        if not own_backup.is_file():
            own_backup.write_text(original_text(path, kind), encoding="utf-8", newline="")
        path.write_text(text, encoding="utf-8", newline="")
        changed.append(name)
    return changed


def uninstall(root: Path, kind: str = "recompiled") -> list[str]:
    restored = []
    for name in PROFILES[kind]["edits"]:
        path = root / name
        if not path.is_file():
            continue
        text = _read(path)
        if _is_modified(text, kind):
            path.write_text(original_text(path, kind), encoding="utf-8", newline="")
            restored.append(name)
        for b in _backups(path):
            if b.is_file():
                b.unlink()
    return restored
