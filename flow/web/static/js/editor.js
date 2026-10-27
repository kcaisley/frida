// The netlist editor's library, CodeMirror 5 from the CDN (loaded once, when first asked for), and its
// SPICE mode: the Compiler's editor and the netlist panels' read-only listing highlight alike.

import { h } from "./icons.js";

const CODEMIRROR = "https://cdn.jsdelivr.net/npm/codemirror@5.65.18";

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = h("script", { src });
        script.addEventListener("load", resolve);
        script.addEventListener("error", () => reject(new Error(`${src} did not load`)));
        document.head.append(script);
    });
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

let loading = null;

// CodeMirror with the SPICE mode, once; a failed load is tried again on the next call
export function loadEditor() {
    loading ||= (async () => {
        if (typeof CodeMirror === "undefined") {
            document.head.append(h("link", { rel: "stylesheet", href: `${CODEMIRROR}/lib/codemirror.css` }));
            await loadScript(`${CODEMIRROR}/lib/codemirror.min.js`);
            await loadScript(`${CODEMIRROR}/addon/mode/simple.js`);
        }
        defineMode();
    })().catch((error) => {
        loading = null;
        throw error;
    });
    return loading;
}
