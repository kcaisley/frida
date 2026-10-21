// The design-space explorer: a block's sweep (python -m flow.sweep table) as one table, a row per
// instance (its PDK, topology and sizing, the parameters that differ, then the metrics), and a
// scatter plot of any metric against any other, coloured by PDK and marked by topology. A column
// header sorts and filters; hovering a row or a point lights up the other; clicking a point (or a
// row's pin) pins it, across axis changes; a row's detail button opens the instance's own page.

import { h, icon, popover, select } from "./icons.js";
import { currentTheme, PAPERS, paperLayout, tone } from "./paper.js";
import { COLORS, recall, store } from "./store.js";
import { fieldInfo, formatValue, scaledUnit, siExponent } from "./units.js";

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
};

function status(message, error = false) {
    const element = document.querySelector("#status-bar .msg");
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("err", error);
}

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
    const columns = [
        { key: "pdk", label: "PDK", kind: "cat", get: (row) => row.pdk },
        { key: "topology", label: "Topology", kind: "cat", get: (row) => row.topology },
        { key: "sizing", label: "Sizing", kind: "cat", get: (row) => row.sizing },
    ];
    for (const name of table.params) {
        const get = (row) => row.params[name];
        columns.push({ key: `p:${name}`, label: name, kind: numeric(get) ? "num" : "cat", get, param: true, info: { label: name, unit: "", scalable: false }, decimals: decimalsOf(rows, get) });
    }
    for (const name of table.metrics) {
        const get = (row) => row.metrics[name];
        const info = fieldInfo(name);
        const exponent = siExponent(rows.map(get));
        columns.push({ key: `m:${name}`, label: info.label, unit: scaledUnit(info, info.scalable ? exponent : 0), kind: "num", get, info, exponent: info.scalable ? exponent : 0, metric: name, decimals: decimalsOf(rows, get) });
    }
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
    const headRow = h("tr", {}, h("th.tools", {}, ""));
    for (const column of view.columns) {
        const sorted = view.sort?.key === column.key ? (view.sort.dir === "asc" ? "▲" : "▼") : "";
        const filtered = view.filters[column.key];
        const th = h(
            `th${column.kind === "num" ? ".num" : ""}${column.param ? ".param" : ""}${filtered ? ".filtered" : ""}${sorted ? ".sorted" : ""}`,
            { title: `${column.metric || column.label}: click to sort or filter` },
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
            const td = h(`td${column.kind === "num" ? ".num" : ""}`, {}, cellText(column, value));
            if (column.key === "pdk") td.prepend(h("span.swatch", { style: { background: pdkColor(row.pdk) } }));
            if (column.key === "topology") td.prepend(h("span.symbol", {}, symbolGlyph(row.topology)));
            tr.append(td);
        }
        tr.addEventListener("mouseenter", () => setHover(row.id, "table"));
        tr.addEventListener("mouseleave", () => setHover(null, "table"));
        body.append(tr);
    }
    table.replaceChildren(head, body);
    document.getElementById("count").textContent = `${view.rows.length} of ${view.block.rows.length} instances${Object.keys(view.filters).length ? " (filtered)" : ""}`;
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
    const logBox = (axis) => {
        const box = h("input", { type: "checkbox", title: `Log ${axis}` });
        box.checked = axis === "x" ? view.logX : view.logY;
        box.disabled = !positive(columnOf(axis === "x" ? view.x : view.y));
        box.addEventListener("change", () => {
            if (axis === "x") view.logX = box.checked;
            else view.logY = box.checked;
            save();
            renderPlot();
        });
        return h("label.check", {}, box, "log");
    };
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
    host.replaceChildren(
        h("label.field", {}, h("span", {}, "x"), choose("x"), logBox("x")),
        h("label.field", {}, h("span", {}, "y"), choose("y"), logBox("y")),
        h("button.icon-btn", { title: "Swap the axes", onclick: () => { [view.x, view.y, view.logX, view.logY] = [view.y, view.x, view.logY, view.logX]; save(); renderPlotControls(); renderPlot(); } }, "⇄"),
        h("span.grow"),
        h("span.muted", { id: "pin-count" }, ""),
        h("button.icon-btn", { title: "Unpin every instance", onclick: () => { view.pins.clear(); save(); refresh(); } }, "Clear pins"),
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
    // the legend alone: each PDK's colour, each topology's marker
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
    traces.push({ type: "scatter", mode: "markers", name: "hover", showlegend: false, x: [], y: [], hoverinfo: "skip", marker: { symbol: "circle-open", size: 24, line: { width: 3, color: "#EBCB8B" } } });
    const layout = paperLayout("", axisLabel(x), axisLabel(y), view.logX, view.logY, 1, theme);
    // the mode bar sits in the top margin, above the legend beside the plot
    layout.margin = { l: 70, r: 10, t: 40, b: 52 };
    layout.legend = {
        ...layout.legend,
        x: 1.02,
        xanchor: "left",
        y: 1,
        yanchor: "top",
        font: { size: 12 },
        tracegroupgap: 12,
        itemclick: false,
        itemdoubleclick: false,
    };
    layout.uirevision = `${view.x}|${view.y}|${view.logX}|${view.logY}`;
    Plotly.react(element, traces, layout, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] });
    if (!element.dataset.bound) {
        element.dataset.bound = "1";
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
    document.getElementById("pin-count").textContent = view.pins.size ? `${view.pins.size} pinned` : "";
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
    if (row) status(`${row.pdk} · ${row.topology} · ${row.sizing}${row.seconds ? ` · characterized in ${row.seconds} s` : ""}`);
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
    status(`Loading ${name}…`);
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
    status(`${table.title}: ${table.rows.length} instances (${failed} failed), ${table.metrics.length} metrics, run ${table.run}`);
}

