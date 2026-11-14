"""The charge-sensitive amplifier's analysis results (``flow.csa.analysis``), pure data: its response
to each injected charge, its output noise, its response and noise over the supply; and the record's
metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPulse(Analysis):
    """Amplifier response at each injected charge (a charge run each), the smallest charge first.

    ``vout_v`` is the output before the charge arrives (its baseline), ``amplitude_v`` its largest
    excursion from there (away from the input device's rail), ``peaking_time_s`` the time from the
    injection step's middle to the excursion's maximum (refined between the strobes by the parabola
    through the largest sample and its neighbours) and ``rise_time_s`` the leading edge's 10-90 %.
    ``tot_s`` is the time over a threshold ``threshold_v``, half the smallest charge's amplitude
    from the baseline, ``return_s`` the time from the injection until the output stays within 5 %
    of the amplitude of the baseline, ``idd_a`` the supply current's average before the charge at
    supply ``vdd_v``. A reset amplifier holds the charge until its reset: its peaking time (the
    maximum of a held level) is NaN, and so are its time over threshold and return, which never
    come; so are another amplifier's where its tail outlasts the record, and every timing where the
    output does not respond (no positive amplitude). ``time_s`` and ``pulse_v`` hold each
    response's excursion from the baseline, one row per charge, from the injection on, on the
    smallest charge's samples to the shortest record's end.
    """

    # not in the reference texts: the charge a step through the injection capacitor puts on the
    # input, C_inj times the step (detector read-out)
    charge_c: np.ndarray
    # [Razavi-Analog] Fig. 3.4, p. 48: the supply voltage V_DD
    vdd_v: np.ndarray
    # [Razavi-Analog] Fig. 3.4, p. 48: the output voltage V_out, here at rest before the charge
    vout_v: np.ndarray
    # not in the reference texts: the pulse's amplitude, its largest excursion from the baseline
    # (detector read-out)
    amplitude_v: np.ndarray
    # not in the reference texts: the peaking time, from the injection step's middle to the
    # pulse's maximum (detector read-out)
    peaking_time_s: np.ndarray
    # [Baker] Eq. (2.26), p. 49; Fig. 10.9, p. 333: the rise time, from 10 % to 90 % of the
    # excursion to the peak
    rise_time_s: np.ndarray
    # not in the reference texts: the discriminator threshold, half the smallest charge's amplitude
    # above the baseline (the block's choice)
    threshold_v: np.ndarray
    # not in the reference texts: the time over threshold, from the pulse's rising to its falling
    # crossing of the threshold (detector read-out)
    tot_s: np.ndarray
    # [Razavi-Analog] Fig. 11.48, p. 496: settling into a band about the final value; here from the
    # injection until the pulse stays within 5 % of its amplitude of the baseline
    return_s: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: the supply current I_DD, here its average at rest
    idd_a: np.ndarray
    # not in the reference texts: the figures' time axis, from the injection step's middle
    time_s: np.ndarray
    # not in the reference texts: each charge's excursion from the baseline on time_s, one row a
    # charge (the figures' responses)
    pulse_v: np.ndarray

    @property
    def charge_gain_v_per_c(self) -> np.ndarray:
        # not in the reference texts: the charge gain, the amplitude over the injected charge
        # (detector read-out); [Razavi-Analog] Fig. 13.7, p. 542: ideally 1/C_f, the charge moving
        # onto the feedback capacitor, less by Eq. (11.17), p. 497 for a finite open-loop gain
        return self.amplitude_v / self.charge_c


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisNoise(Analysis):
    """Amplifier noise at each noise run: ``vout_v`` and ``idd_a`` the operating point's output and
    supply current, ``noise_out_v`` the output's rms noise over the sweep (no shaper),
    ``charge_gain_v_per_c`` the response to the smallest charge per coulomb, ``enc_electrons``
    their quotient in electrons (NaN for no gain); ``noise_out_v_per_rthz`` the density over
    ``frequency_hz``, one row per run."""

    # [Razavi-Analog] Fig. 3.4, p. 48: the output voltage V_out at the operating point
    vout_v: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: the supply current I_DD at the operating point
    idd_a: np.ndarray
    # [Razavi-Analog] Eq. (7.20), p. 229: output noise, rms, the density squared integrated over
    # the band, its square root
    noise_out_v: np.ndarray
    # not in the reference texts: the charge gain at the smallest charge (AnalysisPulse's)
    charge_gain_v_per_c: np.ndarray
    # not in the reference texts: the equivalent noise charge, the output rms noise over the charge
    # gain in electrons, unshaped at the amplifier's output (detector read-out)
    enc_electrons: np.ndarray
    # [Razavi-Analog] Fig. 7.26, p. 234: the frequency f a noise spectrum is drawn over
    frequency_hz: np.ndarray
    # [Razavi-Analog] Sec. 7.1.1, pp. 221-223: noise spectral density, the square root of the PSD
    noise_out_v_per_rthz: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSupply(Analysis):
    """Amplifier response to the smallest charge, and its noise, at each supply (``vdd_v``, in the
    order of the runs): its charge gain, peaking time, ENC (NaN without a noise run) and the power
    the supply delivers before the charge."""

    # [Razavi-Analog] Fig. 3.4, p. 48: the supply voltage V_DD
    vdd_v: np.ndarray
    # not in the reference texts: the charge gain at the smallest charge (detector read-out)
    charge_gain_v_per_c: np.ndarray
    # not in the reference texts: the peaking time at the smallest charge (detector read-out)
    peaking_time_s: np.ndarray
    # not in the reference texts: the equivalent noise charge, unshaped (detector read-out)
    enc_electrons: np.ndarray
    # [Razavi-PLL] Sec. 3.3.3, p. 74: power, the supply current times V_DD
    power_w: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A charge-sensitive amplifier's numbers (``analysis.metrics``): from the response to the
    smallest charge its charge gain, peaking and rise time, baseline and power; the amplitude's
    nonlinearity over the charges, at the largest charge its time over threshold and return to the
    baseline; the output noise and ENC; and over the supply the smallest gain, the largest peaking
    time and ENC."""

    # not in the reference texts: the charge gain, the amplitude over the injected charge
    charge_gain_v_per_c: float = metric("Output amplitude over the injected charge, smallest charge", "higher")
    # not in the reference texts: from the injection to the pulse's peak (detector read-out)
    peaking_time_s: float = metric("From the injection to the peak, smallest charge", "lower")
    # [Baker] Eq. (2.26), p. 49: the rise time, 10 % to 90 %
    rise_time_s: float = metric("Leading edge 10-90 %, smallest charge", "lower")
    # [Razavi-Analog] Fig. 3.4, p. 48: the output voltage V_out, at rest
    vout_v: float = metric("Output baseline before the charge", "none")
    # [Razavi-Analog] Fig. 14.4, p. 578: nonlinearity, the largest deviation of the amplitude from
    # the straight line through the end points (zero charge and the largest) over the largest
    # amplitude, a fraction
    nonlinearity: float = metric(
        "Largest deviation of the amplitude from the end-point line, 0 to 2 fC, over the 2 fC amplitude", "lower"
    )
    # not in the reference texts: the time over threshold (detector read-out), at the largest charge
    tot_2fc_s: float = metric("Time over threshold at 2 fC", "none")
    # [Razavi-Analog] Fig. 11.48, p. 496: settling into a band about the final value, here 5 % of
    # the amplitude about the baseline, at the largest charge
    return_2fc_s: float = metric("Return to within 5 % of the baseline at 2 fC", "lower")
    # [Razavi-PLL] Sec. 3.3.3, p. 74: power, the supply current times V_DD
    power_w: float = metric("Supply power before the charge", "lower")
    # [Razavi-Analog] Eq. (7.20), p. 229: output noise, rms
    noise_out_v: float = metric("Output rms noise, 1 Hz to 1 THz", "lower")
    # not in the reference texts: the equivalent noise charge, the output rms noise over the charge
    # gain in electrons, unshaped at the amplifier's output, FSTART_HZ to FSTOP_HZ (detector read-out)
    enc_electrons: float = metric(
        "Equivalent noise charge: the output rms noise, 1 Hz to 1 THz, no shaper, over the 0.25 fC charge gain", "lower"
    )
    # not in the reference texts: the charge gain, its least over the supply
    charge_gain_min_supply_v_per_c: float = metric("Smallest charge gain over the supply", "higher")
    # not in the reference texts: the peaking time, its largest over the supply
    peaking_time_max_supply_s: float = metric("Largest peaking time over the supply", "lower")
    # not in the reference texts: the equivalent noise charge, its largest over the supply
    enc_max_supply_electrons: float = metric("Largest equivalent noise charge over the supply", "lower")
