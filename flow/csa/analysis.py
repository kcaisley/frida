"""Typed charge-sensitive amplifier measurements, results, and analyses.

A ``MeasCsa`` is one transient of the amplifier testbench: the output's response to one injected
charge. A ``MeasCsaNoise`` is the output noise density without charge, and the operating point
(supply current, input and output levels) in its run readbacks. The figures are each a calculator function of
``flow.analysis.calc``: the baseline before the charge (``average``), the peak above it (``ymax``)
and the gain per charge, the peaking and 10–90 % rise time of the leading edge (``xmax``,
``riseTime``), the time over a threshold (``cross``), the return to the baseline (``settlingTime``),
the output's rms noise (``rmsNoise``) and over the gain the equivalent noise charge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from hdl21.primitives import MosType
from scipy.constants import elementary_charge

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.csa.sim import CsaTbParams
from flow.csa.subckt import CsaNets, CsaParams, Feedback


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCsa(Meas):
    """Amplifier transient for one injected charge: one record, all in ``wave``."""

    dut: CsaParams
    param: CsaTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCsaNoise(Meas):
    """Amplifier output noise density without charge: one row per frequency."""

    dut: CsaParams
    param: CsaTbParams
    frequency_hz: np.ndarray
    output_noise_v_rthz: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCsaPulse(Analysis):
    """Amplifier response at each injected charge.

    ``baseline_v`` is the output before the charge arrives, ``amplitude_v`` its peak excursion from
    there (away from the input device's rail), ``peaking_time_s`` the time from the injection
    step's middle to that peak and ``rise_time_s`` the leading edge's 10–90 %. ``tot_s`` is the time
    over a threshold half the smallest charge's amplitude from the baseline, ``return_time_s`` the
    time from the injection until the output stays within 5 % of the amplitude of the baseline,
    ``supply_current_a`` the average before the charge. A reset amplifier holds the charge until
    its reset: its peaking time (the maximum of a held level) is NaN, and so are its time over
    threshold and return, which never come; so are another amplifier's where its tail outlasts the
    record. ``time_s`` and ``pulse_v`` hold each response's excursion from the baseline, one row
    per charge, from the injection on.
    """

    charge_c: np.ndarray
    baseline_v: np.ndarray
    amplitude_v: np.ndarray
    peaking_time_s: np.ndarray
    rise_time_s: np.ndarray
    threshold_v: np.ndarray
    tot_s: np.ndarray
    return_time_s: np.ndarray
    supply_current_a: np.ndarray
    time_s: np.ndarray
    pulse_v: np.ndarray

    @property
    def gain_v_per_c(self) -> np.ndarray:
        return self.amplitude_v / self.charge_c


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCsaNoise(Analysis):
    """Amplifier noise: ``noise_rms_v`` the output's rms noise over the sweep, ``gain_v_per_c``
    the response to the smallest charge per coulomb, ``enc_electrons`` their quotient in
    electrons; ``output_noise_v_rthz`` the density over ``frequency_hz``, one row per bench."""

    out_v: np.ndarray
    supply_current_a: np.ndarray
    noise_rms_v: np.ndarray
    gain_v_per_c: np.ndarray
    enc_electrons: np.ndarray
    frequency_hz: np.ndarray
    output_noise_v_rthz: np.ndarray


def analyze_csa_pulse(measurements: Sequence[MeasCsa]) -> AnalysisCsaPulse:
    """Measure the baseline, amplitude, peaking and rise time, time over threshold, return to the
    baseline and supply current at each injected charge."""

    identity = measurement_identity(measurements)
    measurements = sorted(measurements, key=lambda item: float(item.param.charge_c))
    rows, pulses = [], []
    for measurement in measurements:
        wave, tb = measurement.wave, measurement.param
        if wave is None:
            raise ValueError("amplifier pulse requires a waveform record")
        time_s, output = wave.time_s, wave.v[CsaNets.out.name][0]
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
                baseline,
                amplitude,
                np.nan if measurement.dut.feedback == Feedback.RESET else peak_s - inject_s,
                calc.riseTime(*leading, 0.0, amplitude) if len(leading[0]) > 1 else np.nan,
                returned - inject_s,
                calc.average(*calc.clip(wave.i[CsaNets.vdd.name][0], time_s, *rest)),
            )
        )
        pulses.append((pulse_s - inject_s, pulse_v))
    charge, baseline, amplitude, peaking, rise, returned, current = (
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
    return AnalysisCsaPulse(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        charge_c=charge,
        baseline_v=baseline,
        amplitude_v=amplitude,
        peaking_time_s=peaking,
        rise_time_s=rise,
        threshold_v=np.full(len(charge), threshold),
        tot_s=np.asarray(tot, dtype=np.float64),
        return_time_s=returned,
        supply_current_a=current,
        time_s=np.asarray(pulses[0][0][:length], dtype=np.float64),
        pulse_v=np.asarray([pulse_v[:length] for _, pulse_v in pulses], dtype=np.float64),
    )


def analyze_csa_noise(measurements: Sequence[MeasCsaNoise], *, pulse: AnalysisCsaPulse) -> AnalysisCsaNoise:
    """Measure the output's rms noise and, over the response to the smallest charge, the ENC."""

    identity = measurement_identity(measurements)
    check_identity(pulse, identity, name="pulse")
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("amplifier noise requires one frequency sweep for every bench")
    gain = float(pulse.gain_v_per_c[np.argmin(pulse.charge_c)])
    noise = np.asarray([calc.rmsNoise(item.output_noise_v_rthz, frequency_hz) for item in measurements])
    return AnalysisCsaNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        out_v=np.asarray([float(item.info.readbacks["op_out_v"]) for item in measurements], dtype=np.float64),
        supply_current_a=np.asarray(
            [float(item.info.readbacks["op_supply_current_a"]) for item in measurements], dtype=np.float64
        ),
        noise_rms_v=noise.astype(np.float64),
        gain_v_per_c=np.full(len(measurements), gain),
        enc_electrons=(noise / gain / elementary_charge).astype(np.float64),
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        output_noise_v_rthz=np.asarray([item.output_noise_v_rthz for item in measurements], dtype=np.float64),
    )
