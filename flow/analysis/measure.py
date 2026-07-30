"""Small hardware-free waveform and converter calculations.

Functions in this module operate directly on NumPy arrays and scalars. They
neither know about HDF5 nor create analysis-result objects.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy.signal.windows import blackmanharris


def find_crossings(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    threshold: float,
    *,
    rising: bool,
) -> np.ndarray:
    """Return linearly interpolated threshold-crossing coordinates."""

    signal = np.asarray(signal, dtype=np.float64)
    axis = np.asarray(axis, dtype=np.float64)
    if signal.ndim != 1 or axis.ndim != 1:
        raise ValueError("crossing input arrays must be one-dimensional")
    if len(signal) != len(axis):
        raise ValueError("crossing signal and axis must have equal lengths")
    if len(signal) < 2:
        return np.asarray([], dtype=np.float64)
    if not np.all(np.diff(axis) > 0):
        raise ValueError("crossing axis must increase strictly")

    if rising:
        indices = np.flatnonzero((signal[:-1] < threshold) & (signal[1:] >= threshold))
    else:
        indices = np.flatnonzero((signal[:-1] > threshold) & (signal[1:] <= threshold))
    if not len(indices):
        return np.asarray([], dtype=np.float64)

    left_signal = signal[indices]
    right_signal = signal[indices + 1]
    fractions = (threshold - left_signal) / (right_signal - left_signal)
    return axis[indices] + fractions * (axis[indices + 1] - axis[indices])


def amplitude_spectrum(
    signal: Sequence[float] | np.ndarray,
    sample_interval_s: float,
    *,
    window: str = "hann",
) -> tuple[np.ndarray, np.ndarray]:
    """Return a one-sided peak-amplitude spectrum including DC."""

    samples = np.asarray(signal, dtype=np.float64)
    if samples.ndim != 1:
        raise ValueError("spectrum signal must be one-dimensional")
    if len(samples) < 3:
        raise ValueError("spectrum signal must contain at least three samples")
    if not math.isfinite(sample_interval_s) or sample_interval_s <= 0:
        raise ValueError("sample interval must be positive and finite")

    if window == "hann":
        weights = np.hanning(len(samples))
    elif window == "blackman_harris":
        weights = blackmanharris(len(samples), sym=False)
    elif window == "none":
        weights = np.ones(len(samples))
    else:
        raise ValueError("FFT window must be 'hann', 'blackman_harris', or 'none'")

    coherent_gain = float(np.sum(weights))
    spectrum = np.abs(np.fft.rfft(samples * weights)) / coherent_gain
    if len(samples) % 2 == 0:
        spectrum[1:-1] *= 2.0
    else:
        spectrum[1:] *= 2.0
    return np.fft.rfftfreq(len(samples), d=sample_interval_s), spectrum


def sample_at_edges(
    axis: Sequence[float] | np.ndarray,
    clock: Sequence[float] | np.ndarray,
    signals: Sequence[Sequence[float] | np.ndarray],
    threshold: float,
    *,
    rising: bool = True,
    sample_fraction: float = 0.5,
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """Sample signals at a fixed fraction of each clock interval."""

    if not 0.0 <= sample_fraction <= 1.0:
        raise ValueError("sample_fraction must be in [0, 1]")
    axis_array = np.asarray(axis, dtype=np.float64)
    edges = find_crossings(clock, axis_array, threshold, rising=rising)
    if len(edges) < 2:
        empty = tuple(np.asarray([], dtype=np.float64) for _ in signals)
        return np.asarray([], dtype=np.float64), empty
    sample_axis = edges[:-1] + sample_fraction * np.diff(edges)
    sampled = tuple(np.interp(sample_axis, axis_array, np.asarray(signal, dtype=np.float64)) for signal in signals)
    return sample_axis, sampled


def measure_settling(
    axis: Sequence[float] | np.ndarray,
    signal: Sequence[float] | np.ndarray,
    *,
    target: float | None = None,
    relative_tolerance: float = 0.01,
) -> float:
    """Return the first coordinate after which a signal remains settled."""

    axis = np.asarray(axis, dtype=np.float64)
    signal = np.asarray(signal, dtype=np.float64)
    if axis.ndim != 1 or signal.ndim != 1 or len(axis) != len(signal):
        raise ValueError("settling axis and signal must be aligned one-dimensional arrays")
    if relative_tolerance <= 0 or not math.isfinite(relative_tolerance):
        raise ValueError("settling tolerance must be positive and finite")
    if len(signal) == 0:
        return math.nan
    target = float(signal[-1]) if target is None else float(target)
    limit = relative_tolerance if abs(target) < 1e-15 else abs(target) * relative_tolerance
    settled = np.abs(signal - target) < limit
    suffix_settled = np.logical_and.accumulate(settled[::-1])[::-1]
    indices = np.flatnonzero(suffix_settled)
    return float(axis[indices[0]]) if len(indices) else math.nan


def measure_delay(
    axis: Sequence[float] | np.ndarray,
    trigger: Sequence[float] | np.ndarray,
    response: Sequence[float] | np.ndarray,
    trigger_threshold: float,
    response_threshold: float,
    *,
    trigger_rising: bool = True,
    response_rising: bool = True,
) -> tuple[float, float, float]:
    """Return trigger time, first following response time, and delay."""

    trigger_edges = find_crossings(trigger, axis, trigger_threshold, rising=trigger_rising)
    response_edges = find_crossings(response, axis, response_threshold, rising=response_rising)
    if not len(trigger_edges):
        return math.nan, math.nan, math.nan
    trigger_time = float(trigger_edges[0])
    following = response_edges[response_edges > trigger_time]
    if not len(following):
        return trigger_time, math.nan, math.nan
    response_time = float(following[0])
    return trigger_time, response_time, response_time - trigger_time


def measure_average_power(
    current_a: Sequence[float] | np.ndarray,
    voltage_v: float | Sequence[float] | np.ndarray,
) -> float:
    """Return mean positive consumed power."""

    current = np.asarray(current_a, dtype=np.float64)
    if current.ndim != 1:
        raise ValueError("power current must be one-dimensional")
    if not len(current):
        return math.nan
    voltage = np.asarray(voltage_v, dtype=np.float64)
    if voltage.ndim == 0:
        return float(voltage.item()) * float(np.mean(np.abs(current)))
    if voltage.shape != current.shape:
        raise ValueError("power voltage and current waveforms must be aligned")
    return float(np.mean(np.abs(current * voltage)))


def measure_offset_crossing(
    input_difference: Sequence[float] | np.ndarray,
    output_difference: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
) -> float:
    """Return the input value at the first output zero crossing."""

    input_difference = np.asarray(input_difference, dtype=np.float64)
    output_difference = np.asarray(output_difference, dtype=np.float64)
    axis = np.asarray(axis, dtype=np.float64)
    if input_difference.shape != output_difference.shape or input_difference.shape != axis.shape:
        raise ValueError("offset input, output, and axis arrays must be aligned")
    crossings = np.concatenate(
        (
            find_crossings(output_difference, axis, 0.0, rising=True),
            find_crossings(output_difference, axis, 0.0, rising=False),
        )
    )
    if not len(crossings):
        return math.nan
    crossing = float(np.min(crossings))
    return float(np.interp(crossing, axis, input_difference))


def measure_charge_injection(v_before: float, v_after: float) -> float:
    """Return the sampled-node voltage step caused by a switching event."""

    return float(v_after - v_before)


def endpoint_linearity(
    codes: Sequence[float] | np.ndarray,
    outputs: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return DNL, INL, and endpoint LSB from a monotonic transfer."""

    codes = np.asarray(codes, dtype=np.float64)
    outputs = np.asarray(outputs, dtype=np.float64)
    if codes.ndim != 1 or outputs.ndim != 1 or len(codes) != len(outputs):
        raise ValueError("linearity code and output arrays must be aligned")
    if len(codes) < 2:
        return np.asarray([]), np.asarray([]), math.nan
    order = np.argsort(codes)
    outputs = outputs[order]
    lsb = float((outputs[-1] - outputs[0]) / (len(outputs) - 1))
    if abs(lsb) < 1e-15:
        return np.zeros(len(outputs) - 1), np.zeros(len(outputs)), 0.0
    dnl = np.diff(outputs) / lsb - 1.0
    ideal = outputs[0] + np.arange(len(outputs)) * lsb
    inl = (outputs - ideal) / lsb
    return dnl, inl, lsb


