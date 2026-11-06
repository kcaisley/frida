"""The ADC's analysis results (``flow.adc.analysis``), pure data."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.pipeline import Analysis


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMismatch(Analysis):
    """An array's mismatch statistics at a Pelgrom coefficient of 1 (every sigma scales with A):
    by stage (C0 first) and by code (1 to code_max - 1), and the distinct code widths the worst
    DNL and the missing codes are over. ``analyze_mismatch`` derives them from a capture's nominal
    array; ``flow.adc.analysis`` predicts from them the worst DNL and INL, the missing codes and
    each stage's margin over its sigma at a coefficient A (a fraction: 0.001 is 0.1 %·sqrt(fF))."""

    weight_sigma: np.ndarray  # each stage's step on one side (LSB)
    transition_sigma: np.ndarray  # the largest DNL sigma of a code that stage's decision bounds (LSB)
    margin_lsb: np.ndarray  # each stage's redundancy margin (Ogawa et al.), at the design weights
    margin_sigma: np.ndarray  # the margin's own sigma: stage k's step and every later one's (LSB)
    gamma_error: np.ndarray  # each stage's step on both sides less its decoder weight, gain off (LSB)
    gamma_sigma: np.ndarray  # and its sigma
    dnl_mean: np.ndarray  # the nominal array's DNL by code (its own error against the design weights)
    dnl_sigma: np.ndarray
    inl_mean: np.ndarray
    inl_sigma: np.ndarray
    width_mean: np.ndarray  # by distinct width: its nominal width (LSB), sigma and how many codes
    width_sigma: np.ndarray
    width_dnl_sigma: np.ndarray  # the same as DNL: the mean width and the gain taken off
    width_codes: np.ndarray
