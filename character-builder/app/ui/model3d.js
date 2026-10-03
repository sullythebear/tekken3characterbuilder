// 3D model page: upload an own .fbx/.glb, check it (rigged or locked), import it over a costume
// of the fighting style, remove it. Uses app.js globals: $, api, state, toast, showWarnings,
// loadCharacters, copyFighter.
"use strict";

const T3Model = (() => {
  let busy = false;

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
    if (!info) return;
    $("model-file-name").textContent = info.file || "";
    const facts = $("model-facts");
    facts.replaceChildren();
    if (info.ok) {
      facts.append(fact(`${info.triangles} triangles, ${info.vertices} vertices`));
      facts.append(fact(info.textured ? "Texture: embedded" : "Texture: none"));
      facts.append(fact(info.bones ? `Skeleton: ${info.bones} bones` : "Skeleton: none"));
    }
    const lock = $("model-lock");
    lock.className = "model-lock " + (info.rigged ? "ready" : "locked");
    lock.textContent = info.rigged ? "✓ Rigged: ready to import"
      : "🔒 Locked: this model is not rigged and cannot be imported";
    const problems = $("model-problems");
    problems.replaceChildren(...(info.problems || []).map(fact));
    $("model-import").disabled = busy || !info.rigged;
  }

  async function refresh() {
    const c = state.current;
    const saved = Boolean(c.id);
    $("model-need-save").hidden = saved;
    $("model-upload-box").hidden = !saved;
    const own = saved && c.own_model;
    $("own-model").hidden = !(saved && c.has_model);
    if (own) {
      const m = c.own_model;
      $("own-model-line").textContent = `Own model: ${m.file} · ${m.triangles || "?"} triangles · `
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
      o.textContent = `Costume ${i + 1}` + ([" (square)", " (cross)", " (Start)"][i] || "");
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

  async function importModel() {
    const info = state.current.model_upload;
    if (busy || !info || !info.rigged) return;
    if (state.dirty) { toast("Save your changes first."); return; }
    busy = true;
    $("model-import").disabled = true;
    const progress = $("model-progress");
    progress.hidden = false;
    progress.textContent = "Importing: fitting the model to the style's skeleton, texture and joints (about a minute)…";
    try {
      const saved = await api("/api/model/import", { id: state.current.id, costume: Number($("model-costume").value) });
      progress.hidden = true;
      await after(saved, `${saved.name} has its own model now`);
    } catch (e) {
      progress.textContent = e.message;
    } finally { busy = false; showCheck(state.current.model_upload); }
  }

  async function remove() {
    if (busy || !state.current.id || !confirm(`Remove ${state.current.name}'s own model? The style's model returns.`)) return;
    try { await after(await api("/api/model/remove", { id: state.current.id }), "Own model removed"); }
    catch (e) { toast(e.message); }
  }

  $("model-file").addEventListener("change", (e) => upload(e.target.files[0]));
  $("model-import").addEventListener("click", importModel);
  $("model-remove").addEventListener("click", remove);
  refresh();
  return { refresh };
})();
window.T3Model = T3Model;
