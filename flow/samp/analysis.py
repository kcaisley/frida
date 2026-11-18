"""The sampler's analyses: each from a run's measurement (``flow.pipeline.Meas``, its signals on
Spectre's own time axis) of a testbench, and the record's metrics.

A run tracks while ``clk`` is high, and its input steps once per period in the middle of each hold
phase. Every figure is a median over the periods after the first (whose track phase starts from
an arbitrary held value); where a figure differs between the input's rising and falling steps, the
median of each direction and then the worse of the two. A track phase settles from the step: its
time constant, the switch's effective resistance into the load, and what is left at the end
(``analyze_track``); a bootstrap's boosted gate (``analyze_boost``); a full-scale step's
acquisition time (``analyze_acquisition``). A hold phase shows the pedestal the opening switch
leaves, the droop before the input steps, and how much of that step feeds through
(``analyze_hold``); the droop while the DAC's first step moves the held output (``analyze_dac``).
A sine's held samples show the switch's distortion and how far the behavioral model's held value
is from them (``analyze_sine``). Every run that saved its devices' values shows their largest
voltages (``analyze_stress``); a clock period's energy (``analyze_energy``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.circuit import oppoint
from flow.pipeline import Meas, analysis, measurement_identity

from .params import ACQUISITION_BITS, NOMINAL_VIN
from .subckt import Nets, netlist
from .types import (
    AnalysisAcquisition,
    AnalysisBoost,
    AnalysisDac,
    AnalysisEnergy,
    AnalysisHold,
    AnalysisSine,
    AnalysisStress,
    AnalysisTrack,
)


def _worse(by_direction: dict[bool, list[float]], *, slower: bool = True) -> float:
    """The median of each step direction's values, then the larger: NaN where a direction's
    median is NaN (that direction never settled) or no direction has a value. A direction's first
    phase is left out where it has others: it starts from what the first, unmeasured phase left."""
    medians = [
        float(np.median(values[1:] if len(values) > 1 else values)) for values in by_direction.values() if values
    ]
    if not medians or any(math.isnan(value) for value in medians):
        return math.nan
    return max(medians) if slower else min(medians)


def _tracks(measurement: Meas) -> list[tuple[float, float, float, bool]]:
    """Each track phase after the first: its clock's rising and falling mid-supply crossings, the
    input level it settles to, and whether the input stepped up to it (from the level a period
    before: the held output, a pedestal off, may lie on either side of it)."""
    tb = measurement.param
    vdd, period = float(tb.vdd), float(tb.clock_period_s)
    time_s = measurement.time_s
    clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.vin, Nets.vout))
    falls = calc.cross(clock, time_s, vdd / 2, edge="falling")
    found = []
    for start in calc.cross(clock, time_s, vdd / 2, edge="rising")[1:]:
        ends = falls[falls > start]
        if not len(ends):
            continue
        end = float(ends[0])
        middle = (start + end) / 2
        level = calc.value(data, time_s, middle)
        before = calc.value(data, time_s, middle - period) if middle - period >= time_s[0] else math.nan
        rising = level >= (calc.value(output, time_s, float(start)) if math.isnan(before) else before)
        found.append((float(start), end, level, bool(rising)))
    return found


@analysis
def analyze_track(measurements: Sequence[Meas]) -> AnalysisTrack:
    """Measure the track phases' time constant, on-resistance, bandwidth, and remaining error at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        transition = float(tb.clock_transition_time_s)
        time_s, output = measurement.time_s, measurement.v[Nets.vout.name]
        constants: dict[bool, list[float]] = {True: [], False: []}
        errors: dict[bool, list[float]] = {True: [], False: []}
        for start, end, level, rising in _tracks(measurement):
            error, error_s = calc.clip(np.abs(output - level), time_s, start, end)
            # not in the reference texts: tau as the time between the track error's 1/e and 1/e^2
            # of its largest value from the clock's mid-supply crossing on (its value there, unless
            # the closing switch's own charge first kicks the output further away): the exponential
            # alone, its turn-on (some 40 ps, which reads as 40 ohm into 1 pF) excluded
            peak = int(np.argmax(error))
            error, error_s = error[peak:], error_s[peak:]
            first = calc.cross(error, error_s, float(error[0]) / math.e, edge="falling")
            second = calc.cross(error, error_s, float(error[0]) / math.e**2, edge="falling")
            constants[rising].append(float(second[0]) - float(first[0]) if len(first) and len(second) else math.nan)
            # [Razavi-ADC] Sec. 3.9.1, p. 53: the error |V_in - V_out| left when acquisition ends
            errors[rising].append(abs(calc.value(output, time_s, end - transition) - level))
        # the slower direction's time constant: the one that sets the acquisition
        tau = _worse(constants)
        rows.append(
            (
                float(tb.vdd),
                float(tb.input_voltage),
                tau,
                # [Razavi-Analog] Eq. (13.31), p. 552: tau = R_on C_H, solved for R_on
                tau / float(tb.cload),
                # [Razavi-ADC] Eq. (3.26), p. 29: the RC sampler's -3 dB at R_on C_1 omega = 1
                1 / (2 * math.pi * tau),
                _worse(errors),
            )
        )
    vdd_v, vin_v, tau_s, resistance, bandwidth, error_v = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTrack(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        tau_s=tau_s,
        ron_ohm=resistance,
        bandwidth_hz=bandwidth,
        track_error_v=error_v,
    )


