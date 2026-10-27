// Field names carry their unit as a suffix (``rise_delay_s``, ``supply_current_a``); these turn
// a name into an axis label and pick an SI prefix for the values shown, as the Matplotlib
// figures do (``Delay (ps)``).

// suffix, unit, whether an SI prefix applies; longest first
const SUFFIXES = [
    ["_f_nm_per_um", "F·nm/µm", false],
    ["_f_per_um", "F/µm", true],
    ["_v_per_s", "V/s", true],
    ["_v_s", "V/s", true],
    ["_v_per_v", "V/V", false],
    ["_v_per_c", "V/C", true],
    ["_v_rthz", "V/√Hz", true],
    ["_j_um2", "J·µm²", true],
    ["_db_ohm", "dBΩ", false],
    ["_dbfs", "dBFS", false],
    ["_db", "dB", false],
    ["_deg", "°", false],
    ["_bits", "bit", false],
    ["_lsb", "LSB", false],
    ["_pct", "%", false],
    ["_ohm", "Ω", true],
    ["_hz", "Hz", true],
    ["_um2", "µm²", false],
    ["_um", "µm", false],
    ["_nm", "nm", false],
    ["_electrons", "e⁻", false],
    ["_v", "V", true],
    ["_s", "s", true],
    ["_a", "A", true],
    ["_f", "F", true],
    ["_j", "J", true],
    ["_w", "W", true],
    ["_c", "C", true],
];

const WORDS = {
    vdd: "VDD", vddl: "VDDL", ugbw: "UGBW", gbw: "GBW", psrr: "PSRR", cmrr: "CMRR", thd: "THD",
    sndr: "SNDR", enc: "ENC", tot: "ToT", dc: "DC", iv: "I–V", cm: "CM", inl: "INL", dnl: "DNL",
    rms: "RMS", enob: "ENOB", sfdr: "SFDR", fom: "FoM", vcm: "Vcm", iref: "Iref", vin: "Vin", vout: "Vout", op: "OP", rise: "rise",
    n: "NMOS", p: "PMOS", q: "q",
};

const PREFIXES = { "-18": "a", "-15": "f", "-12": "p", "-9": "n", "-6": "µ", "-3": "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T" };

export function fieldInfo(name) {
    let base = name;
    let unit = "";
    let scalable = false;
    for (const [suffix, label, si] of SUFFIXES) {
        if (name.endsWith(suffix) && name.length > suffix.length) {
            base = name.slice(0, -suffix.length);
            unit = label;
            scalable = si;
            break;
        }
    }
    const words = base.split("_").map((word, index) => {
        // a stimulus in a name: 0p5mv, 100mv, 10ff -> 0.5 mV, 100 mV, 10 fF
        const stimulus = word.match(/^(\d+)(?:p(\d+))?(mv|uv|v|ps|ns|us|ff|pf|ua|ma|mhz|ghz|khz)$/);
        if (stimulus) {
            const units = { mv: "mV", uv: "µV", v: "V", ps: "ps", ns: "ns", us: "µs", ff: "fF", pf: "pF", ua: "µA", ma: "mA", mhz: "MHz", ghz: "GHz", khz: "kHz" };
            return `${stimulus[1]}${stimulus[2] ? `.${stimulus[2]}` : ""} ${units[stimulus[3]]}`;
        }
        const mapped = WORDS[word];
        if (mapped && (index > 0 || mapped !== word)) return mapped;
        return index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word;
    });
    return { name, label: words.join(" "), unit, scalable };
}

// the power of 1000 that brings the largest finite magnitude into [1, 1000)
export function siExponent(values) {
    let largest = 0;
    for (const value of values) {
        if (value !== null && Number.isFinite(value)) largest = Math.max(largest, Math.abs(value));
    }
    if (!largest) return 0;
    const exponent = Math.floor(Math.log10(largest) / 3) * 3;
    return Math.max(-18, Math.min(12, exponent));
}

export function scaledUnit(info, exponent) {
    if (!info.unit) return "";
    if (!info.scalable || !exponent) return info.unit;
    return `${PREFIXES[exponent]}${info.unit}`;
}

export function axisTitle(infos, exponent) {
    const unit = scaledUnit(infos[0], exponent);
    // later labels in lower case, acronyms (PMOS, VDD) kept
    const labels = infos.map((info, index) => (index && !/^[A-Z]{2}/.test(info.label) ? info.label.charAt(0).toLowerCase() + info.label.slice(1) : info.label));
    return unit ? `${labels.join(", ")} (${unit})` : labels.join(", ");
}

export function formatValue(value, info) {
    if (value === null || value === undefined || (typeof value === "number" && !Number.isFinite(value))) return "—";
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (typeof value !== "number") return String(value);
    if (!info || !info.scalable) {
        const text = Math.abs(value) >= 1e5 || (value && Math.abs(value) < 1e-3) ? value.toExponential(3) : +value.toPrecision(4);
        return `${text}${info?.unit ? ` ${info.unit}` : ""}`;
    }
    const exponent = siExponent([value]);
    return `${+(value / 10 ** exponent).toPrecision(4)} ${scaledUnit(info, exponent)}`;
}
