"""Software-only plotting unit tests; no hardware I/O is performed."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from flow.scans.plot import SubplotSpec, plot_frequency_domain_csv, plot_time_domain_csv


def write_signal_csv(path: Path, *, sample_count: int = 1_024, sample_interval_s: float = 1.0e-9) -> None:
    """Write deterministic voltage, current, and power waveforms for plotting."""
    times_s = np.arange(sample_count) * sample_interval_s
    voltage_v = 0.6 + 0.5 * np.sin(2.0 * np.pi * 20.0e6 * times_s)
    current_a = 1.0e-3 + 0.2e-3 * np.cos(2.0 * np.pi * 10.0e6 * times_s)
    power_w = voltage_v * current_a
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("time_s", "voltage_v", "current_a", "power_w"))
        writer.writerows(zip(times_s, voltage_v, current_a, power_w, strict=True))


def assert_plot_formats(paths: tuple[Path, ...]) -> None:
    """Check that PNG, PDF, and SVG exports were produced and are nonempty."""
    assert tuple(path.suffix for path in paths) == (".png", ".pdf", ".svg")
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 0


def test_time_domain_plot_supports_voltage_current_and_power(tmp_path: Path) -> None:
    csv_path = tmp_path / "signals.csv"
    write_signal_csv(csv_path)
    paths = plot_time_domain_csv(
        csv_path,
        {
            "voltage_v": SubplotSpec("Input voltage (V)", ("Voltage information",)),
            "current_a": SubplotSpec("Supply current (A)", ("Current information",)),
            "power_w": SubplotSpec("Input power (W)", ("Power information",)),
        },
        png_path=tmp_path / "time.png",
        title="Arbitrary time-domain quantities",
    )

    assert_plot_formats(paths)
    svg = paths[-1].read_text()
    for text in (
        "Input voltage (V)",
        "Supply current (A)",
        "Input power (W)",
        "Voltage information",
        "Current information",
        "Power information",
        "Time (µs)",
    ):
        assert text in svg
    assert "voltage_v" not in svg


def test_frequency_domain_plot_uses_caller_labels_and_metadata(tmp_path: Path) -> None:
    csv_path = tmp_path / "signals.csv"
    write_signal_csv(csv_path)
    paths = plot_frequency_domain_csv(
        csv_path,
        {
            "voltage_v": SubplotSpec("Voltage magnitude (dBV)", ("Voltage spectrum",)),
            "current_a": SubplotSpec("Current magnitude (dBA)", ("Current spectrum",)),
        },
        png_path=tmp_path / "frequency.png",
        title="Arbitrary frequency-domain quantities",
        max_frequency_hz=100.0e6,
    )

    assert_plot_formats(paths)
    svg = paths[-1].read_text()
    for text in (
        "Voltage magnitude (dBV)",
        "Current magnitude (dBA)",
        "Voltage spectrum",
        "Current spectrum",
        "Frequency (MHz)",
    ):
        assert text in svg
    assert "current_a" not in svg


def test_plot_validation_rejects_invalid_subplots_and_limits(tmp_path: Path) -> None:
    csv_path = tmp_path / "signals.csv"
    write_signal_csv(csv_path, sample_count=16)

    with pytest.raises(ValueError, match="one to four subplots"):
        plot_time_domain_csv(csv_path, {})
    with pytest.raises(ValueError, match="labels must not be empty"):
        plot_time_domain_csv(csv_path, {"voltage_v": SubplotSpec("")})
    with pytest.raises(ValueError, match="missing required columns: missing"):
        plot_time_domain_csv(csv_path, {"missing": SubplotSpec("Missing")})
    with pytest.raises(ValueError, match="max_frequency_hz must be positive"):
        plot_frequency_domain_csv(csv_path, {"voltage_v": SubplotSpec("Voltage")}, max_frequency_hz=0.0)
