// Move Lab: the style's COMMAND LIST as Tekken 3 shows it, read from the player's disc
// (/api/moves). Read-only for now. Uses app.js's state, api, $ and DONORS.
(() => {
  let shown = null, shownFor = null;     // the style shown, for which fighter

  // the basic inputs grouped by direction, in Tekken order
  const ORDER = ["", "f", "b", "d", "df", "db", "u", "uf", "ub"];
  function showBasic(basic) {
    const grid = $("basic-list");
    grid.textContent = "";
    const names = Object.keys(basic).filter((k) => basic[k]);
    $("basic-field").hidden = !names.length;
    const dir = (k) => (k.includes("+") && isNaN(k.split("+")[0]) ? k.split("+")[0] : "");
    names.sort((a, b) => ORDER.indexOf(dir(a)) - ORDER.indexOf(dir(b)) || a.length - b.length || a.localeCompare(b));
    const own = state.current.move_damage || {};
    for (const k of names) {
      const cell = document.createElement("label");
      const input = document.createElement("span"), value = document.createElement("input");
      input.className = "move-input";
      input.textContent = k;
      value.type = "number"; value.min = "0"; value.max = "200";
      value.dataset.move = k; value.dataset.original = basic[k];
      value.value = own[k] ?? basic[k];
      value.title = `Tekken 3: ${basic[k]}`;
      const mark = () => cell.classList.toggle("changed", Number(value.value) !== basic[k]);
      value.addEventListener("input", () => { mark(); markDirty(); });
      mark();
      cell.append(input, value);
      grid.append(cell);
    }
  }

  // the changed damage for the save (only values that differ from Tekken 3's)
  function body() {
    const out = {};
    for (const v of document.querySelectorAll("#basic-list input")) {
      const n = Math.max(0, Math.min(200, Math.round(Number(v.value))));
      if (Number.isFinite(n) && n !== Number(v.dataset.original)) out[v.dataset.move] = n;
    }
    if (shown !== state.current.donor) return { move_damage: state.current.move_damage || null };
    return { move_damage: Object.keys(out).length ? out : null };
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
          damage.textContent = !m.damage ? "" : own !== undefined && own !== m.damage ? `${own} dmg (Tekken 3: ${m.damage})` : `${m.damage} dmg`;
          row.append(name, input, damage);
        }
        list.append(row);
      }
      showBasic(r.basic || {});
    } catch (e) { note.textContent = e.message; shown = null; }
  }

  window.T3MoveLab = { show, body, reset: () => { shown = null; } };
})();
