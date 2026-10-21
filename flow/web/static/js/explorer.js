// The design-space explorer: a block's sweep (python -m flow.sweep table) as one table, a row per
// instance (its PDK, topology and sizing, the parameters that differ, then the metrics), and a
// scatter plot of any metric against any other, coloured by PDK and marked by topology. A column
// header sorts and filters; hovering a row or a point lights up the other; clicking a point (or a
// row's pin) pins it, across axis changes; a row's detail button opens the instance's own page.
// The three are GoldenLayout panels (Blocks, Sweeps, Metrics), as the instance page's.

import { GoldenLayout } from "golden-layout";
import { h, icon, popover, select, toast } from "./icons.js";
import { currentTheme, PAPERS, paperLayout, tone } from "./paper.js";
import { COLORS, recall, store } from "./store.js";
import { fieldInfo, scaledUnit, siExponent } from "./units.js";

const PDK_ORDER = ["tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65"];
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "triangle-down", "cross", "x", "star", "hexagon", "pentagon", "hourglass", "bowtie"];

const view = {
    catalog: null,
    block: null, // the block's table
    columns: [],
    rows: [], // shown, in order
    sort: null, // {key, dir}
    filters: {}, // key -> {values: [...]} or {min, max}
    pins: new Set(),
    hover: null,
    x: null,
    y: null,
    logX: false,
    logY: false,
    dragmode: "zoom", // the scatter's drag: box zoom or pan
};

async function fetchJson(path) {
    const response = await fetch(`data/${path}`);
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
}

// ---- columns ----------------------------------------------------------------------------------

function buildColumns(table) {
    const rows = table.rows;
    const numeric = (get) => rows.every((row) => {
        const value = get(row);
        return value === null || value === undefined || typeof value === "number";
    });
    // an instance is a PDK, a topology and a sizing of the block's sweep (flow/<block>/sweep.py):
    // the names its parameters come from, the parameters' columns after them
    const columns = [
        { key: "pdk", label: "pdk", kind: "cat", get: (row) => row.pdk, group: "instance", note: "The PDK" },
        { key: "topology", label: "topology", kind: "cat", get: (row) => row.topology, group: "instance", note: "The sweep's topology (TOPOLOGIES in the block's sweep.py): it sets the circuit's structural parameters" },
        { key: "sizing", label: "sizing", kind: "cat", get: (row) => row.sizing, group: "instance", note: "The sweep's sizing (SIZINGS in the block's sweep.py): it scales the key devices' sizes" },
    ];
    for (const name of table.params) {
        const get = (row) => row.params[name];
        columns.push({ key: `p:${name}`, label: name, kind: numeric(get) ? "num" : "cat", get, group: "parameters", info: { label: name, unit: "", scalable: false }, decimals: decimalsOf(rows, get) });
    }
    for (const name of table.metrics) {
        const get = (row) => row.metrics[name];
        const info = fieldInfo(name);
        const exponent = siExponent(rows.map(get));
        columns.push({ key: `m:${name}`, label: info.label, unit: scaledUnit(info, info.scalable ? exponent : 0), kind: "num", get, group: "metrics", info, exponent: info.scalable ? exponent : 0, metric: name, decimals: decimalsOf(rows, get) });
    }
    // each group's first column draws the line between the groups
    columns.forEach((column, index) => {
        column.first = index > 0 && columns[index - 1].group !== column.group;
    });
    return columns;
}

function columnOf(key) {
    return view.columns.find((column) => column.key === key) || null;
}

// a number at its column's scale and decimals: three (to 0.001 of the column's unit), none in a
// column of whole numbers, so the column's points line up
function cellText(column, value) {
    if (value === null || value === undefined || (typeof value === "number" && !Number.isFinite(value))) return "—";
    if (column.kind !== "num" || typeof value !== "number") return String(value);
    const text = (value / 10 ** (column.exponent || 0)).toFixed(column.decimals);
    return /^-0\.?0*$/.test(text) ? text.slice(1) : text;
}

function decimalsOf(rows, get) {
    return rows.every((row) => {
        const value = get(row);
        return !Number.isFinite(value) || Number.isInteger(value);
    })
        ? 0
        : 3;
}

