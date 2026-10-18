"""OTA analysis and plots on synthetic responses of known gain, bandwidth, phase margin, slew and distortion."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.ota.analysis import (
    MeasOta,
    MeasOtaTran,
    analyze_ota_ac,
    analyze_ota_distortion,
    analyze_ota_noise,
    analyze_ota_slew,
)
from flow.ota.plots import (
    plot_ota_bode,
    plot_ota_common_mode,
    plot_ota_distortion,
    plot_ota_noise,
    plot_ota_rejection,
    plot_ota_slew,
    plot_ota_supply,
)
from flow.ota.sim import OtaTbParams
from flow.ota.subckt import CASES


def _two_pole(
    gain: float,
    pole_hz: float,
    second_hz: float,
    *,
    vdd: float = 1.2,
    vcm: float = 0.6,
    vbp: float = 0.5,
    third_hz: float | None = None,
) -> MeasOta:
    """An amplifier of DC gain ``gain`` and poles at ``pole_hz`` and ``second_hz`` (and ``third_hz``),
    its input noise a white 10 nV/sqrt(Hz), its load bias at ``vbp``; at outp half its gain, the
    supply passing a tenth and the common mode a hundredth."""
    frequency_hz = np.logspace(3, 11, 161)
    response = gain / ((1 + 1j * frequency_hz / pole_hz) * (1 + 1j * frequency_hz / second_hz))
    if third_hz is not None:
        response = response / (1 + 1j * frequency_hz / third_hz)
    params = OtaTbParams(ota=CASES["five_t"], vdd=vdd, vcm=vcm)
    return MeasOta(
        group=None,
        index=None,
        dut=params.ota,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC),
            readbacks={"op_supply_current_a": 50e-6, "op_outp_v": 0.6, "op_vbp_v": vbp},
        ),
        param=params,
        frequency_hz=frequency_hz,
        gain_v_per_v=np.abs(response),
        phase_deg=np.degrees(np.unwrap(np.angle(response))),
        output_noise_v_rthz=10e-9 * np.abs(response),
        outp_gain_v_per_v=np.abs(response) / 2,
        common_mode_gain_v_per_v=np.full_like(frequency_hz, 0.01),
        supply_gain_v_per_v=np.full_like(frequency_hz, 0.1),
    )


def test_gain_bandwidth_and_phase_margin_of_a_two_pole_amplifier() -> None:
    result = analyze_ota_ac([_two_pole(100.0, 1e6, 1e9)])
    # unity gain near the gain-bandwidth product; both poles' phase there sets the margin
    assert result.dc_gain_db[0] == pytest.approx(40.0, abs=0.01)
    assert result.ugbw_hz[0] == pytest.approx(99.5e6, rel=0.01)
    expected = 180 - np.degrees(np.arctan(result.ugbw_hz[0] / 1e6) + np.arctan(result.ugbw_hz[0] / 1e9))
    assert result.phase_margin_deg[0] == pytest.approx(expected, abs=0.3)
    assert result.bandwidth_hz[0] == pytest.approx(1e6, rel=0.01)
    assert result.gbw_hz[0] == pytest.approx(100e6, rel=0.01)
    assert np.isnan(result.gain_margin_db[0])  # two poles never turn the phase 180°
    # outp: half the gain (34 dB) over a tenth from the supply and a hundredth from the common mode
    assert result.low_psrr_db[0] == pytest.approx(20 * np.log10(50 / 0.1), abs=0.01)
    assert result.low_cmrr_db[0] == pytest.approx(20 * np.log10(50 / 0.01), abs=0.01)
    assert result.psrr_db.shape == result.gain_db.shape
    three = analyze_ota_ac([_two_pole(1000.0, 1e5, 1e7, third_hz=2e7)])
    assert three.gain_margin_db[0] < 0  # three close poles: the loop gain exceeds unity where the phase turns 180°
    assert result.power_w[0] == pytest.approx(1.2 * 50e-6)
    assert result.output_cm_v[0] == pytest.approx(0.6)
    below_unity = analyze_ota_ac([_two_pole(0.5, 1e6, 1e9)])
    assert np.isnan(below_unity.ugbw_hz[0]) and np.isnan(below_unity.phase_margin_deg[0])
    # a load bias the feedback drove below ground: no figure, nor any noise, at that point
    measurements = [_two_pole(100.0, 1e6, 1e9), _two_pole(100.0, 1e6, 1e9, vcm=0.5, vbp=-4.0)]
    held = analyze_ota_ac(measurements)
    assert np.isfinite(held.dc_gain_db[0]) and np.isnan(held.dc_gain_db[1]) and np.isnan(held.power_w[1])
    assert np.all(np.isnan(held.gain_db[1]))
    assert np.isnan(analyze_ota_noise(measurements, ac=held).spot_noise_v_rthz[1])


def test_input_referred_noise_spot_and_integrated() -> None:
    measurements = [_two_pole(100.0, 1e6, 1e9)]
    ac = analyze_ota_ac(measurements)
    noise = analyze_ota_noise(measurements, ac=ac)
    assert noise.input_noise_v_rthz[0] == pytest.approx(10e-9)
    assert noise.spot_frequency_hz == pytest.approx(1e6)
    assert noise.spot_noise_v_rthz[0] == pytest.approx(10e-9)
    # white noise integrated from 1 kHz to the unity-gain bandwidth
    assert noise.integrated_noise_v[0] == pytest.approx(10e-9 * np.sqrt(ac.ugbw_hz[0] - 1e3), rel=0.01)
    with pytest.raises(ValueError, match="same points"):
        analyze_ota_noise([_two_pole(100.0, 1e6, 1e9, vcm=0.5)], ac=ac)


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    vcm = analyze_ota_ac([_two_pole(100.0 * value, 1e6, 1e9, vcm=value) for value in (0.4, 0.6, 0.8)])
    supply = analyze_ota_ac([_two_pole(100.0, 1e6 * value, 1e9, vdd=value) for value in (1.0, 1.2)])
    paths = (
        *plot_ota_bode([vcm], labels=["a"], output_path=tmp_path / "bode"),
        *plot_ota_common_mode([vcm], labels=["a"], output_path=tmp_path / "common_mode"),
        *plot_ota_rejection([vcm], labels=["a"], output_path=tmp_path / "rejection"),
        *plot_ota_supply([supply], labels=["a"], output_path=tmp_path / "supply"),
        *plot_ota_noise(
            [analyze_ota_noise([_two_pole(100.0 * value, 1e6, 1e9, vcm=value) for value in (0.4, 0.6, 0.8)], ac=vcm)],
            labels=["a"],
            output_path=tmp_path / "noise",
        ),
    )
    assert paths and all(path.exists() for path in paths)


def _transient(params: OtaTbParams, time_s: np.ndarray, outp: np.ndarray, inp: np.ndarray) -> MeasOtaTran:
    return MeasOtaTran(
        group=None,
        index=None,
        dut=params.ota,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"inp": inp[None, :], "outp": outp[None, :]},
            i={"vdd": np.full((1, len(time_s)), 30e-6)},
        ),
    )


def _step(rise_v_per_s: float, fall_v_per_s: float) -> MeasOtaTran:
    """An output ramping between 0.45 and 0.75 V at the given slopes after each input edge (20 ns
    period: up at 5 ns, down at 15 ns), drawing 30 µA."""
    params = OtaTbParams(ota=CASES["five_t"], vcm=0.6, step_v=0.3)
    time_s = np.arange(0.0, 20e-9, 5e-12)
    rising = np.clip(0.45 + rise_v_per_s * (time_s - 5e-9), 0.45, 0.75)
    output = np.where(time_s < 15e-9, rising, np.clip(0.75 - fall_v_per_s * (time_s - 15e-9), 0.45, 0.75))
    return _transient(params, time_s, output, np.where((time_s >= 5e-9) & (time_s < 15e-9), 0.75, 0.45))


def _sine(second_harmonic: float) -> MeasOtaTran:
    """A unity-gain output of 0.95 times a 0.12 V, 10 MHz sine with a second harmonic of the given
    fraction of the fundamental."""
    params = OtaTbParams(ota=CASES["five_t"], vcm=0.6, sine_v=0.12, waveform_sample_interval_s=100e-12)
    time_s = np.arange(0.0, params.sine_periods / params.sine_hz, 100e-12)
    phase = 2 * np.pi * params.sine_hz * time_s
    fundamental = 0.95 * 0.12 * np.sin(phase)
    output = 0.6 + fundamental + second_harmonic * 0.95 * 0.12 * np.sin(2 * phase)
    return _transient(params, time_s, output, 0.6 + 0.12 * np.sin(phase))


def test_unity_gain_slew_settling_and_overshoot() -> None:
    slew = analyze_ota_slew([_step(1e9, 2e8)])
    assert slew.low_v[0] == pytest.approx(0.45) and slew.high_v[0] == pytest.approx(0.75)
    assert slew.rise_slew_v_per_s[0] == pytest.approx(1e9, rel=1e-3)
    assert slew.fall_slew_v_per_s[0] == pytest.approx(-2e8, rel=1e-3)
    # within 1 % of the 0.3 V step: 0.297 V of ramp after the edge's middle
    assert slew.rise_settling_s[0] == pytest.approx(0.297e-9, rel=0.02)
    assert slew.fall_settling_s[0] == pytest.approx(1.485e-9, rel=0.01)
    assert slew.rise_overshoot[0] == 0.0 and slew.supply_current_a[0] == pytest.approx(30e-6)
    with pytest.raises(ValueError, match="step bench"):
        analyze_ota_slew([_sine(0.01)])


def test_unity_gain_harmonic_distortion() -> None:
    distortion = analyze_ota_distortion([_sine(0.01)])
    # a second harmonic at 1 % of the fundamental: -40 dB
    assert distortion.thd_db[0] == pytest.approx(-40.0, abs=0.1)
    assert distortion.sndr_db[0] == pytest.approx(40.0, abs=0.1)
    assert distortion.gain_v_per_v[0] == pytest.approx(0.95, rel=1e-3)
    with pytest.raises(ValueError, match="sine bench"):
        analyze_ota_distortion([_step(1e9, 2e8)])


def test_unity_gain_plots_render(tmp_path: Path) -> None:
    step, sine = _step(1e9, 2e8), _sine(0.01)
    paths = (
        *plot_ota_slew([step], [analyze_ota_slew([step])], labels=["a"], output_path=tmp_path / "slew"),
        *plot_ota_distortion([analyze_ota_distortion([sine])], labels=["a"], output_path=tmp_path / "distortion"),
    )
    assert paths and all(path.exists() for path in paths)
