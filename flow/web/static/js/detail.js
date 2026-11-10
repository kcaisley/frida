// The Explorer and the Comparer: the instances marked in the Sweeps, opened in place by the top
// bar's View (one) or Compare (two or more); nothing here loads before.
//
// Each instance is its story: the steps of the pipeline it went through (flow.steps: netlist, sim,
// layout, drc, lvs, pex, pexsim, record; flow.web.export.steps_view), top to bottom, a row a step.
// On a row's left the step's state (ok; kept: made in an earlier invocation of the run; failed, with
// its error; rejected, with the bounds it missed; skipped or not run, with why), its seconds, its
// tools' warnings and errors (its log over the page) and what it found or established; on its right
// what it made: the netlist's schematic and listing, the pre-layout runs' waveforms, the layout in
// 2-D and 3-D and its layers, DRC's violations, LVS's verdict, the extraction's nets, the
// post-layout runs' waveforms, the record's analyses (each plot scaled to its own data: curves, a
// map, markers and bands, as flow/plot.py draws a spec). The shared panels (layout, 3D, layers,
// schematic, waveforms) read a one-instance block from the store, as they read any other.
//
// Compared, a row's left is a column per design under its colour (blue, orange, ...: COLORS, the
// values that differ tinted) and its right one design's at a time (the head's Show), but for the
// analyses: there every design's curves overlay, a design a colour under one key (a design clicked
// in it hides or shows its curves), its several curves a dash each, its maps side by side, a marker
// or band only some have in each one's colour.

import { h, icon } from "./icons.js";
import { LayersPanel, rgba } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { currentTheme, DENSITY, keepTicks, PAPERS, paperColorBar, paperLayout, thinLabels, tone } from "./paper.js";
import { SchematicPanel } from "./panels.js";
import { Layout } from "./regions.js";
import { COLORS, DASHES, emit, hostBar, on, recall, state, store } from "./store.js";
import { describe, differs, formatted, paramNames, shown } from "./sweep.js";
import { TracesPanel } from "./traces.js";
import { fieldInfo, scaledUnit, siExponent, words } from "./units.js";

// the units the detail plots' labels end in that take an SI prefix
const SCALABLE = new Set(["s", "V", "A", "J", "W", "F", "Hz", "Ω", "C", "V/C", "V/√Hz"]);
const PREFIXES = { "-18": "a", "-15": "f", "-12": "p", "-9": "n", "-6": "µ", "-3": "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T" };
// a family of counted paths is drawn in this many weights, the most taken boldest
const PATH_LEVELS = 8;

// the shown designs, their names, whether compared, and the one whose visualizations show
const page = { instances: [], labels: [], compare: false, shown: 0, onlyDifferences: true };

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
        this.plots = h("div.detail-plots");
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
        // a design a colour (the first blue, the second orange: COLORS) and, where it has several
        // series, a series a dash; compared, the dashes keyed under the plot in the spine's grey (the
        // key over the plots names the colours), alone the curves themselves in its legend
        const seriesNames = [...new Set(entries.flatMap(({ detail }) => Object.keys(detail.series)))];
        const several = entries.some(({ detail }) => Object.keys(detail.series).length > 1);
        const dashed = compare && several;
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
                    line: { color: colorOf(compare ? index : 0, theme), width: dense ? 1.2 : 2, dash: several ? DASHES[j % DASHES.length] : "solid", ...(histogram ? { shape: "hvh" } : {}) },
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