@analysis
def analyze_hold(measurements: Sequence[Meas]) -> AnalysisHold:
    """Measure the hold phases' pedestal, droop, and input feedthrough at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s = measurement.time_s
        clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.vin, Nets.vout))
        rises = calc.cross(clock, time_s, vdd / 2, edge="rising")
        steps = calc.cross(data, time_s, float(tb.input_voltage), edge="either")
        pedestals, droops, feedthroughs = [], [], []
        for fall in calc.cross(clock, time_s, vdd / 2, edge="falling")[1:]:
            following, stepped = rises[rises > fall], steps[steps > fall]
            if not len(following) or not len(stepped) or stepped[0] > following[0]:
                continue
            step, release = float(stepped[0]), float(following[0])
            held_s, before_s, after_s = (fall + step) / 2, step - transition, release - transition
            held = calc.value(output, time_s, held_s)
            before = calc.value(output, time_s, before_s)
            # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold, the held output's slope
            droop = (before - held) / (before_s - held_s)
            # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal the opening switch leaves on C_H,
            # the held output's droop since the clock fell taken back to the opening
            pedestals.append(held - droop * (held_s - fall) - calc.value(output, time_s, fall - transition))
            droops.append(droop)
            # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough, the held output's change over the
            # input's while the switch is off, its droop over the same time taken out
            feedthroughs.append(
                (calc.value(output, time_s, after_s) - before - droop * (after_s - before_s))
                / (calc.value(data, time_s, after_s) - calc.value(data, time_s, before_s))
            )
        rows.append(
            (
                vdd,
                float(tb.input_voltage),
                *(float(np.median(values)) if values else math.nan for values in (pedestals, droops, feedthroughs)),
            )
        )
    vdd_v, vin_v, pedestal_v, droop, feedthrough = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisHold(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        pedestal_v=pedestal_v,
        droop_v_per_s=droop,
        feedthrough=feedthrough,
    )


@analysis
def analyze_boost(measurements: Sequence[Meas]) -> AnalysisBoost:
    """Measure a bootstrapped switch's V_GS at the end of each track phase and its gate's peak."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        time_s, gate = measurement.time_s, measurement.v.get("gate")
        vgs, peak = math.nan, math.nan
        if gate is not None:
            data = measurement.v[Nets.vin.name]
            transition = float(tb.clock_transition_time_s)
            # [Razavi-ADC] Sec. 3.8.1, p. 43: the switch's V_GS while tracking, the boosted gate over the input
            values = [
                calc.value(gate, time_s, end - transition) - calc.value(data, time_s, end - transition)
                for _, end, _, _ in _tracks(measurement)
            ]
            vgs = float(np.median(values)) if values else math.nan
            peak = calc.ymax(gate)
        rows.append((float(tb.vdd), float(tb.input_voltage), vgs, peak))
    vdd_v, vin_v, vgs_v, gate_max_v = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisBoost(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        vgs_v=vgs_v,
        gate_max_v=gate_max_v,
    )


