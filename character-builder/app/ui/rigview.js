// Rig view (Model Importer): a model without a skeleton of its own is rigged automatically
// (autorig.py); here the player sees that skeleton over the model from the front and the side,
// drags joints that are off, turns a model that lies or faces away, and tries a pose to see each
// part move with its bone. Uses app.js globals: $, api, state, toast.
"use strict";

const T3Rig = (() => {
  // the joints a player can place, with a name and a colour per body region
  const JOINTS = {
    neck: ["Head (base of the skull)", "#ffd84a"], hips: ["Hips", "#b06cff"],
    upperL: ["Left shoulder", "#ff5a5a"], upperR: ["Right shoulder", "#ff5a5a"],
    foreL: ["Left elbow", "#ff9a3c"], foreR: ["Right elbow", "#ff9a3c"],
    handL: ["Left wrist", "#ffe7b0"], handR: ["Right wrist", "#ffe7b0"],
    handendL: ["Left fingertips", "#fff6dc"], handendR: ["Right fingertips", "#fff6dc"],
    thighL: ["Left hip joint", "#4fd06a"], thighR: ["Right hip joint", "#4fd06a"],
    shinL: ["Left knee", "#2fa04a"], shinR: ["Right knee", "#2fa04a"],
    footL: ["Left ankle", "#c8c8c8"], footR: ["Right ankle", "#c8c8c8"],
    toeL: ["Left toes", "#e8e8e8"], toeR: ["Right toes", "#e8e8e8"],
  };
  const PART_COLOUR = { head: "#ffd84a", spine: "#6a78ff", pelvis: "#b06cff", collar: "#4fd6e6", upper: "#ff5a5a",
    fore: "#ff9a3c", hand: "#ffe7b0", thigh: "#4fd06a", shin: "#2fa04a", foot: "#c8c8c8" };
  const BONES = [["hips", "chest"], ["chest", "neck"], ["neck", "top"], ["chest", "upperL"], ["chest", "upperR"],
    ["upperL", "foreL"], ["foreL", "handL"], ["handL", "handendL"], ["upperR", "foreR"], ["foreR", "handR"],
    ["handR", "handendR"], ["hips", "thighL"], ["hips", "thighR"], ["thighL", "shinL"], ["shinL", "footL"],
    ["footL", "toeL"], ["thighR", "shinR"], ["shinR", "footR"], ["footR", "toeR"]];
  const mirrorOf = (k) => (k.endsWith("L") ? k.slice(0, -1) + "R" : k.endsWith("R") ? k.slice(0, -1) + "L" : null);

  let rig = null, joints = {}, changed = false, onInfo = null, drag = null, hover = null;
  let posing = false, poseStart = 0, frame = 0;
  // painting body parts: the strokes kept ([x, y, z, part]) and the part on the brush
  let painting = false, strokes = [], brushPart = "pelvis", brushDown = false, movedJoints = false;
  const PAINT = [["head", "Head"], ["spine", "Chest"], ["pelvis", "Hips"], ["collarL", "L collar"], ["collarR", "R collar"],
    ["upperL", "L upper arm"], ["upperR", "R upper arm"], ["foreL", "L forearm"], ["foreR", "R forearm"],
    ["handL", "L hand"], ["handR", "R hand"], ["thighL", "L thigh"], ["thighR", "R thigh"], ["shinL", "L shin"],
    ["shinR", "R shin"], ["footL", "L foot"], ["footR", "R foot"]];
  const views = [{ id: "rig-front", ax: 0 }, { id: "rig-side", ax: 2 }];   // x or z across, y up

  // world <-> canvas: one scale for both views, from the model's height
  function frameOf(canvas, ax) {
    const pts = ax === 0 ? rig.front : rig.side;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const [a, b] of pts) { x0 = Math.min(x0, a); x1 = Math.max(x1, a); y0 = Math.min(y0, b); y1 = Math.max(y1, b); }
    const all = [...rig.front, ...rig.side];
    const H = Math.max(y1 - y0, 1e-6), W = Math.max(...all.map((p) => p[0])) - Math.min(...all.map((p) => p[0]));
    const s = Math.min((canvas.height - 30) / H, (canvas.width - 20) / Math.max(W, 1e-6));
    const cx = (x0 + x1) / 2;
    return { to: (a, b) => [canvas.width / 2 + (a - cx) * s, canvas.height - 14 - (b - y0) * s],
             from: (px, py) => [cx + (px - canvas.width / 2) / s, y0 + (canvas.height - 14 - py) / s] };
  }

  const withExtras = (J) => {
    const out = { ...J };
    const top = Math.max(...rig.front.map((p) => p[1]));
    out.top = [J.neck[0], top, J.neck[2]];
    out.chest = [(J.upperL[0] + J.upperR[0]) / 2, (J.upperL[1] + J.upperR[1]) / 2, (J.upperL[2] + J.upperR[2]) / 2];
    return out;
  };

  // ---------------------------------------------------------------- try a pose (forward kinematics)
  // chains: each body part turns around its joint, carrying the parts below it
  const CHAINS = [
    { parts: ["upperL", "foreL", "handL"], pivots: ["upperL", "foreL", "handL"], front: [1, 0.6, 0.2], side: [0.8, 0.9, 0.2] },
    { parts: ["upperR", "foreR", "handR"], pivots: ["upperR", "foreR", "handR"], front: [-1, -0.6, -0.2], side: [-0.8, 0.9, 0.2] },
    { parts: ["thighL", "shinL", "footL"], pivots: ["thighL", "shinL", "footL"], front: [0.25, 0, 0], side: [0.7, -1.1, 0.3] },
    { parts: ["thighR", "shinR", "footR"], pivots: ["thighR", "shinR", "footR"], front: [-0.25, 0, 0], side: [-0.7, -1.1, 0.3] },
    { parts: ["head"], pivots: ["neck"], front: [0.3], side: [0.3] },
  ];
  const rot = (p, c, a) => {
    const s = Math.sin(a), co = Math.cos(a), dx = p[0] - c[0], dy = p[1] - c[1];
    return [c[0] + dx * co - dy * s, c[1] + dx * s + co * dy];
  };
  function posed(view, t) {
    // 2D positions of points and joints in a view at time t (radians of the swing)
    const ax = view.ax, J = withExtras(joints);
    const pick = (p3) => [p3[ax], p3[1]];
    const pts = (ax === 0 ? rig.front : rig.side).map((p) => p.slice());
    const jp = {};
    for (const k in J) jp[k] = pick(J[k]);
    if (!posing) return { pts, jp };
    const amp = 0.55 * Math.sin(t);
    for (const ch of CHAINS) {
      const w = ax === 0 ? ch.front : ch.side;
      // the pivots after the turns above them
      const piv = ch.pivots.map((k) => jp[k].slice());
      const turn = (q, level) => {
        let r = q;
        for (let i = 0; i <= level; i++) {
          const cur = piv[i];
          r = rot(r, cur, amp * w[i]);
        }
        return r;
      };
      // move the points of each part
      rig.parts.forEach((name, i) => {
        const level = ch.parts.indexOf(name);
        if (level >= 0) pts[i] = turn(pts[i], level);
      });
      // and the joints below each pivot (the pivots move with their parents' turns)
      for (let lv = ch.pivots.length - 1; lv >= 1; lv--) jp[ch.pivots[lv]] = turn(jp[ch.pivots[lv]], lv - 1);
      const ends = { handL: "handendL", handR: "handendR", footL: "toeL", footR: "toeR", neck: "top" };
      const last = ch.pivots[ch.pivots.length - 1];
      if (ends[last]) jp[ends[last]] = turn(jp[ends[last]], ch.pivots.length - 1);
    }
    return { pts, jp };
  }

  // ---------------------------------------------------------------- drawing
  function draw() {
    if (!rig) return;
    const t = posing ? (performance.now() - poseStart) / 450 : 0;
    const colourParts = $("rig-colours").checked || posing || painting;
    for (const v of views) {
      const canvas = $(v.id), ctx = canvas.getContext("2d");
      const f = frameOf(canvas, v.ax);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#0b0c12";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const { pts, jp } = posed(v, t);
      // the model: behind first (side view: far x first)
      pts.forEach((p, i) => {
        const [px, py] = f.to(p[0], p[1]);
        ctx.fillStyle = colourParts && rig.parts[i] ? PART_COLOUR[rig.parts[i].replace(/[LR]$/, "")] || "#888" : "#6d7184";
        ctx.globalAlpha = colourParts ? 0.85 : 0.55;
        ctx.fillRect(px, py, 1.6, 1.6);
      });
      ctx.globalAlpha = 1;
      if (!joints.neck) continue;
      // bones
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = "rgba(255,255,255,0.75)";
      for (const [a, b] of BONES) {
        if (!jp[a] || !jp[b]) continue;
        const [x1, y1] = f.to(...jp[a]), [x2, y2] = f.to(...jp[b]);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      }
      // joints
      for (const k of Object.keys(JOINTS)) {
        if (!jp[k]) continue;
        const [x, y] = f.to(...jp[k]);
        const big = hover && hover.key === k ? 7 : 5;
        ctx.beginPath(); ctx.arc(x, y, big, 0, 2 * Math.PI);
        ctx.fillStyle = JOINTS[k][1]; ctx.fill();
        ctx.lineWidth = 1.5; ctx.strokeStyle = "#000"; ctx.stroke();
      }
      if (hover && hover.view === v.id && jp[hover.key]) {
        const [x, y] = f.to(...jp[hover.key]);
        ctx.font = "12px sans-serif";
        const label = JOINTS[hover.key][0], w = ctx.measureText(label).width + 10;
        const lx = Math.min(Math.max(x + 10, 2), canvas.width - w - 2);
        ctx.fillStyle = "rgba(0,0,0,0.8)"; ctx.fillRect(lx, y - 22, w, 18);
        ctx.fillStyle = "#fff"; ctx.fillText(label, lx + 5, y - 9);
      }
    }
    if (posing) frame = requestAnimationFrame(draw);
  }

  // ---------------------------------------------------------------- dragging joints
  function nearest(view, px, py) {
    const canvas = $(view.id), f = frameOf(canvas, view.ax);
    let best = null;
    for (const k of Object.keys(JOINTS)) {
      if (!joints[k]) continue;
      const [x, y] = f.to(joints[k][view.ax], joints[k][1]);
      const d = Math.hypot(x - px, y - py);
      if (d < 12 && (!best || d < best.d)) best = { key: k, d };
    }
    return best && best.key;
  }
  function pointer(view, e) {
    const canvas = $(view.id), r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height];
  }
  function attach(view) {
    const canvas = $(view.id);
    canvas.addEventListener("pointerdown", (e) => {
      if (posing) return;
      const [px, py] = pointer(view, e);
      if (painting) {
        brushDown = true;
        canvas.setPointerCapture(e.pointerId);
        paintAt(view, px, py);
        draw();
        return;
      }
      const key = nearest(view, px, py);
      if (!key) return;
      drag = { view, key };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      const [px, py] = pointer(view, e);
      if (painting) {
        if (brushDown) paintAt(view, px, py);
        draw();
        return;
      }
      if (drag && drag.view === view) {
        const f = frameOf(canvas, view.ax), [a, b] = f.from(px, py);
        const j = joints[drag.key].slice();
        j[view.ax] = a; j[1] = b;
        joints[drag.key] = j;
        const twin = mirrorOf(drag.key);
        if ($("rig-mirror").checked && twin && joints[twin]) {      // the other side, mirrored
          const m = joints[twin].slice();
          if (view.ax === 0) m[0] = -a; else m[2] = a;
          m[1] = b;
          joints[twin] = m;
        }
        changed = true;
        movedJoints = true;
        showState();
      } else {
        const key = nearest(view, px, py);
        hover = key ? { key, view: view.id } : null;
        canvas.style.cursor = key ? "grab" : "default";
      }
      draw();
    });
    const end = () => { drag = null; brushDown = false; };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("pointerleave", () => { hover = null; draw(); });
  }

  // ---------------------------------------------------------------- painting body parts
  function paintAt(view, px, py) {
    const canvas = $(view.id), f = frameOf(canvas, view.ax), r = Number($("rig-brush").value);
    const pts = view.ax === 0 ? rig.front : rig.side;
    pts.forEach((p, i) => {
      const [x, y] = f.to(p[0], p[1]);
      if (Math.hypot(x - px, y - py) <= r && rig.parts[i] !== brushPart) {
        rig.parts[i] = brushPart;
        strokes.push([rig.front[i][0], rig.front[i][1], rig.side[i][0], brushPart]);
        changed = true;
      }
    });
    showState();
  }
  function palette() {
    const box = $("rig-palette");
    box.replaceChildren();
    for (const [key, label] of PAINT) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.style.background = PART_COLOUR[key.replace(/[LR]$/, "")];
      b.className = key === brushPart ? "on" : "";
      b.addEventListener("click", () => { brushPart = key; palette(); });
      box.append(b);
    }
  }

  // ---------------------------------------------------------------- state and actions
  function showState() {
    const badge = $("rig-badge"), status = $("rig-status");
    if (rig.error && !changed) {
      badge.textContent = "✗"; badge.className = "rig-badge bad";
      status.textContent = "The skeleton was not found automatically: drag the dots onto the joints, then press Use these joints.";
    } else if (changed) {
      badge.textContent = "✎"; badge.className = "rig-badge edit";
      status.textContent = "Changed: press Use these joints to rig the model with your joints and painting.";
    } else if (rig.by_hand || (rig.paint || []).length) {
      badge.textContent = "✓"; badge.className = "rig-badge ok";
      status.textContent = rig.by_hand ? "Rigged with the joints you placed" + ((rig.paint || []).length ? " and your painting." : ".")
        : "Rigged automatically, with your painting.";
    } else {
      badge.textContent = "✓"; badge.className = "rig-badge ok";
      status.textContent = "Rigged automatically from the model's shape. Check that every dot sits on its joint.";
    }
    $("rig-apply").disabled = !changed;
    $("rig-auto").hidden = !rig.by_hand && !changed && !rig.turned_by_hand && !(rig.paint || []).length;
  }

  // a starting skeleton when none was found: human proportions over the model's box
  function guess() {
    const xs = rig.front.map((p) => p[0]), ys = rig.front.map((p) => p[1]), zs = rig.side.map((p) => p[0]);
    const y0 = Math.min(...ys), H = Math.max(...ys) - y0, w = Math.max(...xs.map(Math.abs));
    const z = zs.reduce((a, b) => a + b, 0) / zs.length, at = (x, f) => [x, y0 + f * H, z];
    const J = { neck: at(0, 0.87), hips: at(0, 0.53) };
    for (const [s, k] of [[1, "L"], [-1, "R"]]) {
      Object.assign(J, { ["upper" + k]: at(s * 0.12 * H, 0.81), ["fore" + k]: at(s * (0.12 * H + 0.4 * (w - 0.12 * H)), 0.81),
        ["hand" + k]: at(s * (w - 0.1 * H), 0.81), ["handend" + k]: at(s * w, 0.81), ["thigh" + k]: at(s * 0.09 * H, 0.5),
        ["shin" + k]: at(s * 0.09 * H, 0.27), ["foot" + k]: at(s * 0.09 * H, 0.05), ["toe" + k]: [s * 0.09 * H, y0, z + 0.08 * H] });
    }
    return J;
  }

  function show(info, callback) {
    onInfo = callback;
    const box = $("rig-view");
    rig = info && info.ok !== false && info.rig ? info.rig : null;
    box.hidden = !rig;
    cancelAnimationFrame(frame); posing = false; $("rig-pose").textContent = "▶ Try a pose";
    if (!rig) return;
    joints = {};
    const src = rig.joints || guess();
    for (const k of Object.keys(JOINTS)) if (src[k]) joints[k] = src[k].slice();
    changed = !rig.joints;          // a guess must be applied before it counts
    movedJoints = !rig.joints;
    strokes = (rig.paint || []).map((s) => s.slice());
    showState();
    draw();
  }

  async function send(body, message) {
    const progress = $("rig-progress");
    progress.hidden = false;
    progress.textContent = message;
    try {
      const info = await api("/api/model/rig", { id: state.current.id, ...body });
      progress.hidden = true;
      if (onInfo) onInfo(info);
    } catch (e) { progress.textContent = e.message; }
  }

  const turnBy = (R) => {
    const cur = Array.isArray(rig.turn) ? rig.turn : [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    const M = R.map((r) => [0, 1, 2].map((j) => r[0] * cur[0][j] + r[1] * cur[1][j] + r[2] * cur[2][j]));
    send({ turn: M, joints: null }, "Turning the model and rigging it again…");
  };

  function init() {
    views.forEach(attach);
    $("rig-colours").addEventListener("change", draw);
    $("rig-apply").addEventListener("click", () => {
      const turn = Array.isArray(rig.turn) ? rig.turn : "auto";
      send({ joints: rig.by_hand || movedJoints ? joints : null, turn, paint: strokes },
        "Rigging the model with your joints and painting…");
    });
    $("rig-auto").addEventListener("click", () => send({ joints: null, turn: "auto", paint: null }, "Rigging the model automatically…"));
    $("rig-paint").addEventListener("change", () => {
      painting = $("rig-paint").checked;
      $("rig-paintbox").hidden = !painting;
      if (painting) palette();
      draw();
    });
    $("rig-paint-clear").addEventListener("click", () => {
      strokes = [];
      send({ joints: rig.by_hand ? joints : null, turn: Array.isArray(rig.turn) && rig.turned_by_hand ? rig.turn : "auto", paint: null },
        "Rigging the model without the painting…");
    });
    $("rig-pose").addEventListener("click", () => {
      posing = !posing;
      $("rig-pose").textContent = posing ? "■ Stop the pose" : "▶ Try a pose";
      poseStart = performance.now();
      cancelAnimationFrame(frame);
      draw();
    });
    // turns: tip forward (around X), roll sideways (around Z), turn around (around Y)
    $("rig-turn-x").addEventListener("click", () => turnBy([[1, 0, 0], [0, 0, -1], [0, 1, 0]]));
    $("rig-turn-z").addEventListener("click", () => turnBy([[0, -1, 0], [1, 0, 0], [0, 0, 1]]));
    $("rig-turn-y").addEventListener("click", () => turnBy([[-1, 0, 0], [0, 1, 0], [0, 0, -1]]));
  }

  return { show, init };
})();

T3Rig.init();
