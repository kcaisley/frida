"""Typed phase interpolator measurements, results, and analyses.

A ``MeasPi`` is one transient of the shared interpolator testbench. Each figure is taken after
three clock periods of start-up, on the differential signals (a CMOS interpolator's mix node is
its outn): the output's delay from phase A's rising crossing, as a phase, the swing and duty
cycle. Over a spacing sweep, an ideal interpolator's delay rises by phase B's weight share of the
spacing (Usb2Phy's code-to-delay slope); the linearity fit over quadrature gives that slope and the deviation
from it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.pi.sim import PiTbParams
from flow.pi.subckt import PiNets, PiParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasPi(Meas):
    """Phase interpolator transient at one period and phase spacing: one record, all in ``wave``."""

    dut: PiParams
    param: PiTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPiPhase(Analysis):
    """Interpolator output timing at each point: ``delay_s`` the median from each rising A
    crossing to the next rising output crossing, ``output_phase_deg`` that as a phase,
    ``swing_v`` half the differential peak-to-peak, ``duty_cycle`` the output's high share."""

    period_s: np.ndarray
    spacing_deg: np.ndarray
    delay_s: np.ndarray
    output_phase_deg: np.ndarray
    swing_v: np.ndarray
    duty_cycle: np.ndarray
    supply_current_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPiLinearity(Analysis):
    """Interpolator transfer over a spacing sweep at one period.

    ``slope`` is the delay per unit of spacing (both in time) fitted over spacings up to 90°,
    ``ideal_slope`` phase B's weight share; ``intrinsic_delay_s`` the fit's delay at zero spacing;
    ``inl_deg`` each point's deviation from the fit, as output phase (NaN where the output did not
    cross); ``max_inl_deg`` its largest within the fitted range.
    """

    period_s: float
    ideal_slope: float
    slope: float
    intrinsic_delay_s: float
    spacing_deg: np.ndarray
    inl_deg: np.ndarray

    @property
    def max_inl_deg(self) -> float:
        return float(np.nanmax(np.abs(self.inl_deg[self.spacing_deg <= 90.0])))


def analyze_pi_phase(measurements: Sequence[MeasPi]) -> AnalysisPiPhase:
    """Measure output delay and phase from phase A, swing, duty cycle, and supply current at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("phase interpolator analysis requires a waveform record")
        period = float(measurement.param.period_s)
        time_s = wave.time_s
        start_s, stop_s = 3 * period, float(time_s[-1])
        phase_a = wave.v[PiNets.ap.name][0] - wave.v[PiNets.an.name][0]
        output = wave.v[PiNets.outp.name][0] - wave.v[PiNets.outn.name][0]
        launches = calc.cross(phase_a, time_s, 0.0, edge="rising")
        responses = calc.cross(output, time_s, 0.0, edge="rising")
        delays = [
            float(responses[responses > launch][0] - launch)
            for launch in launches[launches > start_s]
            if np.any(responses > launch) and responses[responses > launch][0] - launch < period
        ]
        window_v, window_s = calc.clip(output, time_s, start_s, stop_s)
        current, current_s = calc.clip(wave.i[PiNets.vdd.name][0], time_s, start_s, stop_s)
        delay_s = float(np.median(delays)) if delays else math.nan
        rows.append(
            (
                period,
                float(measurement.param.spacing_deg),
                delay_s,
                360 * delay_s / period,
                calc.peakToPeak(window_v) / 2,
                calc.average((window_v > 0).astype(np.float64), window_s),
                calc.average(current, current_s),
            )
        )
    period_s, spacing, delay, phase, swing, duty, current_a = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisPiPhase(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        period_s=period_s,
        spacing_deg=spacing,
        delay_s=delay,
        output_phase_deg=phase,
        swing_v=swing,
        duty_cycle=duty,
        supply_current_a=current_a,
    )


def analyze_pi_linearity(measurements: Sequence[MeasPi], *, phase: AnalysisPiPhase) -> AnalysisPiLinearity:
    """Fit the delay over a spacing sweep at one period: slope against phase B's weight share, and INL."""

    identity = measurement_identity(measurements)
    check_identity(phase, identity, name="phase")
    # the fit covers quadrature, the range an interpolator works within, where the output crossed
    valid = np.isfinite(phase.delay_s) & (phase.spacing_deg <= 90.0)
    if len(set(phase.period_s)) != 1 or len(set(phase.spacing_deg[valid])) < 3:
        raise ValueError("interpolator linearity requires a spacing sweep at one period, three spacings crossing")
    period = float(phase.period_s[0])
    spacing_s = phase.spacing_deg / 360 * period
    slope, intercept = np.polyfit(spacing_s[valid], phase.delay_s[valid], 1)
    return AnalysisPiLinearity(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        period_s=period,
        ideal_slope=identity.dut.weight_b / (identity.dut.weight_a + identity.dut.weight_b),
        slope=float(slope),
        intrinsic_delay_s=float(intercept),
        spacing_deg=phase.spacing_deg,
        inl_deg=360 * (phase.delay_s - (slope * spacing_s + intercept)) / period,
    )
