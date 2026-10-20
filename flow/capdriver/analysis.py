"""Typed capacitor driver measurements, results, and analyses.

A ``MeasCapdriver`` is one transient of the capacitor driver testbench: one stage driving its load,
first through the state input, then through the invert input. The figures are those a CDAC's
settling budget needs, each a calculator function of ``flow.analysis.calc``: the delay from each
input edge to the output's (``delay``, at mid-supply), the output's 10–90 % transitions
(``riseTime``, ``fallTime``), its settling to 1 % (``settlingTime``) and the energy it draws per
cycle (``integ``). Over the load, the transitions' slope against the capacitance is the drive's
effective drive resistance (a 10–90 % RC transition is ln 9 RC), the driver sizing's input.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.capdriver.sim import CapdriverTbParams
from flow.capdriver.subckt import CapDriverParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCapdriver(Meas):
    """Capacitor driver transient at one supply and load: one record, all in ``wave``."""

    dut: CapDriverParams
    param: CapdriverTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCapdriverDrive(Analysis):
    """Capacitor driver timing at each measured point (stage 0).

    ``state_rise_delay_s`` and ``state_fall_delay_s`` run from the state's rising and falling edges
    to the output's, ``invert_rise_delay_s`` and ``invert_fall_delay_s`` from the invert input's,
    all at mid-supply. ``rise_time_s`` and ``fall_time_s`` are the output's 10–90 % transitions on
    the state edges, ``rise_settling_s`` and ``fall_settling_s`` the time from those input edges
    until the output stays within 1 % of the supply step, ``energy_per_cycle_j`` the supply energy
    over one output cycle (charging and discharging the load once). NaN where an edge is missing.
    """

    vdd_v: np.ndarray
    load_f: np.ndarray
    state_rise_delay_s: np.ndarray
    state_fall_delay_s: np.ndarray
    invert_rise_delay_s: np.ndarray
    invert_fall_delay_s: np.ndarray
    rise_time_s: np.ndarray
    fall_time_s: np.ndarray
    rise_settling_s: np.ndarray
    fall_settling_s: np.ndarray
    energy_per_cycle_j: np.ndarray

    @property
    def energy_per_cv2(self) -> np.ndarray:
        """Energy per cycle over the load's C V²: 1 for an ideal driver, more for its own switching."""
        return self.energy_per_cycle_j / (self.load_f * self.vdd_v**2)

    def drive_resistance_ohm(self) -> tuple[float, float]:
        """The rising and falling effective drive resistance: the 10–90 % transitions' slope
        against the load (least squares over the finite points at the first point's supply), over
        ln 9; NaN from fewer than two such points."""
        same = np.isclose(self.vdd_v, self.vdd_v[0])
        resistances = []
        for transition in (self.rise_time_s, self.fall_time_s):
            used = same & np.isfinite(transition)
            fit = np.polyfit(self.load_f[used], transition[used], 1)[0] if np.count_nonzero(used) >= 2 else math.nan
            resistances.append(float(fit) / math.log(9.0))
        return resistances[0], resistances[1]


def analyze_capdriver_drive(measurements: Sequence[MeasCapdriver]) -> AnalysisCapdriverDrive:
    """Measure each path's delays, the output's transitions and settling, and the energy per cycle at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("capacitor driver analysis requires a waveform record")
        tb = measurement.param
        vdd, period, edge = float(tb.vdd), float(tb.period_s), float(tb.transition_time_s)
        time_s, mid = wave.time_s, float(tb.vdd) / 2
        state, invert, output = (wave.v[name][0] for name in ("dac_state", "dac_drive_invert", "dac_drive"))
        delays = [
            calc.delay(trigger, output, time_s, mid, mid, trigger_edge=direction, response_edge=direction)[2]
            for trigger in (state, invert)
            for direction in ("rising", "falling")
        ]
        # the state path's period: up a quarter in, down three quarters in
        up_v, up_s = calc.clip(output, time_s, period / 4, 3 * period / 4)
        down_v, down_s = calc.clip(output, time_s, 3 * period / 4, period)
        rise_settled = calc.settlingTime(up_v, up_s, initial=0.0, final=vdd, percent_of_step=1.0)
        fall_settled = calc.settlingTime(down_v, down_s, initial=vdd, final=0.0, percent_of_step=1.0)
        current, current_s = calc.clip(wave.i["vdd"][0], time_s, 0.0, period)
        rows.append(
            (
                vdd,
                float(tb.cload),
                *delays,
                calc.riseTime(up_v, up_s, 0.0, vdd),
                calc.fallTime(down_v, down_s, vdd, 0.0),
                rise_settled - period / 4 - edge / 2,
                fall_settled - 3 * period / 4 - edge / 2,
                vdd * calc.integ(current, current_s),
            )
        )
    columns = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    vdd_v, load_f, state_rise, state_fall, invert_rise, invert_fall, rise, fall, rise_set, fall_set, energy = columns
    return AnalysisCapdriverDrive(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        load_f=load_f,
        state_rise_delay_s=state_rise,
        state_fall_delay_s=state_fall,
        invert_rise_delay_s=invert_rise,
        invert_fall_delay_s=invert_fall,
        rise_time_s=rise,
        fall_time_s=fall,
        rise_settling_s=rise_set,
        fall_settling_s=fall_set,
        energy_per_cycle_j=energy,
    )
