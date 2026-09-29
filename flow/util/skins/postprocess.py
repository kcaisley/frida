"""Finish a netlistsvg digital render with constants and bus widths.

Run after rendering with the Circuitikz digital skin::

    python flow/util/skins/postprocess.py diagram.svg netlist.json

netlistsvg 1.0.2 omits the constant cell's ``value`` skin attribute; the
generated cell ID contains the bit pattern. It also loses connection widths
from block pin and external port labels.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
SKIN_NS = "https://github.com/nturley/netlistsvg"
SVG = f"{{{SVG_NS}}}"
SKIN = f"{{{SKIN_NS}}}"
BUS_CLASS = re.compile(r"net_\d+(?:,\d+)+")


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
        ET.SubElement(mark, f"{SVG}path", {"d": f"M{x-4:g},{y+4:g} L{x+4:g},{y-4:g}"})
        text = ET.SubElement(
            mark, f"{SVG}text", {"x": f"{x:g}", "y": f"{y-7:g}", "text-anchor": "middle", "font-size": "8"}
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("netlist", type=Path)
    args = parser.parse_args()
    postprocess(args.svg, args.netlist)


if __name__ == "__main__":
    main()
