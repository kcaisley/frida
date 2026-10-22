"""Typed CDAC measurements and their per-stage settling.

A ``MeasCdac`` is one transient of the CDAC testbench (``flow.cdac.sim``): every stage switched
alone, up (its P side's state rising, its N side's falling) and back down. For each stage and
direction ``analyze_cdac_settling`` measures, with ``flow.analysis.calc``:

- the differential top plate's step, from the window's start to its end;
- the driver's delay (``delay``): from the P side's state crossing mid-supply to its main bottom
  plate crossing it;
- the settling time (``settlingTime``): from that input edge until the differential top plate
  stays within half the converter's LSB (2 full scale / 2^adc_bits) of its final value.

The behavioral ADC lets each stage's step start its driver's delay after the edge and settle as one
exponential (``flow.adc.behavioral``): the time constant that brings the measured step within half
an LSB exactly when SPICE does is (settling - delay) / ln(|step| / half an LSB). A stage's main and
difference plates move in opposite directions, so a small net step can follow a large transient
that its plates' drivers leave behind; the time constant carries it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity

from .sim import CdacTbParams, window_start_s
from .subckt import CdacParams


def full_scale_v(dac: CdacParams, vdd: float) -> float:
    """The differential full scale (+-): the reference across the switched plates' share of the top
    plate, main less difference (as ``AdcModel.full_scale_v``)."""
    load = sum(dac.main_f) + sum(dac.diff_f) + dac.parasitic_f
    return vdd * (sum(dac.main_f) - sum(dac.diff_f)) / load


def lsb_v(dac: CdacParams, vdd: float, adc_bits: int) -> float:
    """The converter's LSB: twice the full scale over its codes."""
    return 2 * full_scale_v(dac, vdd) / 2**adc_bits


def ideal_steps_v(dac: CdacParams, vdd: float) -> np.ndarray:
    """Each stage's differential step as its P side rises and its N side falls: twice its main less
    difference plate's share of the top plate, times the reference."""
    load = sum(dac.main_f) + sum(dac.diff_f) + dac.parasitic_f
    return 2 * vdd * (np.asarray(dac.main_f) - np.asarray(dac.diff_f)) / load


def settling_tau_s(settling_s: float, delay_s: float, step_v: float, tolerance_v: float) -> float:
    """The time constant of a step starting ``delay_s`` after its edge that comes within
    ``tolerance_v`` at ``settling_s``; 0 for a step that never leaves the tolerance."""
    ratio = abs(step_v) / tolerance_v
    if ratio <= 1 or not settling_s > delay_s:
        return 0.0
    return (settling_s - delay_s) / math.log(ratio)


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCdac(Meas):
    """CDAC transient: every stage up and back down in its turn, one record in ``wave``."""

    dut: CdacParams
    param: CdacTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCdacSettling(Analysis):
    """Each stage's switching, C0 first, up (``rise``: the differential top plate rising) and down.

    ``step_*_v`` is the differential top plate's step, ``delay_*_s`` the driver's from the state's
    edge to its main bottom plate's, ``settling_*_s`` the time from the state's edge until the step
    stays within ``tolerance_v`` (half an LSB) of its final value; NaN where an edge is missing.
    ``ideal_step_v`` is the step the capacitances alone give.
    """

    lsb_v: float
    window_s: float
    ideal_step_v: np.ndarray
    step_rise_v: np.ndarray
    step_fall_v: np.ndarray
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    settling_rise_s: np.ndarray
    settling_fall_s: np.ndarray

    @property
    def tolerance_v(self) -> float:
        return self.lsb_v / 2

    @property
    def settled(self) -> bool:
        """Whether every step settled in its window's first half: its end is its final value."""
        times = np.concatenate([self.settling_rise_s, self.settling_fall_s])
        return bool(np.all(np.isfinite(times)) and np.all(times < self.window_s / 2))

    @property
    def step_error_lsb(self) -> float:
        """The largest step's difference from the capacitances' (the simulator's precision), in LSB."""
        error = np.abs(np.concatenate([self.step_rise_v - self.ideal_step_v, self.step_fall_v + self.ideal_step_v]))
        return float(np.max(error)) / self.lsb_v

    def _slower(self, rise: np.ndarray, fall: np.ndarray) -> np.ndarray:
        """Each stage's value in the direction that settles later."""
        return np.where(self.settling_rise_s >= self.settling_fall_s, rise, fall)

    @property
    def settling_s(self) -> np.ndarray:
        """Each stage's settling time, the slower direction's."""
        return np.maximum(self.settling_rise_s, self.settling_fall_s)

    @property
    def delay_s(self) -> np.ndarray:
        """Each stage's driver delay, in its slower direction."""
        return self._slower(self.delay_rise_s, self.delay_fall_s)

    @property
    def step_v(self) -> np.ndarray:
        """Each stage's step, in its slower direction."""
        return self._slower(self.step_rise_v, self.step_fall_v)

    @property
    def tau_s(self) -> np.ndarray:
        """Each stage's time constant: started at its driver's delay, its step comes within half an
        LSB when it settles (its slower direction)."""
        return np.asarray(
            [
                settling_tau_s(settling, delay, step, self.tolerance_v)
                for settling, delay, step in zip(self.settling_s, self.delay_s, self.step_v, strict=True)
            ]
        )


