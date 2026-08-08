"""Small hardware-free waveform and converter calculations.

Functions in this module operate directly on NumPy arrays and scalars. They
neither know about HDF5 nor create analysis-result objects.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


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
