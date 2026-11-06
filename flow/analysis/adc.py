"""Typed views of an ADC capture's comparator and scope records: the comparator's output edges and
their eye from scope records (``analyze_adc_comp_out_edge_eye``), the scope's decisions against
FastRX's (``analyze_adc_scope_bits``), and a simulation's comparator edge eye and response. The
converter's own analyses are its block's (``flow.adc.analysis``).

Every public function follows the analysis contract in ``readme.md``: one positional measurement
input, keyword-only prior results, and one typed result. Architecture sizes (decisions,
capacitors, codes, symbols per decision) are derived from the measurement parameters, never
written as literals.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.adc.sim import AdcSequence
from flow.analysis import calc
from flow.analysis.types import (
    AnalysisAdcComparatorEdgeEye,
    AnalysisAdcComparatorResponse,
    AnalysisAdcCompOutEdgeEye,
    AnalysisAdcScopeBits,
    MeasAdc,
    measurement_identity,
)

# =============================================================================
# Scope and comparator-output analyses
# =============================================================================


def analyze_adc_comp_out_edge_eye(measurements: Sequence[MeasAdc]) -> AnalysisAdcCompOutEdgeEye:
    """Measure external comparator transitions and clock jitter from scope records.

    Every scope record of every measurement is one capture of one complete
    conversion. All measurements must share one sequence and symbol rate.
    """

    identity = measurement_identity(measurements)
    first = measurements[0]
    sequence = AdcSequence.from_tb_params(first.tb)
    symbol_rate_bps = float(first.tb.symbol_rate)
    if any(
        AdcSequence.from_tb_params(measurement.tb) != sequence or float(measurement.tb.symbol_rate) != symbol_rate_bps
        for measurement in measurements
    ):
        raise ValueError("comparator eye measurements must share one sequence and symbol rate")
    decisions = len(first.nominal_bout_weights)
    decision_period_s = first.symbols_per_decision / symbol_rate_bps

    time_s = None
    comp_records = []
    comp_out_records = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("comparator eye requires scope waveform records")
        if time_s is None:
            time_s = wave.time_s
        elif not np.array_equal(time_s, wave.time_s):
            raise ValueError("comparator eye scope records must share one time axis")
        comp_records.extend(wave.v["seq_comp"])
        comp_out_records.extend(wave.v["comp_out"])
    assert time_s is not None

    capture_count = len(comp_records)
    clock_edges_s = np.empty((capture_count, decisions))
    delays_s = np.full((capture_count, decisions), np.nan)
    jitter_s = np.empty((capture_count, decisions))
    unchanged = np.zeros(decisions, dtype=np.int64)
    multiple = np.zeros(decisions, dtype=np.int64)
    unsettled = np.zeros(decisions, dtype=np.int64)
    for capture_index, (comp_v, comp_out_v) in enumerate(zip(comp_records, comp_out_records, strict=True)):
        # Take logic levels from the 5th/95th percentiles, which ignore edge
        # overshoot, and require at least 50 mV of swing to call it a logic signal.
        comp_low, comp_high = np.percentile(comp_v, (5, 95))
        out_low, out_high = np.percentile(comp_out_v, (5, 95))
        if comp_high - comp_low < 0.05 or out_high - out_low < 0.05:
            raise ValueError(f"capture {capture_index} lacks a valid COMP or COMP_OUT swing")
        comp_level = float((comp_low + comp_high) / 2)
        out_level = float((out_low + out_high) / 2)
        clock_edges = calc.cross(comp_v, time_s, comp_level, edge="rising")
        clock_edges = clock_edges[clock_edges >= 0][:decisions]
        # Allow 20% of a decision period of edge jitter before rejecting the record.
        if len(clock_edges) != decisions or np.any(
            np.abs(np.diff(clock_edges) - decision_period_s) > 0.2 * decision_period_s
        ):
            raise ValueError(f"capture {capture_index} does not contain one complete {decisions}-decision conversion")
        clock_edges_s[capture_index] = clock_edges
        jitter_s[capture_index] = clock_edges - clock_edges[0] - np.arange(decisions) * decision_period_s
        rising_edges = calc.cross(comp_out_v, time_s, out_level, edge="rising")
        output_edges = calc.cross(comp_out_v, time_s, out_level, edge="either")
        for decision, clock_edge in enumerate(clock_edges):
            matching = output_edges[(output_edges >= clock_edge) & (output_edges < clock_edge + decision_period_s)]
            if len(matching) == 1:
                rising = bool(np.any(rising_edges == matching[0]))
                final_index = min(np.searchsorted(time_s, clock_edge + decision_period_s), len(time_s)) - 1
                final_valid = comp_out_v[final_index] >= out_level if rising else comp_out_v[final_index] <= out_level
                if final_valid:
                    delays_s[capture_index, decision] = matching[0] - clock_edge
                else:
                    unsettled[decision] += 1
            elif len(matching) == 0:
                unchanged[decision] += 1
            else:
                multiple[decision] += 1

    # Resample every capture at the scope spacing, aligned to its B0 COMP rise
    # and folded at every decision's COMP rise; NaN lies outside the record.
    sample_interval_s = float(np.median(np.diff(time_s)))
    aligned_time_s = np.arange(-0.2 * decision_period_s, decisions * decision_period_s, sample_interval_s)
    eye_phase = np.arange(-0.2, 1.0, sample_interval_s / decision_period_s)
    traces = (np.asarray(comp_records), np.asarray(comp_out_records))
    aligned = [
        np.asarray(
            [
                np.interp(edges[0] + aligned_time_s, time_s, row, left=np.nan, right=np.nan)
                for row, edges in zip(values, clock_edges_s, strict=True)
            ]
        )
        for values in traces
    ]
    folded = [
        np.asarray(
            [
                np.interp(edge + eye_phase * decision_period_s, time_s, row, left=np.nan, right=np.nan)
                for row, edges in zip(values, clock_edges_s, strict=True)
                for edge in edges
            ]
        )
        for values in traces
    ]
    return AnalysisAdcCompOutEdgeEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        aligned_time_s=aligned_time_s,
        aligned_comp_v=aligned[0],
        aligned_comp_out_v=aligned[1],
        eye_phase=eye_phase,
        eye_comp_v=folded[0],
        eye_comp_out_v=folded[1],
        clock_edges_s=clock_edges_s,
        delays_s=delays_s,
        jitter_s=jitter_s,
        unchanged=unchanged,
        multiple=multiple,
        unsettled=unsettled,
        decision_period_s=decision_period_s,
        conversion_rate_hz=symbol_rate_bps / sequence.conversion_symbols,
    )


def analyze_adc_scope_bits(measurement: MeasAdc) -> AnalysisAdcScopeBits:
    """Decode the scope in the middle of the delayed comparator decision.

    New captures record the characterized COMP-to-COMP_OUT link delay. Older
    files without that field retain their historical 7/8-period reference.
    This independent scope reference is not the physical FastRX sample instant.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("scope/FastRX comparison requires a captured scope waveform")
    tb = measurement.tb
    decisions = measurement.bout.shape[1]
    symbols_per_decision = measurement.symbols_per_decision
    time_s = wave.time_s
    comp_v = wave.v["seq_comp"][0]
    comp_out_v = wave.v["comp_out"][0]
    # Logic levels from the 1st/99th percentiles; at least 100 mV of swing is
    # required before a scope trace is treated as a logic signal.
    comp_low_v, comp_high_v = np.percentile(comp_v, (1.0, 99.0))
    comp_out_low_v, comp_out_high_v = np.percentile(comp_out_v, (1.0, 99.0))
    comp_threshold_v = float((comp_low_v + comp_high_v) / 2.0)
    comp_out_threshold_v = float((comp_out_low_v + comp_out_high_v) / 2.0)
    if comp_high_v - comp_low_v < 0.1:
        raise ValueError("scope COMP waveform does not have a valid logic swing")
    if comp_out_high_v - comp_out_low_v < 0.1:
        raise ValueError("scope COMP_OUT waveform does not have a valid logic swing")

    rising_edges_s = calc.cross(comp_v, time_s, comp_threshold_v, edge="rising")
    rising_edges_s = rising_edges_s[rising_edges_s >= 0.0]
    if len(rising_edges_s) < decisions:
        raise ValueError(f"scope contains only {len(rising_edges_s)} COMP rising edges; expected at least {decisions}")
    comp_edge_times_s = rising_edges_s[:decisions]
    decision_period_s = symbols_per_decision / float(tb.symbol_rate)
    link_delay_s = measurement.info.readbacks.get("scope_comp_out_delay_s")
    # Historical captures sample 7/8 of a decision period after the COMP edge.
    sample_offset_s = (7.0 / 8.0) * decision_period_s
    if link_delay_s is not None:
        link_delay_s = float(link_delay_s)
        if not math.isfinite(link_delay_s) or link_delay_s < 0:
            raise ValueError("scope comparator link delay must be finite and non-negative")
        # Sample mid-decision after the characterized link delay.
        sample_offset_s = link_delay_s + 0.5 * decision_period_s
    sample_times_s = comp_edge_times_s + sample_offset_s
    sample_values_v = calc.value(comp_out_v, time_s, sample_times_s, extrapolate=False)
    scope_bits = np.asarray(sample_values_v) > comp_out_threshold_v
    if measurement.info.readbacks.get("scope_comp_out_inverted") is True:
        scope_bits = ~scope_bits
    identity = measurement.identity
    return AnalysisAdcScopeBits(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        scope_bits=scope_bits,
        fastrx_bits=measurement.bout[measurement.conversion_index == wave.record_index[0]][0].astype(np.bool_),
        comp_threshold_v=comp_threshold_v,
        comp_out_threshold_v=comp_out_threshold_v,
        comp_edge_times_s=comp_edge_times_s,
        sample_times_s=sample_times_s,
        sample_values_v=np.asarray(sample_values_v),
    )


