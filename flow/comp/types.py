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

from .params import Validity


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
    """Each trial's clock-to-decision delay (to the latch's half swing, ``clock_to_decision_s``; to
    the held outputs' crossing, ``clock_to_output_s``, NaN where they did not change) and settling,
    and whether it resolved."""

    trial_index: np.ndarray
    clock_to_decision_s: np.ndarray
    clock_to_output_s: np.ndarray
    settling_s: np.ndarray
    unresolved: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDelay(Analysis):
    """Comparator clock-to-decision delay over common mode and differential input.

    ``delay_s`` has one row per common mode and one column per differential input: the median
    delay of that point's resolved trials that decided as its input's sign asks (any decision of a
    zero input), NaN where none did; ``slowest_s`` the slowest of them; ``output_delay_s`` and
    ``output_slowest_s`` the same to the held outputs (of the trials that changed them);
    ``against_sign`` how many of the point's resolved trials decided against its input's sign.
    A delay given without its trials has the median alone (``slowest_s`` and the rest None).
    """

    vin_cm_v: np.ndarray
    vin_diff_v: np.ndarray
    delay_s: np.ndarray
    slowest_s: np.ndarray | None = None
    output_delay_s: np.ndarray | None = None
    output_slowest_s: np.ndarray | None = None
    against_sign: np.ndarray | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMetastability(Analysis):
    """The delay over the positive inputs of one common mode, smallest first (``output_delay_s``:
    to the held outputs); the regeneration time constant, the delay's growth per e-fold fall of the
    input less the systematic offset (the latch's own where one stage regenerates alone:
    ``analysis._regeneration``), and that offset (``offset_v``), fitted together to the
    decisions near the offset; the delays over the input less the offset (``effective_v``,
    |V - V_OS| ascending: to the latch, ``effective_delay_s``, and to the held outputs,
    ``effective_output_s``, NaN where no decision there changed them; None without an offset); and
    how many of the run's resolved decisions went against their programmed input's sign
    (``against_sign``)."""

    input_v: np.ndarray
    delay_s: np.ndarray
    regeneration_tau_s: float
    output_delay_s: np.ndarray | None = None
    offset_v: float = float("nan")
    effective_v: np.ndarray | None = None
    effective_delay_s: np.ndarray | None = None
    effective_output_s: np.ndarray | None = None
    against_sign: int | None = None


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
    """The inputs' largest excursion over the first decision from where they started (up to the
    next decision's first clock edge), each input alone (what a DAC's top plate sees) and their
    difference, on the run's source; and the difference's error the
    decisions leave for the next ones, read as each later decision's clock edges reach the
    comparator (before they kick the inputs themselves) against the programmed input
    (``residual_diff_v``, the largest; NaN in a run of one decision)."""

    kickback_v: float
    kickback_diff_v: float
    residual_diff_v: float = float("nan")


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisScurve(Analysis):
    """An S-curve's decisions per input: the decision probability, the share of the resolved ones
    high (NaN where none resolved), the fraction unresolved, and the fraction unresolved over every
    input."""

    vin_diff_v: np.ndarray
    probability: np.ndarray
    unresolved_fraction: np.ndarray
    total_unresolved_fraction: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPower(Analysis):
    """The supply's average power over each run, and the energy of one decision at that power (the
    run's settled decisions, every input); each input's own (``point_energy_j``: a row a run, a
    column an input of ``vin_diff_v``, NaN where the run has no settled decision there; None in a
    power given without them); and each run's supply current late in the evaluation
    (``static_current_a``: its mean over the evaluation's last quarter up to the read, of the
    settled decisions; None in a power given without it)."""

    supply_v: np.ndarray
    average_power_w: np.ndarray
    energy_per_decision_j: np.ndarray
    vin_diff_v: np.ndarray | None = None
    point_energy_j: np.ndarray | None = None
    static_current_a: np.ndarray | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisStress(Analysis):
    """Every transistor's junctions and terminal pairs over runs at the supply's corners
    (``flow.circuit.oppoint.stress``): the largest forward bias of a junction (``forward_v``, its
    device ``forward_device``), the largest voltage across a pair of terminals (``terminal_v``, its
    device and pair), the limit a pair may reach (``limit_v``: the nominal supply times the largest
    corner), and the devices past it or past ``flow.circuit.oppoint.FORWARD_BIAS_V`` forward."""

    forward_v: float
    forward_device: str
    terminal_v: float
    terminal_device: str
    terminal_pair: str
    limit_v: float
    overstressed: tuple[str, ...]
    forward: tuple[str, ...]


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
    validity: Validity


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCommonMode(Analysis):
    """Comparator offset, noise, and validity across input common modes, each common mode's S-curve
    a row of ``vin_diff_v``, ``decision_probability`` and ``trial_count`` (NaN and 0 past its
    inputs).

    ``Validity.STUCK_LOW`` and ``STUCK_HIGH`` mark a curve pinned below 0.1 or above 0.9
    probability whose expected transition, given by a valid neighboring common
    mode's offset, lies inside its swept input range.
    """

    vin_cm_v: np.ndarray
    offset_v: np.ndarray
    noise_sigma_v: np.ndarray
    decision_polarity: np.ndarray
    validity: tuple[Validity, ...]
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
    validity: tuple[Validity, ...]
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
    supply and whether it decides within the clock, all from the screen's runs (``Level.SCREEN``),
    with, where their runs ran, the delays to the held outputs and the energy where they toggle, the
    supply's current late in the evaluation, the kickback left for the next decisions, the delay after a full-scale input, at the slow corner,
    over the common mode and on the converter's clocks, the decisions against their input's sign,
    and the devices' largest junction and terminal voltages; the nominal common mode's noise and
    offset (NaN unless valid), the fraction of its decisions unresolved (``Level.SEARCH``); the
    largest valid noise over the common mode (``Level.FULL``). None where the runs that measure it
    did not run."""

    # [Razavi-ADC] Sec. 7.3, p. 131: the comparator's speed, the time from the clock's rising edge
    # at V_DD/2 until |V_X - V_Y| reaches a set level
    # V_X, V_Y: latch_p, latch_n; the level: half the latch difference's own largest value over
    # the decision (analysis.analyze_timing), not a fixed voltage; the clock: the comparator's
    # own, behind its drivers. The slowest of the bench's decisions at the programmed input that
    # follow its sign. The latch's delay: the held outputs the converter reads change later, or,
    # with a weak init pair, earlier (delay_out_0p5mv_s)
    delay_0p5mv_s: float = metric("Delay at 0.5 mV, the slowest of its decisions that follow the input's sign", "lower")
    delay_100mv_s: float = metric("Delay at 100 mV, the slowest of its decisions that follow the input's sign", "lower")
    # [Razavi-ADC] Eq. (7.6), p. 136: the delay near metastability, growing as the input falls
    # the source's input is the imbalance from the balance point; this one is at the programmed
    # 0.1 mV, the offset not taken off: near metastability only where the systematic offset is
    # small against 0.1 mV (the curve over the input less the offset: analyze_metastability)
    delay_0p1mv_s: float = metric("Delay at a programmed input of 0.1 mV (the offset not taken off)", "lower")
    # [Razavi-ADC] Eq. (5.19), p. 78: the regeneration time constant
    # [Razavi-ADC] Eq. (7.6), p. 136: from the delay's shift over the log of the input less the
    # offset (analysis._regeneration, where its terms and where it holds are)
    regeneration_tau_s: float = metric(
        "Regeneration time constant: the delay's growth per e-fold fall of the input less the offset (the latch's "
        "own where one stage regenerates alone)",
        "lower",
    )
    # [Baker] Eq. (11.15), p. 355: the power, V_DD times the supply's average current; a decision's
    # energy that power over the clock's frequency
    # the supply: the comparator's (vvdd), its clock chains on it; a cycle of the bench's clock
    # (analysis.analyze_power); holds as a decision's own for a latch that cuts its current once
    # decided (idd_static_a)
    energy_0p5mv_j: float = metric(
        "Energy per decision at 0.5 mV after 0.5 mV (the held outputs unchanged), the clock's drivers included",
        "lower",
    )
    energy_100mv_j: float = metric(
        "Energy per decision at 100 mV after 100 mV (the held outputs unchanged), the clock's drivers included",
        "lower",
    )
    # [Razavi-ADC] Sec. 5.7.4, p. 88: kickback noise, the error the comparator's switching leaves
    # at its input
    # the source's is a current through the driving impedance; these are the voltages it leaves
    # on the kickback run's source (params.KICKBACK_SOURCE: 1 pF a side behind 1 Mohm), over a
    # decision and its reset, and hold for that source alone
    kickback_v: float = metric("Largest excursion of either input over a decision, on the 1 pF source", "lower")
    kickback_diff_v: float = metric(
        "Largest excursion of the input difference over a decision, on the 1 pF source", "lower"
    )
    # [Razavi-ADC] Sec. 7.3, p. 131: the comparator's speed, at each supply of the sweep
    # the largest over params.SUPPLY_SWEEP of each corner's slowest 0.5 mV decision (NaN where a
    # corner did not resolve), the common mode following the supply
    delay_max_supply_s: float = metric("Slowest 0.5 mV delay over the supply", "lower")
    # [Razavi-ADC] Eq. (7.7), p. 136: 10 uV from the offset decided n tau_reg ln 10 after the
    # decision nearest the offset
    # not in the reference texts: the verdict's other tests: every decision resolved and the same,
    # the delays within 10 %, at twice the clock (analysis.analyze_clock_check)
    decides_in_time: bool | None = metric("Decides within the clock", "true", None)
    # [Razavi-ADC] Eq. (6.63), p. 118: the input-referred rms noise, the sigma of the Gaussian whose
    # cumulative area gives the decisions' shares
    noise_v: float | None = metric("Input-referred noise at the nominal common mode", "lower", None)
    # [Razavi-ADC] Sec. 5.1, p. 71: the input-referred offset, the input at which the circuit balances
    offset_v: float | None = metric(
        "Systematic offset at the nominal common mode (NaN unless its S-curve locates it)", "none", None
    )
    # [Razavi-ADC] Sec. 6.2.1, p. 109: a metastable state, the output short of its level in the time
    # allowed (here the latch short of half the supply apart when read)
    unresolved_fraction: float | None = metric("Fraction of the S-curve's decisions unresolved", "lower", None)
    # [Razavi-ADC] Eq. (6.63), p. 118: the input-referred noise, at each common mode of the sweep
    # the largest sigma of the valid S-curve fits over params.CM_SWEEP; from more than one common
    # mode alone
    noise_max_v: float | None = metric("Largest valid noise over the common mode", "lower", None)
    # [Razavi-ADC] Sec. 7.5, p. 134: the RS latch's delay, part of the converter's decision time
    # [Baker] Fig. 10.9, p. 333: a propagation delay, to an output's 50 % point
    # timed to outp = outn, between the two outputs' 50 % points (analysis._output_delay), on
    # TbParams.output_load_f a side, at the input less the offset
    delay_out_0p5mv_s: float | None = metric(
        "Delay to the held outputs at 0.5 mV from the offset, the outputs toggling after 100 mV", "lower", None
    )
    delay_out_100mv_s: float | None = metric(
        "Delay to the held outputs at 100 mV from the offset, the outputs toggling after 100 mV", "lower", None
    )
    # [Baker] Eq. (11.15), p. 355: the power, V_DD times the supply's average current; a decision's
    # energy that power over the clock's frequency
    # as energy_0p5mv_j, of the +0.5 mV decisions that change the held outputs (each after 100 mV
    # of either sign): the SR latch, the buffers and TbParams.output_load_f a side switch too
    energy_toggle_0p5mv_j: float | None = metric(
        "Energy per decision at 0.5 mV toggling the held outputs (after 100 mV), the clock's drivers included",
        "lower",
        None,
    )
    # [Razavi-PLL] Example 3.5, p. 70: the supply current, I_DD, over time
    # its mean over the last quarter of the evaluation up to the read, the larger of the 0.5 mV
    # and 100 mV runs': leakage for a latch that cuts its current once it has decided
    # ([Razavi-ADC] Sec. 5.8.4, pp. 96-97: no static power); where it is more, the energies
    # above grow with the clock's high time. A decision still settling then shows its own
    # current, and a capacitor to the supply that is still charging (a dynamic bias's) a
    # negative one
    idd_static_a: float | None = metric(
        "Supply current over the last quarter of the evaluation (static: a latch that cuts its current draws "
        "leakage alone)",
        "lower",
        None,
    )
    # [Razavi-ADC] Sec. 7.8, p. 137: whether the kickback does harm depends on when it happens: what
    # is left on the inputs when the next decision begins
    kickback_residual_diff_v: float | None = metric(
        "Input difference's error left as the next decisions' clock edges begin, on the 1 pF source", "lower", None
    )
    # not in the reference texts: the delay of a small decision after a full-scale one of the
    # other sign (the converter's first decision's, params.ADC_FULL_SCALE of the supply). It
    # probes what the sources define as a voltage: the dynamic offset of [Razavi-ADC] Sec. 7.1,
    # Fig. 7.2, pp. 129-130 (the difference a decision leaves on the pair's drains) and the
    # hysteresis of [Pelgrom] Sec. 12.2.4, p. 620 (the trip level's memory)
    delay_recovery_0p5mv_s: float | None = metric(
        "Delay at 0.5 mV after a full-scale decision of the other sign, the slowest that follows the input's sign",
        "lower",
        None,
    )
    # [Razavi-ADC] Eqs. (5.2)-(5.3), p. 72: the decision a comparator owes its input's sign
    # counted: the delay benches' resolved decisions against their programmed input's sign (the
    # offset not taken off: an input between zero and the offset counts; a latch that repeats its
    # last decision at a small input counts in the runs that follow an input of either sign)
    decisions_against_sign: int | None = metric(
        "Delay benches' resolved decisions against their input's sign (0.5 and 100 mV, the supply, after full "
        "scale, the delay over the input and to the held outputs)",
        "lower",
        None,
    )
    # [Razavi-ADC] Sec. 7.1, p. 130: the comparator designed at its slow corner, low supply and hot
    delay_slow_0p5mv_s: float | None = metric(
        "Delay at 0.5 mV at the slow corner, 75 C and 90 % supply, the slowest of its decisions", "lower", None
    )
    # [Razavi-ADC] Sec. 5.8.4, p. 98: the StrongArm's tail current, so its speed, set by the input
    # common mode
    delay_max_cm_s: float | None = metric("Slowest 0.5 mV delay over the common mode", "lower", None)
    # not in the reference texts: the delay and energy on the converter's own clocks
    # (flow.adc.subckt: clkb from clk through one inverter), as [Razavi-ADC] Sec. 7.3, p. 131 times it
    delay_converter_0p5mv_s: float | None = metric(
        "Delay at 0.5 mV on the converter's clocks (clkb from clk through its inverter)", "lower", None
    )
    energy_converter_0p5mv_j: float | None = metric(
        "Energy per decision at 0.5 mV on the converter's clocks, clk's driver not counted", "lower", None
    )
    # [Razavi-Analog] Sec. 15.4.2, p. 641: a junction forward-biased by 300 mV conducts negligibly
    forward_bias_max_v: float | None = metric(
        "Largest forward bias of a device's junction over the supply's corners", "lower", None
    )
    # not in the reference texts: the largest voltage across a device's terminal pair over the
    # supply's corners, which the guard bounds at the nominal supply times 1.1 (flow.circuit.oppoint)
    terminal_max_v: float | None = metric(
        "Largest voltage across a device's terminal pair over the supply's corners", "lower", None
    )
