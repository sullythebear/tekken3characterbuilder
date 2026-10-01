"use strict";

const TOKEN = document.querySelector('meta[name="t3cb-token"]').content;
// The select-screen portrait is shown at 168 x 252 but stored 126 texels wide
// (the PS1 stretches it back), in four 64-row bands of 64 colors each.
const PORTRAIT_W = 126, PORTRAIT_H = 252, SHOWN_W = 168, BAND_ROWS = 64, BAND_COLORS = 63;

// Internal Tekken 3 (SLUS-00402) character IDs, as read from the game's own
// character records (confirmed by Tekken3Recompiled and Tekken 3 Expanded).
const DONORS = [
  ["Paul"], ["Law"], ["Lei"], ["King"], ["Yoshimitsu"], ["Nina"], ["Hwoarang"],
  ["Xiaoyu", "Tested: works fully as a donor."], ["Eddy", "Eddy and Tiger share this slot."], ["Jin"],
  ["Julia"], ["Kuma", "Kuma and Panda share this slot."], ["Bryan"], ["Heihachi"],
  ["Ogre", "Boss character. Not tested as a donor yet."],
  ["Mokujin", "Mokujin copies other fighters' styles. Not tested as a donor yet."], ["Gun Jack"],
  ["Gon", "Not tested as a donor yet."], ["Anna"],
  ["Dr. B", "Not tested as a donor yet."],
  ["True Ogre", "Boss character. Not tested as a donor yet."],
].map(([name, note = "", probable = false], id) => ({ id, name, note, probable }));

const $ = (id) => document.getElementById(id);
// Tekken 3's name font has no F or Q, and 2 is its only digit.
const NAME_BLOCKED = /[^A-EG-PR-Z2 .\-]/g, NAME_VALID = /^[A-EG-PR-Z2 .\-]{1,15}$/;
const isExpanded = () => state.status && state.status.kind === "expanded";
function showWarnings(result) {
  const list = (result && result.warnings) || [];
  list.forEach((w) => log("WARNING: " + w));
  if (list.length) { toast(list[0]); $("console").open = true; }
  return list.length;
}
const state = {
  status: null, characters: [], unlinked: [], current: blank(), dirty: false,
  source: null, crop: { zoom: 100, x: 0, y: 0 }, portraitChanged: false, hasPortrait: false,
  logTotal: 0, lastBuild: "idle", lastGameRunning: false, lastTest: "idle",
};

function blank() { return { id: null, name: "", donor: null, author: "" }; }

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-T3CB-Token": TOKEN },
    body: JSON.stringify(body),
  };
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error("The builder is not responding. Is the server window still open?"); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Error ${response.status}`);
  return data;
}

function flash(text) {
  const el = $("flash");
  $("flash-text").textContent = text;
  el.classList.remove("show");
  void el.offsetWidth;
  el.classList.add("show");
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2600);
}

function log(text) {
  const el = $("log");
  el.textContent += text + "\n";
  el.scrollTop = el.scrollHeight;
}

/* ------------------------------------------------------------ donors -- */

function renderDonors() {
  const grid = $("donor-grid");
  grid.replaceChildren();
  for (const donor of DONORS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "donor" + (donor.probable ? " probable" : "");
    button.dataset.initial = donor.name[0];
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(state.current.donor === donor.id));
    button.dataset.id = donor.id;
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = `#${donor.id}`;
    const name = document.createElement("span");
    name.className = "dn";
    name.textContent = donor.name;
    button.append(num, name);
    button.title = donor.probable ? `${donor.name} (probable)` : donor.name;
    button.addEventListener("click", () => { state.current.donor = donor.id; markDirty(); renderDonors(); renderStage(); });
    grid.append(button);
  }
  const d = DONORS[state.current.donor];
  $("donor-info").textContent = d
    ? (d.note || `Based on ${d.name}.`)
    : "";
}

function donorLabel(id) {
  if (id === null || id === undefined) return "Choose a donor";
  return `Fights as ${DONORS[id].name}`;
}

/* ---------------------------------------------------------- portrait -- */

