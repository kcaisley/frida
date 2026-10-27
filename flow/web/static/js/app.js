// The viewer, one page (index.html): the Library of blocks on the left (it folds to a strip), a top
// bar, and under it the stage in one of four states, kept in the URL's hash so a view is bookmarked
// and Back and Forward step through them (#block=<block>&search=<label>&ids=<id>,<id>&compiler&job=<run>):
//   the Assembler (no ids): the block's sweep, or one of its optimizations (search, a study's problem
//     as adc(bits=12); the Sweeps panel's Search picks it), its table on its side and its scatter (sweep.js);
//     marking instances (a column's head, a point) loads nothing;
//   the Explorer (one id, the top bar's View): its column, its analyses, waveforms, layout and
//     schematic (detail.js);
//   the Comparer (several ids, Compare): their columns, their analyses stacked (detail.js);
//   the Compiler (compiler, the Compiler button): a netlist laid out (compile.js), the block and the
//     instances kept for the way back.
// The top bar's back button returns to every instance and unloads the instances' panels. Nothing
// opens a tab or a window.

import { h, icon, toast } from "./icons.js";
import { Layout } from "./regions.js";
import { emit, on, recall, setBar, store } from "./store.js";
import { clearFilters, marks, ScatterPanel, setBlock, setMarks, setSearches, SweepTablePanel, sweepStatus } from "./sweep.js";

const app = {
    catalog: null, // block -> {title, run, instances, searches: {label -> {table, title, run, instances}}}
    block: null, // the shown block's name
    search: null, // the shown optimization's label, null for the block's sweep
    file: null, // the shown table's name under data/sweep/: the block's, or its search's
    table: null, // the shown table
    mode: null, // "table", "view", "compare" or "compiler"
    key: null, // what the stage shows: block, mode and ids
    ids: [],
    stage: null, // the shown state's panels (not the Assembler's, kept while hidden)
    routes: 0, // the newest hash change
    mounts: 0, // the newest stage
};

const element = {};

async function fetchJson(path) {
    const response = await fetch(`data/${path}`);
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
}

// ---- the URL ----------------------------------------------------------------------------------

function parseHash() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    return {
        block: params.get("block"),
        search: params.get("search"),
        ids: (params.get("ids") || "").split(",").filter(Boolean),
        compiler: params.has("compiler"),
        job: params.get("job"),
    };
}

function hashOf({ block, search = null, ids = [], compiler = false, job = null }) {
    const parts = [];
    if (block) parts.push(`block=${encodeURIComponent(block)}`);
    if (search) parts.push(`search=${encodeURIComponent(search)}`);
    if (ids.length) parts.push(`ids=${ids.map(encodeURIComponent).join(",")}`);
    if (compiler) parts.push("compiler", ...(job ? [`job=${encodeURIComponent(job)}`] : []));
    return `#${parts.join("&")}`;
}

// a step the user takes: a history entry of its own
function navigate(change) {
    const next = { ...parseHash(), ...change };
    if (!next.compiler) next.job = null;
    const hash = hashOf(next);
    if (hash !== location.hash) location.hash = hash;
}

// the URL corrected or completed in place (no entry of its own)
function amend(change) {
    history.replaceState(null, "", hashOf({ ...parseHash(), ...change }));
}

// ---- the states -------------------------------------------------------------------------------

async function route() {
    const token = ++app.routes;
    const want = parseHash();
    // the block: the URL's, else the last one shown
    let block = want.block && app.catalog[want.block] ? want.block : null;
    if (want.block && !block) toast(`No sweep table for ${want.block}`);
    const last = recall("sweep.block", null);
    block ||= app.block || (app.catalog[last] ? last : Object.keys(app.catalog)[0]);
    // the search: the URL's, else the block's sweep, else (a block with optimizations alone) its first
    const searches = app.catalog[block].searches || {};
    let search = want.search && searches[want.search] ? want.search : null;
    if (want.search && !search) toast(`No search ${want.search} of ${block}`);
    if (!search && app.catalog[block].instances === undefined) search = Object.keys(searches)[0] || null;
    // another block's or search's ids are not this one's
    const same = block === want.block && search === want.search;
    if (!same) amend({ block, search, ids: [] });
    const file = search ? searches[search].table : block;
    if (file !== app.file || !app.table) {
        let table;
        try {
            table = await fetchJson(`sweep/${file}.json`);
        } catch (error) {
            toast(error.message);
            return;
        }
        if (token !== app.routes) return;
        app.block = block;
        app.search = search;
        app.file = file;
        app.table = table;
        store("sweep.block", block);
        setBlock(table);
        // the Search: the block's sweep and each of its optimizations, where it has any
        const options = [...(app.catalog[block].instances !== undefined ? [{ value: "", label: `sweep · ${app.catalog[block].instances}` }] : []), ...Object.entries(searches).map(([label, entry]) => ({ value: label, label: `${label} · ${entry.instances}` }))];
        setSearches(Object.keys(searches).length ? options : [], search || "", (value) => navigate({ search: value || null, ids: [] }));
        renderLibrary();
    }
    // the instances: those of the shown table (an id from an older sweep is gone)
    const ids = same ? want.ids : [];
    const known = ids.filter((id) => app.table.rows.some((row) => row.id === id));
    if (known.length !== ids.length) {
        toast(`Not in ${block}'s sweep: ${ids.filter((id) => !known.includes(id)).join(", ")}`);
        amend({ ids: known });
    }
    const mode = want.compiler ? "compiler" : !known.length ? "table" : known.length === 1 ? "view" : "compare";
    await show(mode, known, want);
}

