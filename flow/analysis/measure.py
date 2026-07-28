"""Backend-neutral waveform measurements.

Public entry points consume :class:`AnalysisRequest` and return
:class:`AnalysisResult`.  The private NumPy kernels intentionally retain
ordinary array arguments so the numerical implementation stays direct and
easy to test.
"""

from __future__ import annotations

import math

import numpy as np

from flow.analysis.models import (
    AnalysisKind,
    AnalysisRequest,
    AnalysisResult,
    DataColumn,
    DataTable,
    Metric,
    StatisticsSettings,
    WaveformSettings,
)


def _find_crossings(
    signal: np.ndarray,
    axis: np.ndarray,
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


def _amplitude_spectrum(
    signal: np.ndarray,
    sample_interval_s: float,
    *,
    window: str,
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
    elif window == "none":
        weights = np.ones(len(samples))
    else:
        raise ValueError("FFT window must be 'hann' or 'none'")

    coherent_gain = float(np.sum(weights))
    spectrum = np.abs(np.fft.rfft(samples * weights)) / coherent_gain
    if len(samples) % 2 == 0:
        spectrum[1:-1] *= 2.0
    else:
        spectrum[1:] *= 2.0
    return np.fft.rfftfreq(len(samples), d=sample_interval_s), spectrum


def _sample_at_edges(
    axis: np.ndarray,
    clock: np.ndarray,
    signals: tuple[np.ndarray, ...],
    threshold: float,
    *,
    rising: bool,
    sample_fraction: float,
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """Sample signals at a fixed fraction of each clock interval."""

    if not 0.0 <= sample_fraction <= 1.0:
        raise ValueError("sample_fraction must be in [0, 1]")
    edges = _find_crossings(clock, axis, threshold, rising=rising)
    if len(edges) < 2:
        return np.asarray([], dtype=float), tuple(np.asarray([], dtype=float) for _ in signals)
    sample_axis = edges[:-1] + sample_fraction * np.diff(edges)
    return sample_axis, tuple(np.interp(sample_axis, axis, signal) for signal in signals)


def _settling_time(
    axis: np.ndarray,
    signal: np.ndarray,
    *,
    target: float | None,
    tolerance: float,
) -> float:
    """Return the first coordinate after which a signal remains settled."""

    if tolerance <= 0 or not math.isfinite(tolerance):
        raise ValueError("settling tolerance must be positive and finite")
    if len(signal) == 0:
        return math.nan
    target = float(signal[-1]) if target is None else float(target)
    limit = tolerance if abs(target) < 1e-15 else abs(target) * tolerance
    settled = np.abs(np.asarray(signal) - target) < limit
    for index in range(len(settled)):
        if np.all(settled[index:]):
            return float(axis[index])
    return math.nan


def _delay(
    axis: np.ndarray,
    trigger: np.ndarray,
    response: np.ndarray,
    trigger_threshold: float,
    response_threshold: float,
    *,
    rising: bool,
) -> tuple[float, float, float]:
    """Return trigger time, first following response time, and delay."""

    trigger_edges = _find_crossings(trigger, axis, trigger_threshold, rising=rising)
    response_edges = _find_crossings(response, axis, response_threshold, rising=rising)
    if not len(trigger_edges):
        return math.nan, math.nan, math.nan
    trigger_time = float(trigger_edges[0])
    following = response_edges[response_edges > trigger_time]
    if not len(following):
        return trigger_time, math.nan, math.nan
    response_time = float(following[0])
    return trigger_time, response_time, response_time - trigger_time


def _average_power(current: np.ndarray, voltage: float | np.ndarray) -> float:
    """Return mean positive consumed power."""

    current = np.asarray(current, dtype=np.float64)
    if not len(current):
        return math.nan
    if np.ndim(voltage):
        voltage_array = np.asarray(voltage, dtype=np.float64)
        if len(voltage_array) != len(current):
            raise ValueError("power voltage and current waveforms must be aligned")
        return float(np.mean(np.abs(current * voltage_array)))
    return float(voltage) * float(np.mean(np.abs(current)))


def _offset_crossing(
    input_difference: np.ndarray,
    output_difference: np.ndarray,
    axis: np.ndarray,
) -> float:
    """Return the input value at the first output zero crossing."""

    if len(input_difference) != len(output_difference):
        raise ValueError("offset input and output arrays must be aligned")
    crossings = np.concatenate(
        (
            _find_crossings(output_difference, axis, 0.0, rising=True),
            _find_crossings(output_difference, axis, 0.0, rising=False),
        )
    )
    if not len(crossings):
        return math.nan
    crossing = float(np.min(crossings))
    return float(np.interp(crossing, axis, input_difference))


def _endpoint_linearity(codes: np.ndarray, outputs: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Return DNL, INL, and endpoint LSB from a monotonic transfer."""

    codes = np.asarray(codes, dtype=np.float64)
    outputs = np.asarray(outputs, dtype=np.float64)
    if len(codes) != len(outputs):
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


def _statistics(values: np.ndarray) -> tuple[Metric, ...]:
    """Return common scalar statistics."""

    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return (
            Metric("count", 0),
            Metric("mean", math.nan),
            Metric("std", math.nan),
            Metric("minimum", math.nan),
            Metric("maximum", math.nan),
            Metric("sigma3_low", math.nan),
            Metric("sigma3_high", math.nan),
        )
    mean = float(np.mean(values))
    std = float(np.std(values))
    return (
        Metric("count", len(values)),
        Metric("mean", mean),
        Metric("std", std),
        Metric("minimum", float(np.min(values))),
        Metric("maximum", float(np.max(values))),
        Metric("sigma3_low", mean - 3.0 * std),
        Metric("sigma3_high", mean + 3.0 * std),
    )


def _run(request: AnalysisRequest):
    if len(request.spec.input_ids) != 1:
        raise ValueError(f"{request.spec.kind.value} measurement requires exactly one input run")
    input_id = request.spec.input_ids[0]
    for run in request.runs:
        if run.run_id == input_id:
            return run
    raise KeyError(f"measurement request has no run {input_id!r}")


def _column(run, name: str) -> tuple[np.ndarray, str]:
    matches = [
        (table.column(name), table.unit(name))
        for table in run.tables
        if name in table.column_names
    ]
    if not matches:
        raise KeyError(f"run {run.run_id!r} has no column {name!r}")
    if len(matches) > 1:
        raise KeyError(f"run {run.run_id!r} contains ambiguous column {name!r}")
    return matches[0]


def analyze_crossings(request: AnalysisRequest) -> AnalysisResult:
    """Measure threshold crossings in one waveform."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("crossing analysis requires WaveformSettings")
    if len(settings.signal_columns) != 1 or len(settings.thresholds) != 1:
        raise ValueError("crossing analysis requires one signal and one threshold")
    run = _run(request)
    axis, axis_unit = _column(run, settings.axis_column)
    signal, _signal_unit = _column(run, settings.signal_columns[0])
    crossings = _find_crossings(
        signal,
        axis,
        settings.thresholds[0],
        rising=settings.rising,
    )
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.CROSSINGS,
        request.spec.input_ids,
        metrics=(Metric("crossing_count", len(crossings)),),
        tables=(
            DataTable(
                "crossings",
                (DataColumn("crossing_axis", crossings, axis_unit),),
            ),
        ),
    )


def analyze_spectrum(request: AnalysisRequest) -> AnalysisResult:
    """Calculate one-sided amplitude spectra for aligned waveforms."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("spectrum analysis requires WaveformSettings")
    if not settings.signal_columns:
        raise ValueError("spectrum analysis requires at least one signal")
    run = _run(request)
    axis, axis_unit = _column(run, settings.axis_column)
    if axis_unit not in {"", "s"}:
        raise ValueError("spectrum axis must use seconds")
    if len(axis) < 3:
        raise ValueError("spectrum axis requires at least three samples")
    intervals = np.diff(np.asarray(axis, dtype=np.float64))
    interval = float(np.median(intervals))
    if not np.allclose(intervals, interval, rtol=1e-6, atol=1e-18):
        raise ValueError("spectrum axis must be uniformly sampled")

    result_columns = []
    frequency_hz = None
    for signal_name in settings.signal_columns:
        signal, signal_unit = _column(run, signal_name)
        frequencies, amplitudes = _amplitude_spectrum(
            signal,
            interval,
            window=settings.window,
        )
        if frequency_hz is None:
            frequency_hz = frequencies
            result_columns.append(DataColumn("frequency_hz", frequencies, "Hz"))
        result_columns.append(DataColumn(f"{signal_name}_amplitude", amplitudes, signal_unit))
    assert frequency_hz is not None
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.SPECTRUM,
        request.spec.input_ids,
        metrics=(
            Metric("sample_count", len(axis)),
            Metric("sample_interval_s", interval, "s"),
            Metric("nyquist_hz", float(frequency_hz[-1]), "Hz"),
        ),
        tables=(DataTable("spectrum", tuple(result_columns)),),
    )


def analyze_edge_samples(request: AnalysisRequest) -> AnalysisResult:
    """Sample waveforms at a stable point in each clock interval."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("edge-sampling analysis requires WaveformSettings")
    if len(settings.signal_columns) < 2 or len(settings.thresholds) != 1:
        raise ValueError("edge sampling requires a clock, at least one signal, and one threshold")
    run = _run(request)
    axis, axis_unit = _column(run, settings.axis_column)
    clock, _ = _column(run, settings.signal_columns[0])
    sampled_names = settings.signal_columns[1:]
    sampled_inputs = tuple(_column(run, name)[0] for name in sampled_names)
    sample_axis, sampled = _sample_at_edges(
        axis,
        clock,
        sampled_inputs,
        settings.thresholds[0],
        rising=settings.rising,
        sample_fraction=settings.sample_fraction,
    )
    columns = [DataColumn("sample_axis", sample_axis, axis_unit)]
    for name, values in zip(sampled_names, sampled, strict=True):
        columns.append(DataColumn(name, values, _column(run, name)[1]))
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.EDGE_SAMPLES,
        request.spec.input_ids,
        metrics=(Metric("sample_count", len(sample_axis)),),
        tables=(DataTable("edge_samples", tuple(columns)),),
    )


def analyze_delay(request: AnalysisRequest) -> AnalysisResult:
    """Measure the first response delay after one trigger edge."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("delay analysis requires WaveformSettings")
    if len(settings.signal_columns) != 2 or len(settings.thresholds) != 2:
        raise ValueError("delay analysis requires trigger/ response signals and thresholds")
    run = _run(request)
    axis, axis_unit = _column(run, settings.axis_column)
    trigger, _ = _column(run, settings.signal_columns[0])
    response, _ = _column(run, settings.signal_columns[1])
    trigger_time, response_time, delay = _delay(
        axis,
        trigger,
        response,
        settings.thresholds[0],
        settings.thresholds[1],
        rising=settings.rising,
    )
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.DELAY,
        request.spec.input_ids,
        metrics=(
            Metric("trigger_axis", trigger_time, axis_unit),
            Metric("response_axis", response_time, axis_unit),
            Metric("delay", delay, axis_unit),
        ),
    )


def analyze_settling(request: AnalysisRequest) -> AnalysisResult:
    """Measure the first point after which a waveform stays within tolerance."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("settling analysis requires WaveformSettings")
    if len(settings.signal_columns) != 1:
        raise ValueError("settling analysis requires one signal")
    run = _run(request)
    axis, axis_unit = _column(run, settings.axis_column)
    signal, signal_unit = _column(run, settings.signal_columns[0])
    tolerance = 0.01 if settings.tolerance is None else settings.tolerance
    settling = _settling_time(
        axis,
        signal,
        target=settings.target,
        tolerance=tolerance,
    )
    target = float(signal[-1]) if settings.target is None else settings.target
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.SETTLING,
        request.spec.input_ids,
        metrics=(
            Metric("settling_axis", settling, axis_unit),
            Metric("target", target, signal_unit),
            Metric("relative_tolerance", tolerance),
        ),
    )


def analyze_power(request: AnalysisRequest) -> AnalysisResult:
    """Measure mean consumed power from current and voltage."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("power analysis requires WaveformSettings")
    if len(settings.signal_columns) not in {1, 2}:
        raise ValueError("power analysis requires current and optional voltage columns")
    run = _run(request)
    current, _ = _column(run, settings.signal_columns[0])
    if len(settings.signal_columns) == 2:
        voltage, _ = _column(run, settings.signal_columns[1])
    elif settings.target is not None:
        voltage = settings.target
    else:
        raise ValueError("power analysis requires a voltage column or target supply voltage")
    power = _average_power(current, voltage)
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.POWER,
        request.spec.input_ids,
        metrics=(Metric("average_power_w", power, "W"),),
    )


def analyze_offset(request: AnalysisRequest) -> AnalysisResult:
    """Measure input-referred offset at an output zero crossing."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("offset analysis requires WaveformSettings")
    if len(settings.signal_columns) != 2:
        raise ValueError("offset analysis requires input- and output-difference columns")
    run = _run(request)
    axis, _ = _column(run, settings.axis_column)
    input_difference, input_unit = _column(run, settings.signal_columns[0])
    output_difference, _ = _column(run, settings.signal_columns[1])
    offset = _offset_crossing(input_difference, output_difference, axis)
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.OFFSET,
        request.spec.input_ids,
        metrics=(Metric("input_offset", offset, input_unit),),
    )


