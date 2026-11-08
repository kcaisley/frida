"""One instance as a page of its own: a single HTML file to open from disk or publish as a
claude.ai artifact, no server behind it. Its metrics by the pipeline's steps, in their order (its
record's metrics, the netlist, the layout, DRC, LVS, PEX: each one's statistics and run time), its
netlist, its schematic and its layout in 2-D and 3-D.

    python -m flow capdac --from page --to page --instance 9a5e63c5482c --pdk tsmc65

An instance's directory is a run's ``<pdk>/<name>/`` (``flow.__main__``: a folder a step,
``netlist/``, ``layout/``, ``drc/``, ``lvs/``, ``pex/``, each with its ``step.json``, and its record
``instance.json``), or a layout run's from before the steps (``build/<block>/layout/<stamp>/``:
``netlist/``, ``align/``, ``summary.json``); the page is ``page.html`` in it, the CLI's in
``page/``. Its data sit in the page as JSON; the 3-D view loads three.js from jsDelivr when it is
first opened, and draws on a 2-D canvas where a browser has no WebGL.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static" / "page"
# the layers the views draw: the front end, the contacts, every metal and via
DRAWN = re.compile(r"^(OD|PO|CO|M\d+|V\d+)$")
STAMP = re.compile(r"^\d{8}_\d{6}$")


# =============================================================================
# The steps' statistics
# =============================================================================


def subcircuits(text: str) -> dict[str, dict[str, Any]]:
    """A SPICE netlist's subcircuits by name (lowercase), in order: each one's ports and its element
    lines (continuations joined, comments dropped)."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        elif raw.strip() and not raw.lstrip().startswith("*"):
            lines.append(raw.strip())
    found: dict[str, dict[str, Any]] = {}
    current = None
    for line in lines:
        fields = line.split()
        head = fields[0].lower()
        if head == ".subckt":
            current = found[fields[1].lower()] = {"name": fields[1], "ports": fields[2:], "elements": []}
        elif head.startswith(".ends"):
            current = None
        elif current is not None and not head.startswith("."):
            current["elements"].append(fields)
    return found


def _model(fields: list[str]) -> str:
    """An element's model or subcircuit: its last field that is not a parameter."""
    return next(field for field in reversed(fields[1:]) if "=" not in field)


def _nets(fields: list[str]) -> list[str]:
    """An element's nets: a subcircuit instance's fields before its subcircuit, a transistor's
    four, a two-terminal element's two."""
    kind = fields[0][0].lower()
    if kind == "x":
        return [field for field in fields[1:] if "=" not in field][:-1]
    return fields[1:5] if kind == "m" else fields[1:3]


def netlist_stats(text: str) -> dict[str, Any]:
    """A netlist's statistics: its top subcircuit (the last), its ports and nets, its subcircuits,
    the instances in it, and every leaf it holds when flattened, by kind: transistors by model,
    capacitors, resistors, and the cells it names but does not define (a generator's primitive,
    a library cell)."""
    subs = subcircuits(text)
    if not subs:
        return {"top": None}
    top = list(subs.values())[-1]
    nets = {port.lower() for port in top["ports"]}
    for fields in top["elements"]:
        nets |= {net.lower() for net in _nets(fields)}
    leaves: Counter[str] = Counter()

    def flatten(sub: dict[str, Any], times: int, depth: int = 0) -> None:
        for fields in sub["elements"]:
            kind = fields[0][0].lower()
            if kind == "x":
                child = subs.get(_model(fields).lower())
                if child is not None and depth < 32:
                    flatten(child, times, depth + 1)
                else:
                    leaves[f"cell {_model(fields)}"] += times
            elif kind == "m":
                leaves[f"MOS {_model(fields)}"] += times
            elif kind in "cr":
                leaves[{"c": "capacitor", "r": "resistor"}[kind]] += times
            else:
                leaves[f"element {kind.upper()}"] += times

    flatten(top, 1)
    return {
        "top": top["name"],
        "ports": len(top["ports"]),
        "nets": len(nets),
        "subcircuits": len(subs),
        "instances": len(top["elements"]),
        "leaves": dict(sorted(leaves.items(), key=lambda item: (-item[1], item[0]))),
        "lines": len(text.splitlines()),
    }


