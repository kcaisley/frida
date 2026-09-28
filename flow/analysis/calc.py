"""Calculator operations on NumPy waveforms and scalar values.

The independent axis is explicit because NumPy arrays contain only sample
values. Functions do not read simulator results or construct circuit-specific
analysis results.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, NamedTuple, overload

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import welch
from scipy.signal.windows import blackmanharris


def _waveform(
    signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(signal, dtype=np.float64)
    coordinates = np.asarray(axis, dtype=np.float64)
    if values.ndim != 1 or coordinates.ndim != 1 or len(values) != len(coordinates):
        raise ValueError("signal and axis must be aligned one-dimensional arrays")
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(coordinates)):
        raise ValueError("signal and axis must be finite")
    if len(coordinates) > 1 and not np.all(np.diff(coordinates) > 0):
        raise ValueError("axis must increase strictly")
    return values, coordinates


@overload
def value(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    at: float,
    *,
    method: str = "linear",
    extrapolate: bool = True,
) -> float: ...


@overload
def value(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    at: Sequence[float] | np.ndarray,
    *,
    method: str = "linear",
    extrapolate: bool = True,
) -> np.ndarray: ...


def value(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    at: float | Sequence[float] | np.ndarray,
    *,
    method: str = "linear",
    extrapolate: bool = True,
) -> float | np.ndarray:
    """Return waveform values at coordinates; ``roundDown`` holds the prior sample."""
    signal, axis = _waveform(signal, axis)
    points = np.asarray(at, dtype=np.float64)
    if not len(axis):
        raise ValueError("value requires a non-empty waveform")
    if not np.all(np.isfinite(points)):
        raise ValueError("interpolation coordinates must be finite")
    if not extrapolate and np.any((points < axis[0]) | (points > axis[-1])):
        raise ValueError("interpolation coordinates lie outside the waveform")
    if method == "linear":
        result = np.interp(points, axis, signal)
    elif method == "roundDown":
        result = signal[np.clip(np.searchsorted(axis, points, side="right") - 1, 0, len(axis) - 1)]
    else:
        raise ValueError("method must be 'linear' or 'roundDown'")
    return float(result) if points.ndim == 0 else np.asarray(result)


def clip(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    start: float,
    stop: float,
    *,
    interpolate: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return signal and axis inside a closed interval, including interpolated ends."""
    signal, axis = _waveform(signal, axis)
    if not len(axis) or not axis[0] <= start < stop <= axis[-1]:
        raise ValueError("clip interval must lie within the waveform")
    interior = (axis >= start) & (axis <= stop)
    if not interpolate:
        return signal[interior].copy(), axis[interior].copy()
    clipped_axis = np.r_[start, axis[(axis > start) & (axis < stop)], stop]
    return np.asarray(value(signal, axis, clipped_axis)), clipped_axis


