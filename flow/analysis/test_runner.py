"""Software-only tests for the explicit analysis-pipeline command line."""

from __future__ import annotations

import ast
import dataclasses
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hdl21 as h
import numpy as np
import pytest

import flow.analysis as analysis_api
from flow.adc.sequences import SEQUENCES
from flow.analysis import runner
from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.io import read_analysis
from flow.analysis.test_adc import adc_measurement, adc_ramp_measurement
from flow.analysis.types import (
    AnalysisAdcCalibration,
    AnalysisAdcCodeDensityNonlinearity,
    AnalysisAdcOperatingConditions,
    AnalysisAdcTimingSummary,
)


def test_root_api_exposes_domain_analyses_not_campaign_combiners() -> None:
    """Keep the package root focused on reusable measurement analyses."""

    assert hasattr(analysis_api, "analyze_adc_code_distribution")
    assert hasattr(analysis_api, "analyze_adc_code_density_nonlinearity")
    assert hasattr(analysis_api, "analyze_adc_ramp")
    assert hasattr(analysis_api, "analyze_cdac_cap_mismatch")
    assert not hasattr(analysis_api, "combine_adc_noise_comparison")
    assert not hasattr(analysis_api, "classify_comp_common_mode_validity")
    assert not hasattr(analysis_api, "analyze_adc_noise_sweep")
    assert not hasattr(analysis_api, "analyze_adc_dynamic_sweep")


