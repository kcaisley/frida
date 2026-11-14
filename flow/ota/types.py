"""The amplifier's analysis results (``flow.ota.analysis``), pure data: its small-signal figures
and its noise at each measured point (a run at the nominal input common mode, over the input
common mode or over the supply), its input common-mode range, its unity-gain step and sine
responses, and the record's metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisAc(Analysis):
    """Amplifier small-signal figures at each measured point.

    The response is the amplifier's output (``outp``, or ``outp`` minus ``outn``) per volt of
    differential input, its polarity taken off: a two-stage amplifier's, which its second stage
    inverts, is turned over, so that the phase starts from 0 deg at DC and keeps what the lowest
    frequency has already turned. ``gain_db`` and
    ``phase_deg`` hold it, one row per point and one column per ``frequency_hz``; the margins are
    read on that phase. ``gain_margin_db`` is NaN where the phase never reaches -180 deg on the
    sweep (the margin is beyond it), ``unity_gain_bandwidth_hz`` and ``phase_margin_deg`` where
    the gain never reaches unity. ``psrr_db`` and ``cmrr_db`` (and their lowest-frequency values)
    are taken on the amplifier's output: a single-ended amplifier's at ``outp``, with the supply's
    ripple on the amplifier's supply and on the bias network's together (the bias network's
    references stay ideal currents) and the inputs held; a differential output rejects both perfectly without
    mismatch, which the bench has none of, so they are NaN there. ``idd_a`` is the amplifier's own
    supply current (the bias network draws from a supply of its own), ``iss_a`` its tail's current
    (the self-biased amplifier's NMOS tail's), ``vout_v`` a single-ended output's level and
    ``vout_cm_v`` a differential output's common mode (the feedback's target, a check that it
    holds), each NaN for the other kind. ``saturation_margin_v`` is the least V_DS - V_D,sat over
    the amplifier's bench-biased transistors (every one but the self-biased amplifier's tails,
    which its own drains bias), ``saturation_margin_pair_v`` over its tail and input pair alone:
    negative where one is in triode. Every figure is NaN where the ideal common-mode feedback
    saturates, vbp on a rail: it no longer holds the output common mode.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: supply voltage
    vdd_v: np.ndarray
    # [Razavi-Analog] Sec. 4.2, p. 103: input common-mode level
    vin_cm_v: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: frequency
    frequency_hz: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: gain over frequency
    gain_db: np.ndarray
    # [Razavi-Analog] Sec. 10.1, Fig. 10.2, p. 411: phase of the loop transmission (beta = 1)
    phase_deg: np.ndarray
    # [Razavi-Analog] Sec. 6.7.1, p. 204: low-frequency gain
    gain_dc_db: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: unity-gain bandwidth
    unity_gain_bandwidth_hz: np.ndarray
    # [Razavi-Analog] Sec. 10.3, p. 417: phase margin
    phase_margin_deg: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: -3 dB bandwidth
    bandwidth_hz: np.ndarray
    # [Razavi-Analog] Eq. (6.98), p. 204: gain-bandwidth product
    gbw_hz: np.ndarray
    # [Baker] Sec. 24.1, p. 810: gain margin
    gain_margin_db: np.ndarray
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_db: np.ndarray
    # [Razavi-Analog] Eq. (5.42), p. 157: common-mode rejection ratio of a single output
    cmrr_db: np.ndarray
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_dc_db: np.ndarray
    # [Razavi-Analog] Eq. (5.42), p. 157: common-mode rejection ratio of a single output
    cmrr_dc_db: np.ndarray
    # [Baker] Sec. 24.1, p. 805: the amplifier's supply current
    idd_a: np.ndarray
    # [Razavi-Analog] Sec. 4.2, Fig. 4.7, p. 103: tail current
    iss_a: np.ndarray
    # [Razavi-Analog] Fig. 3.4, p. 48: output voltage
    vout_v: np.ndarray
    # [Razavi-Analog] Sec. 4.2, p. 103: output common-mode level
    vout_cm_v: np.ndarray
    # [Razavi-Analog] Example 2.2, p. 18: V_D,sat, the least V_DS of saturation
    # not in the reference texts: the least V_DS - V_D,sat over devices, V_D,sat as the models give it
    saturation_margin_v: np.ndarray
    # [Razavi-Analog] Example 2.2, p. 18: V_D,sat, the least V_DS of saturation
    # not in the reference texts: the least V_DS - V_D,sat over the tail and input pair
    saturation_margin_pair_v: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        """The amplifier's power from its own supply, the bias network's left out."""
        # [Baker] Sec. 24.1, p. 805: power dissipation, VDD times the amplifier's current
        return self.vdd_v * self.idd_a


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRange(Analysis):
    """Amplifier input common-mode range: the span of input common modes about the nominal one
    over which the tail and the input pair stay saturated (``saturation_margin_pair_v`` of the
    common-mode sweep and the nominal point), its ends interpolated where the margin crosses zero.
    An end the margin never crosses lies on a rail (the sweep reaches both); a nominal point out
    of saturation has no range (NaN)."""

    # [Razavi-Analog] Fig. 3.4, p. 48: supply voltage
    vdd_v: float
    # [Razavi-Analog] Sec. 4.2, p. 103: input common-mode level
    vin_cm_v: float
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range, its lower end
    vin_cm_min_v: float
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range, its upper end
    vin_cm_max_v: float
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range, its span
    vin_cm_range_v: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisNoise(Analysis):
    """Amplifier noise at each measured point.

    ``noise_out_v_per_rthz`` is the output noise density and ``noise_in_v_per_rthz`` it over the
    gain, one row per point and one column per ``frequency_hz``; ``noise_in_1mhz_v_per_rthz`` the
    latter at the sweep frequency nearest 1 MHz (``spot_frequency_hz``). ``noise_out_v`` is the
    output noise integrated over the whole sweep, ``noise_in_v`` it over the low-frequency gain.
    Points the AC result leaves out, their feedback saturated on a rail, are NaN.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: supply voltage
    vdd_v: np.ndarray
    # [Razavi-Analog] Sec. 4.2, p. 103: input common-mode level
    vin_cm_v: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: frequency
    frequency_hz: np.ndarray
    # [Razavi-Analog] Sec. 7.1.1, p. 223: noise spectral density
    noise_out_v_per_rthz: np.ndarray
    # [Razavi-Analog] Example 7.11, Eq. (7.45), p. 238: the output noise density over the gain
    noise_in_v_per_rthz: np.ndarray
    # not in the reference texts: the sweep point nearest 1 MHz in log frequency, a reporting convention
    spot_frequency_hz: float
    # [Razavi-Analog] Example 7.11, Eq. (7.45), p. 238: input-referred noise density
    # not in the reference texts: at the sweep point nearest 1 MHz, a reporting convention
    noise_in_1mhz_v_per_rthz: np.ndarray
    # [Razavi-Analog] Sec. 7.8, Eq. (7.145), p. 264: total output noise
    noise_out_v: np.ndarray
    # [Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265: total input-referred noise
    noise_in_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSlew(Analysis):
    """Amplifier unity-gain step response at each step point.

    The input rises at ``vin_rise_s`` and falls at ``vin_fall_s`` between ``vin_low_v`` and
    ``vin_high_v``; ``vout_low_v`` and ``vout_high_v`` are ``outp``'s levels over the last
    twentieth of a period before each. ``slew_rate_rise_v_per_s`` and ``slew_rate_fall_v_per_s``
    are its steepest slopes between its 10 % and 90 % crossings of each edge (the fall's negative),
    the ramp's slope where the edge slews; ``settling_rise_s`` and ``settling_fall_s`` the time from
    each input edge until it stays within 1 % of the step of its final level (``settlingTime``):
    the rise's final level is ``vout_high_v``, the fall's ``vout_low_v``, which the run starts
    from, its last level checked against it. A settling time is NaN where the output never stays
    within the band, or where its final level is not settled itself (outside the band of its own
    average, or drifting more than a quarter of the band, over its window), as when the loop rings
    on or settles slower than the window. ``overshoot_rise`` and ``overshoot_fall`` are how far it
    passes the final level, a fraction of the step (``overshoot``), ``idd_a`` the supply current's
    average over the period. The edges are NaN where the output moves less than a tenth of the
    step. ``vout_v`` is ``outp`` over ``time_s``, one row per point.
    """

    # not in the reference texts: the input's levels over the window before each edge, and its edges' middles
    vin_low_v: np.ndarray
    vin_high_v: np.ndarray
    vin_rise_s: np.ndarray
    vin_fall_s: np.ndarray
    # not in the reference texts: the output's levels over the window before each input edge
    vout_low_v: np.ndarray
    vout_high_v: np.ndarray
    # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: slew rate, the slope of the slewing ramp
    slew_rate_rise_v_per_s: np.ndarray
    slew_rate_fall_v_per_s: np.ndarray
    # [Razavi-Analog] Example 9.2, Eq. (9.11), p. 347: settling time to 1 %
    settling_rise_s: np.ndarray
    settling_fall_s: np.ndarray
    # not in the reference texts: how far a step response passes its final level, a fraction of the
    # step (the calculator's overshoot)
    overshoot_rise: np.ndarray
    overshoot_fall: np.ndarray
    # [Baker] Sec. 24.1, p. 805: the amplifier's supply current
    idd_a: np.ndarray
    # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: the output's step response over time
    time_s: np.ndarray
    vout_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDistortion(Analysis):
    """Amplifier unity-gain sine response at each sine point: ``thd_db`` and ``sndr_db`` of ``outp``
    over the whole periods after the first two (``spectrumMeas``, THD summing the second to the
    seventh harmonic), and its fundamental's ``gain`` over the input's amplitude; ``frequency_hz``
    and ``spectrum_db`` its spectrum relative to the input's amplitude, one row per point. The input carries the sine
    about ``vin_cm_v``. The transient carries no device noise: SNDR is the distortion and the
    numerical residue."""

    # [Razavi-Analog] Sec. 4.2, p. 103: input common-mode level, the sine's middle
    vin_cm_v: np.ndarray
    # [Razavi-Analog] Sec. 14.1.1, p. 579: the input sine's amplitude, at which THD is stated
    vin_amplitude_v: np.ndarray
    # [Razavi-Analog] Sec. 14.1.1, Eq. (14.8), p. 579: the input sine's frequency
    vin_frequency_hz: np.ndarray
    # [Razavi-Analog] Sec. 14.1.1, Eq. (14.10), p. 579: total harmonic distortion, to the seventh harmonic
    thd_db: np.ndarray
    # [Razavi-ADC] Eq. (8.17), p. 152: signal-to-(noise + distortion) ratio
    sndr_db: np.ndarray
    # [Razavi-Analog] Example 9.2, Eqs. (9.5)-(9.7), p. 347: closed-loop gain of the buffer
    gain: np.ndarray
    # not in the reference texts: the calculator's spectrum (spectrumMeas), window-corrected bins in
    # dB of the input's amplitude
    frequency_hz: np.ndarray
    spectrum_db: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """An amplifier's numbers (``analysis.metrics``): its small-signal figures, power and noise at
    the nominal input common mode, its input common-mode range, the lowest low-frequency gain and
    saturation margin over the supply; and, of a single-ended amplifier in unity gain, its slew
    rates, settling and distortion (None for a differential one, which has no unity-gain bench,
    and NaN where the stimulus leaves the input common-mode range)."""

    # [Razavi-Analog] Sec. 6.7.1, p. 204: low-frequency gain
    gain_dc_db: float = metric("Low-frequency gain", "higher")
    # [Razavi-Analog] Fig. 6.43, p. 204: unity-gain bandwidth
    unity_gain_bandwidth_hz: float = metric("Unity-gain bandwidth", "higher")
    # [Razavi-Analog] Sec. 10.3, p. 417: phase margin
    phase_margin_deg: float = metric("Phase margin of the open-loop response", "higher")
    # [Baker] Sec. 24.1, p. 810: gain margin
    gain_margin_db: float | None = metric(
        "Gain margin of the open-loop response (None: the phase never reaches -180 deg on the sweep)", "higher", None
    )
    # [Razavi-Analog] Fig. 6.43, p. 204: -3 dB bandwidth
    bandwidth_hz: float = metric("-3 dB bandwidth of the open-loop response", "none")
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_dc_db: float | None = metric(
        "PSRR of a single-ended output at the lowest frequency, the bias network on the supply too "
        "(None: a differential output's, perfect without mismatch)",
        "higher",
        None,
    )
    # [Razavi-Analog] Eq. (5.42), p. 157: common-mode rejection ratio of a single output
    cmrr_dc_db: float | None = metric(
        "CMRR of a single-ended output at the lowest frequency (None: a differential output's, perfect "
        "without mismatch)",
        "higher",
        None,
    )
    # [Baker] Sec. 24.1, p. 805: power dissipation, VDD times the amplifier's current
    power_w: float = metric("The amplifier's own supply power at the operating point (bias network excluded)", "lower")
    # [Razavi-Analog] Sec. 4.2, Fig. 4.7, p. 103: tail current
    iss_a: float = metric("Tail current at the operating point", "none")
    # [Razavi-Analog] Fig. 3.4, p. 48: output voltage
    vout_v: float | None = metric(
        "A single-ended output's level at the open-loop operating point (None: a differential output's "
        "common mode is the bench's)",
        "none",
        None,
    )
    # [Razavi-Analog] Example 7.11, Eq. (7.45), p. 238: input-referred noise density
    # not in the reference texts: at the sweep point nearest 1 MHz, a reporting convention
    noise_in_1mhz_v_per_rthz: float = metric("Input-referred noise density at 1 MHz", "lower")
    # [Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265: total input-referred noise
    noise_in_v: float = metric("Output noise integrated over the sweep, over the low-frequency gain", "lower")
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range
    vin_cm_min_v: float = metric("Lowest input common mode keeping the tail and input pair saturated", "lower")
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range
    vin_cm_max_v: float = metric("Highest input common mode keeping the tail and input pair saturated", "higher")
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range
    vin_cm_range_v: float = metric("Input common-mode range keeping the tail and input pair saturated", "higher")
    # not in the reference texts: the lowest low-frequency gain over the 90, 100 and 110 % supplies
    gain_dc_min_supply_db: float = metric("Lowest low-frequency gain over the supply", "higher")
    # [Razavi-Analog] Example 2.2, p. 18: V_D,sat, the least V_DS of saturation
    # not in the reference texts: the least V_DS - V_D,sat over devices and the 90, 100 and 110 % supplies
    saturation_margin_min_supply_v: float = metric(
        "Least V_DS - V_D,sat over the bench-biased transistors and the supply (negative: one in triode)", "higher"
    )
    # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: slew rate, the slope of the slewing ramp
    slew_rate_rise_v_per_s: float | None = metric("Unity-gain slew rate, output rising", "higher", None)
    # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: slew rate, the slope of the slewing ramp
    slew_rate_fall_v_per_s: float | None = metric("Unity-gain slew rate, output falling", "higher", None)
    # [Razavi-Analog] Example 9.2, Eq. (9.11), p. 347: settling time to 1 %
    settling_s: float | None = metric("Unity-gain 1 % settling time, the slower edge", "lower", None)
    # [Razavi-Analog] Sec. 14.1.1, Eq. (14.10), p. 579: total harmonic distortion, to the seventh harmonic
    thd_db: float | None = metric(
        "Unity-gain total harmonic distortion, the second to the seventh harmonic", "lower", None
    )
