// The plots' paper, as flow/analysis/plots.py draws it: Computer Modern on white for saved SVGs,
// a plain sans on screen, on white in the light theme and Nord's dark paper in the dark one;
// inward ticks on all four sides and style_grid's grid.

const PT = 4 / 3; // px per point
const FONTS = {
    screen: { family: 'Inter, "Segoe UI", "Helvetica Neue", Arial, "Liberation Sans", "DejaVu Sans", sans-serif', tick: 13, axis: 14, title: 15, legend: 12.5 },
    paper: { family: "CMU Serif, Computer Modern Roman, Latin Modern Roman, DejaVu Serif, serif", tick: 10 * PT, axis: 10 * PT, title: 12 * PT, legend: 8.33 * PT },
};
export const PAPERS = {
    light: { paper: "#fff", ink: "#000", spine: "#4C566A", major: "#D8DEE9", minor: "#E5E9F0", legend: "rgba(236, 239, 244, 0.9)", hover: "#ECEFF4" },
    dark: { paper: "#2E3440", ink: "#ECEFF4", spine: "#8F9BB0", major: "rgba(216, 222, 233, 0.13)", minor: "rgba(216, 222, 233, 0.06)", legend: "rgba(59, 66, 82, 0.92)", hover: "#3B4252" },
};
PAPERS.paper = PAPERS.light;

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
        dtick: log ? 1 : undefined,
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

// mode: "dark" or "light" on screen, "paper" for a saved SVG
export function paperLayout(title, xTitle, yTitle, logX, logY, legendCount, mode = currentTheme()) {
    const colors = PAPERS[mode];
    const fonts = mode === "paper" ? FONTS.paper : FONTS.screen;
    const legend = { bgcolor: colors.legend, bordercolor: colors.spine, borderwidth: 0.8, font: { size: fonts.legend } };
    return {
        paper_bgcolor: colors.paper,
        plot_bgcolor: colors.paper,
        font: { family: fonts.family, size: fonts.tick, color: colors.ink },
        title: { text: title, font: { size: fonts.title }, x: 0.5, xanchor: "center", y: 0.97 },
        margin: { l: 74, r: 22, t: 48, b: 58 },
        xaxis: paperAxis(xTitle, logX, colors, fonts),
        yaxis: paperAxis(yTitle, logY, colors, fonts),
        showlegend: legendCount > 0,
        legend:
            legendCount > 4
                ? { ...legend, x: 1.02, xanchor: "left", y: 1, yanchor: "top" }
                : { ...legend, x: 0.99, xanchor: "right", y: 0.99, yanchor: "top" },
        hovermode: "closest",
        hoverlabel: { bgcolor: colors.hover, bordercolor: colors.spine, font: { family: fonts.family, size: 13, color: colors.ink } },
        dragmode: "zoom",
    };
}
