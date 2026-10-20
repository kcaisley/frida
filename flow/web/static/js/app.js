// The application shell: toolbar, GoldenLayout's docked panels and the status bar.

import { GoldenLayout, LayoutConfig } from "golden-layout";
import { h, icon, popover } from "./icons.js";
import { LayersPanel } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { BlocksPanel, FiguresPanel, InstancesPanel, SchematicPanel, SelectionPanel } from "./panels.js";
import { PlotPanel, TablePanel } from "./plot.js";
import { TracesPanel } from "./traces.js";
import { emit, loadBlock, loadCatalog, on, recall, series, state, status, store } from "./store.js";

const LAYOUT_KEY = "layout.v3";

const PANELS = {
    blocks: { title: "Blocks", icon: "list", make: (container) => new BlocksPanel(container) },
    selection: { title: "Selection", icon: "params", make: (container) => new SelectionPanel(container) },
    instances: { title: "Instances", icon: "instances", make: (container, saved) => new InstancesPanel(container, saved) },
    plot: { title: "Plot", icon: "chart", make: (container, saved) => new PlotPanel(container, saved) },
    table: { title: "Results", icon: "table", make: (container, saved) => new TablePanel(container, saved) },
    traces: { title: "Traces", icon: "wave", make: (container, saved) => new TracesPanel(container, saved) },
    figures: { title: "Figures", icon: "image", make: (container, saved) => new FiguresPanel(container, saved) },
    layout: { title: "Layout", icon: "layout", make: (container, saved) => new LayoutPanel(container, saved) },
    layout3d: { title: "3D", icon: "cube", make: (container, saved) => new Layout3DPanel(container, saved) },
    schematic: { title: "Schematic", icon: "schematic", make: (container, saved) => new SchematicPanel(container, saved) },
    layers: { title: "Layers", icon: "layers", make: (container) => new LayersPanel(container) },
};

const component = (type, componentState = {}) => ({ type: "component", componentType: type, title: PANELS[type].title, componentState });

const DEFAULT_LAYOUT = {
    settings: { showPopoutIcon: false, popoutWholeStack: false, reorderEnabled: true },
    dimensions: { borderWidth: 4, headerHeight: 28, minItemHeight: 90, minItemWidth: 180 },
    header: { popout: false },
    root: {
        type: "row",
        content: [
            {
                type: "column",
                width: 19,
                content: [
                    { type: "stack", height: 30, content: [component("blocks")] },
                    { type: "stack", height: 70, content: [component("selection")] },
                ],
            },
            {
                type: "column",
                width: 48,
                content: [
                    // the instances first: the cached targets are what there is to choose from
                    { type: "stack", height: 58, content: [component("instances"), component("plot", { slot: 0 }), component("table"), component("traces"), component("figures")] },
                    { type: "stack", height: 42, content: [component("plot", { slot: 1 })] },
                ],
            },
            {
                type: "column",
                width: 33,
                content: [
                    { type: "stack", height: 60, content: [component("layout"), component("layout3d")] },
                    { type: "stack", height: 40, content: [component("schematic"), component("layers")] },
                ],
            },
        ],
    },
};

let layout = null;

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    store("theme", theme);
    emit("theme", theme);
    buildToolbar();
}

function addPanel(type, componentState = {}) {
    layout.addComponent(type, componentState, PANELS[type].title);
}

function resetLayout() {
    store(LAYOUT_KEY, null);
    layout.loadLayout(DEFAULT_LAYOUT);
    status("Panels reset");
}

function dialog(title, ...content) {
    const back = h("div.dialog-back");
    const box = h("div.dialog", {}, h("h2", {}, title), ...content);
    back.append(box);
    back.addEventListener("mousedown", (event) => event.target === back && back.remove());
    document.addEventListener("keydown", function close(event) {
        if (event.key === "Escape") {
            back.remove();
            document.removeEventListener("keydown", close);
        }
    });
    document.body.append(back);
}