function drawPortrait() {
  const out = $("portrait-canvas");
  const ctx = out.getContext("2d");
  if (!state.source) return;
  const img = state.source;
  const temp = document.createElement("canvas");
  temp.width = SHOWN_W; temp.height = PORTRAIT_H;
  const t = temp.getContext("2d");
  t.fillStyle = "#000"; t.fillRect(0, 0, SHOWN_W, PORTRAIT_H);
  const cover = Math.max(SHOWN_W / img.width, PORTRAIT_H / img.height) * (state.crop.zoom / 100);
  const w = img.width * cover, h = img.height * cover;
  const x = (SHOWN_W - w) / 2 + (state.crop.x / 100) * Math.max(0, (w - SHOWN_W) / 2);
  const y = (PORTRAIT_H - h) / 2 + (state.crop.y / 100) * Math.max(0, (h - PORTRAIT_H) / 2);
  t.imageSmoothingQuality = "high";
  t.drawImage(img, x, y, w, h);
  const squeeze = document.createElement("canvas");
  squeeze.width = PORTRAIT_W; squeeze.height = PORTRAIT_H;
  const q = squeeze.getContext("2d");
  q.imageSmoothingEnabled = false;
  q.drawImage(temp, 0, 0, PORTRAIT_W, PORTRAIT_H);
  state.fullCanvas = temp;
  for (let top = 0; top < PORTRAIT_H; top += BAND_ROWS) {
    const rows = Math.min(BAND_ROWS, PORTRAIT_H - top);
    const band = q.getImageData(0, top, PORTRAIT_W, rows);
    quantizePS1(band.data, BAND_COLORS);
    q.putImageData(band, 0, top);
  }
  ctx.clearRect(0, 0, PORTRAIT_W, PORTRAIT_H);
  ctx.drawImage(squeeze, 0, 0);
  state.hasPortrait = true;
  $("portrait-empty").hidden = true;
}

// PS1 color is 15-bit (5 bits per channel).
function quantizePS1(px, maxColors) {
  const counts = new Map();
  for (let i = 0; i < px.length; i += 4) {
    const key = ((px[i] >> 3) << 10) | ((px[i + 1] >> 3) << 5) | (px[i + 2] >> 3);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  let colors = [...counts].map(([k, n]) => ({ r: k >> 10, g: (k >> 5) & 31, b: k & 31, n }));
  let boxes = [colors];
  while (boxes.length < maxColors) {
    let pick = -1, best = 0, axis = "r";
    boxes.forEach((box, i) => {
      if (box.length < 2) return;
      for (const a of ["r", "g", "b"]) {
        let lo = 31, hi = 0;
        for (const c of box) { if (c[a] < lo) lo = c[a]; if (c[a] > hi) hi = c[a]; }
        if (hi - lo > best) { best = hi - lo; pick = i; axis = a; }
      }
    });
    if (pick < 0) break;
    const box = boxes[pick].sort((p, q) => p[axis] - q[axis]);
    const total = box.reduce((s, c) => s + c.n, 0);
    let acc = 0, cut = 1;
    for (let i = 0; i < box.length - 1; i++) { acc += box[i].n; if (acc >= total / 2) { cut = i + 1; break; } }
    boxes.splice(pick, 1, box.slice(0, cut), box.slice(cut));
  }
  const palette = boxes.map((box) => {
    const n = box.reduce((s, c) => s + c.n, 0);
    const avg = (a) => Math.round(box.reduce((s, c) => s + c[a] * c.n, 0) / n);
    return { r: avg("r"), g: avg("g"), b: avg("b") };
  });
  const lookup = new Map();
  for (const k of counts.keys()) {
    const r = k >> 10, g = (k >> 5) & 31, b = k & 31;
    let best = 0, dist = Infinity;
    palette.forEach((p, i) => {
      const d = (p.r - r) ** 2 * 3 + (p.g - g) ** 2 * 4 + (p.b - b) ** 2 * 2;
      if (d < dist) { dist = d; best = i; }
    });
    lookup.set(k, palette[best]);
  }
  const expand = (v) => (v << 3) | (v >> 2);
  for (let i = 0; i < px.length; i += 4) {
    const key = ((px[i] >> 3) << 10) | ((px[i + 1] >> 3) << 5) | (px[i + 2] >> 3);
    const p = lookup.get(key);
    px[i] = expand(p.r); px[i + 1] = expand(p.g); px[i + 2] = expand(p.b); px[i + 3] = 255;
  }
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("This image cannot be opened."));
    img.src = src;
  });
}

