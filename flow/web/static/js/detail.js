// One sweep instance's own page (detail.html?block=<block>&id=<pdk>__<topology>__<sizing>): its
// parameters and metrics, its condition sweeps on the axes every instance of the block shares (so
// two pages compare at a glance), and the shared panels (layout, 3D, layers, schematic,
// waveforms) on the instance alone: the store holds a one-instance block they read as any other.

import { GoldenLayout } from "golden-layout";
import { h, icon } from "./icons.js";
import { LayersPanel } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { currentTheme, PAPERS, paperLayout, tone } from "./paper.js";
import { SchematicPanel } from "./panels.js";
import { COLORS, emit, on, state, store } from "./store.js";
import { TracesPanel } from "./traces.js";
import { fieldInfo, formatValue, siExponent } from "./units.js";

const query = new URLSearchParams(location.search);
const BLOCK = query.get("block");
const ID = query.get("id");
// the units the detail plots' labels end in that take an SI prefix
const SCALABLE = new Set(["s", "V", "A", "J", "W", "F", "Hz", "Ω", "C", "V/√Hz"]);
const PREFIXES = { "-18": "a", "-15": "f", "-12": "p", "-9": "n", "-6": "µ", "-3": "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T" };

const page = { instance: null, table: null };

async function fetchJson(path) {
    const response = await fetch(`data/${path}`);
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
}

function status(message, error = false) {
    emit("status", { message, error });
}

// ---- the summary ------------------------------------------------------------------------------

class SummaryPanel {
    constructor(container) {
        this.element = h("div.panel.summary");
        container.element.append(this.element);
        this.render();
        this.off = on("theme", () => this.render());
        container.on("destroy", () => this.off());
    }

    render() {
        const instance = page.instance;
        // one table, so the two sections' columns line up: the name, the number (right-aligned),
        // its unit
        const metricRows = Object.entries(instance.metrics).map(([name, value]) => {
            const info = fieldInfo(name);
            const text = formatValue(value, info);
            const unit = info.unit && text.includes(" ") ? text.slice(text.lastIndexOf(" ") + 1) : "";
            const number = unit ? text.slice(0, text.lastIndexOf(" ")) : text;
            return h("tr", {}, h("th", { title: name }, info.label), h("td.num", {}, number), h("td.unit", {}, unit));
        });
        const paramRows = Object.entries(instance.params).map(([name, value]) =>
            h("tr", {}, h("th.mono", { title: name }, name), h(typeof value === "number" ? "td.num" : "td.num.text", {}, value === null ? "—" : String(value)), h("td.unit", {}, "")),
        );
        const section = (title) => h("tr.section", {}, h("th", { colspan: "3" }, title));
        const layout = instance.layout;
        const layoutNote = !layout
            ? "Not laid out."
            : layout.error
              ? `ALIGN failed: ${layout.error.trim().split("\n").pop()}`
              : `ALIGN${layout.floorplan ? " (by the floorplan)" : ""}: ${layout.w_um.toFixed(2)} × ${layout.h_um.toFixed(2)} µm, DRC ${layout.drc_violations} violations, LVS ${layout.lvs_correct ? "correct" : "incorrect"}.`;
        const parts = [
            h("h1", {}, `${page.table?.title || BLOCK}: ${instance.topology} · ${instance.sizing} · ${instance.pdk}`),
            h("p.muted", {}, `Run ${page.table?.run || "?"}, characterized in ${instance.seconds ?? "?"} s. ${layoutNote}`),
            instance.error ? h("pre.error", {}, instance.error) : null,
            h("table.summary-table", {}, h("tbody", {}, section("Metrics"), metricRows, section("Parameters"), paramRows)),
        ];
        this.element.replaceChildren(...parts.filter(Boolean));
    }
}

// ---- the detail plots, on the block's shared axes ----------------------------------------------

function unitScale(label, limits) {
    const match = label.match(/\(([^)]+)\)$/);
    const unit = match?.[1];
    if (!unit || !SCALABLE.has(unit)) return { label, factor: 1 };
    const exponent = siExponent(limits.filter((value) => Number.isFinite(value)));
    return { label: label.replace(/\(([^)]+)\)$/, `(${PREFIXES[exponent]}${unit})`), factor: 10 ** -exponent };
}

