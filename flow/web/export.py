"""The views the viewer's pages read beside the sweep tables (``flow.sweep``): a layout flattened
onto its PDK's generic layer keys (``OD``, ``PO``, ``CO``, ``M1``, ``V1`` ...: ``layout/tech.py``'s
``LAYERS``), merged per layer and written with its labels; a netlist's transistor schematic
(``flow.util.netlist2image``); the index of an instance's waveform measurements, and one record of
them, read from its HDF5 file when the server is asked for it."""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Iterable
from enum import Enum
from importlib import import_module
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "build/web/data"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
# block -> title
BLOCKS = {
    "adc": "SAR ADC (behavioral)",
    "comp": "Comparator",
    "samp": "Sampling switch",
    "caparray": "Capacitor array",
    "momcap": "MOM capacitor",
    "capdriver": "Capacitor driver",
    "cdac": "CDAC (array and drivers)",
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
    "mosfet": "MOSFET",
}
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
