"""Software-only tests for the explicit analysis-pipeline command line."""

from __future__ import annotations

import ast
import dataclasses
import json
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

    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    registry = next(node for node in main.body if isinstance(node, ast.AnnAssign))
    assert isinstance(registry.value, ast.DictComp)
    entries = registry.value.generators[0].iter
    assert isinstance(entries, ast.Tuple)
    targets = {ast.unparse(node) for node in entries.elts}
    assert not hasattr(runner, "TARGETS")
    assert private_functions == []
    assert {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)} == {*targets, "main"}
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
        if isinstance(node, ast.FunctionDef) and node.name != "main":
            assert [arg.arg for arg in node.args.args] == ["output_dir"]
            assert not node.args.kwonlyargs
            assert node.returns is not None
            assert ast.unparse(node.returns) == "tuple[Path, ...]"


def test_sequence_plots_stored_measurements_without_redecoding(tmp_path: Path, monkeypatch) -> None:
    campaigns = (
        ("frida-20260906_124441_733878", "frida1_fixed_input_noise", "20260906_125026", (1, 2), (17, 20)),
        ("frida-20260906_124442_994752", "frida2_fixed_input_noise", "20260906_124953", (1, 2, 3), (17,)),
    )
    for session, target, stamp, layers, radices in campaigns:
        campaign = tmp_path / "build/remote" / session
        campaign.mkdir(parents=True)
        for layer in layers:
            for radix in radices:
                for timing in ("original", "extended_comp", "continuous_100ns"):
                    path = (
                        campaign
                        / "results/sim/adc"
                        / target
                        / stamp
                        / f"{target[:6]}_{layer}layer_radix{radix}"
                        / timing
                        / "result.h5"
                    )
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b"unchanged measurement")
        # Unrelated results must not enter this explicitly pinned comparison.
        (campaign / "result.h5").write_bytes(b"unrelated")

    for index, (_, target, _, layers, radices) in enumerate(campaigns):
        campaign = tmp_path / "build/remote" / ("frida-20260910_185707_055364", "frida-20260910_185757_562573")[index]
        campaign.mkdir(parents=True)
        for layer in layers:
            for radix in radices:
                path = (
                    campaign
                    / "results/sim/adc"
                    / (target + "_comp7of8")
                    / ("20260910_185921", "20260910_190007")[index]
                    / f"{target[:6]}_{layer}layer_radix{radix}"
                    / "continuous_100ns_comp7of8"
                    / "result.h5"
                )
                path.parent.mkdir(parents=True)
                path.write_bytes(b"unchanged measurement")
    output_dir = tmp_path / "output"
    physical_path = tmp_path / "build/scan_adc/20260915_111149/0102_adc03.h5"
    physical_path.parent.mkdir(parents=True)
    physical_path.touch()
    (physical_path.parent / "scope_diagnostic.h5").touch()
    output_dir.mkdir()
    # Neither output files nor another acquisition directory can override inputs.
    (output_dir / "0000_unrelated.h5").touch()
    case_count = 28
    clock_count = 4
    selected_cases = []

    from flow.analysis.test_adc import adc_timing_measurement
    from flow.analysis.types import AnalysisWaveform

    physical = adc_measurement([100, 101, 100, 101], observed_adc=3)
    physical = dataclasses.replace(
        physical,
        param=dataclasses.replace(
            physical.param, tb=dataclasses.replace(physical.param.tb, vin_diff=h.Vdc.Params(dc=0.05))
        ),
    )

    shifted_path = physical_path.with_name("0103_adc03.h5")
    shifted_path.touch()
    shifted = dataclasses.replace(
        physical,
        param=dataclasses.replace(
            physical.param,
            tb=dataclasses.replace(
                physical.param.tb,
                **{
                    name: getattr(physical.param.tb, name)[5:] + getattr(physical.param.tb, name)[:5]
                    for name in ("seq_init_pattern", "seq_samp_pattern", "seq_comp_pattern", "seq_logic_pattern")
                },
            ),
        ),
    )

    def load(path):
        if path == physical_path:
            return physical
        if path == shifted_path:
            return shifted
        assert path.read_bytes() == b"unchanged measurement"
        selected_cases.append("/".join(path.parts[-3:]))
        return adc_timing_measurement()

    monkeypatch.setattr(runner, "read_measurement", load)
    monkeypatch.setattr(runner, "analyze_adc_decision_paths", lambda *args, **kwargs: object())
    monkeypatch.setattr(runner, "analyze_adc_cdac_settling", lambda *args: object())
    monkeypatch.setattr(
        runner,
        "analyze_measurement_waveforms",
        lambda *args, **kwargs: AnalysisWaveform(
            title="clocks",
            time_s=np.array([0.0, 1.0]),
            signal_values=np.zeros((4, 2)),
            signal_names=("INIT", "SAMP", "COMP", "LOGIC"),
            signal_units=("V",) * 4,
        ),
    )

    def plot(*args, output_path, **kwargs):
        if output_path.name.endswith("sequences1"):
            assert len(args[0]) == 2
            assert kwargs["series_labels"] == ["Sequence 1", "Sequence 1"]
            assert args[0][0].param.tb.seq_init_pattern != args[0][1].param.tb.seq_init_pattern
        return (output_path.with_suffix(".pdf"),)

    for name in (
        "plot_adc_decision_path_density",
        "plot_adc_cdac_settling",
        "plot_waveforms",
        "plot_adc_noise_sweep",
        "plot_adc_code_distribution",
    ):
        monkeypatch.setattr(runner, name, plot)

    def compile_deck(command, *, cwd, **kwargs):
        assert command[-1] == "frida_2_vs_1.tex"
        tex = (cwd / command[-1]).read_text()
        assert tex.count("\\begin{frame}") == tex.count("\\includegraphics") == 3 * case_count + clock_count + 7
        assert "FRIDA-1 1L R17 original" in tex
        assert "FRIDA-2 3L R17 continuous 100ns" in tex
        assert "FRIDA-2 3L R17 continuous 100ns comp7of8" in tex
        (cwd / "frida_2_vs_1.pdf").touch()

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", compile_deck)

    artifacts = runner.adc_sequence_study(output_dir)
    assert len(artifacts) == 5 * case_count + 2 * clock_count + 7 + 3 + 5
    assert not list(output_dir.glob("*.md"))
    tables = list(output_dir.glob("*_timing_closure.csv"))
    assert len(tables) == case_count
    assert all(len(path.read_text().splitlines()) == 18 for path in tables)
    assert "logic_setup_s" in tables[0].read_text().splitlines()[0]
    assert len(set(selected_cases)) == case_count
    records = json.loads((tmp_path / "output/sources.json").read_text())
    assert len(records) == case_count
    assert all(len(row["sha256"]) == 64 for row in records)
    assert sum(row["sequence_plot"] for row in records) == clock_count
    assert all("frida2_3layer_radix17/" in row["case"] for row in records if row["sequence_plot"])
    assert not list(output_dir.glob("*_captures.h5"))


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
            nominal_weights=nominal_weight,
            calibrated_weights=weight,
            measured_weight_mask=np.ones(17, dtype=np.bool_),
            training_sample_count=100,
            validation_sample_count=50,
            output_gain=1.0,
            output_offset_lsb=0.0,
        )

    ramp_dir = tmp_path / "build/scan_adc/20260812_011910"
    ramp_dir.mkdir(parents=True)
    ramp_path = ramp_dir / (
        "0000_00_adc00_160mbd_pwl10hz_m1000top1000mv_logicp0sym_vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
    )
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
    fake_cdac = SimpleNamespace(param=SimpleNamespace(board_id="00", observed_adc=0))
    cdac_measurements = (fake_cdac,)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasAdcExt", SimpleNamespace)
    monkeypatch.setattr(runner, "MeasCdacExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda path: fake_ramp if path == ramp_path else fake_cdac)
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
        "plot_adc_ramp_nonlinearity",
    ):
        monkeypatch.setattr(runner, name, lambda *_args, **_kwargs: ())

    artifacts = runner.adc_calibration_study(tmp_path)

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
                                    tb=SimpleNamespace(dac_diffcaps=diffcaps),
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
                    tb=SimpleNamespace(dac_diffcaps=0),
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
            measurement.param.tb.dac_diffcaps,
        )
        == ("p", 0, "1to0", 0)
    ]
    assert [cast(Any, measurement).point_index for measurement in replaced_curve] == [2, 3, 4]


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
                board_id="fixture_board",
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

    with pytest.raises(TypeError, match="expected MeasAdcExt"):
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
                param=SimpleNamespace(
                    observed_adc=adc_index,
                    tb=SimpleNamespace(vin_cm=h.Vdc.Params(dc=common_mode_v)),
                )
            )

    plotted = []
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasCompExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", measurements_by_path.__getitem__)
    monkeypatch.setattr(runner, "analyze_comp_offset_noise", lambda group: tuple(group))
    monkeypatch.setattr(runner, "classify_comp_common_mode_validity", lambda _groups, analyses: analyses)
    monkeypatch.setattr(
        runner,
        "plot_comp_common_mode_campaign",
        lambda groups, _analyses, *, output_path: plotted.append((groups, output_path)) or (output_path,),
    )

    runner.comp_system_common_mode_study(tmp_path / "output")

    assert [path.name for _groups, path in plotted] == [
        "adc02_comparator_common_mode",
        "adc05_comparator_common_mode",
    ]
    assert [float(group[0].param.tb.vin_cm.dc) for group in plotted[0][0]] == [0.7, 0.9]


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
    monkeypatch.setattr(runner, "MeasCompExt", SimpleNamespace)
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
    enum_value = SimpleNamespace(name="fixture")
    comp = SimpleNamespace(
        comp_stages=enum_value,
        preamp_diff_xtors=enum_value,
        preamp_bias=enum_value,
        latch_inner_on_xtors=enum_value,
        latch_outer_on_xtors=enum_value,
        latch_inner_init_xtors=enum_value,
        latch_outer_init_xtors=enum_value,
        diffpair_w=1,
        diffpair_l=1,
        tail_w=1,
        tail_l=1,
        rst_w=1,
        rst_l=1,
        latch_on_w=1,
        latch_on_l=1,
        latch_init_w=1,
        latch_init_l=1,
        srlatch_n_w=1,
        srlatch_p_w=1,
    )
    measurement = SimpleNamespace(
        info=SimpleNamespace(readbacks={"candidate_id": "fixture"}),
        param=SimpleNamespace(comp=comp),
    )
    analysis = SimpleNamespace(
        candidate_id=("fixture",),
        candidate_label=("Fixture",),
        size_profile=("half",),
        topology_index=np.asarray([0]),
        total_width_units=np.asarray([1.0]),
        total_active_area_units=np.asarray([1.0]),
        total_active_area_um2=np.asarray([1.0]),
        device_count=np.asarray([1]),
        validity=("valid",),
        offset_v=np.asarray([0.0]),
        noise_sigma_v=np.asarray([1e-3]),
        average_power_w=np.asarray([1e-6]),
        energy_per_decision_j=np.asarray([1e-15]),
        maximum_clock_to_decision_s=np.asarray([1e-9]),
        maximum_settling_s=np.asarray([2e-9]),
        unresolved_fraction=np.asarray([0.0]),
    )
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasCompInt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: measurement)
    monkeypatch.setattr(runner, "analyze_comp_candidate_sweep", lambda measurements: analysis)
    monkeypatch.setattr(runner, "plot_comp_candidate_sweep", lambda *_args, output_path: (output_path,))
    monkeypatch.setattr(runner, "plot_comp_noise_power_tradeoff", lambda *_args, output_path: (output_path,))

    artifacts = runner.comp_candidate_sweep_study(tmp_path / "output")

    assert [artifact.name for artifact in artifacts] == [
        "comp_candidate_noise_power_settling",
        "comp_candidate_noise_power_tradeoff",
        "comp_candidate_noise_power_settling.csv",
    ]
    assert "fixture" in artifacts[-1].read_text()