def test_runner_exposes_only_named_orchestration_entry_points() -> None:
    """Keep the public runner surface limited to explicit, user-invoked pipelines.

    Private helpers implement shared stages (input selection and prior-result
    analyses) used by several pipelines.
    """

    tree = ast.parse(Path(runner.__file__).read_text())
    public_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }

    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    registry = next(node for node in main.body if isinstance(node, ast.AnnAssign))
    assert isinstance(registry.value, ast.DictComp)
    entries = registry.value.generators[0].iter
    assert isinstance(entries, ast.Tuple)
    targets = {ast.unparse(node) for node in entries.elts}
    assert not hasattr(runner, "TARGETS")
    assert public_functions == {*targets, "main"}
    assert targets == {
        "adc_transfer_curve_study",
        "adc_ramp_nonlinearity_study",
        "adc_calibration_study",
        "adc_sequence_study",
        "adc_sample_rate_study",
        "adc_power_study",
        "comp_system_common_mode_study",
        "comp_system_sampling_noise_study",
        "comp_candidate_sweep_study",
        "cdac_system_cap_mismatch_study",
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            assert [arg.arg for arg in node.args.args] == ["output_dir"]
            assert not node.args.kwonlyargs
            assert node.returns is not None
            assert ast.unparse(node.returns) == "tuple[Path, ...]"


def test_sequence_plots_stored_measurements_without_redecoding(tmp_path: Path, monkeypatch) -> None:
    campaigns = (
        ("frida-20260926_215421_042700", "frida1_sequence", "20260926_221031_frida1_sequence", (1, 2), (17, 20)),
        ("frida-20260926_215427_988306", "frida2_sequence", "20260926_221039_frida2_sequence", (1, 2, 3), (17,)),
    )
    timings = (
        "symbol160_init4_samp20_comp11110000_logic00001111",
        "symbol160_init4_samp20_comp11110000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11100001",
        "symbol160_init4_samp20_comp11111110_logic11100001",
    )
    for session, target, stamp, layers, radices in campaigns:
        campaign = tmp_path / "build/remote" / session
        campaign.mkdir(parents=True)
        for layer in layers:
            for radix in radices:
                for timing in timings:
                    path = (
                        campaign
                        / "results/sim/adc"
                        / stamp
                        / f"{target[:6]}_{layer}layer_radix{radix}"
                        / timing
                        / "result.h5"
                    )
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b"unchanged measurement")
        # Unrelated results must not enter this explicitly pinned comparison.
        (campaign / "result.h5").write_bytes(b"unrelated")

    historical = tmp_path / "build/remote/frida-20260906_124441_733878/result.h5"
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"historical measurement")
    output_dir = tmp_path / "output"
    sequence_name, sequence = next(
        (name, seq) for name, seq in runner.SEQUENCES if name.startswith("symbol160_init4_samp20_")
    )
    monkeypatch.setattr(runner, "SEQUENCES", ((sequence_name, sequence),))
    physical_dir = tmp_path / "build/scan_adc/20260926_172920_adc_sequence_static"
    physical_dir.mkdir(parents=True)
    physical_captures = {}
    for adc in range(16):
        for baud_mbd in (320, 960, 1600):
            path = physical_dir / f"{len(physical_captures):04d}_capture.h5"
            path.touch()
            physical_captures[path] = adc, baud_mbd
    (physical_dir / "scope_diagnostic.h5").touch()
    output_dir.mkdir()
    # Neither output files nor another acquisition directory can override inputs.
    (output_dir / "0000_unrelated.h5").touch()
    case_count = 49
    clock_count = 7
    selected_cases = []

    from flow.analysis.test_adc import adc_timing_measurement

    physical = adc_measurement(np.tile([100, 101], 50_000), observed_adc=0)
    historical_sequence = dataclasses.replace(sequence, logic="00010000" + sequence.logic[8:])
    physical = dataclasses.replace(
        physical,
        param=dataclasses.replace(
            physical.param,
            tb=dataclasses.replace(
                physical.param.tb,
                vin_diff=h.Vdc.Params(dc=0.05),
                **historical_sequence.as_tb_fields(),
            ),
        ),
    )

    pex_sequences = dict(SEQUENCES)

    def load(path):
        if path in physical_captures:
            adc, baud_mbd = physical_captures[path]
            return dataclasses.replace(
                physical,
                index=adc,
                param=dataclasses.replace(
                    physical.param,
                    observed_adc=adc,
                    tb=dataclasses.replace(physical.param.tb, symbol_rate=baud_mbd * 1e6),
                ),
                info=dataclasses.replace(
                    physical.info,
                    backend="physical",
                    readbacks={
                        "scope_fastrx_comparison_valid": True,
                        "scope_fastrx_bit_mismatches": 0,
                        "fastrx_lost_count": 0,
                    },
                ),
            )
        assert path.read_bytes() == b"unchanged measurement"
        selected_cases.append("/".join(path.parts[-3:]))
        measurement = adc_timing_measurement()
        assert measurement.wave is not None
        # The sequence clock figure shows the second saved conversion.
        measurement = dataclasses.replace(
            measurement,
            wave=dataclasses.replace(
                measurement.wave,
                record_index=np.arange(2),
                v={name: np.repeat(trace, 2, axis=0) for name, trace in measurement.wave.v.items()},
                i={name: np.repeat(trace, 2, axis=0) for name, trace in measurement.wave.i.items()},
            ),
        )
        sequence = pex_sequences[path.parent.name]
        return dataclasses.replace(measurement, param=dataclasses.replace(measurement.param, **sequence.as_tb_fields()))

    monkeypatch.setattr(runner, "read_measurement", load)
    monkeypatch.setattr(
        runner, "read_measurement_param", lambda path: SimpleNamespace(observed_adc=physical_captures[path][0])
    )
    monkeypatch.setattr(runner, "analyze_adc_decision_paths", lambda *args, **kwargs: object())
    monkeypatch.setattr(runner, "analyze_adc_cdac_settling", lambda *args: object())

    def plot(*args, output_path, **kwargs):
        if output_path.name == "all_adc_sequence_overview":
            assert len(args[0]) == 16
            assert all(isinstance(result, AnalysisAdcOperatingConditions) for result in args[0])
        if output_path.name.startswith("adc") and output_path.name.endswith("_sequence_enob"):
            assert isinstance(args[0], AnalysisAdcOperatingConditions)
            assert len(args[0].symbol_rate_hz) == 3
        return (output_path.with_suffix(".pdf"),)

    for name in (
        "plot_adc_sequence_chip_overview",
        "plot_adc_sequence_enob",
        "plot_adc_decision_path_density",
        "plot_adc_cdac_settling",
        "plot_waveforms",
        "plot_adc_noise_sweep",
        "plot_adc_code_distribution",
    ):
        monkeypatch.setattr(runner, name, plot)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)

    artifacts = runner.adc_sequence_study(output_dir)
    flavor_count = 7
    assert len(artifacts) == 2 * 16 + 1 + 4 * case_count + clock_count + 2 * flavor_count
    assert len([path for path in artifacts if path.name.endswith("_sequence_enob.pdf")]) == 16
    assert len(set(selected_cases)) == case_count
    # Runners save figures and analysis HDF5 only: no CSV, JSON, text, or TeX reports.
    assert not [path for path in output_dir.iterdir() if path.suffix in {".csv", ".json", ".txt", ".tex", ".md"}]
    operating = sorted(output_dir.glob("*_operating_conditions.h5"))
    assert len(operating) == 16 + flavor_count
    assert all(isinstance(read_analysis(path), AnalysisAdcOperatingConditions) for path in operating)
    summaries = sorted(output_dir.glob("*_timing_summary.h5"))
    assert len(summaries) == case_count
    assert all(isinstance(read_analysis(path), AnalysisAdcTimingSummary) for path in summaries)


