// The Explorer: one sweep instance's own page (detail.html?block=<block>&id=<pdk>__<topology>__<sizing>): its
// parameters and metrics, its condition sweeps (each plot scaled to its own data), and the shared
// panels (layout, 3D, layers, schematic, netlist, waveforms) on the instance alone: the store holds
// a one-instance block they read as any other.
//
// The Comparer: several instances (detail.html?block=<block>&ids=<id>,<id>,..., the Assembler's pins): their
// parameters and metrics in one table, a column each, and their condition sweeps overlaid, an
// instance a colour; no layout, schematic or waveforms.

import { GoldenLayout } from "golden-layout";
import { h, toast } from "./icons.js";
import { LayersPanel } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { currentTheme, PAPERS, paperLayout, tone } from "./paper.js";
import { SchematicPanel } from "./panels.js";
import { COLORS, DASHES, emit, on, recall, state, store } from "./store.js";
import { TracesPanel } from "./traces.js";
import { fieldInfo, scaledUnit, siExponent } from "./units.js";

const query = new URLSearchParams(location.search);
const BLOCK = query.get("block");
const IDS = (query.get("ids") || query.get("id") || "").split(",").filter(Boolean);
const ID = IDS[0];
const COMPARE = IDS.length > 1;
// the units the detail plots' labels end in that take an SI prefix
const SCALABLE = new Set(["s", "V", "A", "J", "W", "F", "Hz", "Ω", "C", "V/√Hz"]);
const PREFIXES = { "-18": "a", "-15": "f", "-12": "p", "-9": "n", "-6": "µ", "-3": "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T" };
// a family of counted paths is drawn in this many weights, the most taken boldest
const PATH_LEVELS = 8;

const page = { instance: null, instances: [] };

async function fetchJson(path) {
    const response = await fetch(`data/${path}`);
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
}

// an instance's colour on the compare page
const colorOf = (index, theme) => tone(COLORS[index % COLORS.length], theme);

// an instance's name on the compare page: its topology and sizing, its PDK where they differ
function labelOf(instance) {
    const pdks = new Set(page.instances.map((item) => item.pdk));
    return [instance.topology, instance.sizing, ...(pdks.size > 1 ? [instance.pdk] : [])].join(" · ");
}

// a number at its row's SI prefix to 0.001 of it (whole numbers as they are), as the explorer's
// table shows them
function formatted(value, exponent) {
    if (typeof value !== "number" || !Number.isFinite(value)) return value === null || value === undefined ? "—" : String(value);
    return Number.isInteger(value) ? String(value) : (value / 10 ** exponent).toFixed(3).replace(/^-(0\.0*)$/, "$1");
}

// ---- the summary ------------------------------------------------------------------------------

class SummaryPanel {
    constructor(container) {
        this.element = h("div.panel.summary");
        container.element.append(this.element);
        this.onlyDifferences = recall("compare.differences", true);
        this.render();
        this.off = on("theme", () => this.render());
        container.on("destroy", () => this.off());
    }

    render() {
        this.element.replaceChildren(...(COMPARE ? this.compared() : this.single()).filter(Boolean));
    }

    single() {
        const instance = page.instance;
        // one table, so the two sections' columns line up: the name, the number (right-aligned),
        // its unit
        const metricRows = Object.entries(instance.metrics).map(([name, value]) => {
            const info = fieldInfo(name);
            const exponent = info.scalable && typeof value === "number" && !Number.isInteger(value) ? siExponent([value]) : 0;
            const number = formatted(value, exponent);
            return h("tr", {}, h("th", { title: name }, info.label), h("td.num", {}, number), h("td.unit", {}, number === "—" ? "" : scaledUnit(info, exponent)));
        });
        const paramRows = Object.entries(instance.params).map(([name, value]) =>
            h("tr", {}, h("th.mono", { title: name }, name), h(typeof value === "number" ? "td.num" : "td.num.text", {}, value === null ? "—" : String(value)), h("td.unit", {}, "")),
        );
        const section = (title) => h("tr.section", {}, h("th", { colspan: "3" }, title));
        const row = (name, number, unit = "") => h("tr", {}, h("th", {}, name), h("td.num", {}, number), h("td.unit", {}, unit));
        const layout = instance.layout;
        const layoutRows = !layout
            ? [row("Layout", "none")]
            : layout.error
              ? [row("ALIGN", "failed")]
              : [
                  row("Size", `${layout.w_um.toFixed(3)} × ${layout.h_um.toFixed(3)}`, "µm"),
                  // the blocks' own layouts side by side (a behavioral ADC): nothing routed or signed off
                  ...(layout.blocks
                      ? [row("Placed", "blocks, unconnected"), row("Signoff", "none")]
                      : [
                            row("Placed", layout.floorplan ? "by floorplan" : "ALIGN alone"),
                            row("DRC", layout.drc_violations ? `${layout.drc_violations} violations` : "clean"),
                            row("LVS", layout.lvs_correct ? "correct" : "incorrect"),
                        ]),
              ];
        return [
            instance.error ? h("pre.error", {}, instance.error) : null,
            h("table.summary-table", {}, h("tbody", {}, section("Parameters"), paramRows, section("Metrics"), metricRows, section("Layout"), layoutRows)),
        ];
    }

