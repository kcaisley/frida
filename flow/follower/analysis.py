"""The follower's analyses: each from runs' measurements (``flow.pipeline.Meas``) of its testbench,
and the record's metrics. The figures are built from ``flow.analysis.calc`` where the calculator has
the operation, and from NumPy otherwise (a magnitude, a sliding window, a minimum over corners).

A run with the AC stimulus on the input holds the operating point (the output level and the supply
current), the output's response per volt of input and the output per volt of each supply (Spectre's
``xf``): the gain, bandwidth and PSRR, the supply's ripple on the follower's supply and on its bias
references' together (``analyze_transfer``); and the output per ampere of the test current into it,
the output impedance (``analyze_impedance``); the nominal input's run also holds the input's DC
sweep, the input-output characteristic and its slope, the gain over the input level, and from it
the input range and the nominal input (``analyze_characteristic``). A step run holds the transient of a large input step
up and back down, whose output gives the transition times, settling and overshoot, and, beside the
same step at half its size, the slew rate of an edge that slews (``analyze_slew``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, measurement_identity

from .params import NOMINAL_VIN, SUPPLY_SWEEP, Stimulus
from .subckt import Nets
from .types import AnalysisCharacteristic, AnalysisImpedance, AnalysisSlew, AnalysisTransfer, Metrics


@analysis
def analyze_transfer(measurements: Sequence[Meas]) -> AnalysisTransfer:
    """Measure output level, small-signal gain, bandwidth, PSRR, and supply current at each point."""

    identity = measurement_identity(measurements)
    if any(item.tb.stimulus is not Stimulus.INPUT for item in measurements):
        raise ValueError("follower transfer requires the AC stimulus on the input")
    frequency_hz = measurements[0].sweeps["ac"].x
    if any(not np.array_equal(item.sweeps["ac"].x, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    if len({float(item.tb.cload_f) for item in measurements}) != 1:
        raise ValueError("follower analysis requires one load for every point")
    rows = []
    for measurement in measurements:
        op, ac, xf = (measurement.sweeps[name] for name in ("opdc", "ac", "xf"))
        if not np.array_equal(xf.x, ac.x):
            raise ValueError("follower analysis requires the transfer functions on the AC response's frequencies")
        # the output per volt of input, and per volt of supply: one ripple on the follower's supply
        # and on the references' (vddb, the bench's), whose current-source bias moves with it (not
        # in the reference texts: the bench's convention, the two sources' transfers summed)
        magnitude = np.abs(ac.v[Nets.vout.name])
        supply_gain = np.abs(xf.v[Nets.vdd.name] + xf.v["vddb"])
        rows.append(
            (
                float(measurement.tb.vdd),
                float(measurement.tb.vin_v),
                float(op.v[Nets.vout.name][0]),
                # [Razavi-Analog] Eq. (3.8), p. 48: the voltage gain, at the lowest frequency
                float(magnitude[0]),
                # [Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth
                calc.bandwidth(magnitude, frequency_hz, 3.0, "low"),
                # [Razavi-Analog] Sec. 9.11, p. 400: PSRR, the input's gain over the supply's to the
                # output, at the lowest frequency
                float(calc.db20(magnitude[0]) - calc.db20(supply_gain[0])),
                # [Razavi-PLL] Example 3.5, p. 70: the supply current, the operating point's
                float(op.i[Nets.vdd.name][0]),
                # [Razavi-Analog] Fig. 6.43, p. 204: the response 20 log |Vout / Vin|
                calc.db20(magnitude),
            )
        )
    vdd_v, vin_v, vout_v, gain, bandwidth, psrr, current, gain_db = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        vout_v=vout_v,
        gain_dc=gain,
        bandwidth_hz=bandwidth,
        psrr_dc_db=psrr,
        idd_a=current,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        gain_db=gain_db,
        cload_f=float(measurements[0].tb.cload_f),
    )


@analysis
def analyze_impedance(measurements: Sequence[Meas]) -> AnalysisImpedance:
    """Measure the output impedance at each point from the output test current's transfer to it."""

    identity = measurement_identity(measurements)
    if any(item.tb.stimulus is not Stimulus.INPUT for item in measurements):
        raise ValueError("follower impedance requires the runs with the AC stimulus on the input")
    frequency_hz = measurements[0].sweeps["xf"].x
    if any(not np.array_equal(item.sweeps["xf"].x, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    if len({float(item.tb.cload_f) for item in measurements}) != 1:
        raise ValueError("follower analysis requires one load for every point")
    # the output per ampere of the test current into it (the bench's itest) is the output node's
    # impedance, the load across the follower's own: its admittance taken away leaves the follower's
    # (not in the reference texts: the bench's test current read through Spectre's xf, the load's
    # admittance subtracted from the node's)
    # [Razavi-Analog] Eq. (6.63), p. 192: output impedance Z_out = V_X/I_X, the bench's load
    # admittance removed, the input source at AC ground
    zout_ohm = np.asarray(
        [
            np.abs(1 / (1 / item.sweeps["xf"].v["itest"] - 2j * np.pi * frequency_hz * item.tb.cload_f))
            for item in measurements
        ],
        dtype=np.float64,
    )
    return AnalysisImpedance(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=np.asarray([float(item.tb.vin_v) for item in measurements], dtype=np.float64),
        # [Razavi-Analog] Eq. (3.93), p. 71: a source follower's output resistance 1/(g_m + g_mb),
        # in parallel with r_O1 || r_O2 (Fig. 3.42, p. 72)
        # not in the reference texts: a flipped follower's output resistance, |Z_out| at the lowest
        # frequency
        rout_ohm=zout_ohm[:, 0],
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        zout_ohm=zout_ohm,
        cload_f=float(measurements[0].tb.cload_f),
    )


def _ramp(values: np.ndarray, axis: np.ndarray, begin_s: float, end_s: float) -> tuple[float, float]:
    """The output's ramp from ``begin_s`` to ``end_s``: its slope and how far the output moves along
    it. The output's local slope (its chord over a fortieth of the span either side of each of 801
    times) is taken; the ramp is the longest stretch over which that slope keeps one sign and
    stays within 2.5 % of one value (its largest magnitude within 1.025 / 0.975 of its smallest),
    with no steeper slope after it (a current-limited ramp gives way only to slower settling),
    its slope the output's chord over the quarter of the stretch where the local slope varies
    least; NaN for both where the span is empty or the output does not move."""

    span = end_s - begin_s
    if not span > 0:
        return math.nan, math.nan
    local = span / 40
    centres = np.linspace(begin_s + local, end_s - local, 801)
    slopes = (calc.value(values, axis, centres + local) - calc.value(values, axis, centres - local)) / (2 * local)
    size, sign = np.abs(slopes), np.sign(slopes)
    # the steepest local slope from each time on, and none past the last
    after = np.append(np.maximum.accumulate(size[::-1])[::-1], 0.0)
    first, last = 0, -1
    for start in range(len(slopes)):
        if not size[start] > 0:
            continue
        top, bottom = np.maximum.accumulate(size[start:]), np.minimum.accumulate(size[start:])
        held = np.logical_and.accumulate(sign[start:] == sign[start]) & (top * 0.975 <= bottom * 1.025)
        stop = start + int(np.count_nonzero(held)) - 1
        if after[stop + 1] * 0.975 > top[stop - start] * 1.025:
            continue
        if stop - start > last - first:
            first, last = start, stop
    if last < first:
        return math.nan, math.nan
    width = max(1, round((last - first) / 4))
    if last - first < width:
        begin, end = float(centres[first]), float(centres[last]) if last > first else float(centres[first] + local)
    else:
        spread = np.ptp(np.lib.stride_tricks.sliding_window_view(slopes[first : last + 1], width + 1), axis=1)
        low = first + int(np.argmin(spread))
        begin, end = float(centres[low]), float(centres[low + width])
    slope = float((calc.value(values, axis, end) - calc.value(values, axis, begin)) / (end - begin))
    moved = abs(float(calc.value(values, axis, float(centres[last])) - calc.value(values, axis, float(centres[first]))))
    return slope, moved


def _edge(
    output: np.ndarray,
    time_s: np.ndarray,
    start_s: float,
    stop_s: float,
    edge_s: float,
    initial: float,
    final: float,
    hold_s: float,
) -> tuple[float, float, float, float, float, float]:
    """One edge of the step, from ``initial`` to ``final``, its window from the input edge's start
    ``start_s`` to ``stop_s``, the input edge ``edge_s`` long, the last ``hold_s`` of the window
    the final level's interval: the output's ramp from the input edge's end to its 90 % level
    (``_ramp``: its slope, signed, and the share of the step it spans), the output's steepest
    slope there (signed); the 10-90 % transition time; the time the output enters and stays in the
    1 % band about ``final`` (absolute; NaN where the output drifts across more than that band over
    the final level's interval, or settles only inside it); and the overshoot past ``final``
    before that interval, a fraction of the step, 0 where it passes ``final`` by no more than the
    block's threshold, 1 uV (set at Spectre's absolute voltage tolerance, abstol(V))."""

    up = final > initial
    values, axis = calc.clip(output, time_s, start_s, stop_s)
    # [Razavi-Analog] Sec. 9.9, p. 391: the slew rate, the slope of the output's ramp (Fig. 9.70),
    # from the input edge's end (not in the reference texts: the estimator, the longest stretch of
    # one slope, _ramp)
    high_s = calc.cross(
        values, axis, initial + 0.9 * (final - initial), edge="rising" if up else "falling", occurrence=1
    )
    begin_s = start_s + edge_s
    if math.isfinite(high_s) and high_s > begin_s:
        slope, moved = _ramp(values, axis, begin_s, high_s)
        derivative = calc.deriv(*calc.clip(values, axis, begin_s, high_s))
        steepest = float(np.max(derivative) if up else np.min(derivative))
    else:
        slope, moved, steepest = math.nan, math.nan, math.nan
    share = moved / abs(final - initial)
    # [Baker] Fig. 10.9, p. 333: the output's rise and fall times, from 10 to 90 % of the step
    transition = calc.riseTime(values, axis, initial, final) if up else calc.fallTime(values, axis, initial, final)
    # [Razavi-ADC] Sec. 8.2.2, p. 150: settling, the output entering an error band about its final
    # value, here within 1 % of the step ([Razavi-Analog] Example 9.2, pp. 346-347); not in the
    # reference texts: that it stays in the band from then on (calc.settlingTime)
    band = 0.01 * abs(final - initial)
    settled = calc.settlingTime(values, axis, initial=initial, final=final, percent_of_step=1.0)
    # not in the reference texts: the final level is known only where the output holds it, its
    # drift over the final level's interval (twice the difference of its halves' averages: a
    # linear drift's change over the interval) within the band; and the output has settled in the
    # window only where it does so before that interval, from which it stays in the band
    middle_s = stop_s - hold_s / 2
    drift = 2 * (
        calc.average(*calc.clip(values, axis, middle_s, stop_s))
        - calc.average(*calc.clip(values, axis, stop_s - hold_s, middle_s))
    )
    if abs(drift) > band or not settled <= stop_s - hold_s:
        settled = math.nan
    # not in the reference texts: overshoot, how far the response passes its final level, a fraction
    # of the step (the calculator's overshoot), up to the final level's interval; an excursion of
    # no more than the block's threshold, 1 uV (set at Spectre's absolute voltage tolerance
    # abstol(V), its default, which the bench keeps), is 0 (+ 0.0: never -0.0)
    passed = calc.overshoot(*calc.clip(values, axis, start_s, stop_s - hold_s), initial, final) / 100
    resolved = passed * abs(final - initial) > 1e-6
    return slope, share, steepest, float(transition), settled, passed + 0.0 if resolved else 0.0


@analysis
def analyze_slew(measurements: Sequence[Meas]) -> AnalysisSlew:
    """Measure the output's slew rates, transition times, settling and overshoot on the input's
    rising and falling steps: the step runs of one instance at one input level, at two step sizes
    or more, one row each in their order. An edge's slew rate is its ramp's slope (``_ramp``: from
    the input edge's end, the longest stretch of one slope with no steeper slope after it), NaN in a row whose ramp spans less
    than a twentieth of its output's step; and NaN in every row where the slope scales with the step
    (linear settling, or the device driving the load): the largest step's ramp spans less than a
    twentieth of its output's step, or the smallest step's slope (its ramp's, or where its ramp is
    shorter its steepest past the input edge's end) is not more than the square root of the
    steps' ratio times the largest's ramp's."""

    identity = measurement_identity(measurements)
    if any(item.tb.stimulus is not Stimulus.STEP or not len(item.time_s) for item in measurements):
        raise ValueError("follower slew requires the transient of a step run")
    if (
        len({float(item.tb.vin_v) for item in measurements}) != 1
        or len({float(item.tb.step_v) for item in measurements}) < 2
    ):
        raise ValueError("follower slew requires the step runs of one input level at two step sizes or more")
    rows = []
    for measurement in measurements:
        tb, time_s = measurement.tb, measurement.time_s
        output = measurement.v[Nets.vout.name]
        period, edge = float(tb.step_period_s), float(tb.transition_time_s)
        # the record's end: Spectre's last strobe, the sum of the strobes before it, falls a few
        # ulps short of tran_stop_s; a record ending more than a strobe short of it was cut short
        if tb.tran_stop_s - float(time_s[-1]) > tb.waveform_sample_interval_s:
            raise ValueError("follower slew requires the step run's record to its end")
        rise_s, fall_s, stop_s = period / 4, 3 * period / 4, min(tb.tran_stop_s, float(time_s[-1]))
        # the settled levels: the output over the last twentieth of a period before each input edge
        # (the low and the high one) and before the record's end (the fall's own final level)
        hold_s = period / 20
        low, high, end = (
            calc.average(*calc.clip(output, time_s, end_s - hold_s, end_s)) for end_s in (rise_s, fall_s, stop_s)
        )
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.step_v) / 10:
            ramp_rise, share_rise, steep_rise, rise_time, rise_settled, over_rise = _edge(
                output, time_s, rise_s, fall_s, edge, low, high, hold_s
            )
            ramp_fall, share_fall, steep_fall, fall_time, fall_settled, over_fall = _edge(
                output, time_s, fall_s, stop_s, edge, high, end, hold_s
            )
            # settling from the middle of each input edge
            edges = (
                ramp_rise,
                ramp_fall,
                share_rise,
                share_fall,
                steep_rise,
                steep_fall,
                rise_time,
                fall_time,
                rise_settled - rise_s - edge / 2,
                fall_settled - fall_s - edge / 2,
                over_rise,
                over_fall,
            )
        else:
            edges = (math.nan,) * 12
        rows.append(
            (
                float(tb.vin_v),
                float(tb.step_v),
                low,
                high,
                *edges,
                # over one period from the rise: each level and each edge once
                calc.average(*calc.clip(measurement.i[Nets.vdd.name], time_s, rise_s, stop_s)),
            )
        )
    (
        vin_v,
        step_v,
        low_v,
        high_v,
        slew_rise,
        slew_fall,
        share_rise,
        share_fall,
        steep_rise,
        steep_fall,
        rise_time,
        fall_time,
        settling_rise,
        settling_fall,
        over_rise,
        over_fall,
        current,
    ) = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    largest, smallest = int(np.argmax(step_v)), int(np.argmin(step_v))
    # [Razavi-Analog] Eq. (9.58), p. 390: a linear step response's slope is in proportion to the
    # step; Sec. 9.9, pp. 391-392: a slewing output ramps at a slope its current sets, whatever the
    # step. not in the reference texts: the tests, a ramp over a twentieth of the output's step at
    # least, and the threshold, the square root of the steps' ratio (halfway, on a log scale,
    # between holding and scaling); a linear edge's slope at half the step is half its own
    ratio = math.sqrt(step_v[smallest] / step_v[largest])
    for slopes, shares, steepest in ((slew_rise, share_rise, steep_rise), (slew_fall, share_fall, steep_fall)):
        small = slopes[smallest] if shares[smallest] >= 0.05 else steepest[smallest]
        if not (shares[largest] >= 0.05 and abs(small) > ratio * abs(slopes[largest])):
            slopes[:] = math.nan
        slopes[~(shares >= 0.05)] = math.nan
    return AnalysisSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=vin_v,
        step_v=step_v,
        vol_v=low_v,
        voh_v=high_v,
        slew_rate_rise_v_per_s=slew_rise,
        slew_rate_fall_v_per_s=slew_fall,
        rise_time_s=rise_time,
        fall_time_s=fall_time,
        settling_rise_s=settling_rise,
        settling_fall_s=settling_fall,
        overshoot_rise=over_rise,
        overshoot_fall=over_fall,
        idd_a=current,
    )