// the shown design's layout, schematic and waveform indices under data/sweep/<its table>/<id>/
function shimBlock(instance) {
    const id = instance.id;
    const layout = instance.layout;
    // the GDS's own cell name for its download
    const cell = (layout?.gds || "layout").split("/").pop().replace(/\.gds$/, "");
    state.catalog = { pdks: [instance.pdk], blocks: [] };
    state.block = {
        name: `sweep/${instance.file}/${id}`,
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

// ---- the steps --------------------------------------------------------------------------------

// a step's name on its row, and what it does
const STEPS = {
    netlist: ["Netlist", "the circuit as simulated, and its size"],
    sim: ["Simulation", "each testbench run before layout"],
    circuit: ["Circuit simulation", "the runs a behavioral block leaves to the circuit simulator"],
    layout: ["Layout", "placed and routed"],
    drc: ["DRC", "the design rules checked"],
    lvs: ["LVS", "the layout against its schematic"],
    pex: ["Extraction", "the layout's parasitic capacitance"],
    pexsim: ["Post-layout simulation", "the runs again, the extraction back-annotated"],
    record: ["Record", "the metrics and analyses, post-layout where the extraction was simulated"],
};
// a state's chip (compile.js's stage chips): its class and word
const STATES = {
    ok: ["done", "ok"],
    kept: ["done.kept", "kept"],
    failed: ["failed", "failed"],
    rejected: ["rejected", "rejected"],
    skipped: ["skipped", "skipped"],
    "not run": ["skipped", "not run"],
};
// the chips' marks, drawn as icons.js draws its set (compile.js's)
const GLYPHS = {
    done: '<path d="M3 8.5l3 3 7-7"/>',
    "done.kept": '<path d="M3 8.5l3 3 7-7"/>',
    failed: '<path d="M4 4l8 8M12 4l-8 8"/>',
    rejected: '<path d="M8 2.2l6.3 11.3H1.7z"/><path d="M8 6.5v3.2M8 11.6v.1"/>',
    skipped: '<path d="M4 8h8"/>',
};
const glyph = (name, size = 11) => `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GLYPHS[name] || ""}</svg>`;

// an instance's steps (its export's), or where it has none (a search's design, flow.opt; a run's
// from before the steps kept their own records) those its record tells of
function stepsOf(instance) {
    if (instance.steps) return instance.steps;
    const layout = instance.layout || {};
    const why = instance.status ? "the search kept no record of it" : "the run is from before the steps kept their own records";
    const has = (yes) => (yes ? "ok" : "not run");
    const known = (value) => value !== null && value !== undefined;
    return [
        { step: "netlist", state: has(layout.netlist_file), why },
        { step: "sim", state: has(Object.keys(instance.waves || {}).length || Object.keys(instance.metrics || {}).length), why },
        { step: "layout", state: layout.error ? "failed" : has(layout.file || layout.gds), error: layout.error, why, outputs: { cell_um: layout.w_um ? [layout.w_um, layout.h_um] : undefined, router: layout.router } },
        { step: "drc", state: has(known(layout.drc_violations)), why, outputs: { violations: layout.drc_violations, checker: layout.signoff } },
        { step: "lvs", state: has(known(layout.lvs_correct)), why, outputs: known(layout.lvs_correct) ? { lvs_correct: layout.lvs_correct } : {} },
        { step: "record", state: instance.error ? "failed" : "ok", error: instance.error },
    ];
}

const stepOf = (instance, key) => stepsOf(instance).find((entry) => entry.step === key) || { step: key, state: "not run", why: "not in this instance's pipeline" };
const ran = (entry) => entry.state === "ok" || entry.state === "kept" || entry.state === "rejected";

function chip(entry, { label = null, time = true, onclick = null } = {}) {
    const [kind, word] = STATES[entry.state] || STATES["not run"];
    const title = [`${STEPS[entry.step]?.[0] || entry.step}: ${word}`, entry.why, entry.error?.trim().split("\n").pop(), rejection(entry.rejected)].filter(Boolean).join("\n");
    return h(
        `${onclick ? "button" : "span"}.stage-chip.${kind}`,
        { title, onclick },
        h("span", { html: glyph(kind) }),
        label ?? word,
        time && entry.seconds !== undefined && entry.seconds !== null && entry.state !== "not run" ? h("span.time", {}, duration(entry.seconds)) : "",
    );
}

function duration(seconds) {
    if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
    return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

// a step's warnings and errors by tool (flow.steps.logged): "align 4 errors, 10 warnings"
function logged(counts) {
    const nouns = [
        ["CRITICAL", "critical"],
        ["ERROR", "error"],
        ["WARNING", "warning"],
    ];
    return Object.entries(counts || {})
        .map(([tool, levels]) => `${tool} ${nouns.filter(([level]) => levels[level]).map(([level, noun]) => `${levels[level]} ${noun}${levels[level] === 1 ? "" : "s"}`).join(", ")}`)
        .join("; ");
}

// a rejection as the dashboard says it: "rejected at sim (prelayout): delay 2.1e-09 > 2e-09"
function rejection(rejected) {
    if (!rejected) return "";
    const misses = Object.entries(rejected.bounds || {}).map(([metric, [value, limit]]) => `${metric} ${formatQuantity(value, fieldInfo(metric))} (bound ${formatQuantity(limit, fieldInfo(metric))})`);
    return `rejected at ${rejected.step} (${rejected.evidence}): ${misses.join(", ")}`;
}

function formatQuantity(value, info) {
    if (typeof value !== "number" || !Number.isFinite(value)) return shown(value);
    const exponent = info.scalable ? siExponent([value]) : 0;
    const unit = scaledUnit(info, exponent);
    return `${+(value / 10 ** exponent).toPrecision(4)}${unit ? ` ${unit}` : ""}`;
}

// capacitance in fF
const femto = (value) => (typeof value === "number" && Number.isFinite(value) ? `${+(value * 1e15).toPrecision(4)}` : "—");

// a step's log over the page until clicked or Escape (the server's /api/log: its end)
async function showLog(path, title) {
    const text = h("pre.log-text", {}, "Loading…");
    const close = () => {
        overlay.remove();
        document.removeEventListener("keydown", onKey, true);
    };
    const onKey = (event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        close();
    };
    const overlay = h("div.lightbox.log", { onclick: (event) => event.target === overlay && close() }, h("figure", {}, h("figcaption", {}, title, h("span.grow"), h("button.icon-btn", { title: "Close (Escape)", onclick: close, html: icon("x", 14) })), text));
    document.body.append(overlay);
    document.addEventListener("keydown", onKey, true);
    try {
        const response = await fetch(`api/log?path=${encodeURIComponent(path)}`);
        const body = response.ok ? (await response.text()) || "(empty)" : `HTTP ${response.status}`;
        // its errors and warnings in their colours
        text.replaceChildren(...body.split("\n").map((line) => h(/ (ERROR|CRITICAL) /.test(line) ? "span.log-error" : / WARNING /.test(line) ? "span.log-warning" : "span", {}, `${line}\n`)));
        text.scrollTop = text.scrollHeight;
    } catch (error) {
        text.textContent = error.message;
    }
}

// ---- a step's facts: a row per fact, a column per design --------------------------------------

// a cell: its value (an enumeration's member in words; raw, as it is: a tool's, a cell's name) or
// node, its title, whether it is bad (an error, a violation)
const cell = (value, { title = "", bad = false, node = null, raw = false } = {}) => ({ value, title, bad, node, raw });

// rows: [label, cells, {unit, title, mono, section}]; the values that differ between compared
// designs tinted
function factsTable(rows) {
    const body = [];
    for (const [label, cells, options = {}] of rows) {
        if (options.section) {
            body.push(h("tr.section", {}, h("th.label", {}, label), h("td", { colspan: String(page.instances.length) })));
            continue;
        }
        const differ = page.compare && !options.plain && differs(cells.map((item) => item.value));
        body.push(
            h(
                `tr${differ ? ".differs" : ""}`,
                {},
                h("th.label", { title: options.title || label }, h("div.lab", {}, h(`span.name${options.mono ? ".mono" : ""}`, {}, label), h("span.unit", {}, options.unit || ""))),
                cells.map((item) => h(`td${item.bad ? ".failed" : ""}${item.node ? ".node" : ""}`, { title: item.title || (typeof item.value === "string" && item.value.length > 18 ? item.value : "") }, item.node || (item.raw && item.value !== null && item.value !== undefined ? String(item.value) : shown(item.value)))),
            ),
        );
    }
    // compared: a column per design under its colour and name
    const head = page.compare
        ? h("thead", {}, h("tr", {}, h("th.corner", {}), page.instances.map((_instance, index) => h("th.inst.sel", { title: page.labels[index]?.full || "" }, h("div.inst-head", {}, h("span.swatch", { style: { background: colorOf(index) } }), h("span.inst-name", {}, labelOf(index)))))))
        : null;
    return h("table.tgrid.narrow.facts", {}, head, h("tbody", {}, body));
}

// a metric row per name: its values at the row's SI prefix
function metricRows(names, valuesOf, { title = (name) => name } = {}) {
    return names.map((name) => {
        const info = fieldInfo(name);
        const values = page.instances.map((instance, index) => valuesOf(instance, index)?.[name]);
        const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value));
        const exponent = info.scalable && finite.length ? siExponent(finite) : 0;
        return [info.label, values.map((value, index) => cell(formatted(value, exponent), { title: title(name, index) })), { unit: scaledUnit(info, exponent), title: name }];
    });
}

// the facts every step's row starts with: its state, seconds, warnings and log; its error, why it did
// not run, the bounds it missed
function commonRows(key) {
    const entries = page.instances.map((instance) => stepOf(instance, key));
    // alone, the state is the row's head's chip
    const rows = [
        ...(page.compare ? [["State", entries.map((entry) => cell(entry.state, { node: chip(entry, { time: false }) })), { plain: true }]] : []),
        ["Time", entries.map((entry) => cell(entry.seconds === undefined || entry.seconds === null ? "—" : duration(entry.seconds))), { plain: true }],
    ];
    if (entries.some((entry) => entry.finished)) {
        const when = (entry) => (entry.finished ? new Date(entry.finished * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
        rows.push(["Finished", entries.map((entry) => cell(when(entry))), { plain: true }]);
    }
    if (entries.some((entry) => Object.keys(entry.counts || {}).length || entry.log_file)) {
        rows.push([
            "Warnings · errors",
            entries.map((entry) => {
                const text = logged(entry.counts) || "none";
                const errors = Object.values(entry.counts || {}).some((levels) => levels.ERROR || levels.CRITICAL);
                const node = entry.log_file
                    ? h("button.link.log-link", { title: `Show ${entry.step}'s log (step.log)`, onclick: () => showLog(entry.log_file, `${STEPS[key]?.[0] || key}: ${entry.log_file}`) }, text)
                    : document.createTextNode(text);
                return cell(text, { node, bad: errors });
            }),
            { plain: true },
        ]);
    }
    if (entries.some((entry) => entry.error)) {
        rows.push(["Error", entries.map((entry) => cell(entry.error ? entry.error.trim().split("\n").pop() : "—", { title: entry.error || "", bad: Boolean(entry.error) }))]);
    }
    if (entries.some((entry) => entry.why && !ran(entry) && entry.state !== "failed")) {
        rows.push(["Why", entries.map((entry) => cell(!ran(entry) && entry.state !== "failed" ? entry.why || "—" : "—"))]);
    }
    if (entries.some((entry) => entry.note)) rows.push(["Note", entries.map((entry) => cell(entry.note || "—"))]);
    const missed = [...new Set(entries.flatMap((entry) => Object.keys(entry.rejected?.bounds || {})))];
    if (missed.length) {
        rows.push(["Bounds missed", [], { section: true }]);
        for (const metric of missed) {
            const info = fieldInfo(metric);
            rows.push([
                info.label,
                entries.map((entry) => {
                    const pair = entry.rejected?.bounds?.[metric];
                    return pair ? cell(`${formatQuantity(pair[0], info)}, bound ${formatQuantity(pair[1], info)}`, { bad: true }) : cell("—");
                }),
                { title: metric },
            ]);
        }
    }
    // what the step established for the run's bounds (its step.json's metrics)
    const established = [...new Set(entries.flatMap((entry) => Object.keys(entry.metrics || {})))];
    if (established.length && key !== "sim" && key !== "record") {
        rows.push(["Established for the bounds", [], { section: true }], ...metricRows(established, (instance) => stepOf(instance, key).metrics));
    }
    return rows;
}

const outputsOf = (instance, key) => stepOf(instance, key).outputs || {};
const valuesOf = (key, get) => page.instances.map((instance) => cell(get(outputsOf(instance, key), instance, stepOf(instance, key)) ?? null, { raw: true }));

// the step's own facts, after the common ones
function stepRows(key) {
    const instances = page.instances;
    switch (key) {
        case "netlist": {
            const names = ["pdk", ...paramNames(instances)].filter((name) => !page.compare || !page.onlyDifferences || name === "pdk" || differs(instances.map((instance) => instance.params?.[name])));
            const params = names.map((name) => [name, instances.map((instance) => (name === "pdk" ? cell(instance.pdk, { raw: true }) : cell(instance.params?.[name] ?? null))), { mono: true }]);
            const sizes = [...new Set(instances.flatMap((instance) => Object.keys(stepOf(instance, key).geometry || {})))];
            const leaves = [...new Set(instances.flatMap((instance) => Object.keys(stepOf(instance, key).netlist?.leaves || {})))];
            const stat = (name) => valuesOf(key, (_outputs, _instance, entry) => entry.netlist?.[name]);
            return [
                ["Parameters", [], { section: true }],
                ...params,
                ...(sizes.length ? [["Size", [], { section: true }], ...metricRows(sizes, (instance) => stepOf(instance, key).geometry)] : []),
                ...(instances.some((instance) => stepOf(instance, key).netlist?.top)
                    ? [
                          ["Netlist", [], { section: true }],
                          ["Top cell", stat("top"), { mono: true }],
                          ["Ports", stat("ports")],
                          ["Nets", stat("nets")],
                          ["Instances", stat("instances")],
                          ["Subcircuits", stat("subcircuits")],
                          ...leaves.map((leaf) => [leaf, valuesOf(key, (_outputs, _instance, entry) => entry.netlist?.leaves?.[leaf] ?? 0), { mono: true }]),
                      ]
                    : []),
            ];
        }
        case "sim":
        case "circuit": {
            const rows = [["Runs", valuesOf(key, (outputs) => outputs.runs?.length)]];
            if (key === "circuit") return rows;
            // the pre-layout metrics: the record's own where it is pre-layout, else beside its post-layout ones
            const before = (instance) => (instance.evidence === "postlayout" ? instance.prelayout : ran(stepOf(instance, "sim")) ? instance.metrics : null);
            const names = [...new Set(instances.flatMap((instance) => Object.keys(before(instance) || {})))].filter((name) => !["layout_area_um2", "density"].includes(name));
            return names.length ? [...rows, ["Pre-layout metrics", [], { section: true }], ...metricRows(names, before)] : rows;
        }
        case "layout":
            return [
                ["Outline", valuesOf(key, (outputs) => (outputs.cell_um ? outputs.cell_um.map((value) => +value.toPrecision(5)).join(" × ") : null)), { unit: "µm" }],
                ...metricRows(
                    ["layout_area_um2", "density"].filter((name) => instances.some((instance) => instance.metrics?.[name] !== undefined)),
                    (instance) => instance.metrics,
                ),
                ["Placed", valuesOf(key, (outputs, instance) => (outputs.placed === undefined ? null : instance.layout?.floorplan ? `by ${instance.layout.floorplan}` : outputs.placed ? "by its generator" : "ALIGN alone"))],
                ["Router", valuesOf(key, (outputs) => outputs.router)],
                ["Route shorts", valuesOf(key, (outputs) => outputs.route_shorts)],
                ...parts(key),
            ];
        case "drc":
            return [
                ["Checker", valuesOf(key, (outputs) => outputs.checker)],
                ["Violations", page.instances.map((instance) => cell(outputsOf(instance, key).violations ?? null, { bad: outputsOf(instance, key).violations > 0 }))],
                ["Rules violated", valuesOf(key, (_outputs, _instance, entry) => (entry.rules ? Object.keys(entry.rules).length : null))],
                ["Top cell", valuesOf(key, (outputs) => outputs.top), { mono: true }],
            ];
        case "lvs":
            return [
                ["Checker", valuesOf(key, (outputs) => outputs.lvs_checker || null)],
                ["Verdict", page.instances.map((instance) => cell(verdict(outputsOf(instance, key)), { bad: outputsOf(instance, key).lvs_correct === false }))],
                ["Source top", valuesOf(key, (outputs) => outputs.source_top), { mono: true }],
                ["Layout top", valuesOf(key, (outputs) => outputs.layout_top), { mono: true }],
                ["Mismatches", valuesOf(key, (_outputs, _instance, entry) => entry.mismatches?.length ?? null)],
            ];
        case "pex":
            return [
                ["Extractor", valuesOf(key, (outputs) => outputs.extractor)],
                ["Capacitors", valuesOf(key, (outputs) => outputs.capacitors)],
                ["Total", valuesOf(key, (outputs) => (outputs.total_f === undefined ? null : femto(outputs.total_f))), { unit: "fF" }],
                ["Nets", valuesOf(key, (outputs) => (outputs.nets ? Object.keys(outputs.nets).length : null))],
            ];
        case "pexsim":
            return [
                ["Runs", valuesOf(key, (outputs) => outputs.runs?.length)],
                ["Capacitors", valuesOf(key, (outputs) => outputs.capacitors)],
                ["Extracted", valuesOf(key, (outputs) => (outputs.total_f === undefined ? null : femto(outputs.total_f))), { unit: "fF" }],
                ["Added", valuesOf(key, (outputs) => (outputs.added_f === undefined ? null : femto(outputs.added_f))), { unit: "fF", title: "The capacitance the back-annotation added to the simulated circuit" }],
                ["Drawn taken off", valuesOf(key, (outputs) => (outputs.drawn_f === undefined ? null : femto(outputs.drawn_f))), { unit: "fF", title: "The drawn capacitors' own capacitance, which the extraction measured as metal" }],
                ["Unmapped", page.instances.map((instance) => {
                    const outputs = outputsOf(instance, key);
                    return outputs.unmapped_share === undefined ? cell(null) : cell(`${femto(outputs.unmapped_f)} fF (${(100 * outputs.unmapped_share).toFixed(1)} %)`, { bad: outputs.unmapped_share > 0.05, title: Object.keys(outputs.unmapped_nets || {}).join(", ") });
                }), { title: "The extraction's capacitance on nets with no schematic net (the step fails over 5 %)" }],
                ["Unsimulated nets", valuesOf(key, (outputs) => (outputs.unsimulated ? Object.keys(outputs.unsimulated).length : null))],
                ["Unannotated", valuesOf(key, (outputs) => (outputs.unannotated ? outputs.unannotated.join(", ") || "none" : null)), { title: "The testbenches without the design, run as they are" }],
            ];
        case "record": {
            const rows = [
                ["Evidence", instances.map((instance) => cell(instance.evidence ? words(instance.evidence.toUpperCase()) : null))],
                ["Verdict", instances.map((instance) => cell(instance.rejected ? rejection(instance.rejected) : instance.error ? "failed" : "met its bounds", { bad: Boolean(instance.rejected || instance.error) }))],
            ];
            if (instances.some((instance) => instance.unjudged?.length)) rows.push(["Unjudged", instances.map((instance) => cell(instance.unjudged?.join(", ") || "none")), { title: "The bounds the record's evidence could not judge" }]);
            const names = [...new Set(instances.flatMap((instance) => Object.keys(instance.metrics || {})))];
            if (!names.length) return rows;
            // alone: post-layout beside pre-layout and the change; compared: each design's, the pre-layout in its title
            if (!page.compare && instances[0].evidence === "postlayout" && instances[0].prelayout) {
                return [...rows, ["Metrics", [], { section: true }], ...prePost(instances[0], names)];
            }
            const before = (name, index) => {
                const value = instances[index].prelayout?.[name];
                return value === undefined ? name : `${name}: pre-layout ${formatQuantity(value, fieldInfo(name))}`;
            };
            return [...rows, ["Metrics", [], { section: true }], ...metricRows(names, (instance) => instance.metrics, { title: before })];
        }
    }
    return [];
}

// the parts of a step's time (the layout's: parameters, netlist, floorplan, layout)
function parts(key) {
    const names = [...new Set(page.instances.flatMap((instance) => Object.keys(outputsOf(instance, key).parts || {})))];
    if (!names.length) return [];
    return [["Its time by part", [], { section: true }], ...names.map((part) => [part, valuesOf(key, (outputs) => (outputs.parts?.[part] === undefined ? null : `${outputs.parts[part]} s`)), { plain: true, title: `The step's ${part}` }])];
}

const verdict = (outputs) => (outputs.lvs_correct === undefined ? null : outputs.lvs_correct === null ? "no deck" : outputs.lvs_correct ? "match" : "no match");

// one design's metrics post-layout, pre-layout beside them and the change
function prePost(instance, names) {
    const head = h("tr", {}, h("th.corner", {}, ""), h("th.inst", {}, "post-layout"), h("th.inst", {}, "pre-layout"), h("th.inst", {}, "change"));
    const rows = names.map((name) => {
        const info = fieldInfo(name);
        const [post, pre] = [instance.metrics?.[name], instance.prelayout?.[name]];
        const finite = [post, pre].filter((value) => typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value));
        const exponent = info.scalable && finite.length ? siExponent(finite) : 0;
        const change = typeof post === "number" && typeof pre === "number" && pre !== 0 && Number.isFinite(post) && Number.isFinite(pre) ? `${post >= pre ? "+" : ""}${((100 * (post - pre)) / Math.abs(pre)).toFixed(1)} %` : "—";
        return h(
            "tr",
            {},
            h("th.label", { title: name }, h("div.lab", {}, h("span.name", {}, info.label), h("span.unit", {}, scaledUnit(info, exponent)))),
            h("td", {}, formatted(post, exponent)),
            h("td.muted", {}, pre === undefined ? "—" : formatted(pre, exponent)),
            h("td.muted", {}, change),
        );
    });
    return [["", [], { node: h("table.tgrid.narrow.facts.prepost", {}, h("thead", {}, head), h("tbody", {}, rows)) }]];
}

// ---- what a step made: its row's right side ---------------------------------------------------

// the shown design's index of its pre-layout runs' waveforms (traces.sim.json where the record's
// are post-layout), or of its post-layout runs' (the record's, where they are)
const simIndex = (instance) => (instance.layout?.traces_sim ? "traces.sim.json" : instance.evidence === "postlayout" || !Object.keys(instance.waves || {}).length ? null : "traces.json");
const pexsimIndex = (instance) => (instance.evidence === "postlayout" && Object.keys(instance.waves || {}).length ? "traces.json" : null);
const shownInstance = () => page.instances[page.shown];

// a panel of the shown design's step findings, drawn again when another design is shown
class FindingsPanel {
    constructor(container, key) {
        this.key = key;
        this.body = h("div.panel-body.findings");
        this.element = h("div.panel", {}, this.body);
        container.element.append(this.element);
        this.off = [on("story-shown", () => this.render()), on("theme", () => this.render())];
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            this.body.querySelectorAll(".plot").forEach((plot) => Plotly.purge(plot));
        });
        container.on("resize", () => this.body.querySelectorAll(".plot").forEach((plot) => plot.data && Plotly.Plots.resize(plot)));
        this.render();
    }

    render() {
        this.body.querySelectorAll(".plot").forEach((plot) => Plotly.purge(plot));
        const instance = shownInstance();
        const entry = stepOf(instance, this.key);
        const outputs = entry.outputs || {};
        const named = page.compare ? h("div.findings-who", {}, h("span.swatch", { style: { background: colorOf(page.shown) } }), labelOf(page.shown)) : null;
        if (!ran(entry)) {
            this.body.replaceChildren(h("div.empty", {}, h("strong", {}, `${STEPS[this.key][0]}: ${STATES[entry.state]?.[1] || entry.state}`), h("span", {}, entry.why || entry.error?.trim().split("\n").pop() || "")));
            return;
        }
        if (this.key === "drc") {
            const rules = Object.entries(entry.rules || {});
            const verdictLine = h(`div.verdict${outputs.violations ? ".bad" : ".ok"}`, {}, outputs.violations ? `${outputs.violations} violation${outputs.violations === 1 ? "" : "s"}` : "clean", h("span.muted", {}, ` · ${outputs.checker || ""}`));
            const table = rules.length ? h("table.tgrid.narrow.facts", {}, h("thead", {}, h("tr", {}, h("th.corner", {}, "rule"), h("th.inst", {}, "violations"))), h("tbody", {}, rules.map(([rule, count]) => h("tr", {}, h("th.label", {}, h("div.lab", {}, h("span.name.mono", {}, rule))), h("td.failed", {}, String(count)))))) : null;
            this.body.replaceChildren(...[named, verdictLine, table].filter(Boolean));
        } else if (this.key === "lvs") {
            const word = verdict(outputs);
            const verdictLine = h(`div.verdict${outputs.lvs_correct === false ? ".bad" : outputs.lvs_correct ? ".ok" : ""}`, {}, word === "no deck" ? "not compared: no LVS deck" : word, h("span.muted", {}, outputs.lvs_checker ? ` · ${outputs.lvs_checker}` : ""));
            const mismatches = entry.mismatches?.length ? h("pre.mismatches", {}, entry.mismatches.join("\n")) : null;
            this.body.replaceChildren(...[named, verdictLine, h("div.muted.mono", {}, `${outputs.layout_top || "?"} (layout) against ${outputs.source_top || "?"} (source)`), mismatches].filter(Boolean));
        } else if (this.key === "pex") {
            const nets = Object.entries(outputs.nets || {}).sort((a, b) => b[1] - a[1]);
            const verdictLine = h("div.verdict", {}, `${femto(outputs.total_f)} fF`, h("span.muted", {}, ` in ${outputs.capacitors ?? "?"} capacitors · ${outputs.extractor || ""}`));
            if (!nets.length) {
                this.body.replaceChildren(...[named, verdictLine, h("div.muted", {}, "The extraction's netlist alone: no capacitance by net.")].filter(Boolean));
                return;
            }
            const element = h("div.plot");
            this.body.replaceChildren(...[named, verdictLine, element].filter(Boolean));
            netsPlot(element, nets, colorOf(page.shown));
        }
    }
}

