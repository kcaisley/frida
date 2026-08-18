"""Software-only tests for the explicit analysis-pipeline command line."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import hdl21 as h
import numpy as np
import pytest

import flow.analysis as analysis_api
import flow.analysis.cdac as cdac_analysis
from flow.analysis import runner
from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.test_adc import adc_measurement, adc_ramp_measurement
from flow.analysis.types import AdcCalibrationMethod, AnalysisAdcCalibration


def test_root_api_exposes_domain_analyses_not_campaign_combiners() -> None:
    """Keep the package root focused on reusable measurement analyses."""

    assert hasattr(analysis_api, "analyze_adc_code_distribution")
    assert hasattr(analysis_api, "analyze_adc_nonlinearity")
    assert hasattr(analysis_api, "analyze_adc_ramp")
    assert hasattr(analysis_api, "analyze_cdac_cap_mismatch")
    assert not hasattr(analysis_api, "combine_adc_noise_comparison")
    assert not hasattr(analysis_api, "classify_comp_common_mode_validity")


def test_runner_exposes_only_named_orchestration_entry_points() -> None:
    """Keep the runner surface limited to explicit, user-invoked pipelines."""

    tree = ast.parse(Path(runner.__file__).read_text())
    private_functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_")
    ]

    assert private_functions == []
    assert not any(target_name.startswith("adc00_adc01_") for target_name in runner.TARGETS)
    assert "adc_transfer_curve" in runner.TARGETS
    assert "adc_ramp_nonlinearity" in runner.TARGETS
    assert "adc_calibration" in runner.TARGETS
    assert "adc00_pex_transfer" not in runner.TARGETS
    assert "adc_code_distributions" in runner.TARGETS
    assert "adc_code_diag" not in runner.TARGETS
    assert "cdac_system_cap_mismatch" in runner.TARGETS
    assert "cdac_cap_mismatch" not in runner.TARGETS
    assert all(len(name) <= 26 for name in runner.TARGETS)


def test_adc_calibration_runner_combines_three_common_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurement = adc_ramp_measurement(cycles=8)
    nominal_ramp = analyze_adc_ramp(measurement)
    nominal_weight = nominal_ramp.curves[0].weights.astype(np.float64)
    nominal_weight *= 4095.0 / np.sum(nominal_weight)

    def calibration(method: AdcCalibrationMethod) -> AnalysisAdcCalibration:
        weight = nominal_weight.copy()
        weight[0] *= {"calibration1": 1.01, "calibration2": 0.99, "calibration3": 1.02}[method]
        weight *= 4095.0 / np.sum(weight)
        return AnalysisAdcCalibration(
            adc_index=0,
            method=method,
            label=method,
            code_max=4095,
            nominal_weight=nominal_weight,
            calibrated_weight=weight,
            weight_from_measurement=np.ones(17, dtype=np.bool_),
            training_sample_count=100,
            validation_sample_count=50,
            output_gain=1.0,
            output_offset_lsb=0.0,
        )

    ramp_dir = tmp_path / "build/scan_adc/20260812_011910"
    ramp_dir.mkdir(parents=True)
    ramp_path = ramp_dir / "adc00.h5"
    ramp_path.touch()
    cdac_dir = tmp_path / "build/scan_cdac/20260804_171234"
    cdac_dir.mkdir(parents=True)
    cdac_path = cdac_dir / "adc00.h5"
    cdac_path.touch()
    fake_ramp = SimpleNamespace(
        param=SimpleNamespace(campaign="adc_ramp", observed_adc=0, board_id="00"),
        daq=SimpleNamespace(dout=range(4_000_000)),
        info=SimpleNamespace(readbacks={}),
    )
    cdac_measurements = (SimpleNamespace(param=SimpleNamespace(board_id="00")),)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasAdcExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda path: fake_ramp if path == ramp_path else object())
    monkeypatch.setattr(
        runner,
        "analyze_cdac_cap_mismatch_campaign",
        lambda *_args, **_kwargs: ((cdac_measurements,), (object(),)),
    )
    monkeypatch.setattr(
        runner,
        "load_board_map",
        lambda: {"boards": {"00": {"comparator_calibration": {0: {"offset_v": 0.0}}}}},
    )
    monkeypatch.setattr(
        runner,
        "analyze_calibration1",
        lambda _measurements, *, comparator_offset_v: calibration("calibration1"),
    )
    monkeypatch.setattr(
        runner,
        "analyze_calibration2",
        lambda _measurement, _ramp: calibration("calibration2"),
    )
    monkeypatch.setattr(
        runner,
        "analyze_calibration3",
        lambda _measurement, _ramp: calibration("calibration3"),
    )
    monkeypatch.setattr(
        runner,
        "analyze_adc_ramp",
        lambda _measurement, *, calibrations=(): analyze_adc_ramp(measurement, calibrations=calibrations),
    )
    for name in (
        "plot_adc_calibration_weights",
        "plot_adc_ramp_transfer",
        "plot_adc_ramp_histogram",
        "plot_adc_nonlinearity",
    ):
        monkeypatch.setattr(runner, name, lambda *_args, **_kwargs: ())

    artifacts = runner.adc_calibration(tmp_path)

    assert [path.name for path in artifacts] == [
        "adc00_calibration_metrics.csv",
        "adc00_calibration_weights.csv",
    ]
    metrics = artifacts[0].read_text()
    weights = artifacts[1].read_text()
    assert all(method in metrics for method in ("calibration1", "calibration2", "calibration3"))
    assert "ideal_weight_lsb" in weights
    assert len(weights.splitlines()) == 18


def test_cdac_analysis_replaces_whole_curves(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never concatenate analog points from two acquisition sessions."""

    measurement_runs = [[], [], []]
    for adc_index in range(4):
        for side in ("p", "n"):
            for element in range(16):
                for direction in ("1to0", "0to1"):
                    for diffcaps in (0, 1):
                        measurement_runs[0].append(
                            SimpleNamespace(
                                param=SimpleNamespace(
                                    campaign="cdac_ab",
                                    board_id="test_board",
                                    observed_adc=adc_index,
                                    cdac_side=side,
                                    cdac_element=element,
                                    cdac_direction=direction,
                                    dac_diffcaps=diffcaps,
                                ),
                                info=SimpleNamespace(backend="spice", readbacks={}),
                                point_index=0,
                            )
                        )
    for point_index in (2, 3, 4):
        measurement_runs[1].append(
            SimpleNamespace(
                param=SimpleNamespace(
                    campaign="cdac_ab",
                    board_id="test_board",
                    observed_adc=0,
                    cdac_side="p",
                    cdac_element=0,
                    cdac_direction="1to0",
                    dac_diffcaps=0,
                ),
                info=SimpleNamespace(backend="spice", readbacks={}),
                point_index=point_index,
            )
        )

    analyzed_measurements = {}

    def analyze(measurements, *, comparator_offset_v):
        assert comparator_offset_v == 8e-3
        analyzed_measurements[measurements[0].param.observed_adc] = measurements
        return SimpleNamespace(adc_index=measurements[0].param.observed_adc)

    monkeypatch.setattr(cdac_analysis, "MeasCdacExt", SimpleNamespace)
    monkeypatch.setattr(cdac_analysis, "analyze_cdac_cap_mismatch", analyze)
    groups, _analyses = cdac_analysis.analyze_cdac_cap_mismatch_campaign(
        measurement_runs,
        adc_indices=(0, 1, 2, 3),
        board_id="test_board",
        comparator_offset_v_by_adc={adc_index: 8e-3 for adc_index in range(4)},
    )
    replaced_curve = [
        measurement
        for measurement in groups[0]
        if (
            measurement.param.cdac_side,
            measurement.param.cdac_element,
            measurement.param.cdac_direction,
            measurement.param.dac_diffcaps,
        )
        == ("p", 0, "1to0", 0)
    ]
    assert [cast(Any, measurement).point_index for measurement in replaced_curve] == [2, 3, 4]


