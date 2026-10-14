"""Schematic images from HDL (Verilog, SystemVerilog), through Yosys and netlistsvg.

    uv run python -m flow.util.hdl2image input.v --top TOP -o out.svg [--skin digital|analog|SKIN.svg]
    uv run python -m flow.util.hdl2image script.tcl -o out.svg      # a Yosys script that writes the JSON
    uv run python -m flow.util.hdl2image netlist.json -o out.svg    # a Yosys JSON netlist

The digital skin draws blocks, with bus widths and 0/1 tie symbols added after netlistsvg (it drops
both). The analog skin normalizes MOS cells (any PDK's MOS models, flow/util/mos_models.py)
to transistor symbols, omits bulk terminals, and moves an input that drives a single gate beside it.
The skins live with the documentation, in ``docs/images/netlistsvg``. For transistor netlists in
SPICE, laid out by signal-flow stage and symmetry, see ``flow/util/netlist2image.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from flow.util.mos_models import polarity

ROOT = Path(__file__).resolve().parents[2]
SKINS = ROOT / "docs/images/netlistsvg"
DIGITAL_SKIN = SKINS / "style.svg"
ANALOG_SKIN = SKINS / "circuitikz_analog.svg"
NETLISTSVG = "netlistsvg@1.0.2"

_SVG_NS = "http://www.w3.org/2000/svg"
_SKIN_NS = "https://github.com/nturley/netlistsvg"
SVG_NS, SKIN_NS = _SVG_NS, _SKIN_NS
SVG = f"{{{SVG_NS}}}"
SKIN = f"{{{SKIN_NS}}}"
BUS_CLASS = re.compile(r"net_\d+(?:,\d+)+")


# ==== Digital: blocks with bus widths and tie symbols ====


def orient_inout_ports(netlist: dict) -> dict:
    for module in netlist["modules"].values():
        for port in module.get("ports", {}).values():
            if port["direction"] == "inout":
                port["direction"] = "output"
        for cell in module.get("cells", {}).values():
            for pin, direction in cell.get("port_directions", {}).items():
                if direction == "inout":
                    cell["port_directions"][pin] = "output"
    return netlist


def style_constants(root: ET.Element) -> None:
    for cell in root.findall(f"{SVG}g"):
        if cell.get(f"{SKIN}type") != "constant":
            continue
        bits = cell.get("id", "").removeprefix("cell_")
        if not bits or set(bits) - {"0", "1"}:
            continue

        if set(bits) == {"0"}:
            # Same 16-unit first bar and 4-unit bar spacing as analog ground.
            path = "M16,24 H28 M16,24 V40 M8,40 H24 M11,44 H21 M14,48 H18"
            label = "0"
        elif set(bits) == {"1"} or int(bits, 2) == 1:
            path = "M8,4 H24 M16,4 V24 H28"
            label = "1"
        else:
            path = "M4,18 H20 V30 H4 Z M20,24 H28"
            label = f"0x{int(bits, 2):X}"

        for child in list(cell):
            if child.tag in {f"{SVG}path", f"{SVG}text"}:
                cell.remove(child)
        cell.insert(1, ET.Element(f"{SVG}path", {"d": path, "class": f"symbol {cell.get('id')}"}))
        cell.insert(2, ET.Element(f"{SVG}text", {"x": "2", "y": "27", "class": cell.get("id", "")}))
        cell[2].text = label


def label_pin_widths(root: ET.Element, netlist: dict) -> None:
    modules = netlist["modules"]
    top = next(
        (module for module in modules.values() if str(module.get("attributes", {}).get("top", "")).endswith("1")),
        next(iter(modules.values())),
    )

    for cell in root.findall(f"{SVG}g"):
        cell_id = cell.get("id", "")
        cell_type = cell.get(f"{SKIN}type")
        if cell_type in {"inputExt", "outputExt"}:
            port = top["ports"].get(cell_id.removeprefix("cell_"))
            if port is not None and len(port["bits"]) > 1:
                label = cell.find(f"{SVG}text")
                suffix = f"[{len(port['bits']) - 1}:0]"
                if label is not None and not (label.text or "").endswith(suffix):
                    label.text = f"{label.text}{suffix}"
        elif cell_type == "generic":
            instance = top["cells"].get(cell_id.removeprefix("cell_"))
            if instance is None:
                continue
            for pin in cell.findall(f"{SVG}g"):
                port_name = pin.get("id", "").split("~", 1)[-1]
                bits = instance["connections"].get(port_name, [])
                if len(bits) <= 1:
                    continue
                label = pin.find(f"{SVG}text")
                suffix = f"[{len(bits) - 1}:0]"
                if label is not None and not (label.text or "").endswith(suffix):
                    label.text = f"{label.text}{suffix}"


def annotate_bus_wires(root: ET.Element) -> None:
    """Use a uniform stroke with a diagonal bus tick and width above it."""
    for mark in root.findall(f"{SVG}g"):
        if mark.get("class") == "bus-width-mark":
            root.remove(mark)
    horizontal: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    vertical: list[tuple[float, float, float]] = []
    for line in root.findall(f"{SVG}line"):
        x1, x2, y1, y2 = (float(line.get(key, "0")) for key in ("x1", "x2", "y1", "y2"))
        if x1 == x2:
            vertical.append((x1, min(y1, y2), max(y1, y2)))
        elif y1 == y2 and BUS_CLASS.fullmatch(line.get("class", "")):
            horizontal[line.get("class", "")].append((min(x1, x2), max(x1, x2), y1))

    for wire_class, segments in horizontal.items():
        width = len(wire_class.removeprefix("net_").split(","))
        x1, x2, y = max(segments, key=lambda item: item[1] - item[0])
        if x2 - x1 < 28:
            continue
        x = (x1 + x2) / 2
        for fraction in (0.5, 0.35, 0.65, 0.2, 0.8):
            candidate = x1 + fraction * (x2 - x1)
            if all(abs(candidate - vx) > 10 or not (vy1 - 4 <= y <= vy2 + 4) for vx, vy1, vy2 in vertical):
                x = candidate
                break
        mark = ET.SubElement(root, f"{SVG}g", {"class": "bus-width-mark"})
        ET.SubElement(mark, f"{SVG}path", {"d": f"M{x - 4:g},{y + 4:g} L{x + 4:g},{y - 4:g}"})
        text = ET.SubElement(
            mark, f"{SVG}text", {"x": f"{x:g}", "y": f"{y - 7:g}", "text-anchor": "middle", "font-size": "8"}
        )
        text.text = str(width)


def postprocess(svg_path: Path, netlist_path: Path) -> None:
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("s", SKIN_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    netlist = json.loads(netlist_path.read_text())
    style_constants(root)
    label_pin_widths(root, netlist)
    annotate_bus_wires(root)
    tree.write(svg_path, encoding="unicode")


def json_to_digital_svg(netlist_path: Path, svg_path: Path, skin: Path = DIGITAL_SKIN) -> Path:
    """Render a Yosys JSON netlist with a block skin, then add bus widths and tie symbols."""

    # netlistsvg needs input/output directions and readable parameterized cell names.
    data = orient_inout_ports(json.loads(netlist_path.read_text()))
    for module in data["modules"].values():
        for cell in module.get("cells", {}).values():
            if cell["type"].startswith("$paramod") and "\\" in cell["type"]:
                cell["type"] = cell["type"].split("\\")[-1]
    netlist_path.write_text(json.dumps(data, indent=2) + "\n")
    subprocess.run(
        ["npx", "--yes", NETLISTSVG, str(netlist_path), "--skin", str(skin), "-o", str(svg_path)], check=True
    )
    postprocess(svg_path, netlist_path)
    return svg_path


def tcl_to_digital_svg(script: Path, netlist_path: Path, svg_path: Path, skin: Path = DIGITAL_SKIN) -> Path:
    """Run a Yosys script that writes ``netlist_path``, then render it (``json_to_digital_svg``)."""

    subprocess.run(["yosys", "-Q", "-q", "-c", str(script)], check=True, cwd=ROOT)
    return json_to_digital_svg(netlist_path, svg_path, skin)


# ==== Analog: transistor symbols from MOS cells ====


def _straighten_single_gate_inputs(module: dict, svg_path: Path) -> None:
    """Place a sole external MOS-gate input directly left of its gate pin."""
    uses: dict[int, list[tuple[str, str, str]]] = {}
    for cell_name, cell in module.get("cells", {}).items():
        for pin, bits in cell.get("connections", {}).items():
            for bit in bits:
                if isinstance(bit, int):
                    uses.setdefault(bit, []).append((cell_name, cell["type"], pin))

    port_counts = Counter(
        bit for port in module.get("ports", {}).values() for bit in port.get("bits", []) if isinstance(bit, int)
    )
    ET.register_namespace("", _SVG_NS)
    ET.register_namespace("s", _SKIN_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    groups = {group.get("id", "").removeprefix("cell_"): group for group in root.findall(f"{{{_SVG_NS}}}g")}
    changed = False

    def position(group: ET.Element) -> tuple[float, float]:
        match = re.fullmatch(r"translate\(\s*([^,]+),\s*([^,)]+)\s*\)", group.attrib["transform"])
        if match is None:
            raise ValueError(f"unexpected netlistsvg transform: {group.attrib['transform']}")
        return float(match[1]), float(match[2])

    for port_name, port in module.get("ports", {}).items():
        bits = port.get("bits", [])
        if port.get("direction") != "input" or len(bits) != 1 or not isinstance(bits[0], int):
            continue
        bit = bits[0]
        if port_counts[bit] != 1 or len(uses.get(bit, [])) != 1:
            continue
        cell_name, cell_type, pin = uses[bit][0]
        if cell_type not in {"mos_n", "mos_p"} or pin != "G":
            continue
        terminal = groups.get(port_name)
        transistor = groups.get(cell_name)
        if terminal is None or transistor is None:
            continue
        terminal_port = terminal.find(f"{{{_SVG_NS}}}g[@{{{_SKIN_NS}}}pid='Y']")
        gate_port = transistor.find(f"{{{_SVG_NS}}}g[@{{{_SKIN_NS}}}pid='G']")
        if terminal_port is None or gate_port is None or gate_port.get(f"{{{_SKIN_NS}}}position") != "left":
            continue
        terminal_x, _ = position(terminal)
        transistor_x, transistor_y = position(transistor)
        route_start = terminal_x + float(terminal_port.get(f"{{{_SKIN_NS}}}x"))
        route_end = transistor_x + float(gate_port.get(f"{{{_SKIN_NS}}}x"))
        if route_start >= route_end:
            continue
        gate_y = transistor_y + float(gate_port.get(f"{{{_SKIN_NS}}}y"))
        new_terminal_y = gate_y - float(terminal_port.get(f"{{{_SKIN_NS}}}y"))
        net_class = f"net_{bit}"
        route_elements = [
            element
            for element in root
            if element.tag in {f"{{{_SVG_NS}}}line", f"{{{_SVG_NS}}}circle"}
            and net_class in element.get("class", "").split()
        ]
        if not route_elements:
            continue
        terminal.set("transform", f"translate({terminal_x:g},{new_terminal_y:g})")
        for element in route_elements:
            root.remove(element)
        ET.SubElement(
            root,
            f"{{{_SVG_NS}}}line",
            {
                "x1": f"{route_start:g}",
                "x2": f"{route_end:g}",
                "y1": f"{gate_y:g}",
                "y2": f"{gate_y:g}",
                "class": net_class,
            },
        )
        changed = True

    if changed:
        tree.write(svg_path, encoding="unicode")


def _align_low_shared_gate_inputs(module: dict, svg_path: Path) -> None:
    """Move a dangling input stub up to the lowest MOS gate on its net."""
    uses: dict[int, list[tuple[str, str, str]]] = {}
    for cell_name, cell in module.get("cells", {}).items():
        for pin, bits in cell.get("connections", {}).items():
            for bit in bits:
                if isinstance(bit, int):
                    uses.setdefault(bit, []).append((cell_name, cell["type"], pin))

    ET.register_namespace("", _SVG_NS)
    ET.register_namespace("s", _SKIN_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    groups = {group.get("id", "").removeprefix("cell_"): group for group in root.findall(f"{{{_SVG_NS}}}g")}

    def position(group: ET.Element) -> tuple[float, float]:
        match = re.fullmatch(r"translate\(\s*([^,]+),\s*([^,)]+)\s*\)", group.attrib["transform"])
        if match is None:
            raise ValueError(f"unexpected netlistsvg transform: {group.attrib['transform']}")
        return float(match[1]), float(match[2])

    changed = False
    for port_name, port in module.get("ports", {}).items():
        bits = port.get("bits", [])
        if port.get("direction") != "input" or len(bits) != 1 or not isinstance(bits[0], int):
            continue
        bit = bits[0]
        gate_uses = uses.get(bit, [])
        if len(gate_uses) < 2 or any(kind not in {"mos_n", "mos_p"} or pin != "G" for _, kind, pin in gate_uses):
            continue
        terminal = groups.get(port_name)
        if terminal is None:
            continue
        terminal_pin = terminal.find(f"{{{_SVG_NS}}}g[@{{{_SKIN_NS}}}pid='Y']")
        if terminal_pin is None:
            continue
        terminal_x, terminal_y = position(terminal)
        pin_x = terminal_x + float(terminal_pin.get(f"{{{_SKIN_NS}}}x"))
        pin_y_offset = float(terminal_pin.get(f"{{{_SKIN_NS}}}y"))
        pin_y = terminal_y + pin_y_offset

        gate_ys = []
        for cell_name, _, _ in gate_uses:
            cell = groups.get(cell_name)
            gate = cell.find(f"{{{_SVG_NS}}}g[@{{{_SKIN_NS}}}pid='G']") if cell is not None else None
            if cell is None or gate is None:
                break
            gate_ys.append(position(cell)[1] + float(gate.get(f"{{{_SKIN_NS}}}y")))
        if len(gate_ys) != len(gate_uses) or pin_y <= max(gate_ys):
            continue
        target_y = max(gate_ys)
        net_class = f"net_{bit}"
        lines = [line for line in root.findall(f"{{{_SVG_NS}}}line") if net_class in line.get("class", "").split()]
        stubs = [
            line
            for line in lines
            if float(line.get("y1")) == pin_y == float(line.get("y2"))
            and pin_x in (float(line.get("x1")), float(line.get("x2")))
        ]
        if len(stubs) != 1:
            continue
        stub = stubs[0]
        junction_x = float(stub.get("x2")) if float(stub.get("x1")) == pin_x else float(stub.get("x1"))
        tail = [
            line
            for line in lines
            if line.get("x1") == line.get("x2")
            and float(line.get("x1")) == junction_x
            and {float(line.get("y1")), float(line.get("y2"))} == {target_y, pin_y}
        ]
        gate_branch = any(
            line not in tail
            and float(line.get("y1")) == target_y == float(line.get("y2"))
            and junction_x in (float(line.get("x1")), float(line.get("x2")))
            for line in lines
        )
        if len(tail) != 1 or not gate_branch or pin_x >= junction_x:
            continue

        root.remove(stub)
        root.remove(tail[0])
        terminal.set("transform", f"translate({terminal_x:g},{target_y - pin_y_offset:g})")
        ET.SubElement(
            root,
            f"{{{_SVG_NS}}}line",
            {
                "x1": f"{pin_x:g}",
                "x2": f"{junction_x:g}",
                "y1": f"{target_y:g}",
                "y2": f"{target_y:g}",
                "class": net_class,
            },
        )
        changed = True

    if changed:
        tree.write(svg_path, encoding="unicode")


def _consolidate_net_wires(svg_path: Path) -> None:
    """Draw overlapping ELK segments only once to avoid dark seams."""
    ET.register_namespace("", _SVG_NS)
    ET.register_namespace("s", _SKIN_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    segments: dict[tuple[str, str, float], list[tuple[float, float, ET.Element]]] = {}

    for line in root.findall(f"{{{_SVG_NS}}}line"):
        net_class = line.get("class", "")
        if not net_class.startswith("net_"):
            continue
        x1, x2 = float(line.get("x1")), float(line.get("x2"))
        y1, y2 = float(line.get("y1")), float(line.get("y2"))
        if y1 == y2:
            key, start, end = (net_class, "horizontal", y1), min(x1, x2), max(x1, x2)
        elif x1 == x2:
            key, start, end = (net_class, "vertical", x1), min(y1, y2), max(y1, y2)
        else:
            continue
        segments.setdefault(key, []).append((start, end, line))

    changed = False
    for (net_class, direction, fixed), spans in segments.items():
        if len(spans) == 1 and spans[0][0] != spans[0][1]:
            continue
        for _, _, line in spans:
            root.remove(line)
        current_start, current_end = None, None
        for start, end, _ in sorted(spans, key=lambda item: (item[0], item[1])):
            if current_start is None:
                current_start, current_end = start, end
            elif start <= current_end:
                current_end = max(current_end, end)
            else:
                if current_start != current_end:
                    coords = (
                        (current_start, fixed, current_end, fixed)
                        if direction == "horizontal"
                        else (fixed, current_start, fixed, current_end)
                    )
                    ET.SubElement(
                        root,
                        f"{{{_SVG_NS}}}line",
                        dict(zip(("x1", "y1", "x2", "y2"), (f"{v:g}" for v in coords))) | {"class": net_class},
                    )
                current_start, current_end = start, end
        if current_start is not None and current_start != current_end:
            coords = (
                (current_start, fixed, current_end, fixed)
                if direction == "horizontal"
                else (fixed, current_start, fixed, current_end)
            )
            ET.SubElement(
                root,
                f"{{{_SVG_NS}}}line",
                dict(zip(("x1", "y1", "x2", "y2"), (f"{v:g}" for v in coords))) | {"class": net_class},
            )
        changed = True

    circles: set[tuple[str, str, str, str]] = set()
    for circle in root.findall(f"{{{_SVG_NS}}}circle"):
        net_class = circle.get("class", "")
        if not net_class.startswith("net_"):
            continue
        key = (net_class, circle.get("cx", ""), circle.get("cy", ""), circle.get("r", ""))
        if key in circles:
            root.remove(circle)
            changed = True
        else:
            circles.add(key)

    if changed:
        tree.write(svg_path, encoding="unicode")


def verilog_to_analog_svg(
    verilog_path: Path, output_path: Path, top: str, skin: Path = ANALOG_SKIN
) -> tuple[Path, Path]:
    """Convert one structural Verilog module to netlistsvg JSON and analog SVG."""

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", top) is None:
        raise ValueError(f"invalid Verilog top-module name {top!r}")
    verilog_path = verilog_path.resolve()
    output_path = output_path.resolve()
    json_path = output_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="frida-netlistsvg-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        yosys_json = temporary_path / "yosys.json"
        yosys_script = f'read_verilog -sv "{verilog_path}"; hierarchy -check -top {top}; write_json "{yosys_json}"'
        subprocess.run(["yosys", "-q", "-p", yosys_script], check=True)

        data = json.loads(yosys_json.read_text())
        if top not in data.get("modules", {}):
            raise ValueError(f"top module {top!r} was not emitted by Yosys")

        for module in data["modules"].values():
            for port in module.get("ports", {}).values():
                if port.get("direction") not in ("input", "output"):
                    port["direction"] = "input"

            for cell in module.get("cells", {}).values():
                cell_type = str(cell.get("type", ""))
                normalized_type = cell_type.lower().lstrip("\\")
                pol = polarity(normalized_type)
                if pol is None:
                    continue
                cell["type"] = f"mos_{pol}"

                connections = cell.get("connections", {})
                cell["connections"] = {
                    name.upper(): bits for name, bits in connections.items() if name.lower() in {"d", "g", "s"}
                }
                # Guide the top-down skin from the PMOS supply through the NMOS tail to
                # ground. These are drawing directions, not electrical claims about a
                # MOS terminal.
                out_pin = "D" if cell["type"] == "mos_p" else "S"
                cell["port_directions"] = {
                    name.upper(): "output" if name.upper() == out_pin else "input"
                    for name in connections
                    if name.lower() in {"d", "g", "s"}
                }
                parameters = cell.get("parameters", {})
                if parameters:
                    cell.setdefault("attributes", {})["value"] = " ".join(
                        f"{name}={value}"
                        for name, value in sorted(parameters.items())
                        if name.lower() in ("w", "l", "m")
                    )

        json_path.write_text(json.dumps(data, indent=2) + "\n")

        locator = subprocess.run(
            [
                "npx",
                "--yes",
                "--package",
                "netlistsvg@1.0.2",
                "sh",
                "-c",
                'readlink -f "$(command -v netlistsvg)"',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        executable = Path(locator.stdout.strip())
        skin_path = skin.resolve()
        if not skin_path.is_file():
            raise FileNotFoundError(f"netlistsvg skin not found at {skin_path}")

        subprocess.run(
            ["node", str(executable), str(json_path), "-o", str(output_path), "--skin", str(skin_path)],
            check=True,
        )

        _straighten_single_gate_inputs(data["modules"][top], output_path)
        _align_low_shared_gate_inputs(data["modules"][top], output_path)
        _consolidate_net_wires(output_path)

    return json_path, output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="structural Verilog, a Yosys script (.tcl) writing the JSON, or the JSON"
    )
    parser.add_argument("-o", "--output", required=True, type=Path, help="output SVG path")
    parser.add_argument("--top", help="top-level Verilog module (Verilog input)")
    parser.add_argument("--json", type=Path, help="the JSON a Yosys script writes (default: OUTPUT with .json)")
    parser.add_argument("--skin", default="digital", help="digital, analog, or a skin SVG")
    args = parser.parse_args()
    skin = {"digital": DIGITAL_SKIN, "analog": ANALOG_SKIN}.get(args.skin, Path(args.skin))
    if args.source.suffix == ".json":
        json_to_digital_svg(args.source, args.output, skin)
    elif args.source.suffix == ".tcl":
        tcl_to_digital_svg(args.source, args.json or args.output.with_suffix(".json"), args.output, skin)
    elif skin == DIGITAL_SKIN:
        if not args.top:
            parser.error("Verilog input needs --top")
        with tempfile.TemporaryDirectory(prefix="frida-netlistsvg-") as tmp:
            script = Path(tmp) / "write_json.tcl"
            json_path = args.output.resolve().with_suffix(".json")
            script.write_text(
                f'yosys -import\nread_verilog -sv "{args.source.resolve()}"\nprep -top {args.top}\n'
                f'techmap\nopt\nwrite_json "{json_path}"\n'
            )
            tcl_to_digital_svg(script, json_path, args.output.resolve(), skin)
    else:
        if not args.top:
            parser.error("Verilog input needs --top")
        verilog_to_analog_svg(args.source, args.output, args.top, skin)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