def install_cdac_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, adc_indices=(0, 1)) -> dict[str, Any]:
    """Create placeholder CDAC and comparator files whose reads return marked fakes.

    The first CDAC run holds every curve; the second reacquires ADC00's
    (p, C0, 1to0, diffcaps 0) curve with points 2, 3, and 4.
    """

    def point(adc_index, side, element, direction, diffcaps, point_index, stage="fine"):
        return SimpleNamespace(
            param=SimpleNamespace(
                campaign="cdac_ab",
                observed_adc=adc_index,
                cdac_side=side,
                cdac_element=element,
                cdac_direction=direction,
                sweep_stage=stage,
                tb=SimpleNamespace(dac_diffcaps=diffcaps),
            ),
            info=SimpleNamespace(backend="spice", readbacks={}),
            point_index=point_index,
        )

    runs = {
        "20260804_171234": [
            point(adc_index, side, element, direction, diffcaps, 0, stage)
            for adc_index in adc_indices
            for side in ("p", "n")
            for element in range(2)
            for direction in ("1to0", "0to1")
            for diffcaps in (0, 1)
            for stage in ("coarse", "fine")
        ],
        "20260804_193030": [point(0, "p", 0, "1to0", 0, index) for index in (2, 3, 4)],
        "20260804_193631": [],
    }
    by_path: dict[Path, object] = {}
    for run_name, points in runs.items():
        directory = tmp_path / "build/scan_cdac" / run_name
        directory.mkdir(parents=True)
        for index, value in enumerate(points):
            path = directory / f"{index:05d}.h5"
            path.touch()
            by_path[path] = value
    comparator_dirs = {0: "20260804_051653", 1: "20260804_053759", 2: "20260804_051653", 3: "20260804_054953"}
    for adc_index in adc_indices:
        path = tmp_path / "build/scan_comp" / comparator_dirs[adc_index] / f"adc{adc_index:02d}.h5"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        by_path[path] = SimpleNamespace(comparator=adc_index)
    received: dict[str, Any] = {"mismatch": {}}

    def offset_noise(points):
        return ("fit", tuple(points))

    def transition(points, *, offset):
        assert offset == ("fit", tuple(points))
        return ("transition", tuple(points))

    def cap_mismatch(measurements, *, transitions, comparator):
        adc_index = measurements[0].param.observed_adc
        received["mismatch"][adc_index] = SimpleNamespace(
            measurements=measurements, transitions=transitions, comparator=comparator
        )
        return SimpleNamespace(index=adc_index)

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasCdac", SimpleNamespace)
    monkeypatch.setattr(runner, "MeasComp", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", by_path.__getitem__)
    monkeypatch.setattr(runner, "analyze_comp_offset_noise", offset_noise)
    monkeypatch.setattr(runner, "analyze_cdac_transition", transition)
    monkeypatch.setattr(runner, "analyze_cdac_cap_mismatch", cap_mismatch)
    received["by_path"] = by_path
    return received


def test_adc_calibration_runner_combines_three_common_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurement = adc_ramp_measurement(cycles=8)
    nominal_ramp = analyze_adc_ramp(measurement)
    nominal_weight = nominal_ramp.weights.astype(np.float64)
    nominal_weight *= 4095.0 / np.sum(nominal_weight)

    def calibration(method) -> AnalysisAdcCalibration:
        weight = nominal_weight.copy()
        weight[0] *= {"calibration1": 1.01, "calibration2": 0.99, "calibration3": 1.02}[method]
        weight *= 4095.0 / np.sum(weight)
        return AnalysisAdcCalibration(
            group=measurement.group,
            index=measurement.index,
            dut=measurement.dut,
            method=method,
            label=method,
            code_max=4095,
            nominal_weights=nominal_weight,
            calibrated_weights=weight,
            measured_weight_mask=np.ones(17, dtype=np.bool_),
            training_sample_count=100,
            validation_sample_count=50,
            output_gain=1.0,
            output_offset_lsb=0.0,
        )

    received = install_cdac_inputs(tmp_path, monkeypatch)
    ramp_path = tmp_path / (
        "build/scan_adc/20260812_011910/"
        "0000_00_adc00_160mbd_pwl10hz_m1000top1000mv_logicp0sym_"
        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
    )
    received["by_path"][ramp_path] = measurement

    def calibration1(measurements, *, cap_mismatch):
        received["calibration1"] = (measurements, cap_mismatch)
        return calibration("calibration1")

    monkeypatch.setattr(runner, "analyze_adc_calibration1", calibration1)
    monkeypatch.setattr(runner, "analyze_adc_calibration2", lambda _m, *, ramp: calibration("calibration2"))
    monkeypatch.setattr(runner, "analyze_adc_calibration3", lambda _m, *, ramp: calibration("calibration3"))
    plotted = []
    for name in (
        "plot_adc_calibration_weights",
        "plot_adc_ramp_transfer",
        "plot_adc_ramp_histogram",
        "plot_adc_ramp_nonlinearity",
    ):
        monkeypatch.setattr(runner, name, lambda analysis, **_kwargs: plotted.append(analysis) or ())
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    assert runner.adc_calibration_study(output_dir) == ()
    # Only ADC00's curves reach calibration 1, together with ADC00's mismatch result.
    measurements, cap_mismatch = received["calibration1"]
    assert {point.param.observed_adc for point in measurements} == {0}
    assert cap_mismatch.index == 0
    assert set(received["mismatch"]) == {0}
    assert received["mismatch"][0].comparator == (
        "fit",
        (received["by_path"][next(path for path in received["by_path"] if path.name == "adc00.h5")],),
    )
    assert [ramp.decoding for ramp in plotted[-1]] == [
        "uncalibrated_dout",
        "calibration1",
        "calibration2",
        "calibration3",
    ]
    assert not list(output_dir.iterdir())


def test_cdac_runner_replaces_whole_curves_and_uses_each_adc_comparator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never concatenate analog points from two acquisition sessions."""

    received = install_cdac_inputs(tmp_path, monkeypatch, adc_indices=(0, 1))
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch", lambda *_args, output_path: (output_path,))
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch_comparison", lambda *_args, output_path: (output_path,))

    artifacts = runner.cdac_system_cap_mismatch_study(tmp_path / "output")

    assert [path.name for path in artifacts] == [
        "adc00_cdac_cap_mismatch",
        "adc01_cdac_cap_mismatch",
        "adc00_adc03_cdac_cap_mismatch_comparison",
    ]
    adc00 = received["mismatch"][0]
    replaced_curve = [
        point
        for point in adc00.measurements
        if (point.param.cdac_side, point.param.cdac_element, point.param.cdac_direction, point.param.tb.dac_diffcaps)
        == ("p", 0, "1to0", 0)
    ]
    assert [point.point_index for point in replaced_curve] == [2, 3, 4]
    # Every other curve keeps both stages, and only its fine points are fitted.
    assert len(adc00.measurements) == 2 * 2 * 2 * 2 * 2 - 2 + 3
    assert all(all(point.param.sweep_stage == "fine" for point in transition[1]) for transition in adc00.transitions)
    assert len(adc00.transitions) == 2 * 2 * 2 * 2
    assert received["mismatch"][1].comparator[1][0].comparator == 1


def test_adc_transfer_curve_loads_pinned_directory_without_reconstructing_grid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate transfer-coordinate validation to the typed analysis."""

    meas_read_dir = tmp_path / "build/scan_adc/20260818_135848"
    meas_read_dir.mkdir(parents=True)
    measurements = {}
    for point_index, input_v in enumerate((-0.75, 0.0, 0.75)):
        path = meas_read_dir / f"{point_index:04d}_adc00.h5"
        path.touch()
        measurement = adc_measurement(
            np.full(7, 2048),
            vin_diff_v=input_v,
            sample_rate_hz=3.0e6,
            observed_adc=0,
        )
        measurements[path] = dataclasses.replace(
            measurement,
            info=dataclasses.replace(measurement.info, backend="physical"),
            param=dataclasses.replace(
                measurement.param,
                campaign="adc_transfer",
                board_id=3,
                tb=dataclasses.replace(
                    measurement.param.tb,
                    conversions=7,
                    vin_cm=h.Vdc.Params(dc=0.615),
                    vin_diff=h.Vdc.Params(dc=input_v),
                ),
            ),
        )
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "analyze_adc_transfer", lambda measurements: measurements)
    monkeypatch.setattr(
        runner,
        "plot_adc_transfer",
        lambda _measurements, _analysis, *, output_path: (output_path.with_suffix(".png"),),
    )

    assert runner.adc_transfer_curve_study(tmp_path / "output") == (tmp_path / "output/adc00_transfer_curve.png",)