    // a column an instance: the parameters (those that differ, unless asked for all), every metric
    // at one SI prefix a row
    compared() {
        const instances = page.instances;
        const theme = currentTheme();
        const span = instances.length + 2;
        const section = (title) => h("tr.section", {}, h("th", { colspan: String(span) }, title));
        const names = (key) => [...new Set(instances.flatMap((instance) => Object.keys(instance[key] || {})))];
        const differs = (values) => new Set(values.map((value) => JSON.stringify(value ?? null))).size > 1;
        const paramRows = names("params")
            .map((name) => [name, instances.map((instance) => instance.params?.[name])])
            .filter(([, values]) => !this.onlyDifferences || differs(values))
            .map(([name, values]) =>
                h(
                    `tr${differs(values) ? ".differs" : ""}`,
                    {},
                    h("th.mono", { title: name }, name),
                    values.map((value) => h(typeof value === "number" ? "td.num" : "td.num.text", {}, value === null || value === undefined ? "—" : String(value))),
                    h("td.unit", {}, ""),
                ),
            );
        const metricRows = names("metrics").map((name) => {
            const info = fieldInfo(name);
            const values = instances.map((instance) => instance.metrics?.[name]);
            const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value));
            const exponent = info.scalable && finite.length ? siExponent(finite) : 0;
            return h(
                `tr${differs(values) ? ".differs" : ""}`,
                {},
                h("th", { title: name }, info.label),
                values.map((value) => h("td.num", {}, formatted(value, exponent))),
                h("td.unit", {}, scaledUnit(info, exponent)),
            );
        });
        const failed = instances.some((instance) => instance.error);
        const errorRow = failed
            ? [h("tr.error-row", {}, h("th", {}, "Error"), instances.map((instance) => h("td.text", { title: instance.error || "" }, instance.error ? (instance.error.trim().split("\n").pop() || "failed") : "—")), h("td.unit", {}, ""))]
            : [];
        const head = h(
            "tr",
            {},
            h("th", {}, ""),
            instances.map((instance, index) =>
                h(
                    "th.instance",
                    {},
                    h("span.swatch", { style: { background: colorOf(index, theme) } }),
                    h("a", { href: `detail.html?block=${encodeURIComponent(BLOCK)}&id=${encodeURIComponent(instance.id)}`, target: "_blank", title: "Open this instance alone" }, labelOf(instance)),
                ),
            ),
            h("th", {}, ""),
        );
        const toggle = h("label.check", {}, h("input", { type: "checkbox", checked: this.onlyDifferences }), "Only the parameters that differ");
        toggle.querySelector("input").addEventListener("change", (event) => {
            this.onlyDifferences = event.target.checked;
            store("compare.differences", this.onlyDifferences);
            this.render();
        });
        return [
            h("div.compare-controls", {}, toggle),
            h("table.summary-table.compare", {}, h("thead", {}, head), h("tbody", {}, errorRow, section("Parameters"), paramRows, section("Metrics"), metricRows)),
        ];
    }
}

// ---- the detail plots, each on its own data -----------------------------------------------------

