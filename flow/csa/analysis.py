"""The charge-sensitive amplifier's analyses: each from runs' measurements (``flow.pipeline.Meas``)
of its testbench, and the record's metrics. Every figure is a calculator function of
``flow.analysis.calc``.

A charge run holds the output's transient response to one injected charge: the baseline before the
charge (``average``), the peak above it (``ymax``) and the gain per charge, the peaking time (the
largest sample, ``xmax``, refined between the strobes by the parabola through it and its
neighbours) and the 10-90 % rise time of the leading edge (``riseTime``), the time over a threshold
(``cross``), the return to the baseline (``settlingTime``) and the supply current before the charge
(``analyze_pulse``); the responses on one grid (``value``). A noise run holds the operating point and the output noise density without
charge: the output's rms noise (``rmsNoise``) and over the smallest charge's gain the equivalent
noise charge (``analyze_noise``). Over the supply, the smallest charge's gain and peaking time,
the ENC and the power (``analyze_supply``).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from hdl21.primitives import MosType
from scipy.constants import elementary_charge

from flow.analysis import calc
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import Feedback, Stimulus
from .subckt import Nets
from .types import AnalysisNoise, AnalysisPulse, AnalysisSupply, Metrics


def _vertex(signal: np.ndarray, axis: np.ndarray, index: int) -> float:
    """Where the parabola through the sample at ``index`` and its two neighbours peaks (they may lie
    unevenly apart): the maximum's time between samples. The sample's own time where it is the
    first or last sample, or not above both neighbours (a flat or held top)."""
    if not 0 < index < len(axis) - 1 or not signal[index] > max(signal[index - 1], signal[index + 1]):
        return float(axis[index])
    (t0, t1, t2), (v0, v1, v2) = axis[index - 1 : index + 2], signal[index - 1 : index + 2]
    # not in the reference texts: three-point parabolic interpolation of a sampled maximum
    num = (t1 - t0) ** 2 * (v1 - v2) - (t1 - t2) ** 2 * (v1 - v0)
    den = (t1 - t0) * (v1 - v2) - (t1 - t2) * (v1 - v0)
    return float(t1 - 0.5 * num / den)


@analysis
def analyze_pulse(measurements: Sequence[Meas]) -> AnalysisPulse:
    """Measure the baseline, amplitude, peaking and rise time, time over threshold, return to the
    baseline and supply current at each injected charge."""

    identity = measurement_identity(measurements)
    if any(item.tb.stimulus is not Stimulus.CHARGE for item in measurements):
        raise ValueError("amplifier pulse requires charge runs")
    measurements = sorted(measurements, key=lambda item: float(item.tb.charge_c))
    rows, pulses = [], []
    for measurement in measurements:
        tb = measurement.tb
        time_s, output = measurement.time_s, measurement.v[Nets.out.name]
        inject_s = float(tb.inject_time_s) + float(tb.transition_time_s) / 2
        # at rest: the second half of the time between the reset's opening and the charge
        rest = (float(tb.reset_time_s) + float(tb.inject_time_s)) / 2, float(tb.inject_time_s)
        # [Razavi-Analog] Fig. 3.4, p. 48: the output voltage V_out, its average at rest
        baseline = calc.average(*calc.clip(output, time_s, *rest))
        # the output's excursion: up for an NMOS input, down for a PMOS one
        direction = 1.0 if measurement.dut.input_xtors == MosType.NMOS else -1.0
        pulse_v, pulse_s = calc.clip(direction * (output - baseline), time_s, inject_s, time_s[-1])
        # not in the reference texts: the amplitude, the excursion's largest sample
        amplitude, sample_s = calc.ymax(pulse_v), calc.xmax(pulse_v, pulse_s)
        # not in the reference texts: the peaking time, from the injection step's middle to the
        # excursion's maximum, refined between the strobes
        peak_s = _vertex(pulse_v, pulse_s, int(np.searchsorted(pulse_s, sample_s)))
        leading = calc.clip(pulse_v, pulse_s, inject_s, sample_s) if sample_s > inject_s else (pulse_v[:1], pulse_s[:1])
        trailing = calc.clip(pulse_v, pulse_s, sample_s, pulse_s[-1]) if sample_s < pulse_s[-1] else leading
        # [Razavi-Analog] Fig. 11.48, p. 496: settling into a band about the final value, here the
        # baseline, the band 5 % of the amplitude
        returned = calc.settlingTime(*trailing, initial=amplitude, final=0.0, percent_of_step=5.0)
        # no response (no excursion away from the rail) has no peak, edge or return
        responds = amplitude > 0
        rows.append(
            (
                float(tb.charge_c),
                float(tb.vdd),
                baseline,
                amplitude,
                peak_s - inject_s if responds and measurement.dut.feedback != Feedback.RESET else np.nan,
                # [Baker] Eq. (2.26), p. 49: rise time, 10 % to 90 % of the excursion
                calc.riseTime(*leading, 0.0, amplitude) if responds and len(leading[0]) > 1 else np.nan,
                returned - inject_s if responds else np.nan,
                # [Razavi-PLL] Example 3.5, p. 70: the supply current I_DD, its average at rest
                calc.average(*calc.clip(measurement.i[Nets.vdd.name], time_s, *rest)),
            )
        )
        pulses.append((pulse_s - inject_s, pulse_v))
    charge, vdd, baseline, amplitude, peaking, rise, returned, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    # not in the reference texts: one discriminator threshold for every charge, half the smallest
    # charge's amplitude; the time over it from its rising to its falling crossing
    threshold = float(amplitude[0]) / 2
    tot = [
        calc.cross(pulse_v, pulse_s, threshold, edge="falling", occurrence=1)
        - calc.cross(pulse_v, pulse_s, threshold, edge="rising", occurrence=1)
        if threshold > 0 and peak > 0
        else np.nan
        for (pulse_s, pulse_v), peak in zip(pulses, amplitude, strict=True)
    ]
    # the responses on one time grid from the injection: the smallest charge's samples up to the
    # shortest record's end, each response read at them
    end_s = min(float(pulse_s[-1]) for pulse_s, _ in pulses)
    grid_s = pulses[0][0][pulses[0][0] <= end_s]
    return AnalysisPulse(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        charge_c=charge,
        vdd_v=vdd,
        vout_v=baseline,
        amplitude_v=amplitude,
        peaking_time_s=peaking,
        rise_time_s=rise,
        threshold_v=np.full(len(charge), threshold),
        tot_s=np.asarray(tot, dtype=np.float64),
        return_s=returned,
        idd_a=current,
        time_s=np.asarray(grid_s, dtype=np.float64),
        pulse_v=np.asarray([calc.value(pulse_v, pulse_s, grid_s) for pulse_s, pulse_v in pulses], dtype=np.float64),
    )


@analysis
def analyze_noise(measurements: Sequence[Meas], *, pulse: AnalysisPulse) -> AnalysisNoise:
    """Measure the output's rms noise and, over the response to the smallest charge, the ENC."""

    identity = measurement_identity(measurements)
    check_identity(pulse, identity, name="pulse")
    if any(item.tb.stimulus is not Stimulus.NOISE for item in measurements):
        raise ValueError("amplifier noise requires noise runs")
    frequency_hz = measurements[0].sweeps["noise"].x
    if any(not np.array_equal(item.sweeps["noise"].x, frequency_hz) for item in measurements):
        raise ValueError("amplifier noise requires one frequency sweep for every bench")
    density = [np.asarray(item.sweeps["noise"].v["out"], dtype=np.float64) for item in measurements]
    # not in the reference texts: the charge gain, the smallest charge's amplitude over its charge
    gain = float(pulse.charge_gain_v_per_c[np.argmin(pulse.charge_c)])
    # [Razavi-Analog] Eq. (7.20), p. 229: the output noise power, the density squared integrated
    # over the band; its square root the rms
    noise = np.asarray([calc.rmsNoise(row, frequency_hz) for row in density])
    operating = [item.sweeps["opdc"] for item in measurements]
    return AnalysisNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vout_v=np.asarray([float(op.v[Nets.out.name][0]) for op in operating], dtype=np.float64),
        idd_a=np.asarray([float(op.i[Nets.vdd.name][0]) for op in operating], dtype=np.float64),
        noise_out_v=noise.astype(np.float64),
        charge_gain_v_per_c=np.full(len(measurements), gain),
        # not in the reference texts: the equivalent noise charge, the output rms noise over the
        # charge gain in electrons, unshaped at the amplifier's output; the integrated output noise
        # over the gain as [Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265 refers a total to the input;
        # none for no gain
        enc_electrons=(noise / gain / elementary_charge if gain > 0 else np.full(len(noise), np.nan)).astype(
            np.float64
        ),
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        noise_out_v_per_rthz=np.asarray(density, dtype=np.float64),
    )


