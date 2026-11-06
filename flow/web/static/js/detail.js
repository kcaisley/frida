// The Explorer and the Comparer: the instances marked in the Sweeps, opened in place by the top
// bar's View (one) or Compare (two or more); nothing here loads before.
//
// View: the instance's column on the left (its parameters, metrics and layout: sweep.js's
// SelectionPanel), its condition sweeps (Analyses, each plot scaled to its own data: curves, a map,
// markers and bands, as flow/plot.py draws a spec) and waveforms beside it, its layout, 3D and
// layers and its schematic and netlist on the right: the shared panels read a one-instance block
// from the store, as they read any other.
//
// Compare: their columns side by side, each under its colour, and their condition sweeps stacked,
// an instance a colour under one key (an instance clicked in it hides or shows its curves in every
// plot), a detail's several series a dash each, its maps side by side, a marker or band only some
// instances have in each one's colour; no layout, schematic or waveforms.

import { h } from "./icons.js";
import { LayersPanel, rgba } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { currentTheme, DENSITY, keepTicks, PAPERS, paperColorBar, paperLayout, thinLabels, tone } from "./paper.js";
import { SchematicPanel } from "./panels.js";
import { Layout } from "./regions.js";
import { COLORS, DASHES, emit, on, state } from "./store.js";
import { describe, SelectionPanel } from "./sweep.js";
import { TracesPanel } from "./traces.js";
import { siExponent } from "./units.js";

// the units the detail plots' labels end in that take an SI prefix
const SCALABLE = new Set(["s", "V", "A", "J", "W", "F", "Hz", "Ω", "C", "V/C", "V/√Hz"]);
const PREFIXES = { "-18": "a", "-15": "f", "-12": "p", "-9": "n", "-6": "µ", "-3": "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T" };
// a family of counted paths is drawn in this many weights, the most taken boldest
const PATH_LEVELS = 8;

const page = { instances: [], labels: [], compare: false };

// a compared instance's colour, by its place in the selection
export const colorOf = (index, theme = currentTheme()) => tone(COLORS[index % COLORS.length], theme);

// a compared instance's name: its PDK and the parameters that tell it from the others
const labelOf = (index) => page.labels[index]?.short || `instance ${index + 1}`;

// ---- the detail plots, each on its own data -----------------------------------------------------

function unitScale(label, values) {
    const match = label.match(/\(([^)]+)\)$/);
    const unit = match?.[1];
    if (!unit || !SCALABLE.has(unit)) return { label, factor: 1 };
    const exponent = siExponent(values.filter((value) => Number.isFinite(value)));
    return { label: label.replace(/\(([^)]+)\)$/, `(${PREFIXES[exponent]}${unit})`), factor: 10 ** -exponent };
}

// a family of counted step lines (the ADC's decision paths) as a few traces, each the paths of one
// weight joined by gaps: the more conversions took a path, the bolder and more opaque it is; meta,
// the compared instance they are (the key over the plots names it)
function pathTraces(detail, x, y, color, meta) {
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
        .map(({ level, weight }) => ({
            type: "scatter",
            mode: "lines",
            x: level.xs,
            y: level.ys,
            connectgaps: false,
            line: { color, width: 0.8 + 2.6 * weight, shape: "hv" },
            opacity: 0.18 + 0.82 * weight,
            name: "paths",
            meta,
            showlegend: false,
            hovertemplate: `${level.paths} path${level.paths > 1 ? "s" : ""}, ${level.count} of ${total} conversions<extra></extra>`,
        }));
}

