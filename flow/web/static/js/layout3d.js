// The 3-D layout view (three.js): every visible layer of the focused layout extruded between its
// nominal heights (an even stack, the same for every PDK: the exported geometry carries no
// thicknesses), with an adjustable vertical exaggeration. Drag orbits, right-drag pans, wheel
// zooms.

import { h, icon, select } from "./icons.js";
import { isVisible, layerColor, layerStyle, reportLayers } from "./layers.js";
import { generators, layoutFocus, layoutsFor, loadLayout } from "./layout2d.js";
import { on, series, setFocus, state, status } from "./store.js";

let THREE = null;
let OrbitControls = null;
let mergeGeometries = null;

async function three() {
    if (!THREE) {
        THREE = await import("three");
        ({ OrbitControls } = await import("three/addons/controls/OrbitControls.js"));
        ({ mergeGeometries } = await import("three/addons/utils/BufferGeometryUtils.js"));
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

export class Layout3DPanel {
    constructor(container, saved) {
        this.container = container;
        this.config = { generator: null, exaggeration: 4, edges: true, ...(saved || {}) };
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
        if (shown.length) {
            this.toolbar.append(
                h("label.field", {}, h("span", {}, "Series"), select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))),
            );
        }
        if (gens.length) {
            this.toolbar.append(
                h("label.field", {}, h("span", {}, "Generator"), select(gens.map((generator) => ({ value: generator, label: generator })), this.config.generator, (value) => {
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
            this.emptyNote.lastChild.textContent = !state.block ? "Select a block." : "No layout for the focused series with this generator.";
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
            this.info.replaceChildren(h("span", {}, `${layout.cell} · ${layout.pdk} · ${meta.generator}`), h("span", {}, "nominal stack"));
            this.home(false);
        } catch (error) {
            status(`3-D view: ${error.message}`, true);
        }
    }

    ensureRenderer() {
        if (this.renderer) return;
        try {
            this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
        } catch (error) {
            throw new Error("WebGL is not available in this browser");
        }
        this.renderer.setPixelRatio(window.devicePixelRatio || 1);
        this.host.prepend(this.renderer.domElement);
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(35, 1, 0.01, 1e4);
        this.camera.up.set(0, 0, 1);
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.12;
        this.controls.addEventListener("change", () => this.render());
        this.controls.addEventListener("start", () => this.animate(true));
        this.controls.addEventListener("end", () => this.animate(false));
        this.scene.add(new THREE.HemisphereLight(0xeceff4, 0x2e3440, 1.1));
        const sun = new THREE.DirectionalLight(0xffffff, 1.6);
        sun.position.set(0.6, -1, 1.4);
        this.scene.add(sun);
        const fill = new THREE.DirectionalLight(0x88c0d0, 0.5);
        fill.position.set(-1, 0.8, 0.6);
        this.scene.add(fill);
        this.applyTheme();
        this.resize();
    }

    animate(running) {
        this.running = running;
        const tick = () => {
            if (!this.renderer) return;
            const moving = this.controls.update();
            this.renderer.render(this.scene, this.camera);
            if (this.running || moving) requestAnimationFrame(tick);
        };
        if (running) requestAnimationFrame(tick);
    }

    clear() {
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
        if (this.group) this.clear();
        const [x1, y1, x2, y2] = layout.bbox;
        const cx = (x1 + x2) / 2;
        const cy = (y1 + y2) / 2;
        this.extent = Math.max(x2 - x1, y2 - y1);
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
            const material = new THREE.MeshStandardMaterial({
                color,
                roughness: style.group === "metal" ? 0.42 : 0.7,
                metalness: style.group === "metal" || style.group === "via" ? 0.35 : 0.05,
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
        const base = new THREE.Mesh(
            new THREE.PlaneGeometry((x2 - x1) * 1.15, (y2 - y1) * 1.15),
            new THREE.MeshStandardMaterial({ color: 0x3b4252, roughness: 0.9, metalness: 0, transparent: true, opacity: 0.55 }),
        );
        base.position.z = -0.13;
        this.group.add(base);
        this.group.scale.z = this.config.exaggeration;
        this.scene.add(this.group);
        reportLayers(this, Object.fromEntries(layout.layers.map((layer) => [layer.key, layer.count])));
        this.applyVisibility();
    }

    applyVisibility() {
        for (const [key, { holder, lines }] of Object.entries(this.layers || {})) {
            holder.visible = isVisible(key);
            lines.visible = this.config.edges;
        }
        this.render();
    }

    applyTheme() {
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
        if (!this.renderer) return;
        this.renderer.render(this.scene, this.camera);
        const link = document.createElement("a");
        link.download = `${this.path?.split("/").pop()?.replace(".json", "") || "layout"}_3d.png`;
        link.href = this.renderer.domElement.toDataURL("image/png");
        link.click();
    }

    resize() {
        if (!this.renderer) return;
        const width = this.host.clientWidth;
        const height = this.host.clientHeight;
        if (!width || !height) return;
        this.renderer.setSize(width, height);
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.render();
    }

    render() {
        if (this.renderer && !this.running) this.renderer.render(this.scene, this.camera);
    }
}