@analysis
def analyze_supply(pulses: Sequence[AnalysisPulse], *, noises: Sequence[AnalysisNoise] | None = None) -> AnalysisSupply:
    """Gather the smallest charge's gain and peaking time, the ENC (``noises``, one a supply in the
    same order; NaN without them) and the power before the charge, at each supply (``pulses``, one
    a supply)."""

    identity = measurement_identity(pulses)
    if noises is not None:
        check_identity(noises, identity, name="noises")
        if len(noises) != len(pulses):
            raise ValueError("amplifier supply sweep requires one noise result a pulse result")
    # each pulse result's smallest charge, its first row
    small = 0
    vdd = np.asarray([float(pulse.vdd_v[small]) for pulse in pulses], dtype=np.float64)
    return AnalysisSupply(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd,
        charge_gain_v_per_c=np.asarray([float(pulse.charge_gain_v_per_c[small]) for pulse in pulses]),
        peaking_time_s=np.asarray([float(pulse.peaking_time_s[small]) for pulse in pulses]),
        enc_electrons=np.asarray(
            [float(noise.enc_electrons[0]) for noise in noises] if noises is not None else [np.nan] * len(pulses),
            dtype=np.float64,
        ),
        # [Razavi-PLL] Sec. 3.3.3, p. 74: power, the supply current times V_DD
        power_w=vdd * np.asarray([float(pulse.idd_a[small]) for pulse in pulses]),
    )


