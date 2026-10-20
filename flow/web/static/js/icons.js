// 16-pixel stroke icons, drawn in currentColor.

const PATHS = {
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
    fit: '<path d="M2 5.5V2h3.5M14 5.5V2h-3.5M2 10.5V14h3.5M14 10.5V14h-3.5"/><rect x="5" y="5" width="6" height="6" rx=".5"/>',
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
    reset: '<path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9"/><path d="M2.5 2.5v3h3"/>',
    chevron: '<path d="M4 6l4 4 4-4"/>',
    keyboard: '<rect x="1.5" y="4" width="13" height="8" rx="1"/><path d="M4 7h1M7 7h1M10 7h1M5 9.5h6"/>',
    top: '<rect x="3" y="3" width="10" height="10" rx="1"/><path d="M8 6v4M6 8h4"/>',
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
