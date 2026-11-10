"""The numbers a layout step and an extraction step report beyond their outputs, as rows the viewer
shows under their sections (``stat``: section, label, value, unit): ALIGN's layout by its parts
(Init, Floorplanning, Placement, Routing, Finishing: each part's seconds, then what its files and
the GDS say), FasterCap's solve (its panels, links, iterations, memory and time)."""

from __future__ import annotations

import json
import re
from importlib import import_module
from pathlib import Path
from typing import Any

Stat = dict[str, Any]


def stat(section: str, label: str, value: Any, unit: str = "") -> Stat:
    """One row: its section, its label, its value (a number, a text or None) and unit (``s``,
    ``#``, ``µm``, ``µm²``, ``B``; none for a text)."""
    return {"section": section, "label": label, "value": value, "unit": unit}


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _hpwl(pnr: dict[str, Any]) -> tuple[float, int]:
    """The half-perimeter of each net's bounding box over its routed shapes (ALIGN's PnR output,
    nm), summed in µm, and the nets counted."""
    boxes: dict[str, list[int]] = {}
    for shape in pnr.get("terminals", []):
        net = shape.get("netName")
        if not net or shape.get("layer", "").startswith("V"):
            continue
        x1, y1, x2, y2 = shape["rect"]
        box = boxes.setdefault(net, [x1, y1, x2, y2])
        box[:] = [min(box[0], x1), min(box[1], y1), max(box[2], x2), max(box[3], y2)]
    return sum((x2 - x1) + (y2 - y1) for x1, y1, x2, y2 in boxes.values()) / 1000, len(boxes)


def _metal(gds: Path, pdk: str) -> tuple[dict[str, float], dict[str, int]]:
    """Each metal's wire length (µm: each merged shape's long side, a polygon's half perimeter) and
    each via layer's cuts in the GDS, by the PDK's generic layer names (``M1``, ``V1``)."""
    import klayout.db as kdb

    try:
        tech = import_module(f"pdk.{pdk}.layout.tech")
    except ImportError:  # a kit not installed (the public repository's CI): no layer names to count by
        return {}, {}
    layout = kdb.Layout()
    layout.read(str(gds))
    top = next((cell for cell in layout.top_cells() if cell.name.lower() == gds.stem.lower()), layout.top_cells()[0])
    numbers = {tuple(number): key for key, number in tech.LAYERS.items() if number}
    lengths: dict[str, float] = {}
    cuts: dict[str, int] = {}
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        key = numbers.get((info.layer, info.datatype))
        if key is None or not re.fullmatch(r"[MV]\d+", key):
            continue
        region = kdb.Region(top.begin_shapes_rec(index))
        if key.startswith("V"):
            cuts[key] = region.count()
            continue
        total = 0.0
        for polygon in region.merged().each():
            box = polygon.bbox()
            total += max(box.width(), box.height()) if polygon.is_box() else polygon.perimeter() / 2
        lengths[key] = round(total * layout.dbu, 2)
    order = lambda item: int(item[0][1:])
    return dict(sorted(lengths.items(), key=order)), dict(sorted(cuts.items(), key=order))


