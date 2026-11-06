"""The capacitive DAC's analysis results (``flow.capdac.analysis``), pure data: a simulation's
settling and its plates' Monte Carlo, and the bench's switching curves (``AnalysisSwitching``, a
converter's capture as the CDAC sees it), each curve's transition (``AnalysisTransition``) and each
stage's capacitance from them (``AnalysisCapMismatch``)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from flow.pipeline import Analysis, MeasInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSettling(Analysis):
    """Each stage's switching, C0 first, up (``rise``: the differential top plate rising) and down.

    ``step_*_v`` is the differential top plate's step, ``delay_*_s`` the driver's from the state's
    edge to its main bottom plate's, ``settling_*_s`` the time from the state's edge until the step
    stays within ``tolerance_v`` (half an LSB) of its final value; NaN where an edge is missing.
    ``gain`` is the drawn array's against its design (its top plates' load beyond the design's
    plates, fitted to the steps); ``ideal_step_v`` the step the design's weights give at that gain,
    ``full_scale_v`` the converter's, ``lsb_v`` its LSB.

    The behavioral ADC (``flow.adc.behavioral``) starts each stage's step its driver's delay after
    the edge and settles it as one exponential: ``tau_s`` is the time constant that brings the
    measured step within half an LSB exactly when SPICE does, (settling - delay) / ln(|step| / half
    an LSB), in each stage's slower direction (0 for a step that never leaves the tolerance). A
    stage's main and difference plates move in opposite directions, so a small net step can follow a
    large transient that its plates' drivers leave behind; the time constant carries it.
    """

    lsb_v: float
    full_scale_v: float
    gain: float
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
        """The largest step's difference from the design weights' at the drawn gain (a unit drawn other
        than designed; the simulator's precision), in LSB."""
        error = np.abs(np.concatenate([self.step_rise_v - self.ideal_step_v, self.step_fall_v + self.ideal_step_v]))
        return float(np.max(error)) / self.lsb_v

    @property
    def settling_s(self) -> np.ndarray:
        """Each stage's settling time, the slower direction's."""
        return np.maximum(self.settling_rise_s, self.settling_fall_s)

    @property
    def delay_s(self) -> np.ndarray:
        """Each stage's driver delay, in its slower direction."""
        return np.where(self.settling_rise_s >= self.settling_fall_s, self.delay_rise_s, self.delay_fall_s)

    @property
    def step_v(self) -> np.ndarray:
        """Each stage's step, in its slower direction."""
        return np.where(self.settling_rise_s >= self.settling_fall_s, self.step_rise_v, self.step_fall_v)

    @property
    def tau_s(self) -> np.ndarray:
        """Each stage's time constant: started at its driver's delay, its step comes within half an
        LSB when it settles (its slower direction); 0 where the step never leaves the tolerance."""
        ratios = np.abs(self.step_v) / self.tolerance_v
        return np.asarray(
            [
                (settling - delay) / math.log(ratio) if ratio > 1 and settling > delay else 0.0
                for settling, delay, ratio in zip(self.settling_s, self.delay_s, ratios, strict=True)
            ]
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMismatch(Analysis):
    """The plates' Monte Carlo at one condition (``pelgrom``: Pelgrom's coefficient, a fraction):
    each run's drawn plates (F, a row a run, C0 first; zero where the design has no plate) and what
    they give, a value a run:

    - the DAC alone (``dac_*``): either side's capacitor DAC over all its control words, each placed
      by its design weights (the decoder's halved), its worst |INL| and |DNL| (LSB of the DAC's
      unit), the worse side's;
    - the converter's static transfer with the design weights (``dnl_lsb``, ``inl_lsb``: worst |DNL|
      and |INL|, ``missing_codes``): every decision path of the drawn sides in the SAR loop, from the
      converter's A state;
    - what no calibration recovers (``gap_lsb``): with every decision's true weight, the widest
      decision path over the mean, less one LSB (Hsu's missing level).

    ``dac_inl_curve_lsb`` and ``dac_dnl_curve_lsb`` are the DAC's INL and DNL by code of the run at
    the 95th percentile of the DAC's worst INL (the worse side).
    """

    pelgrom: float
    main_p_f: np.ndarray
    diff_p_f: np.ndarray
    main_n_f: np.ndarray
    diff_n_f: np.ndarray
    dac_inl_lsb: np.ndarray
    dac_dnl_lsb: np.ndarray
    dnl_lsb: np.ndarray
    inl_lsb: np.ndarray
    missing_codes: np.ndarray
    gap_lsb: np.ndarray
    dac_inl_curve_lsb: np.ndarray
    dac_dnl_curve_lsb: np.ndarray

    @property
    def runs(self) -> int:
        return len(self.gap_lsb)

    @property
    def dac_inl_p95_lsb(self) -> float:
        """The DAC's worst INL, its 95th percentile over the runs."""
        return float(np.nanpercentile(self.dac_inl_lsb, 95))

    @property
    def inl_p95_lsb(self) -> float:
        """The converter's worst INL with its design weights, its 95th percentile over the runs."""
        return float(np.nanpercentile(self.inl_lsb, 95))

    @property
    def gap_p95_lsb(self) -> float:
        """What no calibration recovers, its 95th percentile over the runs."""
        return float(np.nanpercentile(self.gap_lsb, 95))


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSwitching(Analysis):
    """One point of a stage's switching curve on the bench as the CDAC sees it, where its lab
    analyses meet a converter's captures (``adc.analyze_switching`` gives it), as a converter's
    conversions meet the comparator's: the trials at one input (each one's input, common mode and
    decision; ``info`` and ``param`` the capture's), the stage that switches (``side``: ``p`` or
    ``n``; ``stage``, C0 first; ``direction``: ``1to0`` or ``0to1``), its difference plate switching
    with its main plate (``diffcaps`` 0) or against it (1), the scan's ``campaign``, the reference the
    plates switch to (``vdd_dac_v``), the array's ``stages``, the design's expectation of each stage's
    effective fraction (``expected_fraction``: its weight over the array's total and its top plate's
    parasitic; NaN where the array has no weights of its own) and the design of the comparator that
    decided (``comparator``: its characterization's identity)."""

    info: MeasInfo
    param: Any
    campaign: str
    side: str | None
    stage: int | None
    direction: str | None
    diffcaps: int
    trial_index: np.ndarray
    vin_diff_v: np.ndarray
    vin_cm_v: np.ndarray
    decision: np.ndarray
    vdd_dac_v: float
    stages: int
    expected_fraction: np.ndarray
    comparator: Any


@dataclass(frozen=True, slots=True)
class AnalysisTransition(Analysis):
    """The comparator's decision transition of one switching curve: its stage (side, element,
    direction and mode), its curve (each input's probability of a high decision and its trials) and
    its 50 % point (``transition_v``; NaN unless ``valid``)."""

    side: Literal["p", "n"]
    element: int
    direction: Literal["1to0", "0to1"]
    diffcaps: int
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray
    transition_v: float
    valid: bool


@dataclass(frozen=True, slots=True)
class AnalysisCapMismatch(Analysis):
    """Each stage's capacitance as a fraction of its side's total (C/Ctotal), from its switching
    curves: a row a side (P, N), a column a stage (C0 first). Its main and difference plates'
    fractions, its effective fraction (main less difference, as the converter switches them) and
    that by direction (``1to0``, ``0to1``), each mode's direction bias (half the difference of the
    directions: main and difference together, then against each other), and the design's
    expectation of the effective fraction (``expected_fraction``, a stage each)."""

    main_fraction: np.ndarray
    diff_fraction: np.ndarray
    effective_fraction: np.ndarray
    effective_fraction_by_direction: np.ndarray
    direction_bias: np.ndarray
    expected_fraction: np.ndarray

    @property
    def fraction(self) -> np.ndarray:
        """Each stage's effective fraction, P's and N's mean (what the converter's decision weighs)."""
        return (self.effective_fraction[0] + self.effective_fraction[1]) / 2.0

    @property
    def fraction_error(self) -> np.ndarray:
        """Each stage's effective fraction (P's and N's mean) less the design's expectation."""
        return self.fraction - self.expected_fraction

    @property
    def asymmetry(self) -> np.ndarray:
        """Each stage's effective fraction, P's less N's."""
        return self.effective_fraction[0] - self.effective_fraction[1]

    @property
    def separation(self) -> np.ndarray:
        """Each stage's difference plates, P's and N's together: the mean of the sides' main-plus-
        difference less main-less-difference fractions."""
        return self.diff_fraction[0] + self.diff_fraction[1]

    @property
    def main(self) -> np.ndarray:
        """Each stage's main plate's fraction, P's and N's mean."""
        return (self.main_fraction[0] + self.main_fraction[1]) / 2.0

    @property
    def bias(self) -> np.ndarray:
        """Each stage's direction bias as the converter switches it (main and difference plates
        against each other), P's and N's mean."""
        return (self.direction_bias[0, :, 1] + self.direction_bias[1, :, 1]) / 2.0
