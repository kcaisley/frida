// The page's fixed arrangement, in place of GoldenLayout's docking: regions that cannot be closed,
// moved or popped out, split into rows and columns by dividers that drag (their shares kept per
// arrangement in the browser), a region's panels as tabs over one body. Each panel gets a container
// as GoldenLayout gave one (its element, on("destroy" | "show" | "resize")), so the shared panels
// (layout2d, layout3d, layers, traces, panels) run unchanged.

import { h } from "./icons.js";
import { recall, store } from "./store.js";

// what a panel is given: the element it fills and its lifetime's events
export class Container {
    constructor(element) {
        this.element = element;
        this.handlers = new Map();
    }

    on(name, callback) {
        if (!this.handlers.has(name)) this.handlers.set(name, new Set());
        this.handlers.get(name).add(callback);
    }

    emit(name) {
        for (const callback of this.handlers.get(name) || []) {
            try {
                callback();
            } catch (error) {
                console.error(error);
            }
        }
    }
}

// one arrangement (a selection state's panels): its regions start once it is on the page and go
// together
export class Layout {
    constructor(host) {
        this.host = host;
        this.regions = [];
        this.element = null;
    }

    // panels: [{id, title, make(container)}]; key: the region's remembered tab
    region(panels, key) {
        const region = new Region(panels, key);
        this.regions.push(region);
        return region.element;
    }

    // items: elements (regions or splits) side by side ("row") or stacked ("column"); shares in
    // percent, remembered under key once dragged
    split(direction, items, key, shares) {
        return split(direction, items, key, shares);
    }

    mount(root) {
        this.element = h("div.layout-root", {}, root);
        this.host.append(this.element);
        for (const region of this.regions) region.start();
        return this;
    }

    has(id) {
        return this.regions.some((region) => region.has(id));
    }

    // bring a panel's tab to the front
    activate(id) {
        for (const region of this.regions) if (region.has(id)) region.activate(id);
    }

    destroy() {
        for (const region of this.regions) region.destroy();
        this.regions = [];
        this.element?.remove();
        this.element = null;
    }
}

class Region {
    constructor(panels, key) {
        this.key = key;
        this.head = h("div.region-head");
        this.body = h("div.region-body");
        this.element = h("div.region", {}, this.head, this.body);
        this.entries = panels.map((panel) => {
            const pane = h("div.pane");
            const tab = h("button.region-tab", { onclick: () => this.activate(panel.id) }, panel.title);
            this.head.append(tab);
            this.body.append(pane);
            return { ...panel, pane, tab, container: new Container(pane), made: null };
        });
        // a lone panel's title is a label, not a tab to press
        if (this.entries.length === 1) this.head.classList.add("single");
        const saved = key ? recall(`tab.${key}`, null) : null;
        this.active = this.entries.some((entry) => entry.id === saved) ? saved : this.entries[0]?.id;
        this.show();
        this.resizeObserver = new ResizeObserver(() => this.current()?.container.emit("resize"));
    }

    has(id) {
        return this.entries.some((entry) => entry.id === id);
    }

    current() {
        return this.entries.find((entry) => entry.id === this.active) || null;
    }

    // every panel made at once, as GoldenLayout made a stack's: the hidden ones keep up with the
    // page's events (the layers follow the layout panels whether shown or not)
    start() {
        for (const entry of this.entries) {
            try {
                entry.made = entry.make(entry.container);
            } catch (error) {
                console.error(error);
                entry.pane.append(h("div.empty", {}, h("strong", {}, entry.title), h("span", {}, error.message)));
            }
        }
        this.resizeObserver.observe(this.body);
    }

    show() {
        for (const entry of this.entries) {
            const on = entry.id === this.active;
            entry.pane.classList.toggle("hidden", !on);
            entry.tab.classList.toggle("on", on);
        }
    }

    activate(id) {
        if (!this.has(id)) return;
        this.active = id;
        if (this.key) store(`tab.${this.key}`, id);
        this.show();
        const entry = this.current();
        entry.container.emit("show");
        entry.container.emit("resize");
    }

    destroy() {
        this.resizeObserver.disconnect();
        for (const entry of this.entries) entry.container.emit("destroy");
    }
}

const MIN_PX = 120;

export function split(direction, items, key, shares) {
    const element = h(`div.split.${direction}`);
    const saved = key ? recall(`split.${key}`, null) : null;
    const valid = Array.isArray(saved) && saved.length === items.length && saved.every((value) => value > 0);
    let sizes = valid ? saved : shares;
    const apply = () => items.forEach((item, index) => (item.style.flex = `${sizes[index]} 1 0px`));
    // a page may fit the first item to its content, where the user has not dragged it yet
    element.dragged = valid;
    element.fitFirst = (share) => {
        if (element.dragged) return;
        const rest = shares.slice(1).reduce((sum, value) => sum + value, 0);
        sizes = [share, ...shares.slice(1).map((value) => ((100 - share) * value) / rest)];
        apply();
    };
    items.forEach((item, index) => {
        if (index) element.append(divider(index));
        element.append(item);
    });
    apply();

    function divider(index) {
        const bar = h("div.divider");
        bar.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            bar.setPointerCapture(event.pointerId);
            bar.classList.add("dragging");
            const a = items[index - 1];
            const b = items[index];
            const horizontal = direction === "row";
            const pixels = (item) => (horizontal ? item.getBoundingClientRect().width : item.getBoundingClientRect().height);
            const start = horizontal ? event.clientX : event.clientY;
            const pa = pixels(a);
            const pb = pixels(b);
            const share = sizes[index - 1] + sizes[index];
            const move = (moveEvent) => {
                const delta = (horizontal ? moveEvent.clientX : moveEvent.clientY) - start;
                const next = Math.max(Math.min(MIN_PX, pa), Math.min(pa + pb - Math.min(MIN_PX, pb), pa + delta));
                sizes = [...sizes];
                sizes[index - 1] = (share * next) / (pa + pb);
                sizes[index] = share - sizes[index - 1];
                apply();
            };
            const up = () => {
                bar.classList.remove("dragging");
                bar.removeEventListener("pointermove", move);
                bar.removeEventListener("pointerup", up);
                bar.removeEventListener("pointercancel", up);
                element.dragged = true;
                if (key) store(`split.${key}`, sizes);
            };
            bar.addEventListener("pointermove", move);
            bar.addEventListener("pointerup", up);
            bar.addEventListener("pointercancel", up);
        });
        // double-click: back to the arrangement's own shares
        bar.addEventListener("dblclick", () => {
            sizes = shares;
            element.dragged = false;
            apply();
            if (key) store(`split.${key}`, null);
            element.dispatchEvent(new Event("reset"));
        });
        return bar;
    }

    return element;
}
