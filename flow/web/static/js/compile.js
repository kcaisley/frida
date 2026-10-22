// The layout compiler, a view of the one page (index.html#compiler&job=<id>, switched to from the
// top bar and back with the block and selection kept): a netlist typed, pasted or opened on the left
// and checked as it changes (its diagnostics, its schematic), then laid out on demand in the chosen
// PDK: ALIGN places and routes it, gdscheck checks its rules and the PDK's KLayout deck its netlist.
// The Flow panel starts a run and follows its stages; the result shows in the shared Layout, 3D and
// Layers panels on the right, fed through a one-instance block as the Explorer's. Its state (the
// editor, the run, its polling) outlives the view: switched back to, it is as it was left.

import { h, icon, seg, select, toast } from "./icons.js";
import { LayersPanel } from "./layers.js";
import { Layout3DPanel } from "./layout3d.js";
import { LayoutPanel } from "./layout2d.js";
import { SchematicPanel } from "./panels.js";
import { Layout } from "./regions.js";
import { emit, on, recall, state, store } from "./store.js";

// the editor, from jsDelivr the first time the Compiler is opened
const CODEMIRROR = "https://cdn.jsdelivr.net/npm/codemirror@5.65.18";

// a run's stages, in order (the server's keys)
const STAGES = [
    ["check", "Check"],
    ["constraints", "Constraints"],
    ["primitives", "Primitives"],
    ["placement", "Placement"],
    ["routing", "Routing"],
    ["gds", "GDS"],
    ["drc", "DRC"],
    ["lvs", "LVS"],
    ["view", "View"],
];
const ACTIVE = new Set(["queued", "running"]);
const SOURCES = { netlist: "Netlist issues", align: "ALIGN messages", drc: "DRC violations", lvs: "LVS mismatches" };
const GROUPS = ["Netlist", "Layout", "DRC", "LVS"];
const STYLES = [
    { value: "symmetric", label: "Symmetric", title: "ALIGN finds matched pairs and places them symmetrically" },
    { value: "dense", label: "Dense", title: "No symmetry constraints: ALIGN packs for area" },
];
const KEY = "compile"; // the one case of the page's block

// the page's own icons, drawn as icons.js draws its set
const GLYPHS = {
    play: '<path d="M4.5 2.5v11l9-5.5z"/>',
    stop: '<rect x="3.5" y="3.5" width="9" height="9" rx="1"/>',
    open: '<path d="M1.5 4V13h13V5.5H8L6.5 4z"/>',
    example: '<path d="M3 2h7l3 3v9H3z"/><path d="M10 2v3h3M5.5 8h5M5.5 10.5h5"/>',
    error: '<circle cx="8" cy="8" r="6"/><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4"/>',
    warning: '<path d="M8 2.2l6.3 11.3H1.7z"/><path d="M8 6.5v3.2M8 11.6v.1"/>',
    info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.9v.1"/>',
    done: '<path d="M3 8.5l3 3 7-7"/>',
    failed: '<path d="M4 4l8 8M12 4l-8 8"/>',
    skipped: '<path d="M4 8h8"/>',
    pending: '<circle cx="8" cy="8" r="3.2"/>',
    explorer: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M2 6h12M6 6v7.5"/>',
    file: '<path d="M3 2h7l3 3v9H3z"/><path d="M10 2v3h3"/>',
};

function glyph(name, size = 14) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GLYPHS[name] || ""}</svg>`;
}

const page = {
    pdks: [], // the server's PDKs, their checks and availability
    examples: {}, // PDK -> example netlist
    pdk: null,
    style: "symmetric",
    editor: null,
    check: null, // the editor's last check
    checking: false,
    checkToken: 0,
    checkTimer: null,
    marked: [], // the editor's lines carrying a lint class
    job: null, // the shown run's status
    jobText: null, // {id, text}: the shown run's netlist, to tell an edited editor
    jobs: [], // the run history, newest first
    polling: null, // the run being polled
    view: null, // the panels' Layout while the Compiler is shown
    mounted: false,
    onJob: null, // (id or null): the shown run, for the page's URL
    editorHost: null, // the editor's element, moved into each Netlist panel
    log: null, // {path, text}: the shown run's log
};

async function api(path, body) {
    const options = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const response = await fetch(`api/compile/${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(data.error || `${path}: HTTP ${response.status}`);
        error.data = data;
        error.status = response.status;
        throw error;
    }
    return data;
}

const pdkInfo = (name) => page.pdks.find((pdk) => pdk.name === name) || null;
const running = () => Boolean(page.job && ACTIVE.has(page.job.state));
const edited = () => Boolean(page.job && page.jobText?.id === page.job.id && page.editor && page.editor.getValue() !== page.jobText.text);

