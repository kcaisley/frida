// The 3-D layout view (three.js): every visible layer of the focused layout extruded between its
// nominal heights (an even stack, the same for every PDK: the exported geometry carries no
// thicknesses), its boxes edged, seen first from the top as the 2-D layout (Top, Side, Isometric).
// Left-drag turns it, middle- (or right-) drag pans, the wheel zooms. Where the browser has no
// WebGL (the Claude app's artifact panel), the same view is drawn
// on a 2-D canvas: each box's faces toward the camera, the boxes far to near, each face lit flat
// (a polygon's top face alone).

import { h, icon, select, sizeMeter, titled } from "./icons.js";
import { isVisible, layerColor, layerStyle, reportLayers } from "./layers.js";
import { generators, layoutFocus, layoutsFor, loadLayout } from "./layout2d.js";
import { on, series, setFocus, state, status } from "./store.js";
import { bytes } from "./units.js";

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
// a wall's shade by its outward normal (nx, ny, 0), as SHADE lights a box's sides
const wallShade = (nx, ny) => {
    const sun = [0.6, -1, 1.4].map((v, _, all) => v / Math.hypot(...all));
    const fill = [-1, 0.8, 0.6].map((v, _, all) => v / Math.hypot(...all));
    return 0.28 + 0.11 + 0.5 * Math.max(0, nx * sun[0] + ny * sun[1]) + 0.12 * Math.max(0, nx * fill[0] + ny * fill[1]);
};
const tint = (rgb, shade) => `rgb(${Math.min(255, rgb[0] * shade) | 0},${Math.min(255, rgb[1] * shade) | 0},${Math.min(255, rgb[2] * shade) | 0})`;

