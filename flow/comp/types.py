"""The comparator's analysis results (``flow.comp.analysis``), pure data.

``AnalysisDecisions`` is where a comparator's measurement and a lab capture meet: each trial's
input, decision and whether the latch had decided, read from a simulation (``analyze_decisions``)
or captured on the bench (``flow.scans``); the offset, noise and common-mode analyses take it, for
both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from flow.pipeline import Analysis, MeasInfo, Wave


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDecisions(Analysis):
    """A comparator's trials: each trial's differential input and common mode, its decision (1:
    the positive output high), and, from a simulation, whether the latch had decided when it was
    read (``resolved``: the latch's nodes half the supply apart; an undecided latch leaves the
    output stage holding the previous decision). ``info`` and ``param`` are the run's (a capture's
    batches, its scan parameters); ``fastrx_word`` and ``fastrx_frame`` the raw words a capture
    decoded its decisions from, ``wave`` the oscilloscope's record of the point where it took one."""

    info: MeasInfo
    param: Any
    trial_index: np.ndarray
    vin_diff_v: np.ndarray
    vin_cm_v: np.ndarray
    decision: np.ndarray
    resolved: np.ndarray | None = None
    fastrx_word: np.ndarray | None = None
    fastrx_frame: np.ndarray | None = None
    wave: Wave | None = None

    @property
    def tb(self) -> Any:
        """The testbench parameters, nested inside scan parameters for a physical capture."""
        return getattr(self.param, "tb", self.param)


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTiming(Analysis):
    """Each trial's clock-to-decision delay and settling, and whether it resolved."""

    trial_index: np.ndarray
    clock_to_decision_s: np.ndarray
    settling_s: np.ndarray
    unresolved: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDelay(Analysis):
    """Comparator clock-to-decision delay over common mode and differential input.

    ``delay_s`` has one row per common mode and one column per differential
    input: the median delay of that point's resolved trials, NaN where none
    resolved.
    """

    vin_cm_v: np.ndarray
    vin_diff_v: np.ndarray
    delay_s: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMetastability(Analysis):
    """The delay over the positive inputs of one common mode, smallest first, and the latch's
    regeneration time constant: the delay's growth per e-fold fall of the input, between the two
    smallest."""

    input_v: np.ndarray
    delay_s: np.ndarray
    regeneration_tau_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisClockCheck(Analysis):
    """Whether a comparator decides within its clock: its noise-free decisions over the input at
    the clock against the same at a longer one. ``decides_in_time`` is the verdict, ``reasons`` why
    not."""

    evaluation_s: float
    unresolved_count: int
    decisions_match: bool
    delay_change: float  # the largest relative change of a positive input's delay
    resolved_10uv_s: float  # 10 uV's delay, extrapolated
    decides_in_time: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisKickback(Analysis):
    """The inputs' largest excursion over the first decision from where they started, each input
    alone (what a DAC's top plate sees) and their difference."""

    kickback_v: float
    kickback_diff_v: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisScurve(Analysis):
    """An S-curve's decisions per input: P(high) of the resolved ones (NaN where none resolved), the
    fraction unresolved, and the fraction unresolved over every input."""

    vin_diff_v: np.ndarray
    probability: np.ndarray
    unresolved_fraction: np.ndarray
    total_unresolved_fraction: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPower(Analysis):
    """The supply's average power over each run, and the energy of one decision at that power."""

    supply_v: np.ndarray
    average_power_w: np.ndarray
    energy_per_decision_j: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisOffsetNoise(Analysis):
    """Comparator decision probability, offset, and input-referred noise at one common mode."""

    vin_cm_v: float
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray
    offset_v: float
    noise_sigma_v: float
    decision_polarity: Literal[-1, 1]
    validity: Literal["valid", "unbracketed", "non_monotonic", "unresolved"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCommonMode(Analysis):
    """Comparator offset, noise, and validity across input common modes, each common mode's S-curve
    a row of ``vin_diff_v``, ``decision_probability`` and ``trial_count`` (NaN and 0 past its
    inputs).

    ``stuck-low`` and ``stuck-high`` mark a curve pinned below 0.1 or above 0.9
    probability whose expected transition, given by a valid neighboring common
    mode's offset, lies inside its swept input range.
    """

    vin_cm_v: np.ndarray
    offset_v: np.ndarray
    noise_sigma_v: np.ndarray
    decision_polarity: np.ndarray
    validity: tuple[Literal["valid", "unbracketed", "non_monotonic", "unresolved", "stuck-low", "stuck-high"], ...]
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSamplingNoise(Analysis):
    """Comparator offset and noise of one ADC over how its DAC couples to the inputs: each curve one
    P-side coupling (``coupling_percent`` of VDD_DAC, the N side the rest) in one sampling mode
    (``track`` or ``hold``), its S-curve a row of ``vin_diff_v``, ``decision_probability`` and
    ``trial_count`` (NaN and 0 past its inputs)."""

    coupling_percent: np.ndarray
    sampling_mode: tuple[str, ...]
    offset_v: np.ndarray
    noise_sigma_v: np.ndarray
    decision_polarity: np.ndarray
    validity: tuple[Literal["valid", "unbracketed", "non_monotonic", "unresolved"], ...]
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray
