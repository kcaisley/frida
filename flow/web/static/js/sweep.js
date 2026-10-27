// The Sweeps: a block's sweep (python -m flow web.tables) as one table on its side, a row per field
// (the PDK first, then the parameters that differ between the instances, then the metrics) and a
// column per instance, and beside it a scatter plot of any metric against any other, a point
// coloured and shaped by its PDK as the PDK row's dot is. A row's label sorts the columns by it and
// filters them; hovering a column or a point lights up the other; clicking a column's head or a point
// marks the instance. Marking loads nothing: the top bar's View (one marked) and Compare (two or
// more) open the marked instances in place (detail.js), where the table narrows to their columns
// (SelectionPanel). An instance is its PDK and parameters: its id names it only in the URL.

import { h, icon, popover, select } from "./icons.js";
import { currentTheme, keepTicks, PAPERS, paperLayout, TICK_KEYS, tone } from "./paper.js";
import { COLORS, emit, hostBar, on, recall, store } from "./store.js";
import { fieldInfo, scaledUnit, siExponent } from "./units.js";

export const PDK_ORDER = ["tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65"];
// a PDK's marker, in the scatter and beside its name in the table: Plotly's symbol names
const PDK_SYMBOLS = ["circle", "square", "diamond", "triangle-up", "triangle-down", "hexagon"];

const view = {
    table: null, // the block's table
    fields: [], // the table's rows: sections, the PDK, the parameters, the metrics
    cols: [], // the instances shown, in order
    index: new Map(), // id -> its place in cols
    labelWidth: 200,
    colWidth: 78, // an instance's column, in pixels: only the columns in view are drawn
    sort: null, // {key, dir}
    filters: {}, // key -> {values: [...]} or {min, max}
    marks: new Set(),
    hover: null,
    x: null,
    y: null,
    logX: false,
    logY: false,
    dragmode: "zoom", // the scatter's drag: box zoom or pan
};

let tablePanel = null;
let scatterPanel = null;

// ---- the PDKs' colours and markers ------------------------------------------------------------

export function pdkColor(pdk, theme = currentTheme()) {
    const index = PDK_ORDER.indexOf(pdk);
    return tone(COLORS[(index < 0 ? PDK_ORDER.length : index) % COLORS.length], theme);
}

export function pdkSymbol(pdk) {
    const index = PDK_ORDER.indexOf(pdk);
    return index < 0 ? "star" : PDK_SYMBOLS[index];
}

// Plotly's marker shapes, as small SVGs for the table and the legends
const SHAPES = {
    circle: '<circle cx="5" cy="5" r="4.2"/>',
    square: '<rect x="1.1" y="1.1" width="7.8" height="7.8"/>',
    diamond: '<path d="M5 .3L9.7 5 5 9.7.3 5z"/>',
    "triangle-up": '<path d="M5 .8l4.6 8.2H.4z"/>',
    "triangle-down": '<path d="M.4 1h9.2L5 9.2z"/>',
    hexagon: '<path d="M5 .4l4 2.3v4.6l-4 2.3-4-2.3V2.7z"/>',
    star: '<path d="M5 .3l1.2 3.3h3.5L6.9 5.8l1 3.4L5 7.2 2.1 9.2l1-3.4L.3 3.6h3.5z"/>',
};

export function symbolSvg(symbol, color, size = 10) {
    return `<svg class="pdk-mark" width="${size}" height="${size}" viewBox="0 0 10 10" aria-hidden="true" fill="${color}">${SHAPES[symbol] || SHAPES.circle}</svg>`;
}

export function pdkMark(pdk, size = 10) {
    return symbolSvg(pdkSymbol(pdk), pdkColor(pdk), size);
}

const escapes = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
const esc = (text) => String(text).replace(/[&<>"]/g, (char) => escapes[char]);

// ---- fields ----------------------------------------------------------------------------------

function buildFields(table) {
    const rows = table.rows;
    const numeric = (get) =>
        rows.every((row) => {
            const value = get(row);
            return value === null || value === undefined || typeof value === "number";
        });
    // an instance is its PDK and the parameters its sweep sets: the PDK a parameter, the first
    const fields = [{ section: "Parameters" }, { key: "pdk", label: "pdk", kind: "cat", get: (row) => row.pdk, pdk: true, note: "The PDK" }];
    for (const name of table.params) {
        const get = (row) => row.params?.[name];
        fields.push({ key: `p:${name}`, label: name, kind: numeric(get) ? "num" : "cat", get, decimals: decimalsOf(rows, get) });
    }
    fields.push({ section: "Metrics" });
    // a row's SI prefix by the instances in the running, where some are dimmed; by its smallest tenth
    // where every one is (an optimization that met no bound, its costs over many decades: the
    // cheapest, sorted first, read in full)
    const running = rows.filter((row) => !row.dim);
    const smallest = (values) => {
        const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value)).sort((a, b) => Math.abs(a) - Math.abs(b));
        return finite.length ? [finite[Math.floor(finite.length / 10)]] : [];
    };
    for (const name of table.metrics) {
        const get = (row) => row.metrics?.[name];
        const info = fieldInfo(name);
        const exponent = !info.scalable ? 0 : running.length ? siExponent(running.map(get)) : siExponent(smallest(rows.map(get)));
        fields.push({ key: `m:${name}`, label: info.label, unit: scaledUnit(info, exponent), kind: "num", get, info, exponent, metric: name, decimals: decimalsOf(rows, get) });
    }
    return fields;
}

function fieldOf(key) {
    return view.fields.find((field) => field.key === key) || null;
}