// the extraction's capacitance by net, each net's to everything else: a bar a net, the largest first
function netsPlot(element, nets, color) {
    const theme = currentTheme();
    const colors = PAPERS[theme];
    const trace = { type: "bar", orientation: "h", x: nets.map(([, value]) => value * 1e15), y: nets.map(([net]) => net), marker: { color }, hovertemplate: "%{y}: %{x:.4g} fF<extra></extra>" };
    const layout = paperLayout("", "Capacitance (fF)", "", false, false, 0, theme, { traces: [trace] });
    layout.yaxis = { ...layout.yaxis, type: "category", autorange: "reversed", tickfont: { family: "var(--font-mono)", size: 11, color: colors.ink }, title: { text: "" }, automargin: true };
    layout.margin = { l: 12, r: 16, t: 8, b: 44 };
    layout.bargap = 0.3;
    element.style.height = `${Math.min(420, 60 + 22 * nets.length)}px`;
    Plotly.newPlot(element, [trace], layout, { displayModeBar: false }).then(() => keepTicks(element));
}

// the regions a step's right side holds: [panels, its height class], none where nothing was made
function vizOf(key) {
    const instances = page.instances;
    const panel = (id, title, make) => ({ id, title, make });
    const any = (test) => instances.some(test);
    switch (key) {
        case "netlist":
            if (!any((instance) => instance.layout?.schematic || instance.layout?.netlist_file)) return null;
            return [[panel("schematic", "Schematic", (container) => new SchematicPanel(container, "schematic")), panel("netlist", "Netlist", (container) => new SchematicPanel(container, "netlist"))], "sheet"];
        case "sim":
            if (!any(simIndex)) return null;
            return [[panel("traces", "Waveforms", (container) => new TracesPanel(container, null, { index: () => simIndex(shownInstance()) }))], "traces"];
        case "layout":
            if (!any((instance) => instance.layout?.file)) return null;
            return [
                [panel("layout", "Layout", (container) => new LayoutPanel(container)), panel("layout3d", "3D", (container) => new Layout3DPanel(container)), panel("layers", "Layers", (container) => new LayersPanel(container))],
                "layout",
            ];
        case "drc":
        case "lvs":
        case "pex": {
            if (!any((instance) => ran(stepOf(instance, key)))) return null;
            const title = { drc: "Violations", lvs: "Comparison", pex: "Nets" }[key];
            return [[panel(key, title, (container) => new FindingsPanel(container, key))], "auto"];
        }
        case "pexsim":
            if (!any(pexsimIndex)) return null;
            return [[panel("traces.pexsim", "Waveforms", (container) => new TracesPanel(container, null, { index: () => pexsimIndex(shownInstance()) }))], "traces"];
        case "record":
            if (!any((instance) => instance.details?.length)) return null;
            return [[panel("plots", "Analyses", (container) => new PlotsPanel(container))], "auto"];
    }
    return null;
}