function duration(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "";
    if (seconds < 10) return `${seconds.toFixed(1)} s`;
    if (seconds < 60) return `${Math.round(seconds)} s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
    return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

function when(epoch) {
    if (!epoch) return "";
    const date = new Date(epoch * 1000);
    const today = new Date().toDateString() === date.toDateString();
    const time = date.toTimeString().slice(0, 5);
    return today ? time : `${date.toISOString().slice(5, 10)} ${time}`;
}

// ---- the netlist check ------------------------------------------------------------------------

function scheduleCheck(delay = 500) {
    clearTimeout(page.checkTimer);
    page.checkTimer = setTimeout(runCheck, delay);
}

async function runCheck() {
    if (!page.editor || !page.pdk) return;
    const token = ++page.checkToken;
    page.checking = true;
    emit("compile", "checking");
    let result;
    try {
        result = await api("check", { netlist: page.editor.getValue(), pdk: page.pdk });
    } catch (error) {
        result = {
            ok: false,
            top: null,
            diagnostics: [{ severity: "error", source: "netlist", message: `The check did not run: ${error.message}` }],
            stats: [],
            schematic: null,
            netlist: null,
        };
    }
    if (token !== page.checkToken) return;
    page.check = result;
    page.checking = false;
    markEditor();
    shim();
    emit("compile", "check");
}

// the check's diagnostics on their lines: a gutter mark (its messages as its title), the line
// underlined in the severity's color
function markEditor() {
    const editor = page.editor;
    if (!editor) return;
    editor.operation(() => {
        editor.clearGutter("lint");
        for (const handle of page.marked) editor.removeLineClass(handle, "wrap");
        page.marked = [];
        const byLine = new Map();
        for (const item of page.check?.diagnostics || []) {
            if (!item.line || item.line > editor.lineCount()) continue;
            byLine.set(item.line, [...(byLine.get(item.line) || []), item]);
        }
        for (const [line, items] of byLine) {
            const worst = ["error", "warning", "info"].find((severity) => items.some((item) => item.severity === severity)) || "info";
            const marker = h(`div.lint-marker.${worst}`, { title: items.map((item) => item.message).join("\n"), html: glyph(worst, 12) });
            editor.setGutterMarker(line - 1, "lint", marker);
            page.marked.push(editor.addLineClass(line - 1, "wrap", `lint-line ${worst}`));
        }
    });
}

function gotoLine(line) {
    const editor = page.editor;
    if (!editor || !line) return;
    activate("netlist");
    const index = Math.min(line, editor.lineCount()) - 1;
    editor.focus();
    editor.setCursor({ line: index, ch: 0 });
    editor.scrollIntoView({ line: index, ch: 0 }, 60);
    const handle = editor.addLineClass(index, "background", "flash");
    setTimeout(() => editor.removeLineClass(handle, "background", "flash"), 1400);
}

// ---- the one-instance block the shared panels read ----------------------------------------------

function layoutNote() {
    const job = page.job;
    if (!job) return "Run the flow: the layout appears here when it is done.";
    if (job.state === "queued") return "Queued: the layout appears here when the flow is done.";
    if (job.state === "running") {
        const stage = (job.stages || []).find((item) => item.state === "running");
        return `Laying out${stage ? ` (${stage.label.toLowerCase()})` : ""}: see Flow.`;
    }
    if (job.state === "failed") return "The flow failed: see Flow and Diagnostics.";
    if (job.state === "cancelled") return "The run was cancelled.";
    return "The run wrote no layout.";
}

function schematicNote() {
    const check = page.check;
    if (!check) return "Checking the netlist…";
    if (!check.ok) return "Fix the netlist's errors to draw its schematic.";
    return "No transistors to draw.";
}

// the page's block: the run's layout once it is done, the editor's schematic as it is checked; only
// while the Compiler is shown (the store is the shown view's)
function shim() {
    if (!page.mounted) return;
    const job = page.job;
    const done = job?.state === "done" && job.files?.layout;
    const pdk = done ? job.pdk : page.pdk;
    const check = page.check;
    const before = state.block ? `${state.block.pdks[0]}|${state.block.layouts[0]?.path || ""}` : null;
    const title = (done && job.cell) || check?.top || "draft";
    state.catalog = { pdks: [pdk], blocks: [] };
    state.block = {
        name: `compile/${job?.id || "draft"}`,
        title,
        pdks: [pdk],
        cases: { [KEY]: { label: title } },
        layouts: done
            ? [
                  {
                      case: KEY,
                      pdk,
                      generator: "align",
                      path: job.files.layout,
                      cell: job.cell,
                      gds: job.files.gds ? `data/${job.files.gds}` : null,
                      drc_violations: job.checks?.drc ? job.checks.drc.violations : null,
                      lvs_correct: job.checks?.lvs ? job.checks.lvs.correct : null,
                  },
              ]
            : [],
        schematics: check ? [{ case: KEY, pdk, path: check.schematic || null, netlist: check.netlist || null, note: check.schematic ? null : schematicNote() }] : [],
        datasets: [],
        layoutNote: layoutNote(),
    };
    state.pdks = new Set([pdk]);
    state.cases = new Set([KEY]);
    state.focus = `${pdk}|${KEY}`;
    // a new layout (or none) refits the views; anything else keeps them where they are
    if (`${pdk}|${state.block.layouts[0]?.path || ""}` !== before) emit("block", state.block);
    else emit("selection");
}

// bring a panel's tab to the front
function activate(id) {
    page.view?.activate(id);
}

// ---- runs ------------------------------------------------------------------------------------

async function refreshJobs() {
    try {
        page.jobs = (await api("jobs")).jobs || [];
    } catch (error) {
        page.jobs = [];
    }
    emit("compile", "jobs");
}

async function startRun() {
    if (!page.editor) return;
    const text = page.editor.getValue();
    try {
        const { id } = await api("jobs", { netlist: text, pdk: page.pdk, style: page.style });
        page.jobText = { id, text };
        await openJob(id, false);
        refreshJobs();
    } catch (error) {
        toast(`Run: ${error.message}`);
        // the server's own check refused it: its diagnostics in place of the editor's
        if (error.data?.diagnostics) {
            page.check = { ...(page.check || {}), ok: false, diagnostics: error.data.diagnostics };
            markEditor();
            emit("compile", "check");
        }
    }
}

async function cancelRun() {
    if (!page.job) return;
    try {
        await api(`jobs/${encodeURIComponent(page.job.id)}/cancel`, {});
    } catch (error) {
        toast(`Cancel: ${error.message}`);
    }
    poll(page.job.id);
}

// show a run: its status (followed while it runs) and, from the history, its netlist, PDK and style
async function openJob(id, withNetlist) {
    page.polling = id;
    page.job = { id, state: "queued", stages: [], diagnostics: [], stats: [], files: {}, checks: {} };
    page.onJob?.(id);
    emit("markers", { boxes: [] });
    shim();
    emit("compile", "job");
    await poll(id);
    // the netlist as it was written (comments and all), else the one the flow built from
    const netlist = page.job?.files?.source || page.job?.files?.netlist;
    if (page.job?.id !== id || !netlist) return;
    try {
        const response = await fetch(`data/${netlist}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const text = await response.text();
        if (page.job?.id !== id) return;
        page.jobText = { id, text };
        // reopened with the editor's own draft: the draft stays, a note tells it apart
        if (!withNetlist) {
            emit("compile", "job");
            return;
        }
        if (page.job.style) setStyle(page.job.style);
        if (page.job.pdk && page.job.pdk !== page.pdk) setPdk(page.job.pdk, false);
        page.editor.setValue(text);
        page.editor.clearHistory();
    } catch (error) {
        toast(`The run's netlist: ${error.message}`);
    }
}