// ---- filtering and sorting --------------------------------------------------------------------

function passes(row) {
    for (const [key, filter] of Object.entries(view.filters)) {
        const column = columnOf(key);
        if (!column) continue;
        const value = column.get(row);
        if (filter.values && !filter.values.includes(value === undefined ? null : value)) return false;
        if (filter.min !== undefined && filter.min !== null && !(value >= filter.min)) return false;
        if (filter.max !== undefined && filter.max !== null && !(value <= filter.max)) return false;
    }
    return true;
}

function orderRows() {
    const rows = view.block.rows.filter(passes);
    if (view.sort) {
        const column = columnOf(view.sort.key);
        const sign = view.sort.dir === "asc" ? 1 : -1;
        rows.sort((a, b) => {
            const va = column.get(a);
            const vb = column.get(b);
            const missingA = va === null || va === undefined || (typeof va === "number" && !Number.isFinite(va));
            const missingB = vb === null || vb === undefined || (typeof vb === "number" && !Number.isFinite(vb));
            if (missingA || missingB) return missingA - missingB;
            return (typeof va === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true })) * sign;
        });
    }
    view.rows = rows;
}

function save() {
    if (!view.block) return;
    store(`sweep.${view.block.block}`, {
        sort: view.sort,
        filters: view.filters,
        pins: [...view.pins],
        x: view.x,
        y: view.y,
        logX: view.logX,
        logY: view.logY,
    });
}

// the header's popover: sort both ways; tick the values to keep (categories) or bound the range
function headerMenu(anchor, column) {
    popover(anchor, (element) => {
        element.classList.add("filter-pop");
        const sortRow = h(
            "div.filter-sort",
            {},
            h("button.icon-btn", { onclick: () => { view.sort = { key: column.key, dir: "asc" }; element.remove(); refresh(); } }, "Sort ascending"),
            h("button.icon-btn", { onclick: () => { view.sort = { key: column.key, dir: "desc" }; element.remove(); refresh(); } }, "Sort descending"),
        );
        element.append(h("div.filter-title", {}, column.label, column.unit ? ` (${column.unit})` : ""), sortRow);
        const current = view.filters[column.key];
        if (column.kind === "cat") {
            const counts = new Map();
            for (const row of view.block.rows) {
                const value = column.get(row) ?? null;
                counts.set(value, (counts.get(value) || 0) + 1);
            }
            const values = [...counts.keys()].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
            const kept = new Set(current?.values ?? values);
            const list = h("div.filter-values");
            for (const value of values) {
                const box = h("input", { type: "checkbox" });
                box.checked = kept.has(value);
                box.addEventListener("change", () => {
                    if (box.checked) kept.add(value);
                    else kept.delete(value);
                    apply();
                });
                const only = h("button.link", { title: "Only this value", onclick: (event) => { event.preventDefault(); kept.clear(); kept.add(value); for (const input of list.querySelectorAll("input")) input.checked = input === box; apply(); } }, "only");
                list.append(h("label.filter-value", {}, box, h("span", {}, value === null ? "—" : String(value)), h("span.muted", {}, `${counts.get(value)}`), only));
            }
            const apply = () => {
                if (kept.size === values.length) delete view.filters[column.key];
                else view.filters[column.key] = { values: [...kept] };
                refresh();
            };
            element.append(list, h("div.filter-sort", {}, h("button.icon-btn", { onclick: () => { for (const input of list.querySelectorAll("input")) input.checked = true; kept.clear(); values.forEach((value) => kept.add(value)); apply(); } }, "All")));
        } else {
            const scale = 10 ** (column.exponent || 0);
            const bound = (name) => {
                const input = h("input.num", { type: "number", step: "any", placeholder: name, value: current?.[name] !== undefined && current?.[name] !== null ? +(current[name] / scale).toPrecision(6) : "" });
                input.addEventListener("change", () => {
                    const filter = view.filters[column.key] || {};
                    filter[name] = input.value === "" ? null : Number(input.value) * scale;
                    if (filter.min === null && filter.max === null) delete view.filters[column.key];
                    else view.filters[column.key] = filter;
                    refresh();
                });
                return input;
            };
            element.append(h("div.filter-range", {}, bound("min"), h("span", {}, "to"), bound("max"), h("span.muted", {}, column.unit || "")));
        }
        if (current) element.append(h("div.filter-sort", {}, h("button.icon-btn", { onclick: () => { delete view.filters[column.key]; element.remove(); refresh(); } }, "Clear filter")));
    });
}

