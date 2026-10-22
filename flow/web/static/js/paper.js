// The plots' paper, as flow/analysis/plots.py draws it: Computer Modern on white for saved SVGs,
// a plain sans on screen, on white in the light theme and the panels' One Dark in the dark one;
// inward ticks on all four sides and style_grid's grid.

const PT = 4 / 3; // px per point
const FONTS = {
    screen: { family: 'Inter, "Segoe UI", "Helvetica Neue", Arial, "Liberation Sans", "DejaVu Sans", sans-serif', tick: 13, axis: 14, title: 15, legend: 12.5 },
    paper: { family: "CMU Serif, Computer Modern Roman, Latin Modern Roman, DejaVu Serif, serif", tick: 10 * PT, axis: 10 * PT, title: 12 * PT, legend: 8.33 * PT },
};
export const PAPERS = {
    light: { paper: "#fff", ink: "#000", spine: "#4C566A", major: "#D8DEE9", minor: "#E5E9F0", legend: "rgba(236, 239, 244, 0.9)", hover: "#ECEFF4" },
    dark: { paper: "#2F343E", ink: "#DCE0E5", spine: "#A9AFBC", major: "rgba(220, 224, 229, 0.13)", minor: "rgba(220, 224, 229, 0.06)", legend: "rgba(59, 65, 77, 0.92)", hover: "#3B414D" },
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
        // a log axis labelled at 1, 2 and 5 of each decade: a narrow range still reads
        dtick: log ? "D2" : undefined,
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

// mode: "dark" or "light" on screen, "paper" for a saved SVG; the legend, where there is one, under
// the plot (plots.py's "outside lower center"), its entries a row that wraps: never over the curves
export function paperLayout(title, xTitle, yTitle, logX, logY, legendCount, mode = currentTheme()) {
    const colors = PAPERS[mode];
    const fonts = mode === "paper" ? FONTS.paper : FONTS.screen;
    return {
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
}