function renderBlocks() {
    const host = document.getElementById("blocks");
    host.replaceChildren();
    for (const [name, entry] of Object.entries(view.catalog)) {
        const row = h("div.block-row", { title: `run ${entry.run}` }, h("span.title", {}, entry.title), h("span.counts", {}, h("span.badge", {}, `${entry.instances}`)));
        if (name === view.block?.block) row.classList.add("on");
        row.addEventListener("click", () => loadBlock(name).catch((error) => status(error.message, true)));
        host.append(row);
    }
}

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    store("theme", theme);
    buildToolbar();
    if (view.block) {
        renderTable();
        renderPlot();
    }
}

function buildToolbar() {
    const theme = document.documentElement.dataset.theme;
    const bar = document.getElementById("toolbar");
    bar.replaceChildren(
        h("span.brand", {}, h("span", { html: icon("chip", 16) }), "FRIDA design space"),
        h("span.spacer"),
        h("span.toolbar-title", { id: "count" }, ""),
        h("button.tool-btn", { title: "Clear every filter and the sort", onclick: () => { view.filters = {}; view.sort = null; refresh(); } }, h("span", { html: icon("reset", 16) }), h("span", {}, "Clear filters")),
        h("div.tool-sep"),
        h("button.tool-btn", { title: "Theme (T)", onclick: () => setTheme(theme === "dark" ? "light" : "dark") }, h("span", { html: icon(theme === "dark" ? "sun" : "moon", 16) })),
    );
}

async function main() {
    buildToolbar();
    document.getElementById("status-bar").replaceChildren(h("span.cell", {}, h("span.dot"), "sweep"), h("span.msg", {}, "Ready"));
    window.addEventListener("keydown", (event) => {
        const target = event.target;
        if (event.ctrlKey || event.metaKey || target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return;
        if (event.key === "t" || event.key === "T") setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
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
    await loadBlock(names.includes(last) ? last : names[0]).catch((error) => status(error.message, true));
    loading.classList.add("done");
}

main();
