"""Software-only tests for HDF5 and acquisition-wave adapters."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

from flow.adc.sim import AdcTbParams
from flow.analysis.io import _read_native, write_measurement
from flow.scans.scan_behavioral import build_adc_interface_wave
from flow.scans.scope import scope_records_to_adc_wave


@pytest.mark.parametrize("spawn_worker", (False, True), ids=("cli", "spawned-cli"))
def test_cli_parameter_type_survives_a_separate_reader(tmp_path: Path, monkeypatch, spawn_worker: bool) -> None:
    """Exercise real python -m entry points, including multiprocessing's alias."""
    module_name = "measurement_persistence_cli"
    (tmp_path / f"{module_name}.py").write_text(
        dedent("""\
            from concurrent.futures import ProcessPoolExecutor
            from dataclasses import dataclass
            from multiprocessing import get_context
            import sys
            import h5py
            from flow.analysis.io import _write_native

            @dataclass
            class CliParams:
                conversions: int = 100

            def write(path):
                with h5py.File(path, "w") as stored:
                    _write_native(stored, "param", CliParams())

            if __name__ == "__main__":
                if sys.argv[2] == "spawn":
                    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as executor:
                        executor.submit(write, sys.argv[1]).result()
                else:
                    write(sys.argv[1])
            """)
    )
    path = tmp_path / "cli.h5"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(tmp_path), str(Path(__file__).resolve().parents[2]), env.get("PYTHONPATH", ""))
    )
    subprocess.run(
        [sys.executable, "-m", module_name, str(path), "spawn" if spawn_worker else "direct"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with h5py.File(path, "r") as stored:
        assert stored["param"].attrs["_type"] == f"{module_name}:CliParams"
        loaded = _read_native(stored["param"])
    assert loaded.conversions == 100
    assert type(loaded).__module__ == module_name


@pytest.mark.parametrize("module_name", ("__main__", "__mp_main__"))
def test_writer_rejects_unimportable_entry_point_types(monkeypatch, module_name):
    from flow.analysis.io import _qualified_type

    transient_type = type("TransientParams", (), {"__module__": module_name})
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(__spec__=None))
    with pytest.raises(ValueError, match="importable module"):
        _qualified_type(transient_type)


@pytest.mark.parametrize("with_input", (True, False))
def test_scope_records_build_dense_adc_external_wave(with_input: bool) -> None:
    scale = SimpleNamespace(offset=-1.0e-9, slope=1.0e-9)

    def waveform(values):
        return SimpleNamespace(x_scale=scale, data=np.asarray(values))

    records = [
        {
            1: waveform([0.0, 0.1, 0.2]),
            2: waveform([0.0, 1.2, 0.0]),
            3: waveform([1.2, 0.0, 1.2]),
            4: waveform([0.0, 0.0, 1.2]),
        },
        {
            1: waveform([0.2, 0.1, 0.0]),
            2: waveform([1.2, 0.0, 1.2]),
            3: waveform([0.0, 1.2, 0.0]),
            4: waveform([1.2, 1.2, 0.0]),
        },
    ]
    wave = scope_records_to_adc_wave(
        records,
        [3, 9],
        {
            **({"vin_diff": 1} if with_input else {"seq_init": 1}),
            "seq_comp": 2,
            "seq_logic": 3,
            "comp_out": 4,
        },
    )

    np.testing.assert_array_equal(wave.record_index, [3, 9])
    np.testing.assert_allclose(wave.time_s, [-1.0e-9, 0.0, 1.0e-9])
    if with_input:
        assert wave.v["vin_diff"].shape == (2, 3)
    else:
        assert "vin_diff" not in wave.v
        np.testing.assert_allclose(wave.v["seq_init"][1], [0.2, 0.1, 0.0])
    np.testing.assert_allclose(wave.v["comp_out"][1], [1.2, 1.2, 0.0])


def test_behavioral_adapter_builds_one_complete_interface_record() -> None:
    params = AdcTbParams(conversions=1)
    wave = build_adc_interface_wave(params, [1] * 17, samples_per_symbol=2)

    assert wave.record_index.tolist() == [0]
    assert wave.v["vin_diff"].shape == (1, 2 * len(params.seq_init_pattern))
    assert wave.v["seq_comp"].shape == wave.v["vin_diff"].shape
    assert np.count_nonzero(np.diff(wave.v["comp_out"][0])) <= 1


def test_spectre_reader_uses_raw_to_alias_map_and_preserves_all_samples(tmp_path, monkeypatch):
    from vlsirtools.spice import spectre

    from flow.circuit.results import read_raw_transient

    time = np.array([0.0, 0.1, 0.37, 1.0])
    data = {"time": time, "xtop.saved": np.array([0.2, 0.8, 1.0, 0.0])}
    path = tmp_path / "netlist.raw"
    path.write_bytes(b"raw data")
    monkeypatch.setattr(
        spectre, "parse_nutbin", lambda stream: {"tran": SimpleNamespace(analysis_name="tran", data=data)}
    )
    result = read_raw_transient(path)
    np.testing.assert_array_equal(result.data["time"], time)
    assert "xtop.saved" in result.data


def analysis_results():
    """Return one constructed instance of many analysis result types, nested records included."""

    from flow.analysis.adc import (
        analyze_adc_code_density_nonlinearity,
        analyze_adc_decision_paths,
        analyze_adc_dynamic,
        analyze_adc_noise,
        analyze_adc_operating_conditions,
        analyze_adc_power,
        analyze_adc_ramp,
        analyze_adc_timing_closure,
        analyze_adc_timing_summary,
        analyze_adc_transfer,
    )
    from flow.analysis.comp import analyze_comp_common_mode, analyze_comp_offset_noise
    from flow.analysis.test_adc import adc_measurement, adc_ramp_measurement, adc_timing_measurement
    from flow.analysis.test_cdac import _curve, transition_of
    from flow.analysis.test_comp import comparator_measurement

    ramp_measurement = adc_ramp_measurement()
    ramp = analyze_adc_ramp(ramp_measurement)
    sample_rate_hz = 100_000.0
    time_s = np.arange(2_048) / sample_rate_hz
    sine = adc_measurement(
        np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * 1_000.0 * time_s)),
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=1_000.0,
    )
    power = adc_measurement(
        [100, 101],
        readbacks={
            f"{rail}_{kind}_average_power_w": value
            for rail in ("vdd_a", "vdd_d", "vdd_dac")
            for kind, value in (("active", 2e-6), ("static", 1e-6))
        },
    )
    noise_measurement = adc_measurement([100, 101, 100, 102], observed_adc=2)
    timing = adc_timing_measurement()
    closure = analyze_adc_timing_closure(timing)
    comparator = comparator_measurement()
    offset = analyze_comp_offset_noise([comparator])
    return (
        ramp,
        analyze_adc_code_density_nonlinearity(ramp_measurement, ramp=ramp),
        analyze_adc_dynamic(sine),
        analyze_adc_transfer([sine]),
        analyze_adc_power(power),
        analyze_adc_noise(noise_measurement),
        analyze_adc_operating_conditions([noise_measurement], noise=[analyze_adc_noise(noise_measurement)]),
        analyze_adc_decision_paths(noise_measurement),
        closure,
        analyze_adc_timing_summary(timing, closure=closure),
        offset,
        analyze_comp_common_mode([comparator], offsets=[offset]),
        transition_of(_curve("n", "1to0", 0, 2e-3)),
    )


