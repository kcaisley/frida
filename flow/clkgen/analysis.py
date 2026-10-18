"""Typed clock conditioning measurements, results, and analyses.

A ``MeasClkgen`` is one transient of the shared clock testbench. The figures follow BAG's clock
benches, all at mid-supply and from one period after the enable: the delay from clk's rising
edge to outp's, outp's high width and duty cycle, the gaps between one output falling and the
other rising (positive: non-overlapping), outp's pulses before the enable (a clock gate's should
be none) and the share of clock periods after it that produced one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.clkgen.sim import ClkgenTbParams
from flow.clkgen.subckt import ClkgenNets, ClkgenParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasClkgen(Meas):
    """Clock conditioning transient at one supply and period: one record, all in ``wave``."""

    dut: ClkgenParams
    param: ClkgenTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisClkgenTiming(Analysis):
    """Clock conditioning timing at each measured point (medians over the periods after the enable).

    ``duty_cycle`` is outp's high share of each of its cycles (``dutyCycle``), averaged over the
    whole clock periods in the window; NaN where outp completes no cycle there. ``rise_gap_s``
    runs from each outp fall to the nearest outn rise, ``fall_gap_s`` from each outn fall to the
    nearest outp rise; negative where the outputs overlap.
    """

    vdd_v: np.ndarray
    period_s: np.ndarray
    delay_s: np.ndarray
    high_width_s: np.ndarray
    duty_cycle: np.ndarray
    rise_gap_s: np.ndarray
    fall_gap_s: np.ndarray
    pulses_before_enable: np.ndarray
    pulse_fraction: np.ndarray
    supply_current_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a * self.period_s


def analyze_clkgen_timing(measurements: Sequence[MeasClkgen]) -> AnalysisClkgenTiming:
    """Measure delay, high width, duty, output gaps, pulses around the enable, and supply current at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("clock conditioning analysis requires a waveform record")
        vdd, period = float(measurement.param.vdd), float(measurement.param.period_s)
        time_s = wave.time_s
        threshold = vdd / 2
        enable_s = calc.cross(wave.v[ClkgenNets.en.name][0], time_s, threshold, edge="rising", occurrence=1)
        start_s, stop_s = enable_s + period, float(time_s[-1]) - period / 2
        clock = calc.cross(wave.v[ClkgenNets.clk.name][0], time_s, threshold, edge="rising")
        edges = {
            (name, edge): calc.cross(wave.v[name][0], time_s, threshold, edge=edge)
            for name in (ClkgenNets.outp.name, ClkgenNets.outn.name)
            for edge in ("rising", "falling")
        }
        p_rise, p_fall = edges["outp", "rising"], edges["outp", "falling"]
        n_rise, n_fall = edges["outn", "rising"], edges["outn", "falling"]
        delays = [
            float(p_rise[p_rise > edge][0] - edge)
            for edge in clock[(clock > start_s) & (clock < stop_s)]
            if np.any((p_rise > edge) & (p_rise < edge + period / 2))
        ]
        widths = [float(p_fall[p_fall > rise][0] - rise) for rise in p_rise[p_rise > start_s] if np.any(p_fall > rise)]
        rise_gaps = [
            float(n_rise[np.argmin(np.abs(n_rise - fall))] - fall) for fall in p_fall[p_fall > start_s] if len(n_rise)
        ]
        fall_gaps = [
            float(p_rise[np.argmin(np.abs(p_rise - fall))] - fall) for fall in n_fall[n_fall > start_s] if len(p_rise)
        ]
        # duty and current over whole periods: from the first clock edge in the window to its last
        periods = clock[(clock > start_s) & (clock < stop_s)]
        window_v, window_s = calc.clip(wave.v[ClkgenNets.outp.name][0], time_s, periods[0], periods[-1])
        current, current_s = calc.clip(wave.i[ClkgenNets.vdd.name][0], time_s, periods[0], periods[-1])
        clocked = len(periods)
        rows.append(
            (
                vdd,
                period,
                float(np.median(delays)) if delays else math.nan,
                float(np.median(widths)) if widths else math.nan,
                calc.dutyCycle(window_v, window_s, threshold=threshold, output_type="average") / 100,
                float(np.median(rise_gaps)) if rise_gaps else math.nan,
                float(np.median(fall_gaps)) if fall_gaps else math.nan,
                int(np.sum(p_rise < enable_s)),
                np.sum((p_rise > start_s) & (p_rise < stop_s)) / clocked if clocked else math.nan,
                calc.average(current, current_s),
            )
        )
    columns = list(zip(*rows))
    vdd_v, period_s, delay, width, duty, rise_gap, fall_gap, _before, fraction, current_a = (
        np.asarray(column, dtype=np.float64) for column in columns
    )
    return AnalysisClkgenTiming(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        period_s=period_s,
        delay_s=delay,
        high_width_s=width,
        duty_cycle=duty,
        rise_gap_s=rise_gap,
        fall_gap_s=fall_gap,
        pulses_before_enable=np.asarray(columns[7], dtype=np.int64),
        pulse_fraction=fraction,
        supply_current_a=current_a,
    )
