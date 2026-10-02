"""Fighter models for the builder's 3D preview, read from the player's own disc.

Runs with Tekken 3 Expanded's Python (.setup/venv) and reuses Expanded's tools:
bns_tool.py (TEKKEN3.BNS records), tools/ttt1/model/fmt.py and tools/ttt1/anim_model.py
(3DMK rows, bind, rotations), tim_tool.py (costume TIMs), motion.py (a stance pose).

  model_export.py donors --root R                      -> JSON: models per donor costume
  model_export.py model  --root R --model 6 --out f    -> JSON mesh for the 3D preview

Model m lives in BNS records 71 + 4m (3DMK) and 73 + 4m (ARC with the costume TIMs).
The output holds game data: it stays in the builder's cache and is never shared.
"""
from __future__ import annotations

import argparse, base64, json, struct, sys
from pathlib import Path

MODEL_MAP = 0x800958C4
FIRST_MODEL_RECORD = 71


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(2)


def setup(root: Path) -> None:
    for sub in ("tools/ttt1/model", "tools/ttt1", "tools"):
        sys.path.insert(0, str(root / sub))


def exe_bytes(root: Path) -> bytes:
    path = root / "disc/SLUS_004.02"
    if not path.is_file():
        fail("disc/SLUS_004.02 is missing. Run Tekken 3 Expanded's setup first.")
    return path.read_bytes()


def donors(root: Path) -> dict:
    exe = exe_bytes(root)
    at = MODEL_MAP - 0x80010000 + 0x800
    return {d: [m for m in exe[at + d * 4: at + d * 4 + 4] if m != 255] for d in range(21)}


def track_image(root: Path) -> Path:
    disc = root / "disc"
    found = sorted(disc.glob("*Track 1*.bin")) or sorted(disc.glob("*.bin"), key=lambda p: -p.stat().st_size)
    if not found:
        fail("The Tekken 3 disc image is missing from the disc folder.")
    return found[0]


def records(root: Path, ids: list[int]) -> dict[int, bytes]:
    import bns_tool
    table, _, _ = bns_tool.load_us_table(root / "disc/SLUS_004.02")
    out = {}
    with bns_tool.open_bns_source(track_image(root)) as source:
        for i in ids:
            entry = table[i]
            out[i] = source.read_at(entry.offset, entry.size)
    return out


def stance_pose(root: Path) -> list[int] | None:
    """Frame 0 of the first clip of Kazuya's TTT1 moveset (Expanded's import data), or None."""
    try:
        from motion import decode
        bank = (root / "workspace/ttt1-import/ttt1/bankedroms.bin").read_bytes()
        ram = (root / "workspace/ttt1-import/captures/kazuya-select-ram.bin").read_bytes()
        pack = (root / "workspace/ttt1-import/kazuya/guest/Kazuya-TTT1-combat.jmv").read_bytes()
        first = struct.unpack_from("<I", pack, 36)[0]
        clip = struct.unpack_from("<I", ram, first & 0x3FFFFF)[0]
        pose = decode(bank, clip, 0)
        return pose if len(pose) == 57 else None
    except (OSError, ValueError, IndexError, struct.error, ImportError):
        return None


# Standing pose. Rest-pose layout (all rotations zero): every main bone runs along local +X,
# sideways offsets are local Z, so local Y is front/back. Chains: spine 1 -> head 19;
# pelvis 3 -> thigh 5/8 -> shin 6/9 -> foot 7/10; spine -> collarbone 11/15 -> upper arm 12/16
# -> forearm 13/17 -> hand 14/18. Relative to the spine the pelvis is a half turn about Z.
ARM_SPREAD, LEG_SPREAD = 0.38, 0.07     # radians: arms ~22° and thighs ~4° away from the body
FOOT_ANGLE = -1.571                     # radians about the shin's sideways axis: foot flat, toes forward
NOT_HUMAN = (42, 43)                    # Gon: a dinosaur; standing tears his head off his body
HEAD_TURN = -0.785                      # radians about the spine: undoes the stance's look over the shoulder


