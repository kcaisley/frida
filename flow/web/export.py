"""The views the viewer's pages read beside the sweep tables (``flow.sweep``): a layout flattened
onto its PDK's generic layer keys (``OD``, ``PO``, ``CO``, ``M1``, ``V1`` ...: ``layout/tech.py``'s
``LAYERS``), merged per layer and written with its labels; a netlist's transistor schematic
(``flow.util.netlist2image``); the index of an instance's waveform measurements, and one record of
them, read from its HDF5 file when the server is asked for it."""

from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Iterable
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "build/web/data"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
# block -> title
BLOCKS = {
    "adc": "SAR ADC (behavioral)",
    "comp": "Comparator",
    "samp": "Sampling switch",
    "capdac": "Capacitive DAC",
    "latch": "Latches and flip-flops",
    "delay": "Delay lines and rings",
    "clkgen": "Clock generator",
    "cml": "Current-mode logic",
    "pi": "Phase interpolator",
    "lvshift": "Level shifter",
    "schmitt": "Schmitt trigger",
    "ota": "OTA",
    "follower": "Source follower",
    "ringamp": "Ring amplifier",
    "csa": "Charge-sensitive amplifier",
    "disc": "Discriminator",
    "idac": "Current source",
    "bias": "Cascode bias",
}
# block -> the parameter that is its topology, which the scatter marks a point by (its colour is the
# PDK's): the sampling switch's kind, the comparator's latch, the DAC's redundancy scheme, the
# converter's DAC scheme. A block not named here: its first parameter that is an enumeration's
# member (``topology``).
TOPOLOGY = {"samp": "switch_type", "comp": "latch", "capdac": "redundancy", "adc": "cdac.redundancy"}
# 2-D records longer than this are thinned to it for the browser (every k-th sample)
MAX_SAMPLES = 1600


def json_value(value):
    """A JSON-ready copy of an analysis or parameter value: arrays as nested lists of floats at
    six significant digits (NaN and infinities as null), enums by name, dataclasses as dicts."""

    if isinstance(value, np.ndarray):
        if value.dtype == bool:
            return value.tolist()
        if not np.issubdtype(value.dtype, np.number) or value.ndim > 2:
            return None
        if value.ndim == 2 and value.shape[1] > MAX_SAMPLES:
            value = value[:, thinned(value.shape[1])]
        elif value.ndim == 1 and len(value) > MAX_SAMPLES:
            value = value[thinned(len(value))]
        if np.issubdtype(value.dtype, np.integer):
            return value.tolist()
        rows = value.reshape(-1, value.shape[-1]) if value.ndim else value.reshape(1, 1)
        out = [[float(f"{v:.6g}") if math.isfinite(v) else None for v in row] for row in rows.tolist()]
        return out if value.ndim == 2 else out[0] if value.ndim == 1 else out[0][0]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return float(f"{value:.6g}") if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.name
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def topology(block: str, rows: list[dict[str, Any]], varying: list[str]) -> str | None:
    """The parameter a table's scatter marks its points by: the block's topology (``TOPOLOGY``), else
    its first parameter whose every value is a name (an enumeration's member, upper case), where it
    differs between the rows (``varying``); None where none does."""
    named = TOPOLOGY.get(block)
    if named is not None:
        return named if named in varying else None
    for name in varying:
        values = [row["params"].get(name) for row in rows]
        if all(isinstance(value, str) and value.isupper() for value in values):
            return name
    return None


def thinned(length: int) -> np.ndarray:
    """Indices of at most ``MAX_SAMPLES`` evenly spread samples, both ends kept."""
    return np.unique(np.linspace(0, length - 1, MAX_SAMPLES).round().astype(int))


def measurement_wave(measurement):
    """A measurement's waveforms as records (``flow.pipeline.Wave``): its own, or a pipeline
    measurement's signals on the simulator's time axis as one record; None without."""

    from flow.pipeline import Wave

    wave = getattr(measurement, "wave", None)
    time_s = getattr(measurement, "time_s", None)
    if wave is not None or time_s is None or len(time_s) < 2:
        return wave
    # the simulator may repeat a time point at a breakpoint: the first of each kept
    keep = np.concatenate(([True], np.diff(time_s) > 0))
    return Wave(
        record_index=np.zeros(1, dtype=np.int64),
        time_s=time_s[keep],
        v={name: values[keep][None, :] for name, values in measurement.v.items()},
        i={name: values[keep][None, :] for name, values in measurement.i.items()},
    )


