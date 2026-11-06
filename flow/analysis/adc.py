"""A typed view of an ADC capture's scope records: the scope's decisions against FastRX's
(``analyze_adc_scope_bits``). The converter's own analyses are its block's (``flow.adc.analysis``),
the comparator's views of its captures the comparator's (``comp.analyze_scope_edges``,
``comp.analyze_edge_eye``, ``comp.analyze_response``).

Every public function follows the analysis contract in ``readme.md``: one positional measurement
input, keyword-only prior results, and one typed result. Architecture sizes (decisions,
capacitors, codes, symbols per decision) are derived from the measurement parameters, never
written as literals.
"""

from __future__ import annotations

import math

import numpy as np

from flow.analysis import calc
from flow.analysis.types import AnalysisAdcScopeBits, MeasAdc

# =============================================================================
# Scope analyses
# =============================================================================


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