def _input_range(gain: np.ndarray, vin_v: np.ndarray, ends: tuple[float, float]) -> tuple[float, float]:
    """The input levels on either side of the gain's largest value nearest it where the gain,
    linear between the points ``vin_v``, falls to 0.9 of it (calc.cross), or ``ends`` (the sweep's
    own) where it does not; NaN for both where the gain is nowhere positive."""

    # not in the reference texts: the input range of a single-ended follower, over which its gain
    # stays within 10 % of its largest; its devices' saturation bounds it ([Razavi-Analog]
    # Example 3.12, p. 70)
    peak = int(np.argmax(gain))
    level = float(gain[peak])
    if not level > 0:
        return math.nan, math.nan
    crossings = calc.cross(gain, vin_v, 0.9 * level, edge="either")
    below, above = crossings[crossings < vin_v[peak]], crossings[crossings > vin_v[peak]]
    return (
        float(np.max(below)) if len(below) else ends[0],
        float(np.min(above)) if len(above) else ends[1],
    )


@analysis
def analyze_characteristic(measurement: Meas) -> AnalysisCharacteristic:
    """Measure the input-output characteristic over the input's DC sweep: the output and its
    slope dVout/dVin at the middle of each step, the input range over which that slope stays
    within 10 % of its largest, and the nominal input, the level the nominal input may take
    (``NOMINAL_VIN`` of the run's supply) nearest the range's middle, inside it."""

    if measurement.tb.stimulus is not Stimulus.INPUT or "dc" not in measurement.sweeps:
        raise ValueError("follower characteristic requires a run with the input's DC sweep")
    sweep = measurement.sweeps["dc"]
    vin_v, output = sweep.x, sweep.v[Nets.vout.name]
    middles = (vin_v[1:] + vin_v[:-1]) / 2
    # [Razavi-Analog] Eq. (3.8), p. 48: the gain, the slope dVout/dVin of the characteristic
    gain = calc.deriv(output, vin_v)
    low, high = _input_range(gain, middles, (float(vin_v[0]), float(vin_v[-1])))
    # not in the reference texts: the nominal input, where every nominal-point metric is taken:
    # inside the input range, where the devices are saturated and the follower follows
    # ([Razavi-Analog] Example 3.12, p. 70), the level nearest its middle (each as runs.testbenches
    # rounds it)
    vdd = float(measurement.tb.vdd)
    inside = [level for level in (round(share * vdd, 4) for share in NOMINAL_VIN) if low <= level <= high]
    nominal = min(inside, key=lambda level: abs(level - (low + high) / 2)) if inside else math.nan
    return AnalysisCharacteristic(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        vin_v=np.asarray(middles, dtype=np.float64),
        # [Razavi-Analog] Fig. 3.34(c), p. 68: the follower's input-output characteristic
        vout_v=np.asarray(calc.value(output, vin_v, middles), dtype=np.float64),
        gain=np.asarray(gain, dtype=np.float64),
        vin_nominal_v=nominal,
        vin_min_v=low,
        vin_max_v=high,
    )