// ---- the story --------------------------------------------------------------------------------

// a step's row: its facts on the left, what it made on the right (its own Layout of one region)
function stepRow(key, number, layouts) {
    const [title, about] = STEPS[key] || [key, ""];
    const entries = page.instances.map((instance) => stepOf(instance, key));
    const anchor = { id: `step-${key}` };
    // a step none of the designs ran: one line, why
    if (entries.every((entry) => entry.state === "not run")) {
        const why = [...new Set(entries.map((entry) => entry.why).filter(Boolean))].join("; ");
        return h("section.step-row.idle", anchor, h("div.step-head", {}, h("span.step-index", {}, String(number)), h("strong", {}, title), chip(entries[0], { time: false }), h("span.muted", {}, why)));
    }
    const rows = [...commonRows(key), ...stepRows(key)];
    const facts = h("div.step-facts");
    const table = factsTable(rows.filter((row) => !row[2]?.node));
    facts.append(table, ...rows.filter((row) => row[2]?.node).map((row) => row[2].node));
    // alone, a failure's whole message under the facts
    const error = !page.compare && entries[0].error ? h("pre.error", {}, entries[0].error) : null;
    const left = h(
        "div.step-card",
        {},
        h("div.step-head", {}, h("span.step-index", {}, String(number)), h("strong", {}, title), page.compare ? null : chip(entries[0]), h("span.muted.grow", {}, about)),
        facts,
        error,
    );
    const viz = vizOf(key);
    if (!viz) return h("section.step-row.solo", anchor, left);
    const [panels, size] = viz;
    const host = h(`div.step-viz.${size}`);
    const layout = new Layout(host);
    const region = layout.region(panels, `story.${key}`);
    layouts.push([layout, region]);
    return h("section.step-row", anchor, left, host);
}