def metrics(*, pulse: AnalysisPulse, noise: AnalysisNoise | None = None, supply: AnalysisSupply) -> Metrics:
    """The record's numbers: from the charges' runs (``pulse``) the gain, peaking and rise time,
    baseline and power at the smallest charge, the amplitude's nonlinearity over every charge, the
    time over threshold and return at the largest; from the noise run (``noise``, None for a reset amplifier: NaN) the
    output's rms noise and the ENC; over the supply (``supply``) the smallest gain and the largest
    peaking time and ENC (NaN where any point is)."""

    # the pulse result's rows by charge: the smallest first
    small, large = 0, len(pulse.charge_c) - 1
    # [Razavi-Analog] Fig. 14.4, p. 578: nonlinearity, the largest deviation from the straight line
    # through the characteristic's end points (no charge, no excursion; the largest charge) over the
    # largest output
    line_v = pulse.amplitude_v[large] * pulse.charge_c / pulse.charge_c[large]
    return Metrics(
        charge_gain_v_per_c=float(pulse.charge_gain_v_per_c[small]),
        peaking_time_s=float(pulse.peaking_time_s[small]),
        rise_time_s=float(pulse.rise_time_s[small]),
        vout_v=float(pulse.vout_v[small]),
        nonlinearity=float(np.max(np.abs(pulse.amplitude_v - line_v)) / pulse.amplitude_v[large]),
        tot_2fc_s=float(pulse.tot_s[large]),
        return_2fc_s=float(pulse.return_s[large]),
        # [Razavi-PLL] Sec. 3.3.3, p. 74: power, the supply current times V_DD
        power_w=float(pulse.vdd_v[small] * pulse.idd_a[small]),
        noise_out_v=float(noise.noise_out_v[0]) if noise is not None else np.nan,
        enc_electrons=float(noise.enc_electrons[0]) if noise is not None else np.nan,
        charge_gain_min_supply_v_per_c=float(np.min(supply.charge_gain_v_per_c)),
        peaking_time_max_supply_s=float(np.max(supply.peaking_time_s)),
        enc_max_supply_electrons=float(np.max(supply.enc_electrons)),
    )