def wave_entry(path: Path, measurement, *, root: Path = ROOT) -> dict | None:
    """A measurement's waveforms in the traces index: its PDK, case and sweep (from the path:
    ``<pdk>/<case>/<sweep>/...``), its bench parameters, its nets and time span; None without."""

    wave = measurement_wave(measurement)
    if wave is None:
        return None
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    parts = relative.parts
    places = [index for index, part in enumerate(parts[:-1]) if part in PDKS]
    if not places:
        return None
    at = places[-1]
    param = json_value(getattr(measurement, "param", None))
    return {
        "pdk": parts[at],
        "case": parts[at + 1] if at + 2 < len(parts) else "",
        "sweep": parts[at + 2] if at + 3 < len(parts) else "",
        "path": str(relative),
        "params": {
            name: value
            for name, value in (param.items() if isinstance(param, dict) else ())
            if value is None or isinstance(value, (bool, int, float, str))
        },
        "records": len(wave.record_index),
        "samples": len(wave.time_s),
        "t": [json_value(float(wave.time_s[0])), json_value(float(wave.time_s[-1]))],
        "v": sorted(wave.v),
        "i": sorted(wave.i),
    }


def read_wave(relative: str, record: int = 0, *, root: Path = ROOT) -> dict:
    """One record of a cached measurement's waveforms, for the traces view: time and every node
    voltage and supply current, every sample (the view draws a column of min and max per pixel,
    so a zoom shows the samples the simulator wrote). Only HDF5 files under ``root/build`` are
    read."""

    from flow.analysis.io import read_measurement

    path = (root / relative).resolve()
    if path.suffix != ".h5" or not path.is_relative_to((root / "build").resolve()):
        raise ValueError(f"{relative} is not a cached measurement")
    wave = measurement_wave(read_measurement(path))
    if wave is None:
        raise ValueError(f"{relative} holds no waveforms")
    if not 0 <= record < len(wave.record_index):
        raise ValueError(f"{relative} has no record {record}")

    def trace(values: np.ndarray) -> list:  # not json_value: that thins to MAX_SAMPLES
        return [float(f"{value:.6g}") if math.isfinite(value) else None for value in values[record].tolist()]

    return {
        "path": relative,
        "record": record,
        "records": len(wave.record_index),
        # the measurement file's size, which the traces view states beside what it draws
        "file_bytes": path.stat().st_size,
        "samples": len(wave.time_s),
        "time_s": [float(f"{value:.10g}") for value in wave.time_s.tolist()],
        "v": {name: trace(values) for name, values in sorted(wave.v.items())},
        "i": {name: trace(values) for name, values in sorted(wave.i.items())},
    }


def trace_index(waves: Iterable[dict]) -> dict:
    """The waveform measurements per PDK and case, each sweep's points named by the bench
    parameters that differ between them."""

    groups: dict[tuple[str, str, str], list[dict]] = {}
    for entry in waves:
        key = entry["pdk"], entry["case"], entry["sweep"]
        if all(other["path"] != entry["path"] for other in groups.get(key, [])):
            groups.setdefault(key, []).append(entry)
    index: dict = {}
    for (pdk, case, _sweep), entries in groups.items():
        names = list(dict.fromkeys(name for entry in entries for name in entry["params"]))
        varying = [name for name in names if len({json.dumps(entry["params"].get(name)) for entry in entries}) > 1]
        for entry in sorted(entries, key=lambda item: [json.dumps(item["params"].get(name)) for name in varying]):
            entry["point"] = {name: entry["params"].get(name) for name in varying}
            entry.pop("params")
            entry.pop("pdk")
            entry.pop("case")
            index.setdefault(pdk, {}).setdefault(case, []).append(entry)
    return index


# =============================================================================
# Layouts and schematics
# =============================================================================


