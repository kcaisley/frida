from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pytest

from flow.web.export import DATA_DIR, MAX_SAMPLES, export_layout, json_value
from flow.web.server import STATIC_DIR, Handler


class Flavour(Enum):
    LOW = "LOW"


@dataclass(frozen=True)
class ToyParams:
    w: int = 2
    vth: Flavour = Flavour.LOW


def test_values_become_json_at_six_digits_with_nan_as_null() -> None:
    assert json_value(np.array([1.23456789, math.nan, math.inf])) == [1.23457, None, None]
    assert json_value(np.array([True, False])) == [True, False]
    assert json_value(ToyParams()) == {"w": 2, "vth": "LOW"}
    assert json_value(np.float64(2.5e-12)) == 2.5e-12
    assert json_value("text") == "text"


def test_long_records_are_thinned_keeping_both_ends() -> None:
    rows = json_value(np.tile(np.arange(5000.0), (2, 1)))
    assert len(rows) == 2 and len(rows[0]) == MAX_SAMPLES
    assert rows[0][0] == 0 and rows[0][-1] == 4999


def test_layouts_flatten_onto_generic_layers_and_merge(tmp_path: Path) -> None:
    import klayout.db as kdb

    from pdk.ihp130.layout import tech

    layout = kdb.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("toy")
    m1 = layout.layer(*tech.LAYERS["M1"])
    cell.shapes(m1).insert(kdb.Box(0, 0, 1000, 200))
    cell.shapes(m1).insert(kdb.Box(0, 0, 200, 1000))  # with the first, an L
    cell.shapes(layout.layer(*tech.LAYERS["M2"])).insert(kdb.Box(0, 0, 500, 500))
    cell.shapes(layout.layer(*tech.PIN_TEXT["M1"])).insert(kdb.Text("vin", kdb.Trans(100, 100)))
    cell.shapes(layout.layer(999, 0)).insert(kdb.Box(0, 0, 50, 50))  # no generic key: dropped
    gds = tmp_path / "toy.gds"
    layout.write(str(gds))

    summary = export_layout(str(gds), "ihp130", str(tmp_path / "toy.json"))
    record = json.loads((tmp_path / "toy.json").read_text())
    assert summary["layers"] == ["M1", "M2"]
    layers = {layer["key"]: layer for layer in record["layers"]}
    assert layers["M1"]["rects"] == [] and len(layers["M1"]["polys"]) == 1
    assert len(layers["M1"]["polys"][0][0]) == 12  # six corners
    assert layers["M2"]["rects"] == [0, 0, 500, 500]
    assert record["labels"] == [{"text": "vin", "layer": "M1.PIN", "x": 100, "y": 100}]
    assert record["bbox"] == [0, 0, 1000, 1000] and record["dbu"] == pytest.approx(0.001)


def test_the_server_answers_data_from_the_export_and_the_rest_from_static() -> None:
    handler = Handler.__new__(Handler)
    handler.directory = str(STATIC_DIR)
    assert Path(handler.translate_path("/data/sweep/comp.json")) == DATA_DIR / "sweep/comp.json"
    assert Path(handler.translate_path("/js/explorer.js?v=1")) == STATIC_DIR / "js/explorer.js"
    assert Path(handler.translate_path("/data/../../../etc/passwd")).is_relative_to(DATA_DIR)


@pytest.mark.parametrize("page", ["index.html", "detail.html"])
def test_the_pages_load_only_pinned_library_versions(page: str) -> None:
    urls = re.findall(r"https://[^\"' )]+", (STATIC_DIR / page).read_text())
    assert urls
    assert all(re.search(r"@\d+\.\d+\.\d+", url) for url in urls)


def test_waveforms_are_indexed_per_instance_and_served_thinned(tmp_path: Path) -> None:
    from flow.analysis.io import write_measurement
    from flow.schmitt.test_analysis import _step
    from flow.web.export import read_wave, trace_index, wave_entry

    measurement = _step(40e-12)
    path = tmp_path / "build/sim/schmitt/run/ihp130/inv/step/vdd1200/result.h5"
    path.parent.mkdir(parents=True)
    write_measurement(path, measurement)

    samples = len(measurement.wave.time_s)  # about 4000 of inp, out and the supply current
    wave = read_wave(str(path.relative_to(tmp_path)), root=tmp_path, max_samples=3000)  # more than MAX_SAMPLES kept
    stride = math.ceil(samples / 3000)
    assert wave["samples"] == samples and wave["stride"] == stride
    kept = len({*range(0, samples, stride), samples - 1})
    assert kept > MAX_SAMPLES
    assert len(wave["time_s"]) == len(wave["v"]["inp"]) == len(wave["v"]["out"]) == len(wave["i"]["vdd"]) == kept
    assert wave["time_s"][-1] == pytest.approx(float(measurement.wave.time_s[-1]))
    assert set(wave["v"]) == {"inp", "out"} and set(wave["i"]) == {"vdd"}
    with pytest.raises(ValueError, match="not a cached measurement"):
        read_wave("../outside.h5", root=tmp_path)

    entry = wave_entry(path, measurement, root=tmp_path)
    assert (entry["pdk"], entry["case"], entry["sweep"], entry["v"]) == ("ihp130", "inv", "step", ["inp", "out"])
    entry = {**entry, "path": "a.h5"}
    other = {**entry, "path": "b.h5", "params": {**entry["params"], "vdd": 0.9}}
    index = trace_index([entry, other, dict(entry)])  # the same file twice is one run
    assert [run["point"] for run in index["ihp130"]["inv"]] == [{"vdd": 0.9}, {"vdd": 1.2}]