async function useFile(file) {
  if (!file || !file.type.startsWith("image/")) { toast("Choose an image (PNG, JPG or WebP)."); return; }
  const url = URL.createObjectURL(file);
  try {
    state.source = await loadImage(url);
    state.crop = { zoom: 100, x: 0, y: 0 };
    syncSliders();
    $("portrait-controls").hidden = false;
    state.portraitChanged = true;
    drawPortrait();
    markDirty();
  } catch (error) { toast(error.message); }
}

function syncSliders() {
  $("zoom").value = state.crop.zoom; $("pan-x").value = state.crop.x; $("pan-y").value = state.crop.y;
}

function sourcePNG() {
  const img = state.source;
  const scale = Math.min(1, 1024 / Math.max(img.width, img.height));
  const c = document.createElement("canvas");
  c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL("image/png");
}

function clearPortrait() {
  const c = $("portrait-canvas");
  c.getContext("2d").clearRect(0, 0, c.width, c.height);
  state.source = null; state.hasPortrait = false; state.portraitChanged = false;
  $("portrait-empty").hidden = false;
  $("portrait-controls").hidden = true;
}

/* ---------------------------------------------------------- editor -- */

function renderStage() {
  const plate = $("nameplate"), shown = state.current.name || "NEW FIGHTER";
  const longest = Math.max(0, ...shown.split(" ").map((w) => w.length));
  plate.textContent = shown;
  plate.classList.toggle("long", longest > 7 && longest <= 10);
  plate.classList.toggle("longer", longest > 10);
  $("donor-line").textContent = donorLabel(state.current.donor);
}

function markDirty() { state.dirty = true; renderSteps(); }

function fillForm() {
  $("name").value = state.current.name;
  $("author").value = state.current.author || "";
  $("export").hidden = $("delete").hidden = !state.current.id;
  $("form-error").textContent = "";
  renderDonors();
  renderStage();
}

async function selectCharacter(character) {
  if (state.dirty && !confirm("You have unsaved changes. Switch anyway?")) return;
  state.current = character ? { ...character } : blank();
  state.dirty = false;
  clearPortrait();
  fillForm();
  renderRoster();
  if (character && character.portrait) {
    try {
      const ps1 = await loadImage(character.portrait);
      $("portrait-canvas").getContext("2d").drawImage(ps1, 0, 0, PORTRAIT_W, PORTRAIT_H);
      state.hasPortrait = true;
      $("portrait-empty").hidden = true;
      if (character.source) {
        state.source = await loadImage(character.source);
        state.crop = { zoom: 100, x: 0, y: 0 };
        syncSliders();
        $("portrait-controls").hidden = false;
      }
    } catch { /* portrait missing; the form still works */ }
  }
  renderSteps();
}

function renderRoster() {
  const list = $("roster");
  list.replaceChildren();
  for (const c of state.characters) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-current", String(c.id === state.current.id));
    const thumb = c.portrait ? Object.assign(document.createElement("img"), { src: c.portrait, alt: "" })
      : Object.assign(document.createElement("span"), { className: "thumb" });
    const text = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = c.name;
    const small = document.createElement("small");
    small.textContent = donorLabel(c.donor);
    text.append(strong, small);
    button.append(thumb, text);
    button.addEventListener("click", () => selectCharacter(c));
    li.append(button);
    list.append(li);
  }
  $("roster-empty").hidden = state.characters.length > 0;
}

// Fighters in the game's customs.txt that this library does not have. The
// builder never drops them on its own: the user adds or removes each one.
function renderUnlinked() {
  const list = $("unlinked-list");
  list.replaceChildren();
  for (const u of state.unlinked) {
    const li = document.createElement("li");
    const thumb = u.portrait ? Object.assign(document.createElement("img"), { src: u.portrait, alt: "" })
      : Object.assign(document.createElement("span"), { className: "thumb" });
    const who = document.createElement("div");
    who.className = "who";
    const strong = document.createElement("strong");
    strong.textContent = u.name;
    const small = document.createElement("small");
    small.textContent = u.files ? donorLabel(u.donor) : `${donorLabel(u.donor)} · portrait files missing`;
    const actions = document.createElement("div");
    actions.className = "actions";
    const add = Object.assign(document.createElement("button"), { type: "button", className: "btn btn-ghost", textContent: "Add to library" });
    add.addEventListener("click", () => adoptUnlinked(u));
    const drop = Object.assign(document.createElement("button"), { type: "button", className: "btn btn-danger", textContent: "Remove from game" });
    drop.addEventListener("click", () => removeUnlinked(u));
    actions.append(add, drop);
    who.append(strong, small, actions);
    li.append(thumb, who);
    list.append(li);
  }
  $("unlinked").hidden = state.unlinked.length === 0;
}