// ---- table ------------------------------------------------------------------------------------

function renderTable() {
    const table = document.getElementById("instances");
    const head = h("thead");
    // the groups over the columns: the instance's names, its parameters, its metrics
    const groupRow = h("tr.groups", {}, h("th.tools", {}, ""));
    for (const column of view.columns) {
        const last = groupRow.lastChild;
        if (last.dataset.group === column.group) last.colSpan += 1;
        else groupRow.append(h(`th.group${column.first ? ".first" : ""}`, { "data-group": column.group }, column.group));
    }
    head.append(groupRow);
    const headRow = h("tr", {}, h("th.tools", {}, ""));
    for (const column of view.columns) {
        const sorted = view.sort?.key === column.key ? (view.sort.dir === "asc" ? "▲" : "▼") : "";
        const filtered = view.filters[column.key];
        const th = h(
            `th${column.kind === "num" ? ".num" : ""}${column.first ? ".first" : ""}${filtered ? ".filtered" : ""}${sorted ? ".sorted" : ""}`,
            { title: `${column.note ? `${column.note}. ` : ""}${column.metric || column.label}: click to sort or filter` },
            h("span.label", {}, column.label),
            column.unit ? h("span.unit", {}, column.unit) : null,
            h("span.marks", {}, `${filtered ? "⏷" : ""}${sorted}`),
        );
        th.addEventListener("click", () => headerMenu(th, column));
        headRow.append(th);
    }
    head.append(headRow);
    const body = h("tbody");
    for (const row of view.rows) {
        const pin = h("button.pin", { title: view.pins.has(row.id) ? "Unpin" : "Pin (its point stays marked)", html: view.pins.has(row.id) ? "●" : "○" });
        pin.addEventListener("click", (event) => {
            event.stopPropagation();
            togglePin(row.id);
        });
        const open = h("a.detail", { href: `detail.html?block=${encodeURIComponent(view.block.block)}&id=${encodeURIComponent(row.id)}`, target: "_blank", title: "Open the instance: schematic, layout, 3D, detail plots, waveforms" }, "Open");
        const tr = h(`tr${view.pins.has(row.id) ? ".pinned" : ""}${row.error ? ".failed" : ""}`, { "data-id": row.id }, h("td.tools", {}, pin, open));
        if (row.error) tr.title = `failed: ${row.error}`;
        for (const column of view.columns) {
            const value = column.get(row);
            const td = h(`td${column.kind === "num" ? ".num" : ""}${column.first ? ".first" : ""}`, {}, cellText(column, value));
            if (column.key === "pdk") td.prepend(h("span.swatch", { style: { background: pdkColor(row.pdk) } }));
            if (column.key === "topology") td.prepend(h("span.symbol", {}, symbolGlyph(row.topology)));
            tr.append(td);
        }
        tr.addEventListener("mouseenter", () => setHover(row.id, "table"));
        tr.addEventListener("mouseleave", () => setHover(null, "table"));
        body.append(tr);
    }
    table.replaceChildren(head, body);
    document.getElementById("count").textContent = `${view.rows.length} of ${view.block.rows.length}${Object.keys(view.filters).length ? " (filtered)" : ""}`;
    const clear = document.getElementById("clear-filters");
    clear.disabled = !Object.keys(view.filters).length && !view.sort;
}

function rowElement(id) {
    return document.querySelector(`#instances tr[data-id="${CSS.escape(id)}"]`);
}

// ---- scatter ----------------------------------------------------------------------------------

function pdkColor(pdk) {
    const index = PDK_ORDER.indexOf(pdk);
    return tone(COLORS[(index < 0 ? PDK_ORDER.length : index) % COLORS.length], currentTheme());
}

