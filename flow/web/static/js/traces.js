// The traces view, after Surfer's waveform viewer: the focused instance's cached transient runs,
// one row per chosen net on a shared time axis, analog or (threshold at mid-swing) digital. The
// waveform comes from the measurement's HDF5 file through the server (/api/wave), on request.
// Wheel zooms time about the cursor, drag pans, right-drag zooms to a span, double-click fits;
// a click places the cursor, shift-click a second marker for the time between them.

import { h, icon, select } from "./icons.js";
import { COLORS, emit, fetchData, focusSeries, on, series, setFocus, state, status } from "./store.js";
import { fieldInfo, formatValue, scaledUnit, siExponent } from "./units.js";

const ROW = 54; // px per signal row
const AXIS = 26; // px of the time axis
const GUTTER = 200; // px of the names column
const VOLT = { unit: "V", scalable: true };
const AMP = { unit: "A", scalable: true };

const waves = new Map();

function loadWave(path, record) {
    const key = `${path}#${record}`;
    if (!waves.has(key)) {
        waves.set(
            key,
            fetch(`api/wave?path=${encodeURIComponent(path)}&record=${record}`).then((response) => {
                if (!response.ok) throw new Error(`waveform: HTTP ${response.status}`);
                return response.json();
            }),
        );
        waves.get(key).catch(() => waves.delete(key));
    }
    return waves.get(key);
}

// the run's label: its sweep and the bench parameters that tell its points apart
function runLabel(run) {
    const point = Object.entries(run.point || {})
        .map(([name, value]) => {
            const info = fieldInfo(name);
            return `${info.label} ${typeof value === "number" ? formatValue(value, info.unit ? info : null) : value}`;
        })
        .join(", ");
    return `${run.sweep || "run"}${point ? ` · ${point}` : ""}`;
}

function niceStep(span, target) {
    const raw = span / target;
    const power = 10 ** Math.floor(Math.log10(raw));
    for (const step of [1, 2, 5, 10]) if (step * power >= raw) return step * power;
    return 10 * power;
}

// the first index whose time is at least t
function lowerBound(times, t) {
    let low = 0;
    let high = times.length;
    while (low < high) {
        const middle = (low + high) >> 1;
        if (times[middle] < t) low = middle + 1;
        else high = middle;
    }
    return low;
}

function valueAt(times, values, t) {
    const index = lowerBound(times, t);
    if (index <= 0) return values[0];
    if (index >= times.length) return values[times.length - 1];
    const [t0, t1] = [times[index - 1], times[index]];
    const [y0, y1] = [values[index - 1], values[index]];
    if (y0 === null || y1 === null) return null;
    return y0 + ((y1 - y0) * (t - t0)) / (t1 - t0);
}

export class TracesPanel {
    constructor(container, saved) {
        this.config = { run: null, record: 0, signals: null, digital: [], ...(saved || {}) };
        this.view = null; // visible time span [t0, t1]
        this.cursor = null;
        this.marker = null;
        this.hover = null;
        this.element = h("div.panel");
        this.toolbar = h("div.panel-toolbar");
        this.filter = h("input", { type: "search", placeholder: "Filter nets", spellcheck: "false" });
        this.filter.addEventListener("input", () => this.buildSignals());
        this.signalList = h("div.signal-list");
        this.sidebar = h("div.traces-side", {}, h("div.traces-side-head", {}, this.filter), this.signalList);
        this.axisCanvas = h("canvas");
        this.names = h("div.traces-names");
        this.canvas = h("canvas");
        this.scroller = h("div.traces-scroll", {}, h("div.traces-rows", {}, this.names, h("div.traces-canvas", {}, this.canvas)));
        this.rubber = h("div.rubber", { style: { display: "none" } });
        this.emptyNote = h("div.empty", {}, h("span", { html: icon("wave", 28) }), h("strong", {}, "No waveforms"), h("span", {}, ""));
        this.main = h(
            "div.traces-main",
            {},
            h("div.traces-axis", {}, h("div.traces-axis-gutter", {}, "Signal"), h("div.traces-axis-canvas", {}, this.axisCanvas)),
            this.scroller,
            this.rubber,
            this.emptyNote,
        );
        this.element.append(this.toolbar, h("div.panel-body.fill.traces", {}, this.sidebar, this.main));
        container.element.append(this.element);
        container.stateRequestEvent = () => ({ ...this.config });
        this.bindInput();
        this.off = [
            on("block", () => this.refresh()),
            on("selection", () => this.refresh()),
            on("focus", () => this.refresh()),
            on("theme", () => this.draw()),
            on("command", (command) => command === "fit" && this.main.offsetParent !== null && this.fit()),
        ];
        this.resizeObserver = new ResizeObserver(() => this.draw());
        this.resizeObserver.observe(this.main);
        container.on("destroy", () => {
            this.off.forEach((off) => off());
            this.resizeObserver.disconnect();
        });
        this.refresh();
    }