// the head: each design (its colour, PDK, name, run, evidence and verdict), its pipeline as chips
// (each scrolls to its step), and compared, which design's visualizations the rows show
function storyHead(onRemove, onView, scroller) {
    const keys = Object.keys(STEPS);
    const lines = page.instances.map((instance, index) => {
        const steps = stepsOf(instance).filter((entry) => keys.includes(entry.step));
        const goto = (key) => () => scroller.querySelector(`#step-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
        const verdictChip = instance.rejected
            ? h("span.stage-chip.rejected", { title: rejection(instance.rejected) }, h("span", { html: glyph("rejected") }), `rejected at ${instance.rejected.step}`)
            : instance.error
              ? h("span.stage-chip.failed", { title: instance.error }, h("span", { html: glyph("failed") }), "failed")
              : null;
        const line = h(
            `div.story-design${page.compare && index === page.shown ? ".on" : ""}`,
            {
                title: page.compare ? `${page.labels[index]?.full || ""}\nClick: show this design's netlist, waveforms, layout and findings on the right` : page.labels[index]?.full || "",
                onclick: page.compare ? () => setShown(index) : null,
            },
            page.compare ? h("span.swatch", { style: { background: colorOf(index) } }) : null,
            h("span.pdk-name", {}, instance.pdk),
            h("strong", {}, instance.label || instance.name || labelOf(index)),
            page.compare && labelOf(index) !== instance.pdk ? h("span.muted", {}, labelOf(index)) : null,
            h("span.mono.muted", { title: "The run" }, instance.file?.split("/runs/")[1] || ""),
            instance.evidence ? h("span.evidence", { title: "What the record's metrics come from" }, words(instance.evidence.toUpperCase())) : null,
            verdictChip,
            h("span.grow"),
            h("div.stage-chips", {}, steps.map((entry) => chip(entry, { label: STEPS[entry.step][0], onclick: (event) => (event.stopPropagation(), goto(entry.step)()) }))),
            page.compare ? h("button.icon-btn.mini", { title: "View this design alone", onclick: (event) => (event.stopPropagation(), onView(instance.id)), html: icon("eye", 13) }) : null,
            h("button.icon-btn.mini", { title: page.compare ? "Remove from the comparison" : "Close: back to every instance", onclick: (event) => (event.stopPropagation(), onRemove(instance.id)), html: icon("x", 13) }),
        );
        return line;
    });
    return h("div.story-key", {}, lines);
}