async function adoptUnlinked(u) {
  if (state.dirty && !confirm("You have unsaved changes. Continue anyway?")) return;
  try {
    const character = await api("/api/unlinked/adopt", { key: u.key });
    state.dirty = false;
    await loadCharacters();
    selectCharacter(character);
    toast(character.portrait ? `${character.name} added to your library` : `${character.name} added to your library, without a portrait`);
  } catch (e) { toast(e.message); }
}

async function removeUnlinked(u) {
  if (!confirm(`Remove ${u.name} from the Custom page? Its portrait and name plate files are deleted from the game folder. This cannot be undone.`)) return;
  try {
    const result = await api("/api/unlinked/remove", { key: u.key, confirm: true });
    await loadCharacters();
    if (!showWarnings(result)) toast(`${u.name} removed from the Custom page`);
  } catch (e) { toast(e.message); }
}

async function loadCharacters() {
  [state.characters, state.unlinked] = await Promise.all([api("/api/characters"), api("/api/unlinked")]);
  renderRoster();
  renderUnlinked();
}

async function save(event) {
  event.preventDefault();
  const error = $("form-error");
  const name = $("name").value.trim().toUpperCase();
  if (!NAME_VALID.test(name)) { error.textContent = "Enter a name of 1 to 15 characters: letters (no F or Q), space, period, hyphen or 2."; $("name").focus(); return; }
  if (state.current.donor === null) { error.textContent = "Choose a donor."; return; }
  error.textContent = "";
  const body = { id: state.current.id, name, donor: state.current.donor, author: $("author").value.trim() };
  if (state.portraitChanged && state.source) {
    body.portrait_ps1 = $("portrait-canvas").toDataURL("image/png");
    body.portrait_source = sourcePNG();
    if (state.fullCanvas) body.portrait_full = state.fullCanvas.toDataURL("image/png");
  }
  $("save").disabled = true;
  try {
    const saved = await api("/api/characters", body);
    state.dirty = false;
    state.portraitChanged = false;
    state.current = { ...saved };
    await loadCharacters();
    fillForm();
    if (!showWarnings(saved)) toast(isExpanded() ? `${saved.name} saved to the Custom page` : `${saved.name} saved`);
  } catch (e) { error.textContent = e.message; }
  finally { $("save").disabled = false; renderSteps(); }
}

async function removeCharacter() {
  if (!state.current.id || !confirm(`Delete ${state.current.name}? This cannot be undone.`)) return;
  try {
    const result = await api("/api/characters/delete", { id: state.current.id });
    if (!showWarnings(result)) toast(`${state.current.name} deleted`);
    state.dirty = false;
    await loadCharacters();
    selectCharacter(null);
  } catch (e) { toast(e.message); }
}

async function importPackage(file) {
  if (!file) return;
  const buffer = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < buffer.length; i += 0x8000) binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000));
  try {
    const character = await api("/api/import", { file: btoa(binary) });
    await loadCharacters();
    state.dirty = false;
    selectCharacter(character);
    if (!showWarnings(character)) toast(`${character.name} imported`);
  } catch (e) { toast(e.message); }
  $("import-file").value = "";
}

/* ---------------------------------------------------------- status -- */

function setStep(id, kind, text, fill) {
  const step = $(id);
  step.classList.remove("ok", "bad", "busy");
  if (kind) step.classList.add(kind);
  step.querySelector(".sym").textContent = { ok: "△", bad: "○", busy: "□" }[kind] || "□";
  step.querySelector(".step-text").textContent = text;
  const bar = step.querySelector(".bar");
  bar.classList.toggle("indeterminate", fill === "busy");
  step.querySelector(".fill").style.width = kind === "ok" ? "100%" : typeof fill === "number" ? `${Math.round(fill * 100)}%` : "0%";
}