function shortcuts() {
    const rows = [
        ["/", "Filter blocks"],
        ["F", "Fit the layout"],
        ["K", "Measure in the layout (ruler); Esc clears"],
        ["L", "Layout labels"],
        ["+  −", "Zoom the layout"],
        ["Wheel, drag", "Zoom about the cursor, pan"],
        ["Right-drag", "Zoom the layout to a box"],
        ["Click a point", "Leave a plot point out (click its ring to restore)"],
        ["Alt-click", "Show only that PDK, case, parameter value or layer"],
        ["T", "Dark or light theme"],
        ["?", "This list"],
    ];
    const generated = state.catalog?.generated?.slice(0, 16).replace("T", " ") || "—";
    dialog(
        "Keyboard and mouse",
        h("table", {}, h("tbody", {}, rows.map(([keys, what]) => h("tr", {}, h("td", {}, ...keys.split(/(?<=\S) {2}|, /).map((key) => h("kbd", { style: { marginRight: "4px" } }, key))), h("td", {}, what))))),
        h("p", { class: "muted" }, `Cached results exported ${generated} to build/web/data: each block's characterization study on its pinned run, the layout runners' layouts and their netlists. Refresh them with`),
        h("pre", { class: "mono", style: { padding: "8px 10px", background: "var(--bg-input)", borderRadius: "4px" } }, "uv run python -m flow.web export"),
    );
}

function buildToolbar() {
    const bar = document.getElementById("toolbar");
    bar.replaceChildren();
    const block = state.block;
    const picker = h(
        "div.block-picker",
        { title: "Choose a block ( / filters the Blocks panel)" },
        h("span", { html: icon("chip", 16), style: { color: "var(--accent-bright)", display: "flex" } }),
        h("span.name", {}, block?.title || "Choose a block"),
        h("span.key", {}, block?.name || ""),
        h("span.chev", { html: icon("chevron", 14) }),
    );
    picker.addEventListener("click", () =>
        popover(picker, (element) => {
            for (const entry of state.catalog?.blocks || []) {
                const row = h("div.block-row", {}, h("span.title", {}, entry.title), h("span.key", {}, entry.name), h("span.counts", {}, h("span.badge", {}, `${entry.cases}`), h(entry.layouts ? "span.badge.ok" : "span.badge", {}, `${entry.layouts} ⬚`)));
                if (entry.name === block?.name) row.classList.add("on");
                row.addEventListener("click", () => {
                    element.remove();
                    loadBlock(entry.name).catch((error) => status(error.message, true));
                });
                element.append(row);
            }
        }),
    );
    const tool = (name, title, onclick, label) => h("button.tool-btn", { title, onclick }, h("span", { html: icon(name, 16) }), label ? h("span", {}, label) : null);
    const shown = series();
    const strip = h("div.series-strip", { title: shown.map((item) => item.label).join("\n") });
    for (const item of shown.slice(0, 24)) strip.append(h("span.series-dot", { style: { background: item.color } }));
    const theme = document.documentElement.dataset.theme;
    // every other panel, and the default arrangement
    const panels = h("button.tool-btn", { title: "More panels" }, h("span", { html: icon("plus", 16) }), h("span", { html: icon("chevron", 12), style: { display: "flex" } }));
    panels.addEventListener("click", () =>
        popover(panels, (element) => {
            for (const type of ["figures", "layers", "selection", "blocks", "instances", "plot", "table", "traces", "layout", "layout3d", "schematic"]) {
                element.append(
                    h(
                        "div.menu-item",
                        {
                            onclick: () => {
                                element.remove();
                                addPanel(type, type === "plot" ? { slot: 0 } : {});
                            },
                        },
                        h("span.check", { html: icon(PANELS[type].icon, 14) }),
                        PANELS[type].title,
                    ),
                );
            }
            element.append(
                h("div.menu-sep"),
                h("div.menu-item", { onclick: () => { element.remove(); resetLayout(); } }, h("span.check", { html: icon("reset", 14) }), "Reset panels"),
            );
        }),
    );
    bar.append(
        picker,
        h("div.tool-sep"),
        tool("instances", "The block's instances and their parameters", () => addPanel("instances"), "Instances"),
        tool("chart", "New plot panel", () => addPanel("plot", { slot: 0 }), "Plot"),
        tool("table", "The results per instance, in a table", () => addPanel("table"), "Results"),
        tool("wave", "The focused instance's transient waveforms", () => addPanel("traces"), "Traces"),
        tool("layout", "New layout panel", () => addPanel("layout"), "Layout"),
        tool("cube", "New 3-D panel", () => addPanel("layout3d"), "3D"),
        tool("schematic", "New schematic panel", () => addPanel("schematic"), "Schematic"),
        panels,
        h("div.tool-sep"),
        tool("fit", "Fit the layout (F)", () => emit("command", "fit")),
        tool("ruler", "Measure (K)", () => emit("command", "ruler")),
        tool("tag", "Layout labels (L)", () => emit("command", "labels")),
        h("span.spacer"),
        h("span.toolbar-title", {}, `${shown.length} series`),
        strip,
        h("div.tool-sep"),
        tool(theme === "dark" ? "sun" : "moon", "Theme (T)", () => setTheme(theme === "dark" ? "light" : "dark")),
        tool("keyboard", "Keyboard and mouse (?)", shortcuts),
    );
}

