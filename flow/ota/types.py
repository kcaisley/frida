"""The amplifier's analysis results (``flow.ota.analysis``), pure data: its small-signal figures
and its input-referred noise at each measured point (a run over the input common mode or the
supply), its unity-gain step and sine responses, and the record's metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisAc(Analysis):
    """Amplifier small-signal figures at each measured point.

    ``gain_db`` and ``phase_deg`` hold the response, one row per point and one column per
    ``frequency_hz``. ``gain_dc_db`` is the gain at the lowest frequency,
    ``unity_gain_bandwidth_hz`` the first unity-gain crossing (``unityGainFreq``),
    ``phase_margin_deg`` 180 degrees plus the phase there relative to the lowest frequency
    (``phaseMargin``); NaN where the gain never reaches unity. ``bandwidth_hz`` is the -3 dB
    frequency (``bandwidth``), ``gbw_hz`` the low-frequency gain times it (``gainBwProd``),
    ``gain_margin_db`` how far below unity the gain is where the phase has turned 180 degrees
    (``gainMargin``, positive when stable; NaN for a response that never turns so far).
    ``psrr_db`` and ``cmrr_db`` (per point and frequency) are the differential gain at ``outp``
    over the gain there from the supply and from the input common mode, and ``psrr_dc_db`` and
    ``cmrr_dc_db`` their values at the lowest frequency. Both are taken at ``outp``, the only
    output of a single-ended amplifier and one side of a differential one, whose differential
    output rejects both perfectly without mismatch. ``idd_a`` is the supply current and
    ``vout_cm_v`` the outputs' average at the operating point. Every figure is NaN where the ideal
    common-mode feedback drives vbp beyond the rails: no real feedback holds the output common
    mode there (a folded cascode at the lowest supplies).
    """

    vdd_v: np.ndarray
    vin_cm_v: np.ndarray
    frequency_hz: np.ndarray
    gain_db: np.ndarray
    phase_deg: np.ndarray
    gain_dc_db: np.ndarray
    unity_gain_bandwidth_hz: np.ndarray
    phase_margin_deg: np.ndarray
    bandwidth_hz: np.ndarray
    gbw_hz: np.ndarray
    gain_margin_db: np.ndarray
    psrr_db: np.ndarray
    cmrr_db: np.ndarray
    psrr_dc_db: np.ndarray
    cmrr_dc_db: np.ndarray
    idd_a: np.ndarray
    vout_cm_v: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: power dissipation
        return self.vdd_v * self.idd_a


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisNoise(Analysis):
    """Amplifier input-referred noise at each measured point.

    ``noise_in_v_per_rthz`` is the output noise density over the differential gain, one row per
    point and one column per ``frequency_hz``; ``noise_in_1mhz_v_per_rthz`` its value at the sweep
    frequency nearest 1 MHz (``spot_frequency_hz``); ``noise_in_v`` its RMS from the lowest
    frequency to the unity-gain bandwidth (NaN where there is none). Points the AC result leaves
    out, their load bias beyond the rails, are NaN.
    """

    vdd_v: np.ndarray
    vin_cm_v: np.ndarray
    frequency_hz: np.ndarray
    noise_in_v_per_rthz: np.ndarray
    spot_frequency_hz: float
    noise_in_1mhz_v_per_rthz: np.ndarray
    noise_in_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSlew(Analysis):
    """Amplifier unity-gain step response at each step point.

    ``vout_low_v`` and ``vout_high_v`` are ``outp``'s levels just before the rising and falling
    input steps, ``slew_rate_rise_v_per_s`` and ``slew_rate_fall_v_per_s`` its 10-90 % slopes
    between them (``slewrate``; the fall's negative), ``settling_rise_s`` and ``settling_fall_s``
    the time from each input edge until it stays within 1 % of the step (``settlingTime``; NaN
    where it never does, as when the loop rings on), ``overshoot_rise`` and ``overshoot_fall`` how
    far it passes the final level, a fraction of the step (``overshoot``), ``idd_a`` the supply
    current's average over the period. The edges are NaN where the output moves less than a tenth
    of the step. ``vout_v`` is ``outp`` over ``time_s``, one row per point.
    """

    vin_cm_v: np.ndarray
    vin_step_v: np.ndarray
    vout_low_v: np.ndarray
    vout_high_v: np.ndarray
    slew_rate_rise_v_per_s: np.ndarray
    slew_rate_fall_v_per_s: np.ndarray
    settling_rise_s: np.ndarray
    settling_fall_s: np.ndarray
    overshoot_rise: np.ndarray
    overshoot_fall: np.ndarray
    idd_a: np.ndarray
    time_s: np.ndarray
    vout_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDistortion(Analysis):
    """Amplifier unity-gain sine response at each sine point: ``thd_db`` and ``sndr_db`` of ``outp``
    over the whole periods after the first two (``spectrumMeas``, harmonics to the fifth), and its
    fundamental's ``gain`` over the input's amplitude; ``frequency_hz`` and ``spectrum_db`` its
    spectrum relative to the input's amplitude, one row per point."""

    vin_cm_v: np.ndarray
    vin_amplitude_v: np.ndarray
    vin_frequency_hz: np.ndarray
    thd_db: np.ndarray
    sndr_db: np.ndarray
    gain: np.ndarray
    frequency_hz: np.ndarray
    spectrum_db: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """An amplifier's numbers (``analysis.metrics``): its small-signal figures, power and noise at
    mid-supply input, the input common-mode range and the lowest low-frequency gain over the
    supply; and, of a single-ended amplifier in unity gain, its slew rates, settling and
    distortion (None for a differential one, which has no unity-gain bench)."""

    gain_dc_db: float = metric("Low-frequency gain", "higher")
    unity_gain_bandwidth_hz: float = metric("Unity-gain bandwidth", "higher")
    phase_margin_deg: float = metric("Phase margin of the open-loop response", "higher")
    gain_margin_db: float = metric("Gain margin of the open-loop response", "higher")
    bandwidth_hz: float = metric("-3 dB bandwidth of the open-loop response", "none")
    psrr_dc_db: float = metric("PSRR at outp at the lowest frequency", "higher")
    cmrr_dc_db: float = metric("CMRR at outp at the lowest frequency", "higher")
    power_w: float = metric("Supply power at the operating point", "lower")
    vout_cm_v: float = metric("Output common mode at the operating point", "none")
    noise_in_1mhz_v_per_rthz: float = metric("Input-referred noise density at 1 MHz", "lower")
    noise_in_v: float = metric("Input-referred noise, RMS to the unity-gain bandwidth", "lower")
    vin_cm_range_v: float = metric("Input common-mode range keeping the gain within 6 dB", "higher")
    gain_dc_min_supply_db: float = metric("Lowest low-frequency gain over the supply", "higher")
    slew_rate_rise_v_per_s: float | None = metric("Unity-gain slew rate, output rising", "higher", None)
    slew_rate_fall_v_per_s: float | None = metric("Unity-gain slew rate, output falling", "higher", None)
    settling_s: float | None = metric("Unity-gain 1 % settling time, the slower edge", "lower", None)
    thd_db: float | None = metric("Unity-gain total harmonic distortion", "lower", None)
