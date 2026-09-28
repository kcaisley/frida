"""Generate experimental netlistsvg skins with Circuitikz-style symbols.

Run from the FRIDA root with:

    python flow/util/skins/generate_circuitikz_skins.py

The MOS proportions follow integrated-circuits-tikz with its arrows removed
(https://github.com/patrickschulz/integrated-circuits-tikz). The digital glyphs
follow Circuitikz's American logic-port geometry. Digital cell names and pins
follow OpenROAD's openroad_skin.svg
(https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/web/src/openroad_skin.svg).
This file does not require OpenROAD or TeX to regenerate the standalone skins.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = "https://github.com/nturley/netlistsvg"
FONT_PATH = HERE / "latin_modern_mono_subset.woff"


def num(value: float) -> str:
    return f"{value:g}"


def svg_header(*, analog: bool) -> list[str]:
    font_data = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    properties = (
        '<s:properties constants="false" splitsAndJoins="false" genericsLaterals="true">'
        if analog
        else "<s:properties>"
    )
    options = (
        'org.eclipse.elk.direction="DOWN" '
        'org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers="45" '
        'org.eclipse.elk.spacing.nodeNode="45"'
        if analog
        else 'org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers="35" '
        'org.eclipse.elk.spacing.nodeNode="35" '
        'org.eclipse.elk.layered.layering.strategy="LONGEST_PATH"'
    )
    return [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:s="{S}" '
            f'width="{560 if analog else 900}" height="{350 if analog else 820}">'
        ),
        "<!-- Experimental Circuitikz-style netlistsvg skin for FRIDA. -->",
        properties,
        f"  <s:layoutEngine {options}/>",
        '  <s:low_priority_alias val="$dff"/>',
        "</s:properties>",
        "<style>",
        (
            '@font-face { font-family: "FRIDA Latin Modern Mono"; '
            f'src: url("data:font/woff;base64,{font_data}") format("woff"); }}'
        ),
        "svg { stroke: #000; fill: none; stroke-width: 1.1; stroke-linecap: butt; stroke-linejoin: miter; }",
        'text { fill: #000; stroke: none; font: 10px "FRIDA Latin Modern Mono", "Latin Modern Mono", monospace; }',
        ".nodelabel { text-anchor: middle; }",
        ".inputPortLabel { text-anchor: end; }",
        ".gatebubble { fill: white; }",
        ".gate-dot, .splitjoinBody { fill: #000; }",
        "</style>",
    ]


def template(
    kind: str,
    width: float,
    height: float,
    aliases: list[str],
    artwork: list[str],
    ports: list[tuple[str, float, float, str]],
    *,
    x: float,
    y: float,
    label: bool = True,
) -> list[str]:
    lines = [
        (
            f'<g s:type="{escape(kind)}" s:width="{num(width)}" s:height="{num(height)}" '
            f'transform="translate({num(x)},{num(y)})">'
        )
    ]
    lines += [f'  <s:alias val="{escape(alias, quote=True)}"/>' for alias in aliases]
    if label:
        lines.append(
            f'  <text x="{num(width / 2)}" y="-5" class="nodelabel $cell_id" s:attribute="ref">{escape(kind)}</text>'
        )
    lines += [f"  {item}" for item in artwork]
    lines += [
        f'  <g s:x="{num(px)}" s:y="{num(py)}" s:pid="{escape(pid, quote=True)}" s:position="{position}"/>'
        for pid, px, py, position in ports
    ]
    return lines + ["</g>"]


def outline(kind: str, x: float, y: float, width: float, height: float) -> list[str]:
    """Path geometry based on Circuitikz's American logic-port silhouettes."""
    left = x + 3
    right = x + width - 3
    top = y + 1
    bottom = y + height - 1
    middle = (top + bottom) / 2
    if kind == "and":
        shoulder = left + (right - left) * 0.43
        d = (
            f"M{num(left)},{num(top)} H{num(shoulder)} "
            f"C{num(right - 3)},{num(top)} {num(right)},{num(middle - 5)} "
            f"{num(right)},{num(middle)} "
            f"C{num(right)},{num(middle + 5)} {num(right - 3)},{num(bottom)} "
            f"{num(shoulder)},{num(bottom)} H{num(left)} Z"
        )
        return [f'<path d="{d}" class="symbol $cell_id" fill="white"/>']
    if kind in {"or", "xor"}:
        shoulder = left + (right - left) * 0.38
        notch = left + (right - left) * 0.15
        d = (
            f"M{num(left)},{num(top)} "
            f"C{num(shoulder)},{num(top)} {num(right - 6)},{num(top + 3)} "
            f"{num(right)},{num(middle)} "
            f"C{num(right - 6)},{num(bottom - 3)} {num(shoulder)},{num(bottom)} "
            f"{num(left)},{num(bottom)} "
            f"Q{num(notch + 4)},{num(middle)} {num(left)},{num(top)} Z"
        )
        paths = [f'<path d="{d}" class="symbol $cell_id" fill="white"/>']
        if kind == "xor":
            paths.append(
                f'<path d="M{num(left - 3)},{num(top)} '
                f'Q{num(notch + 1)},{num(middle)} {num(left - 3)},{num(bottom)}" '
                'class="symbol $cell_id"/>'
            )
        return paths
    if kind == "buffer":
        d = f"M{num(left)},{num(top)} L{num(right)},{num(middle)} L{num(left)},{num(bottom)} Z"
        return [f'<path d="{d}" class="symbol $cell_id" fill="white"/>']
    raise ValueError(kind)


