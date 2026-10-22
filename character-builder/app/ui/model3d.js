// 3D model page: upload an own .fbx/.glb, check it (rigged or locked), import it over a costume
// of the fighting style, remove it. Uses app.js globals: $, api, state, toast, showWarnings,
// loadCharacters, copyFighter.
"use strict";

const T3Model = (() => {
  let busy = false;
  let choices = {};            // parts that stick out: {id: {mode, angle}} (angle null = automatic)
  let partsFor = null;         // the upload the choices belong to
  let previewTimer = null, previewRun = 0, autoAngles = {};

  const fact = (text) => { const li = document.createElement("li"); li.textContent = text; return li; };

  async function costumeCount(donor) {
    try {
      const info = await api("/api/models");
      return info.available ? (info.donors[String(donor)] || []).length : 0;
    } catch { return 0; }
  }

  function showCheck(info) {
    const box = $("model-check");
    box.hidden = !info;
    $("model-import-row").hidden = !info || !info.ok;
    // the detail settings act on big models only (reduced to PS1 size: direct_import.REDUCE_ABOVE)
    $("model-settings").hidden = $("model-settings-hint").hidden = !info || !info.ok || !info.reduce;
    if (!info) return;
    $("model-file-name").textContent = info.file || "";
    $("model-texture-row").hidden = !info.ok;
    showTextures(info);
    const facts = $("model-facts");
    facts.replaceChildren();
    if (info.ok && info.checks) {
      // pre-import checks (direct_import.checks): geometry, materials, rigging
      const marks = { ok: "✓", info: "i", warn: "!", bad: "✗" };
      let area = "";
      for (const c of info.checks) {
        if (c.area !== area) {
          area = c.area;
          const head = fact(area);
          head.className = "check-area";
          facts.append(head);
        }
        const li = fact(c.text);
        li.className = "check check-" + c.level;
        li.dataset.mark = marks[c.level] || "";
        facts.append(li);
      }
    } else if (info.ok) {
      facts.append(fact(`${info.triangles} triangles, ${info.vertices} vertices`));
      facts.append(fact(info.textured ? "Texture: embedded" : "Texture: none"));
      facts.append(fact(info.bones ? `Skeleton: ${info.bones} bones` : "Skeleton: none"));
    }
    const lock = $("model-lock");
    lock.className = "model-lock " + (info.rigged ? "ready" : "locked");
    lock.textContent = info.rigged ? (info.rig ? "✓ Rigged by the creator: check the skeleton below, then import"
      : "✓ Rigged: ready to import")
      : info.rig ? "🔒 Not rigged yet: place the joints below" : "🔒 Locked: this model is not rigged and cannot be imported";
    const problems = $("model-problems");
    problems.replaceChildren(...(info.problems || []).map(fact));
    const notes = $("model-notes");
    notes.replaceChildren(...(info.notes || []).map(fact));
    showParts(info);
    T3Rig.show(info, (fresh) => { state.current.model_upload = fresh; showCheck(fresh); });
    T3Paint.show(info, (fresh) => { state.current.model_upload = fresh; showCheck(fresh); });
    $("model-import").disabled = busy || !info.rigged;
  }

  // parts that stick out: folded down by default, the user can keep or remove them or set the angle
  function showParts(info) {
    const parts = (info.ok && info.rigged && info.parts) || [];
    $("model-parts").hidden = !parts.length;
    if (!parts.length) return;
    const key = `${info.file}|${info.triangles}|${parts.length}`;
    if (partsFor !== key) {
      partsFor = key;
      choices = {};
      autoAngles = {};
      for (const p of parts) choices[p.id] = { mode: p.mode || "fold", angle: p.angle ?? null };
      schedulePreview(0);
    }
    const list = $("model-part-list");
    list.replaceChildren(...parts.map(partRow));
  }

  function partRow(p) {
    const c = choices[p.id];
    const li = document.createElement("li");
    li.className = "model-part";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = p.colour;
    const label = document.createElement("span");
    label.textContent = p.label;
    const controls = document.createElement("div");
    controls.className = "controls";
    const mode = document.createElement("select");
    mode.setAttribute("aria-label", `What to do with part ${p.id}`);
    for (const [v, t] of [["fold", "Fold down"], ["keep", "Keep as modelled"], ["remove", "Remove"]]) {
      const o = document.createElement("option");
      o.value = v; o.textContent = t;
      mode.append(o);
    }
    mode.value = c.mode;
    const range = document.createElement("input");
    range.type = "range"; range.min = "0"; range.max = "90"; range.step = "5";
    range.setAttribute("aria-label", `Hang angle of part ${p.id}, degrees from straight down`);
    const angle = document.createElement("span");
    angle.className = "angle";
    const auto = document.createElement("button");
    auto.type = "button"; auto.className = "btn btn-ghost"; auto.textContent = "Auto";
    auto.title = "Let the creator pick the steepest angle that clears the body";
    const sync = () => {
      const fold = c.mode === "fold";
      range.hidden = angle.hidden = !fold;
      auto.hidden = !fold || c.angle === null;
      const shown = c.angle ?? autoAngles[p.id];
      range.value = String(shown ?? 30);
      angle.textContent = shown == null ? "angle: auto" : `${Math.round(shown)}° from down${c.angle === null ? " (auto)" : ""}`;
    };
    mode.addEventListener("change", () => { c.mode = mode.value; sync(); schedulePreview(); });
    range.addEventListener("input", () => { c.angle = Number(range.value); sync(); schedulePreview(); });
    auto.addEventListener("click", () => { c.angle = null; sync(); schedulePreview(); });
    li.sync = sync;
    sync();
    controls.append(mode, range, angle, auto);
    li.append(sw, label, controls);
    return li;
  }

  function schedulePreview(delay = 450) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updatePreview, delay);
  }

  async function updatePreview() {
    const run = ++previewRun;
    const img = $("model-parts-preview");
    img.classList.add("busy");
    try {
      const res = await api("/api/model/preview", { id: state.current.id, parts: choices });
      if (run !== previewRun) return;
      img.src = `data:image/png;base64,${res.png}`;
      autoAngles = res.angles || {};
      for (const li of $("model-part-list").children) if (li.sync) li.sync();
    } catch (e) {
      if (run === previewRun) toast(e.message);
    } finally {
      if (run === previewRun) img.classList.remove("busy");
    }
  }

  async function refresh() {
    const c = state.current;
    const saved = Boolean(c.id);
    $("model-need-save").hidden = saved;
    $("model-upload-box").hidden = !saved;
    const own = saved && c.own_model;
    $("own-model").hidden = !(saved && c.has_model);
    $("model-undo").hidden = !(saved && c.model_undo);
    $("model-before").hidden = !(saved && c.has_model && c.own_model && c.own_model.file !== "Character Builder");
    $("model-before-img").hidden = true;
    if (own) {
      const m = c.own_model;
      const reduced = m.source_triangles && m.source_triangles !== m.triangles ? ` (reduced from ${m.source_triangles})` : "";
      $("own-model-line").textContent = `Own model: ${m.file} · ${m.triangles || "?"} triangles${reduced} · `
        + `replaces costume ${m.costume + 1} of the style`;
    } else if (saved && c.has_model) {
      $("own-model-line").textContent = "Own model: imported earlier (model.bin)";
    }
    showCheck(saved ? c.model_upload : null);
    if (!saved) return;
    const select = $("model-costume"), keep = select.value;
    const n = await costumeCount(c.donor);
    select.replaceChildren();
    for (let i = 0; i < Math.max(n, 1); i++) {
      const o = document.createElement("option");
      o.value = String(i);
      o.textContent = `Costume ${i + 1}`;
      select.append(o);
    }
    select.value = keep && Number(keep) < n ? keep : String(own ? c.own_model.costume : 0);
  }

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.onerror = () => reject(new Error("The file could not be read."));
      reader.readAsDataURL(file);
    });
  }

  async function after(result, message) {
    state.current = copyFighter(result);
    await loadCharacters();
    refresh();
    if (window.showPortraitFromModel) showPortraitFromModel();
    if (!showWarnings(result)) toast(message);
  }

  async function upload(file) {
    if (!file || busy) return;
    if (state.dirty) { toast("Save your changes first."); return; }
    busy = true;
    const progress = $("model-progress");
    progress.hidden = false;
    progress.textContent = `Checking ${file.name}…`;
    try {
      const info = await api("/api/model/check", { id: state.current.id, name: file.name, file: await readBase64(file) });
      state.current.model_upload = info;
      busy = false;
      showCheck(info);
      progress.hidden = true;
    } catch (e) {
      progress.textContent = e.message;
    } finally { busy = false; $("model-file").value = ""; }
  }

  // texture images beside the model file (.png, .jpg, .tga; several): each goes on the material
  // that asks for it or is named like it (automatic), or where the player puts it per material
  function showTextures(info) {
    const images = info.images || [], mats = info.materials || [];
    $("model-texture-name").textContent = images.length ? `${images.length} image${images.length > 1 ? "s" : ""} added`
      : mats.some((m) => m.asks) ? "The model asks for texture files: add them here." : "Only needed when the model's textures are separate files.";
    const list = $("model-texture-images");
    list.replaceChildren(...images.map((name, k) => {
      const li = document.createElement("li");
      li.textContent = name;
      const x = document.createElement("button");
      x.type = "button"; x.textContent = "✕"; x.title = `Remove ${name}`;
      x.addEventListener("click", () => textureChoice({ remove: k }, `Removing ${name}…`));
      li.append(x);
      return li;
    }));
    const table = $("model-materials");
    table.hidden = !mats.length || (!images.length && !mats.some((m) => m.own));
    const body = table.querySelector("tbody");
    body.replaceChildren(...mats.map((m) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = m.name;
      const why = document.createElement("span");
      why.className = "why";
      why.textContent = `${m.triangles} triangles` + (m.asks ? ` · asks for ${m.asks}` : "");
      name.append(why);
      const cell = document.createElement("td");
      const sel = document.createElement("select");
      const wears = (u) => (u === "own" ? "its own texture" : u === "colour" ? "plain colour" : u === "hide" ? "left out"
        : images[u] || "?");
      const opts = [["auto", `Automatic (${m.how === "auto" ? wears(m.use) : "as found"})`]];
      if (m.own) opts.push(["own", "Its own texture"]);
      opts.push(["colour", "Plain colour"]);
      opts.push(["hide", "Leave out (see-through layers)"]);
      // colour maps first; normal, mask and other maps last, marked (they hold no colours)
      const kinds = info.image_kinds || [];
      images.forEach((n, k) => { if (kinds[k] !== "other") opts.push([String(k), n]); });
      images.forEach((n, k) => { if (kinds[k] === "other") opts.push([String(k), `${n} (not a colour map)`]); });
      for (const [v, label] of opts) {
        const o = document.createElement("option");
        o.value = v; o.textContent = label;
        sel.append(o);
      }
      sel.value = m.how === "chosen" ? String(m.use) : "auto";
      sel.addEventListener("change", () => {
        const v = sel.value;
        textureChoice({ assign: { [m.index]: /^[0-9]+$/.test(v) ? Number(v) : v } }, `${m.name}: ${sel.selectedOptions[0].textContent}…`);
      });
      const note = document.createElement("span");
      note.className = "why";
      note.textContent = m.how === "auto" ? m.why : "your choice";
      cell.append(sel, note);
      tr.append(name, cell);
      return tr;
    }));
  }

  async function textureChoice(body, message) {
    if (busy) return;
    busy = true;
    const progress = $("model-progress");
    progress.hidden = false;
    progress.textContent = message;
    try {
      const info = await api("/api/model/texture-choice", { id: state.current.id, ...body });
      state.current.model_upload = info;
      busy = false;
      showCheck(info);
      progress.hidden = true;
    } catch (e) {
      progress.textContent = e.message;
    } finally { busy = false; }
  }

  async function uploadTextures(files) {
    if (!files.length || busy) return;
    busy = true;
    const progress = $("model-progress");
    progress.hidden = false;
    try {
      let info = null;
      for (const [k, file] of files.entries()) {
        const last = k === files.length - 1;     // the model is checked once, after the last image
        progress.textContent = last ? `Adding ${file.name} and checking the model…` : `Adding ${file.name} (${k + 1} of ${files.length})…`;
        info = await api("/api/model/texture", { id: state.current.id, name: file.name, file: await readBase64(file), recheck: last });
      }
      state.current.model_upload = info;
      busy = false;
      showCheck(info);
      progress.hidden = true;
    } catch (e) {
      progress.textContent = e.message;
    } finally { busy = false; $("model-texture").value = ""; }
  }

  async function importModel() {
    const info = state.current.model_upload;
    if (busy || !info || !info.rigged) return;
    if (state.dirty) { toast("Save your changes first."); return; }
    busy = true;
    $("model-import").disabled = true;
    const progress = $("model-progress");
    progress.hidden = false;
    progress.textContent = info.reduce
      ? "Importing: reducing the model to PS1 size, baking its texture and fitting it to the style's skeleton (1 to 3 minutes)…"
      : "Importing: fitting the model to the style's skeleton, texture and joints (a few seconds)…";
    try {
      const id = state.current.id;
      await api("/api/model/import", { id, costume: Number($("model-costume").value), parts: choices,
        settings: { head: Number($("model-head").value), detail: Number($("model-detail").value) } });
      // the import runs in the background: its log lines name the step it is at
      let job;
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        job = await api("/api/model/progress", { id });
        if (job.done) break;
        progress.textContent = `${stepOf(job.lines)} (${job.seconds} s)…`;
      }
      if (job.error) throw new Error(job.error);
      progress.hidden = true;
      await after(job.result, `${job.result.name} has its own model now: here it is in 3D`);
      if (window.showView) showView(true);           // the result, to keep or undo
    } catch (e) {
      progress.textContent = e.message;
    } finally { busy = false; showCheck(state.current.model_upload); }
  }

  // the import's log lines -> the step a person understands
  function stepOf(lines) {
    const steps = [["OK direct import", "Writing the PS1 model"], ["triangle pairs", "Writing the PS1 model"],
      ["seam vertices", "Posing it in the style's stance"], ["auto rig", "Fitting it to the style's skeleton"],
      ["do not fit", "Too big for the slot: trying a smaller version"], ["texture baked", "Fitting it to the style's skeleton"],
      ["texture charts", "Baking the texture"], ["reduced to", "Laying out the texture"],
      ["left out", "Reducing it to PS1 size"], ["part ", "Reducing it to PS1 size"]];
    for (let i = lines.length - 1; i >= 0; i--) {
      const hit = steps.find(([key]) => lines[i].includes(key));
      if (hit) return hit[1];
    }
    return "Reading the model";
  }

  async function undo() {
    if (busy || !state.current.id) return;
    try { await after(await api("/api/model/undo", { id: state.current.id }), "Import undone"); }
    catch (e) { toast(e.message); }
  }

  async function remove() {
    if (busy || !state.current.id || !confirm(`Remove ${state.current.name}'s own model? The style's model returns.`)) return;
    try { await after(await api("/api/model/remove", { id: state.current.id }), "Own model removed"); }
    catch (e) { toast(e.message); }
  }

  $("model-file").addEventListener("change", (e) => upload(e.target.files[0]));
  $("model-texture").addEventListener("change", (e) => uploadTextures([...e.target.files]));
  $("model-import").addEventListener("click", importModel);
  $("model-remove").addEventListener("click", remove);
  $("model-undo").addEventListener("click", undo);
  $("model-before").addEventListener("click", async () => {
    const button = $("model-before"), img = $("model-before-img");
    button.disabled = true;
    try {
      const r = await api("/api/model/source", { id: state.current.id });
      img.src = "data:image/png;base64," + r.png;
      img.hidden = false;
      if (window.showView) showView(true);           // after: the PS1 model in the 3D view
    } catch (e) { toast(e.message); } finally { button.disabled = false; }
  });
  refresh();
  return { refresh };
})();
window.T3Model = T3Model;