async function poll(id) {
    clearTimeout(page.timer);
    let status;
    try {
        status = await api(`jobs/${encodeURIComponent(id)}`);
    } catch (error) {
        if (page.polling !== id) return;
        if (error.status === 404) {
            toast(`No run ${id}`);
            page.job = null;
            page.polling = null;
            page.onJob?.(null);
            shim();
            emit("compile", "job");
            return;
        }
        // the server is restarting, say: try again shortly
        page.timer = setTimeout(() => poll(id), 2000);
        return;
    }
    if (page.polling !== id) return;
    const wasActive = running();
    page.job = status;
    shim();
    emit("compile", "job");
    if (ACTIVE.has(status.state)) page.timer = setTimeout(() => poll(id), 700);
    else if (wasActive) refreshJobs();
}

// ---- settings --------------------------------------------------------------------------------

const isExample = (text) => Object.values(page.examples).some((example) => example.trim() === text.trim());

function setPdk(name, swapExample = true) {
    if (name === page.pdk) return;
    page.pdk = name;
    store("compile.pdk", name);
    // an untouched example follows the PDK: its devices are the PDK's
    if (swapExample && page.editor && isExample(page.editor.getValue()) && page.examples[name]) page.editor.setValue(page.examples[name]);
    shim();
    emit("compile", "settings");
    scheduleCheck(0);
}

function setStyle(value) {
    if (value === page.style) return;
    page.style = value;
    store("compile.style", value);
    emit("compile", "settings");
}

// ---- the panels ------------------------------------------------------------------------------