def metrics(
    *,
    transfer: AnalysisTransfer,
    impedance: AnalysisImpedance,
    characteristic: AnalysisCharacteristic,
    slew: AnalysisSlew,
    supply: AnalysisTransfer,
) -> Metrics:
    """The record's numbers: from the input level's runs (``transfer``, ``impedance``) the output
    level, level shift, gain, bandwidth, PSRR, supply current and output resistance at the
    nominal input (``characteristic.vin_nominal_v``); from the DC sweep (``characteristic``) the
    input range over which the gain dVout/dVin stays within 10 % of its largest; from the bench's
    step at the nominal input (``slew``'s largest) the slew rates, transition times, settling and
    overshoot of each edge, NaN where one of its levels lies outside the input range, and how far
    its levels lie inside it; from the supply's runs at the nominal input (``supply``, in
    ``SUPPLY_SWEEP``'s order) the smallest bandwidth. Every nominal-point value is NaN where the
    follower has no input range (no nominal input)."""

    at = characteristic.vin_nominal_v
    low, high = characteristic.vin_min_v, characteristic.vin_max_v
    if not math.isfinite(at):
        # every other metric's default: NaN
        return Metrics(input_range_v=high - low)
    nominal = int(np.argmin(np.abs(transfer.vin_v - at)))
    if not np.array_equal(transfer.vin_v, impedance.vin_v) or abs(transfer.vin_v[nominal] - at) > 1e-9:
        raise ValueError("follower metrics require the input levels' runs at the nominal input")
    if np.any(np.abs(slew.vin_v - at) > 1e-9):
        raise ValueError("follower metrics require the step runs at the nominal input")
    # the bench's step, the largest of the step runs
    step = int(np.argmax(slew.step_v))
    # not in the reference texts: the step's two input levels inside the input range by at least
    # this much; where one lies outside it the step's edges are not the follower's, and its metrics
    # are NaN
    margin = min(
        float(slew.vin_v[step] - slew.step_v[step] / 2) - low,
        high - float(slew.vin_v[step] + slew.step_v[step] / 2),
    )
    edges = {
        name: float(getattr(slew, name)[step]) if margin >= 0 else math.nan
        for name in (
            "slew_rate_rise_v_per_s",
            "slew_rate_fall_v_per_s",
            "rise_time_s",
            "fall_time_s",
            "settling_rise_s",
            "settling_fall_s",
            "overshoot_rise",
            "overshoot_fall",
        )
    }

    # [Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth over the supply corners; a corner's
    # NaN lies beyond the sweep, above every finite one, only where that corner follows (not in the
    # reference texts: its gain within 10 % of the nominal corner's, and its response at the
    # sweep's end within 3 dB of its lowest frequency's); any other NaN corner makes the smallest
    # NaN
    centre = SUPPLY_SWEEP.index(1.0)
    beyond = (np.abs(supply.gain_dc - supply.gain_dc[centre]) <= 0.1 * supply.gain_dc[centre]) & (
        supply.gain_db[:, -1] >= supply.gain_db[:, 0] - 3.0
    )
    unknown = np.isnan(supply.bandwidth_hz) & ~beyond
    return Metrics(
        vin_v=at,
        vout_v=float(transfer.vout_v[nominal]),
        level_shift_v=float(transfer.level_shift_v[nominal]),
        gain_dc=float(transfer.gain_dc[nominal]),
        bandwidth_hz=float(transfer.bandwidth_hz[nominal]),
        psrr_dc_db=float(transfer.psrr_dc_db[nominal]),
        idd_a=float(transfer.idd_a[nominal]),
        rout_ohm=float(impedance.rout_ohm[nominal]),
        # not in the reference texts: the span over which the DC sweep's gain stays within 10 % of
        # its largest
        input_range_v=high - low,
        step_margin_v=margin,
        **edges,
        bandwidth_min_supply_hz=math.nan if unknown.any() else float(np.fmin.reduce(supply.bandwidth_hz)),
    )
