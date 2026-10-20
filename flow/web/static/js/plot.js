// Plot and results panels. A plot shows one metric of one result set over the field the set
// sweeps (or a curve over its own axis, or one value per series), every selected series overlaid;
// a curve per sweep point draws the chosen points' curves. Clicking a point leaves it out (and
// back in). Colours, ticks and grid are those of flow/analysis/plots.py, on Nord's dark paper in
// the dark theme, in a plain sans font on screen; saved SVGs are the Matplotlib figure itself:
// paper and Computer Modern.

import { h, icon, select } from "./icons.js";
import { COLORS, DASHES, on, selectionChanged, series, state, status } from "./store.js";
import { axisTitle, fieldInfo, formatValue, siExponent } from "./units.js";

const PT = 4 / 3; // px per point
// text on screen, and on a saved SVG (PLOT_STYLE's sizes in points)
const FONTS = {
    screen: { family: 'Inter, "Segoe UI", "Helvetica Neue", Arial, "Liberation Sans", "DejaVu Sans", sans-serif', tick: 13, axis: 14, title: 15, legend: 12.5 },
    paper: { family: "CMU Serif, Computer Modern Roman, Latin Modern Roman, DejaVu Serif, serif", tick: 10 * PT, axis: 10 * PT, title: 12 * PT, legend: 8.33 * PT },
};
// flow/analysis/plots.py's colours (light, and every saved SVG) and their dark counterparts
const PAPERS = {
    light: { paper: "#fff", ink: "#000", spine: "#4C566A", major: "#D8DEE9", minor: "#E5E9F0", legend: "rgba(236, 239, 244, 0.9)", hover: "#ECEFF4" },
    dark: { paper: "#2E3440", ink: "#ECEFF4", spine: "#8F9BB0", major: "rgba(216, 222, 233, 0.13)", minor: "rgba(216, 222, 233, 0.06)", legend: "rgba(59, 66, 82, 0.92)", hover: "#3B4252" },
};
PAPERS.paper = PAPERS.light;

function currentTheme() {
    return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

// NORD_DARK, the last curve colour, would vanish on the dark paper
function tone(color, theme) {
    return theme === "dark" && color.toUpperCase() === "#4C566A" ? "#D8DEE9" : color;
}

function datasetOf(key) {
    return state.block?.datasets.find((item) => item.key === key) || null;
}

function recordOf(dataset, item) {
    return state.results?.[dataset.key]?.[item.pdk]?.[item.case] || null;
}

function shapeOf(value) {
    if (!Array.isArray(value)) return typeof value === "number" || typeof value === "boolean" ? [] : null;
    return Array.isArray(value[0]) ? [value.length, value[0].length] : [value.length];
}

function numeric(value) {
    return value === null || typeof value === "number" || typeof value === "boolean";
}

function flat(value) {
    return Array.isArray(value) ? value.flat(2) : [value];
}

function varies(values) {
    const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value));
    return finite.length > 1 && finite.some((value) => value !== finite[0]);
}

function monotonic(values) {
    const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value));
    if (finite.length < 2) return false;
    let up = true;
    let down = true;
    for (let i = 1; i < finite.length; i++) {
        if (finite[i] <= finite[i - 1]) up = false;
        if (finite[i] >= finite[i - 1]) down = false;
    }
    return up || down;
}

// a sample record of the dataset among the selected series (or any)
function sampleRecord(dataset) {
    for (const item of series()) {
        const record = recordOf(dataset, item);
        if (record) return record;
    }
    const byPdk = state.results?.[dataset.key] || {};
    for (const pdk of Object.keys(byPdk)) {
        for (const name of Object.keys(byPdk[pdk])) return byPdk[pdk][name];
    }
    return null;
}

