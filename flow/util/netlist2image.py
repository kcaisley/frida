"""Transistor-level schematic images of SPICE netlists, laid out by signal flow and symmetry.

    from flow.util.netlist2image import render
    render(Path("NETLIST.sp"), Path("OUT.svg"), "ALIGN.const.json")  # the constraints optional

Stages are channel-connected components in signal-flow order, inputs on the left: devices
joined through drain and source nets form one stage (a StrongARM is one), and each next stage
is gated by the nets of the stages before. Consecutive static CMOS stages (decision inverters,
SR latch, buffers) share one stack; every other stage is a stack of its own (drawn without outlines).

Each stage has its own symmetry axis. With ALIGN's constraints (the ``.const.json`` its
topology step writes: GroupBlocks, SymmetricBlocks and SymmetricNets), its mirror pairs sit at
+-x, the right one drawn mirrored; without them, devices whose names differ in one p/n letter
are paired. PMOS rows are on top, ordered by distance from VDD through drain and source, NMOS
rows below by distance from VSS.

Supplies are local symbols. A port on exactly one gate is a flag beside that gate; a port on
several gates is a label at each; every other net is a horizontal trunk in the channel
between rows, outputs extended to a flag on the right.

Symbols, supplies, port flags and the font come from the netlistsvg analog skin
(``docs/images/netlistsvg/circuitikz_analog.svg``), so these images match the netlistsvg
ones from ``flow/util/hdl2image.py``; netlistsvg's own layout is not used.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from flow.util.mos_models import polarity

SUPPLY = {"vdd": "vdd", "vss": "vss"}
SKIN = Path(__file__).resolve().parents[2] / "docs/images/netlistsvg/circuitikz_analog.svg"
DEV_W, DEV_H, SLOT, STAGE_GAP, SUB_GAP, TRACK = 80, 64, 190, 160, 0, 12
GAP = 4  # half the break in a wire where another net's trunk crosses it
CHAR_W = 5.3  # the skin's 10 px monospace font
_SVG_NS, _SKIN_NS = "http://www.w3.org/2000/svg", "https://github.com/nturley/netlistsvg"


class Skin:
    """Symbol templates of a netlistsvg skin: geometry, pins and size per ``s:type``."""

    def __init__(self, path: Path = SKIN):
        ET.register_namespace("", _SVG_NS)
        ET.register_namespace("s", _SKIN_NS)
        root = ET.parse(path).getroot()
        self.style = ET.tostring(root.find(f"{{{_SVG_NS}}}style"), encoding="unicode")
        self.types = {}
        for g in root.findall(f"{{{_SVG_NS}}}g"):
            kind = g.get(f"{{{_SKIN_NS}}}type")
            if not kind:
                continue
            pins = {
                p.get(f"{{{_SKIN_NS}}}pid"): (float(p.get(f"{{{_SKIN_NS}}}x")), float(p.get(f"{{{_SKIN_NS}}}y")))
                for p in g
                if p.get(f"{{{_SKIN_NS}}}pid")
            }
            body = [c for c in g if not c.get(f"{{{_SKIN_NS}}}pid") and not c.tag.endswith("alias")]
            self.types[kind] = (pins, body)

    def pins(self, kind: str) -> dict[str, tuple[float, float]]:
        return self.types[kind][0]

    def draw(self, kind: str, x: float, y: float, ref: str = "", value: str = "") -> str:
        """The symbol at (x, y), its ``ref``/``value`` text replaced."""
        parts = []
        for element in self.types[kind][1]:
            attribute = element.get(f"{{{_SKIN_NS}}}attribute")
            if attribute in ("ref", "value"):
                text = ref if attribute == "ref" else value
                if not text:
                    continue
                element = ET.fromstring(ET.tostring(element))
                element.text = text
            parts.append(ET.tostring(element, encoding="unicode"))
        body = re.sub(r'\s*xmlns(:\w+)?="[^"]*"', "", "".join(parts))
        body = re.sub(r'\s*s:attribute="[^"]*"', "", body).replace("$cell_id", "")
        return f'<g transform="translate({x:g},{y:g})">{body}</g>'


# ---- netlist --------------------------------------------------------------------------------
def _si(value: str) -> float:
    """A SPICE number with an optional scale suffix (500n, 1.2u, 2)."""
    m = re.fullmatch(r"([-+0-9.eE]+)([a-zA-Z]*)", value)
    scale = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6}
    return float(m[1]) * scale.get(m[2].lower(), 1.0) if m else float("nan")


def parse(path: Path):
    ports, devs = [], {}
    for line in path.read_text().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0].lower() == ".subckt":
            ports = [p.lower() for p in f[2:]]
        elif f[0][0] in "Mm":
            d, g, s, _bulk, model = (x.lower() for x in f[1:6])
            devs[f[0]] = {"d": d, "g": g, "s": s, "pol": polarity(model) or "n", "model": model}
            p = {k.lower(): _si(v) for k, v in (a.split("=", 1) for a in f[6:] if "=" in a)}
            if "w" in p and "l" in p:
                w = p["w"] * p.get("nf", 1) * p.get("m", 1)
                devs[f[0]]["size"] = f"{w * 1e6:.3g}/{p['l'] * 1e6:.3g}"
    return ports, devs


def symmetry(devs, const_path):
    if not const_path:  # no ALIGN constraints: pair devices whose names differ in one p/n letter
        pairs = []
        for a in sorted(devs):
            for b in sorted(devs):
                d = [(x, y) for x, y in zip(a, b) if x != y]
                if (
                    a < b
                    and len(a) == len(b)
                    and len(d) == 1
                    and set(d[0]) == {"p", "n"}
                    and devs[a]["pol"] == devs[b]["pol"]
                ):
                    pairs.append([a, b] if d[0][0] == "n" else [b, a])
        return pairs, [], []
    const = json.loads(Path(const_path).read_text())
    upper = {k.upper(): k for k in devs}
    groups = {
        c["instance_name"]: [upper[i] for i in c["instances"] if i in upper]
        for c in const
        if c["constraint"] == "GroupBlocks"
    }
    members = lambda n: groups.get(n, [upper[n]] if n in upper else [])

    def partner(a, bs):
        for b in bs:
            d = [(x, y) for x, y in zip(a.lower(), b.lower()) if x != y]
            if len(a) == len(b) and len(d) == 1 and set(d[0]) == {"p", "n"}:
                return b

    pairs, axis = [], []
    for c in const:
        if c["constraint"] != "SymmetricBlocks":
            continue
        for e in c["pairs"]:
            if len(e) == 2:
                mb = members(e[1])
                pairs += [[a, partner(a, mb)] for a in members(e[0]) if partner(a, mb)]
            else:
                ms = members(e[0])
                if len(ms) == 2 and devs[ms[0]]["pol"] == devs[ms[1]]["pol"]:
                    pairs.append(sorted(ms))
                else:
                    axis += ms
    nets = [(c["net1"].lower(), c["net2"].lower()) for c in const if c["constraint"] == "SymmetricNets"]
    return pairs, axis, nets


# ---- stages -----------------------------------------------------------------------------------
def groups(devs, stage):
    """Stacks of stages: a stage of static CMOS logic (each device's complement shares its gate,
    pull-up and pull-down meeting at the outputs) joins the static stages next to it; any
    other stage (a preamp, a latch, a StrongARM) is a stack of its own."""
    n = max(stage.values()) + 1

    def static(s):
        mem = [d for name, d in devs.items() if stage[name] == s]
        return all(any(e["pol"] != d["pol"] and e["g"] == d["g"] for e in mem) for d in mem)

    stack, k = {}, -1
    for s in range(n):
        if not (static(s) and s > 0 and static(s - 1)):
            k += 1
        stack[s] = k
    return stack


def stages(ports, devs, sym_nets):
    """Signal-flow stages of channel-connected components (devices joined through drain and
    source nets, the rails excepted): the components gated by the data inputs come first, then
    each step the components gated by nets of the steps before. A StrongARM (latch on the input
    pair's drains) is one component; a double tail's latch, gated by the preamp, the next step."""
    sd = {n: {d["d"], d["s"]} - set(SUPPLY) for n, d in devs.items()}
    comp, k = {}, 0
    for n in devs:  # components by flood fill over shared drain/source nets
        if n in comp:
            continue
        comp[n], todo = k, [n]
        while todo:
            m = todo.pop()
            for o in devs:
                if o not in comp and sd[o] & sd[m]:
                    comp[o] = k
                    todo.append(o)
        k += 1
    nets = {c: {x for n in devs if comp[n] == c for x in sd[n]} for c in range(k)}
    data_in = {n for pair in sym_nets for n in pair if n in ports} or {p for p in ports if p.startswith("in")}
    step = {c: 0 for c in range(k) if any(devs[n]["g"] in data_in for n in devs if comp[n] == c)}
    i = 0
    while len(step) < k:
        driven = {x for c, j in step.items() if j <= i for x in nets[c]}
        nxt = [c for c in range(k) if c not in step and any(devs[n]["g"] in driven for n in devs if comp[n] == c)]
        for c in nxt or [min(set(range(k)) - set(step))]:
            step[c] = i + 1
        i += 1
    order = sorted(set(step.values()))
    return {n: order.index(step[comp[n]]) for n in devs}


def levels(devs, stage):
    """Row of each device within its stage (stages top-aligned): PMOS from the top by distance
    from VDD, NMOS below them by distance from VSS (through the stage's drain/source nets)."""
    row = {}
    for st in set(stage.values()):
        mem = {n: d for n, d in devs.items() if stage[n] == st}

        def dist(rail, pol, mem=mem):
            lvl = {n: 0 for n, d in mem.items() if d["pol"] == pol and rail in (d["d"], d["s"])}
            frontier = list(lvl)
            while frontier:
                nets = {x for n in frontier for x in (mem[n]["d"], mem[n]["s"])} - set(SUPPLY)
                frontier = [n for n, d in mem.items() if d["pol"] == pol and n not in lvl and {d["d"], d["s"]} & nets]
                # from the rounds before alone: devices of one round (a pair on its common source,
                # a latch's input and hold pairs on the clock pair's drains) share a row
                before = dict(lvl)
                for n in frontier:
                    lvl[n] = (
                        max(
                            before[m]
                            for m in before
                            if {mem[m]["d"], mem[m]["s"]} & {mem[n]["d"], mem[n]["s"]} - set(SUPPLY)
                        )
                        + 1
                    )
            return lvl

        up, down = dist("vdd", "p"), dist("vss", "n")
        # a row at least for each polarity the stage has (its PMOS above its NMOS though none is on
        # a rail: a transmission gate's pair)
        p_rows = max(up.values(), default=0) + 1 if any(d["pol"] == "p" for d in mem.values()) else 0
        n_rows = max(down.values(), default=0) + 1
        for n, d in mem.items():
            row[n] = up.get(n, 0) if d["pol"] == "p" else p_rows + (n_rows - 1 - down.get(n, n_rows - 1))
    return row, max(row.values()) + 1


# ---- drawing (netlistsvg analog skin) ------------------------------------------------------
def passes(ports, devs):
    """Turn each device whose drain the netlist puts on its rail (``Mpre vdd gate top vdd pch``)
    so the rail is its source; mark each MOS capacitor (``cap``: its drain and source one net), drawn gate up, drain and
    source joined below (``moscap_n``, ``moscap_p``); and each pass device (``pass``): its drain and
    source both off the rails and one of them a port (a transmission gate's, a sampling switch's),
    drawn on its side (``mos_n_down``, gate down; ``mos_p_up``, gate up), the earlier port of the
    two on the left (``pass`` True: its source)."""
    order = {net: place for place, net in enumerate(ports)}
    for d in devs.values():
        # a MOS is symmetric: its rail drawn where the symbol puts the source (a PMOS's on top, an
        # NMOS's below), whichever end the netlist names it
        if d["d"] == ("vdd" if d["pol"] == "p" else "vss") and d["s"] != d["d"]:
            d["d"], d["s"] = d["s"], d["d"]
        ends = {d["d"], d["s"]}
        if len(ends) == 1:
            d["cap"] = True
        elif not ends & set(SUPPLY) and ends & set(ports):
            d["pass"] = order.get(d["s"], len(ports)) < order.get(d["d"], len(ports))


def mos_kind(dev, mirrored):
    if "cap" in dev:
        return f"moscap_{dev['pol']}"
    if "pass" in dev:
        return f"mos_{dev['pol']}_{'up' if dev['pol'] == 'p' else 'down'}"
    return f"mos_{dev['pol']}{'_r' if mirrored else ''}"


def upright(dev) -> bool:
    """Whether the device stands upright, its gate to its side (not a pass device, not a capacitor,
    whose gates point up or down)."""
    return "pass" not in dev and "cap" not in dev


def pins(skin, dev, x, y, mirrored):
    """Pin coordinates of a device symbol at (x, y) (top left); a pass device's drain and source
    swapped where its source goes on the left."""
    found = {pin: (x + px, y + py) for pin, (px, py) in skin.pins(mos_kind(dev, mirrored)).items()}
    if dev.get("pass"):
        found["D"], found["S"] = found["S"], found["D"]
    return found


def symbol(skin, dev, x, y, mirrored, name, raised=False):
    out = [skin.draw(mos_kind(dev, mirrored), x, y, ref="" if raised else name, value=dev.get("size", ""))]
    if raised:  # clear of the mirrored neighbour's name: above the symbol
        anchor = "end" if mirrored else "start"
        out.append(
            f'<text x="{x + (DEV_W / 2 + 8 if not mirrored else DEV_W / 2 - 8):g}" y="{y + 6:g}" text-anchor="{anchor}">{name}</text>'
        )
    return out


def supply(skin, kind, x, y):
    if kind == "vdd":
        ((px, py),) = skin.pins("vcc").values()
        return [skin.draw("vcc", x - px, y - py)]
    ((px, py),) = skin.pins("gnd").values()
    return [skin.draw("gnd", x - px, y - py)]


def flag(skin, name, x, y, side):
    """A port flag whose pin touches (x, y); the body extends to ``side`` ("left"/"right")."""
    kind = "inputExt" if side == "left" else "outputExt"
    ((px, py),) = skin.pins(kind).values()
    return [skin.draw(kind, x - px, y - py, ref=name)]


def label(name, x, y, side):
    s = -1 if side == "left" else 1
    return [
        f'<path d="M{x},{y} H{x + s * 14}"/>',
        f'<text x="{x + s * 16}" y="{y + 3}" text-anchor="{"end" if s < 0 else "start"}" font-style="italic">{name}</text>',
    ]


GATE_SKIN = SKIN.with_name("style.svg")  # the digital skin: its logic gates in Circuitikz's geometry
ROW, GATE_PITCH, CAP_W = 100, 110, 150


def _subcircuits(text: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """A netlist's subcircuits in order: each one's name, ports and element lines (continuations
    joined, comments and directives dropped)."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        elif raw.strip() and not raw.lstrip().startswith("*"):
            lines.append(raw.strip())
    found, current = [], None
    for line in lines:
        f = line.split()
        if f[0].lower() == ".subckt":
            current = (f[1], f[2:], [])
            found.append(current)
        elif f[0].lower().startswith(".ends"):
            current = None
        elif current is not None and not f[0].startswith("."):
            current[2].append(f)
    return found


def _supply(net: str) -> bool:
    net = net.lower()
    return net in SUPPLY or net.startswith(("vdd", "vss", "gnd", "vcc"))


def _cell(name: str, nets: list[str], ports: list[str], elements: list[list[str]]) -> dict | None:
    """What an instance of a defined subcircuit is drawn as: an inverter (its two transistors share
    their gate and their drain), a capacitor unit (a port ``TOP``: each other plate a capacitor to
    it, ``SHIELD`` on the shield), else None."""
    by_port = dict(zip((port.lower() for port in ports), nets, strict=False))
    mos = [f for f in elements if f[0][0] in "Mm" and len(f) > 5]
    if len(mos) == 2 and len(elements) == 2:
        (d1, g1, s1, _b1, m1), (d2, g2, s2, _b2, m2) = (tuple(x.lower() for x in f[1:6]) for f in mos)
        kinds = {polarity(m1) or "n": s1, polarity(m2) or "n": s2}
        if g1 == g2 and d1 == d2 and set(kinds) == {"n", "p"}:
            net = lambda port: by_port.get(port, port)
            widths = {polarity(f[5].lower()) or "n": _width_um(f) for f in mos}
            fingers = max(int(float(dict(a.split("=", 1) for a in f if "=" in a).get("nf", 1))) for f in mos)
            return {
                "kind": "not",
                "name": name,
                "a": net(g1),
                "y": net(d1),
                "vdd": net(kinds["p"]),
                "vss": net(kinds["n"]),
                "size": f"Wn/Wp {widths['n']:g}/{widths['p']:g}" + (f" ×{fingers}" if fingers > 1 else ""),
            }
    if "top" in by_port:
        # each plate's finger length as its unit states it (a strip's difference plate: diff_length)
        params = {k.lower(): v for f in elements for k, _, v in (a.partition("=") for a in f if "=" in a)}
        lengths = {}
        for port, net in by_port.items():
            value = params.get("diff_length" if port == "diff" else "length")
            lengths[net] = float(value) if value else None
        plates = [by_port[p] for p in by_port if p not in ("top", "shield", "bulk", "b")]
        return {"kind": "cap", "name": name, "plates": plates, "top": by_port["top"],
                "shield": by_port.get("shield"), "lengths": lengths}  # fmt: skip
    return None


def _device(name: str, nets: list[str], model: str, element: list[str]) -> dict | None:
    """A MOM unit called as its style's device (``fmomcap``, ``flow.layout.devices.momcap``): drawn
    as a capacitor unit, as its subcircuit was (``_cell``); None for another model."""
    from flow.layout.devices.momcap.geometry import DEVICES, PINS

    style = next((style for style, device in DEVICES.items() if device == model.lower()), None)
    if style is None:
        return None
    params = dict(a.split("=", 1) for a in element if "=" in a)
    return _cell(
        name, nets, list(PINS[style]), [["Xc0", *PINS[style], model, *(f"{k}={v}" for k, v in params.items())]]
    )


def _width_um(element: list[str]) -> float:
    """A MOS line's total width in um (``w=240n``: 0.24)."""
    value = dict(a.split("=", 1) for a in element if "=" in a)["w"].lower()
    scale = {"n": 1e-3, "u": 1.0, "p": 1e-6}.get(value[-1], None)
    return round(float(value[:-1]) * scale if scale else float(value) * 1e6, 4)


# the NOT gate's triangle in the digital skin (style.svg): its back at x 8, its tip at x 30, 13 above
# and below its axis; a supply stub leaves its slope where it is this far along
_NOT_BACK, _NOT_TIP, _NOT_HALF, _STUB = 8, 30, 13, 14


def _gate_edge(dx: float) -> float:
    """How far above (or below) the NOT gate's axis its triangle's edge is, ``dx`` from its left."""
    return _NOT_HALF * (_NOT_TIP - dx) / (_NOT_TIP - _NOT_BACK)


def _expanded(elements: list[list[str]], defs: dict, net=None, scope: str = "") -> list[list[str]]:
    """``elements`` with each instance of a subcircuit that is not a cell (``_cell``: an inverter, a
    capacitor unit) in its place as its own elements, all the way down (a driver: its chain of
    inverters): its ports the instance's nets, its own nets ``<instance>.<net>``, each instance's
    name its type's letter then ``<instance>.``. An element that is not an instance, at any depth,
    stays as it is (``render_cells`` draws none)."""
    net = net or (lambda name: name)
    found: list[list[str]] = []
    for f in elements:
        plain = [x for x in f[1:] if "=" not in x]
        named = f[0][0] + scope + f[0][1:]
        if f[0][0] not in "Xx" or not plain:
            found.append(f)
            continue
        model, nets = plain[-1], [net(x) for x in plain[:-1]]
        sub = defs.get(model.lower())
        if sub is None or _cell(named, nets, *sub) is not None:
            found.append([named, *nets, model, *(x for x in f[1:] if "=" in x)])
            continue
        ports, inner = sub
        where = dict(zip((port.lower() for port in ports), nets, strict=False))
        inside = f"{scope}{f[0][1:]}."
        found += _expanded(
            inner, defs, lambda name, where=where, inside=inside: where.get(name.lower(), inside + name), inside
        )
    return found


def render_cells(netlist: Path, out: Path) -> bool:
    """A netlist of cells drawn as its signal chains (``out``, SVG) in the Circuitikz skin: each
    chain a row from its input's port flag through its inverters (the digital skin's NOT gate, its
    drive over it, its supplies a vdd symbol above and a ground below) to the capacitors on its last
    net: a stage's parallel pieces one capacitor, ×N, their shield to ground, their top plate a bus
    on the right with its port flag at the top. The top subcircuit's instances of other subcircuits
    (a driver, its chain of inverters) are drawn as what they hold (``_expanded``). False (nothing
    written) where the cells are not inverters and capacitor units."""
    subs = _subcircuits(netlist.read_text())
    if not subs:
        return False
    top_name, _top_ports, top = subs[-1]
    defs = {name.lower(): (ports, elements) for name, ports, elements in subs[:-1]}
    gates, caps = [], []
    for f in _expanded(top, defs):
        if f[0][0] not in "Xx":
            return False
        model = next(x for x in reversed(f[1:]) if "=" not in x)
        nets = [x for x in f[1:] if "=" not in x][:-1]
        if model.lower() in defs:
            found = _cell(f[0], nets, *defs[model.lower()])
        else:  # a first-class device called with its parameters (a MOM unit, fmomcap): its pins' own
            found = _device(f[0], nets, model, f)
        if found is None:
            return False
        found["cell"] = model
        (gates if found["kind"] == "not" else caps).append(found)
    if not caps:
        return False
    # a chain: from a net no gate drives, gate after gate, branching where a net feeds several
    driven = {gate["y"] for gate in gates}
    starts = sorted({gate["a"] for gate in gates if gate["a"] not in driven})
    chains: list[tuple[str, list[dict]]] = []

    def follow(net: str, path: list[dict], start: str) -> None:
        nexts = [gate for gate in gates if gate["a"] == net]
        if not nexts:
            chains.append((start, path))
        for gate in nexts:
            follow(gate["y"], [*path, gate], start)

    for start in starts:
        follow(start, [], start)
    # each chain's capacitors: the branches (a piece's plate) on its last net, by top plate
    rows = []
    for start, path in chains:
        end = path[-1]["y"] if path else start
        branches = [(cap, plate) for cap in caps for plate in cap["plates"] if plate == end]
        for top_net in sorted({cap["top"] for cap, _ in branches}):
            pieces = [{**cap, "length": cap["lengths"].get(end)} for cap, _ in branches if cap["top"] == top_net]
            rows.append((start, path, end, top_net, pieces))
    if not rows:
        return False
    # a column per top plate (a CDAC's two sides beside each other), in the netlist's order
    tops = list(dict.fromkeys(cap["top"] for cap in caps))
    # a stage's chains together (its input's), the longest first: a strip's main, then its difference
    rows.sort(key=lambda row: (tops.index(row[3]), _natural(row[0]), -len(row[1]), _natural(row[2])))

    skin, gate_skin = Skin(SKIN), Skin(GATE_SKIN)
    depth = max(len(path) for _s, path, *_ in rows)
    x_in = 20 + 8 * max(len(row[0]) for row in rows)
    # a gate's pitch: its drive's label (over it, from 20 in) clear of the next gate's, 7 a character
    pitch = max(GATE_PITCH, 30 + 7 * max(len(gate["size"]) for _s, path, *_ in rows for gate in path or [{"size": ""}]))
    x_cap = x_in + 40 + 30 + depth * pitch + 40
    x_bus = x_cap + CAP_W
    column = x_bus + 120 + 8 * max(len(top) for top in tops)
    svg: list[str] = []
    buses: dict[str, list[float]] = defaultdict(list)
    bottom = 0.0
    for start, path, end, top_net, pieces in rows:
        dx = tops.index(top_net) * column
        y = 60.0 + ROW * len(buses[top_net])
        svg.append(f'<g transform="translate({dx:g},0)">')
        svg.append(skin.draw("inputExt", x_in, y - 4, ref=start))
        x = x_in + 40
        for k, gate in enumerate(path):
            gx = x_in + 70 + k * pitch
            svg.append(f'<path d="M{x:g},{y:g} H{gx:g}"/>')
            svg.append(gate_skin.draw("not", gx, y - 15))
            svg.append(f'<text x="{gx + 20:g}" y="{y - 18:g}">{gate["size"]}</text>')
            # its supplies: a stub from the triangle's edge up to vdd, one down to ground
            edge, sx = _gate_edge(_STUB), gx + _STUB
            svg.append(f'<path d="M{sx:g},{y - edge:g} V{y - 30:g}"/>')
            svg += supply(skin, "vdd", sx, y - 30)
            svg.append(f'<text x="{sx + 12:g}" y="{y - 36:g}">{gate["vdd"]}</text>')
            svg.append(f'<path d="M{sx:g},{y + edge:g} V{y + 30:g}"/>')
            svg += supply(skin, "vss", sx, y + 30)
            x = gx + 42
        # the stage's net to its capacitor: its name over the wire
        svg.append(f'<path d="M{x:g},{y:g} H{x_cap:g}"/>')
        svg.append(f'<text x="{(x + x_cap) / 2:g}" y="{y - 5:g}" class="nodelabel">{end}</text>')
        svg.append(_capacitor(x_cap, y, pieces))
        svg.append(f'<path d="M{x_cap + 26:g},{y:g} H{x_bus:g}"/>')
        svg.append(f'<circle cx="{x_bus:g}" cy="{y:g}" r="2.5" class="splitjoinBody"/>')
        svg.append("</g>")
        buses[top_net].append(y)
    for top_net, ys in buses.items():
        # the bus's port flag at its top, over the first row
        dx, y_flag = tops.index(top_net) * column, ys[0] - 40
        svg.append(f'<path d="M{dx + x_bus + 20:g},{y_flag:g} H{dx + x_bus:g} V{ys[-1]:g}"/>')
        svg.append(skin.draw("outputExt", dx + x_bus + 20, y_flag - 4, ref=top_net))
        bottom = max(bottom, ys[-1] + 50)
    width, height = column * len(tops), bottom + 30
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}">'
        f'{skin.style}<rect width="100%" height="100%" fill="white" stroke="none"/>'
        f'<text x="20" y="24">{top_name}</text>' + "".join(svg) + "</svg>"
    )
    return True


def _natural(text: str) -> list:
    """``main_p_10`` after ``main_p_9``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def _capacitor(x: float, y: float, pieces: list[dict]) -> str:
    """A capacitor at (x, y) from its plate's lead to its top plate's (26 wide): ×N for a stage's
    parallel pieces, their length under it, their shield to ground."""
    lengths = sorted({piece["length"] for piece in pieces if piece["length"]})
    size = " + ".join(f"{length / 1000:g}" for length in lengths) + " µm" if lengths else ""
    count = f"×{len(pieces)}" if len(pieces) > 1 else pieces[0]["name"]
    parts = [
        f'<path d="M{x:g},{y:g} H{x + 10:g} M{x + 10:g},{y - 10:g} V{y + 10:g} M{x + 16:g},{y - 10:g} V{y + 10:g} M{x + 16:g},{y:g} H{x + 26:g}"/>',
        f'<text x="{x + 13:g}" y="{y - 15:g}" class="nodelabel">{count}</text>',
    ]
    if size:
        parts.append(f'<text x="{x + 34:g}" y="{y + 16:g}">{size}</text>')
    if any(piece["shield"] for piece in pieces):
        # the shield under the plates, to ground
        parts.append(
            f'<path d="M{x + 6:g},{y + 14:g} H{x + 20:g} M{x + 13:g},{y + 14:g} V{y + 22:g}" stroke-dasharray="2 2"/>'
        )
        parts += supply(Skin(SKIN), "vss", x + 13, y + 22)
    return "".join(parts)


def _render_boxes(netlist: Path, out: Path) -> None:
    """A netlist of library cells and capacitors drawn as chains (``out``, SVG): each chain a row
    from its first cell's input to its capacitor, a cell a box of its name over its library cell, a
    capacitor its value, every net shared with another row (a top plate, a supply) a label."""
    cells = []  # (name, nets, kind): a cell's pins in its order, a capacitor's two plates
    for line in netlist.read_text().splitlines():
        f = line.split()
        if not f or f[0].startswith((".", "*", "+")):
            continue
        if f[0][0] in "cC" or "@c" in f[0].lower():
            cells.append((f[0], [n.lower() for n in f[1:3]], f[3] if len(f) > 3 else "C"))
        elif len(f) > 2 and "=" not in line:  # a cell instance (named as it was, x-prefixed or not)
            cells.append((f[0], [n.lower() for n in f[1:-1]], f[-1]))
    signal = lambda nets: [n for n in nets if n.lower() not in SUPPLY and not n.startswith(("vdd", "vss"))]
    # a chain: cells joined through nets only they share (a cell's input its first signal pin, its output its second)
    users: dict[str, list[int]] = defaultdict(list)
    for k, (_n, nets, _kind) in enumerate(cells):
        for net in set(signal(nets)):
            users[net].append(k)
    group = list(range(len(cells)))
    find = lambda k: k if group[k] == k else find(group[k])
    for net, ks in users.items():
        if len(ks) <= 6:  # a top plate or a bus is a label, not a link
            for k in ks[1:]:
                group[find(k)] = find(ks[0])
    rows: dict[int, list[int]] = defaultdict(list)
    for k in range(len(cells)):
        rows[find(k)].append(k)
    box_w, box_h, gap, row_h = 120, 34, 30, 60
    width = 40 + max(len(ks) for ks in rows.values()) * (box_w + gap) + 120
    height = 40 + len(rows) * row_h
    svg = []
    for r, ks in enumerate(rows.values()):
        y = 30 + r * row_h
        shared = sorted({n for k in ks for n in signal(cells[k][1]) if len(users[n]) > 6})
        for c, k in enumerate(ks):
            name, nets, kind = cells[k]
            x = 20 + c * (box_w + gap)
            if c:
                svg.append(f'<path d="M{x - gap},{y + box_h / 2} H{x}" stroke="#000"/>')
            svg.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="#fff" stroke="#000"/>')
            svg.append(
                f'<text x="{x + box_w / 2}" y="{y + 14}" text-anchor="middle" font-size="10">{name.split("@")[-1] if name.lower().startswith("cap@") else name.split("@")[0]}</text>'
            )
            svg.append(
                f'<text x="{x + box_w / 2}" y="{y + 27}" text-anchor="middle" font-size="10" fill="#555">{kind}</text>'
            )
        if shared:
            x = 20 + len(ks) * (box_w + gap)
            svg.append(
                f'<text x="{x}" y="{y + box_h / 2 + 4}" font-size="10" fill="#1f5fa8">{", ".join(shared)}</text>'
            )
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="sans-serif">' + "".join(svg).replace("<text", '<text fill="#000"', 0) + "</svg>"
    )


def render(netlist: Path, out: Path, const_path=None, skin_path: Path = SKIN) -> dict[int, list[str]]:
    """Draw ``netlist`` into ``out`` (SVG), by ALIGN's constraints (``const_path``, a
    ``.const.json``) where given; the stacks drawn, each its devices."""
    skin = Skin(skin_path)
    # a block of cells (its top subcircuit holds no transistor: a CDAC, its drivers and capacitors):
    # its signal chains, or plain boxes where its cells are not inverters and capacitor units
    subs = _subcircuits(netlist.read_text())
    if subs and not any(f[0][0] in "Mm" for f in subs[-1][2]):
        if not render_cells(netlist, out):
            _render_boxes(netlist, out)
        return {}
    ports, devs = parse(netlist)
    if not devs:  # cells and capacitors alone, outside a subcircuit: their chains
        _render_boxes(netlist, out)
        return {}
    passes(ports, devs)
    pairs, axis, sym_nets = symmetry(devs, const_path)
    stage = stages(ports, devs, sym_nets)
    row, nrows = levels(devs, stage)
    mirrored = {b for _, b in pairs}
    # x within each stage: pairs at +-k slots about the stage axis, axis devices on it, others after
    nstage = max(stage.values()) + 1
    slot = {}
    for s in range(nstage):
        mem = [n for n in devs if stage[n] == s]
        used = defaultdict(set)  # row -> used slots
        # a pass device without its complement (a transmission gate's other half) takes a column of
        # its own, after the others: another's wires through its column would read as its pins'
        lone = {
            n
            for n in mem
            if "pass" in devs[n]
            and not any(
                m != n
                and "pass" in devs[m]
                and devs[m]["pol"] != devs[n]["pol"]
                and {devs[m]["d"], devs[m]["s"]} == {devs[n]["d"], devs[n]["s"]}
                for m in mem
            )
        }
        on_axis = [n for n in mem if n in axis or not any(n in p for p in pairs)]
        for n in sorted(on_axis, key=lambda n: n in lone):
            taken = set().union(*used.values()) if n in lone else used[row[n]]
            k = 0
            while k in taken:
                k = -k + (1 if k <= 0 else 0)  # 0, 1, -1, 2, -2 ...
            slot[n] = k
            used[row[n]].add(k)
        for a, b in pairs:
            if a in mem and b in mem:
                r = row[a] = row[b] = min(row[a], row[b])
                k = 1
                while k in used[r] or -k in used[r]:
                    k += 1
                slot[a], slot[b] = -k, k
                used[r] |= {k, -k}
    # stage widths and offsets
    span = {s: max([abs(slot[n]) for n in devs if stage[n] == s] + [0]) for s in range(nstage)}
    stack = groups(devs, stage)
    offset, x, box = {}, 80, defaultdict(lambda: [1e9, -1e9])
    for s in range(nstage):
        box[stack[s]][0] = min(box[stack[s]][0], x)
        x += span[s] * SLOT + 60
        offset[s] = x
        x += span[s] * SLOT + 60
        box[stack[s]][1] = x
        x += SUB_GAP if s + 1 < nstage and stack[s + 1] == stack[s] else STAGE_GAP
    width = x
    pos = {}
    for n, d in devs.items():
        pos[n] = (offset[stage[n]] + slot[n] * SLOT - DEV_W // 2, row[n])
    # channels between rows: assign later; first count tracks
    gate_only = {
        p for p in ports if p not in SUPPLY and all(d["g"] == p for d in devs.values() if p in (d["d"], d["g"], d["s"]))
    }
    fanout = {p: sum(1 for d in devs.values() if d["g"] == p) for p in ports}
    as_label = {p for p in gate_only if fanout[p] > 1}
    beside = {p for p in gate_only if fanout[p] == 1}

    # row y positions: channels sized by their tracks (two passes: provisional, then final)
    def place_rows(chan_tracks):
        ys, y = [], 60
        for r in range(nrows):
            y += (len(chan_tracks.get(r, [])) + 2) * TRACK + 30  # channel above row r
            ys.append(y)
            y += DEV_H
        return ys, y + (len(chan_tracks.get(nrows, [])) + 2) * TRACK + 60

    def crosses(p, ch, ys):
        bottom = p[3] > ys[p[4]] + DEV_H / 2
        return ch <= p[4] if bottom else ch > p[4]

    def jog_x(p):
        """A column beside the device, past its name on the side away from the gate (staggered by
        row, so jogs out of one column keep apart)."""
        text = len(p[0]) * CHAR_W + 14 + 8 * (p[4] % 3)
        return round(p[2] - text) if p[0] in mirrored else round(p[2] + text)

    def blocked(p, ch):
        """Whether the straight wire from a drain or source to channel ``ch`` passes another device
        of its column: it would read as joined to that device's pins."""
        bottom = p[3] > ys[p[4]] + DEV_H / 2 if ys else False
        passed = range(p[4] + 1, ch) if bottom else range(ch, p[4])
        return any(m != p[0] and pos[m][0] == pos[p[0]][0] and row[m] in passed for m in devs)

    forced = set()  # (net, device, pin): drains and sources jogged off another net's wire

    def route(ys):
        all_pins = defaultdict(list)
        for n, d in devs.items():
            px, r = pos[n]
            for pin, (x, y) in pins(skin, d, px, ys[r], n in mirrored).items():
                all_pins[d[pin.lower()]].append((n, pin, x, y, r))
        chans = defaultdict(list)  # channel index (above row r) -> [(net, x0, x1)]
        plan = {}
        for net, ps in all_pins.items():
            if net in SUPPLY or net in as_label or net in beside or len(ps) < 2 and net not in ports:
                continue
            # the channel nearest the pins' median edge
            edges = sorted(p[4] + (1 if (p[3] > ys[p[4]] + DEV_H / 2) else 0) for p in ps)
            ch = edges[len(edges) // 2]
            # gate jogs staggered by row, so stacked devices in one column keep separate verticals
            # (a pass device's gate points up or down: no jog)
            xs = [
                p[2]
                + (
                    ((-1 if p[0] not in mirrored else 1) * (16 + 10 * (p[4] % 3)))
                    if p[1] == "G" and upright(devs[p[0]])
                    else 0
                )
                for p in ps
            ]
            # a drain/source whose trunk lies past its own device, or past another of its column, or
            # whose wire would run along another net's: jog around it
            for i, p in enumerate(ps):
                if p[1] != "G" and (crosses(p, ch, ys) or blocked(p, ch) or (net, p[0], p[1]) in forced):
                    xs[i] = jog_x(p)
            plan[net] = (ch, ps, xs)
            hi = max(xs + ([width - 60] if net in ports and net.startswith("out") else []))  # the output flag's run
            chans[ch].append((net, min(xs), hi))
        tracks = {}
        for ch, items in chans.items():
            lanes = []
            for net, a, b in sorted(items, key=lambda t: t[1]):
                for i, lane in enumerate(lanes):
                    if all(b + 10 < l0 or a - 10 > l1 for l0, l1 in lane):
                        lane.append((a, b))
                        tracks[(ch, net)] = i
                        break
                else:
                    lanes.append([(a, b)])
                    tracks[(ch, net)] = len(lanes) - 1
            chans[ch] = lanes
        return all_pins, plan, tracks, chans

    def trunk_y(ch, net, chans, tracks):
        chan_top = (ys[ch] if ch < nrows else height - 60) - 30 - (len(chans[ch]) + 1) * TRACK
        return chan_top + (tracks[(ch, net)] + 1) * TRACK

    def verticals(plan, tracks, chans):
        """Every wire's vertical runs: (x, y0, y1, net, (net, device, pin))."""
        runs = []
        for net, (ch, ps, xs) in plan.items():
            ty = trunk_y(ch, net, chans, tracks)
            for (n, pin, x, y, r), sx in zip(ps, xs, strict=True):
                if pin != "G" and sx != x:
                    yy = y + (10 if y > ys[r] + DEV_H / 2 else -10)
                    runs += [(x, y, yy, net, None), (sx, yy, ty, net, (net, n, pin))]
                else:
                    runs.append((sx, y, ty, net, (net, n, pin) if pin != "G" else None))
        return runs

    def collisions(plan, tracks, chans):
        """Drains and sources whose vertical touches another net's at the same x, or ends within a
        track of it: two junctions a track apart in one column read as one wire."""
        runs = verticals(plan, tracks, chans)
        found = set()
        for i, (x, a0, a1, net, key) in enumerate(runs):
            for x2, b0, b1, net2, key2 in runs[i + 1 :]:
                gap = max(min(a0, a1), min(b0, b1)) - min(max(a0, a1), max(b0, b1))
                if abs(x - x2) < 1 and net != net2 and gap <= TRACK:
                    # jog the one not yet jogged, a drain or source (a gate's run is staggered already)
                    for k in (key, key2):
                        if k and k not in forced:
                            found.add(k)
                            break
        return found

    ys, height = [], 0
    ys, height = place_rows({})
    for _ in range(2):
        _, plan, tracks, chans = route(ys)
        ys, height = place_rows(chans)
    _, plan, tracks, chans = route(ys)
    for _ in range(4):  # jog until no two nets' wires run together
        found = collisions(plan, tracks, chans)
        if not found:
            break
        forced |= found
        _, plan, tracks, chans = route(ys)
        ys, height = place_rows(chans)
        _, plan, tracks, chans = route(ys)

    svg: list[str] = []  # the stages side by side, no outline around each
    for n, d in devs.items():
        px, r = pos[n]
        crowded = slot[n] == 0 and any(slot[m] == 1 and row[m] == r and stage[m] == stage[n] for m in devs)
        svg += symbol(skin, d, px, ys[r], n in mirrored, n, raised=crowded)  # clear of the mirrored neighbour's name
        for pin, (x, y) in pins(skin, d, px, ys[r], n in mirrored).items():
            net = d[pin.lower()]
            if net in SUPPLY and pin != "G":
                svg += supply(skin, net, x, y)
            elif (net in beside or net in as_label) and not upright(d):
                # a pass device's or a capacitor's gate: a stub out of it (down from a pass NMOS's,
                # else up), its flag or label to the left
                end = y + (14 if "pass" in d and d["pol"] == "n" else -14)
                svg += [f'<path d="M{x},{y} V{end}"/>']
                svg += flag(skin, net, x, end, "left") if net in beside else label(net, x, end, "left")
            elif net in beside or net in as_label:
                side = "right" if n in mirrored else "left"
                if net in beside:
                    svg += [f'<path d="M{x},{y} H{x + (20 if side == "right" else -20)}"/>']
                    svg += flag(skin, net, x + (20 if side == "right" else -20), y, side)
                else:
                    svg += label(net, x, y, side)

    def outward(ps) -> str | None:
        """The side a port's flag points to where the port reaches only pass devices' drains and
        sources on one side (their left ends: an input, "left"; their right: "right"); else None."""
        sides = {
            ("left" if x == pos[n][0] else "right") if "pass" in devs[n] and pin != "G" else None
            for n, pin, x, _y, _r in ps
        }
        return sides.pop() if len(sides) == 1 and None not in sides else None

    spans = {}  # net -> (trunk y, x0, x1)
    for net, (ch, ps, xs) in plan.items():
        a, b = min(xs), max(xs)
        if net in ports and net not in SUPPLY:  # an output or a multi-pin port: a flag at the trunk's end
            b = max(b, width - 60) if net.startswith("out") else b
            side = outward(ps)
            a, b = (a - 30, b) if side == "left" else (a, b + 30) if side == "right" else (a, b)
        spans[net] = (trunk_y(ch, net, chans, tracks), a, b)

    def down(net, x, y0, y1):
        """A wire's vertical from y0 to y1 at x (path commands after a move to (x, y0)), broken
        where another net's trunk crosses it: a crossing a track from a junction, drawn unbroken,
        reads as a second junction (two outputs drawn as one)."""
        lo, hi = min(y0, y1), max(y0, y1)
        cuts = sorted(
            (ty for other, (ty, a, b) in spans.items() if other != net and a < x < b and lo + GAP < ty < hi - GAP),
            reverse=y1 < y0,
        )
        sign = 1 if y1 > y0 else -1
        return "".join(f" V{c - sign * GAP} M{x},{c + sign * GAP}" for c in cuts) + f" V{y1}"

    for net, (ch, ps, xs) in plan.items():
        ty, a, b = spans[net]
        svg.append(f'<path d="M{a},{ty} H{b}"/>')
        flagged = net in ports and net not in SUPPLY
        if flagged:
            svg += flag(skin, net, a, ty, "left") if outward(ps) == "left" else flag(skin, net, b, ty, "right")
        drops = defaultdict(set)  # x on the trunk -> the sides (above/below) wires drop from
        for (_n, pin, x, y, r), sx in zip(ps, xs, strict=True):
            if pin == "G":
                svg.append(f'<path d="M{x},{y} H{sx}{down(net, sx, y, ty)}"/>')
            elif sx != x:  # jog: out of the pin, across, then to the trunk
                yy = y + (10 if y > ys[r] + DEV_H / 2 else -10)
                svg.append(f'<path d="M{x},{y} V{yy} H{sx}{down(net, sx, yy, ty)}"/>')
            else:
                svg.append(f'<path d="M{x},{y}{down(net, x, y, ty)}"/>')
            drops[sx].add("above" if y < ty else "below")
        # a junction dot only where three or more wires meet; a trunk end with one drop is a corner
        for sx, sides in drops.items():
            wires = len(sides) + (sx > a) + (sx < b) + (flagged and sx in (a, b))
            if wires >= 3:
                svg.append(f'<circle cx="{sx}" cy="{ty}" r="2.5" fill="#000"/>')
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'{skin.style}<rect width="100%" height="100%" fill="white" stroke="none"/>' + "".join(svg) + "</svg>"
    )
    return {k: sorted(n for n in devs if stack[stage[n]] == k) for k in sorted(set(stack.values()))}
