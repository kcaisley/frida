// The plots' paper, as flow/analysis/plots.py draws it: Computer Modern on white for saved SVGs,
// a plain sans on screen, on white in the light theme and the panels' One Dark in the dark one;
// inward ticks on all four sides and style_grid's grid.
//
// paperLayout(title, xTitle, yTitle, logX, logY, legendCount, mode = currentTheme(), axes = {})
//   title, xTitle, yTitle: the plot's and its axes' titles; logX, logY: log axes;
//   legendCount: the legend's entries (0: none, under the plot otherwise);
//   mode: "dark" or "light" on screen, "paper" for a saved SVG;
//   axes (optional; without it Plotly ticks the axes itself):
//     traces: the plot's traces as drawn (scaled to their units): their finite x and y values
//       fit each axis's ticks
//     x, y: each axis's kind, a Detail's x_ticks / y_ticks: "integer", "code", "step", "real", or
//       null to infer it (see fitAxis)
//     xLabels, yLabels: the axis's categories by name (a Detail's x_labels), its values their
//       indices 0, 1, 2, ...: then it is ticked at each by its name (labelTicks), its kind unused
//   returns the Plotly layout.
// keepTicks(element): call once after Plotly.newPlot or Plotly.react; refits the ticks paperLayout
//   fitted when the plot is zoomed or panned, and restores them when it is reset.
//
// The ticks (fitAxis): every step a 1, 2 or 5 times a power of ten, counted from 0 (so 0 is a tick
// wherever it is in range), about six on an axis.
// - integer ("integer", "code", or every value whole): whole-number ticks only, plain integers
//   (no exponent or SI prefix), minor ticks on whole numbers too (none between 0 and 1);
// - step ("step", or whole values on an axis titled by a stage, decision or step): every step
//   labelled up to 10 of them, every even one up to 30, the odd ones ticked;
// - log: under 0.8 decades plain linear steps, fully labelled; up to 2.5 decades 1, 2 and 5 of
//   each decade, fully labelled; beyond, the decades (every second or more past 7), plain from
//   0.001 to 10000 and powers of ten otherwise, the digits between them ticked, not labelled;
// - degrees (a "(deg)" or "(°)" title): 15, 30, 45, 90 or 180 degree steps where the range is wide;
// - real: Plotly's own steps;
// - labels (xLabels, yLabels): each category's index, by its name, nothing between; level where the
//   names fit, angled where they would collide (Plotly's automatic angles).

const PT = 4 / 3; // px per point
const FONTS = {
    screen: { family: 'Inter, "Segoe UI", "Helvetica Neue", Arial, "Liberation Sans", "DejaVu Sans", sans-serif', tick: 13, axis: 14, title: 15, legend: 12.5 },
    paper: { family: "CMU Serif, Computer Modern Roman, Latin Modern Roman, DejaVu Serif, serif", tick: 10 * PT, axis: 10 * PT, title: 12 * PT, legend: 8.33 * PT },
};
export const PAPERS = {
    light: { paper: "#fafafa", ink: "#000", spine: "#4C566A", major: "#D8DEE9", minor: "#E5E9F0", legend: "rgba(236, 239, 244, 0.9)", hover: "#ECEFF4" },
    dark: { paper: "#2F343E", ink: "#DCE0E5", spine: "#A9AFBC", major: "rgba(220, 224, 229, 0.13)", minor: "rgba(220, 224, 229, 0.06)", legend: "rgba(59, 65, 77, 0.92)", hover: "#3B414D" },
};
// on screen the panels' colour, a saved figure on white
PAPERS.paper = { ...PAPERS.light, paper: "#fff" };