def align(a, b):
    """Shortest rotation turning unit vector a onto unit vector b."""
    import numpy as np
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c < -0.999999:                       # opposite: half turn about any perpendicular axis
        p = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1.0, 0])
        p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def stand_pose(m, stance: dict, twist: float = 0.0):
    """fix() for world(): a relaxed standing pose built from the skeleton's own axes (no borrowed
    stance, whose turned upper body made the torso sit crooked on the hips). Spine straight up,
    legs straight down a little apart, collarbones level, arms hanging ~22° out. Head, feet and
    hands keep their stance angle to their parent (their local X is not along the limb: a foot's
    X points forward, so the rest angle would point the feet down). That angle is taken against
    the stance parent turned straight by the shortest rotation, not against the stance parent
    itself, so a head that looked over a turned shoulder now looks ahead. stance = world() of the
    stance without fix. Game Y points down."""
    import numpy as np
    from fmt import row

    def about_y(a):
        c, s = np.cos(a), np.sin(a)
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])

    def about_x(a):
        c, s = np.cos(a), np.sin(a)
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])

    def about_axis(u, a):             # rotation by a about unit vector u (Rodrigues)
        k = np.array([[0, -u[2], u[1]], [u[2], 0, -u[0]], [-u[1], u[0], 0]])
        return np.eye(3) + np.sin(a) * k + (1 - np.cos(a)) * k @ k

    spine = np.array([[0.0, 1, 0], [-1, 0, 0], [0, 0, 1]])   # X up, Y front/back, Z sideways
    pelvis = spine @ np.diag([-1.0, -1, 1])

    def side(r):                     # +1 / -1: which side the limb's root offset puts it on
        return 1.0 if row(m, r)[5] >= 0 else -1.0

    def fix(r, R, W, w):
        if r == 1:
            return spine
        if r == 3:
            return pelvis
        if r in (5, 8):              # about_y(a) turns X toward -Z for a > 0
            return pelvis @ about_y(-side(r) * LEG_SPREAD)
        if r in (6, 9):
            return W[r - 1][0]
        if r in (11, 15):            # collarbone: level, out to its side
            return spine @ about_y(-side(r) * np.pi / 2) @ about_x(side(r) * twist)
        if r in (12, 16):            # upper arm: down, a little out
            return spine @ about_y(-side(r - 1) * (np.pi - ARM_SPREAD)) @ about_x(side(r - 1) * twist)
        if r in (13, 17):
            return W[r - 1][0]
        if r in (14, 18):            # hands: straight on from the forearm
            return W[r - 1][0]
        if r in (7, 10):             # feet: at a right angle to the shin, toes forward
            return W[r - 1][0] @ about_axis(np.array([0.0, 0, 1]), FOOT_ANGLE)
        if r == 19:                  # head: carried by the straightened spine, then turned to the front
            Ps, Pn = stance[1][0], W[1][0]
            straight = align(Ps[:, 0] / np.linalg.norm(Ps[:, 0]), Pn[:, 0]) @ Ps
            return about_axis(spine[:, 0], HEAD_TURN) @ Pn @ straight.T @ stance[19][0]
        return R
    return fix


# Turns found by seam fitting (scratch fit.py, 10 models): each is a local rotation of a joint about
# its own axis (0 = X, along the bone: twist; 2 = Z, sideways: pitch), applied after stand_pose, the
# joint's children following. Left rows get the angle, right rows its mirror (twists change sign,
# a sideways pitch keeps it). The seams (triangles shared by two bones) are least stretched with
# these. Feet: FOOT_ANGLE +90° had them upside down, then (fitted from there) back to front;
# -90° with these small turns cuts the ankle seams' stretch to 40 % (fit over 8 models).
POSE_TWEAKS = {  # name: (left rows, right rows, axis, radians)
    "pelvis_pitch": ([3], [], 2, 0.06), "thigh_twist": ([5], [8], 0, 0.12),
    "foot_twist": ([7], [10], 0, 0.15), "foot_pitch": ([7], [10], 2, 0.29),
}
MIRRORED = {"foot_pitch"}


