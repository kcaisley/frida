// The navigator panels: blocks, the instances (every named case of the block, the parameters
// that define it and what is cached for it), the selection (PDKs, cases, the parameters that tell
// the cases apart, the series they make), the focused series' schematic, and the study's figures.

import { h, icon, seg, select } from "./icons.js";
import { blockPdks, caseNames, fetchData, focusSeries, loadBlock, on, selectionChanged, series, setFocus, state, status, toggle } from "./store.js";

// the parameter names over the cases, in their order, and those whose values differ
function caseParameters(cases) {
    const block = state.block;
    const names = [...new Set(cases.flatMap((name) => Object.keys(block.cases[name].params || {})))];
    const varying = names.filter((param) => new Set(cases.map((name) => paramText(block.cases[name].params?.[param]))).size > 1);
    return { names, varying };
}

const PDK_SHORT = { tsmc65: "65", tsmc28: "28", ihp130: "IHP", tower180: "TWR", lf150: "LF", tpsc65: "TPS" };

// one small pill per PDK, lit by ``state(pdk)``: "" off, "on", "on ok" (signoff clean), "on bad"
function pdkPills(pdks, stateOf) {
    return h(
        "span.pills",
        {},
        pdks.map((pdk) => {
            const pill = h("span.pill", { title: pdk }, PDK_SHORT[pdk] || pdk);
            for (const name of stateOf(pdk).split(" ").filter(Boolean)) pill.classList.add(name);
            return pill;
        }),
    );
}