def export_layout(gds: str, pdk: str, out: str) -> dict:
    """Flatten one layout onto the PDK's generic layer keys, merge each layer and write its
    rectangles, polygons and labels (database units) as JSON; the layers and the bounding box."""

    import klayout.db as kdb

    tech = import_module(f"pdk.{pdk}.layout.tech")
    keys = {tuple(number): key for key, number in tech.LAYERS.items() if number}
    keys.update({tuple(number): f"{key}.PIN" for key, number in getattr(tech, "PIN_TEXT", {}).items()})
    layout = kdb.Layout()
    layout.read(gds)
    stem = Path(gds).stem
    top = next((cell for cell in layout.top_cells() if cell.name.lower() == stem.lower()), layout.top_cells()[0])
    layers, labels = {}, []
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        key = keys.get((info.layer, info.datatype))
        if key is None:
            continue
        for text in kdb.Texts(top.begin_shapes_rec(index)).each():
            point = text.position()
            labels.append({"text": text.string, "layer": key, "x": point.x, "y": point.y})
        region = kdb.Region(top.begin_shapes_rec(index)).merged()
        if region.is_empty():
            continue
        shapes = layers.setdefault(key, {"key": key, "rects": [], "polys": []})
        for polygon in region.each():
            if polygon.is_box():
                box = polygon.bbox()
                shapes["rects"] += [box.left, box.bottom, box.right, box.top]
            else:
                rings = [[c for point in polygon.each_point_hull() for c in (point.x, point.y)]]
                rings += [
                    [c for point in polygon.each_point_hole(hole) for c in (point.x, point.y)]
                    for hole in range(polygon.holes())
                ]
                shapes["polys"].append(rings)
    box = top.bbox()
    record = {
        "cell": stem,
        "pdk": pdk,
        "dbu": layout.dbu,
        "bbox": [box.left, box.bottom, box.right, box.top],
        "layers": list(layers.values()),
        "labels": labels,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(record, separators=(",", ":")))
    return {"layers": sorted(layers), "bbox_um": [round(c * layout.dbu, 4) for c in record["bbox"]]}


def export_schematic(netlist: str, out: str) -> str:
    """The netlist's transistor schematic as SVG (``flow.util.netlist2image``)."""

    from flow.util.netlist2image import render

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    render(Path(netlist), Path(out))
    return out


# =============================================================================
# An instance's steps: the story of its run through the pipeline
# =============================================================================

# a DRC rule's markers exported at most (its count is whole)
MAX_MARKERS = 100
# what a step's view leaves out of its step.json: its record of the run, kept apart, and its files
_RUN_KEYS = ("step", "finished", "seconds", "error", "log")