def logic_gate(
    name: str,
    primitive: str,
    inputs: int,
    inverted: bool,
    aliases: list[str],
    *,
    x: float,
    y: float,
) -> list[str]:
    height = max(30, 12 * inputs)
    body_right = 38
    output_x = 48 if inverted else 44
    center = height / 2
    pins = [height * (index + 1) / (inputs + 1) for index in range(inputs)]
    artwork = [f'<path d="M0,{num(py)} H9" class="connect $cell_id"/>' for py in pins]
    artwork += outline(primitive, 6, 1, 32, height - 2)
    if inverted:
        artwork.append(f'<circle cx="41" cy="{num(center)}" r="3" class="gatebubble $cell_id"/>')
        artwork.append(f'<path d="M44,{num(center)} H48" class="connect $cell_id"/>')
    else:
        artwork.append(f'<path d="M{body_right},{num(center)} H44" class="connect $cell_id"/>')
    return template(
        name,
        output_x,
        height,
        aliases,
        artwork,
        [(chr(65 + index), 0, py, "left") for index, py in enumerate(pins)] + [("Y", output_x, center, "right")],
        x=x,
        y=y,
    )


def compound_gate(name: str, aliases: list[str], *, x: float, y: float) -> list[str]:
    family = name[:3]
    groups = [int(digit) for digit in name[3:]]
    count = sum(groups)
    height = 14 * count + 12
    inputs_y = [12 + 14 * index for index in range(count)]
    group_y = []
    offset = 0
    for size in groups:
        group_y.append(sum(inputs_y[offset : offset + size]) / size)
        offset += size
    final_input_y = [height * (i + 1) / (len(groups) + 1) for i in range(len(groups))]
    first = "and" if family == "aoi" else "or"
    second = "or" if family == "aoi" else "and"
    artwork = []
    offset = 0
    for group_index, size in enumerate(groups):
        group_pins = inputs_y[offset : offset + size]
        if size == 1:
            artwork.append(
                f'<path d="M0,{num(group_pins[0])} H38 '
                f'V{num(final_input_y[group_index])} H49" '
                'class="connect $cell_id"/>'
            )
        else:
            gate_height = max(23, 14 * size + 2)
            gate_top = group_y[group_index] - gate_height / 2
            artwork += outline(first, 8, gate_top, 30, gate_height)
            for py in group_pins:
                artwork.append(f'<path d="M0,{num(py)} H11" class="connect $cell_id"/>')
            artwork.append(
                f'<path d="M35,{num(group_y[group_index])} H43 '
                f'V{num(final_input_y[group_index])} H49" '
                'class="connect $cell_id"/>'
            )
        offset += size
    final_height = max(28, 12 * len(groups))
    artwork += outline(second, 45, height / 2 - final_height / 2, 31, final_height)
    artwork += [
        f'<circle cx="79" cy="{num(height / 2)}" r="3" class="gatebubble $cell_id"/>',
        f'<path d="M82,{num(height / 2)} H88" class="connect $cell_id"/>',
    ]
    ports = [(chr(65 + index), 0, py, "left") for index, py in enumerate(inputs_y)] + [("Y", 88, height / 2, "right")]
    return template(name, 88, height, aliases, artwork, ports, x=x, y=y)


