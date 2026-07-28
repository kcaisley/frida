"""Typed comparator, CDAC, and sampler analyses.

Block analyses use canonical column names and compose the numerical kernels in
``flow.analysis.measure``.  Optional measurements are omitted with an explicit
warning when a result does not contain the required waveform.
"""

from __future__ import annotations

import math

import numpy as np

from flow.analysis.measure import (
    _average_power,
    _delay,
    _endpoint_linearity,
    _find_crossings,
    _offset_crossing,
    _settling_time,
)
from flow.analysis.models import (
    AnalysisKind,
    AnalysisRequest,
    AnalysisResult,
    DataColumn,
    DataTable,
    Metric,
    WaveformSettings,
)


def _run(request: AnalysisRequest):
    if len(request.spec.input_ids) != 1:
        raise ValueError(f"{request.spec.kind.value} analysis requires exactly one run")
    run_id = request.spec.input_ids[0]
    for run in request.runs:
        if run.run_id == run_id:
            return run
    raise KeyError(f"block analysis has no run {run_id!r}")


def _optional_column(run, name: str) -> np.ndarray | None:
    matches = [table.column(name) for table in run.tables if name in table.column_names]
    if not matches:
        return None
    if len(matches) > 1:
        raise KeyError(f"run {run.run_id!r} contains ambiguous column {name!r}")
    return np.asarray(matches[0], dtype=np.float64)


def _required_column(run, name: str) -> np.ndarray:
    values = _optional_column(run, name)
    if values is None:
        raise KeyError(f"run {run.run_id!r} requires canonical column {name!r}")
    return values


def _parameter_float(run, name: str, default: float | None = None) -> float | None:
    value = run.parameters.get(name, default)
    return float(value) if isinstance(value, (int, float)) else default


def _power_metric(run) -> Metric | None:
    current = _optional_column(run, "supply_current_a")
    if current is None:
        return None
    voltage = _optional_column(run, "supply_v")
    if voltage is None:
        voltage = _parameter_float(run, "supply_v")
    if voltage is None:
        return None
    return Metric("average_power_w", _average_power(current, voltage), "W")


def analyze_comparator(request: AnalysisRequest) -> AnalysisResult:
    """Analyze comparator offset, transition noise, delay, resolution, and power."""

    run = _run(request)
    settings = request.spec.settings
    if settings is not None and not isinstance(settings, WaveformSettings):
        raise TypeError("comparator analysis settings must be WaveformSettings")
    settings = settings or WaveformSettings()

    time_s = _required_column(run, settings.axis_column)
    input_difference = _required_column(run, "vin_p_v") - _required_column(run, "vin_n_v")
    output_difference = _required_column(run, "vout_p_v") - _required_column(run, "vout_n_v")
    metrics = [
        Metric(
            "input_offset_v",
            _offset_crossing(input_difference, output_difference, time_s),
            "V",
        )
    ]
    tables = []
    warnings = []

    unique_inputs, inverse = np.unique(input_difference, return_inverse=True)
    if len(unique_inputs) >= 3:
        probabilities = np.asarray(
            [np.mean(output_difference[inverse == index] > 0.0) for index in range(len(unique_inputs))],
            dtype=np.float64,
        )
        order = np.argsort(probabilities)
        sorted_probability = probabilities[order]
        sorted_input = unique_inputs[order]
        if sorted_probability[0] <= 0.158655 <= sorted_probability[-1] and sorted_probability[0] <= 0.841345 <= sorted_probability[-1]:
            input_p16 = float(np.interp(0.158655, sorted_probability, sorted_input))
            input_p84 = float(np.interp(0.841345, sorted_probability, sorted_input))
            metrics.append(Metric("input_noise_sigma_v", abs(input_p84 - input_p16) / 2.0, "V"))
        else:
            warnings.append("comparator decision sweep does not span both Gaussian one-sigma probabilities")
        tables.append(
            DataTable(
                "decision_curve",
                (
                    DataColumn("vin_diff_v", unique_inputs, "V"),
                    DataColumn("decision_probability", probabilities),
                ),
            )
        )
    else:
        warnings.append("comparator noise needs at least three distinct differential inputs")

    clock = _optional_column(run, "clock_v")
    if clock is not None:
        clock_threshold = (
            settings.thresholds[0]
            if settings.thresholds
            else float((np.min(clock) + np.max(clock)) / 2.0)
        )
        response = np.abs(output_difference)
        response_threshold = float(np.max(response) / 2.0)
        _trigger, _response, delay = _delay(
            time_s,
            clock,
            response,
            clock_threshold,
            response_threshold,
            rising=True,
        )
        metrics.append(Metric("clock_to_decision_delay_s", delay, "s"))
    else:
        warnings.append("comparator delay needs clock_v")

    tolerance = settings.tolerance if settings.tolerance is not None else 0.01
    metrics.append(
        Metric(
            "settling_time_s",
            _settling_time(
                time_s,
                output_difference,
                target=settings.target,
                tolerance=tolerance,
            ),
            "s",
        )
    )
    resolution_threshold = _parameter_float(
        run,
        "metastability_threshold_v",
        0.1 * float(np.ptp(output_difference)),
    )
    assert resolution_threshold is not None
    metrics.append(
        Metric(
            "unresolved_fraction",
            float(np.mean(np.abs(output_difference) < resolution_threshold)),
        )
    )
    power = _power_metric(run)
    if power is not None:
        metrics.append(power)
    else:
        warnings.append("comparator power needs supply_current_a and supply_v")

    return AnalysisResult(
        request.spec.name,
        AnalysisKind.COMPARATOR,
        request.spec.input_ids,
        metrics=tuple(metrics),
        tables=tuple(tables),
        warnings=tuple(warnings),
    )


