"""The comparator's analysis results (``flow.comp.analysis``), pure data.

``AnalysisDecisions`` is where a comparator's measurement and a lab capture meet: each trial's
input, decision and whether the latch had decided, read from a simulation (``analyze_decisions``)
or captured on the bench (``flow.scans``); the offset, noise and common-mode analyses take it, for
both.

The comparator inside a converter is seen through the converter's captures, each as its comparator
sees it (``AnalysisConversions``, which the converter gives): its output at the scope, COMP_OUT,
against its clock COMP on the bench (``AnalysisScopeEdges``), and in a simulation its SR latch's
output and its regenerative latch (XC) over each decision (``AnalysisEdgeEye``,
``AnalysisResponse``). Their maps are each cell's share of what was folded into it, NaN where
nothing was (a map's empty cell).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, MeasInfo, Wave, metric


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


@dataclass(frozen=True, slots=True)
class AnalysisConversions(Analysis):
    """A converter's capture as its comparator sees it (``adc.analyze_conversions``), where the
    comparator's analyses of a converter meet its captures, as a CDAC's switching curves meet them
    in ``AnalysisDecisions``: each record of ``wave`` one conversion (a scope's ``seq_comp`` and
    ``comp_out``; a simulation's ``clk_comp``, ``comp_out_p``, ``comp.latch_p``, ``comp.latch_n``,
    ``seq_init``, ``seq_logic``), its ``decisions`` (a clock rise each), the ``sequence`` its
    testbench programs (INIT, SAMP, COMP and LOGIC's patterns) at ``symbol_rate_hz``, the decisions'
    spacing it programs (``decision_period_s``; NaN where its clock rises are not evenly spaced), its
    conversion rate without idle symbols, and its analog and digital supplies."""

    wave: Wave | None
    sequence: tuple[str, str, str, str]
    symbol_rate_hz: float
    decisions: int
    decision_period_s: float
    conversion_rate_hz: float
    vdd_a_v: float
    vdd_d_v: float


@dataclass(frozen=True, slots=True)
class AnalysisScopeEdges(Analysis):
    """The comparator's output edges in a converter's scope records (the bench's): its clock COMP
    and its output COMP_OUT as the scope sees them, past the pads, the board and the probes; one
    sequence and symbol rate, every record one complete conversion.

    Rows of ``clock_edges_s``, ``delays_s`` and ``jitter_s`` are records, columns the decisions of
    one conversion (B0 first): each COMP rise; the time from it to COMP_OUT's one crossing of its
    midpoint within the decision (NaN where it has none, ``unchanged``, more than one,
    ``multiple``, or ends the decision on the other side, ``unsettled``: counts per decision); the
    rise's distance from its place in the period after B0's.

    COMP_OUT as maps over the voltage's cells (``voltage_v``: their edges): every decision of every
    record folded at its COMP rise (``eye_share``, on ``eye_time_s``: the cells' edges from the
    rise), and every record from its B0 rise over the conversion (``timing_share``, on
    ``timing_time_s``), each cell's share of the decisions or the records. COMP is high from its
    rise for ``clock_high_s`` (the median), and over the conversion from each decision's
    ``rise_s`` to its ``fall_s`` after B0's rise (medians over the records). ``response_share``:
    each decision's delays (a column each) over cells of ``response_s`` (their edges), each cell's
    share of that decision's timed transitions, and their median, ``response_median_s``.
    """

    clock_edges_s: np.ndarray
    delays_s: np.ndarray
    jitter_s: np.ndarray
    unchanged: np.ndarray
    multiple: np.ndarray
    unsettled: np.ndarray
    decision_period_s: float
    conversion_rate_hz: float
    voltage_v: np.ndarray
    eye_time_s: np.ndarray
    eye_share: np.ndarray
    timing_time_s: np.ndarray
    timing_share: np.ndarray
    clock_high_s: float
    rise_s: np.ndarray
    fall_s: np.ndarray
    response_s: np.ndarray
    response_share: np.ndarray
    response_median_s: np.ndarray

    @property
    def decision_count(self) -> int:
        return self.clock_edges_s.shape[1]

    @property
    def records(self) -> int:
        return self.clock_edges_s.shape[0]

    @property
    def delay_bounds_s(self) -> tuple[float, float]:
        valid = self.delays_s[np.isfinite(self.delays_s)]
        return float(valid.min()), float(valid.max())


@dataclass(frozen=True, slots=True)
class AnalysisEdgeEye(Analysis):
    """A simulated converter's comparator over each of its saved conversions (a SPICE capture's
    internal nets): its SR latch's positive output (``sr_*``) and its regenerative latch's
    magnitude |P - N| (``xc_*``), as maps over the voltage's cells (``voltage_v``: their edges,
    -0.1 to 1.1 of the supply ``supply_v``). ``*_eye``: every decision of every conversion folded at
    its clock's rise (on ``eye_time_s``, the cells' edges from it, -0.1 to 1.1 decision periods);
    ``*_timing``: every conversion from B0's clock rise to a period after its last decision's (on
    ``timing_time_s``); each cell's share of the decisions or the conversions.

    ``decision_edge_s`` is each decision's clock rise after B0's, ``fall_s`` its fall (medians over
    the conversions), ``clock_high_s`` how long the clock is high from a rise (the median), and
    ``decision_period_s`` the median spacing of the rises.
    """

    decision_period_s: float
    decision_edge_s: np.ndarray
    fall_s: np.ndarray
    clock_high_s: float
    supply_v: float
    records: int
    voltage_v: np.ndarray
    eye_time_s: np.ndarray
    timing_time_s: np.ndarray
    sr_eye: np.ndarray
    xc_eye: np.ndarray
    sr_timing: np.ndarray
    xc_timing: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisResponse(Analysis):
    """A simulated converter's comparator: each decision's response from its clock's rise, valid at
    half the supply (NaN where it did not settle in its window): its regenerative latch's
    (``internal_response_s``: one of its XC nodes below half the analog supply and the other above
    it before the clock resets) and its SR latch's positive output's (``sr_response_s``: in the half
    of the rail the XC latch's final polarity asks for, before the next clock rise). An SR output
    already holding that state at the rise is ``sr_held``, not a response of zero.

    Each as a map over the decisions (a column each, B0 first): ``xc_share`` and ``sr_share`` each
    decision's responses over cells of ``xc_s`` and ``sr_s`` (their edges), each cell's share of the
    decision's timed responses; ``xc_median_s`` and ``sr_median_s`` their medians (NaN: none).
    """

    conversion_index: np.ndarray
    decision_index: np.ndarray
    internal_response_s: np.ndarray
    sr_response_s: np.ndarray
    sr_held: np.ndarray
    sample_interval_s: float
    conversion_rate_hz: float
    xc_s: np.ndarray
    xc_share: np.ndarray
    xc_median_s: np.ndarray
    sr_s: np.ndarray
    sr_share: np.ndarray
    sr_median_s: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A comparator's numbers (``analysis.metrics``): the delays and energy at 0.5 mV and 100 mV, the
    0.1 mV delay and regeneration time constant, the kickback, the slowest small-input delay over the
    supply and whether it decides within the clock, all from the screen's runs (``Level.SCREEN``);
    the nominal common mode's noise and offset (None unless valid), the fraction of its decisions
    unresolved (``Level.SEARCH``); the largest valid noise over the common mode (``Level.FULL``).
    None where the runs of a level that measures it did not run."""

    delay_0p5mv_s: float = metric("Delay at 0.5 mV, the slowest of its decisions", "lower")
    delay_100mv_s: float = metric("Delay at 100 mV, the slowest of its decisions", "lower")
    delay_0p1mv_s: float = metric("Delay at 0.1 mV", "lower")
    regeneration_tau_s: float = metric("Regeneration time constant", "lower")
    energy_0p5mv_j: float = metric("Energy per decision at 0.5 mV, the clock's drivers included", "lower")
    energy_100mv_j: float = metric("Energy per decision at 100 mV, the clock's drivers included", "lower")
    kickback_v: float = metric("Largest excursion of either input over a decision", "lower")
    kickback_diff_v: float = metric("Largest excursion of the input difference over a decision", "lower")
    delay_max_supply_s: float = metric("Slowest 0.5 mV delay over the supply", "lower")
    decides_in_time: bool | None = metric("Decides within the clock", "true", None)
    noise_v: float | None = metric("Input-referred noise at the nominal common mode", "lower", None)
    offset_v: float | None = metric("Systematic offset at the nominal common mode", "none", None)
    unresolved_fraction: float | None = metric("Fraction of the S-curve's decisions unresolved", "lower", None)
    noise_max_v: float | None = metric("Largest valid noise over the common mode", "lower", None)