// a detail's map (its heatmap: the cells' edges on x and y, a row of values a row of cells) under its
// curves, in the density colours beside its colour bar (by decade where it asks, hovered with the
// value itself); an empty cell (null, by decade one at or under 0 too) shows the paper. On an axis of
// categories (names: the detail's x_labels, y_labels) a cell is a category, hovered by its name.
function heatmapTrace(heatmap, x, y, theme, names = {}) {
    const z = unitScale(heatmap.label, heatmap.z.flat());
    const values = heatmap.z.map((row) => row.map((value) => (value === null ? null : value * z.factor)));
    const shown = heatmap.log ? values.map((row) => row.map((value) => (value > 0 ? Math.log10(value) : null))) : values;
    // a cell's place: its category's name, or its centre in the axis's prefixed unit
    const at = (edges, factor, labels, index) => labels?.[index] ?? Number(((edges[index] + edges[index + 1]) * factor * 0.5).toPrecision(4));
    const named = names.x || names.y;
    return {
        type: "heatmap",
        x: heatmap.x.map((value) => value * x.factor),
        y: heatmap.y.map((value) => value * y.factor),
        z: shown,
        customdata: values,
        colorscale: DENSITY,
        colorbar: paperColorBar(z.label, heatmap.log, shown.flat(), theme),
        hoverongaps: false,
        showlegend: false,
        ...(named
            ? {
                  text: heatmap.z.map((row, j) => row.map((_, i) => `${x.label}: ${at(heatmap.x, x.factor, names.x, i)}<br>${y.label}: ${at(heatmap.y, y.factor, names.y, j)}`)),
                  hovertemplate: `%{text}<br>${z.label}: %{customdata:.4~g}<extra></extra>`,
              }
            : { hovertemplate: `${x.label}: %{x}<br>${y.label}: %{y}<br>${z.label}: %{customdata:.4~g}<extra></extra>` }),
    };
}

// a value's place on an axis in its prefixed unit: NaN where it has none (not a number, or not
// positive on a log axis)
function place(value, factor, log) {
    return value === null || value === undefined || !Number.isFinite(value) || (log && value <= 0) ? NaN : value * factor;
}

// where a band's label sits along it (plot.py's _band_side): at its outer edge and inside it ("left",
// "right") where the band's middle lies in the first or last fifth of the data's x, `extent` (a
// centred label there would run off the plot), "center" otherwise
function bandSide(low, high, extent, log) {
    const at = (value) => (log ? Math.log10(value) : value);
    const [first, last] = extent.map(at);
    if (!(last - first > 0)) return "center";
    const share = ((at(low) + at(high)) / 2 - first) / (last - first);
    return share >= 0.8 ? "right" : share <= 0.2 ? "left" : "center";
}

// one marker (a labelled line at an x or a y: kind "x" or "y") or band (a labelled range of x shaded
// behind the curves: "band") as a shape of the plot, its label on it: a line dashed over the curves,
// its label along it at the top (an x's) or over it at the right (a y's); a band over the grid and
// under the curves, its label at its top (at its outer edge at the end of the data's x, `extent`).
// Null where it has no place on its axis.
function guideShape(kind, guide, x, y, color, logX, logY, extent) {
    const label = guide.label ? { text: guide.label, font: { size: 11, color } } : null;
    if (kind === "band") {
        const [low, high] = [place(guide.low, x.factor, logX), place(guide.high, x.factor, logX)];
        if (Number.isNaN(low) || Number.isNaN(high)) return null;
        const band = { type: "rect", xref: "x", yref: "paper", x0: low, x1: high, y0: 0, y1: 1, fillcolor: rgba(color, 0.15), line: { width: 0 }, layer: "between" };
        const side = bandSide(low, high, extent, logX);
        return label ? { ...band, label: { ...label, textposition: `top ${side}`, xanchor: side } } : band;
    }
    const at = kind === "x" ? place(guide.at, x.factor, logX) : place(guide.at, y.factor, logY);
    if (Number.isNaN(at)) return null;
    const across = kind === "x" ? { xref: "x", yref: "paper", x0: at, x1: at, y0: 0, y1: 1 } : { xref: "paper", yref: "y", x0: 0, x1: 1, y0: at, y1: at };
    const line = { type: "line", ...across, line: { color, width: 1, dash: "dash" }, layer: "above" };
    // at the line's far end (the top, the right), along it and ending there: inside the plot (a
    // vertical line's label is centred on its end otherwise, half outside)
    return label ? { ...line, label: { ...label, textposition: "end", xanchor: "right" } } : line;
}

// the entries' markers (detail.x_markers, y_markers) and bands (x_bands) as the plot's shapes, in the
// spine's grey; compared, one every instance has drawn once, grey, another in its instance's colour,
// named by its id (hidden with its curves); `extent` the data's x, where a band's label stays inside
function guideShapes(entries, x, y, theme, logX, logY, extent) {
    const found = new Map();
    for (const entry of entries) {
        const { detail } = entry;
        for (const [kind, guides] of [
            ["band", detail.x_bands],
            ["x", detail.x_markers],
            ["y", detail.y_markers],
        ]) {
            for (const guide of guides || []) {
                const key = JSON.stringify([kind, guide]);
                if (!found.has(key)) found.set(key, { kind, guide, owners: [] });
                found.get(key).owners.push(entry);
            }
        }
    }
    const shapes = [];
    for (const { kind, guide, owners } of found.values()) {
        const shared = !page.compare || owners.length === entries.length;
        for (const owner of shared ? [null] : owners) {
            const shape = guideShape(kind, guide, x, y, owner ? colorOf(owner.index, theme) : PAPERS[theme].spine, logX, logY, extent);
            if (shape && owner) shape.name = owner.instance.id;
            if (shape) shapes.push(shape);
        }
    }
    return shapes;
}

