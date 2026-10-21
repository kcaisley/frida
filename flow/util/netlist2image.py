"""Transistor-level schematic images of SPICE netlists, laid out by signal flow and symmetry.

    uv run python -m flow.util.netlist2image NETLIST.sp OUT.svg [ALIGN.const.json]

Stages are channel-connected components in signal-flow order, inputs on the left: devices
joined through drain and source nets form one stage (a StrongARM is one), and each next stage
is gated by the nets of the stages before. Consecutive static CMOS stages (decision inverters,
SR latch, buffers) share one dashed stack; every other stage is a stack of its own.

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
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from flow.util.mos_models import polarity

SUPPLY = {"vdd": "vdd", "vss": "vss"}
SKIN = Path(__file__).resolve().parents[2] / "docs/images/netlistsvg/circuitikz_analog.svg"
DEV_W, DEV_H, SLOT, STAGE_GAP, SUB_GAP, TRACK = 80, 64, 190, 160, 0, 12
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
        p_rows = max(up.values(), default=-1) + 1 if any(d["pol"] == "p" for d in mem.values()) else 0
        n_rows = max(down.values(), default=-1) + 1
        for n, d in mem.items():
            row[n] = up.get(n, 0) if d["pol"] == "p" else p_rows + (n_rows - 1 - down.get(n, n_rows - 1))
    return row, max(row.values()) + 1


# ---- drawing (netlistsvg analog skin) ------------------------------------------------------
def mos_kind(dev, mirrored):
    return f"mos_{dev['pol']}{'_r' if mirrored else ''}"


def pins(skin, dev, x, y, mirrored):
    """Pin coordinates of a device symbol at (x, y) (top left)."""
    return {pin: (x + px, y + py) for pin, (px, py) in skin.pins(mos_kind(dev, mirrored)).items()}


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


def render(netlist: Path, out: Path, const_path=None, skin_path: Path = SKIN):
    skin = Skin(skin_path)
    ports, devs = parse(netlist)
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
        on_axis = [n for n in mem if n in axis or not any(n in p for p in pairs)]
        for n in on_axis:
            k = 0
            while k in used[row[n]]:
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
            xs = [
                p[2] + (((-1 if p[0] not in mirrored else 1) * (16 + 10 * (p[4] % 3))) if p[1] == "G" else 0)
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

    svg = [
        f'<rect x="{a - 20}" y="20" width="{b - a + 40}" height="{height - 40}" stroke="#999" stroke-dasharray="6 4"/>'
        for a, b in box.values()
    ]
    for n, d in devs.items():
        px, r = pos[n]
        crowded = slot[n] == 0 and any(slot[m] == 1 and row[m] == r and stage[m] == stage[n] for m in devs)
        svg += symbol(skin, d, px, ys[r], n in mirrored, n, raised=crowded)  # clear of the mirrored neighbour's name
        for pin, (x, y) in pins(skin, d, px, ys[r], n in mirrored).items():
            net = d[pin.lower()]
            if net in SUPPLY and pin != "G":
                svg += supply(skin, net, x, y)
            elif net in beside or net in as_label:
                side = "right" if n in mirrored else "left"
                if net in beside:
                    svg += [f'<path d="M{x},{y} H{x + (20 if side == "right" else -20)}"/>']
                    svg += flag(skin, net, x + (20 if side == "right" else -20), y, side)
                else:
                    svg += label(net, x, y, side)
    for net, (ch, ps, xs) in plan.items():
        ty = trunk_y(ch, net, chans, tracks)
        a, b = min(xs), max(xs)
        if net in ports and net not in SUPPLY:  # an output or a multi-pin port: a flag at the trunk's end
            b = max(b, width - 60) if net.startswith("out") else b
        svg.append(f'<path d="M{a},{ty} H{b}"/>')
        flagged = net in ports and net not in SUPPLY
        if flagged:
            svg += flag(skin, net, b, ty, "right")
        drops = defaultdict(set)  # x on the trunk -> the sides (above/below) wires drop from
        for (_n, pin, x, y, r), sx in zip(ps, xs, strict=True):
            if pin == "G":
                svg.append(f'<path d="M{x},{y} H{sx} V{ty}"/>')
            elif sx != x:  # jog: out of the pin, across, then to the trunk
                yy = y + (10 if y > ys[r] + DEV_H / 2 else -10)
                svg.append(f'<path d="M{x},{y} V{yy} H{sx} V{ty}"/>')
            else:
                svg.append(f'<path d="M{x},{y} V{ty}"/>')
            drops[sx].add("above" if y < ty else "below")
        # a junction dot only where three or more wires meet; a trunk end with one drop is a corner
        for sx, sides in drops.items():
            wires = len(sides) + (sx > a) + (sx < b) + (flagged and sx == b)
            if wires >= 3:
                svg.append(f'<circle cx="{sx}" cy="{ty}" r="2.5" fill="#000"/>')
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'{skin.style}<rect width="100%" height="100%" fill="white" stroke="none"/>' + "".join(svg) + "</svg>"
    )
    return {k: sorted(n for n in devs if stack[stage[n]] == k) for k in sorted(set(stack.values()))}


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    for k, members in render(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None).items():
        print(f"stack {k}: {' '.join(members)}")


if __name__ == "__main__":
    main()