export class Layout3DPanel {
    constructor(container, saved) {
        this.container = container;
        // the stack at its nominal heights, every box edged (no exaggeration or edges to set)
        this.config = { generator: null, ...(saved || {}), exaggeration: 1, edges: true };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.host = h("div.canvas-host", { style: { background: "var(--scene-bg)" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("cube", 28) }), h("strong", {}, "No layout"), h("span", {}, ""));
        this.host.append(this.emptyNote);
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
        // the generator is the block's own (ALIGN for analog, OpenROAD for digital): no choice offered
        if (!gens.includes(this.config.generator)) this.config.generator = gens[0] || null;
        const shown = series();
        const focus = layoutFocus(this.config.generator);
        const meta = focus ? layoutsFor(focus, this.config.generator) : null;
        this.toolbar.replaceChildren();
        if (shown.length > 1) {
            this.toolbar.append(
                titled("Series", select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))),
            );
        }
        // the layout's GDS size, what draws it (WebGL, else the CPU on a 2-D canvas) and the page's
        // memory; the stack at its nominal heights, every box's edges drawn
        const renderer = this.renderer ? "WebGL" : this.flat ? "CPU (no WebGL)" : null;
        const view = (name, label, title) => {
            const button = h(`button.icon-btn${this.view === name ? ".on" : ""}`, { title, onclick: () => (this.home(name), this.buildToolbar()) }, h("span", { html: icon(name, 14) }), label);
            return button;
        };
        this.toolbar.append(
            h("span.grow"),
            meta ? sizeMeter({ file: typeof meta.gdsBytes === "number" ? bytes(meta.gdsBytes) : "—", label: "GDS", renderer, held: () => this.heldBytes() }) : "",
            view("top", "Top", "View from the top, as the 2-D layout"),
            view("side", "Side", "View from the side: the layers' stack edge on"),
            view("iso", "Isometric", "View at an angle"),
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
            this.emptyNote.lastChild.textContent = !state.block ? "Select a block." : state.block.layoutNote || "No layout for the focused series.";
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
            // from the top, as the 2-D layout, until turned; the renderer is known now
            this.home("top");
            this.buildToolbar();
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
        // the left button turns the view, the middle (and the right) one pans it, the wheel zooms
        this.controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };
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
        // the CPU's drawing: every visible face rasterized with a depth test (a z-buffer of 1/w per
        // pixel), as the GPU draws it, so no face shows through one in front of it; edges drawn
        // depth-tested too, a little darker
        const ctx = this.flat;
        const width = this.canvas.width;
        const height = this.canvas.height;
        const image = ctx.createImageData(width, height);
        const pixels = image.data;
        const depth = new Float32Array(width * height);
        const backdrop = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue("--scene-bg").trim() || "#20242c").getHexString();
        const [br, bgreen, bb] = [0, 2, 4].map((at) => parseInt(backdrop.slice(at, at + 2), 16));
        for (let k = 0; k < pixels.length; k += 4) {
            pixels[k] = br;
            pixels[k + 1] = bgreen;
            pixels[k + 2] = bb;
            pixels[k + 3] = 255;
        }
        if (this.flatLayers) {
            const camera = this.camera;
            camera.updateMatrixWorld();
            const e = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
            const { x: px, y: py, z: pz } = camera.position;
            const near = camera.near;
            const project = (x, y, z) => {
                const w = e[3] * x + e[7] * y + e[11] * z + e[15];
                return [((e[0] * x + e[4] * y + e[8] * z + e[12]) / w * 0.5 + 0.5) * width, (0.5 - ((e[1] * x + e[5] * y + e[9] * z + e[13]) / w) * 0.5) * height, w];
            };
            // one triangle, flat colour [r, g, b] and opacity: a pixel drawn where nearer (1/w larger)
            const triangle = (a, b, c, color, alpha) => {
                const minX = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])));
                const maxX = Math.min(width - 1, Math.ceil(Math.max(a[0], b[0], c[0])));
                const minY = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])));
                const maxY = Math.min(height - 1, Math.ceil(Math.max(a[1], b[1], c[1])));
                const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
                if (!area || minX > maxX || minY > maxY) return;
                const ia = 1 / a[2];
                const ib = 1 / b[2];
                const ic = 1 / c[2];
                for (let y = minY; y <= maxY; y++) {
                    const sy = y + 0.5;
                    for (let x = minX; x <= maxX; x++) {
                        const sx = x + 0.5;
                        const w0 = ((b[0] - sx) * (c[1] - sy) - (b[1] - sy) * (c[0] - sx)) / area;
                        const w1 = ((c[0] - sx) * (a[1] - sy) - (c[1] - sy) * (a[0] - sx)) / area;
                        const w2 = 1 - w0 - w1;
                        if (w0 < 0 || w1 < 0 || w2 < 0) continue;
                        const iz = w0 * ia + w1 * ib + w2 * ic;
                        const at = y * width + x;
                        if (iz <= depth[at]) continue;
                        const k = at * 4;
                        if (alpha >= 1) {
                            depth[at] = iz;
                            pixels[k] = color[0];
                            pixels[k + 1] = color[1];
                            pixels[k + 2] = color[2];
                        } else {
                            pixels[k] += (color[0] - pixels[k]) * alpha;
                            pixels[k + 1] += (color[1] - pixels[k + 1]) * alpha;
                            pixels[k + 2] += (color[2] - pixels[k + 2]) * alpha;
                        }
                    }
                }
            };
            // a line, depth-tested with a little bias so it shows on its own face
            const line = (a, b, color) => {
                const steps = Math.ceil(Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]))) + 1;
                const ia = 1 / a[2];
                const ib = 1 / b[2];
                for (let s = 0; s <= steps; s++) {
                    const t = s / steps;
                    const x = Math.round(a[0] + (b[0] - a[0]) * t);
                    const y = Math.round(a[1] + (b[1] - a[1]) * t);
                    if (x < 0 || y < 0 || x >= width || y >= height) continue;
                    const iz = (ia + (ib - ia) * t) * 1.002;
                    const at = y * width + x;
                    if (iz < depth[at]) continue;
                    const k = at * 4;
                    pixels[k] = color[0];
                    pixels[k + 1] = color[1];
                    pixels[k + 2] = color[2];
                }
            };
            const shade = (rgb, factor) => rgb.map((v) => Math.min(255, v * factor));
            const quad = (points, rgb, factor, alpha, edges) => {
                if (points.some((point) => point[2] <= near)) return;
                const color = shade(rgb, factor);
                triangle(points[0], points[1], points[2], color, alpha);
                triangle(points[0], points[2], points[3], color, alpha);
                if (edges && alpha >= 1) {
                    const dark = shade(rgb, factor * 0.45);
                    for (let k = 0; k < 4; k++) line(points[k], points[(k + 1) % 4], dark);
                }
            };
            const zs = this.config.exaggeration;
            // opaque layers first, the translucent ones (wells) over them
            const layers = this.flatLayers.filter((layer) => isVisible(layer.key)).sort((a, b) => (b.alpha >= 1) - (a.alpha >= 1));
            for (const layer of layers) {
                const z0 = layer.z[0] * zs;
                const z1 = layer.z[1] * zs;
                const edges = this.config.edges;
                const r = layer.rects;
                for (let i = 0; i < r.length; i += 4) {
                    const x1 = r[i];
                    const y1 = r[i + 1];
                    const x2 = r[i + 2];
                    const y2 = r[i + 3];
                    const c = [project(x1, y1, z0), project(x2, y1, z0), project(x2, y2, z0), project(x1, y2, z0), project(x1, y1, z1), project(x2, y1, z1), project(x2, y2, z1), project(x1, y2, z1)];
                    if (pz > z1) quad([c[4], c[5], c[6], c[7]], layer.rgb, SHADE.top, layer.alpha, edges);
                    else if (pz < z0) quad([c[0], c[3], c[2], c[1]], layer.rgb, SHADE.bottom, layer.alpha, edges);
                    if (px > x2) quad([c[1], c[2], c[6], c[5]], layer.rgb, SHADE.px, layer.alpha, edges);
                    else if (px < x1) quad([c[3], c[0], c[4], c[7]], layer.rgb, SHADE.nx, layer.alpha, edges);
                    if (py > y2) quad([c[2], c[3], c[7], c[6]], layer.rgb, SHADE.py, layer.alpha, edges);
                    else if (py < y1) quad([c[0], c[1], c[5], c[4]], layer.rgb, SHADE.ny, layer.alpha, edges);
                }
                // a polygon: its walls (each edge facing the camera, lit by its outward normal) and its
                // top face, triangulated
                for (const ring of layer.polys) {
                    const contour = [];
                    for (let k = 0; k < ring.length; k += 2) contour.push(new THREE.Vector2(ring[k], ring[k + 1]));
                    const outward = THREE.ShapeUtils.isClockWise(contour) ? -1 : 1;
                    for (let k = 0; k < contour.length; k++) {
                        const a = contour[k];
                        const b = contour[(k + 1) % contour.length];
                        const length = Math.hypot(b.x - a.x, b.y - a.y);
                        if (!length) continue;
                        const nx = (outward * (b.y - a.y)) / length;
                        const ny = (-outward * (b.x - a.x)) / length;
                        if (nx * (px - a.x) + ny * (py - a.y) <= 0) continue;
                        quad([project(a.x, a.y, z0), project(b.x, b.y, z0), project(b.x, b.y, z1), project(a.x, a.y, z1)], layer.rgb, wallShade(nx, ny), layer.alpha, edges);
                    }
                    if (pz <= z1) continue;
                    const points = contour.map((point) => project(point.x, point.y, z1));
                    if (points.some((point) => point[2] <= near)) continue;
                    const color = shade(layer.rgb, SHADE.top);
                    for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(contour, [])) triangle(points[a], points[b], points[c], color, layer.alpha);
                    if (edges && layer.alpha >= 1) {
                        const dark = shade(layer.rgb, SHADE.top * 0.45);
                        for (let k = 0; k < points.length; k++) line(points[k], points[(k + 1) % points.length], dark);
                    }
                }
            }
        }
        ctx.putImageData(image, 0, 0);
    }

    // what the view holds (bytes): its geometry's arrays, the WebGL buffers or the CPU's layers and
    // depth buffer; the memory the browser needs for it where the browser does not say its own
    heldBytes() {
        let total = 0;
        if (this.flatLayers) {
            for (const layer of this.flatLayers) total += layer.rects.byteLength + layer.polys.reduce((sum, ring) => sum + ring.length * 8, 0);
            if (this.canvas) total += this.canvas.width * this.canvas.height * 8;  // the image and the depth buffer
        }
        this.group?.traverse((object) => {
            for (const attribute of Object.values(object.geometry?.attributes || {})) total += attribute.array.byteLength;
        });
        return total;
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

    // the view from the top (as the 2-D layout, y up), from its side (the stack's layers edge on,
    // from below the drawing's y) or at an angle (isometric)
    home(view = "top") {
        if (!this.camera || !this.extent) return;
        this.view = view;
        const distance = this.extent * 1.6;
        this.controls.target.set(0, 0, 0.5);
        if (view === "top") this.camera.position.set(0, -0.001, distance * 1.15);
        else if (view === "side") this.camera.position.set(0, -distance * 1.25, 0.5);
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