@analysis
def analyze_stress(measurements: Sequence[Meas]) -> AnalysisStress:
    """Measure the largest terminal voltages and junction forward bias of the switch's transistors
    over each run's operating point and transient (NaN for a run that did not save them)."""

    identity = measurement_identity(measurements)
    oxide = (oppoint.Terminals.GS, oppoint.Terminals.GD, oppoint.Terminals.DS)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        found = (math.nan, math.nan, math.nan)
        if any(name.endswith(":vgs") for name in measurement.v):
            devices = oppoint.mos_devices(netlist(tb.params))
            points = [measurement, *(measurement.sweeps[name] for name in ("opdc",) if name in measurement.sweeps)]
            stress = oppoint.stress(points, devices, nominal_v=float(tb.vdd))
            pairs = stress.terminal_v.values()
            found = (
                max(float(np.max(pair[kind])) for pair in pairs for kind in oxide),
                max(float(np.max(pair[oppoint.Terminals.GB])) for pair in pairs),
                max(float(np.max(bias)) for junction in stress.junction_v.values() for bias in junction.values()),
            )
        rows.append((float(tb.vdd), float(tb.input_voltage), *found))
    vdd_v, vin_v, terminal_v, gate_bulk_v, junction_v = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisStress(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        terminal_v=terminal_v,
        gate_bulk_v=gate_bulk_v,
        junction_v=junction_v,
    )


@analysis
def analyze_acquisition(measurements: Sequence[Meas]) -> AnalysisAcquisition:
    """Measure the time each track phase takes to settle to half an LSB at each resolution, and
    the error left at its end, the worse of the rising and the falling step."""

    identity = measurement_identity(measurements)
    rows, times = [], []
    for measurement in measurements:
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s, output = measurement.time_s, measurement.v[Nets.vout.name]
        settles: dict[int, dict[bool, list[float]]] = {bits: {True: [], False: []} for bits in ACQUISITION_BITS}
        errors: dict[bool, list[float]] = {True: [], False: []}
        for start, end, level, rising in _tracks(measurement):
            # up to the clock's fall starting: from there its feedthrough moves the output
            clipped, clipped_s = calc.clip(output, time_s, start, end - transition)
            for bits in ACQUISITION_BITS:
                # [Razavi-ADC] Eq. (3.82), p. 54: t_acq, |V_in - V_out| within half an LSB, the LSB
                # here the supply over 2^N, counted from the clock's rising mid-supply crossing
                settled = calc.settlingTime(clipped, clipped_s, final=level, absolute_tolerance=vdd / 2 ** (bits + 1))
                settles[bits][rising].append(settled - start)
            # [Razavi-ADC] Fig. 3.50, p. 53: the error |V_in - V_out| left as acquisition ends
            errors[rising].append(abs(calc.value(output, time_s, end - transition) - level))
        times.append([_worse(settles[bits]) for bits in ACQUISITION_BITS])
        rows.append((vdd, float(tb.input_voltage), float(tb.input_step_v), _worse(errors)))
    vdd_v, vin_v, step_v, error_v = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisAcquisition(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        step_v=step_v,
        bits=np.asarray(ACQUISITION_BITS, dtype=np.float64),
        acquisition_s=np.asarray(times, dtype=np.float64),
        track_error_v=error_v,
    )


def _held(measurement: Meas) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Each hold phase after the first: the input and its slope at the clock's falling mid-supply
    crossing, and the held output halfway through the hold."""
    tb = measurement.param
    vdd, time_s = float(tb.vdd), measurement.time_s
    clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.vin, Nets.vout))
    rises = calc.cross(clock, time_s, vdd / 2, edge="rising")
    # each interval's slope, at its middle
    slope, middles = calc.deriv(data, time_s), (time_s[1:] + time_s[:-1]) / 2
    found = []
    for fall in calc.cross(clock, time_s, vdd / 2, edge="falling")[1:]:
        following = rises[rises > fall]
        if not len(following):
            continue
        middle = (float(fall) + float(following[0])) / 2
        found.append(
            (
                calc.value(data, time_s, float(fall)),
                calc.value(slope, middles, float(fall)),
                calc.value(output, time_s, middle),
            )
        )
    vin, rate, held = (np.asarray(column, dtype=np.float64) for column in zip(*found))
    return vin, rate, held, np.full(len(vin), float(tb.cload))


def _harmonics(held: np.ndarray, cycles: int, orders: int) -> float:
    """The harmonic distortion of ``held``, coherent samples of ``cycles`` cycles: the power of the
    2nd to ``orders``-th harmonic (each folded onto its bin) over the fundamental's, in dB."""
    _, amplitude = calc.dft(held - float(np.mean(held)), 1.0)
    count = len(held)
    bins = [(order * cycles) % count for order in range(2, orders + 1)]
    folded = [min(index, count - index) for index in bins]
    harmonic = sum(abs(amplitude[index]) ** 2 for index in folded if 0 < index)
    return calc.thd(abs(amplitude[cycles]) ** 2, harmonic)


