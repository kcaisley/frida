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

    ``vout_v`` is the output before the charge arrives (its baseline), ``amplitude_v`` its peak
    excursion from there (away from the input device's rail), ``peaking_time_s`` the time from the
    injection step's middle to that peak and ``rise_time_s`` the leading edge's 10-90 %.
    ``tot_s`` is the time over a threshold ``threshold_v``, half the smallest charge's amplitude
    from the baseline, ``return_s`` the time from the injection until the output stays within 5 %
    of the amplitude of the baseline, ``idd_a`` the supply current's average before the charge at
    supply ``vdd_v``. A reset amplifier holds the charge until its reset: its peaking time (the
    maximum of a held level) is NaN, and so are its time over threshold and return, which never
    come; so are another amplifier's where its tail outlasts the record. ``time_s`` and ``pulse_v``
    hold each response's excursion from the baseline, one row per charge, from the injection on.
    """

    # not in the reference texts: the charge a step through the injection capacitor puts on the input
    charge_c: np.ndarray
    # [Razavi-Analog] Fig. 3.4, p. 48: supply voltage and output voltage
    vdd_v: np.ndarray
    vout_v: np.ndarray
    amplitude_v: np.ndarray
    # not in the reference texts: from the injection to the pulse's peak (detector read-out)
    peaking_time_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: output rise time (10-90 %)
    rise_time_s: np.ndarray
    threshold_v: np.ndarray
    # not in the reference texts: how long the pulse stays past the threshold (detector read-out)
    tot_s: np.ndarray
    # not in the reference texts: from the injection until the pulse stays within 5 % of its
    # amplitude of the baseline (the calculator's settlingTime on the trailing edge)
    return_s: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current
    idd_a: np.ndarray
    time_s: np.ndarray
    pulse_v: np.ndarray

    @property
    def charge_gain_v_per_c(self) -> np.ndarray:
        # not in the reference texts: output amplitude over the injected charge (detector read-out)
        return self.amplitude_v / self.charge_c


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisNoise(Analysis):
    """Amplifier noise at each noise run: ``vout_v`` and ``idd_a`` the operating point's output and
    supply current, ``noise_out_v`` the output's rms noise over the sweep, ``charge_gain_v_per_c``
    the response to the smallest charge per coulomb, ``enc_electrons`` their quotient in electrons;
    ``noise_out_v_per_rthz`` the density over ``frequency_hz``, one row per run."""

    vout_v: np.ndarray
    idd_a: np.ndarray
    # [Razavi-Analog] Eq. (7.20), p. 229: output noise, rms
    noise_out_v: np.ndarray
    charge_gain_v_per_c: np.ndarray
    # not in the reference texts: output rms noise over the charge gain, in electrons (detector read-out)
    enc_electrons: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: frequency
    frequency_hz: np.ndarray
    # [Razavi-Analog] Sec. 7.1.1, p. 223: noise spectral density
    noise_out_v_per_rthz: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSupply(Analysis):
    """Amplifier response to the smallest charge, and its noise, at each supply (``vdd_v``, in the
    order of the runs): its charge gain, peaking time, ENC (NaN without a noise run) and the power
    the supply delivers before the charge."""

    vdd_v: np.ndarray
    charge_gain_v_per_c: np.ndarray
    peaking_time_s: np.ndarray
    enc_electrons: np.ndarray
    # [Razavi-PLL] Sec. 3.3.2, p. 74: power dissipation
    power_w: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A charge-sensitive amplifier's numbers (``analysis.metrics``): from the response to the
    smallest charge its charge gain, peaking and rise time, baseline and power; the gain's linearity
    to the largest charge, where also its time over threshold and return to the baseline; the
    output noise and ENC; and over the supply the smallest gain, the largest peaking time and ENC."""

    charge_gain_v_per_c: float = metric("Output amplitude over the injected charge, smallest charge", "higher")
    peaking_time_s: float = metric("From the injection to the peak, smallest charge", "lower")
    rise_time_s: float = metric("Leading edge 10-90 %, smallest charge", "lower")
    vout_v: float = metric("Output baseline before the charge", "none")
    # not in the reference texts: the charge gain at the largest charge over that at the smallest
    linearity: float = metric("Charge gain at 2 fC over that at 0.25 fC", "none")
    tot_2fc_s: float = metric("Time over threshold at 2 fC", "none")
    return_2fc_s: float = metric("Return to within 5 % of the baseline at 2 fC", "lower")
    power_w: float = metric("Supply power before the charge", "lower")
    noise_out_v: float = metric("Output rms noise, 1 Hz to 1 GHz", "lower")
    enc_electrons: float = metric("Equivalent noise charge", "lower")
    charge_gain_min_supply_v_per_c: float = metric("Smallest charge gain over the supply", "higher")
    peaking_time_max_supply_s: float = metric("Largest peaking time over the supply", "lower")
    enc_max_supply_electrons: float = metric("Largest equivalent noise charge over the supply", "lower")
