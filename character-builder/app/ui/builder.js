// Character Builder: body parts from Tekken 3's own fighters (kitbash.py, read from the player's
// disc). Uses app.js's state, api, toast, DONORS, showView, loadCharacters, fillForm.
(() => {
  const PART_NAMES = { head: "Head", body: "Body", arm_l: "Left arm", arm_r: "Right arm",
    leg_l: "Left leg", leg_r: "Right leg" };
  let models = null, fit = 0.07, busy = false, previewTimer = null, previewRun = 0;

  const label = (m) => `${DONORS[m.donor].name} ${m.costume + 1}`;

  async function load() {
    if (models) return models;
    const r = await api("/api/kit/models", {});
    models = r.models.sort((a, b) => a.donor - b.donor || a.costume - b.costume);
    fit = r.fit;
    const rows = $("kit-parts");
    rows.textContent = "";
    for (const part of r.parts) {
      const row = document.createElement("label");
      row.textContent = PART_NAMES[part] || part;
      const select = document.createElement("select");
      select.id = `kit-${part}`;
      select.dataset.part = part;
      select.add(new Option("Style's own", ""));
      for (const m of models) {
        const option = new Option(label(m), String(m.model));
        option.dataset.height = m.height;
        select.add(option);
      }
      select.addEventListener("change", schedulePreview);
      row.append(select);
      rows.append(row);
    }
    return models;
  }

  async function fill() {
    const section = $("kit-section");
    if (!state.current.id || state.current.donor === null) { section.hidden = true; return; }
    try { await load(); } catch (e) { section.hidden = true; return; }
    section.hidden = false;
    const own = state.current.own_model || {};
    const kit = own.kit || {};
    for (const select of document.querySelectorAll("#kit-parts select"))
      select.value = kit[select.dataset.part] !== undefined ? String(kit[select.dataset.part]) : "";
    const costume = $("kit-costume");
    costume.textContent = "";
    for (const m of models.filter((m) => m.donor === state.current.donor))
      costume.add(new Option(`Costume ${m.costume + 1}`, String(m.costume)));
    costume.value = String(own.kit ? own.costume || 0 : 0);
    matchBuild();
  }

  // only parts of fighters with a similar build (the server checks it too)
  function matchBuild() {
    const base = models.find((m) => m.donor === state.current.donor && m.costume === Number($("kit-costume").value));
    for (const select of document.querySelectorAll("#kit-parts select")) {
      for (const option of select.options) {
        if (!option.value) continue;
        option.hidden = option.disabled = !base || Math.abs(option.dataset.height / base.height - 1) > fit;
      }
      if (select.selectedOptions[0]?.disabled) select.value = "";
    }
  }

  function chosen() {
    const parts = {};
    for (const select of document.querySelectorAll("#kit-parts select"))
      if (select.value !== "") parts[select.dataset.part] = Number(select.value);
    return parts;
  }

  function randomize() {
    // one other fighter (two or more rarely fit the colour tables a fighter has); each part: the
    // style's own or that fighter's
    const selects = [...document.querySelectorAll("#kit-parts select")];
    const usable = [...selects[0].options].filter((o) => o.value && !o.disabled).map((o) => o.value);
    if (!usable.length) return;
    const pick = () => usable[Math.floor(Math.random() * usable.length)];
    const sources = [pick()];
    for (const select of selects)
      select.value = Math.random() < 0.4 ? "" : sources[Math.floor(Math.random() * sources.length)];
    if (!Object.keys(chosen()).length) selects[0].value = sources[0];
    schedulePreview();
  }

  // the mix in the 3D view before it is built (cache only); a mix that does not fit says why
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(preview, 600);
  }

  async function preview() {
    const parts = chosen(), note = $("kit-progress"), run = ++previewRun;
    if (!state.current.id || !Object.keys(parts).length) return;
    note.hidden = false;
    note.textContent = "Preview: building the mix…";
    try {
      const json = await api("/api/kit/preview", { id: state.current.id, costume: Number($("kit-costume").value), parts });
      if (run !== previewRun) return;
      showView(true);
      T3Costumes.preview(json, "Preview of the chosen parts: not built yet. Build puts it in the game.");
      note.textContent = "Preview shown. Build puts this body in the game.";
    } catch (e) {
      if (run === previewRun) note.textContent = `This mix does not work: ${e.message}`;
    }
  }

  async function build() {
    if (busy) return;
    if (state.dirty) { toast("Save the fighter first."); return; }
    const parts = chosen();
    if (!Object.keys(parts).length) { toast("Choose at least one body part from another fighter."); return; }
    busy = true;
    const button = $("kit-build"), note = $("kit-progress");
    button.disabled = true;
    note.hidden = false;
    note.textContent = "Building the fighter from the chosen parts…";
    try {
      const saved = await api("/api/kit/build", { id: state.current.id, costume: Number($("kit-costume").value), parts });
      state.current = copyFighter(saved);
      await loadCharacters();
      fillForm();
      if (window.T3Model) T3Model.refresh();
      T3Costumes.refresh(true);
      showView(true);
      note.textContent = saved.own_model?.triangles ? `Built: ${saved.own_model.triangles} triangles. Undo is on the Model Importer page.` : "Built.";
      if (!showWarnings(saved)) toast(`${saved.name} has a new body`);
    } catch (e) {
      note.textContent = e.message;
    } finally { busy = false; button.disabled = false; }
  }

  function init() {
    $("kit-build").addEventListener("click", build);
    $("kit-random").addEventListener("click", randomize);
    $("kit-costume").addEventListener("change", () => { matchBuild(); schedulePreview(); });
  }

  window.T3Builder = { init, fill };
})();