def analyze_cdac(request: AnalysisRequest) -> AnalysisResult:
    """Analyze CDAC transfer linearity, settling, mismatch, and power."""

    run = _run(request)
    settings = request.spec.settings
    if settings is not None and not isinstance(settings, WaveformSettings):
        raise TypeError("CDAC analysis settings must be WaveformSettings")
    settings = settings or WaveformSettings()
    codes = _required_column(run, "code")
    output_v = _required_column(run, "output_v")
    unique_codes, inverse = np.unique(codes, return_inverse=True)
    mean_output = np.asarray(
        [np.mean(output_v[inverse == index]) for index in range(len(unique_codes))],
        dtype=np.float64,
    )
    dnl, inl, lsb_v = _endpoint_linearity(unique_codes, mean_output)
    metrics = (
        Metric("lsb_v", lsb_v, "V"),
        Metric("maximum_abs_dnl", float(np.max(np.abs(dnl))) if len(dnl) else math.nan, "LSB"),
        Metric("maximum_abs_inl", float(np.max(np.abs(inl))) if len(inl) else math.nan, "LSB"),
    )
    tables = [
        DataTable(
            "transfer",
            (
                DataColumn("code", unique_codes, "LSB"),
                DataColumn("output_v", mean_output, "V"),
                DataColumn("inl", inl, "LSB"),
            ),
        )
    ]
    if len(dnl):
        tables.append(
            DataTable(
                "dnl",
                (
                    DataColumn("code", unique_codes[1:], "LSB"),
                    DataColumn("dnl", dnl, "LSB"),
                ),
            )
        )

    metric_list = list(metrics)
    warnings = []
    time_s = _optional_column(run, settings.axis_column)
    if time_s is not None:
        tolerance = settings.tolerance if settings.tolerance is not None else 0.01
        metric_list.append(
            Metric(
                "settling_time_s",
                _settling_time(
                    time_s,
                    output_v,
                    target=settings.target,
                    tolerance=tolerance,
                ),
                "s",
            )
        )
    else:
        warnings.append("CDAC settling needs time_s")
    power = _power_metric(run)
    if power is not None:
        metric_list.append(power)
    else:
        warnings.append("CDAC power needs supply_current_a and supply_v")

    return AnalysisResult(
        request.spec.name,
        AnalysisKind.CDAC,
        request.spec.input_ids,
        metrics=tuple(metric_list),
        tables=tuple(tables),
        warnings=tuple(warnings),
    )


def analyze_sampler(request: AnalysisRequest) -> AnalysisResult:
    """Analyze sampler error, settling, charge injection, noise, and power."""

    run = _run(request)
    settings = request.spec.settings
    if settings is not None and not isinstance(settings, WaveformSettings):
        raise TypeError("sampler analysis settings must be WaveformSettings")
    settings = settings or WaveformSettings()
    time_s = _required_column(run, settings.axis_column)
    input_v = _required_column(run, "input_v")
    output_v = _required_column(run, "output_v")
    error_v = output_v - input_v
    metrics = [
        Metric("rms_sampling_error_v", float(np.sqrt(np.mean(error_v**2))), "V"),
        Metric("mean_sampling_error_v", float(np.mean(error_v)), "V"),
        Metric("sampling_noise_rms_v", float(np.std(error_v)), "V"),
        Metric(
            "settling_time_s",
            _settling_time(
                time_s,
                output_v,
                target=settings.target if settings.target is not None else float(input_v[-1]),
                tolerance=settings.tolerance if settings.tolerance is not None else 0.01,
            ),
            "s",
        ),
    ]
    warnings = []
    clock = _optional_column(run, "clock_v")
    if clock is not None:
        threshold = (
            settings.thresholds[0]
            if settings.thresholds
            else float((np.min(clock) + np.max(clock)) / 2.0)
        )
        edges = _find_crossings(clock, time_s, threshold, rising=False)
        if len(edges):
            edge_index = int(np.searchsorted(time_s, edges[0]))
            before_index = max(0, edge_index - 1)
            after_index = min(len(output_v) - 1, edge_index + 1)
            metrics.append(
                Metric(
                    "charge_injection_v",
                    float(output_v[after_index] - output_v[before_index]),
                    "V",
                )
            )
        else:
            warnings.append("sampler clock contains no falling edge")
    else:
        warnings.append("sampler charge injection needs clock_v")
    power = _power_metric(run)
    if power is not None:
        metrics.append(power)
    else:
        warnings.append("sampler power needs supply_current_a and supply_v")

    return AnalysisResult(
        request.spec.name,
        AnalysisKind.SAMPLER,
        request.spec.input_ids,
        metrics=tuple(metrics),
        tables=(
            DataTable(
                "sampling_error",
                (
                    DataColumn("time_s", time_s, "s"),
                    DataColumn("input_v", input_v, "V"),
                    DataColumn("output_v", output_v, "V"),
                    DataColumn("error_v", error_v, "V"),
                ),
            ),
        ),
        warnings=tuple(warnings),
    )


def analyze_block(request: AnalysisRequest) -> AnalysisResult:
    """Dispatch one comparator, CDAC, or sampler analysis."""

    handlers = {
        AnalysisKind.COMPARATOR: analyze_comparator,
        AnalysisKind.CDAC: analyze_cdac,
        AnalysisKind.SAMPLER: analyze_sampler,
    }
    try:
        handler = handlers[request.spec.kind]
    except KeyError:
        raise ValueError(f"{request.spec.kind.value!r} is not a block analysis") from None
    return handler(request)
