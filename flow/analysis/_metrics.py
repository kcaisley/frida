"""Project-specific numerical measurements used by circuit analyses."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, NamedTuple

import numpy as np
from scipy.optimize import minimize_scalar

from flow.analysis import calc


def linear_fit(signal: Sequence[float] | np.ndarray, axis: Sequence[float] | np.ndarray) -> tuple[float, float]:
    """Return the least-squares slope and intercept of a sampled signal."""
    signal, axis = calc._waveform(signal, axis)
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
        return coefficients, fitted, residual, calc.average(residual * residual)

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


def median_period_frequency(
    signal: Sequence[float] | np.ndarray,
    axis: Sequence[float] | np.ndarray,
    *,
    threshold: float,
    minimum_separation: float,
    minimum_crossings: int = 3,
    edge: str = "rising",
) -> float:
    """Estimate frequency after rejecting crossings too close to the preceding one."""
    if not math.isfinite(minimum_separation) or minimum_separation < 0 or minimum_crossings < 2:
        raise ValueError("minimum_separation must be nonnegative and minimum_crossings at least two")
    crossings = calc.cross(signal, axis, threshold, edge=edge)
    retained: list[float] = []
    for crossing in crossings:
        if not retained or crossing - retained[-1] >= minimum_separation:
            retained.append(float(crossing))
    if len(retained) < minimum_crossings:
        return math.nan
    return 1.0 / float(np.median(np.diff(retained)))


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
    ideal_count = calc.average(active_counts)
    dnl_values = calc.dnl(active_counts, ideal_count=ideal_count)
    inl_values = calc.inl(dnl_values)
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
