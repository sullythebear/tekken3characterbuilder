// Stage, music and the announcer's name call of a fighter (game patch T3CB-PATCH-17 and
// <Key>-TTT1-sfx.jus). Uses app.js's state, api, toast, markDirty and DONORS.
(() => {
  // Tekken 3's stages, by a fighter that owns each (several fighters share one)
  const STAGES = [[0, "Paul / Bryan"], [1, "Law / Kuma"], [2, "Lei"], [3, "King"], [4, "Yoshimitsu / Mokujin"],
    [5, "Nina / Anna / Gun Jack"], [6, "Hwoarang"], [7, "Xiaoyu"], [8, "Eddy"], [9, "Jin"],
    [10, "Julia / Heihachi"], [14, "Ogre / True Ogre"], [17, "Gon"], [19, "Dr. B"]];
  const RECORD_SECONDS = 3;
  let recordingWav = null, rawWav = null, recorder = null, audio = null;

  function fillLists() {
    const stage = $("stage"), music = $("music");
    stage.add(new Option("", ""));
    for (const [id, owners] of STAGES) stage.add(new Option(`${owners}'s stage`, String(id)));
    music.add(new Option("", ""));
    for (const d of DONORS) music.add(new Option(`${d.name}'s theme`, String(d.id)));
  }

  // the first option follows the fighting style
  function styleLabels() {
    const d = DONORS[state.current.donor];
    $("stage").options[0].text = d ? `Style's (${d.name}'s stage)` : "Style's stage";
    $("music").options[0].text = d ? `Style's (${d.name}'s theme)` : "Style's theme";
  }

  function fill() {
    recordingWav = rawWav = null;
    $("name-pitch").value = "0"; $("name-echo").value = "none";
    styleLabels();
    $("stage").value = state.current.stage ?? "";
    $("music").value = state.current.music ?? "";
    $("name-call").value = state.current.name_call || "off";
    loadVoices().then(() => { $("name-voice").value = state.current.name_call_voice || ""; });
    $("stage-look").value = state.current.stage_look || "";
    $("stage-tint").value = state.current.stage_tint || "#ff8040";
    $("stage-strength").value = state.current.stage_strength ?? 60;
    $("stage-tint-row").hidden = $("stage-look").value !== "custom";
    showMode();
    sheet();
  }

  // the speech voices installed on this computer (asked once)
  let voicesLoaded = null;
  function loadVoices() {
    voicesLoaded ||= api("/api/namecall/voices", {}).then((r) => {
      for (const v of r.voices) $("name-voice").add(new Option(v.replace(/^Microsoft /, "").replace(/ Desktop$/, ""), v));
    }).catch(() => {});
    return voicesLoaded;
  }

  function showMode() {
    const mode = $("name-call").value;
    $("name-play").disabled = mode === "off";
    $("name-own").hidden = mode !== "own";
    $("name-voice-row").hidden = mode !== "auto";
    $("name-shape").hidden = mode !== "own" || !rawWav;
    $("name-hint").textContent = mode === "own" && !recordingWav && !state.current.name_recording
      ? "Record your call (up to 3 seconds) or choose a sound file."
      : "The announcer calls the name in Practice, as Tekken 3 does for its own fighters.";
  }

  // the stage (or its textures) in the chosen colours (Stage Lab preview)
  let sheetFor = "";
  async function sheet() {
    const img = $("stage-sheet");
    if (state.current.donor === null || $("page-stage").hidden) return;
    $("stage-tint-row").hidden = $("stage-look").value !== "custom";
    const want = { donor: state.current.donor, stage: $("stage").value, look: $("stage-look").value,
      tint: $("stage-tint").value, strength: Number($("stage-strength").value), view: $("stage-view").value };
    const key = JSON.stringify(want);
    if (key === sheetFor) return;
    sheetFor = key;
    try {
      const r = await api("/api/stage/preview", want);
      if (sheetFor !== key) return;
      img.src = "data:image/png;base64," + r.png;
      img.hidden = false;
    } catch (e) { img.hidden = true; sheetFor = ""; toast(e.message); }
  }

  function body() {
    const value = (id) => ($(id).value === "" ? null : Number($(id).value));
    const b = { stage: value("stage"), music: value("music"), name_call: $("name-call").value,
      name_call_voice: $("name-voice").value || null,
      stage_look: $("stage-look").value || null, stage_tint: $("stage-tint").value,
      stage_strength: Number($("stage-strength").value) };
    if (recordingWav) b.name_call_wav = recordingWav;
    return b;
  }

  function play(url) {
    if (audio) audio.pause();
    audio = new Audio(url);
    audio.play().catch(() => toast("The sound could not play."));
  }

  async function preview() {
    const mode = $("name-call").value;
    if (mode === "own" && recordingWav) return play(recordingWav);
    const button = $("name-play");
    button.disabled = true;
    try {
      const r = await api("/api/namecall/preview", { mode, id: state.current.id, name: $("name").value,
        voice: $("name-voice").value });
      play(r.wav);
    } catch (e) { toast(e.message); } finally { button.disabled = false; }
  }

  // any sound the browser can decode -> 44100 Hz mono 16-bit WAV (the game's rate)
  async function toWav(blob) {
    const context = new AudioContext();
    let decoded;
    try { decoded = await context.decodeAudioData(await blob.arrayBuffer()); }
    finally { context.close(); }
    const frames = Math.min(Math.ceil(decoded.duration * 44100), 44100 * 10);
    const offline = new OfflineAudioContext(1, frames, 44100);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const pcm = (await offline.startRendering()).getChannelData(0);
    const view = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
    text(0, "RIFF"); view.setUint32(4, 36 + pcm.length * 2, true); text(8, "WAVEfmt ");
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, 44100, true); view.setUint32(28, 88200, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, pcm.length * 2, true);
    pcm.forEach((v, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 32767, true));
    const bytes = new Uint8Array(view.buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return "data:audio/wav;base64," + btoa(binary);
  }

  async function useSound(blob) {
    try { rawWav = await toWav(blob); await processSound(); }
    catch (e) { toast(e.message || "That sound could not be read."); }
  }

  // the server trims and levels it (and with the effect, makes it the announcer's): what plays
  // here is what the game plays
  async function processSound() {
    if (!rawWav) return;
    try {
      const r = await api("/api/namecall/preview", { mode: "own", wav: rawWav,
        pitch: Number($("name-pitch").value), echo: $("name-echo").value });
      recordingWav = r.wav;
      $("name-call").value = "own";
      markDirty();
      showMode();
      play(recordingWav);
    } catch (e) { toast(e.message || "That sound could not be read."); }
  }

  async function record() {
    const button = $("name-record");
    if (recorder) { recorder.stop(); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { toast("No microphone, or it is not allowed: choose a sound file instead."); return; }
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      recorder = null;
      button.textContent = "Record";
      useSound(new Blob(chunks, { type: chunks[0]?.type || "audio/webm" }));
    };
    recorder.start();
    button.textContent = "Stop";
    setTimeout(() => recorder?.stop(), RECORD_SECONDS * 1000);
  }

  function init() {
    fillLists();
    for (const id of ["stage", "music", "stage-look"]) $(id).addEventListener("change", markDirty);
    for (const id of ["stage", "stage-look", "stage-tint", "stage-strength", "stage-view"]) $(id).addEventListener("change", sheet);
    for (const id of ["stage-tint", "stage-strength"]) $(id).addEventListener("change", markDirty);
    $("name-call").addEventListener("change", () => { markDirty(); showMode(); });
    $("name-play").addEventListener("click", preview);
    $("name-record").addEventListener("click", record);
    $("name-voice").addEventListener("change", markDirty);
    $("name-pitch").addEventListener("input", () => { $("name-pitch").title = `${$("name-pitch").value} %`; });
    for (const id of ["name-pitch", "name-echo"]) $(id).addEventListener("change", processSound);
    $("name-announcer").addEventListener("click", () => {
      $("name-pitch").value = "-18"; $("name-echo").value = "hall"; processSound();
    });
    $("name-file").addEventListener("change", (e) => { if (e.target.files[0]) useSound(e.target.files[0]); e.target.value = ""; });
  }

  window.T3Arena = { init, fill, body, styleLabels, sheet, saved: () => { recordingWav = null; } };
})();
