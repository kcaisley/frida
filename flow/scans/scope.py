"""Reusable oscilloscope acquisition and SCPI synchronization helpers."""

from __future__ import annotations

import csv
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from basil.HL.tektronix_oscilloscope import response_value
from yaml import safe_load

from flow.analysis.types import AdcExtWave

DEFAULT_CAPTURE_TIMEOUT_S = 2.0

SCOPE_MAP_PATH = Path(__file__).with_name("map_scope.yaml")


def scope_channels(*required: str, optional: tuple[str, ...] = ()) -> dict[str, int]:
    """Read the actual probe hookup, requiring signals before any hardware I/O."""
    connections = safe_load(SCOPE_MAP_PATH.read_text())["connections"]
    known = {"seq_init", "seq_samp", "seq_comp", "seq_logic", "comp_out", "vin_diff"}
    if not isinstance(connections, dict) or set(connections) - known:
        raise ValueError(f"invalid scope signal names in {SCOPE_MAP_PATH}")
    if any(type(channel) is not int or channel not in range(1, 5) for channel in connections.values()):
        raise ValueError(f"scope channels must be integers 1..4 in {SCOPE_MAP_PATH}")
    if len(set(connections.values())) != len(connections):
        raise ValueError(f"scope channels must be unique in {SCOPE_MAP_PATH}")
    if set(required + optional) - known:
        raise ValueError("unknown requested scope signal")
    missing = set(required) - connections.keys()
    if missing:
        raise ValueError(f"scope signals not connected in {SCOPE_MAP_PATH}: {', '.join(sorted(missing))}")
    selected = set(required + optional) if required or optional else set(connections)
    return {name: channel for name, channel in connections.items() if name in selected}


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


def crop_adc_scope_conversion(
    wave: AdcExtWave,
    *,
    skip_conversions: int,
    conversion_period_s: float,
    symbol_period_s: float,
) -> AdcExtWave:
    """Select a complete ADC conversion after sequencer startup, with COMP as reference.

    A long startup-triggered scope record contains the startup conversion and the
    first retained conversion. Keep one symbol before its first COMP edge, so
    the normal scope decoder sees exactly that conversion's B0--B16. The caller
    has already associated the record with the retained DAQ conversion index.
    """
    from dataclasses import replace

    import numpy as np

    from flow.analysis.measure import find_crossings

    if len(wave.conversion_index) != 1 or skip_conversions < 0:
        raise ValueError("scope cropping requires one record and a nonnegative skip count")
    comp = wave.seq_comp_v[0]
    low, high = np.percentile(comp, (1, 99))
    if high - low < 0.1:
        raise ValueError("scope COMP waveform has no valid logic swing")
    edges = find_crossings(comp, wave.time_s, (low + high) / 2, rising=True)
    if len(edges) < 17 * (skip_conversions + 1):
        raise ValueError("scope record lacks the complete retained ADC conversion after startup")
    origin = edges[17 * skip_conversions] - symbol_period_s
    stop = origin + conversion_period_s
    if origin < wave.time_s[0] or stop > wave.time_s[-1]:
        raise ValueError("scope record does not cover the retained ADC conversion window")
    selected = (wave.time_s >= origin) & (wave.time_s < stop)
    return replace(
        wave,
        time_s=wave.time_s[selected] - origin,
        vin_diff_v=wave.vin_diff_v[:, selected] if wave.vin_diff_v is not None else None,
        seq_init_v=wave.seq_init_v[:, selected] if wave.seq_init_v is not None else None,
        seq_comp_v=wave.seq_comp_v[:, selected],
        seq_logic_v=wave.seq_logic_v[:, selected],
        comp_out_v=wave.comp_out_v[:, selected],
    )


def scope_records_to_adc_wave(
    records: Sequence[Mapping[int, Any]],
    conversion_index: Sequence[int],
    channels: Mapping[str, int],
) -> AdcExtWave:
    """Convert aligned triggered scope records into an external ADC wave section."""

    required = {"seq_comp_v", "seq_logic_v", "comp_out_v"}
    if not required <= set(channels) or set(channels) - required - {"vin_diff_v", "seq_init_v"}:
        raise ValueError(f"scope channels must include {sorted(required)}, with optional vin_diff_v and seq_init_v")
    if len(set(channels.values())) != len(channels):
        raise ValueError("scope channels must be unique")
    if len(records) != len(conversion_index):
        raise ValueError("scope record count must match waveform conversion indices")

    time_s = None
    signals = {name: [] for name in channels}
    for record_number, record in enumerate(records):
        missing_channels = sorted(set(channels.values()).difference(record))
        if missing_channels:
            raise ValueError(f"scope record {record_number} is missing channels {missing_channels}")
        reference = record[next(iter(channels.values()))]
        record_time = reference.x_scale.offset + np.arange(len(reference.data)) * reference.x_scale.slope
        if time_s is None:
            time_s = record_time
        elif not np.array_equal(record_time, time_s):
            raise ValueError(f"scope record {record_number} has a different time axis")
        for name, channel in channels.items():
            values = np.asarray(record[channel].data, dtype=np.float64)
            if len(values) != len(record_time):
                raise ValueError(f"scope record {record_number} channel {channel} is not aligned")
            signals[name].append(values)
    if time_s is None:
        raise ValueError("at least one scope record is required")
    return AdcExtWave(
        conversion_index=np.asarray(conversion_index),
        time_s=time_s,
        **{name: np.stack(values) for name, values in signals.items()},
    )