async function show(mode, ids, want) {
    const key = mode === "compiler" ? "compiler" : `${app.file}|${mode}|${ids.join(",")}`;
    if (key === app.key) {
        if (mode === "compiler") app.stage?.show?.(want.job);
        renderBar();
        return;
    }
    const token = ++app.mounts;
    app.stage?.destroy();
    app.stage = null;
    app.key = key;
    app.mode = mode;
    app.ids = ids;
    // one host on the stage at a time: the other neither shows nor takes the mouse
    element.sweeps.classList.toggle("hidden", mode !== "table");
    element.view.classList.toggle("hidden", mode === "table");
    element.view.replaceChildren();
    renderBar();
    document.title = { table: `Assembler · ${app.block}`, view: `Explorer · ${app.block}`, compare: `Comparer · ${app.block} (${ids.length})`, compiler: "Compiler" }[mode];
    if (mode === "table") return;
    if (mode === "compiler") {
        const { mountCompiler } = await import("./compile.js");
        if (token !== app.mounts) return;
        const stage = await mountCompiler(element.view, { job: want.job, onJob: (id) => app.mode === "compiler" && amend({ job: id }) });
        if (token !== app.mounts) stage.destroy();
        else app.stage = stage;
        return;
    }
    // View and Compare: the marked instances are the shown ones, their files loaded only now
    setMarks(ids);
    const note = h("div.stage-note", {}, h("div.spinner"), h("span", {}, `Loading ${ids.length > 1 ? `the ${ids.length} instances` : "the instance"}…`));
    element.view.append(note);
    let instances;
    let mount;
    try {
        [instances, { mountInstances: mount }] = await Promise.all([Promise.all(ids.map((id) => fetchJson(`sweep/${app.file}/${id}.json`).then((instance) => ({ ...instance, id })))), import("./detail.js")]);
    } catch (error) {
        if (token !== app.mounts) return;
        note.replaceChildren(h("strong", {}, "The instance did not load"), h("span.mono.muted", {}, error.message));
        return;
    }
    if (token !== app.mounts) return;
    note.remove();
    app.stage = mount(element.view, {
        block: app.file,
        instances,
        onRemove: (id) => navigate({ ids: app.ids.filter((item) => item !== id) }),
        onView: (id) => navigate({ ids: [id] }),
    });
}

// ---- the Library ------------------------------------------------------------------------------

function renderLibrary() {
    const list = element.blocks;
    list.replaceChildren();
    // the blocks whose name or title has the filter's text
    const query = element.filter.value.trim().toLowerCase();
    for (const [name, entry] of Object.entries(app.catalog)) {
        if (query && !`${name} ${entry.title || ""}`.toLowerCase().includes(query)) continue;
        // the block's folder under flow/ and its instance count, as Zed's git panel lists a file
        const row = h(
            "button.block-row",
            { title: [entry.instances !== undefined ? `${entry.title}: ${entry.instances} instances, run ${entry.run}` : entry.title, ...Object.entries(entry.searches || {}).map(([label, search]) => `${label}: ${search.run}`)].join("\n"), onclick: () => navigate({ block: name, search: null, ids: [], compiler: false }) },
            h("span.title", {}, name),
            h("span.count", {}, `${entry.instances ?? Object.values(entry.searches || {}).reduce((total, search) => total + search.instances, 0)}`),
        );
        if (name === app.block) row.classList.add("on");
        list.append(row);
    }
}

function setCollapsed(collapsed) {
    element.library.classList.toggle("collapsed", collapsed);
    element.fold.innerHTML = icon(collapsed ? "chevronRight" : "chevronLeft", 14);
    element.fold.title = collapsed ? "Show the Library" : "Fold the Library to the left";
    store("library.collapsed", collapsed);
}

// ---- the bar: in the toolbar of the shown state's first panel (store.js's setBar) -------------

function button(name, label, title, onclick, { on = false, disabled = false } = {}) {
    const item = h(`button.bar-btn${on ? ".on" : ""}`, { title, onclick }, h("span", { html: icon(name, 14) }), label);
    item.disabled = disabled;
    return item;
}