function setGauge(prefix, kind, label, text, fill) {
  const sym = $(`${prefix}-sym`);
  sym.className = "sym" + (kind ? ` ${kind}` : "");
  sym.textContent = { ok: "△", bad: "○", busy: "□" }[kind] || "□";
  $(`${prefix}-label`).textContent = label;
  const bar = $(`${prefix}-fill`).parentElement;
  bar.classList.toggle("indeterminate", fill === "busy");
  $(`${prefix}-fill`).style.width = typeof fill === "number" ? `${Math.round(fill * 100)}%` : "0%";
  $(prefix === "project" ? "project-text" : "build-gauge-text").textContent = text;
}

function renderSteps() {
  const s = state.status;
  const supportBtn = $("support-button"), buildBtn = $("build-button"), playBtn = $("play-button"), testBtn = $("test-button");
  supportBtn.textContent = "Install";
  supportBtn.disabled = buildBtn.disabled = playBtn.disabled = testBtn.disabled = true;
  if (!s) return;
  const testing = s.test && s.test.state === "running";
  testBtn.textContent = testing ? `${s.test.phase || "Testing"}…` : "Test";
  testBtn.disabled = testing || !s.patch || !s.patch.installed || s.build === "running" || s.game.running;
  if (!s.found) {
    setStep("step-support", "bad", "Tekken 3 Recompiled folder not found. Click the Project bar to choose it.");
    setStep("step-build", null, "Waiting for step 1");
    setStep("step-play", null, "Waiting for step 2");
    return;
  }
  const building = s.build === "running";
  const p = s.patch;
  $("step-support").querySelector(".step-name").textContent = isExpanded() ? "Custom page" : "Creator support";
  if (!s.jun) setStep("step-support", "bad", "Requires Jun: run the Easy Setup with Include Jun Kazama checked.");
  else if (p.installed) setStep("step-support", "ok", "Installed");
  else if (p.outdated && p.compatible) {
    setStep("step-support", null, "Update ready for the builder's changes. Install, then build again.");
    supportBtn.textContent = "Update";
    supportBtn.disabled = building;
  }
  else if (!p.compatible) setStep("step-support", "bad", p.problem || "This version is not supported.");
  else {
    setStep("step-support", null, p.old_probe ? "Replaces the Dizzy test with the full version."
      : isExpanded() ? "Adds a CUSTOM page to the select screen" : "Not installed yet");
    supportBtn.disabled = building;
  }

  const phase = s.build_phase === "Configure" ? "Configuring" : "Building";
  if (building) setStep("step-build", "busy", `${phase}${s.build_progress != null ? ` ${Math.round(s.build_progress * 100)}%` : "…"}`,
    s.build_progress != null ? s.build_progress : "busy");
  else if (!p.installed && s.exe_support) { setStep("step-build", null, "Rebuild to get the original game with Jun back"); buildBtn.disabled = !s.toolchain; }
  else if (!p.installed) setStep("step-build", null, "Waiting for step 1");
  else if (!s.toolchain) setStep("step-build", "bad", "Easy Setup compiler not found.");
  else if (s.built) setStep("step-build", "ok", "Up to date");
  else if (state.lastBuild === "failed") { setStep("step-build", "bad", "Build failed. Open the log for details."); buildBtn.disabled = false; }
  else { setStep("step-build", null, isExpanded() ? "Needed to put the Custom page in the game" : "Needed to put creator support in the game"); buildBtn.disabled = false; }

  const c = state.current;
  if (isExpanded()) {
    playBtn.lastChild.textContent = "Play";
    const count = state.characters.length + state.unlinked.length, max = s.custom_max || 12;
    if (s.game.running) setStep("step-play", "busy", "Game running", "busy");
    else if (!s.built) setStep("step-play", null, "Waiting for step 2");
    else if (!count) setStep("step-play", null, "Save a fighter to put it on the Custom page");
    else if (state.dirty) setStep("step-play", null, "Save your changes first");
    else {
      setStep("step-play", "ok", `${Math.min(count, max)} on the CUSTOM page: press R2 twice on the select screen`);
      playBtn.disabled = false;
    }
    return;
  }
  playBtn.lastChild.textContent = c.id ? `Play as ${c.name}` : "Play";
  if (s.game.running) setStep("step-play", "busy", `Game running${s.game.character ? ` with ${s.game.character} in the last slot` : ""}`, "busy");
  else if (!s.built) setStep("step-play", null, "Waiting for step 2");
  else if (!c.id) setStep("step-play", null, "Choose or save a fighter");
  else if (state.dirty) setStep("step-play", null, "Save your changes first");
  else {
    setStep("step-play", "ok", `${c.name} takes the last slot, with Jun's portrait for now`);
    playBtn.disabled = false;
  }
}