// a number at its row's scale and decimals: three (to 0.001 of the row's unit), none in a row of
// whole numbers, so a row's values line up
function cellText(field, value) {
    if (value === null || value === undefined || (typeof value === "number" && !Number.isFinite(value))) return "—";
    if (field.kind !== "num" || typeof value !== "number") return String(value);
    const text = (value / 10 ** (field.exponent || 0)).toFixed(field.decimals);
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

function monoContext() {
    const context = document.createElement("canvas").getContext("2d");
    const mono = getComputedStyle(document.documentElement).getPropertyValue("--font-mono") || "monospace";
    context.font = `11px ${mono}`;
    return context;
}

// an instance's column as wide as the widest value it may show (a long category's name), within
// bounds: a number takes at most eight characters
function colWidth(fields, rows) {
    const context = monoContext();
    let widest = context.measureText("-000.000").width;
    for (const field of fields) {
        if (field.section || field.kind !== "cat") continue;
        const values = new Set(rows.map((row) => cellText(field, field.get(row))));
        for (const value of values) widest = Math.max(widest, context.measureText(value).width + (field.pdk ? 14 : 0));
    }
    return Math.round(Math.min(108, Math.max(70, widest + 18)));
}

// the label column as wide as its longest label and unit
function labelWidth(fields) {
    const context = monoContext();
    let widest = 0;
    for (const field of fields) {
        if (field.section) continue;
        widest = Math.max(widest, context.measureText(field.label).width + (field.unit ? context.measureText(field.unit).width + 10 : 0));
    }
    // the padding, the gaps between name, unit and marks, the marks
    return Math.round(Math.min(340, Math.max(150, widest + 60)));
}

// ---- filtering and sorting --------------------------------------------------------------------

function passes(row) {
    for (const [key, filter] of Object.entries(view.filters)) {
        const field = fieldOf(key);
        if (!field) continue;
        const value = field.get(row);
        if (filter.values && !filter.values.includes(value === undefined ? null : value)) return false;
        if (filter.min !== undefined && filter.min !== null && !(value >= filter.min)) return false;
        if (filter.max !== undefined && filter.max !== null && !(value <= filter.max)) return false;
    }
    return true;
}

const missing = (value) => value === null || value === undefined || (typeof value === "number" && !Number.isFinite(value));

function orderCols() {
    const cols = view.table.rows.filter(passes);
    if (view.sort) {
        const field = fieldOf(view.sort.key);
        const sign = view.sort.dir === "asc" ? 1 : -1;
        cols.sort((a, b) => {
            // a dimmed instance (an optimization's design that missed a bound) after every other
            if (Boolean(a.dim) !== Boolean(b.dim)) return a.dim ? 1 : -1;
            const va = field.get(a);
            const vb = field.get(b);
            if (missing(va) || missing(vb)) return missing(va) - missing(vb);
            return (typeof va === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true })) * sign;
        });
    }
    view.cols = cols;
    view.index = new Map(cols.map((row, index) => [row.id, index]));
}

function save() {
    if (!view.table) return;
    store(`sweep.${view.table.block}`, {
        sort: view.sort,
        filters: view.filters,
        marks: [...view.marks],
        x: view.x,
        y: view.y,
        logX: view.logX,
        logY: view.logY,
    });
}

// a row label's popover: sort the columns by the row either way; tick the values to keep
// (categories) or bound the range
function rowMenu(anchor, field) {
    popover(anchor, (element) => {
        element.classList.add("filter-pop");
        const sortBy = (dir) => {
            view.sort = { key: field.key, dir };
            element.remove();
            refresh();
        };
        const sortRow = h("div.filter-sort", {}, h("button.icon-btn", { onclick: () => sortBy("asc") }, "Sort ascending"), h("button.icon-btn", { onclick: () => sortBy("desc") }, "Sort descending"));
        element.append(h("div.filter-title", {}, field.label, field.unit ? ` (${field.unit})` : ""), sortRow);
        const current = view.filters[field.key];
        if (field.kind === "cat") {
            const counts = new Map();
            for (const row of view.table.rows) {
                const value = field.get(row) ?? null;
                counts.set(value, (counts.get(value) || 0) + 1);
            }
            const values = [...counts.keys()].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
            const kept = new Set(current?.values ?? values);
            const list = h("div.filter-values");
            const apply = () => {
                if (kept.size === values.length) delete view.filters[field.key];
                else view.filters[field.key] = { values: [...kept] };
                refresh();
            };
            for (const value of values) {
                const box = h("input", { type: "checkbox" });
                box.checked = kept.has(value);
                box.addEventListener("change", () => {
                    if (box.checked) kept.add(value);
                    else kept.delete(value);
                    apply();
                });
                const only = h(
                    "button.link",
                    {
                        title: "Only this value",
                        onclick: (event) => {
                            event.preventDefault();
                            kept.clear();
                            kept.add(value);
                            for (const input of list.querySelectorAll("input")) input.checked = input === box;
                            apply();
                        },
                    },
                    "only",
                );
                const name = value === null ? "—" : String(value);
                list.append(h("label.filter-value", {}, box, h("span", field.pdk ? { html: `${pdkMark(value)} ${esc(name)}` } : {}, field.pdk ? null : name), h("span.muted", {}, `${counts.get(value)}`), only));
            }
            const all = () => {
                for (const input of list.querySelectorAll("input")) input.checked = true;
                kept.clear();
                values.forEach((value) => kept.add(value));
                apply();
            };
            element.append(list, h("div.filter-sort", {}, h("button.icon-btn", { onclick: all }, "All")));
        } else {
            const scale = 10 ** (field.exponent || 0);
            const bound = (name) => {
                const input = h("input.num", { type: "number", step: "any", placeholder: name, value: current?.[name] !== undefined && current?.[name] !== null ? +(current[name] / scale).toPrecision(6) : "" });
                input.addEventListener("change", () => {
                    const filter = view.filters[field.key] || {};
                    filter[name] = input.value === "" ? null : Number(input.value) * scale;
                    if (filter.min === null && filter.max === null) delete view.filters[field.key];
                    else view.filters[field.key] = filter;
                    refresh();
                });
                return input;
            };
            element.append(h("div.filter-range", {}, bound("min"), h("span", {}, "to"), bound("max"), h("span.muted", {}, field.unit || "")));
        }
        if (current) {
            const clear = () => {
                delete view.filters[field.key];
                element.remove();
                refresh();
            };
            element.append(h("div.filter-sort", {}, h("button.icon-btn", { onclick: clear }, "Clear filter")));
        }
    });
}

// ---- the table: a row per field, a column per instance ----------------------------------------

// the Search: the block's sweep and each of its optimizations (app.js), none where it has its sweep alone
const searches = { options: [], value: "", onChange: null };