function padded([low, high], log) {
    if (!Number.isFinite(low) || !Number.isFinite(high)) return undefined;
    if (log) return [Math.log10(low) - 0.05 * (Math.log10(high) - Math.log10(low) || 1), Math.log10(high) + 0.05 * (Math.log10(high) - Math.log10(low) || 1)];
    const span = high - low || Math.abs(high) || 1;
    return [low - 0.05 * span, high + 0.05 * span];
}

class PlotsPanel {
    constructor(container) {
        this.element = h("div.panel.detail-plots");
        container.element.append(this.element);
        this.off = on("theme", () => this.render());
        container.on("destroy", () => this.off());
        container.on("resize", () => this.element.querySelectorAll(".plot").forEach((plot) => Plotly.Plots.resize(plot)));
        this.render();
    }

    render() {
        const theme = currentTheme();
        const colors = PAPERS[theme];
        this.element.replaceChildren();
        if (!page.instance.details.length) {
            this.element.append(h("div.empty", {}, h("strong", {}, "No condition sweeps"), h("span", {}, page.instance.error ? "The characterization failed." : "")));
            return;
        }
        for (const detail of page.instance.details) {
            const shared = page.table?.details?.[detail.name] || { x: [], y: [] };
            const x = unitScale(detail.x_label, shared.x);
            const y = unitScale(detail.y_label, shared.y);
            const traces = Object.entries(detail.series).map(([name, values], index) => ({
                type: "scatter",
                mode: "lines+markers",
                name,
                x: detail.x.map((value) => (value === null ? null : value * x.factor)),
                y: values.map((value) => (value === null ? null : value * y.factor)),
                line: { color: tone(COLORS[index % COLORS.length], theme), width: 2 },
                marker: { size: 6 },
            }));
            const layout = paperLayout(detail.title, x.label, y.label, detail.x_log, detail.y_log, traces.length > 1 ? traces.length : 0, theme);
            layout.title.font.size = 13;
            layout.margin = { l: 64, r: 12, t: 34, b: 46 };
            layout.xaxis.range = padded(shared.x.map((value) => value * x.factor), detail.x_log);
            layout.yaxis.range = padded(shared.y.map((value) => value * y.factor), detail.y_log);
            layout.legend.font = { size: 11, color: colors.ink };
            const element = h("div.plot");
            this.element.append(element);
            Plotly.newPlot(element, traces, layout, { displayModeBar: false, responsive: true });
        }
    }
}

// ---- the page ---------------------------------------------------------------------------------

const PANELS = {
    summary: { title: "Summary", make: (container) => new SummaryPanel(container) },
    plots: { title: "Condition sweeps", make: (container) => new PlotsPanel(container) },
    layout: { title: "Layout", make: (container, saved) => new LayoutPanel(container, saved) },
    layout3d: { title: "3D", make: (container, saved) => new Layout3DPanel(container, saved) },
    layers: { title: "Layers", make: (container) => new LayersPanel(container) },
    schematic: { title: "Schematic", make: (container, saved) => new SchematicPanel(container, saved) },
    traces: { title: "Waveforms", make: (container, saved) => new TracesPanel(container, saved) },
};

const component = (type) => ({ type: "component", componentType: type, title: PANELS[type].title, componentState: {} });

const LAYOUT = {
    settings: { showPopoutIcon: false, popoutWholeStack: false, reorderEnabled: true },
    dimensions: { borderWidth: 4, headerHeight: 28, minItemHeight: 90, minItemWidth: 180 },
    header: { popout: false },
    root: {
        type: "row",
        content: [
            { type: "column", width: 15, content: [{ type: "stack", content: [component("summary")] }] },
            {
                type: "column",
                width: 47,
                content: [
                    { type: "stack", height: 55, content: [component("plots")] },
                    { type: "stack", height: 45, content: [component("traces")] },
                ],
            },
            {
                type: "column",
                width: 38,
                content: [
                    { type: "stack", height: 60, content: [component("layout"), component("layout3d")] },
                    { type: "stack", height: 40, content: [component("schematic"), component("layers")] },
                ],
            },
        ],
    },
};