@analysis
def analyze_sine(measurements: Sequence[Meas], *, track: AnalysisTrack, hold: AnalysisHold) -> AnalysisSine:
    """Measure each sine run's held samples: their harmonic distortion, their distance from the
    behavioral model's held values (the level runs' on-resistance and pedestal, ``track`` and
    ``hold``), and the sampling instant the rest of that distance implies."""

    identity = measurement_identity(measurements)
    settled = np.isfinite(track.ron_ohm)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vin, rate, held, load = _held(measurement)
        period = float(tb.clock_period_s)
        cycles = round(float(tb.sine_frequency_hz) * period * len(held))
        # [Razavi-ADC] Eq. (3.85), p. 55: the held samples' harmonics over their fundamental
        thd_db = _harmonics(held, cycles, orders=5)
        # [Razavi-ADC] Eq. (3.26), p. 29: the first-order track lags by R_on C_1, so the held value
        # is V_in - R(V_in) C dV_in/dt (flow.samp.model.Model.sample); plus the pedestal at V_in
        resistance = np.interp(vin, track.vin_v[settled], track.ron_ohm[settled]) if settled.any() else np.nan
        pedestal = np.interp(vin, hold.vin_v[settled], hold.pedestal_v[settled]) if settled.any() else np.nan
        rest = held - (vin - resistance * load * rate + pedestal)
        # [Razavi-ADC] Eq. (3.86), p. 55: an instant later by dT moves the held value by dT dV_in/dt;
        # the rest fitted as (a + b V_in) dV_in/dt (least squares)
        basis = np.stack([rate, rate * vin], axis=1)
        fit = np.linalg.lstsq(basis, rest, rcond=None)[0] if np.all(np.isfinite(rest)) else (math.nan, math.nan)
        rows.append(
            (
                float(tb.vdd),
                float(tb.input_voltage),
                float(tb.sine_frequency_hz),
                thd_db,
                float(np.max(np.abs(rest))),
                float(fit[0]),
                float(fit[1]),
            )
        )
    vdd_v, vin_v, frequency, thd, error, aperture, aperture_per_v = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisSine(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        frequency_hz=frequency,
        thd_db=thd,
        model_error_v=error,
        aperture_s=aperture,
        aperture_s_per_v=aperture_per_v,
    )


@analysis
def analyze_dac(measurements: Sequence[Meas]) -> AnalysisDac:
    """Measure the held output's slope while the DAC's step holds it moved, at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, edge = float(tb.vdd), float(tb.clock_transition_time_s)
        period, high = float(tb.clock_period_s), float(tb.clock_high_time_s)
        time_s, clock, output = measurement.time_s, measurement.v[Nets.clk.name], measurement.v[Nets.vout.name]
        hold = period - high - 2 * edge
        droops = []
        for fall in calc.cross(clock, time_s, vdd / 2, edge="falling")[1:]:
            # the stepped hold: from a step's edge after it rose (a quarter into the hold, an edge
            # later) to the same before it falls back (a quarter before the hold's end)
            first, last = float(fall) + edge / 2 + hold / 4 + 2 * edge, float(fall) + edge / 2 + 3 * hold / 4 - edge
            if last >= float(time_s[-1]):
                continue
            # [Pelgrom] Eq. (8.3), p. 387: the held output's slope, its leakage over C
            droops.append((calc.value(output, time_s, last) - calc.value(output, time_s, first)) / (last - first))
        rows.append(
            (vdd, float(tb.input_voltage), float(tb.dac_step_v), float(np.median(droops)) if droops else math.nan)
        )
    vdd_v, vin_v, step_v, droop = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisDac(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        step_v=step_v,
        droop_v_per_s=droop,
    )


@analysis
def analyze_energy(measurements: Sequence[Meas]) -> AnalysisEnergy:
    """Measure the energy the supply and both clocks' sources deliver over each whole period after
    the first, at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        period, time_s = float(tb.clock_period_s), measurement.time_s
        # [Baker] Eq. (11.15), p. 355: the average power V_DD I_avg; over a period, its energy, each
        # source's voltage times the current drawn from it
        power = np.zeros_like(time_s)
        for net, current in measurement.i.items():
            power = power + measurement.v.get(net, np.full_like(time_s, float(tb.vdd))) * current
        energies = [
            calc.integ(*calc.clip(power, time_s, start, start + period))
            for start in np.arange(1, int(tb.periods)) * period + float(tb.clock_delay_s)
            if start + period <= float(time_s[-1])
        ]
        rows.append((float(tb.vdd), float(tb.input_voltage), float(np.median(energies)) if energies else math.nan))
    vdd_v, vin_v, energy = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisEnergy(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        energy_per_cycle_j=energy,
    )