export function setSearches(options, value, onChange) {
    Object.assign(searches, { options, value, onChange });
    tablePanel?.renderSearches();
}

export class SweepTablePanel {
    constructor(container) {
        this.scroller = h("div.sweep-scroll");
        this.table = h("table.tgrid.full");
        this.emptyNote = h("div.empty", { style: { display: "none" } }, h("strong", {}, "No instances"), h("span", {}, "None passes the filters: clear them in the bar above."));
        this.scroller.append(this.table);
        this.toolbar = h("div.panel-toolbar");
        this.barSlot = h("div.bar-slot");
        this.element = h("div.panel", {}, this.toolbar, h("div.panel-body.fill", {}, this.scroller, this.emptyNote));
        container.element.append(this.element);
        this.renderSearches();
        this.range = null;
        this.dirty = true;
        this.scroller.addEventListener("scroll", () => this.update(false), { passive: true });
        this.resizeObserver = new ResizeObserver(() => this.update(false));
        this.resizeObserver.observe(this.scroller);
        this.table.addEventListener("mouseover", (event) => {
            const index = this.columnAt(event.target);
            setHover(index === null ? null : view.cols[index]?.id ?? null, "table");
        });
        this.table.addEventListener("mouseleave", () => setHover(null, "table"));
        this.table.addEventListener("click", (event) => this.click(event));
        this.off = on("theme", () => this.update(true));
        this.offBar = hostBar(this.barSlot, ["table"]);
        tablePanel = this;
        container.on("destroy", () => {
            this.resizeObserver.disconnect();
            this.off();
            this.offBar();
            if (tablePanel === this) tablePanel = null;
        });
        this.update(true);
    }

    // the Search, as the layout's Generator above its panel
    renderSearches() {
        // then the page's bar: the instances shown, filters and marks, View, Compare and Compiler
        this.toolbar.replaceChildren(...(searches.options.length ? [h("label.field", {}, h("span", {}, "Search"), select(searches.options, searches.value, (value) => searches.onChange?.(value)))] : []), this.barSlot);
    }

    // the instance a cell is in: a head carries its index, a value cell its place in the row
    columnAt(target) {
        const cell = target.closest?.("td, th");
        if (!cell || !this.table.contains(cell) || !this.range) return null;
        if (cell.dataset.i !== undefined) return Number(cell.dataset.i);
        if (cell.parentElement.classList.contains("section")) return null;
        const index = this.range[0] + cell.cellIndex - 2;
        return cell.cellIndex >= 2 && index < this.range[1] ? index : null;
    }

    click(event) {
        const cell = event.target.closest?.("th");
        if (!cell) return;
        if (cell.dataset.i !== undefined) {
            const row = view.cols[Number(cell.dataset.i)];
            if (row) toggleMark(row.id);
        } else if (cell.dataset.key) {
            const field = fieldOf(cell.dataset.key);
            if (field) rowMenu(cell, field);
        }
    }

    // the columns in view and as many again either side; redrawn once the view leaves them
    update(force) {
        if (!view.table) return;
        if (force) this.dirty = true;
        const width = this.scroller.clientWidth;
        if (!width) return;
        const count = view.cols.length;
        this.emptyNote.style.display = count ? "none" : "";
        const left = this.scroller.scrollLeft;
        const from = Math.max(0, Math.floor(left / view.colWidth));
        const to = Math.min(count, Math.ceil((left + width - view.labelWidth) / view.colWidth) + 1);
        if (!this.dirty && this.range && from >= this.range[0] && to <= this.range[1]) return;
        const span = Math.max(8, to - from);
        this.range = [Math.max(0, from - span), Math.min(count, to + span)];
        this.dirty = false;
        this.render();
    }

    render() {
        const [first, last] = this.range;
        const cols = view.cols.slice(first, last);
        const count = view.cols.length;
        const theme = currentTheme();
        const marks = cols.map((row) => [view.marks.has(row.id) ? "marked" : "", view.hover === row.id ? "hover" : ""].filter(Boolean).join(" "));
        const parts = [`<colgroup><col style="width:${view.labelWidth}px"><col style="width:${first * view.colWidth}px">`];
        for (const mark of marks) parts.push(`<col class="${mark}" style="width:${view.colWidth}px">`);
        parts.push(`<col style="width:${(count - last) * view.colWidth}px"></colgroup>`);
        // the heads: a column's mark (and its failure)
        parts.push(`<thead><tr><th class="corner"><span class="muted">${count} instance${count === 1 ? "" : "s"}</span></th><th class="pad"></th>`);
        cols.forEach((row, k) => {
            const failed = row.error ? (row.error.trim().split("\n").pop() || "failed") : "";
            const title = `${view.marks.has(row.id) ? "Unmark" : "Mark"} this instance: View or Compare the marked ones from the bar above${failed ? `\nFailed: ${failed}` : ""}`;
            parts.push(`<th class="inst ${marks[k]}${failed ? " failed" : ""}" data-i="${first + k}" title="${esc(title)}"><span class="mark"></span>${failed ? '<span class="fail">!</span>' : ""}</th>`);
        });
        parts.push('<th class="pad"></th></tr></thead><tbody>');
        for (const field of view.fields) {
            if (field.section) {
                parts.push(`<tr class="section"><th class="label">${esc(field.section)}</th><td colspan="${cols.length + 2}"></td></tr>`);
                continue;
            }
            const sorted = view.sort?.key === field.key ? (view.sort.dir === "asc" ? "▲" : "▼") : "";
            const filtered = view.filters[field.key] ? icon("filter", 9) : "";
            const title = `${field.note ? `${field.note}. ` : ""}${field.metric || field.label}: click to sort or filter the instances by it`;
            parts.push(
                `<tr><th class="label${sorted ? " sorted" : ""}${filtered ? " filtered" : ""}" data-key="${esc(field.key)}" title="${esc(title)}"><div class="lab"><span class="name">${esc(field.label)}</span><span class="unit">${esc(field.unit || "")}</span><span class="mk">${filtered}${sorted}</span></div></th><td class="pad"></td>`,
            );
            if (field.pdk) {
                for (const row of cols) parts.push(`<td class="pdk">${symbolSvg(pdkSymbol(row.pdk), pdkColor(row.pdk, theme), 9)}${esc(row.pdk ?? "—")}</td>`);
            } else {
                // a category's name longer than its column whole in its title
                const fits = Math.floor((view.colWidth - 14) / 6.7);
                for (const row of cols) {
                    const text = esc(cellText(field, field.get(row)));
                    const title = field.kind === "cat" && text.length > fits ? ` title="${text}"` : "";
                    const kind = row.error ? "failed" : row.dim ? "dim" : "";
                    parts.push(`<td${kind ? ` class="${kind}"` : ""}${title}>${text}</td>`);
                }
            }
            parts.push('<td class="pad"></td></tr>');
        }
        parts.push("</tbody>");
        this.table.style.width = `${view.labelWidth + count * view.colWidth}px`;
        this.table.innerHTML = parts.join("");
        this.colElements = this.table.querySelector("colgroup").children;
        this.headElements = this.table.querySelector("thead tr").children;
    }