function topologies() {
    return [...new Set(view.block.rows.map((row) => row.topology))];
}

function symbolOf(topology) {
    return SYMBOLS[topologies().indexOf(topology) % SYMBOLS.length];
}

function symbolGlyph(topology) {
    return { circle: "●", square: "■", diamond: "◆", "triangle-up": "▲", "triangle-down": "▼", cross: "✚", x: "✖", star: "★", hexagon: "⬢", pentagon: "⬟", hourglass: "⧗", bowtie: "⋈" }[symbolOf(topology)];
}

function axisColumns() {
    return view.columns.filter((column) => column.kind === "num" && view.block.rows.some((row) => Number.isFinite(column.get(row))));
}

function positive(column) {
    return view.block.rows.every((row) => {
        const value = column.get(row);
        return !Number.isFinite(value) || value > 0;
    });
}

function wideRange(column) {
    const values = view.block.rows.map(column.get).filter((value) => Number.isFinite(value) && value > 0);
    return values.length > 1 && Math.max(...values) / Math.min(...values) > 100;
}

function point(row, column) {
    const value = column.get(row);
    return Number.isFinite(value) ? value / 10 ** (column.exponent || 0) : null;
}

function axisLabel(column) {
    return column.unit ? `${column.label} (${column.unit})` : column.label;
}

function renderPlotControls() {
    const columns = axisColumns();
    const host = document.getElementById("plot-controls");
    const options = columns.map((column) => ({ value: column.key, label: column.unit ? `${column.label} (${column.unit})` : column.label }));
    const logButton = (axis) => {
        const on = axis === "x" ? view.logX : view.logY;
        const button = toolButton("log", positive(columnOf(axis === "x" ? view.x : view.y)) ? `Log ${axis} axis` : `Log ${axis} axis: the column is not positive`, () => {
            if (axis === "x") view.logX = !view.logX;
            else view.logY = !view.logY;
            save();
            renderPlotControls();
            renderPlot();
        }, on);
        button.disabled = !positive(columnOf(axis === "x" ? view.x : view.y));
        return button;
    };
    const drag = (mode, name, title) =>
        toolButton(name, title, () => {
            view.dragmode = mode;
            Plotly.relayout("scatter", { dragmode: mode });
            renderPlotControls();
        }, view.dragmode === mode);
    const choose = (axis) =>
        select(options, axis === "x" ? view.x : view.y, (value) => {
            const column = columnOf(value);
            if (axis === "x") {
                view.x = value;
                view.logX = positive(column) && wideRange(column);
            } else {
                view.y = value;
                view.logY = positive(column) && wideRange(column);
            }
            save();
            renderPlotControls();
            renderPlot();
        });
    const unpin = toolButton("unpin", "", () => {
        view.pins.clear();
        save();
        refresh();
    });
    unpin.id = "unpin";
    host.replaceChildren(
        h("label.field", {}, h("span", {}, "x"), choose("x")),
        logButton("x"),
        toolButton("swap", "Swap the axes", () => {
            [view.x, view.y, view.logX, view.logY] = [view.y, view.x, view.logY, view.logX];
            save();
            renderPlotControls();
            renderPlot();
        }),
        h("label.field", {}, h("span", {}, "y"), choose("y")),
        logButton("y"),
        h("span.grow"),
        // the plot's own tools, always shown (Plotly's mode bar only on hover, over the plot)
        drag("zoom", "zoom", "Drag: zoom to a box (wheel: zoom)"),
        drag("pan", "pan", "Drag: pan"),
        toolButton("fit", "Fit both axes to the points (double-click)", () => Plotly.relayout("scatter", { "xaxis.autorange": true, "yaxis.autorange": true })),
        toolButton("download", "Save as PNG, with its legend", () => savePng()),
        unpin,
    );
    updateUnpin();
}

// an icon button, as every toolbar's; ``on`` marks a toggle that is set
function toolButton(name, title, onclick, on = false) {
    const button = h("button.icon-btn", { title, onclick, html: icon(name, 14) });
    if (on) button.classList.add("on");
    return button;
}

