"""Render structural Verilog as an analog netlistsvg schematic.

The input Verilog should describe analog primitives as black-box cells. MOS
cell types named ``mos_n``/``nmos``/``nch*`` and
``mos_p``/``pmos``/``pch*`` are normalized to analog symbols. Bulk terminals
are omitted from the drawing to keep shared supply rails readable.
With a custom skin, an external input driving only one gate is drawn directly
to the left of that gate when the geometry permits it.

Run from the repository root with:

    uv run python -m flow.util.verilog_schematic input.v --top Comp -o comp.svg
    uv run python -m flow.util.verilog_schematic input.v --top Comp -o comp.svg \
        --skin flow/util/skins/circuitikz_analog.svg
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

_MOS_SKIN = r"""
<g s:type="mos_n" s:width="48" s:height="58" transform="translate(15,350)">
  <s:alias val="mos_n"/><s:alias val="nmos"/>
  <text x="44" y="27" s:attribute="ref" class="$cell_id">MN</text>
  <path d="M24,12 V46 M30,13 V45" class="symbol $cell_id"/>
  <path d="M0,29 H24 M38,0 V18 H30 M30,40 H38 V58" class="connect $cell_id"/>
  <g s:x="38" s:y="0" s:pid="D" s:position="top"/>
  <g s:x="0" s:y="29" s:pid="G" s:position="left"/>
  <g s:x="38" s:y="58" s:pid="S" s:position="bottom"/>
</g>
<g s:type="mos_p" s:width="48" s:height="58" transform="translate(75,350)">
  <s:alias val="mos_p"/><s:alias val="pmos"/>
  <text x="44" y="27" s:attribute="ref" class="$cell_id">MP</text>
  <path d="M26,12 V46 M32,13 V45" class="symbol $cell_id"/>
  <path d="M0,29 H20 M38,0 V18 H32 M32,40 H38 V58" class="connect $cell_id"/>
  <circle cx="23" cy="29" r="3" class="gatebubble $cell_id"/>
  <g s:x="38" s:y="58" s:pid="D" s:position="bottom"/>
  <g s:x="0" s:y="29" s:pid="G" s:position="left"/>
  <g s:x="38" s:y="0" s:pid="S" s:position="top"/>
</g>
"""

_SVG_NS = "http://www.w3.org/2000/svg"
_SKIN_NS = "https://github.com/nturley/netlistsvg"


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


def verilog_to_analog_svg(
    verilog_path: Path, output_path: Path, top: str, skin: Path | None = None
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
                if normalized_type in ("mos_n", "nmos") or normalized_type.startswith(("nch", "nfet")):
                    cell["type"] = "mos_n"
                elif normalized_type in ("mos_p", "pmos") or normalized_type.startswith(("pch", "pfet")):
                    cell["type"] = "mos_p"
                else:
                    continue

                connections = cell.get("connections", {})
                cell["connections"] = {
                    name.upper(): bits for name, bits in connections.items() if name.lower() in {"d", "g", "s"}
                }
                if skin is None:
                    cell["port_directions"] = {
                        name.upper(): "output" if name.lower() == "d" else "input"
                        for name in connections
                        if name.lower() in {"d", "g", "s"}
                    }
                else:
                    # Guide the new top-down skin from the PMOS supply through
                    # the NMOS tail to ground. These are drawing directions,
                    # not electrical claims about a MOS terminal.
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
                "netlistsvg",
                "sh",
                "-c",
                'readlink -f "$(command -v netlistsvg)"',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        executable = Path(locator.stdout.strip())
        package_path = executable.parent.parent
        if skin is None:
            analog_skin = package_path / "lib" / "analog.svg"
            if not analog_skin.is_file():
                raise FileNotFoundError(f"netlistsvg analog skin not found at {analog_skin}")
            skin_text = analog_skin.read_text()
            skin_path = temporary_path / "analog_mos.svg"
            skin_path.write_text(skin_text.replace("</svg>", _MOS_SKIN + "\n</svg>"))
        else:
            skin_path = skin.resolve()
            if not skin_path.is_file():
                raise FileNotFoundError(f"netlistsvg skin not found at {skin_path}")

        subprocess.run(
            ["node", str(executable), str(json_path), "-o", str(output_path), "--skin", str(skin_path)],
            check=True,
        )

        if skin is not None:
            _straighten_single_gate_inputs(data["modules"][top], output_path)
            _align_low_shared_gate_inputs(data["modules"][top], output_path)

    return json_path, output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verilog", type=Path, help="structural Verilog input")
    parser.add_argument("--top", required=True, help="top-level Verilog module")
    parser.add_argument("-o", "--output", required=True, type=Path, help="output SVG path")
    parser.add_argument("--skin", type=Path, help="standalone netlistsvg skin SVG")
    args = parser.parse_args()

    json_path, svg_path = verilog_to_analog_svg(args.verilog, args.output, args.top, args.skin)
    print(f"Created {json_path}")
    print(f"Created {svg_path}")


if __name__ == "__main__":
    main()