class FlowPanel {
    constructor(container) {
        this.element = h("div.panel.flow");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body.flow-body");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        this.off = [on("compile", () => this.render())];
        // the running stage's clock
        this.clock = setInterval(() => running() && this.renderProgress(), 1000);
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            clearInterval(this.clock);
        });
        this.render();
    }

    render() {
        this.renderToolbar();
        this.renderProgress();
    }

    // rebuilt only when it changes: an open dropdown survives the polls
    renderToolbar() {
        const check = page.check;
        const pdk = pdkInfo(page.pdk);
        const why = running()
            ? "A run is in progress"
            : !pdk?.available
              ? pdk?.reason || "This PDK is not available"
              : page.checking || !check
                ? "Checking the netlist…"
                : !check.ok
                  ? "The netlist has errors: see Diagnostics"
                  : null;
        const key = JSON.stringify([page.pdk, page.style, running(), why, page.pdks.length]);
        if (key === this.toolbarKey) return;
        this.toolbarKey = key;
        const pdkSelect = select(
            page.pdks.map((item) => ({ value: item.name, label: item.available ? item.name : `${item.name} (unavailable)`, disabled: !item.available })),
            page.pdk,
            (value) => setPdk(value),
        );
        pdkSelect.title = pdk?.note || "";
        const run = h("button.btn-run", { title: why || "Lay out the netlist (Ctrl+Enter)", onclick: () => startRun() }, h("span", { html: glyph("play", 12) }), "Run");
        run.disabled = Boolean(why);
        this.toolbar.replaceChildren(
            h("label.field", {}, h("span", {}, "PDK"), pdkSelect),
            h("label.field", {}, h("span", {}, "Style"), seg(STYLES, page.style, (value) => setStyle(value))),
            h("span.grow"),
            running() ? h("button.icon-btn", { title: "Stop the run", onclick: () => cancelRun() }, h("span", { html: glyph("stop", 12) }), "Cancel") : "",
            run,
        );
    }

    renderProgress() {
        const job = page.job;
        const pdk = pdkInfo(job?.pdk || page.pdk);
        const parts = [];
        // what the PDK's run checks: a gdscheck-only DRC is a precheck
        if (pdk) {
            const drc = pdk.drc?.length ? pdk.drc.join(", ") : "none";
            const precheck = (pdk.drc || []).some((engine) => /precheck/i.test(engine));
            parts.push(
                h(
                    "div.flow-checks",
                    { title: pdk.note || "" },
                    h("span", {}, h("b", {}, "DRC "), drc, precheck ? h("span.muted", {}, " (precheck only)") : ""),
                    h("span.sep", {}, "·"),
                    h("span", {}, h("b", {}, "LVS "), pdk.lvs || h("span.muted", {}, "none for this PDK")),
                ),
            );
        }
        if (!job) {
            parts.push(h("div.flow-idle", {}, "Edit the netlist, then Run: ALIGN derives the constraints, places and routes; gdscheck checks the layout's rules and KLayout compares it with the netlist."));
        } else {
            const stages = STAGES.map(([key, label]) => (job.stages || []).find((item) => item.key === key) || { key, label, state: "pending" });
            const now = Date.now() / 1000;
            const finished = stages.filter((item) => item.state === "done" || item.state === "skipped").length;
            const current = stages.find((item) => item.state === "running");
            const fraction = job.state === "done" ? 1 : (finished + (current?.progress || 0)) / stages.length;
            const starts = stages.map((item) => item.start).filter(Boolean);
            const ends = stages.map((item) => item.end).filter(Boolean);
            const elapsed = starts.length ? (ACTIVE.has(job.state) ? now : Math.max(...ends, ...starts)) - Math.min(...starts) : null;
            const word = { queued: "Queued", running: current ? current.label : "Running", done: "Done", failed: "Failed", cancelled: "Cancelled" }[job.state] || job.state;
            parts.push(
                h(
                    "div.flow-head",
                    {},
                    h(`span.flow-state.${job.state}`, {}, word),
                    h("span.mono.muted", { title: job.id }, `${job.cell || ""} · ${job.pdk || ""} · ${job.style || ""}`),
                    h("span.grow"),
                    h("span.mono.muted", {}, elapsed === null ? "" : duration(elapsed)),
                ),
                h(`div.progress.${job.state}`, {}, h("div.bar", { style: { width: `${Math.round(100 * fraction)}%` } })),
                h(
                    "div.stage-chips",
                    {},
                    stages.map((item) => {
                        const seconds = item.start ? (item.end || (item.state === "running" ? now : item.start)) - item.start : null;
                        const time = item.state === "running" && item.progress ? `${Math.round(100 * item.progress)} %` : seconds !== null && item.state !== "pending" ? duration(seconds) : "";
                        const mark = item.state === "running" ? h("span.chip-spin") : h("span", { html: glyph(item.state === "done" ? "done" : item.state === "failed" ? "failed" : item.state === "skipped" ? "skipped" : "pending", 11) });
                        return h(`span.stage-chip.${item.state}`, { title: item.message || `${item.label}: ${item.state}` }, mark, item.label, time ? h("span.time", {}, time) : "");
                    }),
                ),
            );
            const message = job.state === "failed" ? job.message || (job.error || "").trim().split("\n").pop() : job.message;
            if (message) parts.push(h(`div.flow-message.${job.state === "failed" ? "bad" : "info"}`, { title: job.error || message }, message));
            if (edited()) parts.push(h("div.flow-message.note", {}, "The netlist has changed since this run."));
        }
        parts.push(this.footer());
        this.body.replaceChildren(...parts);
    }

    // the run history and the run's files; kept while unchanged so an open dropdown survives
    footer() {
        const job = page.job;
        const files = job?.files || {};
        const key = JSON.stringify([page.jobs.map((item) => [item.id, item.state]), job?.id, files.gds, files.log]);
        if (key === this.footerKey && this.footerElement) return this.footerElement;
        this.footerKey = key;
        const options = [
            { value: "", label: page.jobs.length ? `Runs (${page.jobs.length})` : "No runs yet" },
            ...page.jobs.map((item) => ({ value: item.id, label: `${when(item.created)} · ${item.cell} · ${item.pdk} · ${item.style} · ${item.state}${item.seconds ? ` · ${duration(item.seconds)}` : ""}` })),
        ];
        const runs = select(options, job?.id && page.jobs.some((item) => item.id === job.id) ? job.id : "", (value) => {
            if (value) openJob(value, true);
        });
        runs.title = "Open a previous run: its netlist, settings, layout and checks";
        this.footerElement = h(
            "div.flow-footer",
            {},
            h("label.field", {}, h("span", {}, "History"), runs),
            h("span.grow"),
            files.gds && job?.state === "done" ? h("a.icon-btn", { href: `data/${files.gds}`, download: `${job.cell || "layout"}.gds`, title: "Download the GDS" }, h("span", { html: icon("download", 13) }), "GDS") : "",
            // the log in its tab beside Diagnostics, not a page of its own
            files.log ? h("button.icon-btn", { title: "The run's log, in its tab beside Diagnostics", onclick: () => activate("log") }, h("span", { html: glyph("file", 13) }), "Log") : "",
        );
        return this.footerElement;
    }
}