def assert_results_equal(expected, actual) -> None:
    from dataclasses import fields, is_dataclass

    assert type(actual) is type(expected)
    for field in fields(expected):
        left, right = getattr(expected, field.name), getattr(actual, field.name)
        if isinstance(left, np.ndarray):
            assert left.dtype == right.dtype, field.name
            np.testing.assert_array_equal(left, right, err_msg=field.name)
        elif isinstance(left, tuple) and left and is_dataclass(left[0]) and not hasattr(left[0], "init"):
            assert len(left) == len(right)
            for item_left, item_right in zip(left, right, strict=True):
                assert_results_equal(item_left, item_right)
        elif isinstance(left, float) and np.isnan(left):
            assert np.isnan(right), field.name
        else:
            assert left == right, field.name


@pytest.mark.parametrize("result", analysis_results(), ids=lambda value: type(value).__name__)
def test_every_analysis_result_round_trips(tmp_path: Path, result) -> None:
    from flow.analysis.io import read_analysis, write_analysis

    path = write_analysis(tmp_path / "result.h5", result)
    assert_results_equal(result, read_analysis(path))


def test_analysis_reader_rejects_measurement_files(tmp_path: Path) -> None:
    from flow.analysis.io import read_analysis
    from flow.analysis.test_types import adc_spice

    path = write_measurement(tmp_path / "measurement.h5", adc_spice())
    with pytest.raises(ValueError, match="not an analysis"):
        read_analysis(path)
