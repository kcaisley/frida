// Layer styles on the generic layer keys every PDK's layout/tech.py maps (OD, PO, CO, M<n>,
// V<n>, NW, PP, NP, BND, M<n>.PIN): Nord colours, translucent fills with a screen-fixed hatch,
// the front end under the metals. Also the Layers panel, shared by the 2-D and 3-D views.

import { h, icon } from "./icons.js";
import { emit, on, recall, state, store } from "./store.js";

// M1, M2, ... and the vias above each
const METALS = ["#5E81AC", "#B48EAD", "#D08770", "#EBCB8B", "#8FBCBB", "#88C0D0", "#81A1C1", "#A3BE8C", "#BF616A"];

export function layerStyle(key) {
    if (key.endsWith(".PIN")) {
        const base = layerStyle(key.slice(0, -4));
        return { ...base, alpha: 0, hatch: null, outline: true, width: 2, dash: null, order: base.order + 0.5, visible: false, group: "pin", z: base.z };
    }
    let match = /^M(\d+)$/.exec(key);
    if (match) {
        const n = Number(match[1]);
        return { color: METALS[(n - 1) % METALS.length], alpha: 0.3, hatch: n % 2 ? "/" : "\\", outline: true, order: 10 + 2 * n, visible: true, group: "metal", z: metalZ(n) };
    }
    match = /^V(\d+)$/.exec(key);
    if (match) {
        const n = Number(match[1]);
        const below = metalZ(n);
        const above = metalZ(n + 1);
        return { color: METALS[n % METALS.length], alpha: 0.75, hatch: "x", outline: true, order: 11 + 2 * n, visible: true, group: "via", z: [below[1], above[0]] };
    }
    const fixed = {
        DNW: { color: "#81A1C1", alpha: 0.04, hatch: null, outline: true, dash: [6, 4], order: 0, visible: false, group: "well", z: [-0.12, -0.08] },
        NW: { color: "#8FBCBB", alpha: 0.07, hatch: null, outline: true, dash: [6, 4], order: 1, visible: true, group: "well", z: [-0.06, 0] },
        PP: { color: "#D08770", alpha: 0, hatch: null, outline: true, dash: [3, 3], order: 2, visible: false, group: "implant", z: null },
        NP: { color: "#88C0D0", alpha: 0, hatch: null, outline: true, dash: [3, 3], order: 2.1, visible: false, group: "implant", z: null },
        OD: { color: "#A3BE8C", alpha: 0.35, hatch: ".", outline: true, order: 4, visible: true, group: "fe", z: [0, 0.06] },
        PO: { color: "#BF616A", alpha: 0.45, hatch: "/", outline: true, order: 5, visible: true, group: "fe", z: [0.06, 0.14] },
        CO: { color: "ink", alpha: 0.85, hatch: null, outline: true, order: 6, visible: true, group: "via", z: [0.06, 0.3] },
        BND: { color: "ink", alpha: 0, hatch: null, outline: true, dash: [5, 4], order: 99, visible: true, group: "boundary", z: null },
    };
    if (fixed[key]) return fixed[key];
    return { color: "#8F9BB0", alpha: 0, hatch: null, outline: true, dash: [2, 3], order: 3, visible: false, group: "other", z: null };
}

// metal n's bottom and top (µm, nominal: an even stack, not the PDK's)
function metalZ(n) {
    const bottom = 0.3 + (n - 1) * 0.28;
    return [bottom, bottom + 0.14];
}

export function layerColor(style) {
    if (style.color !== "ink") return style.color;
    return getComputedStyle(document.documentElement).getPropertyValue("--layout-ink").trim() || "#d8dee9";
}