    // the focused series, or where it has no waveforms the first shown series with some
    async refresh() {
        const block = state.block;
        this.index = block ? await fetchData(`${block.name}/traces.json`).catch(() => ({})) : {};
        const runsOf = (item) => this.index?.[item.pdk]?.[item.case] || [];
        const shown = series();
        const focused = focusSeries();
        const focus = focused && !runsOf(focused).length ? shown.find((item) => runsOf(item).length) || focused : focused;
        const runs = focus ? runsOf(focus) : [];
        this.toolbar.replaceChildren();
        if (shown.length > 1) {
            this.toolbar.append(
                h("label.field", {}, h("span", {}, "Series"), select(shown.map((item) => ({ value: item.key, label: `${item.case} · ${item.pdk}${runsOf(item).length ? "" : " (none)"}` })), focus?.key, (value) => setFocus(value))),
            );
        }
        if (!runs.length) {
            this.wave = null;
            this.emptyNote.style.display = "";
            this.emptyNote.lastChild.textContent = !block ? "Select a block." : "No cached transient runs for the selected series.";
            this.signalList.replaceChildren();
            this.names.replaceChildren();
            this.draw();
            return;
        }
        this.emptyNote.style.display = "none";
        if (!runs.some((run) => run.path === this.config.run)) {
            // a run of the same sweep and point in the new series, else its first
            const previous = this.run;
            const same = previous && runs.find((run) => run.sweep === previous.sweep && JSON.stringify(run.point) === JSON.stringify(previous.point));
            this.config.run = (same || runs[0]).path;
            this.config.record = 0;
        }
        this.run = runs.find((run) => run.path === this.config.run);
        const chooser = h("select", { title: "The cached transient run" });
        for (const sweep of [...new Set(runs.map((run) => run.sweep))]) {
            const group = h("optgroup", { label: sweep || "runs" });
            for (const run of runs.filter((item) => item.sweep === sweep)) group.append(h("option", { value: run.path }, runLabel(run)));
            chooser.append(group);
        }
        chooser.value = this.config.run;
        chooser.addEventListener("change", () => {
            this.config.run = chooser.value;
            this.config.record = 0;
            this.refresh();
        });
        this.toolbar.append(h("label.field", {}, h("span", {}, "Run"), chooser));
        if (this.run.records > 1) {
            this.toolbar.append(
                h("label.field", {}, h("span", {}, "Record"), select(Array.from({ length: this.run.records }, (_, index) => ({ value: String(index), label: String(index) })), String(this.config.record), (value) => {
                    this.config.record = Number(value);
                    this.refresh();
                })),
            );
        }
        this.readout = h("span.mono.muted", {}, "");
        this.toolbar.append(h("span.grow"), this.readout, h("button.icon-btn", { title: "Fit (F, double-click)", onclick: () => this.fit(), html: icon("fit", 14) }));
        const key = `${this.run.path}#${this.config.record}`;
        if (key === this.key) {
            this.buildSignals();
            this.draw();
            return;
        }
        status(`Reading ${this.run.path.split("/").slice(-4, -1).join("/")}…`);
        let wave;
        try {
            wave = await loadWave(this.run.path, this.config.record);
        } catch (error) {
            status(`Traces: ${error.message}`, true);
            return;
        }
        if (this.config.run !== wave.path) return;
        this.key = key;
        this.wave = wave;
        this.traces = [
            ...Object.entries(wave.v).map(([name, values]) => ({ name, values, info: VOLT, kind: "v" })),
            ...Object.entries(wave.i).map(([name, values]) => ({ name, values, info: AMP, kind: "i" })),
        ];
        for (const trace of this.traces) {
            let low = Infinity;
            let high = -Infinity;
            for (const value of trace.values) {
                if (value === null) continue;
                low = Math.min(low, value);
                high = Math.max(high, value);
            }
            if (!Number.isFinite(low)) [low, high] = [0, 1];
            if (high - low < 1e-15) [low, high] = [low - 0.5 * (Math.abs(low) || 1), high + 0.5 * (Math.abs(high) || 1)];
            trace.range = [low, high];
        }
        // the chosen nets carry over between runs of one bench; another bench starts with its first
        const names = this.traces.map((trace) => trace.name);
        const nets = names.join(",");
        if (!this.config.signals || nets !== this.config.nets) this.config.signals = names.slice(0, 12);
        this.config.nets = nets;
        status(`${this.run.sweep} run: ${wave.samples} samples${wave.stride > 1 ? `, 1 in ${wave.stride} shown` : ""}`);
        this.fit();
        this.buildSignals();
    }

