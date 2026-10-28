"""Typed capacitor-array transients, results, and analyses.

A ``MeasCapArrayTran`` is one transient of the CDAC testbench: the top plate while the bottom
plates step through a sequence of packed codes, each held for a dwell. Every figure reads the top
plate in the middle of a code's dwell. Toggling one stage alone after an all-zero code moves the
top plate by that stage's share of the supply (its capacitance over the whole array's and the
load's); the packed ramp gives the code-to-voltage transfer and its nonlinearity. The extracted
array's capacitances are ``MeasCapArray``'s (reserved, ``flow.analysis.types``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas
from flow.cdac.caparray.sim import CapArrayTbParams
from flow.cdac.caparray.subckt import CapArrayConfig, get_caparray_weights


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCapArrayTran(Meas):
    """CDAC code-sequence transient: one record, the top plate in ``wave``."""

    dut: CapArrayConfig
    param: CapArrayTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCaparrayWeights(Analysis):
    """Every stage's share of the supply on the top plate, C0 first.

    ``fraction`` is the top plate's step when the stage alone switches, over the supply;
    ``design_weight`` the stage's unit-capacitor weight; ``weight_error`` the measured weight (the
    fractions scaled to the design weights' total) over the design's, minus one;
    ``total_fraction`` the fractions' sum, the share of the supply the whole array delivers to
    its top plate (below one by the load and the arrays' fixed capacitance).
    """

    fraction: np.ndarray
    design_weight: np.ndarray
    weight_error: np.ndarray
    total_fraction: float


def analyze_caparray_weights(measurement: MeasCapArrayTran) -> AnalysisCaparrayWeights:
    """Measure each stage's top-plate step and compare its weight with the design's."""

    tb = measurement.param
    wave = measurement.wave
    if wave is None or tb.codes is None:
        raise ValueError("stage weights require a waveform record of explicit stage codes")
    design = np.asarray(get_caparray_weights(measurement.dut), dtype=np.float64)
    if len(tb.codes) != 2 * len(design):
        raise ValueError("stage weights require an all-zero code before each stage's own code")
    step_s = float(tb.code_dwell_s) + float(tb.transition_time_s)
    centers = (np.arange(len(tb.codes)) + 0.5) * step_s - float(tb.transition_time_s) / 2
    levels = np.asarray(calc.value(wave.v["cap_topplate"][0], wave.time_s, centers), dtype=np.float64)
    fraction = (levels[1::2] - levels[0::2]) / float(tb.vdd)
    measured = fraction * np.sum(design) / np.sum(fraction)
    return AnalysisCaparrayWeights(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        fraction=fraction,
        design_weight=design,
        weight_error=measured / design - 1,
        total_fraction=float(np.sum(fraction)),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCaparrayTransfer(Analysis):
    """The packed code ramp's top plate against what the design weights predict.

    A packed code's bit n_stages - 1 - s drives stage s, so ``design_weight`` is the sum of the
    driven stages' unit-capacitor weights (a redundant array's ramp is not monotonic: its weights
    overlap). ``volts_per_unit`` is the least-squares slope of the top plate's change over that
    sum; ``error_units`` each code's change over the slope, minus its design weight, in unit
    capacitors.
    """

    code: np.ndarray
    design_weight: np.ndarray
    voltage_v: np.ndarray
    volts_per_unit: float
    error_units: np.ndarray


def analyze_caparray_transfer(measurement: MeasCapArrayTran) -> AnalysisCaparrayTransfer:
    """Read the top plate at every code of the ramp and compare it with the design weights."""

    tb = measurement.param
    wave = measurement.wave
    if wave is None:
        raise ValueError("the code transfer requires a waveform record")
    weights = np.asarray(get_caparray_weights(measurement.dut), dtype=np.float64)
    code = np.arange(2**tb.cdac.n_dac) if tb.codes is None else np.asarray(tb.codes)
    bits = (code[:, None] >> (len(weights) - 1 - np.arange(len(weights)))[None, :]) & 1
    design = bits @ weights
    step_s = float(tb.code_dwell_s) + float(tb.transition_time_s)
    centers = (np.arange(len(code)) + 0.5) * step_s - float(tb.transition_time_s) / 2
    voltage = np.asarray(calc.value(wave.v["cap_topplate"][0], wave.time_s, centers), dtype=np.float64)
    change = voltage - voltage[0]
    slope = float(np.dot(change, design - design[0]) / np.dot(design - design[0], design - design[0]))
    return AnalysisCaparrayTransfer(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        code=code.astype(np.int64),
        design_weight=design,
        voltage_v=voltage,
        volts_per_unit=slope,
        error_units=change / slope - (design - design[0]),
    )