def sample(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    start: float,
    stop: float,
    by: float,
    *,
    scale: str = "linear",
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a waveform at regular linear steps or points per decade."""
    if not math.isfinite(by) or by <= 0 or not math.isfinite(start) or not math.isfinite(stop) or stop < start:
        raise ValueError("sample interval and step must be finite and ordered")
    if scale == "linear":
        points = start + np.arange(math.floor((stop - start) / by) + 1) * by
    elif scale == "logarithmic":
        if start <= 0:
            raise ValueError("logarithmic sampling requires a positive start")
        points = 10.0 ** (np.log10(start) + np.arange(math.floor(math.log10(stop / start) * by) + 1) / by)
    else:
        raise ValueError("scale must be 'linear' or 'logarithmic'")
    return np.asarray(value(signal, axis, points, extrapolate=False)), points


def integ(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> float:
    """Integrate a sampled waveform with trapezoidal interpolation."""
    signal, axis = _waveform(signal, axis)
    return float(np.trapezoid(signal, axis))


def deriv(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> np.ndarray:
    """Return the slope over each interval between adjacent samples."""
    signal, axis = _waveform(signal, axis)
    return np.diff(signal) / np.diff(axis)


def average(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray | None = None) -> float:
    """Average discrete samples, or time-weight a continuous waveform with ``axis``."""
    if axis is None:
        return float(np.mean(np.asarray(signal, dtype=np.float64)))
    signal, axis = _waveform(signal, axis)
    if len(axis) < 2:
        return math.nan
    return integ(signal, axis) / float(axis[-1] - axis[0])


def rms(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray | None = None) -> float:
    """Return root mean square amplitude."""
    squared = np.square(np.asarray(signal, dtype=np.float64))
    return math.sqrt(average(squared, axis))


def stddev(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray | None = None,
    *,
    sample: bool = False,
) -> float:
    """Return discrete standard deviation, or time-weighted waveform deviation."""
    if axis is None:
        return float(np.std(np.asarray(signal, dtype=np.float64), ddof=int(sample)))
    if sample:
        raise ValueError("sample standard deviation requires discrete observations without an axis")
    signal, axis = _waveform(signal, axis)
    return rms(signal - average(signal, axis), axis)


def peakToPeak(signal: Sequence[float] | np.ndarray) -> float:
    """Return maximum minus minimum waveform value."""
    return float(np.ptp(np.asarray(signal, dtype=np.float64)))


def ymax(signal: Sequence[float] | np.ndarray) -> float:
    """Return the largest signal value."""
    return float(np.max(np.asarray(signal, dtype=np.float64)))


def ymin(signal: Sequence[float] | np.ndarray) -> float:
    """Return the smallest signal value."""
    return float(np.min(np.asarray(signal, dtype=np.float64)))


def xmax(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> float:
    """Return the axis coordinate at the first signal maximum."""
    signal, axis = _waveform(signal, axis)
    if not len(signal):
        raise ValueError("xmax requires a non-empty waveform")
    return float(axis[np.argmax(signal)])


def xmin(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> float:
    """Return the axis coordinate at the first signal minimum."""
    signal, axis = _waveform(signal, axis)
    if not len(signal):
        raise ValueError("xmin requires a non-empty waveform")
    return float(axis[np.argmin(signal)])


def histogram2D(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    *,
    bins: tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Count samples in a two-dimensional grid of bin edges."""
    return np.histogram2d(x, y, bins=bins)


def histogram(
    signal: Sequence[float] | np.ndarray,
    *,
    bins: int | Sequence[float] | np.ndarray,
    value_range: tuple[float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Count samples in one-dimensional bins."""
    return np.histogram(signal, bins=bins, range=value_range)


def median(signal: Sequence[float] | np.ndarray) -> float:
    """Return the median of a one-dimensional set of samples."""
    return float(np.median(np.asarray(signal, dtype=np.float64)))


@overload
def percentile(signal: Sequence[float] | np.ndarray, percent: float) -> float: ...


@overload
def percentile(signal: Sequence[float] | np.ndarray, percent: Sequence[float] | np.ndarray) -> np.ndarray: ...


def percentile(
    signal: Sequence[float] | np.ndarray, percent: float | Sequence[float] | np.ndarray
) -> float | np.ndarray:
    """Return interpolated percentiles of a one-dimensional set of samples."""
    result = np.percentile(np.asarray(signal, dtype=np.float64), percent)
    return float(result) if np.ndim(percent) == 0 else np.asarray(result)


def linear_fit(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> tuple[float, float]:
    """Return the least-squares slope and intercept of a sampled signal."""
    signal, axis = _waveform(signal, axis)
    if len(signal) < 2:
        raise ValueError("linear fit requires at least two samples")
    slope, intercept = np.linalg.lstsq(np.column_stack((axis, np.ones(len(axis)))), signal, rcond=None)[0]
    return float(slope), float(intercept)


class SineFit(NamedTuple):
    """Least-squares sinusoid parameters and aligned waveform samples."""

    frequency_hz: float
    amplitude: float
    phase_rad: float
    offset: float
    residual_rms: float
    time_s: np.ndarray
    fitted: np.ndarray
    residual: np.ndarray


def sine_fit(
    signal: Sequence[float] | np.ndarray,
    *,
    sample_rate: float,
    frequency: float,
    frequency_search_fraction: float = 0.0,
) -> SineFit:
    """Fit a sine, cosine, and offset at a known or nearby frequency."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1 or len(signal) < 8 or not np.all(np.isfinite(signal)):
        raise ValueError("sine fit requires at least eight finite one-dimensional samples")
    if not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be finite and positive")
    if not math.isfinite(frequency) or not 0 < frequency < sample_rate / 2:
        raise ValueError("frequency must be finite and between zero and Nyquist")
    if not math.isfinite(frequency_search_fraction) or not 0 <= frequency_search_fraction < 1:
        raise ValueError("frequency_search_fraction must be finite and in [0, 1)")
    time_s = np.arange(signal.size, dtype=np.float64) / sample_rate
    ones = np.ones(signal.size, dtype=np.float64)

    def fit_at_frequency(frequency_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        phase = 2.0 * np.pi * frequency_hz * time_s
        design = np.column_stack((np.sin(phase), np.cos(phase), ones))
        coefficients = np.linalg.lstsq(design, signal, rcond=None)[0]
        fitted = design @ coefficients
        residual = signal - fitted
        return coefficients, fitted, residual, average(residual * residual)

    if frequency_search_fraction:
        maximum_offset_hz = min(frequency * frequency_search_fraction, 0.45 * sample_rate / signal.size)
        lower_hz = max(np.nextafter(0.0, 1.0), frequency - maximum_offset_hz)
        upper_hz = min(np.nextafter(sample_rate / 2.0, 0.0), frequency + maximum_offset_hz)
        result = minimize_scalar(
            lambda frequency_hz: fit_at_frequency(float(frequency_hz))[3],
            bounds=(lower_hz, upper_hz),
            method="bounded",
            options={"xatol": max(1e-9, frequency * 1e-10)},
        )
        if not result.success:
            raise RuntimeError(f"sine frequency fit failed: {result.message}")
        frequency = float(result.x)

    coefficients, fitted, residual, residual_power = fit_at_frequency(frequency)
    sine_coefficient, cosine_coefficient, offset = (float(value) for value in coefficients)
    return SineFit(
        frequency_hz=frequency,
        amplitude=math.hypot(sine_coefficient, cosine_coefficient),
        phase_rad=math.atan2(cosine_coefficient, sine_coefficient),
        offset=offset,
        residual_rms=math.sqrt(residual_power),
        time_s=time_s,
        fitted=fitted,
        residual=residual,
    )


def rmsNoise(density: Sequence[float] | np.ndarray, frequency: Sequence[float] | np.ndarray) -> float:
    """Integrate amplitude noise density over frequency and return RMS noise."""
    return math.sqrt(integ(np.square(np.asarray(density, dtype=np.float64)), frequency))


def psd(
    signal: Sequence[float] | np.ndarray,
    *,
    sample_rate: float,
    window: str = "hann",
    segment_length: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return one-sided Welch power spectral density and its frequency axis."""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("psd requires a non-empty finite one-dimensional signal")
    if not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be finite and positive")
    if segment_length is not None and segment_length < 1:
        raise ValueError("segment_length must be positive")
    length = min(len(values), segment_length or len(values))
    return welch(
        values,
        fs=sample_rate,
        window=window,
        nperseg=length,
        noverlap=length // 2,
        detrend=False,
        return_onesided=True,
        scaling="density",
    )


def dft(signal: Sequence[float] | np.ndarray, sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
    """Return one-sided complex amplitudes and their frequency axis."""
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("dft requires a non-empty finite one-dimensional signal")
    if not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be finite and positive")
    amplitudes = np.fft.rfft(values) / len(values)
    if len(values) % 2 == 0:
        amplitudes[1:-1] *= 2.0
    else:
        amplitudes[1:] *= 2.0
    return np.fft.rfftfreq(len(values), d=1.0 / sample_rate), amplitudes


def thd(fundamental_power: float, harmonic_power: float) -> float:
    """Return harmonic distortion relative to fundamental power, in dB."""
    if fundamental_power < 0 or harmonic_power < 0:
        raise ValueError("spectral powers must be non-negative")
    if fundamental_power == 0:
        return math.inf if harmonic_power > 0 else -math.inf
    return 10.0 * math.log10(harmonic_power / fundamental_power) if harmonic_power > 0 else -math.inf


def frequency(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    *,
    threshold: float | None = None,
    edge: str = "rising",
) -> float:
    """Return average cycle frequency from the first and last threshold crossing."""
    signal, axis = _waveform(signal, axis)
    if threshold is None:
        threshold = (float(np.min(signal)) + float(np.max(signal))) / 2.0
    crossings = cross(signal, axis, threshold, edge=edge)
    if len(crossings) < 2:
        return math.nan
    return float((len(crossings) - 1) / (crossings[-1] - crossings[0]))


def dnl(counts: Sequence[int] | np.ndarray, *, ideal_count: float | None = None) -> np.ndarray:
    """Return code-density differential nonlinearity in LSB."""
    counts = np.asarray(counts, dtype=np.float64)
    if counts.ndim != 1 or not len(counts) or np.any(counts < 0) or not np.all(np.isfinite(counts)):
        raise ValueError("counts must be a non-empty finite non-negative one-dimensional array")
    ideal = average(counts) if ideal_count is None else float(ideal_count)
    return counts / ideal - 1.0 if ideal > 0 else np.zeros_like(counts)


def inl(dnl_values: Sequence[float] | np.ndarray, *, endpoint_correct: bool = True) -> np.ndarray:
    """Integrate DNL, optionally correcting the line through both endpoints.

    Without endpoint correction, each output is the cumulative DNL through
    that code. With correction, each output is the INL at the code's start.
    """
    values = np.asarray(dnl_values, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("dnl_values must be one-dimensional")
    if not len(values):
        return values.copy()
    if not endpoint_correct:
        return np.cumsum(values, dtype=np.float64)
    raw = np.r_[0.0, np.cumsum(values[:-1], dtype=np.float64)]
    return raw - np.linspace(raw[0], raw[-1], len(raw)) if len(raw) > 1 else raw


@overload
def cross(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    threshold: float,
    *,
    edge: str = "rising",
    initial_high: bool = False,
    occurrence: None = None,
) -> np.ndarray: ...


@overload
def cross(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    threshold: float,
    *,
    edge: str = "rising",
    initial_high: bool = False,
    occurrence: int,
) -> float: ...


def cross(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    threshold: float,
    *,
    edge: str = "rising",
    initial_high: bool = False,
    occurrence: int | None = None,
) -> np.ndarray | float:
    """Return crossing coordinates, including first contact at an interior threshold sample.

    A contact at the final sample is excluded because its direction is not
    observable. ``occurrence`` is one-based, with negative indices from the end.
    """

    signal, axis = _waveform(signal, axis)
    if edge not in {"rising", "falling", "either"}:
        raise ValueError("edge must be 'rising', 'falling', or 'either'")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if occurrence == 0:
        raise ValueError("occurrence is one-based and cannot be zero")
    if len(signal) < 2:
        return np.asarray([], dtype=np.float64) if occurrence is None else math.nan
    direct_rises = np.flatnonzero((signal[:-1] < threshold) & (signal[1:] > threshold))
    direct_falls = np.flatnonzero((signal[:-1] > threshold) & (signal[1:] < threshold))
    # A threshold sample inside the record is an event at first contact,
    # including a touch that subsequently reverses. The final sample alone
    # does not establish an event.
    touch_rises = np.flatnonzero((signal[:-2] < threshold) & (signal[1:-1] == threshold)) + 1
    touch_falls = np.flatnonzero((signal[:-2] > threshold) & (signal[1:-1] == threshold)) + 1
    initial = (
        axis[:1]
        if initial_high
        and (
            (signal[0] > threshold)
            if edge == "rising"
            else (signal[0] < threshold)
            if edge == "falling"
            else signal[0] != threshold
        )
        else axis[:0]
    )
    rising_coordinates = np.r_[
        axis[direct_rises]
        + (threshold - signal[direct_rises])
        / (signal[direct_rises + 1] - signal[direct_rises])
        * (axis[direct_rises + 1] - axis[direct_rises]),
        axis[touch_rises],
    ]
    falling_coordinates = np.r_[
        axis[direct_falls]
        + (threshold - signal[direct_falls])
        / (signal[direct_falls + 1] - signal[direct_falls])
        * (axis[direct_falls + 1] - axis[direct_falls]),
        axis[touch_falls],
    ]
    selected_coordinates = (
        rising_coordinates
        if edge == "rising"
        else falling_coordinates
        if edge == "falling"
        else np.r_[rising_coordinates, falling_coordinates]
    )
    crossings = np.r_[initial, np.sort(selected_coordinates)]
    if occurrence is None:
        return crossings
    selected = occurrence - 1 if occurrence > 0 else occurrence
    return float(crossings[selected]) if -len(crossings) <= selected < len(crossings) else math.nan


def settlingTime(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    *,
    initial: float | None = None,
    final: float | None = None,
    percent_of_step: float = 5.0,
    absolute_tolerance: float | None = None,
) -> float:
    """Return the first coordinate after which a signal remains within tolerance.

    The default tolerance is a percentage of the initial-to-final step.
    ``absolute_tolerance`` supports fixed-band checks, including zero steps.
    """

    signal, axis = _waveform(signal, axis)
    if len(signal) == 0:
        return math.nan
    initial = float(signal[0]) if initial is None else float(initial)
    final = float(signal[-1]) if final is None else float(final)
    if not math.isfinite(initial) or not math.isfinite(final):
        raise ValueError("initial and final values must be finite")
    if absolute_tolerance is None:
        if not math.isfinite(percent_of_step) or percent_of_step <= 0:
            raise ValueError("percent_of_step must be positive and finite")
        limit = abs(final - initial) * percent_of_step / 100.0
    else:
        limit = float(absolute_tolerance)
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("absolute_tolerance must be positive and finite")
    settled = np.abs(signal - final) <= limit
    suffix_settled = np.logical_and.accumulate(settled[::-1])[::-1]
    indices = np.flatnonzero(suffix_settled)
    if not len(indices):
        return math.nan
    first = int(indices[0])
    if first == 0:
        return float(axis[0])
    boundary = final + limit if signal[first - 1] > final else final - limit
    fraction = (boundary - signal[first - 1]) / (signal[first] - signal[first - 1])
    return float(axis[first - 1] + fraction * (axis[first] - axis[first - 1]))


def stable_since(axis: Sequence[float] | np.ndarray, valid: Sequence[bool] | np.ndarray) -> float:
    """Return the first sample of the last uninterrupted valid interval."""
    coordinates = np.asarray(axis, dtype=np.float64)
    mask = np.asarray(valid, dtype=np.bool_)
    if coordinates.ndim != 1 or mask.ndim != 1 or len(coordinates) != len(mask):
        raise ValueError("validity mask and axis must be aligned one-dimensional arrays")
    if len(coordinates) < 2 or not mask[-1]:
        return math.nan
    invalid = np.flatnonzero(~mask)
    return float(coordinates[invalid[-1] + 1] if len(invalid) else coordinates[0])


def delay(
    trigger: Sequence[float] | np.ndarray,
    response: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    trigger_threshold: float,
    response_threshold: float,
    *,
    trigger_edge: str = "rising",
    response_edge: str = "rising",
    occurrence: int = 1,
) -> tuple[float, float, float]:
    """Return trigger time, first following response time, and delay."""

    trigger_edges = cross(trigger, axis, trigger_threshold, edge=trigger_edge)
    response_edges = cross(response, axis, response_threshold, edge=response_edge)
    if not len(trigger_edges):
        return math.nan, math.nan, math.nan
    if occurrence == 0:
        raise ValueError("occurrence is one-based and cannot be zero")
    index = occurrence - 1 if occurrence > 0 else occurrence
    if not -len(trigger_edges) <= index < len(trigger_edges):
        return math.nan, math.nan, math.nan
    trigger_time = float(trigger_edges[index])
    following = response_edges[response_edges > trigger_time]
    if not len(following):
        return trigger_time, math.nan, math.nan
    response_time = float(following[0])
    return trigger_time, response_time, response_time - trigger_time


def code_density(
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
    ideal_count = average(active_counts)
    dnl_values = dnl(active_counts, ideal_count=ideal_count)
    inl_values = inl(dnl_values)
    return {
        "codes": codes,
        "counts": active_counts,
        "ideal_count": ideal_count,
        "dnl": dnl_values,
        "inl": inl_values,
        "missing_codes": int(np.count_nonzero(active_counts == 0)),
    }


def code_transitions(
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


def spectrumMeas(
    signal: Sequence[float] | np.ndarray,
    *,
    sample_rate: float,
    fundamental_frequency: float,
    offset: float,
    full_scale_peak: float,
    maximum_harmonic_order: int,
) -> tuple[float, float, float, float, float, np.ndarray, np.ndarray]:
    """Calculate windowed SNR, SNDR, THD, SFDR, ENOB, and spectrum."""

    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1 or len(signal) < 8 or not np.all(np.isfinite(signal)):
        raise ValueError("spectrum measurement requires at least eight finite samples")
    if not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be finite and positive")
    if not math.isfinite(fundamental_frequency) or not 0 < fundamental_frequency < sample_rate / 2:
        raise ValueError("fundamental_frequency must lie between zero and Nyquist")
    if not math.isfinite(offset) or not math.isfinite(full_scale_peak) or full_scale_peak <= 0:
        raise ValueError("offset and positive full_scale_peak must be finite")
    if maximum_harmonic_order < 2:
        raise ValueError("maximum_harmonic_order must be at least two")
    window = blackmanharris(signal.size, sym=False)
    frequency_hz, spectrum = dft((signal - offset) * window, sample_rate)
    amplitude = np.abs(spectrum) * signal.size / float(np.sum(window))
    amplitude_dbfs = 20.0 * np.log10(
        np.maximum(
            amplitude / full_scale_peak,
            np.finfo(np.float64).tiny,
        )
    )

    spectral_power = np.abs(spectrum) ** 2 * signal.size**2
    if signal.size % 2 == 0:
        spectral_power[1:-1] *= 0.5
    else:
        spectral_power[1:] *= 0.5
    spectral_power[0] = 0.0
    bin_width_hz = sample_rate / signal.size

    def tone_bins(tone_frequency_hz: float) -> set[int]:
        center_bin = round(tone_frequency_hz / bin_width_hz)
        return set(
            range(
                max(1, center_bin - 4),
                min(len(spectral_power), center_bin + 5),
            )
        )

    fundamental_bins = tone_bins(fundamental_frequency)
    harmonic_bins: set[int] = set()
    for harmonic_order in range(2, maximum_harmonic_order + 1):
        wrapped_hz = (harmonic_order * fundamental_frequency) % sample_rate
        aliased_hz = min(wrapped_hz, sample_rate - wrapped_hz)
        harmonic_bins.update(tone_bins(aliased_hz) - fundamental_bins)

    noise_bins = set(range(1, len(spectral_power))) - fundamental_bins - harmonic_bins
    fundamental_power = float(np.sum(spectral_power[list(fundamental_bins)]))
    harmonic_power = float(np.sum(spectral_power[list(harmonic_bins)]))
    noise_power = float(np.sum(spectral_power[list(noise_bins)]))
    noise_and_distortion = harmonic_power + noise_power
    if fundamental_power <= 0:
        sndr_db = -math.inf
        snr_db = -math.inf
        thd_db = thd(fundamental_power, harmonic_power)
    else:
        sndr_db = 10.0 * math.log10(fundamental_power / noise_and_distortion) if noise_and_distortion > 0 else math.inf
        snr_db = 10.0 * math.log10(fundamental_power / noise_power) if noise_power > 0 else math.inf
        thd_db = thd(fundamental_power, harmonic_power)

    spur_candidates = np.asarray(
        sorted(set(range(1, len(spectral_power))) - fundamental_bins),
        dtype=np.int64,
    )
    if fundamental_power > 0 and spur_candidates.size:
        spur_center = int(spur_candidates[np.argmax(spectral_power[spur_candidates])])
        spur_bins = tone_bins(frequency_hz[spur_center]) - fundamental_bins
        spur_power = float(np.sum(spectral_power[list(spur_bins)]))
        sfdr_db = 10.0 * math.log10(fundamental_power / spur_power) if spur_power > 0 else math.inf
    else:
        sfdr_db = math.inf
    return (
        sndr_db,
        snr_db,
        thd_db,
        sfdr_db,
        (sndr_db - 1.76) / 6.02,
        frequency_hz,
        amplitude_dbfs,
    )