def test_adc_ramp_runner_rejects_wrong_measurement_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the runner boundary at the typed measurement object."""

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: object())
    path = tmp_path / "build/scan_adc/20260812_011910/0000_adc00.h5"
    path.parent.mkdir(parents=True)
    path.touch()

    with pytest.raises(TypeError, match="expected MeasAdc"):
        runner.adc_ramp_nonlinearity_study(tmp_path / "output")


def test_comp_common_mode_groups_adc_and_common_mode_from_h5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meas_read_dir = tmp_path / "build/scan_comp/20260805_171216"
    meas_read_dir.mkdir(parents=True)
    measurements_by_path = {}
    for adc_index in (2, 5):
        for point_index, common_mode_v in enumerate((0.9, 0.7)):
            path = meas_read_dir / f"adc{adc_index:02d}_{point_index}.h5"
            path.touch()
            measurements_by_path[path] = SimpleNamespace(
                index=adc_index,
                tb=SimpleNamespace(vin_cm=h.Vdc.Params(dc=common_mode_v)),
            )

    plotted = []
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasComp", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", measurements_by_path.__getitem__)
    monkeypatch.setattr(runner, "analyze_comp_offset_noise", lambda group: tuple(group))

    def common_mode(measurements, *, offsets):
        return ("common-mode", tuple(measurements), tuple(offsets))

    monkeypatch.setattr(runner, "analyze_comp_common_mode", common_mode)
    monkeypatch.setattr(
        runner,
        "plot_comp_common_mode_campaign",
        lambda measurements, offsets, result, *, output_path: (
            plotted.append((offsets, result, output_path)) or (output_path,)
        ),
    )

    runner.comp_system_common_mode_study(tmp_path / "output")

    assert [path.name for _offsets, _result, path in plotted] == [
        "adc02_comparator_common_mode",
        "adc05_comparator_common_mode",
    ]
    offsets, result, _path = plotted[0]
    assert [float(group[0].tb.vin_cm.dc) for group in offsets] == [0.7, 0.9]
    assert result[0] == "common-mode" and result[2] == tuple(offsets)


def test_comp_sampling_noise_replaces_exact_correction_curves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_meas_read_dir = tmp_path / "build/scan_comp/20260805_183915"
    correction_meas_read_dir = tmp_path / "build/scan_comp/20260805_192902"
    base_meas_read_dir.mkdir(parents=True)
    correction_meas_read_dir.mkdir(parents=True)
    measurements_by_path = {}

    def add(directory: Path, name: str, adc_index: int, coupling: float, mode: str, marker: str) -> None:
        path = directory / f"{name}.h5"
        path.touch()
        measurements_by_path[path] = SimpleNamespace(
            marker=marker,
            index=adc_index,
            param=SimpleNamespace(
                observed_adc=adc_index,
                requested_dac_rail_percent=coupling,
                sampling_mode=mode,
            ),
        )

    add(base_meas_read_dir, "adc01_target_a", 1, 100.0, "track", "base-adc01-target-a")
    add(base_meas_read_dir, "adc01_target_b", 1, 100.0, "track", "base-adc01-target-b")
    add(base_meas_read_dir, "adc01_keep", 1, 50.0, "hold", "base-adc01-keep")
    add(base_meas_read_dir, "adc02_target_a", 2, 75.0, "track", "base-adc02-target-a")
    add(base_meas_read_dir, "adc02_target_b", 2, 75.0, "track", "base-adc02-target-b")
    add(base_meas_read_dir, "adc02_keep", 2, 25.0, "hold", "base-adc02-keep")
    add(correction_meas_read_dir, "adc01_a", 1, 100.0, "track", "correction-adc01-a")
    add(correction_meas_read_dir, "adc01_b", 1, 100.0, "track", "correction-adc01-b")
    add(correction_meas_read_dir, "adc02_a", 2, 75.0, "track", "correction-adc02-a")
    add(correction_meas_read_dir, "adc02_b", 2, 75.0, "track", "correction-adc02-b")

    analyzed_groups = {}

    def analyze(group):
        first = group[0]
        key = (
            first.param.observed_adc,
            first.param.requested_dac_rail_percent,
            first.param.sampling_mode,
        )
        analyzed_groups[key] = tuple(measurement.marker for measurement in group)
        return SimpleNamespace()

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasComp", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", measurements_by_path.__getitem__)
    monkeypatch.setattr(runner, "analyze_comp_offset_noise", analyze)
    monkeypatch.setattr(
        runner,
        "plot_comp_sampling_campaign",
        lambda *_args, output_path: (output_path,),
    )

    runner.comp_system_sampling_noise_study(tmp_path / "output")

    assert analyzed_groups[(1, 100.0, "track")] == ("correction-adc01-a", "correction-adc01-b")
    assert analyzed_groups[(2, 75.0, "track")] == ("correction-adc02-a", "correction-adc02-b")
    assert analyzed_groups[(1, 50.0, "hold")] == ("base-adc01-keep",)
    assert analyzed_groups[(2, 25.0, "hold")] == ("base-adc02-keep",)


def test_comp_candidate_sweep_delegates_validity_to_typed_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "build/comp/frida65_candidate_scurve_power/candidates/fixture/result.h5"
    path.parent.mkdir(parents=True)
    path.touch()
    measurement = SimpleNamespace(info=SimpleNamespace(readbacks={"candidate_id": "fixture"}))
    received = {}

    def candidate(value, *, offset, timing, power):
        received.update(measurement=value, offset=offset, timing=timing, power=power)
        return SimpleNamespace(candidate_id="fixture")

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasComp", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: measurement)
    monkeypatch.setattr(runner, "analyze_comp_offset_noise", lambda values: ("offset", tuple(values)))
    monkeypatch.setattr(runner, "analyze_comp_timing", lambda values: ("timing", tuple(values)))
    monkeypatch.setattr(runner, "analyze_comp_power", lambda values: ("power", tuple(values)))
    monkeypatch.setattr(runner, "analyze_comp_candidate", candidate)
    monkeypatch.setattr(runner, "plot_comp_candidate_sweep", lambda *_args, output_path: (output_path,))
    monkeypatch.setattr(runner, "plot_comp_noise_power_tradeoff", lambda *_args, output_path: (output_path,))

    artifacts = runner.comp_candidate_sweep_study(tmp_path / "output")

    assert [artifact.name for artifact in artifacts] == [
        "comp_candidate_noise_power_settling",
        "comp_candidate_noise_power_tradeoff",
    ]
    assert received == {
        "measurement": measurement,
        "offset": ("offset", (measurement,)),
        "timing": ("timing", (measurement,)),
        "power": ("power", (measurement,)),
    }
    assert not (tmp_path / "output").exists()


def test_main_runs_named_target_in_one_timestamped_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pass one shared derived-artifact directory to the selected target."""

    received_output_dirs: list[Path] = []

    def comp_system_common_mode_study(output_dir: Path) -> tuple[Path, ...]:
        received_output_dirs.append(output_dir)
        artifact = output_dir / "example.png"
        artifact.write_bytes(b"plot")
        return (artifact,)

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "comp_system_common_mode_study", comp_system_common_mode_study)
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "comp_system_common_mode_study"])

    runner.main()

    assert len(received_output_dirs) == 1
    output_dir = received_output_dirs[0]
    assert output_dir.parent == tmp_path / "build/analysis/comp"
    assert re.fullmatch(r"\d{8}_\d{6}", output_dir.name)
    assert (output_dir / "example.png").read_bytes() == b"plot"
    output = capsys.readouterr().out
    assert f"Analysis output: {output_dir}" in output
    assert "Completed comp_system_common_mode_study: 1 artifacts" in output