def tweaked(m, stance: list, W: dict) -> dict:
    """world() of stand_pose W with POSE_TWEAKS applied as local rotations."""
    import numpy as np
    import anim_model as A
    parent = A.ROW_PARENT
    local = {r: W[parent[r]][0].T @ W[r][0] for r in parent}
    for name, (left, right, axis, angle) in POSE_TWEAKS.items():
        for rows, sign in ((left, 1), (right, 1 if name in MIRRORED else -1)):
            for r in rows:
                v = np.zeros(3)
                v[axis] = sign * angle
                c, s = np.cos(v[axis]), np.sin(v[axis])
                turn = {0: [[1, 0, 0], [0, c, -s], [0, s, c]], 2: [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
                local[r] = local[r] @ np.array(turn)
    return world(m, stance, lambda r, R, Wn, w: Wn[parent[r]][0] @ local[r] if r in local else R)


def facing(W):
    """Turns the whole model so the shoulders (row 11 -> 15) lie along +X."""
    import numpy as np
    d = W[15][1] - W[11][1]
    a = np.arctan2(d[2], d[0])
    turn = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return {r: (turn @ R, turn @ T) for r, (R, T) in W.items()}


def world(m, pose, fix=None):
    """Per-row (R, T) for a 57-channel pose, like anim_model.world() but tolerating empty
    accessory rows (part -1). fix(r, R, W, w) may replace a main row's world rotation."""
    import numpy as np
    import anim_model as A
    from fmt import nrows, row
    loc = {}
    for b in range(18):
        R = A.rotation(pose[3 + b * 3: 6 + b * 3]) if pose else np.eye(3)
        if b == 0:
            R[1:, :] *= -1
        loc[b] = R
    W = {0: (loc[0], np.zeros(3))}

    def get(r):
        if r in W:
            return W[r]
        w = row(m, r)
        part = w[6] & 0xFF
        if r in A.ROW_PARENT:
            Rp, Tp = get(A.ROW_PARENT[r])
            b = A.PART_BONE[A.P2R.index(r)]
            R = Rp @ loc[b]
            if fix:
                R = fix(r, R, W, w)
            W[r] = (R, Tp + Rp @ np.array(w[3:6], dtype=float))
        elif r in (2, 4, 20):
            W[r] = get({2: 1, 4: 3, 20: 19}[r])
        elif r in (21, 22, 23, 24) and part < len(A.P2R):
            Rp, Tp = get(A.P2R[part])
            W[r] = (Rp @ A.rotation(w[7:10], neg=False), Tp + Rp @ np.array(w[3:6], dtype=float))
        elif r in (25, 26) and part < len(A.P2R):
            W[r] = get(A.P2R[part])
        else:
            W[r] = W[0]
        return W[r]

    for r in range(nrows(m)):
        get(r)
    return W


BAND_WORDS = 128                       # two 4-bit texture pages of 64 halfwords
PAGE2 = 0x100                          # material bit: texture from the second page
SECOND_AFTER = {2: 1, 4: 3, 20: 19}     # second geometry layer of spine, pelvis, head -> its main row


def bind(m) -> dict:
    """{row: vertex slots}, like anim_model.bind() but for Tekken 3's own models: the second
    layers (rows 2, 4, 20) are drawn right after their main row. anim_model only takes them when
    word 6 holds a guest-model part number; T3 models keep 0 or 1 there, so the layer was skipped
    (missing chest/hair/face pieces on nearly every model) and the shoulder and head rows that
    borrow its vertices lost triangles (Hwoarang, Bryan, True Ogre...). With this order every
    slot of all 48 fighter models resolves."""
    import anim_model as A
    from fmt import row, nrows
    from simulate import vlist
    scratch, cache, out, order = [None] * 128, {}, {}, []
    for p in range(1, 22):
        order.append(A.P2R[p])
        for r in A.SECONDS:
            if r >= nrows(m) or r in order:
                continue
            w = row(m, r)
            if not (w[10] and w[1] > 2):
                continue
            if r in (25, 26) and (w[6] & 0xFF) == p or SECOND_AFTER.get(r) == A.P2R[p]:
                order.append(r)
    for r in order:
        w = row(m, r)
        if not w[10] or w[1] <= 2:
            continue
        a = vlist(m, r)
        if not a:
            continue
        L = [scratch[b // 2 - 1] if 0 < b // 2 <= 128 else None for b in a["g1"]]
        L += [cache.get(b // 2) for b in a["g2"]]
        s = len(L)
        L += [(r, tuple(v[:3])) for v in a["verts"]]
        copies = []
        for gi, grp in enumerate(a["tails"][:5]):
            for f in grp:
                if s >= len(L):
                    break
                if gi in (0, 3):
                    cache[(f & 0xFF) // 2] = L[s]
                elif gi == 4:
                    copies.append(((f & 0xFF) // 2 - 1, s))
                s += 1
        scratch[:len(L)] = L
        for t, sl in copies:
            if 0 <= t < 128:
                scratch[t] = L[sl]
        out[r] = list(L)
    return out


def export_model(root: Path, model: int) -> dict:
    import numpy as np
    import anim_model as A
    from fmt import row, block, parse_b, parse_c_ps1
    from tim_tool import scan_tims

    if not 0 <= model < 52:
        fail("No such model.")
    rid = FIRST_MODEL_RECORD + 4 * model
    data = records(root, [rid, rid + 2])
    m, arc = data[rid], data[rid + 2]
    if m[8:12] != b"3DMK":
        fail("This record is not a fighter model.")

    stance = stance_pose(root)       # Kazuya's: the standing pose's constants were fitted on it
    fight = world(m, stance)
    # Standing pose; Gon (not human) keeps the stance. Fight stances are not shown: Kazuya's and
    # the fighters' own TTT1 stances both looked wrong to the user (see NOTES).
    poses = [facing(fight) if model in NOT_HUMAN else facing(tweaked(m, stance, world(m, stance, stand_pose(m, fight))))]
    positions, uvs, materials, triangles, bones = [[] for _ in poses], [], [], [], []
    for r, slots in bind(m).items():
        w = row(m, r)
        prims = parse_c_ps1(block(m, w[2]))
        pos = [[None if s is None else W[s[0]][0] @ np.array(s[1], dtype=float) + W[s[0]][1] for s in slots]
               for W in poses]
        i = 0
        for k, fam in enumerate(parse_b(block(m, w[1]))):
            for rec in fam:
                corners = A.prim_verts(k, rec)
                _, mat, uv = prims[i]
                i += 1
                for a, b, c in ([(0, 1, 2)] if len(corners) == 3 else [(0, 1, 2), (1, 3, 2)]):
                    ps = [[at[corners[j]] if corners[j] < len(at) else None for j in (a, b, c)] for at in pos]
                    p = ps[0]
                    q = [uv[j] for j in (a, b, c)]
                    if mat is None or any(x is None for x in p) or None in q:
                        continue
                    base = len(materials)
                    for out, pts in zip(positions, ps):
                        for point in pts:
                            out += [round(float(point[0]), 1), round(float(-point[1]), 1), round(float(point[2]), 1)]
                    # Material bit 0x100 selects the second texture page (64 halfwords further
                    # on, where e.g. Law's belt and Bryan's trousers are); the CLUT is the id
                    # without it.
                    page = mat & PAGE2
                    shift = (128 if mat & 0x8000 else 256) if page else 0
                    for u, v in q:
                        uvs += [u + shift, v]
                        materials.append(mat & ~PAGE2)
                    triangles += [base, base + 1, base + 2]
                    bones.append(r)                  # the row (body part) that draws it

    band = np.zeros((256, BAND_WORDS), dtype=np.uint16)
    cluts = {}
    for t in scan_tims(arc):
        img = t.image
        if t.mode == 0 and (img.x, img.y, img.width_words, img.height) == (0, 0, 8, 32):
            continue  # the strip tiles (uploaded by 0x8007619C elsewhere), not the model band
        if t.clut is not None:
            c = t.clut
            cols = np.frombuffer(arc[c.offset + 12: c.offset + 12 + c.width_words * 2], dtype="<u2")
            cluts[(c.y << 6) | (c.x >> 4)] = [int(x) for x in cols]
        width = min(img.width_words, BAND_WORDS - img.x)
        if width <= 0 or img.y >= 256:
            continue
        raw = arc[img.offset + 12: img.offset + 12 + img.width_words * img.height * 2]
        px = np.frombuffer(raw, dtype="<u2").reshape(img.height, img.width_words)
        rows = min(img.height, 256 - img.y)
        band[img.y: img.y + rows, img.x: img.x + width] = px[:rows, :width]

    used = sorted({int(x) & 0x7FFF for x in materials})   # 8-bit materials name their CLUT too (Bryan: 0 and 64)
    return {"format": 7, "model": model, "positions": positions[0], "uv": uvs, "material": [int(x) for x in materials],
            "triangles": triangles, "bones": bones, "band": base64.b64encode(band.tobytes()).decode(), "band_words": BAND_WORDS,
            "cluts": {str(k): v for k, v in sorted(cluts.items())},
            "missing": [u for u in used if u not in cluts]}


# --- Own models (phase 1): a fighter model file the game loads over its donor's model ---------
# 3DMK header: rows (27), scale, "3DMK", 0, u32 pointer at +16 (to 24 + 27 * 56 - 8), 0; then 27
# rows of 14 i32. Pointer words: header +16, row words 0, 1, 2, 12, 13 when > 2, and the entries
# of the hand-pose table that word 13 points to (as tools/ttt1/model/convert.py relocates them).
MODEL_HEADER = 24 + 27 * 56


def relocations(m: bytes) -> list[int]:
    """File offsets of every pointer word in a 3DMK model."""
    from fmt import row, block, nrows
    out = [16]
    for r in range(nrows(m)):
        w = row(m, r)
        out += [24 + r * 56 + 4 * k for k in (0, 1, 2, 12, 13) if w[k] > 2]
        if w[13] > 2:
            out += [w[13] + 4 * i for i in range(len(block(m, w[13])) // 4)]
    return sorted(set(out))


def own_vertex_span(m: bytes, r: int) -> tuple[int, int] | None:
    """(file offset, count) of row r's own vertices (4 x s16 each). Row r reads row r-1's word 12."""
    import struct
    from fmt import row, block, parse_a
    w = row(m, r - 1)
    if w[12] <= 2:
        return None
    a = parse_a(block(m, w[12]))
    n = len(a["verts"])
    return w[12] + a["used"] - 8 * n, n


def scaled_rows(m: bytes, rows: list[int], factor: float) -> bytes:
    """A copy of model m with the own vertices of `rows` scaled about their bone (phase 1 test)."""
    import struct
    out = bytearray(m)
    for r in rows:
        span = own_vertex_span(m, r)
        if not span:
            continue
        at, n = span
        for i in range(n):
            x, y, z, pad = struct.unpack_from("<4h", out, at + 8 * i)
            clamp = lambda v: max(-32768, min(32767, int(round(v * factor))))
            struct.pack_into("<4h", out, at + 8 * i, clamp(x), clamp(y), clamp(z), pad)
    return bytes(out)


def own_model_file(model: int, stock: bytes, new: bytes, texture: dict | None = None) -> bytes:
    """<prefix>-model.bin: "T3CM", u16 version (1, or 2 with a texture), u16 model it replaces,
    u32 new size, u32 relocation count, the stock model's header (how the patch recognises it in
    memory), the new 3DMK model, then u32 relocation offsets. Version 2 adds "T3TX", u16 band
    width in halfwords (64), u16 rows (256), u16 CLUT id, u16 colours, the colours (PS1 15-bit, consecutive CLUTs),
    then the band halfwords: the first texture page of the player's band."""
    import struct
    if new[8:12] != b"3DMK" or struct.unpack_from("<I", new, 0)[0] != 27:
        fail("Not a 27-row 3DMK model.")
    relocs = relocations(new)
    out = (b"T3CM" + struct.pack("<HHII", 2 if texture else 1, model, len(new), len(relocs)) + stock[:MODEL_HEADER]
           + new + b"".join(struct.pack("<I", r) for r in relocs))
    if texture:
        band = texture["band"]
        runs = texture.get("runs") or [(0, texture["palette"])]
        if len(runs) == 1:
            out += b"T3TX" + struct.pack("<4H", band.shape[1], band.shape[0], runs[0][0], len(runs[0][1]))
            out += b"".join(struct.pack("<H", c) for c in runs[0][1])
        else:          # T3CB-PATCH-12: several CLUT runs (id 0xFFFF, then id/count/colours each)
            out += b"T3TX" + struct.pack("<4H", band.shape[1], band.shape[0], 0xFFFF, len(runs))
            for cid, pal in runs:
                out += struct.pack("<2H", cid, len(pal)) + b"".join(struct.pack("<H", c) for c in pal)
        out += band.astype("<u2").tobytes()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("donors", "model", "ownmodel"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--model", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--scale-rows", default="", help="ownmodel test: rows whose own vertices are scaled")
    parser.add_argument("--factor", type=float, default=1.0)
    args = parser.parse_args()
    setup(args.root)
    if args.command == "donors":
        print(json.dumps(donors(args.root)))
        return
    if args.command == "ownmodel":
        if args.model is None or args.out is None:
            fail("--model and --out are needed.")
        rid = FIRST_MODEL_RECORD + 4 * args.model
        stock = records(args.root, [rid])[rid]
        rows = [int(x) for x in args.scale_rows.split(",") if x.strip()]
        new = scaled_rows(stock, rows, args.factor) if rows else stock
        data = own_model_file(args.model, stock, new)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
        print(f"OK own model over model {args.model}: {len(new)} bytes, {len(relocations(new))} relocations")
        return
    if args.model is None or args.out is None:
        fail("--model and --out are needed.")
    out = export_model(args.root, args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    tmp.replace(args.out)
    print(f"OK model {args.model}: {len(out['triangles']) // 3} triangles, {len(out['cluts'])} palettes")


if __name__ == "__main__":
    main()
