"""Software-only tests of the ADC's comparator and scope views (``flow.analysis.adc``); the
converter's own analyses are tested with its block (``flow/adc/test_analysis.py``), whose capture
builders these take."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from flow import adc
from flow.adc.test_analysis import adc_measurement, adc_timing_measurement
from flow.analysis.adc import analyze_adc_comparator_response, analyze_adc_scope_bits
from flow.analysis.types import MeasAdc


@pytest.mark.parametrize("symbol_rate_hz", (800.0e6, 1600.0e6))
@pytest.mark.parametrize("comp_high_symbols", (4, 5, 6, 7))
@pytest.mark.parametrize("link_delay_periods", (None, 1.2))
def test_scope_wave_decode_matches_fastrx_with_normal_and_inverted_probe(
    symbol_rate_hz: float, comp_high_symbols: int, link_delay_periods: float | None
) -> None:
    expected_bits = np.asarray(([1, 0] * 8) + [1], dtype=np.uint8)
    decision_period_s = 8.0 / symbol_rate_hz
    first_rise_s = 0.2 * decision_period_s
    time_s = np.arange(-0.2, 19.8, 0.002) * decision_period_s
    comp_v = np.where(
        (time_s >= first_rise_s)
        & (np.mod(time_s - first_rise_s, decision_period_s) < comp_high_symbols / 8.0 * decision_period_s),
        1.2,
        0.0,
    )
    comp_out_v = np.zeros_like(time_s)
    for index, bit in enumerate(expected_bits):
        # Late decisions still resolve before 7/8, independently of COMP width.
        edge_s = (
            first_rise_s + (index + (0.85 if link_delay_periods is None else link_delay_periods)) * decision_period_s
        )
        comp_out_v[(time_s >= edge_s) & (time_s < edge_s + decision_period_s)] = 1.2 * bit

    base = adc_measurement([100], sample_rate_hz=symbol_rate_hz / 256.0, observed_adc=1)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    assert base.wave is not None
    normal = replace(
        base,
        bout=expected_bits[np.newaxis, :],
        wave=replace(
            base.wave,
            time_s=time_s,
            v={
                **base.wave.v,
                "vin_diff": np.zeros((1, len(time_s))),
                "seq_comp": comp_v[np.newaxis, :],
                "seq_logic": np.zeros((1, len(time_s))),
                "comp_out": comp_out_v[np.newaxis, :],
            },
        ),
    )
    assert normal.wave is not None
    offset_periods = 7.0 / 8.0
    if link_delay_periods is not None:
        # A real propagation delay can exceed one decision period at high baud.
        # The legacy reference samples the wrong bit; explicit latency fixes it.
        assert analyze_adc_scope_bits(normal).mismatch_count > 0
        normal = replace(
            normal,
            info=replace(
                normal.info,
                readbacks={
                    "scope_comp_out_delay_s": link_delay_periods * decision_period_s,
                },
            ),
        )
        assert normal.wave is not None
        offset_periods = link_delay_periods + 0.5
    normal_analysis = analyze_adc_scope_bits(normal)

    assert normal_analysis.scope_bit_string == "10101010101010101"
    assert normal_analysis.fastrx_bit_string == normal_analysis.scope_bit_string
    assert normal_analysis.mismatch_count == 0
    np.testing.assert_allclose(
        normal_analysis.sample_times_s,
        first_rise_s + (np.arange(17) + offset_periods) * decision_period_s,
        rtol=0,
        atol=0.002 * decision_period_s,
    )

    assert normal.wave is not None
    inverted = replace(
        normal,
        info=replace(normal.info, readbacks=normal.info.readbacks | {"scope_comp_out_inverted": True}),
        wave=replace(normal.wave, v={**normal.wave.v, "comp_out": (1.2 - comp_out_v)[np.newaxis, :]}),
    )
    inverted_analysis = analyze_adc_scope_bits(inverted)
    assert inverted_analysis.scope_bit_string == normal_analysis.scope_bit_string
    assert inverted_analysis.mismatch_count == 0

    # A triggered scope record can refer to a later FastRX conversion.
    later = replace(
        normal,
        param=replace(normal.param, tb=replace(normal.param.tb, conversions=2)),
        conversion_index=np.array([0, 1]),
        bout=np.stack((1 - expected_bits, expected_bits)),
        dout_raw=np.repeat(normal.dout_raw, 2),
        dout=np.repeat(normal.dout, 2),
        vin_diff_v=np.repeat(normal.vin_diff_v, 2),
        wave=replace(normal.wave, record_index=np.array([1])),
    )
    assert analyze_adc_scope_bits(later).mismatch_count == 0


def test_adc_record_analyses_ignore_high_comp_at_record_boundary() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    clock = measurement.wave.v["clk_comp"].copy()
    clock[0, 0] = 1.2  # Tail of the preceding conversion, not a new COMP edge.
    voltage = {**measurement.wave.v, "clk_comp": clock}
    measurement = replace(measurement, wave=replace(measurement.wave, v=voltage))
    assert measurement.wave is not None

    timing = adc.analyze_timing_closure(measurement)
    response = analyze_adc_comparator_response(measurement)
    np.testing.assert_array_equal(timing.decision_index, np.arange(17))
    np.testing.assert_array_equal(response.decision_index, np.arange(17))


def test_adc_comparator_response_requires_both_xc_rails_and_times_one_sr_output() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    time = measurement.wave.time_s
    signals = {name: values.copy() for name, values in measurement.wave.v.items()}
    glitch = (time >= 1.5e-9) & (time < 1.6e-9)
    signals["comp.latch_p"][0, glitch] = 0.5
    signals["comp_out_p"][0, glitch] = 0.5
    not_low_enough = (time >= 5e-9) & (time < 5.8e-9)
    signals["comp.latch_p"][0, not_low_enough] = 0.7
    weak_midpoint_decision = (time >= 7.25e-9) & (time < 7.8e-9)
    signals["comp.latch_p"][0, weak_midpoint_decision] = 0.7
    signals["comp.latch_n"][0, weak_midpoint_decision] = 0.55
    del signals["comp_out_n"]
    result = analyze_adc_comparator_response(replace(measurement, wave=replace(measurement.wave, v=signals)))

    np.testing.assert_array_equal(result.decision_index, np.arange(17))
    assert result.internal_response_s[0] == pytest.approx(0.595e-9, abs=11e-12)
    assert result.sr_response_s[0] == pytest.approx(0.595e-9, abs=11e-12)
    assert result.sr_held[1] and np.isnan(result.sr_response_s[1])
    assert np.isnan(result.internal_response_s[2])
    assert np.isfinite(result.sr_response_s[2])
    assert np.isfinite(result.internal_response_s[3])