function unitScale(label, values) {
    const match = label.match(/\(([^)]+)\)$/);
    const unit = match?.[1];
    if (!unit || !SCALABLE.has(unit)) return { label, factor: 1 };
    const exponent = siExponent(values.filter((value) => Number.isFinite(value)));
    return { label: label.replace(/\(([^)]+)\)$/, `(${PREFIXES[exponent]}${unit})`), factor: 10 ** -exponent };
}

// a family of counted step lines (the ADC's decision paths) as a few traces, each the paths of one
// weight joined by gaps: the more conversions took a path, the bolder and more opaque it is
function pathTraces(detail, x, y, color, legend) {
    const most = Math.max(...detail.paths.map((path) => path.count));
    const levels = Array.from({ length: PATH_LEVELS }, () => ({ xs: [], ys: [], count: 0, paths: 0 }));
    for (const path of detail.paths) {
        const weight = most > 1 ? Math.log(path.count) / Math.log(most) : 1;
        const level = levels[Math.min(PATH_LEVELS - 1, Math.round(weight * (PATH_LEVELS - 1)))];
        level.xs.push(...detail.x.map((value) => value * x.factor), null);
        level.ys.push(...path.y.map((value) => (value === null ? null : value * y.factor)), null);
        level.count += path.count;
        level.paths += 1;
    }
    const total = detail.paths.reduce((sum, path) => sum + path.count, 0);
    return levels
        .map((level, index) => ({ level, weight: index / (PATH_LEVELS - 1) }))
        .filter(({ level }) => level.paths)
        .map(({ level, weight }, index) => ({
            type: "scatter",
            mode: "lines",
            x: level.xs,
            y: level.ys,
            connectgaps: false,
            line: { color, width: 0.8 + 2.6 * weight, shape: "hv" },
            opacity: 0.18 + 0.82 * weight,
            name: legend?.name || "paths",
            legendgroup: legend?.group,
            showlegend: Boolean(legend) && index === 0,
            hovertemplate: `${level.paths} path${level.paths > 1 ? "s" : ""}, ${level.count} of ${total} conversions<extra></extra>`,
        }));
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
        const instances = page.instances;
        // every detail any instance has, in the first one's order
        const names = [...new Set(instances.flatMap((instance) => instance.details.map((detail) => detail.name)))];
        if (!names.length) {
            this.element.append(h("div.empty", {}, h("strong", {}, "No condition sweeps"), h("span", {}, instances.some((instance) => instance.error) ? "The characterization failed." : "")));
            return;
        }
        for (const name of names) {
            const entries = instances
                .map((instance, index) => ({ instance, index, detail: instance.details.find((detail) => detail.name === name) }))
                .filter((entry) => entry.detail);
            const first = entries[0].detail;
            // a figure the analysis plots drew (an SVG under build/sweep/): shown as it is, side by side
            if (first.figure) {
                this.element.append(
                    h(
                        "figure.figure-card",
                        {},
                        h("figcaption", {}, first.title),
                        h(
                            "div.figure-row",
                            {},
                            entries.map(({ instance, detail }) => {
                                const src = `api/figure?path=${encodeURIComponent(detail.figure)}`;
                                return h("a", { href: src, target: "_blank", title: "Open full size" }, COMPARE ? h("span.figure-label", {}, labelOf(instance)) : null, h("img", { src, loading: "lazy", alt: detail.title }));
                            }),
                        ),
                    ),
                );
                continue;
            }
            // a map (detail.grid): one per instance, side by side when compared
            if (first.grid?.z) {
                const row = h("div.map-row");
                this.element.append(h("div.map-card", {}, h("div.map-title", {}, first.title), row));
                for (const { instance, index, detail } of entries) this.map(row, detail, COMPARE ? labelOf(instance) : null, index, theme);
                continue;
            }
            // SI prefixes from the values plotted
            const xs = entries.flatMap(({ detail }) => detail.x);
            const ys = entries.flatMap(({ detail }) => [...Object.values(detail.series).flat(), ...(detail.paths || []).flatMap((path) => path.y)]);
            const x = unitScale(first.x_label, xs);
            const y = unitScale(first.y_label, ys);
            // a condition sweep's few points marked; a long series (a code axis, a spectrum) a thin line
            const dense = entries.some(({ detail }) => detail.x.length > 100);
            const traces = [];
            for (const { instance, index, detail } of entries) {
                const group = COMPARE ? instance.id : undefined;
                if (detail.paths?.length) {
                    traces.push(...pathTraces(detail, x, y, COMPARE ? colorOf(index, theme) : colorOf(0, theme), COMPARE ? { name: labelOf(instance), group } : null));
                }
                Object.entries(detail.series).forEach(([series, values], j) =>
                    traces.push({
                        type: "scatter",
                        mode: dense ? "lines" : "lines+markers",
                        // compared: an instance a colour, its series by dash
                        name: COMPARE ? (Object.keys(detail.series).length > 1 ? `${labelOf(instance)} · ${series}` : labelOf(instance)) : series,
                        legendgroup: group,
                        x: detail.x.map((value) => (value === null ? null : value * x.factor)),
                        y: values.map((value) => (value === null ? null : value * y.factor)),
                        line: { color: colorOf(COMPARE ? index : j, theme), width: dense ? 1.2 : 2, dash: COMPARE ? DASHES[j % DASHES.length] : "solid" },
                        marker: { size: 6 },
                    }),
                );
            }
            const legendEntries = traces.filter((trace) => trace.showlegend !== false).length;
            const layout = paperLayout(first.title, x.label, y.label, first.x_log, first.y_log, legendEntries > 1 ? legendEntries : 0, theme);
            layout.title.font.size = 13;
            layout.margin = { l: 64, r: 12, t: 34, b: 46 };
            layout.legend.font = { size: 11, color: colors.ink };
            const element = h("div.plot");
            this.element.append(element);
            Plotly.newPlot(element, traces, layout, { displayModeBar: false, responsive: true });
        }
    }
}

