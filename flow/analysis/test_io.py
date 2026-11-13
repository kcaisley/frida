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

from flow import adc
from flow.analysis.io import _read_native, write_measurement
from flow.scans.scan_adc import scope_records_to_adc_wave
from flow.scans.scope import ScopeConns


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
        ScopeConns(ch1="vin_diff" if with_input else "seq_init", ch2="seq_comp", ch3="seq_logic", ch4="comp_out"),
    )

    np.testing.assert_array_equal(wave.record_index, [3, 9])
    np.testing.assert_allclose(wave.time_s, [-1.0e-9, 0.0, 1.0e-9])
    if with_input:
        assert wave.v["vin_diff"].shape == (2, 3)
    else:
        assert "vin_diff" not in wave.v
        np.testing.assert_allclose(wave.v["seq_init"][1], [0.2, 0.1, 0.0])
    np.testing.assert_allclose(wave.v["comp_out"][1], [1.2, 1.2, 0.0])


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

    from flow import capdac, comp
    from flow.adc.test_analysis import adc_measurement, adc_ramp_measurement, adc_timing_measurement
    from flow.capdac.test_analysis import _curve, comparator_offset, switched, transition_of
    from flow.comp.test_analysis import decisions_at

    ramp_measurement = adc_ramp_measurement()
    ramp = adc.analyze_ramp(ramp_measurement)
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
    closure = adc.analyze_timing_closure(timing)
    comparator = decisions_at()
    offset = comp.analyze_offset_noise([comparator])
    curve = _curve("n", "1to0", 0, 2e-3)
    return (
        ramp,
        adc.analyze_code_density_nonlinearity(ramp_measurement, ramp=ramp),
        adc.analyze_dynamic(sine),
        adc.analyze_transfer([sine]),
        adc.analyze_power(power),
        adc.analyze_noise(noise_measurement),
        adc.analyze_operating_conditions([noise_measurement], noise=[adc.analyze_noise(noise_measurement)]),
        adc.analyze_decision_paths(noise_measurement),
        closure,
        adc.analyze_timing_summary(timing, closure=closure),
        offset,
        comp.analyze_common_mode([comparator]),
        transition_of(curve),
        capdac.analyze_cap_mismatch(
            switched(curve), transitions=[transition_of(curve)], comparator=comparator_offset(curve[0], 0.0)
        ),
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


def test_cap_table_reads_a_pex_tables_effective_column_and_a_dacs_measured_steps(tmp_path: Path, monkeypatch) -> None:
    """A PEX per-stage table (CSV): its ``effective_ff`` column; the settling measurement a
    capacitive DAC's characterization keeps (HDF5): each stage's step as measured
    (``capdac.Model.measured_steps``), read and analyzed once a process."""
    import flow.capdac.model as capdac_model
    from flow.analysis import io

    table = tmp_path / "capacitance_table.csv"
    table.write_text("stage,main_ff,diff_ff,effective_ff\n0,2.5,1,1.5\n1,4,1,3\n")
    np.testing.assert_array_equal(io.read_cap_table(table), [1.5, 3.0])
    steps = np.asarray([0.4e-3, -0.8e-3])
    path = tmp_path / "settling" / "result.h5"
    read = []
    monkeypatch.setattr(capdac_model, "read_measurement", lambda source: read.append(source) or "settling")
    monkeypatch.setattr(capdac_model, "analyze_settling", lambda meas: SimpleNamespace(step_v=steps) if meas else None)
    np.testing.assert_array_equal(io.read_cap_table(path), np.abs(steps))
    np.testing.assert_array_equal(io.read_cap_table(path), np.abs(steps))
    assert read == [path]


# The shared reader (``flow.pipeline.read``) on raw output written here as Spectre writes it.


def write_nutbin(path: Path, plots) -> Path:
    """Spectre's nutbin at ``path``: each plot its title ("AC Analysis `ac': ...") and its
    variables in order, the swept one first, each name its unit and values."""
    with path.open("wb") as raw:
        raw.write(b"Title: \nDate: 12:00:00 PM, Wed Jul 29, 2026\n")
        for title, variables in plots:
            columns = [np.asarray(values) for _unit, values in variables.values()]
            kind = "complex" if any(np.iscomplexobj(column) for column in columns) else "real"
            raw.write(f"Plotname: {title}\nFlags: {kind}\n".encode())
            raw.write(f"No. Variables: {len(columns):8d}\nNo. Points: {len(columns[0]):8d}\n".encode())
            for index, (name, (unit, _values)) in enumerate(variables.items()):
                raw.write(f"{'Variables:' if index == 0 else chr(9)}\t{index}\t{name}\t{unit}\n".encode())
            raw.write(b"Binary:\n")
            raw.write(np.stack(columns, axis=1).astype(">c16" if kind == "complex" else ">f8").tobytes())
    return path


def write_psf(folder: Path, name: str, kind: str, body: str) -> None:
    """One analysis of Spectre's PSF ASCII directory: its header, then ``body`` (its types, sweep,
    traces and values)."""
    folder.mkdir(parents=True, exist_ok=True)
    header = f'HEADER\n"PSFversion" "1.00"\n"analysis type" "{kind}"\n"analysis name" "{name}"\n'
    (folder / f"{name}.{kind}").write_text(header + dedent(body) + "END\n")


def small_signal_nutbin(path: Path) -> Path:
    """A run of every analysis nutbin holds: the flow's operating point, a transient, the AC
    response, the transfer functions to the output and a DC sweep of the input source."""
    f = np.asarray([1e3, 1e6, 1e9])
    h = 1 / (1 + 1j * f / 1e6)
    time = np.asarray([0.0, 1e-9, 3e-9])
    swept = np.asarray([0.0, 0.6, 1.2])
    return write_nutbin(
        path,
        [
            (
                "DC Analysis `opdc'",
                {
                    "dummy": ("dummy", [0.0]),
                    "xtop.vvdd:p": ("A", [-2e-6]),
                    "xtop.out": ("V", [0.6]),
                    "xtop.dut.tail": ("V", [0.2]),
                },
            ),
            (
                "Transient Analysis `tran': time = (0 s -> 3 ns)",
                {"time": ("s", time), "xtop.vvdd:p": ("A", [-1e-6, -2e-6, -3e-6]), "xtop.out": ("V", [0.1, 0.5, 0.6])},
            ),
            (
                "AC Analysis `ac': freq = (1 kHz -> 1 GHz)",
                {"freq": ("Hz", f + 0j), "xtop.vvdd:p": ("A", -1e-6 * h), "xtop.out": ("V", h)},
            ),
            (
                "Transfer Function Analysis `xf': freq = (1 kHz -> 1 GHz)",
                {"freq": ("Hz", f + 0j), "xtop.vvdd": ("V/V", 0.01 * h), "xtop.ibias": ("V/A", 1e3 * h)},
            ),
            (
                "DC Analysis `sweep_in': xtop.vin:dc = (0 V -> 1.2 V)",
                {"dc": ("V", swept), "xtop.vin:p": ("A", -1e-6 * swept), "xtop.out": ("V", 0.5 * swept)},
            ),
        ],
    )


def test_the_shared_reader_keeps_a_runs_transient_and_each_other_analysis_by_its_name(tmp_path: Path) -> None:
    """The transient on the simulator's time axis, as a run of it alone reads; beside it each
    other analysis a sweep of its kind, on the simulator's points, its signals named alike (a
    source's current by its net, positive for current drawn; a net inside the DUT by its name)."""
    from flow import pipeline, samp
    from flow.pipeline import SweepKind

    tb = samp.TbParams()
    meas = pipeline.read(small_signal_nutbin(tmp_path / "netlist.raw"), tb)
    assert meas.param is tb and meas.dut == tb.params and meas.info.backend == "spice"
    assert meas.info.readbacks == {"raw_file": "netlist.raw", "raw_points": 3}
    np.testing.assert_array_equal(meas.time_s, [0.0, 1e-9, 3e-9])
    np.testing.assert_array_equal(meas.v["out"], [0.1, 0.5, 0.6])
    np.testing.assert_array_equal(meas.i["vdd"], [1e-6, 2e-6, 3e-6])
    assert {name: sweep.kind for name, sweep in meas.sweeps.items()} == {
        "opdc": SweepKind.OP,
        "ac": SweepKind.AC,
        "xf": SweepKind.XF,
        "sweep_in": SweepKind.DC,
    }
    op, ac, xf, dc = (meas.sweeps[name] for name in ("opdc", "ac", "xf", "sweep_in"))
    assert op.x.shape == (0,) and op.v["out"][0] == 0.6 and op.v["tail"][0] == 0.2 and op.i["vdd"][0] == 2e-6
    f = np.asarray([1e3, 1e6, 1e9])
    h = 1 / (1 + 1j * f / 1e6)
    np.testing.assert_array_equal(ac.x, f)
    assert ac.x.dtype == np.float64 and ac.v["out"].dtype == np.complex128
    np.testing.assert_allclose(ac.v["out"], h)
    np.testing.assert_allclose(ac.i["vdd"], 1e-6 * h)
    # each source's transfer to the output: a voltage source by its net, another by its own name
    assert sorted(xf.v) == ["ibias", "vdd"] and not xf.i
    np.testing.assert_allclose(xf.v["vdd"], 0.01 * h)
    np.testing.assert_array_equal(dc.x, [0.0, 0.6, 1.2])
    assert dc.v["out"].dtype == np.float64
    np.testing.assert_allclose(dc.v["out"], [0.0, 0.3, 0.6])
    np.testing.assert_allclose(dc.i["in"], [0.0, 0.6e-6, 1.2e-6])


def test_a_run_without_a_transient_reads_as_its_sweeps_alone(tmp_path: Path) -> None:
    from flow import pipeline, samp

    f = np.asarray([1e3, 1e6])
    raw = write_nutbin(
        tmp_path / "netlist.raw",
        [("AC Analysis `ac': freq = (1 kHz -> 1 MHz)", {"freq": ("Hz", f + 0j), "xtop.out": ("V", [1 + 0j, 0.5j])})],
    )
    meas = pipeline.read(raw, samp.TbParams())
    assert meas.time_s.shape == (0,) and not meas.v and not meas.i
    assert meas.info.readbacks["raw_points"] == 0
    np.testing.assert_array_equal(meas.sweeps["ac"].v["out"], [1 + 0j, 0.5j])


def test_a_noise_run_reads_from_its_psf_ascii_directory(tmp_path: Path) -> None:
    """A run with a noise analysis writes PSF ASCII, a file an analysis: the noise's densities,
    its gain and each device's total contribution (those of a device's sources apart left out),
    the AC response and the operating point beside it; what is no analysis is passed over."""
    from flow import pipeline, samp
    from flow.pipeline import SweepKind

    raw = tmp_path / "netlist.raw"
    write_psf(
        raw,
        "noise",
        "noise",
        """\
        TYPE
        "sweep" FLOAT DOUBLE PROP(
        "key" "sweep"
        )
        "V/sqrt(Hz)" FLOAT DOUBLE PROP(
        "units" "V/sqrt(Hz)"
        )
        "V/V" FLOAT DOUBLE
        "resistor" STRUCT(
        "rn" FLOAT DOUBLE PROP(
        "units" "V^2/Hz"
        )
        "total" FLOAT DOUBLE PROP(
        "units" "V^2/Hz"
        )
        ) PROP(
        "key" "inst"
        )
        SWEEP
        "freq" "sweep" PROP(
        "units" "Hz"
        )
        TRACE
        "xtop.dut.r" "resistor"
        "out" "V/sqrt(Hz)"
        "in" "V/sqrt(Hz)"
        "gain" "V/V"
        VALUE
        "freq" 1.0e+03
        "xtop.dut.r" (
        1.6e-17
        1.6e-17
        )
        "out" 4.0e-09
        "in" 8.0e-09
        "gain" 5.0e-01
        "freq" 1.0e+06
        "xtop.dut.r" (
        4.0e-18
        4.0e-18
        )
        "out" 2.0e-09
        "in" 8.0e-09
        "gain" 2.5e-01
        """,
    )
    write_psf(
        raw,
        "ac",
        "ac",
        """\
        TYPE
        "sweep" FLOAT DOUBLE
        "V" COMPLEX DOUBLE
        SWEEP
        "freq" "sweep"
        TRACE
        "xtop.out" "V"
        VALUE
        "freq" 1.0e+03
        "xtop.out" (5.0e-01 0.0e+00)
        "freq" 1.0e+06
        "xtop.out" (0.0e+00 -2.5e-01)
        """,
    )
    write_psf(
        raw,
        "op",
        "dc",
        """\
        TYPE
        "V" FLOAT DOUBLE
        "I" FLOAT DOUBLE
        VALUE
        "xtop.vvdd:p" "I" -2.0e-06 PROP(
        "units" "A"
        )
        "xtop.out" "V" 6.0e-01
        """,
    )
    write_psf(
        raw,
        "sweep_vdd",
        "dc",
        """\
        TYPE
        "sweep" FLOAT DOUBLE PROP(
        "key" "sweep"
        )
        "V" FLOAT DOUBLE PROP(
        "units" "V"
        )
        "I" FLOAT DOUBLE PROP(
        "units" "A"
        )
        SWEEP
        "dc" "sweep" PROP(
        "units" "V"
        )
        TRACE
        "xtop.vvdd:p" "I"
        "xtop.out" "V"
        VALUE
        "dc" 0.0e+00
        "xtop.vvdd:p" 0.0e+00
        "xtop.out" 0.0e+00
        "dc" 1.2e+00
        "xtop.vvdd:p" -2.0e-06
        "xtop.out" 6.0e-01
        """,
    )
    write_psf(
        raw,
        "xf",
        "xf",
        """\
        TYPE
        "sweep" FLOAT DOUBLE PROP(
        "key" "sweep"
        )
        "V/V" COMPLEX DOUBLE PROP(
        "units" "V/V"
        )
        "V/A" COMPLEX DOUBLE PROP(
        "units" "V/A"
        )
        SWEEP
        "freq" "sweep" PROP(
        "units" "Hz"
        )
        TRACE
        "xtop.vinp" "V/V"
        "xtop.ibn" "V/A"
        VALUE
        "freq" 1.0e+03
        "xtop.vinp" (5.0e-01 0.0e+00)
        "xtop.ibn" (1.0e+03 0.0e+00)
        "freq" 1.0e+06
        "xtop.vinp" (0.0e+00 -2.5e-01)
        "xtop.ibn" (0.0e+00 -5.0e+02)
        """,
    )
    write_psf(raw, "op", "info", 'VALUE\n"xtop.dut.r" "resistor" 1.0\n')
    # the directory's index, a file in the analyses' format that is none of them
    log = 'TYPE\n"analysisInst" STRUCT(\n"analysisType" STRING *\n"dataFile" STRING *\n)\n'
    (raw / "logFile").write_text(
        f'HEADER\n"PSFversion" "1.00"\n{log}VALUE\n"op-dc" "analysisInst" (\n"dc"\n"op.dc"\n)\nEND\n'
    )
    meas = pipeline.read(raw, samp.TbParams())
    assert meas.time_s.shape == (0,) and meas.info.readbacks["raw_file"] == "netlist.raw"
    assert {name: sweep.kind for name, sweep in meas.sweeps.items()} == {
        "noise": SweepKind.NOISE,
        "ac": SweepKind.AC,
        "op": SweepKind.OP,
        "sweep_vdd": SweepKind.DC,
        "xf": SweepKind.XF,
    }
    noise, ac, op, dc, xf = (meas.sweeps[name] for name in ("noise", "ac", "op", "sweep_vdd", "xf"))
    np.testing.assert_array_equal(noise.x, [1e3, 1e6])
    assert sorted(noise.v) == ["gain", "in", "out", "r.total"] and not noise.i
    np.testing.assert_array_equal(noise.v["out"], [4e-9, 2e-9])
    np.testing.assert_allclose(noise.v["r.total"], noise.v["out"] ** 2)
    np.testing.assert_array_equal(ac.v["out"], [0.5 + 0j, -0.25j])
    assert op.x.shape == (0,) and op.v["out"][0] == 0.6 and op.i["vdd"][0] == 2e-6
    # the DC sweep: the swept source's values, each signal real at each
    np.testing.assert_array_equal(dc.x, [0.0, 1.2])
    assert sorted(dc.v) == ["out"] and sorted(dc.i) == ["vdd"] and dc.v["out"].dtype == np.float64
    np.testing.assert_array_equal(dc.v["out"], [0.0, 0.6])
    np.testing.assert_array_equal(dc.i["vdd"], [0.0, 2e-6])
    # the transfer functions: a voltage source by its net, another source by its own name
    np.testing.assert_array_equal(xf.x, [1e3, 1e6])
    assert sorted(xf.v) == ["ibn", "inp"] and not xf.i and xf.v["inp"].dtype == np.complex128
    np.testing.assert_array_equal(xf.v["inp"], [0.5 + 0j, -0.25j])
    np.testing.assert_array_equal(xf.v["ibn"], [1e3 + 0j, -500j])


def test_an_operating_point_is_told_from_a_sweep_by_its_file_not_its_first_name(tmp_path: Path) -> None:
    """A PSF ASCII operating point has no sweep section and no placeholder variable: one whose
    first saved signal is a net of the bench's top (no ``xtop.`` name) is an operating point all
    the same, that net a signal among the others; nutbin's is told by its placeholder."""
    from flow import pipeline, samp
    from flow.pipeline import SweepKind

    psf = tmp_path / "psf" / "netlist.raw"
    body = 'TYPE\n"V" FLOAT DOUBLE\nVALUE\n"qmeter" "V" 1.0e-03\n"xtop.out" "V" 6.0e-01\n'
    write_psf(psf, "opdc", "dc", body)
    point = {"dummy": ("dummy", [0.0]), "qmeter": ("V", [1e-3]), "xtop.out": ("V", [0.6])}
    nutbin = write_nutbin(tmp_path / "netlist.raw", [("DC Analysis `opdc'", point)])
    for raw in (psf, nutbin):
        op = pipeline.read(raw, samp.TbParams()).sweeps["opdc"]
        assert op.kind is SweepKind.OP and op.x.shape == (0,)
        assert sorted(op.v) == ["out", "qmeter"] and op.v["qmeter"][0] == 1e-3 and op.v["out"][0] == 0.6


def test_a_monte_carlo_of_operating_points_reads_a_value_a_run_beside_its_nominal_point(tmp_path: Path) -> None:
    from flow import pipeline, samp
    from flow.pipeline import SweepKind

    def point(name: str, value: float):
        return (f"DC Analysis `{name}'", {"dummy": ("dummy", [0.0]), "xtop.dut.c.drawn": ("V", [value])})

    # the family's plots as Spectre writes them, a run each, here out of order
    raw = write_nutbin(tmp_path / "netlist.raw", [point("op", 2.0), point("mc-002_op", 2.2), point("mc-001_op", 2.1)])
    meas = pipeline.read(raw, samp.TbParams())
    assert meas.time_s.shape == (0,) and meas.info.readbacks["runs"] == 2
    np.testing.assert_array_equal(meas.v["c.drawn"], [2.1, 2.2])
    assert list(meas.sweeps) == ["op"] and meas.sweeps["op"].kind is SweepKind.OP
    assert meas.sweeps["op"].v["c.drawn"][0] == 2.0


def test_the_shared_reader_refuses_what_it_cannot_tell(tmp_path: Path) -> None:
    from flow import pipeline, samp

    tb = samp.TbParams()
    time = {"time": ("s", [0.0, 1e-9]), "xtop.out": ("V", [0.0, 1.0])}
    two = write_nutbin(tmp_path / "two.raw", [("Transient Analysis `a'", time), ("Transient Analysis `b'", time)])
    with pytest.raises(ValueError, match="holds 2 transients"):
        pipeline.read(two, tb)
    empty = tmp_path / "empty.raw"
    empty.write_bytes(b"Title: \n")
    with pytest.raises(ValueError, match="holds 0 transients"):
        pipeline.read(empty, tb)
    other = write_nutbin(
        tmp_path / "other.raw",
        [("Stability Analysis `stb': freq = (1 Hz -> 1 GHz)", {"freq": ("Hz", [1 + 0j]), "loopGain": ("V", [2 + 0j])})],
    )
    with pytest.raises(ValueError, match="analysis stb is of a kind the shared reader does not read"):
        pipeline.read(other, tb)


def test_a_measurement_with_sweeps_survives_hdf5(tmp_path: Path) -> None:
    from flow import pipeline, samp
    from flow.analysis.io import read_measurement

    meas = pipeline.read(small_signal_nutbin(tmp_path / "netlist.raw"), samp.TbParams())
    loaded = read_measurement(write_measurement(tmp_path / "result.h5", meas))
    assert loaded.sweeps.keys() == meas.sweeps.keys()
    for name, sweep in meas.sweeps.items():
        kept = loaded.sweeps[name]
        assert kept.kind is sweep.kind and kept.v.keys() == sweep.v.keys() and kept.i.keys() == sweep.i.keys()
        np.testing.assert_array_equal(kept.x, sweep.x)
        for signals, found in ((sweep.v, kept.v), (sweep.i, kept.i)):
            for key, values in signals.items():
                assert found[key].dtype == values.dtype
                np.testing.assert_array_equal(found[key], values)


def test_raw_output_is_discarded_as_a_file_or_a_directory(tmp_path: Path) -> None:
    from flow import pipeline

    nutbin = small_signal_nutbin(tmp_path / "netlist.raw")
    # the devices' operating points an hs.Op writes beside a nutbin file go with it
    points = tmp_path / "netlist.raw.psf"
    write_psf(points, "op", "info", 'VALUE\n"xtop.dut.r" "resistor" 1.0\n')
    pipeline.discard(nutbin)
    psf = tmp_path / "psf" / "netlist.raw"
    write_psf(psf, "op", "dc", 'TYPE\n"V" FLOAT DOUBLE\nVALUE\n"xtop.out" "V" 6.0e-01\n')
    pipeline.discard(psf)
    assert not nutbin.exists() and not points.exists() and not psf.exists()
    assert [path.name for path in tmp_path.iterdir()] == ["psf"] and not list(psf.parent.iterdir())
