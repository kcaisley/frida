// The focused series' transistor schematic (pan, zoom) and, in a panel of its own, the netlist its
// layout was built from; on an instance page, the instance's. Each under a bar of what it shows: the
// schematic's SVG and its size, the netlist's file type, size, encoding and lines.

import { h, icon, select, sizeMeter, titled } from "./icons.js";
import { fetchData, focusSeries, on, series, setFocus, state, status } from "./store.js";
import { bytes } from "./units.js";

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

// a text's encoding as its bytes tell it: ASCII where every character is, else UTF-8 (as fetched)
const encoding = (text) => (/^[\x00-\x7f]*$/.test(text) ? "ASCII" : "UTF-8");

// a SPICE line's parts, highlighted as the Compiler's editor does: a comment, a dot statement, a
// device (its name's first letter), a continuation; parameters (name=value) within
function spiceLine(line) {
    if (/^\s*\*/.test(line)) return [h("span.sp-comment", {}, line)];
    const comment = line.search(/[$;]/);
    const [code, rest] = comment >= 0 ? [line.slice(0, comment), line.slice(comment)] : [line, ""];
    const parts = [];
    const head = code.match(/^(\s*)(\.\w+|\+|[A-Za-z]\w*)/);
    let body = code;
    if (head) {
        const kind = head[2].startsWith(".") ? "sp-keyword" : head[2] === "+" ? "sp-operator" : /^[Mm]/.test(head[2]) ? "sp-device" : /^[Xx]/.test(head[2]) ? "sp-instance" : "sp-def";
        parts.push(head[1], h(`span.${kind}`, {}, head[2]));
        body = code.slice(head[0].length);
    }
    for (const piece of body.split(/(\b[A-Za-z_]\w*=)/)) parts.push(/^[A-Za-z_]\w*=$/.test(piece) ? h("span.sp-param", {}, piece) : piece);
    if (rest) parts.push(h("span.sp-comment", {}, rest));
    return parts;
}

// view: "schematic" or "netlist"
export class SchematicPanel {
    constructor(container, view = "schematic") {
        this.viewName = view;
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.sheet = h("div.sheet");
        this.page = h("div.page");
        // the netlist as a listing, numbered and highlighted (no editor library: it loads nowhere a
        // page cannot fetch a stylesheet)
        this.listing = h("div.netlist-listing", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("schematic", 28) }), h("strong", {}, view === "netlist" ? "No netlist" : "No schematic"), h("span", {}, ""));
        this.sheet.append(this.page);
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.sheet, this.listing, this.emptyNote));
        container.element.append(this.element);
        this.view = { k: 1, x: 0, y: 0 };
        this.bindInput();
        this.off = [on("block", () => this.refresh()), on("selection", () => this.refresh()), on("focus", () => this.refresh())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.resizeObserver = new ResizeObserver(() => this.box && !this.moved && this.fit());
        this.resizeObserver.observe(this.sheet);
        this.refresh();
    }

    // the bar: the series to show where several are, then what is shown (its file and size), the
    // schematic's fit
    bar(shown, focus, facts) {
        this.toolbar.replaceChildren();
        if (shown.length > 1) {
            this.toolbar.append(titled("Series", select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}` })), focus?.key, (value) => setFocus(value))));
        }
        this.toolbar.append(h("span.grow"));
        if (facts) this.toolbar.append(sizeMeter({ ...facts, memory: false }));
        if (facts && this.viewName === "schematic") this.toolbar.append(h("button.icon-btn", { title: "Fit (double-click)", onclick: () => this.fit(), html: icon("fit", 14) }));
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
        const path = entry && (view === "netlist" ? entry.netlist : entry.path);
        if (!path) {
            this.bar(shown, focus, null);
            this.page.replaceChildren();
            this.listing.style.display = "none";
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
            const size = bytes(new TextEncoder().encode(text).length);
            this.listing.style.display = view === "netlist" ? "" : "none";
            this.sheet.style.display = view === "netlist" ? "none" : "";
            if (view === "netlist") {
                const lines = text.replace(/\n$/, "").split("\n");
                const type = `.${path.split(".").pop()}`;
                this.bar(shown, focus, { file: size, label: type, extra: [encoding(text), `${lines.length} lines`] });
                this.listing.replaceChildren(
                    h(
                        "pre.netlist-code",
                        {},
                        lines.map((line, index) => h("span.line", {}, h("span.number", {}, String(index + 1)), h("span.code", {}, ...spiceLine(line)), "\n")),
                    ),
                );
                return;
            }
            this.bar(shown, focus, { file: size, label: "SVG" });
            this.page.innerHTML = scopedSvg(text);
            const svg = this.page.querySelector("svg");
            // no outline around the sheet, nor its white backdrop: the sheet is the theme's
            svg.querySelectorAll(":scope > rect[stroke-dasharray], :scope > rect[fill='white'], :scope > rect[fill='#fff'], :scope > rect[fill='#ffffff']").forEach((rect) => rect.remove());
            // fitted to what it draws, not its page's margins
            const drawn = svg.getBBox();
            this.box = drawn.width && drawn.height ? [drawn.x, drawn.y, drawn.width, drawn.height] : [0, 0, Number(svg.getAttribute("width")) || svg.viewBox.baseVal.width, Number(svg.getAttribute("height")) || svg.viewBox.baseVal.height];
            this.moved = false;
            this.fit();
        } catch (error) {
            status(`${view === "netlist" ? "Netlist" : "Schematic"}: ${error.message}`, true);
        }
    }

    // the drawing as large as the sheet takes it, a small margin around
    fit() {
        if (!this.box) return;
        const width = this.sheet.clientWidth;
        const height = this.sheet.clientHeight;
        if (!width || !height) return;
        const [bx, by, bw, bh] = this.box;
        const k = 0.94 * Math.min(width / bw, height / bh);
        this.view = { k, x: (width - k * bw) / 2 - k * bx, y: (height - k * bh) / 2 - k * by };
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
