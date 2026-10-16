// Move Lab: the style's COMMAND LIST as Tekken 3 shows it, read from the player's disc
// (/api/moves). Read-only for now. Uses app.js's state, api, $ and DONORS.
(() => {
  let shown = null;

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
          th.colSpan = 2;
          th.textContent = m.section;
          row.append(th);
        } else {
          const name = document.createElement("td"), input = document.createElement("td");
          name.textContent = m.name;
          input.textContent = m.command;
          input.className = "move-input";
          row.append(name, input);
        }
        list.append(row);
      }
    } catch (e) { note.textContent = e.message; shown = null; }
  }

  window.T3MoveLab = { show, reset: () => { shown = null; } };
})();