// the dataset's plottable fields: name, info, shape (from a sample record)
function fieldsOf(dataset) {
    const record = sampleRecord(dataset);
    if (!record) return [];
    const out = [];
    for (const { name } of dataset.fields) {
        const value = record[name];
        const shape = shapeOf(value);
        if (shape === null) continue;
        if (Array.isArray(value) && !flat(value).every(numeric)) continue;
        out.push({ name, info: fieldInfo(name), shape, value });
    }
    return out;
}

function kindOf(field) {
    if (field.shape.length === 2) return "curve";
    if (field.shape.length === 1 && field.shape[0] > 1) return "sweep";
    return "scalar";
}

// partners plotted together, and their names in a legend
const PAIRS = [["rise", "fall"], ["n", "p"], ["on", "off"]];
const PAIR_WORDS = { rise: "rise", fall: "fall", n: "NMOS", p: "PMOS", on: "on", off: "off" };

// a 2-D field that a curve is drawn against rather than a result: an input or time on a grid
function axisLike(field) {
    return field.shape.length === 2 && /^(inp?|vin|vout|input|time|frequency)(_|$)/.test(field.name);
}

// the field a result set sweeps: the first 1-D field, in the analysis' order, that varies and is
// monotonic; else the first that varies
function sweepAxis(fields) {
    const candidates = fields.filter((field) => kindOf(field) === "sweep" && varies(field.value));
    return candidates.find((field) => monotonic(field.value)) || candidates[0] || null;
}

// what a curve is drawn against: a monotonic 1-D field of its length, else a grid field beside it
function curveAxis(fields, field) {
    const length = field.shape[1];
    const line = fields.find((other) => other.shape.length === 1 && other.shape[0] === length && monotonic(other.value));
    const grid = fields.find((other) => other !== field && axisLike(other) && String(other.shape) === String(field.shape));
    return line?.name || grid?.name || "#index";
}

// a field's partner (rise_x and fall_x, n_x and p_x, on_x and off_x) of the same shape, in order
function pairOf(field, fields) {
    const tokens = field.name.split("_");
    for (const [a, b] of PAIRS) {
        for (const [mine, other] of [[a, b], [b, a]]) {
            const index = tokens.indexOf(mine);
            if (index < 0) continue;
            const name = [...tokens.slice(0, index), other, ...tokens.slice(index + 1)].join("_");
            const partner = fields.find((item) => item.name === name && String(item.shape) === String(field.shape));
            if (!partner) continue;
            const base = fieldInfo([...tokens.slice(0, index), ...tokens.slice(index + 1)].join("_")).label;
            return { fields: mine === a ? [field, partner] : [partner, field], words: [PAIR_WORDS[a], PAIR_WORDS[b]], label: `${base} (${PAIR_WORDS[a]}, ${PAIR_WORDS[b]})` };
        }
    }
    return null;
}

// the metrics a plot offers: each result over the swept field; curves over their own axis; and
// single values that differ between the shown series, one point per series
function metricsOf(dataset, fields) {
    const axis = sweepAxis(fields);
    const shownValues = (field) =>
        series().flatMap((item) => {
            const value = recordOf(dataset, item)?.[field.name];
            return Array.isArray(value) ? value.flat() : [value];
        });
    const metrics = [];
    const used = new Set();
    const add = (field, kind, x, group) => {
        if (used.has(field.name)) return;
        const pair = pairOf(field, fields);
        const members = pair ? pair.fields : [field];
        members.forEach((member) => used.add(member.name));
        metrics.push({ value: members.map((member) => member.name).join(","), names: members.map((member) => member.name), kind, x, group, words: pair?.words || null, label: pair?.label || field.info.label });
    };
    if (axis) {
        for (const field of fields) {
            // a result changes over the sweep; a condition (the supply of a period sweep) does not
            const changes = series().some((item) => {
                const value = recordOf(dataset, item)?.[field.name];
                return Array.isArray(value) && varies(value);
            });
            if (field !== axis && kindOf(field) === "sweep" && field.shape[0] === axis.shape[0] && changes) add(field, "sweep", axis.name, `Over ${axis.info.label.toLowerCase()}`);
        }
    }
    for (const field of fields) if (kindOf(field) === "curve" && !axisLike(field)) add(field, "curve", curveAxis(fields, field), "Curves");
    for (const field of fields) if (kindOf(field) === "scalar" && varies(shownValues(field))) add(field, "scalar", "#series", "One value per series");
    return metrics;
}