def _subcircuits(text: str) -> dict[str, dict[str, Any]]:
    """A SPICE netlist's subcircuits by name (lowercase), in order: each one's ports and its element
    lines (continuations joined, comments dropped)."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        elif raw.strip() and not raw.lstrip().startswith("*"):
            lines.append(raw.strip())
    found: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
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


def netlist_stats(text: str) -> dict[str, Any]:
    """A netlist's statistics: its top subcircuit (the last), its ports and nets, its subcircuits,
    the instances in it, and every leaf it holds when flattened, by kind (transistors by model,
    capacitors, resistors, the cells it names but does not define)."""
    subs = _subcircuits(text)
    if not subs:
        return {"top": None}
    top = list(subs.values())[-1]

    def model(fields: list[str]) -> str:  # an element's model or subcircuit: its last bare field
        return next(field for field in reversed(fields[1:]) if "=" not in field)

    def nets(fields: list[str]) -> list[str]:
        kind = fields[0][0].lower()
        if kind == "x":
            return [field for field in fields[1:] if "=" not in field][:-1]
        return fields[1:5] if kind == "m" else fields[1:3]

    named = {port.lower() for port in top["ports"]}
    for fields in top["elements"]:
        named |= {net.lower() for net in nets(fields)}
    leaves: dict[str, int] = {}

    def flatten(sub: dict[str, Any], depth: int = 0) -> None:
        for fields in sub["elements"]:
            kind = fields[0][0].lower()
            child = subs.get(model(fields).lower()) if kind == "x" else None
            if child is not None and depth < 32:
                flatten(child, depth + 1)
                continue
            leaf = {"x": f"cell {model(fields)}", "m": f"MOS {model(fields)}", "c": "capacitor", "r": "resistor"}
            key = leaf.get(kind, f"element {kind.upper()}")
            leaves[key] = leaves.get(key, 0) + 1

    flatten(top)
    return {
        "top": top["name"],
        "ports": len(top["ports"]),
        "nets": len(named),
        "subcircuits": len(subs),
        "instances": len(top["elements"]),
        "leaves": dict(sorted(leaves.items(), key=lambda item: (-item[1], item[0]))),
    }


def _relative(path, root: Path) -> str | None:
    """A path a step names, from the repository's root where it is under it."""
    if not path:
        return None
    path = Path(path)
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def steps_view(folder: Path, record: dict[str, Any], *, root: Path = ROOT) -> list[dict[str, Any]] | None:
    """The instance's steps in their order (``flow.steps.Step``: netlist, sim, circuit where it ran,
    layout, drc, lvs, pex, pexsim, record), each as the viewer tells it: its state (``ok``; ``failed`` with its error;
    ``rejected``: the step after which the run's bounds rejected the design, with the bounds it
    missed; ``skipped`` with why; ``not run`` with why), when it finished, its seconds, its log's
    warnings and errors by tool (``counts``) and its log's path, what it established for the bounds
    (``metrics``) and its outputs, paths from the repository's root; DRC's violations by rule, LVS's
    mismatches where it found some, the netlist's statistics and size. None for an instance of a run
    from before steps kept their own records (no ``step.json``): its record alone tells its story.
    A record whose failure no step recorded (a run from before the record step) fails that step."""
    from flow.steps import Step

    ended = {}
    for step in Step:
        path = folder / str(step) / "step.json"
        if path.exists():
            try:
                ended[step] = json.loads(path.read_text())
            except ValueError:  # a step.json being written
                continue
    if not ended:
        return None
    if Step.RECORD not in ended and record.get("error"):
        ended[Step.RECORD] = {"step": "record", "finished": None, "seconds": None, "error": record["error"]}
    rejected = record.get("rejected") or None
    rejected_at = (
        Step[rejected["step"].upper()] if rejected and rejected.get("step", "").upper() in Step.__members__ else None
    )
    failed: list[Step] = []
    out = []
    for step in Step:
        if step in (Step.FIGURES, Step.TABLE) or (step is Step.CIRCUIT and step not in ended):
            continue
        entry = ended.get(step)
        view: dict[str, Any] = {"step": str(step)}
        if entry is None:
            if rejected_at is not None and step.value > rejected_at.value and step is not Step.RECORD:
                why = f"rejected at {rejected_at}"
            elif failed and set(failed) & (step.required - {step}):
                why = f"after {next(str(s) for s in failed if s in step.required)} failed"
            else:
                why = "not run in this run"
            out.append({**view, "state": "not run", "why": why})
            continue
        outputs = {key: value for key, value in entry.items() if key not in _RUN_KEYS}
        for key, value in outputs.items():
            if isinstance(value, str) and value.startswith("/") and Path(value).exists():
                outputs[key] = _relative(value, root)
        view.update(
            finished=entry.get("finished"),
            seconds=entry.get("seconds"),
            counts=entry.get("log") or {},
            log_file=_relative(folder / str(step) / "step.log", root)
            if (folder / str(step) / "step.log").exists()
            else None,
            metrics=outputs.pop("metrics", None) or {},
            outputs=outputs,
        )
        if entry.get("error"):
            failed.append(step)
            view.update(state="failed", error=entry["error"])
        elif outputs.get("skipped"):
            view.update(state="skipped", why=outputs["skipped"])
        elif step is rejected_at:
            view.update(state="rejected", rejected=rejected)
        else:
            view["state"] = "ok"
        if rejected_at is not None and step.value > rejected_at.value and step is not Step.RECORD:
            view["note"] = f"made before the design was rejected at {rejected_at}"
        out.append(view | _step_extras(step, folder, view))
    return out


def _step_extras(step, folder: Path, view: dict[str, Any]) -> dict[str, Any]:
    """What a step's view adds beside its step.json: the netlist's statistics and size, the GDS's
    size, DRC's violations by rule and the rules it checked, LVS's devices by class on each side and
    its mismatches (a KLayout database that did not match)."""
    from flow.steps import Step

    extras: dict[str, Any] = {}
    if step is Step.LAYOUT:
        gds = view["outputs"].get("gds")
        if gds and (ROOT / gds).is_file():
            extras["gds_bytes"] = (ROOT / gds).stat().st_size
    if step is Step.NETLIST:
        netlist = next(iter(sorted((folder / "netlist").glob("*.cdl"))), None)
        if netlist is not None:
            extras["netlist"] = netlist_stats(netlist.read_text(errors="replace"))
        geometry = folder / "netlist" / "geometry.json"
        if geometry.exists():
            extras["geometry"] = json.loads(geometry.read_text())
    elif step is Step.DRC:
        report = folder / "drc" / "drc_violations.json"
        if report.exists():
            found = json.loads(report.read_text())
            extras["rules"] = dict(sorted(found.get("violations", {}).items(), key=lambda item: (-item[1], item[0])))
            extras["waived"] = found.get("waived") or {}
        extras["markers"] = drc_markers(folder / "drc", view["outputs"].get("top") or "")
        extras["checked"] = drc_checked(folder / "drc")
    elif step is Step.LVS:
        report = view["outputs"].get("lvs_report")
        if report and str(report).endswith(".lvsdb") and (ROOT / report).exists():
            extras["devices"] = lvs_devices(ROOT / report)
            if view["outputs"].get("lvs_correct") is False:
                from flow.layout.signoff import _lvs_findings

                try:
                    extras["mismatches"] = _lvs_findings(ROOT / report)[:200]
                except Exception as error:  # noqa: BLE001 - the verdict stands without them
                    extras["mismatches"] = [f"(the LVS database did not read: {error})"]
    return extras