    // an instance's column, where it is drawn: its column (the cells show through) and its head
    setClass(id, name, value) {
        const index = view.index.get(id);
        if (index === undefined || !this.range || index < this.range[0] || index >= this.range[1]) return;
        this.colElements?.[2 + index - this.range[0]]?.classList.toggle(name, value);
        this.headElements?.[2 + index - this.range[0]]?.classList.toggle(name, value);
    }

    // scrolled to an instance's column (from its point)
    reveal(id) {
        const index = view.index.get(id);
        if (index === undefined || !this.scroller.clientWidth) return;
        const left = index * view.colWidth;
        const room = this.scroller.clientWidth - view.labelWidth;
        const scroll = this.scroller.scrollLeft;
        if (left < scroll) this.scroller.scrollLeft = left;
        else if (left + view.colWidth > scroll + room) this.scroller.scrollLeft = left + view.colWidth - room;
        this.update(false);
    }
}

// ---- the scatter ------------------------------------------------------------------------------

function axisFields() {
    return view.fields.filter((field) => field.kind === "num" && view.table.rows.some((row) => Number.isFinite(field.get(row))));
}

function positive(field) {
    return Boolean(field) && view.table.rows.every((row) => {
        const value = field.get(row);
        return !Number.isFinite(value) || value > 0;
    });
}

function wideRange(field) {
    const values = view.table.rows.map(field.get).filter((value) => Number.isFinite(value) && value > 0);
    return values.length > 1 && Math.max(...values) / Math.min(...values) > 100;
}

function point(row, field) {
    const value = field.get(row);
    return Number.isFinite(value) ? value / 10 ** (field.exponent || 0) : null;
}

function axisLabel(field) {
    return field.unit ? `${field.label} (${field.unit})` : field.label;
}

// an icon button, as every toolbar's; ``on`` marks a toggle that is set
export function toolButton(name, title, onclick, on = false) {
    const button = h("button.icon-btn", { title, onclick, html: icon(name, 14) });
    if (on) button.classList.add("on");
    return button;
}

export class ScatterPanel {
    constructor(container) {
        this.controls = h("div.panel-toolbar");
        this.plot = h("div.scatter");
        this.legend = h("div.plot-legend");
        this.element = h("div.panel", {}, this.controls, this.plot, this.legend);
        container.element.append(this.element);
        this.dirty = true;
        // the legend under the plot takes more or fewer lines by block: the plot follows its room
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(this.plot);
        this.off = on("theme", () => this.render());
        scatterPanel = this;
        container.on("destroy", () => {
            this.resizeObserver.disconnect();
            this.off();
            Plotly.purge(this.plot);
            if (scatterPanel === this) scatterPanel = null;
        });
        if (view.table) {
            this.renderControls();
            this.render();
        }
    }

    shown() {
        return this.plot.offsetParent !== null && this.plot.clientWidth > 0;
    }

    // a frame at most per resize: a divider's drag stays smooth
    resize() {
        if (this.resizeFrame) return;
        this.resizeFrame = requestAnimationFrame(() => {
            this.resizeFrame = null;
            if (!this.shown()) return;
            if (this.dirty) this.render();
            else if (this.plot.data) Plotly.Plots.resize(this.plot);
        });
    }

    renderControls() {
        const fields = axisFields();
        const options = fields.map((field) => ({ value: field.key, label: axisLabel(field) }));
        const rerender = () => {
            save();
            this.renderControls();
            this.render();
        };
        const logButton = (axis) => {
            const field = fieldOf(axis === "x" ? view.x : view.y);
            const button = toolButton("log", positive(field) ? `Log ${axis} axis` : `Log ${axis} axis: the values are not all positive`, () => {
                if (axis === "x") view.logX = !view.logX;
                else view.logY = !view.logY;
                rerender();
            }, axis === "x" ? view.logX : view.logY);
            button.disabled = !positive(field);
            return button;
        };
        const drag = (mode, name, title) =>
            toolButton(name, title, () => {
                view.dragmode = mode;
                if (this.plot.data) Plotly.relayout(this.plot, { dragmode: mode });
                this.renderControls();
            }, view.dragmode === mode);
        const choose = (axis) =>
            select(options, axis === "x" ? view.x : view.y, (value) => {
                const field = fieldOf(value);
                if (axis === "x") {
                    view.x = value;
                    view.logX = positive(field) && wideRange(field);
                } else {
                    view.y = value;
                    view.logY = positive(field) && wideRange(field);
                }
                rerender();
            });
        this.controls.replaceChildren(
            h("label.field", {}, h("span", {}, "x"), choose("x")),
            logButton("x"),
            toolButton("swap", "Swap the axes", () => {
                [view.x, view.y, view.logX, view.logY] = [view.y, view.x, view.logY, view.logX];
                rerender();
            }),
            h("label.field", {}, h("span", {}, "y"), choose("y")),
            logButton("y"),
            h("span.grow"),
            // the plot's own tools, always shown (Plotly's mode bar only on hover, over the plot)
            drag("zoom", "zoom", "Drag: zoom to a box (wheel: zoom)"),
            drag("pan", "pan", "Drag: pan"),
            toolButton("fit", "Fit both axes to the points (double-click)", () => this.fit()),
            toolButton("download", "Save as PNG, with its legend", () => this.savePng()),
        );
    }