function updateUnpin() {
    const button = document.getElementById("unpin");
    if (!button) return;
    button.disabled = !view.pins.size;
    button.title = view.pins.size ? `Unpin the ${view.pins.size} pinned instance${view.pins.size > 1 ? "s" : ""}` : "Unpin: no instance is pinned";
}

// the plot as PNG: the legend the page draws beside it is Plotly's here
async function savePng() {
    const element = document.getElementById("scatter");
    const layout = { ...element.layout, showlegend: true, margin: { ...element.layout.margin, r: 150 } };
    const url = await Plotly.toImage({ data: element.data, layout }, { format: "png", width: element.clientWidth + 140, height: element.clientHeight, scale: 2 });
    h("a", { href: url, download: `${view.block.block}_${view.y}_vs_${view.x}.png`.replace(/[:/]/g, "_") }).click();
}

// under the plot: each PDK's colour, each topology's marker
function renderLegend(pdks) {
    const group = (title, items) => h("span.legend-group", {}, h("span.legend-title", {}, title), ...items);
    document.getElementById("plot-legend").replaceChildren(
        group("pdk", pdks.map((pdk) => h("span.legend-item", {}, h("span.swatch", { style: { background: pdkColor(pdk) } }), pdk))),
        group("topology", topologies().map((topology) => h("span.legend-item", {}, h("span.symbol", {}, symbolGlyph(topology)), topology))),
    );
}

function renderPlot() {
    const element = document.getElementById("scatter");
    const x = columnOf(view.x);
    const y = columnOf(view.y);
    if (!x || !y) {
        Plotly.purge(element);
        return;
    }
    const theme = currentTheme();
    const colors = PAPERS[theme];
    const pdks = PDK_ORDER.filter((pdk) => view.rows.some((row) => row.pdk === pdk));
    const traces = pdks.map((pdk) => {
        const rows = view.rows.filter((row) => row.pdk === pdk);
        return {
            type: "scatter",
            mode: "markers",
            name: pdk,
            showlegend: false,
            x: rows.map((row) => point(row, x)),
            y: rows.map((row) => point(row, y)),
            customdata: rows.map((row) => row.id),
            text: rows.map((row) => `${row.pdk} · ${row.topology} · ${row.sizing}`),
            hovertemplate: `%{text}<br>${x.label}: %{x:.4g} ${x.unit || ""}<br>${y.label}: %{y:.4g} ${y.unit || ""}<extra></extra>`,
            marker: { color: pdkColor(pdk), symbol: rows.map((row) => symbolOf(row.topology)), size: 9, line: { width: 0.6, color: colors.paper }, opacity: 0.9 },
        };
    });
    // the legend alone, for the saved PNG (the page draws its own under the plot)
    for (const pdk of pdks) {
        traces.push({ type: "scatter", mode: "markers", name: pdk, legendgroup: "pdk", legendgrouptitle: { text: "PDK" }, x: [null], y: [null], hoverinfo: "skip", marker: { color: pdkColor(pdk), symbol: "circle", size: 9 } });
    }
    for (const topology of topologies()) {
        traces.push({
            type: "scatter",
            mode: "markers",
            name: topology,
            legendgroup: "topology",
            legendgrouptitle: { text: "Topology" },
            x: [null],
            y: [null],
            hoverinfo: "skip",
            marker: { color: colors.spine, symbol: symbolOf(topology), size: 9 },
        });
    }
    const pinned = view.rows.filter((row) => view.pins.has(row.id));
    traces.push({
        type: "scatter",
        mode: "markers+text",
        name: "pinned",
        showlegend: false,
        x: pinned.map((row) => point(row, x)),
        y: pinned.map((row) => point(row, y)),
        customdata: pinned.map((row) => row.id),
        text: pinned.map((row) => `${row.topology} ${row.sizing}`),
        textposition: "top center",
        textfont: { size: 11, color: colors.ink },
        hoverinfo: "skip",
        marker: { symbol: "circle-open", size: 18, line: { width: 2, color: colors.ink }, color: colors.ink },
    });
    // the hovered row's point
    const ring = getComputedStyle(document.documentElement).getPropertyValue("--sem-warn").trim();
    traces.push({ type: "scatter", mode: "markers", name: "hover", showlegend: false, x: [], y: [], hoverinfo: "skip", marker: { symbol: "circle-open", size: 24, line: { width: 3, color: ring } } });
    const layout = paperLayout("", axisLabel(x), axisLabel(y), view.logX, view.logY, 1, theme);
    // the axes' titles and ticks take what they need (automargin); no legend or mode bar beside
    layout.margin = { l: 12, r: 16, t: 14, b: 12 };
    layout.showlegend = false;
    layout.legend = { ...layout.legend, x: 1.02, xanchor: "left", y: 1, yanchor: "top", font: { size: 12 }, tracegroupgap: 12 };
    layout.dragmode = view.dragmode;
    layout.uirevision = `${view.x}|${view.y}|${view.logX}|${view.logY}`;
    renderLegend(pdks);
    Plotly.react(element, traces, layout, { displaylogo: false, displayModeBar: false, responsive: true, scrollZoom: true });
    if (!element.dataset.bound) {
        element.dataset.bound = "1";
        // the legend under the plot takes more or fewer lines by block: the plot follows its room
        new ResizeObserver(() => element.data && Plotly.Plots.resize(element)).observe(element);
        element.on("plotly_hover", (event) => {
            const id = event.points?.[0]?.customdata;
            if (id) setHover(id, "plot");
        });
        element.on("plotly_unhover", () => setHover(null, "plot"));
        element.on("plotly_click", (event) => {
            const id = event.points?.[0]?.customdata;
            if (id) togglePin(id);
        });
    }
    updateUnpin();
}