// a map's colours: the theme's blue (none) through to red (the scale's top and beyond), as the
// thesis maps it is read against draw an error count
const MAP_SCALE = [
    [0, "#5E81AC"],
    [0.1, "#81A1C1"],
    [0.3, "#A3BE8C"],
    [0.5, "#EBCB8B"],
    [0.75, "#D08770"],
    [1, "#BF616A"],
];

PlotsPanel.prototype.map = function map(host, detail, label, index, theme) {
    const colors = PAPERS[theme];
    const grid = detail.grid;
    const x = unitScale(detail.x_label, detail.x);
    const y = unitScale(detail.y_label, grid.y);
    const trace = {
        type: "heatmap",
        x: detail.x.map((value) => value * x.factor),
        y: grid.y.map((value) => value * y.factor),
        z: grid.z,
        zmin: 0,
        zmax: grid.z_max ?? undefined,
        colorscale: MAP_SCALE,
        xgap: 1,
        ygap: 1,
        colorbar: { title: { text: grid.z_label || "", side: "right" }, thickness: 10, outlinewidth: 0, tickfont: { size: 11, color: colors.ink } },
        hovertemplate: `${x.label}: %{x}<br>${y.label}: %{y}<br>${grid.z_label || "z"}: %{z}<extra></extra>`,
    };
    const layout = paperLayout(label || "", x.label, y.label, detail.x_log, grid.y_log, 0, theme);
    layout.title.font.size = 12;
    layout.margin = { l: 64, r: 12, t: label ? 30 : 12, b: 46 };
    if (label) layout.title.font.color = colorOf(index, theme);
    // categories, not a continuous axis: each rate and time constant a cell
    layout.xaxis.type = "category";
    layout.yaxis.type = "category";
    layout.xaxis.dtick = layout.yaxis.dtick = undefined;
    const element = h("div.plot.map");
    host.append(element);
    Plotly.newPlot(element, [trace], layout, { displayModeBar: false, responsive: true });
};

// ---- the page ---------------------------------------------------------------------------------

const PANELS = {
    summary: { title: "Summary", make: (container) => new SummaryPanel(container) },
    plots: { title: "Analyses", make: (container) => new PlotsPanel(container) },
    layout: { title: "Layout", make: (container, saved) => new LayoutPanel(container, saved) },
    layout3d: { title: "3D", make: (container, saved) => new Layout3DPanel(container, saved) },
    layers: { title: "Layers", make: (container) => new LayersPanel(container) },
    schematic: { title: "Schematic", make: (container) => new SchematicPanel(container, "schematic") },
    netlist: { title: "Netlist", make: (container) => new SchematicPanel(container, "netlist") },
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
                    { type: "stack", height: 60, content: [component("layout"), component("layout3d"), component("layers")] },
                    { type: "stack", height: 40, content: [component("schematic"), component("netlist")] },
                ],
            },
        ],
    },
};