    // every point in view, the dimmed ones too
    fit() {
        if (!this.plot.data) return;
        this.focus = false;
        this.render();
        Plotly.relayout(this.plot, { "xaxis.autorange": true, "yaxis.autorange": true });
    }

    // where a table dims some instances, the metric axes' ranges over the others (log ones in decades),
    // padded: the plot opens on the instances in the running, Fit shows them all; a parameter's axis
    // (a search's trial) keeps every instance
    focusRanges(x, y) {
        const ranges = {};
        for (const [key, field, log] of [
            ["x", x, view.logX],
            ["y", y, view.logY],
        ]) {
            if (!field.metric) continue;
            const values = view.cols
                .filter((row) => !row.dim)
                .map((row) => point(row, field))
                .filter((value) => Number.isFinite(value) && (!log || value > 0))
                .map((value) => (log ? Math.log10(value) : value));
            if (!values.length) continue;
            const low = Math.min(...values);
            const high = Math.max(...values);
            const pad = (high - low) * 0.06 || (log ? 0.1 : Math.abs(high) * 0.05 || 1);
            ranges[key] = [low - pad, high + pad];
        }
        return ranges;
    }

    // the plot as PNG: the legend the page draws under it is Plotly's here
    async savePng() {
        const element = this.plot;
        if (!element.data) return;
        const layout = { ...element.layout, showlegend: true, margin: { ...element.layout.margin, r: 150 } };
        const url = await Plotly.toImage({ data: element.data, layout }, { format: "png", width: element.clientWidth + 140, height: element.clientHeight, scale: 2 });
        h("a", { href: url, download: `${view.table.block}_${view.y}_vs_${view.x}.png`.replace(/[:/]/g, "_") }).click();
    }

