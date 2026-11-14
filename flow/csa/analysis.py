"""The charge-sensitive amplifier's analyses: each from runs' measurements (``flow.pipeline.Meas``)
of its testbench, and the record's metrics. Every figure is a calculator function of
``flow.analysis.calc``.

A charge run holds the output's transient response to one injected charge: the baseline before the
charge (``average``), the peak above it (``ymax``) and the gain per charge, the peaking and 10-90 %
rise time of the leading edge (``xmax``, ``riseTime``), the time over a threshold (``cross``), the
return to the baseline (``settlingTime``) and the supply current before the charge
(``analyze_pulse``). A noise run holds the operating point and the output noise density without
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
        baseline = calc.average(*calc.clip(output, time_s, *rest))
        # the output's excursion: up for an NMOS input, down for a PMOS one
        direction = 1.0 if measurement.dut.input_xtors == MosType.NMOS else -1.0
        pulse_v, pulse_s = calc.clip(direction * (output - baseline), time_s, inject_s, time_s[-1])
        amplitude, peak_s = calc.ymax(pulse_v), calc.xmax(pulse_v, pulse_s)
        leading = calc.clip(pulse_v, pulse_s, inject_s, peak_s) if peak_s > inject_s else (pulse_v[:1], pulse_s[:1])
        trailing = calc.clip(pulse_v, pulse_s, peak_s, pulse_s[-1]) if peak_s < pulse_s[-1] else leading
        returned = calc.settlingTime(*trailing, initial=amplitude, final=0.0, percent_of_step=5.0)
        rows.append(
            (
                float(tb.charge_c),
                float(tb.vdd),
                baseline,
                amplitude,
                np.nan if measurement.dut.feedback == Feedback.RESET else peak_s - inject_s,
                calc.riseTime(*leading, 0.0, amplitude) if len(leading[0]) > 1 else np.nan,
                returned - inject_s,
                calc.average(*calc.clip(measurement.i[Nets.vdd.name], time_s, *rest)),
            )
        )
        pulses.append((pulse_s - inject_s, pulse_v))
    charge, vdd, baseline, amplitude, peaking, rise, returned, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    # one discriminator threshold for every charge: half the smallest charge's amplitude
    threshold = float(amplitude[0]) / 2
    tot = [
        calc.cross(pulse_v, pulse_s, threshold, edge="falling", occurrence=1)
        - calc.cross(pulse_v, pulse_s, threshold, edge="rising", occurrence=1)
        for pulse_s, pulse_v in pulses
    ]
    # the responses on one time grid from the injection: the shortest record's
    length = min(len(pulse_s) for pulse_s, _ in pulses)
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
        time_s=np.asarray(pulses[0][0][:length], dtype=np.float64),
        pulse_v=np.asarray([pulse_v[:length] for _, pulse_v in pulses], dtype=np.float64),
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
    gain = float(pulse.charge_gain_v_per_c[np.argmin(pulse.charge_c)])
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
        enc_electrons=(noise / gain / elementary_charge).astype(np.float64),
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
        power_w=vdd * np.asarray([float(pulse.idd_a[small]) for pulse in pulses]),
    )


def metrics(*, pulse: AnalysisPulse, noise: AnalysisNoise | None = None, supply: AnalysisSupply) -> Metrics:
    """The record's numbers: from the charges' runs (``pulse``) the gain, peaking and rise time,
    baseline and power at the smallest charge, the gain's linearity to the largest, its time over
    threshold and return there; from the noise run (``noise``, None for a reset amplifier: NaN) the
    output's rms noise and the ENC; over the supply (``supply``) the smallest gain and the largest
    peaking time and ENC (NaN where any point is)."""

    # the pulse result's rows by charge: the smallest first
    small, large = 0, len(pulse.charge_c) - 1
    return Metrics(
        charge_gain_v_per_c=float(pulse.charge_gain_v_per_c[small]),
        peaking_time_s=float(pulse.peaking_time_s[small]),
        rise_time_s=float(pulse.rise_time_s[small]),
        vout_v=float(pulse.vout_v[small]),
        linearity=float(pulse.charge_gain_v_per_c[large] / pulse.charge_gain_v_per_c[small]),
        tot_2fc_s=float(pulse.tot_s[large]),
        return_2fc_s=float(pulse.return_s[large]),
        power_w=float(pulse.vdd_v[small] * pulse.idd_a[small]),
        noise_out_v=float(noise.noise_out_v[0]) if noise is not None else np.nan,
        enc_electrons=float(noise.enc_electrons[0]) if noise is not None else np.nan,
        charge_gain_min_supply_v_per_c=float(np.min(supply.charge_gain_v_per_c)),
        peaking_time_max_supply_s=float(np.max(supply.peaking_time_s)),
        enc_max_supply_electrons=float(np.max(supply.enc_electrons)),
    )