function rowLabels(fields, record, yField) {
    const rows = yField.shape[0];
    const candidates = fields.filter((field) => field.shape.length === 1 && field.shape[0] === rows && varies(record[field.name] || []));
    const labelField = candidates.find((field) => monotonic(record[field.name])) || candidates[0];
    return Array.from({ length: rows }, (_, index) => {
        if (!labelField) return `#${index + 1}`;
        return `${labelField.info.label} ${formatValue(record[labelField.name][index], labelField.info)}`;
    });
}

function paperAxis(title, log, colors, fonts) {
    return {
        title: { text: title, font: { size: fonts.axis }, standoff: 6 },
        type: log ? "log" : "linear",
        dtick: log ? 1 : undefined,
        showline: true,
        linecolor: colors.spine,
        linewidth: 0.8 * PT,
        mirror: "ticks",
        ticks: "inside",
        ticklen: 2.5 * PT,
        tickwidth: 0.8,
        tickcolor: colors.ink,
        tickfont: { size: fonts.tick },
        minor: { ticks: "inside", ticklen: 1.5 * PT, tickcolor: colors.ink, showgrid: true, gridcolor: colors.minor, gridwidth: 0.5 * PT },
        showgrid: true,
        gridcolor: colors.major,
        gridwidth: 0.8 * PT,
        zeroline: false,
        exponentformat: "power",
        automargin: true,
    };
}

// mode: "dark" or "light" on screen, "paper" for a saved SVG
export function paperLayout(title, xTitle, yTitle, logX, logY, legendCount, mode = currentTheme()) {
    const colors = PAPERS[mode];
    const fonts = mode === "paper" ? FONTS.paper : FONTS.screen;
    const legend = { bgcolor: colors.legend, bordercolor: colors.spine, borderwidth: 0.8, font: { size: fonts.legend } };
    return {
        paper_bgcolor: colors.paper,
        plot_bgcolor: colors.paper,
        font: { family: fonts.family, size: fonts.tick, color: colors.ink },
        title: { text: title, font: { size: fonts.title }, x: 0.5, xanchor: "center", y: 0.97 },
        margin: { l: 74, r: 22, t: 48, b: 58 },
        xaxis: paperAxis(xTitle, logX, colors, fonts),
        yaxis: paperAxis(yTitle, logY, colors, fonts),
        showlegend: legendCount > 0,
        legend:
            legendCount > 4
                ? { ...legend, x: 1.02, xanchor: "left", y: 1, yanchor: "top" }
                : { ...legend, x: 0.99, xanchor: "right", y: 0.99, yanchor: "top" },
        hovermode: "closest",
        hoverlabel: { bgcolor: colors.hover, bordercolor: colors.spine, font: { family: fonts.family, size: 13, color: colors.ink } },
        dragmode: "zoom",
    };
}

const PLOT_CONFIG = {
    displaylogo: false,
    displayModeBar: "hover",
    scrollZoom: true,
    responsive: false,
    edits: { legendPosition: true },
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines", "hoverClosestCartesian", "hoverCompareCartesian"],
};