export function currentTheme() {
    return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

// NORD_DARK, the last curve colour, would vanish on the dark paper
export function tone(color, theme) {
    return theme === "dark" && color.toUpperCase() === "#4C566A" ? "#D8DEE9" : color;
}

export function paperAxis(title, log, colors, fonts) {
    return {
        title: { text: title, font: { size: fonts.axis }, standoff: 6 },
        type: log ? "log" : "linear",
        showline: true,
        linecolor: colors.spine,
        linewidth: 0.8 * PT,
        mirror: "ticks",
        ticks: "inside",
        ticklen: 2.5 * PT,
        tickwidth: 0.8,
        tickcolor: colors.ink,
        tickfont: { size: fonts.tick },
        minor: { ticks: "inside", ticklen: 1.5 * PT, tickcolor: colors.ink, showgrid: true, gridcolor: colors.minor, gridwidth: 0.5 * PT },
        showgrid: true,
        gridcolor: colors.major,
        gridwidth: 0.8 * PT,
        zeroline: false,
        exponentformat: "power",
        automargin: true,
    };
}

// ---- ticks ---------------------------------------------------------------------------------------

// about this many intervals between labelled ticks on an axis
const TARGET = 6;
const KINDS = new Set(["integer", "code", "step", "real"]);
// an axis titled by an index of steps: its whole values are steps
const STEP_TITLE = /\b(stage|decision|step|cycle)s?\b/i;
const DEGREES = /\((deg|°)\)\s*$/;
// an angle's steps and their minor steps
const ANGLE_STEPS = { 15: 5, 30: 10, 45: 15, 90: 30, 180: 45, 360: 90 };
// the layouts paperLayout fitted, with what keepTicks needs to refit them
const FITTED = new WeakMap();

// the smallest 1, 2 or 5 times a power of ten at least `rough`; at least 1 on a whole-number axis
function niceStep(rough, integer = false) {
    if (!(rough > 0) || !Number.isFinite(rough)) return 1;
    const power = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 5, 10].map((m) => m * power).find((value) => value >= rough * (1 - 1e-9));
    return integer ? Math.max(1, Math.round(step)) : step;
}

// a whole-number step's minor step, a whole number dividing it (none under 2)
function integerMinor(step) {
    if (step < 2) return null;
    const mantissa = Math.round(step / 10 ** Math.floor(Math.log10(step) + 1e-9));
    return step / (mantissa === 2 ? (step === 2 ? 2 : 4) : 5);
}

// whole to rounding (2e6 scaled to MHz is 1.9999999999999998), absolutely: 1.2e14 + 0.94 is not
function isWhole(value) {
    return Math.abs(value - Math.round(value)) <= 1e-6;
}

// the smallest and largest of many numbers (a spread of a long code axis would overflow the stack)
function extent(values) {
    let low = Infinity;
    let high = -Infinity;
    for (const value of values) {
        if (value < low) low = value;
        if (value > high) high = value;
    }
    return [low, high];
}

// every finite number of the traces' `key` ("x" or "y"), nested arrays (a heatmap's z) left out
function traceValues(traces, key) {
    const values = [];
    for (const trace of traces || []) {
        for (const value of trace?.[key] || []) {
            if (typeof value === "number" && Number.isFinite(value)) values.push(value);
        }
    }
    return values;
}

// an axis's kind from its hint, its title and its values: "log", "step", "integer", "degrees" or "real"
function axisKind(hint, title, log, values) {
    if (log) return "log";
    const kind = KINDS.has(hint) ? hint : null;
    if (kind === "code") return "integer";
    if (kind) return kind;
    if (DEGREES.test(title || "")) return "degrees";
    // whole values, and not a few tiny ones near 0 (5.7e-11 rounds to 0 as well as 0 does)
    const [low, high] = extent(values);
    const whole = values.length > 0 && values.every(isWhole) && (values.every(Number.isInteger) || high - low >= 1);
    if (!whole) return "real";
    return STEP_TITLE.test(title || "") ? "step" : "integer";
}

function decadeLabel(exponent) {
    return `10<sup>${exponent < 0 ? "−" : ""}${Math.abs(exponent)}</sup>`;
}

// a positive number as a tick label: plain from 0.001 to 99999, a power of ten beyond
function logLabel(value) {
    const exponent = Math.floor(Math.log10(value) + 1e-9);
    if (exponent >= -3 && exponent <= 4) return String(Number(value.toPrecision(6)));
    const mantissa = Number((value / 10 ** exponent).toPrecision(3));
    return mantissa === 1 ? decadeLabel(exponent) : `${mantissa}×${decadeLabel(exponent)}`;
}

