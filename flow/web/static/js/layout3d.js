// The 3-D layout view (three.js): every visible layer of the focused layout extruded between its
// nominal heights (an even stack, the same for every PDK: the exported geometry carries no
// thicknesses), with an adjustable vertical exaggeration. Drag orbits, right-drag pans, wheel
// zooms. Where the browser has no WebGL (the Claude app's artifact panel), the same view is drawn
// on a 2-D canvas: each box's faces toward the camera, the boxes far to near, each face lit flat
// (a polygon's top face alone).

import { h, icon, select, titled } from "./icons.js";
import { isVisible, layerColor, layerStyle, reportLayers } from "./layers.js";
import { generators, layoutFocus, layoutsFor, loadLayout } from "./layout2d.js";
import { on, series, setFocus, state, status } from "./store.js";

// three.js and its addons by their full module URLs (jsDelivr's +esm: an addon imports the same
// three, and no import map, which an artifact's frame refuses)
const THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0";
let THREE = null;
let OrbitControls = null;
let mergeGeometries = null;

async function three() {
    if (!THREE) {
        THREE = await import(`${THREE_URL}/+esm`);
        ({ OrbitControls } = await import(`${THREE_URL}/examples/jsm/controls/OrbitControls.js/+esm`));
        ({ mergeGeometries } = await import(`${THREE_URL}/examples/jsm/utils/BufferGeometryUtils.js/+esm`));
    }
    return THREE;
}

// non-indexed boxes for many rectangles at once: positions and normals
function boxesGeometry(rects, z0, z1, ox, oy) {
    const count = rects.length / 4;
    const positions = new Float32Array(count * 36 * 3);
    const normals = new Float32Array(count * 36 * 3);
    let p = 0;
    const face = (a, b, c, d, n) => {
        for (const v of [a, b, c, a, c, d]) {
            positions[p] = v[0];
            positions[p + 1] = v[1];
            positions[p + 2] = v[2];
            normals[p] = n[0];
            normals[p + 1] = n[1];
            normals[p + 2] = n[2];
            p += 3;
        }
    };
    for (let i = 0; i < rects.length; i += 4) {
        const x1 = rects[i] - ox;
        const y1 = rects[i + 1] - oy;
        const x2 = rects[i + 2] - ox;
        const y2 = rects[i + 3] - oy;
        const a = [x1, y1, z0], b = [x2, y1, z0], c = [x2, y2, z0], d = [x1, y2, z0];
        const e = [x1, y1, z1], f = [x2, y1, z1], g = [x2, y2, z1], k = [x1, y2, z1];
        face(e, f, g, k, [0, 0, 1]);
        face(a, d, c, b, [0, 0, -1]);
        face(a, b, f, e, [0, -1, 0]);
        face(c, d, k, g, [0, 1, 0]);
        face(b, c, g, f, [1, 0, 0]);
        face(d, a, e, k, [-1, 0, 0]);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
    return geometry;
}

function polygonGeometry(rings, z0, z1, ox, oy) {
    const toPoints = (ring) => {
        const points = [];
        for (let i = 0; i < ring.length; i += 2) points.push(new THREE.Vector2(ring[i] - ox, ring[i + 1] - oy));
        return points;
    };
    const shape = new THREE.Shape(toPoints(rings[0]));
    for (const hole of rings.slice(1)) shape.holes.push(new THREE.Path(toPoints(hole)));
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: z1 - z0, bevelEnabled: false });
    geometry.translate(0, 0, z0);
    geometry.deleteAttribute("uv");
    return geometry.index ? geometry.toNonIndexed() : geometry;
}