export class PlotPanel {
    constructor(container, saved) {
        this.container = container;
        this.config = { dataset: null, metric: null, logX: null, logY: null, rows: null, ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.rowsBar = h("div.rows-bar", { style: { display: "none" } });
        this.paper = h("div.paper");
        this.host = h("div.plot-host");
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("chart", 28) }), h("strong", {}, "Nothing to plot"), h("span", {}, "Select a block, PDKs and cases."));
        this.paper.append(this.host);
        this.element.append(this.toolbar, this.rowsBar, h("div.panel-body.fill", {}, this.paper, this.emptyNote));
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.off = [on("block", () => this.blockChanged()), on("selection", () => this.render()), on("theme", () => this.render())];
        container.on("resize", () => this.resize());
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            if (window.Plotly) window.Plotly.purge(this.host);
        });
        if (state.block) this.blockChanged();
    }

    blockChanged() {
        const datasets = state.block?.datasets || [];
        if (!datasets.some((item) => item.key === this.config.dataset)) {
            const index = this.config.slot || 0;
            this.config.dataset = datasets[Math.min(index, datasets.length - 1)]?.key || null;
            this.resetFields();
        }
        this.render();
    }

    // the result set's first metric, axes chosen afresh
    resetFields() {
        this.config.metric = null;
        this.config.logX = null;
        this.config.logY = null;
        this.config.rows = null;
    }

    buildToolbar(dataset, metrics) {
        const toolbar = this.toolbar;
        toolbar.replaceChildren();
        const datasets = state.block?.datasets || [];
        toolbar.append(
            h(
                "label.field",
                {},
                h("span", {}, "Result"),
                select(
                    datasets.map((item) => ({ value: item.key, label: item.title })),
                    this.config.dataset,
                    (value) => {
                        this.config.dataset = value;
                        this.resetFields();
                        this.render();
                    },
                ),
            ),
        );
        if (!dataset) return;
        // the metrics, grouped: over the swept field, curves, one value per series
        const chooser = h("select", { title: "The metric to plot" });
        for (const group of [...new Set(metrics.map((metric) => metric.group))]) {
            const options = h("optgroup", { label: group });
            for (const metric of metrics.filter((item) => item.group === group)) options.append(h("option", { value: metric.value }, metric.label));
            chooser.append(options);
        }
        chooser.value = this.config.metric || "";
        chooser.addEventListener("change", () => {
            this.config.metric = chooser.value;
            this.config.logX = null;
            this.config.logY = null;
            this.config.rows = null;
            this.render();
        });
        toolbar.append(h("label.field", {}, h("span", {}, "Metric"), chooser));
        toolbar.append(h("span.grow"));
        const logX = h("button.icon-btn", { title: "Logarithmic x axis", onclick: () => { this.config.logX = !this.logX; this.render(); } }, "log x");
        const logY = h("button.icon-btn", { title: "Logarithmic y axis", onclick: () => { this.config.logY = !this.logY; this.render(); } }, "log y");
        if (this.logX) logX.classList.add("on");
        if (this.logY) logY.classList.add("on");
        const excluded = [...state.excludedPoints].filter((key) => key.startsWith(`${dataset.key}|`)).length;
        toolbar.append(
            logX,
            logY,
            h(
                "button.icon-btn",
                {
                    title: excluded ? `Restore ${excluded} left-out points` : "Click a point to leave it out",
                    disabled: !excluded,
                    onclick: () => {
                        for (const key of [...state.excludedPoints]) if (key.startsWith(`${dataset.key}|`)) state.excludedPoints.delete(key);
                        selectionChanged();
                    },
                },
                h("span", { html: icon("points", 14) }),
                excluded ? `${excluded}` : "",
            ),
            h(
                "button.icon-btn",
                {
                    title: "Save the plot as SVG (on paper, as the Matplotlib figures)",
                    onclick: () =>
                        this.figure &&
                        window.Plotly.downloadImage(this.figure("paper"), {
                            format: "svg",
                            filename: `${state.block.name}_${dataset.key.replace(":", "_")}`,
                            width: this.host.clientWidth,
                            height: this.host.clientHeight,
                        }),
                },
                h("span", { html: icon("download", 14) }),
            ),
        );
    }

    buildRows(labels) {
        const bar = this.rowsBar;
        bar.replaceChildren();
        if (!labels || labels.length < 2) {
            bar.style.display = "none";
            return;
        }
        bar.style.display = "";
        const rows = new Set(this.rows(labels.length));
        bar.append(h("span.field", {}, h("span", {}, "Points")));
        labels.forEach((label, index) => {
            const chip = h("span.chip", { title: "Show or hide this point's curve" }, label);
            if (rows.has(index)) chip.classList.add("on");
            chip.addEventListener("click", () => {
                if (rows.has(index)) rows.delete(index);
                else rows.add(index);
                this.config.rows = [...rows].sort((a, b) => a - b);
                this.render();
            });
            bar.append(chip);
        });
        bar.append(
            h("span.link", { onclick: () => { this.config.rows = labels.map((_, index) => index); this.render(); } }, "all"),
            h("span.link", { onclick: () => { this.config.rows = [0]; this.render(); } }, "first"),
        );
    }

    rows(count) {
        if (Array.isArray(this.config.rows)) return this.config.rows.filter((index) => index < count);
        if (count <= 8) return Array.from({ length: count }, (_, index) => index);
        return [0, Math.floor((count - 1) / 2), count - 1];
    }

    render() {
        if (!window.Plotly) return;
        const dataset = datasetOf(this.config.dataset);
        const fields = dataset ? fieldsOf(dataset) : [];
        const metrics = dataset ? metricsOf(dataset, fields) : [];
        let metric = metrics.find((item) => item.value === this.config.metric);
        if (!metric) {
            metric = metrics[0] || null;
            this.config.metric = metric?.value || null;
            this.config.logX = null;
            this.config.logY = null;
            this.config.rows = null;
        }
        this.buildToolbar(dataset, metrics);
        const yFields = (metric?.names || []).map((name) => fields.find((field) => field.name === name)).filter(Boolean);
        const shown = series();
        if (!dataset || !yFields.length || !shown.length) {
            this.buildRows(null);
            this.empty(true, !state.block ? "Select a block." : !shown.length ? "Select at least one PDK and case." : "This result has no plottable fields.");
            return;
        }
        const kind = metric.kind;
        const xName = metric.x;
        const xField = fields.find((field) => field.name === xName);
        const traces = [];
        const yValues = [];
        const xValues = [];
        let rowLabelList = null;
        const fieldDash = (index) => (yFields.length > 1 ? DASHES[index % DASHES.length] : null);

        for (const item of shown) {
            const record = recordOf(dataset, item);
            if (!record) continue;
            yFields.forEach((yField, fieldIndex) => {
                const y = record[yField.name];
                if (y === undefined) return;
                const name = yFields.length > 1 ? `${item.label} (${metric.words?.[fieldIndex] || yField.info.label})` : item.label;
                const dash = fieldDash(fieldIndex) || item.dash;
                if (kind === "scalar" || xName === "#series") {
                    const value = Array.isArray(y) ? y[0] : y;
                    traces.push({ series: item, field: yField, type: "category", x: [item.label], y: [value], name, color: item.color, symbol: item.symbol, dash });
                    yValues.push(value);
                } else if (kind === "sweep") {
                    const x = xName === "#index" ? y.map((_, index) => index) : record[xName];
                    if (!x) return;
                    traces.push({ series: item, field: yField, type: "sweep", x, y, name, color: item.color, symbol: item.symbol, dash });
                    yValues.push(...y);
                    xValues.push(...x);
                } else {
                    const labels = rowLabels(fields, record, yField);
                    rowLabelList = rowLabelList || labels;
                    const rows = this.rows(y.length);
                    rows.forEach((row, rowIndex) => {
                        if (!y[row]) return;
                        const xSource = xName === "#index" ? null : record[xName];
                        const x = !xSource ? y[row].map((_, index) => index) : Array.isArray(xSource[0]) ? xSource[row] : xSource;
                        const single = shown.length === 1 && yFields.length === 1;
                        traces.push({
                            series: item,
                            field: yField,
                            type: "curve",
                            x,
                            y: y[row],
                            name: single ? labels[row] : rows.length > 1 ? `${name}, ${labels[row]}` : name,
                            color: single ? COLORS[rowIndex % COLORS.length] : item.color,
                            dash: single ? "solid" : dash,
                            opacity: single || rows.length < 2 ? 1 : 0.45 + 0.55 * (1 - rowIndex / Math.max(1, rows.length - 1)),
                        });
                        yValues.push(...y[row]);
                        xValues.push(...x);
                    });
                }
            });
        }
        this.buildRows(kind === "curve" ? rowLabelList : null);
        if (!traces.length) {
            this.empty(true, "No result for the selected PDKs and cases.");
            return;
        }
        this.empty(false);

        const xInfo = xField?.info || { label: xName === "#series" ? "" : "Index", unit: "", scalable: false };
        // max over min of the finite values when all are positive, else 0 (a loop: curves hold too
        // many values to spread into Math.max)
        const span = (values) => {
            let low = Infinity;
            let high = 0;
            for (const value of values) {
                if (typeof value !== "number" || !Number.isFinite(value)) continue;
                if (value <= 0) return 0;
                low = Math.min(low, value);
                high = Math.max(high, value);
            }
            return high ? high / low : 0;
        };
        if (this.config.logX === null) this.logX = kind !== "scalar" && xName !== "#series" && (/freq|_hz$/.test(xName) || span(xValues) > 300);
        else this.logX = this.config.logX;
        if (this.config.logY === null) this.logY = span(yValues) > 1e3;
        else this.logY = this.config.logY;
        this.buildToolbar(dataset, metrics);
        // SI prefixes on linear axes; a log axis keeps the base unit and labels its decades
        const yExponent = yFields[0].info.scalable && !this.logY ? siExponent(yValues) : 0;
        const xExponent = xInfo.scalable && !this.logX ? siExponent(xValues) : 0;

        const build = (theme) => {
            const colors = PAPERS[theme];
            const data = [];
            for (const trace of traces) {
                const color = tone(trace.color, theme);
                const yScale = 10 ** -yExponent;
                const xScale = 10 ** -xExponent;
                const base = {
                    name: trace.name,
                    legendgroup: `${trace.series.key}|${trace.field.name}`,
                    hovertemplate: `${trace.name}<br>%{x}, %{y}<extra></extra>`,
                };
                if (trace.type === "category") {
                    data.push({ ...base, type: "scatter", mode: "markers", x: trace.x, y: trace.y.map((v) => (v === null ? null : v * yScale)), marker: { color, size: 9, symbol: trace.symbol, line: { color: colors.ink, width: 0.5 } } });
                    continue;
                }
                if (trace.type === "curve") {
                    data.push({
                        ...base,
                        type: "scatter",
                        mode: "lines",
                        x: trace.x.map((v) => (v === null ? null : v * xScale)),
                        y: trace.y.map((v) => (v === null ? null : v * yScale)),
                        line: { color, width: 1.2 * PT, dash: trace.dash },
                        opacity: trace.opacity,
                    });
                    continue;
                }
                // in x order, so a result holding several sweeps draws as one curve
                const order = trace.y.map((_, index) => index).sort((a, b) => (trace.x[a] ?? Infinity) - (trace.x[b] ?? Infinity));
                const keep = [];
                const left = [];
                for (const index of order) {
                    const key = `${dataset.key}|${trace.series.key}|${trace.field.name}|${index}`;
                    (state.excludedPoints.has(key) ? left : keep).push(index);
                }
                const markers = trace.y.length <= 80;
                data.push({
                    ...base,
                    type: "scatter",
                    mode: markers ? "lines+markers" : "lines",
                    x: keep.map((index) => (trace.x[index] === null ? null : trace.x[index] * xScale)),
                    y: keep.map((index) => (trace.y[index] === null ? null : trace.y[index] * yScale)),
                    customdata: keep.map((index) => [`${dataset.key}|${trace.series.key}|${trace.field.name}|${index}`]),
                    line: { color, width: 1.0 * PT, dash: trace.dash },
                    marker: { color, size: 5.5, symbol: trace.symbol },
                });
                if (left.length) {
                    data.push({
                        ...base,
                        name: `${trace.name} (left out)`,
                        showlegend: false,
                        type: "scatter",
                        mode: "markers",
                        x: left.map((index) => (trace.x[index] === null ? null : trace.x[index] * xScale)),
                        y: left.map((index) => (trace.y[index] === null ? null : trace.y[index] * yScale)),
                        customdata: left.map((index) => [`${dataset.key}|${trace.series.key}|${trace.field.name}|${index}`]),
                        marker: { color: "rgba(0,0,0,0)", size: 7, symbol: "circle-open", line: { color: "#8F9BB0", width: 1.2 } },
                        hovertemplate: `${trace.name}: left out<br>%{x}, %{y}<extra>click to restore</extra>`,
                    });
                }
            }
            return data;
        };
        const pdks = new Set(shown.map((item) => item.pdk));
        const title = `${dataset.title}${pdks.size === 1 ? ` · ${[...pdks][0]}` : ""}`;
        const xTitle = xName === "#series" ? "" : axisTitle([xInfo], xExponent);
        const yTitle = axisTitle(yFields.map((field) => field.info), yExponent);
        const logX = this.logX;
        const logY = this.logY;
        // the figure on screen ("dark" or "light") or saved ("paper")
        this.figure = (mode) => {
            const data = build(mode);
            const legendCount = data.filter((trace) => trace.showlegend !== false).length;
            const layout = paperLayout(title, xTitle, yTitle, logX, logY, legendCount > 1 || yFields.length > 1 ? legendCount : 0, mode);
            if (xName === "#series") layout.xaxis.type = "category";
            return { data, layout };
        };
        const { data, layout } = this.figure(currentTheme());
        window.Plotly.react(this.host, data, layout, PLOT_CONFIG).then(() => {
            if (this.bound) return;
            this.bound = true;
            this.host.on("plotly_click", (event) => {
                const point = event.points?.[0];
                const key = point?.customdata?.[0];
                if (!key) return;
                if (state.excludedPoints.has(key)) state.excludedPoints.delete(key);
                else state.excludedPoints.add(key);
                status(state.excludedPoints.has(key) ? "Point left out: click its ring to restore it" : "Point restored");
                selectionChanged();
            });
        });
    }

    empty(show, message) {
        this.emptyNote.style.display = show ? "" : "none";
        this.paper.style.visibility = show ? "hidden" : "visible";
        if (message) this.emptyNote.lastChild.textContent = message;
    }

    resize() {
        cancelAnimationFrame(this.frame);
        this.frame = requestAnimationFrame(() => {
            if (window.Plotly && this.host.offsetWidth && this.host.data) window.Plotly.Plots.resize(this.host);
        });
    }
}