// the tick attributes of an axis of `kind` over [low, high] (the data's or the zoomed range, in
// data units), merged over paperAxis's; `minor` its minor ticks' style
function fitAxis(kind, low, high, minor, values = []) {
    if (!Number.isFinite(low) || !Number.isFinite(high)) return {};
    if (low > high) [low, high] = [high, low];
    const span = high - low;
    const noMinor = { ...minor, ticks: "", showgrid: false };
    if (kind === "real") return { tickmode: "auto", minor: { ...minor, tickmode: "auto" } };
    if (kind === "degrees") {
        const rough = span / TARGET;
        if (rough < 7.5) return { tickmode: "auto", minor: { ...minor, tickmode: "auto" } };
        const step = Object.keys(ANGLE_STEPS).map(Number).find((value) => value >= rough);
        if (!step) return { tickmode: "auto", minor: { ...minor, tickmode: "auto" } };
        return { tickmode: "linear", tick0: 0, dtick: step, minor: { ...minor, tickmode: "linear", tick0: 0, dtick: ANGLE_STEPS[step] } };
    }
    if (kind === "integer" || kind === "step") {
        const step = kind === "step" && span <= 10 ? 1 : kind === "step" && span <= 30 ? 2 : niceStep(span / TARGET, true);
        const minorStep = integerMinor(step);
        const whole = values.length > 0 && values.every(isWhole);
        return {
            tickmode: "linear",
            tick0: 0,
            dtick: step,
            tickformat: "d",
            // a whole value hovers whole; a code estimate between codes keeps its fraction
            hoverformat: whole ? "d" : ".7~g",
            minor: minorStep ? { ...minor, tickmode: "linear", tick0: 0, dtick: minorStep } : noMinor,
        };
    }
    // log: the range of positive values, in decades
    if (!(low > 0)) low = high / 10;
    if (!(high > 0)) return {};
    const decades = Math.log10(high) - Math.log10(low);
    if (decades < 0.8) {
        // a narrow range: linear steps, every tick labelled in full
        return { tickmode: "linear", tick0: 0, dtick: `L${niceStep((high - low) / 5)}`, minor: { ...minor, tickmode: "linear", tick0: 0, dtick: "D1" } };
    }
    if (decades <= 2.5) {
        // 1, 2 and 5 of each decade, labelled in full (not in Plotly's small digits)
        const tickvals = [];
        for (let exponent = Math.floor(Math.log10(low)); exponent <= Math.ceil(Math.log10(high)); exponent++) {
            for (const mantissa of [1, 2, 5]) tickvals.push(Number((mantissa * 10 ** exponent).toPrecision(6)));
        }
        return { tickmode: "array", tickvals, ticktext: tickvals.map(logLabel), minor: { ...minor, tickmode: "linear", tick0: 0, dtick: "D1" } };
    }
    // the decades (every second or more past 7), plainly where they all read so (0.001 to 10000),
    // as powers of ten otherwise, in the other labels' size; the digits between them ticked
    const every = decades <= 7 ? 1 : Math.ceil(decades / 7);
    const first = Math.floor(Math.log10(low) + 1e-9);
    const last = Math.ceil(Math.log10(high) - 1e-9);
    const plain = first >= -3 && last <= 4;
    const exponents = [];
    for (let exponent = Math.ceil(first / every) * every; exponent <= last; exponent += every) exponents.push(exponent);
    return {
        tickmode: "array",
        tickvals: exponents.map((exponent) => 10 ** exponent),
        ticktext: exponents.map((exponent) => (plain || exponent === 0 || exponent === 1 ? logLabel(10 ** exponent) : decadeLabel(exponent))),
        minor: every === 1 ? { ...minor, tickmode: "linear", tick0: 0, dtick: "D1" } : { ...minor, tickmode: "linear", tick0: 0, dtick: 1 },
    };
}

// a categories' axis: a tick at each index, labelled by the category's name, nothing between; the
// names level where they fit and angled where they would collide (Plotly's auto angle tries 0, 30
// and 90 degrees); a hovered index reads whole
function labelTicks(labels, minor) {
    return {
        tickmode: "array",
        tickvals: labels.map((_, index) => index),
        ticktext: labels.map(String),
        tickangle: "auto",
        hoverformat: "d",
        minor: { ...minor, ticks: "", showgrid: false },
    };
}

function fitFromValues(kind, values, minor) {
    // a kind without values to fit: whole numbers at least print whole
    if (!values.length) return kind === "integer" || kind === "step" ? { tickformat: "d" } : {};
    const finite = kind === "log" ? values.filter((value) => value > 0) : values;
    if (!finite.length) return {};
    let [low, high] = extent(finite);
    // a constant: Plotly shows it a unit either side
    if (low === high) [low, high] = kind === "log" ? [low / 10, high * 10] : [low - 1, high + 1];
    return fitAxis(kind, low, high, minor, values);
}

