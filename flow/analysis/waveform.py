"""Typed preparation of measurement and oscilloscope waveforms for plotting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import Any

import numpy as np

from flow.analysis.types import AnalysisWaveform, MeasAdcExt, MeasAdcInt, Measurement


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
    adc_index = getattr(msmt.param, "observed_adc", None)
    if adc_index is not None:
        lines += (f"ADC: {adc_index:02d}",)
    elif msmt.info.backend != "physical" and isinstance(msmt, (MeasAdcExt, MeasAdcInt)):
        lines += (f"Source: {msmt.info.backend.upper()}",)
    board_id = getattr(msmt.param, "board_id", None)
    if board_id is not None:
        lines += (f"Board: {board_id}",)
    for field_name, label in (("vin_cm", "Vcm"), ("vin_diff", "Vdiff")):
        source = getattr(msmt.param, field_name, None)
        dc_v = getattr(source, "dc", None)
        if dc_v is not None:
            lines += (f"{label}: {float(dc_v) * 1e3:g} mV",)
    active_rate_hz = msmt.info.readbacks.get("active_conversion_rate_hz")
    if not isinstance(active_rate_hz, (int, float)):
        patterns = (
            msmt.param.seq_init_pattern,
            msmt.param.seq_samp_pattern,
            msmt.param.seq_comp_pattern,
            msmt.param.seq_logic_pattern,
        )
        active_indices = tuple(
            index
            for index in range(len(msmt.param.seq_init_pattern))
            if any(pattern[index] == "1" for pattern in patterns)
        )
        if active_indices:
            active_rate_hz = float(msmt.param.symbol_rate) / (active_indices[-1] - active_indices[0] + 1)
    if isinstance(active_rate_hz, (int, float)):
        lines += (f"Rate: {float(active_rate_hz) / 1e6:g} Msps",)
    init_p = int("".join(str(int(bit)) for bit in msmt.param.dac_astate_p), 2)
    init_n = int("".join(str(int(bit)) for bit in msmt.param.dac_astate_n), 2)
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
) -> AnalysisWaveform:
    """Select one validated waveform record from a typed measurement."""

    if msmt.wave is None:
        raise ValueError("measurement does not contain a commissioned waveform")
    record_ids = getattr(msmt.wave, "conversion_index", None)
    if record_ids is None:
        record_ids = getattr(msmt.wave, "trial_index", None)
    if record_ids is None:
        raise ValueError("measurement waveform has no record index")
    if not 0 <= record_index < len(record_ids):
        raise IndexError("waveform record_index is outside the measurement")

    available_names = tuple(
        field.name
        for field in fields(msmt.wave)
        if field.name not in {"conversion_index", "trial_index", "time_s"}
        and getattr(msmt.wave, field.name) is not None
    )
    selected_names = available_names if signal_names is None else tuple(signal_names)
    missing = sorted(set(selected_names).difference(available_names))
    if missing:
        raise ValueError(f"measurement has no waveform signals {missing}")
    measurement_kind = type(msmt).__name__.removeprefix("Meas").removesuffix("Ext").removesuffix("Int")
    return AnalysisWaveform(
        title=f"{measurement_kind.upper()} waveforms",
        time_s=msmt.wave.time_s,
        signal_names=selected_names,
        signal_units=tuple(_signal_unit(name) for name in selected_names),
        signal_values=np.asarray(
            [getattr(msmt.wave, name)[record_index] for name in selected_names],
            dtype=np.float64,
        ),
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