export class TablePanel {
    constructor(container, saved) {
        this.container = container;
        this.config = { dataset: null, point: 0, sort: null, ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.off = [on("block", () => this.render()), on("selection", () => this.render())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        if (state.block) this.render();
    }

    render() {
        const datasets = state.block?.datasets || [];
        if (!datasets.some((item) => item.key === this.config.dataset)) this.config.dataset = datasets[0]?.key || null;
        const dataset = datasetOf(this.config.dataset);
        this.toolbar.replaceChildren(
            h(
                "label.field",
                {},
                h("span", {}, "Result"),
                select(datasets.map((item) => ({ value: item.key, label: item.title })), this.config.dataset, (value) => {
                    this.config.dataset = value;
                    this.config.point = 0;
                    this.render();
                }),
            ),
        );
        this.body.replaceChildren();
        if (!dataset) {
            this.body.append(h("div.empty", {}, h("span", { html: icon("table", 28) }), h("strong", {}, "No results"), h("span", {}, "Select a block.")));
            return;
        }
        const fields = fieldsOf(dataset);
        const sweeps = fields.filter((field) => kindOf(field) === "sweep");
        const length = Math.max(0, ...sweeps.map((field) => field.shape[0]));
        const sweepFields = sweeps.filter((field) => field.shape[0] === length);
        const columns = [...fields.filter((field) => kindOf(field) === "scalar"), ...sweepFields];
        if (length > 1) {
            const record = sampleRecord(dataset);
            const axis = sweepFields.find((field) => monotonic(record[field.name])) || sweepFields[0];
            this.config.point = Math.min(this.config.point, length - 1);
            this.toolbar.append(
                h(
                    "label.field",
                    {},
                    h("span", {}, "At"),
                    select(
                        Array.from({ length }, (_, index) => ({ value: String(index), label: `${axis.info.label} = ${formatValue(record[axis.name][index], axis.info)}` })),
                        String(this.config.point),
                        (value) => {
                            this.config.point = Number(value);
                            this.render();
                        },
                    ),
                ),
            );
        }
        this.toolbar.append(
            h("span.grow"),
            h("button.icon-btn", { title: "Copy the table (tab-separated)", onclick: () => this.copy() }, h("span", { html: icon("download", 14) }), "Copy"),
        );
        const rows = series()
            .map((item) => ({ item, record: recordOf(dataset, item) }))
            .filter((row) => row.record);
        const valueOf = (record, field) => {
            const value = record[field.name];
            return Array.isArray(value) ? value[Math.min(this.config.point, value.length - 1)] : value;
        };
        if (this.config.sort) {
            const { name, descending } = this.config.sort;
            const field = columns.find((column) => column.name === name);
            if (field) {
                rows.sort((a, b) => {
                    const x = valueOf(a.record, field);
                    const y = valueOf(b.record, field);
                    const order = (x ?? -Infinity) > (y ?? -Infinity) ? 1 : (x ?? -Infinity) < (y ?? -Infinity) ? -1 : 0;
                    return descending ? -order : order;
                });
            }
        }
        const table = h("table.grid");
        const head = h("tr", {}, h("th", {}, "Series"));
        for (const field of columns) {
            const th = h("th", { title: field.name }, field.info.label, h("span.unit", {}, field.info.unit || "—"));
            th.addEventListener("click", () => {
                const descending = this.config.sort?.name === field.name ? !this.config.sort.descending : false;
                this.config.sort = { name: field.name, descending };
                this.render();
            });
            head.append(th);
        }
        table.append(h("thead", {}, head));
        const body = h("tbody");
        for (const { item, record } of rows) {
            const tr = h("tr", {}, h("td", {}, h("span.series-dot", { style: { background: item.color, display: "inline-block", marginRight: "8px" } }), item.label));
            for (const field of columns) {
                const value = valueOf(record, field);
                const td = h("td", {}, formatValue(value, field.info));
                if (value === null || value === undefined) td.classList.add("nan");
                tr.append(td);
            }
            body.append(tr);
        }
        table.append(body);
        this.lastTable = { columns, rows, valueOf };
        this.body.append(table);
    }

    copy() {
        const { columns, rows, valueOf } = this.lastTable || {};
        if (!columns) return;
        const lines = [["series", ...columns.map((field) => field.name)].join("\t")];
        for (const { item, record } of rows) lines.push([item.label, ...columns.map((field) => valueOf(record, field) ?? "")].join("\t"));
        navigator.clipboard?.writeText(lines.join("\n")).then(() => status("Table copied"), () => status("The clipboard is not available here", true));
    }
}

