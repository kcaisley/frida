"""Software-only tests for physical scan target composition and dispatch."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import hdl21 as h
import pytest

from flow.adc.sequences import SEQUENCES
from flow.scans import runner

timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)


def test_registered_targets_cover_every_accepted_physical_campaign() -> None:
    tree = ast.parse(Path(runner.__file__).read_text())
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not hasattr(runner, "TARGETS")
    assert functions == {
        "main",
        "adc_sample_rate_static",
        "adc_sequence_static",
        "adc_activity_noise",
        "adc_transfer_curve",
        "adc_ramp_code_density",
        "comp_common_mode",
        "comp_sampling_noise",
        "comp_sampling_noise_repair",
        "cdac_cap_mismatch",
        "cdac_cap_mismatch_diagnostic_repair",
        "cdac_cap_mismatch_calibration_boundary_repair",
    }


@pytest.mark.parametrize(
    ("target_name", "expected_count", "expected_adcs", "expected_conversions", "source_type"),
    (
        ("adc00_fixed_input_noise", 3, {0}, 100_000, h.Vdc.Params),
        ("adc00_all_adc_activity_noise", 3, {0}, 100_000, h.Vdc.Params),
        ("adc_transfer_curve", 1_001, {0}, 100, h.Vdc.Params),
        ("adc_ramp_code_density", 4, {0, 1, 2, 3}, 4_000_000, h.Vpwl.Params),
    ),
)
def test_adc_targets_reproduce_accepted_campaign_shapes(
    monkeypatch,
    target_name: str,
    expected_count: int,
    expected_adcs: set[int],
    expected_conversions: int,
    source_type: type,
) -> None:
    captured_calls = []
    captured_run_dirs = []
    captured_control_modes = []

    def scan(params, *, run_dir: Path, position: str) -> Path:
        captured_calls.append((params, position))
        captured_run_dirs.append(run_dir)
        captured_control_modes.append("controlled")
        return run_dir

    def scan_noctl(params, *, run_dir: Path, position: str) -> Path:
        captured_calls.append((params, position))
        captured_run_dirs.append(run_dir)
        captured_control_modes.append("manual")
        return run_dir

    monkeypatch.setattr(runner.scan_adc, "scan", scan)
    monkeypatch.setattr(runner.scan_adc_noctl, "scan", scan_noctl)
    # Keep the historical recipes as independent acceptance cases after consolidation.
    family = {
        "adc00_fixed_input_noise": "adc_activity_noise",
        "adc00_all_adc_activity_noise": "adc_activity_noise",
    }.get(target_name, target_name)
    result = getattr(runner, family)()
    variants = [params for params, position in captured_calls if position != "abort"]
    positions = [position for _params, position in captured_calls]

    assert result == captured_run_dirs[-1]
    assert result.parent == runner.BASE_PATH / "build/scan_adc"
    total = {"adc_activity_noise": 6}.get(family, expected_count)
    assert len(variants) == total
    assert result.name.endswith("_" + family)
    assert positions[0] == "first"
    assert positions[-1] == "last"
    assert positions[1:-1] == ["middle"] * (total - 2)
    if family == "adc_activity_noise":
        all_active = target_name == "adc00_all_adc_activity_noise"
        variants = [p for p in variants if (p.active_adc_mask == (1,) * 16) == all_active]
    assert len(variants) == expected_count
    expected_control_mode = "manual" if target_name.endswith("_noctl") else "controlled"
    assert set(captured_control_modes) == {expected_control_mode}
    assert {params.observed_adc for params in variants} == expected_adcs
    assert {params.tb.conversions for params in variants} == {expected_conversions}
    assert all(isinstance(params.tb.vin_diff, source_type) for params in variants)
    if target_name == "adc_ramp_code_density":
        assert {float(params.tb.symbol_rate) for params in variants} == {160.0e6}
    elif target_name in {
        "adc00_fixed_input_noise",
        "adc00_all_adc_activity_noise",
        "adc_fixed_input_noise_50mv_700mvcm",
        "adc_fixed_input_noise_0mv_600mvcm",
    }:
        assert {float(params.tb.symbol_rate) for params in variants} == {320.0e6, 960.0e6, 1.6e9}
    elif target_name == "adc_transfer_curve":
        assert {float(params.tb.symbol_rate) for params in variants} == {1.6e9}
    else:
        assert {float(params.tb.symbol_rate) for params in variants} == {rate * 40.0e6 for rate in range(2, 41)}
    if target_name in {"adc00_fixed_input_noise", "adc00_all_adc_activity_noise"}:
        assert {float(params.tb.vin_cm.dc) for params in variants} == {0.7}
        assert {float(params.tb.vin_diff.dc) for params in variants} == {0.05}
        assert {
            timing_sequences.index(next(row for row in timing_sequences if row.logic == params.tb.seq_logic_pattern))
            - 3
            for params in variants
        } == {2.0}
        if target_name == "adc00_all_adc_activity_noise":
            assert [params.active_adc_mask for params in variants] == [(1,) * 16] * 3
    elif target_name == "adc_ramp_code_density":
        assert {float(params.tb.vin_cm.dc) for params in variants} == {0.7}
        assert {params.campaign for params in variants} == {"adc_ramp"}
        assert {params.tb.vin_diff.wave for params in variants} == {"0 -1 0.1 1"}
    elif target_name == "adc_transfer_curve":
        assert {float(params.tb.vin_cm.dc) for params in variants} == {0.7}
        assert {params.campaign for params in variants} == {"adc_transfer"}
        assert {float(params.tb.vin_diff.dc) for params in variants} == {(step - 500) * 0.0015 for step in range(1_001)}
        assert {float(params.tb.symbol_rate) for params in variants} == {1.6e9}
        assert [params.observed_adc for params in variants] == [0] * 1_001


def test_adc_target_aborts_powered_hardware_after_interrupted_middle_point(monkeypatch) -> None:
    calls = []

    def scan(params, *, run_dir: Path, position: str) -> Path:
        calls.append((params, position))
        if position == "middle" and sum(call_position == "middle" for _params, call_position in calls) == 1:
            raise RuntimeError("interrupted")
        return run_dir

    monkeypatch.setattr(runner.scan_adc, "scan", scan)

    with pytest.raises(RuntimeError, match="interrupted"):
        runner.adc_ramp_code_density()

    assert [position for _params, position in calls] == ["first", "middle", "abort"]
    assert calls[-1][0] is calls[-2][0]


def test_adc_noctl_target_aborts_fpga_after_interrupted_middle_point(monkeypatch) -> None:
    calls = []

    def scan_noctl(params, *, run_dir: Path, position: str) -> Path:
        calls.append((params, position))
        if position == "middle" and sum(call_position == "middle" for _params, call_position in calls) == 1:
            raise RuntimeError("interrupted")
        return run_dir

    monkeypatch.setattr(runner.scan_adc_noctl, "scan", scan_noctl)

    with pytest.raises(RuntimeError, match="interrupted"):
        runner.adc_sequence_static()

    assert [position for _params, position in calls] == ["first", "middle", "abort"]
    assert calls[-1][0] is calls[-2][0]


def test_comparator_repair_target_owns_the_accepted_curve_selection(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def build(**kwargs):
        captured["builder"] = kwargs
        return [sentinel]

    def scan(variants, *, run_dir: Path, capture_scope_per_curve: bool) -> Path:
        captured["variants"] = variants
        captured["run_dir"] = run_dir
        captured["capture_scope_per_curve"] = capture_scope_per_curve
        return run_dir

    monkeypatch.setattr(runner.scan_comp, "build_sampling_noise_variants", build)
    monkeypatch.setattr(runner.scan_comp, "scan", scan)
    result = runner.comp_sampling_noise_repair()

    assert captured["builder"]["selected_curves"] == {
        (1, 100.0, "track"),
        (2, 75.0, "track"),
    }
    assert {key: value for key, value in captured["builder"].items() if key != "selected_curves"} == {
        "adc_indices": (0, 1, 2, 3),
        "coupling_percentages": (0.0, 25.0, 50.0, 75.0, 100.0),
        "vin_cm_v": 0.7,
        "minimum_v": 0.0,
        "maximum_v": 25.0e-3,
        "step_v": 100.0e-6,
        "conversions": 1_000,
    }
    assert captured["variants"] == [sentinel]
    assert captured["capture_scope_per_curve"] is False
    assert result.parent == runner.BASE_PATH / "build/scan_comp"


@pytest.mark.parametrize(
    ("target_name", "expected_curves"),
    (
        (
            "cdac_cap_mismatch_diagnostic_repair",
            {
                (2, "n", 0, "1to0", 0),
                (2, "n", 4, "1to0", 1),
                (3, "p", 9, "0to1", 0),
            },
        ),
        (
            "cdac_cap_mismatch_calibration_boundary_repair",
            {
                (0, "n", 6, "0to1", 1),
                (0, "p", 6, "1to0", 1),
                (1, "n", 5, "0to1", 1),
                (1, "n", 6, "0to1", 1),
                (1, "n", 7, "0to1", 1),
                (1, "n", 8, "0to1", 1),
                (1, "p", 6, "1to0", 1),
                (1, "p", 7, "1to0", 1),
                (1, "p", 8, "1to0", 1),
                (1, "p", 9, "1to0", 1),
                (2, "n", 4, "1to0", 1),
                (2, "n", 6, "0to1", 1),
                (2, "p", 6, "1to0", 1),
                (3, "n", 10, "0to1", 1),
                (3, "p", 10, "1to0", 1),
            },
        ),
    ),
)
def test_cdac_repair_targets_own_the_accepted_curve_selections(
    monkeypatch,
    target_name: str,
    expected_curves: set[tuple[int, str, int, str, int]],
) -> None:
    captured = {}

    def build(**kwargs):
        captured["builder"] = kwargs
        return [object()]

    def scan(variants, *, run_dir: Path, capture_scope_per_curve: bool) -> Path:
        captured["variants"] = variants
        captured["run_dir"] = run_dir
        captured["capture_scope_per_curve"] = capture_scope_per_curve
        return run_dir

    monkeypatch.setattr(runner.scan_cdac, "build_capacitor_variants", build)
    monkeypatch.setattr(runner.scan_cdac, "scan", scan)
    result = getattr(runner, target_name)()

    assert captured["builder"]["selected_curves"] == expected_curves
    assert captured["capture_scope_per_curve"] is False
    assert result.parent == runner.BASE_PATH / "build/scan_cdac"


def test_main_requires_and_dispatches_one_named_target(monkeypatch, tmp_path) -> None:
    observed = []

    def adc_sample_rate_static():
        observed.append("run")
        return tmp_path

    monkeypatch.setattr(runner, "adc_sample_rate_static", adc_sample_rate_static)
    monkeypatch.setattr(sys, "argv", ["runner"])
    with pytest.raises(SystemExit):
        runner.main()

    monkeypatch.setattr(sys, "argv", ["runner", "adc_sample_rate_static"])
    runner.main()
    assert observed == ["run"]


@pytest.mark.parametrize(
    "sequence_name",
    (
        "symbol256_init8_samp16_comp11110000_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11100001",
        "symbol160_init4_samp20_comp11111100_logic11000011",
    ),
)
def test_fixed_input_grid_noctl_covers_all_adcs_and_three_rates(monkeypatch, sequence_name):
    captured = []
    sequence = dict(SEQUENCES)[sequence_name]
    monkeypatch.setattr(runner.scan_adc_noctl, "scan", lambda params, **kwargs: captured.append((params, kwargs)))
    runner.adc_sequence_static(
        adc_indices=tuple(range(16)),
        nominal_conversion_rates_hz=(2e6, 6e6, 10e6),
        sequences=(sequence,),
    )
    assert len(captured) == 48
    assert [kw["position"] for _, kw in captured] == ["first"] + ["middle"] * 46 + ["last"]
    assert {(p.observed_adc, float(p.tb.symbol_rate) / 160) for p, _ in captured} == {
        (adc, rate) for adc in range(16) for rate in (2e6, 6e6, 10e6)
    }
    assert all(p.tb.conversions == 100_000 for p, _ in captured)
    assert all(float(p.tb.vin_diff.dc) == 0.050 and float(p.tb.vin_cm.dc) == 0.700 for p, _ in captured)
    assert all(p.tb.seq_logic_pattern == sequence.logic for p, _ in captured)


def test_sequence_static_default_covers_complete_catalogue(monkeypatch):
    captured = []
    monkeypatch.setattr(runner.scan_adc_noctl, "scan", lambda params, **kwargs: captured.append(params))
    runner.adc_sequence_static()
    assert len(captured) == 16 * len(SEQUENCES) * 3
    actual = {
        (
            p.observed_adc,
            p.tb.seq_init_pattern,
            p.tb.seq_samp_pattern,
            p.tb.seq_comp_pattern,
            p.tb.seq_logic_pattern,
            float(p.tb.symbol_rate),
        )
        for p in captured
    }
    expected = {
        (adc, seq.init, seq.samp, seq.comp, seq.logic, rate * 160)
        for adc in range(16)
        for _, seq in SEQUENCES
        for rate in (2e6, 6e6, 10e6)
    }
    assert actual == expected
    assert all(p.tb.conversions == 100_000 for p in captured)


def test_rate_static_requires_sequence_selection_before_hardware(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.scan_adc_noctl, "scan", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="TODO select"):
        runner.adc_sample_rate_static()
    assert not calls