// light up an instance in both views (from the table: its point; from the plot: its row)
function setHover(id, source) {
    for (const element of document.querySelectorAll("#instances tr.hover")) element.classList.remove("hover");
    view.hover = id;
    const element = document.getElementById("scatter");
    const traceIndex = (element.data || []).findIndex((trace) => trace.name === "hover");
    const row = id ? view.rows.find((item) => item.id === id) : null;
    if (row) {
        const tr = rowElement(id);
        tr?.classList.add("hover");
        if (source === "plot" && tr) tr.scrollIntoView({ block: "nearest" });
    }
    if (traceIndex >= 0 && source === "table") {
        const x = columnOf(view.x);
        const y = columnOf(view.y);
        Plotly.restyle(element, { x: [row ? [point(row, x)] : []], y: [row ? [point(row, y)] : []] }, [traceIndex]);
    }
}

function togglePin(id) {
    if (view.pins.has(id)) view.pins.delete(id);
    else view.pins.add(id);
    save();
    const tr = rowElement(id);
    if (tr) {
        tr.classList.toggle("pinned", view.pins.has(id));
        const pin = tr.querySelector(".pin");
        pin.innerHTML = view.pins.has(id) ? "●" : "○";
    }
    renderPlot();
}

function refresh() {
    orderRows();
    save();
    renderTable();
    renderPlot();
}

// ---- blocks -----------------------------------------------------------------------------------

async function loadBlock(name) {
    const table = await fetchJson(`sweep/${name}.json`);
    view.block = table;
    view.columns = buildColumns(table);
    const saved = recall(`sweep.${name}`, {});
    const axes = axisColumns().map((column) => column.key);
    view.sort = saved.sort && columnOf(saved.sort.key) ? saved.sort : null;
    view.filters = Object.fromEntries(Object.entries(saved.filters || {}).filter(([key]) => columnOf(key)));
    view.pins = new Set((saved.pins || []).filter((id) => table.rows.some((row) => row.id === id)));
    // first visit: the first two metrics (energy against delay, where the block has them)
    const preferX = axes.find((key) => /energy|power/.test(key)) || axes[0];
    const preferY = axes.find((key) => /delay|time|noise/.test(key) && key !== preferX) || axes[1] || axes[0];
    view.x = axes.includes(saved.x) ? saved.x : preferX;
    view.y = axes.includes(saved.y) ? saved.y : preferY;
    view.logX = saved.logX ?? (positive(columnOf(view.x)) && wideRange(columnOf(view.x)));
    view.logY = saved.logY ?? (positive(columnOf(view.y)) && wideRange(columnOf(view.y)));
    store("sweep.block", name);
    renderBlocks();
    renderPlotControls();
    refresh();
    const failed = table.rows.filter((row) => row.error).length;
    const title = document.getElementById("block-title");
    title.textContent = table.title;
    title.title = `${table.metrics.length} metrics${failed ? `, ${failed} failed` : ""}, run ${table.run}`;
}