function renderProject() {
  const s = state.status;
  $("title-game").textContent = s && s.kind === "expanded" ? "Tekken 3 Expanded" : s && s.kind ? "Tekken 3 Recompiled" : "Tekken 3";
  if (s && s.found && s.kind) setGauge("project", "ok", `${s.kind === "expanded" ? "Expanded" : "Game"} v${s.version || "?"}`, s.root, 1);
  else if (s && s.found) setGauge("project", "bad", "Project", "Unsupported game version", 0);
  else setGauge("project", "bad", "Project", "Folder not found. Click to choose it.", 0);
  if (!s || !s.found) setGauge("build", null, "Build", "Waiting", 0);
  else if (s.build === "running") setGauge("build", "busy", "Build",
    `${s.build_phase === "Configure" ? "Configuring" : "Building"}…`, s.build_progress != null ? s.build_progress : "busy");
  else if (state.lastBuild === "failed" && !s.built) setGauge("build", "bad", "Build", "Failed", 0);
  else if (s.built) setGauge("build", "ok", "Build", isExpanded() ? "Custom page ready" : "Creator support ready", 1);
  else setGauge("build", null, "Build", s.patch.installed ? "Rebuild needed" : "Not built with the builder's support", 0);
  $("project-details").textContent = s && s.found
    ? `Found: ${s.root}\n${s.kind === "expanded" ? "Tekken 3 Expanded" : s.kind ? "Tekken3Recompiled" : "Unsupported project"} ${s.version || ""}. `
      + `${s.kind === "recompiled" ? `Jun ${s.jun ? "installed" : "not installed"}. ` : ""}Compiler ${s.toolchain ? "found" : "not found"}.`
    : "Put the character-builder folder inside your Easy Setup folder, or enter the path below.";
}

async function refresh() {
  try {
    state.status = await api("/api/status");
  } catch (e) {
    $("project-text").textContent = e.message;
    return;
  }
  const s = state.status;
  if (s.build === "running" || state.lastBuild === "running") await pollBuild();
  if (state.lastGameRunning && !s.game.running && s.game.summary.length) {
    log("== Game closed ==");
    s.game.summary.forEach(log);
  }
  state.lastGameRunning = s.game.running;
  const testState = s.test ? s.test.state : "idle";
  if (state.lastTest === "running" && testState !== "running") {
    await loadReport(true);
    toast(testState === "done" ? "Test finished: report ready" : "Test failed: see the report");
  }
  state.lastTest = testState;
  renderProject();
  renderSteps();
}

async function loadReport(open) {
  const r = await api("/api/test");
  $("report").textContent = r.report || "";
  $("report-panel").hidden = !r.report;
  if (open && r.report) $("report-panel").open = true;
}

async function pollBuild() {
  const b = await api(`/api/build?since=${state.logTotal}`);
  b.lines.forEach(log);
  state.logTotal = b.total;
  if (state.lastBuild === "running" && b.state === "success") toast("Game built");
  if (state.lastBuild === "running" && b.state === "failed") { toast("Build failed"); $("console").open = true; }
  state.lastBuild = b.state;
}

/* ---------------------------------------------------------- wiring -- */