function renderBar() {
    if (!app.table) return;
    const mode = app.mode;
    const marked = marks();
    const status = sweepStatus();
    const left = [];
    if (mode === "view" || mode === "compare") left.push(button("back", "All instances", "Back to every instance of the block (the shown ones stay marked)", () => navigate({ ids: [] })));
    if (mode === "compiler") left.push(button("back", app.block, `Back to ${app.table.title}`, () => navigate({ compiler: false })));
    if (mode === "table") {
        // the filters' and sort's clear, the marks' (the instances shown are the table's corner)
        const clear = button("unfilter", "", "Clear every filter and the sort", () => clearFilters());
        clear.disabled = !status.filtered && !status.sorted;
        left.push(clear);
        if (marked.length) left.push(h("button.bar-btn.bar-marks", { title: "Unmark every instance", onclick: () => setMarks([]) }, `${marked.length} marked`, h("span", { html: icon("x", 12) })));
    }
    const single = marked.length === 1;
    const several = marked.length > 1;
    const view = button(
        "eye",
        "View",
        single ? "View the marked instance in place: its analyses, waveforms, layout and schematic" : "View: mark exactly one instance (a column's ○ or its point)",
        () => navigate({ ids: marked, compiler: false }),
        { on: mode === "view", disabled: !single || (mode === "view" && marked[0] === app.ids[0]) },
    );
    const compare = button(
        "compare",
        several ? `Compare ${marked.length}` : "Compare",
        several ? `Compare the ${marked.length} marked instances in place: their parameters, metrics and analyses side by side` : "Compare: mark two or more instances",
        () => navigate({ ids: marked, compiler: false }),
        { on: mode === "compare", disabled: !several || (mode === "compare" && marked.join(",") === app.ids.join(",")) },
    );
    const compiler = button("chip", "Compiler", mode === "compiler" ? `Back to ${app.block}` : "The Compiler: lay out a netlist with ALIGN and check it (the block and its marked instances stay)", () => navigate({ compiler: mode !== "compiler" }), {
        on: mode === "compiler",
    });
    setBar(mode, mode === "compiler" ? left : [...left, h("span.grow"), h("div.bar-group", {}, view, compare, compiler)]);
}

// ---- the page ---------------------------------------------------------------------------------

function build() {
    element.fold = h("button.icon-btn.fold", { onclick: () => setCollapsed(!element.library.classList.contains("collapsed")) });
    element.blocks = h("div.block-list");
    element.filter = h("input", { type: "search", placeholder: "Filter", spellcheck: "false", oninput: () => renderLibrary() });
    element.library = h(
        "aside.library",
        {},
        // as the stage's regions: a head with its one tab (and the fold), a panel's toolbar (the filter
        // box) and its list in the region's body
        h("div.region-head.single.library-head", {}, h("button.region-tab.on.library-title", { tabindex: "-1" }, "Library"), h("span.grow"), element.fold),
        // folded: the strip's name, a button too
        h("button.library-strip", { title: "Show the Library", onclick: () => setCollapsed(false) }, "Library"),
        h(
            "div.library-main",
            {},
            h("div.panel-toolbar.library-tools", {}, h("label.search-field", { title: "Show the blocks whose name or title has this text" }, h("span", { html: icon("filter", 13) }), element.filter)),
            h("div.library-body", {}, element.blocks),
        ),
    );
    element.sweeps = h("div.stage-host");
    element.view = h("div.stage-host");
    element.stage = h("div.stage", {}, element.sweeps, element.view);
    document.getElementById("app").replaceChildren(element.library, h("main.main", {}, element.stage));
    setCollapsed(recall("library.collapsed", false));
    // the Assembler's two regions, made once and kept while another state is shown
    const sweeps = new Layout(element.sweeps);
    sweeps.mount(
        sweeps.split(
            "row",
            [sweeps.region([{ id: "sweeps", title: "Sweeps", make: (container) => new SweepTablePanel(container) }]), sweeps.region([{ id: "scatter", title: "Scatter", make: (container) => new ScatterPanel(container) }])],
            "assembler",
            [58, 42],
        ),
    );
}

async function main() {
    // the panels' errors show for a few seconds in the corner: the page has no status bar
    on("status", ({ message, error }) => error && toast(message));
    on("marks", () => renderBar());
    on("sweep", () => renderBar());
    // F, K and L reach the shown layout unless a field or the editor has the keys
    window.addEventListener("keydown", (event) => {
        const target = event.target;
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement || target.isContentEditable || target.closest?.(".CodeMirror")) return;
        const key = event.key.toLowerCase();
        if (key === "f") emit("command", "fit");
        else if (key === "k") emit("command", "ruler");
        else if (key === "l") emit("command", "labels");
        else return;
        event.preventDefault();
    });
    // the desktop's light or dark setting, followed as it changes
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
        document.documentElement.dataset.theme = event.matches ? "dark" : "light";
        emit("theme", document.documentElement.dataset.theme);
    });
    build();
    const loading = document.getElementById("loading");
    try {
        app.catalog = await fetchJson("sweep/catalog.json");
    } catch (error) {
        loading.replaceChildren(h("strong", {}, "No sweep tables"), h("span", {}, "Run  uv run python -m flow web.tables  and reload."), h("span.mono.muted", {}, error.message));
        return;
    }
    renderLibrary();
    window.addEventListener("hashchange", () => route());
    await route();
    loading.classList.add("done");
}

main();