def statistics(values: Sequence[float] | np.ndarray) -> dict[str, float]:
    """Return common scalar statistics."""

    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("statistics values must be one-dimensional")
    if not len(values):
        return {
            "count": 0.0,
            "mean": math.nan,
            "std": math.nan,
            "minimum": math.nan,
            "maximum": math.nan,
            "sigma3_low": math.nan,
            "sigma3_high": math.nan,
        }
    mean = float(np.mean(values))
    std = float(np.std(values))
    return {
        "count": float(len(values)),
        "mean": mean,
        "std": std,
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "sigma3_low": mean - 3.0 * std,
        "sigma3_high": mean + 3.0 * std,
    }


def diff_to_single(pos: Sequence[float] | np.ndarray, neg: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convert positive and negative waveforms to one differential waveform."""

    pos = np.asarray(pos, dtype=np.float64)
    neg = np.asarray(neg, dtype=np.float64)
    if pos.shape != neg.shape:
        raise ValueError("positive and negative waveforms must have equal shapes")
    return pos - neg


def quantize_to_bits(
    values: Sequence[float] | np.ndarray,
    *,
    threshold: float = 0.5,
) -> np.ndarray:
    """Quantize an analog waveform to uint8 zero/one values."""

    values = np.asarray(values, dtype=np.float64)
    return np.asarray(values >= threshold, dtype=np.uint8)


def redundant_bits_to_code(
    bits: Sequence[int] | np.ndarray,
    weights: Sequence[float] | np.ndarray,
) -> float:
    """Recombine one redundant SAR decision vector with its code weights."""

    bits = np.asarray(bits, dtype=np.uint8)
    weights = np.asarray(weights, dtype=np.float64)
    if bits.ndim != 1 or weights.ndim != 1 or len(bits) != len(weights):
        raise ValueError("decision bits and weights must be aligned one-dimensional arrays")
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("decision bits must contain only zero or one")
    return float(bits @ weights)


def code_to_voltage(
    code: float | Sequence[float] | np.ndarray,
    *,
    v_min: float,
    v_max: float,
    adc_bits: int,
) -> np.ndarray:
    """Map unipolar ADC codes linearly onto a voltage range."""

    if adc_bits <= 0:
        raise ValueError("adc_bits must be positive")
    return v_min + np.asarray(code, dtype=np.float64) * (v_max - v_min) / ((1 << adc_bits) - 1)


def histogram_inl_dnl(
    counts: Sequence[int] | np.ndarray,
    *,
    first_code: int = 1,
    last_code: int | None = None,
) -> dict[str, Any]:
    """Calculate code-density DNL and endpoint-corrected INL."""

    counts = np.asarray(counts, dtype=np.int64)
    if counts.ndim != 1 or not len(counts):
        raise ValueError("histogram counts must be a non-empty one-dimensional array")
    last_code = len(counts) - 2 if last_code is None else last_code
    if not 0 <= first_code <= last_code < len(counts):
        raise ValueError(f"code range must fit within 0..{len(counts) - 1}")
    codes = np.arange(first_code, last_code + 1, dtype=np.int64)
    active_counts = counts[first_code : last_code + 1]
    ideal_count = float(np.mean(active_counts))
    dnl = active_counts / ideal_count - 1.0 if ideal_count else np.zeros_like(active_counts, dtype=float)
    raw_inl = np.concatenate(([0.0], np.cumsum(dnl[:-1], dtype=np.float64)))
    inl = raw_inl - np.linspace(raw_inl[0], raw_inl[-1], len(raw_inl)) if len(raw_inl) > 1 else raw_inl
    return {
        "codes": codes,
        "counts": active_counts,
        "ideal_count": ideal_count,
        "dnl": dnl,
        "inl": inl,
        "missing_codes": int(np.count_nonzero(active_counts == 0)),
    }


def find_code_transitions(
    inputs: Sequence[float] | np.ndarray,
    outputs: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate input coordinates at each half-code transition."""

    inputs = np.asarray(inputs, dtype=np.float64)
    outputs = np.asarray(outputs, dtype=np.float64)
    if inputs.ndim != 1 or outputs.ndim != 1 or len(inputs) != len(outputs):
        raise ValueError("transition inputs and outputs must be aligned")
    if len(inputs) < 2:
        return np.asarray([], dtype=np.int64), np.asarray([], dtype=np.float64)
    order = np.argsort(inputs)
    inputs = inputs[order]
    outputs = outputs[order]
    direction = 1.0 if outputs[-1] >= outputs[0] else -1.0
    increasing = direction * outputs
    if np.any(np.diff(increasing) < 0):
        raise ValueError("code transition extraction requires a monotonic transfer")
    first = math.ceil(increasing[0] - 0.5)
    last = math.floor(increasing[-1] - 0.5)
    codes = np.arange(first, last + 1, dtype=np.int64)
    transitions = np.interp(codes + 0.5, increasing, inputs)
    return np.asarray(direction * codes, dtype=np.int64), transitions


def compute_static_error(
    inputs: Sequence[float] | np.ndarray,
    outputs: Sequence[float] | np.ndarray,
) -> dict[str, Any]:
    """Calculate endpoint gain, offset, DNL, and INL from a static transfer."""

    codes, transitions = find_code_transitions(inputs, outputs)
    if len(transitions) < 2:
        raise ValueError("static error requires at least two code transitions")
    lsb_v = float((transitions[-1] - transitions[0]) / (len(transitions) - 1))
    ideal = transitions[0] + np.arange(len(transitions)) * lsb_v
    inl = (transitions - ideal) / lsb_v
    dnl = np.diff(transitions) / lsb_v - 1.0
    return {
        "codes": codes,
        "transitions_v": transitions,
        "lsb_v": lsb_v,
        "dnl": dnl,
        "inl": inl,
    }


def compute_enob_fft(
    codes: Sequence[float] | np.ndarray,
    *,
    sample_rate_hz: float,
    input_frequency_hz: float,
    adc_bits: int,
    maximum_harmonic_order: int = 5,
) -> dict[str, Any]:
    """Calculate windowed ADC SNR, SNDR, THD, SFDR, and ENOB."""

    codes = np.asarray(codes, dtype=np.float64)
    if codes.ndim != 1 or len(codes) < 8:
        raise ValueError("FFT ENOB requires at least eight one-dimensional samples")
    if not 0 < input_frequency_hz < sample_rate_hz / 2:
        raise ValueError("input frequency must lie between zero and Nyquist")
    window = blackmanharris(len(codes), sym=False)
    spectrum = np.fft.rfft((codes - np.mean(codes)) * window)
    power = np.abs(spectrum) ** 2
    power[0] = 0.0
    bin_width = sample_rate_hz / len(codes)

    def tone_bins(frequency_hz: float) -> set[int]:
        center = round(frequency_hz / bin_width)
        return set(range(max(1, center - 4), min(len(power), center + 5)))

    fundamental = tone_bins(input_frequency_hz)
    harmonics: set[int] = set()
    for order in range(2, maximum_harmonic_order + 1):
        wrapped = (order * input_frequency_hz) % sample_rate_hz
        harmonics.update(tone_bins(min(wrapped, sample_rate_hz - wrapped)) - fundamental)
    noise = set(range(1, len(power))) - fundamental - harmonics
    fundamental_power = float(np.sum(power[list(fundamental)]))
    harmonic_power = float(np.sum(power[list(harmonics)]))
    noise_power = float(np.sum(power[list(noise)]))
    sndr_db = 10.0 * math.log10(fundamental_power / (noise_power + harmonic_power))
    snr_db = 10.0 * math.log10(fundamental_power / noise_power)
    thd_db = 10.0 * math.log10(harmonic_power / fundamental_power) if harmonic_power else -math.inf
    frequency_hz = np.fft.rfftfreq(len(codes), 1.0 / sample_rate_hz)
    peak_codes = ((1 << adc_bits) - 1) / 2.0
    amplitude = 2.0 * np.abs(spectrum) / np.sum(window)
    amplitude_dbfs = 20.0 * np.log10(np.maximum(amplitude / peak_codes, np.finfo(float).tiny))
    return {
        "sndr_db": sndr_db,
        "snr_db": snr_db,
        "thd_db": thd_db,
        "enob_bits": (sndr_db - 1.76) / 6.02,
        "frequency_hz": frequency_hz,
        "amplitude_dbfs": amplitude_dbfs,
    }


def mc_statistics(values: Sequence[float] | np.ndarray) -> dict[str, float]:
    """Alias the shared statistical summary for Monte Carlo results."""

    return statistics(values)