def test_main_requires_a_target(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner"])
    with pytest.raises(SystemExit, match="2"):
        runner.main()
    assert not (tmp_path / "build").exists()


def test_main_propagates_missing_input(tmp_path, monkeypatch):
    def adc_transfer_curve_study(output_dir):
        raise FileNotFoundError("capture.h5")

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "adc_transfer_curve_study", adc_transfer_curve_study)
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "adc_transfer_curve_study"])
    with pytest.raises(FileNotFoundError, match="capture.h5"):
        runner.main()


def test_main_rejects_unknown_target(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject arbitrary function names before creating an output directory."""

    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "unknown_target"])

    with pytest.raises(SystemExit, match="2"):
        runner.main()

    assert "invalid choice: 'unknown_target'" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--capture-decodes", "--additional-campaign", "--inputs"])
def test_main_rejects_experiment_flags(flag, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "adc_sequence_study", flag])
    with pytest.raises(SystemExit, match="2"):
        runner.main()


def test_ramp_study_uses_the_ramp_wrap_exclusion_and_no_cdac_measurements(tmp_path, monkeypatch):
    directory = tmp_path / "build/scan_adc/20260812_011910"
    directory.mkdir(parents=True)
    measurements = {}
    for adc_index in range(4):
        path = directory / f"{adc_index:04d}_adc{adc_index:02d}.h5"
        path.touch()
        measurements[path] = adc_ramp_measurement(observed_adc=adc_index)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    plotted = []

    def plot(measurement, analysis, *, output_path):
        if isinstance(analysis, AnalysisAdcCodeDensityNonlinearity):
            assert analysis.retained_sample_count < analysis.sample_count
            plotted.append(measurement.index)
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_code_distribution", plot)
    monkeypatch.setattr(runner, "plot_adc_static_nonlinearity", plot)
    assert len(runner.adc_ramp_nonlinearity_study(tmp_path / "output")) == 8
    assert plotted == [0, 1, 2, 3]


def test_sample_rate_study_separates_sequences_inputs_and_spectral_data(tmp_path, monkeypatch):
    measurements = {}
    for stamp in ("20260801_194930", "20260802_021624", "20260802_081407", "20260730_215145_complete"):
        directory = tmp_path / "build/scan_adc" / stamp
        directory.mkdir(parents=True)
        for index, (phase, rate) in enumerate(((-3, 0.5e6), (-3, 1e6), (2, 0.5e6), (2, 1e6))):
            path = directory / f"{index:04d}_adc01.h5"
            path.touch()
            value = adc_measurement(
                [100, 101, 102, 100], observed_adc=1, sample_rate_hz=rate, logic_phase_delay_symbols=phase
            )
            # Hardware stores a rate-dependent common FastRX alignment rotation.
            shift = 5 if rate == 0.5e6 else 0
            value = dataclasses.replace(
                value,
                param=dataclasses.replace(
                    value.param,
                    tb=dataclasses.replace(
                        value.param.tb,
                        **{
                            name: getattr(value.param.tb, name)[shift:] + getattr(value.param.tb, name)[:shift]
                            for name in (
                                "seq_init_pattern",
                                "seq_samp_pattern",
                                "seq_comp_pattern",
                                "seq_logic_pattern",
                            )
                        },
                    ),
                ),
            )
            if stamp != "20260730_215145_complete":
                value = dataclasses.replace(
                    value,
                    param=dataclasses.replace(
                        value.param, tb=dataclasses.replace(value.param.tb, vin_diff=h.Vdc.Params(dc=0.05))
                    ),
                )
            measurements[path] = value
    # A consolidated acquisition can contain both stimulus types in one directory.
    for directory in {path.parent for path in measurements}:
        path = directory / "9999_capture.h5"
        path.touch()
        wrong_source = (
            h.Vdc.Params(dc=0.05)
            if directory.name.endswith("complete")
            else h.Vsin.Params(voff=0.0, vamp=0.5, freq=10_000.0)
        )
        value = adc_measurement([100, 101], observed_adc=1, logic_phase_delay_symbols=2)
        measurements[path] = dataclasses.replace(
            value, param=dataclasses.replace(value.param, tb=dataclasses.replace(value.param.tb, vin_diff=wrong_source))
        )
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    calls = []

    def noise_plot(values, analyses, *, output_path, rate_axis, series_labels=()):
        assert rate_axis == "sampling"
        assert len(analyses) == len(values)
        assert all(m.param.observed_adc == 1 for m in values)
        assert all(isinstance(m.param.tb.vin_diff, h.Vdc.Params) for m in values)
        if series_labels:
            assert set(series_labels) == {"LOGIC 6/8"}
        else:
            assert len({m.param.tb.seq_logic_pattern for m in values}) == 2
        assert len(values) == 2
        calls.append(output_path)
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_noise_sweep", noise_plot)
    monkeypatch.setattr(runner, "plot_adc_noise_distribution_sweep", noise_plot)

    def analyze_dynamic(value):
        assert isinstance(value.param.tb.vin_diff, h.Vsin.Params)
        return SimpleNamespace(sample_rate_hz=value.sample_rate_hz)

    monkeypatch.setattr(runner, "analyze_adc_dynamic", analyze_dynamic)
    spectra = []

    def dynamic_plot(values, analyses, *, output_path, x_axis):
        assert len(values) == len(analyses) == 2
        assert x_axis == "sample_rate"
        spectra.append(output_path)
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_dynamic_sweep", dynamic_plot)
    monkeypatch.setattr(runner, "plot_adc_dynamic", lambda *args, output_path: (output_path.with_suffix(".pdf"),))
    artifacts = runner.adc_sample_rate_study(tmp_path / "output")
    assert len(calls) == 6
    assert len(spectra) == 1
    assert len(artifacts) == 9


def test_power_study_selects_instrumented_dc_measurements(tmp_path, monkeypatch):
    measurements = {}
    for stamp in ("20260801_194930", "20260802_021624", "20260819_113714"):
        path = tmp_path / "build/scan_adc" / stamp / "0000_adc00.h5"
        path.parent.mkdir(parents=True)
        path.touch()
        value = adc_measurement(
            [100, 101],
            observed_adc=0,
            readbacks={
                f"{rail}_{kind}_average_power_w": power
                for rail in ("vdd_a", "vdd_d", "vdd_dac")
                for kind, power in (("active", 2e-6), ("static", 1e-6))
            },
        )
        measurements[path] = dataclasses.replace(
            value,
            param=dataclasses.replace(
                value.param, tb=dataclasses.replace(value.param.tb, vin_diff=h.Vdc.Params(dc=0.05))
            ),
        )
    for path, measurement in tuple(measurements.items()):
        for index, shift in enumerate((5, 8, 10), start=1):
            shifted_path = path.with_name(f"{index:04d}_adc00.h5")
            shifted_path.touch()
            rows = {
                name: getattr(measurement.param.tb, name)[shift:] + getattr(measurement.param.tb, name)[:shift]
                for name in ("seq_init_pattern", "seq_samp_pattern", "seq_comp_pattern", "seq_logic_pattern")
            }
            measurements[shifted_path] = dataclasses.replace(
                measurement,
                param=dataclasses.replace(measurement.param, tb=dataclasses.replace(measurement.param.tb, **rows)),
            )
        changed_path = path.with_name("0004_adc00.h5")
        changed_path.touch()
        logic = measurement.param.tb.seq_logic_pattern
        measurements[changed_path] = dataclasses.replace(
            measurement,
            param=dataclasses.replace(
                measurement.param,
                tb=dataclasses.replace(measurement.param.tb, seq_logic_pattern=logic[1:] + logic[:1]),
            ),
        )
    for directory in {path.parent for path in measurements}:
        path = directory / "9999_capture.h5"
        path.touch()
        measurements[path] = adc_measurement([100, 101], observed_adc=0)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    group_sizes = []

    def plot(values, analyses, *, output_path, rate_axis):
        assert rate_axis == "sampling"
        group_sizes.append(len(values))
        np.testing.assert_allclose([analysis.total_power_w for analysis in analyses], np.full(len(values), 6e-6))
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_power_sweep", plot)
    assert len(runner.adc_power_study(tmp_path / "output")) == 6
    assert group_sizes == [4, 1] * 3


def test_main_rejects_input_directory_override(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "adc_sequence_study", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        runner.main()