def drc_stats(signoff: Path) -> dict[str, Any] | None:
    """DRC's findings (``drc_violations.json``): its checker, the violations by rule, the waived."""
    path = signoff / "drc_violations.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    rules = dict(sorted(data.get("violations", {}).items(), key=lambda item: (-item[1], item[0])))
    return {
        "checker": data.get("checker"),
        "rules": rules,
        "total": sum(rules.values()),
        "waived": data.get("waived", {}),
    }


def calibre_lvs(report: str) -> dict[str, Any]:
    """A Calibre LVS report's comparison: the objects after its transformations, layout against
    source (``rows``: [object, layout, source]), and how many nets and instances it found wrong."""
    rows = []
    section = report.split("NUMBERS OF OBJECTS AFTER TRANSFORMATION", 1)
    kind = ""
    for line in section[1].splitlines() if len(section) == 2 else []:
        text = line.strip()
        if not text or set(text) <= {"-", " "} or text.startswith("Layout"):
            continue
        match = re.match(r"(Ports|Nets|Instances|Total Inst):\s+(\d+)\s+(\d+)\s*\*?\s*(.*)$", text)
        if match:
            kind = match.group(1)
            label = f"Instances: {match.group(4).strip()}" if kind == "Instances" else kind
            rows.append([label, int(match.group(2)), int(match.group(3))])
            if kind == "Total Inst":
                break
            continue
        match = re.match(r"(\d+)\s+(\d+)\s*\*?\s+(\S.*)$", text)
        if not (match and kind == "Instances"):
            break
        rows.append([f"Instances: {match.group(3).strip()}", int(match.group(1)), int(match.group(2))])
    wrong = {"nets": 0, "instances": 0}
    for key, head in (("nets", "INCORRECT NETS"), ("instances", "INCORRECT INSTANCES")):
        if head in report:
            block = report.split(head, 1)[1].split("*" * 20, 2)[-1]
            block = re.split(r"\n\*{20,}", block, maxsplit=1)[0]
            wrong[key] = len(re.findall(r"^\s{0,4}\d+\s{2,}\S", block, re.MULTILINE))
    return {"rows": rows, "wrong": wrong}


def lvs_stats(signoff: Path, entry: dict[str, Any]) -> dict[str, Any] | None:
    """LVS's verdict (None: not run), its checker, and its comparison: Calibre's objects
    (``calibre_lvs``), or KLayout's mismatches from its database (``mismatches``)."""
    record = next((path for path in (signoff / "row_signoff.json", signoff / "lvs.json") if path.exists()), None)
    if record is None and "lvs_correct" not in entry:
        return None
    data = json.loads(record.read_text()) if record else {}
    correct = data.get("lvs_correct", entry.get("lvs_correct"))
    checker = data.get("lvs_checker") or ("calibre" if (signoff / "lvs.rep").exists() else "")
    out: dict[str, Any] = {"correct": correct, "rows": [], "wrong": None, "checker": checker, "mismatches": []}
    if checker == "calibre" and (signoff / "lvs.rep").exists():
        out.update(calibre_lvs((signoff / "lvs.rep").read_text(errors="replace")))
    elif (
        str(data.get("lvs_report") or "").endswith(".lvsdb") and Path(data["lvs_report"]).exists() and correct is False
    ):
        from flow.layout.signoff import _lvs_findings

        try:
            out["mismatches"] = _lvs_findings(Path(data["lvs_report"]))
        except Exception as error:  # noqa: BLE001 - the verdict stands without them
            out["mismatches"] = [f"(the LVS database did not read: {error})"]
    return out


def _rank(key: str) -> int:
    """A drawn layer's place in the stack, bottom up: OD, PO, CO, M1, V1, M2 ..."""
    front = {"OD": 0, "PO": 1, "CO": 2}
    if key in front:
        return front[key]
    return 2 * int(key[1:]) + (1 if key[0] == "V" else 0) + 1