@pytest.mark.parametrize("internal", (False, True), ids=("external", "internal"))
def test_adc_transfer_curve_accepts_external_and_internal_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
) -> None:
    """Let this mixed-source runner declare support for both ADC measurement views."""

    path = tmp_path / "build/adc_pex_monotonic/adc_00.h5"
    path.parent.mkdir(parents=True)
    path.touch()
    expected = adc_measurement([0], internal=internal)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: expected)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "analyze_adc_transfer", lambda measurements: measurements)
    monkeypatch.setattr(
        runner,
        "plot_adc_transfer",
        lambda _measurements, _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )

    assert runner.adc_transfer_curve(tmp_path / "output") == (tmp_path / "output/adc00_transfer_curve.png",)


def test_adc_ramp_runner_reuses_accepted_cdac_analysis_and_completed_ramp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep accepted ramp selection in the runner and plotting measurement-free."""

    measurements = {}
    ramp_dir = tmp_path / "build/scan_adc/20260812_011910"
    ramp_dir.mkdir(parents=True)
    cdac_dir = tmp_path / "build/scan_cdac/20260804_171234"
    cdac_dir.mkdir(parents=True)
    cdac_path = cdac_dir / "adc00.h5"
    cdac_path.touch()
    cdac_groups = []
    cdac_analyses = []
    for adc_index in range(4):
        ramp_path = ramp_dir / f"adc{adc_index:02d}.h5"
        ramp_path.touch()
        ramp_measurement = SimpleNamespace(
            param=SimpleNamespace(campaign="adc_ramp", observed_adc=adc_index, board_id="00"),
            daq=SimpleNamespace(dout=range(4_000_000)),
            info=SimpleNamespace(readbacks={}),
        )
        measurements[ramp_path] = ramp_measurement
        cdac_groups.append(
            (
                SimpleNamespace(
                    param=SimpleNamespace(observed_adc=adc_index, board_id="00"),
                ),
            )
        )
        cdac_analyses.append(
            SimpleNamespace(
                adc_index=adc_index,
            )
        )
    measurements[cdac_path] = object()
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasAdcExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    monkeypatch.setattr(
        runner,
        "analyze_cdac_cap_mismatch_campaign",
        lambda *_args, **_kwargs: (tuple(cdac_groups), tuple(cdac_analyses)),
    )
    monkeypatch.setattr(
        runner,
        "load_board_map",
        lambda: {
            "boards": {"00": {"comparator_calibration": {adc_index: {"offset_v": 0.0} for adc_index in range(4)}}}
        },
    )
    monkeypatch.setattr(
        runner,
        "analyze_calibration1",
        lambda measurements, *, comparator_offset_v: SimpleNamespace(
            adc_index=measurements[0].param.observed_adc,
            comparator_offset_v=comparator_offset_v,
        ),
    )
    monkeypatch.setattr(
        runner,
        "plot_adc_ramp_transfer",
        lambda _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )
    monkeypatch.setattr(
        runner,
        "plot_adc_ramp_histogram",
        lambda _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )
    monkeypatch.setattr(
        runner,
        "plot_adc_ramp_weights",
        lambda _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )
    monkeypatch.setattr(
        runner,
        "plot_adc_nonlinearity",
        lambda _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )

    class Curve:
        decoding = "uncalibrated_dout"
        maximum_abs_dnl = 0.1
        maximum_abs_inl = 0.2
        missing_codes = 0
        maximum_transfer_reversal_dout = 0.5

    monkeypatch.setattr(
        runner,
        "analyze_adc_ramp",
        lambda measurement, *, calibrations: SimpleNamespace(
            adc_index=measurement.param.observed_adc,
            sample_count=4_000_000,
            retained_sample_count=3_999_488,
            reset_excluded_sample_count=512,
            sample_rate_hz=6.25e6,
            ramp_frequency_hz=1e3,
            curves=(Curve(),),
            calibration_adc_index=calibrations[0].adc_index,
        ),
    )

    artifacts = runner.adc_ramp_nonlinearity(tmp_path / "output")

    assert len(artifacts) == 17
    assert artifacts[0] == tmp_path / "output/adc00_ramp_transfer.png"
    assert artifacts[-2] == tmp_path / "output/adc03_ramp_nonlinearity.png"
    assert artifacts[-1] == tmp_path / "output/adc00_adc03_ramp_metrics.csv"


def test_adc_ramp_runner_rejects_incomplete_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require the accepted four-million-conversion capture contract."""

    ramp_dir = tmp_path / "build/scan_adc/20260812_011910"
    ramp_dir.mkdir(parents=True)
    ramp_path = ramp_dir / "adc00.h5"
    ramp_path.touch()
    measurement = adc_ramp_measurement(observed_adc=0)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: measurement)

    with pytest.raises(ValueError, match="complete, valid"):
        runner.adc_ramp_nonlinearity(tmp_path / "output")


