// Application state: the catalog, the loaded block and its results, the selection of PDKs and
// cases (their product is the series every panel shows), and a small event bus.

// flow/analysis/plots.py CURVE_COLORS, in order
export const COLORS = [
    "#5E81AC", "#D08770", "#A3BE8C", "#B48EAD", "#EBCB8B",
    "#BF616A", "#88C0D0", "#8FBCBB", "#81A1C1", "#4C566A",
];
export const DASHES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"];
export const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "triangle-down", "x"];

const listeners = new Map();

export function on(event, callback) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(callback);
    return () => listeners.get(event).delete(callback);
}

export function emit(event, payload) {
    for (const callback of listeners.get(event) || []) {
        try {
            callback(payload);
        } catch (error) {
            console.error(error);
            status(`${event}: ${error.message}`, true);
        }
    }
}

export const state = {
    catalog: null,
    block: null,
    results: null,
    pdks: new Set(),
    cases: new Set(),
    hidden: new Set(), // series keys hidden from every panel
    focus: null, // the series key layouts and schematics follow
    excludedPoints: new Set(), // `${dataset}|${series}|${field}|${index}`
    layerVisible: {},
    cursor: "",
};

export function status(message, error = false) {
    emit("status", { message, error });
}

export function store(key, value) {
    try {
        localStorage.setItem(`frida.${key}`, JSON.stringify(value));
    } catch (error) {
        /* private windows have no storage */
    }
}

export function recall(key, fallback) {
    try {
        const value = localStorage.getItem(`frida.${key}`);
        return value === null ? fallback : JSON.parse(value);
    } catch (error) {
        return fallback;
    }
}

const cache = new Map();

export function fetchData(path, kind = "json") {
    const key = `${kind}:${path}`;
    if (!cache.has(key)) {
        cache.set(
            key,
            fetch(`data/${path}`).then((response) => {
                if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
                return kind === "json" ? response.json() : response.text();
            }),
        );
        cache.get(key).catch(() => cache.delete(key));
    }
    return cache.get(key);
}

export async function loadCatalog() {
    state.catalog = await fetchData("catalog.json");
    emit("catalog", state.catalog);
    return state.catalog;
}

export async function loadBlock(name) {
    status(`Loading ${name}…`);
    const [block, results] = await Promise.all([fetchData(`${name}/block.json`), fetchData(`${name}/results.json`)]);
    state.block = block;
    state.results = results;
    // first visit: the first instance, in every PDK
    const saved = recall(`selection.v2.${name}`, null);
    const pdks = blockPdks();
    const cases = Object.keys(block.cases);
    state.pdks = new Set((saved?.pdks || pdks).filter((pdk) => pdks.includes(pdk)));
    state.cases = new Set((saved?.cases || cases.slice(0, 1)).filter((name) => cases.includes(name)));
    if (!state.pdks.size && pdks.length) state.pdks.add(pdks[0]);
    if (!state.cases.size && cases.length) state.cases.add(cases[0]);
    state.hidden = new Set(saved?.hidden || []);
    state.excludedPoints = new Set(saved?.points || []);
    state.focus = saved?.focus || null;
    store("block", name);
    emit("block", block);
    selectionChanged();
    status(`${block.title}: ${cases.length} cases, ${block.datasets.length} result sets, ${block.layouts.length} layouts`);
}

export function blockPdks() {
    const block = state.block;
    if (!block) return [];
    const known = new Set([...block.pdks, ...block.layouts.map((item) => item.pdk)]);
    // catalog order; a study's results across PDKs ("all") last
    return [...state.catalog.pdks.filter((pdk) => known.has(pdk)), ...[...known].filter((pdk) => !state.catalog.pdks.includes(pdk))];
}

export function caseNames() {
    return state.block ? Object.keys(state.block.cases) : [];
}

// every selected PDK and case, PDKs in catalog order, cases in the block's order; colour by case
// when several cases are shown, else by PDK; PDKs then differ by dash and marker
export function series({ includeHidden = false } = {}) {
    if (!state.block) return [];
    const pdks = blockPdks().filter((pdk) => state.pdks.has(pdk));
    const cases = caseNames().filter((name) => state.cases.has(name));
    const byCase = cases.length > 1;
    const out = [];
    for (const name of cases) {
        for (const pdk of pdks) {
            const key = `${pdk}|${name}`;
            const caseIndex = caseNames().indexOf(name);
            const pdkIndex = Math.max(0, blockPdks().indexOf(pdk));
            const color = COLORS[(byCase ? caseIndex : pdkIndex) % COLORS.length];
            const item = {
                key,
                pdk,
                case: name,
                color,
                dash: byCase && pdks.length > 1 ? DASHES[pdkIndex % DASHES.length] : "solid",
                symbol: byCase && pdks.length > 1 ? SYMBOLS[pdkIndex % SYMBOLS.length] : "circle",
                label: pdks.length > 1 && cases.length > 1 ? `${name} · ${pdk}` : cases.length > 1 ? name : pdk,
                hidden: state.hidden.has(key),
            };
            if (includeHidden || !item.hidden) out.push(item);
        }
    }
    return out;
}

export function focusSeries() {
    const all = series();
    return all.find((item) => item.key === state.focus) || all[0] || null;
}

export function selectionChanged() {
    if (state.block) {
        store(`selection.v2.${state.block.name}`, {
            pdks: [...state.pdks],
            cases: [...state.cases],
            hidden: [...state.hidden],
            points: [...state.excludedPoints],
            focus: state.focus,
        });
    }
    emit("selection");
}

export function setFocus(key) {
    state.focus = key;
    selectionChanged();
    emit("focus", key);
}

export function toggle(set, value) {
    if (set.has(value)) set.delete(value);
    else set.add(value);
}