function wire() {
  $("character-form").addEventListener("submit", save);
  $("name").addEventListener("input", (e) => {
    const cleaned = e.target.value.toUpperCase().replace(NAME_BLOCKED, "");
    if (cleaned !== e.target.value) e.target.value = cleaned;
    state.current.name = cleaned.trim(); markDirty(); renderStage();
  });
  $("author").addEventListener("input", markDirty);
  $("new-character").addEventListener("click", () => selectCharacter(null));
  $("delete").addEventListener("click", removeCharacter);
  $("export").addEventListener("click", () => { if (state.current.id) location.href = `/api/export/${state.current.id}`; });
  $("import-file").addEventListener("change", (e) => importPackage(e.target.files[0]));
  $("portrait-file").addEventListener("change", (e) => { useFile(e.target.files[0]); e.target.value = ""; });
  for (const [id, key] of [["zoom", "zoom"], ["pan-x", "x"], ["pan-y", "y"]]) {
    $(id).addEventListener("input", (e) => {
      state.crop[key] = Number(e.target.value); state.portraitChanged = true; drawPortrait(); markDirty();
    });
  }
  const frame = $("portrait-frame");
  frame.addEventListener("dragover", (e) => { e.preventDefault(); frame.classList.add("dragging"); });
  frame.addEventListener("dragleave", () => frame.classList.remove("dragging"));
  frame.addEventListener("drop", (e) => { e.preventDefault(); frame.classList.remove("dragging"); useFile(e.dataTransfer.files[0]); });

  $("support-button").addEventListener("click", async () => {
    try {
      const result = await api("/api/support/install", {});
      log(isExpanded() ? "Custom page support installed in the source code. Build the game next."
        : "Creator support installed in the source code. Build the game next.");
      if (!showWarnings(result)) toast(isExpanded() ? "Custom page support installed" : "Creator support installed");
    } catch (e) { toast(e.message); log("ERROR: " + e.message); }
    loadCharacters().catch(() => {});
    refresh();
  });
  $("build-button").addEventListener("click", async () => {
    try {
      $("log").textContent = ""; state.logTotal = 0;
      await api("/api/build", {});
      state.lastBuild = "running";
      $("console").open = true;
    } catch (e) { toast(e.message); }
    refresh();
  });
  $("play-button").addEventListener("click", async () => {
    try {
      await api("/api/play", { id: state.current.id });
      flash(state.current.name);
      toast(`${state.current.name} is waiting in the last slot`);
    } catch (e) { toast(e.message); }
    refresh();
  });
  $("test-button").addEventListener("click", async () => {
    try {
      await api("/api/test", {});
      state.lastTest = "running";
      toast("Test started: play a fight, then close the game");
    } catch (e) { toast(e.message); }
    refresh();
  });
  $("copy-report").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("report").textContent); toast("Report copied"); }
    catch {
      const range = document.createRange(); range.selectNodeContents($("report"));
      getSelection().removeAllRanges(); getSelection().addRange(range);
      toast(document.execCommand("copy") ? "Report copied" : "Report selected: press Ctrl+C");
    }
  });
  $("project-button").addEventListener("click", () => {
    $("root-input").value = state.status && state.status.root ? state.status.root : "";
    $("root-error").textContent = "";
    $("support-remove").hidden = !(state.status && state.status.patch && (state.status.patch.installed || state.status.patch.old_probe));
    $("sync-customs").hidden = !isExpanded();
    $("project-dialog").showModal();
  });
  $("root-save").addEventListener("click", async () => {
    try {
      state.status = await api("/api/root", { root: $("root-input").value.trim() });
      $("project-dialog").close(); toast("Folder set"); refresh();
    } catch (e) { $("root-error").textContent = e.message; }
  });
  $("support-remove").addEventListener("click", async () => {
    if (!confirm(isExpanded() ? "Restore Tekken 3 Expanded's original source code? Rebuild afterwards."
      : "Restore the original source code? Rebuild afterwards to get Jun back.")) return;
    try {
      await api("/api/support/uninstall", {});
      $("project-dialog").close(); toast("Original code restored. Rebuild the game."); refresh();
    } catch (e) { $("root-error").textContent = e.message; }
  });
  $("sync-customs").addEventListener("click", async () => {
    try {
      const result = await api("/api/sync", {});
      $("project-dialog").close();
      loadCharacters().catch(() => {});
      if (!showWarnings(result)) toast("Custom page files refreshed");
    } catch (e) { $("root-error").textContent = e.message; }
  });
  window.addEventListener("beforeunload", (e) => { if (state.dirty) e.preventDefault(); });
}

wire();
fillForm();
loadCharacters().catch((e) => toast(e.message));
loadReport(false).catch(() => {});
refresh();
setInterval(refresh, 1500);