def test_adc_noise_vs_comp_time_runner_uses_configured_adc_subset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the configured ADC subset without assuming only ADC00 and ADC01 exist."""

    measurements_by_path = {}
    run_dirs = {
        0: tmp_path / "build/scan_adc/20260802_081407",
        1: tmp_path / "build/loopback_fastrx/20260729_181030",
    }
    for adc_index, run_dir in run_dirs.items():
        run_dir.mkdir(parents=True)
        for rate_mbd in range(80, 1601, 40):
            for logic_offset in range(-3, 4):
                if adc_index == 0:
                    path = run_dir / (
                        f"{rate_mbd}_{logic_offset + 3}_00_adc00_{rate_mbd}mbd_dcp50mv_"
                        f"logic{logic_offset}sym_vcm800mv_test.h5"
                    )
                else:
                    path = run_dir / f"adc01_{rate_mbd}mbd_logic{logic_offset}_rx0_tap0.h5"
                path.touch()
                measurements_by_path[path] = SimpleNamespace(
                    param=SimpleNamespace(
                        observed_adc=adc_index,
                        symbol_rate=rate_mbd * 1e6,
                        seq_logic_phase_delay_symbols=logic_offset,
                        seq_comp_phase_delay_symbols=0,
                        vin_diff=h.Vdc.Params(dc=0.05),
                        vin_cm=h.Vdc.Params(dc=0.8),
                    )
                )

    output_paths = []

    def plot(_measurements, _analysis, *, output_path):
        output_paths.append(output_path)
        return (output_path.with_suffix(".png"),)

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasAdcExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda path: measurements_by_path[path])
    monkeypatch.setattr(runner, "analyze_adc_noise_sweep", lambda _measurements: SimpleNamespace())
    monkeypatch.setattr(runner, "plot_adc_noise_sweep", plot)

    artifacts = runner.adc_noise_vs_comp_time(tmp_path / "output")

    assert [path.name for path in output_paths] == (
        ["adc00_noise_vs_conversion_rate_and_logic_offset", "adc01_noise_vs_conversion_rate_and_logic_offset"]
    )
    assert len(artifacts) == 2


def test_adc_power_runner_combines_measured_and_separate_simulated_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readbacks = {f"{rail}_active_average_power_w": 10.0e-6 for rail in ("vdd_a", "vdd_d", "vdd_dac")}
    readbacks.update({f"{rail}_static_average_power_w": 2.0e-6 for rail in ("vdd_a", "vdd_d", "vdd_dac")})
    physical_by_adc = {
        adc_index: adc_measurement(
            [100, 101, 102],
            observed_adc=adc_index,
            readbacks=readbacks,
        )
        for adc_index in (0, 1)
    }
    simulated = adc_measurement([100, 101, 102], readbacks=readbacks, internal=True)
    measurements_by_path = {}
    sine_dir = tmp_path / "build/scan_adc/20260730_215145_complete"
    sine_dir.mkdir(parents=True)
    for adc_index in (0, 1):
        for rate_mbd in range(80, 1601, 40):
            path = sine_dir / (
                f"point_00_adc{adc_index:02d}_{rate_mbd}mbd_sin9998.77hz_p0mv_1000mvpp_"
                "logicp2sym_vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
            )
            path.touch()
            measurements_by_path[path] = physical_by_adc[adc_index]
    for run_name in ("hdl21gen_noise_vs_rate/20260801_0821", "frida65a_noise_vs_rate/20260731_2353"):
        run_dir = tmp_path / "build/adc" / run_name
        for rate_msps in (2, 6, 10):
            path = run_dir / f"{rate_msps}msps_cm600mv_dc50mv/result.h5"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            measurements_by_path[path] = simulated

    plot_calls = []

    def analyze_power(measurements):
        rates_hz = np.asarray((2.0e6, 6.0e6, 10.0e6)) if len(measurements) == 3 else np.asarray((10.0e6,))
        if len(measurements) > 3:
            rates_hz = np.linspace(0.5e6, 10.0e6, len(measurements))
        return SimpleNamespace(active_conversion_rate_hz=rates_hz)

    def plot_power(_measurements, _analysis, *, output_path, title=None):
        plot_calls.append(("rate", output_path.name, title))
        return (output_path.with_suffix(".png"),)

    def plot_power_waveform(_measurement, _analysis, *, output_path, title):
        plot_calls.append(("waveform", output_path.name, title))
        return (output_path.with_suffix(".png"),)

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", measurements_by_path.__getitem__)
    monkeypatch.setattr(runner, "analyze_adc_power_sweep", analyze_power)
    monkeypatch.setattr(runner, "plot_adc_power_sweep", plot_power)
    monkeypatch.setattr(runner, "plot_adc_power_waveform", plot_power_waveform)
    monkeypatch.setattr(runner, "plot_measurement_waveforms", lambda *_args, output_path, **_kwargs: (output_path,))
    monkeypatch.setattr(runner, "analyze_adc_dynamic", lambda _measurement: object())
    monkeypatch.setattr(runner, "plot_adc_dynamic", lambda *_args, output_path, **_kwargs: (output_path,))

    artifacts = runner.adc_power_vs_rate(tmp_path / "output")

    assert [(kind, name) for kind, name, _title in plot_calls] == [
        ("rate", "adc_power_vs_conversion_rate"),
        ("rate", "spice_ideal_power_vs_conversion_rate"),
        ("waveform", "spice_ideal_10msps_supply_power"),
        ("rate", "spice_pex_power_vs_conversion_rate"),
        ("waveform", "spice_pex_10msps_supply_power"),
    ]
    assert len(artifacts) == 9


def test_main_runs_named_target_in_one_timestamped_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pass one shared derived-artifact directory to the selected target."""

    received_output_dirs: list[Path] = []

    def example_target(output_dir: Path) -> tuple[Path, ...]:
        received_output_dirs.append(output_dir)
        artifact = output_dir / "example.png"
        artifact.write_bytes(b"plot")
        return (artifact,)

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "TARGETS", {"comp_example_target": example_target})
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "comp_example_target"])

    runner.main()

    assert len(received_output_dirs) == 1
    output_dir = received_output_dirs[0]
    assert output_dir.parent == tmp_path / "build/analysis/comp"
    assert re.fullmatch(r"\d{8}_\d{4}", output_dir.name)
    assert (output_dir / "example.png").read_bytes() == b"plot"
    output = capsys.readouterr().out
    assert f"Analysis output: {output_dir}" in output
    assert "Completed comp_example_target: 1 artifacts in " in output


