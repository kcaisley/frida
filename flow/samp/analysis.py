"""The sampler's analyses: each from a run's measurement (``flow.pipeline.Meas``, its signals on
Spectre's own time axis) of a testbench, and the record's metrics.

A run tracks while ``clk`` is high; its input steps once per period in the middle of each hold
phase and, in the level runs, onto its level in the middle of each track phase. Every figure is a
median over the periods after the first (whose track phase starts from an arbitrary held value);
where a figure differs between the input's rising and falling steps, the median of each direction
and then the worse of the two. A track phase settles from its last step (the input's inside the
phase, else the switch's closing): its time constant where the switch's gate drive has settled,
the on-resistance into the load, and what is left at the end (``analyze_track``); a bootstrap's boosted gate (``analyze_boost``); a full-scale step's
acquisition time (``analyze_acquisition``). A hold phase shows the pedestal the opening switch
leaves, the droop before the input steps, and how much of that step feeds through
(``analyze_hold``); over the ADC's long hold, the droop, with the DAC's first step moving the held
output or without (``analyze_droop``). A sine's held samples show the switch's distortion and how
far the behavioral model's held value is from them (``analyze_sine``). Every run that saved its
devices' values shows their largest voltages (``analyze_stress``); a clock period's energy
(``analyze_energy``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.circuit import oppoint
from flow.pipeline import Meas, analysis, measurement_identity

from .params import ACQUISITION_BITS, ERROR_SETTLED, NOMINAL_VIN, VGS_SETTLED
from .subckt import Nets, netlist
from .types import (
    AnalysisAcquisition,
    AnalysisBoost,
    AnalysisDroop,
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
    # not in the reference texts: a figure of a run is max over the step directions (rising,
    # falling) of the median over that direction's track phases
    # Terms: the phases are the run's track phases after the first, by the direction the input
    #   stepped to their level (``_tracks``).
    # Holds for: a run with at least one measured phase in a direction; a direction whose median
    #   is NaN makes the figure NaN (the slower direction sets the acquisition).
    medians = [
        float(np.median(values[1:] if len(values) > 1 else values)) for values in by_direction.values() if values
    ]
    if not medians or any(math.isnan(value) for value in medians):
        return math.nan
    return max(medians) if slower else min(medians)


def _tracks(measurement: Meas) -> list[tuple[float, float, float, bool]]:
    """Each track phase after the first: its clock's rising and falling mid-supply crossings, the
    input level it settles to (the input as the clock starts to fall), and whether the input
    stepped up to it: inside the phase where it steps there, else from the level a period before
    (the held output, a pedestal off, may lie on either side of it)."""
    tb = measurement.param
    vdd, period, transition = float(tb.vdd), float(tb.clock_period_s), float(tb.clock_transition_time_s)
    time_s = measurement.time_s
    clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.vin, Nets.vout))
    falls = calc.cross(clock, time_s, vdd / 2, edge="falling")
    found = []
    for start in calc.cross(clock, time_s, vdd / 2, edge="rising")[1:]:
        ends = falls[falls > start]
        if not len(ends):
            continue
        end = float(ends[0])
        # not in the reference texts: the level a track phase settles to is vin a clock edge
        # before the clock's falling crossing; the input stepped up to it where it is above vin at
        # the phase's start (a step inside the phase), else above the level a period before
        # Terms: vin the bench's input; a clock edge tb.clock_transition_time_s.
        # Holds for: an input that is still from its step to the end of the phase.
        settled = end - transition
        level = calc.value(data, time_s, settled)
        opening = calc.value(data, time_s, float(start))
        before = calc.value(data, time_s, settled - period) if settled - period >= time_s[0] else math.nan
        if not math.isclose(level, opening, rel_tol=0.0, abs_tol=1e-9 * vdd):
            rising = level > opening
        else:
            rising = level >= (calc.value(output, time_s, float(start)) if math.isnan(before) else before)
        found.append((float(start), end, level, bool(rising)))
    return found


def _settled_s(measurement: Meas, start: float, end: float) -> float:
    """The instant in the track phase from ``start`` to ``end`` from which the switch's gate drive
    stays within ``VGS_SETTLED`` of its value as the clock starts to fall: a bootstrap's saved
    ``gate`` over the input, else each clock over the input. NaN where the drive is still outside
    that band at the last sample before then."""
    # not in the reference texts: V_GS settled where |V_GS(t) - V_GS(end)| <= VGS_SETTLED |V_GS(end)|
    # from t on
    # Terms: V_GS the gate of MN (``gate``, a bootstrap's A; ``clk`` for a plain NMOS, ``clk_b`` for
    #   MP) over vin; its end value read a clock edge before the clock's falling crossing.
    # Ours against the source: [Razavi-Analog] Eq. (13.32), p. 552 has the gate at V_DD from the
    #   start; ours has a clock edge and a bootstrap's gate that rises with its bottom plate.
    # Holds for: a run that saves the gate it drives the switch with (flow.samp.sim.BOOST_SAVES).
    tb = measurement.param
    time_s, data = measurement.time_s, measurement.v[Nets.vin.name]
    names = ("gate",) if "gate" in measurement.v else (Nets.clk.name, Nets.clk_b.name)
    latest = start
    for name in names:
        if name not in measurement.v:
            continue
        drive, drive_s = calc.clip(measurement.v[name] - data, time_s, start, end - float(tb.clock_transition_time_s))
        outside = np.flatnonzero(np.abs(drive - drive[-1]) > VGS_SETTLED * abs(float(drive[-1])))
        if not len(outside):
            continue
        if outside[-1] + 1 >= len(drive) - 1:
            return math.nan
        latest = max(latest, float(drive_s[outside[-1] + 1]))
    return latest


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
        data = measurement.v[Nets.vin.name]
        for start, end, level, rising in _tracks(measurement):
            # not in the reference texts: the settling read is that of the phase's last step: where
            # the input steps inside the phase (vin crosses halfway between its level at the
            # clock's rising crossing and the level it settles to), from a clock edge before that;
            # else from the clock's rising crossing
            # Terms: vin the bench's input; a clock edge tb.clock_transition_time_s, the step's own;
            #   the window ends a clock edge before the clock's falling crossing (from there the
            #   opening switch moves vout).
            # Holds for: at most one input step inside a track phase.
            opening, since = calc.value(data, time_s, start), start
            if not math.isclose(level, opening, rel_tol=0.0, abs_tol=1e-9 * float(tb.vdd)):
                stepped = calc.cross(*calc.clip(data, time_s, start, end), (opening + level) / 2, edge="either")
                since = max(start, float(stepped[0]) - transition) if len(stepped) else start
            error, error_s = calc.clip(np.abs(output - level), time_s, since, end - transition)
            # [Razavi-Analog] Eq. (13.31), p. 552: tau = R_on C_H, the on switch's time constant
            # Terms: tau the time the track error |vout - vin| takes to fall by a factor e, from the
            #   later of its 1/e point (of its largest value since the phase's last step: at the
            #   input's step inside the phase, else at the clock's crossing or after the closing
            #   switch's kick) and the instant the gate drive has settled (``_settled_s``); R_on
            #   MN's (and MP's) channel; C_H the load on vout (tb.cload).
            # Ours against the source: the source's switch is on from the start; ours turns on
            #   over a clock edge, a bootstrap over its bottom plate's rise, so the window waits for
            #   the gate drive: the turn-on is in the acquisition times
            #   (``analyze_acquisition``), not here.
            # Holds for: an error that falls by a further factor e inside the phase after the gate
            #   drive has settled, and is still ERROR_SETTLED of its largest or more there; NaN
            #   otherwise.
            peak = int(np.argmax(error))
            error, error_s = error[peak:], error_s[peak:]
            first = calc.cross(error, error_s, float(error[0]) / math.e, edge="falling")
            settled = _settled_s(measurement, start, end)
            constant = math.nan
            if len(first) and math.isfinite(settled) and max(float(first[0]), settled) < float(error_s[-1]):
                begin = max(float(first[0]), settled)
                later, later_s = calc.clip(error, error_s, begin, float(error_s[-1]))
                second = calc.cross(later, later_s, float(later[0]) / math.e, edge="falling")
                readable = float(later[0]) >= ERROR_SETTLED * float(error[0])
                constant = float(second[0]) - begin if len(second) and readable else math.nan
            constants[rising].append(constant)
            # [Razavi-ADC] Sec. 3.9.1, p. 53: the error |V_in - V_out| left when acquisition ends
            # Terms: V_in vin, V_out vout, a clock edge before the clock's falling crossing (from
            #   there the clock's feedthrough moves vout).
            # Ours against the source: the source's is a full-scale step's; this one is what the
            #   level runs' small step leaves (the full-scale one: ``analyze_acquisition``).
            # Holds for: the run's own step and track window.
            errors[rising].append(abs(calc.value(output, time_s, end - transition) - level))
        # the slower direction's time constant: the one that sets the acquisition
        tau = _worse(constants)
        rows.append(
            (
                float(tb.vdd),
                float(tb.input_voltage),
                tau,
                # [Razavi-Analog] Eq. (13.31), p. 552: tau = R_on C_H, solved for R_on = tau / C_H
                # Terms: tau as above; C_H tb.cload, the bench's load capacitor on vout.
                # Ours against the source: vout also carries the switch's own drain capacitance
                #   and, with dummies, theirs, which C_H leaves out: R_on reads high by their
                #   share of the load (a bound from above).
                # Holds for: a load large against the switch's own capacitance.
                tau / float(tb.cload),
                # [Razavi-ADC] Eq. (3.26), p. 29: the RC sampler's attenuation 1 / sqrt(R_on^2 C_1^2
                # omega^2 + 1), 3 dB down at R_on C_1 omega = 1: f = 1 / (2 pi tau)
                # Terms: R_on C_1 the measured tau (the on switch into tb.cload).
                # Ours against the source: none (a first-order track).
                # Holds for: the load tau is measured into.
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
        pedestals, droops, feedthroughs = [], [], []
        for fall in calc.cross(clock, time_s, vdd / 2, edge="falling")[1:]:
            following = rises[rises > fall]
            if not len(following):
                continue
            release = float(following[0])
            # not in the reference texts: the input's step in this hold phase is where vin crosses
            # (V_fall + V_rise) / 2, halfway between its levels as the clock falls and as it rises
            # again (no step where the two are the same)
            # Terms: V_fall, V_rise vin at the clock's falling crossing and at its next rising one.
            # Holds for: one input step a hold phase, in either direction, from or onto any level.
            first, last = calc.value(data, time_s, float(fall)), calc.value(data, time_s, release)
            if math.isclose(first, last, rel_tol=0.0, abs_tol=1e-9 * vdd):
                continue
            stepped = calc.cross(*calc.clip(data, time_s, float(fall), release), (first + last) / 2, edge="either")
            if not len(stepped):
                continue
            step = float(stepped[0])
            held_s, before_s, after_s = (fall + step) / 2, step - transition, release - transition
            held = calc.value(output, time_s, held_s)
            before = calc.value(output, time_s, before_s)
            # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold, a linear fall: its slope
            # Terms: the slope of vout from halfway between the clock's fall and the input's step
            #   to a clock edge before that step; I_leak the off switch's and its junctions'
            #   leakage, C_hold tb.cload.
            # Ours against the source: read in volts a second, not over T_hold.
            # Holds for: a hold whose leakage is constant over the window (the level runs' short
            #   one; the ADC's long one is ``analyze_droop``'s).
            droop = (before - held) / (before_s - held_s)
            # [Razavi-Analog] Eq. (13.26), p. 550: Delta V = W L C_ox (V_DD - V_in - V_TH) / (2 C_H),
            # the pedestal the opening switch's channel charge leaves on C_H
            # Terms: Delta V the held vout (halfway to the input's step, its droop since the
            #   clock's fall taken back) less vout a clock edge before the clock's fall; the charge
            #   MN's (MP's) channel's, less what the dummies take.
            # Ours against the source: the source's is half the channel charge alone; the measured
            #   step also holds the clock's feedthrough through the overlap capacitance
            #   ([Razavi-ADC] Eq. (3.45), p. 35) and whatever split the channel charge takes.
            # Holds for: the bench's clock edges and ideal input source.
            pedestals.append(held - droop * (held_s - fall) - calc.value(output, time_s, fall - transition))
            droops.append(droop)
            # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough, the held output's change over the
            # input's while the switch is off
            # Terms: vout a clock edge before the next track phase less vout a clock edge before the
            #   input's step, its droop over that time taken out, over vin's change between the
            #   same instants (V/V).
            # Ours against the source: the source names the coupling path (the off switch's
            #   drain-source capacitance) without an expression.
            # Holds for: the hold-phase input step of the level runs.
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
            # [Razavi-ADC] Sec. 3.8.1, p. 43: V_GS = V_A - V_in, held at V_b as V_in swings
            # Terms: V_A ``gate`` (MN's gate), V_in vin, both a clock edge before the clock's fall.
            # Ours against the source: the source's V_b is an ideal battery; ours is V_b' of Eq.
            #   (3.70), p. 50, less what Eq. (3.72) takes with V_in.
            # Holds for: a bootstrapped switch (a run that saved ``gate``).
            values = [
                calc.value(gate, time_s, end - transition) - calc.value(data, time_s, end - transition)
                for _, end, _, _ in _tracks(measurement)
            ]
            vgs = float(np.median(values)) if values else math.nan
            # [Razavi-ADC] Sec. 3.8.1, p. 43: the gate's peak, V_in + V_b, above the supply
            # Terms: the largest of ``gate`` over the whole run.
            # Holds for: a bootstrapped switch.
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
def analyze_stress(measurements: Sequence[Meas], *, track: AnalysisTrack) -> AnalysisStress:
    """Measure the largest terminal voltages and junction forward bias of the switch's transistors
    over each run's operating point and transient (NaN for a run that did not save them), against
    the nominal supply, the level runs' (``track``): a supply corner's own is not the limit's base."""

    identity = measurement_identity(measurements)
    # not in the reference texts: the nominal supply is the median of the level runs' supplies
    # (all at the nominal one), the base of the stress limit, nominal times the largest supply
    # corner (flow.circuit.oppoint.SUPPLY_CORNER_MAX)
    # Terms: the level runs' supplies ``track.vdd_v``.
    # Holds for: level runs at the nominal supply (flow.samp.runs.testbenches).
    nominal_v = float(np.median(track.vdd_v))
    # [Razavi-ADC] Sec. 3.8.2, p. 48: a device whose terminal voltages exceed the technology's is
    # stressed: the largest |V_GS|, |V_GD| and |V_DS| of any transistor over the run
    # Terms: every transistor of the switch (flow.samp.subckt.netlist), its saved V_GS, V_DS.
    # Ours against the source: |V_GB| is kept apart (``gate_bulk_v``): under an inverted channel
    #   the oxide carries V_GS, and whether V_GB counts is a kit's rule.
    # Holds for: a run that saved its devices' values (tb.oppoint).
    oxide = (oppoint.Terminals.GS, oppoint.Terminals.GD, oppoint.Terminals.DS)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        found = (math.nan, math.nan, math.nan)
        if any(name.endswith(":vgs") for name in measurement.v):
            devices = oppoint.mos_devices(netlist(tb.params))
            points = [measurement, *(measurement.sweeps[name] for name in ("opdc",) if name in measurement.sweeps)]
            stress = oppoint.stress(points, devices, nominal_v=nominal_v)
            pairs = stress.terminal_v.values()
            # [Razavi-Analog] Sec. 2.1, p. 9: the junctions to the bulk kept reverse biased: the
            # largest forward bias of any source or drain junction over the run (the last of the three)
            # Terms: V_BS and V_BD = V_BS - V_DS of each NMOS, their negatives of each PMOS
            #   (flow.circuit.oppoint.stress).
            # Holds for: a run that saved its devices' values.
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
                # [Razavi-ADC] Eq. (3.82), p. 54: t_acq = R_on1 C_1 ln 2^(N+1), the time for
                # |V_in - V_out| to fall within V_FS / 2^(N+1) (half an LSB)
                # Terms: read off the transient: from the clock's rising mid-supply crossing until
                #   |vin - vout| stays within V_DD / 2^(N+1); V_FS taken as the supply tb.vdd.
                # Ours against the source: the source's is the ideal exponential's; the measured
                #   one holds the turn-on (the clock's edge, a bootstrap's bottom plate's rise).
                # Holds for: the run's step (the ADC's full scale a side) and track window.
                settled = calc.settlingTime(clipped, clipped_s, final=level, absolute_tolerance=vdd / 2 ** (bits + 1))
                settles[bits][rising].append(settled - start)
            # [Razavi-ADC] Fig. 3.50, p. 53: Delta V, the error |V_in - V_out| left as acquisition ends
            # Terms: vin and vout a clock edge before the clock's falling crossing.
            # Ours against the source: none.
            # Holds for: the ADC's track window and its full-scale step.
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
    # not in the reference texts: dV_in/dt as the input's difference over each output interval, at
    # the interval's middle, read at the clock's falling crossing
    # Terms: V_in vin on the run's own time axis (a sample every tb.waveform_sample_interval_s).
    # Holds for: an input that is a straight line over an interval (a sine far below the strobe rate).
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
    # [Razavi-ADC] Eq. (3.85), p. 55: HD_tot, the harmonics' power over the fundamental's
    # Terms: the fundamental the DFT bin ``cycles`` of the held samples; harmonic k the bin
    #   (k cycles) mod N, folded about N / 2 (the sampled spectrum's alias), k = 2 to ``orders``.
    # Ours against the source: the source sums the harmonics it reads off a spectrum; ours takes
    #   the first ``orders`` and leaves out one that folds onto DC.
    # Holds for: coherent sampling (a whole number of cycles in the N samples, the two coprime).
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
    low, high = _settled_span(track)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vin, rate, held, load = _held(measurement)
        # the model's error and the aperture over the samples inside the range the level runs settle over
        inside = (vin >= low) & (vin <= high)
        period = float(tb.clock_period_s)
        cycles = round(float(tb.sine_frequency_hz) * period * len(held))
        # [Razavi-ADC] Eq. (3.85), p. 55: the held samples' harmonics over their fundamental (``_harmonics``)
        thd_db = _harmonics(held, cycles, orders=5)
        # [Razavi-ADC] Eq. (3.26), p. 29: a first-order track's phase shift tan^-1(R_on C_1 omega),
        # for R_on C_1 omega << 1 a delay R_on C_1: the held value is V_in - R(V_in) C dV_in/dt
        # Terms: V_in and dV_in/dt vin and its slope at the clock's falling crossing; R(V_in) the
        #   level runs' on-resistance (``track``) and the pedestal theirs (``hold``), interpolated
        #   over their settled levels; C tb.cload.
        # Ours against the source: the pedestal at V_in added ([Razavi-Analog] Eq. (13.26), p. 550);
        #   this is flow.samp.model.Model.sample without its noise, jitter and aperture.
        # Holds for: R C omega << 1; samples whose input lies inside the settled input range.
        resistance = np.interp(vin, track.vin_v[settled], track.ron_ohm[settled]) if settled.any() else np.nan
        pedestal = np.interp(vin, hold.vin_v[settled], hold.pedestal_v[settled]) if settled.any() else np.nan
        rest = (held - (vin - resistance * load * rate + pedestal))[inside]
        # [Razavi-ADC] Eq. (3.86), p. 55: Delta V = Delta T dV_in/dt, a sampling instant Delta T late
        # Terms: Delta V the rest of the held sample over the model's; Delta T = a + b V_in, fitted
        #   by least squares over the samples inside the settled range (a ``aperture_s``, b
        #   ``aperture_s_per_v``).
        # Ours against the source: the source's Delta T is a random jitter; ours is the
        #   deterministic, input-dependent instant of [Razavi-ADC] Fig. 3.25(c), p. 37 (the switch
        #   opens as CK falls through V_in + V_TH), to first order in V_in.
        # Holds for: at least three samples inside the settled range; NaN otherwise.
        basis = np.stack([rate[inside], rate[inside] * vin[inside]], axis=1)
        fitted = rest.size >= 3 and bool(np.all(np.isfinite(rest)))
        fit = np.linalg.lstsq(basis, rest, rcond=None)[0] if fitted else (math.nan, math.nan)
        rows.append(
            (
                float(tb.vdd),
                float(tb.input_voltage),
                float(tb.sine_frequency_hz),
                thd_db,
                float(np.max(np.abs(rest))) if fitted else math.nan,
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
def analyze_droop(measurements: Sequence[Meas]) -> AnalysisDroop:
    """Measure the held output's slope over the middle half of each hold (where a DAC step holds
    it moved, over that step), at each point."""

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
            # not in the reference texts: the droop's window, from a quarter into the hold (two
            # clock edges after the DAC's step there) to a quarter before its end: t_fall + t_edge / 2 +
            # t_hold / 4 + 2 t_edge to t_fall + t_edge / 2 + 3 t_hold / 4 - t_edge
            # Terms: t_fall the clock's falling crossing, t_hold = T - t_high - 2 t_edge
            #   (flow.samp.sim.testbench's DAC step rises and falls at its ends).
            # Holds for: the bench's DAC step timing, or none.
            first, last = float(fall) + edge / 2 + hold / 4 + 2 * edge, float(fall) + edge / 2 + 3 * hold / 4 - edge
            if last >= float(time_s[-1]):
                continue
            # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold, a linear fall: its slope
            # Terms: vout's change over the middle half of the hold (a quarter in, two clock edges
            #   after the DAC's step there, to a quarter before its end), over that time; I_leak the
            #   off switch's and its junctions', C_hold tb.cload.
            # Ours against the source: with a DAC step the held output sits moved by it meanwhile.
            # Holds for: the run's gmin below the leakage it reads (LEAKAGE_GMIN_S).
            droops.append((calc.value(output, time_s, last) - calc.value(output, time_s, first)) / (last - first))
        rows.append(
            (
                vdd,
                float(tb.input_voltage),
                float(tb.temperature_c),
                float(tb.dac_step_v),
                float(np.median(droops)) if droops else math.nan,
            )
        )
    vdd_v, vin_v, temperature_c, step_v, droop = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisDroop(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        temperature_c=temperature_c,
        step_v=step_v,
        droop_v_per_s=droop,
    )


@analysis
def analyze_energy(measurements: Sequence[Meas]) -> AnalysisEnergy:
    """Measure the energy the supply and both clocks draw over each whole period after the first:
    the supply voltage times the supply's net charge and the charge each clock delivers, at each
    point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, period, time_s = float(tb.vdd), float(tb.clock_period_s), measurement.time_s
        # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg: over a clock period, E = V_DD times the
        # charge drawn from V_DD
        # Terms: the supply's net charge (the current of the bench's vdd source, what the circuit
        #   returns to it taken off) and the charge each clock source (clk, clk_b) delivers, the
        #   integral of its positive current alone.
        # Ours against the source: the source has one supply; ours adds the clocks, whose drivers
        #   (not in the bench) would draw an edge's charge from V_DD and return none of it.
        # Holds for: ideal clock sources of the supply's swing; whole periods after the first.
        delivered = sum(
            current if name == Nets.vdd.name else np.maximum(current, 0.0) for name, current in measurement.i.items()
        )
        energies = [
            vdd * calc.integ(*calc.clip(np.asarray(delivered, dtype=np.float64), time_s, start, start + period))
            for start in np.arange(1, int(tb.periods)) * period + float(tb.clock_delay_s)
            if start + period <= float(time_s[-1])
        ]
        rows.append((vdd, float(tb.input_voltage), float(np.median(energies)) if energies else math.nan))
    vdd_v, vin_v, energy = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisEnergy(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        energy_per_cycle_j=energy,
    )


def _settled_span(track: AnalysisTrack) -> tuple[float, float]:
    """The lowest and highest input level of the contiguous levels whose time constant is
    measured within the track window: those around the nominal one where it is, else the widest
    such run; NaN for both where none is."""
    # not in the reference texts: the settled input range, the span of the contiguous input levels
    # with a finite on-resistance, around the nominal level where it has one, else the widest
    # Terms: the levels ``track.vin_v`` of the level runs, R_on ``track.ron_ohm``.
    # Ours against the source: [Razavi-Analog] Eq. (13.24), p. 548 bounds an NMOS switch's input
    #   by V_DD - V_TH; this one is where the track window still shows a time constant.
    # Holds for: the level runs' levels and track window.
    nominal = int(np.argmin(np.abs(track.vin_v - NOMINAL_VIN * track.vdd_v)))
    runs, first = [], None
    for index, value in enumerate([*np.isfinite(track.ron_ohm), False]):
        if value and first is None:
            first = index
        elif not value and first is not None:
            runs.append((first, index - 1))
            first = None
    held = [run for run in runs if run[0] <= nominal <= run[1]]
    widest = held or sorted(runs, key=lambda run: (run[0] - run[1], run[0]))
    if not widest:
        return math.nan, math.nan
    return float(track.vin_v[widest[0][0]]), float(track.vin_v[widest[0][1]])


def _largest(values: np.ndarray, mask: np.ndarray | None = None) -> float:
    """The largest magnitude among the finite ``values`` (where ``mask``), NaN where there is none."""
    # not in the reference texts: a metric over points or corners is max_i |x_i| over the finite x_i
    # Terms: x_i an analysis result's value at each point (a level, a supply, a corner, a run).
    # Holds for: at least one finite value; NaN otherwise (a point not measured is no worst case).
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
    droop: AnalysisDroop | None = None,
    skew: AnalysisHold | None = None,
    boost: AnalysisBoost | None = None,
    stress: AnalysisStress | None = None,
    dac_stress: AnalysisStress | None = None,
    acquisition: AnalysisAcquisition | None = None,
    sine: AnalysisSine | None = None,
    dac: AnalysisDroop | None = None,
    energy: AnalysisEnergy | None = None,
) -> dict[str, float]:
    """The record's numbers: from the input level's runs (``track``, ``hold``) the on-resistance,
    bandwidth, track error, pedestal, droop and feedthrough at the nominal input, the largest
    on-resistance and pedestal where a point settled, the input range over which it settles; from
    the supply's (``supply``, ``supply_hold``) the largest on-resistance and pedestal; and where
    given, the corners' (``corners``, ``corners_hold``), the droop over the ADC's hold at 25 C and
    hot (``droop``, in that order: the droop in place of the level run's), the pedestal with a
    late complementary clock (``skew``), the boost's V_GS over the input and the gate's peak
    (``boost``), the devices' largest voltages in the level runs and the full-scale step
    (``stress``) and under the DAC's step (``dac_stress``), the acquisition times and the full-scale track error
    (``acquisition``), the sines' distortion, their distance from the model and the aperture
    (``sine``, low tone first), the droop under the DAC's step (``dac``) and the energy a cycle
    (``energy``)."""

    # not in the reference texts: the nominal point, the level run whose input is nearest
    # NOMINAL_VIN of its supply (argmin |V_in - NOMINAL_VIN V_DD|)
    # Terms: V_in ``track.vin_v``, V_DD ``track.vdd_v`` of the level runs.
    # Holds for: level runs that include the nominal input (flow.samp.runs.testbenches).
    nominal = int(np.argmin(np.abs(track.vin_v - NOMINAL_VIN * track.vdd_v)))
    settled = np.isfinite(track.ron_ohm)
    # not in the reference texts: the input range, the settled span's width (``_settled_span``)
    low, high = _settled_span(track)
    span = high - low if math.isfinite(low) else 0.0
    # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough, in dB: 20 log10 |Delta V_out / Delta V_in|
    # Terms: the ratio ``hold.feedthrough`` (``analyze_hold``).
    # Ours against the source: the source gives no expression; the sign is dropped.
    # Holds for: a feedthrough above the simulator's resolution.
    feedthrough_db = 20 * np.log10(np.abs(hold.feedthrough))
    found = {
        # [Razavi-Analog] Eq. (13.31), p. 552: R_on = tau / C_H of the on switch, at the nominal input
        # Terms: ``track.ron_ohm`` at the nominal point (``analyze_track``).
        # Holds for: the bench's load; NaN where the nominal level shows no time constant.
        "ron_ohm": float(track.ron_ohm[nominal]),
        # [Razavi-Analog] Eq. (13.22), p. 547: R_on over the input level; its largest, max_i R_on(V_in,i)
        # Terms: the level runs' R_on that are finite (a level without one is left out: it is
        #   outside the input range, not a large resistance).
        # Ours against the source: the source's is a single NMOS's law; ours the measured curve.
        # Holds for: the level runs' levels.
        "ron_max_ohm": _largest(track.ron_ohm),
        "input_range_v": span,
        # [Razavi-ADC] Eq. (3.26), p. 29: f_-3dB = 1 / (2 pi R_on C_1), at the nominal input
        # Terms: ``track.bandwidth_hz`` at the nominal point (``analyze_track``).
        # Holds for: the bench's load.
        "bandwidth_hz": float(track.bandwidth_hz[nominal]),
        # [Razavi-ADC] Sec. 3.9.1, p. 53: |V_in - V_out| as tracking ends, at the nominal input
        # Terms: ``track.track_error_v`` at the nominal point: what the level runs' step leaves.
        # Holds for: the level runs' step and track window (the full-scale one:
        #   track_error_full_scale_v).
        "track_error_v": float(track.track_error_v[nominal]),
        # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal, at the nominal input; and max_i |pedestal_i|
        # over the levels inside the settled input range
        # Terms: ``hold.pedestal_v`` (``analyze_hold``); the settled levels those with a finite R_on.
        # Ours against the source: the measured step (channel charge and clock feedthrough).
        # Holds for: the bench's clock edges and load.
        "pedestal_v": float(hold.pedestal_v[nominal]),
        "pedestal_max_v": _largest(hold.pedestal_v, settled),
        # [Pelgrom] Eq. (8.3), p. 387: the droop: over the ADC's hold at 25 C where its run is given
        # (``droop``'s first point), else the nominal level run's
        # Terms: ``droop.droop_v_per_s[0]`` (``analyze_droop``) or ``hold.droop_v_per_s`` at the
        #   nominal point.
        # Holds for: the ADC's hold at the nominal input, typical process, 25 C.
        "droop_v_per_s": float(hold.droop_v_per_s[nominal] if droop is None else droop.droop_v_per_s[0]),
        "feedthrough_db": float(feedthrough_db[nominal]),
        # not in the reference texts: the largest R_on over the 90, 100 and 110 % supply runs at the
        # nominal input, max_k R_on(V_DD,k)
        # Terms: ``supply.ron_ohm`` (``analyze_track`` of the supply runs), finite ones.
        # Holds for: the nominal input (of the nominal supply) at each supply.
        "ron_max_supply_ohm": _largest(supply.ron_ohm),
    }
    if supply_hold is not None:
        # not in the reference texts: the largest |pedestal| over the 90, 100 and 110 % supply runs
        # Terms: ``supply_hold.pedestal_v`` (``analyze_hold`` of the supply runs).
        # Holds for: the nominal input at each supply.
        found["pedestal_max_supply_v"] = _largest(supply_hold.pedestal_v)
    if corners is not None and corners_hold is not None:
        # not in the reference texts: the largest R_on and |pedestal| over the slow, fast and hot runs
        # Terms: ``corners.ron_ohm`` and ``corners_hold.pedestal_v`` (the corner runs' analyses).
        # Holds for: the nominal input and supply; slow and fast at 25 C, hot at typical process.
        found["ron_max_corner_ohm"] = _largest(corners.ron_ohm)
        found["pedestal_max_corner_v"] = _largest(corners_hold.pedestal_v)
    if droop is not None:
        # [Pelgrom] Eq. (8.3), p. 387: the droop over the ADC's hold, hot (``droop``'s last point)
        # Terms: ``droop.droop_v_per_s[-1]`` (``analyze_droop`` of the hot run).
        # Holds for: the nominal input, typical process, the hot corner's temperature.
        found["droop_hot_v_per_s"] = float(droop.droop_v_per_s[-1])
    if skew is not None:
        # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal, the complementary clock an edge late
        # Terms: ``skew.pedestal_v[0]`` (``analyze_hold`` of the skew run).
        # Ours against the source: dummies cancel only with clock edges that meet ([Razavi-ADC]
        #   Sec. 3.7, p. 42); this run moves one.
        # Holds for: the nominal input and supply, clk_b a clock edge late.
        found["pedestal_skew_v"] = float(skew.pedestal_v[0])
    if boost is not None:
        # [Razavi-ADC] Eq. (3.72), p. 50: V_P - V_in = V_b' - C_p / (C_b + C_G1 + C_G2 + C_p) V_in,
        # the boosted V_GS over the input: its least and largest over the level runs
        # Terms: ``boost.vgs_v`` (``analyze_boost``): ``gate`` over vin as tracking ends.
        # Ours against the source: read at the gate A, below P by Mgate's drop (none, settled).
        # Holds for: a bootstrapped switch; NaN otherwise.
        boosted = np.isfinite(boost.vgs_v)
        found["vgs_min_v"] = float(boost.vgs_v[boosted].min()) if boosted.any() else math.nan
        found["vgs_max_v"] = float(boost.vgs_v[boosted].max()) if boosted.any() else math.nan
        # [Razavi-ADC] Sec. 3.8.1, p. 43: the gate's peak, V_in + V_b: its largest over the level runs
        # Terms: ``boost.gate_max_v``, the largest of ``gate`` over each run.
        # Holds for: the level runs' inputs (the highest the supply less half the step).
        found["gate_max_v"] = _largest(boost.gate_max_v)
    for suffix, given in (("", stress), ("_dac", dac_stress)):
        if given is None:
            continue
        # [Razavi-ADC] Sec. 3.8.2, p. 48: the largest terminal voltages over the runs given, against
        # the technology's (the stress limit: the nominal supply times its largest corner)
        # Terms: ``terminal_v`` the largest |V_GS|, |V_GD|, |V_DS| of any transistor, ``gate_bulk_v``
        #   the largest |V_GB| (``analyze_stress``); max over the runs that saved their devices.
        # Ours against the source: the source names the stress without a limit.
        # Holds for: the level runs at the ends and the middle, the highest supply's run and the
        #   full-scale steps (``stress``); the DAC runs (``dac_stress``).
        found[f"terminal_max{suffix}_v"] = _largest(given.terminal_v)
        found[f"gate_bulk_max{suffix}_v"] = _largest(given.gate_bulk_v)
        # [Razavi-Analog] Sec. 2.1, p. 9: the source and drain junctions kept reverse biased: the
        # largest forward bias of any (negative: all reverse biased)
        # Terms: ``junction_v`` (``analyze_stress``), V_BS and V_BD of an NMOS, their negatives of a PMOS.
        # Holds for: the same runs.
        forward = given.junction_v[np.isfinite(given.junction_v)]
        found[f"junction_forward_max{suffix}_v"] = float(forward.max()) if forward.size else math.nan
    if acquisition is not None:
        # [Razavi-ADC] Eq. (3.82), p. 54: t_acq to half an LSB at each resolution
        # Terms: ``acquisition.acquisition_s`` of the full-scale step at the nominal supply
        #   (``analyze_acquisition``), the slower step direction.
        # Holds for: the ADC's track window, its full scale a side, the bench's load.
        for index, bits in enumerate(acquisition.bits):
            found[f"acquisition_{int(bits)}b_s"] = float(acquisition.acquisition_s[0, index])
        # [Razavi-ADC] Fig. 3.50, p. 53: the error a full-scale step leaves as the ADC's track window ends
        # Terms: ``acquisition.track_error_v[0]``, the larger of the two step directions.
        # Holds for: the same run.
        found["track_error_full_scale_v"] = float(acquisition.track_error_v[0])
    if sine is not None:
        # [Razavi-ADC] Eq. (3.85), p. 55: the held samples' distortion, the low tone's and the high one's
        # Terms: ``sine.thd_db`` first and last (``analyze_sine``, low tone first).
        # Holds for: the ADC's timing and swing, the bench's load, one side (single-ended).
        found["thd_low_db"], found["thd_high_db"] = float(sine.thd_db[0]), float(sine.thd_db[-1])
        # not in the reference texts: the largest distance of a held sample from the behavioral
        # model's, max over both tones of max_n |held_n - model_n|, over the samples inside the
        # input range the level runs settle over
        # Terms: ``sine.model_error_v`` (``analyze_sine``).
        # Holds for: the settled input range (outside it the model holds the previous sample).
        found["model_error_v"] = _largest(sine.model_error_v)
        # [Pelgrom] Sec. 8.3.2, p. 390: the signal-dependent aperture delay, a + b V_in, from the high tone
        # Terms: ``sine.aperture_s`` and ``sine.aperture_s_per_v`` of the last (highest) tone.
        # Ours against the source: the source names the effect; the fit is ``analyze_sine``'s.
        # Holds for: the high tone's slopes; NaN where the fit had too few samples.
        found["aperture_s"], found["aperture_s_per_v"] = float(sine.aperture_s[-1]), float(sine.aperture_s_per_v[-1])
    if dac is not None:
        # [Pelgrom] Eq. (8.3), p. 387: the largest |droop| while the DAC's first step holds the output raised
        # Terms: ``dac.droop_v_per_s`` of the two DAC runs (``analyze_droop``).
        # Ours against the source: the held output stands a_0 above its sample meanwhile
        #   ([Razavi-ADC] Sec. 16.2.1, p. 346).
        # Holds for: the hot corner, the lowest level a side reaches and the common mode.
        found["droop_conversion_v_per_s"] = _largest(dac.droop_v_per_s)
    if energy is not None:
        # [Baker] Eq. (11.15), p. 355: V_DD times the charge drawn over a clock period (``analyze_energy``)
        # Terms: ``energy.energy_per_cycle_j[0]``, the nominal level run's.
        # Holds for: the bench's 10 ns clock, load and nominal input.
        found["energy_per_cycle_j"] = float(energy.energy_per_cycle_j[0])
    return found