export class InstancesPanel {
    constructor(container, saved) {
        this.config = { all: false, ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.off = [on("block", () => this.render()), on("selection", () => this.render())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        const block = state.block;
        this.toolbar.replaceChildren();
        this.body.replaceChildren();
        if (!block) {
            this.body.append(h("div.empty", {}, h("span", { html: icon("instances", 28) }), h("strong", {}, "No block"), h("span", {}, "Choose a block to list its instances.")));
            return;
        }
        const cases = caseNames();
        const pdks = blockPdks();
        const { names, varying } = caseParameters(cases);
        const shownParams = this.config.all || !varying.length ? names : varying;
        const datasets = Object.values(state.results || {});
        const resultPdks = (name) => pdks.filter((pdk) => datasets.some((byPdk) => byPdk?.[pdk]?.[name]));
        const colors = Object.fromEntries(series().map((item) => [item.case, item.color]));
        // which PDKs every view shows: a chip each (alt-click: only that one)
        const pdkChips = h("span.chips.pdk-toggle", { title: "The PDKs shown in plots, results, traces and layouts (alt-click: only that one)" });
        for (const pdk of pdks) {
            const chip = h("span.chip", {}, pdk);
            if (state.pdks.has(pdk)) chip.classList.add("on");
            chip.addEventListener("click", (event) => {
                if (event.altKey) state.pdks = new Set([pdk]);
                else toggle(state.pdks, pdk);
                selectionChanged();
            });
            pdkChips.append(chip);
        }
        this.toolbar.append(
            h("span.field", {}, h("span", {}, "Show")),
            pdkChips,
            h("span.link", { onclick: () => { state.pdks = new Set(pdks); selectionChanged(); } }, "all"),
            h("span.grow"),
            h("span.muted", {}, `${cases.length} instances`),
            seg(
                [
                    { value: false, label: "Defining parameters", title: "The parameters that differ between the instances" },
                    { value: true, label: "All parameters", title: "Every parameter of every instance" },
                ],
                Boolean(this.config.all),
                (value) => {
                    this.config.all = value;
                    this.render();
                },
            ),
            h("button.icon-btn", { title: "Copy the table (tab-separated)", onclick: () => this.copy(cases, shownParams) }, h("span", { html: icon("download", 14) }), "Copy"),
        );
        const table = h("table.grid.instances");
        const all = h("input", { type: "checkbox", title: "Select every instance" });
        all.checked = cases.every((name) => state.cases.has(name));
        all.addEventListener("change", () => {
            state.cases = new Set(all.checked ? cases : []);
            selectionChanged();
        });
        table.append(
            h(
                "thead",
                {},
                h(
                    "tr",
                    {},
                    h("th.check", {}, all),
                    h("th", {}, "Instance"),
                    h("th", { title: "The PDKs with simulation results" }, "Simulated in"),
                    h("th", { title: "The PDKs with cached layouts: green where every one is DRC clean and LVS correct" }, "Laid out in"),
                    h("th", {}, "Description"),
                    ...shownParams.map((param) => h(varying.includes(param) ? "th.varies" : "th", { title: param }, param)),
                ),
            ),
        );
        const body = h("tbody");
        for (const name of cases) {
            const entry = block.cases[name];
            const selected = state.cases.has(name);
            const box = h("input", { type: "checkbox" });
            box.checked = selected;
            const withResults = resultPdks(name);
            const layouts = block.layouts.filter((item) => item.case === name);
            const clean = layouts.filter((item) => item.drc_violations === 0 && item.lvs_correct === true).length;
            const generators = [...new Set(layouts.map((item) => item.generator))].join(", ");
            const description = entry.comment || entry.description || "";
            const row = h(
                "tr",
                { title: "Click to add or remove; alt-click to show only this one; double-click to focus it" },
                h("td.check", {}, box),
                h("td.name", {}, h("span.series-dot", { style: { background: selected ? colors[name] || "var(--fg-disabled)" : "transparent", display: "inline-block", marginRight: "8px" } }), name),
                h("td.pdks", { title: withResults.length ? `simulated in ${withResults.join(", ")}` : "no simulation results" }, pdkPills(pdks, (pdk) => (withResults.includes(pdk) ? "on" : ""))),
                h(
                    "td.pdks",
                    { title: layouts.length ? `${generators}; ${clean} of ${layouts.length} DRC clean and LVS correct` : "no cached layout" },
                    pdkPills(pdks, (pdk) => {
                        const here = layouts.filter((item) => item.pdk === pdk);
                        if (!here.length) return "";
                        if (here.every((item) => item.drc_violations === 0 && item.lvs_correct === true)) return "on ok";
                        return here.some((item) => item.drc_violations > 0 || item.lvs_correct === false) ? "on bad" : "on";
                    }),
                ),
                h("td.text", { title: description }, description || "—"),
                ...shownParams.map((param) => h(varying.includes(param) ? "td.varies" : "td", {}, paramText(entry.params?.[param]))),
            );
            if (selected) row.classList.add("on");
            row.addEventListener("click", (event) => {
                if (event.altKey) state.cases = new Set([name]);
                else toggle(state.cases, name);
                selectionChanged();
            });
            row.addEventListener("dblclick", () => {
                state.cases.add(name);
                const pdk = [...state.pdks][0] || withResults[0] || layouts[0]?.pdk;
                if (pdk) {
                    state.pdks.add(pdk);
                    setFocus(`${pdk}|${name}`);
                } else selectionChanged();
            });
            body.append(row);
        }
        table.append(body);
        this.body.append(table);
    }

    copy(cases, params) {
        const block = state.block;
        const lines = [["instance", "description", ...params].join("\t")];
        for (const name of cases) {
            const entry = block.cases[name];
            lines.push([name, entry.comment || entry.description || "", ...params.map((param) => paramText(entry.params?.[param]))].join("\t"));
        }
        navigator.clipboard?.writeText(lines.join("\n")).then(() => status("Instances copied"), () => status("The clipboard is not available here", true));
    }
}

export class BlocksPanel {
    constructor(container) {
        this.element = h("div.panel");
        this.search = h("input", { type: "search", placeholder: "Filter blocks  ( / )", spellcheck: "false" });
        this.search.addEventListener("input", () => this.render());
        this.list = h("div.block-list");
        this.element.append(h("div.panel-toolbar", {}, this.search), h("div.panel-body", {}, this.list));
        container.element.append(this.element);
        this.off = [on("catalog", () => this.render()), on("block", () => this.render()), on("command", (command) => command === "search" && this.search.focus())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        const filter = this.search.value.trim().toLowerCase();
        this.list.replaceChildren();
        for (const block of state.catalog?.blocks || []) {
            if (filter && !`${block.name} ${block.title}`.toLowerCase().includes(filter)) continue;
            const row = h(
                "div.block-row",
                { title: block.errors ? `${block.errors} export errors` : "" },
                h("span.title", {}, block.title),
                h("span.key", {}, block.name),
                h(
                    "span.counts",
                    {},
                    h("span.badge", { title: "cases" }, `${block.cases} cases`),
                    h(block.layouts ? "span.badge.ok" : "span.badge", { title: "layouts" }, `${block.layouts} ⬚`),
                    block.errors ? h("span.badge.err", {}, "!") : null,
                ),
            );
            if (state.block?.name === block.name) row.classList.add("on");
            row.addEventListener("click", () => loadBlock(block.name).catch((error) => status(error.message, true)));
            this.list.append(row);
        }
    }
}

function paramText(value) {
    if (value === null || value === undefined) return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

export class SelectionPanel {
    constructor(container) {
        this.element = h("div.panel");
        this.body = h("div.panel-body");
        this.element.append(this.body);
        container.element.append(this.element);
        this.off = [on("block", () => this.render()), on("selection", () => this.render())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        const scroll = this.body.scrollTop;
        this.body.replaceChildren();
        const block = state.block;
        if (!block) {
            this.body.append(h("div.empty", {}, h("span", { html: icon("params", 28) }), h("strong", {}, "No block"), h("span", {}, "Choose a block to set its parameters.")));
            return;
        }
        const pdks = blockPdks();
        const cases = caseNames();

        // PDKs
        const pdkChips = h("div.chips");
        for (const pdk of pdks) {
            const chip = h("span.chip", { title: block.pdks.includes(pdk) ? "" : "layouts only" }, pdk);
            if (state.pdks.has(pdk)) chip.classList.add("on");
            chip.addEventListener("click", (event) => {
                if (event.altKey) state.pdks = new Set([pdk]);
                else toggle(state.pdks, pdk);
                selectionChanged();
            });
            pdkChips.append(chip);
        }
        this.body.append(
            h(
                "div.section",
                {},
                h("div.section-title", {}, "PDK", h("span.links", {}, h("span.link", { onclick: () => { state.pdks = new Set(pdks); selectionChanged(); } }, "all"), h("span.link", { onclick: () => { state.pdks = new Set(pdks.slice(0, 1)); selectionChanged(); } }, "one"))),
                pdkChips,
            ),
        );

        // cases
        const caseChips = h("div.chips");
        for (const name of cases) {
            const entry = block.cases[name];
            const chip = h("span.chip", { title: entry.comment || entry.description || "" }, h("span.mono", {}, name));
            if (state.cases.has(name)) chip.classList.add("on");
            chip.addEventListener("click", (event) => {
                if (event.altKey) state.cases = new Set([name]);
                else toggle(state.cases, name);
                selectionChanged();
            });
            caseChips.append(chip);
        }
        this.body.append(
            h(
                "div.section",
                {},
                h("div.section-title", {}, "Case", h("span.links", {}, h("span.link", { onclick: () => { state.cases = new Set(cases); selectionChanged(); } }, "all"), h("span.link", { onclick: () => { state.cases = new Set(cases.slice(0, 1)); selectionChanged(); } }, "one"))),
                caseChips,
                h("div.note", {}, "Click to add or remove; alt-click to show only that one."),
            ),
        );

        // parameters that tell the cases apart, each value a chip selecting its cases
        const { varying } = caseParameters(cases);
        if (varying.length) {
            const section = h("div.section", {}, h("div.section-title", {}, "Parameters"));
            for (const param of varying) {
                // the values the cases take (a case without the parameter is not one)
                const values = [...new Set(cases.map((name) => paramText(block.cases[name].params?.[param])))].filter((value) => value !== "—");
                const chips = h("div.chips");
                for (const value of values) {
                    const members = cases.filter((name) => paramText(block.cases[name].params?.[param]) === value);
                    const chip = h("span.chip", { title: members.join(", ") }, h("span.mono", {}, value));
                    if (members.every((name) => state.cases.has(name))) chip.classList.add("on");
                    chip.addEventListener("click", (event) => {
                        const on = members.every((name) => state.cases.has(name));
                        if (event.altKey) state.cases = new Set(members);
                        else for (const name of members) on ? state.cases.delete(name) : state.cases.add(name);
                        selectionChanged();
                    });
                    chips.append(chip);
                }
                section.append(h("div.param-row", {}, h("span.mono.muted", { title: param }, param), chips));
            }
            this.body.append(section);
        }

        // series
        const all = series({ includeHidden: true });
        const focus = focusSeries();
        const list = h("div.series-list");
        for (const item of all) {
            const swatch = h("canvas", { width: 44, height: 12, style: { width: "22px", height: "6px" } });
            const ctx = swatch.getContext("2d");
            ctx.strokeStyle = item.color;
            ctx.lineWidth = 4;
            ctx.setLineDash(item.dash === "solid" ? [] : item.dash === "dot" ? [3, 4] : [10, 5]);
            ctx.beginPath();
            ctx.moveTo(0, 6);
            ctx.lineTo(44, 6);
            ctx.stroke();
            const eye = h("button.icon-btn", {
                title: item.hidden ? "Show" : "Hide",
                html: icon(item.hidden ? "eyeOff" : "eye", 14),
                onclick: (event) => {
                    event.stopPropagation();
                    toggle(state.hidden, item.key);
                    selectionChanged();
                },
            });
            const remove = h("button.icon-btn", {
                title: "Remove from the selection",
                html: icon("x", 14),
                onclick: (event) => {
                    event.stopPropagation();
                    const others = all.filter((other) => other.key !== item.key);
                    if (!others.some((other) => other.case === item.case)) state.cases.delete(item.case);
                    else if (!others.some((other) => other.pdk === item.pdk)) state.pdks.delete(item.pdk);
                    else state.hidden.add(item.key);
                    selectionChanged();
                },
            });
            const row = h("div.series-row", { title: "Focus: layouts and the schematic follow it" }, swatch, h("span.label", {}, item.label), eye, remove);
            if (item.hidden) row.classList.add("hidden");
            if (focus?.key === item.key) row.classList.add("focus");
            row.addEventListener("click", () => setFocus(item.key));
            list.append(row);
        }
        this.body.append(h("div.section", {}, h("div.section-title", {}, `Series · ${all.length}`), list));

        this.body.scrollTop = scroll;
    }
}

export class SchematicPanel {
    constructor(container, saved) {
        this.config = { view: "schematic", ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.sheet = h("div.sheet");
        this.page = h("div.page");
        this.listing = h("pre.netlist", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("schematic", 28) }), h("strong", {}, "No schematic"), h("span", {}, ""));
        this.sheet.append(this.page);
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.sheet, this.listing, this.emptyNote));
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.view = { k: 1, x: 0, y: 0 };
        this.bindInput();
        this.off = [on("block", () => this.refresh()), on("selection", () => this.refresh()), on("focus", () => this.refresh())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.resizeObserver = new ResizeObserver(() => this.svgSize && !this.moved && this.fit());
        this.resizeObserver.observe(this.sheet);
        this.refresh();
    }

    // the focused series' schematic, or its netlist where it has no schematic (standard cells)
    async refresh() {
        const shown = series();
        const schematicOf = (item) => (state.block?.schematics || []).find((entry) => entry.case === item.case && entry.pdk === item.pdk);
        // the focused series, or where it has none the first shown series with a netlist
        const focused = focusSeries();
        const focus = focused && !schematicOf(focused) ? shown.find(schematicOf) || focused : focused;
        const entry = focus && schematicOf(focus);
        const view = entry && !entry.path ? "netlist" : this.config.view;
        this.toolbar.replaceChildren();
        if (shown.length) {
            this.toolbar.append(h("label.field", {}, h("span", {}, "Series"), select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))));
        }
        const toggle = seg(
            [
                { value: "schematic", label: "Schematic", title: entry && !entry.path ? entry.note || "A standard-cell netlist: no transistor schematic" : "Transistor schematic" },
                { value: "netlist", label: "Netlist", title: "The netlist the layout was built from" },
            ],
            view,
            (value) => {
                this.config.view = value;
                this.key = null;
                this.refresh();
            },
        );
        this.toolbar.append(h("span.grow"), toggle, h("button.icon-btn", { title: "Fit", onclick: () => this.fit(), html: icon("fit", 14) }));
        if (!entry) {
            this.page.replaceChildren();
            this.listing.style.display = "none";
            this.sheet.style.display = "";
            this.key = null;
            this.emptyNote.style.display = "";
            this.emptyNote.lastChild.textContent = !state.block ? "Select a block." : "No netlist was cached for the focused series' layout.";
            return;
        }
        this.emptyNote.style.display = "none";
        const path = view === "netlist" ? entry.netlist : entry.path;
        const key = `${view}:${path}`;
        if (key === this.key) return;
        this.key = key;
        try {
            const text = await fetchData(path, "text");
            if (this.key !== key) return;
            this.listing.style.display = view === "netlist" ? "" : "none";
            this.sheet.style.display = view === "netlist" ? "none" : "";
            if (view === "netlist") {
                this.listing.textContent = text;
                if (!entry.path) status(`${entry.cell}: a standard-cell netlist, shown as text`);
                return;
            }
            this.page.innerHTML = text;
            const svg = this.page.querySelector("svg");
            this.svgSize = [Number(svg.getAttribute("width")) || svg.viewBox.baseVal.width, Number(svg.getAttribute("height")) || svg.viewBox.baseVal.height];
            this.moved = false;
            this.fit();
        } catch (error) {
            status(`Schematic: ${error.message}`, true);
        }
    }

    fit() {
        if (!this.svgSize) return;
        const width = this.sheet.clientWidth;
        const height = this.sheet.clientHeight;
        const k = 0.92 * Math.min(width / this.svgSize[0], height / this.svgSize[1]);
        this.view = { k, x: (width - k * this.svgSize[0]) / 2, y: (height - k * this.svgSize[1]) / 2 };
        this.moved = false;
        this.apply();
    }

    apply() {
        this.page.style.transform = `translate(${this.view.x}px, ${this.view.y}px) scale(${this.view.k})`;
    }

    bindInput() {
        let drag = null;
        this.sheet.addEventListener("wheel", (event) => {
            event.preventDefault();
            const rect = this.sheet.getBoundingClientRect();
            const px = event.clientX - rect.left;
            const py = event.clientY - rect.top;
            const factor = Math.exp(-event.deltaY * 0.0015);
            const { k, x, y } = this.view;
            this.view = { k: k * factor, x: px - (px - x) * factor, y: py - (py - y) * factor };
            this.moved = true;
            this.apply();
        }, { passive: false });
        this.sheet.addEventListener("mousedown", (event) => {
            drag = { x: event.clientX, y: event.clientY, view: { ...this.view } };
            this.sheet.classList.add("panning");
        });
        window.addEventListener("mousemove", (event) => {
            if (!drag) return;
            this.view = { ...drag.view, x: drag.view.x + event.clientX - drag.x, y: drag.view.y + event.clientY - drag.y };
            this.moved = true;
            this.apply();
        });
        window.addEventListener("mouseup", () => {
            drag = null;
            this.sheet.classList.remove("panning");
        });
        this.sheet.addEventListener("dblclick", () => this.fit());
    }
}

export class FiguresPanel {
    constructor(container, saved) {
        this.config = { pdk: null, ...(saved || {}) };
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.off = [on("block", () => this.render()), on("selection", () => this.render())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    render() {
        const figures = state.block?.figures || [];
        const pdks = [...new Set(figures.map((figure) => figure.pdk))];
        const preferred = [...state.pdks].find((pdk) => pdks.includes(pdk));
        if (!pdks.includes(this.config.pdk) || (preferred && !state.pdks.has(this.config.pdk))) this.config.pdk = preferred || pdks[0] || null;
        this.toolbar.replaceChildren(
            h("span.muted", {}, "The study's own Matplotlib figures, as flow.analysis.runner draws them"),
            h("span.grow"),
        );
        if (pdks.length) {
            this.toolbar.append(h("label.field", {}, h("span", {}, "PDK"), select(pdks.map((pdk) => ({ value: pdk, label: pdk })), this.config.pdk, (value) => {
                this.config.pdk = value;
                this.render();
            })));
        }
        this.body.replaceChildren();
        const shown = figures.filter((figure) => figure.pdk === this.config.pdk);
        if (!shown.length) {
            this.body.append(h("div.empty", {}, h("span", { html: icon("image", 28) }), h("strong", {}, "No figures"), h("span", {}, state.block ? "Export without --no-figures to include them." : "Select a block.")));
            return;
        }
        const grid = h("div.figure-grid");
        for (const figure of shown) {
            const card = h("div.figure-card", { title: "Open" }, h("img", { src: `data/${figure.path}`, alt: figure.name, loading: "lazy" }), h("div.cap", {}, figure.name));
            card.addEventListener("click", () => {
                const full = h("div.figure-full", { title: "Back" }, h("img", { src: `data/${figure.path}`, alt: figure.name }));
                full.addEventListener("click", () => full.remove());
                this.body.append(full);
            });
            grid.append(card);
        }
        this.body.append(grid);
    }
}
