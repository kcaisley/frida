// 16-pixel stroke icons, drawn in currentColor.

const PATHS = {
    compare: '<rect x="1.5" y="2.5" width="5.5" height="11" rx="1"/><rect x="9" y="2.5" width="5.5" height="11" rx="1"/><path d="M3.5 5.5h1.5M3.5 8h1.5M11 5.5h1.5M11 8h1.5"/>',
    chip: '<rect x="4" y="4" width="8" height="8" rx="1"/><path d="M6 1.5v2.5M10 1.5v2.5M6 12v2.5M10 12v2.5M1.5 6H4M1.5 10H4M12 6h2.5M12 10h2.5"/>',
    chart: '<path d="M2 2v12h12"/><path d="M4.5 10.5l3-4 2.5 2.5 3.5-5"/>',
    instances: '<rect x="2" y="2" width="12" height="3.2" rx=".7"/><rect x="2" y="6.4" width="12" height="3.2" rx=".7"/><rect x="2" y="10.8" width="12" height="3.2" rx=".7"/><path d="M4.5 3.6h.01M4.5 8h.01M4.5 12.4h.01"/>',
    wave: '<path d="M1.5 11.5h2.5v-7h3v7h3v-7h4.5"/>',
    table: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M2 6h12M2 9.5h12M6 6v7.5"/>',
    layout: '<rect x="2" y="2" width="12" height="12" rx="1"/><path d="M2 6h5v8M7 9h7M10 2v7"/>',
    cube: '<path d="M8 1.5l5.5 3v7L8 14.5l-5.5-3v-7z"/><path d="M2.5 4.5L8 7.5l5.5-3M8 7.5v7"/>',
    schematic: '<path d="M4 2.5v11L13 8z"/><path d="M1 5.5h3M1 10.5h3M13 8h2.5M5.6 5.5h1.8M5.6 10.5h1.8M6.5 9.6v1.8"/>',
    image: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><circle cx="6" cy="6.5" r="1.3"/><path d="M2.5 12l4-4 3 3 2-2 2.5 2.5"/>',
    layers: '<path d="M8 2l6 3-6 3-6-3z"/><path d="M2 8l6 3 6-3M2 11l6 3 6-3"/>',
    params: '<path d="M2 4h7M12 4h2M2 8h2M7 8h7M2 12h9M14 12h0"/><circle cx="10.5" cy="4" r="1.5"/><circle cx="5.5" cy="8" r="1.5"/><circle cx="12.5" cy="12" r="1.5"/>',
    list: '<path d="M5.5 4h8.5M5.5 8h8.5M5.5 12h8.5"/><circle cx="2.5" cy="4" r=".6"/><circle cx="2.5" cy="8" r=".6"/><circle cx="2.5" cy="12" r=".6"/>',
    // the view fitted to what it shows: a lens over a frame (the four corners are full screen's)
    fit: '<circle cx="6.8" cy="6.8" r="4.8"/><path d="M10.3 10.3L14 14"/><rect x="4.6" y="4.6" width="4.4" height="4.4" rx=".4"/>',
    // a panel over the whole window
    expand: '<path d="M10 2h4v4M14 2l-4.5 4.5M6 14H2v-4M2 14l4.5-4.5"/>',
    shrink: '<path d="M13.5 6.5h-4v-4M9.5 6.5L14 2M2.5 9.5h4v4M6.5 9.5L2 14"/>',
    copy: '<rect x="5" y="5" width="9" height="9" rx="1"/><path d="M11 5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h2"/>',
    ruler: '<path d="M1.5 11.5l10-10 3 3-10 10z"/><path d="M4.5 8.5l1.5 1.5M6.5 6.5l1 1M8.5 4.5l1.5 1.5"/>',
    tag: '<path d="M2 2h5.5L14 8.5 8.5 14 2 7.5z"/><circle cx="5" cy="5" r="1"/>',
    tiles: '<rect x="1.5" y="3" width="5.5" height="10" rx=".5"/><rect x="9" y="3" width="5.5" height="10" rx=".5"/>',
    sun: '<circle cx="8" cy="8" r="3"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1"/>',
    moon: '<path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z"/>',
    eye: '<path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/>',
    eyeOff: '<path d="M2 2l12 12M6.5 3.3A7.5 7.5 0 0 1 8 3c4.5 0 7 5 7 5a12 12 0 0 1-1.9 2.5M10.9 11.9A7 7 0 0 1 8 13c-4.5 0-7-5-7-5a12 12 0 0 1 3-3.4"/>',
    x: '<path d="M4 4l8 8M12 4l-8 8"/>',
    plus: '<path d="M8 3v10M3 8h10"/>',
    download: '<path d="M8 2v8M4.5 6.5L8 10l3.5-3.5M2.5 13.5h11"/>',
    log: '<path d="M2 2v12h12"/><path d="M4 12c1-4.5 3.5-7.5 10-8.5"/><path d="M6 14v-1.3M9.5 14v-1.3M11.5 14v-1.3M12.7 14v-1.3"/>',
    swap: '<path d="M3 5h10M10.5 2.5L13 5l-2.5 2.5M13 11H3M5.5 8.5L3 11l2.5 2.5"/>',
    unpin: '<path d="M6 2h4M7 2v4L4.5 9h7L9 6V2M8 9v5"/><path d="M2.5 2.5l11 11"/>',
    filter: '<path d="M1.5 2.5h13l-5 6v5l-3-1.5V8.5z"/>',
    unfilter: '<path d="M1.5 2.5h11l-4 5v5l-3-1.5V7.5z"/><path d="M11 10.5l3.5 3.5M14.5 10.5L11 14"/>',
    zoom: '<circle cx="7" cy="7" r="4.5"/><path d="M10.3 10.3L14 14"/>',
    pan: '<path d="M8 1.5v13M1.5 8h13M6 3.5l2-2 2 2M6 12.5l2 2 2-2M3.5 6l-2 2 2 2M12.5 6l2 2-2 2"/>',
    reset: '<path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9"/><path d="M2.5 2.5v3h3"/>',
    chevron: '<path d="M4 6l4 4 4-4"/>',
    chevronLeft: '<path d="M10 4L6 8l4 4"/>',
    chevronRight: '<path d="M6 4l4 4-4 4"/>',
    back: '<path d="M13.5 8h-11M6.5 4l-4 4 4 4"/>',
    keyboard: '<rect x="1.5" y="4" width="13" height="8" rx="1"/><path d="M4 7h1M7 7h1M10 7h1M5 9.5h6"/>',
    top: '<rect x="3" y="3" width="10" height="10" rx="1"/><path d="M8 6v4M6 8h4"/>',
    // a layout seen from its side: its layers stacked
    side: '<path d="M2 13h12M3 10.5h10M4.5 8h7M6 5.5h4"/>',
    // a layout seen at an angle: a box on its corner
    iso: '<path d="M8 2l5.5 3.2v6.1L8 14.5l-5.5-3.2V5.2z"/><path d="M8 8.4v6.1M8 8.4l5.5-3.2M8 8.4L2.5 5.2"/>',
    // a link: two rings joined
    link: '<path d="M6.5 9.5l3-3"/><path d="M7.2 4.3l1.3-1.3a2.8 2.8 0 0 1 4 4l-1.3 1.3M8.8 11.7l-1.3 1.3a2.8 2.8 0 0 1-4-4l1.3-1.3"/>',
    // opened elsewhere: a box and an arrow out of it
    open: '<path d="M9 2h5v5M14 2L7.5 8.5"/><path d="M12 9.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3.5"/>',
    edges: '<path d="M2.5 5.5L8 2.5l5.5 3v5l-5.5 3-5.5-3z" stroke-dasharray="2 1.5"/>',
    points: '<circle cx="4" cy="11" r="1.5"/><circle cx="8" cy="6" r="1.5"/><circle cx="12" cy="8" r="1.5"/>',
};