    render() {
        const element = this.plot;
        const x = fieldOf(view.x);
        const y = fieldOf(view.y);
        if (!view.table || !x || !y) {
            Plotly.purge(element);
            this.legend.replaceChildren();
            return;
        }
        // drawn once shown: a hidden plot has no size to draw at
        if (!this.shown()) {
            this.dirty = true;
            return;
        }
        this.dirty = false;
        const theme = currentTheme();
        const colors = PAPERS[theme];
        const known = [...new Set(view.cols.map((row) => row.pdk))];
        const pdks = [...PDK_ORDER.filter((pdk) => known.includes(pdk)), ...known.filter((pdk) => !PDK_ORDER.includes(pdk))];
        const traces = pdks.map((pdk) => {
            const rows = view.cols.filter((row) => row.pdk === pdk && !row.dim);
            return {
                type: "scatter",
                mode: "markers",
                name: pdk,
                showlegend: false,
                x: rows.map((row) => point(row, x)),
                y: rows.map((row) => point(row, y)),
                customdata: rows.map((row) => row.id),
                hovertemplate: `${pdk}<br>${x.label}: %{x:.4g} ${x.unit || ""}<br>${y.label}: %{y:.4g} ${y.unit || ""}<extra></extra>`,
                marker: { color: pdkColor(pdk, theme), symbol: pdkSymbol(pdk), size: 9, line: { width: 0.6, color: colors.paper }, opacity: 0.9 },
            };
        });
        // the dimmed instances (an optimization's designs that missed a bound) in grey, under the rest
        const dimmed = view.cols.filter((row) => row.dim);
        if (dimmed.length) {
            traces.unshift({
                type: "scatter",
                mode: "markers",
                name: "dimmed",
                showlegend: false,
                x: dimmed.map((row) => point(row, x)),
                y: dimmed.map((row) => point(row, y)),
                customdata: dimmed.map((row) => row.id),
                text: dimmed.map((row) => `${row.pdk} · ${typeof row.dim === "string" ? row.dim : "dimmed"}`),
                hovertemplate: `%{text}<br>${x.label}: %{x:.4g} ${x.unit || ""}<br>${y.label}: %{y:.4g} ${y.unit || ""}<extra></extra>`,
                marker: { color: colors.spine, size: 6, opacity: 0.3, line: { width: 0 } },
            });
        }
        // the legend alone, for the saved PNG (the page draws its own under the plot)
        for (const pdk of pdks) {
            traces.push({ type: "scatter", mode: "markers", name: pdk, legendgroup: "pdk", legendgrouptitle: { text: "PDK" }, x: [null], y: [null], hoverinfo: "skip", marker: { color: pdkColor(pdk, theme), symbol: pdkSymbol(pdk), size: 9 } });
        }
        const marked = view.cols.filter((row) => view.marks.has(row.id));
        traces.push({
            type: "scatter",
            mode: "markers",
            name: "marked",
            showlegend: false,
            x: marked.map((row) => point(row, x)),
            y: marked.map((row) => point(row, y)),
            customdata: marked.map((row) => row.id),
            hoverinfo: "skip",
            marker: { symbol: "circle-open", size: 18, line: { width: 2, color: colors.ink }, color: colors.ink },
        });
        // the hovered column's point
        const ring = getComputedStyle(document.documentElement).getPropertyValue("--sem-warn").trim();
        const hovered = view.hover ? view.cols.find((row) => row.id === view.hover) : null;
        traces.push({
            type: "scatter",
            mode: "markers",
            name: "hover",
            showlegend: false,
            x: hovered ? [point(hovered, x)] : [],
            y: hovered ? [point(hovered, y)] : [],
            hoverinfo: "skip",
            marker: { symbol: "circle-open", size: 24, line: { width: 3, color: ring } },
        });
        // the instances with an x and no y (a search's designs rejected before they had a cost) as
        // ticks in a strip over the plot, where the y axis is one the table names (its cost: another
        // metric a design lacks was only not measured): one lane by the rug's label, or a lane each by
        // its field
        const rug = view.table.rug && (!view.table.rug.on || view.table.rug.on.includes(view.y)) ? view.table.rug : null;
        const rugField = rug?.key ? fieldOf(rug.key) : null;
        const rugRows = rug ? view.cols.filter((row) => point(row, x) !== null && point(row, y) === null) : [];
        const laneOf = (row) => (rugField ? String(rugField.get(row) ?? "—") : rug.label || "no value");
        const present = new Set(rugRows.map(laneOf));
        const lanes = [...(view.table.rug?.lanes || []).filter((lane) => present.has(lane)), ...[...present].filter((lane) => !(view.table.rug?.lanes || []).includes(lane))];
        if (rugRows.length) {
            traces.push({
                type: "scatter",
                mode: "markers",
                name: "rug",
                showlegend: false,
                yaxis: "y2",
                x: rugRows.map((row) => point(row, x)),
                y: rugRows.map(laneOf),
                customdata: rugRows.map((row) => row.id),
                text: rugRows.map((row) => `${row.pdk} · ${typeof row.dim === "string" ? row.dim : laneOf(row)}`),
                hovertemplate: `%{text}<br>${x.label}: %{x:.4g} ${x.unit || ""}<br>no ${y.label.toLowerCase()}: %{y}<extra></extra>`,
                // an open symbol is drawn in the marker's colour
                marker: { symbol: "line-ns-open", size: 11, color: colors.spine, line: { width: 1.2 }, opacity: 0.4 },
            });
        }
        // a new table or new axes open focused on the undimmed instances, until Fit or a double-click
        const revision = `${view.table.block}|${view.x}|${view.y}|${view.logX}|${view.logY}`;
        if (this.revision !== revision) [this.revision, this.focus] = [revision, true];
        const focused = this.focus && dimmed.length && dimmed.length < view.cols.length;
        // the ticks of every point (Fit restores them), a focused axis's of the undimmed ones alone
        const layout = paperLayout("", axisLabel(x), axisLabel(y), view.logX, view.logY, 1, theme, { traces: traces.slice(0, pdks.length + (dimmed.length ? 1 : 0)) });
        if (focused) {
            const narrow = paperLayout("", axisLabel(x), axisLabel(y), view.logX, view.logY, 1, theme, { traces: traces.slice(1, pdks.length + 1) });
            for (const [key, range] of Object.entries(this.focusRanges(x, y))) {
                const axis = layout[`${key}axis`];
                for (const attribute of TICK_KEYS) axis[attribute] = narrow[`${key}axis`][attribute];
                axis.range = range;
            }
        }
        if (rugRows.length) {
            const strip = Math.min(0.3, 0.035 * lanes.length + 0.02);
            layout.yaxis.domain = [0, 1 - strip];
            layout.yaxis2 = {
                domain: [1 - strip + 0.012, 1],
                anchor: "x",
                type: "category",
                categoryorder: "array",
                categoryarray: [...lanes].reverse(),
                range: [-0.6, lanes.length - 0.4],
                fixedrange: true,
                automargin: true,
                showgrid: false,
                zeroline: false,
                showline: false,
                ticks: "",
                tickfont: { size: 10, color: colors.spine },
            };
        }
        // the table's bands on an axis it plots (a study's warm start over its trials), shaded behind
        const top = layout.yaxis.domain?.[1] ?? 1;
        for (const band of view.table.bands || []) {
            const on = band.key === view.x ? "x" : band.key === view.y ? "y" : null;
            if (!on) continue;
            const field = fieldOf(band.key);
            const log = on === "x" ? view.logX : view.logY;
            const [from, to] = [band.from, band.to].map((value) => value / 10 ** (field?.exponent || 0)).map((value) => (log ? Math.log10(Math.max(value, 1e-300)) : value));
            const across = on === "x" ? { xref: "x", yref: "paper", x0: from, x1: to, y0: 0, y1: 1 } : { xref: "paper", yref: "y", x0: 0, x1: 1, y0: from, y1: to };
            layout.shapes = [...(layout.shapes || []), { type: "rect", ...across, fillcolor: colors.major, opacity: 0.5, line: { width: 0 }, layer: "below" }];
            const label = on === "x" ? { xref: "x", yref: "paper", x: (from + to) / 2, y: top, yanchor: "top" } : { xref: "paper", yref: "y", x: 0, y: (from + to) / 2, xanchor: "left" };
            layout.annotations = [...(layout.annotations || []), { ...label, text: band.label, showarrow: false, font: { size: 11, color: colors.spine } }];
        }
        // the axes' titles and ticks take what they need (automargin); no legend or mode bar beside
        layout.margin = { l: 12, r: 16, t: 14, b: 12 };
        layout.showlegend = false;
        layout.legend = { ...layout.legend, orientation: "v", x: 1.02, xanchor: "left", yref: "paper", y: 1, yanchor: "top", font: { size: 12 }, tracegroupgap: 12 };
        layout.dragmode = view.dragmode;
        layout.uirevision = revision;
        this.renderLegend(pdks, dimmed.length ? view.table.dimmed || "dimmed" : null);
        Plotly.react(element, traces, layout, { displaylogo: false, displayModeBar: false, scrollZoom: true });
        keepTicks(element);
        if (!element.dataset.bound) {
            element.dataset.bound = "1";
            element.on("plotly_hover", (event) => {
                const id = event.points?.[0]?.customdata;
                if (id) setHover(id, "plot");
            });
            element.on("plotly_unhover", () => setHover(null, "plot"));
            element.on("plotly_doubleclick", () => {
                this.focus = false;
            });
            element.on("plotly_click", (event) => {
                const id = event.points?.[0]?.customdata;
                if (id) toggleMark(id);
            });
        }
    }

    // under the plot: each PDK's colour and marker, and the grey of the dimmed instances (named by the table)
    renderLegend(pdks, dimmed) {
        this.legend.replaceChildren(
            h("span.legend-group", {}, h("span.legend-title", {}, "pdk"), ...pdks.map((pdk) => h("span.legend-item", { html: `${pdkMark(pdk, 10)}${esc(pdk)}` }))),
            ...(dimmed ? [h("span.legend-group", {}, h("span.legend-item.muted", { html: `${symbolSvg("circle", PAPERS[currentTheme()].spine, 8)}${esc(dimmed)}` }))] : []),
        );
    }

    // the hovered column's point ringed
    ring(id) {
        const element = this.plot;
        const index = (element.data || []).findIndex((trace) => trace.name === "hover");
        if (index < 0) return;
        const row = id ? view.cols.find((item) => item.id === id) : null;
        const x = fieldOf(view.x);
        const y = fieldOf(view.y);
        Plotly.restyle(element, { x: [row ? [point(row, x)] : []], y: [row ? [point(row, y)] : []] }, [index]);
    }
}