def analyze_cdac_settling(measurement: MeasCdac) -> AnalysisCdacSettling:
    """Measure every stage's step, driver delay and settling to half an LSB, both directions."""

    identity = measurement_identity([measurement])
    wave = measurement.wave
    if wave is None:
        raise ValueError("CDAC analysis requires a waveform record")
    tb = measurement.param
    vdd, window, time_s = float(tb.vdd), float(tb.window_s), wave.time_s
    lsb = lsb_v(tb.dac, vdd, tb.adc_bits)
    differential = wave.v["vdac_p"][0] - wave.v["vdac_n"][0]
    columns = ("step", "delay", "settling")
    rows: dict[str, dict[str, list[float]]] = {
        direction: {key: [] for key in columns} for direction in ("rise", "fall")
    }
    for stage in range(tb.dac.driver.n_stages):
        state, bottom = wave.v[f"dac_state_p[{stage}]"][0], wave.v[f"dac_botplate_p[{stage}]"][0]
        for direction, edge in (("rise", "rising"), ("fall", "falling")):
            start = window_start_s(tb, stage, rising=direction == "rise")
            stop = min(start + window, float(time_s[-1]))
            # the state's edge in this window: the stimulus switches each state once each way
            edge_s, _, delay = calc.delay(
                state, bottom, time_s, vdd / 2, vdd / 2, trigger_edge=edge, response_edge=edge
            )
            initial = calc.value(differential, time_s, start)
            final = calc.value(differential, time_s, stop)
            settling = math.nan
            if math.isfinite(edge_s):
                segment, segment_s = calc.clip(differential, time_s, edge_s, stop)
                settled = calc.settlingTime(
                    segment, segment_s, initial=initial, final=final, absolute_tolerance=lsb / 2
                )
                settling = settled - edge_s
            rows[direction]["step"].append(final - initial)
            rows[direction]["delay"].append(delay)
            rows[direction]["settling"].append(settling)
    array = {f"{key}_{direction}": np.asarray(rows[direction][key]) for direction in rows for key in columns}
    return AnalysisCdacSettling(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        lsb_v=lsb,
        window_s=window,
        ideal_step_v=ideal_steps_v(tb.dac, vdd),
        step_rise_v=array["step_rise"],
        step_fall_v=array["step_fall"],
        delay_rise_s=array["delay_rise"],
        delay_fall_s=array["delay_fall"],
        settling_rise_s=array["settling_rise"],
        settling_fall_s=array["settling_fall"],
    )
