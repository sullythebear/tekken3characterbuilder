"""The fairness check: a traffic light per part of a fighter, with Tekken 3's own cast as the
yardstick (stdlib).

Only what the builder can change is measured: the damage of moves (Move Lab, patch 20) and moves
put on other buttons (patch 21). Speed, launchers, punishment and lows stay the style's own, so
they are as fair as the cast itself and are reported as not changed.

cast (model_export.py cast): {"basic": {input: [damage per style]}, "own": [...], "hits": [...]}.
style: the fighter's style as server.command_list gives it ("basic", "own", "records").
"""
from __future__ import annotations

GREEN, AMBER, RED = "green", "amber", "red"
MARGIN = 1.25                      # up to 25 % above the cast: amber
LABELS = {GREEN: "Fair", AMBER: "Fair, a little strong", RED: "Just for fun"}


def yardstick(values: list[int]) -> int:
    """The cast's strongest value but one: a single outlier (King's b+1+2 = 100) sets no bar."""
    values = sorted((int(v) for v in values), reverse=True)
    return values[1] if len(values) > 1 else (values[0] if values else 0)


def light(value: int, bar: int) -> str:
    if value <= bar:
        return GREEN
    return AMBER if value <= bar * MARGIN else RED


def worst(lights) -> str:
    lights = list(lights)
    return RED if RED in lights else AMBER if AMBER in lights else GREEN


def check(cast: dict, style: dict, move_damage: dict | None, move_buttons: dict | None) -> dict:
    """{"label", "light", "parts": [{"part", "light", "notes"}]}."""
    damage = {k: int(v) for k, v in (move_damage or {}).items()}
    records = style.get("records", {})
    basic_bar = {k: yardstick(v) for k, v in cast.get("basic", {}).items()}
    own_bar, hit_bar = yardstick(cast.get("own", [])), yardstick(cast.get("hits", []))
    now = lambda k: damage.get(k, (records.get(k) or [0, 0])[1])

    def bar(k):
        if k in basic_bar:
            return basic_bar[k], "cast"
        return (hit_bar, "cast's string hits") if "#" in k else (own_bar, "cast's own moves")

    parts = []
    for part, keys in (("Damage of the basic inputs", [k for k in damage if k in style.get("basic", {})]),
                       ("Damage of the style's own moves", [k for k in damage if k not in style.get("basic", {})])):
        notes, lights = [], []
        for k in sorted(keys):
            b, what = bar(k)
            lights.append(light(damage[k], b))
            if lights[-1] != GREEN:
                notes.append(f"{k}: {damage[k]} ({what} up to {b})")
        parts.append({"part": part, "light": worst(lights),
                      "notes": notes or ([f"{len(keys)} changed, within the cast"] if keys else ["unchanged"])})
    notes, lights = [], []
    for k, move in sorted((move_buttons or {}).items()):
        if (k not in basic_bar and "#" not in k) or move not in records:
            continue
        b, what = bar(k)                       # a basic input, or a string's later hit
        lights.append(light(now(move), b))
        if lights[-1] != GREEN:
            notes.append(f"{k} gives {now(move)} ({what} up to {b})")
    parts.append({"part": "Moves on other buttons", "light": worst(lights),
                  "notes": notes or ([f"{len(lights)} moved, within the cast's damage"] if lights else ["unchanged"])})
    overall = worst(p["light"] for p in parts)
    parts.append({"part": "Speed, launchers, punishment, lows", "light": None,
                  "notes": ["the style's own (not measured; moved moves keep their own speed)"]})
    return {"label": LABELS[overall], "light": overall, "parts": parts}
