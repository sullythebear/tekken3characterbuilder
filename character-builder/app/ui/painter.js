// Painter (Model Importer): colours painted on an uploaded model, for the many 3D files that come
// without colours (or with the wrong ones). The model is shown in 3D with every triangle in its
// own colour; a brush, a fill bucket and a colour picker paint whole triangles (the PS1 look),
// on both sides at once if wanted. Saved as runs of triangles per colour (colours-upload.json);
// the import bakes them like any texture. Uses app.js globals: $, api, state, toast.
"use strict";

const T3Paint = (() => {
  const PRESETS = [
    ["#f2c9a0", "Light skin"], ["#d9a066", "Tan skin"], ["#a86b3c", "Brown skin"], ["#6b4226", "Dark skin"],
    ["#1a1a1a", "Black hair"], ["#5a3a1a", "Brown hair"], ["#d8b25a", "Blond hair"], ["#a8321e", "Red hair"],
    ["#ffffff", "White"], ["#8c8c8c", "Grey"], ["#3a3a3a", "Dark grey"], ["#c81e1e", "Red"],
    ["#1e4fc8", "Blue"], ["#1e8c3a", "Green"], ["#e8c81e", "Yellow"], ["#7a2ea8", "Purple"],
    ["#e8781e", "Orange"], ["#d84f9a", "Pink"], ["#2a1a5a", "Navy"], ["#c8a878", "Khaki"],
  ];
  const TOOLS = { brush: "Paint", fill: "Fill a piece", part: "Colour a whole body part", pick: "Pick a colour", turn: "Turn" };

  let info = null, onInfo = null, mesh = null, gl = null, prog = null, idProg = null, fbo = null;
  let buffers = {}, idDirty = true, nT = 0;
  let base = null;            // Uint8Array nT*3: the file's own colour per triangle
  let painted = null;         // Int16Array nT: palette index per triangle, -1 = the file's own
  let palette = [];           // the colours used, "#rrggbb"
  let colour = "#c81e1e", tool = "brush", mirror = true, size = 10;
  let yaw = 0, pitch = 0.15, zoom = 1, pan = [0, 0];
  let centre = [0, 0, 0], radius = 1;
  let undo = [], redo = [], stroke = null, changed = false, drag = null;
  let adjacency = null, mirrorMap = null, cornerColour = null, faceNormal = null, creases = false;
  let parts = null, partNames = [];   // every triangle's body part (index into partNames, -1 = none)

  // ------------------------------------------------------------------ the model
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0)).buffer;
  const hex = (r, g, b) => "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
  const rgbOf = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));

  function loadMesh(data) {
    const P = new Float32Array(b64(data.positions));
    const T = new Uint32Array(b64(data.triangles));
    base = new Uint8Array(b64(data.colours));
    parts = data.parts ? new Int8Array(b64(data.parts)) : null;
    partNames = data.part_names || [];
    nT = data.count;
    mesh = { P, T };
    painted = new Int16Array(nT).fill(-1);
    palette = (data.paint && data.paint.colours) || [];
    for (const [start, count, ci] of (data.paint && data.paint.runs) || []) {
      for (let f = start; f < Math.min(nT, start + count); f++) painted[f] = ci;
    }
    let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < P.length; i += 3) {
      for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], P[i + k]); hi[k] = Math.max(hi[k], P[i + k]); }
    }
    centre = lo.map((v, k) => (v + hi[k]) / 2);
    radius = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2 || 1;
    adjacency = mirrorMap = null;
    undo = []; redo = []; changed = false;
    upload();
  }

  // every triangle's three corners on their own (flat colour and normal per triangle)
  function upload() {
    const { P, T } = mesh;
    const pos = new Float32Array(nT * 9), nrm = new Float32Array(nT * 9), ids = new Uint8Array(nT * 9);
    cornerColour = new Uint8Array(nT * 9);
    faceNormal = new Float32Array(nT * 3);
    for (let f = 0; f < nT; f++) {
      const a = T[3 * f] * 3, b = T[3 * f + 1] * 3, c = T[3 * f + 2] * 3;
      const e1 = [P[b] - P[a], P[b + 1] - P[a + 1], P[b + 2] - P[a + 2]];
      const e2 = [P[c] - P[a], P[c + 1] - P[a + 1], P[c + 2] - P[a + 2]];
      let n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
      const l = Math.hypot(...n) || 1;
      n = n.map((v) => v / l);
      faceNormal.set(n, 3 * f);
      const id = f + 1;
      [a, b, c].forEach((v, k) => {
        const o = f * 9 + k * 3;
        pos[o] = P[v] - centre[0]; pos[o + 1] = P[v + 1] - centre[1]; pos[o + 2] = P[v + 2] - centre[2];
        nrm[o] = n[0]; nrm[o + 1] = n[1]; nrm[o + 2] = n[2];
        ids[o] = id & 255; ids[o + 1] = (id >> 8) & 255; ids[o + 2] = (id >> 16) & 255;
      });
      setCorner(f);
    }
    const put = (name, data) => {
      if (!buffers[name]) buffers[name] = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers[name]);
      gl.bufferData(gl.ARRAY_BUFFER, data, name === "colour" ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW);
    };
    put("pos", pos); put("nrm", nrm); put("id", ids); put("colour", cornerColour);
    idDirty = true;
  }

  function faceRGB(f) {
    const ci = painted[f];
    return ci >= 0 ? rgbOf(palette[ci]) : [base[3 * f], base[3 * f + 1], base[3 * f + 2]];
  }
  function setCorner(f) {
    const c = faceRGB(f);
    for (let k = 0; k < 3; k++) cornerColour.set(c, f * 9 + k * 3);
  }

  // ------------------------------------------------------------------ WebGL
  const VS = `attribute vec3 pos; attribute vec3 nrm; attribute vec3 col; uniform mat4 m; uniform mat3 r;
    varying vec3 v_col; varying vec3 v_n;
    void main() { gl_Position = m * vec4(pos, 1.0); v_col = col; v_n = r * nrm; }`;
  const FS = `precision mediump float; varying vec3 v_col; varying vec3 v_n;
    void main() { float l = 0.55 + 0.45 * abs(normalize(v_n).z); gl_FragColor = vec4(v_col * l, 1.0); }`;
  const ID_FS = `precision mediump float; varying vec3 v_col; varying vec3 v_n;
    void main() { gl_FragColor = vec4(v_col, 1.0); }`;

  function compile(vs, fs) {
    const p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      gl.attachShader(p, s);
    }
    gl.linkProgram(p);
    return p;
  }

  function initGL() {
    const canvas = $("paint-canvas");
    gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: false });
    if (!gl) throw new Error("This browser cannot show 3D (WebGL).");
    prog = compile(VS, FS);
    idProg = compile(VS, ID_FS);
    buffers = {};
  }

  function matrices() {
    const canvas = $("paint-canvas");
    const aspect = canvas.width / canvas.height;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    // rotation: yaw about Y, then pitch about X (rows)
    const R = [cy, 0, sy, sp * sy, cp, -sp * cy, -cp * sy, sp, cp * cy];
    const s = zoom / (radius * 1.1);
    const sx = aspect >= 1 ? s / aspect : s, syy = aspect >= 1 ? s : s * aspect;
    const zs = -0.5 / radius;
    // column-major 4x4: ortho of the rotated model, panned
    const m = new Float32Array([
      R[0] * sx, R[3] * syy, R[6] * zs, 0,
      R[1] * sx, R[4] * syy, R[7] * zs, 0,
      R[2] * sx, R[5] * syy, R[8] * zs, 0,
      pan[0], pan[1], 0, 1]);
    const r = new Float32Array([R[0], R[3], R[6], R[1], R[4], R[7], R[2], R[5], R[8]]);
    return { m, r };
  }

  function bind(p, colourBuffer) {
    gl.useProgram(p);
    const attr = (name, buffer, size, type, norm) => {
      const loc = gl.getAttribLocation(p, name);
      if (loc < 0) return;
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, type, norm, 0, 0);
    };
    attr("pos", buffers.pos, 3, gl.FLOAT, false);
    attr("nrm", buffers.nrm, 3, gl.FLOAT, false);
    attr("col", colourBuffer, 3, gl.UNSIGNED_BYTE, true);
    const { m, r } = matrices();
    gl.uniformMatrix4fv(gl.getUniformLocation(p, "m"), false, m);
    gl.uniformMatrix3fv(gl.getUniformLocation(p, "r"), false, r);
  }

  let frameQueued = false;
  function draw() {
    if (frameQueued) return;
    frameQueued = true;
    requestAnimationFrame(() => {
      frameQueued = false;
      if (!gl || !mesh) return;
      const canvas = $("paint-canvas");
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0.11, 0.11, 0.14, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      bind(prog, buffers.colour);
      gl.drawArrays(gl.TRIANGLES, 0, nT * 3);
    });
  }

  // which triangle is under each pixel: the model drawn once more with its triangle numbers as colours
  function idPass() {
    const canvas = $("paint-canvas");
    if (!fbo || fbo.w !== canvas.width || fbo.h !== canvas.height) {
      if (fbo) { gl.deleteFramebuffer(fbo.fb); gl.deleteTexture(fbo.tex); gl.deleteRenderbuffer(fbo.depth); }
      const fb = gl.createFramebuffer(), tex = gl.createTexture(), depth = gl.createRenderbuffer();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, canvas.width, canvas.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.bindRenderbuffer(gl.RENDERBUFFER, depth);
      gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, canvas.width, canvas.height);
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depth);
      fbo = { fb, tex, depth, w: canvas.width, h: canvas.height };
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.fb);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    bind(idProg, buffers.id);
    gl.drawArrays(gl.TRIANGLES, 0, nT * 3);
    idDirty = false;
  }

  // the triangles seen within r device pixels of (x, y)
  function facesAt(x, y, r) {
    if (idDirty) idPass();
    const canvas = $("paint-canvas");
    const x0 = Math.max(0, Math.floor(x - r)), y0 = Math.max(0, Math.floor(y - r));
    const x1 = Math.min(canvas.width - 1, Math.ceil(x + r)), y1 = Math.min(canvas.height - 1, Math.ceil(y + r));
    if (x1 < x0 || y1 < y0) return [];
    const w = x1 - x0 + 1, h = y1 - y0 + 1;
    const px = new Uint8Array(w * h * 4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo.fb);
    gl.readPixels(x0, canvas.height - 1 - y1, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    const out = new Set();
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const gx = x0 + i, gy = y1 - j;               // readPixels rows start at the bottom
        if ((gx - x) ** 2 + (gy - y) ** 2 > r * r) continue;
        const o = (j * w + i) * 4;
        const id = px[o] | (px[o + 1] << 8) | (px[o + 2] << 16);
        if (id) out.add(id - 1);
      }
    }
    return [...out];
  }

  // ------------------------------------------------------------------ painting
  function paletteIndex(h) {
    let i = palette.indexOf(h);
    if (i < 0) { palette.push(h); i = palette.length - 1; }
    return i;
  }

  // the triangle on the other side (mirrored left-right), by the nearest middle point
  function mirrorFaces() {
    if (mirrorMap) return mirrorMap;
    const { P, T } = mesh;
    const mid = new Float32Array(nT * 3);
    for (let f = 0; f < nT; f++) {
      for (let k = 0; k < 3; k++) {
        mid[3 * f + k] = (P[T[3 * f] * 3 + k] + P[T[3 * f + 1] * 3 + k] + P[T[3 * f + 2] * 3 + k]) / 3;
      }
    }
    const cell = radius / 40, grid = new Map();
    const key = (x, y, z) => `${Math.floor(x / cell)},${Math.floor(y / cell)},${Math.floor(z / cell)}`;
    for (let f = 0; f < nT; f++) {
      const k = key(mid[3 * f], mid[3 * f + 1], mid[3 * f + 2]);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push(f);
    }
    mirrorMap = new Int32Array(nT).fill(-1);
    for (let f = 0; f < nT; f++) {
      const x = 2 * centre[0] - mid[3 * f], y = mid[3 * f + 1], z = mid[3 * f + 2];
      const gx = Math.floor(x / cell), gy = Math.floor(y / cell), gz = Math.floor(z / cell);
      let best = -1, bd = (cell * 1.5) ** 2;
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        for (const g of grid.get(`${gx + dx},${gy + dy},${gz + dz}`) || []) {
          const d = (mid[3 * g] - x) ** 2 + (mid[3 * g + 1] - y) ** 2 + (mid[3 * g + 2] - z) ** 2;
          if (d < bd) { bd = d; best = g; }
        }
      }
      mirrorMap[f] = best;
    }
    return mirrorMap;
  }

  // triangles sharing an edge (corners at the same place count as one)
  function neighbours() {
    if (adjacency) return adjacency;
    const { P, T } = mesh;
    const weld = new Map(), id = new Int32Array(P.length / 3);
    for (let v = 0; v < id.length; v++) {
      const k = `${P[3 * v].toFixed(5)},${P[3 * v + 1].toFixed(5)},${P[3 * v + 2].toFixed(5)}`;
      if (!weld.has(k)) weld.set(k, weld.size);
      id[v] = weld.get(k);
    }
    const edges = new Map();
    adjacency = Array.from({ length: nT }, () => []);
    for (let f = 0; f < nT; f++) {
      for (let k = 0; k < 3; k++) {
        const a = id[T[3 * f + k]], b = id[T[3 * f + (k + 1) % 3]];
        const e = a < b ? `${a},${b}` : `${b},${a}`;
        const other = edges.get(e);
        if (other === undefined) edges.set(e, [f]);
        else { for (const g of other) { adjacency[f].push(g); adjacency[g].push(f); } other.push(f); }
      }
    }
    return adjacency;
  }

  function setFace(f, ci) {
    if (f < 0 || painted[f] === ci) return;
    stroke.push([f, painted[f]]);
    painted[f] = ci;
    setCorner(f);
  }

  function paintFaces(faces) {
    const ci = paletteIndex(colour);
    const mm = mirror ? mirrorFaces() : null;
    for (const f of faces) {
      setFace(f, ci);
      if (mm) setFace(mm[f], ci);
    }
    pushColours();
  }

  // the connected piece of (about) the same colour as the triangle clicked
  function fill(start) {
    const adj = neighbours();
    const c0 = faceRGB(start);
    const near = (f) => { const c = faceRGB(f); return Math.abs(c[0] - c0[0]) + Math.abs(c[1] - c0[1]) + Math.abs(c[2] - c0[2]) <= 24; };
    // stop at sharp edges (if wanted): neighbours turned more than 50 degrees
    const flat = (f, g) => !creases || faceNormal[3 * f] * faceNormal[3 * g] + faceNormal[3 * f + 1] * faceNormal[3 * g + 1]
      + faceNormal[3 * f + 2] * faceNormal[3 * g + 2] > 0.64;
    const seen = new Uint8Array(nT), todo = [start], out = [];
    seen[start] = 1;
    while (todo.length) {
      const f = todo.pop();
      out.push(f);
      for (const g of adj[f]) if (!seen[g] && near(g) && flat(f, g)) { seen[g] = 1; todo.push(g); }
    }
    return out;
  }

  // every triangle of the body part clicked (the skeleton's: head, upper arm, thigh, ...)
  function wholePart(start) {
    if (!parts || parts[start] < 0) return fill(start);
    const want = new Set([parts[start]]);
    if (mirror) {
      const name = partNames[parts[start]];
      const other = name.endsWith("L") ? name.slice(0, -1) + "R" : name.endsWith("R") ? name.slice(0, -1) + "L" : null;
      if (other && partNames.includes(other)) want.add(partNames.indexOf(other));
    }
    const out = [];
    for (let f = 0; f < nT; f++) if (want.has(parts[f])) out.push(f);
    return out;
  }

  function pushColours() {
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.colour);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, cornerColour);
    changed = true;
    showState();
    draw();
  }

  function endStroke() {
    if (stroke && stroke.length) { undo.push(stroke); redo = []; }
    stroke = null;
    showState();
  }

  function step(from, to) {
    const s = from.pop();
    if (!s) return;
    const back = [];
    for (let i = s.length - 1; i >= 0; i--) {
      const [f, old] = s[i];
      back.push([f, painted[f]]);
      painted[f] = old;
      setCorner(f);
    }
    to.push(back);
    pushColours();
  }

  // ------------------------------------------------------------------ pointer
  function pointer(e) {
    const canvas = $("paint-canvas"), r = canvas.getBoundingClientRect();
    const k = canvas.width / r.width;
    return [(e.clientX - r.left) * k, (e.clientY - r.top) * k, k];
  }

  function onDown(e) {
    if (!mesh) return;
    e.preventDefault();
    const [x, y, k] = pointer(e);
    const turning = tool === "turn" || e.button === 2 || e.shiftKey;
    $("paint-canvas").setPointerCapture(e.pointerId);
    if (turning) {
      drag = { x: e.clientX, y: e.clientY, yaw, pitch, pan: [...pan], panning: e.shiftKey || e.button === 1 };
      return;
    }
    const hit = facesAt(x, y, tool === "brush" ? size * k : 1);
    if (tool === "pick") {
      if (hit.length) setColour(hex(...faceRGB(hit[0])));
      return;
    }
    stroke = [];
    if (tool === "fill" || tool === "part") {
      if (hit.length) paintFaces(tool === "fill" ? fill(hit[0]) : wholePart(hit[0]));
      endStroke();
      return;
    }
    drag = { painting: true };
    paintFaces(hit);
  }

  function onMove(e) {
    if (!mesh) return;
    const [x, y, k] = pointer(e);
    showBrush(e);
    if (!drag) return;
    if (drag.painting) {
      paintFaces(facesAt(x, y, size * k));
      return;
    }
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (drag.panning) {
      const w = $("paint-canvas").getBoundingClientRect();
      pan = [drag.pan[0] + 2 * dx / w.width, drag.pan[1] - 2 * dy / w.height];
    } else {
      yaw = drag.yaw + dx * 0.01;
      pitch = Math.max(-1.5, Math.min(1.5, drag.pitch + dy * 0.01));
    }
    idDirty = true;
    draw();
  }

  function onUp() {
    if (drag && drag.painting) endStroke();
    drag = null;
  }

  function onWheel(e) {
    if (!mesh) return;
    e.preventDefault();
    const canvas = $("paint-canvas"), r = canvas.getBoundingClientRect();
    // zoom towards the pointer: the point under it stays put
    const nx = ((e.clientX - r.left) / r.width) * 2 - 1, ny = 1 - ((e.clientY - r.top) / r.height) * 2;
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const z = Math.max(0.5, Math.min(12, zoom * f));
    const g = z / zoom;
    pan = [nx - (nx - pan[0]) * g, ny - (ny - pan[1]) * g];
    zoom = z;
    idDirty = true;
    draw();
  }

  function showBrush(e) {
    const ring = $("paint-ring"), canvas = $("paint-canvas");
    const show = tool === "brush" && e && e.type !== "pointerleave";
    ring.hidden = !show;
    if (!show) return;
    const box = canvas.parentElement.getBoundingClientRect();
    ring.style.width = ring.style.height = `${2 * size}px`;
    ring.style.left = `${e.clientX - box.left - size}px`;
    ring.style.top = `${e.clientY - box.top - size}px`;
    ring.style.borderColor = colour;
  }

  // ------------------------------------------------------------------ panel
  function setColour(h) {
    colour = h.toLowerCase();
    $("paint-colour").value = colour;
    $("paint-current").style.background = colour;
    for (const b of $("paint-palette").children) b.classList.toggle("on", b.dataset.colour === colour);
  }

  function setTool(t) {
    tool = t;
    for (const b of document.querySelectorAll("#paint-tools button")) b.classList.toggle("on", b.dataset.tool === t);
    $("paint-canvas").style.cursor = t === "turn" ? "grab" : t === "pick" ? "copy" : "crosshair";
    // the brush size and the fill's edge stop share one place, so the panel does not jump
    $("paint-size-row").hidden = t === "fill";
    $("paint-size-row").style.visibility = t === "brush" ? "visible" : "hidden";
    $("paint-creases-row").hidden = t !== "fill";
  }

  function view(y, p) { yaw = y; pitch = p; zoom = 1; pan = [0, 0]; idDirty = true; draw(); }

  function runs() {
    // compact: [first triangle, count, colour] for every stretch of one painted colour;
    // colours no triangle uses any more are left out
    const used = new Map(), out = [], colours = [];
    let f = 0;
    while (f < nT) {
      const ci = painted[f];
      let e = f + 1;
      while (e < nT && painted[e] === ci) e++;
      if (ci >= 0) {
        if (!used.has(ci)) { used.set(ci, colours.length); colours.push(palette[ci]); }
        out.push([f, e - f, used.get(ci)]);
      }
      f = e;
    }
    return { colours, runs: out };
  }

  function count() { let n = 0; for (let f = 0; f < nT; f++) if (painted[f] >= 0) n++; return n; }

  function showState() {
    const n = painted ? count() : 0;
    $("paint-status").textContent = !mesh ? "" : changed ? `${n} triangles painted: press Use these colours to keep them`
      : n ? `${n} triangles painted` : "Nothing painted yet";
    $("paint-apply").disabled = !changed;
    $("paint-undo").disabled = !undo.length;
    $("paint-redo").disabled = !redo.length;
  }

  async function open() {
    $("paint-editor").hidden = false;
    $("paint-open").hidden = true;
    $("paint-status").textContent = "Reading the model…";
    try {
      if (!gl) initGL();
      sizeCanvas();
      loadMesh(await api("/api/model/colour-mesh", { id: info.id }));
      view(0, 0.15);
      showState();
    } catch (error) {
      $("paint-status").textContent = "";
      toast(error.message);
      close();
    }
  }

  function close() {
    $("paint-editor").hidden = true;
    $("paint-open").hidden = false;
  }

  function sizeCanvas() {
    const canvas = $("paint-canvas"), r = canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round((r.width || 520) * dpr), h = Math.round((r.height || 440) * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; idDirty = true; }
  }

  async function apply(paint, message) {
    $("paint-status").textContent = message;
    $("paint-apply").disabled = true;
    try {
      const fresh = await api("/api/model/colours", { id: info.id, paint });
      changed = false;
      if (onInfo) onInfo(fresh);
      toast(paint ? "Colours kept: the import uses them." : "Painting cleared: the file's own colours again.");
    } catch (error) {
      toast(error.message);
    }
    showState();
  }

  function show(fresh, onFresh) {
    onInfo = onFresh;
    const box = $("paint-view");
    box.hidden = !fresh || !fresh.ok;
    if (box.hidden) { info = null; return; }
    const id = state.current && state.current.id;
    const same = info && info.id === id && info.file === fresh.file;
    info = { ...fresh, id };
    $("paint-summary").textContent = fresh.painted ? `${fresh.painted} triangles painted by hand.`
      : fresh.colourless ? "This file has no colours of its own: paint it here." : "Change or add colours by painting on the model.";
    if (!same) { mesh = null; close(); }
  }

  function init() {
    if (!$("paint-view")) return;
    const pal = $("paint-palette");
    for (const [c, name] of PRESETS) {
      const b = document.createElement("button");
      b.type = "button"; b.title = name; b.dataset.colour = c; b.style.background = c;
      b.addEventListener("click", () => setColour(c));
      pal.append(b);
    }
    for (const [key, label] of Object.entries(TOOLS)) {
      const b = $("paint-tools").querySelector(`[data-tool="${key}"]`);
      if (b) { b.title = label; b.addEventListener("click", () => setTool(key)); }
    }
    $("paint-colour").addEventListener("input", (e) => setColour(e.target.value));
    $("paint-size").addEventListener("input", (e) => { size = Number(e.target.value); });
    $("paint-mirror").addEventListener("change", (e) => { mirror = e.target.checked; });
    $("paint-creases").addEventListener("change", (e) => { creases = e.target.checked; });
    const canvas = $("paint-canvas");
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("pointerleave", (e) => showBrush(e));
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    $("paint-open").addEventListener("click", open);
    $("paint-close").addEventListener("click", close);
    $("paint-undo").addEventListener("click", () => step(undo, redo));
    $("paint-redo").addEventListener("click", () => step(redo, undo));
    $("paint-front").addEventListener("click", () => view(0, 0.15));
    $("paint-back").addEventListener("click", () => view(Math.PI, 0.15));
    $("paint-left").addEventListener("click", () => view(-Math.PI / 2, 0.15));
    $("paint-right").addEventListener("click", () => view(Math.PI / 2, 0.15));
    $("paint-apply").addEventListener("click", () => {
      const r = runs();
      apply(r.runs.length ? r : null, "Saving the colours…");
    });
    $("paint-clear").addEventListener("click", () => {
      if (!mesh) return;
      stroke = [];
      for (let f = 0; f < nT; f++) setFace(f, -1);
      endStroke();
      pushColours();
    });
    window.addEventListener("resize", () => { if (mesh) { sizeCanvas(); draw(); } });
    setColour(colour);
    setTool("brush");
  }

  return { init, show };
})();

T3Paint.init();