def layout_stats(work: Path, design: str, gds: Path, pdk: str, laid: dict[str, Any]) -> list[Stat]:
    """ALIGN's layout of ``design`` (its work directory ``work``) by part: Init (its netlist read and
    its primitives mapped), Floorplanning, Placement, Routing (global and detailed, no clock tree)
    and Finishing (the post step and the GDS), each its seconds (``laid['parts']``) and what ALIGN's
    files and the GDS ``gds`` say."""
    parts = laid.get("parts") or {}
    name = design.upper()
    folder = work / design
    seconds = lambda *keys: round(sum(parts.get(key) or 0.0 for key in keys), 2)
    topology = _json(folder / "1_topology" / f"{name}.verilog.json") or {}
    modules = topology.get("modules", [])
    instances = sum(len(module.get("instances", [])) for module in modules)
    nets = len(
        {
            net
            for module in modules
            for net in module.get("parameters", [])
            + [conn["actual"] for inst in module.get("instances", []) for conn in inst.get("fa_map", [])]
        }
    )
    primitives = _json(folder / "2_primitives" / "__primitives__.json") or {}
    constraints = _json(folder / "1_topology" / f"{design}.const.json") or []
    rows = [
        stat("Init", "Time", seconds("read", "mapping"), "s"),
        stat("Init", "Modules", len(modules), "#"),
        stat("Init", "Instances", instances, "#"),
        stat("Init", "Nets", nets or None, "#"),
        stat("Init", "Primitives", len(primitives), "#"),
        stat("Init", "Constraints", len(constraints), "#"),
    ]
    width, height = laid.get("cell_um") or (None, None)
    rows += [
        stat("Floorplanning", "Time", seconds("floorplan"), "s"),
        stat("Floorplanning", "Placement", "constraints" if laid.get("placed") else "generated"),
        stat("Floorplanning", "Outline", f"{width:g} × {height:g}" if width else None, "µm"),
        stat("Floorplanning", "Aspect ratio", round(height / width, 2) if width else None),
    ]
    log = (folder / "LOG" / "align.log").read_text(errors="replace") if (folder / "LOG" / "align.log").exists() else ""
    found = re.findall(r"found (\d+) placement solution", log)
    pnr = _json(folder / "3_pnr" / f"{name}_0.json") or {}
    hpwl, routed = _hpwl(pnr) if pnr else (None, None)
    rows += [
        stat("Placement", "Time", seconds("placement"), "s"),
        stat("Placement", "Solutions", int(found[-1]) if found else None, "#"),
        stat("Placement", "HPWL", round(hpwl, 2) if hpwl is not None else None, "µm"),
    ]
    lengths, cuts = _metal(gds, pdk) if gds.exists() else ({}, {})
    opens = re.findall(r"OPEN: (\d+)", log)
    rows += [
        stat("Routing", "Time", seconds("global_route", "detail_route", "cts"), "s"),
        stat("Routing", "Router", laid.get("router")),
        stat("Routing", "Nets routed", routed, "#"),
        stat("Routing", "Wirelength", round(sum(lengths.values()), 2) if lengths else None, "µm"),
        *(stat("Routing", f"{layer} length", value, "µm") for layer, value in lengths.items()),
        stat("Routing", "Vias", sum(cuts.values()) if cuts else None, "#"),
        stat("Routing", "Shorts", len(laid.get("route_shorts") or {}), "#"),
        stat("Routing", "ALIGN opens", int(opens[-1]) if opens else 0, "#"),
    ]
    post = _json(Path(f"{folder / design}.gds.post.json")) or {}
    rows += [
        stat("Finishing", "Time", seconds("finishing"), "s"),
        *(stat("Finishing", what.capitalize(), count, "#") for what, count in post.items()),
        stat("Finishing", "GDS", gds.stat().st_size if gds.exists() else None, "B"),
    ]
    return rows


def fastercap_stats(output: Path, tolerance: float | None = None) -> list[Stat]:
    """FasterCap's solve (its output ``FasterCap_Output.txt``): the last iteration's panels
    (conductor and dielectric), links, matrix, the iterations, the memory and time they took."""
    if not output.exists():
        return []
    text = output.read_text(errors="replace")
    last = text.rsplit("Solve statistics:", 1)[-1]
    number = lambda pattern, source=last: int(found[1]) if (found := re.search(pattern, source)) else None
    times = [float(value) for value in re.findall(r"Iteration time: ([\d.]+)s", text)]
    memory = [float(value) for value in re.findall(r"Iteration allocated memory: (\d+) kilobytes", text)]
    dimension = re.findall(r"Dimension (\d+) x \d+", text)
    return [
        stat("FasterCap", "Tolerance", tolerance * 100 if tolerance else None, "%"),
        stat("FasterCap", "Iterations", len(times) or None, "#"),
        stat("FasterCap", "Panels refined", number(r"Number of panels after refinement: (\d+)"), "#"),
        stat("FasterCap", "Conductor panels", number(r"of which (\d+) conductors"), "#"),
        stat("FasterCap", "Dielectric panels", number(r"conductors and (\d+) dielectric"), "#"),
        stat("FasterCap", "Links", number(r"Number of links: (\d+)"), "#"),
        stat("FasterCap", "Matrix", f"{dimension[-1]} × {dimension[-1]}" if dimension else None),
        stat("FasterCap", "Memory", int(max(memory)) * 1024 if memory else None, "B"),
        # its iteration times accumulate: the last is the solve's
        stat("FasterCap", "Solve time", round(times[-1], 2) if times else None, "s"),
    ]
