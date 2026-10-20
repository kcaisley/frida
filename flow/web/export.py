"""Export the cached block results the web viewer shows; nothing is simulated or laid out.

Every block's characterization study in ``flow.analysis.runner`` runs once on its pinned
simulation run with each ``plot_*`` call recorded: the analyses a plot is handed, one per case
label, are written as JSON per PDK and case (``results.json``), and the study's own figures as
SVG. Every measurement the study reads that holds waveforms is indexed per PDK and case
(``traces.json``); the server reads a waveform from its HDF5 file when it is asked for. Every layout the layout runners left in ``build/layout`` (the newest per cell, PDK and
generator, from their ``summary.json``) is flattened onto the PDK's generic layer keys (``OD``,
``PO``, ``CO``, ``M1``, ``V1`` ...: ``layout/tech.py``'s ``LAYERS``), merged per layer and written
with its labels; each layout's netlist becomes a schematic (``flow.util.netlist2image``).

    uv run python -m flow.web export [--blocks schmitt bias] [--no-figures] [--workers 16]
"""

from __future__ import annotations

import ast
import dataclasses
import json
import math
import re
import traceback
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from enum import Enum
from importlib import import_module
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "build/web/data"
LAYOUT_DIR = ROOT / "build/layout"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
GENERATORS = ("cic", "laygo", "align")
# block -> title, in the order the viewer lists them
BLOCKS = {
    "comp": "Comparator",
    "samp": "Sampling switch",
    "caparray": "Capacitor array",
    "momcap": "MOM capacitor",
    "capdriver": "Capacitor driver",
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
    "moscap": "MOS capacitor",
}
# class-name words that are acronyms (AnalysisOtaAc: "AC")
ACRONYMS = {"Ac": "AC", "Dc": "DC", "Sr": "SR", "Iv": "I–V", "Cv": "C–V"}
# 2-D records longer than this are thinned to it for the browser (every k-th sample)
MAX_SAMPLES = 1600
# a waveform record longer than this is thinned to it when served
MAX_WAVE_SAMPLES = 20000


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


def thinned(length: int) -> np.ndarray:
    """Indices of at most ``MAX_SAMPLES`` evenly spread samples, both ends kept."""
    return np.unique(np.linspace(0, length - 1, MAX_SAMPLES).round().astype(int))


def analysis_record(analysis) -> dict:
    """An analysis's fields and public properties, as JSON-ready values (its ``dut`` apart)."""

    record = {
        field.name: json_value(getattr(analysis, field.name))
        for field in dataclasses.fields(analysis)
        if field.name not in ("group", "index", "dut")
    }
    for cls in type(analysis).__mro__:
        for name, attribute in vars(cls).items():
            if isinstance(attribute, property) and not name.startswith("_") and name not in record:
                try:
                    value = getattr(analysis, name)
                except (ArithmeticError, AttributeError, IndexError, TypeError, ValueError):
                    value = None  # a property the analysis cannot evaluate is left out
                if isinstance(value, (np.ndarray, np.number, float, int)):  # derived results, not identity
                    record[name] = json_value(value)
    return {name: value for name, value in record.items() if value is not None}


def case_name(label: str) -> tuple[str, str]:
    """A study label's case name and description: ``"inv: inverting"`` -> ``("inv", "inverting")``."""
    name, _, description = label.partition(":")
    return name.strip(), description.strip()


def dataset_title(block: str, cls: str, plot: str | None) -> str:
    """``AnalysisBiasMirror`` -> "Mirror"; with the plot it was first seen in when the class
    appears in several datasets: "Mirror (supply)"."""

    stem = cls.removeprefix("Analysis")
    stem = stem.removeprefix(block.capitalize()) or stem
    words = [ACRONYMS.get(word, word) for word in re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stem).split()]
    title = " ".join([words[0], *(word if word.isupper() else word.lower() for word in words[1:])]) if words else cls
    if plot:
        title += f" ({plot.removeprefix(f'{block}_').replace('_', ' ')})"
    return title


