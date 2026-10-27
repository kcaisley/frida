// The focused series' transistor schematic (pan, zoom) and, in a panel of its own, the netlist its
// layout was built from; on an instance page, the instance's.

import { loadEditor } from "./editor.js";
import { h, icon, select } from "./icons.js";
import { fetchData, focusSeries, on, series, setFocus, state, status } from "./store.js";

// The schematic's own stylesheet (netlist2image: black on white) scoped to the sheet: inline, its
// "svg" and "text" rules would restyle every icon on the page; the theme recolours the sheet.
function scopedSvg(text) {
    return text.replace(/<style([^>]*)>([\s\S]*?)<\/style>/, (whole, attributes, css) => {
        const scoped = css.replace(/(^|\})\s*([^@{}][^{}]*)\{/g, (rule, close, selectors) =>
            `${close}\n${selectors.split(",").map((selector) => `.sheet .page ${selector.trim()}`).join(", ")} {`,
        );
        return `<style${attributes}>${scoped}</style>`;
    });
}

// view: "schematic" or "netlist"
export class SchematicPanel {
    constructor(container, view = "schematic") {
        this.viewName = view;
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.sheet = h("div.sheet");
        this.page = h("div.page");
        this.listing = h("pre.netlist", { style: { display: "none" } });
        // the netlist as the Compiler's editor highlights it, read-only (the listing where it cannot load)
        this.editorHost = h("div.editor-host", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("schematic", 28) }), h("strong", {}, view === "netlist" ? "No netlist" : "No schematic"), h("span", {}, ""));
        this.sheet.append(this.page);
        // the schematic's fit floats over its sheet: no toolbar row for one button
        this.fitButton = h("button.icon-btn.float", { title: "Fit (double-click)", onclick: () => this.fit(), html: icon("fit", 14) });
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.sheet, this.listing, this.editorHost, this.emptyNote, this.fitButton));
        container.element.append(this.element);
        this.view = { k: 1, x: 0, y: 0 };
        this.bindInput();
        this.off = [on("block", () => this.refresh()), on("selection", () => this.refresh()), on("focus", () => this.refresh())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        // an editor made while its tab was hidden measures itself once shown
        container.on("show", () => this.editor?.refresh());
        this.resizeObserver = new ResizeObserver(() => this.svgSize && !this.moved && this.fit());
        this.resizeObserver.observe(this.sheet);
        this.refresh();
    }

    // the focused series' schematic, or its netlist
    async refresh() {
        const shown = series();
        const schematicOf = (item) => (state.block?.schematics || []).find((entry) => entry.case === item.case && entry.pdk === item.pdk);
        // the focused series, or where it has none the first shown series with a netlist
        const focused = focusSeries();
        const focus = focused && !schematicOf(focused) ? shown.find(schematicOf) || focused : focused;
        const entry = focus && schematicOf(focus);
        const view = this.viewName;
        this.toolbar.replaceChildren();
        if (shown.length > 1) {
            this.toolbar.append(h("label.field", {}, h("span", {}, "Series"), select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))));
        }
        // a toolbar only to choose among several series
        this.toolbar.style.display = this.toolbar.childElementCount ? "" : "none";
        const path = entry && (view === "netlist" ? entry.netlist : entry.path);
        this.fitButton.style.display = view === "schematic" && path ? "" : "none";
        if (!path) {
            this.page.replaceChildren();
            this.listing.style.display = "none";
            this.editorHost.style.display = "none";
            this.sheet.style.display = "none";
            this.key = null;
            this.emptyNote.style.display = "";
            this.emptyNote.lastChild.textContent = !state.block
                ? "Select a block."
                : entry
                  ? entry.note || "A standard-cell netlist: no transistor schematic. See the Netlist panel."
                  : "No netlist was cached for the focused series' layout.";
            return;
        }
        this.emptyNote.style.display = "none";
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
                try {
                    await loadEditor();
                } catch {
                    return;
                }
                if (this.key !== key) return;
                this.editor ||= CodeMirror(this.editorHost, { mode: "spice", readOnly: true, lineNumbers: true, lineWrapping: false });
                this.editor.setValue(text);
                this.listing.style.display = "none";
                this.editorHost.style.display = "";
                this.editor.refresh();
                return;
            }
            this.page.innerHTML = scopedSvg(text);
            const svg = this.page.querySelector("svg");
            this.svgSize = [Number(svg.getAttribute("width")) || svg.viewBox.baseVal.width, Number(svg.getAttribute("height")) || svg.viewBox.baseVal.height];
            this.moved = false;
            this.fit();
        } catch (error) {
            status(`${view === "netlist" ? "Netlist" : "Schematic"}: ${error.message}`, true);
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