def analyze_charge_injection(request: AnalysisRequest) -> AnalysisResult:
    """Measure a waveform step between two explicit axis coordinates."""

    settings = request.spec.settings
    if not isinstance(settings, WaveformSettings):
        raise TypeError("charge-injection analysis requires WaveformSettings")
    if len(settings.signal_columns) != 1 or len(settings.thresholds) != 2:
        raise ValueError("charge injection requires one signal and before/after axis coordinates")
    run = _run(request)
    axis, _ = _column(run, settings.axis_column)
    signal, signal_unit = _column(run, settings.signal_columns[0])
    before = float(np.interp(settings.thresholds[0], axis, signal))
    after = float(np.interp(settings.thresholds[1], axis, signal))
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.CHARGE_INJECTION,
        request.spec.input_ids,
        metrics=(
            Metric("before", before, signal_unit),
            Metric("after", after, signal_unit),
            Metric("charge_injection", after - before, signal_unit),
        ),
    )


def analyze_statistics(request: AnalysisRequest) -> AnalysisResult:
    """Calculate a reusable scalar statistical summary."""

    settings = request.spec.settings
    if not isinstance(settings, StatisticsSettings):
        raise TypeError("statistics analysis requires StatisticsSettings")
    run = _run(request)
    values, unit = _column(run, settings.value_column)
    metrics = tuple(Metric(metric.name, metric.value, unit if metric.name != "count" else "") for metric in _statistics(values))
    counts, edges = np.histogram(values, bins=settings.histogram_bins)
    return AnalysisResult(
        request.spec.name,
        AnalysisKind.STATISTICS,
        request.spec.input_ids,
        metrics=metrics,
        tables=(
            DataTable(
                "histogram",
                (
                    DataColumn("bin_start", edges[:-1], unit),
                    DataColumn("bin_stop", edges[1:], unit),
                    DataColumn("count", counts),
                ),
            ),
        ),
    )


def analyze_waveform(request: AnalysisRequest) -> AnalysisResult:
    """Dispatch a generic waveform or scalar measurement request."""

    handlers = {
        AnalysisKind.CROSSINGS: analyze_crossings,
        AnalysisKind.EDGE_SAMPLES: analyze_edge_samples,
        AnalysisKind.SPECTRUM: analyze_spectrum,
        AnalysisKind.DELAY: analyze_delay,
        AnalysisKind.SETTLING: analyze_settling,
        AnalysisKind.POWER: analyze_power,
        AnalysisKind.OFFSET: analyze_offset,
        AnalysisKind.CHARGE_INJECTION: analyze_charge_injection,
        AnalysisKind.STATISTICS: analyze_statistics,
    }
    try:
        handler = handlers[request.spec.kind]
    except KeyError:
        raise ValueError(f"{request.spec.kind.value!r} is not a generic measurement") from None
    return handler(request)
