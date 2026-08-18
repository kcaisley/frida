"""Software-only tests for physical scan target composition and dispatch."""

from __future__ import annotations

import sys
from pathlib import Path

import hdl21 as h
import pytest

from flow.scans import runner


def test_registered_targets_cover_every_accepted_physical_campaign() -> None:
    assert set(runner.TARGETS) == {
        "adc_sine_conversion_rate",
        "adc_fixed_input_noise_50mv",
        "adc_fixed_input_noise_100mv",
        "adc00_fixed_input_timing",
        "adc01_fixed_input_timing",
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
        ("adc_sine_conversion_rate", 78, {0, 1}, 1_000_000, h.Vsin.Params),
        ("adc_fixed_input_noise_50mv", 78, {0, 1}, 100_000, h.Vdc.Params),
        ("adc_fixed_input_noise_100mv", 78, {0, 1}, 100_000, h.Vdc.Params),
        ("adc00_fixed_input_timing", 273, {0}, 1_000, h.Vdc.Params),
        ("adc01_fixed_input_timing", 273, {1}, 1_000, h.Vdc.Params),
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

    def scan(params, *, run_dir: Path, position: str) -> Path:
        captured_calls.append((params, position))
        captured_run_dirs.append(run_dir)
        return run_dir

    monkeypatch.setattr(runner.scan_adc, "scan", scan)
    result = runner.TARGETS[target_name]()
    variants = [params for params, position in captured_calls if position != "abort"]
    positions = [position for _params, position in captured_calls]

    assert result == captured_run_dirs[-1]
    assert result.parent == runner.BASE_PATH / "build/scan_adc"
    assert len(variants) == expected_count
    assert positions[0] == ("only" if expected_count == 1 else "first")
    assert positions[-1] == ("only" if expected_count == 1 else "last")
    assert positions[1:-1] == ["middle"] * max(0, expected_count - 2)
    assert {params.observed_adc for params in variants} == expected_adcs
    assert {params.conversions for params in variants} == {expected_conversions}
    assert all(isinstance(params.vin_diff, source_type) for params in variants)
    if target_name == "adc_ramp_code_density":
        assert {float(params.symbol_rate) for params in variants} == {160.0e6}
    elif target_name == "adc_transfer_curve":
        assert {float(params.symbol_rate) for params in variants} == {1.6e9}
    else:
        assert {float(params.symbol_rate) for params in variants} == {rate * 40.0e6 for rate in range(2, 41)}
    if target_name.startswith("adc0"):
        assert {float(params.vin_cm.dc) for params in variants} == {0.7}
        assert {float(params.vin_diff.dc) for params in variants} == {0.05}
        assert {
            float(params.seq_logic_phase_delay_symbols) - float(params.seq_comp_phase_delay_symbols)
            for params in variants
        } == set(range(-3, 4))
    elif target_name == "adc_ramp_code_density":
        assert {float(params.vin_cm.dc) for params in variants} == {0.7}
        assert {params.campaign for params in variants} == {"adc_ramp"}
        assert {params.vin_diff.wave for params in variants} == {"0 -1 0.1 1"}
    elif target_name == "adc_transfer_curve":
        assert {float(params.vin_cm.dc) for params in variants} == {0.7}
        assert {params.campaign for params in variants} == {"adc_transfer"}
        assert {float(params.vin_diff.dc) for params in variants} == {(step - 500) * 0.0015 for step in range(1_001)}
        assert {float(params.symbol_rate) for params in variants} == {1.6e9}
        assert [params.observed_adc for params in variants] == [0] * 1_001
    else:
        assert {float(params.vin_cm.dc) for params in variants} == {0.7}
        assert {
            float(params.seq_logic_phase_delay_symbols) - float(params.seq_comp_phase_delay_symbols)
            for params in variants
        } == {2.0}
        if target_name == "adc_sine_conversion_rate":
            assert {float(params.vin_diff.voff) for params in variants} == {0.0}
            assert {float(params.vin_diff.vamp) for params in variants} == {0.5}
            assert {float(params.vin_diff.freq) for params in variants} == {9_998.770151}
        elif target_name == "adc_fixed_input_noise_50mv":
            assert {float(params.vin_diff.dc) for params in variants} == {0.05}
        else:
            assert {float(params.vin_diff.dc) for params in variants} == {0.1}


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
    result = runner.TARGETS[target_name]()

    assert captured["builder"]["selected_curves"] == expected_curves
    assert captured["capture_scope_per_curve"] is False
    assert result.parent == runner.BASE_PATH / "build/scan_cdac"


def test_main_requires_and_dispatches_one_named_target(monkeypatch, tmp_path) -> None:
    observed = []
    monkeypatch.setattr(runner, "TARGETS", {"known_target": lambda: observed.append("run") or tmp_path})
    monkeypatch.setattr(sys, "argv", ["runner"])
    with pytest.raises(SystemExit):
        runner.main()

    monkeypatch.setattr(sys, "argv", ["runner", "known_target"])
    runner.main()
    assert observed == ["run"]