function renderBlocks() {
    const host = document.getElementById("blocks");
    host.replaceChildren();
    for (const [name, entry] of Object.entries(view.catalog)) {
        // the block's folder under flow/ and its instance count, as Zed's git panel lists a file
        const row = h("div.block-row", { title: `${entry.title}: run ${entry.run}` }, h("span.title", {}, name), h("span.count", {}, `${entry.instances}`));
        if (name === view.block?.block) row.classList.add("on");
        row.addEventListener("click", () => loadBlock(name).catch((error) => toast(error.message)));
        host.append(row);
    }
}

// ---- the page ---------------------------------------------------------------------------------

const PANELS = {
    blocks: { title: "Blocks", make: () => h("div.panel", {}, h("div.panel-body", {}, h("div.block-list", { id: "blocks" }))) },
    sweeps: {
        title: "Sweeps",
        make: () => h("div.panel", {}, h("div.panel-toolbar", { id: "table-controls" }), h("div.panel-body", {}, h("table.grid.sweep", { id: "instances" }))),
    },
    metrics: { title: "Metrics", make: () => h("div.panel", {}, h("div.panel-toolbar", { id: "plot-controls" }), h("div", { id: "scatter" }), h("div", { id: "plot-legend" })) },
};

const component = (type) => ({ type: "component", componentType: type, title: PANELS[type].title, isClosable: false, componentState: {} });

const LAYOUT = {
    settings: { showPopoutIcon: false, popoutWholeStack: false, reorderEnabled: true },
    dimensions: { borderWidth: 4, headerHeight: 28, minItemHeight: 90, minItemWidth: 120 },
    header: { popout: false, close: false },
    root: {
        type: "row",
        content: [
            { type: "stack", width: 9, content: [component("blocks")] },
            { type: "stack", width: 52, content: [component("sweeps")] },
            { type: "stack", width: 39, content: [component("metrics")] },
        ],
    },
};

async function main() {
    // the three panels in GoldenLayout's tabs
    const container = document.getElementById("gl-container");
    const layout = new GoldenLayout(container);
    for (const [type, panel] of Object.entries(PANELS)) layout.registerComponentFactoryFunction(type, (glContainer) => glContainer.element.append(panel.make()));
    layout.loadLayout(LAYOUT);
    new ResizeObserver(() => layout.updateRootSize?.() ?? layout.updateSize?.()).observe(container);
    // above the table: the block, how many of its instances are shown, the filters' reset
    const clear = toolButton("unfilter", "Clear every filter and the sort", () => {
        view.filters = {};
        view.sort = null;
        refresh();
    });
    clear.id = "clear-filters";
    document.getElementById("table-controls").replaceChildren(h("strong", { id: "block-title" }, ""), h("span.muted.mono", { id: "count" }, ""), h("span.grow"), clear);
    // the desktop's light or dark setting, followed as it changes
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
        document.documentElement.dataset.theme = event.matches ? "dark" : "light";
        if (view.block) {
            renderTable();
            renderPlot();
        }
    });
    const loading = document.getElementById("loading");
    try {
        view.catalog = await fetchJson("sweep/catalog.json");
    } catch (error) {
        loading.replaceChildren(h("strong", {}, "No sweep tables"), h("span", {}, "Run  uv run python -m flow.sweep table  and reload."), h("span.mono.muted", {}, error.message));
        return;
    }
    const names = Object.keys(view.catalog);
    const last = recall("sweep.block", null);
    await loadBlock(names.includes(last) ? last : names[0]).catch((error) => toast(error.message));
    loading.classList.add("done");
}

main();