    shownTraces() {
        return (this.config.signals || []).map((name) => this.traces?.find((trace) => trace.name === name)).filter(Boolean);
    }

    buildSignals() {
        this.signalList.replaceChildren();
        if (!this.traces) return;
        const filter = this.filter.value.trim().toLowerCase();
        for (const [kind, title] of [["v", "Voltages"], ["i", "Supply currents"]]) {
            const group = this.traces.filter((trace) => trace.kind === kind && trace.name.toLowerCase().includes(filter));
            if (!group.length) continue;
            this.signalList.append(h("div.group", {}, title));
            for (const trace of group) {
                const box = h("input", { type: "checkbox" });
                box.checked = this.config.signals.includes(trace.name);
                const row = h("label.signal", { title: `${trace.name}: ${formatValue(trace.range[0], trace.info)} to ${formatValue(trace.range[1], trace.info)}` }, box, h("span.mono", {}, trace.name));
                box.addEventListener("change", () => {
                    this.config.signals = box.checked ? [...this.config.signals, trace.name] : this.config.signals.filter((name) => name !== trace.name);
                    this.buildNames();
                    this.draw();
                });
                this.signalList.append(row);
            }
        }
        this.buildNames();
    }

    buildNames() {
        this.names.replaceChildren();
        this.valueCells = [];
        this.shownTraces().forEach((trace, index) => {
            const color = COLORS[index % COLORS.length];
            const digital = this.config.digital.includes(trace.name);
            const value = h("span.value.mono", {}, "");
            this.valueCells.push(value);
            const toggle = h("button.icon-btn", { title: digital ? "Show as analog" : "Show as digital (threshold at mid-swing)" }, digital ? "D" : "A");
            toggle.addEventListener("click", () => {
                this.config.digital = digital ? this.config.digital.filter((name) => name !== trace.name) : [...this.config.digital, trace.name];
                this.buildNames();
                this.draw();
            });
            const remove = h("button.icon-btn", { title: "Remove", html: icon("x", 12) });
            remove.addEventListener("click", () => {
                this.config.signals = this.config.signals.filter((name) => name !== trace.name);
                this.buildSignals();
                this.draw();
            });
            this.names.append(
                h(
                    "div.trace-name",
                    { style: { height: `${ROW}px`, borderLeftColor: color } },
                    h("div.line", {}, h("span.mono.label", { style: { color } }, trace.name), toggle, remove),
                    h("div.line", {}, value, h("span.range.mono", {}, `${formatValue(trace.range[0], trace.info)} … ${formatValue(trace.range[1], trace.info)}`)),
                ),
            );
        });
        this.updateValues();
    }

    fit() {
        if (!this.wave) return;
        const times = this.wave.time_s;
        this.view = [times[0], times[times.length - 1]];
        this.draw();
    }

    // the waveform column's width (the rows' scroll bar taken off)
    widthOf() {
        return Math.max(10, this.canvas.parentElement.clientWidth || this.main.clientWidth - GUTTER);
    }

    timeAt(px) {
        const [t0, t1] = this.view;
        return t0 + ((t1 - t0) * px) / this.widthOf();
    }

    pxAt(t) {
        const [t0, t1] = this.view;
        return ((t - t0) / (t1 - t0)) * this.widthOf();
    }

    draw() {
        cancelAnimationFrame(this.frame);
        this.frame = requestAnimationFrame(() => this.paint());
    }

