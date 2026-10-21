// Move Lab: the style's COMMAND LIST as Tekken 3 shows it, read from the player's disc
// (/api/moves). Read-only for now. Uses app.js's state, api, $ and DONORS.
(() => {
  let shown = null, shownFor = null;     // the style shown, for which fighter

  // the basic inputs grouped by direction, in Tekken order
  const ORDER = ["", "f", "b", "d", "df", "db", "u", "uf", "ub"];
  // basic: {input: damage}; titles (own moves): {input: move name}, kept in COMMAND LIST order
  function showBasic(basic, gridId = "basic-list", titles = null) {
    const grid = $(gridId);
    grid.textContent = "";
    const names = Object.keys(basic).filter((k) => basic[k]);
    const dir = (k) => (k.includes("+") && isNaN(k.split("+")[0]) ? k.split("+")[0] : "");
    if (!titles) names.sort((a, b) => ORDER.indexOf(dir(a)) - ORDER.indexOf(dir(b)) || a.length - b.length || a.localeCompare(b));
    const own = state.current.move_damage || {};
    for (const k of names) {
      const cell = document.createElement("label");
      const input = document.createElement("span"), value = document.createElement("input");
      input.className = "move-input";
      input.textContent = titles && titles[k] ? titles[k] : k;
      value.type = "number"; value.min = "0"; value.max = "200";
      value.dataset.move = k; value.dataset.original = basic[k];
      value.value = own[k] ?? basic[k];
      value.title = `Tekken 3: ${basic[k]}`;
      const mark = () => cell.classList.toggle("changed", Number(value.value) !== basic[k]);
      value.addEventListener("input", () => { mark(); markDirty(); fairSoon(); });
      mark();
      cell.append(input, value);
      grid.append(cell);
    }
    return names.length;
  }

  // moves on buttons: each basic input with alias slots, a choice of the style's other moves
  function showButtons(r, titles) {
    const grid = $("buttons-list"), own = state.current.move_buttons || {};
    grid.textContent = "";
    const inputs = Object.keys(r.slots || {}).filter((k) => (r.basic || {})[k]);
    const later = Object.keys(r.slots || {}).filter((k) => k.includes("#"));    // a string's later hit
    const dir = (k) => (k.includes("+") && isNaN(k.split("+")[0]) ? k.split("+")[0] : "");
    inputs.sort((a, b) => ORDER.indexOf(dir(a)) - ORDER.indexOf(dir(b)) || a.length - b.length || a.localeCompare(b));
    const name = (k) => titles[k] || k;
    const dmg = (k) => ((r.records || {})[k] || [])[1];
    const label = (k) => (dmg(k) > 0 ? `${name(k)}  (${dmg(k)} dmg)` : name(k));
    const movable = r.movable || [];
    const ownFirst = movable.filter((m) => !(m in (r.basic || {}))).sort((a, b) => name(a).localeCompare(name(b)));
    const basicToo = movable.filter((m) => m in (r.basic || {}));
    for (const k of [...inputs, ...later]) {
      const cell = document.createElement("label");
      const input = document.createElement("span"), pick = document.createElement("select");
      input.className = "move-input";
      input.textContent = k.includes("#") ? name(k) : k;
      pick.dataset.move = k;
      pick.setAttribute("aria-label", `Move on ${k}`);
      pick.append(new Option(`its own: ${label(k)}`, ""));
      for (const [title, list] of [["The style's own moves", ownFirst], ["Other basic inputs", basicToo]]) {
        const group = document.createElement("optgroup");
        group.label = title;
        for (const m of list) if (m !== k) group.append(new Option(label(m), m));
        if (group.children.length) pick.append(group);
      }
      pick.value = own[k] && movable.includes(own[k]) ? own[k] : "";
      const mark = () => cell.classList.toggle("changed", pick.value !== "");
      pick.addEventListener("change", () => { mark(); markDirty(); fairSoon(); });
      mark();
      cell.append(input, pick);
      grid.append(cell);
    }
    $("buttons-field").hidden = !inputs.length && !later.length;
  }

  // intro and win pose: Tekken 3's draw, or one of the style's own (1-based)
  function showPoses(r) {
    const chosen = state.current.poses || {};
    let any = false;
    for (const [name, label] of [["intro", "Intro"], ["win", "Win pose"]]) {
      const pick = $(`pose-${name}`), list = (r.poses || {})[name] || [];
      pick.textContent = "";
      pick.append(new Option("Tekken 3's choice (drawn)", ""));
      list.forEach((_, i) => pick.append(new Option(`${label} ${i + 1}`, String(i + 1))));
      pick.value = chosen[name] && chosen[name] <= list.length ? String(chosen[name]) : "";
      if (list.length > 1) any = true;
    }
    $("poses-field").hidden = !any;
  }

  // fairness check: traffic lights against the cast (/api/fairness), refreshed after each change
  let fairTimer = null, fairRun = 0;
  function fairSoon() { clearTimeout(fairTimer); fairTimer = setTimeout(fair, 400); }
  async function fair() {
    if (shown === null) return;
    const run = ++fairRun;
    let r;
    try { r = await api("/api/fairness", { donor: shown, ...body() }); } catch (e) { $("fair-field").hidden = true; return; }
    if (run !== fairRun) return;
    $("fair-label").textContent = r.label;
    const list = $("fair-list");
    list.textContent = "";
    for (const p of r.parts) {
      const li = document.createElement("li"), dot = document.createElement("span"), text = document.createElement("span");
      dot.className = `fair-light ${p.light || ""}`;
      dot.title = p.light || "not measured";
      text.textContent = p.part;
      const notes = document.createElement("small");
      notes.textContent = p.notes.join("; ");
      text.append(notes);
      li.append(dot, text);
      list.append(li);
    }
    $("fair-field").hidden = false;
  }

  // the changed damage for the save (only values that differ from Tekken 3's)
  function body() {
    const out = {};
    for (const v of document.querySelectorAll("#basic-list input, #own-list input")) {
      const n = Math.max(0, Math.min(200, Math.round(Number(v.value))));
      if (Number.isFinite(n) && n !== Number(v.dataset.original)) out[v.dataset.move] = n;
    }
    if (shown !== state.current.donor)
      return { move_damage: state.current.move_damage || null, move_buttons: state.current.move_buttons || null,
               poses: state.current.poses || null };
    const poses = {};
    for (const name of ["intro", "win"]) if ($(`pose-${name}`).value) poses[name] = Number($(`pose-${name}`).value);
    const buttons = {};
    for (const s of document.querySelectorAll("#buttons-list select")) if (s.value) buttons[s.dataset.move] = s.value;
    return { move_damage: Object.keys(out).length ? out : null,
             move_buttons: Object.keys(buttons).length ? buttons : null,
             poses: Object.keys(poses).length ? poses : null };
  }

  async function show() {
    const list = $("move-list"), note = $("move-note");
    const donor = state.current.donor;
    if (donor === null) { list.textContent = ""; note.textContent = "Choose a fighting style first."; shown = null; return; }
    if (shown === donor && shownFor === state.current.id) return;
    note.textContent = "Reading the moves from your Tekken 3 disc…";
    list.textContent = "";
    try {
      const r = await api("/api/moves", { donor });
      shown = donor; shownFor = state.current.id;
      note.textContent = `${DONORS[donor].name}'s command list: ${r.moves.filter((m) => m.name).length} moves.`;
      for (const m of r.moves) {
        const row = document.createElement("tr");
        if (m.section) {
          const th = document.createElement("th");
          th.colSpan = 3;
          th.textContent = m.section;
          row.append(th);
        } else {
          const name = document.createElement("td"), input = document.createElement("td");
          const damage = document.createElement("td");
          name.textContent = m.name;
          input.textContent = m.command;
          input.className = "move-input";
          damage.className = "move-damage";
          const own = (state.current.move_damage || {})[(m.command || "").replace(/ /g, "")];
          damage.textContent = !m.damage ? "" : m.hits ? `${m.hits.join(" + ")} = ${m.damage} dmg`
            : own !== undefined && own !== m.damage ? `${own} dmg (Tekken 3: ${m.damage})` : `${m.damage} dmg`;
          row.append(name, input, damage);
        }
        list.append(row);
      }
      const titles = {};
      for (const m of r.moves) if (m.command) titles[m.command.replace(/ /g, "")] ??= `${m.name}  ${m.command}`;
      for (const k of Object.keys(r.own || {})) {                // a string's later hits: "(hit 2)"
        const [base, hit] = k.split("#");
        if (hit && titles[base]) titles[k] = `${titles[base]} (hit ${hit})`;
      }
      const basic = showBasic(r.basic || {});
      const own = showBasic(r.own || {}, "own-list", titles);
      $("own-moves").hidden = !own;
      $("basic-field").hidden = !basic && !own;
      showButtons(r, titles);
      showPoses(r);
      fair();
    } catch (e) { note.textContent = e.message; shown = null; }
  }

  function resetDamage() {
    let changed = false;
    for (const v of document.querySelectorAll("#basic-list input, #own-list input")) {
      if (v.value !== v.dataset.original) { v.value = v.dataset.original; v.parentElement.classList.remove("changed"); changed = true; }
    }
    if (changed) { markDirty(); fairSoon(); }
  }
  document.getElementById("basic-reset").addEventListener("click", resetDamage);
  for (const id of ["pose-intro", "pose-win"]) document.getElementById(id).addEventListener("change", () => markDirty());
  document.getElementById("buttons-reset").addEventListener("click", () => {
    let changed = false;
    for (const s of document.querySelectorAll("#buttons-list select")) {
      if (s.value) { s.value = ""; s.parentElement.classList.remove("changed"); changed = true; }
    }
    if (changed) { markDirty(); fairSoon(); }
  });

  window.T3MoveLab = { show, body, reset: () => { shown = null; } };
})();