function buildStatusBar() {
    const bar = document.getElementById("status-bar");
    const message = h("span.msg", {}, "Ready");
    const cursor = h("span.cell", {}, "");
    const count = h("span.cell", {}, "");
    const generated = h("span.cell", { title: "When the data was exported (python -m flow.web export)" }, "");
    bar.replaceChildren(h("span.cell", {}, h("span.dot"), "cached"), message, cursor, count, generated);
    on("catalog", (catalog) => {
        generated.textContent = `data ${catalog.generated.slice(0, 16).replace("T", " ")}`;
    });
    on("status", ({ message: text, error }) => {
        message.textContent = text;
        message.classList.toggle("err", Boolean(error));
        message.title = text;
    });
    on("cursor", (text) => {
        cursor.textContent = text;
    });
    on("selection", () => {
        const shown = series();
        count.textContent = state.block ? `${state.block.name} · ${shown.length} series` : "";
    });
}

function bindKeys() {
    window.addEventListener("keydown", (event) => {
        if (event.defaultPrevented || event.ctrlKey || event.metaKey) return;
        const target = event.target;
        if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement) return;
        const key = event.key;
        if (key === "/") emit("command", "search");
        else if (key === "?") shortcuts();
        else if (key === "t" || key === "T") setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
        else if (key === "f" || key === "F") emit("command", "fit");
        else if (key === "k" || key === "K") emit("command", "ruler");
        else if (key === "l" || key === "L") emit("command", "labels");
        else return;
        event.preventDefault();
    });
}

function startLayout() {
    const container = document.getElementById("gl-container");
    layout = new GoldenLayout(container);
    for (const [type, panel] of Object.entries(PANELS)) {
        layout.registerComponentFactoryFunction(type, (glContainer, saved) => {
            panel.make(glContainer, saved);
        });
    }
    const saved = recall(LAYOUT_KEY, null);
    try {
        layout.loadLayout(saved ? LayoutConfig.fromResolved(saved) : DEFAULT_LAYOUT);
    } catch (error) {
        console.warn("saved panel layout not usable", error);
        layout.loadLayout(DEFAULT_LAYOUT);
    }
    let pending = 0;
    layout.on("stateChanged", () => {
        clearTimeout(pending);
        pending = setTimeout(() => {
            try {
                store(LAYOUT_KEY, layout.saveLayout());
            } catch (error) {
                console.warn(error);
            }
        }, 400);
    });
    new ResizeObserver(() => layout.updateRootSize?.() ?? layout.updateSize?.()).observe(container);
}

async function main() {
    buildToolbar();
    buildStatusBar();
    bindKeys();
    on("block", () => buildToolbar());
    on("selection", () => buildToolbar());
    const loading = document.getElementById("loading");
    try {
        await loadCatalog();
    } catch (error) {
        loading.replaceChildren(
            h("strong", {}, "No exported data"),
            h("span", {}, "Run  uv run python -m flow.web export  and reload."),
            h("span.mono.muted", {}, error.message),
        );
        return;
    }
    startLayout();
    const blocks = state.catalog.blocks.map((block) => block.name);
    const last = recall("block", null);
    const first = blocks.includes(last) ? last : blocks[0];
    if (first) await loadBlock(first).catch((error) => status(error.message, true));
    loading.classList.add("done");
}

main();