// an instance with figures and no waveforms (a behavioral ADC): its summary, its figures and,
// where it has one, the layout of its blocks
const figuresLayout = (withLayout) => ({
    ...LAYOUT,
    root: {
        type: "row",
        content: [
            { type: "stack", width: 18, content: [component("summary")] },
            { type: "stack", width: withLayout ? 52 : 82, content: [component("plots")] },
            ...(withLayout ? [{ type: "stack", width: 30, content: [component("layout"), component("layout3d"), component("layers")] }] : []),
        ],
    },
});

// several instances: their table (wider as they are more) and their analyses
const compareLayout = (count) => ({
    ...LAYOUT,
    root: {
        type: "row",
        content: [
            { type: "stack", width: Math.min(55, 16 + 9 * count), content: [component("summary")] },
            { type: "stack", width: 100 - Math.min(55, 16 + 9 * count), content: [component("plots")] },
        ],
    },
});

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
        layouts: layout?.file
            ? [
                  {
                      case: ID,
                      pdk: instance.pdk,
                      generator: layout.blocks ? "blocks" : "align",
                      path: layout.file,
                      cell: instance.topology,
                      // the GDS itself, answered as a download by the server
                      gds: layout.gds ? `api/gds?path=${encodeURIComponent(layout.gds)}` : null,
                  },
              ]
            : [],
        schematics: layout?.schematic || layout?.netlist_file ? [{ case: ID, pdk: instance.pdk, path: layout.schematic || null, netlist: layout.netlist_file }] : [],
        datasets: [],
    };
    state.pdks = new Set([instance.pdk]);
    state.cases = new Set([ID]);
    state.focus = `${instance.pdk}|${ID}`;
}

async function main() {
    // the panels' errors; their other notes went to the status bar this page no longer has
    on("status", ({ message, error }) => {
        if (error) toast(message);
    });
    window.addEventListener("keydown", (event) => {
        const target = event.target;
        if (event.ctrlKey || event.metaKey || target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return;
        const key = event.key.toLowerCase();
        if (key === "f") emit("command", "fit");
        else if (key === "k") emit("command", "ruler");
        else if (key === "l") emit("command", "labels");
        else return;
        event.preventDefault();
    });
    const loading = document.getElementById("loading");
    try {
        page.instances = await Promise.all(IDS.map((id) => fetchJson(`sweep/${BLOCK}/${id}.json`).then((instance) => ({ ...instance, id }))));
    } catch (error) {
        loading.replaceChildren(h("strong", {}, "No such instance"), h("span.mono.muted", {}, error.message));
        return;
    }
    page.instance = page.instances[0];
    document.title = COMPARE ? `Comparer · ${page.instances.length} ${BLOCK}` : `Explorer · ${page.instance.topology} · ${page.instance.sizing} · ${page.instance.pdk}`;
    if (!COMPARE) shimBlock(page.instance);
    // the desktop's light or dark setting, followed as it changes
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
        document.documentElement.dataset.theme = event.matches ? "dark" : "light";
        emit("theme", document.documentElement.dataset.theme);
    });
    const container = document.getElementById("gl-container");
    const layout = new GoldenLayout(container);
    for (const [type, panel] of Object.entries(PANELS)) layout.registerComponentFactoryFunction(type, (glContainer, saved) => panel.make(glContainer, saved));
    const instanceLayout = page.instance.layout;
    const figures = page.instance.details.some((detail) => detail.figure || detail.paths?.length) && !Object.keys(page.instance.waves || {}).length && (!instanceLayout || instanceLayout.blocks);
    layout.loadLayout(COMPARE ? compareLayout(page.instances.length) : figures ? figuresLayout(Boolean(instanceLayout?.file)) : LAYOUT);
    new ResizeObserver(() => layout.updateRootSize?.() ?? layout.updateSize?.()).observe(container);
    if (!COMPARE) {
        emit("block", state.block);
        emit("selection");
    }
    loading.classList.add("done");
}

main();
