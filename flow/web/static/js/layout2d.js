// The 2-D layout view: a canvas of the exported, merged layer geometry. One layout follows the
// focused series; "tiled" lays every selected series' layout out at one scale, a column per PDK
// and a row per case. Wheel zooms about the cursor, drag pans, right-drag (or shift-drag) zooms
// to a box, double-click fits; K measures (KLayout's ruler key), L toggles labels, F fits.

import { h, icon, select } from "./icons.js";
import { hatchTile, isVisible, layerColor, layerStyle, reportLayers, rgba, sortLayers } from "./layers.js";
import { fetchData, focusSeries, on, series, setFocus, state, status } from "./store.js";

export function layoutsFor(item, generator) {
    return (state.block?.layouts || []).find((layout) => layout.case === item.case && layout.pdk === item.pdk && layout.generator === generator) || null;
}

// the focused series, or where it has no layout the first shown series that has one
export function layoutFocus(generator) {
    const focus = focusSeries();
    if (!focus || layoutsFor(focus, generator)) return focus;
    return series().find((item) => layoutsFor(item, generator)) || focus;
}

// the row-cell tools first, then any other variant a block's layouts come in (metal layers, units)
export function generators() {
    const order = ["cic", "laygo", "align"];
    const present = [...new Set((state.block?.layouts || []).map((layout) => layout.generator))];
    return [...order.filter((generator) => present.includes(generator)), ...present.filter((generator) => !order.includes(generator)).sort()];
}

// the layout record in µm, one Float64Array of rectangles and the polygon rings per layer
export async function loadLayout(path) {
    const raw = await fetchData(path);
    if (raw.prepared) return raw.prepared;
    const scale = raw.dbu;
    const layers = raw.layers.map((layer) => ({
        key: layer.key,
        rects: Float64Array.from(layer.rects, (value) => value * scale),
        polys: layer.polys.map((rings) => rings.map((ring) => Float64Array.from(ring, (value) => value * scale))),
        count: layer.rects.length / 4 + layer.polys.length,
    }));
    raw.prepared = {
        cell: raw.cell,
        pdk: raw.pdk,
        bbox: raw.bbox.map((value) => value * scale),
        layers,
        labels: raw.labels.map((label) => ({ ...label, x: label.x * scale, y: label.y * scale })),
    };
    return raw.prepared;
}

function pathOf(layer, dx, dy) {
    const path = new Path2D();
    const rects = layer.rects;
    for (let i = 0; i < rects.length; i += 4) path.rect(rects[i] + dx, rects[i + 1] + dy, rects[i + 2] - rects[i], rects[i + 3] - rects[i + 1]);
    for (const rings of layer.polys) {
        for (const ring of rings) {
            path.moveTo(ring[0] + dx, ring[1] + dy);
            for (let i = 2; i < ring.length; i += 2) path.lineTo(ring[i] + dx, ring[i + 1] + dy);
            path.closePath();
        }
    }
    return path;
}

function inRing(ring, x, y) {
    let inside = false;
    for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
        const xi = ring[i];
        const yi = ring[i + 1];
        const xj = ring[j];
        const yj = ring[j + 1];
        if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
}

function niceLength(target) {
    const power = 10 ** Math.floor(Math.log10(target));
    for (const step of [1, 2, 5, 10]) if (step * power >= target) return step * power;
    return 10 * power;
}

function um(value) {
    return `${+value.toFixed(3)}`;
}

