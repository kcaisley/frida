"""Software-only tests for normalized waveform and block analyses."""

from __future__ import annotations

import numpy as np
import pytest

from flow.analysis.blocks import analyze_cdac, analyze_comparator, analyze_sampler
from flow.analysis.measure import (
    analyze_charge_injection,
    analyze_crossings,
    analyze_delay,
    analyze_edge_samples,
    analyze_offset,
    analyze_power,
    analyze_settling,
    analyze_spectrum,
    analyze_statistics,
)
from flow.analysis.models import (
    AnalysisKind,
    AnalysisRequest,
    AnalysisSpec,
    BackendKind,
    BlockKind,
    DataColumn,
    DataTable,
    RunData,
    StatisticsSettings,
    WaveformSettings,
)


def waveform_run(
    run_id: str = "waveform",
    block: BlockKind = BlockKind.GENERIC,
    parameters=None,
    **columns,
) -> RunData:
    return RunData(
        run_id,
        BackendKind.SPICE,
        block,
        (
            DataTable(
                "waveforms",
                tuple(
                    DataColumn(
                        name,
                        np.asarray(values),
                        "s" if name == "time_s" else ("A" if name.endswith("_a") else "V"),
                    )
                    for name, values in columns.items()
                ),
            ),
        ),
        parameters=parameters or {},
    )


def request(
    run: RunData,
    kind: AnalysisKind,
    settings,
    *,
    name: str = "measurement",
) -> AnalysisRequest:
    return AnalysisRequest(
        AnalysisSpec(name, kind, (run.run_id,), settings),
        runs=(run,),
    )


def test_crossings_delay_and_edge_samples_interpolate_events() -> None:
    time_s = np.linspace(0.0, 4.0, 401)
    clock = np.sin(2.0 * np.pi * time_s)
    response = np.sin(2.0 * np.pi * (time_s - 0.1))
    run = waveform_run(time_s=time_s, clock_v=clock, response_v=response)

    crossings = analyze_crossings(
        request(
            run,
            AnalysisKind.CROSSINGS,
            WaveformSettings(signal_columns=("clock_v",), thresholds=(0.0,)),
        )
    )
    assert crossings.metric("crossing_count") == 3
    assert crossings.table("crossings").column("crossing_axis")[0] == pytest.approx(1.0)

    delay = analyze_delay(
        request(
            run,
            AnalysisKind.DELAY,
            WaveformSettings(
                signal_columns=("clock_v", "response_v"),
                thresholds=(0.0, 0.0),
            ),
        )
    )
    assert delay.metric("delay") == pytest.approx(0.1, abs=1e-3)

    sampled = analyze_edge_samples(
        request(
            run,
            AnalysisKind.EDGE_SAMPLES,
            WaveformSettings(
                signal_columns=("clock_v", "response_v"),
                thresholds=(0.0,),
                sample_fraction=0.5,
            ),
        )
    )
    assert sampled.metric("sample_count") == 2


def test_spectrum_recovers_dc_and_coherent_tone() -> None:
    sample_rate_hz = 1.0e9
    time_s = np.arange(10_000) / sample_rate_hz
    signal = 0.6 + 0.5 * np.sin(2.0 * np.pi * 20.0e6 * time_s)
    run = waveform_run(time_s=time_s, signal_v=signal)
    result = analyze_spectrum(
        request(
            run,
            AnalysisKind.SPECTRUM,
            WaveformSettings(signal_columns=("signal_v",), window="none"),
        )
    )
    spectrum = result.table("spectrum")
    frequency_hz = spectrum.column("frequency_hz")
    amplitude = spectrum.column("signal_v_amplitude")
    tone_bin = int(np.argmin(np.abs(frequency_hz - 20.0e6)))
    assert amplitude[0] == pytest.approx(0.6, rel=1e-6)
    assert amplitude[tone_bin] == pytest.approx(0.5, rel=1e-6)


