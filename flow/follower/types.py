"""The follower's analysis results (``flow.follower.analysis``), pure data: at each measured point
(a run over the input level or the supply) its transfer and its output impedance, at each step its
large-signal response; and the record's metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTransfer(Analysis):
    """Follower transfer at each measured point (a run with the AC stimulus on the input).

    ``vdd_v`` is the run's supply, ``vin_v`` its input level, ``vout_v`` the operating-point
    output, ``gain_dc`` the response's magnitude at the lowest frequency, ``bandwidth_hz`` where it
    has fallen 3 dB (``calc.bandwidth``, NaN beyond the sweep),
    ``psrr_dc_db`` that gain over the output's gain from one ripple on the follower's supply and
    the bias references' together (the references ideal currents into diodes on that supply), no
    ripple on ground, ``idd_a`` the operating point's supply current, ``gain_db`` the whole
    response, one row per point and one column per ``frequency_hz``; ``cload_f`` the load the runs
    drive, from an ideal input source (R_S = 0).
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: supply voltage
    vdd_v: np.ndarray
    # [Razavi-Analog] Fig. 3.4, p. 48: input and output voltage
    vin_v: np.ndarray
    vout_v: np.ndarray
    # [Razavi-Analog] Eq. (3.8), p. 48: voltage gain
    gain_dc: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: -3-dB bandwidth
    bandwidth_hz: np.ndarray
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_dc_db: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current
    idd_a: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: frequency, and the response 20 log |Vout / Vin| over it
    frequency_hz: np.ndarray
    gain_db: np.ndarray
    # [Razavi-Analog] Sec. 6.7.1, p. 204: load capacitance C_L
    cload_f: float

    @property
    def level_shift_v(self) -> np.ndarray:
        # [Razavi-Analog] Sec. 3.4, p. 68: level shift of a follower
        return self.vin_v - self.vout_v


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCharacteristic(Analysis):
    """Follower input-output characteristic from the input's DC sweep (the middle level's run):
    at the middle of each swept step ``vin_v``, the output ``vout_v`` there and ``gain`` its slope
    over the step, dVout/dVin; ``vin_min_v`` and ``vin_max_v`` the input range's ends, where the
    gain, linear between the steps' middles, falls to 0.9 of its largest on either side of it, or
    the sweep's end, a rail (NaN where the gain is nowhere positive); ``vin_nominal_v`` the
    nominal input, the level the nominal input may take (``params.NOMINAL_VIN``) nearest the
    range's middle, inside it (NaN where none is)."""

    # [Razavi-Analog] Fig. 3.4, p. 48: input and output voltage (the characteristic Vout over Vin)
    vin_v: np.ndarray
    vout_v: np.ndarray
    # [Razavi-Analog] Eq. (3.8), p. 48: voltage gain, the slope dVout/dVin of the characteristic
    gain: np.ndarray
    # not in the reference texts: the input range's ends, where the gain dVout/dVin falls to 0.9 of
    # its largest (the block's criterion: where the devices are saturated and the follower follows,
    # [Razavi-Analog] Example 3.12, p. 70), and the nominal input inside it nearest its middle
    vin_nominal_v: float
    vin_min_v: float
    vin_max_v: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisImpedance(Analysis):
    """Follower output impedance at each measured point (a run with the AC stimulus on the input,
    the output test current's transfer to the output, the input from an ideal source, R_S = 0):
    the follower's own, the load's admittance (``cload_f``) taken from the output node's, its
    magnitude ``zout_ohm`` over ``frequency_hz``, one row per point, and ``rout_ohm`` that at the
    lowest frequency, the output resistance."""

    # [Razavi-Analog] Fig. 3.4, p. 48: input voltage
    vin_v: np.ndarray
    # [Razavi-Analog] Eq. (3.93), p. 71: a source follower's output resistance 1/(g_m + g_mb), in
    # parallel with r_O1 || r_O2 (Fig. 3.42, p. 72)
    # not in the reference texts: a flipped follower's output resistance, |Z_out| at the lowest
    # frequency
    rout_ohm: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: frequency
    frequency_hz: np.ndarray
    # [Razavi-Analog] Eq. (6.63), p. 192: output impedance Z_out = V_X/I_X, the bench's load
    # admittance removed, the input source at AC ground
    zout_ohm: np.ndarray
    # [Razavi-Analog] Sec. 6.7.1, p. 204: load capacitance C_L
    cload_f: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSlew(Analysis):
    """Follower large-signal step response at each step run (the nominal input, the bench's step
    and the same step at half its size, a row each).

    ``vol_v`` and ``voh_v`` are the output's settled levels, its average over the last twentieth of
    a period before the rising and the falling input edge: the rise's initial and final levels and
    the fall's initial one; the fall's final level is its own, the average over the record's last
    twentieth of a period. On each edge ``slew_rate_rise_v_per_s`` and ``slew_rate_fall_v_per_s``
    are the slope of the output's ramp (the fall's negative): from the input edge's end to the
    output's 90 % level, the longest stretch over which the output's local slope stays within
    2.5 % of one value with no steeper slope after it, the output's chord over the quarter of it where that slope varies least;
    in a row whose ramp spans less than a twentieth of its output's step, NaN. They are NaN in every
    row on an edge whose slope scales with the step (linear settling, or the device driving the
    load), which its transition time and settling describe alone: the largest step's ramp spans
    less than a twentieth of its output's step, or the smallest step's slope (its ramp's, or where it
    has none its steepest past the input edge's end) is not more than the square root of the
    steps' ratio times the largest's ramp's. ``rise_time_s`` and ``fall_time_s`` are the output's 10-90 %
    transition times between ``vol_v`` and ``voh_v`` (the fall's to its own final level);
    ``settling_rise_s`` and ``settling_fall_s`` the time from the middle of each input edge until
    the output stays within 1 % of the output's step about its final level (NaN where it does not
    within the edge's half period, or still moves across more than that band over the final level's
    interval); ``overshoot_rise`` and ``overshoot_fall`` how far it passes the final level before
    that interval, a fraction of the output's step (0 where it passes by no more than the block's
    threshold, 1 uV, set at Spectre's absolute voltage tolerance abstol(V)); ``idd_a`` the supply current's average over one
    period from the rise. The edges are NaN where the output moves less than a tenth of the step.
    """

    # not in the reference texts: the bench's input level and step (TbParams.vin_v, step_v)
    vin_v: np.ndarray
    step_v: np.ndarray
    # [Baker] Fig. 10.9, p. 333: output low and high levels V_OL, V_OH (Razavi: none); not in the
    # reference texts: each the output's average over the last twentieth of a period before an
    # input edge
    vol_v: np.ndarray
    voh_v: np.ndarray
    # [Razavi-Analog] Sec. 9.9, p. 391: slew rate, the slope of the output's ramp (Fig. 9.70)
    slew_rate_rise_v_per_s: np.ndarray
    slew_rate_fall_v_per_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: output rise and fall times t_LH, t_HL (Razavi: none), 10 to 90 %
    rise_time_s: np.ndarray
    fall_time_s: np.ndarray
    # [Razavi-ADC] Sec. 8.2.2, p. 150: settling time, into an error band about the final value; here
    # 1 % of the output's step ([Razavi-Analog] Example 9.2, pp. 346-347)
    settling_rise_s: np.ndarray
    settling_fall_s: np.ndarray
    # not in the reference texts: how far a step response passes its final level, a fraction of the
    # step (the calculator's overshoot)
    overshoot_rise: np.ndarray
    overshoot_fall: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current, here its average over one period of the step
    idd_a: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A follower's numbers (``analysis.metrics``), on typical models at 25 C, from an ideal input
    source (R_S = 0) into 100 fF, at its nominal input ``vin_v`` unless said (NaN where the
    follower has no input range): the output level and the level shift, the small-signal gain,
    bandwidth and PSRR, the supply current, the output resistance, the input range over which the
    gain holds, the step's slew rates, settling and overshoot on each edge (NaN where a step's
    level lies outside the input range), and the smallest bandwidth over the supply."""

    # [Razavi-Analog] Fig. 3.4, p. 48: input voltage, the nominal input
    vin_v: float = metric(
        "Nominal input: the level of 2/12 to 10/12 of the supply nearest the middle of the input range", "none"
    )
    # [Razavi-Analog] Fig. 3.4, p. 48: output voltage, at the operating point
    vout_v: float = metric("Output level", "none")
    # [Razavi-Analog] Sec. 3.4, p. 68: level shift of a follower
    level_shift_v: float = metric("Input minus output level", "none")
    # [Razavi-Analog] Eq. (3.8), p. 48: voltage gain
    gain_dc: float = metric("Small-signal gain at the lowest frequency", "higher")
    # [Razavi-Analog] Fig. 6.43, p. 204: -3-dB bandwidth
    bandwidth_hz: float = metric("-3 dB bandwidth, from an ideal source (R_S = 0) into 100 fF", "higher")
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_dc_db: float = metric(
        "Gain over the output's gain from one ripple on V_DD and the references' supply together (the references"
        " ideal currents into diodes on that supply), at the lowest frequency, no ripple on ground",
        "higher",
    )
    # [Razavi-PLL] Example 3.5, p. 70: supply current
    idd_a: float = metric("Supply current at the operating point", "lower")
    # [Razavi-Analog] Eq. (3.93), p. 71: a source follower's output resistance 1/(g_m + g_mb), in
    # parallel with r_O1 || r_O2 (Fig. 3.42, p. 72)
    # not in the reference texts: a flipped follower's output resistance, |Z_out| at the lowest
    # frequency
    rout_ohm: float = metric("Output resistance, the output impedance at the lowest frequency", "lower")
    # not in the reference texts: the span of input level over which the gain dVout/dVin of the DC
    # sweep stays above 0.9 of its largest, its ends interpolated between the sweep's steps
    # (calc.cross); the devices' saturation bounds it ([Razavi-Analog] Example 3.12, p. 70)
    input_range_v: float = metric(
        "Input range over which the DC gain dVout/dVin stays within 10 % of its largest (an end at a rail: the rail)",
        "higher",
    )
    # not in the reference texts: how far the step's two input levels lie inside the input range,
    # the smaller of the two distances, negative where a level lies outside it (where the follower
    # does not follow, and the step's edges are not the follower's)
    step_margin_v: float = metric(
        "The step's input levels inside the input range by at least this (negative: a level outside it, and the"
        " step's metrics NaN)",
        "higher",
    )
    # [Razavi-Analog] Sec. 9.9, p. 391: slew rate, the slope of the output's ramp (Fig. 9.70)
    slew_rate_rise_v_per_s: float = metric(
        "Slew rate of the rising step from an ideal source (R_S = 0) into 100 fF: the slope of the output's ramp"
        " (where it holds at half the step; none where the slope scales with the step)",
        "higher",
    )
    # [Razavi-Analog] Sec. 9.9, p. 391: slew rate of the falling edge (negative)
    slew_rate_fall_v_per_s: float = metric(
        "Slew rate of the falling step (negative) from an ideal source (R_S = 0) into 100 fF: the slope of the"
        " output's ramp (where it holds at half the step; none where the slope scales with the step)",
        "lower",
    )
    # [Baker] Fig. 10.9, p. 333: output rise and fall times t_LH, t_HL (Razavi: none), 10 to 90 %
    rise_time_s: float = metric(
        "Output rise time, 10 to 90 % of the output's rising step, from an ideal source (R_S = 0) into 100 fF", "lower"
    )
    fall_time_s: float = metric(
        "Output fall time, 90 to 10 % of the output's falling step, from an ideal source (R_S = 0) into 100 fF", "lower"
    )
    # [Razavi-ADC] Sec. 8.2.2, p. 150: settling time, into an error band about the final value; here
    # 1 % of the output's step ([Razavi-Analog] Example 9.2, pp. 346-347)
    settling_rise_s: float = metric(
        "Settling to within 1 % of the output's rising step, from the middle of the input edge, from an ideal source"
        " (R_S = 0) into 100 fF",
        "lower",
    )
    settling_fall_s: float = metric(
        "Settling to within 1 % of the output's falling step, from the middle of the input edge, from an ideal"
        " source (R_S = 0) into 100 fF",
        "lower",
    )
    # not in the reference texts: how far a step response passes its final level, a fraction of the
    # step (the calculator's overshoot)
    overshoot_rise: float = metric(
        "Overshoot past the output's final level on the rising step, a fraction of the output's step", "lower"
    )
    overshoot_fall: float = metric(
        "Overshoot past the output's final level on the falling step, a fraction of the output's step", "lower"
    )
    # [Razavi-Analog] Fig. 6.43, p. 204: -3-dB bandwidth; not in the reference texts: its smallest
    # over the supply corners
    bandwidth_min_supply_hz: float = metric(
        "Smallest -3 dB bandwidth over the supply at 90 to 110 %, the input held relative to the rail its input"
        " device's source rides, from an ideal source (R_S = 0) into 100 fF (a corner beyond the sweep, following,"
        " is above it; none where every corner is, or one does not follow)",
        "higher",
    )