def test_main_without_target_runs_all_in_registration_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run all targets in one output directory when no name is supplied."""

    calls: list[tuple[str, Path]] = []

    def first(output_dir: Path) -> tuple[Path, ...]:
        calls.append(("first", output_dir))
        return ()

    def second(output_dir: Path) -> tuple[Path, ...]:
        calls.append(("second", output_dir))
        return ()

    def missing(output_dir: Path) -> tuple[Path, ...]:
        calls.append(("missing", output_dir))
        raise FileNotFoundError(2, "missing input", "capture.h5")

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(
        runner,
        "TARGETS",
        {"first": first, "missing": missing, "second": second},
    )
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner"])

    runner.main()

    assert [name for name, _output_dir in calls] == ["first", "missing", "second"]
    assert len({output_dir for _name, output_dir in calls}) == 1
    output = capsys.readouterr().out
    assert output.count("Completed ") == 2
    assert "Completed first: 0 artifacts in " in output
    assert "Completed second: 0 artifacts in " in output
    assert "Skipped missing: missing capture.h5 after " in output


def test_main_rejects_unknown_target(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject arbitrary function names before creating an output directory."""

    monkeypatch.setattr(runner, "TARGETS", {"known_target": lambda _output_dir: ()})
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "unknown_target"])

    with pytest.raises(SystemExit, match="2"):
        runner.main()

    assert "invalid choice: 'unknown_target'" in capsys.readouterr().err