// the design whose visualizations the rows' right sides show
function setShown(index) {
    if (index === page.shown) return;
    page.shown = index;
    page.head?.querySelectorAll(".story-design").forEach((line, k) => line.classList.toggle("on", k === index));
    shimBlock(shownInstance());
    emit("block", state.block);
    emit("selection");
    emit("story-shown", index);
}

// the instances (their exported files, each with its id and its table's file) in place under host;
// onRemove(id) takes one out of the selection, onView(id) views it alone. Returns the story, destroyed
// on leaving.
export function mountInstances(host, { instances, onRemove, onView }) {
    const compare = instances.length > 1;
    Object.assign(page, { instances, compare, labels: describe(instances), shown: 0, onlyDifferences: recall("compare.differences", true) });
    const barSlot = h("div.bar-slot");
    const toolbar = h("div.panel-toolbar.story-toolbar", {}, barSlot);
    const scroller = h("div.story-scroll");
    const root = h("div.story", {}, toolbar, h("div.story-head"), scroller);
    // the facts' width: a column per design
    root.style.setProperty("--story-left", compare ? `${Math.min(760, 230 + 130 * instances.length)}px` : "390px");
    const offs = [hostBar(barSlot, ["view", "compare"])];
    let layouts = [];
    const render = () => {
        for (const [layout] of layouts) layout.destroy();
        layouts = [];
        page.head = storyHead(onRemove, onView, scroller);
        root.querySelector(".story-head").replaceChildren(page.head);
        const keys = [...new Set(instances.flatMap((instance) => stepsOf(instance).map((entry) => entry.step)))].filter((key) => key in STEPS);
        const order = Object.keys(STEPS).filter((key) => keys.includes(key));
        scroller.replaceChildren(...order.map((key, index) => stepRow(key, index + 1, layouts)));
        for (const [layout, region] of layouts) layout.mount(region);
        shimBlock(shownInstance());
        emit("block", state.block);
        emit("selection");
    };
    if (compare) {
        const toggle = h("label.check", { title: "Hide the parameters every compared design shares" }, h("input", { type: "checkbox", checked: page.onlyDifferences }), "Only the parameters that differ");
        toggle.querySelector("input").addEventListener("change", (event) => {
            page.onlyDifferences = event.target.checked;
            store("compare.differences", page.onlyDifferences);
            const top = scroller.scrollTop;
            render();
            scroller.scrollTop = top;
        });
        toolbar.append(h("span.grow"), toggle);
    }
    host.append(root);
    render();
    // the colours follow the theme
    offs.push(
        on("theme", () => {
            page.head = storyHead(onRemove, onView, scroller);
            root.querySelector(".story-head").replaceChildren(page.head);
        }),
    )
    return {
        destroy() {
            offs.forEach((off) => off());
            for (const [layout] of layouts) layout.destroy();
            root.remove();
            page.head = null;
        },
    };
}