def test_cdac_runner_derives_board_and_adc_indices_from_h5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurement_runs = []
    measurements_by_path = {}
    for run_name in ("20260804_171234", "20260804_193030", "20260804_193631"):
        meas_read_dir = tmp_path / "build/scan_cdac" / run_name
        meas_read_dir.mkdir(parents=True)
        run_measurements = []
        for adc_index in (2, 7):
            path = meas_read_dir / f"adc{adc_index:02d}.h5"
            path.touch()
            measurement = SimpleNamespace(param=SimpleNamespace(observed_adc=adc_index, board_id="fixture"))
            measurements_by_path[path] = measurement
            run_measurements.append(measurement)
        measurement_runs.append(tuple(run_measurements))

    received = {}

    def analyze(runs, *, adc_indices, board_id, comparator_offset_v_by_adc):
        received.update(
            runs=tuple(runs),
            adc_indices=adc_indices,
            board_id=board_id,
            offsets=comparator_offset_v_by_adc,
        )
        groups = tuple(
            (measurements_by_path[next(path for path in measurements_by_path if f"adc{adc:02d}" in path.name)],)
            for adc in adc_indices
        )
        analyses = tuple(SimpleNamespace(adc_index=adc_index) for adc_index in adc_indices)
        return groups, analyses

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasCdacExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", measurements_by_path.__getitem__)
    monkeypatch.setattr(
        runner,
        "load_board_map",
        lambda: {"boards": {"fixture": {"comparator_calibration": {2: {"offset_v": 2e-3}, 7: {"offset_v": 7e-3}}}}},
    )
    monkeypatch.setattr(runner, "analyze_cdac_cap_mismatch_campaign", analyze)
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch", lambda *_args, output_path: (output_path,))
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch_comparison", lambda *_args, output_path: (output_path,))

    artifacts = runner.cdac_system_cap_mismatch_study(tmp_path / "output")

    assert received == {
        "runs": tuple(measurement_runs),
        "adc_indices": (2, 7),
        "board_id": "fixture",
        "offsets": {2: 2e-3, 7: 7e-3},
    }
    assert [path.name for path in artifacts] == [
        "adc02_cdac_cap_mismatch",
        "adc07_cdac_cap_mismatch",
        "adc00_adc03_cdac_cap_mismatch_comparison",
    ]


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