export function icon(name, size = 16) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name] || ""}</svg>`;
}

// a tiny element builder: h("div.class", {attributes}, children...)
export function h(tag, attributes = {}, ...children) {
    const [name, ...classes] = tag.split(".");
    const element = document.createElement(name || "div");
    if (classes.length) element.className = classes.join(" ");
    for (const [key, value] of Object.entries(attributes || {})) {
        if (value === undefined || value === null || value === false) continue;
        if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
        else if (key === "html") element.innerHTML = value;
        else if (key === "style" && typeof value === "object") Object.assign(element.style, value);
        else element.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        element.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return element;
}

export function select(options, value, onChange, attributes = {}) {
    const element = h("select", attributes);
    for (const option of options) {
        const item = h("option", { value: option.value, disabled: option.disabled }, option.label);
        if (option.group) item.label = option.label;
        element.append(item);
    }
    element.value = value;
    element.addEventListener("change", () => onChange(element.value));
    return element;
}

// a dropdown that names itself: each option reads "title: label" (the shown one too), no label beside it
export function titled(title, element) {
    for (const option of element.options) option.textContent = `${title}: ${option.textContent}`;
    element.title ||= title;
    return element;
}

export function seg(options, value, onChange) {
    const element = h("div.seg");
    for (const option of options) {
        const button = h(
            "button",
            { title: option.title, onclick: () => onChange(option.value) },
            option.icon ? h("span", { html: icon(option.icon, 14) }) : option.label,
        );
        if (option.value === value) button.classList.add("on");
        element.append(button);
    }
    return element;
}

// a toolbar's facts about what it draws: its file's size ("GDS 14.3 kB"), what draws it (WebGL,
// CPU) and the memory, read every two seconds while on the page: the page's JavaScript heap where
// the browser tells it (Chromium's performance.memory, "RAM"), else what the view holds (``held``:
// its arrays and buffers, "Data"), else "n/a"
export function sizeMeter({ file = null, label = "file", renderer = null, extra = [], memory: withMemory = true, held = null } = {}) {
    const memory = h("span", {}, "");
    // its items " · " apart (extra: more facts, a file's encoding)
    const items = [file !== null ? `${label} ${file}` : null, ...extra, renderer].filter(Boolean).map((text) => h("span", {}, text));
    if (withMemory) items.push(memory);
    const element = h(
        "span.size-meter.mono",
        { title: "What this view loaded and the page's memory in use (the browser's JavaScript heap, where it tells it)" },
        items.flatMap((item, index) => (index ? [h("span.meter-dot", {}, "·"), item] : [item])),
    );
    if (!withMemory) return element;
    const amount = (value) => {
        const mb = value / 1e6;
        return mb >= 1000 ? `${+(mb / 1000).toPrecision(3)} GB` : mb >= 1 ? `${+mb.toPrecision(3)} MB` : `${+(value / 1e3).toPrecision(3)} kB`;
    };
    const read = () => {
        const used = globalThis.performance?.memory?.usedJSHeapSize;
        const own = typeof used === "number" ? null : held?.();
        memory.textContent = typeof used === "number" ? `RAM ${amount(used)}` : typeof own === "number" && own > 0 ? `Data ${amount(own)}` : "RAM n/a";
        memory.title = typeof used === "number" ? "The page's JavaScript heap in use" : "What this view holds in memory: its geometry and buffers (the browser does not tell its own heap)";
    };
    read();
    const timer = setInterval(() => (element.isConnected ? read() : clearInterval(timer)), 2000);
    return element;
}

// a passing note at the window's bottom right: the pages' errors, as they have no status bar
export function toast(message) {
    const element = h("div.toast", {}, message);
    document.body.append(element);
    setTimeout(() => element.remove(), 8000);
}

// a popover anchored under ``anchor``; closes on an outside click or Escape
export function popover(anchor, build) {
    document.querySelectorAll(".popover").forEach((element) => element.remove());
    const element = h("div.popover");
    build(element);
    document.body.append(element);
    const rect = anchor.getBoundingClientRect();
    const width = element.offsetWidth;
    element.style.left = `${Math.max(4, Math.min(rect.left, window.innerWidth - width - 4))}px`;
    element.style.top = `${rect.bottom + 3}px`;
    const close = (event) => {
        if (event.type === "keydown" ? event.key === "Escape" : !element.contains(event.target) && !anchor.contains(event.target)) {
            element.remove();
            document.removeEventListener("mousedown", close, true);
            document.removeEventListener("keydown", close, true);
        }
    };
    setTimeout(() => {
        document.addEventListener("mousedown", close, true);
        document.addEventListener("keydown", close, true);
    });
    return element;
}
