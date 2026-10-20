// The focused series' transistor schematic (pan, zoom), or the netlist its layout was built
// from; on an instance page, the instance's.

import { h, icon, seg, select } from "./icons.js";
import { fetchData, focusSeries, on, series, setFocus, state, status } from "./store.js";

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
