"""Software-only tests for typed ADC analyses."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime

import hdl21 as h
import numpy as np
import pytest

from flow.adc import AdcParams
from flow.adc.sequences import SEQUENCES, AdcSequence
from flow.adc.sim import AdcTbParams
from flow.analysis.adc import (
    analyze_adc_cdac_settling,
    analyze_adc_code_density_nonlinearity,
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_endpoint_nonlinearity,
    analyze_adc_noise,
    analyze_adc_operating_conditions,
    analyze_adc_power,
    analyze_adc_power_waveform,
    analyze_adc_ramp,
    analyze_adc_sampling_noise,
    analyze_adc_scope_bits,
    analyze_adc_transfer,
)
from flow.analysis.types import (
    AnalysisAdcCalibration,
    MeasAdc,
    MeasInfo,
    Wave,
)
from flow.caparray import CapArrayConfig
from flow.scans.params import AdcScanParams

timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)


def adc_sampling_measurement() -> MeasAdc:
    """Three held samples with known differential spread and common fast ripple."""

    template = adc_measurement([0, 0, 0], internal=True, sample_rate_hz=1e8, waveform_sample_count=101)
    assert template.wave is not None
    assert isinstance(template, MeasAdc)
    wave = template.wave
    assert wave is not None
    repeated = {name: np.repeat(value, 3, axis=0) for name, value in wave.v.items()}
    sample = np.tile(np.where(wave.time_s < 2e-9, 1.2, 0.0), (3, 1))
    comp = np.tile(np.where(wave.time_s < 5e-9, 0.0, 1.2), (3, 1))
    ripple = 1e-3 * np.sin(wave.time_s * 2e9 * np.pi)
    repeated.update(
        seq_samp=sample,
        seq_comp=comp,
        clk_comp=comp,
        clk_samp_p=sample,
        clk_samp_n=sample,
        clk_samp_p_b=1.2 - sample,
        clk_samp_n_b=1.2 - sample,
        vin_p=np.full_like(sample, 0.725),
        vin_n=np.full_like(sample, 0.675),
        vdac_p=0.725 + np.array([-1e-4, 0, 1e-4])[:, None] + ripple,
        vdac_n=np.full_like(sample, 0.675),
    )
    return replace(
        template,
        wave=replace(
            wave,
            record_index=np.arange(3),
            v=repeated,
            i={name: np.repeat(value, 3, axis=0) for name, value in wave.i.items()},
        ),
    )


def test_sampling_noise_interpolates_exactly_one_ns_after_each_sample_edge() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    edges_s = np.asarray([1.93e-9, 2.17e-9, 2.41e-9])
    sample = np.clip(0.6 + (edges_s[:, None] - wave.time_s) * 1e9, 0.0, 1.2)
    offsets = np.asarray([-1e-4, 0.0, 1e-4])
    vp = 0.725 + offsets[:, None] + wave.time_s * 1e6
    analysis = analyze_adc_sampling_noise(
        replace(measurement, wave=replace(wave, v={**wave.v, "seq_samp": sample, "vdac_p": vp}))
    )
    expected_times = edges_s + 1e-9
    np.testing.assert_allclose(analysis.window_start_s, expected_times, rtol=0, atol=1e-23)
    np.testing.assert_array_equal(analysis.window_start_s, analysis.window_stop_s)
    np.testing.assert_allclose(analysis.held_diff_v, 0.05 + offsets + expected_times * 1e6)
    assert analysis.sigma_v == pytest.approx(np.std(offsets + expected_times * 1e6, ddof=1))


@pytest.mark.parametrize("comp_level", (0.0, 1.2))
def test_sampling_noise_accepts_comparator_already_fired_or_inactive(comp_level) -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    clocks = np.full_like(measurement.wave.v["seq_comp"], comp_level)
    analysis = analyze_adc_sampling_noise(
        replace(
            measurement,
            wave=replace(measurement.wave, v={**measurement.wave.v, "seq_comp": clocks, "clk_comp": clocks}),
        )
    )
    assert len(analysis.held_diff_v) == 3
    assert analysis.sigma_v == pytest.approx(100e-6)


def test_sampling_noise_does_not_extrapolate_past_saved_record() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    sample = np.tile(np.where(wave.time_s < wave.time_s[-1] - 0.5e-9, 1.2, 0.0), (3, 1))
    with pytest.raises(ValueError, match="outside the waveform"):
        analyze_adc_sampling_noise(replace(measurement, wave=replace(wave, v={**wave.v, "seq_samp": sample})))


def test_sampling_noise_rejects_changing_input_and_missing_sample_edge() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    with pytest.raises(ValueError, match="fixed differential input"):
        analyze_adc_sampling_noise(
            replace(
                measurement,
                wave=replace(measurement.wave, v={**measurement.wave.v, "vin_p": measurement.wave.v["vdac_p"]}),
            )
        )
    with pytest.raises(ValueError, match="SAMP falling edge"):
        analyze_adc_sampling_noise(
            replace(
                measurement,
                wave=replace(
                    measurement.wave,
                    v={
                        **measurement.wave.v,
                        "seq_samp": np.zeros_like(measurement.wave.v["seq_samp"]),
                    },
                ),
            )
        )


def adc_measurement(
    dout,
    *,
    vin_diff_v: float | Sequence[float] | np.ndarray = 0.0,
    sample_rate_hz: float = 1.0e6,
    input_frequency_hz: float = 10.0e3,
    logic_phase_delay_symbols: float = 0.0,
    observed_adc: int | None = None,
    readbacks: Mapping[str, str | int | float | bool] | None = None,
    internal: bool = False,
    waveform_sample_count: int = 8,
) -> MeasAdc:
    """Build one compact external or internal ADC measurement for numerical tests."""

    dout = np.asarray(dout, dtype=np.int64)
    vin_diff_array = np.asarray(vin_diff_v, dtype=np.float64)
    if vin_diff_array.ndim == 0:
        vin_diff_array = np.full(len(dout), vin_diff_array.item())
    template = AdcTbParams()
    measurement_selection = {}
    if observed_adc is not None:
        measurement_selection = {
            "board_id": 7,
            "observed_adc": observed_adc,
            "active_adc_mask": tuple(int(index == observed_adc) for index in reversed(range(16))),
        }
    tb_params = AdcTbParams(
        conversions=len(dout),
        symbol_rate=sample_rate_hz * len(template.seq_init_pattern),
        vin_diff=h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
        seq_logic_pattern=timing_sequences[int(logic_phase_delay_symbols) + 3].logic,
    )
    time_s = np.linspace(0.0, 1.0 / sample_rate_hz, waveform_sample_count)
    zeros = np.zeros((1, len(time_s)))
    daq = {
        "conversion_index": np.arange(len(dout)),
        "bout": np.zeros((len(dout), 17), dtype=np.uint8),
        "dout_raw": dout,
        "dout": dout,
        "vin_diff_v": vin_diff_array,
    }
    if internal:
        return MeasAdc(
            group=tb_params.mc_seed,
            index=tb_params.mc_index,
            dut=tb_params.dut,
            info=MeasInfo(
                backend="spice", timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC), readbacks=dict(readbacks or {})
            ),
            param=tb_params,
            **daq,
            wave=Wave(
                record_index=np.asarray([0], dtype=np.int64),
                time_s=time_s,
                v={
                    "seq_comp": zeros,
                    "seq_logic": zeros,
                    "comp_out": zeros,
                    "vin_p": zeros,
                    "vin_n": zeros,
                    "seq_init": zeros,
                    "seq_samp": zeros,
                    "vdac_p": zeros,
                    "vdac_n": zeros,
                    "clk_samp_p": zeros,
                    "clk_samp_p_b": zeros,
                    "clk_samp_n": zeros,
                    "clk_samp_n_b": zeros,
                    "clk_comp": zeros,
                    "comp_out_p": zeros,
                    "comp_out_n": zeros,
                    "dac_state_p[0]": zeros,
                    "dac_state_p[7]": zeros,
                    "dac_state_p[15]": zeros,
                    "dac_state_n[0]": zeros,
                    "dac_state_n[7]": zeros,
                    "dac_state_n[15]": zeros,
                    "dac_botplate_p[0]": zeros,
                    "dac_botplate_p[7]": zeros,
                    "dac_botplate_p[15]": zeros,
                    "dac_botplate_n[0]": zeros,
                    "dac_botplate_n[7]": zeros,
                    "dac_botplate_n[15]": zeros,
                },
                i={"vdd_a": zeros, "vdd_d": zeros, "vdd_dac": zeros},
            ),
        )
    return MeasAdc(
        group=7 if observed_adc is not None else None,
        index=observed_adc,
        dut=tb_params.dut,
        info=MeasInfo(
            backend="behavioral", timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC), readbacks=dict(readbacks or {})
        ),
        param=AdcScanParams(tb=tb_params, **measurement_selection),
        **daq,
        wave=Wave(
            record_index=np.asarray([0], dtype=np.int64),
            time_s=time_s,
            v={"vin_diff": zeros, "seq_comp": zeros, "seq_logic": zeros, "comp_out": zeros},
        ),
    )


def adc_cdac_settling_measurement() -> MeasAdc:
    """Build one compact internal waveform with three representative CDAC updates."""

    base = adc_measurement([2_048], internal=True)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    time_s = np.arange(0.0, 18.51e-9, 10e-12)
    zeros = np.zeros((1, len(time_s)))
    comp_edges_s = 0.5e-9 + np.arange(17) * 1e-9
    logic_edges_s = 0.9e-9 + np.arange(16) * 1e-9

    def pulse_train(edges_s: np.ndarray, width_s: float) -> np.ndarray:
        values = np.zeros_like(time_s)
        for edge_s in edges_s:
            values[(time_s >= edge_s) & (time_s < edge_s + width_s)] = 1.2
        return values

    seq_comp_v = pulse_train(comp_edges_s, 0.3e-9)
    seq_logic_v = pulse_train(logic_edges_s, 0.2e-9)
    comp_out_p_v = np.zeros_like(time_s)
    for cycle, edge_s in enumerate(comp_edges_s):
        comp_out_p_v[time_s >= edge_s + 0.08e-9] = 1.2 * (cycle % 2)
    comp_out_n_v = 1.2 - comp_out_p_v

    wave_values = {name: zeros for name in base.wave.v}
    vdac_p_v = np.full_like(time_s, 0.7)
    vdac_n_v = np.full_like(time_s, 0.7)
    for stage_index, cycle_index, step_v in ((0, 0, 0.12), (7, 7, -0.04), (15, 15, 0.01)):
        logic_edge_s = logic_edges_s[cycle_index]
        switched = time_s >= logic_edge_s
        settling = np.zeros_like(time_s)
        settling[switched] = step_v * (1.0 - np.exp(-(time_s[switched] - logic_edge_s) / 0.05e-9))
        vdac_p_v += settling
        vdac_n_v -= settling
        state_p_v = np.where(switched, 1.2, 0.0)
        state_n_v = 1.2 - state_p_v
        bottom_switched = time_s >= logic_edge_s + 0.05e-9
        wave_values[f"dac_state_p[{stage_index}]"] = state_p_v[None, :]
        wave_values[f"dac_state_n[{stage_index}]"] = state_n_v[None, :]
        wave_values[f"dac_botplate_p[{stage_index}]"] = np.where(bottom_switched, 1.2, 0.0)[None, :]
        wave_values[f"dac_botplate_n[{stage_index}]"] = np.where(bottom_switched, 0.0, 1.2)[None, :]

    wave_values.update(
        {
            "seq_comp": seq_comp_v[None, :],
            "clk_comp": seq_comp_v[None, :],
            "seq_logic": seq_logic_v[None, :],
            "comp_out": comp_out_p_v[None, :],
            "comp_out_p": comp_out_p_v[None, :],
            "comp_out_n": comp_out_n_v[None, :],
            "vdac_p": vdac_p_v[None, :],
            "vdac_n": vdac_n_v[None, :],
        }
    )
    wave = Wave(
        record_index=np.asarray([0]),
        time_s=time_s,
        v={
            **wave_values,
            "comp.latch_p": (1.2 - 0.5 * seq_comp_v)[None, :],
            "comp.latch_n": (1.2 - 0.8 * seq_comp_v)[None, :],
        },
        i={key: zeros for key in base.wave.i},
    )
    return replace(base, wave=wave)


def adc_ramp_measurement(*, cycles: int = 4, observed_adc: int = 0, start_offset: int = 0) -> MeasAdc:
    """Build a repeated monotonic decision ramp whose PWL period matches its capture.

    ``start_offset`` delays the capture start relative to the ramp, so the
    first wrap occurs ``samples_per_cycle - start_offset`` conversions in.
    """

    samples_per_cycle = 4_096
    nominal_weights = np.asarray(
        [2 * value for value in (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1)] + [1]
    )
    # Convert an ideal linear ramp with a greedy SAR search; the redundant
    # weights represent every raw code, so DOUT_RAW equals BOUT @ weights.
    remaining = np.rint(np.linspace(0.0, np.sum(nominal_weights), samples_per_cycle)).astype(np.int64)
    one_cycle_bout = np.zeros((samples_per_cycle, len(nominal_weights)), dtype=np.uint8)
    for decision, weight in enumerate(nominal_weights):
        one_cycle_bout[:, decision] = remaining >= weight
        remaining -= one_cycle_bout[:, decision] * weight
    bout = np.roll(np.tile(one_cycle_bout, (cycles, 1)), -start_offset, axis=0).astype(np.uint8, copy=False)
    sample_count = len(bout)
    dout_raw = bout @ nominal_weights
    dout = np.rint(dout_raw * 4_095 / np.sum(nominal_weights)).astype(np.int64)
    vin_diff_v = np.tile(np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False), cycles)
    base = adc_measurement(np.zeros(sample_count, dtype=np.int64), observed_adc=observed_adc)
    assert isinstance(base, MeasAdc)
    params = AdcScanParams(
        tb=AdcTbParams(
            dut=base.param.tb.dut,
            conversions=sample_count,
            symbol_rate=base.param.tb.symbol_rate,
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / base.sample_rate_hz:.12g} 1"),
        ),
        board_id=7,
        observed_adc=observed_adc,
        active_adc_mask=tuple(int(index == observed_adc) for index in reversed(range(16))),
        campaign="adc_ramp",
    )
    return replace(
        base,
        param=params,
        conversion_index=np.arange(sample_count),
        bout=bout,
        dout_raw=dout_raw,
        dout=dout,
        vin_diff_v=vin_diff_v,
    )


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


def test_dynamic_analysis_recovers_sine_and_spectral_metrics() -> None:
    rng = np.random.default_rng(12345)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 20_000
    amplitude = 1_500.0
    offset = 2_040.0
    phase = 0.37
    noise_rms = 2.0
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = np.rint(
        offset
        + amplitude * np.sin(2.0 * np.pi * input_frequency_hz * time_s + phase)
        + rng.normal(0.0, noise_rms, sample_count)
    )
    msmt = adc_measurement(
        samples,
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz * (1.0 + 5e-6),
    )
    result = analyze_adc_dynamic(msmt)

    assert result.sample_count == sample_count
    assert result.fitted_frequency_hz == pytest.approx(input_frequency_hz, abs=0.02)
    assert result.amplitude_dout == pytest.approx(amplitude, rel=2e-4)
    assert result.offset_dout == pytest.approx(offset, abs=0.05)
    assert result.phase_rad == pytest.approx(phase, abs=2e-4)
    assert result.residual_rms_dout == pytest.approx(math.hypot(noise_rms, 1 / math.sqrt(12)), rel=0.05)
    assert result.input_referred_residual_rms_v == pytest.approx(result.residual_rms_dout * 0.5 / result.amplitude_dout)
    assert result.input_referred_noise_rms_v > 0
    assert result.enob_bits == pytest.approx((result.sinad_db - 1.76) / 6.02)
    assert len(result.fitted_dout) == sample_count


def test_dynamic_analysis_counts_sine_fit_residual_tails() -> None:
    """Count residuals beyond three fitted sigma without deleting samples."""

    sample_rate_hz = 1.0e6
    input_frequency_hz = 15_625.0
    time_s = np.arange(8_192) / sample_rate_hz
    samples = np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s))
    samples[1_234] += 40.0
    samples[4_321] -= 40.0
    msmt = adc_measurement(
        samples,
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
    )

    result = analyze_adc_dynamic(msmt)
    assert result.residual_tail_limit_dout == pytest.approx(3.0 * result.residual_rms_dout)
    assert result.expected_residual_tail_count == pytest.approx(len(samples) * math.erfc(3.0 / math.sqrt(2.0)))
    assert result.negative_residual_tail_count == 1
    assert result.positive_residual_tail_count == 1
    assert result.maximum_abs_residual_dout > 39.0


def test_dynamic_analysis_separates_noise_and_harmonics() -> None:
    rng = np.random.default_rng(7)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 65_536
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = np.rint(
        2_048.0
        + 1_500.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s + 0.2)
        + 15.0 * np.sin(2.0 * np.pi * 2.0 * input_frequency_hz * time_s - 0.1)
        + rng.normal(0.0, 1.0, sample_count)
    )
    result = analyze_adc_dynamic(
        adc_measurement(
            samples,
            sample_rate_hz=sample_rate_hz,
            input_frequency_hz=input_frequency_hz,
        )
    )

    assert result.spectral_snr_db == pytest.approx(59.9, abs=0.5)
    assert result.spectral_thd_db == pytest.approx(-40.0, abs=0.15)
    assert result.spectral_sfdr_db == pytest.approx(40.0, abs=0.15)
    assert result.spectral_sndr_db == pytest.approx(39.96, abs=0.2)


def test_transfer_noise_and_code_density_use_typed_adc_data() -> None:
    msmt = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
    )
    transfer = analyze_adc_transfer([msmt])
    noise = analyze_adc_code_distribution([msmt])
    linearity = analyze_adc_code_density_nonlinearity(msmt)

    np.testing.assert_allclose(transfer.mean_dout, (0.0, 1.5, 3.0))
    np.testing.assert_array_equal(noise.count.sum(axis=0)[:4], (2, 1, 1, 2))
    # The end codes are excluded; codes 1 and 2 hold one conversion each.
    assert linearity.code[0] == 1
    np.testing.assert_array_equal(linearity.count[:3], (1, 1, 2))
    assert linearity.retained_sample_count == linearity.sample_count == 6


def test_ramp_analysis_derives_period_and_fits_phase_without_detecting_jumps() -> None:
    """Fit the wrap phase instead of assuming the AWG and capture start together."""

    measurement = adc_ramp_measurement()
    analysis = analyze_adc_ramp(measurement)

    assert (analysis.group, analysis.index, analysis.dut) == (7, 0, measurement.dut)
    assert analysis.sample_count == 4 * 4_096
    assert analysis.period_conversions == pytest.approx(4_096, rel=1e-6)
    assert analysis.ramp_frequency_hz == pytest.approx(analysis.sample_rate_hz / 4_096, rel=1e-6)
    assert analysis.decoding == "uncalibrated_dout"
    assert analysis.label == "Uncalibrated DOUT"
    assert analysis.retained_sample_count == analysis.sample_count - analysis.reset_excluded_sample_count
    assert analysis.count.sum() == analysis.retained_sample_count
    # Bins whose only conversions sit beside a wrap stay empty; all others are populated.
    assert 4_096 - 9 <= len(analysis.transfer_vin_diff_v) <= 4_096


@pytest.mark.parametrize("start_offset", (1_000, 2_917))
def test_ramp_analysis_recovers_random_phase_and_its_retained_mask(start_offset: int) -> None:
    analysis = analyze_adc_ramp(adc_ramp_measurement(start_offset=start_offset))
    first_wrap = 4_096 - start_offset
    assert analysis.first_wrap_conversion == pytest.approx(first_wrap, abs=1.0)
    expected = np.ones(analysis.sample_count, dtype=bool)
    for wrap in analysis.reset_conversion_index:
        expected[max(0, wrap - 1) : wrap + 8] = False
    np.testing.assert_array_equal(analysis.retained, expected)
    assert abs(int(analysis.reset_conversion_index[0]) - first_wrap) <= 1


def test_ramp_analysis_of_a_nominal_simulation_has_no_instance() -> None:
    measurement = adc_ramp_measurement()
    simulated = replace(
        measurement,
        group=None,
        index=None,
        param=replace(
            measurement.param,
            board_id=None,
            observed_adc=None,
            active_adc_mask=None,
        ),
    )

    analysis = analyze_adc_ramp(simulated)

    assert analysis.group is None and analysis.index is None


def test_ramp_analysis_redecodes_with_common_calibration_weights() -> None:
    """Apply any calibration result to stored decisions without new HDF5."""

    measurement = adc_ramp_measurement()
    nominal = analyze_adc_ramp(measurement).weights.astype(np.float64)
    nominal *= 4095.0 / np.sum(nominal)
    calibrated = nominal.copy()
    calibrated[:2] *= (1.02, 0.97)
    calibrated *= 4095.0 / np.sum(calibrated)
    calibration = AnalysisAdcCalibration(
        group=7,
        index=0,
        dut=measurement.dut,
        method="calibration1",
        label="Synthetic calibrated BOUT",
        code_max=4095,
        nominal_weights=nominal,
        calibrated_weights=calibrated,
        measured_weight_mask=np.ones(17, dtype=np.bool_),
        training_sample_count=100,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )

    uncalibrated = analyze_adc_ramp(measurement)
    analysis = analyze_adc_ramp(measurement, calibration=calibration)

    assert (analysis.decoding, analysis.label) == ("calibration1", "Synthetic calibrated BOUT")
    # Every decoding of one capture shares the nominal phase fit and its retained conversions.
    np.testing.assert_array_equal(analysis.retained, uncalibrated.retained)
    assert analysis.count.sum() == uncalibrated.count.sum() == analysis.retained_sample_count
    assert not np.array_equal(uncalibrated.weights, analysis.weights)
    assert analysis.weights[0] == pytest.approx(calibrated[0])
    decoded = calibration.decode_bout(measurement.bout)
    distribution = analyze_adc_code_distribution([measurement], calibration=calibration)
    nonlinearity = analyze_adc_code_density_nonlinearity(measurement, calibration=calibration)
    assert distribution.count.sum() == len(decoded)
    assert nonlinearity.count.sum() == np.count_nonzero((decoded >= 1) & (decoded <= 4094))
    with pytest.raises(ValueError, match="does not match"):
        analyze_adc_ramp(measurement, calibration=replace(calibration, index=1))
    with pytest.raises(ValueError, match="does not match"):
        analyze_adc_ramp(measurement, calibration=replace(calibration, dut=replace(measurement.dut, adc_bits=10)))

    # Code-density nonlinearity reuses the ramp's single wrap-exclusion mask.
    ramp = analyze_adc_ramp(measurement)
    retained = analyze_adc_code_density_nonlinearity(measurement, ramp=ramp)
    assert retained.retained_sample_count == ramp.retained_sample_count
    counts = np.bincount(measurement.dout[ramp.retained], minlength=4096)[1:4095]
    np.testing.assert_array_equal(retained.count, counts)


def test_shared_adc_analyses_accept_internal_measurements() -> None:
    """Analyze simulated ADC data through the same public entry points."""

    static = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
        internal=True,
    )
    assert isinstance(static, MeasAdc)
    assert analyze_adc_transfer([static]).sample_count.sum() == 6
    assert analyze_adc_code_distribution([static]).sample_count.sum() == 6
    assert analyze_adc_code_density_nonlinearity(static).retained_sample_count == 6

    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    time_s = np.arange(2_048) / sample_rate_hz
    dynamic = adc_measurement(
        np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s)),
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
        internal=True,
    )
    assert analyze_adc_dynamic(dynamic).sample_count == len(time_s)


def test_endpoint_nonlinearity_uses_first_contact_and_omits_unbracketed_endpoints() -> None:
    # Mean codes are [0, 0.5, 0.5, 1.5, 3.5]. The first plateau is
    # reached at input 1; the final 3.5 threshold has no saved crossing.
    measurement = adc_measurement([0, 0, 1, 0, 1, 1, 2, 3, 4], vin_diff_v=[0, 1, 1, 2, 2, 3, 3, 4, 4])
    analysis = analyze_adc_endpoint_nonlinearity(measurement)
    np.testing.assert_array_equal(analysis.code, [1, 2])
    np.testing.assert_allclose(analysis.transition_vin_diff_v, [3.0, 3.5])
    assert analysis.endpoint_lsb_v == pytest.approx(1.25)


def test_endpoint_linearity_interpolates_static_code_transitions() -> None:
    inputs = np.linspace(-0.6, 0.6, 129)
    ideal_codes = np.rint(np.linspace(0.0, 15.0, len(inputs)))
    ideal = analyze_adc_endpoint_nonlinearity(adc_measurement(ideal_codes, vin_diff_v=inputs))
    assert ideal.endpoint_lsb_v == pytest.approx(0.08, abs=0.01)
    assert ideal.missing_codes == 0

    nonlinear_codes = np.rint(
        np.linspace(0.0, 15.0, len(inputs)) + 0.6 * np.sin(np.pi * np.linspace(0.0, 15.0, len(inputs)) / 15.0)
    )
    nonlinear = analyze_adc_endpoint_nonlinearity(adc_measurement(nonlinear_codes, vin_diff_v=inputs))
    assert nonlinear.maximum_abs_inl > 0.05


def test_decision_paths_keep_every_conversion() -> None:
    msmt = adc_measurement([5, 5, 3])
    bout = np.asarray(
        [
            [1, 0, 1] + [0] * 14,
            [1, 0, 1] + [0] * 14,
            [0, 1, 1] + [0] * 14,
        ],
        dtype=np.uint8,
    )
    object.__setattr__(msmt, "bout", bout)
    paths = analyze_adc_decision_paths(msmt)

    assert paths.estimate_dout.shape == (3, 18)
    np.testing.assert_array_equal(paths.final_dout, (5, 5, 3))


def test_cdac_settling_aligns_saved_stages_and_removes_static_levels() -> None:
    measurement = adc_cdac_settling_measurement()
    result = analyze_adc_cdac_settling(measurement)
    assert result.comp_latch_p_v is not None
    assert result.comp_latch_n_v is not None
    np.testing.assert_allclose(result.comp_latch_p_v, 1.2 - 0.5 * result.clk_comp_v)
    np.testing.assert_allclose(result.comp_latch_n_v, 1.2 - 0.8 * result.clk_comp_v)

    assert result.stage_index.tolist() == [0, 7, 15]
    assert result.cycle_index.tolist() == [0, 7, 15]
    assert result.conversion_index.tolist() == [0, 0, 0]
    assert result.time_s[0] == pytest.approx(-0.05e-9, abs=15e-12)
    assert result.time_s[-1] == pytest.approx(1.35e-9, abs=15e-12)
    assert 0.0 in result.time_s
    assert result.clk_comp_v.shape == (3, len(result.time_s))
    settled = (result.time_s >= 0.85e-9) & (result.time_s <= 0.97e-9)
    np.testing.assert_allclose(np.median(result.vdac_p_settling_error_v[:, settled], axis=1), 0.0, atol=1e-6)
    np.testing.assert_allclose(np.median(result.vdac_n_settling_error_v[:, settled], axis=1), 0.0, atol=1e-6)
    np.testing.assert_allclose(result.vdac_p_settling_s, result.vdac_n_settling_s, atol=10e-12)
    assert np.all((result.vdac_p_settling_s > 0.1e-9) & (result.vdac_p_settling_s < 0.3e-9))


def test_cdac_settling_keeps_final_pulse_cut_by_record_boundary() -> None:
    measurement = adc_cdac_settling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    selected = wave.time_s < 16.7e-9
    shortened = replace(
        wave,
        time_s=wave.time_s[selected],
        v={name: values[:, selected] for name, values in wave.v.items()},
        i={name: values[:, selected] for name, values in wave.i.items()},
    )
    result = analyze_adc_cdac_settling(replace(measurement, wave=shortened))
    assert result.stage_index.tolist() == [0, 7, 15]
    assert 1.1e-9 < result.time_s[-1] < 1.21e-9
    assert np.all(result.clk_comp_v[:, -1] > 0.6)


def test_cdac_settling_rejects_missing_reset_inside_record() -> None:
    measurement = adc_cdac_settling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    comp = wave.v["clk_comp"].copy()
    comp[:, wave.time_s >= 16.5e-9] = 1.2
    with pytest.raises(ValueError, match="cycle 16.*reset edge"):
        analyze_adc_cdac_settling(replace(measurement, wave=replace(wave, v={**wave.v, "clk_comp": comp})))


def test_decision_paths_normalize_redundant_raw_weights() -> None:
    """Keep the running estimate in nominal ADC LSB for non-4095 raw sums."""

    msmt = adc_measurement([4095])
    weights = (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)
    object.__setattr__(
        msmt,
        "param",
        replace(
            msmt.param,
            tb=replace(
                msmt.param.tb,
                dut=AdcParams(
                    adc_bits=12,
                    cdac=CapArrayConfig(n_dac=11, n_extra=5, weights=weights),
                ),
            ),
        ),
    )
    object.__setattr__(msmt, "bout", np.ones((1, 17), dtype=np.uint8))

    paths = analyze_adc_decision_paths(msmt)

    assert paths.estimate_dout[0, 0] == pytest.approx(2047.5)
    assert paths.estimate_dout[0, -1] == pytest.approx(4095.0)


def test_sequence_logic_timing_uses_the_full_crossing_span() -> None:
    comp = "".join("1" if index in (0, 2, 6, 18) else "0" for index in range(24))
    logic = "".join("1" if index in (1, 3, 7) else "0" for index in range(24))
    # Four COMP rises span 18 symbols: the average period is six rather
    # than the median spacing of four. LOGIC remains one symbol after COMP.
    sequence = AdcSequence(init="1" + "0" * 23, samp="0" * 24, comp=comp, logic=logic)
    assert sequence.logic_timing == pytest.approx((6.0, 1.0))


def test_dynamic_results_retain_rate_frequency_and_logic_phase() -> None:
    measurements = []
    for index, frequency_hz in enumerate((1_000.0, 5_000.0)):
        sample_rate_hz = 100_000.0
        time_s = np.arange(2_048) / sample_rate_hz
        samples = np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * frequency_hz * time_s))
        measurements.append(
            adc_measurement(
                samples,
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=frequency_hz,
                logic_phase_delay_symbols=index - 1,
            )
        )
    results = [analyze_adc_dynamic(measurement) for measurement in measurements]
    np.testing.assert_allclose([result.input_frequency_hz for result in results], (1_000.0, 5_000.0))
    np.testing.assert_allclose([result.sample_rate_hz for result in results], (100_000.0, 100_000.0))
    np.testing.assert_array_equal([result.logic_phase_delay_symbols for result in results], (-1, 0))
    assert all(result.index is None for result in results)
    assert all(result.input_referred_noise_rms_v > 0 for result in results)


def test_power_sweep_uses_active_smu_readbacks() -> None:
    measurements = []
    for adc_index, sample_rate_hz in ((0, 100_000.0), (1, 200_000.0)):
        readbacks = {}
        for rail, current_a in (("vdd_a", 2e-6), ("vdd_d", 40e-6), ("vdd_dac", 20e-6)):
            readbacks[f"{rail}_measured_voltage_v"] = 1.2
            readbacks[f"{rail}_measured_current_a"] = 0.5 * current_a
            readbacks[f"{rail}_active_average_current_a"] = current_a
            readbacks[f"{rail}_active_average_power_w"] = 1.2 * current_a
            if adc_index == 1:
                readbacks[f"{rail}_static_average_power_w"] = 0.25 * 1.2 * current_a
        measurements.append(
            adc_measurement(
                [100, 101, 102] * 3,
                sample_rate_hz=sample_rate_hz,
                observed_adc=adc_index,
                readbacks=readbacks,
            )
        )

    power = [analyze_adc_power(measurement) for measurement in measurements]

    assert [result.index for result in power] == [0, 1]
    np.testing.assert_allclose([result.vdd_d_static_power_w for result in power], (24e-6, 12e-6))
    np.testing.assert_allclose([result.vdd_d_dynamic_power_w for result in power], (24e-6, 36e-6))
    np.testing.assert_allclose([result.total_static_power_w for result in power], (37.2e-6, 18.6e-6))
    np.testing.assert_allclose([result.total_dynamic_power_w for result in power], (37.2e-6, 55.8e-6))
    np.testing.assert_allclose([result.total_power_w for result in power], (74.4e-6, 74.4e-6))


def test_power_sweep_extracts_spice_static_from_settled_idle_tail() -> None:
    readbacks = {
        "vdd_a_active_average_power_w": 999.0e-6,
        "vdd_d_active_average_power_w": 999.0e-6,
        "vdd_dac_active_average_power_w": 999.0e-6,
    }
    measurement = adc_measurement(
        [100, 101, 102],
        readbacks=readbacks,
        internal=True,
        waveform_sample_count=201,
    )
    assert measurement.wave is not None
    assert isinstance(measurement, MeasAdc)
    time_s = measurement.wave.time_s
    seq_init_v = np.zeros_like(measurement.wave.v["seq_init"])
    seq_init_v[0, (time_s >= 25.0e-9) & (time_s <= 50.0e-9)] = 1.2
    active_stop_s = 650.0e-9
    rail_currents = {}
    for rail, static_current_a, active_current_a in (
        ("vdd_a", 2.0e-6, 10.0e-6),
        ("vdd_d", 4.0e-6, 20.0e-6),
        ("vdd_dac", 6.0e-6, 30.0e-6),
    ):
        current_a = np.full_like(measurement.wave.v["seq_init"], active_current_a)
        current_a[0, time_s < 25.0e-9] = 100.0e-6
        current_a[0, time_s > active_stop_s] = static_current_a
        rail_currents[rail] = current_a
    measurement = replace(
        measurement,
        wave=replace(measurement.wave, i=rail_currents, v={**measurement.wave.v, "seq_init": seq_init_v}),
    )
    assert measurement.wave is not None

    power = analyze_adc_power(measurement)

    # INIT crosses halfway between 20 and 25 ns. Integrating the linear
    # current segments from 22.5 to 647.5 ns gives these active means.
    expected_active_w = 1.2e-6 * np.asarray((10.09, 20.08, 30.07))
    # The idle samples span 650..995 ns and include half of the 5 ns
    # transition from active to static current, giving a 10/345 correction.
    expected_static_w = 1.2e-6 * np.asarray((2.0, 4.0, 6.0)) * (1.0 + 10.0 / 345.0)
    assert power.index is None
    np.testing.assert_allclose(
        (power.vdd_a_static_power_w, power.vdd_d_static_power_w, power.vdd_dac_static_power_w),
        expected_static_w,
    )
    np.testing.assert_allclose(
        (power.vdd_a_dynamic_power_w, power.vdd_d_dynamic_power_w, power.vdd_dac_dynamic_power_w),
        expected_active_w - expected_static_w,
    )
    assert power.total_power_w == pytest.approx(72.288e-6)
    aligned = analyze_adc_power_waveform(measurement, power=power)
    assert aligned.time_s[0] == pytest.approx(-12.5e-9)


def test_power_sweep_requires_spice_settled_idle_tail() -> None:
    readbacks = {f"{rail}_active_average_power_w": 10.0e-6 for rail in ("vdd_a", "vdd_d", "vdd_dac")}
    measurement = adc_measurement(
        [100, 101, 102],
        readbacks=readbacks,
        internal=True,
        waveform_sample_count=201,
    )
    assert measurement.wave is not None
    assert isinstance(measurement, MeasAdc)
    time_s = measurement.wave.time_s
    seq_init_v = np.zeros_like(measurement.wave.v["seq_init"])
    seq_init_v[0, time_s <= 5.0e-9] = 1.2
    seq_init_v[0, (time_s >= 630.0e-9) & (time_s <= 635.0e-9)] = 1.2
    measurement = replace(measurement, wave=replace(measurement.wave, v={**measurement.wave.v, "seq_init": seq_init_v}))
    assert measurement.wave is not None

    with pytest.raises(ValueError, match="at least two settled-idle samples"):
        analyze_adc_power(measurement)


def test_noise_sweep_uses_active_rate_while_dynamic_uses_true_repeat_rate() -> None:
    """Keep nominal timing sweeps distinct from the waveform sampling interval."""

    low = adc_measurement(
        [100, 101, 100],
        sample_rate_hz=1.0e6,
        logic_phase_delay_symbols=-3,
    )
    high = adc_measurement(
        [100, 102, 101],
        sample_rate_hz=2.0e6,
        logic_phase_delay_symbols=3,
    )

    noise = [analyze_adc_noise(low), analyze_adc_noise(high)]

    # The default pattern has 160 active symbols within a 256-symbol repeat.
    np.testing.assert_allclose([result.active_conversion_rate_hz for result in noise], [1.6e6, 3.2e6])
    np.testing.assert_allclose([result.comparator_time_percent for result in noise], [12.5, 87.5])
    assert noise[0].input_lsb_v == pytest.approx(1.2 / 4095)
    for result in noise:
        assert result.input_referred_noise_rms_v == pytest.approx(result.std_dout * 1.2 / 4095)
        assert math.isnan(result.pretrigger_vin_diff_mean_v)
        assert math.isnan(result.pretrigger_vin_diff_noise_rms_v)
        # Behavioral captures have no physical readout to distrust.
        assert result.readout_valid


def test_noise_sweep_does_not_treat_constant_codes_as_zero_noise() -> None:
    noise = analyze_adc_noise(adc_measurement([100, 100, 100, 100], sample_rate_hz=1.0e6))

    assert noise.std_dout == 0.0
    assert math.isnan(noise.input_referred_noise_rms_v)
    assert not noise.noise_valid
    assert math.isnan(noise.enob_bits)


def test_noise_sweep_preserves_failed_and_recovered_points() -> None:
    recovered = adc_measurement(
        [100, 101, 100, 101],
        sample_rate_hz=3.0e6,
    )
    settled = adc_measurement(
        [100, 101, 100, 101],
        sample_rate_hz=1.0e6,
    )
    failed = adc_measurement(
        [80, 120, 80, 120],
        sample_rate_hz=2.0e6,
    )

    noise = [analyze_adc_noise(measurement) for measurement in (recovered, settled, failed)]

    assert all(result.noise_valid for result in noise)
    np.testing.assert_allclose([result.sample_rate_hz for result in noise], [3e6, 1e6, 2e6])


@pytest.mark.parametrize("offsets", ((-0.05,), (-0.05, -0.15, 0.05)))
def test_noise_sweep_extracts_pretrigger_input_noise(offsets) -> None:
    msmt = adc_measurement([100, 101, 100])
    assert msmt.wave is not None
    time_s = np.asarray((-2.0, -1.0, 0.0, 1.0)) * 1e-9
    vin_diff_v = np.asarray(offsets)[:, None] + np.asarray((-0.001, 0.001, 0.01, -0.01))
    msmt = replace(
        msmt,
        wave=replace(
            msmt.wave,
            record_index=np.arange(len(offsets)),
            time_s=time_s,
            v={
                **msmt.wave.v,
                "vin_diff": vin_diff_v,
                "seq_comp": np.zeros_like(vin_diff_v),
                "seq_logic": np.zeros_like(vin_diff_v),
                "comp_out": np.zeros_like(vin_diff_v),
            },
        ),
    )
    assert msmt.wave is not None

    noise = analyze_adc_noise(msmt)

    assert noise.pretrigger_vin_diff_mean_v == pytest.approx(-0.05)
    assert noise.pretrigger_vin_diff_noise_rms_v == pytest.approx(0.001)


def test_noise_sweep_accepts_measurement_without_scope_waveform() -> None:
    msmt = replace(adc_measurement([100, 101, 100]), wave=None)

    noise = analyze_adc_noise(msmt)

    assert noise.std_dout == pytest.approx(np.std([100, 101, 100]))
    assert math.isnan(noise.pretrigger_vin_diff_mean_v)
    assert math.isnan(noise.pretrigger_vin_diff_noise_rms_v)


def test_physical_noise_readout_requires_valid_scope_and_fastrx_readbacks() -> None:
    good = {"scope_fastrx_comparison_valid": True, "scope_fastrx_bit_mismatches": 0, "fastrx_lost_count": 0}
    measurement = adc_measurement([100, 101, 100], observed_adc=0, readbacks=good)
    physical = replace(measurement, info=replace(measurement.info, backend="physical"))
    assert analyze_adc_noise(physical).readout_valid
    for name, value in (("scope_fastrx_bit_mismatches", 2), ("fastrx_lost_count", 1)):
        bad = replace(physical, info=replace(physical.info, readbacks={**good, name: value}))
        assert not analyze_adc_noise(bad).readout_valid


def test_operating_conditions_judge_constant_shifted_and_readout_rows() -> None:
    sequences = timing_sequences[:3]
    measurements = []
    for rate_index, sample_rate_hz in enumerate((1.0e6, 2.0e6)):
        for sequence_index, sequence in enumerate(sequences):
            dout = [1000, 1001, 1002, 1001] * 25
            if (rate_index, sequence_index) == (1, 1):
                dout = [1000] * 100
            if (rate_index, sequence_index) == (1, 2):
                dout = [1100, 1101, 1102, 1101] * 25
            base = adc_measurement(dout, sample_rate_hz=sample_rate_hz, observed_adc=3)
            measurements.append(
                replace(base, param=replace(base.param, tb=replace(base.param.tb, **sequence.as_tb_fields())))
            )
    noise = [analyze_adc_noise(measurement) for measurement in measurements]
    result = analyze_adc_operating_conditions(measurements, noise=list(reversed(noise)))

    assert (result.group, result.index) == (7, 3)
    assert result.reference_mean_dout == pytest.approx(1001.0)
    np.testing.assert_array_equal(result.constant, (False, False, False, False, True, False))
    np.testing.assert_array_equal(result.shifted, (False, False, False, False, False, True))
    np.testing.assert_array_equal(result.plausible, (True, True, True, True, False, False))
    with pytest.raises(ValueError, match="no noise result matches"):
        analyze_adc_operating_conditions(measurements, noise=noise[:-1])


@pytest.mark.parametrize(
    ("samples", "sample_rate_hz", "input_frequency_hz", "message"),
    [
        ([1] * 7, 1_000.0, 10.0, "at least eight"),
        ([1] * 8, 0.0, 10.0, "sample_rate_hz"),
        ([1] * 8, 1_000.0, 500.0, "Nyquist"),
    ],
)
def test_dynamic_analysis_rejects_invalid_records(
    samples: list[int],
    sample_rate_hz: float,
    input_frequency_hz: float,
    message: str,
) -> None:
    msmt = adc_measurement(samples)
    msmt = replace(
        msmt,
        param=replace(
            msmt.param,
            tb=replace(
                msmt.param.tb,
                symbol_rate=sample_rate_hz * len(msmt.param.tb.seq_init_pattern),
                vin_diff=h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
            ),
        ),
    )
    with pytest.raises(ValueError, match=message):
        analyze_adc_dynamic(msmt)


def adc_timing_measurement() -> MeasAdc:
    """Seventeen known decisions and a next-cycle tail at 10 ps resolution."""
    base = adc_measurement([2048], internal=True)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    time = np.arange(3631, dtype=np.float64) * 10e-12
    t = time / 1e-9
    signals = {name: np.zeros_like(t) for name in base.wave.v}

    def pulse(edges, width):
        return np.asarray([any(edge <= value < edge + width for edge in edges) for value in t], dtype=float) * 1.2

    starts = 1 + 2 * np.arange(17)
    signals.update(
        seq_init=pulse([0.2, 35], 0.5),
        seq_logic=pulse([0.4, *list(starts[:16] + 1), 35.2], 0.1),
        clk_comp=pulse([*starts, 36], 0.8),
        seq_comp=pulse([*starts, 36], 0.8),
    )
    bits = np.array([1, 1, *[index % 2 for index in range(15)]])
    signals["comp.latch_p"] = np.full_like(t, 1.2)
    signals["comp.latch_n"] = np.full_like(t, 1.2)
    sr = np.zeros_like(t)
    for decision, start in enumerate(starts):
        active = (t >= start + 0.25) & (t < start + 0.8)
        signals["comp.latch_p"][active] = bits[decision] * 1.2
        signals["comp.latch_n"][active] = (1 - bits[decision]) * 1.2
        sr[t >= start + 0.4] = bits[decision] * 1.2
        if decision == 16:
            continue
        for side, state in (("p", 1 - bits[decision]), ("n", bits[decision])):
            for diff in (False, True):
                suffix = "_diff" if diff else ""
                signals[f"dac_state_{side}{suffix}[{decision}]"] = np.where(t >= start + 1.1, state * 1.2, 0)
                target = bool(state) ^ (diff and bool(base.param.dac_diffcaps))
                signals[f"dac_botplate_{side}{suffix}[{decision}]"] = np.where(t >= start + 1.2, target * 1.2, 0)
    signals.update(
        comp_out_p=sr, comp_out_n=1.2 - sr, comp_out=sr, vdac_p=np.full_like(t, 0.7), vdac_n=np.full_like(t, 0.7)
    )
    return replace(
        base,
        wave=Wave(
            record_index=np.array([0]), time_s=time, v={name: values[None, :] for name, values in signals.items()}
        ),
    )


def test_adc_timing_closure_uses_typed_wave_records_and_preserves_codes(tmp_path) -> None:
    from flow.analysis.adc import analyze_adc_timing_closure
    from flow.analysis.io import read_measurement, write_measurement
    from flow.analysis.types import AnalysisAdcTimingClosure

    measurement = adc_timing_measurement()
    path = tmp_path / "measurement.h5"
    write_measurement(path, measurement)
    loaded = read_measurement(path)
    assert isinstance(loaded, MeasAdc)
    before = loaded.bout.copy()
    result = analyze_adc_timing_closure(loaded)
    assert isinstance(result, AnalysisAdcTimingClosure)
    assert np.all(result.passed)
    np.testing.assert_array_equal(result.decision_index, np.arange(17))
    assert result.required_logic_setup_s == result.required_cdac_setup_s == 200e-12
    assert result.sample_interval_s == pytest.approx(10e-12)
    np.testing.assert_allclose(result.logic_setup_s[np.r_[0, 2:16]], 0.595e-9, atol=11e-12)
    assert result.logic_setup_s[1] > 0.7e-9
    assert np.all(result.cdac_setup_s[:16] > 0.7e-9)
    # Consecutive equal decisions do not require a new SR transition.
    assert result.sr_stable_s[1] == pytest.approx(3e-9)
    assert result.logic_ready[-1] and not result.cdac_applicable[-1]
    assert np.isnan(result.cdac_setup_s[-1])
    np.testing.assert_array_equal(loaded.bout, before)


def test_adc_record_analyses_ignore_high_comp_at_record_boundary() -> None:
    from flow.analysis.adc import analyze_adc_comparator_response, analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    clock = measurement.wave.v["clk_comp"].copy()
    clock[0, 0] = 1.2  # Tail of the preceding conversion, not a new COMP edge.
    voltage = {**measurement.wave.v, "clk_comp": clock}
    measurement = replace(measurement, wave=replace(measurement.wave, v=voltage))
    assert measurement.wave is not None

    timing = analyze_adc_timing_closure(measurement)
    response = analyze_adc_comparator_response(measurement)
    np.testing.assert_array_equal(timing.decision_index, np.arange(17))
    np.testing.assert_array_equal(response.decision_index, np.arange(17))


def test_adc_comparator_response_requires_both_xc_rails_and_times_one_sr_output() -> None:
    from flow.analysis.adc import analyze_adc_comparator_response

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


@pytest.mark.parametrize(
    "failure", ("wrong_sr", "late_sr", "unresolved", "late_internal", "ringing_cdac", "wrong_state", "missing_reset")
)
def test_adc_timing_closure_flags_failed_handoffs(failure) -> None:
    from flow.analysis.adc import analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    time = measurement.wave.time_s
    signals = {name: value.copy() for name, value in measurement.wave.v.items()}
    if failure in ("wrong_sr", "late_sr"):
        stop = 2.01e-9 if failure == "wrong_sr" else 1.9e-9
        signals["comp_out_p"][0, time < stop] = 0
        signals["comp_out_n"][0, time < stop] = 1.2
    elif failure == "unresolved":
        active = (time >= 1e-9) & (time < 1.81e-9)
        signals["comp.latch_p"][0, active] = 0.61
        signals["comp.latch_n"][0, active] = 0.60
    elif failure == "late_internal":
        # The final tendency reverses after LOGIC; a first crossing would miss this.
        active = (time >= 1.25e-9) & (time < 2.15e-9)
        signals["clk_comp"][0, active] = 1.2
        signals["comp.latch_p"][0, active] = 0
        signals["comp.latch_n"][0, active] = 1.2
        final = (time >= 2.05e-9) & (time < 2.15e-9)
        signals["comp.latch_p"][0, final] = 1.2
        signals["comp.latch_n"][0, final] = 0
    elif failure == "ringing_cdac":
        signals["vdac_p"][0, (time >= 2.8e-9) & (time < 2.9e-9)] += 0.01
    elif failure == "wrong_state":
        signals["dac_state_n[0]"][:] = 0
    else:
        signals["clk_comp"][0, (time >= 1.8e-9) & (time < 3e-9)] = 1.2
        # Preserve the next rise while hiding only the internal reset with an initial-high record:
        # the absent pulse boundary is a malformed decision sequence, and is rejected explicitly.
        with pytest.raises(ValueError, match="COMP rises; expected"):
            analyze_adc_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
        return
    result = analyze_adc_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
    assert not result.passed[0]
    assert np.all(result.passed[1:])
    if failure == "wrong_sr":
        assert not result.sr_matches_at_logic[0]
    elif failure in ("late_sr", "late_internal"):
        assert result.logic_setup_s[0] < 200e-12
    elif failure == "unresolved":
        assert result.internal_final_diff_v[0] == pytest.approx(0.01)
        assert np.isnan(result.internal_stable_s[0])
    else:
        assert not result.cdac_ready[0]


def test_adc_timing_closure_reports_unknown_when_final_tail_is_missing() -> None:
    from flow.analysis.adc import analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    selected = wave.time_s <= 34e-9
    result = analyze_adc_timing_closure(
        replace(
            measurement,
            wave=replace(
                wave, time_s=wave.time_s[selected], v={name: values[:, selected] for name, values in wave.v.items()}
            ),
        )
    )
    assert np.all(result.passed[:16])
    assert np.isnan(result.logic_setup_s[-1])
    assert not result.passed[-1]


def test_adc_timing_closure_requires_saved_internals() -> None:
    from flow.analysis.adc import analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    signals = dict(measurement.wave.v)
    del signals["comp.latch_n"]
    with pytest.raises(ValueError, match="comp.latch_n"):
        analyze_adc_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))


def test_adc_timing_closure_preserves_saved_conversion_indices() -> None:
    from flow.analysis.adc import analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    result = analyze_adc_timing_closure(
        replace(
            measurement,
            conversion_index=np.array([37]),
            wave=replace(measurement.wave, record_index=np.array([37])),
        )
    )
    np.testing.assert_array_equal(result.conversion_index, np.full(17, 37))
    assert np.all(result.passed)


def test_adc_timing_closure_marks_missing_logic_unknown_instead_of_guessing() -> None:
    from flow.analysis.adc import analyze_adc_timing_closure

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    signals = {name: values.copy() for name, values in measurement.wave.v.items()}
    signals["seq_logic"][0, (measurement.wave.time_s >= 1.9e-9) & (measurement.wave.time_s <= 2.2e-9)] = 0
    result = analyze_adc_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
    assert np.isnan(result.logic_rise_s[0])
    assert not result.passed[0]
    assert np.all(result.passed[1:])


def test_dynamic_sine_fit_recovers_signal_with_frequency_error() -> None:
    """The fit refines a programmed frequency that is off by 0.6%."""

    sample_rate = 1000.0
    time_s = np.arange(1000) / sample_rate
    samples = np.rint(2_000.0 + 1_500.0 * np.sin(2.0 * np.pi * 41.25 * time_s + 0.4))
    result = analyze_adc_dynamic(adc_measurement(samples, sample_rate_hz=sample_rate, input_frequency_hz=41.0))
    assert result.fitted_frequency_hz == pytest.approx(41.25, abs=1e-4)
    assert result.amplitude_dout == pytest.approx(1_500.0, rel=1e-4)
    assert result.phase_rad == pytest.approx(0.4, abs=1e-3)
    assert result.offset_dout == pytest.approx(2_000.0, abs=0.05)
    # Only rounding to whole codes remains in the residual.
    assert result.residual_rms_dout == pytest.approx(1 / np.sqrt(12), rel=0.1)
    np.testing.assert_allclose(result.time_s, time_s)
    np.testing.assert_allclose(result.fitted_dout + result.residual_dout, samples)
