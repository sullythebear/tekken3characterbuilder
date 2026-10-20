// Character Builder: body parts from Tekken 3's own fighters (kitbash.py, read from the player's
// disc). Uses app.js's state, api, toast, DONORS, showView, loadCharacters, fillForm.
(() => {
  const PART_NAMES = { head: "Head", body: "Body", arm_l: "Left arm", arm_r: "Right arm",
    leg_l: "Left leg", leg_r: "Right leg", hands: "Hands (gloves)", arms: "Arms", legs: "Legs" };
  let models = null, fit = 0.07, busy = false, previewTimer = null, previewRun = 0;
  let pieceColours = {}, piecesFor = "";    // {"model:clut": [hue, saturation, lightness]}

  // colour presets: [hue, saturation, lightness]
  // body shape presets: head, arms, legs, body in % (the sliders' ranges)
  const SHAPE_PRESETS = [["Normal shape", [100, 100, 100, 100]], ["Slim", [100, 85, 88, 90]],
    ["Athletic", [100, 112, 108, 106]], ["Heavy", [105, 125, 120, 122]], ["Big head", [128, 100, 100, 100]]];
  function setShape(values) {
    const inputs = [...document.querySelectorAll(".kit-shape input")];
    inputs.forEach((input, k) => { input.value = String(values[k]); });
  }
  const PRESETS = [["Original", 0, 100, 0], ["Darker", 0, 90, -15], ["Lighter", 0, 90, 12], ["Muted", 0, 40, 0],
    ["Vivid", 0, 160, 0], ["Opposite", 180, 100, 0]];
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
    costume.value = String(own.file === "Character Builder" ? own.costume || 0 : 0);
    const c = own.colours || [0, 100, 0, true];
    [$("kit-hue").value, $("kit-sat").value, $("kit-light").value, $("kit-skin").checked] = c;
    const sh = own.file === "Character Builder" ? own.shape || {} : {};
    for (const input of document.querySelectorAll(".kit-shape input"))
      input.value = String(Math.round((sh[input.dataset.shape] || 1) * 100));
    pieceColours = own.file === "Character Builder" ? { ...(own.pieces || {}) } : {};
    matchBuild();
    loadPieces();
  }

  // pieces of clothing of the current mix (kitbash.list_pieces): a swatch, hue and lightness each
  const hsl = (hex, h, l) => {                  // the swatch with the piece's hue and lightness
    const n = parseInt(hex.slice(1), 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    let H = 0, L = (mx + mn) / 2, S = mx === mn ? 0 : (L > 0.5 ? (mx - mn) / (2 - mx - mn) : (mx - mn) / (mx + mn));
    if (mx !== mn) H = mx === r ? (g - b) / (mx - mn) + (g < b ? 6 : 0) : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4;
    return `hsl(${(H * 60 + h + 360) % 360} ${Math.round(S * 100)}% ${Math.max(0, Math.min(100, Math.round(L * 100 + l)))}%)`;
  };
  async function loadPieces() {
    const parts = chosen(), costume = Number($("kit-costume").value);
    const key = JSON.stringify([state.current.id, costume, parts]);
    if (key === piecesFor || !state.current.id) return;
    piecesFor = key;
    const list = $("kit-pieces");
    let pieces;
    try {
      pieces = (await api("/api/kit/pieces", { id: state.current.id, costume, parts })).pieces;
    } catch (e) { list.textContent = e.message; return; }
    if (key !== piecesFor) return;
    for (const k of Object.keys(pieceColours)) if (!pieces.some((p) => (p.keys || [p.key]).includes(k))) delete pieceColours[k];
    list.textContent = "";
    const count = {};
    for (const p of pieces) {
      count[p.part] = (count[p.part] || 0) + 1;
      const model = models.find((m) => m.model === p.model);
      const row = document.createElement("div");
      row.className = "kit-piece";
      const sw = document.createElement("span");
      sw.className = "swatch";
      const name = document.createElement("span");
      name.textContent = `${PART_NAMES[p.part] || p.part} ${count[p.part]}`;
      name.title = model ? `${label(model)}, ${p.polygons} polygons` : `${p.polygons} polygons`;
      const [h0, , l0] = pieceColours[p.key] || [0, 100, 0];
      const hue = Object.assign(document.createElement("input"), { type: "range", min: -180, max: 180, value: h0, title: "Hue" });
      const light = Object.assign(document.createElement("input"), { type: "range", min: -40, max: 40, value: l0, title: "Lightness" });
      hue.setAttribute("aria-label", `Hue of ${name.textContent}`);
      light.setAttribute("aria-label", `Lightness of ${name.textContent}`);
      const show = () => {
        const h = Number(hue.value), l = Number(light.value);
        for (const k of p.keys || [p.key])         // the shades of one piece change together
          if (h || l) pieceColours[k] = [h, 100, l]; else delete pieceColours[k];
        sw.style.background = hsl(p.colour, h, l);
        row.classList.toggle("changed", Boolean(h || l));
      };
      for (const input of [hue, light]) {
        input.addEventListener("input", show);
        input.addEventListener("change", schedulePreview);
      }
      show();
      row.append(sw, name, hue, light);
      list.append(row);
    }
    $("kit-pieces-box").hidden = !pieces.length;
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

  // the body's own colours (hue, saturation, lightness), or null for the parts' own
  function colours() {
    const c = [Number($("kit-hue").value), Number($("kit-sat").value), Number($("kit-light").value), $("kit-skin").checked];
    return c[0] === 0 && c[1] === 100 && c[2] === 0 ? null : c;
  }

  // body shape: head size on all axes; arms, legs and body thicker or thinner (kitbash.SHAPES)
  function shape() {
    const out = {};
    for (const input of document.querySelectorAll(".kit-shape input"))
      if (Number(input.value) !== 100) out[input.dataset.shape] = Number(input.value) / 100;
    return out;
  }

  const nothing = () => !Object.keys(chosen()).length && !colours() && !Object.keys(shape()).length &&
    !Object.keys(pieceColours).length;

  // saved looks (server looks.json): parts, colours and shape under a name, for any fighter
  let looks = [];
  async function loadLooks() {
    try { looks = (await api("/api/looks", {})).looks; } catch { looks = []; }
    showLooks();
  }
  function showLooks(pick) {
    const select = $("kit-looks");
    select.textContent = "";
    if (!looks.length) select.add(new Option("None saved yet", ""));
    for (const l of looks) {
      const style = l.donor !== null && DONORS[l.donor] ? ` (${DONORS[l.donor].name})` : "";
      select.add(new Option(l.name + style, l.name));
    }
    if (pick) select.value = pick;
    $("kit-look-use").disabled = $("kit-look-delete").disabled = !looks.length;
  }
  function useLook() {
    const look = looks.find((l) => l.name === $("kit-looks").value);
    if (!look) return;
    for (const select of document.querySelectorAll("#kit-parts select")) {
      const v = look.kit[select.dataset.part];
      select.value = v !== undefined && [...select.options].some((o) => o.value === String(v) && !o.disabled) ? String(v) : "";
    }
    const c = look.colours || [0, 100, 0, true];
    [$("kit-hue").value, $("kit-sat").value, $("kit-light").value, $("kit-skin").checked] = c;
    for (const input of document.querySelectorAll(".kit-shape input"))
      input.value = String(Math.round(((look.shape || {})[input.dataset.shape] || 1) * 100));
    pieceColours = { ...(look.pieces || {}) };
    piecesFor = "";
    const left = Object.keys(look.kit).filter((p) => !chosen()[p]);
    if (left.length) toast(`Not for this style's build: ${left.join(", ")}`);
    schedulePreview();
  }
  async function saveLook() {
    const name = prompt("Name for this look:", "");
    if (!name) return;
    try {
      looks = (await api("/api/looks/save", { name, donor: state.current.donor, parts: chosen(), colours: colours(), shape: shape(),
        pieces: pieceColours })).looks;
      showLooks(name.trim());
      toast("Look saved");
    } catch (e) { toast(e.message); }
  }
  async function deleteLook() {
    const name = $("kit-looks").value;
    if (!name || !confirm(`Delete the look "${name}"?`)) return;
    try { looks = (await api("/api/looks/delete", { name })).looks; showLooks(); } catch (e) { toast(e.message); }
  }

  function chosen() {
    const parts = {};
    for (const select of document.querySelectorAll("#kit-parts select"))
      if (select.value !== "") parts[select.dataset.part] = Number(select.value);
    return parts;
  }

  let retries = 0;          // a random mix that does not build is drawn again (a few times)
  function randomize(again = false) {
    // one or two other fighters (95 % of two-fighter mixes build, tested 2026-10-18); each part:
    // the style's own or one of theirs
    retries = again ? retries + 1 : 0;
    const selects = [...document.querySelectorAll("#kit-parts select")];
    const usable = [...selects[0].options].filter((o) => o.value && !o.disabled).map((o) => o.value);
    if (!usable.length) return;
    const pick = () => usable[Math.floor(Math.random() * usable.length)];
    const sources = [pick()];
    if (usable.length > 1 && Math.random() < 0.5) sources.push(pick());
    for (const select of selects)
      select.value = Math.random() < 0.4 ? "" : sources[Math.floor(Math.random() * sources.length)];
    if (!Object.keys(chosen()).length) selects[0].value = sources[0];
    const hue = Math.random() < 0.4 ? Math.round(Math.random() * 360 - 180) : 0;   // sometimes new colours
    [$("kit-hue").value, $("kit-sat").value, $("kit-light").value] = [hue, 100, 0];
    // sometimes another build too (never the extremes)
    setShape(Math.random() < 0.3 ? SHAPE_PRESETS[1 + Math.floor(Math.random() * 3)][1] : SHAPE_PRESETS[0][1]);
    pieceColours = {};
    schedulePreview();
  }

  // the mix in the 3D view before it is built (cache only); a mix that does not fit says why
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(preview, 600);
  }

  async function preview() {
    const parts = chosen(), note = $("kit-progress"), run = ++previewRun;
    loadPieces();
    if (!state.current.id || nothing()) return;
    note.hidden = false;
    note.textContent = "Preview: building the mix…";
    try {
      const json = await api("/api/kit/preview", { id: state.current.id, costume: Number($("kit-costume").value), parts,
        colours: colours(), shape: shape(), pieces: pieceColours });
      if (run !== previewRun) return;
      showView(true);
      T3Costumes.preview(json, "Preview of the chosen parts: not built yet. Build puts it in the game.");
      note.textContent = "Preview shown. Build puts this body in the game." +
        (json.half_textures ? " Some parts' textures are at half size, so all of them fit Tekken 3's one texture page." : "");
    } catch (e) {
      if (run !== previewRun) return;
      if (retries && retries < 3) { randomize(true); return; }
      note.textContent = `This mix does not work: ${e.message}`;
    } finally {
      if (run === previewRun && !note.textContent.startsWith("Preview: building")) retries = 0;
    }
  }

  async function build() {
    if (busy) return;
    if (state.dirty) { toast("Save the fighter first."); return; }
    const parts = chosen();
    if (nothing()) { toast("Choose a body part from another fighter, colours or a body shape."); return; }
    busy = true;
    const button = $("kit-build"), note = $("kit-progress");
    button.disabled = true;
    note.hidden = false;
    note.textContent = "Building the fighter from the chosen parts…";
    try {
      const saved = await api("/api/kit/build", { id: state.current.id, costume: Number($("kit-costume").value), parts,
        colours: colours(), shape: shape(), pieces: pieceColours });
      state.current = copyFighter(saved);
      await loadCharacters();
      fillForm();
      if (window.T3Model) T3Model.refresh();
      T3Costumes.refresh(true);
      showView(true);
      note.textContent = (saved.own_model?.triangles ? `Built: ${saved.own_model.triangles} triangles. Undo is on the Model Importer page.` : "Built.") +
        (saved.own_model?.half_textures ? " Some parts' textures are at half size to fit one texture page." : "");
      if (!showWarnings(saved)) toast(`${saved.name} has a new body`);
    } catch (e) {
      note.textContent = e.message;
    } finally { busy = false; button.disabled = false; }
  }

  function init() {
    $("kit-build").addEventListener("click", build);
    $("kit-look-use").addEventListener("click", useLook);
    $("kit-look-save").addEventListener("click", saveLook);
    $("kit-look-delete").addEventListener("click", deleteLook);
    loadLooks();
    $("kit-random").addEventListener("click", () => { randomize(); retries = 1; });
    $("kit-pieces-reset").addEventListener("click", () => { pieceColours = {}; piecesFor = ""; loadPieces(); schedulePreview(); });
    $("kit-costume").addEventListener("change", () => { matchBuild(); schedulePreview(); });
    for (const id of ["kit-hue", "kit-sat", "kit-light", "kit-skin"]) $(id).addEventListener("change", schedulePreview);
    for (const input of document.querySelectorAll(".kit-shape input")) {
      input.addEventListener("change", schedulePreview);
      input.addEventListener("input", () => { input.title = `${input.value} %`; });
    }
    for (const [name, values] of SHAPE_PRESETS) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "btn btn-ghost mini"; b.textContent = name;
      b.addEventListener("click", () => { setShape(values); schedulePreview(); });
      $("kit-shape-presets").append(b);
    }
    for (const [name, h, s, l] of PRESETS) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "btn btn-ghost mini"; b.textContent = name;
      b.addEventListener("click", () => { [$("kit-hue").value, $("kit-sat").value, $("kit-light").value] = [h, s, l]; schedulePreview(); });
      $("kit-presets").append(b);
    }
  }

  window.T3Builder = { init, fill };
})();