class NetlistPanel {
    constructor(container, initial) {
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.host = h("div.editor-host");
        this.summary = h("span.netlist-summary.mono");
        this.fileInput = h("input", { type: "file", accept: ".sp,.cir,.spice,.cdl,.net,.txt", style: { display: "none" } });
        this.fileInput.addEventListener("change", () => this.openFile());
        this.toolbar.append(
            h("button.icon-btn", { title: "Open a SPICE netlist from disk", onclick: () => this.fileInput.click() }, h("span", { html: glyph("open", 13) }), "Open"),
            h("button.icon-btn", { title: "The example netlist for this PDK", onclick: () => page.examples[page.pdk] && page.editor.setValue(page.examples[page.pdk]) }, h("span", { html: glyph("example", 13) }), "Example"),
            h("span.grow"),
            this.summary,
            this.fileInput,
        );
        // the one editor, made the first time and moved here after: its text, cursor and undo kept
        if (page.editorHost) this.host = page.editorHost;
        this.element.append(this.toolbar, h("div.panel-body.fill", {}, this.host));
        container.element.append(this.element);
        if (!page.editor) {
            page.editorHost = this.host;
            const editor = CodeMirror(this.host, {
                value: initial,
                mode: "spice",
                lineNumbers: true,
                gutters: ["lint", "CodeMirror-linenumbers"],
                indentUnit: 4,
                tabSize: 4,
                indentWithTabs: false,
                lineWrapping: false,
                extraKeys: { "Ctrl-Enter": () => startRun(), "Cmd-Enter": () => startRun() },
            });
            editor.setSize("100%", "100%");
            page.editor = editor;
            editor.on("change", () => {
                store("compile.netlist", editor.getValue());
                scheduleCheck();
                emit("compile", "edit");
            });
        }
        const editor = page.editor;
        this.resizeObserver = new ResizeObserver(() => editor.refresh());
        this.resizeObserver.observe(this.host);
        this.off = [on("compile", () => this.renderSummary())];
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            this.resizeObserver.disconnect();
        });
        container.on("show", () => editor.refresh());
        this.renderSummary();
    }

    renderSummary() {
        const check = page.check;
        const items = check?.diagnostics || [];
        const errors = items.filter((item) => item.severity === "error").length;
        const warnings = items.filter((item) => item.severity === "warning").length;
        this.summary.replaceChildren(
            page.checking ? h("span.muted", {}, "checking…") : "",
            check?.top ? h("span", { title: "The top subcircuit" }, check.top) : "",
            errors ? h("span.bad", {}, `${errors} error${errors > 1 ? "s" : ""}`) : "",
            warnings ? h("span.warn", {}, `${warnings} warning${warnings > 1 ? "s" : ""}`) : "",
            check && !errors && !warnings && !page.checking ? h("span.ok", {}, "no issues") : "",
        );
    }

    async openFile() {
        const file = this.fileInput.files?.[0];
        if (!file) return;
        try {
            page.editor.setValue(await file.text());
        } catch (error) {
            toast(`Open: ${error.message}`);
        }
        this.fileInput.value = "";
    }
}