// ---- linking ----------------------------------------------------------------------------------

// light up an instance in both views (from the table: its point; from the plot: its column)
function setHover(id, source) {
    if (view.hover === id) return;
    const previous = view.hover;
    view.hover = id;
    if (previous) tablePanel?.setClass(previous, "hover", false);
    if (id) {
        if (source === "plot") tablePanel?.reveal(id);
        tablePanel?.setClass(id, "hover", true);
    }
    if (source === "table") scatterPanel?.ring(id);
}

function toggleMark(id) {
    if (view.marks.has(id)) view.marks.delete(id);
    else view.marks.add(id);
    marksChanged([id]);
}

function marksChanged(ids) {
    save();
    for (const id of ids) tablePanel?.setClass(id, "marked", view.marks.has(id));
    scatterPanel?.render();
    emit("marks", [...view.marks]);
}

export function marks() {
    // in the table's order, as View and Compare open them
    return view.table ? view.table.rows.filter((row) => view.marks.has(row.id)).map((row) => row.id) : [];
}

// the instances shown in place (View, Compare) are the marked ones
export function setMarks(ids) {
    const before = [...view.marks];
    view.marks = new Set(ids.filter((id) => view.table?.rows.some((row) => row.id === id)));
    marksChanged([...before, ...view.marks]);
}

export function sweepStatus() {
    return {
        shown: view.cols.length,
        total: view.table?.rows.length || 0,
        filtered: Object.keys(view.filters).length > 0,
        sorted: Boolean(view.sort),
    };
}

export function clearFilters() {
    view.filters = {};
    view.sort = null;
    refresh();
}

function refresh() {
    orderCols();
    save();
    tablePanel?.update(true);
    scatterPanel?.render();
    emit("sweep");
}

// a block's table, shown with its sort, filters, marks and axes as last left
export function setBlock(table) {
    view.table = table;
    view.fields = buildFields(table);
    view.labelWidth = labelWidth(view.fields);
    view.colWidth = colWidth(view.fields, table.rows);
    view.hover = null;
    const saved = recall(`sweep.${table.block}`, {});
    const axes = axisFields().map((field) => field.key);
    const ids = new Set(table.rows.map((row) => row.id));
    // first visit: the table's own sort and axes where it gives them (a study's: by cost, cost
    // against trial), else unsorted, energy against delay where the block has them
    const sort = "sort" in saved ? saved.sort : table.sort;
    view.sort = sort && fieldOf(sort.key) ? sort : null;
    view.filters = Object.fromEntries(Object.entries(saved.filters || {}).filter(([key]) => fieldOf(key)));
    view.marks = new Set((saved.marks || saved.pins || []).filter((id) => ids.has(id)));
    const preferX = axes.find((key) => key === table.axes?.x) || axes.find((key) => /energy|power/.test(key)) || axes[0];
    const preferY = axes.find((key) => key === table.axes?.y) || axes.find((key) => /delay|time|noise/.test(key) && key !== preferX) || axes[1] || axes[0];
    view.x = axes.includes(saved.x) ? saved.x : preferX;
    view.y = axes.includes(saved.y) ? saved.y : preferY;
    view.logX = saved.logX ?? (positive(fieldOf(view.x)) && wideRange(fieldOf(view.x)));
    view.logY = saved.logY ?? (positive(fieldOf(view.y)) && wideRange(fieldOf(view.y)));
    if (tablePanel) tablePanel.scroller.scrollLeft = 0;
    scatterPanel?.renderControls();
    refresh();
    emit("marks", [...view.marks]);
}

// ---- the narrowed table: the instances shown in place, a column each ------------------------------

const differs = (values) => new Set(values.map((value) => JSON.stringify(value ?? null))).size > 1;

// the parameters any of the instances has, in the order their sweep sets them
function paramNames(instances) {
    return [...new Set(instances.flatMap((instance) => Object.keys(instance.params || {})))];
}

const shown = (value) => (value === null || value === undefined ? "—" : String(value));

// a number at its row's SI prefix to 0.001 of it, whole numbers as they are
function formatted(value, exponent) {
    if (typeof value !== "number" || !Number.isFinite(value)) return shown(value);
    return Number.isInteger(value) ? String(value) : (value / 10 ** exponent).toFixed(3).replace(/^-(0\.0*)$/, "$1");
}

// each compared instance's name: its PDK and the parameters that tell it from the others
export function describe(instances) {
    const keys = ["pdk", ...paramNames(instances)];
    const valueOf = (instance, key) => (key === "pdk" ? instance.pdk : instance.params?.[key]);
    const telling = keys.filter((key) => differs(instances.map((instance) => valueOf(instance, key))));
    // short: the fewest of them that tell every instance apart, each taken where it splits the most
    const groups = (keys) => new Set(instances.map((instance) => JSON.stringify(keys.map((key) => valueOf(instance, key) ?? null)))).size;
    const chosen = [];
    while (groups(chosen) < instances.length) {
        let best = null;
        for (const key of telling) {
            if (chosen.includes(key)) continue;
            const count = groups([...chosen, key]);
            if (!best || count > best.count) best = { key, count };
        }
        if (!best || best.count === groups(chosen)) break;
        chosen.push(best.key);
    }
    const short = telling.filter((key) => chosen.includes(key));
    const name = (instance, key) => (key === "pdk" ? shown(instance.pdk) : `${key}=${shown(valueOf(instance, key))}`);
    return instances.map((instance, index) => {
        const full = telling.map((key) => name(instance, key)).join(", ") || `instance ${index + 1}`;
        return { short: short.map((key) => name(instance, key)).join(", ") || full, full };
    });
}

