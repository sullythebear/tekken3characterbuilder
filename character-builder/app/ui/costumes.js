"use strict";
// 3D preview and colour variants. The model comes from the player's own disc through
// /api/model/<n>; textures stay palette indices, so recolouring rewrites a palette texture.

const T3Costumes = (() => {
  const $ = (id) => document.getElementById(id);
  let host = null;             // { getCurrent(), onChange(), log(text) }
  let donorModels = null;      // { available, reason, donors: { donor: [model per costume] } }
  const models = new Map();    // model number -> parsed model
  let selected = { kind: "costume", index: 0 };   // or { kind: "variant", index }
  let mode = "parts";
  let viewer = null;
  let current = null;          // parsed model on screen
  let pickedPart = null;

  /* ------------------------------------------------------------ colours -- */
  const ps1ToRgb = (c) => [(c & 31) / 31, ((c >> 5) & 31) / 31, ((c >> 10) & 31) / 31];
  function rgbToPs1(r, g, b, stp) {
    const q = (v) => Math.max(0, Math.min(31, Math.round(v * 31)));
    let c = q(r) | (q(g) << 5) | (q(b) << 10) | (stp ? 0x8000 : 0);
    return c === 0 ? 0x0421 : c;     // pure 0 would turn transparent on the PS1
  }
  function toHsl(r, g, b) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
    if (mx === mn) return [0, 0, l];
    const d = mx - mn, s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [h / 6, s, l];
  }
  function fromHsl(h, s, l) {
    if (!s) return [l, l, l];
    const f = (p, q, t) => { t = ((t % 1) + 1) % 1;
      return t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    return [f(p, q, h + 1 / 3), f(p, q, h), f(p, q, h - 1 / 3)];
  }
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const rgbToHex = (r, g, b) => "#" + [r, g, b].map((v) => Math.round(clamp01(v) * 255).toString(16).padStart(2, "0")).join("");
  const ps1ToCss = (c) => (c === 0 ? "transparent" : rgbToHex(...ps1ToRgb(c)));
  const isSkin = (h, s, l) => h >= 0.02 && h <= 0.11 && s >= 0.18 && s <= 0.75 && l >= 0.25 && l <= 0.82;

  /* ------------------------------------------------------------- model --- */
  function parseModel(json) {
    // the game's axes are mirrored against the viewer's (text on a shirt read backwards)
    json.positions = json.positions.map((v, i) => (i % 3 === 0 ? -v : v));
    const raw = Uint8Array.from(atob(json.band), (c) => c.charCodeAt(0));
    const hw = new Uint16Array(raw.buffer), words = json.band_words || 64;   // halfwords per band row
    const idx4 = new Uint8Array(words * 4 * 256), idx8 = new Uint8Array(words * 2 * 256);
    for (let y = 0; y < 256; y++) for (let x = 0; x < words; x++) {
      const w = hw[y * words + x];
      for (let k = 0; k < 4; k++) idx4[(y * words + x) * 4 + k] = (w >> (4 * k)) & 15;
      idx8[(y * words + x) * 2] = w & 255; idx8[(y * words + x) * 2 + 1] = w >> 8;
    }
    const ids = Object.keys(json.cluts).map(Number).sort((a, b) => a - b);
    const cluts = new Map(ids.map((id) => [id, json.cluts[id]]));
    // per-CLUT triangle counts, for sorting parts by size
    const use = new Map();
    for (let i = 0; i < json.material.length; i += 3) {
      const id = json.material[i] & 0x7fff;   // bit 15: 8-bit texture; the rest: its CLUT id
      use.set(id, (use.get(id) || 0) + 1);
    }
    const model = { json, words, idx4, idx8, ids, cluts, use, missing: new Set(json.missing || []) };
    model.parts = groupParts(model);
    return model;
  }

  // Pieces of clothing: the game can only recolour whole palettes (CLUTs). A palette usually
  // covers one piece, and one piece can use several palettes (Bryan's camouflage trousers: six),
  // so palettes on the same body part with a similar colour form one piece. Named after where
  // their triangles sit on the body.
  const REGION = { 1: "Torso", 2: "Torso", 3: "Hips", 4: "Hips", 5: "Legs", 6: "Legs", 8: "Legs", 9: "Legs",
    7: "Feet", 10: "Feet", 11: "Shoulders", 15: "Shoulders", 12: "Arms", 13: "Arms", 16: "Arms", 17: "Arms",
    14: "Hands", 18: "Hands", 19: "Head", 20: "Head" };
  const REGION_ORDER = ["Head", "Shoulders", "Torso", "Arms", "Hands", "Hips", "Legs", "Feet", "Extra"];
  // How often each palette entry shows on the model: texels at the corners and centre of every
  // triangle. A 256-colour palette holds several pieces (Bryan's vest and skin), so a piece's
  // colour comes from the entries its triangles use, not from the whole palette.
  function texelUse(model) {
    const j = model.json, use = new Map(), w4 = model.words * 4, w8 = model.words * 2;
    for (let t = 0; t < j.material.length; t += 3) {
      const m = j.material[t], id = m & 0x7fff, eight = m & 0x8000;
      const counts = use.get(id) || new Map(); use.set(id, counts);
      const pts = [0, 1, 2].map((k) => [j.uv[(t + k) * 2], j.uv[(t + k) * 2 + 1]]);
      pts.push([(pts[0][0] + pts[1][0] + pts[2][0]) / 3, (pts[0][1] + pts[1][1] + pts[2][1]) / 3]);
      for (const [u, v] of pts) {
        const x = Math.min(Math.floor(u), (eight ? w8 : w4) - 1), y = Math.min(Math.floor(v), 255);
        const i = eight ? model.idx8[y * w8 + x] : model.idx4[y * w4 + x];
        counts.set(i, (counts.get(i) || 0) + 1);
      }
    }
    return use;
  }

  function groupParts(model) {
    const bones = model.json.bones || [], where = new Map(), texels = texelUse(model);
    for (let t = 0; t < bones.length; t++) {
      const id = model.json.material[t * 3] & 0x7fff, region = REGION[bones[t]] || "Extra";
      const m = where.get(id) || new Map(); m.set(region, (m.get(region) || 0) + 1); where.set(id, m);
    }
    let parts = [];
    for (const id of model.ids) {
      const pal = model.cluts.get(id);
      if (!pal.some((c) => c !== 0) || !model.use.get(id)) continue;
      let x = 0, y = 0, s = 0, l = 0, n = 0, chroma = 0;
      const seen = texels.get(id) || new Map();
      const weights = seen.size ? [...seen] : pal.map((c, i) => [i, 1]);
      for (const [i, w] of weights) {
        const c = pal[i]; if (!c) continue;
        const rgb = ps1ToRgb(c), [h, ss, ll] = toHsl(...rgb);
        chroma += (Math.max(...rgb) - Math.min(...rgb)) * w;
        x += Math.cos(h * 2 * Math.PI) * ss * w; y += Math.sin(h * 2 * Math.PI) * ss * w; s += ss * w; l += ll * w; n += w;
      }
      if (!n) continue;
      const h = ((Math.atan2(y, x) / (2 * Math.PI)) + 1) % 1;
      const counts = [...(where.get(id) || new Map([["Extra", 1]])).entries()].sort((a, b) => b[1] - a[1]);
      const total = counts.reduce((sum, [, c]) => sum + c, 0);
      const regions = counts.filter(([, c], i) => i === 0 || c >= total * 0.25).map(([r]) => r).slice(0, 2);
      parts.push({ ids: [id], key: String(id), h, s: s / n, l: l / n, chroma: chroma / n, weight: model.use.get(id), skin: isSkin(h, s / n, l / n),
        regions, region: REGION_ORDER.indexOf(regions[0]) });
    }
    const grey = (p) => p.chroma < 0.12;
    const similar = (g, c) => g.skin === c.skin && (c.skin || (grey(g) && grey(c) ? Math.abs(g.l - c.l) < 0.25 :
      Math.abs(g.s - c.s) < 0.22 && Math.abs(g.l - c.l) < 0.28 && Math.min(Math.abs(g.h - c.h), 1 - Math.abs(g.h - c.h)) < 0.06));
    const pieces = [];
    for (const c of parts.sort((a, b) => b.weight - a.weight)) {
      const g = pieces.find((g) => g.regions.some((r) => c.regions.includes(r)) && similar(g, c));   // share a body part
      if (!g) { pieces.push(c); continue; }
      g.ids.push(c.ids[0]); g.weight += c.weight;
      for (const r of c.regions) if (!g.regions.includes(r) && g.regions.length < 2) g.regions.push(r);
    }
    for (const g of pieces) g.key = g.ids.join("-");
    parts = pieces;
    parts.sort((a, b) => a.region - b.region || b.weight - a.weight);
    const count = new Map(), seen = new Map();
    const base = (p) => `${p.regions.join(" & ")} \u00b7 ${p.skin ? "Skin" : colourName(p.h, p.chroma < 0.12 ? 0 : p.s, p.l)}`;
    for (const p of parts) count.set(base(p), (count.get(base(p)) || 0) + 1);
    for (const p of parts) {
      const k = (seen.get(base(p)) || 0) + 1; seen.set(base(p), k);
      p.label = count.get(base(p)) > 1 ? `${base(p)} ${k}` : base(p);
    }
    return parts;
  }
  function colourName(h, s, l) {
    if (s < 0.2) return l < 0.25 ? "Black" : l > 0.7 ? "White" : "Grey";
    const names = [[0.03, "Red"], [0.09, "Orange"], [0.17, "Gold"], [0.25, "Yellow"], [0.45, "Green"], [0.55, "Teal"],
      [0.7, "Blue"], [0.8, "Purple"], [0.93, "Pink"], [1.01, "Red"]];
    return (l < 0.22 ? "Dark " : "") + names.find(([lim]) => h < lim)[1];
  }

  /* ------------------------------------------------------- variant maths -- */
  function blankRecipe() { return { tint: { h: 0, s: 100, l: 0, keepSkin: true }, parts: {}, free: {} }; }

  // Final palettes of a variant: tint, then part colours, then single colours.
  function computeCluts(model, recipe) {
    const out = {};
    const skinIds = new Set(model.parts.filter((p) => p.skin).flatMap((p) => p.ids));
    const partOf = new Map(), colourOf = new Map();
    for (const p of model.parts) for (const id of p.ids) partOf.set(id, p);
    for (const [key, hex] of Object.entries(recipe.parts || {})) for (const id of key.split("-")) colourOf.set(Number(id), hex);
    const t = recipe.tint || blankRecipe().tint;
    for (const id of model.ids) {
      const src = model.cluts.get(id);
      const part = partOf.get(id), target = part && colourOf.get(id);
      const tinted = !(t.keepSkin && skinIds.has(id)) && (t.h || t.s !== 100 || t.l);
      let changed = false;
      const cols = src.map((c, i) => {
        const free = recipe.free[`${id}:${i}`];
        if (free !== undefined) { changed = true; return free; }
        if (c === 0) return 0;
        let [h, s, l] = toHsl(...ps1ToRgb(c));
        if (tinted) { h = (h + t.h / 360 + 1) % 1; s = clamp01(s * t.s / 100); l = clamp01(l + t.l / 100); }
        if (target) {
          const [th, ts, tl] = toHsl(...hexToRgb(target));
          h = th; s = part.s < 0.08 ? ts : clamp01(s * ts / Math.max(part.s, 0.05)); l = clamp01(l + (tl - part.l));
        }
        if (!tinted && !target) return c;
        changed = true;
        return rgbToPs1(...fromHsl(h, s, l), c & 0x8000);
      });
      if (changed) out[id] = cols;
    }
    return out;
  }

  const SCHEMES = [
    ["Crimson", ["#b3122e", "#1b1b22", "#d8b04a"]], ["Midnight", ["#1d2b6b", "#0d0d16", "#8fa3d8"]],
    ["Jade", ["#1f8f5f", "#e8e2c8", "#0f3d2e"]], ["Royal", ["#5b2a86", "#e0b43a", "#f2f2f2"]],
    ["Ash", ["#6d6d6d", "#2a2a2a", "#bdbdbd"]], ["Neon", ["#ff2fa8", "#20f0ff", "#ffe600"]],
    ["Sunset", ["#ff7a2f", "#7a1f3d", "#ffd27a"]], ["Ivory", ["#efe6d2", "#a88a5a", "#3c2f25"]],
    ["Shadow", ["#1a1a1f", "#3a3a48", "#8a1020"]], ["Ocean", ["#0e6ba8", "#a2d6f9", "#123049"]],
  ];

  /* ------------------------------------------------------------- WebGL --- */
  // models are exported standing with the shoulders along +X; this angle looks at the front, a little turned
  const FRONT_YAW = 0.35;
  function createViewer(canvas) {
    const gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: false });
    if (!gl) return null;
    const vs = `attribute vec3 pos; attribute vec2 uv; attribute float row; attribute float bpp;
      uniform mat4 mvp; varying vec2 vUv; varying float vRow; varying float vBpp;
      void main(){ vUv = uv; vRow = row; vBpp = bpp; gl_Position = mvp * vec4(pos, 1.0); }`;
    const fs = `precision mediump float; uniform sampler2D tex4; uniform sampler2D tex8; uniform sampler2D pal;
      uniform float rows; uniform float pick; uniform float sel; uniform sampler2D chosen; uniform float w4; uniform float w8; varying vec2 vUv; varying float vRow; varying float vBpp;
      void main(){
        vec2 p = floor(vUv) + 0.5;
        float idx = vBpp > 0.5 ? texture2D(tex8, vec2(p.x / w8, p.y / 256.0)).r * 255.0
                               : texture2D(tex4, vec2(p.x / w4, p.y / 256.0)).r * 255.0;
        vec4 c = texture2D(pal, vec2((floor(idx + 0.5) + 0.5) / 256.0, (floor(vRow + 0.5) + 0.5) / rows));
        if (c.a < 0.5) discard;
        if (pick > 0.5) { float r = floor(vRow + 0.5) + 1.0; gl_FragColor = vec4(mod(r, 256.0) / 255.0, floor(r / 256.0) / 255.0, 0.0, 1.0); }
        else if (sel >= 0.0 && texture2D(chosen, vec2((floor(vRow + 0.5) + 0.5) / 256.0, 0.5)).r < 0.5) gl_FragColor = vec4(mix(c.rgb, vec3(0.03, 0.05, 0.17), 0.7), 1.0);
        else gl_FragColor = vec4(c.rgb, 1.0);
      }`;
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    const v = { gl, prog, yaw: FRONT_YAW, pitch: 0.12, dist: 1, zoom: 1, halfW: 1, halfH: 1, center: [0, 0, 0], count: 0, rows: 1, sel: -1, bufs: [], tex: {} };
    const tex = (w, h, fmt, data) => {
      const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texImage2D(gl.TEXTURE_2D, 0, fmt, w, h, 0, fmt, gl.UNSIGNED_BYTE, data);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
      for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, p, gl.CLAMP_TO_EDGE);
      return t;
    };
    v.setModel = (model) => {
      const j = model.json, n = j.material.length, positions = j.positions;
      const rowOf = new Map(model.ids.map((id, i) => [id, i]));
      const missingRow = model.ids.length;            // shared palettes: drawn grey
      v.rows = model.ids.length + 1; v.rowIds = [...model.ids, -1];
      const row = new Float32Array(n), bpp = new Float32Array(n);
      for (let i = 0; i < n; i++) { const m = j.material[i]; const id = m & 0x7fff;   // 8-bit too: Bryan has two 256-colour CLUTs
        row[i] = rowOf.has(id) ? rowOf.get(id) : missingRow; bpp[i] = m & 0x8000 ? 1 : 0; }
      const put = (name, data, size) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); v.bufs.push([name, b, size]); };
      v.bufs = [];
      put("pos", new Float32Array(positions), 3); put("uv", new Float32Array(j.uv), 2); put("row", row, 1); put("bpp", bpp, 1);
      v.index = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, v.index);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(j.triangles), gl.STATIC_DRAW);
      v.count = j.triangles.length;
      v.w4 = model.words * 4; v.w8 = model.words * 2;
      v.tex.t4 = tex(v.w4, 256, gl.LUMINANCE, model.idx4); v.tex.t8 = tex(v.w8, 256, gl.LUMINANCE, model.idx8);
      v.pal = new Uint8Array(256 * v.rows * 4); v.tex.pal = tex(256, v.rows, gl.RGBA, v.pal);
      v.tex.sel = tex(256, 1, gl.RGBA, new Uint8Array(256 * 4));
      const p = positions, mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
      for (let i = 0; i < p.length; i += 3) for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], p[i + k]); mx[k] = Math.max(mx[k], p[i + k]); }
      v.center = mn.map((a, k) => (a + mx[k]) / 2);
      v.halfW = Math.max(mx[0] - mn[0], mx[2] - mn[2]) / 2 || 1; v.halfH = (mx[1] - mn[1]) / 2 || 1;
      v.sel = -1; v.reset();
    };
    v.highlight = (ids) => {           // dims everything but these palettes
      const on = new Uint8Array(256 * 4).fill(0);
      v.sel = ids && ids.length ? 1 : -1;
      if (ids) for (const id of ids) { const r = v.rowIds.indexOf(id); if (r >= 0) on[r * 4] = 255; }
      gl.bindTexture(gl.TEXTURE_2D, v.tex.sel); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, on);
      v.draw();
    };
    v.setPalettes = (paletteOf) => {         // paletteOf(id) -> colours
      for (let r = 0; r < v.rows; r++) {
        const id = v.rowIds[r], cols = id >= 0 ? paletteOf(id) : null;
        for (let i = 0; i < 256; i++) {
          const o = (r * 256 + i) * 4, c = cols ? cols[i] : (i ? 0x4210 : 0);
          if (c === undefined || c === 0) { v.pal[o + 3] = 0; continue; }
          const [R, G, B] = ps1ToRgb(c); v.pal[o] = R * 255; v.pal[o + 1] = G * 255; v.pal[o + 2] = B * 255; v.pal[o + 3] = 255;
        }
      }
      gl.bindTexture(gl.TEXTURE_2D, v.tex.pal);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, v.rows, 0, gl.RGBA, gl.UNSIGNED_BYTE, v.pal);
      v.draw();
    };
    const mul = (a, b) => { const o = new Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
      let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; };
    v.reset = () => { v.yaw = FRONT_YAW; v.pitch = 0.12; v.zoom = 1; };
    // distance at which the model's width and height both fit the canvas, with a little margin
    v.fitDist = () => {
      const t = Math.tan(0.35), aspect = canvas.width / canvas.height || 1;
      return Math.max(v.halfH / t, v.halfW / (t * aspect)) * 1.12 + v.halfW * 0.5;
    };
    v.matrix = () => {
      v.dist = v.fitDist() * v.zoom;
      const w = canvas.width, h = canvas.height, f = 1 / Math.tan(0.35), near = v.dist / 20, far = v.dist * 10;
      const P = [f / (w / h), 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0];
      const cy = Math.cos(v.yaw), sy = Math.sin(v.yaw), cp = Math.cos(v.pitch), sp = Math.sin(v.pitch);
      const R = [cy, sy * sp, -sy * cp, 0, 0, cp, sp, 0, sy, -cy * sp, cy * cp, 0, 0, 0, 0, 1];
      const T = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -v.center[0], -v.center[1], -v.center[2], 1];
      const V = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -v.dist, 1];
      return mul(P, mul(V, mul(R, T)));
    };
    v.draw = (pick = false) => {
      if (!v.count) return;
      const r = canvas.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      const W = Math.max(1, Math.round(r.width * dpr)), H = Math.max(1, Math.round(r.height * dpr));
      if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
      gl.viewport(0, 0, W, H);
      gl.clearColor(0.027, 0.05, 0.17, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST); gl.useProgram(prog);
      for (const [name, b, size] of v.bufs) { const loc = gl.getAttribLocation(prog, name);
        gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0); }
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, v.index);
      gl.uniformMatrix4fv(gl.getUniformLocation(prog, "mvp"), false, new Float32Array(v.matrix()));
      [["tex4", v.tex.t4], ["tex8", v.tex.t8], ["pal", v.tex.pal], ["chosen", v.tex.sel]].forEach(([name, t], i) => {
        gl.activeTexture(gl.TEXTURE0 + i); gl.bindTexture(gl.TEXTURE_2D, t); gl.uniform1i(gl.getUniformLocation(prog, name), i); });
      gl.uniform1f(gl.getUniformLocation(prog, "rows"), v.rows);
      gl.uniform1f(gl.getUniformLocation(prog, "w4"), v.w4); gl.uniform1f(gl.getUniformLocation(prog, "w8"), v.w8);
      gl.uniform1f(gl.getUniformLocation(prog, "pick"), pick ? 1 : 0);
      gl.uniform1f(gl.getUniformLocation(prog, "sel"), pick ? -1 : v.sel);
      gl.drawElements(gl.TRIANGLES, v.count, gl.UNSIGNED_SHORT, 0);
    };
    v.pickAt = (x, y) => {                    // CSS pixels -> CLUT id or null
      v.draw(true);
      const r = canvas.getBoundingClientRect(), px = new Uint8Array(4);
      gl.readPixels(Math.round(x * canvas.width / r.width), Math.round(canvas.height - y * canvas.height / r.height), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      v.draw();
      const row = px[0] + px[1] * 256 - 1;
      return px[2] === 0 && row >= 0 && row < v.rowIds.length ? v.rowIds[row] : null;
    };
    // orbit: drag rotates, wheel zooms, a short click picks
    let drag = null, pickTimer = null;
    canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, moved: 0 }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved += Math.abs(dx) + Math.abs(dy);
      drag.x = e.clientX; drag.y = e.clientY;
      v.yaw += dx * 0.01; v.pitch = Math.max(-1.4, Math.min(1.4, v.pitch + dy * 0.01)); v.draw();
    });
    canvas.addEventListener("pointerup", (e) => {
      if (drag && drag.moved < 4 && v.onPick) {          // a click picks, unless it becomes a double-click
        const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
        clearTimeout(pickTimer); pickTimer = e.detail > 1 ? null : setTimeout(() => v.onPick(v.pickAt(x, y)), 260);
      }
      drag = null;
    });
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); v.zoom = Math.max(0.15, Math.min(3, v.zoom * (e.deltaY > 0 ? 1.1 : 0.9))); v.draw(); }, { passive: false });
    canvas.addEventListener("dblclick", () => { clearTimeout(pickTimer); v.reset(); requestAnimationFrame(() => v.draw()); });
    new ResizeObserver(() => v.draw()).observe(canvas);
    return v;
  }

  /* -------------------------------------------------------------- state -- */
  const fighter = () => host.getCurrent();
  const variants = () => (fighter().costumes = fighter().costumes || []);
  function costumeModels() {
    const d = fighter().donor;
    return donorModels && donorModels.available && d !== null && d !== undefined ? donorModels.donors[d] || [] : [];
  }
  function activeBase() {
    if (selected.kind === "variant") return variants()[selected.index]?.base ?? 0;
    return selected.index;
  }
  function activeVariant() { return selected.kind === "variant" ? variants()[selected.index] : null; }

  // the fighter's own model (3D model page) stands in for the costume it replaces
  function modelKey(base, n) {
    const own = fighter().own_model;
    return own && fighter().id && own.costume === base ? `own/${fighter().id}?v=${encodeURIComponent(own.imported || "")}` : n;
  }
  async function loadModel(n) {
    if (models.has(n)) return models.get(n);
    const r = await fetch(typeof n === "string" ? `/api/ownmodel/${n.slice(4)}` : `/api/model/${n}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "The model could not be loaded.");
    const m = parseModel(await r.json()); models.set(n, m); return m;
  }

  function paletteFor(model, variant) {
    const cl = variant ? variant.cluts || {} : {};
    return (id) => cl[id] || model.cluts.get(id);
  }

  async function show() {
    const list = costumeModels(), status = $("model-status");
    if (!donorModels || !donorModels.available) { status.textContent = donorModels ? donorModels.reason : "Loading…"; return; }
    if (!list.length) { status.textContent = "Choose a fighting style to see the model."; current = null; renderPanel(); return; }
    const base = Math.min(activeBase(), list.length - 1), n = modelKey(base, list[base]);
    status.textContent = typeof n === "string" ? "Loading your own model…" : "Loading the model from your disc…";
    try {
      const model = await loadModel(n);
      const now = Math.min(activeBase(), list.length - 1);
      if (modelKey(now, costumeModels()[now]) !== n) return;   // changed meanwhile
      if (!viewer) viewer = createViewer($("model-canvas"));
      if (!viewer) { status.textContent = "Your browser cannot show 3D (WebGL is off)."; return; }
      if (current !== model) { viewer.setModel(model); current = model; }
      viewer.onPick = onPick;
      repaint(); highlight();
      const shared = model.missing.size ? " Grey areas use shared game palettes and cannot be recoloured yet." : "";
      status.textContent = `Drag to turn, scroll to zoom, double-click to reset, click a part to recolour it.${shared}`;
    } catch (e) { status.textContent = e.message; }
    renderPanel();
  }

  function repaint() {
    if (!viewer || !current) return;
    const v = activeVariant();
    if (v) v.cluts = computeCluts(current, v.recipe || (v.recipe = blankRecipe()));
    viewer.setPalettes(paletteFor(current, v));
  }

  function changed() { repaint(); host.onChange(); }
  function highlight() {
    const part = mode === "parts" && current && current.parts.find((p) => p.key === pickedPart);
    if (viewer) viewer.highlight(part ? part.ids : null);
  }

  function onPick(id) {
    if (id === null || id === undefined || !current) return;
    const part = current.parts.find((p) => p.ids.includes(id));
    if (!part) return;
    // Clicking a donor costume opens its colour variant (made on the spot if there is none yet).
    if (!activeVariant()) {
      const base = activeBase(), i = variants().findIndex((o) => o.base === base);
      if (i >= 0) select("variant", i); else addVariant();
    }
    host.openColours?.();
    pickedPart = part.key;
    mode = "parts";
    renderPanel(); highlight();
    const el = document.querySelector(`[data-part="${part.key}"]`);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "nearest" }); el.classList.add("pulse"); setTimeout(() => el.classList.remove("pulse"), 900); }
  }

  /* -------------------------------------------------------------- panel -- */
  function el(tag, props = {}, ...kids) {
    const { dataset, ...rest } = props;
    const e = Object.assign(document.createElement(tag), rest);
    if (dataset) Object.assign(e.dataset, dataset);
    for (const k of kids) if (k !== null && k !== undefined) e.append(k);
    return e;
  }

  function renderPanel() {
    const box = $("costume-panel");
    if (!box) return;
    box.replaceChildren();
    const list = costumeModels();
    if (!donorModels) { box.append(el("p", { className: "hint", textContent: "Loading…" })); return; }
    if (!donorModels.available) { box.append(el("p", { className: "hint", textContent: donorModels.reason })); return; }
    if (!list.length) { box.append(el("p", { className: "hint", textContent: "Choose a fighting style first." })); return; }

    const tabs = el("div", { className: "costume-tabs", role: "tablist" });
    list.forEach((_, c) => tabs.append(tab(`Costume ${c + 1}`, selected.kind === "costume" && selected.index === c, () => select("costume", c))));
    variants().forEach((v, i) => tabs.append(tab(v.name, selected.kind === "variant" && selected.index === i, () => select("variant", i), "variant")));
    if (variants().length < 8) tabs.append(el("button", { type: "button", className: "costume-tab add", textContent: "+ Colour variant", onclick: addVariant }));
    box.append(tabs);

    const v = activeVariant();
    if (!v) {
      box.append(el("p", { className: "hint", textContent: `The donor's costume ${activeBase() + 1}. Add a colour variant to recolour it; variants are saved with your fighter.` }));
      return;
    }
    const name = el("input", { value: v.name, maxLength: 24, className: "variant-name", oninput: (e) => { v.name = e.target.value || "Variant"; host.onChange(); } });
    const base = el("select", { onchange: (e) => { v.base = Number(e.target.value); v.recipe = blankRecipe();
      if (v.slot >= 0 && v.slot < list.length && v.slot !== v.base) v.slot = -1; current = null; show(); host.onChange(); } });
    list.forEach((_, c) => base.append(el("option", { value: c, textContent: `Based on costume ${c + 1}`, selected: v.base === c })));
    box.append(el("div", { className: "variant-head" }, name, base));
    // In the game: replace one of the donor's costumes, or (two-costume styles) be costume 3 on Start.
    const slotSel = el("select", { onchange: (e) => setSlot(v, Number(e.target.value)) });
    const takenBy = (s) => variants().find((o) => o !== v && o.slot === s);
    const option = (value, label) => slotSel.append(el("option", { value, selected: (v.slot ?? -1) === value,
      textContent: takenBy(value) && value >= 0 ? `${label} (now: ${takenBy(value).name})` : label }));
    option(-1, "Not in the game");
    list.forEach((_, c) => option(c, `Replaces costume ${c + 1}`));
    if (list.length === 2) option(2, "Extra costume 3 (press Start)");
    box.append(el("label", { className: "slot-pick" }, "In the game ", slotSel));

    const modes = el("div", { className: "mode-tabs", role: "tablist" });
    for (const [key, label] of [["parts", "Clothing"], ["whole", "Whole costume"], ["schemes", "Schemes"]])
      modes.append(tab(label, mode === key, () => { mode = key; renderPanel(); highlight(); }));
    box.append(modes);
    if (!current) { box.append(el("p", { className: "hint", textContent: "Loading the model…" })); return; }
    const r = v.recipe || (v.recipe = blankRecipe());

    if (mode === "whole") {
      const slider = (label, key, min, max) => el("label", { className: "slider" }, `${label} `,
        el("input", { type: "range", min, max, value: r.tint[key], oninput: (e) => { r.tint[key] = Number(e.target.value); changed(); } }));
      box.append(slider("Hue", "h", -180, 180), slider("Saturation", "s", 0, 200), slider("Lightness", "l", -40, 40),
        el("label", { className: "check" }, el("input", { type: "checkbox", checked: r.tint.keepSkin, onchange: (e) => { r.tint.keepSkin = e.target.checked; changed(); } }), " Keep skin tones"));
    } else if (mode === "parts") {
      box.append(el("p", { className: "hint", textContent: "Every piece of clothing and accessory has its own palette. Click one here or on the model, "
        + "then give it a colour, or change its colours one by one. A piece named after two body parts is one palette in the game." }));
      const ul = el("ul", { className: "piece-list" });
      const pal = paletteFor(current, v);
      for (const p of current.parts) {
        const open = p.key === pickedPart, mine = r.parts[p.key] || r.parts[Object.keys(r.parts).find((k) => k.split("-").includes(String(p.ids[0])))];
        const orig = rgbToHex(...fromHsl(p.h, p.s, p.l));
        const strip = el("span", { className: "piece-swatches" });
        for (const id of p.ids) {
          const src = current.cluts.get(id);
          pal(id).slice(0, src.length === 256 ? 32 : 16).forEach((c, i) => {
            if (src[i] === 0) return;
            const sw = el("span"); sw.style.background = ps1ToCss(c); strip.append(sw);
          });
        }
        const name = el("button", { type: "button", className: "piece-name", textContent: p.label, ariaExpanded: String(open),
          title: "Show this piece on the model and its colours", onclick: () => { pickedPart = open ? null : p.key; renderPanel(); highlight(); } });
        const input = el("input", { type: "color", value: mine || orig, title: `Colour of ${p.label}`,
          oninput: (e) => { setPieceColour(r, p, e.target.value); changed(); } });
        input.addEventListener("change", () => renderPanel());
        const mineFree = (k) => p.ids.includes(Number(k.split(":")[0]));
        const edited = mine || Object.keys(r.free).some(mineFree);
        const reset = el("button", { type: "button", className: "btn btn-ghost mini", textContent: "Reset",
          onclick: () => { setPieceColour(r, p, null); for (const k of Object.keys(r.free)) if (mineFree(k)) delete r.free[k]; changed(); renderPanel(); } });
        const li = el("li", { className: open ? "picked" : "", dataset: { part: p.key } },
          el("div", { className: "piece-row" }, name, strip, input, edited ? reset : null));
        if (open) {          // its colours one by one, a row per palette
          for (const id of p.ids) {
            const src = current.cluts.get(id), grid = el("div", { className: "piece-colours" });
            pal(id).slice(0, src.length === 256 ? 64 : 16).forEach((c, i) => {
              if (src[i] === 0) return;
              grid.append(el("input", { type: "color", className: "free-cell", value: rgbToHex(...ps1ToRgb(c)), title: `${p.label}, colour ${i + 1}`,
                oninput: (e) => { r.free[`${id}:${i}`] = rgbToPs1(...hexToRgb(e.target.value), src[i] & 0x8000); changed(); } }));
            });
            li.append(grid);
          }
        }
        ul.append(li);
      }
      box.append(ul);
    } else {
      box.append(el("p", { className: "hint", textContent: "A scheme colours the biggest pieces (skin stays). Fine-tune it under Clothing." }));
      const grid = el("div", { className: "scheme-grid" });
      for (const [label, cols] of SCHEMES) {
        const b = el("button", { type: "button", className: "scheme", onclick: () => applyScheme(cols) },
          el("span", { className: "scheme-swatches" }, ...cols.map((c) => { const s = el("span"); s.style.background = c; return s; })), label);
        grid.append(b);
      }
      box.append(grid);
    }
    box.append(el("div", { className: "variant-actions" },
      el("button", { type: "button", className: "btn btn-ghost", textContent: "Reset colours", onclick: () => { v.recipe = blankRecipe(); changed(); renderPanel(); } }),
      el("button", { type: "button", className: "btn btn-danger", textContent: "Delete variant", onclick: deleteVariant })));
  }

  function tab(label, active, onclick, extra = "") {
    return el("button", { type: "button", className: `costume-tab ${extra}`, textContent: label, role: "tab", ariaSelected: String(active), onclick });
  }

  function setPieceColour(r, p, hex) {
    for (const k of Object.keys(r.parts)) if (k.split("-").some((id) => p.ids.includes(Number(id)))) delete r.parts[k];
    if (hex) r.parts[p.key] = hex;
  }

  function applyScheme(cols) {
    const v = activeVariant(); if (!v || !current) return;
    const r = v.recipe || (v.recipe = blankRecipe());
    r.parts = {}; r.free = {}; r.tint = blankRecipe().tint;
    current.parts.filter((p) => !p.skin).sort((a, b) => b.weight - a.weight).forEach((p, i) => { r.parts[p.key] = cols[i % cols.length]; });
    changed(); mode = "parts"; renderPanel(); highlight();
  }

  function setSlot(v, slot) {
    for (const o of variants()) if (o !== v && o.slot === slot) o.slot = -1;   // one variant per slot
    v.slot = slot;
    if (slot >= 0 && slot < costumeModels().length && v.base !== slot) { v.base = slot; v.recipe = blankRecipe(); current = null; show(); }
    renderPanel(); host.onChange();
  }

  function addVariant() {
    const free = costumeModels().length === 2 && !variants().some((o) => o.slot === 2) ? 2 : -1;
    const v = { name: `Colour ${variants().length + 1}`, base: activeBase(), slot: free, recipe: blankRecipe(), cluts: {} };
    variants().push(v);
    select("variant", variants().length - 1);
    host.onChange();
  }
  function deleteVariant() {
    const v = activeVariant(); if (!v || !confirm(`Delete the colour variant "${v.name}"?`)) return;
    variants().splice(selected.index, 1);
    select("costume", Math.min(v.base, Math.max(0, costumeModels().length - 1)));
    host.onChange();
  }
  function select(kind, index) { selected = { kind, index }; pickedPart = null; show(); renderPanel(); highlight(); }

  /* ------------------------------------------------------------ public --- */
  return {
    async init(options) {
      host = options;
      try { donorModels = await (await fetch("/api/models")).json(); }
      catch { donorModels = { available: false, reason: "The builder is not responding." }; }
      renderPanel();
    },
    // a fighter was opened, saved or its style changed
    refresh(keepSelection = false) {
      if (!keepSelection) selected = { kind: "costume", index: 0 };
      current = null; pickedPart = null;
      if (!$("model-view").hidden) show(); else renderPanel();
    },
    showModel() { show(); },
    // what goes into character.json: the recipe (to keep editing) and the resulting palettes
    serialize() { return variants().map((v) => ({ name: v.name, base: v.base, slot: v.slot ?? -1, cluts: v.cluts || {}, recipe: v.recipe || blankRecipe() })); },
  };
})();