export class LayoutPanel {
    constructor(container, saved) {
        this.container = container;
        this.config = { generator: null, tiled: false, labels: true, ...(saved || {}) };
        this.view = null; // {k, ox, oy}
        this.tiles = [];
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.host = h("div.canvas-host", { tabindex: "0" });
        this.canvas = h("canvas");
        this.info = h("div.hud.info", { style: { display: "none" } });
        this.tip = h("div.hud.tip", { style: { display: "none" } });
        this.coords = h("div.hud.coords", { style: { display: "none" } });
        this.rubber = h("div.rubber", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("layout", 28) }), h("strong", {}, "No layout"), h("span", {}, ""));
        this.host.append(this.canvas, this.info, this.tip, this.coords, this.rubber, this.emptyNote);
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.host));
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.ruler = { on: false, a: null, b: null, fixed: false };
        this.bindInput();
        this.off = [
            on("block", () => this.refresh(true)),
            on("selection", () => this.refresh(false)),
            on("focus", () => this.refresh(false)),
            on("layers", () => this.draw()),
            on("theme", () => {
                this.patterns = null;
                this.draw();
            }),
            on("command", (command) => this.command(command)),
        ];
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(this.host);
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            this.resizeObserver.disconnect();
            reportLayers(this, null);
        });
        container.on("show", () => this.resize());
        if (state.block) this.refresh(true);
    }

    command(command) {
        if (!this.host.isConnected || this.host.offsetParent === null) return;
        if (command === "fit") this.fit();
        if (command === "ruler") this.toggleRuler();
        if (command === "labels") {
            this.config.labels = !this.config.labels;
            this.buildToolbar();
            this.draw();
        }
    }

    buildToolbar() {
        const gens = generators();
        if (!gens.includes(this.config.generator)) this.config.generator = gens[0] || null;
        const shown = series();
        const focus = layoutFocus(this.config.generator);
        this.toolbar.replaceChildren();
        if (!this.config.tiled && shown.length > 1) {
            this.toolbar.append(
                h(
                    "label.field",
                    {},
                    h("span", {}, "Series"),
                    select(
                        shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}${layoutsFor(item, this.config.generator) ? "" : " (none)"}` })),
                        focus?.key,
                        (value) => setFocus(value),
                    ),
                ),
            );
        }
        if (gens.length) {
            this.toolbar.append(
                h(
                    "label.field",
                    {},
                    h("span", {}, "Generator"),
                    select(gens.map((generator) => ({ value: generator, label: generator })), this.config.generator, (value) => {
                        this.config.generator = value;
                        this.refresh(true);
                    }),
                ),
            );
        }
        const button = (name, title, active, onclick, label) => {
            const element = h("button.icon-btn", { title, onclick }, h("span", { html: icon(name, 14) }), label || "");
            if (active) element.classList.add("on");
            return element;
        };
        this.toolbar.append(
            h("span.grow"),
            button("tiles", "Tile every selected series at one scale (PDK columns, case rows)", this.config.tiled, () => {
                this.config.tiled = !this.config.tiled;
                this.refresh(true);
            }, "Tiled"),
            button("tag", "Pin labels (L)", this.config.labels, () => this.command("labels")),
            button("ruler", "Measure (K); Esc clears", this.ruler.on, () => this.toggleRuler()),
            button("fit", "Fit (F, double-click)", false, () => this.fit()),
        );
    }

    async refresh(refit) {
        this.buildToolbar();
        const generator = this.config.generator;
        const shown = this.config.tiled ? series() : [layoutFocus(generator)].filter(Boolean);
        const wanted = shown.map((item) => ({ item, layout: layoutsFor(item, generator) })).filter((entry) => entry.layout);
        const signature = wanted.map((entry) => entry.layout.path).join(",");
        if (!wanted.length) {
            this.tiles = [];
            this.signature = "";
            reportLayers(this, null);
            const why = !state.block ? "Select a block." : !state.block.layouts.length ? "This block has no cached layouts." : "No layout for the selected series with this generator.";
            this.empty(true, why);
            this.draw();
            return;
        }
        this.empty(false);
        const token = (this.token = Symbol());
        let loaded;
        try {
            loaded = await Promise.all(wanted.map((entry) => loadLayout(entry.layout.path)));
        } catch (error) {
            status(`Layout: ${error.message}`, true);
            return;
        }
        if (token !== this.token) return;
        this.arrange(wanted, loaded);
        if (refit || signature !== this.signature) this.fit();
        this.signature = signature;
        const counts = {};
        for (const tile of this.tiles) for (const layer of tile.layout.layers) counts[layer.key] = (counts[layer.key] || 0) + layer.count;
        reportLayers(this, counts);
        this.updateInfo();
        this.draw();
    }

    // place the layouts: one column per PDK, one row per case, at one scale
    arrange(wanted, loaded) {
        const pdks = [...new Set(wanted.map((entry) => entry.item.pdk))];
        const cases = [...new Set(wanted.map((entry) => entry.item.case))];
        const widths = pdks.map(() => 0);
        const heights = cases.map(() => 0);
        wanted.forEach((entry, index) => {
            const [x1, y1, x2, y2] = loaded[index].bbox;
            const column = pdks.indexOf(entry.item.pdk);
            const row = cases.indexOf(entry.item.case);
            widths[column] = Math.max(widths[column], x2 - x1);
            heights[row] = Math.max(heights[row], y2 - y1);
        });
        const gap = 0.18 * Math.max(...widths, ...heights);
        const columnX = [];
        let x = 0;
        for (const width of widths) {
            columnX.push(x);
            x += width + gap;
        }
        const rowY = [];
        let y = 0;
        for (const height of heights) {
            rowY.push(y);
            y -= height + gap;
        }
        this.tiles = wanted.map((entry, index) => {
            const layout = loaded[index];
            const [x1, y1, , y2] = layout.bbox;
            const column = pdks.indexOf(entry.item.pdk);
            const row = cases.indexOf(entry.item.case);
            const dx = columnX[column] - x1;
            const dy = rowY[row] - y2;
            return {
                item: entry.item,
                meta: entry.layout,
                layout,
                dx,
                dy,
                bbox: layout.bbox.map((value, i) => value + (i % 2 ? dy : dx)),
                paths: Object.fromEntries(layout.layers.map((layer) => [layer.key, pathOf(layer, dx, dy)])),
            };
        });
    }

    updateInfo() {
        const tiles = this.tiles;
        if (!tiles.length) {
            this.info.style.display = "none";
            return;
        }
        this.info.style.display = "";
        if (tiles.length > 1) {
            this.info.replaceChildren(h("span", {}, `${tiles.length} layouts · ${this.config.generator}`));
            return;
        }
        const { meta, layout } = tiles[0];
        const [x1, y1, x2, y2] = layout.bbox;
        const size = meta.cell_um || [x2 - x1, y2 - y1];
        this.info.replaceChildren(
            h("span", {}, `${layout.cell} · ${layout.pdk} · ${meta.generator}`),
            h("span", {}, `${um(size[0])} × ${um(size[1])} µm`),
            meta.drc_violations === undefined || meta.drc_violations === null ? "" : h(meta.drc_violations ? "span.bad" : "span.ok", {}, `DRC ${meta.drc_violations}`),
            meta.lvs_correct === undefined || meta.lvs_correct === null ? "" : h(meta.lvs_correct ? "span.ok" : "span.bad", {}, meta.lvs_correct ? "LVS ✓" : "LVS ✗"),
            meta.note ? h("span", { title: meta.note }, meta.note.length > 48 ? `${meta.note.slice(0, 48)}…` : meta.note) : "",
        );
    }

    empty(show, message) {
        this.emptyNote.style.display = show ? "" : "none";
        if (message) this.emptyNote.lastChild.textContent = message;
        if (show) this.info.style.display = "none";
    }

    bounds() {
        if (!this.tiles.length) return null;
        const box = [Infinity, Infinity, -Infinity, -Infinity];
        for (const tile of this.tiles) {
            box[0] = Math.min(box[0], tile.bbox[0]);
            box[1] = Math.min(box[1], tile.bbox[1] - (this.tiles.length > 1 ? 0.1 * (tile.bbox[3] - tile.bbox[1]) : 0));
            box[2] = Math.max(box[2], tile.bbox[2]);
            box[3] = Math.max(box[3], tile.bbox[3]);
        }
        return box;
    }

    fit(box = this.bounds()) {
        const width = this.host.clientWidth;
        const height = this.host.clientHeight;
        if (!box || !width || !height) return;
        const [x1, y1, x2, y2] = box;
        // tiled: leave room for the case names on the left and the PDKs on top
        const left = this.tiles.length > 1 ? 90 : 0;
        const top = this.tiles.length > 1 ? 26 : 0;
        const k = 0.92 * Math.min((width - left) / Math.max(x2 - x1, 1e-3), (height - top) / Math.max(y2 - y1, 1e-3));
        this.view = { k, ox: left + (width - left) / 2 - (k * (x1 + x2)) / 2, oy: top + (height - top) / 2 + (k * (y1 + y2)) / 2 };
        this.draw();
    }

    resize() {
        const ratio = window.devicePixelRatio || 1;
        const width = this.host.clientWidth;
        const height = this.host.clientHeight;
        if (!width || !height) return;
        if (this.canvas.width !== Math.round(width * ratio) || this.canvas.height !== Math.round(height * ratio)) {
            const before = this.size;
            this.canvas.width = Math.round(width * ratio);
            this.canvas.height = Math.round(height * ratio);
            this.canvas.style.width = `${width}px`;
            this.canvas.style.height = `${height}px`;
            if (this.view && before) {
                this.view.ox += (width - before[0]) / 2;
                this.view.oy += (height - before[1]) / 2;
            }
            this.size = [width, height];
            this.patterns = null;
            if (!this.view) this.fit();
        }
        this.draw();
    }

    toWorld(px, py) {
        const { k, ox, oy } = this.view;
        return [(px - ox) / k, (oy - py) / k];
    }

    toScreen(x, y) {
        const { k, ox, oy } = this.view;
        return [ox + k * x, oy - k * y];
    }

    draw() {
        cancelAnimationFrame(this.frame);
        this.frame = requestAnimationFrame(() => this.paint());
    }

    paint() {
        const ctx = this.canvas.getContext("2d");
        const ratio = window.devicePixelRatio || 1;
        const width = this.canvas.width / ratio;
        const height = this.canvas.height / ratio;
        const root = getComputedStyle(document.documentElement);
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.fillStyle = root.getPropertyValue("--layout-bg").trim();
        ctx.fillRect(0, 0, width, height);
        if (!this.view || !this.tiles.length) return;
        const { k, ox, oy } = this.view;

        // grid at the scale bar's spacing
        const step = niceLength(110 / k);
        const minor = step / 5;
        if (minor * k >= 14) {
            ctx.strokeStyle = root.getPropertyValue("--layout-grid").trim();
            ctx.lineWidth = 1;
            ctx.beginPath();
            const [wx1, wy2] = this.toWorld(0, 0);
            const [wx2, wy1] = this.toWorld(width, height);
            for (let x = Math.ceil(wx1 / minor) * minor; x <= wx2; x += minor) {
                const sx = Math.round(ox + k * x) + 0.5;
                ctx.moveTo(sx, 0);
                ctx.lineTo(sx, height);
            }
            for (let y = Math.ceil(wy1 / minor) * minor; y <= wy2; y += minor) {
                const sy = Math.round(oy - k * y) + 0.5;
                ctx.moveTo(0, sy);
                ctx.lineTo(width, sy);
            }
            ctx.stroke();
        }

        const transform = new DOMMatrix([ratio * k, 0, 0, -ratio * k, ratio * ox, ratio * oy]);
        const inverse = transform.inverse();
        this.patterns = this.patterns || {};
        const keys = sortLayers(new Set(this.tiles.flatMap((tile) => Object.keys(tile.paths))));
        for (const key of keys) {
            if (!isVisible(key)) continue;
            const style = layerStyle(key);
            const color = layerColor(style);
            if (style.hatch && !this.patterns[key]) this.patterns[key] = ctx.createPattern(hatchTile(style, ratio), "repeat");
            for (const tile of this.tiles) {
                const path = tile.paths[key];
                if (!path) continue;
                ctx.setTransform(transform);
                if (style.alpha) {
                    ctx.fillStyle = rgba(color, style.alpha);
                    ctx.fill(path, "evenodd");
                }
                if (style.hatch) {
                    const pattern = this.patterns[key];
                    pattern.setTransform(inverse);
                    ctx.fillStyle = pattern;
                    ctx.fill(path, "evenodd");
                }
                if (style.outline) {
                    ctx.strokeStyle = color;
                    ctx.lineWidth = (style.width || 1) / k;
                    ctx.setLineDash((style.dash || []).map((d) => d / k));
                    ctx.stroke(path);
                    ctx.setLineDash([]);
                }
            }
        }
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

        // hovered shape
        if (this.hover) {
            const { tile, layer, index, poly } = this.hover;
            const path = new Path2D();
            if (poly === null) {
                const r = layer.rects;
                const [x1, y1] = this.toScreen(r[index] + tile.dx, r[index + 3] + tile.dy);
                const [x2, y2] = this.toScreen(r[index + 2] + tile.dx, r[index + 1] + tile.dy);
                path.rect(x1, y1, x2 - x1, y2 - y1);
            } else {
                for (const ring of layer.polys[poly]) {
                    ring.forEach((_, i) => {
                        if (i % 2) return;
                        const [sx, sy] = this.toScreen(ring[i] + tile.dx, ring[i + 1] + tile.dy);
                        if (i) path.lineTo(sx, sy);
                        else path.moveTo(sx, sy);
                    });
                    path.closePath();
                }
            }
            ctx.strokeStyle = root.getPropertyValue("--accent-bright").trim();
            ctx.lineWidth = 2;
            ctx.stroke(path);
        }

        // labels, on tiles large enough to read them
        if (this.config.labels) {
            ctx.font = "11px ui-monospace, 'SF Mono', 'DejaVu Sans Mono', monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const placed = []; // label boxes so far: a label on another moves below it
            for (const tile of this.tiles) {
                if ((tile.bbox[2] - tile.bbox[0]) * k < 150) continue;
                for (const label of tile.layout.labels) {
                    const layer = label.layer.replace(/\.PIN$/, "");
                    if (!isVisible(label.layer) && !isVisible(layer)) continue;
                    let [sx, sy] = this.toScreen(label.x + tile.dx, label.y + tile.dy);
                    if (sx < -50 || sy < -20 || sx > width + 50 || sy > height + 20) continue;
                    const text = label.text;
                    const textWidth = ctx.measureText(text).width;
                    const overlaps = (box) => Math.abs(box[0] - sx) < (box[2] + textWidth) / 2 + 6 && Math.abs(box[1] - sy) < 15;
                    for (let tries = 0; tries < 4 && placed.some(overlaps); tries++) sy += 15;
                    placed.push([sx, sy, textWidth]);
                    ctx.fillStyle = "rgba(31, 35, 43, 0.82)";
                    ctx.fillRect(sx - textWidth / 2 - 3, sy - 7, textWidth + 6, 14);
                    ctx.fillStyle = layerColor(layerStyle(layer));
                    ctx.fillText(text, sx, sy + 0.5);
                }
            }
        }

        // tiles: PDKs over the columns, cases beside the rows, each tile's size under it
        if (this.tiles.length > 1) {
            const columns = new Map();
            const rows = new Map();
            for (const tile of this.tiles) {
                const column = columns.get(tile.item.pdk) || [Infinity, -Infinity, -Infinity];
                columns.set(tile.item.pdk, [Math.min(column[0], tile.bbox[0]), Math.max(column[1], tile.bbox[2]), Math.max(column[2], tile.bbox[3])]);
                const row = rows.get(tile.item.case) || [Infinity, Infinity, -Infinity];
                rows.set(tile.item.case, [Math.min(row[0], tile.bbox[0]), Math.min(row[1], tile.bbox[1]), Math.max(row[2], tile.bbox[3])]);
            }
            ctx.font = "600 12px -apple-system, 'Segoe UI', sans-serif";
            ctx.fillStyle = root.getPropertyValue("--fg-secondary").trim();
            ctx.textBaseline = "bottom";
            ctx.textAlign = "center";
            for (const [pdk, [x1, x2, top]] of columns) {
                const [sx, sy] = this.toScreen((x1 + x2) / 2, top);
                ctx.fillText(pdk, sx, sy - 8);
            }
            ctx.textAlign = "right";
            ctx.textBaseline = "middle";
            for (const [name, [x1, y1, y2]] of rows) {
                const [sx, sy] = this.toScreen(x1, (y1 + y2) / 2);
                ctx.fillText(name, sx - 10, sy);
            }
            ctx.font = "11px ui-monospace, 'SF Mono', 'DejaVu Sans Mono', monospace";
            ctx.fillStyle = root.getPropertyValue("--fg-muted").trim();
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            for (const tile of this.tiles) {
                const [x1, y1, x2, y2] = tile.bbox;
                const text = `${um(x2 - x1)} × ${um(y2 - y1)}`;
                if (ctx.measureText(text).width > (x2 - x1) * k + 8) continue;
                const [sx, sy] = this.toScreen((x1 + x2) / 2, y1);
                ctx.fillText(text, sx, sy + 5);
            }
        }

        // ruler
        if (this.ruler.a && this.ruler.b) {
            const [ax, ay] = this.toScreen(...this.ruler.a);
            const [bx, by] = this.toScreen(...this.ruler.b);
            ctx.strokeStyle = "#EBCB8B";
            ctx.fillStyle = "#EBCB8B";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();
            for (const [x, y] of [[ax, ay], [bx, by]]) {
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fill();
            }
            const dx = this.ruler.b[0] - this.ruler.a[0];
            const dy = this.ruler.b[1] - this.ruler.a[1];
            const text = `${um(Math.hypot(dx, dy))} µm  (Δx ${um(dx)}, Δy ${um(dy)})`;
            ctx.font = "11px ui-monospace, 'SF Mono', 'DejaVu Sans Mono', monospace";
            const textWidth = ctx.measureText(text).width;
            const mx = (ax + bx) / 2;
            const my = (ay + by) / 2 - 14;
            ctx.fillStyle = "rgba(31, 35, 43, 0.9)";
            ctx.fillRect(mx - textWidth / 2 - 5, my - 9, textWidth + 10, 18);
            ctx.fillStyle = "#EBCB8B";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(text, mx, my);
        }

        // scale bar
        const length = niceLength(90 / k);
        const barWidth = length * k;
        ctx.fillStyle = "rgba(31, 35, 43, 0.78)";
        ctx.fillRect(10, height - 34, barWidth + 16, 24);
        ctx.strokeStyle = "#ECEFF4";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(18, height - 18);
        ctx.lineTo(18, height - 14);
        ctx.lineTo(18 + barWidth, height - 14);
        ctx.lineTo(18 + barWidth, height - 18);
        ctx.stroke();
        ctx.fillStyle = "#ECEFF4";
        ctx.font = "11px ui-monospace, 'SF Mono', 'DejaVu Sans Mono', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.fillText(`${um(length)} µm`, 18 + barWidth / 2, height - 20);
    }

    hit(px, py) {
        const [x, y] = this.toWorld(px, py);
        const keys = sortLayers(new Set(this.tiles.flatMap((tile) => Object.keys(tile.paths)))).reverse();
        for (const key of keys) {
            if (!isVisible(key) || key === "BND") continue;
            for (const tile of this.tiles) {
                const layer = tile.layout.layers.find((item) => item.key === key);
                if (!layer) continue;
                const lx = x - tile.dx;
                const ly = y - tile.dy;
                const r = layer.rects;
                for (let i = 0; i < r.length; i += 4) {
                    if (lx >= r[i] && lx <= r[i + 2] && ly >= r[i + 1] && ly <= r[i + 3]) return { tile, layer, index: i, poly: null, size: [r[i + 2] - r[i], r[i + 3] - r[i + 1]] };
                }
                for (let p = 0; p < layer.polys.length; p++) {
                    const [hull, ...holes] = layer.polys[p];
                    if (inRing(hull, lx, ly) && !holes.some((ring) => inRing(ring, lx, ly))) {
                        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
                        for (let i = 0; i < hull.length; i += 2) {
                            x1 = Math.min(x1, hull[i]);
                            x2 = Math.max(x2, hull[i]);
                            y1 = Math.min(y1, hull[i + 1]);
                            y2 = Math.max(y2, hull[i + 1]);
                        }
                        return { tile, layer, index: 0, poly: p, size: [x2 - x1, y2 - y1] };
                    }
                }
            }
        }
        return null;
    }

    toggleRuler() {
        this.ruler = { on: !this.ruler.on, a: null, b: null, fixed: false };
        this.host.classList.toggle("ruler", this.ruler.on);
        status(this.ruler.on ? "Ruler: click two points; Esc clears" : "Ruler off");
        this.buildToolbar();
        this.draw();
    }

    bindInput() {
        const host = this.host;
        let drag = null;
        const point = (event) => {
            const rect = host.getBoundingClientRect();
            return [event.clientX - rect.left, event.clientY - rect.top];
        };
        const snap = (value) => Math.round(value / 0.005) * 0.005;
        host.addEventListener("contextmenu", (event) => event.preventDefault());
        host.addEventListener("mouseenter", () => host.focus({ preventScroll: true }));
        host.addEventListener("wheel", (event) => {
            if (!this.view) return;
            event.preventDefault();
            const [px, py] = point(event);
            const factor = Math.exp(-event.deltaY * (event.deltaMode ? 0.05 : 0.0015));
            const { k, ox, oy } = this.view;
            const next = Math.min(Math.max(k * factor, 1e-3), 1e7);
            this.view = { k: next, ox: px - ((px - ox) * next) / k, oy: py - ((py - oy) * next) / k };
            this.draw();
        }, { passive: false });
        host.addEventListener("mousedown", (event) => {
            if (!this.view) return;
            const [px, py] = point(event);
            if (this.ruler.on && event.button === 0 && !event.shiftKey) {
                const world = this.toWorld(px, py).map(snap);
                if (!this.ruler.a || this.ruler.fixed) this.ruler = { on: true, a: world, b: world, fixed: false };
                else {
                    this.ruler.b = world;
                    this.ruler.fixed = true;
                }
                this.draw();
                return;
            }
            const box = event.button === 2 || (event.button === 0 && event.shiftKey);
            drag = { box, start: [px, py], view: { ...this.view } };
            if (!box) host.classList.add("panning");
        });
        window.addEventListener("mousemove", (event) => {
            if (!this.view || !host.isConnected) return;
            const [px, py] = point(event);
            const inside = px >= 0 && py >= 0 && px <= host.clientWidth && py <= host.clientHeight;
            if (drag) {
                const dx = px - drag.start[0];
                const dy = py - drag.start[1];
                if (drag.box) {
                    Object.assign(this.rubber.style, {
                        display: "",
                        left: `${Math.min(px, drag.start[0])}px`,
                        top: `${Math.min(py, drag.start[1])}px`,
                        width: `${Math.abs(dx)}px`,
                        height: `${Math.abs(dy)}px`,
                    });
                } else {
                    this.view = { ...drag.view, ox: drag.view.ox + dx, oy: drag.view.oy + dy };
                    this.draw();
                }
                return;
            }
            if (!inside) {
                this.coords.style.display = "none";
                if (this.hover) {
                    this.hover = null;
                    this.tip.style.display = "none";
                    this.draw();
                }
                return;
            }
            const [wx, wy] = this.toWorld(px, py);
            this.coords.textContent = `x ${wx.toFixed(3)}  y ${wy.toFixed(3)} µm`;
            this.coords.style.display = "";
            if (this.ruler.on && this.ruler.a && !this.ruler.fixed) {
                this.ruler.b = [snap(wx), snap(wy)];
                this.draw();
            }
            const hover = this.hit(px, py);
            const changed = hover?.layer !== this.hover?.layer || hover?.index !== this.hover?.index || hover?.poly !== this.hover?.poly || hover?.tile !== this.hover?.tile;
            this.hover = hover;
            if (hover) {
                const caption = this.tiles.length > 1 ? `${hover.tile.item.case} · ${hover.tile.item.pdk} · ` : "";
                this.tip.textContent = `${caption}${hover.layer.key} · ${um(hover.size[0])} × ${um(hover.size[1])} µm`;
                Object.assign(this.tip.style, { display: "", left: `${px}px`, top: `${py}px` });
            } else this.tip.style.display = "none";
            if (changed) this.draw();
        });
        window.addEventListener("mouseup", (event) => {
            if (!drag) return;
            const [px, py] = point(event);
            if (drag.box) {
                this.rubber.style.display = "none";
                if (Math.abs(px - drag.start[0]) > 6 && Math.abs(py - drag.start[1]) > 6) {
                    const [x1, y1] = this.toWorld(Math.min(px, drag.start[0]), Math.max(py, drag.start[1]));
                    const [x2, y2] = this.toWorld(Math.max(px, drag.start[0]), Math.min(py, drag.start[1]));
                    const box = [x1, y1, x2, y2];
                    const width = this.host.clientWidth;
                    const height = this.host.clientHeight;
                    const k = Math.min(width / (x2 - x1), height / (y2 - y1));
                    this.view = { k, ox: width / 2 - (k * (box[0] + box[2])) / 2, oy: height / 2 + (k * (box[1] + box[3])) / 2 };
                    this.draw();
                }
            } else if (Math.hypot(px - drag.start[0], py - drag.start[1]) < 3 && this.hover && this.tiles.length > 1) {
                setFocus(this.hover.tile.item.key);
            }
            host.classList.remove("panning");
            drag = null;
        });
        host.addEventListener("dblclick", () => this.fit());
        host.addEventListener("keydown", (event) => {
            if (event.target !== host) return;
            const key = event.key.toLowerCase();
            if (key === "f") this.fit();
            else if (key === "k") this.toggleRuler();
            else if (key === "l") this.command("labels");
            else if (key === "escape" && this.ruler.on) {
                this.ruler = { on: true, a: null, b: null, fixed: false };
                this.draw();
            } else if (key === "+" || key === "=" || key === "-") {
                const factor = key === "-" ? 1 / 1.4 : 1.4;
                const width = host.clientWidth / 2;
                const height = host.clientHeight / 2;
                const { k, ox, oy } = this.view;
                this.view = { k: k * factor, ox: width - (width - ox) * factor, oy: height - (height - oy) * factor };
                this.draw();
            } else return;
            event.preventDefault();
        });
    }
}