    paint() {
        const ratio = window.devicePixelRatio || 1;
        const root = getComputedStyle(document.documentElement);
        const background = root.getPropertyValue("--layout-bg").trim();
        const grid = root.getPropertyValue("--layout-grid").trim();
        const ink = root.getPropertyValue("--fg-secondary").trim();
        const muted = root.getPropertyValue("--fg-muted").trim();
        const width = this.widthOf();
        const traces = this.shownTraces();
        const height = Math.max(traces.length * ROW, this.scroller.clientHeight);
        for (const [canvas, cssHeight] of [[this.axisCanvas, AXIS], [this.canvas, height]]) {
            canvas.width = Math.round(width * ratio);
            canvas.height = Math.round(cssHeight * ratio);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${cssHeight}px`;
        }
        const axis = this.axisCanvas.getContext("2d");
        const ctx = this.canvas.getContext("2d");
        for (const [context, cssHeight] of [[axis, AXIS], [ctx, height]]) {
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            context.fillStyle = background;
            context.fillRect(0, 0, width, cssHeight);
        }
        if (!this.wave || !this.view) return;
        const [t0, t1] = this.view;

        // time axis and grid
        const exponent = siExponent([Math.max(Math.abs(t0), Math.abs(t1))]);
        const unit = scaledUnit({ unit: "s", scalable: true }, exponent);
        const step = niceStep(t1 - t0, Math.max(2, width / 110));
        axis.font = "11px ui-monospace, 'SF Mono', 'DejaVu Sans Mono', monospace";
        axis.fillStyle = ink;
        axis.strokeStyle = muted;
        axis.textBaseline = "middle";
        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
            const x = Math.round(this.pxAt(t)) + 0.5;
            axis.beginPath();
            axis.moveTo(x, AXIS - 6);
            axis.lineTo(x, AXIS);
            axis.stroke();
            axis.fillText(`${+(t / 10 ** exponent).toPrecision(6)} ${unit}`, x + 4, AXIS / 2 - 1);
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }

        // rows
        const times = this.wave.time_s;
        const first = Math.max(0, lowerBound(times, t0) - 1);
        const last = Math.min(times.length - 1, lowerBound(times, t1) + 1);
        traces.forEach((trace, row) => {
            const top = row * ROW;
            const color = COLORS[row % COLORS.length];
            ctx.strokeStyle = grid;
            ctx.beginPath();
            ctx.moveTo(0, top + ROW - 0.5);
            ctx.lineTo(width, top + ROW - 0.5);
            ctx.stroke();
            const [low, high] = trace.range;
            const pad = 7;
            const y = (value) => top + pad + (1 - (value - low) / (high - low)) * (ROW - 2 * pad);
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.4;
            if (this.config.digital.includes(trace.name)) {
                // Surfer's look: a level per state, transitions at mid-swing, the high state filled
                const threshold = (low + high) / 2;
                const level = (value) => (value >= threshold ? top + pad + 4 : top + ROW - pad - 4);
                ctx.beginPath();
                let previous = null;
                const highs = [];
                for (let index = first; index <= last; index++) {
                    const value = trace.values[index];
                    if (value === null) continue;
                    const x = this.pxAt(times[index]);
                    const state = value >= threshold;
                    if (previous === null) ctx.moveTo(x, level(value));
                    else if (state !== previous.state) {
                        ctx.lineTo(x, level(previous.value));
                        ctx.lineTo(x, level(value));
                    }
                    if (state && (!previous || !previous.state)) highs.push([x, null]);
                    if (!state && previous?.state && highs.length) highs[highs.length - 1][1] = x;
                    previous = { state, value };
                }
                if (previous) ctx.lineTo(width, level(previous.value));
                ctx.stroke();
                ctx.fillStyle = color;
                ctx.globalAlpha = 0.16;
                for (const [x0, x1] of highs) ctx.fillRect(x0, top + pad + 4, (x1 ?? width) - x0, ROW - 2 * pad - 8);
                ctx.globalAlpha = 1;
            } else {
                // a column of min and max per pixel where samples are denser than pixels
                ctx.beginPath();
                let column = null;
                let started = false;
                let low = 0;
                let high = 0;
                const flush = () => {
                    if (column === null) return;
                    if (!started) {
                        ctx.moveTo(column, y(low));
                        started = true;
                    } else ctx.lineTo(column, y(low));
                    if (high !== low) ctx.lineTo(column, y(high));
                };
                for (let index = first; index <= last; index++) {
                    const value = trace.values[index];
                    if (value === null) continue;
                    const x = Math.round(this.pxAt(times[index]) * ratio) / ratio;
                    if (x !== column) {
                        flush();
                        column = x;
                        low = high = value;
                    } else {
                        low = Math.min(low, value);
                        high = Math.max(high, value);
                    }
                }
                flush();
                ctx.stroke();
            }
        });

        // marker, cursor and hover line
        for (const [time, color, dash] of [[this.marker, "#88C0D0", [4, 3]], [this.cursor, "#EBCB8B", []], [this.hover, muted, [2, 3]]]) {
            if (time === null || time < t0 || time > t1) continue;
            const x = Math.round(this.pxAt(time)) + 0.5;
            for (const [context, cssHeight] of [[ctx, height], [axis, AXIS]]) {
                context.strokeStyle = color;
                context.lineWidth = 1;
                context.setLineDash(dash);
                context.beginPath();
                context.moveTo(x, 0);
                context.lineTo(x, cssHeight);
                context.stroke();
                context.setLineDash([]);
            }
        }
        this.updateValues();
    }

    // each row's value at the hover position, else at the cursor; the cursor and marker times
    updateValues() {
        if (!this.wave || !this.valueCells) return;
        const time = this.hover ?? this.cursor;
        this.shownTraces().forEach((trace, index) => {
            const cell = this.valueCells[index];
            if (!cell) return;
            if (time === null) {
                cell.textContent = "";
                return;
            }
            const value = valueAt(this.wave.time_s, trace.values, time);
            const digital = this.config.digital.includes(trace.name);
            cell.textContent = digital ? (value >= (trace.range[0] + trace.range[1]) / 2 ? "1" : "0") : formatValue(value, trace.info);
        });
        if (!this.readout) return;
        const seconds = { unit: "s", scalable: true };
        const parts = [];
        if (this.cursor !== null) parts.push(`cursor ${formatValue(this.cursor, seconds)}`);
        if (this.marker !== null) parts.push(`marker ${formatValue(this.marker, seconds)}`);
        if (this.cursor !== null && this.marker !== null) parts.push(`Δt ${formatValue(Math.abs(this.cursor - this.marker), seconds)}`);
        this.readout.textContent = parts.join("   ");
    }

    bindInput() {
        let drag = null;
        const point = (event) => {
            const rect = this.canvas.getBoundingClientRect();
            return [event.clientX - rect.left, event.clientY - rect.top];
        };
        for (const element of [this.canvas, this.axisCanvas]) {
            element.addEventListener("wheel", (event) => {
                if (!this.view || event.shiftKey) return; // shift-wheel scrolls the rows
                event.preventDefault();
                const [px] = point(event);
                const t = this.timeAt(px);
                const factor = Math.exp(event.deltaY * (event.deltaMode ? 0.05 : 0.0015));
                const [t0, t1] = this.view;
                const span = Math.max((t1 - t0) * factor, 1e-15);
                const left = t - ((t - t0) / (t1 - t0)) * span;
                this.view = [left, left + span];
                this.draw();
            }, { passive: false });
            element.addEventListener("mousedown", (event) => {
                if (!this.view) return;
                const [px] = point(event);
                drag = { box: event.button === 2, start: px, view: [...this.view], moved: false, shift: event.shiftKey };
                event.preventDefault();
            });
            element.addEventListener("contextmenu", (event) => event.preventDefault());
            element.addEventListener("dblclick", () => this.fit());
        }
        window.addEventListener("mousemove", (event) => {
            if (!this.view || !this.canvas.isConnected) return;
            const [px] = point(event);
            if (drag) {
                const dx = px - drag.start;
                if (Math.abs(dx) > 3) drag.moved = true;
                if (drag.box) {
                    const rect = this.main.getBoundingClientRect();
                    const canvasRect = this.canvas.getBoundingClientRect();
                    Object.assign(this.rubber.style, {
                        display: "",
                        left: `${canvasRect.left - rect.left + Math.min(px, drag.start)}px`,
                        width: `${Math.abs(dx)}px`,
                        top: "0",
                        height: "100%",
                    });
                } else if (drag.moved) {
                    const shift = ((drag.view[1] - drag.view[0]) * dx) / this.widthOf();
                    this.view = [drag.view[0] - shift, drag.view[1] - shift];
                    this.draw();
                }
                return;
            }
            const inside = event.target === this.canvas || event.target === this.axisCanvas;
            const hover = inside ? this.timeAt(px) : null;
            if (hover !== this.hover) {
                this.hover = hover;
                if (hover !== null) emit("cursor", `t ${formatValue(hover, { unit: "s", scalable: true })}`);
                this.draw();
            }
        });
        window.addEventListener("mouseup", (event) => {
            if (!drag) return;
            const [px] = point(event);
            if (drag.box) {
                this.rubber.style.display = "none";
                if (Math.abs(px - drag.start) > 6) {
                    const a = this.timeAt(Math.min(px, drag.start));
                    const b = this.timeAt(Math.max(px, drag.start));
                    this.view = [a, b];
                    this.draw();
                }
            } else if (!drag.moved) {
                const time = this.timeAt(px);
                if (drag.shift) this.marker = time;
                else this.cursor = time;
                this.draw();
            }
            drag = null;
        });
        this.main.addEventListener("mouseleave", () => {
            this.hover = null;
            this.draw();
        });
    }
}