// the 2-D drawing's flat lighting: each face's shade by its normal, as the WebGL view's sun and fill
// light it, and a colour shaded
const SHADE = (() => {
    const sun = [0.6, -1, 1.4].map((v, _, all) => v / Math.hypot(...all));
    const fill = [-1, 0.8, 0.6].map((v, _, all) => v / Math.hypot(...all));
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const normals = { top: [0, 0, 1], bottom: [0, 0, -1], px: [1, 0, 0], nx: [-1, 0, 0], py: [0, 1, 0], ny: [0, -1, 0] };
    return Object.fromEntries(Object.entries(normals).map(([key, n]) => [key, 0.28 + 0.22 * (0.5 + 0.5 * n[2]) + 0.5 * Math.max(0, dot(n, sun)) + 0.12 * Math.max(0, dot(n, fill))]));
})();
const tint = (rgb, shade) => `rgb(${Math.min(255, rgb[0] * shade) | 0},${Math.min(255, rgb[1] * shade) | 0},${Math.min(255, rgb[2] * shade) | 0})`;

export class Layout3DPanel {
    constructor(container, saved) {
        this.container = container;
        this.config = { generator: null, exaggeration: 1, edges: true, ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.host = h("div.canvas-host", { style: { background: "var(--scene-bg)" } });
        this.info = h("div.hud.info", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("cube", 28) }), h("strong", {}, "No layout"), h("span", {}, ""));
        this.host.append(this.info, this.emptyNote);
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.host));
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.off = [
            on("block", () => this.refresh(true)),
            on("selection", () => this.refresh(false)),
            on("focus", () => this.refresh(false)),
            on("layers", () => this.applyVisibility()),
            on("theme", () => this.applyTheme()),
        ];
        // WebGL starts only once the panel is on screen (a hidden tab costs nothing)
        this.resizeObserver = new ResizeObserver(() => {
            if (this.deferred && this.host.clientWidth && this.host.clientHeight) {
                this.deferred = false;
                this.refresh(true);
            } else this.resize();
        });
        this.resizeObserver.observe(this.host);
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            this.resizeObserver.disconnect();
            this.renderer?.dispose();
            reportLayers(this, null);
        });
        this.refresh(true);
    }

    buildToolbar() {
        const gens = generators();
        if (!gens.includes(this.config.generator)) this.config.generator = gens[0] || null;
        const shown = series();
        const focus = layoutFocus(this.config.generator);
        this.toolbar.replaceChildren();
        if (shown.length > 1) {
            this.toolbar.append(
                titled("Series", select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))),
            );
        }
        if (gens.length) {
            this.toolbar.append(
                titled("Generator", select(gens.map((generator) => ({ value: generator, label: generator })), this.config.generator, (value) => {
                    this.config.generator = value;
                    this.refresh(true);
                })),
            );
        }
        const range = h("input", { type: "range", min: "1", max: "12", step: "0.5", title: "Vertical exaggeration" });
        range.value = this.config.exaggeration;
        range.addEventListener("input", () => {
            this.config.exaggeration = Number(range.value);
            if (this.group) this.group.scale.z = this.config.exaggeration;
            this.render();
        });
        const edges = h("button.icon-btn", { title: "Edges", onclick: () => {
            this.config.edges = !this.config.edges;
            edges.classList.toggle("on", this.config.edges);
            this.applyVisibility();
        } }, h("span", { html: icon("edges", 14) }));
        if (this.config.edges) edges.classList.add("on");
        this.toolbar.append(
            h("span.grow"),
            h("label.field", {}, h("span", {}, "Z ×"), range),
            edges,
            h("button.icon-btn", { title: "View from above", onclick: () => this.home(true) }, h("span", { html: icon("top", 14) })),
            h("button.icon-btn", { title: "Reset the view", onclick: () => this.home(false) }, h("span", { html: icon("fit", 14) })),
            h("button.icon-btn", { title: "Save the view as PNG", onclick: () => this.save() }, h("span", { html: icon("download", 14) })),
        );
    }

    async refresh(rehome) {
        this.buildToolbar();
        const focus = layoutFocus(this.config.generator);
        const meta = focus ? layoutsFor(focus, this.config.generator) : null;
        if (!meta) {
            this.clear();
            this.emptyNote.style.display = "";
            this.emptyNote.lastChild.textContent = !state.block ? "Select a block." : state.block.layoutNote || "No layout for the focused series with this generator.";
            this.info.style.display = "none";
            return;
        }
        if (meta.path === this.path && !rehome) return;
        this.emptyNote.style.display = "none";
        if (!this.host.clientWidth || !this.host.clientHeight) {
            this.deferred = true;
            return;
        }
        const token = (this.token = Symbol());
        try {
            await three();
            const layout = await loadLayout(meta.path);
            if (token !== this.token) return;
            this.ensureRenderer();
            this.build(layout);
            this.path = meta.path;
            this.info.style.display = "";
            this.info.replaceChildren(h("span", {}, `${layout.cell} · ${layout.pdk} · ${meta.generator}`), h("span", {}, this.flat ? "nominal stack · drawn without WebGL" : "nominal stack"));
            this.home(false);
        } catch (error) {
            status(`3-D view: ${error.message}`, true);
        }
    }

    ensureRenderer() {
        if (this.renderer || this.flat) return;
        let canvas;
        try {
            this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
            this.renderer.setPixelRatio(window.devicePixelRatio || 1);
            canvas = this.renderer.domElement;
        } catch (error) {
            // no WebGL: the 2-D drawing (drawFlat)
            this.renderer = null;
            canvas = document.createElement("canvas");
            this.flat = canvas.getContext("2d");
        }
        this.canvas = canvas;
        this.host.prepend(canvas);
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(35, 1, 0.01, 1e4);
        this.camera.up.set(0, 0, 1);
        this.controls = new OrbitControls(this.camera, canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.12;
        this.controls.addEventListener("change", () => this.render());
        this.controls.addEventListener("start", () => this.animate(true));
        this.controls.addEventListener("end", () => this.animate(false));
        // three's lights in physical units (since r155): an intensity of pi lights as 1 did before
        this.scene.add(new THREE.HemisphereLight(0xeceff4, 0x2e3440, 1.1 * Math.PI));
        const sun = new THREE.DirectionalLight(0xffffff, 1.6 * Math.PI);
        sun.position.set(0.6, -1, 1.4);
        this.scene.add(sun);
        const fill = new THREE.DirectionalLight(0x88c0d0, 0.5 * Math.PI);
        fill.position.set(-1, 0.8, 0.6);
        this.scene.add(fill);
        this.applyTheme();
        this.resize();
    }

    animate(running) {
        this.running = running;
        const tick = () => {
            if (!this.renderer && !this.flat) return;
            const moving = this.controls.update();
            this.draw();
            if (this.running || moving) requestAnimationFrame(tick);
        };
        if (running) requestAnimationFrame(tick);
    }

    clear() {
        if (this.flatLayers) {
            this.flatLayers = null;
            this.path = null;
            reportLayers(this, null);
            this.render();
        }
        if (!this.group) return;
        this.scene.remove(this.group);
        this.group.traverse((object) => {
            object.geometry?.dispose();
            object.material?.dispose();
        });
        this.group = null;
        this.path = null;
        reportLayers(this, null);
        this.render();
    }

    build(layout) {
        if (this.group || this.flatLayers) this.clear();
        const [x1, y1, x2, y2] = layout.bbox;
        const cx = (x1 + x2) / 2;
        const cy = (y1 + y2) / 2;
        this.extent = Math.max(x2 - x1, y2 - y1);
        if (this.flat) return this.buildFlat(layout, cx, cy);
        this.group = new THREE.Group();
        this.layers = {};
        for (const layer of layout.layers) {
            const style = layerStyle(layer.key);
            if (!style.z) continue;
            const [z0, z1] = style.z;
            const parts = [];
            if (layer.rects.length) parts.push(boxesGeometry(layer.rects, z0, z1, cx, cy));
            for (const rings of layer.polys) {
                try {
                    parts.push(polygonGeometry(rings, z0, z1, cx, cy));
                } catch (error) {
                    console.warn(layer.key, error);
                }
            }
            if (!parts.length) continue;
            const geometry = parts.length === 1 ? parts[0] : mergeGeometries(parts, false);
            const color = new THREE.Color(layerColor(style));
            // a little sheen on the metals: with nothing to reflect, a metallic surface is dark
            const material = new THREE.MeshStandardMaterial({
                color,
                roughness: style.group === "metal" ? 0.5 : 0.7,
                metalness: style.group === "metal" || style.group === "via" ? 0.1 : 0,
                transparent: style.group === "well",
                opacity: style.group === "well" ? 0.25 : 1,
                polygonOffset: true,
                polygonOffsetFactor: 1,
                polygonOffsetUnits: 1,
            });
            const mesh = new THREE.Mesh(geometry, material);
            const lines = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 25), new THREE.LineBasicMaterial({ color: color.clone().multiplyScalar(0.45), transparent: true, opacity: 0.6 }));
            const holder = new THREE.Group();
            holder.add(mesh, lines);
            this.layers[layer.key] = { holder, lines };
            this.group.add(holder);
        }
        this.group.scale.z = this.config.exaggeration;
        this.scene.add(this.group);
        reportLayers(this, Object.fromEntries(layout.layers.map((layer) => [layer.key, layer.count])));
        this.applyVisibility();
    }

    // the layers as the 2-D drawing takes them: rectangles and polygons about the centre, each
    // layer's colour as RGB and its edges darker
    buildFlat(layout, cx, cy) {
        this.flatLayers = [];
        for (const layer of layout.layers) {
            const style = layerStyle(layer.key);
            if (!style.z || (!layer.rects.length && !layer.polys.length)) continue;
            const hex = new THREE.Color(layerColor(style)).getHexString();
            const rgb = [0, 2, 4].map((at) => parseInt(hex.slice(at, at + 2), 16));
            this.flatLayers.push({
                key: layer.key,
                z: style.z,
                rects: Float32Array.from(layer.rects, (value, index) => value - (index % 2 ? cy : cx)),
                polys: layer.polys.map((rings) => rings[0].map((value, index) => value - (index % 2 ? cy : cx))),
                rgb,
                edge: tint(rgb, 0.45),
                alpha: style.group === "well" ? 0.25 : 1,
            });
        }
        reportLayers(this, Object.fromEntries(layout.layers.map((layer) => [layer.key, layer.count])));
        this.applyVisibility();
    }

    // the 2-D drawing: each visible box's faces toward the camera, the boxes sorted far to near
    drawFlat() {
        const ctx = this.flat;
        const width = this.canvas.width;
        const height = this.canvas.height;
        ctx.globalAlpha = 1;
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--scene-bg").trim() || "#20242c";
        ctx.fillRect(0, 0, width, height);
        if (!this.flatLayers) return;
        const camera = this.camera;
        camera.updateMatrixWorld();
        const e = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
        const { x: px, y: py, z: pz } = camera.position;
        const project = (x, y, z) => {
            const w = e[3] * x + e[7] * y + e[11] * z + e[15];
            return [((e[0] * x + e[4] * y + e[8] * z + e[12]) / w * 0.5 + 0.5) * width, (0.5 - ((e[1] * x + e[5] * y + e[9] * z + e[13]) / w) * 0.5) * height, w];
        };
        const zs = this.config.exaggeration;
        const items = [];
        for (const layer of this.flatLayers) {
            if (!isVisible(layer.key)) continue;
            const zm = ((layer.z[0] + layer.z[1]) / 2) * zs - pz;
            const r = layer.rects;
            for (let i = 0; i < r.length; i += 4) {
                const mx = (r[i] + r[i + 2]) / 2 - px;
                const my = (r[i + 1] + r[i + 3]) / 2 - py;
                items.push([mx * mx + my * my + zm * zm, layer, i]);
            }
            for (const ring of layer.polys) {
                let mx = 0;
                let my = 0;
                for (let i = 0; i < ring.length; i += 2) {
                    mx += ring[i];
                    my += ring[i + 1];
                }
                mx = mx / (ring.length / 2) - px;
                my = my / (ring.length / 2) - py;
                items.push([mx * mx + my * my + zm * zm, layer, -1, ring]);
            }
        }
        items.sort((a, b) => b[0] - a[0]);
        ctx.lineWidth = 0.6 * (window.devicePixelRatio || 1);
        ctx.lineJoin = "round";
        const shape = (points, fill, stroke) => {
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let k = 1; k < points.length; k++) ctx.lineTo(points[k][0], points[k][1]);
            ctx.closePath();
            ctx.fillStyle = fill;
            ctx.fill();
            if (stroke) {
                ctx.strokeStyle = stroke;
                ctx.stroke();
            }
        };
        const near = camera.near;
        for (const [, layer, i, ring] of items) {
            const z0 = layer.z[0] * zs;
            const z1 = layer.z[1] * zs;
            const edge = this.config.edges ? layer.edge : null;
            ctx.globalAlpha = layer.alpha;
            if (ring) {
                const top = [];
                for (let k = 0; k < ring.length; k += 2) top.push(project(ring[k], ring[k + 1], z1));
                if (pz > z1 && top.every((point) => point[2] > near)) shape(top, tint(layer.rgb, SHADE.top), edge);
                continue;
            }
            const r = layer.rects;
            const x1 = r[i];
            const y1 = r[i + 1];
            const x2 = r[i + 2];
            const y2 = r[i + 3];
            const c = [project(x1, y1, z0), project(x2, y1, z0), project(x2, y2, z0), project(x1, y2, z0), project(x1, y1, z1), project(x2, y1, z1), project(x2, y2, z1), project(x1, y2, z1)];
            if (c.some((point) => point[2] <= near)) continue;
            if (pz > z1) shape([c[4], c[5], c[6], c[7]], tint(layer.rgb, SHADE.top), edge);
            else if (pz < z0) shape([c[0], c[3], c[2], c[1]], tint(layer.rgb, SHADE.bottom), edge);
            if (px > x2) shape([c[1], c[2], c[6], c[5]], tint(layer.rgb, SHADE.px), edge);
            else if (px < x1) shape([c[3], c[0], c[4], c[7]], tint(layer.rgb, SHADE.nx), edge);
            if (py > y2) shape([c[2], c[3], c[7], c[6]], tint(layer.rgb, SHADE.py), edge);
            else if (py < y1) shape([c[0], c[1], c[5], c[4]], tint(layer.rgb, SHADE.ny), edge);
        }
        ctx.globalAlpha = 1;
    }

    applyVisibility() {
        for (const [key, { holder, lines }] of Object.entries(this.layers || {})) {
            holder.visible = isVisible(key);
            lines.visible = this.config.edges;
        }
        this.render();
    }

    applyTheme() {
        if (this.flat) return this.render();
        if (!this.scene) return;
        const background = getComputedStyle(document.documentElement).getPropertyValue("--scene-bg").trim() || "#20242c";
        this.scene.background = new THREE.Color(background);
        this.render();
    }

    home(top) {
        if (!this.camera || !this.extent) return;
        const distance = this.extent * 1.6;
        this.controls.target.set(0, 0, 0.5);
        if (top) this.camera.position.set(0, -0.001, distance * 1.15);
        else this.camera.position.set(distance * 0.55, -distance * 0.85, distance * 0.75);
        this.camera.near = distance / 500;
        this.camera.far = distance * 50;
        this.camera.updateProjectionMatrix();
        this.controls.update();
        this.render();
    }

    save() {
        if (!this.canvas) return;
        this.draw();
        const link = document.createElement("a");
        link.download = `${this.path?.split("/").pop()?.replace(".json", "") || "layout"}_3d.png`;
        link.href = this.canvas.toDataURL("image/png");
        link.click();
    }

    resize() {
        if (!this.renderer && !this.flat) return;
        const width = this.host.clientWidth;
        const height = this.host.clientHeight;
        if (!width || !height) return;
        if (this.renderer) this.renderer.setSize(width, height);
        else {
            const ratio = window.devicePixelRatio || 1;
            Object.assign(this.canvas, { width: Math.round(width * ratio), height: Math.round(height * ratio) });
            Object.assign(this.canvas.style, { width: `${width}px`, height: `${height}px` });
        }
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.render();
    }

    draw() {
        if (this.renderer) this.renderer.render(this.scene, this.camera);
        else if (this.flat) this.drawFlat();
    }

    render() {
        if (!this.running) this.draw();
    }
}
