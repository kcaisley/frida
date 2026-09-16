"""Typed preparation of measurement and oscilloscope waveforms for plotting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import Any

import numpy as np

from flow.adc.sequences import AdcSequence
from flow.analysis.measure import find_crossings
from flow.analysis.types import AdcIntWave, AnalysisWaveform, CompIntWave, MeasAdcExt, MeasAdcInt, Measurement
from flow.scans.params import AdcScanParams


def _signal_unit(name: str) -> str:
    if name.endswith("_v"):
        return "V"
    if name.endswith("_i"):
        return "A"
    return ""


def style_measurement_text(msmt: Measurement) -> tuple[str, ...]:
    """Format concise plot context persisted with one measurement."""

    # rcParams cannot derive display text from typed measurement metadata.
    lines: tuple[str, ...] = ()
    params = msmt.param.tb if isinstance(msmt.param, AdcScanParams) else msmt.param
    adc_index = getattr(msmt.param, "observed_adc", None)
    if adc_index is not None:
        lines += (f"ADC: {adc_index:02d}",)
    elif msmt.info.backend != "physical" and isinstance(msmt, (MeasAdcExt, MeasAdcInt)):
        lines += (f"Source: {msmt.info.backend.upper()}",)
    board_id = getattr(msmt.param, "board_id", None)
    if board_id is not None:
        lines += (f"Board: {board_id}",)
    for field_name, label in (("vin_cm", "Vcm"), ("vin_diff", "Vdiff")):
        source = getattr(params, field_name, None)
        dc_v = getattr(source, "dc", None)
        if dc_v is not None:
            lines += (f"{label}: {float(dc_v) * 1e3:g} mV",)
    sequence = AdcSequence.from_tb_params(params)
    if isinstance(msmt, (MeasAdcExt, MeasAdcInt)):
        conversion_rate_hz = float(params.symbol_rate) / sequence.conversion_symbols
        lines += (f"Conversion: {conversion_rate_hz / 1e6:g} MSPS",)
    repetition_interval_s = len(sequence.init) / float(params.symbol_rate)
    lines += (f"Repetition: {repetition_interval_s * 1e9:g} ns",)
    init_p = int("".join(str(int(bit)) for bit in params.dac_astate_p), 2)
    init_n = int("".join(str(int(bit)) for bit in params.dac_astate_n), 2)
    if init_p == init_n:
        lines += (f"CDAC init: h'{init_p:04X}",)
    else:
        lines += (f"CDAC init: P h'{init_p:04X}, N h'{init_n:04X}",)
    return lines


def analyze_measurement_waveforms(
    msmt: Measurement,
    *,
    record_index: int = 0,
    signal_names: Sequence[str] | None = None,
    reference_signal: str | None = None,
    threshold_v: float | None = None,
    window_s: tuple[float, float] | None = None,
) -> AnalysisWaveform:
    """Select measured waveforms; optional edge alignment uses that same saved record."""
    wave = msmt.wave
    if wave is None:
        raise ValueError("Measurement has no waveform records")
    if isinstance(wave, (AdcIntWave, CompIntWave)):
        available = {**wave.voltage, **{f"i({key})": value for key, value in wave.current.items()}}
        units = {**{key: "V" for key in wave.voltage}, **{f"i({key})": "A" for key in wave.current}}
    else:
        available = {
            field.name: getattr(wave, field.name)
            for field in fields(wave)
            if field.name not in {"conversion_index", "trial_index", "time_s"} and getattr(wave, field.name) is not None
        }
        units = {name: _signal_unit(name) for name in available}
    selected = tuple(available) if signal_names is None else tuple(signal_names)
    if missing := set(selected) - available.keys():
        raise ValueError(f"Measurement has no waveform signals {sorted(missing)}")
    traces = {name: values[record_index] for name, values in available.items()}
    time = wave.time_s
    origin = 0.0
    if reference_signal is not None:
        threshold = 0.6 if threshold_v is None else threshold_v
        edges = find_crossings(traces[reference_signal], time, threshold, rising=True, initial_high=True)
        if not len(edges):
            raise ValueError("Waveform record has no reference edge")
        origin = float(edges[0])
    if window_s is not None:
        start, stop = (origin + value for value in window_s)
        if not time[0] <= start < stop <= time[-1]:
            raise ValueError("Waveform record does not cover the requested window")
        time = np.r_[start, time[(time > start) & (time < stop)], stop]
    return AnalysisWaveform(
        title=f"{type(msmt).__name__.removeprefix('Meas').removesuffix('Int').removesuffix('Ext')} waveforms",
        time_s=time - origin,
        time_origin_s=origin,
        signal_names=selected,
        signal_units=tuple(units[name] for name in selected),
        signal_values=np.asarray([np.interp(time, wave.time_s, traces[name]) for name in selected]),
        setup_lines=style_measurement_text(msmt),
    )


def analyze_scope_waveforms(
    waveforms: Any,
    track_names: Mapping[int, str],
) -> AnalysisWaveform:
    """Normalize one aligned Basil oscilloscope acquisition."""

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
    return AnalysisWaveform(
        title="Oscilloscope waveforms",
        time_s=reference_scale.offset + np.arange(sample_count) * reference_scale.slope,
        signal_names=tuple(track_names[channel] for channel in channels),
        signal_units=("V",) * len(channels),
        signal_values=np.asarray([waveforms[channel].data for channel in channels], dtype=np.float64),
    )