// the places of a plot's markers and bands (its shapes) as a trace that draws nothing: its axes
// range over them as over the data, with the data's margin (a line at the data's edge keeps its
// label in view, as matplotlib's do), and are ticked for them
function guideTrace(shapes) {
    const xs = shapes.filter((shape) => shape.xref === "x").flatMap((shape) => [shape.x0, shape.x1]);
    const ys = shapes.filter((shape) => shape.yref === "y").flatMap((shape) => [shape.y0, shape.y1]);
    return { type: "scatter", mode: "none", x: [...xs, ...ys.map(() => null)], y: [...xs.map(() => null), ...ys], hoverinfo: "skip", showlegend: false };
}

// what a plot's x tick labels take below a level row of them: none level, more where its category
// names angle, as they do where they would collide level
function angledTicks(element) {
    const labels = [...element.querySelectorAll(".xaxislayer-above .xtick text")];
    const angle = Number(labels[0]?.getAttribute("transform")?.match(/rotate\(([-\d.e]+)/)?.[1] || 0);
    if (!angle) return 0;
    // the labels' extent on the page, as drawn (rotated), over one label's own height
    const boxes = labels.map((label) => label.getBoundingClientRect());
    const extent = Math.max(...boxes.map((box) => box.bottom)) - Math.min(...boxes.map((box) => box.top));
    return Math.max(0, Math.ceil(extent - labels[0].getBBox().height));
}

// a plot with a legend under it taller by the legend (its lines wrap to the plot's width), and one
// with angled tick labels by what they take more than level ones: its plot area as tall as the
// others'
function fitLegend(element) {
    if (!element.isConnected) return;
    const legend = element.querySelector(".legend");
    const extra = (legend ? Math.ceil(legend.getBBox().height) : 0) + angledTicks(element);
    if (!extra && !element.style.height) return;
    element.style.height = "";
    element.style.height = `${element.offsetHeight + extra}px`;
    Plotly.Plots.resize(element);
}

// a figure the analysis plots drew, over the page until clicked or Escape
function showFigure(src, title) {
    const close = () => {
        overlay.remove();
        document.removeEventListener("keydown", onKey, true);
    };
    const onKey = (event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        close();
    };
    const overlay = h("div.lightbox", { title: "Close (click or Escape)", onclick: close }, h("figure", {}, h("figcaption", {}, title), h("img", { src, alt: title })));
    document.body.append(overlay);
    document.addEventListener("keydown", onKey, true);
}

class PlotsPanel {
    constructor(container) {
        // compared: one key to the instances' colours over the plots, which then need no legends
        // of their own; an instance clicked in it hides or shows its curves in every plot
        this.key = h("div.compare-key");
        this.plots = h(`div.detail-plots${page.compare ? ".stacked" : ""}`);
        this.element = h("div.panel", {}, page.compare ? this.key : null, this.plots);
        this.hidden = new Set();
        container.element.append(this.element);
        this.off = on("theme", () => this.render());
        container.on("destroy", () => {
            this.off();
            clearTimeout(this.resizeTimer);
            this.plots.querySelectorAll(".plot").forEach((plot) => Plotly.purge(plot));
        });
        container.on("resize", () => this.resize());
        this.render();
    }

    // once a divider's drag pauses: every plot redrawn at each step would stall it
    resize() {
        clearTimeout(this.resizeTimer);
        this.resizeTimer = setTimeout(() => {
            if (!this.plots.clientWidth) return;
            this.plots.querySelectorAll(".plot").forEach((plot) => plot.data && Plotly.Plots.resize(plot).then(() => fitLegend(plot)));
        }, 80);
    }

    render() {
        const theme = currentTheme();
        const compare = page.compare;
        this.plots.querySelectorAll(".plot").forEach((plot) => Plotly.purge(plot));
        this.plots.replaceChildren();
        const instances = page.instances;
        if (compare) {
            this.key.replaceChildren(
                ...instances.map((instance, index) =>
                    h(
                        `button.key-item${this.hidden.has(instance.id) ? ".off" : ""}`,
                        { title: `${page.labels[index]?.full || ""}\nClick: hide or show this instance's curves`, onclick: (event) => this.toggle(instance.id, event.currentTarget) },
                        h("span.swatch", { style: { background: colorOf(index, theme) } }),
                        labelOf(index),
                    ),
                ),
            );
        }
        // every detail any instance has, in the first one's order
        const names = [...new Set(instances.flatMap((instance) => (instance.details || []).map((detail) => detail.name)))];
        if (!names.length) {
            this.plots.append(h("div.empty", {}, h("strong", {}, "No condition sweeps"), h("span", {}, instances.some((instance) => instance.error) ? "The characterization failed." : "")));
            return;
        }
        for (const name of names) {
            const entries = instances
                .map((instance, index) => ({ instance, index, detail: (instance.details || []).find((detail) => detail.name === name) }))
                .filter((entry) => entry.detail);
            const first = entries[0].detail;
            // a figure the analysis plots drew (an SVG under a block's run, build/<block>/): shown as it is, side by side;
            // clicked, over the page
            if (first.figure) {
                this.plots.append(
                    h(
                        "figure.figure-card",
                        {},
                        h("figcaption", {}, first.title),
                        h(
                            "div.figure-row",
                            {},
                            entries.map(({ index, detail }) => {
                                const src = `api/figure?path=${encodeURIComponent(detail.figure)}`;
                                const title = compare ? `${first.title}: ${labelOf(index)}` : first.title;
                                return h(
                                    "button.figure-open",
                                    { title: "Show it over the page", onclick: () => showFigure(src, title) },
                                    compare ? h("span.figure-label", {}, h("span.swatch", { style: { background: colorOf(index, theme) } }), labelOf(index)) : null,
                                    h("img", { src, loading: "lazy", alt: detail.title }),
                                );
                            }),
                        ),
                    ),
                );
                continue;
            }
            // maps do not overlay: compared, each instance's map a plot of its own, side by side under
            // the detail's title, each named in its instance's colour
            if (compare && entries.some(({ detail }) => detail.heatmap)) {
                const row = h("div.map-row");
                this.plots.append(h("figure.map-card", {}, h("figcaption", {}, first.title), row));
                for (const entry of entries) this.plot(row, [entry], { title: labelOf(entry.index), color: colorOf(entry.index, theme) });
                continue;
            }
            this.plot(this.plots, entries);
        }
    }

    // a plot of one detail under host: its entries' map, curves (one instance's, or the compared
    // ones' overlaid), markers and bands, each axis scaled to what it draws; a compared map's titled
    // by its instance (title, in its colour) in place of the detail's
    plot(host, entries, { title = null, color = null } = {}) {
        const theme = currentTheme();
        const colors = PAPERS[theme];
        const compare = page.compare;
        const first = entries[0].detail;
        // SI prefixes from the values plotted (a map's cell edges among them), not the markers
        const xs = entries.flatMap(({ detail }) => [...detail.x, ...(detail.heatmap?.x || [])]);
        const ys = entries.flatMap(({ detail }) => [...Object.values(detail.series).flat(), ...(detail.paths || []).flatMap((path) => path.y), ...(detail.heatmap?.y || [])]);
        // categories on x or y (their indices, by name: first.x_labels, first.y_labels): ticked and
        // hovered by name, never scaled
        const categories = first.x_labels?.length ? first.x_labels : null;
        const rows = first.y_labels?.length ? first.y_labels : null;
        const x = categories ? { label: first.x_label, factor: 1 } : unitScale(first.x_label, xs);
        const y = rows ? { label: first.y_label, factor: 1 } : unitScale(first.y_label, ys);
        // a condition sweep's few points marked; a long series (a code axis, a spectrum) a thin line;
        // a histogram (one bin a code) its outline, steps centred on the bins, so compared ones overlay
        const dense = entries.some(({ detail }) => detail.x.length > 100);
        const histogram = Boolean(first.histogram);
        // alone, a series a colour; compared, an instance a colour (the key over the plots) and,
        // where an instance has several, a series a dash, keyed under the plot in the spine's grey
        const seriesNames = [...new Set(entries.flatMap(({ detail }) => Object.keys(detail.series)))];
        const dashed = compare && entries.some(({ detail }) => Object.keys(detail.series).length > 1);
        const traces = [];
        for (const { instance, index, detail } of entries) {
            const meta = compare ? instance.id : undefined;
            // a map under the curves, kept when its instance's curves are hidden
            if (detail.heatmap) traces.push(heatmapTrace(detail.heatmap, x, y, theme, { x: categories, y: rows }));
            if (detail.paths?.length) traces.push(...pathTraces(detail, x, y, colorOf(compare ? index : 0, theme), meta));
            for (const [series, values] of Object.entries(detail.series)) {
                const j = seriesNames.indexOf(series);
                traces.push({
                    type: "scatter",
                    mode: dense || histogram ? "lines" : "lines+markers",
                    name: compare ? (seriesNames.length > 1 ? `${labelOf(index)} · ${series}` : labelOf(index)) : series,
                    meta,
                    showlegend: !compare,
                    x: detail.x.map((value) => (value === null ? null : value * x.factor)),
                    y: values.map((value) => (value === null ? null : value * y.factor)),
                    line: { color: colorOf(compare ? index : j, theme), width: dense ? 1.2 : 2, dash: dashed ? DASHES[j % DASHES.length] : "solid", ...(histogram ? { shape: "hvh" } : {}) },
                    marker: { size: 6 },
                    ...(categories ? { text: detail.x.map((value) => categories[value] ?? ""), hovertemplate: "%{text}: %{y}" } : {}),
                });
            }
        }
        if (dashed) {
            seriesNames.forEach((series, j) =>
                traces.push({ type: "scatter", mode: "lines", name: series, x: [null], y: [null], hoverinfo: "skip", line: { color: colors.spine, width: 2, dash: DASHES[j % DASHES.length] } }),
            );
        }
        for (const trace of traces) if (this.hidden.has(trace.meta)) trace.visible = false;
        // the data's x in its prefixed unit (positive on a log axis): where a band's label stays inside
        let [xLow, xHigh] = [Infinity, -Infinity];
        for (const value of xs) {
            if (value === null || !Number.isFinite(value) || (first.x_log && value <= 0)) continue;
            xLow = Math.min(xLow, value * x.factor);
            xHigh = Math.max(xHigh, value * x.factor);
        }
        const shapes = guideShapes(entries, x, y, theme, first.x_log, first.y_log, [xLow, xHigh]);
        for (const shape of shapes) if (this.hidden.has(shape.name)) shape.visible = false;
        if (shapes.length) traces.push(guideTrace(shapes));
        const legendEntries = traces.filter((trace) => trace.showlegend !== false).length;
        // the axes ticked for what they hold: the detail's hints (whole codes, steps) where it has them
        const layout = paperLayout(title ?? first.title, x.label, y.label, first.x_log, first.y_log, legendEntries > 1 ? legendEntries : 0, theme, { traces, x: first.x_ticks ?? null, y: first.y_ticks ?? null, xLabels: categories, yLabels: rows });
        layout.title.font.size = 13;
        if (color) layout.title.font.color = color;
        layout.margin = { l: 64, r: 12, t: 34, b: 46 };
        layout.legend.font = { size: 11, color: colors.ink };
        layout.shapes = shapes;
        // the compared series' key names dashes: nothing to toggle
        if (dashed) layout.legend.itemclick = layout.legend.itemdoubleclick = false;
        const element = h("div.plot");
        host.append(element);
        Plotly.newPlot(element, traces, layout, { displayModeBar: false })
            .then(() => {
                keepTicks(element);
                return thinLabels(element);
            })
            .then(() => fitLegend(element));
    }

    // an instance's curves, and the markers and bands of its own, hidden or shown in every plot (its
    // maps and figures stay)
    toggle(id, item) {
        const hidden = !this.hidden.delete(id);
        if (hidden) this.hidden.add(id);
        item.classList.toggle("off", hidden);
        for (const element of this.plots.querySelectorAll(".plot")) {
            const indices = (element.data || []).flatMap((trace, index) => (trace.meta === id ? [index] : []));
            if (indices.length) Plotly.restyle(element, { visible: !hidden }, indices);
            const shapes = Object.fromEntries((element.layout?.shapes || []).flatMap((shape, index) => (shape.name === id ? [[`shapes[${index}].visible`, !hidden]] : [])));
            if (Object.keys(shapes).length) Plotly.relayout(element, shapes);
        }
    }
}

// ---- the shared panels' one-instance block ------------------------------------------------------

// its layout, schematic and waveform index under data/sweep/<block>/<id>/
function shimBlock(block, instance) {
    const id = instance.id;
    const layout = instance.layout;
    // the GDS's own cell name for its download
    const cell = (layout?.gds || "layout").split("/").pop().replace(/\.gds$/, "");
    state.catalog = { pdks: [instance.pdk], blocks: [] };
    state.block = {
        name: `sweep/${block}/${id}`,
        title: instance.pdk,
        pdks: [instance.pdk],
        cases: { [id]: { label: instance.pdk } },
        layouts: layout?.file
            ? [
                  {
                      case: id,
                      pdk: instance.pdk,
                      generator: layout.blocks ? "blocks" : "align",
                      path: layout.file,
                      cell,
                      // the GDS itself, answered as a download by the server
                      gds: layout.gds ? `api/gds?path=${encodeURIComponent(layout.gds)}` : null,
                  },
              ]
            : [],
        schematics: layout?.schematic || layout?.netlist_file ? [{ case: id, pdk: instance.pdk, path: layout.schematic || null, netlist: layout.netlist_file }] : [],
        datasets: [],
    };
    state.pdks = new Set([instance.pdk]);
    state.cases = new Set([id]);
    state.hidden = new Set();
    state.focus = `${instance.pdk}|${id}`;
}

// ---- the arrangements -------------------------------------------------------------------------

// the instances (their exported files, each with its id) in place under host; onRemove(id) takes
// one out of the selection, onView(id) views it alone. Returns the Layout, destroyed on leaving.
export function mountInstances(host, { block, instances, onRemove, onView }) {
    const compare = instances.length > 1;
    page.instances = instances;
    page.compare = compare;
    page.labels = describe(instances);
    const layout = new Layout(host);
    const panel = (id, title, make) => ({ id, title, make });
    const selection = layout.region([panel("sweeps", "Sweeps", (container) => new SelectionPanel(container, { instances, colorOf: (index) => colorOf(index), onRemove, onView }))]);
    const plots = layout.region([panel("plots", "Analyses", (container) => new PlotsPanel(container))]);
    let root;
    if (compare) {
        // their table wider as they are more
        const share = Math.min(55, 14 + 7 * instances.length);
        root = layout.split("row", [selection, plots], `compare.${Math.min(instances.length, 6)}`, [share, 100 - share]);
    } else {
        const instance = instances[0];
        shimBlock(block, instance);
        const shapes = () =>
            layout.region(
                [
                    panel("layout", "Layout", (container) => new LayoutPanel(container)),
                    panel("layout3d", "3D", (container) => new Layout3DPanel(container)),
                    panel("layers", "Layers", (container) => new LayersPanel(container)),
                ],
                "view.layout",
            );
        // an instance with figures and no waveforms (a behavioral ADC): its figures and, where it
        // has one, the layout of its blocks
        const own = instance.layout;
        const figures = (instance.details || []).some((detail) => detail.figure || detail.paths?.length || detail.heatmap) && !Object.keys(instance.waves || {}).length && (!own || own.blocks || !own.file);
        if (figures) {
            root = own?.file ? layout.split("row", [selection, plots, shapes()], "view.figures", [20, 50, 30]) : layout.split("row", [selection, plots], "view.figures.alone", [20, 80]);
        } else {
            const traces = layout.region([panel("traces", "Waveforms", (container) => new TracesPanel(container))]);
            const sheets = layout.region(
                [panel("schematic", "Schematic", (container) => new SchematicPanel(container, "schematic")), panel("netlist", "Netlist", (container) => new SchematicPanel(container, "netlist"))],
                "view.schematic",
            );
            root = layout.split(
                "row",
                [selection, layout.split("column", [plots, traces], "view.center", [55, 45]), layout.split("column", [shapes(), sheets], "view.right", [60, 40])],
                "view",
                [18, 45, 37],
            );
        }
    }
    layout.mount(root);
    // the instances' columns as wide as they need (within bounds) until a divider is dragged
    const fit = () => {
        const table = selection.querySelector("table.tgrid.narrow");
        const total = root.getBoundingClientRect().width;
        if (!table || !total) return;
        table.style.minWidth = "0";
        const natural = table.offsetWidth + 14;
        table.style.minWidth = "";
        root.fitFirst(Math.min(compare ? 62 : 30, Math.max(12, (100 * natural) / total)));
    };
    fit();
    root.addEventListener("reset", fit);
    if (!compare) {
        emit("block", state.block);
        emit("selection");
    }
    return layout;
}
