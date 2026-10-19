"""Amplifier analyses and plots on synthetic responses of known gain, peaking and discharge."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.csa.analysis import ELEMENTARY_CHARGE_C, MeasCsa, MeasCsaNoise, analyze_csa_noise, analyze_csa_pulse
from flow.csa.plots import plot_csa_charge, plot_csa_noise, plot_csa_pulse
from flow.csa.sim import CsaTbParams
from flow.csa.subckt import CASES

GAIN_V_PER_C = 100e-3 / 1e-15
PEAKING_S = 10e-9
SLOPE_V_PER_S = 2e6  # 10 nA out of 5 fF


def _pulse(charge: float, case: str = "krum") -> MeasCsa:
    """An output rising linearly from 0.5 V over 10 ns from the injection step's middle to 100 mV/fC
    of charge, then discharging at 2 V/µs back to the baseline (up for an NMOS input, down for a
    PMOS one), drawing 4 µA."""
    params = CsaTbParams(csa=CASES[case], charge_c=charge)
    time_s = np.arange(0.0, float(params.stop_time_s), 50e-12)
    since = time_s - float(params.inject_time_s) - float(params.transition_time_s) / 2
    amplitude = GAIN_V_PER_C * charge
    pulse = np.clip(np.minimum(amplitude * since / PEAKING_S, amplitude - SLOPE_V_PER_S * (since - PEAKING_S)), 0, None)
    pulse = np.where(since < 0, 0.0, pulse)
    sign = 1.0 if case != "krum_pmos" else -1.0
    return MeasCsa(
        group=None,
        index=None,
        dut=params.csa,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"out": (0.5 + sign * pulse)[None, :]},
            i={"vdd": np.full((1, len(time_s)), 4e-6)},
        ),
    )


def _noise(density_v_rthz: float) -> MeasCsaNoise:
    """A white output noise density from 1 Hz to 1 GHz."""
    params = CsaTbParams(csa=CASES["krum"], charge_c=0.0)
    frequency_hz = np.logspace(0, 9, 91)
    return MeasCsaNoise(
        group=None,
        index=None,
        dut=params.csa,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC),
            readbacks={"op_supply_current_a": 4e-6, "op_out_v": 0.5, "op_inp_v": 0.3},
        ),
        param=params,
        frequency_hz=frequency_hz,
        output_noise_v_rthz=np.full_like(frequency_hz, density_v_rthz),
    )


@pytest.mark.parametrize("case", ("krum", "krum_pmos"))
def test_amplitude_peaking_threshold_and_return(case) -> None:
    charges = (2e-15, 0.5e-15, 1e-15)
    pulse = analyze_csa_pulse([_pulse(charge, case) for charge in charges])
    assert pulse.charge_c == pytest.approx([0.5e-15, 1e-15, 2e-15])
    assert pulse.baseline_v == pytest.approx([0.5] * 3)
    assert pulse.amplitude_v == pytest.approx([0.05, 0.1, 0.2], rel=1e-6)
    assert pulse.gain_v_per_c == pytest.approx([GAIN_V_PER_C] * 3, rel=1e-6)
    assert pulse.peaking_time_s == pytest.approx([PEAKING_S] * 3, rel=1e-6)
    assert pulse.rise_time_s == pytest.approx([0.8 * PEAKING_S] * 3, rel=1e-3)
    # half the smallest amplitude: 25 mV, crossed on the way up and on the discharge
    threshold, amplitude = 0.025, np.asarray([0.05, 0.1, 0.2])
    assert pulse.threshold_v == pytest.approx([threshold] * 3)
    tot = PEAKING_S * (1 - threshold / amplitude) + (amplitude - threshold) / SLOPE_V_PER_S
    assert pulse.tot_s == pytest.approx(tot, rel=1e-3)
    # back within 5 % of the amplitude
    assert pulse.return_time_s == pytest.approx(PEAKING_S + 0.95 * amplitude / SLOPE_V_PER_S, rel=1e-3)
    assert pulse.supply_current_a == pytest.approx([4e-6] * 3)
    assert pulse.pulse_v.shape == (3, len(pulse.time_s))


def test_a_held_charge_has_no_peak_threshold_time_or_return() -> None:
    held = _pulse(1e-15)
    output = held.wave.v["out"][0]
    peak = int(np.argmax(output))
    output[peak:] = output[peak]
    pulse = analyze_csa_pulse([held])
    assert pulse.amplitude_v[0] == pytest.approx(0.1, rel=1e-6)
    assert np.isnan(pulse.peaking_time_s[0]) and np.isnan(pulse.tot_s[0]) and np.isnan(pulse.return_time_s[0])
    assert pulse.rise_time_s[0] == pytest.approx(0.8 * PEAKING_S, rel=1e-3)


def test_enc_is_the_rms_noise_over_the_smallest_charge_gain() -> None:
    pulse = analyze_csa_pulse([_pulse(charge) for charge in (0.5e-15, 1e-15)])
    noise = analyze_csa_noise([_noise(1e-7)], pulse)
    rms = 1e-7 * np.sqrt(1e9 - 1)
    assert noise.noise_rms_v[0] == pytest.approx(rms, rel=1e-6)
    assert noise.enc_electrons[0] == pytest.approx(rms / GAIN_V_PER_C / ELEMENTARY_CHARGE_C, rel=1e-6)
    with pytest.raises(ValueError, match="does not match"):
        analyze_csa_noise([_noise(1e-7)], analyze_csa_pulse([_pulse(1e-15, "krum_pmos")]))


def test_comparison_plots_render(tmp_path: Path) -> None:
    pulse = analyze_csa_pulse([_pulse(charge) for charge in (0.5e-15, 1e-15, 2e-15)])
    noise = analyze_csa_noise([_noise(1e-7)], pulse)
    paths = (
        *plot_csa_pulse([pulse], labels=["a"], output_path=tmp_path / "pulse"),
        *plot_csa_charge([pulse], labels=["a"], output_path=tmp_path / "charge"),
        *plot_csa_noise([noise], labels=["a"], output_path=tmp_path / "noise"),
    )
    assert paths and all(path.exists() for path in paths)