def case_comments(block: str) -> dict[str, str]:
    """The comment above each entry of the block's ``CASES`` dict in ``subckt.py``."""

    path = ROOT / "flow" / block / "subckt.py"
    if not path.exists():
        return {}
    lines = path.read_text().splitlines()
    comments = {}
    for node in ast.parse("\n".join(lines)).body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if not any(getattr(target, "id", None) == "CASES" for target in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if not isinstance(key, ast.Constant):
                continue
            above, row = [], key.lineno - 2
            while row >= 0 and lines[row].strip().startswith("#"):
                above.insert(0, lines[row].strip().lstrip("#").strip())
                row -= 1
            comments[str(key.value)] = " ".join(above)
    return comments


def run_study(block: str, figures_dir: Path | None) -> tuple[list[tuple[str, tuple, dict]], list[dict]]:
    """Run the block's characterization study, recording every plot call's arguments and every
    measurement it reads that holds waveforms; the plots are drawn as SVG under ``figures_dir``,
    or not at all."""

    from flow.analysis import io, plots, runner

    study = getattr(runner, f"{block}_characterization_study")
    calls, waves = [], []
    originals = {name: plot for name, plot in vars(runner).items() if name.startswith("plot_") and callable(plot)}
    formats = plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS
    read = io.read_measurement

    def read_recording(path):
        measurement = read(path)
        entry = wave_entry(Path(path), measurement)
        if entry:
            waves.append(entry)
        return measurement

    plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS = False, True, False
    io.read_measurement = runner.read_measurement = read_recording
    try:
        for name, plot in originals.items():
            setattr(runner, name, recorder(name, plot, calls, draw=figures_dir is not None))
        study(figures_dir or DATA_DIR / block / "figures")
    finally:
        for name, plot in originals.items():
            setattr(runner, name, plot)
        io.read_measurement = runner.read_measurement = read
        plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS = formats
    return calls, waves


def wave_entry(path: Path, measurement, *, root: Path = ROOT) -> dict | None:
    """A measurement's waveforms in the traces index: its PDK, case and sweep (from the path:
    ``<pdk>/<case>/<sweep>/...``), its bench parameters, its nets and time span; None without."""

    wave = getattr(measurement, "wave", None)
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


def read_wave(relative: str, record: int = 0, *, root: Path = ROOT, max_samples: int = MAX_WAVE_SAMPLES) -> dict:
    """One record of a cached measurement's waveforms, for the traces view: time and every node
    voltage and supply current, every k-th sample where longer than ``max_samples``. Only HDF5
    files under ``root/build`` are read."""

    from flow.analysis.io import read_measurement

    path = (root / relative).resolve()
    if path.suffix != ".h5" or not path.is_relative_to((root / "build").resolve()):
        raise ValueError(f"{relative} is not a cached measurement")
    wave = getattr(read_measurement(path), "wave", None)
    if wave is None:
        raise ValueError(f"{relative} holds no waveforms")
    if not 0 <= record < len(wave.record_index):
        raise ValueError(f"{relative} has no record {record}")
    samples = len(wave.time_s)
    stride = max(1, math.ceil(samples / max_samples))
    keep = np.unique(np.append(np.arange(0, samples, stride), samples - 1))

    def trace(values: np.ndarray) -> list:  # not json_value: that thins to MAX_SAMPLES again
        return [float(f"{value:.6g}") if math.isfinite(value) else None for value in values[record][keep].tolist()]

    return {
        "path": relative,
        "record": record,
        "records": len(wave.record_index),
        "samples": samples,
        "stride": stride,
        "time_s": [float(f"{value:.10g}") for value in wave.time_s[keep].tolist()],
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


def recorder(name: str, plot: Callable, calls: list, *, draw: bool) -> Callable:
    """``plot`` that also records its call; it draws only when ``draw``."""

    def record(*args, **kwargs):
        calls.append((name, args, kwargs))
        return plot(*args, **kwargs) if draw else ()

    return record


def study_results(block: str, calls: Iterable[tuple[str, tuple, dict]]) -> tuple[dict, dict, dict]:
    """Datasets (one per analysis class, or per class and first plot where a study hands one plot
    a second set of the same class), their results per PDK and case, and the cases' labels and
    parameters."""

    datasets, results, cases, seen = {}, {}, {}, {}
    for _plot, args, kwargs in calls:
        output_path = Path(kwargs["output_path"])
        default_pdk = output_path.parent.name if output_path.parent.name in PDKS else "all"
        labels = list(kwargs.get("labels") or ())
        arguments = [*args, *(value for key, value in kwargs.items() if key not in ("labels", "output_path"))]
        for argument, argument_labels in zip(arguments, split_labels(arguments, labels), strict=True):
            for pdk, label, analysis in labelled(argument, argument_labels, default_pdk):
                case, description = case_name(label)
                cls = type(analysis).__name__
                key = seen.get(id(analysis))
                if key is None:
                    key = cls
                    if results.get(key, {}).get(pdk, {}).get(case) is not None:
                        key = f"{cls}:{output_path.name}"
                    seen[id(analysis)] = key
                    datasets.setdefault(
                        key, {"key": key, "class": cls, "plot": output_path.name, "suffixed": key != cls, "fields": {}}
                    )
                    record = analysis_record(analysis)
                    results.setdefault(key, {}).setdefault(pdk, {})[case] = record
                    for field, value in record.items():
                        datasets[key]["fields"].setdefault(field, ndim(value))
                    entry = cases.setdefault(case, {"label": label, "description": description, "params": {}})
                    if not entry["params"] and getattr(analysis, "dut", None) is not None:
                        entry["params"] = json_value(analysis.dut)
                datasets[key].setdefault("plots", [])
                if output_path.name not in datasets[key]["plots"]:
                    datasets[key]["plots"].append(output_path.name)
    for dataset in datasets.values():
        dataset["title"] = dataset_title(block, dataset["class"], dataset["plot"] if dataset.pop("suffixed") else None)
        dataset["fields"] = [{"name": name, "ndim": dims} for name, dims in dataset["fields"].items()]
    return datasets, results, cases


def split_labels(arguments: list, labels: list[str]) -> list[list[str]]:
    """The labels of each plot argument: all of them, or, where a plot takes several lists of
    analyses with one label list running through them all, each list's share in order."""

    from flow.analysis.types import Analysis

    lengths = [
        len(argument)
        if isinstance(argument, (list, tuple)) and argument and all(isinstance(item, Analysis) for item in argument)
        else 0
        for argument in arguments
    ]
    if len([length for length in lengths if length]) < 2 or sum(lengths) != len(labels) or len(labels) in lengths:
        return [labels] * len(arguments)
    starts = [sum(lengths[:index]) for index in range(len(lengths))]
    return [labels[start : start + length] for start, length in zip(starts, lengths, strict=True)]


def labelled(argument, labels: list[str], pdk: str) -> list[tuple[str, str, object]]:
    """Each analysis in a plot argument with its PDK and case label. The study's labels name the
    cases; where it gives none, or names PDKs with them (one plot across PDKs), the cases are named
    after the parameters that differ between the analyses' designs."""

    from flow.analysis.types import Analysis

    if isinstance(argument, Analysis):
        items = [argument]
    elif isinstance(argument, (list, tuple)) and argument and all(isinstance(item, Analysis) for item in argument):
        items = list(argument)
    else:
        return []
    if len(labels) == len(items) and not all(label in PDKS for label in labels):
        return [(pdk, label, item) for label, item in zip(labels, items, strict=True)]
    pdks = labels if len(labels) == len(items) else [pdk] * len(items)
    return list(zip(pdks, design_names([item.dut for item in items]), items, strict=True))


def design_names(duts: list) -> list[str]:
    """A name per design from the parameters that differ between them (``difference_2``); "all"
    where they do not differ."""

    values = [json_value(dut) if dut is not None else {} for dut in duts]
    names = list(dict.fromkeys(name for value in values if isinstance(value, dict) for name in value))
    varying = [name for name in names if len({json.dumps(value.get(name)) for value in values}) > 1]
    return ["_".join(str(value.get(name)).lower() for name in varying) or "all" for value in values]


def ndim(value) -> int:
    """0 for a scalar, 1 for a list, 2 for a list of lists."""
    if not isinstance(value, list):
        return 0
    return 2 if value and isinstance(value[0], list) else 1


# =============================================================================
# Layouts and schematics
# =============================================================================


def layout_index(block: str) -> list[dict]:
    """The newest layout of every cell, PDK and generator under ``build/layout/<block>``, with its
    signoff results, from the layout runners' ``summary.json`` files."""

    newest = {}
    for summary in sorted((LAYOUT_DIR / block).glob("**/summary.json")):
        try:
            entries = json.loads(summary.read_text())
        except (OSError, ValueError):
            continue
        for entry in entries.values() if isinstance(entries, dict) else ():
            if not isinstance(entry, dict) or not entry.get("gds"):
                continue
            gds = Path(entry["gds"])
            parts = gds.parts
            places = [i for i, part in enumerate(parts[:-1]) if part in PDKS and parts[i + 1] in GENERATORS]
            if not places or not gds.exists():
                continue
            pdk, generator = parts[places[-1]], parts[places[-1] + 1]
            folder = Path(*parts[: places[-1] + 1]) / "netlist"
            # <cell>.sp, or the comparator's <cell>_transistors.sp beside its standard-cell view
            netlist = next(
                (path for path in (folder / f"{gds.stem}.sp", folder / f"{gds.stem}_transistors.sp") if path.exists()),
                folder / f"{gds.stem}.sp",
            )
            item = {
                "cell": gds.stem,
                "case": gds.stem.removeprefix(f"{block}_"),
                "pdk": pdk,
                "generator": generator,
                "gds": str(gds),
                "netlist": str(netlist) if netlist.exists() else None,
                "cell_um": entry.get("cell_um"),
                "drc_violations": entry.get("drc_violations"),
                "lvs_correct": entry.get("lvs_correct"),
                "mtime": gds.stat().st_mtime,
            }
            key = item["cell"], pdk, generator
            if key not in newest or newest[key]["mtime"] < item["mtime"]:
                newest[key] = item
    return sorted(newest.values(), key=lambda item: (item["cell"], PDKS.index(item["pdk"]), item["generator"]))


def other_layouts(block: str) -> list[dict]:
    """Layouts outside the row-cell runners' ``<pdk>/<generator>/`` folders: the capacitor
    array's (one per metal-layer count, its runner's ``summary.json`` saying "clean" or why
    not) and the MOM capacitor's extraction structures (per family and PDK, the one at the
    smallest spacing and the length nearest 4 µm); no netlists, no LVS."""

    items = []
    if block == "caparray":
        runs = sorted((LAYOUT_DIR / "caparray" / "caparray_all_pdks").glob("*/summary.json"))
        summary = json.loads(runs[-1].read_text()) if runs else {}
        for key, verdict in summary.items():
            pdk, cell = key.split("/", 1)
            match = re.fullmatch(r"caparray_(\d+)layer_(\w+)", cell)
            gds = runs[-1].parent / pdk / cell / f"{cell}.gds"
            if match and gds.exists():
                clean = verdict == "clean"
                items.append(
                    {
                        "cell": cell,
                        "case": match[2],
                        "pdk": pdk,
                        "generator": f"{match[1]}layer",
                        "gds": str(gds),
                        "netlist": None,
                        "cell_um": None,
                        "drc_violations": 0 if clean else None,
                        "lvs_correct": None,
                        "note": None if clean else str(verdict)[:120],
                        "mtime": gds.stat().st_mtime,
                    }
                )
    if block == "momcap":
        runs = sorted(
            (ROOT / "build/pex/momcap/momcap_characterization").glob("*/"), key=lambda path: path.stat().st_mtime
        )
        for family in sorted(runs[-1].glob("*/*_*l")) if runs else ():
            spacings = sorted(family.glob("s*"), key=lambda path: int(path.name[1:]))
            lengths = (
                sorted(spacings[0].glob("len*/momunit.gds"), key=lambda path: abs(int(path.parent.name[3:]) - 4000))
                if spacings
                else []
            )
            if not lengths:
                continue
            style, layers = family.name.rsplit("_", 1)
            items.append(
                {
                    "cell": f"momunit_{family.name}",
                    "case": f"{style}_{layers.removesuffix('l')}",
                    "pdk": family.parent.name,
                    "generator": "unit",
                    "gds": str(lengths[0]),
                    "netlist": None,
                    "cell_um": None,
                    "drc_violations": None,
                    "lvs_correct": None,
                    "note": f"spacing {spacings[0].name[1:]} nm, length {int(lengths[0].parent.name[3:]) / 1000:g} µm",
                    "mtime": lengths[0].stat().st_mtime,
                }
            )
    return items


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
# Export
# =============================================================================


def export_block(block: str, *, figures: bool, pool: ProcessPoolExecutor) -> dict:
    """Write one block's results, figures, layouts and schematics; its catalog entry."""

    block_dir = DATA_DIR / block
    block_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    datasets, results, cases = {}, {}, {}
    try:
        calls, waves = run_study(block, block_dir / "figures" if figures else None)
        datasets, results, cases = study_results(block, calls)
        (block_dir / "traces.json").write_text(json.dumps(trace_index(waves), separators=(",", ":")))
    except Exception:  # noqa: BLE001 - report the block's failure, export its layouts anyway
        errors.append(f"study: {traceback.format_exc(limit=3)}")
    comments = case_comments(block)
    for case, entry in cases.items():
        entry["comment"] = comments.get(case, "")

    layouts = layout_index(block) + other_layouts(block)
    jobs = {}
    for item in layouts:
        name = f"{item['cell']}__{item['pdk']}__{item['generator']}"
        item["path"] = f"{block}/layouts/{name}.json"
        jobs[pool.submit(export_layout, item["gds"], item["pdk"], str(DATA_DIR / item["path"]))] = "layout", item
    # each layout's netlist, and its schematic where it is transistors (not standard cells)
    schematics = {}
    for item in layouts:
        key = item["cell"], item["pdk"]
        if item["netlist"] and key not in schematics:
            stem = f"{block}/schematics/{item['cell']}__{item['pdk']}"
            text = Path(item["netlist"]).read_text()
            (DATA_DIR / f"{stem}.sp").parent.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / f"{stem}.sp").write_text(text)
            entry = {
                "cell": item["cell"],
                "case": item["case"],
                "pdk": item["pdk"],
                "netlist": f"{stem}.sp",
                "path": None,
            }
            schematics[key] = entry
            if any(line.lstrip()[:1] in ("M", "m") for line in text.splitlines()):
                entry["path"] = f"{stem}.svg"
                jobs[pool.submit(export_schematic, item["netlist"], str(DATA_DIR / entry["path"]))] = "schematic", entry
    for future, (kind, item) in jobs.items():
        try:
            result = future.result()
            if isinstance(result, dict):
                item.update(result)
        except Exception as error:  # noqa: BLE001 - report every layout's failure, export the others
            if kind == "schematic":  # a schematic that cannot be drawn leaves its netlist
                item["path"] = None
                item["note"] = f"no schematic: {error}"
            else:
                item["error"] = repr(error)
                errors.append(f"{item.get('path')}: {error!r}")
    for item in layouts:
        item.pop("mtime"), item.pop("gds"), item.pop("netlist")
        item["case_known"] = item["case"] in cases
    layouts = [item for item in layouts if "error" not in item]
    for case in {item["case"] for item in layouts} - set(cases):
        cases[case] = {"label": case, "description": "", "comment": comments.get(case, ""), "params": {}}

    figures_dir = block_dir / "figures"
    figure_paths = [*sorted(figures_dir.glob("*/*.svg")), *sorted(figures_dir.glob("*.svg"))] if figures else []
    meta = {
        "name": block,
        "title": BLOCKS[block],
        "pdks": [pdk for pdk in (*PDKS, "all") if any(pdk in by_pdk for by_pdk in results.values())]
        or sorted({item["pdk"] for item in layouts}, key=PDKS.index),
        "cases": cases,
        "datasets": list(datasets.values()),
        "layouts": layouts,
        "schematics": [item for item in schematics.values() if "error" not in item],
        "figures": [
            {
                "pdk": path.parent.name if path.parent != figures_dir else "all",
                "name": path.stem,
                "path": str(path.relative_to(DATA_DIR)),
            }
            for path in figure_paths
        ],
        "errors": errors,
    }
    (block_dir / "results.json").write_text(json.dumps(results, separators=(",", ":")))
    (block_dir / "block.json").write_text(json.dumps(meta, separators=(",", ":")))
    return {
        "name": block,
        "title": BLOCKS[block],
        "cases": len(cases),
        "datasets": len(datasets),
        "layouts": len(layouts),
        "errors": len(errors),
    }


def export(blocks: Iterable[str] = tuple(BLOCKS), *, figures: bool = True, workers: int = 16) -> Path:
    """Export every named block, then the catalog of all exported blocks; the catalog's path."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = DATA_DIR / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {"blocks": []}
    entries = {entry["name"]: entry for entry in catalog["blocks"]}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for block in blocks:
            entries[block] = export_block(block, figures=figures, pool=pool)
            print(f"{block}: {entries[block]}", flush=True)
    catalog = {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pdks": list(PDKS),
        "blocks": [entries[block] for block in BLOCKS if block in entries],
    }
    catalog_path.write_text(json.dumps(catalog, indent=1))
    return catalog_path