// a one-instance block: its layout, schematic and waveform index under data/sweep/<block>/<id>/
function shimBlock(instance) {
    const name = `sweep/${BLOCK}/${ID}`;
    const layout = instance.layout;
    state.catalog = { pdks: [instance.pdk], blocks: [] };
    state.block = {
        name,
        title: `${instance.topology} · ${instance.sizing}`,
        pdks: [instance.pdk],
        cases: { [ID]: { label: `${instance.topology} · ${instance.sizing}` } },
        layouts: layout?.file ? [{ case: ID, pdk: instance.pdk, generator: "align", path: layout.file, cell: instance.topology }] : [],
        schematics: layout?.schematic ? [{ case: ID, pdk: instance.pdk, path: layout.schematic, netlist: layout.netlist_file }] : [],
        datasets: [],
    };
    state.pdks = new Set([instance.pdk]);
    state.cases = new Set([ID]);
    state.focus = `${instance.pdk}|${ID}`;
}

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    store("theme", theme);
    emit("theme", theme);
    buildToolbar();
}

function buildToolbar() {
    const theme = document.documentElement.dataset.theme;
    const instance = page.instance;
    const tool = (name, title, onclick, label) => h("button.tool-btn", { title, onclick }, h("span", { html: icon(name, 16) }), label ? h("span", {}, label) : null);
    document.getElementById("toolbar").replaceChildren(
        h("a.tool-btn", { href: "index.html", title: "Back to the design space" }, h("span", {}, "← Design space")),
        h("div.tool-sep"),
        h("span.brand", {}, h("span", { html: icon("chip", 16) }), instance ? `${page.table?.title || BLOCK}: ${instance.topology} · ${instance.sizing} · ${instance.pdk}` : ID),
        h("span.spacer"),
        tool("fit", "Fit the layout (F)", () => emit("command", "fit")),
        tool("ruler", "Measure (K)", () => emit("command", "ruler")),
        tool("tag", "Layout labels (L)", () => emit("command", "labels")),
        h("div.tool-sep"),
        tool(theme === "dark" ? "sun" : "moon", "Theme (T)", () => setTheme(theme === "dark" ? "light" : "dark")),
    );
}

async function main() {
    const bar = document.getElementById("status-bar");
    const message = h("span.msg", {}, "Loading…");
    const cursor = h("span.cell", {}, "");
    bar.replaceChildren(h("span.cell", {}, h("span.dot"), "instance"), message, cursor);
    on("status", ({ message: text, error }) => {
        message.textContent = text;
        message.classList.toggle("err", Boolean(error));
    });
    on("cursor", (text) => {
        cursor.textContent = text;
    });
    window.addEventListener("keydown", (event) => {
        const target = event.target;
        if (event.ctrlKey || event.metaKey || target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return;
        const key = event.key.toLowerCase();
        if (key === "t") setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
        else if (key === "f") emit("command", "fit");
        else if (key === "k") emit("command", "ruler");
        else if (key === "l") emit("command", "labels");
        else return;
        event.preventDefault();
    });
    const loading = document.getElementById("loading");
    try {
        [page.instance, page.table] = await Promise.all([fetchJson(`sweep/${BLOCK}/${ID}.json`), fetchJson(`sweep/${BLOCK}.json`).catch(() => null)]);
    } catch (error) {
        loading.replaceChildren(h("strong", {}, "No such instance"), h("span.mono.muted", {}, error.message));
        return;
    }
    document.title = `${page.instance.topology} · ${page.instance.sizing} · ${page.instance.pdk}`;
    shimBlock(page.instance);
    buildToolbar();
    const container = document.getElementById("gl-container");
    const layout = new GoldenLayout(container);
    for (const [type, panel] of Object.entries(PANELS)) layout.registerComponentFactoryFunction(type, (glContainer, saved) => panel.make(glContainer, saved));
    layout.loadLayout(LAYOUT);
    new ResizeObserver(() => layout.updateRootSize?.() ?? layout.updateSize?.()).observe(container);
    emit("block", state.block);
    emit("selection");
    status(page.instance.error ? "The characterization failed: see the summary." : "Ready");
    loading.classList.add("done");
}

main();
