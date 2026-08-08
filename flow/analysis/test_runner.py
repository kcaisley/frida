"""Software-only tests for the explicit analysis-pipeline command line."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import pytest

import flow.analysis as analysis_api
from flow.analysis import runner
from flow.analysis.test_adc import adc_measurement


def test_root_api_exposes_domain_analyses_not_campaign_combiners() -> None:
    """Keep the package root focused on reusable measurement analyses."""

    assert hasattr(analysis_api, "analyze_adc_code_distribution")
    assert hasattr(analysis_api, "analyze_adc_nonlinearity")
    assert hasattr(analysis_api, "analyze_cdac_cap_mismatch")
    assert not hasattr(analysis_api, "combine_adc_noise_comparison")
    assert not hasattr(analysis_api, "classify_comp_common_mode_validity")


def test_runner_keeps_input_selection_and_validation_in_public_runners() -> None:
    """Keep accepted-input configuration, selection, and type policy in public runners."""

    tree = ast.parse(Path(runner.__file__).read_text())
    private_functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_")
    ]

    assert private_functions == []
    assert not any(target_name.startswith("adc00_adc01_") for target_name in runner.TARGETS)
    assert "adc_transfer_curve" in runner.TARGETS
    assert "adc00_pex_transfer" not in runner.TARGETS
    assert "adc_code_distributions" in runner.TARGETS
    assert "adc_code_diag" not in runner.TARGETS
    assert "cdac_system_cap_mismatch" in runner.TARGETS
    assert "cdac_cap_mismatch" not in runner.TARGETS
    assert all(len(name) <= 26 for name in runner.TARGETS)


def test_cdac_runner_replaces_whole_curves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never concatenate analog points from two acquisition sessions."""

    original_dir = tmp_path / "build/scan_cdac/20260804_171234"
    replacement_dir = tmp_path / "build/scan_cdac/20260804_193030"
    unused_dir = tmp_path / "build/scan_cdac/20260804_193631"
    original_dir.mkdir(parents=True)
    replacement_dir.mkdir(parents=True)
    unused_dir.mkdir(parents=True)
    measurements_by_path = {}
    path_index = 0
    for adc_index in range(4):
        for side in ("p", "n"):
            for element in range(16):
                for direction in ("1to0", "0to1"):
                    for diffcaps in (0, 1):
                        path = original_dir / f"{path_index:04d}.h5"
                        path.touch()
                        path_index += 1
                        measurements_by_path[path] = SimpleNamespace(
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
    for point_index in (2, 3, 4):
        path = replacement_dir / f"{point_index}.h5"
        path.touch()
        measurements_by_path[path] = SimpleNamespace(
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

    analyzed_measurements = {}

    def analyze(measurements, *, comparator_offset_v):
        assert comparator_offset_v == 8e-3
        analyzed_measurements[measurements[0].param.observed_adc] = measurements
        return SimpleNamespace()

    monkeypatch.setattr(runner, "BASE_PATH", tmp_path)
    monkeypatch.setattr(runner, "MeasCdacExt", SimpleNamespace)
    monkeypatch.setattr(runner, "read_measurement", lambda path: measurements_by_path[path])
    monkeypatch.setattr(
        runner,
        "load_board_map",
        lambda: {
            "boards": {
                "test_board": {"comparator_calibration": {adc_index: {"offset_v": 8e-3} for adc_index in range(4)}}
            }
        },
    )
    monkeypatch.setattr(runner, "analyze_cdac_cap_mismatch", analyze)
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(runner, "plot_cdac_cap_mismatch_comparison", lambda *_args, **_kwargs: ())

    assert runner.cdac_system_cap_mismatch(tmp_path / "output") == ()
    replaced_curve = [
        measurement
        for measurement in analyzed_measurements[0]
        if (
            measurement.param.cdac_side,
            measurement.param.cdac_element,
            measurement.param.cdac_direction,
            measurement.param.dac_diffcaps,
        )
        == ("p", 0, "1to0", 0)
    ]
    assert [measurement.point_index for measurement in replaced_curve] == [2, 3, 4]


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