def test_ramp_study_needs_no_input_voltage_or_cdac_measurements(tmp_path, monkeypatch):
    directory = tmp_path / "build/scan_adc/20260812_011910"
    directory.mkdir(parents=True)
    measurements = {}
    for adc_index in range(4):
        path = directory / f"{adc_index:04d}_adc{adc_index:02d}.h5"
        path.touch()
        measurements[path] = adc_measurement(np.tile(np.arange(4096), 3), observed_adc=adc_index, vin_diff_v=0.0)
    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "read_measurement", measurements.__getitem__)
    monkeypatch.setattr(runner, "analyze_adc_ramp", lambda *args, **kwargs: pytest.fail("must not fit voltage"))
    plotted = []

    def plot(measurement, analysis, *, output_path):
        if hasattr(analysis, "method"):
            assert analysis.method == "code_density"
            assert analysis.transition_vin_diff_v is None
            plotted.append(measurement.param.observed_adc)
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

    def noise_plot(values, analysis, *, output_path, rate_axis, series_labels=()):
        assert rate_axis == "sampling"
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

    def analyze_dynamic(values):
        assert len(values) == 2
        assert all(isinstance(m.param.tb.vin_diff, h.Vsin.Params) for m in values)
        return SimpleNamespace(sample_rate_hz=np.array([0.5e6, 1e6]))

    monkeypatch.setattr(runner, "analyze_adc_dynamic_sweep", analyze_dynamic)
    spectra = []

    def dynamic_plot(values, analysis, *, output_path, x_axis):
        assert x_axis == "sample_rate"
        spectra.append(output_path)
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_dynamic_sweep", dynamic_plot)
    monkeypatch.setattr(runner, "analyze_adc_dynamic", lambda value: object())
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

    def plot(values, analysis, *, output_path, rate_axis):
        assert rate_axis == "sampling"
        group_sizes.append(len(values))
        np.testing.assert_allclose(analysis.total_power_w, np.full(len(values), 6e-6))
        return (output_path.with_suffix(".pdf"),)

    monkeypatch.setattr(runner, "plot_adc_power_sweep", plot)
    assert len(runner.adc_power_study(tmp_path / "output")) == 6
    assert group_sizes == [4, 1] * 3


def test_main_rejects_input_directory_override(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "adc_sequence_study", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        runner.main()
