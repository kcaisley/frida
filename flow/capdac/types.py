"""The capacitive DAC's analysis results (``flow.capdac.analysis``), pure data: a simulation's
settling and its plates' Monte Carlo, and the bench's switching curves (``AnalysisSwitching``, a
converter's capture as the CDAC sees it), each curve's transition (``AnalysisTransition``) and each
stage's capacitance from them (``AnalysisCapMismatch``)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, MeasInfo, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSettling(Analysis):
    """Each stage's switching, C0 first, up (``rise``: the differential top plate rising) and down.

    ``step_*_v`` is the differential top plate's step, ``delay_*_s`` the driver's from the state's
    edge to its main bottom plate's, ``settling_*_s`` the time from the state's edge until the step
    stays within ``tolerance_v`` (half an LSB) of its final value; NaN where an edge is missing.
    ``gain`` is the drawn array's against its design (its top plates' load beyond the design's
    plates, fitted to the steps); ``ideal_step_v`` the step the design's weights give at that gain.
    ``full_scale_v`` is the drawn array's: half the sum of its steps, the range the converter's
    decisions span (``Model.full_scale_v``'s, the mean of both directions), and ``lsb_v`` its LSB.

    The bench switches both sides at once (P up, N down): a step of 2^N w / W of the converter's
    LSB. The converter switches one side a decision, from its A state (``TbParams.astate``): half
    the step, settling ln 2 time constants sooner where it settles as one pole. ``side_settling_s``
    is that settling, each stage's P top plate alone (``vdac_p``) in the direction the converter
    switches it, to the same half LSB; the two sides are separate circuits on an ideal supply, so it
    is the converter's own.

    The behavioral ADC (``flow.adc.sim``) starts each stage's step its driver's delay after
    the edge and settles it as one exponential: ``tau_s`` is the time constant that brings the
    measured step within half an LSB exactly when SPICE does, (settling - delay) / ln(|step| / half
    an LSB), in each stage's slower direction (0 for a step that never leaves the tolerance; NaN
    where its delay or settling was not measured). A stage's main and difference plates move in
    opposite directions, so a small net step can follow a large transient that its plates' drivers
    leave behind; the time constant carries it.

    ``energy_rise_j``, ``energy_fall_j``: the supply's energy over each window, both sides'
    drivers and the reference's charge (the bench's supply is both); ``excursion_v`` the farthest
    the P side's bottom plates go past the rails; ``settle_s`` and ``budget_s`` the design's limit
    (``settle_ps``) and its drivers' typical budget, ``reference_v`` the bench's supply and
    ``load_f`` the design's top-plate load (each NaN or None where a measurement holds none).
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
    side_settling_s: np.ndarray | None = None
    energy_rise_j: np.ndarray | None = None
    energy_fall_j: np.ndarray | None = None
    excursion_v: float = math.nan
    settle_s: float = math.nan
    budget_s: float = math.nan
    reference_v: float = math.nan
    load_f: float = math.nan

    @property
    def tolerance_v(self) -> float:
        # [Razavi-ADC] Sec. 8.2.2, p. 150: the error band, +-0.5 LSB about the final value
        # Terms: LSB ``lsb_v``, the drawn array's.
        return self.lsb_v / 2

    @property
    def settled(self) -> bool:
        """Whether every step settled in its window's first half: its end is its final value (the
        measurement's validity; the settling's limit is ``settle_s``, ``analysis.metrics``)."""
        # not in the reference texts: a step that settles in its window's first half has its final
        #   value at the window's end, so the measured step is the settled one
        times = np.concatenate([self.settling_rise_s, self.settling_fall_s])
        return bool(np.all(np.isfinite(times)) and np.all(times < self.window_s / 2))

    @property
    def step_error_lsb(self) -> float:
        """The largest step's difference from the design weights' at the drawn gain (a unit drawn other
        than designed), in the LSB of the design's steps at that gain."""
        # not in the reference texts: max |s_k - g d_k| over both directions, in the LSB the
        #   design's steps give at the gain g: sum(g d_k) / 2^N, 2^N = 2 FS / LSB
        # Terms: s_k ``step_*_v``; g d_k ``ideal_step_v``; FS, LSB ``full_scale_v``, ``lsb_v``.
        # Holds for: both directions; the fall's design step is the rise's negated.
        error = np.abs(np.concatenate([self.step_rise_v - self.ideal_step_v, self.step_fall_v + self.ideal_step_v]))
        lsb_at_gain = float(np.sum(self.ideal_step_v)) * self.lsb_v / (2 * self.full_scale_v)
        return float(np.max(error)) / lsb_at_gain

    @property
    def settling_s(self) -> np.ndarray:
        """Each stage's settling time, the slower direction's."""
        # not in the reference texts: each stage's slower direction, max(t_s rise, t_s fall)
        return np.maximum(self.settling_rise_s, self.settling_fall_s)

    @property
    def delay_s(self) -> np.ndarray:
        """Each stage's driver delay, in its slower direction."""
        # [Baker] Fig. 10.9, p. 333: the delay between the input's and the output's 50 % points
        # Terms: the input the state ``dac_state_p_<k>``, the output the main bottom plate ``main_<k>``.
        return np.where(self.settling_rise_s >= self.settling_fall_s, self.delay_rise_s, self.delay_fall_s)

    @property
    def step_v(self) -> np.ndarray:
        """Each stage's step, in its slower direction."""
        return np.where(self.settling_rise_s >= self.settling_fall_s, self.step_rise_v, self.step_fall_v)

    @property
    def tau_s(self) -> np.ndarray:
        """Each stage's time constant: started at its driver's delay, its step comes within half an
        LSB when it settles (its slower direction); 0 where the step never leaves the tolerance or
        settles before the delay, NaN where its delay or settling was not measured."""
        # not in the reference texts (the behavioral model's own): tau = (t_s - t_d) / ln(|s| / (LSB / 2)),
        #   from [Razavi-ADC] Eq. (8.14), p. 151 (t_s = tau ln(step / half an LSB) for one pole) started
        #   at the driver's delay instead of the edge
        # Terms: t_s ``settling_s``; t_d ``delay_s`` (the main bottom plate's 50 %); s ``step_v``.
        # Ours against the source: the step is not one pole (its plates' drivers, the difference
        #   plate first): tau reproduces the half-LSB instant alone, not the residue before it.
        # Holds for: the bench's two-sided step; the converter's one side reaches half an LSB ln 2
        #   tau sooner on the same exponential.
        ratios = np.abs(self.step_v) / self.tolerance_v
        return np.asarray(
            [
                math.nan
                if not (math.isfinite(settling) and math.isfinite(delay))
                else (settling - delay) / math.log(ratio)
                if ratio > 1 and settling > delay
                else 0.0
                for settling, delay, ratio in zip(self.settling_s, self.delay_s, ratios, strict=True)
            ]
        )


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """The record's numbers (``analysis.metrics``, a dict of these names) and which way is better:
    the settling bench's at the typical corner, the slow and fast corners' settling and whether
    every stage settles within ``settle_ps`` at all three, and the plates' Monte Carlo at each
    coefficient, a capacitor's (the schematic's plates at their design values: no layout reaches
    them, so a post-layout record's are its pre-layout ones). ``stages`` and ``window_s`` are the
    design's and the bench's, reported for the viewer, not measured."""

    stages: float = metric("The stages, C0 to the last (the design's: Params)", "none")
    full_scale_v: float = metric("The drawn array's full scale (+-): half the sum of its steps", "higher")
    full_scale_fraction: float = metric("The full scale over the reference (the bench's supply)", "higher")
    full_scale_meets_rule: bool = metric("Whether the full scale is at least 0.80 of the reference", "true")
    gain: float = metric("The drawn steps against the design's, least squares", "higher")
    lsb_v: float = metric("The converter's LSB, twice the drawn full scale over 2^N", "none")
    ktc_noise_ratio: float = metric(
        "Both sides' sampled kT/C noise over the quantization noise, at the drawn top plate and LSB", "lower"
    )
    settling_max_s: float = metric("The slowest stage's settling to half an LSB, both sides switched", "lower")
    settling_msb_s: float = metric("C0's settling to half an LSB, both sides switched", "lower")
    settling_side_max_s: float = metric(
        "The slowest stage's settling to half an LSB, one side in the converter's direction", "lower"
    )
    settling_slow_max_s: float = metric("The slowest settling at the slow corner, 90 % supply, hot", "lower")
    settling_fast_max_s: float = metric("The slowest settling at the fast corner, 110 % supply", "lower")
    settling_budget_ratio: float = metric("The slowest typical settling over the drivers' budget", "lower")
    settles_in_time: bool = metric("Whether every stage settles within settle_ps at every corner run", "true")
    delay_max_s: float = metric("The largest driver delay (state to main bottom plate, 50 %)", "lower")
    tau_max_s: float = metric("The largest time constant of the behavioral model", "lower")
    window_s: float = metric("The bench's window a stage and direction (the bench's)", "none")
    step_error_lsb: float = metric("The largest step's error against the design's at the gain", "lower")
    supply_energy_j: float = metric("The bench's supply energy over every window, both sides", "lower")
    excursion_v: float = metric("The farthest a bottom plate goes past the rails, every corner run", "lower")
    mc_a1_dac_inl_p95_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a1_dac_inl_p95_upper_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a1_inl_p95_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a1_inl_p95_upper_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a1_gap_p95_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, what no calibration recovers: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a1_gap_p95_upper_lsb: float = metric(
        "At 0.1 %·sqrt(fF) a capacitor, what no calibration recovers: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a5_dac_inl_p95_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a5_dac_inl_p95_upper_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a5_inl_p95_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a5_inl_p95_upper_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a5_gap_p95_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, what no calibration recovers: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a5_gap_p95_upper_lsb: float = metric(
        "At 0.5 %·sqrt(fF) a capacitor, what no calibration recovers: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a10_dac_inl_p95_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a10_dac_inl_p95_upper_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, the DAC's worst INL (its own LSB): the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a10_inl_p95_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a10_inl_p95_upper_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, the converter's worst INL with its design weights: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )
    mc_a10_gap_p95_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, what no calibration recovers: its 95th percentile over the runs (the schematic's plates)",
        "lower",
    )
    mc_a10_gap_p95_upper_lsb: float = metric(
        "At 1 %·sqrt(fF) a capacitor, what no calibration recovers: the 95 % upper confidence bound of its 95th percentile",
        "lower",
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMismatch(Analysis):
    """The plates' Monte Carlo at one condition (``pelgrom``: the mismatch coefficient, a fraction,
    one capacitor's: a pair of like plates differs by sqrt(2) times it, ``TbParams.pelgrom``):
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
        # not in the reference texts: the 95th percentile of the runs' worst |INL| (linear
        #   interpolation between order statistics, NumPy's), a sample of ``runs`` draws
        return float(np.nanpercentile(self.dac_inl_lsb, 95))

    @property
    def inl_p95_lsb(self) -> float:
        """The converter's worst INL with its design weights, its 95th percentile over the runs."""
        # not in the reference texts: as ``dac_inl_p95_lsb``, of the converter's worst |INL|
        return float(np.nanpercentile(self.inl_lsb, 95))

    @property
    def gap_p95_lsb(self) -> float:
        """What no calibration recovers, its 95th percentile over the runs."""
        # not in the reference texts: as ``dac_inl_p95_lsb``, of the gap
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
        # not in the reference texts: the two sides' mean of C_k / C_total (the bench's own)
        return (self.effective_fraction[0] + self.effective_fraction[1]) / 2.0

    @property
    def fraction_error(self) -> np.ndarray:
        """Each stage's effective fraction (P's and N's mean) less the design's expectation."""
        # not in the reference texts: the measured fraction less the design's
        return self.fraction - self.expected_fraction

    @property
    def asymmetry(self) -> np.ndarray:
        """Each stage's effective fraction, P's less N's."""
        # not in the reference texts: the sides' difference of C_k / C_total
        return self.effective_fraction[0] - self.effective_fraction[1]

    @property
    def separation(self) -> np.ndarray:
        """Each stage's difference plates, P's and N's together: the mean of the sides' main-plus-
        difference less main-less-difference fractions."""
        # not in the reference texts: mode 0 (main plus difference) less mode 1 (main less
        #   difference), halved a side and summed over both: twice the difference fraction's mean
        return self.diff_fraction[0] + self.diff_fraction[1]

    @property
    def main(self) -> np.ndarray:
        """Each stage's main plate's fraction, P's and N's mean."""
        # not in the reference texts: the sides' mean of (mode 0 + mode 1) / 2
        return (self.main_fraction[0] + self.main_fraction[1]) / 2.0

    @property
    def bias(self) -> np.ndarray:
        """Each stage's direction bias as the converter switches it (main and difference plates
        against each other), P's and N's mean."""
        # not in the reference texts: half the 1-to-0 less the 0-to-1 fraction, mode 1, the sides' mean
        return (self.direction_bias[0, :, 1] + self.direction_bias[1, :, 1]) / 2.0
