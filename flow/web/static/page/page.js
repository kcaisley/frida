// One laid-out instance (flow/web/page.py): its metrics by the pipeline's steps, its netlist, its
// schematic and its layout in 2-D and 3-D, from the JSON in the page; nothing fetched but three.js
// (jsDelivr, full +esm URLs: the artifact frame refuses an import map in Firefox), when the 3-D
// view first opens. Generic: no control, preset or note belongs to one block.

const FLAT = location.hash === "#flat";  // #flat: the 3-D view drawn without WebGL, as a browser without it would
const read = (id) => JSON.parse(document.getElementById(id).textContent);
const P = read("page"), LAYOUT = read("layout"), NETLIST = read("netlist"), SCHEMATIC = read("schematic");
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
// a time: whole seconds as ALIGN's log has them, else tenths
const secs = (s) => (s == null ? "—" : s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : Number.isInteger(s) ? `${s} s` : `${s.toFixed(1)} s`);

// ---------------------------------------------------------------- tabs

const VIEWS = [["metrics", "Metrics"], ["netlist", "Netlist"], ["schematic", "Schematic"], ["2d", "2D"], ["3d", "3D"]];
const opened = {};
function open(key) {
  for (const [k] of VIEWS) {
    $(`view-${k}`).hidden = k !== key;
    $(`tab-${k}`).setAttribute("aria-selected", String(k === key));
  }
  $("dock").hidden = !(key === "2d" || key === "3d");
  for (const el of document.querySelectorAll("[data-3d]")) el.hidden = key !== "3d";
  if (!opened[key]) { opened[key] = true; ({ schematic: initSchematic, "2d": init2d, "3d": init3d })[key]?.(); }
  if (key === "2d") draw2d();
  if (key === "3d") three.resize?.();
  try { history.replaceState(null, "", `#${key}`); } catch {}
}
for (const [key, label] of VIEWS) {
  const b = document.createElement("button");
  b.type = "button"; b.setAttribute("role", "tab"); b.id = `tab-${key}`; b.textContent = label;
  b.onclick = () => open(key);
  $("tabs").append(b);
}

// ---------------------------------------------------------------- metrics, by step
// Each step one table: a row a fact, the step's state and time first, each of its lists a group of
// rows under its title; one value column, the instance's (a second instance a column beside it).
const STATE = { ok: "passed", warn: "warnings", bad: "failed", none: "not run" };
const LIMIT = 12;
function numeric(v) { return typeof v === "number" || /^-?[\d.,]+(\s?(s|µm|µm²|%))?$/.test(String(v)); }
function valueCell(v, html) {
  return `<td class="${numeric(v) ? "num" : "text"}">${html ?? esc(v)}</td>`;
}
// a list's rows as label and one value: the Layout/Source pair "26 / 26" (and marked where they
// differ), else the last column the value and the ones before it the label
function folded(t) {
  const pair = t.head.length === 3 && t.head[1] === "Layout";
  return t.rows.map((r) => pair
    ? { label: String(r[0]), value: `${r[1]} / ${r[2]}`, differ: r[1] !== r[2] }
    : { label: r.slice(0, -1).map(String).join(" · "), value: r[r.length - 1] });
}
function stepTable(s, index) {
  const rows = [];
  const row = (label, cell, cls = "") => rows.push(`<tr class="${cls}"><th scope="row">${esc(label)}</th>${cell}</tr>`);
  row("State", `<td class="text"><span class="state ${s.state}">${STATE[s.state] || s.state}</span></td>`);
  row("Time", valueCell(secs(s.seconds)));
  for (const [k, v] of s.facts) if (v !== null && v !== undefined && v !== "") row(k, valueCell(v));
  s.tables.forEach((t, g) => {
    const items = folded(t);
    rows.push(`<tr class="group"><th colspan="2" scope="rowgroup">${esc(t.title)}</th></tr>`);
    items.forEach((it, k) => row(it.label, valueCell(it.value), [it.differ ? "differ" : "", k >= LIMIT ? `more-${index}-${g}` : ""].join(" ")));
    if (items.length > LIMIT) rows.push(`<tr class="show"><td colspan="2"><button type="button" class="more" data-rows="more-${index}-${g}">Show all ${items.length}</button></td></tr>`);
  });
  return `<section class="card ${s.state}"><h2><span class="n">${index + 1}</span>${esc(s.title)}</h2>` +
    `<div class="table"><table class="step"><colgroup><col class="label"><col class="value"></colgroup>` +
    `<thead><tr><th scope="col"></th><th scope="col">${esc(P.name)}</th></tr></thead><tbody>${rows.join("")}</tbody></table></div></section>`;
}
function metrics() {
  $("metrics").innerHTML = P.steps.map(stepTable).join("");
  for (const tr of $("metrics").querySelectorAll('tr[class*="more-"]')) tr.hidden = true;
  for (const b of $("metrics").querySelectorAll("[data-rows]")) {
    b.onclick = () => {
      for (const tr of $("metrics").querySelectorAll(`tr.${b.dataset.rows}`)) tr.hidden = false;
      b.closest("tr").remove();
    };
  }
}
metrics();