# =============================================================================
# Comparator edge eye and response
# =============================================================================


def analyze_adc_comparator_edge_eye(measurement: MeasAdc) -> AnalysisAdcComparatorEdgeEye:
    """Align every saved conversion at its B0 COMP rise and fold it at every decision.

    The three traces are the comparator clock, the positive SR-latch output,
    and the XC-latch magnitude ``|P-N|``. Aligned records span from 0.2
    decision periods before B0 to one period after the final decision; folded
    windows span -0.1..1.1 periods around each COMP rise. Both are resampled at
    the saved waveform spacing, with NaN outside a record.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC edge eye requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    threshold = float(measurement.tb.vdd_d.dc) / 2
    decisions = len(measurement.nominal_bout_weights)
    traces = (
        wave.v["clk_comp"],
        wave.v["comp_out_p"],
        np.abs(wave.v["comp.latch_p"] - wave.v["comp.latch_n"]),
    )
    record_edges = []
    for record in range(len(wave.record_index)):
        init_edges = calc.cross(wave.v["seq_init"][record], time, threshold, edge="rising", initial_high=True)
        if not len(init_edges):
            raise ValueError(f"conversion {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        clock_edges = calc.cross(wave.v["clk_comp"][record], time, threshold, edge="rising")
        clock_edges = clock_edges[(clock_edges >= init_edges[0]) & (clock_edges < stop)]
        if len(clock_edges) != decisions:
            raise ValueError(f"conversion {record} has {len(clock_edges)} COMP rises; expected {decisions}")
        record_edges.append(clock_edges)
    record_edges = np.asarray(record_edges)
    period_s = float(np.median(np.diff(record_edges, axis=1)))
    decision_edge_s = np.median(record_edges - record_edges[:, :1], axis=0)
    sample_interval_s = float(np.median(np.diff(time)))
    aligned_time_s = np.arange(-0.2 * period_s, decision_edge_s[-1] + period_s, sample_interval_s)
    eye_phase = np.arange(-0.1, 1.1, sample_interval_s / period_s)
    identity = measurement.identity
    return AnalysisAdcComparatorEdgeEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        decision_period_s=period_s,
        decision_edge_s=decision_edge_s,
        supply_v=max(float(measurement.tb.vdd_a.dc), float(measurement.tb.vdd_d.dc)),
        aligned_time_s=aligned_time_s,
        aligned_v=np.asarray(
            [
                [
                    np.interp(edges[0] + aligned_time_s, time, row, left=np.nan, right=np.nan)
                    for row, edges in zip(values, record_edges, strict=True)
                ]
                for values in traces
            ]
        ),
        eye_phase=eye_phase,
        eye_v=np.asarray(
            [
                [
                    np.interp(edge + eye_phase * period_s, time, row, left=np.nan, right=np.nan)
                    for row, edges in zip(values, record_edges, strict=True)
                    for edge in edges
                ]
                for values in traces
            ]
        ),
    )


def analyze_adc_comparator_response(measurement: MeasAdc) -> AnalysisAdcComparatorResponse:
    """Measure midpoint-valid XC and single-ended SR timing after COMP rise.

    One XC node must fall below 50% of VDD and the other remain above 50%
    before COMP reset. The positive buffered SR output must enter the matching
    half-rail band before the next COMP rise. Both must remain valid through
    the end of their windows. Already-held SR states are counted separately.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "seq_logic", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC comparator response requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    analog_supply = float(measurement.tb.vdd_a.dc)
    digital_supply = float(measurement.tb.vdd_d.dc)
    decisions = len(measurement.nominal_bout_weights)
    rows = []
    for record, conversion in enumerate(wave.record_index):
        signals = {name: values[record] for name, values in wave.v.items() if name in required}
        # One conversion starts at the record's INIT rise and holds one COMP rise per decision.
        init_edges = calc.cross(signals["seq_init"], time, digital_supply / 2, edge="rising", initial_high=True)
        comp_edges = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="rising")
        if not len(init_edges):
            raise ValueError(f"record {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        comp_indices = np.flatnonzero((comp_edges >= init_edges[0]) & (comp_edges < stop))
        if len(comp_indices) != decisions:
            raise ValueError(f"record {record} has {len(comp_indices)} COMP rises; expected {decisions}")
        following = np.r_[comp_edges, np.nan][comp_indices + 1]
        resets = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="falling")
        latch_p, latch_n = signals["comp.latch_p"], signals["comp.latch_n"]
        sr_p = signals["comp_out_p"]
        for decision, (start, next_comp) in enumerate(zip(comp_edges[comp_indices], following, strict=True)):
            stop = next_comp if np.isfinite(next_comp) else time[-1]
            reset_edges = resets[(resets > start) & (resets < stop)]
            reset = float(reset_edges[0]) if len(reset_edges) == 1 else math.nan
            evaluation = (time >= start) & (time < reset)
            internal_delay = math.nan
            sr_delay = math.nan
            held = False
            if np.any(evaluation):
                last = np.flatnonzero(evaluation)[-1]
                final_p = float(latch_p[last])
                final_n = float(latch_n[last])
                midpoint = 0.5 * analog_supply
                if final_p != final_n:
                    target = 1 if final_p > final_n else -1
                    high, low = (latch_p, latch_n) if target > 0 else (latch_n, latch_p)
                    valid = (high[evaluation] >= midpoint) & (low[evaluation] <= midpoint)
                    stable = calc.settlingTime(valid, time[evaluation])
                    if np.isfinite(stable):
                        internal_delay = max(0.0, stable - start)
                    # Time the observed SR state even if the XC pair did not
                    # settle across the midpoint before COMP reset.
                    output = (time >= start) & (time < stop)
                    valid = sr_p[output] >= midpoint if target > 0 else sr_p[output] <= midpoint
                    stable = calc.settlingTime(valid, time[output])
                    if np.isfinite(stable):
                        held = bool(np.all(valid))
                        if not held:
                            sr_delay = max(0.0, stable - start)
            rows.append((int(conversion), decision, internal_delay, sr_delay, held))
    identity = measurement.identity
    return AnalysisAdcComparatorResponse(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        conversion_index=np.asarray([row[0] for row in rows]),
        decision_index=np.asarray([row[1] for row in rows]),
        internal_response_s=np.asarray([row[2] for row in rows]),
        sr_response_s=np.asarray([row[3] for row in rows]),
        sr_held=np.asarray([row[4] for row in rows]),
        sample_interval_s=float(calc.ymax(np.diff(time))),
        conversion_rate_hz=measurement.active_conversion_rate_hz,
    )