def digital_skin() -> str:
    lines = svg_header(analog=False)
    gates = [
        ("and", "and", 2, False, ["$and", "$logic_and", "$_AND_"]),
        ("nand", "and", 2, True, ["$nand", "$logic_nand", "$_NAND_", "$_ANDNOT_"]),
        ("or", "or", 2, False, ["$or", "$logic_or", "$_OR_"]),
        ("reduce_nor", "or", 2, True, ["$nor", "$reduce_nor", "$_NOR_", "$_ORNOT_"]),
        ("reduce_xor", "xor", 2, False, ["$xor", "$reduce_xor", "$_XOR_"]),
        ("reduce_nxor", "xor", 2, True, ["$xnor", "$reduce_xnor", "$_XNOR_"]),
        ("and3", "and", 3, False, ["and3"]),
        ("nand3", "and", 3, True, ["nand3"]),
        ("or3", "or", 3, False, ["or3"]),
        ("nor3", "or", 3, True, ["nor3"]),
        ("and4", "and", 4, False, ["and4"]),
        ("nand4", "and", 4, True, ["nand4"]),
        ("or4", "or", 4, False, ["or4"]),
        ("nor4", "or", 4, True, ["nor4"]),
    ]
    for index, (name, kind, count, inverted, aliases) in enumerate(gates):
        lines += logic_gate(
            name,
            kind,
            count,
            inverted,
            aliases,
            x=25 + 115 * (index % 7),
            y=40 + 90 * (index // 7),
        )
    for index, kind in enumerate(("buf", "not")):
        inverted = kind == "not"
        width = 42 if inverted else 38
        body = outline("buffer", 5, 1, 28, 28)
        art = ['<path d="M0,15 H8" class="connect $cell_id"/>'] + body
        if inverted:
            art.append('<circle cx="36" cy="15" r="3" class="gatebubble $cell_id"/>')
            art.append('<path d="M39,15 H42" class="connect $cell_id"/>')
        else:
            art.append('<path d="M33,15 H38" class="connect $cell_id"/>')
        aliases = ["$_BUF_"] if kind == "buf" else ["$_NOT_", "$not", "$logic_not"]
        lines += template(
            kind, width, 30, aliases, art, [("A", 0, 15, "left"), ("Y", width, 15, "right")], x=25 + 115 * index, y=235
        )
    lines += template(
        "mux",
        42,
        42,
        ["$pmux", "$mux", "$_MUX_"],
        [
            '<path d="M6,2 L32,10 V32 L6,40 Z" class="symbol $cell_id" fill="white"/>',
            '<path d="M0,12 H8 M0,30 H8 M20,40 V42 M32,21 H42" class="connect $cell_id"/>',
            '<text x="18" y="24" class="nodelabel $cell_id">MUX</text>',
        ],
        [("A", 0, 12, "left"), ("B", 0, 30, "left"), ("S", 20, 42, "bottom"), ("Y", 42, 21, "right")],
        x=255,
        y=235,
    )
    lines += template(
        "dff",
        46,
        44,
        ["$dff", "$_DFF_", "$_DFF_P_"],
        [
            '<rect x="6" y="2" width="32" height="40" class="symbol $cell_id" fill="white"/>',
            '<path d="M0,11 H6 M0,33 H6 M38,11 H46 M6,29 L12,33 L6,37" class="connect $cell_id"/>',
            '<text x="15" y="15">D</text><text x="31" y="15">Q</text>',
        ],
        [("D", 0, 11, "left"), ("CLK", 0, 33, "left"), ("C", 0, 33, "left"), ("Q", 46, 11, "right")],
        x=370,
        y=235,
    )
    compounds = [
        "aoi21",
        "aoi22",
        "aoi211",
        "aoi221",
        "aoi222",
        "aoi33",
        "oai21",
        "oai22",
        "oai211",
        "oai221",
        "oai222",
        "oai33",
    ]
    for index, name in enumerate(compounds):
        lines += compound_gate(name, [name], x=25 + 145 * (index % 6), y=325 + 175 * (index // 6))
    lines += terminal("inputExt", x=25, y=750)
    lines += terminal("outputExt", x=100, y=750)
    lines += template(
        "constant",
        28,
        20,
        ["$_constant_"],
        [
            '<path d="M8,4 H20 V16 H8 Z M20,10 H28" class="symbol $cell_id"/>',
            '<text x="14" y="13" class="nodelabel $cell_id" s:attribute="value">0</text>',
        ],
        [("Y", 28, 10, "right")],
        x=175,
        y=750,
        label=False,
    )
    lines += [
        '<g s:type="split" s:width="6" s:height="40" transform="translate(250,750)">',
        '  <rect width="6" height="40" class="splitjoinBody" s:generic="body"/>',
        '  <s:alias val="$_split_"/>',
        '  <g s:x="0" s:y="20" s:pid="in"/>',
        '  <g transform="translate(6,10)" s:x="6" s:y="10" s:pid="out0"><text x="5" y="-4">hi:lo</text></g>',
        '  <g transform="translate(6,30)" s:x="6" s:y="30" s:pid="out1"><text x="5" y="-4">hi:lo</text></g>',
        "</g>",
        '<g s:type="join" s:width="6" s:height="40" transform="translate(300,750)">',
        '  <rect width="6" height="40" class="splitjoinBody" s:generic="body"/>',
        '  <s:alias val="$_join_"/>',
        '  <g s:x="6" s:y="20" s:pid="out"/>',
        (
            '  <g transform="translate(0,10)" s:x="0" s:y="10" s:pid="in0">'
            '<text x="-3" y="-4" class="inputPortLabel">hi:lo</text></g>'
        ),
        (
            '  <g transform="translate(0,30)" s:x="0" s:y="30" s:pid="in1">'
            '<text x="-3" y="-4" class="inputPortLabel">hi:lo</text></g>'
        ),
        "</g>",
    ]
    lines += dynamic_generic(x=350, y=750)
    return "\n".join(lines + ["</svg>", ""])


def terminal(kind: str, *, x: float, y: float) -> list[str]:
    """A half-size version of the stock netlistsvg terminal trapezoid."""
    incoming = kind == "inputExt"
    art = [
        '<path d="M0,0 H8 L16,4 L8,8 H0 Z" class="symbol $cell_id" fill="white"/>'
        if incoming
        else '<path d="M16,0 H8 L0,4 L8,8 H16 Z" class="symbol $cell_id" fill="white"/>',
        '<text x="8" y="-3" s:attribute="ref" class="nodelabel $cell_id">net</text>',
    ]
    return template(
        kind,
        16,
        8,
        ["$_inputExt_" if incoming else "$_outputExt_"],
        art,
        [("Y" if incoming else "A", 16 if incoming else 0, 4, "right" if incoming else "left")],
        x=x,
        y=y,
        label=False,
    )


def dynamic_generic(*, x: float, y: float) -> list[str]:
    """netlistsvg needs child text nodes when it grows a generic cell."""
    return [
        f'<g s:type="generic" s:width="48" s:height="42" transform="translate({num(x)},{num(y)})">',
        '  <s:alias val="generic-bus"/>',
        '  <text x="24" y="-5" s:attribute="ref" class="nodelabel $cell_id">generic</text>',
        '  <rect x="0" y="0" width="48" height="42" s:generic="body" class="symbol $cell_id" fill="white"/>',
        '  <g transform="translate(48,10)" s:x="48" s:y="10" s:pid="out0"><text x="5" y="-4">out0</text></g>',
        '  <g transform="translate(48,32)" s:x="48" s:y="32" s:pid="out1"><text x="5" y="-4">out1</text></g>',
        (
            '  <g transform="translate(0,10)" s:x="0" s:y="10" s:pid="in0">'
            '<text x="-3" y="-4" class="inputPortLabel">in0</text></g>'
        ),
        (
            '  <g transform="translate(0,32)" s:x="0" s:y="32" s:pid="in1">'
            '<text x="-3" y="-4" class="inputPortLabel">in1</text></g>'
        ),
        "</g>",
    ]


def mos(kind: str, mirror: bool, x: float, y: float) -> list[str]:
    p = kind == "p"
    name = f"mos_{kind}{'_r' if mirror else ''}"
    aliases = [name]
    if not mirror:
        aliases += ["pmos" if p else "nmos"]
    art = [
        '<path d="M0,32 H24 M24,16 V48 M32,16 V48 M32,16 H48 V0 M32,48 H48 V64" class="symbol $cell_id"/>',
    ]
    if p:
        art += ['<circle cx="18" cy="32" r="2.4" class="gate-dot $cell_id"/>']
    if mirror:
        art = [f'<g transform="translate(96,0) scale(-1,1)">{"".join(art)}</g>']
    art += (
        [
            '<text x="56" y="29" s:attribute="ref" class="$cell_id">M1</text>',
            '<text x="56" y="42" s:attribute="value" class="$cell_id">W/L</text>',
        ]
        if not mirror
        else [
            '<text x="0" y="29" s:attribute="ref" class="$cell_id">M1</text>',
            '<text x="0" y="42" s:attribute="value" class="$cell_id">W/L</text>',
        ]
    )
    if mirror:
        ports = [
            ("G", 96, 32, "right"),
            ("D", 48, 0 if not p else 64, "top" if not p else "bottom"),
            ("S", 48, 64 if not p else 0, "bottom" if not p else "top"),
        ]
    else:
        ports = [
            ("G", 0, 32, "left"),
            ("D", 48, 0 if not p else 64, "top" if not p else "bottom"),
            ("S", 48, 64 if not p else 0, "bottom" if not p else "top"),
        ]
    return template(name, 96, 64, aliases, art, ports, x=x, y=y, label=False)


def analog_skin() -> str:
    lines = svg_header(analog=True)
    lines += mos("n", False, 20, 70)
    lines += mos("p", False, 150, 70)
    lines += mos("n", True, 280, 70)
    lines += mos("p", True, 410, 70)
    lines += template(
        "vcc",
        32,
        24,
        ["vcc", "vdd"],
        [
            '<path d="M0,0 H32 M16,0 V24" class="symbol $cell_id"/>',
            '<text x="16" y="-4" s:attribute="name" class="nodelabel $cell_id">VDD</text>',
        ],
        [("A", 16, 24, "bottom")],
        x=20,
        y=185,
        label=False,
    )
    lines += template(
        "vee",
        32,
        24,
        ["vee", "vss"],
        [
            '<path d="M16,0 V24 M0,24 H32" class="symbol $cell_id"/>',
            '<text x="16" y="38" s:attribute="name" class="nodelabel $cell_id">VSS</text>',
        ],
        [("A", 16, 0, "top")],
        x=90,
        y=185,
        label=False,
    )
    lines += template(
        "gnd",
        32,
        24,
        ["gnd", "ground"],
        ['<path d="M16,0 V8 M0,8 H32 M5,16 H27 M10,24 H22" class="symbol $cell_id"/>'],
        [("A", 16, 0, "top")],
        x=160,
        y=185,
        label=False,
    )
    lines += template(
        "voltage_source",
        96,
        64,
        ["v", "vsource"],
        [
            '<circle cx="24" cy="32" r="18" class="symbol $cell_id"/>',
            '<path d="M24,0 V14 M24,50 V64 M19,25 H29 M24,20 V30 M19,41 H29" class="connect $cell_id"/>',
            '<text x="52" y="29" s:attribute="ref" class="$cell_id">V1</text>',
            '<text x="52" y="43" s:attribute="value" class="$cell_id">V</text>',
        ],
        [("+", 24, 0, "top"), ("-", 24, 64, "bottom")],
        x=230,
        y=185,
        label=False,
    )
    lines += template(
        "current_source",
        96,
        64,
        ["i", "isource"],
        [
            '<circle cx="24" cy="32" r="18" class="symbol $cell_id"/>',
            '<path d="M24,0 V14 M24,50 V64 M24,44 V20 M20,26 L24,20 L28,26" class="connect $cell_id"/>',
            '<text x="52" y="29" s:attribute="ref" class="$cell_id">I1</text>',
            '<text x="52" y="43" s:attribute="value" class="$cell_id">A</text>',
        ],
        [("+", 24, 0, "top"), ("-", 24, 64, "bottom")],
        x=320,
        y=185,
        label=False,
    )
    lines += terminal("inputExt", x=20, y=300)
    lines += terminal("outputExt", x=120, y=300)
    lines += dynamic_generic(x=220, y=300)
    return "\n".join(lines + ["</svg>", ""])


def main() -> None:
    for filename, content in (
        ("circuitikz_analog.svg", analog_skin()),
        ("circuitikz_openroad.svg", digital_skin()),
    ):
        path = HERE / filename
        path.write_text(content)
        print(path)


if __name__ == "__main__":
    main()
