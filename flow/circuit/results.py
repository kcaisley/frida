"""Convert circuit simulation or extraction results into typed FRIDA measurements."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np
from vlsirtools.spice.sim_data import TranResult

from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcNets
from flow.analysis.adc import _adc_decision_times
from flow.analysis.io import interpolate_wave_records
from flow.analysis.types import (
    AdcDaq,
    AdcIntWave,
    CompDaq,
    CompIntWave,
    MeasAdcInt,
    MeasCapArray,
    MeasCompInt,
    MeasInfo,
    MeasSampInt,
)
from flow.caparray import get_caparray_weights
from flow.caparray.subckt import CapArrayParams
from flow.comp.sim import CompTbParams
from flow.comp.subckt import CompNets
from flow.samp.sim import SampTbParams

# Spectre strobe timestamps can jitter by sub-femtoseconds around a 10 ps grid.
_RAW_STEP_RTOL = 1e-3


def read_raw_transient(path: Path) -> TranResult:
    """Read a saved transient with VLSIR, preserving all raw variable names."""
    from vlsirtools.spice.spectre import parse_nutbin

    with path.open("rb") as stream:
        plots = parse_nutbin(stream)
    transient = [plot for plot in plots.values() if "time" in plot.data]
    if len(transient) != 1:
        raise ValueError("Raw file must contain exactly one transient analysis")
    plot = transient[0]
    return TranResult(plot.analysis_name, plot.data, {})


def _is_valid_transient(result: TranResult, names: Mapping[str, str], interval: float) -> bool:
    """Check transient shape, complete bindings, and a requested sampling interval."""
    if not isinstance(result, TranResult) or not np.isfinite(interval) or interval <= 0:
        return False
    if set(result.data) != set(names) or names.get("time") != "time":
        return False
    if len(set(names.values())) != len(names):
        return False
    time = np.asarray(result.data["time"])
    return bool(
        time.ndim == 1
        and len(time) >= 2
        and np.all(np.isfinite(time))
        and np.all(np.diff(time) > 0)
        and np.max(np.diff(time)) <= interval * (1 + _RAW_STEP_RTOL)
        and all(np.asarray(value).shape == time.shape and np.all(np.isfinite(value)) for value in result.data.values())
    )


def _conversion_inputs(result: TranResult, names: Mapping[str, str], interval: float, *, supply_rails: tuple[str, ...]):
    """Alias traces; express selected supply-source currents as positive draw.

    Other current traces retain the simulator's reference direction.
    """
    if not _is_valid_transient(result, names, interval):
        raise ValueError(
            "Invalid transient: require complete unique bindings, aligned finite traces, and raw timestep no larger than waveform_sample_interval_s"
        )
    # VLSIR owns the numerical representation; only its variable names change.
    canonical = TranResult(
        result.analysis_name, {names[key]: np.asarray(value) for key, value in result.data.items()}, result.measurements
    )
    voltage = {key: value for key, value in canonical.data.items() if key != "time" and not key.startswith("i(")}
    current = {
        key[2:-1]: -value if key[2:-1] in supply_rails else value
        for key, value in canonical.data.items()
        if key.startswith("i(")
    }
    return canonical.data["time"], voltage, current


def _validate_adc_conversion(logic_times: np.ndarray) -> np.ndarray:
    """Require at least one complete ADC record, including the next-cycle B16 observation.

    Return the mask of usable records; incomplete records are still discarded.
    """
    valid = np.all(np.isfinite(logic_times), axis=1)
    if not np.any(valid):
        raise ValueError("No complete ADC conversions; save the next-cycle B16 observation")
    return valid


def _validate_comp_conversion(times_s: np.ndarray, params: CompTbParams) -> tuple[int, float]:
    """Require the recorded duration to match every scheduled comparator trial."""
    trial_count = len(params.vin_cm_values_v) * len(params.vin_diff_values_v) * params.conversions
    cycle_s = float(params.reset_time_s) + float(params.evaluation_time_s)
    actual_duration_s = float(times_s[-1] - times_s[0])
    if not np.isclose(actual_duration_s, trial_count * cycle_s, rtol=1e-6, atol=params.waveform_sample_interval_s):
        raise ValueError("Comparator transient duration differs from its trial schedule")
    return trial_count, cycle_s


def convert_raw_adc_to_measurement(
    result: TranResult,
    *,
    params: AdcTbParams,
    raw_path: Path,
    signal_names: Mapping[str, str],
) -> MeasAdcInt:
    """Map a VLSIR transient to canonical ADC records and decode LOGIC observations once."""

    supply_rails = tuple(net.name for net in AdcNets.signals.values() if net.usage == h.Usage.POWER)
    times_s, signals, currents = _conversion_inputs(
        result, signal_names, params.waveform_sample_interval_s, supply_rails=supply_rails
    )
    code_weights = np.asarray([2 * weight for weight in get_caparray_weights(params.dut.cdac)] + [1], dtype=np.int64)
    threshold_v = float(params.vdd_d.dc) / 2
    starts, comp_times, logic_times, _ = _adc_decision_times(
        times_s,
        signals[AdcNets.seq_init.name],
        signals[AdcNets.seq_comp.name],
        signals[AdcNets.seq_logic.name],
        params.conversions,
        threshold_v,
    )
    valid = _validate_adc_conversion(logic_times)
    unavailable_conversions = np.flatnonzero(~valid).tolist()
    retained_conversions = np.flatnonzero(valid).tolist()
    decode_starts = starts
    comp_edge_times_s = comp_times[valid]
    final_sample_times_s = logic_times[valid, -1]
    sample_times_s = logic_times[valid]
    bout = (
        np.interp(sample_times_s.ravel(), times_s, signals[AdcNets.comp_out.name]).reshape(sample_times_s.shape)
        > threshold_v
    ).astype(np.uint8)
    dout_raw = bout.astype(np.int64) @ code_weights
    dout = np.rint(dout_raw * ((1 << params.dut.adc_bits) - 1) / np.sum(code_weights)).astype(np.int64)
    conversion_start_indices = np.searchsorted(times_s, starts[valid], side="right")
    conversion_start_indices[starts[valid] == times_s[0]] = 0
    conversion_starts_s = times_s[conversion_start_indices]
    vin_diff_v = np.interp(
        comp_edge_times_s[:, 0], times_s, (signals[AdcNets.vin_p.name] - signals[AdcNets.vin_n.name])
    )
    complete_conversions = len(conversion_start_indices)
    # HDL21 paramclasses are runtime dataclasses, although their decorator's
    # typing stub does not currently expose that fact to ty.
    params = dataclasses.replace(
        params,
        conversions=complete_conversions,
    )

    # Align waveform records to the repeated sequencer-pattern boundary, not
    # to SEQ_INIT's rising edge inside that pattern. This retains the pre-INIT
    # portion of each conversion; the next-cycle tail retains the B16 observation.
    waveform_starts_s = conversion_starts_s - (conversion_starts_s[0] - times_s[0])
    # Keep a next-cycle tail in every record, including the final B16 observation.
    period_s = len(params.seq_init_pattern) / float(params.symbol_rate)
    tail_s = (params.seq_comp_pattern.index("01") + 2) / float(params.symbol_rate)
    record_duration_s = min(period_s + tail_s, float(times_s[-1] - waveform_starts_s[-1]))
    waveform_conversion_indices = np.asarray(retained_conversions, dtype=np.int64)
    intervals = [(float(start), float(start + record_duration_s)) for start in waveform_starts_s]
    relative_time_s, waveform_records = interpolate_wave_records(
        times_s,
        signals,
        intervals,
        params.waveform_sample_interval_s,
    )
    _, current_records = interpolate_wave_records(
        times_s,
        currents,
        intervals,
        params.waveform_sample_interval_s,
    )

    readbacks: dict[str, str | int | float | bool] = {
        "raw_file": Path(raw_path).name,
        "raw_format": "spectre_nutbin",
        "raw_points": len(times_s),
        "raw_max_timestep_s": float(np.max(np.diff(times_s))),
        "waveform_sample_interval_s": params.waveform_sample_interval_s,
        "waveform_interpolated_from_coarser_raw": bool(
            np.max(np.diff(times_s)) > params.waveform_sample_interval_s * (1.0 + _RAW_STEP_RTOL)
        ),
        "decision_sample_fraction": 1.0,
        "decision_time_reference": "seq_logic_rising_threshold_B0_B15",
        "original_conversion_count": len(decode_starts),
        "unavailable_logic_conversions_json": json.dumps(unavailable_conversions),
        "final_decision_sample_fraction": 1.0,
        "final_decision_time_reference": "next_init_seq_logic_rising_threshold",
        "final_decision_sample_times_s_json": json.dumps([float(value) for value in final_sample_times_s]),
        "supply_power_available": True,
        "supply_current_convention": "positive_current_draw",
        "signal_map_json": json.dumps(dict(signal_names), sort_keys=True),
    }
    rail_voltages = {name: float(getattr(params, name).dc) for name in supply_rails}
    for rail, voltage_v in rail_voltages.items():
        current_draw_a = currents[rail]
        duration_s = float(times_s[-1] - times_s[0])
        average_current_a = float(np.trapezoid(current_draw_a, times_s) / duration_s)
        readbacks[f"{rail}_active_average_current_a"] = average_current_a
        readbacks[f"{rail}_active_average_power_w"] = voltage_v * average_current_a

    return MeasAdcInt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcInt",
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(
                Path(raw_path).stat().st_mtime,
                tz=UTC,
            ),
            instruments={"simulator": "Spectre"},
            readbacks=readbacks,
        ),
        param=params,
        daq=AdcDaq(
            conversion_index=np.asarray(retained_conversions, dtype=np.int64),
            bout=bout,
            dout_raw=dout_raw,
            dout=dout,
            vin_diff_v=vin_diff_v,
        ),
        wave=AdcIntWave(
            conversion_index=waveform_conversion_indices,
            time_s=relative_time_s,
            voltage=waveform_records,
            current=current_records,
        ),
    )


def convert_raw_comp_to_measurement(
    result: TranResult,
    *,
    params: CompTbParams,
    raw_path: Path,
    signal_names: Mapping[str, str],
) -> MeasCompInt:
    """Decode one Spectre comparator campaign result into ``MeasCompInt``.

    All decisions at every input point are retained in ``daq``. Dense
    waveforms retain every trial at the three points nearest 50% probability
    plus one representative trial everywhere else.
    """

    times_s, signals, currents = _conversion_inputs(
        result, signal_names, params.waveform_sample_interval_s, supply_rails=(CompNets.vdd.name,)
    )
    expected_trial_count, cycle_s = _validate_comp_conversion(times_s, params)

    nominal_vdiff = []
    nominal_vcm = []
    point_first_trial = []
    point_index = 0
    for vcm in params.vin_cm_values_v:
        for vdiff in params.vin_diff_values_v:
            first_trial = point_index * params.conversions
            point_first_trial.append(first_trial)
            nominal_vdiff.extend([float(vdiff)] * params.conversions)
            nominal_vcm.extend([float(vcm)] * params.conversions)
            point_index += 1

    # Sample just before the evaluation falling edge. Interpolation uses the
    # uniformly stored raw grid but Spectre's transient-noise integration keeps
    # its much finer internal timesteps.
    decision_margin_s = max(float(params.transition_time_s) * 2.0, params.waveform_sample_interval_s / 2.0)
    sample_times_s = times_s[0] + (np.arange(expected_trial_count) + 1) * cycle_s - decision_margin_s
    out_p = np.interp(sample_times_s, times_s, signals[CompNets.outp.name])
    out_n = np.interp(sample_times_s, times_s, signals[CompNets.outn.name])
    decisions = (out_p > out_n).astype(np.uint8)

    # Preserve all records at the three points closest to 50% probability and
    # one representative record from every other S-curve point. Selecting from
    # the measured decisions follows offset topologies whose metastable region
    # is not centered at zero input, while bounding each production H5 file.
    representative_trials = [first + params.conversions // 2 for first in point_first_trial]
    point_probability = np.asarray(
        [np.mean(decisions[first : first + params.conversions]) for first in point_first_trial],
        dtype=np.float64,
    )
    transition_points = np.argsort(np.abs(point_probability - 0.5), kind="stable")[: min(3, len(point_first_trial))]
    transition_trials = [
        trial
        for point in transition_points
        for trial in range(point_first_trial[point], point_first_trial[point] + params.conversions)
    ]
    waveform_trial_indices = np.unique(np.asarray((*representative_trials, *transition_trials), dtype=np.int64))
    record_duration_s = cycle_s
    relative_time_s, waveform_records = interpolate_wave_records(
        times_s,
        signals,
        [
            (
                float(times_s[0] + trial * cycle_s),
                float(times_s[0] + trial * cycle_s + record_duration_s),
            )
            for trial in waveform_trial_indices
        ],
        params.waveform_sample_interval_s,
    )

    _, current_records = interpolate_wave_records(
        times_s,
        currents,
        [
            (float(times_s[0] + trial * cycle_s), float(times_s[0] + (trial + 1) * cycle_s))
            for trial in waveform_trial_indices
        ],
        params.waveform_sample_interval_s,
    )
    supply_v = float(params.vdd)
    average_current_a = float(np.trapezoid(currents[CompNets.vdd.name], times_s) / (times_s[-1] - times_s[0]))
    average_power_w = supply_v * average_current_a
    readbacks: dict[str, str | int | float | bool] = {
        "signal_map_json": json.dumps(dict(signal_names), sort_keys=True),
        "raw_file": Path(raw_path).name,
        "raw_format": "spectre_nutbin",
        "raw_points": len(times_s),
        "raw_max_timestep_s": float(np.max(np.diff(times_s))),
        "waveform_sample_interval_s": params.waveform_sample_interval_s,
        "waveform_interpolated_from_coarser_raw": bool(
            np.max(np.diff(times_s)) > params.waveform_sample_interval_s * (1.0 + _RAW_STEP_RTOL)
        ),
        "decision_sample_margin_s": decision_margin_s,
        "supply_power_available": True,
        "supply_current_convention": "positive_current_draw",
        "vdd_v": supply_v,
        "vdd_active_average_current_a": average_current_a,
        "vdd_active_average_power_w": average_power_w,
        "energy_per_decision_j": average_power_w * cycle_s,
    }

    return MeasCompInt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasCompInt",
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(Path(raw_path).stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks=readbacks,
        ),
        param=params,
        daq=CompDaq(
            trial_index=np.arange(expected_trial_count, dtype=np.int64),
            vin_diff_v=np.asarray(nominal_vdiff, dtype=np.float64),
            vin_cm_v=np.asarray(nominal_vcm, dtype=np.float64),
            decision=decisions,
        ),
        wave=CompIntWave(
            trial_index=waveform_trial_indices,
            time_s=relative_time_s,
            voltage=waveform_records,
            current=current_records,
        ),
    )


def convert_raw_samp_to_measurement(
    result: TranResult,
    *,
    params: SampTbParams,
    raw_path: Path,
    signal_names: Mapping[str, str],
) -> MeasSampInt:
    """Reserved sampler transient adapter; signal_names maps SPICE names to aliases."""
    raise NotImplementedError("sampler transient conversion to MeasSampInt is not implemented")


def convert_netlist_caparray_to_measurement(
    *,
    netlist_path: Path,
    params: CapArrayParams,
    net_names: Mapping[str, str],
    device_names: Mapping[str, str],
) -> MeasCapArray:
    """Reserved Calibre xACT .pex.netlist adapter, not a transient-waveform decoder.

    ``net_names`` and ``device_names`` map raw netlist identifiers to analysis
    aliases. An empty mapping selects no identifiers from that category.
    The future contract will pair design capacitances with extracted values
    and support per-capacitor Monte Carlo samples and their variation. Its
    measurement type must describe capacitance data, not MeasCdacInt waveforms.
    """
    raise NotImplementedError("caparray nominal/extracted capacitance and Monte Carlo conversion is not implemented")