export function rgba(hex, alpha) {
    const value = hex.replace("#", "");
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function isVisible(key) {
    return key in state.layerVisible ? state.layerVisible[key] : layerStyle(key).visible;
}

export function setVisible(changes) {
    Object.assign(state.layerVisible, changes);
    store("layers", state.layerVisible);
    emit("layers");
}

// the layers each open view shows (2-D and 3-D panels report theirs), merged for the panel
const present = new Map();

export function reportLayers(source, counts) {
    if (counts && Object.keys(counts).length) present.set(source, counts);
    else present.delete(source);
    emit("layers-present");
}

function presentLayers() {
    const counts = {};
    for (const source of present.values()) for (const [key, count] of Object.entries(source)) counts[key] = Math.max(counts[key] || 0, count);
    return { keys: Object.keys(counts), counts };
}

export function sortLayers(keys) {
    return [...keys].sort((a, b) => layerStyle(a).order - layerStyle(b).order || a.localeCompare(b));
}

// an 8 px hatch tile in the layer's colour, at the device pixel ratio
export function hatchTile(style, ratio) {
    const size = Math.round(8 * ratio);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.strokeStyle = rgba(layerColor(style), 0.85);
    ctx.fillStyle = rgba(layerColor(style), 0.85);
    ctx.lineWidth = Math.max(1, ratio * 0.9);
    ctx.beginPath();
    if (style.hatch === "/" || style.hatch === "x") {
        ctx.moveTo(0, size);
        ctx.lineTo(size, 0);
        ctx.moveTo(-size / 2, size / 2);
        ctx.lineTo(size / 2, -size / 2);
        ctx.moveTo(size / 2, size * 1.5);
        ctx.lineTo(size * 1.5, size / 2);
    }
    if (style.hatch === "\\" || style.hatch === "x") {
        ctx.moveTo(0, 0);
        ctx.lineTo(size, size);
        ctx.moveTo(size / 2, -size / 2);
        ctx.lineTo(size * 1.5, size / 2);
        ctx.moveTo(-size / 2, size / 2);
        ctx.lineTo(size / 2, size * 1.5);
    }
    ctx.stroke();
    if (style.hatch === ".") {
        const dot = Math.max(1, ratio);
        ctx.fillRect(size / 4, size / 4, dot, dot);
        ctx.fillRect((3 * size) / 4, (3 * size) / 4, dot, dot);
    }
    return canvas;
}

function swatch(key) {
    const style = layerStyle(key);
    const canvas = h("canvas", { width: 56, height: 28 });
    const ctx = canvas.getContext("2d");
    const color = layerColor(style);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--layout-bg").trim() || "#20242c";
    ctx.fillRect(0, 0, 56, 28);
    if (style.alpha) {
        ctx.fillStyle = rgba(color, style.alpha);
        ctx.fillRect(0, 0, 56, 28);
    }
    if (style.hatch) {
        ctx.fillStyle = ctx.createPattern(hatchTile(style, 2), "repeat");
        ctx.fillRect(0, 0, 56, 28);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = style.width ? 4 : 2;
    ctx.setLineDash((style.dash || []).map((d) => d * 2));
    ctx.strokeRect(2, 2, 52, 24);
    return canvas;
}

export class LayersPanel {
    constructor(container) {
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        this.off = [
            on("layers-present", () => this.render()),
            on("layers", () => this.render()),
            on("theme", () => this.render()),
        ];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        this.present = presentLayers();
        const keys = sortLayers(this.present.keys).reverse();
        const group = (names) => Object.fromEntries(keys.map((key) => [key, names.includes(layerStyle(key).group)]));
        this.toolbar.replaceChildren(
            h("span.link", { onclick: () => setVisible(Object.fromEntries(keys.map((key) => [key, true]))) }, "All"),
            h("span.link", { onclick: () => setVisible(Object.fromEntries(keys.map((key) => [key, false]))) }, "None"),
            h("span.link", { onclick: () => setVisible(group(["metal", "via", "boundary"])) }, "Metals"),
            h("span.link", { onclick: () => setVisible(group(["fe", "well", "via", "boundary"])) }, "Devices"),
            h("span.link", {
                onclick: () => {
                    state.layerVisible = {};
                    store("layers", {});
                    emit("layers");
                },
            }, "Default"),
            h("span.grow"),
            h("span.muted", { title: "Alt-click a layer to show it alone" }, "alt-click: solo"),
        );
        this.body.replaceChildren();
        if (!keys.length) {
            this.body.append(h("div.empty", {}, h("span", { html: icon("layers", 28) }), h("strong", {}, "No layout shown"), h("span", {}, "Open a layout to list its layers.")));
            return;
        }
        for (const key of keys) {
            const box = h("input", { type: "checkbox" });
            box.checked = isVisible(key);
            const row = h("div.layer-row", { title: `${key}: ${layerStyle(key).group}` }, box, swatch(key), h("span.name", {}, key), h("span.count", {}, this.present.counts[key] ?? ""));
            if (!box.checked) row.classList.add("off");
            row.addEventListener("click", (event) => {
                if (event.altKey) {
                    setVisible(Object.fromEntries(keys.map((other) => [other, other === key])));
                    return;
                }
                if (event.target !== box) box.checked = !box.checked;
                setVisible({ [key]: box.checked });
            });
            this.body.append(row);
        }
    }
}

state.layerVisible = recall("layers", {});
