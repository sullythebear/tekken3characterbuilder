# Mokujin (Copycat)

Each entry says how it is known: **tested** (seen in game), **code** (read in the projects' source), or **inferred**.

## Mokujin's round-start draw (code, SLUS-00402)

- At round start `0x8002AA44` / `0x8002AACC` test `actor+0x18` (the selection ID) == 15 for P1 / P2
  and only then call `0x8004F2DC(actor)`. That draws a random unlocked character from the
  availability bits at `0x80097EF0` (mask `0x13FFF`, 22 IDs) and writes the drawn character's ID
  (metadata table `0x80097D40`, descriptor byte 9) to `actor+0x16`, the moves key.
- A custom fighter with Mokujin as donor has `actor+0x18` = its own ID (41..), so the draw does
  not run and the fighter loads "moveset 15" as is.
- **Tested 2026-10-01 (builder 0.3.6, patch T3CB-PATCH-4, fighter MOKU = ID 42, donor 15,
  Arcade, costume 2): Mokujin does NOT work as a donor.** Selecting works and the descriptor is
  Mokujin's (`0f 37 0f 0f 10 09 02 16`), `actor+0x16` 15, model 31 (Mokujin costume 2; stock model
  map for 15 is `30, 31`). But `0x80052958` loads `a1=15` and the moves header reads `0002`
  (key 0, not 15): slot 15 holds no real moveset, because stock Mokujin always has a drawn ID in
  `actor+0x16` before his moves load. In game the model looked squashed into one block and the
  game froze on the first attack button. The test report showed 0 errors and exit code 0 (the
  user closed the frozen game): **the report cannot detect a freeze**, ask the user.
- Consequence: a Mokujin-based fighter needs the round-start draw. That is a patch change: run
  `0x8004F2DC(actor)` at round start (`0x8002A914`, where Expanded already hooks Mokujin in
  `tekken3_ttt1_combat.c`) when `tekken3_guest_native(actor+0x18) == 15`, so `actor+0x16` gets a
  drawn ID like stock Mokujin.
- The round-start routine `0x8002A914` itself reloads the movesets after the draw: `0x80069AA8`
  (copies `actor+0x16` into the request table at `0x800A0510`), `0x80069F74` (loads),
  `0x8006A158` (moves pointers). So writing `actor+0x16` on entry of `0x8002A914` is enough.
- **0.3.6 = T3CB-PATCH-5 (built 2026-10-01, not yet tested in game):**
  `tekken3_custom_copycat_draw()` (roster.c) runs on entry of `__wrap_func_8002A914` (combat.c):
  for each player whose `actor+0x18` is a custom fighter with donor 15 it draws an unlocked
  fighter from `0x80097EF0 & 0x13FFF` (IDs 0..13 and 16, never Mokujin himself) with Expanded's
  `draw()`, writes descriptor byte 9 of `0x80097D40 + id * 16` to `actor+0x16`, and logs
  `Custom fighters: <name> copies character <id> this round`. Install → uninstall restores the
  four sources byte for byte (checked). The broken MOKU was deleted from the test folder; a new
  Copycat fighter is needed for the test. Expected in the report: one `copies character` line
  per round and `Custom probe` header keys that follow the drawn IDs.
- **Tested 2026-10-01 (T3CB-PATCH-5, MOKU = ID 42 re-created by the user, Arcade, 1m55s): works
  "very well" per the user.** Draws per round: 9, 1, 12, 2, 7 (Jin, Law, Bryan, Lei, Xiaoyu); each
  time `0x80052958` loads `a1` = the drawn ID and the header key follows (`0900`, `0100`, `0c00`,
  `0200`, `0700`). Between fights `actor+0x16` briefly reads 15 (key 0) again before the next
  draw; harmless, the draw comes before the moves load. The model moves normally.
- **Sword (found in that test):** MOKU held Mokujin's sword with every style; stock Mokujin only
  holds it with Yoshimitsu's. `0x8003615C`: `if (actor+0x18 == 15) actor+0x7C0 = (actor+0x16 == 4)`,
  the only writer of `actor+0x7C0` in SLUS (no direct `jal` caller, so it runs through a table).
  For a custom fighter `actor+0x18` is 41.., so the flag was never updated. **T3CB-PATCH-6:**
  `copycat_sword()` in the roster tick sets `actor+0x7C0 = (actor+0x16 == 4)` every frame for a
  custom fighter with donor 15. Reversible (checked).
- **Tested 2026-10-01 (T3CB-PATCH-6, MOKU, Arcade, 2m19s): works perfectly per the user.** Draws
  6, 7, 4, 13, 9 (Hwoarang, Xiaoyu, Yoshimitsu, Heihachi, Jin), header keys follow each draw;
  the sword showed only in the Yoshimitsu round. So `actor+0x7C0` is the sword flag (1 = held).
- Still open, not fixed: the sword **glow** (`0x8003172C`) runs when `actor+0x18 == 4`, or when
  `actor+0x18 == 15` and `actor+0x16 == 4`. So a custom fighter based on Yoshimitsu, and a Copycat
  fighter that drew Yoshimitsu, have no sword glow. Fixing it means faking `actor+0x18` around a
  long (sliceable) function; not done yet.
- Other `actor+0x18 == 15` checks in SLUS, not looked at yet: `0x80075450` (calls `0x80075548`)
  and `0x800787DC` (sets 246 / 1 before `0x80077724`). They may be more Mokujin-only details.
- Other donors marked "not tested" (Ogre, Gon, Dr. B, True Ogre) may have their own special
  cases; test each before calling it supported.