def layout_stats(align: Path, entry: dict[str, Any], layout: dict[str, Any] | None) -> dict[str, Any]:
    """The layout's statistics: its outline and area, the primitives ALIGN generated for it, and
    the shapes on each drawn layer."""
    width, height = entry.get("cell_um") or (None, None)
    primitives = sorted(
        path.stem
        for path in align.glob("*/2_primitives/*.json")
        if not path.name.endswith(".gds.json") and not path.name.startswith("__")
    )
    layers = sorted((layout or {}).get("layers", []), key=lambda layer: _rank(layer["key"]))
    shapes = {layer["key"]: len(layer["rects"]) // 4 for layer in layers}
    return {
        "width": width,
        "height": height,
        "area": round(width * height, 2) if width and height else None,
        "primitives": len(primitives),
        "shapes": shapes,
        "error": entry.get("error"),
    }


ALIGN_STAGES = ("topology", "primitives", "placement", "routing", "output")
MESSAGE = re.compile(r"^\S+ \S+ (\S+) (ERROR|WARNING) : (.*)$")


def _align_log(log: Path) -> tuple[list[tuple[float, str]], dict[str, int]]:
    """ALIGN's timestamped log, its last attempt (from its last "Reading netlist"): its lines with
    their times (whole seconds), and the line each stage begins at (``topology`` ... ``output``,
    by the lines that mark them: the times alone cannot tell lines within one second apart) and
    the last (``end``)."""
    import datetime

    if not log.exists():
        return [], {}
    lines = log.read_text(errors="replace").splitlines()
    starts = [i for i, line in enumerate(lines) if "Reading netlist" in line]
    lines = lines[starts[-1] :] if starts else lines

    def stamp(line: str) -> float | None:
        try:
            return datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").astimezone().timestamp()
        except ValueError:
            return None

    timed = [(t, line) for line in lines if (t := stamp(line)) is not None]
    if not timed:
        return [], {}

    def first(*marks: str, after: int = 0) -> int | None:
        return next((k for k in range(after, len(timed)) if any(m in timed[k][1] for m in marks)), None)

    primitives = first("Completed topology identification") or 0
    placement = first("Running Place & Route", after=primitives) or primitives
    routing = (
        first("bottom up routing for", "Starting bottom_up routing", "router started", after=placement) or placement
    )
    output = first("OUTPUT gds.json", "OUTPUT json", "OUTPUT error file", after=routing) or len(timed) - 1
    bounds = {"topology": 0, "primitives": primitives, "placement": placement, "routing": routing, "output": output}
    return timed, {**bounds, "end": len(timed) - 1}


def align_stages(log: Path) -> dict[str, float]:
    """ALIGN's own stages' seconds, from its timestamped log (``_align_log``): ``topology``,
    ``primitives``, ``placement``, ``routing``, ``output`` (its results written), ``span`` (the
    log's first line to its last). The log's times are whole seconds."""
    timed, bounds = _align_log(log)
    if not bounds:
        return {}
    marks = [timed[bounds[key]][0] for key in (*ALIGN_STAGES, "end")]
    stages = {key: marks[k + 1] - marks[k] for k, key in enumerate(ALIGN_STAGES)}
    return {**stages, "span": marks[-1] - marks[0]}


def _template(text: str) -> str:
    """A message as its kind: its paths, rectangles, parameter sets and numbers elided."""
    text = re.sub(r"OrderedDict\(\[.*\]\)", "OrderedDict(…)", text)
    text = re.sub(r"\{.*\}", "{…}", text)
    text = re.sub(r"(?:/[^\s,:]+)+", "…", text)
    text = re.sub(r"\[[-\d, ]+\]", "[…]", text)
    text = re.sub(r"\d+", "#", text)
    return text if len(text) <= 140 else text[:139] + "…"


def align_messages(log: Path) -> dict[str, Counter[tuple[str, str]]]:
    """ALIGN's warnings and errors in its log's last attempt, by the stage they came in (as
    ``align_stages``), each kind ((level, "source: message" with its numbers elided)) counted."""
    timed, bounds = _align_log(log)
    found: dict[str, Counter[tuple[str, str]]] = {key: Counter() for key in ALIGN_STAGES}
    if not bounds:
        return found
    for k, (_t, line) in enumerate(timed):
        match = MESSAGE.match(line)
        if not match:
            continue
        stage = [key for key in ALIGN_STAGES if k >= bounds[key]][-1]
        source = match.group(1).rsplit(".", 1)[-1]
        found[stage][(match.group(2).lower(), f"{source}: {_template(match.group(3))}")] += 1
    return found


def constraints(input_dir: Path) -> Counter[str]:
    """The constraints the generator stated, by kind, over every module (ALIGN's input)."""
    found: Counter[str] = Counter()
    for path in input_dir.glob("*/*.const.json"):
        for item in json.loads(path.read_text()):
            found[item.get("constraint", "?")] += 1
    return found


def primitives(work: Path) -> Counter[str]:
    """The primitives ALIGN generated, by generator."""
    index = work / "2_primitives" / "__primitives__.json"
    if not index.exists():
        return Counter()
    found: Counter[str] = Counter()
    for entry in json.loads(index.read_text()).values():
        parameters = entry.get("parameters") or {}
        kind = parameters.get("real_inst_type") if isinstance(parameters, dict) else None
        found[kind or entry.get("primitive") or entry.get("abstract_template_name", "?")] += 1
    return found


def gdscheck(signoff: Path) -> int | None:
    """gdscheck's violations (its log), where it ran."""
    log = signoff / "gdscheck.log"
    if not log.exists():
        return None
    text = log.read_text(errors="replace")
    match = re.search(r"(\d+) violation\(s\)", text)
    return int(match.group(1)) if match else (0 if "DRC clean" in text else None)


# =============================================================================
# The views' data
# =============================================================================


def compact_layout(raw: dict[str, Any]) -> dict[str, Any]:
    """The viewer's layout export (``export.export_layout``) as rectangles in um on the drawn
    layers, a Manhattan polygon cut into rectangles."""
    import klayout.db as kdb

    scale = raw["dbu"]

    def um(value: float) -> float:
        return round(value * scale, 4)

    def boxes(rings: list[list[int]]) -> list[int]:
        points = [kdb.Point(rings[0][i], rings[0][i + 1]) for i in range(0, len(rings[0]), 2)]
        polygon = kdb.Polygon(points)
        for hole in rings[1:]:
            polygon.insert_hole([kdb.Point(hole[i], hole[i + 1]) for i in range(0, len(hole), 2)])
        out: list[int] = []
        for piece in polygon.decompose_trapezoids():
            box = piece.bbox()
            out += [box.left, box.bottom, box.right, box.top]
        return out

    layers = []
    for layer in raw["layers"]:
        if not DRAWN.match(layer["key"]):
            continue
        flat = list(layer["rects"])
        for rings in layer["polys"]:
            flat += boxes(rings)
        layers.append({"key": layer["key"], "rects": [um(v) for v in flat]})
    labels = [
        {"text": label["text"], "x": um(label["x"]), "y": um(label["y"])}
        for label in raw.get("labels", [])
        if label["layer"].endswith(".PIN") or DRAWN.match(label["layer"])
    ]
    return {"cell": raw["cell"], "bbox": [um(v) for v in raw["bbox"]], "layers": layers, "labels": labels}


def schematic_svg(netlist: Path) -> tuple[str | None, str | None]:
    """The netlist's schematic (``flow.util.netlist2image``: a transistor-level cell's devices, a
    block's chains of cells), as SVG text, and its top subcircuit's name; (None, top) where none is
    drawn."""
    from flow.util.netlist2image import render

    names = [line.split()[1] for line in netlist.read_text().splitlines() if line.lower().startswith(".subckt")]
    top = names[-1] if names else None
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "schematic.svg"
        try:
            render(netlist, out)
        except Exception:  # noqa: BLE001 - a netlist the renderer cannot draw: the page goes without
            return None, top
        return (out.read_text() if out.exists() else None), top


# =============================================================================
# The page
# =============================================================================


def _seconds(entry: dict[str, Any], key: str) -> float | None:
    return (entry.get("seconds") or {}).get(key)


def _sum(*values: float | None) -> float | None:
    found = [value for value in values if value is not None]
    return round(sum(found), 1) if found else None


def _table(title: str, head: list[str], counts: dict[str, int] | Counter[str]) -> list[dict]:
    rows = [[key, value] for key, value in counts.items()]
    return [{"title": title, "head": head, "rows": rows}] if rows else []


def _messages(found: Counter[tuple[str, str]]) -> tuple[list, list[dict]]:
    """A stage's ALIGN messages: facts (its errors and warnings counted) and their table."""
    if not found:
        return [], []
    errors = sum(n for (level, _), n in found.items() if level == "error")
    rows = [[level, text, n] for (level, text), n in sorted(found.items(), key=lambda item: (item[0][0], -item[1]))]
    facts = [["ALIGN errors", errors or None], ["ALIGN warnings", (sum(found.values()) - errors) or None]]
    return facts, [{"title": "ALIGN's messages", "head": ["Level", "Message", "Count"], "rows": rows, "align": "llr"}]


def _counted(found: Counter[tuple[str, str]]) -> str:
    """ALIGN's messages counted for the console: "3 errors and 12 warnings from ALIGN"."""
    errors = sum(n for (level, _), n in found.items() if level == "error")
    parts = [
        f"{n} {kind}{'s' if n != 1 else ''}"
        for kind, n in (("error", errors), ("warning", sum(found.values()) - errors))
        if n
    ]
    return " and ".join(parts) + " from ALIGN" if parts else ""


def steps(
    folders: dict[str, Path], entry: dict[str, Any], netlist_text: str, layout: dict | None, about: dict
) -> list[dict]:
    """The pipeline's steps in order, each its state (ok, bad, or none where it did not run), run
    time, facts ([label, value]) and tables ({title, head, rows}): the parameters, the record's
    metrics, the netlist, the constraints, ALIGN's own stages (topology, primitives, placement,
    routing), the GDS, DRC, LVS, PEX. ``folders``: ALIGN's (``align``), DRC's and LVS's."""
    align = folders["align"]
    signoff = folders["drc"]
    works = [path.parent for path in align.glob("*/LOG")]
    work = works[0] if works else align / "none"
    build_path = work / "build.json"
    build = json.loads(build_path.read_text()) if build_path.exists() else {}
    last = (build.get("attempts") or [{}])[-1]
    stages = align_stages(work / "LOG" / "align.log")
    said = align_messages(work / "LOG" / "align.log")
    ran = entry.get("gds") is not None
    out = []

    def step(
        key: str,
        title: str,
        state: str,
        seconds: float | None,
        facts: list,
        tables: list | None = None,
        brief: str = "",
    ) -> None:
        """A step; on one of ALIGN's stages (the GDS: its output), ALIGN's messages there too, its
        state "warn" where it had some."""
        facts, tables = list(facts), list(tables or [])
        found = said.get("output" if key == "gds" else key)
        if found:
            more_facts, more_tables = _messages(found)
            facts, tables = facts + more_facts, tables + more_tables
            state = "warn" if state == "ok" else state
            brief = ", ".join(part for part in (brief, _counted(found)) if part)
        out.append(
            {
                "key": key,
                "title": title,
                "state": state,
                "seconds": seconds,
                "facts": facts,
                "tables": tables,
                "brief": brief,
            }
        )

    params = [
        [name, value if not isinstance(value, (dict, list)) else json.dumps(value)]
        for name, value in about["params"].items()
    ]
    step(
        "parameters", "Parameters", "ok", _seconds(entry, "parameters"),
        [["Block", about["block"]], ["PDK", about["pdk"]], ["Instance", about["name"]], ["Run", about["run"]]],
        [{"title": "Parameters", "head": ["Parameter", "Value"], "rows": params}] if params else [],
        f"{len(params)} parameters",
    )  # fmt: skip

    metrics = [[name, value] for name, value in about.get("metrics", {}).items()]
    step(
        "record", "Record", "ok" if metrics else "none", about.get("seconds"),
        [["Metrics", len(metrics) or None]],
        [{"title": "Metrics", "head": ["Metric", "Value"], "rows": metrics}] if metrics else [],
        f"{len(metrics)} metrics" if metrics else "",
    )  # fmt: skip

    stats = netlist_stats(netlist_text)
    step(
        "netlist", "Netlist", "ok" if stats["top"] else "none", _seconds(entry, "netlist"),
        [["Top cell", stats["top"]], ["Ports", stats.get("ports")], ["Nets", stats.get("nets")],
         ["Instances", stats.get("instances")], ["Subcircuits", stats.get("subcircuits")], ["Lines", stats.get("lines")]],
        _table("Leaves, flattened", ["Leaf", "Count"], stats.get("leaves", {})),
        f"{stats.get('instances')} instances, {stats.get('nets')} nets" if stats["top"] else "",
    )  # fmt: skip

    stated = constraints(align / "input")
    step(
        "constraints", "Constraints", "ok" if stated else "none", _sum(_seconds(entry, "floorplan"), build.get("input")),
        [["Constraints", sum(stated.values()) or None], ["Kinds", len(stated) or None]],
        _table("Stated, by kind", ["Constraint", "Count"], dict(stated.most_common())),
        f"{sum(stated.values())} constraints" if stated else "",
    )  # fmt: skip

    modules = []
    topology = work / "1_topology"
    for path in topology.glob("*.verilog.json"):
        modules += json.loads(path.read_text()).get("modules", [])
    step(
        "topology", "Topology", "ok" if modules else "none", stages.get("topology"),
        [["Modules", len(modules) or None], ["Instances", sum(len(m.get("instances", [])) for m in modules) or None]],
        [{"title": "Modules", "head": ["Module", "Instances", "Constraints"],
          "rows": [[m["name"], len(m.get("instances", [])), len(m.get("constraints", []))] for m in modules]}] if modules else [],
        f"{len(modules)} modules" if modules else "",
    )  # fmt: skip

    made = primitives(work)
    step(
        "primitives", "Primitives", "ok" if made else "none", stages.get("primitives"),
        [["Primitives", sum(made.values()) or None]],
        _table("Generated, by generator", ["Generator", "Count"], dict(made.most_common())),
        f"{sum(made.values())} primitives" if made else "",
    )  # fmt: skip

    placed = [path for path in (work / "3_pnr").glob("*_0.json")]
    step(
        "placement", "Placement", "ok" if placed else "none", stages.get("placement"),
        [["Nodes placed", len(placed) or None]],
        brief=f"{len(placed)} nodes" if placed else "",
    )  # fmt: skip

    step("routing", "Routing", "ok" if placed else "none", stages.get("routing"), [])

    lay = layout_stats(align, entry, layout)
    gds_post = work / f"{work.name}.gds.post.json"
    done = json.loads(gds_post.read_text()) if gds_post.exists() else {}
    overhead = (last.get("align") or 0) - stages["span"] if stages and last.get("align") else None
    step(
        "gds", "GDS", "ok" if ran else ("bad" if lay["error"] else "none"),
        _sum(stages.get("output"), overhead, last.get("post")),
        [["Outline", f"{lay['width']:g} × {lay['height']:g} µm" if lay["width"] else None],
         ["Area", f"{lay['area']:g} µm²" if lay["area"] else None],
         ["ALIGN output, start-up", f"{_sum(stages.get('output'), overhead)} s" if stages else None],
         ["Post step", f"{last['post']} s" if last.get("post") is not None else None],
         *[[key.capitalize(), value] for key, value in done.items()],
         *([["Error", lay["error"]]] if lay["error"] else [])],
        _table("Shapes by layer", ["Layer", "Rectangles"], lay["shapes"]),
        ", ".join(part for part in (f"{lay['width']:g} × {lay['height']:g} µm" if lay["width"] else "",
                                    f"{done['shield ties']} shield ties" if done.get("shield ties") else "") if part),
    )  # fmt: skip

    drc = drc_stats(signoff)
    pre = gdscheck(signoff)
    if drc is None and pre is None:
        step("drc", "DRC", "none", None, [])
    else:
        drc = drc or {"checker": None, "rules": {}, "total": 0, "waived": {}}
        precheck = not str(drc["checker"]).startswith("gdscheck") and pre is not None
        step(
            "drc", "DRC", "ok" if drc["total"] == 0 and not pre else "bad", _seconds(entry, "drc"),
            [*([["gdscheck (precheck)", f"{pre} violations"]] if precheck else []),
             ["Checker", drc["checker"]], ["Violations", drc["total"]], ["Rules violated", len(drc["rules"])],
             *([["Waived", sum(drc["waived"].values())]] if drc["waived"] else [])],
            _table("Violations by rule", ["Rule", "Count"], drc["rules"]),
            f"{drc['total']} violations ({drc['checker']}" + (f"; gdscheck precheck {pre}" if precheck else "") + ")",
        )  # fmt: skip

    lvs = lvs_stats(folders["lvs"], entry)
    if lvs is None or lvs["correct"] is None:
        step("lvs", "LVS", "none", _seconds(entry, "lvs"), [["Checker", lvs and lvs.get("checker") or None]],
             brief="not run: no LVS deck for these checkers" if lvs else "")  # fmt: skip
    else:
        rows = [[name, layout_n, source_n] for name, layout_n, source_n in lvs["rows"]]
        tables = [{"title": "Objects compared", "head": ["Object", "Layout", "Source"], "rows": rows}] if rows else []
        if lvs["mismatches"]:
            tables.append(
                {
                    "title": "Mismatches",
                    "head": ["Mismatch"],
                    "rows": [[line] for line in lvs["mismatches"][:200]],
                    "align": "l",
                }
            )
        step(
            "lvs", "LVS", "ok" if lvs["correct"] else "bad", _seconds(entry, "lvs"),
            [["Checker", lvs.get("checker")], ["Result", "match" if lvs["correct"] else "no match"],
             *([["Nets wrong", lvs["wrong"]["nets"]], ["Instances wrong", lvs["wrong"]["instances"]]] if lvs["wrong"] else []),
             *([["Mismatches", len(lvs["mismatches"])]] if lvs["mismatches"] else [])],
            tables,
            ("match" if lvs["correct"] else "no match") + (f" ({lvs['checker']})" if lvs.get("checker") else ""),
        )  # fmt: skip

    pex = entry.get("pex")
    if not pex:
        step("pex", "PEX", "none", None, [])
    elif pex.get("skipped"):
        step("pex", "PEX", "none", None, [["Skipped", pex["skipped"]]], brief=f"not run: {pex['skipped']}")
    elif pex.get("error"):
        step("pex", "PEX", "bad", _seconds(entry, "pex"), [["Error", pex["error"][:300]]], brief="failed")
    else:
        nets = pex.get("nets", {})
        largest = [[net, f"{value * 1e15:.4g}"] for net, value in list(nets.items())[:20]]
        step(
            "pex", "PEX", "ok", _seconds(entry, "pex"),
            [["Extractor", pex.get("extractor")], ["Nets", len(nets)], ["Capacitors", pex.get("capacitors")],
             ["Total (fF)", f"{pex.get('total_f', 0.0) * 1e15:.4g}"]],
            [{"title": "Largest nets: each one's capacitance to everything else (fF)", "head": ["Net", "C (fF)"],
              "rows": largest, "align": "l"}] if largest else [],
            f"{len(nets)} nets, {pex.get('total_f', 0.0) * 1e15:.4g} fF ({pex.get('extractor')})",
        )  # fmt: skip
    return out


def _stepped(instance_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    """A run's instance's layout as a layout run's summary entry (``page``'s): the layout step's GDS
    and size, the drc, lvs and pex steps' findings, each one's seconds, the layout's error; and the
    steps' folders. Each from its ``step.json``, a step that ended without error."""

    def ended(step: str) -> dict[str, Any]:
        path = instance_dir / step / "step.json"
        found = json.loads(path.read_text()) if path.exists() else {}
        return found if found.get("error") is None else {"error": found["error"]}

    laid, drc, lvs, pex = (ended(step) for step in ("layout", "drc", "lvs", "pex"))
    seconds = {**laid.get("parts", {}), **{step: ended(step).get("seconds") for step in ("drc", "lvs", "pex")}}
    entry: dict[str, Any] = {
        "gds": laid.get("gds"),
        "cell_um": laid.get("cell_um"),
        "seconds": {key: value for key, value in seconds.items() if value is not None},
        "error": laid.get("error"),
        **({"lvs_correct": lvs["lvs_correct"]} if "lvs_correct" in lvs else {}),
        **({"pex": pex} if pex else {}),
    }
    folders = {"align": instance_dir / "layout" / "align", "drc": instance_dir / "drc", "lvs": instance_dir / "lvs"}
    if "drc_violations.json" not in {path.name for path in folders["drc"].glob("*.json")} and drc.get("report"):
        folders["drc"] = Path(drc["report"]).parent  # the DRC its own lay_out ran
    if lvs.get("lvs_checker") == "lay_out" and lvs.get("lvs_report"):
        folders["lvs"] = Path(lvs["lvs_report"]).parent
    return entry, folders


def page(instance_dir: Path, out: Path | None = None) -> Path:
    """The page of the instance in ``instance_dir`` (a run's ``<pdk>/<name>/``, or a layout run's
    from before the steps), written to ``out`` (default ``instance_dir/page.html``)."""
    from flow.web.export import export_layout

    instance_dir = instance_dir.resolve()
    record_path = instance_dir / "instance.json"
    if not record_path.exists() and (instance_dir.parents[1] / "instance.json").exists():
        record_path = instance_dir.parents[1] / "instance.json"  # a sweep run's: <id>/layout/<flow>/
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    if (instance_dir / "summary.json").exists():  # a layout run's from before the steps
        key, entry = next(iter(json.loads((instance_dir / "summary.json").read_text()).items()))
        pdk = key.split("/")[0]
        folders = {"align": instance_dir / "align", "drc": instance_dir / "align" / "signoff"}
        folders["lvs"] = folders["drc"]
        netlists = sorted((instance_dir / "netlist").glob("*.sp"))
    else:
        entry, folders = _stepped(instance_dir)
        pdk = record.get("pdk") or instance_dir.parent.name
        netlists = [
            *sorted((instance_dir / "layout" / "netlist").glob("*.sp")),
            *sorted((instance_dir / "netlist").glob("*.cdl")),
        ]
    netlist = next(iter(netlists), None)
    netlist_text = netlist.read_text() if netlist else ""

    layout = None
    if entry.get("gds") and Path(entry["gds"]).exists():
        with tempfile.TemporaryDirectory() as folder:
            raw_path = Path(folder) / "layout.json"
            export_layout(entry["gds"], pdk, str(raw_path))
            layout = compact_layout(json.loads(raw_path.read_text()))
    svg, schematic_of = schematic_svg(netlist) if netlist else (None, None)

    parts = instance_dir.parts  # build/<block>/layout/<stamp>/...: the block before "layout"
    block = record.get("block") or (parts[parts.index("layout") - 1] if "layout" in parts else instance_dir.name)
    run = instance_dir.parents[1]
    stamp = next((part for part in instance_dir.parts if STAMP.match(part)), run.name)
    name = record.get("name") or record_path.parent.name  # the instance's directory: its name or digest
    about = {
        "block": block,
        "pdk": pdk,
        "name": name,
        "run": stamp,
        "params": record.get("params", {}),
        "metrics": {key: value for key, value in record.get("metrics", {}).items() if not isinstance(value, dict)},
        "seconds": record.get("seconds"),
    }
    data = {**about, "steps": steps(folders, entry, netlist_text, layout, about), "schematic_of": schematic_of}

    template = (STATIC / "page.html").read_text()
    script = (STATIC / "page.js").read_text()
    html = template.replace("{{TITLE}}", _escape(f"{block} {name}"))
    html = html.replace("/*PAGE*/{}", _json(data)).replace("/*LAYOUT*/null", _json(layout))
    html = html.replace('/*NETLIST*/""', _json(netlist_text)).replace('/*SCHEMATIC*/""', _json(svg or ""))
    html = html.replace("/*SCRIPT*/", script)
    out = out or instance_dir / "page.html"
    out.write_text(html)
    (out.parent / "steps.json").write_text(json.dumps(data["steps"], indent=1, ensure_ascii=False) + "\n")
    return out


def _json(value: Any) -> str:
    """JSON for a ``<script type="application/json">`` block: no ``</`` to close it early."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
