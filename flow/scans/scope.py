"""Reusable oscilloscope acquisition and SCPI synchronization helpers.

Basil captures ──scope_wave()──► Wave                      (plain captures: serdes, diffamp checks)
               └─scope_analysis() = scope_wave() + differential/common-mode traces + spectra + RMS ──► AnalysisScope
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from basil.HL.tektronix_oscilloscope import response_value

from flow.analysis import calc
from flow.analysis.types import AnalysisScope, Wave


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeConns:
    """Oscilloscope probe hookup: the lowercase signal name on each channel, or ``None``.

    The four channels are fixed; what is connected to them changes, so each
    scan declares one of these next to its Basil calls, for example
    ``ScopeConns(ch1="vin_diff", ch2="seq_comp", ch3="seq_logic", ch4="comp_out")``.
    """

    ch1: str | None = None
    ch2: str | None = None
    ch3: str | None = None
    ch4: str | None = None

    def __post_init__(self) -> None:
        names = [name for name in (self.ch1, self.ch2, self.ch3, self.ch4) if name is not None]
        if not names:
            raise ValueError("a scope hookup connects at least one channel")
        if len(set(names)) != len(names) or any(name != name.lower() for name in names):
            raise ValueError(f"scope signal names must be unique and lowercase: {names}")

    @property
    def channels(self) -> dict[str, int]:
        """Return ``{signal: channel}`` for every connected channel, in channel order."""

        return {
            name: channel
            for channel, name in enumerate((self.ch1, self.ch2, self.ch3, self.ch4), start=1)
            if name is not None
        }


def scope_wave(waveforms: Any, scope_conns: ScopeConns) -> Wave:
    """Normalize one aligned Basil oscilloscope acquisition into a one-record wave keyed by signal name."""

    channels = scope_conns.channels
    missing_channels = sorted(set(channels.values()).difference(waveforms))
    if missing_channels:
        raise ValueError(f"scope did not return waveforms for channels {missing_channels}")
    first = waveforms[next(iter(channels.values()))]
    sample_counts = {channel: len(waveforms[channel].data) for channel in channels.values()}
    if len(set(sample_counts.values())) != 1:
        raise ValueError(f"scope channels have different sample counts: {sample_counts}")
    if any(waveforms[channel].x_scale != first.x_scale for channel in channels.values()):
        raise ValueError("scope channels do not share one horizontal scale")
    return Wave(
        record_index=np.zeros(1, dtype=np.int64),
        time_s=first.x_scale.offset + np.arange(len(first.data)) * first.x_scale.slope,
        v={name: np.asarray(waveforms[channel].data, dtype=np.float64)[None, :] for name, channel in channels.items()},
    )


def scope_analysis(
    waveforms: Any,
    scope_conns: ScopeConns,
    *,
    name: str,
    bandwidth_hz: float,
    differential: Mapping[str, tuple[str, str]] | None = None,
    common_mode: Mapping[str, tuple[str, str]] | None = None,
) -> AnalysisScope:
    """Build one scope result: the aligned traces, derived traces, spectra, and statistics.

    ``differential`` maps a derived trace name to the ``(p, n)`` trace names
    whose difference ``p - n`` it holds, such as ``{"vin_diff": ("vin_p",
    "vin_n")}``; ``common_mode`` likewise holds their average ``(p + n) / 2``.
    """

    wave = scope_wave(waveforms, scope_conns)
    traces = dict(wave.v)
    for derived, (positive, negative) in (differential or {}).items():
        traces[derived] = traces[positive] - traces[negative]
    for derived, (positive, negative) in (common_mode or {}).items():
        traces[derived] = (traces[positive] + traces[negative]) / 2.0
    wave = Wave(record_index=wave.record_index, time_s=wave.time_s, v=traces)
    sample_rate_hz = 1.0 / float(wave.time_s[1] - wave.time_s[0])
    mean_v = {trace: calc.average(values[0]) for trace, values in traces.items()}
    spectra = {}
    frequency_hz = np.empty(0)
    for trace, values in traces.items():
        centered = values[0] - mean_v[trace]
        # Three half-overlapping Hann segments: some averaging, while keeping
        # the resolution (2 / record length) fine enough to separate mains lines.
        frequency_hz, density_v2_per_hz = calc.psd(
            centered, sample_rate=sample_rate_hz, window="hann", segment_length=len(centered) // 2
        )
        spectra[trace] = np.sqrt(np.maximum(density_v2_per_hz, 0.0))
    return AnalysisScope(
        group=None,
        index=None,
        dut=None,
        name=name,
        wave=wave,
        bandwidth_hz=bandwidth_hz,
        spectrum_frequency_hz=frequency_hz,
        spectrum_v_per_sqrt_hz=spectra,
        mean_v=mean_v,
        ac_rms_v={trace: calc.stddev(values[0]) for trace, values in traces.items()},
    )


def wait_for_scope_capture(
    scope: Any,
    acquisition_count_before: int,
    # Covers the millisecond-scale records used here plus SCPI polling; slow
    # sequencer runs pass a longer timeout.
    timeout_s: float = 2.0,
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


def wait_for_scope_armed(
    scope: Any,
    # Arming after ACQuire:STATE RUN normally takes milliseconds; 2 s allows for SCPI latency.
    timeout_s: float = 2.0,
) -> int:
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
