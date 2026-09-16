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
from flow.analysis.io import (
    _read_native,
)
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


def test_scope_records_build_dense_adc_external_wave() -> None:
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
            "vin_diff_v": 1,
            "seq_comp_v": 2,
            "seq_logic_v": 3,
            "comp_out_v": 4,
        },
    )

    np.testing.assert_array_equal(wave.conversion_index, [3, 9])
    np.testing.assert_allclose(wave.time_s, [-1.0e-9, 0.0, 1.0e-9])
    assert wave.vin_diff_v is not None
    assert wave.vin_diff_v.shape == (2, 3)
    np.testing.assert_allclose(wave.comp_out_v[1], [1.2, 1.2, 0.0])


def test_behavioral_adapter_builds_one_complete_interface_record() -> None:
    params = AdcTbParams(conversions=1)
    wave = build_adc_interface_wave(params, [1] * 17, samples_per_symbol=2)

    assert wave.conversion_index.tolist() == [0]
    assert wave.vin_diff_v is not None
    assert wave.vin_diff_v.shape == (1, 2 * len(params.seq_init_pattern))
    assert wave.seq_comp_v.shape == wave.vin_diff_v.shape
    assert np.count_nonzero(np.diff(wave.comp_out_v[0])) <= 1


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
