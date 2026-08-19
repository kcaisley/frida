"""Reusable oscilloscope acquisition and SCPI synchronization helpers."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

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
