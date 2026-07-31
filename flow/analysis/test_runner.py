"""Software-only tests for the explicit analysis-pipeline command line."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from flow.analysis import runner
from flow.analysis.test_adc import adc_measurement


@pytest.mark.parametrize("internal", (False, True), ids=("external", "internal"))
def test_read_adc_accepts_only_typed_adc_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
) -> None:
    """Accept both ADC views while retaining a concrete runtime type check."""

    path = tmp_path / "adc.h5"
    path.touch()
    expected = adc_measurement([0], internal=internal)
    monkeypatch.setattr(runner, "read_measurement", lambda _path: expected)

    assert runner._read_adc(path) is expected

    monkeypatch.setattr(runner, "read_measurement", lambda _path: object())
    with pytest.raises(TypeError, match="expected MeasAdcExt or MeasAdcInt"):
        runner._read_adc(path)


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

    monkeypatch.setattr(runner, "ANALYSIS_OUTPUT_BASE", tmp_path)
    monkeypatch.setattr(runner, "TARGETS", {"example_target": example_target})
    monkeypatch.setattr(sys, "argv", ["flow.analysis.runner", "example_target"])

    runner.main()

    assert len(received_output_dirs) == 1
    output_dir = received_output_dirs[0]
    assert output_dir.parent == tmp_path
    assert re.fullmatch(r"\d{8}_\d{6}", output_dir.name)
    assert (output_dir / "example.png").read_bytes() == b"plot"
    output = capsys.readouterr().out
    assert f"Analysis output: {output_dir}" in output
    assert "Completed example_target: 1 artifacts in " in output


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

    monkeypatch.setattr(runner, "ANALYSIS_OUTPUT_BASE", tmp_path)
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