// ---------------------------------------------------------------- netlist
function highlight(line) {
  const t = line.trim();
  if (t.startsWith("*")) return `<span class="c">${esc(line)}</span>`;
  if (t.startsWith(".")) return `<span class="k">${esc(line)}</span>`;
  const m = /^(\s*)(\S+)(.*)$/.exec(line);
  if (!m) return esc(line);
  const rest = esc(m[3]).replace(/(\S+)=(\S+)/g, '<span class="p">$1=</span>$2');
  return `${m[1]}<span class="i">${esc(m[2])}</span>${rest}`;
}
$("code").innerHTML = NETLIST ? NETLIST.split("\n").map((l, i) => `<span class="ln">${i + 1}</span>${highlight(l)}`).join("\n") : "No netlist.";
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText(NETLIST); $("copy").textContent = "Copied"; }
  catch { const r = document.createRange(); r.selectNodeContents($("code")); getSelection().removeAllRanges(); getSelection().addRange(r); $("copy").textContent = "Selected"; }
  setTimeout(() => { $("copy").textContent = "Copy"; }, 1500);
};

// ---------------------------------------------------------------- pan and zoom (schematic, 2-D)
// drag pans, the wheel and a pinch zoom about the pointer; view = {s, x, y}: screen = world * s + (x, y)
function panzoom(el, view, changed) {
  const pts = new Map();
  let last = null;
  el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); pts.set(e.pointerId, [e.offsetX, e.offsetY]); last = null; });
  el.addEventListener("pointerup", (e) => { pts.delete(e.pointerId); last = null; });
  el.addEventListener("pointercancel", (e) => { pts.delete(e.pointerId); last = null; });
  el.addEventListener("pointermove", (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, [e.offsetX, e.offsetY]);
    const p = [...pts.values()];
    const cx = p.reduce((a, q) => a + q[0], 0) / p.length, cy = p.reduce((a, q) => a + q[1], 0) / p.length;
    const d = p.length > 1 ? Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) : null;
    if (last) {
      if (d && last.d) zoomAt(view, cx, cy, d / last.d);
      view.x += cx - last.cx; view.y += cy - last.cy;
      changed();
    }
    last = { cx, cy, d };
  });
  el.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(view, e.offsetX, e.offsetY, Math.exp(-e.deltaY * 0.0015)); changed(); }, { passive: false });
}
function zoomAt(view, x, y, f) { view.x = x - (x - view.x) * f; view.y = y - (y - view.y) * f; view.s *= f; }