def test_settling_power_offset_charge_and_statistics() -> None:
    time_s = np.linspace(0.0, 10.0, 1_001)
    settled = 1.0 - np.exp(-time_s)
    input_difference = np.linspace(-0.1, 0.1, len(time_s))
    output_difference = input_difference - 0.01
    current = np.full(len(time_s), 1e-3)
    run = waveform_run(
        time_s=time_s,
        settled_v=settled,
        input_difference_v=input_difference,
        output_difference_v=output_difference,
        supply_current_a=current,
    )
    settling = analyze_settling(
        request(
            run,
            AnalysisKind.SETTLING,
            WaveformSettings(signal_columns=("settled_v",), target=1.0, tolerance=0.01),
        )
    )
    assert 4.0 < settling.metric("settling_axis") < 6.0

    power = analyze_power(
        request(
            run,
            AnalysisKind.POWER,
            WaveformSettings(signal_columns=("supply_current_a",), target=1.2),
        )
    )
    assert power.metric("average_power_w") == pytest.approx(1.2e-3)

    offset = analyze_offset(
        request(
            run,
            AnalysisKind.OFFSET,
            WaveformSettings(signal_columns=("input_difference_v", "output_difference_v")),
        )
    )
    assert offset.metric("input_offset") == pytest.approx(0.01)

    charge = analyze_charge_injection(
        request(
            run,
            AnalysisKind.CHARGE_INJECTION,
            WaveformSettings(signal_columns=("settled_v",), thresholds=(1.0, 2.0)),
        )
    )
    assert charge.metric("charge_injection") == pytest.approx(
        (1.0 - np.exp(-2.0)) - (1.0 - np.exp(-1.0)),
        rel=1e-4,
    )

    stats = analyze_statistics(
        request(
            run,
            AnalysisKind.STATISTICS,
            StatisticsSettings("input_difference_v", histogram_bins=10),
        )
    )
    assert stats.metric("count") == len(time_s)
    assert stats.metric("mean") == pytest.approx(0.0, abs=1e-12)
    assert len(stats.table("histogram")) == 10


def test_comparator_analysis_uses_shared_delay_offset_and_power() -> None:
    time_s = np.linspace(0.0, 20e-9, 2_001)
    vin_diff = np.linspace(-10e-3, 10e-3, len(time_s))
    clock = np.where(time_s >= 5e-9, 1.2, 0.0)
    response = np.where(time_s >= 7e-9, np.sign(vin_diff + 1e-3) * 1.0, 0.0)
    run = waveform_run(
        "comparator",
        BlockKind.COMPARATOR,
        parameters={"supply_v": 1.2},
        time_s=time_s,
        vin_p_v=0.6 + vin_diff / 2.0,
        vin_n_v=0.6 - vin_diff / 2.0,
        vout_p_v=0.6 + response / 2.0,
        vout_n_v=0.6 - response / 2.0,
        clock_v=clock,
        supply_current_a=np.full(len(time_s), 10e-6),
    )
    result = analyze_comparator(
        request(
            run,
            AnalysisKind.COMPARATOR,
            WaveformSettings(tolerance=0.01),
            name="comparator_summary",
        )
    )
    assert result.metric("input_offset_v") == pytest.approx(-1e-3, abs=2e-5)
    assert result.metric("clock_to_decision_delay_s") == pytest.approx(2e-9, abs=2e-11)
    assert result.metric("average_power_w") == pytest.approx(12e-6)


def test_cdac_and_sampler_analyses_share_result_contract() -> None:
    codes = np.arange(8)
    cdac = waveform_run(
        "cdac",
        BlockKind.CDAC,
        parameters={"supply_v": 1.2},
        code=codes,
        output_v=0.1 * codes,
        supply_current_a=np.full(len(codes), 2e-6),
    )
    cdac_result = analyze_cdac(
        request(cdac, AnalysisKind.CDAC, WaveformSettings(), name="cdac_summary")
    )
    assert cdac_result.metric("lsb_v") == pytest.approx(0.1)
    assert cdac_result.metric("maximum_abs_dnl") < 1e-12
    assert cdac_result.metric("average_power_w") == pytest.approx(2.4e-6)

    time_s = np.linspace(0.0, 2e-6, 2_001)
    input_v = 0.6 + 0.1 * np.sin(2.0 * np.pi * 1e6 * time_s)
    output_v = input_v + 1e-3
    clock = np.sin(2.0 * np.pi * 1e6 * time_s)
    sampler = waveform_run(
        "sampler",
        BlockKind.SAMPLER,
        parameters={"supply_v": 1.2},
        time_s=time_s,
        input_v=input_v,
        output_v=output_v,
        clock_v=clock,
        supply_current_a=np.full(len(time_s), 1e-6),
    )
    sampler_result = analyze_sampler(
        request(
            sampler,
            AnalysisKind.SAMPLER,
            WaveformSettings(target=float(output_v[-1]), tolerance=0.1),
            name="sampler_summary",
        )
    )
    assert sampler_result.metric("rms_sampling_error_v") == pytest.approx(1e-3)
    assert sampler_result.metric("sampling_noise_rms_v") < 1e-15
    assert sampler_result.metric("average_power_w") == pytest.approx(1.2e-6)