// what the old instance page's summary showed, its column on the left: every parameter (the PDK
// first), every metric at its row's SI prefix, the layout's size and signoff; compared, a column
// each under its colour, the parameters those that differ unless asked for all
export class SelectionPanel {
    constructor(container, { instances, colorOf, onRemove, onView }) {
        this.instances = instances;
        this.colorOf = colorOf;
        this.onRemove = onRemove;
        this.onView = onView;
        this.compare = instances.length > 1;
        this.onlyDifferences = recall("compare.differences", true);
        this.toolbar = h("div.panel-toolbar");
        this.barSlot = h("div.bar-slot");
        this.toolbar.append(this.barSlot);
        this.body = h("div.panel-body.selection");
        this.element = h("div.panel", {}, this.toolbar, this.body);
        container.element.append(this.element);
        this.off = [on("theme", () => this.render()), hostBar(this.barSlot, ["view", "compare"])];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        const instances = this.instances;
        const theme = currentTheme();
        const cell = (tag, text, attributes = {}) => h(tag, attributes, text);
        const row = (label, values, { unit = "", mono = false, differ = false, title } = {}) =>
            h(
                `tr${differ ? ".differs" : ""}`,
                {},
                h("th.label", { title: title || label }, h("div.lab", {}, h(`span.name${mono ? ".mono" : ""}`, {}, label), h("span.unit", {}, unit))),
                values,
            );
        const section = (title) => h("tr.section", {}, h("th.label", {}, title), h("td", { colspan: String(instances.length) }));
        // the heads: the colour (compared), this one alone, and out of the selection
        const heads = instances.map((instance, index) =>
            h(
                "th.inst.sel",
                {},
                h(
                    "div.inst-head",
                    {},
                    this.compare ? h("span.swatch", { style: { background: this.colorOf(index) } }) : null,
                    h("span.grow"),
                    this.compare ? h("button.icon-btn.mini", { title: "View this instance alone: its analyses, waveforms, layout and schematic", onclick: () => this.onView(instance.id), html: icon("eye", 13) }) : null,
                    h("button.icon-btn.mini", { title: this.compare ? "Remove from the comparison" : "Close: back to every instance", onclick: () => this.onRemove(instance.id), html: icon("x", 13) }),
                ),
            ),
        );
        const head = h("tr", {}, h("th.corner", {}, h("span.muted", {}, this.compare ? `${instances.length} compared` : "")), heads);
        const pdkRow = row("pdk", instances.map((instance) => h("td.pdk", { html: `${symbolSvg(pdkSymbol(instance.pdk), pdkColor(instance.pdk, theme), 9)}${esc(shown(instance.pdk))}` })), { mono: true, differ: this.compare && differs(instances.map((instance) => instance.pdk)) });
        const paramRows = paramNames(instances)
            .map((name) => [name, instances.map((instance) => instance.params?.[name])])
            .filter(([, values]) => !this.compare || !this.onlyDifferences || differs(values))
            .map(([name, values]) => row(name, values.map((value) => cell("td", shown(value))), { mono: true, differ: this.compare && differs(values) }));
        const metricNames = [...new Set(instances.flatMap((instance) => Object.keys(instance.metrics || {})))];
        const metricRows = metricNames.map((name) => {
            const info = fieldInfo(name);
            const values = instances.map((instance) => instance.metrics?.[name]);
            const finite = values.filter((value) => typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value));
            const exponent = info.scalable && finite.length ? siExponent(finite) : 0;
            return row(info.label, values.map((value, index) => cell(`td${instances[index].error && missing(value) ? ".failed" : ""}`, formatted(value, exponent))), { unit: scaledUnit(info, exponent), differ: this.compare && differs(values), title: name });
        });
        const layoutRows = this.layoutRows(row);
        const failed = instances.some((instance) => instance.error);
        const errorRow = failed
            ? row("Error", instances.map((instance) => h(`td.text${instance.error ? ".failed" : ""}`, { title: instance.error || "" }, instance.error ? instance.error.trim().split("\n").pop() || "failed" : "—")))
            : null;
        const table = h(
            "table.tgrid.narrow",
            {},
            h("thead", {}, head),
            h("tbody", {}, errorRow, section("Parameters"), pdkRow, paramRows, section("Metrics"), metricRows, section("Layout"), layoutRows),
        );
        // alone, a failure's whole message under its column
        const error = !this.compare && instances[0].error ? h("pre.error", {}, instances[0].error) : null;
        this.body.replaceChildren(table, error || "");
        if (this.compare) {
            const toggle = h("label.check", { title: "Hide the parameters every compared instance shares" }, h("input", { type: "checkbox", checked: this.onlyDifferences }), "Only the parameters that differ");
            toggle.querySelector("input").addEventListener("change", (event) => {
                this.onlyDifferences = event.target.checked;
                store("compare.differences", this.onlyDifferences);
                this.render();
            });
            this.toolbar.replaceChildren(this.barSlot, toggle);
        }
    }

    // the ALIGN layout's size and signoff, a row each
    layoutRows(row) {
        const instances = this.instances;
        const value = (instance, key) => {
            const layout = instance.layout;
            if (!layout) return key === "placed" ? "none" : "—";
            if (layout.error) return key === "placed" ? "ALIGN failed" : "—";
            if (key === "w") return Number.isFinite(layout.w_um) ? layout.w_um.toFixed(3) : "—";
            if (key === "h") return Number.isFinite(layout.h_um) ? layout.h_um.toFixed(3) : "—";
            // the blocks' own layouts side by side (a behavioral ADC): nothing routed or signed off
            if (layout.blocks) return key === "placed" ? "blocks, unconnected" : "none";
            if (key === "placed") return layout.floorplan ? "by floorplan" : "ALIGN alone";
            if (key === "drc") return layout.drc_violations === null || layout.drc_violations === undefined ? "—" : layout.drc_violations ? `${layout.drc_violations} violations` : "clean";
            if (key === "lvs") return layout.lvs_correct === null || layout.lvs_correct === undefined ? "—" : layout.lvs_correct ? "correct" : "incorrect";
            return "—";
        };
        const bad = (text) => /violations|incorrect|failed/.test(text);
        return [
            ["Placed", "placed", ""],
            ["Width", "w", "µm"],
            ["Height", "h", "µm"],
            ["DRC", "drc", ""],
            ["LVS", "lvs", ""],
        ].map(([label, key, unit]) => {
            const values = instances.map((instance) => value(instance, key));
            return row(label, values.map((text) => h(`td${bad(text) ? ".failed" : ""}`, {}, text)), { unit, differ: this.compare && differs(values) });
        });
    }
}