# a rule gdscheck checks, as its log states it: ``[FRIDA.M3.width] Checking min_width ...``
_CHECKING = re.compile(r"^\[([^\]]+)\] Checking (.*)$")


def drc_checked(folder: Path) -> dict[str, str]:
    """The rules gdscheck checked, by name, each its checks as its log states them (a rule over
    several layers its checks joined); none from another checker."""
    checked: dict[str, list[str]] = {}
    for log in sorted(folder.glob("gdscheck.*.log")):
        for line in log.read_text(errors="replace").splitlines():
            found = _CHECKING.match(line)
            if found:
                checked.setdefault(found[1], []).append(found[2])
    return {rule: "; ".join(checks) for rule, checks in checked.items()}


def lvs_devices(report: Path) -> dict[str, dict[str, int]]:
    """Each side's devices by class in a KLayout LVS database: the layout's (as extracted) and the
    schematic's (the reference), each netlist flattened; empty where the database does not read."""
    import klayout.db as kdb

    try:
        lvs = kdb.LayoutVsSchematic()
        lvs.read(str(report))
        sides = {"layout": lvs.netlist(), "schematic": lvs.reference}
    except Exception:  # noqa: BLE001 - the verdict stands without the counts
        return {}
    counts: dict[str, dict[str, int]] = {}
    for side, netlist in sides.items():
        if netlist is None:
            continue
        flat = netlist.dup()
        flat.flatten()
        found: dict[str, int] = {}
        for circuit in flat.each_circuit():
            for device in circuit.each_device():
                name = device.device_class().name
                found[name] = found.get(name, 0) + 1
        counts[side] = dict(sorted(found.items()))
    return counts


def drc_markers(folder: Path, top: str) -> dict[str, dict[str, Any]]:
    """DRC's markers by rule, from the KLayout marker databases gdscheck wrote (``gdscheck.<suite>
    .lyrdb``, ``flow.layout.signoff._markers``): each rule's count, description and boxes (µm, in
    the top cell, ``MAX_MARKERS`` at most). A report that does not read is left out; Calibre's
    results are not read."""
    from flow.layout.signoff import _markers

    rules: dict[str, dict[str, Any]] = {}
    for report in sorted(folder.glob("*.lyrdb")):
        try:
            found = _markers(report, top)
        except Exception:  # noqa: BLE001, S112 - the counts stand without their places
            continue
        for rule, entry in found.items():
            kept = rules.setdefault(rule, {"count": 0, "description": entry["description"], "boxes": []})
            kept["count"] += entry["count"]
            kept["boxes"] = (kept["boxes"] + entry["boxes"])[:MAX_MARKERS]
    return rules


def wave_kinds(waves: dict[str, str], root: Path = ROOT) -> dict[str, dict[str, str]]:
    """A record's waves (label -> measurement) by the step that simulated them: ``sim``'s (pre-layout)
    and ``pexsim``'s (the extraction back-annotated), each pexsim measurement's pre-layout
    counterpart (``sim/<run>/`` beside its ``pexsim/<run>/``) among sim's where it is kept."""
    kinds: dict[str, dict[str, str]] = {"sim": {}, "pexsim": {}}
    for label, relative in waves.items():
        parts = Path(relative).parts
        if "pexsim" in parts:
            kinds["pexsim"][label] = relative
            at = len(parts) - 1 - parts[::-1].index("pexsim")
            twin = Path(*parts[:at], "sim", *parts[at + 1 :])
            if (root / twin).exists():
                kinds["sim"][label] = str(twin)
        else:
            kinds["sim"][label] = relative
    return kinds
