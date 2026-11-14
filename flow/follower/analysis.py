"""The follower's analyses: each from runs' measurements (``flow.pipeline.Meas``) of its testbench,
and the record's metrics. Every figure is a calculator function of ``flow.analysis.calc``.

A run with the AC stimulus on the input holds the operating point (the output level and the supply
current), the output's response per volt of input and the output per volt of supply (Spectre's
``xf``): the gain, bandwidth and PSRR (``analyze_transfer``). A run with the stimulus on the output
test current holds the output's response to 1 V behind the test resistance, a divider of that
resistance and the output impedance (``analyze_impedance``). A step run holds the transient of a
large input step up and back down, whose output gives the slew rates, settling and overshoot
(``analyze_slew``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, measurement_identity

from .params import NOMINAL_VIN, VIN_SWEEP, Stimulus
from .subckt import Nets
from .types import AnalysisImpedance, AnalysisSlew, AnalysisTransfer, Metrics


@analysis
def analyze_transfer(measurements: Sequence[Meas]) -> AnalysisTransfer:
    """Measure output level, small-signal gain, bandwidth, PSRR, and supply current at each point."""

    identity = measurement_identity(measurements)
    if any(item.tb.stimulus is not Stimulus.INPUT for item in measurements):
        raise ValueError("follower transfer requires the AC stimulus on the input")
    frequency_hz = measurements[0].sweeps["ac"].x
    if any(not np.array_equal(item.sweeps["ac"].x, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        op, ac, xf = (measurement.sweeps[name] for name in ("opdc", "ac", "xf"))
        # the output per volt of input, and per volt of supply
        magnitude = np.abs(ac.v[Nets.vout.name])
        supply_gain = np.abs(xf.v[Nets.vdd.name])
        rows.append(
            (
                float(measurement.tb.vin_v),
                float(op.v[Nets.vout.name][0]),
                float(magnitude[0]),
                calc.bandwidth(magnitude, frequency_hz, 3.0, "low"),
                float(calc.db20(magnitude[0]) - calc.db20(supply_gain[0])),
                float(op.i[Nets.vdd.name][0]),
                calc.db20(magnitude),
            )
        )
    vin_v, vout_v, gain, bandwidth, psrr, current, gain_db = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=vin_v,
        vout_v=vout_v,
        gain_dc=gain,
        bandwidth_hz=bandwidth,
        psrr_dc_db=psrr,
        idd_a=current,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        gain_db=gain_db,
    )


@analysis
def analyze_impedance(measurements: Sequence[Meas]) -> AnalysisImpedance:
    """Measure the output impedance at each point from the output test current's response."""

    identity = measurement_identity(measurements)
    if not all(item.tb.stimulus is Stimulus.OUTPUT for item in measurements):
        raise ValueError("follower impedance requires the AC stimulus on the output test current")
    frequency_hz = measurements[0].sweeps["ac"].x
    if any(not np.array_equal(item.sweeps["ac"].x, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    # the output impedance, from the divider of the test resistance and the impedance that the
    # 1 V test stimulus drives
    zout_ohm = np.asarray(
        [
            np.abs(response * item.tb.test_resistance_ohm / (1 - response))
            for item in measurements
            for response in (item.sweeps["ac"].v[Nets.vout.name],)
        ],
        dtype=np.float64,
    )
    return AnalysisImpedance(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=np.asarray([float(item.tb.vin_v) for item in measurements], dtype=np.float64),
        zout_dc_ohm=zout_ohm[:, 0],
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        zout_ohm=zout_ohm,
    )


@analysis
def analyze_slew(measurements: Sequence[Meas]) -> AnalysisSlew:
    """Measure the output's slew rates, settling and overshoot on the input's rising and falling steps."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.tb
        if tb.stimulus is not Stimulus.STEP or not len(measurement.time_s):
            raise ValueError("follower slew requires the transient of a step run")
        time_s, output = measurement.time_s, measurement.v[Nets.vout.name]
        period, edge = float(tb.step_period_s), float(tb.transition_time_s)
        rise_s, fall_s = period / 4, 3 * period / 4
        # the settled levels: the output just before each input edge
        low = calc.average(*calc.clip(output, time_s, rise_s - period / 20, rise_s))
        high = calc.average(*calc.clip(output, time_s, fall_s - period / 20, fall_s))
        up_v, up_s = calc.clip(output, time_s, rise_s, fall_s)
        down_v, down_s = calc.clip(output, time_s, fall_s, float(time_s[-1]))
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.step_v) / 10:
            rise_settled = calc.settlingTime(up_v, up_s, initial=low, final=high, percent_of_step=1.0)
            fall_settled = calc.settlingTime(down_v, down_s, initial=high, final=low, percent_of_step=1.0)
            edges = (
                calc.slewrate(up_v, up_s, low, high),
                calc.slewrate(down_v, down_s, high, low),
                rise_settled - rise_s - edge / 2,
                fall_settled - fall_s - edge / 2,
                max(calc.overshoot(up_v, up_s, low, high), 0.0) / 100,
                max(calc.overshoot(down_v, down_s, high, low), 0.0) / 100,
            )
        else:
            edges = (math.nan,) * 6
        rows.append(
            (float(tb.vin_v), float(tb.step_v), low, high, *edges, calc.average(measurement.i[Nets.vdd.name], time_s))
        )
    columns = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    vin_v, step_v, low_v, high_v, rise_slew, fall_slew, rise_settling, fall_settling, rise_over, fall_over, current = (
        columns
    )
    return AnalysisSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=vin_v,
        step_v=step_v,
        vout_low_v=low_v,
        vout_high_v=high_v,
        slew_rate_rise_v_per_s=rise_slew,
        slew_rate_fall_v_per_s=fall_slew,
        settling_rise_s=rise_settling,
        settling_fall_s=fall_settling,
        overshoot_rise=rise_over,
        overshoot_fall=fall_over,
        idd_a=current,
    )


def metrics(
    *, transfer: AnalysisTransfer, impedance: AnalysisImpedance, slew: AnalysisSlew, supply: AnalysisTransfer
) -> Metrics:
    """The record's numbers: from the input level's runs (``transfer``, ``impedance``: in
    ``VIN_SWEEP``'s order) the output level, level shift, gain, bandwidth, PSRR, supply current
    and output impedance at the follower's nominal input, and the input range around it over which
    the gain stays within 10 % of its value there; from the step (``slew``) the slew rates,
    settling and overshoot of each edge; from the supply's runs (``supply``) the smallest
    bandwidth."""

    dut = transfer.dut
    nominal = round(NOMINAL_VIN[dut.topology, dut.input_xtors] * (len(VIN_SWEEP) - 1))
    low, high = calc.compliance_range(transfer.gain_dc, transfer.vin_v, transfer.vin_v[nominal], 0.1)
    return Metrics(
        vout_v=float(transfer.vout_v[nominal]),
        level_shift_v=float(transfer.level_shift_v[nominal]),
        gain_dc=float(transfer.gain_dc[nominal]),
        bandwidth_hz=float(transfer.bandwidth_hz[nominal]),
        psrr_dc_db=float(transfer.psrr_dc_db[nominal]),
        idd_a=float(transfer.idd_a[nominal]),
        zout_dc_ohm=float(impedance.zout_dc_ohm[nominal]),
        input_range_v=high - low,
        slew_rate_rise_v_per_s=float(slew.slew_rate_rise_v_per_s[0]),
        slew_rate_fall_v_per_s=float(slew.slew_rate_fall_v_per_s[0]),
        settling_rise_s=float(slew.settling_rise_s[0]),
        settling_fall_s=float(slew.settling_fall_s[0]),
        overshoot_rise=float(slew.overshoot_rise[0]),
        overshoot_fall=float(slew.overshoot_fall[0]),
        bandwidth_min_supply_hz=float(np.min(supply.bandwidth_hz)),
    )
