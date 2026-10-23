// Anatomy debug view (Model Importer, for developers): the converter's own reading of the model
// (anatomy.py via /api/model/anatomy) - body region or Tekken row per triangle, uncertain regions
// striped, geometry left out, the joints and skeleton the import uses and the file's own bones.
// Drag to turn, wheel to zoom, double-click to reset. Uses app.js globals: $, api, state, toast.
"use strict";

const T3Anatomy = (() => {
  const VS = `attribute vec3 pos; attribute vec3 col; attribute float flag; uniform mat4 m;
    varying vec3 vCol; varying float vFlag; varying float vDepth;
    void main(){ vec4 p = m * vec4(pos, 1.0); gl_Position = p; vCol = col; vFlag = flag; vDepth = p.z;
      gl_PointSize = 7.0; }`;
  const FS = `precision mediump float; uniform float stripes; uniform float unlit;
    varying vec3 vCol; varying float vFlag; varying float vDepth;
    void main(){
      vec3 c = vCol;
      if (stripes > 0.5 && vFlag > 0.5 && mod(floor((gl_FragCoord.x + gl_FragCoord.y) / 5.0), 2.0) < 1.0) c = vec3(1.0, 0.0, 0.8);
      gl_FragColor = vec4(unlit > 0.5 ? c : c * (0.55 + 0.45 * (0.5 - vDepth)), 1.0); }`;
  let gl, prog, data = null, bufs = {}, counts = {}, yaw = 0, pitch = 0.1, zoom = 1, centre = [0, 0, 0], radius = 1;
  const layers = { mode: "regions", stripes: true, excluded: true, joints: true, bones: false };

  const hex = (h) => [1, 3, 5].map(k => parseInt(h.slice(k, k + 2), 16));
  const rowColour = (r) => r ? [(r * 53) % 255, (r * 97) % 255, (r * 151) % 255] : [60, 60, 60];

  function init() {
    const canvas = $("anatomy-canvas");
    gl = canvas.getContext("webgl", { antialias: true });
    if (!gl) throw new Error("This browser cannot show 3D (WebGL).");
    const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return o; };
    prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    let drag = null;
    canvas.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY]; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      yaw += (e.clientX - drag[0]) * 0.01; pitch = Math.max(-1.5, Math.min(1.5, pitch + (e.clientY - drag[1]) * 0.01));
      drag = [e.clientX, e.clientY]; draw();
    });
    canvas.addEventListener("pointerup", () => { drag = null; });
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); zoom = Math.max(0.3, Math.min(8, zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); draw(); }, { passive: false });
    canvas.addEventListener("dblclick", () => { yaw = 0; pitch = 0.1; zoom = 1; draw(); });
  }

  function put(name, arr, size) {
    if (!bufs[name]) bufs[name] = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, bufs[name]);
    gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW);
    bufs[name].size = size;
  }

  // per-corner arrays of the triangles shown (geometry left out only when its layer is on)
  function build() {
    const P = data.P, T = data.T, reg = data.region, row = data.row, uns = data.uncertain;
    const excl = data.regions.findIndex(r => r.name === "excluded");
    const pal = data.regions.map(r => hex(r.colour));
    const keep = [];
    for (let i = 0; i < T.length; i++) if (layers.excluded || reg[i] !== excl) keep.push(i);
    const pos = new Float32Array(keep.length * 9), col = new Float32Array(keep.length * 9), flag = new Float32Array(keep.length * 3);
    keep.forEach((i, n) => {
      const c = layers.mode === "rows" ? rowColour(row[i]) : pal[reg[i]];
      for (let k = 0; k < 3; k++) {
        const p = P[T[i][k]];
        pos.set(p, n * 9 + k * 3);
        col.set([c[0] / 255, c[1] / 255, c[2] / 255], n * 9 + k * 3);
        flag[n * 3 + k] = uns[i];
      }
    });
    put("pos", pos, 3); put("col", col, 3); put("flag", flag, 1);
    counts.tri = keep.length * 3;
    // joints and skeleton (white lines, points), the file's bones (cyan) on top
    const lp = [], lc = [];
    const line = (a, b, c) => { lp.push(...a, ...b); lc.push(...c, ...c); };
    if (layers.joints) for (const [a, b] of data.links) line(data.joints[a], data.joints[b], [1, 1, 1]);
    if (layers.bones) for (const b of data.bones) if (b.parent >= 0) line(data.bones[b.parent].at, b.at, [0.2, 0.9, 1]);
    put("lpos", new Float32Array(lp), 3); put("lcol", new Float32Array(lc), 3); put("lflag", new Float32Array(lp.length / 3), 1);
    counts.line = lp.length / 3;
    const pp = layers.joints ? Object.values(data.joints).flat() : [];
    put("ppos", new Float32Array(pp), 3); put("pcol", new Float32Array(pp.length).fill(1), 3); put("pflag", new Float32Array(pp.length / 3), 1);
    counts.point = pp.length / 3;
  }

  function matrix() {
    const canvas = $("anatomy-canvas");
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const R = [cy, 0, sy, sp * sy, cp, -sp * cy, -cp * sy, sp, cp * cy];
    const s = zoom / (radius * 1.1), aspect = canvas.width / canvas.height;
    const sx = aspect >= 1 ? s / aspect : s, syy = aspect >= 1 ? s : s * aspect, zs = -0.5 / radius;
    const t = [-centre[0], -centre[1], -centre[2]];
    const tx = (R[0] * t[0] + R[1] * t[1] + R[2] * t[2]), ty = (R[3] * t[0] + R[4] * t[1] + R[5] * t[2]), tz = (R[6] * t[0] + R[7] * t[1] + R[8] * t[2]);
    return new Float32Array([R[0] * sx, R[3] * syy, R[6] * zs, 0, R[1] * sx, R[4] * syy, R[7] * zs, 0,
                             R[2] * sx, R[5] * syy, R[8] * zs, 0, tx * sx, ty * syy, tz * zs, 1]);
  }

  function draw() {
    if (!gl || !data) return;
    const canvas = $("anatomy-canvas"), r = canvas.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    const W = Math.max(1, Math.round(r.width * dpr)), H = Math.max(1, Math.round(r.height * dpr));
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    gl.viewport(0, 0, W, H);
    gl.clearColor(0.09, 0.1, 0.14, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(prog);
    gl.uniformMatrix4fv(gl.getUniformLocation(prog, "m"), false, matrix());
    const pass = (p, c, f, mode, n, stripes, flat, depth) => {
      if (!n) return;
      for (const [name, b] of [["pos", p], ["col", c], ["flag", f]]) {
        const loc = gl.getAttribLocation(prog, name);
        gl.bindBuffer(gl.ARRAY_BUFFER, bufs[b]); gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, bufs[b].size, gl.FLOAT, false, 0, 0);
      }
      gl.uniform1f(gl.getUniformLocation(prog, "stripes"), stripes ? 1 : 0);
      gl.uniform1f(gl.getUniformLocation(prog, "unlit"), flat ? 1 : 0);
      if (depth) gl.enable(gl.DEPTH_TEST); else gl.disable(gl.DEPTH_TEST);
      gl.drawArrays(mode, 0, n);
    };
    pass("pos", "col", "flag", gl.TRIANGLES, counts.tri, layers.stripes, false, true);
    pass("lpos", "lcol", "lflag", gl.LINES, counts.line, false, true, false);       // the skeleton shows through
    pass("ppos", "pcol", "pflag", gl.POINTS, counts.point, false, true, false);
  }

  function legend() {
    const box = $("anatomy-legend");
    box.replaceChildren();
    if (layers.mode === "regions") {
      data.regions.forEach((r, k) => {
        const n = data.counts[r.name] || 0;
        if (!n) return;
        const li = document.createElement("li");
        li.innerHTML = `<span class="swatch" style="background:${r.colour}"></span>`;
        li.append(`${r.name} (${n})`);
        box.append(li);
      });
    } else {
      const seen = [...new Set(data.row)].sort((a, b) => a - b);
      for (const r of seen) {
        const li = document.createElement("li"), c = rowColour(r);
        li.innerHTML = `<span class="swatch" style="background:rgb(${c.join(",")})"></span>`;
        li.append(r ? `row ${r}` : "no row");
        box.append(li);
      }
    }
    const flags = $("anatomy-flags");
    flags.replaceChildren(...(data.flags.length ? data.flags : ["No uncertain body parts found."]).map(t => {
      const li = document.createElement("li"); li.textContent = t; return li; }));
    $("anatomy-note").textContent = (data.auto_rig ? "Automatic rig" : "Skeleton from the file") +
      ` · ${data.which === "upload" ? "the uploaded model" : "the imported source"} · ${data.T.length} triangles`;
  }

  async function show() {
    if (!state.current || !state.current.id) return;
    $("anatomy-status").textContent = "Reading the model…";
    try {
      data = await api("/api/model/anatomy", { id: state.current.id });
      if (!gl) init();
      const P = data.P, lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
      for (const p of P) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], p[k]); hi[k] = Math.max(hi[k], p[k]); }
      centre = lo.map((v, k) => (v + hi[k]) / 2);
      radius = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2 || 1;
      build(); legend(); draw();
      $("anatomy-status").textContent = "Drag to turn, scroll to zoom, double-click to reset. Striped: uncertain.";
    } catch (e) { $("anatomy-status").textContent = e.message || String(e); }
  }

  for (const id of ["anatomy-mode", "anatomy-stripes", "anatomy-excluded", "anatomy-joints", "anatomy-bones"]) {
    $(id).addEventListener("change", () => {
      layers.mode = $("anatomy-mode").value;
      layers.stripes = $("anatomy-stripes").checked; layers.excluded = $("anatomy-excluded").checked;
      layers.joints = $("anatomy-joints").checked; layers.bones = $("anatomy-bones").checked;
      if (data) { build(); legend(); draw(); }
    });
  }
  $("anatomy-box").addEventListener("toggle", () => { if ($("anatomy-box").open) show(); });
  return { show, reset: () => { data = null; if ($("anatomy-box").open) show(); } };
})();