def _largest(values: np.ndarray, mask: np.ndarray | None = None) -> float:
    """The largest magnitude among the finite ``values`` (where ``mask``), NaN where there is none."""
    kept = np.abs(values[np.isfinite(values) & (np.ones(len(values), bool) if mask is None else mask)])
    return float(kept.max()) if kept.size else math.nan


def metrics(
    *,
    track: AnalysisTrack,
    hold: AnalysisHold,
    supply: AnalysisTrack,
    supply_hold: AnalysisHold | None = None,
    corners: AnalysisTrack | None = None,
    corners_hold: AnalysisHold | None = None,
    hot: AnalysisHold | None = None,
    skew: AnalysisHold | None = None,
    boost: AnalysisBoost | None = None,
    stress: AnalysisStress | None = None,
    acquisition: AnalysisAcquisition | None = None,
    sine: AnalysisSine | None = None,
    dac: AnalysisDac | None = None,
    energy: AnalysisEnergy | None = None,
) -> dict[str, float]:
    """The record's numbers: from the input level's runs (``track``, ``hold``) the on-resistance,
    bandwidth, track error, pedestal, droop and feedthrough at the nominal input, the largest
    on-resistance and pedestal where a point settled, the input range over which it settles; from
    the supply's (``supply``, ``supply_hold``) the largest on-resistance and pedestal; and where
    given, the corners' (``corners``, ``corners_hold``, the ``hot`` droop), the pedestal with a
    late complementary clock (``skew``), the boost's V_GS over the input and the gate's peak
    (``boost``), the devices' largest voltages (``stress``), the acquisition times and the
    full-scale track error (``acquisition``), the sines' distortion, their distance from the model
    and the aperture (``sine``, low tone first), the droop under the DAC's step (``dac``) and the
    energy a cycle (``energy``)."""

    nominal = int(np.argmin(np.abs(track.vin_v - NOMINAL_VIN * track.vdd_v)))
    settled = np.isfinite(track.ron_ohm)
    # not in the reference texts: the input range, the span of the contiguous input levels whose
    # track phase settles to 1/e^2 within the track window: those around the nominal one where it
    # settles, else the widest such run
    runs, first = [], None
    for index, value in enumerate([*settled, False]):
        if value and first is None:
            first = index
        elif not value and first is not None:
            runs.append((first, index - 1))
            first = None
    held = [run for run in runs if run[0] <= nominal <= run[1]]
    widest = held or sorted(runs, key=lambda run: (run[0] - run[1], run[0]))
    span = float(track.vin_v[widest[0][1]] - track.vin_v[widest[0][0]]) if widest else 0.0
    # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough in dB
    feedthrough_db = 20 * np.log10(np.abs(hold.feedthrough))
    found = {
        # [Razavi-Analog] Eq. (2.11), p. 15: R_on, at the nominal input
        "ron_ohm": float(track.ron_ohm[nominal]),
        # [Razavi-Analog] Eq. (13.22), p. 547: R_on over the input level, its largest
        "ron_max_ohm": _largest(track.ron_ohm),
        "input_range_v": span,
        # [Razavi-ADC] Eq. (3.26), p. 29: -3 dB at R_on C_1 omega = 1
        "bandwidth_hz": float(track.bandwidth_hz[nominal]),
        # [Razavi-ADC] Sec. 3.9.1, p. 53: |V_in - V_out| as tracking ends
        "track_error_v": float(track.track_error_v[nominal]),
        # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal; and its largest where a point settled
        "pedestal_v": float(hold.pedestal_v[nominal]),
        "pedestal_max_v": _largest(hold.pedestal_v, settled),
        # [Pelgrom] Eq. (8.3), p. 387: the droop
        "droop_v_per_s": float(hold.droop_v_per_s[nominal]),
        "feedthrough_db": float(feedthrough_db[nominal]),
        # not in the reference texts: the largest R_on over the 90/100/110 % supply runs at the nominal input
        "ron_max_supply_ohm": _largest(supply.ron_ohm),
    }
    if supply_hold is not None:
        # not in the reference texts: the largest |pedestal| over the 90/100/110 % supply runs
        found["pedestal_max_supply_v"] = _largest(supply_hold.pedestal_v)
    if corners is not None and corners_hold is not None:
        # not in the reference texts: the largest R_on and |pedestal| over the slow, fast and hot runs
        found["ron_max_corner_ohm"] = _largest(corners.ron_ohm)
        found["pedestal_max_corner_v"] = _largest(corners_hold.pedestal_v)
    if hot is not None:
        # [Pelgrom] Eq. (8.3), p. 387: the droop, at the hot corner
        found["droop_hot_v_per_s"] = float(hot.droop_v_per_s[0])
    if skew is not None:
        # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal, the complementary clock an edge late
        found["pedestal_skew_v"] = float(skew.pedestal_v[0])
    if boost is not None:
        # [Razavi-ADC] Eq. (3.72), p. 50: the boosted V_GS over the input, its least and largest
        boosted = np.isfinite(boost.vgs_v)
        found["vgs_min_v"] = float(boost.vgs_v[boosted].min()) if boosted.any() else math.nan
        found["vgs_max_v"] = float(boost.vgs_v[boosted].max()) if boosted.any() else math.nan
        # [Razavi-ADC] Sec. 3.8.1, p. 43: the gate's peak, V_CM + V_b about the supply
        found["gate_max_v"] = _largest(boost.gate_max_v)
    if stress is not None:
        # [Razavi-ADC] Sec. 3.8.2, p. 48: the largest terminal voltages, against the technology's
        found["terminal_max_v"] = _largest(stress.terminal_v)
        found["gate_bulk_max_v"] = _largest(stress.gate_bulk_v)
        # [Razavi-Analog] Sec. 2.1, p. 9: the largest forward bias of a source or drain junction
        forward = stress.junction_v[np.isfinite(stress.junction_v)]
        found["junction_forward_max_v"] = float(forward.max()) if forward.size else math.nan
    if acquisition is not None:
        # [Razavi-ADC] Eq. (3.82), p. 54: t_acq to half an LSB at each resolution
        for index, bits in enumerate(acquisition.bits):
            found[f"acquisition_{int(bits)}b_s"] = float(acquisition.acquisition_s[0, index])
        # [Razavi-ADC] Fig. 3.50, p. 53: the error a full-scale step leaves as the ADC's track window ends
        found["track_error_full_scale_v"] = float(acquisition.track_error_v[0])
    if sine is not None:
        # [Razavi-ADC] Eq. (3.85), p. 55: the held samples' distortion, the low tone's and the high one's
        found["thd_low_db"], found["thd_high_db"] = float(sine.thd_db[0]), float(sine.thd_db[-1])
        # not in the reference texts: the largest distance of a held sample from the behavioral model's
        found["model_error_v"] = _largest(sine.model_error_v)
        # [Pelgrom] Sec. 8.3.2, p. 390: the signal-dependent aperture delay, from the high tone
        found["aperture_s"], found["aperture_s_per_v"] = float(sine.aperture_s[-1]), float(sine.aperture_s_per_v[-1])
    if dac is not None:
        # [Pelgrom] Eq. (8.3), p. 387: the largest |droop| while the DAC's step holds the output moved
        found["droop_conversion_v_per_s"] = _largest(dac.droop_v_per_s)
    if energy is not None:
        # [Baker] Eq. (11.15), p. 355: the energy a clock period takes
        found["energy_per_cycle_j"] = float(energy.energy_per_cycle_j[0])
    return found