// mode: "dark" or "light" on screen, "paper" for a saved SVG; the legend, where there is one, under
// the plot (plots.py's "outside lower center"), its entries a row that wraps: never over the curves
export function paperLayout(title, xTitle, yTitle, logX, logY, legendCount, mode = currentTheme(), axes = {}) {
    const colors = PAPERS[mode];
    const fonts = mode === "paper" ? FONTS.paper : FONTS.screen;
    const layout = {
        paper_bgcolor: colors.paper,
        plot_bgcolor: colors.paper,
        font: { family: fonts.family, size: fonts.tick, color: colors.ink },
        title: { text: title, font: { size: fonts.title }, x: 0.5, xanchor: "center", y: 0.97 },
        margin: { l: 74, r: 22, t: 48, b: 58 },
        xaxis: paperAxis(xTitle, logX, colors, fonts),
        yaxis: paperAxis(yTitle, logY, colors, fonts),
        showlegend: legendCount > 0,
        legend: {
            bgcolor: colors.legend,
            bordercolor: colors.spine,
            borderwidth: 0.8,
            font: { size: fonts.legend },
            orientation: "h",
            x: 0.5,
            xanchor: "center",
            // from the figure's foot: the margin grows to hold it, the axis title stays above
            yref: "container",
            y: 0,
            yanchor: "bottom",
        },
        hovermode: "closest",
        // the whole trace name: where a plot has no legend, the hover is what names a curve
        hoverlabel: { bgcolor: colors.hover, bordercolor: colors.spine, namelength: -1, font: { family: fonts.family, size: 13, color: colors.ink } },
        dragmode: "zoom",
    };
    const traces = axes?.traces;
    if (!traces && !axes?.x && !axes?.y && !axes?.xLabels?.length && !axes?.yLabels?.length) return layout;
    const fitted = {};
    for (const [key, title, log] of [
        ["x", xTitle, logX],
        ["y", yTitle, logY],
    ]) {
        const axis = layout[`${key}axis`];
        const labels = axes[`${key}Labels`];
        if (Array.isArray(labels) && labels.length) {
            Object.assign(axis, labelTicks(labels, axis.minor));
            fitted[key] = { kind: "labels", ticks: { ...axis } };
            continue;
        }
        const values = traceValues(traces, key);
        const kind = axisKind(axes[key], title, log, values);
        Object.assign(axis, fitFromValues(kind, values, axis.minor));
        fitted[key] = { kind, ticks: { ...axis } };
    }
    FITTED.set(layout, fitted);
    return layout;
}

export const TICK_KEYS = ["tickmode", "tick0", "dtick", "tickvals", "ticktext", "tickformat", "hoverformat", "exponentformat", "minor"];

// the ticks paperLayout fitted, refitted to a zoomed or panned range and restored on a reset
export function keepTicks(element) {
    if (!element || element.dataset.paperTicks) return;
    element.dataset.paperTicks = "1";
    element.on?.("plotly_relayout", (event) => {
        const fitted = FITTED.get(element.layout);
        if (!fitted || !event) return;
        const update = {};
        for (const key of ["x", "y"]) {
            const name = `${key}axis`;
            const entry = fitted[key];
            // categories keep their named ticks at any zoom
            if (!entry || entry.kind === "labels") continue;
            let ticks = null;
            if (event[`${name}.autorange`] || event[name]?.autorange) {
                ticks = entry.ticks;
            } else {
                const range = event[`${name}.range`] || (event[`${name}.range[0]`] !== undefined ? [event[`${name}.range[0]`], event[`${name}.range[1]`]] : null);
                if (!range) continue;
                const [low, high] = entry.kind === "log" ? range.map((value) => 10 ** value) : range;
                ticks = { ...fitAxis(entry.kind, low, high, entry.ticks.minor), hoverformat: entry.ticks.hoverformat };
            }
            for (const attribute of TICK_KEYS) update[`${name}.${attribute}`] = ticks[attribute] ?? null;
        }
        if (Object.keys(update).length) Plotly.relayout(element, update);
    });
}