class DiagnosticsPanel {
    constructor(container) {
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.body = h("div.panel-body.diagnostics");
        this.element.append(this.toolbar, this.body);
        container.element.append(this.element);
        this.cursor = new Map(); // rule and message -> the marker last zoomed to
        this.off = [on("compile", (kind) => kind !== "edit" && this.render())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        this.render();
    }

    // the editor's check for the netlist; the run's own for the rest
    items() {
        const job = page.job;
        return [...(page.check?.diagnostics || []), ...(job?.diagnostics || []).filter((item) => item.source !== "netlist")];
    }

    render() {
        const items = this.items();
        const job = page.job;
        const errors = items.filter((item) => item.severity === "error").length;
        const warnings = items.filter((item) => item.severity === "warning").length;
        this.toolbar.replaceChildren(
            h("span.diag-count.bad", { style: { display: errors ? "" : "none" } }, h("span", { html: glyph("error", 12) }), `${errors}`),
            h("span.diag-count.warn", { style: { display: warnings ? "" : "none" } }, h("span", { html: glyph("warning", 12) }), `${warnings}`),
            h("span.grow"),
            page.checking ? h("span.checking", {}, h("span.chip-spin"), "checking…") : "",
        );
        // no counts to show: no empty bar
        this.toolbar.style.display = errors || warnings || page.checking ? "" : "none";
        const parts = [this.stats(), this.checks()];
        if (job?.state === "failed" && job.error) parts.push(h("pre.diag-error", {}, job.error.trim()));
        for (const [source, title] of Object.entries(SOURCES)) {
            const group = items.filter((item) => item.source === source);
            if (!group.length) continue;
            parts.push(h("div.diag-group", {}, title), ...group.map((item) => this.row(item)));
        }
        if (!items.length && page.check && !(job?.state === "failed" && job.error)) parts.push(h("div.diag-none", {}, h("span", { html: glyph("done", 13) }), page.job?.state === "done" ? "No issues: the netlist, the layout and its checks are clean." : "No issues in the netlist."));
        this.body.replaceChildren(...parts.filter(Boolean));
    }

    // the numbers, by group: the netlist's from the editor's check, the rest from the run
    stats() {
        const stats = [...(page.check?.stats || []).filter((stat) => stat.group === "Netlist"), ...(page.job?.stats || []).filter((stat) => stat.group !== "Netlist")];
        if (!stats.length) return null;
        const groups = [...GROUPS, ...new Set(stats.map((stat) => stat.group).filter((group) => !GROUPS.includes(group)))];
        return h(
            "div.diag-stats",
            {},
            groups.map((group) => {
                const rows = stats.filter((stat) => stat.group === group);
                if (!rows.length) return null;
                return h(
                    "div.stat-group",
                    {},
                    h("div.stat-title", {}, group),
                    rows.map((stat) =>
                        h(
                            "div.stat",
                            { title: stat.label },
                            h("span.label", {}, stat.label),
                            h("span.value", {}, typeof stat.value === "number" ? String(+stat.value.toPrecision(4)) : String(stat.value), stat.unit ? h("span.unit", {}, ` ${stat.unit}`) : ""),
                        ),
                    ),
                );
            }),
        );
    }

    // which engines check the layout, and what they found
    checks() {
        const job = page.job;
        const pdk = pdkInfo(job?.pdk || page.pdk);
        if (!pdk) return null;
        const stage = (key) => (job?.stages || []).find((item) => item.key === key);
        const result = (key, found) => {
            if (found) return found;
            const item = stage(key);
            if (!job) return h("span.muted", {}, "not run");
            if (item?.state === "running") return h("span.muted", {}, "running…");
            if (item?.state === "skipped") return h("span.muted", {}, "skipped");
            if (item?.state === "failed") return h("span.bad", {}, "did not finish");
            return h("span.muted", {}, ACTIVE.has(job.state) ? "pending" : "not run");
        };
        const drc = job?.checks?.drc;
        const lvs = job?.checks?.lvs;
        const precheck = (pdk.drc || []).some((engine) => /precheck/i.test(engine));
        return h(
            "div.diag-checks",
            {},
            h(
                "div",
                {},
                h("b", {}, "DRC"),
                h("span.engine", {}, (drc?.engines || pdk.drc || []).join(" + ") || "none", precheck ? " (precheck, not foundry signoff)" : ""),
                result("drc", drc ? h(drc.clean ? "span.ok" : "span.bad", {}, drc.clean ? "clean" : `${drc.violations} violation${drc.violations === 1 ? "" : "s"}`) : null),
            ),
            h(
                "div",
                {},
                h("b", {}, "LVS"),
                h("span.engine", {}, lvs?.engine || pdk.lvs || "none for this PDK"),
                pdk.lvs || lvs ? result("lvs", lvs ? h(lvs.correct ? "span.ok" : "span.bad", {}, lvs.correct ? "correct" : "incorrect") : null) : "",
            ),
        );
    }

    row(item) {
        const boxes = item.boxes || [];
        const clickable = Boolean(item.line) || boxes.length > 0;
        const key = `${item.source}|${item.rule}|${item.message}`;
        const at = this.cursor.get(key) ?? -1;
        const location = item.line
            ? `line ${item.line}`
            : boxes.length
              ? `${at >= 0 ? `${at + 1}/` : ""}${item.count ?? boxes.length}`
              : item.count
                ? `×${item.count}`
                : "";
        const element = h(
            `div.diag-item.${item.severity}${clickable ? ".goto" : ""}`,
            { title: [item.engine, item.message].filter(Boolean).join(": ") },
            h("span.sev", { html: glyph(item.severity, 12) }),
            h("span.text", {}, item.rule ? h("span.rule", {}, item.rule) : "", item.message),
            h("span.where", {}, location),
        );
        if (item.line) element.addEventListener("click", () => gotoLine(item.line));
        else if (boxes.length) {
            // each click zooms to the next of its markers; every marker of the rule shown
            element.addEventListener("click", () => {
                const next = ((this.cursor.get(key) ?? -1) + 1) % boxes.length;
                this.cursor.set(key, next);
                activate("layout");
                emit("markers", { boxes, focus: boxes[next] });
                element.querySelector(".where").textContent = `${next + 1}/${item.count ?? boxes.length}`;
                this.body.querySelectorAll(".diag-item.on").forEach((other) => other.classList.remove("on"));
                element.classList.add("on");
            });
        }
        return element;
    }
}

// a simple SPICE mode: comments, dot statements, instance names, parameters, SI numbers
function defineMode() {
    CodeMirror.defineSimpleMode("spice", {
        start: [
            { regex: /\*.*/, token: "comment", sol: true },
            { regex: /[$;].*/, token: "comment" },
            { regex: /\.\w+/, token: "keyword", sol: true },
            { regex: /\+/, token: "operator", sol: true },
            { regex: /[Mm]\w*/, token: "variable-2", sol: true },
            { regex: /[Xx]\w*/, token: "variable-3", sol: true },
            { regex: /[A-Za-z]\w*/, token: "def", sol: true },
            { regex: /[A-Za-z_]\w*(?==)/, token: "attribute" },
            { regex: /=/, token: "operator" },
            { regex: /[A-Za-z_][\w<>[\]#!.]*/, token: null },
            { regex: /[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?(?:meg|[afpnumkgt])?(?![\w.])/i, token: "number" },
        ],
    });
}

// the run's log, fetched when its tab is shown and again while the run goes on
class LogPanel {
    constructor(container) {
        this.element = h("div.panel");
        this.listing = h("pre.netlist.log");
        this.emptyNote = h("div.empty", {}, h("span", { html: glyph("file", 28) }), h("strong", {}, "No log"), h("span", {}, "A run writes its log here."));
        this.element.append(h("div.panel-body", {}, this.listing, this.emptyNote));
        container.element.append(this.element);
        this.off = [on("compile", (kind) => kind === "job" && this.refresh())];
        container.on("destroy", () => this.off.forEach((off) => off()));
        container.on("show", () => this.refresh(true));
        this.refresh();
    }

    shown() {
        return this.element.offsetParent !== null;
    }

    async refresh(force = false) {
        const path = page.job?.files?.log;
        this.emptyNote.style.display = path ? "none" : "";
        this.listing.style.display = path ? "" : "none";
        if (!path) return;
        const live = ACTIVE.has(page.job.state);
        // a finished run's log once; a running one's at most every two seconds, while shown
        if (!this.shown() || (!force && page.log?.path === path && (!live || Date.now() - (page.log.at || 0) < 2000))) {
            if (page.log?.path === path) this.listing.textContent = page.log.text;
            return;
        }
        try {
            const response = await fetch(`data/${path}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            page.log = { path, text: await response.text(), at: Date.now() };
            if (page.job?.files?.log !== path) return;
            const atEnd = this.listing.scrollHeight - this.listing.scrollTop - this.listing.clientHeight < 40;
            this.listing.textContent = page.log.text;
            if (atEnd || force) this.listing.scrollTop = this.listing.scrollHeight;
        } catch (error) {
            toast(`The run's log: ${error.message}`);
        }
    }
}

// ---- the view ---------------------------------------------------------------------------------

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = h("script", { src });
        script.addEventListener("load", resolve);
        script.addEventListener("error", () => reject(new Error(`${src} did not load`)));
        document.head.append(script);
    });
}

// once per page: the editor's library, the server's PDKs and examples, the run history
async function setup() {
    const catalog = await api("pdks").catch((error) => {
        throw new Error(`No compiler on this server (${error.message}): restart  python -m flow web.serve  and reload.`);
    });
    if (typeof CodeMirror === "undefined") {
        document.head.append(h("link", { rel: "stylesheet", href: `${CODEMIRROR}/lib/codemirror.css` }));
        try {
            await loadScript(`${CODEMIRROR}/lib/codemirror.min.js`);
            await loadScript(`${CODEMIRROR}/addon/mode/simple.js`);
        } catch (error) {
            throw new Error("The editor did not load: CodeMirror comes from cdn.jsdelivr.net; check the connection and reload.");
        }
    }
    defineMode();
    page.pdks = catalog.pdks || [];
    page.examples = catalog.example || {};
    const names = page.pdks.filter((item) => item.available).map((item) => item.name);
    const saved = recall("compile.pdk", null);
    page.pdk = names.includes(saved) ? saved : names.includes(catalog.default) ? catalog.default : names[0] || page.pdks[0]?.name || null;
    page.style = STYLES.some((item) => item.value === recall("compile.style", null)) ? recall("compile.style", null) : "symmetric";
    page.initialText = recall("compile.netlist", null) ?? page.examples[page.pdk] ?? "";
    refreshJobs();
}

let ready = null;

// the Compiler's panels under host; job: a run to show (the URL's); onJob(id or null): the shown
// run changed. Returns {layout, show(job), destroy()}.
export async function mountCompiler(host, { job, onJob }) {
    page.onJob = onJob;
    const loading = h("div.stage-note", {}, h("div.spinner"), h("span", {}, "Loading the compiler…"));
    host.append(loading);
    try {
        await (ready ??= setup());
    } catch (error) {
        ready = null;
        loading.replaceChildren(h("strong", {}, "No compiler"), h("span", {}, error.message));
        return { show() {}, destroy: () => loading.remove() };
    }
    loading.remove();
    const layout = new Layout(host);
    const panel = (id, title, make) => ({ id, title, make });
    const left = layout.split(
        "column",
        [
            layout.region([panel("flow", "Flow", (container) => new FlowPanel(container))]),
            layout.region([panel("netlist", "Netlist", (container) => new NetlistPanel(container, page.initialText))]),
            layout.region([panel("diagnostics", "Diagnostics", (container) => new DiagnosticsPanel(container)), panel("log", "Log", (container) => new LogPanel(container))]),
        ],
        "compile.left",
        [27, 45, 28],
    );
    const right = layout.split(
        "column",
        [
            layout.region(
                [
                    panel("layout", "Layout", (container) => new LayoutPanel(container)),
                    panel("layout3d", "3D", (container) => new Layout3DPanel(container)),
                    panel("layers", "Layers", (container) => new LayersPanel(container)),
                ],
                "compile.layout",
            ),
            layout.region([panel("schematic", "Schematic", (container) => new SchematicPanel(container, "schematic"))]),
        ],
        "compile.right",
        [62, 38],
    );
    page.view = layout;
    page.mounted = true;
    layout.mount(layout.split("row", [left, right], "compile", [36, 64]));
    shim();
    emit("block", state.block);
    emit("selection");
    emit("compile", "settings");
    emit("compile", "job");
    page.editor?.refresh();
    if (!page.check) runCheck();
    const show = (id) => {
        if (id && id !== page.job?.id) openJob(id, recall("compile.netlist", null) === null);
        else if (page.job?.id) onJob(page.job.id);
    };
    show(job);
    return {
        layout,
        show,
        destroy() {
            page.mounted = false;
            page.view = null;
            emit("markers", { boxes: [] });
            layout.destroy();
        },
    };
}
