// Move Lab: the style's COMMAND LIST as Tekken 3 shows it, read from the player's disc
// (/api/moves). Read-only for now. Uses app.js's state, api, $ and DONORS.
(() => {
  let shown = null;

  // the basic inputs grouped by direction, in Tekken order
  const ORDER = ["", "f", "b", "d", "df", "db", "u", "uf", "ub"];
  function showBasic(basic) {
    const grid = $("basic-list");
    grid.textContent = "";
    const names = Object.keys(basic).filter((k) => basic[k]);
    $("basic-field").hidden = !names.length;
    const dir = (k) => (k.includes("+") && isNaN(k.split("+")[0]) ? k.split("+")[0] : "");
    names.sort((a, b) => ORDER.indexOf(dir(a)) - ORDER.indexOf(dir(b)) || a.length - b.length || a.localeCompare(b));
    for (const k of names) {
      const cell = document.createElement("div");
      const input = document.createElement("span"), value = document.createElement("strong");
      input.className = "move-input";
      input.textContent = k;
      value.textContent = basic[k];
      cell.append(input, value);
      grid.append(cell);
    }
  }

  async function show() {
    const list = $("move-list"), note = $("move-note");
    const donor = state.current.donor;
    if (donor === null) { list.textContent = ""; note.textContent = "Choose a fighting style first."; shown = null; return; }
    if (shown === donor) return;
    note.textContent = "Reading the moves from your Tekken 3 disc…";
    list.textContent = "";
    try {
      const r = await api("/api/moves", { donor });
      shown = donor;
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
          damage.textContent = m.damage ? `${m.damage} dmg` : "";
          row.append(name, input, damage);
        }
        list.append(row);
      }
      showBasic(r.basic || {});
    } catch (e) { note.textContent = e.message; shown = null; }
  }

  window.T3MoveLab = { show, reset: () => { shown = null; } };
})();
