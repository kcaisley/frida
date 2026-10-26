"""The CDAC's analysis results (``flow.cdac.analysis``), pure data."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow.pipeline import Analysis


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSettling(Analysis):
    """Each stage's switching, C0 first, up (``rise``: the differential top plate rising) and down.

    ``step_*_v`` is the differential top plate's step, ``delay_*_s`` the driver's from the state's
    edge to its main bottom plate's, ``settling_*_s`` the time from the state's edge until the step
    stays within ``tolerance_v`` (half an LSB) of its final value; NaN where an edge is missing.
    ``ideal_step_v`` is the step the capacitances alone give, ``full_scale_v`` the converter's.

    The behavioral ADC (``flow.adc.behavioral``) starts each stage's step its driver's delay after
    the edge and settles it as one exponential: ``tau_s`` is the time constant that brings the
    measured step within half an LSB exactly when SPICE does, (settling - delay) / ln(|step| / half
    an LSB), in each stage's slower direction (0 for a step that never leaves the tolerance). A
    stage's main and difference plates move in opposite directions, so a small net step can follow a
    large transient that its plates' drivers leave behind; the time constant carries it.
    """

    lsb_v: float
    full_scale_v: float
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
    """The plates' Monte Carlo at one condition (``pelgrom``: Pelgrom's coefficient, a fraction;
    ``gradient_per_um``): each run's drawn plates (F, a row a run, C0 first; zero where the design
    has no plate) and what they give, a value a run:

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
    gradient_per_um: float
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