// ---------------------------------------------------------------- schematic
const sview = { s: 1, x: 0, y: 0 };
function initSchematic() {
  const paper = $("paper"), sheet = $("view-schematic");
  if (!SCHEMATIC) { paper.remove(); sheet.insertAdjacentHTML("beforeend", '<div class="empty">No schematic drawn for this netlist.</div>'); return; }
  // the schematic's own stylesheet (black on white) scoped to the sheet, the theme recolouring it
  // (style.css's .sheet rules in the viewer): its "svg" and "text" rules would restyle the page
  paper.innerHTML = SCHEMATIC.replace(/<style([^>]*)>([\s\S]*?)<\/style>/, (whole, attributes, rules) =>
    `<style${attributes}>${rules.replace(/(^|\})\s*([^@{}][^{}]*)\{/g, (rule, close, selectors) =>
      `${close}\n${selectors.split(",").map((selector) => `#paper ${selector.trim()}`).join(", ")} {`)}</style>`);
  const svg = paper.querySelector("svg");
  const apply = () => { paper.style.transform = `translate(${sview.x}px, ${sview.y}px) scale(${sview.s})`; };
  const fit = () => {
    const w = svg.viewBox.baseVal?.width || svg.width.baseVal.value, h = svg.viewBox.baseVal?.height || svg.height.baseVal.value;
    paper.style.width = `${w}px`; paper.style.height = `${h}px`; svg.setAttribute("width", w); svg.setAttribute("height", h);
    sview.s = Math.min((sheet.clientWidth - 32) / w, (sheet.clientHeight - 32) / h);
    sview.x = (sheet.clientWidth - w * sview.s) / 2; sview.y = (sheet.clientHeight - h * sview.s) / 2; apply();
  };
  panzoom(sheet, sview, apply);
  $("sfit").onclick = fit;
  fit();
}

// ---------------------------------------------------------------- layers (both layout views)
const METALS = ["#5E81AC", "#B48EAD", "#D08770", "#EBCB8B", "#8FBCBB", "#88C0D0", "#81A1C1", "#A3BE8C", "#BF616A"];
const metalZ = (n) => { const b = 0.3 + (n - 1) * 0.28; return [b, b + 0.14]; };
function style(key) {
  let m = /^M(\d+)$/.exec(key);
  if (m) { const n = +m[1]; return { color: METALS[(n - 1) % 9], group: "metal", z: metalZ(n), rank: 2 * n }; }
  m = /^V(\d+)$/.exec(key);
  if (m) { const n = +m[1]; return { color: METALS[n % 9], group: "via", z: [metalZ(n)[1], metalZ(n + 1)[0]], rank: 2 * n + 1 }; }
  return { OD: { color: "#A3BE8C", group: "fe", z: [0, 0.06], rank: -2 }, PO: { color: "#BF616A", group: "fe", z: [0.06, 0.14], rank: -1 },
    CO: { color: "#D8DEE9", group: "via", z: [0.06, 0.3], rank: 0 } }[key];
}
const LAYERS = (LAYOUT?.layers || []).filter((l) => style(l.key) && l.rects.length).sort((a, b) => style(a.key).rank - style(b.key).rank);
const visible = Object.fromEntries(LAYERS.map((l) => [l.key, true]));
const onLayers = [];
for (const layer of LAYERS) {
  const b = document.createElement("button");
  b.type = "button"; b.dataset.key = layer.key; b.style.setProperty("--c", style(layer.key).color);
  b.innerHTML = `<span class="sw"></span>${layer.key}`;
  b.title = "click: show or hide · alt-click: only this one";
  b.onclick = (e) => { if (e.altKey) for (const k in visible) visible[k] = k === layer.key; else visible[layer.key] = !visible[layer.key]; syncLayers(); };
  $("layers").append(b);
}
$("all").onclick = () => { for (const k in visible) visible[k] = true; syncLayers(); };
function syncLayers() {
  for (const b of $("layers").children) b.setAttribute("aria-pressed", String(visible[b.dataset.key]));
  for (const f of onLayers) f();
}
syncLayers();

// ---------------------------------------------------------------- 2-D
const v2 = { s: 1, x: 0, y: 0 };
let paths = null, labelsOn = false;
const canvas2 = $("canvas2");
function init2d() {
  if (!LAYOUT) { canvas2.remove(); $("view-2d").insertAdjacentHTML("beforeend", '<div class="empty">No layout.</div>'); return; }
  paths = LAYERS.map((layer) => {
    const p = new Path2D(), r = layer.rects;
    for (let i = 0; i < r.length; i += 4) p.rect(r[i], r[i + 1], r[i + 2] - r[i], r[i + 3] - r[i + 1]);
    return { key: layer.key, path: p, style: style(layer.key) };
  });
  panzoom(canvas2, v2, draw2d);
  canvas2.addEventListener("pointermove", (e) => {
    const x = (e.offsetX - v2.x) / v2.s, y = -(e.offsetY - v2.y) / v2.s;
    $("readout2").textContent = `x ${x.toFixed(3)}  y ${y.toFixed(3)} µm`;
  });
  new ResizeObserver(() => draw2d()).observe($("view-2d"));
  $("fit2").onclick = () => { fit2d(); draw2d(); };
  $("labels").onclick = () => { labelsOn = !labelsOn; $("labels").setAttribute("aria-pressed", String(labelsOn)); draw2d(); };
  onLayers.push(draw2d);
  fit2d();
}
function fit2d() {
  const [x1, y1, x2, y2] = LAYOUT.bbox, w = canvas2.clientWidth, h = canvas2.clientHeight;
  v2.s = Math.min((w - 40) / (x2 - x1), (h - 40) / (y2 - y1));
  v2.x = (w - (x2 - x1) * v2.s) / 2 - x1 * v2.s; v2.y = (h + (y2 - y1) * v2.s) / 2 + y1 * v2.s;
}
function draw2d() {
  if (!paths || $("view-2d").hidden) return;
  const ratio = Math.min(devicePixelRatio || 1, 2), w = canvas2.clientWidth, h = canvas2.clientHeight;
  if (!w || !h) return;
  if (canvas2.width !== Math.round(w * ratio)) { canvas2.width = Math.round(w * ratio); canvas2.height = Math.round(h * ratio); }
  const g = canvas2.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.fillStyle = css("--scene"); g.fillRect(0, 0, canvas2.width, canvas2.height);
  // world (um, y up) to device pixels
  g.setTransform(v2.s * ratio, 0, 0, -v2.s * ratio, v2.x * ratio, v2.y * ratio);
  for (const { key, path, style: s } of paths) {
    if (!visible[key]) continue;
    g.globalAlpha = s.group === "via" ? 0.85 : s.group === "fe" ? 0.45 : 0.32;
    g.fillStyle = s.color; g.fill(path);
    g.globalAlpha = 0.9; g.lineWidth = 1 / v2.s; g.strokeStyle = s.color; g.stroke(path);
  }
  g.globalAlpha = 1;
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  if (labelsOn) {
    g.font = `11px ${css("--mono")}`; g.fillStyle = css("--fg");
    for (const l of LAYOUT.labels) g.fillText(l.text, l.x * v2.s + v2.x + 3, -l.y * v2.s + v2.y - 3);
  }
  // scale bar: a round length about 100 px long
  const um = 100 / v2.s, step = 10 ** Math.floor(Math.log10(um)), len = [1, 2, 5, 10].map((m) => m * step).find((m) => m >= um * 0.6) || step;
  const px = len * v2.s, x0 = w - px - 16, y0 = h - 16;
  g.strokeStyle = css("--fg"); g.lineWidth = 1.5; g.beginPath(); g.moveTo(x0, y0 - 4); g.lineTo(x0, y0); g.lineTo(x0 + px, y0); g.lineTo(x0 + px, y0 - 4); g.stroke();
  g.fillStyle = css("--fg"); g.font = `11px ${css("--mono")}`; g.textAlign = "center"; g.fillText(`${len >= 1 ? len : len.toPrecision(1)} µm`, x0 + px / 2, y0 - 6); g.textAlign = "start";
}

// ---------------------------------------------------------------- 3-D
const three = {};
async function init3d() {
  const stage = $("view-3d");
  if (!LAYOUT) { stage.insertAdjacentHTML("beforeend", '<div class="empty">No layout.</div>'); return; }
  let THREE, OrbitControls;
  try {
    THREE = await import("https://cdn.jsdelivr.net/npm/three@0.160.0/+esm");
    ({ OrbitControls } = await import("https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js/+esm"));
  } catch (error) {
    stage.insertAdjacentHTML("beforeend", `<div class="empty">The 3-D view needs three.js from cdn.jsdelivr.net, which did not load: ${esc(error.message)}</div>`);
    return;
  }
  const state = { xray: false, edges: true, z: 2 };
  const [bx1, by1, bx2, by2] = LAYOUT.bbox, cx0 = (bx1 + bx2) / 2, cy0 = (by1 + by2) / 2, extent = Math.max(bx2 - bx1, by2 - by1);
  const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const tint = (c, s) => `rgb(${Math.min(255, c[0] * s) | 0},${Math.min(255, c[1] * s) | 0},${Math.min(255, c[2] * s) | 0})`;
  const layers = LAYERS.map((l) => {
    const s = style(l.key), c = rgb(s.color);
    return { key: l.key, group: s.group, z0: s.z[0], z1: s.z[1], rects: Float32Array.from(l.rects, (v, i) => v - (i % 2 ? cy0 : cx0)), rgb: c, edge: tint(c, 0.45), color: s.color };
  });
  let renderer = null;
  try { if (!FLAT) renderer = new THREE.WebGLRenderer({ antialias: true }); } catch { renderer = null; }
  const canvas = renderer ? renderer.domElement : document.createElement("canvas");
  const ratio = Math.min(devicePixelRatio || 1, 2);
  stage.prepend(canvas);
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 1e4);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.dampingFactor = 0.12;
  let running = false, scene = null, group = null, flat = null;
  const meshes = {};
  const draw = () => { if (renderer) renderer.render(scene, camera); else drawFlat(); };
  const render = () => { if (!running) draw(); };
  const animate = (on) => {
    running = on;
    const tick = () => { const moving = controls.update(); draw(); if (running || moving) requestAnimationFrame(tick); };
    if (on) requestAnimationFrame(tick);
  };
  controls.addEventListener("change", render);
  controls.addEventListener("start", () => animate(true));
  controls.addEventListener("end", () => animate(false));
  three.resize = () => {
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;
    if (renderer) renderer.setSize(w, h, false); else { canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio); }
    camera.aspect = w / h; camera.updateProjectionMatrix(); render();
  };
  new ResizeObserver(() => three.resize()).observe(stage);

  function boxes(rects, z0, z1) {
    const count = rects.length / 4, pos = new Float32Array(count * 108), nor = new Float32Array(count * 108);
    let p = 0;
    const face = (a, b, c, d, n) => { for (const v of [a, b, c, a, c, d]) { pos.set(v, p); nor.set(n, p); p += 3; } };
    for (let i = 0; i < rects.length; i += 4) {
      const x1 = rects[i], y1 = rects[i + 1], x2 = rects[i + 2], y2 = rects[i + 3];
      const a = [x1, y1, z0], b = [x2, y1, z0], c = [x2, y2, z0], d = [x1, y2, z0], e = [x1, y1, z1], f = [x2, y1, z1], g = [x2, y2, z1], k = [x1, y2, z1];
      face(e, f, g, k, [0, 0, 1]); face(a, d, c, b, [0, 0, -1]); face(a, b, f, e, [0, -1, 0]);
      face(c, d, k, g, [0, 1, 0]); face(b, c, g, f, [1, 0, 0]); face(d, a, e, k, [-1, 0, 0]);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
    return geo;
  }
  if (renderer) {
    renderer.setPixelRatio(ratio);
    scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xeceff4, 0x2e3440, 1.1 * Math.PI));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6 * Math.PI); sun.position.set(0.6, -1, 1.4); scene.add(sun);
    const fill = new THREE.DirectionalLight(0x88c0d0, 0.5 * Math.PI); fill.position.set(-1, 0.8, 0.6); scene.add(fill);
    group = new THREE.Group();
    for (const layer of layers) {
      const geo = boxes(layer.rects, layer.z0, layer.z1), color = new THREE.Color(layer.color);
      const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: layer.group === "metal" ? 0.5 : 0.7, metalness: layer.group === "fe" ? 0 : 0.1,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
      const lines = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: color.clone().multiplyScalar(0.45), transparent: true, opacity: 0.6 }));
      const holder = new THREE.Group(); holder.add(mesh, lines);
      meshes[layer.key] = { holder, mesh, lines, group: layer.group };
      group.add(holder);
    }
    scene.add(group);
  } else {
    flat = canvas.getContext("2d");
    $("readout3").textContent += " · drawn without WebGL";
  }

  // without WebGL: each visible face of each box on a 2-D canvas, far to near, lit flat
  const SUN = new THREE.Vector3(0.6, -1, 1.4).normalize(), FILL = new THREE.Vector3(-1, 0.8, 0.6).normalize();
  const shade = (n) => { const v = new THREE.Vector3(...n); return 0.28 + 0.22 * (0.5 + 0.5 * n[2]) + 0.5 * Math.max(0, v.dot(SUN)) + 0.12 * Math.max(0, v.dot(FILL)); };
  const SH = { top: shade([0, 0, 1]), bottom: shade([0, 0, -1]), px: shade([1, 0, 0]), nx: shade([-1, 0, 0]), py: shade([0, 1, 0]), ny: shade([0, -1, 0]) };
  const matrix = new THREE.Matrix4();
  function drawFlat() {
    const W = canvas.width, H = canvas.height, zs = state.z;
    flat.globalAlpha = 1; flat.fillStyle = css("--scene"); flat.fillRect(0, 0, W, H);
    camera.updateMatrixWorld();
    matrix.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    const e = matrix.elements, cx = camera.position.x, cy = camera.position.y, cz = camera.position.z;
    const Pj = (x, y, z) => { const w = e[3] * x + e[7] * y + e[11] * z + e[15]; return [((e[0] * x + e[4] * y + e[8] * z + e[12]) / w * 0.5 + 0.5) * W, (0.5 - (e[1] * x + e[5] * y + e[9] * z + e[13]) / w * 0.5) * H, w]; };
    const items = [];
    for (const layer of layers) {
      if (!visible[layer.key]) continue;
      const r = layer.rects, zm = (layer.z0 + layer.z1) / 2 * zs;
      for (let i = 0; i < r.length; i += 4) { const mx = (r[i] + r[i + 2]) / 2 - cx, my = (r[i + 1] + r[i + 3]) / 2 - cy, mz = zm - cz; items.push([mx * mx + my * my + mz * mz, layer, i]); }
    }
    items.sort((a, b) => b[0] - a[0]);
    flat.lineWidth = 0.6 * ratio;
    const quad = (pts, fs, ss) => { flat.beginPath(); flat.moveTo(pts[0][0], pts[0][1]); for (let k = 1; k < 4; k++) flat.lineTo(pts[k][0], pts[k][1]); flat.closePath(); flat.fillStyle = fs; flat.fill(); if (ss) { flat.strokeStyle = ss; flat.stroke(); } };
    for (const [, layer, i] of items) {
      const r = layer.rects, x1 = r[i], y1 = r[i + 1], x2 = r[i + 2], y2 = r[i + 3], z0 = layer.z0 * zs, z1 = layer.z1 * zs;
      const c = [Pj(x1, y1, z0), Pj(x2, y1, z0), Pj(x2, y2, z0), Pj(x1, y2, z0), Pj(x1, y1, z1), Pj(x2, y1, z1), Pj(x2, y2, z1), Pj(x1, y2, z1)];
      if (c.some((q) => q[2] <= camera.near)) continue;
      flat.globalAlpha = state.xray && layer.group === "metal" ? 0.32 : 1;
      const edge = state.edges ? layer.edge : null;
      if (cz > z1) quad([c[4], c[5], c[6], c[7]], tint(layer.rgb, SH.top), edge); else if (cz < z0) quad([c[0], c[3], c[2], c[1]], tint(layer.rgb, SH.bottom), edge);
      if (cx > x2) quad([c[1], c[2], c[6], c[5]], tint(layer.rgb, SH.px), edge); else if (cx < x1) quad([c[3], c[0], c[4], c[7]], tint(layer.rgb, SH.nx), edge);
      if (cy > y2) quad([c[2], c[3], c[7], c[6]], tint(layer.rgb, SH.py), edge); else if (cy < y1) quad([c[0], c[1], c[5], c[4]], tint(layer.rgb, SH.ny), edge);
    }
    flat.globalAlpha = 1;
  }

  function apply() {
    if (renderer) {
      scene.background = new THREE.Color(css("--scene"));
      group.scale.z = state.z;
      for (const [key, m] of Object.entries(meshes)) {
        m.holder.visible = visible[key]; m.lines.visible = state.edges;
        const see = state.xray && m.group === "metal";
        m.mesh.material.transparent = see; m.mesh.material.opacity = see ? 0.32 : 1; m.mesh.material.depthWrite = !see; m.mesh.material.needsUpdate = true;
      }
    }
    render();
  }
  function view(kind) {
    const d = extent * 1.6;
    controls.target.set(0, 0, 0.5);
    if (kind === "top") camera.position.set(0, -0.001, d * 1.15); else camera.position.set(d * 0.55, -d * 0.85, d * 0.75);
    camera.near = d / 500; camera.far = d * 50; camera.updateProjectionMatrix(); controls.update(); render();
  }
  const toggle = (id, key) => { const b = $(id); b.onclick = () => { state[key] = !state[key]; b.setAttribute("aria-pressed", String(state[key])); apply(); }; };
  toggle("xray", "xray"); toggle("edges", "edges");
  $("zscale").oninput = () => { state.z = +$("zscale").value; $("zval").textContent = $("zscale").value; apply(); };
  $("home").onclick = () => view("home");
  $("top").onclick = () => view("top");
  onLayers.push(apply);
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", apply);
  three.resize(); apply(); view("home");
}

// ---------------------------------------------------------------- start
const first = FLAT ? "3d" : VIEWS.some(([k]) => `#${k}` === location.hash) ? location.hash.slice(1) : "metrics";
open(first);
addEventListener("hashchange", () => { const key = location.hash.slice(1); if (VIEWS.some(([k]) => k === key)) open(key); });
window.__pageStarted = true;
