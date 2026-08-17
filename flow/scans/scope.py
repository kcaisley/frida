"""Reusable oscilloscope acquisition and SCPI synchronization helpers."""

from __future__ import annotations

import csv
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from basil.HL.tektronix_oscilloscope import response_value

DEFAULT_CAPTURE_TIMEOUT_S = 2.0

# Fixed physical MSO54 hookup shared by every FRIDA bench test. INIT and SAMP
# are not connected to the scope in this configuration.
FRIDA_SCOPE_CHANNELS = {
    "adc_vdiff": 1,
    "seq_comp": 2,
    "seq_logic": 3,
    "comp_out": 4,
}


def plot_scope_waveforms(
    output_path: Path,
    waveforms: Any,
    track_names: Mapping[int, str],
    *,
    title: str,
    info_lines: Mapping[str, Sequence[str]] | None = None,
    formats: Sequence[str] = ("png", "pdf", "svg"),
) -> tuple[Path, ...]:
    """Plot one aligned scope acquisition without loading or analyzing it."""

    channels = tuple(track_names)
    if not channels:
        raise ValueError("at least one scope track is required")
    missing_channels = sorted(set(channels).difference(waveforms))
    if missing_channels:
        raise ValueError(f"scope did not return waveforms for channels {missing_channels}")
    reference_scale = waveforms[channels[0]].x_scale
    sample_counts = {channel: len(waveforms[channel].data) for channel in channels}
    if len(set(sample_counts.values())) != 1:
        raise ValueError(f"scope channels have different sample counts: {sample_counts}")
    if any(waveforms[channel].x_scale != reference_scale for channel in channels):
        raise ValueError("scope channels do not share one horizontal scale")

    sample_count = next(iter(sample_counts.values()))
    time_s = reference_scale.offset + np.arange(sample_count) * reference_scale.slope
    maximum_time_s = float(np.max(np.abs(time_s)))
    if maximum_time_s < 1e-9:
        time_scale, time_unit = 1e12, "ps"
    elif maximum_time_s < 1e-6:
        time_scale, time_unit = 1e9, "ns"
    elif maximum_time_s < 1e-3:
        time_scale, time_unit = 1e6, "µs"
    elif maximum_time_s < 1.0:
        time_scale, time_unit = 1e3, "ms"
    else:
        time_scale, time_unit = 1.0, "s"

    fig, axes = plt.subplots(
        len(channels),
        1,
        sharex=True,
        figsize=(9.0, max(2.8, 2.2 * len(channels))),
    )
    axes = np.atleast_1d(axes)
    for ax, channel in zip(axes, channels, strict=True):
        track = track_names[channel]
        ax.plot(time_s * time_scale, waveforms[channel].data, linewidth=1.0)
        ax.set_ylabel(f"{track} (V)")
        ax.grid(True, alpha=0.25, linewidth=0.6)
        ax.tick_params(direction="in", which="both", top=True, right=True)
        lines = tuple((info_lines or {}).get(track, ()))
        if lines:
            ax.text(
                0.98,
                0.98,
                "\n".join(lines),
                transform=ax.transAxes,
                horizontalalignment="right",
                verticalalignment="top",
                fontsize="small",
                bbox={
                    "boxstyle": "round,pad=0.35",
                    "facecolor": "white",
                    "alpha": 0.85,
                    "linewidth": 0.6,
                },
            )
    axes[-1].set_xlabel(f"Time ({time_unit})")
    fig.suptitle(title)

    output_path = Path(output_path)
    if output_path.suffix:
        formats = (output_path.suffix.lstrip("."),)
        output_path = output_path.with_suffix("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    saved = []
    for output_format in formats:
        path = output_path.with_suffix(f".{output_format}")
        fig.savefig(path, bbox_inches="tight")
        saved.append(path)
    plt.close(fig)
    return tuple(saved)


def write_scope_csv(
    csv_path: Path,
    waveforms: Any,
    track_names: dict[int, str],
) -> Path:
    """Persist one raw, aligned oscilloscope acquisition as CSV."""

    channels = tuple(track_names)
    if not channels:
        raise ValueError("at least one scope track is required")
    if len(set(track_names.values())) != len(track_names):
        raise ValueError(f"scope track names must be unique, got {tuple(track_names.values())}")

    missing_channels = sorted(set(channels).difference(waveforms))
    if missing_channels:
        raise ValueError(f"scope did not return waveforms for channels {missing_channels}")

    reference_x_scale = waveforms[channels[0]].x_scale
    if reference_x_scale.unit.lower() not in {"s", "sec", "seconds"}:
        raise ValueError(f"expected scope time axis in seconds, got {reference_x_scale.unit!r}")

    sample_counts: dict[int, int] = {}
    for channel in channels:
        waveform = waveforms[channel]
        if waveform.x_scale != reference_x_scale:
            raise ValueError(
                f"scope channel {channel} has horizontal scale {waveform.x_scale}, expected {reference_x_scale}"
            )
        if len(waveform.data) != len(waveform.raw_data):
            raise ValueError(
                f"scope channel {channel} has {len(waveform.data)} voltage samples "
                f"but {len(waveform.raw_data)} raw samples"
            )
        sample_counts[channel] = len(waveform.raw_data)

    if len(set(sample_counts.values())) != 1:
        raise ValueError(f"scope channels have different sample counts: {sample_counts}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "time_s",
                *(f"{track_names[channel]}_v" for channel in channels),
                *(f"{track_names[channel]}_raw" for channel in channels),
            ]
        )
        for index in range(next(iter(sample_counts.values()))):
            writer.writerow(
                [
                    reference_x_scale.offset + index * reference_x_scale.slope,
                    *(waveforms[channel].data[index] for channel in channels),
                    *(waveforms[channel].raw_data[index] for channel in channels),
                ]
            )

    print(f"Saved scope waveform CSV: {csv_path}")
    return csv_path


def wait_for_scope_capture(
    scope: Any,
    acquisition_count_before: int,
    timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S,
) -> None:
    """Wait for a new single-sequence acquisition to complete and stop."""
    deadline = time.monotonic() + timeout_s
    while True:
        acquisition_stopped = response_value(scope.get_acquire_state()) in {"0", "OFF", "STOP"}
        acquisition_count = int(response_value(scope.get_number_waveforms()))
        if acquisition_stopped and acquisition_count > acquisition_count_before:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scope did not complete a new triggered acquisition within {timeout_s:g} s "
                f"(before={acquisition_count_before}, now={acquisition_count})"
            )
        time.sleep(0.01)


def wait_for_scope_armed(scope: Any, timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S) -> int:
    """Wait for a fresh acquisition to reset and arm; return its count."""
    deadline = time.monotonic() + timeout_s
    while True:
        trigger_state = response_value(scope._intf.query("TRIGger:STATE?"))
        acquisition_state = response_value(scope.get_acquire_state())
        acquisition_count = int(response_value(scope.get_number_waveforms()))
        if trigger_state in {"ARMED", "READY"} and acquisition_state in {"1", "ON", "RUN"} and acquisition_count == 0:
            return acquisition_count
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scope did not arm a fresh acquisition within {timeout_s:g} s "
                f"(trigger_state={trigger_state}, acquisition_state={acquisition_state}, "
                f"acquisition_count={acquisition_count})"
            )
        time.sleep(0.01)
