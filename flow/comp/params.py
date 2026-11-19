"""The comparator's parameters: its design (``Params``, every one of which builds), one run of its
testbench (``TbParams``), and the testbench every comparator is tested on.

Every comparator is tested the same way, so that comparators compare: the clock (``RESET_S`` of
reset, then ``EVALUATION_S`` of evaluation), the inputs driven through ``SOURCE_RESISTANCE_OHM`` onto
``SOURCE_CAPACITANCE_F`` a side (a source as quiet and stiff as a CDAC's top plate, so the noise is
the comparator's own), and the stimuli the characterization takes: the delay over the input
(``METASTABILITY_RUN_V``), a transient-noise S-curve (``SCURVE_V``, ``SCURVE_DECISIONS`` a point in
shuffled passes), kickback onto a DAC-like source (``KICKBACK_SOURCE``), over the common mode
(``CM_SWEEP``) and the supply (``SUPPLY_SWEEP``), the held outputs toggling (each of
``METASTABILITY_V`` and ``SMALL_V`` after ``LARGE_V`` of either sign), a small input after a full-scale
one (``ADC_FULL_SCALE``), the slow corner and the converter's clocks (``ClockDrive``).

The behavioral model (``flow.comp.model``) estimates a StrongARM's noise from its sizing with the
rough device constants here (``W_MIN_UM`` to ``COX_F_PER_UM2``).
"""

import math
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline
from flow.circuit.spectre import Accuracy


class Latch(Enum):
    """The comparator's latch, its stages after the input pair: each a topology of its own, which the
    generator builds (``flow.comp.subckt``); a latch from a paper is one more member."""

    # [Razavi-ADC] Sec. 5.8.3, Fig. 5.37, p. 94: the StrongArm comparator, one stage, the
    # cross-coupled pair stacked on the input pair
    STRONGARM = auto()
    # [Schinkel] Fig. 2, p. 90: the double-tail latch, a second stage with its own clocked tail
    DOUBLE_TAIL = auto()
    # [Schinkel] Fig. 2, p. 90, the double tail; frida adds its latch's init devices driven by the
    # input pair's drains instead of the clock (self-timed)
    DOUBLE_TAIL_SELF_TIMED = auto()
    # [vanElzakker] Fig. 7, p. 1010: the two-stage dynamic comparator, its inner on devices
    # signaled by the first stage, a clocked reset
    DOUBLE_TAIL_MODIFIED = auto()
    # [vanElzakker] Fig. 7, p. 1010, the modified double tail; frida adds its inner init devices
    # driven by the input pair's drains instead of the clock (self-timed)
    DOUBLE_TAIL_MODIFIED_SELF_TIMED = auto()
    # not in the reference texts: a cascoded input pair, a regenerating second stage and a clocked
    # latch (frida's own)
    TRIPLE_TAIL = auto()


class Bias(Enum):
    # [Bindra] Fig. 3, p. 2: the dynamic-bias preamplifier, its tail a capacitor reset to ground
    DYNAMIC = auto()
    # [Razavi-ADC] Sec. 5.8.3, Fig. 5.37, p. 94: the input pair's tail a clocked switch
    SWITCHED = auto()


class InputOrder(StrEnum):
    """How a testbench run steps its inputs (``TbParams.trial_point``), at each common mode: its
    members compare equal to their names in lower case, as a run's JSON writes them."""

    BLOCKED = auto()  # every input held for all its decisions, in the order given
    SHUFFLED = auto()  # every input once a pass, each pass in a fresh random order
    CYCLED = auto()  # every input once a pass, each pass in the order given
    # every input but the first two after each of them in turn (the first, the input, the second,
    # the input), the inputs in the order given, once a pass: an input whose decision is either
    # follows one of the other
    AFTER_BOTH = auto()


class Validity(StrEnum):
    """What an S-curve's fit is (``AnalysisOffsetNoise.validity``): its members compare equal to
    their names in lower case, as a record's JSON writes them."""

    VALID = auto()  # the Gaussian of most likelihood, its transition resolved by the inputs
    UNBRACKETED = auto()  # the curve never crosses one of its 16 %, 50 % or 84 % points
    NON_MONOTONIC = auto()  # a significant reversal between neighbouring inputs
    UNRESOLVED = auto()  # more than 1 % of the decisions unresolved
    # fewer than two inputs inside the transition (a share strictly between 0 and 1): its width
    # is below the inputs' spacing there, so the noise is not measured
    UNDERSAMPLED = auto()
    # a curve pinned below 0.1 (above 0.9) where a neighbouring common mode's offset lies in its
    # inputs' span (``AnalysisCommonMode``)
    STUCK_LOW = "stuck-low"
    STUCK_HIGH = "stuck-high"


class ClockDrive(Enum):
    """How a testbench run drives the comparator's two clocks (``TbParams.clock_drive``)."""

    # each clock from an inverter chain of its own on the comparator's supply, the two chains
    # matched and their sources complementary
    CHAINS = auto()
    # as the converter clocks it (flow.adc.subckt): clk from its chain on a supply of its own (the
    # converter's digital block drives it), clkb from clk through one inverter on the comparator's
    # supply
    CONVERTER = auto()


class OutputStage(Enum):
    TRANSISTORS = auto()  # decision inverters, SR latch and buffers drawn transistor by transistor
    STDCELLS = auto()  # the same stage as generic logic cells, mapped to a library by the PDK


@h.paramclass
class Params:
    """The comparator: its latch, input pair and bias, any combination of them, and its device sizes
    as positive multiples of the PDK's unit width and minimum length (w = 10: ten unit widths), so
    that one design ports across PDKs. Every Params the class admits builds; the defaults are the
    characterization's short-channel sizes, at which ``Params(latch=...)`` is a topology's reference.
    What a grid or an optimization varies is a space of it (``pipeline.widen``: runs.py)."""

    latch = h.Param(dtype=Latch, desc="Latch topology", default=Latch.STRONGARM)
    input_pair = h.Param(dtype=MosType, desc="Input pair type (NMOS or PMOS)", default=MosType.NMOS)
    bias = h.Param(
        dtype=Bias,
        desc="The input pair's tail: a clocked switch, or a switch onto C_TAIL (dynamic bias)",
        default=Bias.SWITCHED,
    )
    output_stage = h.Param(
        dtype=OutputStage,
        desc="Output stage implementation (a view: layout draws both)",
        default=OutputStage.TRANSISTORS,
    )

    # device sizes, in unit widths and minimum lengths
    diffpair_w = h.Param(dtype=PositiveInt, desc="Diff pair width multiplier", default=32)
    diffpair_l = h.Param(dtype=PositiveInt, desc="Diff pair length multiplier", default=2)
    tail_w = h.Param(dtype=PositiveInt, desc="Tail width multiplier", default=16)
    tail_l = h.Param(dtype=PositiveInt, desc="Tail length multiplier", default=2)
    rst_w = h.Param(dtype=PositiveInt, desc="Reset device width multiplier", default=8)
    rst_l = h.Param(dtype=PositiveInt, desc="Reset device length multiplier", default=1)
    latch_on_w = h.Param(dtype=PositiveInt, desc="Latch evaluation-side width multiplier", default=8)
    latch_on_l = h.Param(dtype=PositiveInt, desc="Latch evaluation-side length multiplier", default=1)
    latch_init_w = h.Param(dtype=PositiveInt, desc="Latch precharge-side width multiplier", default=8)
    latch_init_l = h.Param(dtype=PositiveInt, desc="Latch precharge-side length multiplier", default=1)
    srlatch_n_w = h.Param(dtype=PositiveInt, desc="Output SR-latch NMOS width multiplier", default=4)
    srlatch_p_w = h.Param(dtype=PositiveInt, desc="Output SR-latch PMOS width multiplier", default=8)
    vth = h.Param(dtype=MosVth, desc="Every device's Vth", default=MosVth.LOW)

    # the dynamic bias's capacitors, MOS capacitors of nominal capacitance (unused with a switched tail)
    preamp_c_ff = h.Param(
        dtype=PositiveInt,
        desc="Dynamic bias: C_P, the MOS capacitance on each input-pair drain to its evaluation rail (fF)",
        default=60,
    )
    bias_c_ff = h.Param(dtype=PositiveInt, desc="Dynamic bias: C_TAIL, the tail's MOS capacitance (fF)", default=100)


def layout_view(params: Params) -> Params:
    """The comparator as laid out: its output stage the PDK's library cells (``OutputStage``'s
    STDCELLS view; the simulations draw it transistor by transistor)."""
    return Params(**{**params.__dict__, "output_stage": OutputStage.STDCELLS})


# the parameters that make a comparator's devices and their wiring; a dynamic bias adds its capacitors
STRUCTURE = ("latch", "input_pair", "bias")


pipeline.Params.register(Params)


FRIDA1 = Params(
    diffpair_w=37,
    tail_w=5,
    rst_w=8,
    latch_on_w=25,
    latch_init_w=33,
    srlatch_n_w=4,
    srlatch_p_w=8,
    diffpair_l=5,
    tail_l=13,
    rst_l=1,
    latch_on_l=6,
    latch_init_l=17,
    latch=Latch.STRONGARM,
    input_pair=MosType.NMOS,
    bias=Bias.SWITCHED,
)  # the fabricated FRIDA-1 comparator: single stage, NMOS input, switched tail


# The clock: 1 ns of reset, then 4 ns of evaluation (a comparator that needs longer is too slow for
# the converter, which allows about 2 ns), and twice both, against which a comparator's decisions
# are checked (flow.comp.analysis.analyze_clock_check)
RESET_S = 1e-9
EVALUATION_S = 4e-9
CHECK_CLOCK_S = (2 * RESET_S, 2 * EVALUATION_S)
TRANSITION_S = 20e-12  # the clock's and the input's edges
# not in the reference texts: a fanout-4 inverter taper to a last stage at fanout 2 (the clock
# drivers, TbParams.clock_fanout): the last stage's input at least half the clocked gates (a fanout
# of 4 or more into the comparator is too slow an edge); their energy is the comparator's, their
# area is not (the converter's digital control drives it)
CLOCK_FANOUT = 4.0
CLOCK_LAST_FANOUT = 2.0
# Spectre's output: every 2 ps for the noise-free runs (readme.md: the strobe's error), every 5 ps
# for the transient-noise S-curves, half a period of the noise's bandwidth (TbParams.noise_fmax_hz),
# the step Spectre's noise sources take
STROBE_S = 2e-12
NOISE_STROBE_S = 5e-12
# the supply's charge, integrated by the simulator (exact at any output step): the supply source's
# current mirrored onto this capacitor, whose voltage is the charge drawn since the run began over it
CHARGE_METER_F = 1e-12
CHARGE_METER = "qmeter"  # its node, as a measurement names it
# the input source: 1 ohm onto 100 fF a side, as quiet and stiff as a CDAC's top plate (a 1 kohm
# source adds thermal noise of its own and lets the input pair's kickback pull the input);
# for kickback, 1 pF a side behind 1 Mohm (a microsecond's time constant: the charge a decision
# kicks onto them stays for the decisions after it)
SOURCE_RESISTANCE_OHM = 1.0
SOURCE_CAPACITANCE_F = 100e-15
KICKBACK_SOURCE = (1e6, 1e-12)
# the stimuli, each a fraction of the PDK's core supply or an input in volts: the nominal common
# mode and its sweep (3/8 to 5/8 of the supply), the supply sweep (90 and 110 % besides nominal:
# never past the models' limits, which TSMC28's core devices check above 110 %), the small and
# large inputs (the slowest and fastest response)
NOMINAL_CM = 13 / 24
CM_SWEEP = (9 / 24, 11 / 24, 13 / 24, 15 / 24)
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
SMALL_V, LARGE_V = 0.5e-3, 100e-3
# the delay over the input, one noise-free decision each: each of METASTABILITY_V after its negative,
# so that every decision but the first follows one of the other sign (a latch the reset leaves
# holding its last decision, which inputs of one sign cannot show, decides it again, or late); 1 to
# 2 mV apart from 2 to 15 mV, so that a systematic offset up to 12 mV either way leaves inputs
# within 1 mV of it on both sides, where the latch regenerates from a small imbalance
# (analysis.analyze_metastability fits the offset with the time constant)
METASTABILITY_V = (0.1e-3, 0.3e-3, 1e-3, 2e-3, 3e-3, 4e-3, 6e-3, 8e-3, 10e-3, 12e-3, 15e-3, 30e-3, 100e-3)
METASTABILITY_RUN_V = tuple(v for value in METASTABILITY_V for v in (-value, value))
# the S-curve: 0 and 16 magnitudes from 5 uV to 3 mV a side (33 points, log-spaced, finest at the
# centre), for 10 uV to 1.5 mV of noise: 15 points within 2 sigma of a 37 uV comparator (a 14-bit
# converter's quantization noise), 29 of a 560 uV one (10 bits); SCURVE_DECISIONS at each, a pass
# through every input at a time in a fresh random order (InputOrder.SHUFFLED), so that noise slower
# than a pass moves every input alike (readme.md: a reading's scatter between seeds)
SCURVE_UV = (5, 10, 15, 20, 25, 35, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 3000)
SCURVE_V = (*(-round(uv * 1e-6, 9) for uv in reversed(SCURVE_UV)), 0.0, *(round(uv * 1e-6, 9) for uv in SCURVE_UV))
SCURVE_DECISIONS = 80

# Rough 65-nm device constants, for the behavioral model's noise estimate from a StrongARM's sizing
# (flow.comp.model.Model.strongarm_noise): the width and the length one size unit stands for, the
# drain junction capacitance per width and the gate capacitance per area
W_MIN_UM = 0.12
L_MIN_UM = 0.06
JUNCTION_F_PER_UM = 0.8e-15
COX_F_PER_UM2 = 14e-15

# The optimization's problems (flow.comp.runs): a comparator for a converter of each resolution. Its
# noise at most the converter's quantization noise (LSB / sqrt(12), every noise source about equal
# to it), the LSB twice the full scale over 2^bits, the full scale ADC_FULL_SCALE of the supply (the
# converter's arrays reach at least 80 % of the reference: flow.adc.runs); its layout within a
# square of AREA_SIDE_UM a side, the same in every PDK (a denser PDK fits more in it); its delay at
# 0.5 mV within DECISION_S (the converter allows about 2 ns a decision), deciding within the clock.
# Its cost, in J um^2: energy x area^AREA_WEIGHT x (1 + (noise / LSB-noise)^2)^NOISE_WEIGHT, the
# last factor the converter's noise power over its quantization noise alone, near 1 where it no
# longer gains from a quieter comparator; a design that only scales settles at noise / LSB-noise =
# 1 / sqrt(NOISE_WEIGHT / (1 + AREA_WEIGHT) - 1), 0.71 here.
ADC_FULL_SCALE = 0.8
AREA_SIDE_UM = {10: 15.0, 12: 20.0, 14: 63.0}
DECISION_S = 2e-9
AREA_WEIGHT = 1.0
NOISE_WEIGHT = 6.0


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the comparator's testbench (flow.comp.sim.testbench): the comparator ``params``
    in ``pdk`` at supply ``vdd``, its models at ``corner`` and ``temperature_c``, ``conversions``
    decisions at each input point (each common mode in ``vin_cm_values_v`` by each differential
    input in ``vin_diff_values_v``), stepped through as ``input_order`` says, on the clock and source
    every comparator is tested at unless given, its clocks driven as ``clock_drive`` says (clkb
    through ``clkb_inverter`` as the converter drives it); with transient noise up to
    ``noise_fmax_hz`` where ``noise``. Spectre writes its output every ``waveform_sample_interval_s``
    (``STROBE_S``; None keeps its own steps). Each device's operating-point values saved where
    ``device_values`` (``flow.circuit.oppoint.saves``); classic Spectre where the run needs its
    accuracy (``accuracy``), else Spectre X."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    vdd: float = 1.2
    vin_cm_values_v: tuple[float, ...] = (0.65,)
    vin_diff_values_v: tuple[float, ...] = (0.0,)
    conversions: int = 1
    input_order: InputOrder = InputOrder.BLOCKED
    noise: bool = False
    corner: h.pdk.Corner = h.pdk.Corner.TYP
    temperature_c: float = 25.0
    clock_drive: ClockDrive = ClockDrive.CHAINS
    # the converter's clkb inverter (flow.adc.subckt: clk_comp_b), in unit widths and minimum
    # lengths, where clock_drive is CONVERTER
    clkb_inverter: tuple[int, int] = (10, 1)
    device_values: bool = False
    accuracy: Accuracy | None = None
    reset_time_s: float = RESET_S
    evaluation_time_s: float = EVALUATION_S
    transition_time_s: float = TRANSITION_S
    source_resistance_ohm: float = SOURCE_RESISTANCE_OHM
    source_capacitance_f: float = SOURCE_CAPACITANCE_F
    output_load_f: float = 10e-15
    # the clock's drivers (flow.comp.sim.testbench): each clock an inverter chain from a unit
    # inverter, on the comparator's supply, tapering by clock_fanout a stage to a last stage whose
    # input is clock_last_fanout times smaller than the clocked gates; None, ideal sources (the
    # clock's energy then not counted)
    clock_fanout: float | None = CLOCK_FANOUT
    clock_last_fanout: float = CLOCK_LAST_FANOUT
    waveform_sample_interval_s: float | None = STROBE_S
    # transient noise's bandwidth where noise (Spectre's noisefmax): an integrating input pair
    # saturated for tens of picoseconds loses a tenth of its variance above 25 GHz (readme.md)
    noise_fmax_hz: float = 100e9
    # TODO: matching a building-block Monte Carlo result to a higher-level run
    # by seed and iteration alone is not valid; the two runs draw independent
    # mismatch. Netlisting does not consume these fields yet.
    mc_seed: int | None = None
    mc_index: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.vdd)) or float(self.vdd) <= 0.0:
            raise ValueError("comparator vdd must be finite and positive")
        for name, values in (("common modes", self.vin_cm_values_v), ("differential inputs", self.vin_diff_values_v)):
            floats = tuple(float(value) for value in values)
            if not floats or not all(math.isfinite(value) for value in floats) or len(set(floats)) != len(floats):
                raise ValueError(f"comparator {name} must be finite and unique")
        if self.conversions <= 0:
            raise ValueError("comparator conversions must be positive")
        # an order given by its name (a run's JSON) is its member; any other name raises
        if self.input_order not in tuple(InputOrder):
            raise ValueError(f"comparator input order must be one of {[order.value for order in InputOrder]}")
        object.__setattr__(self, "input_order", InputOrder(self.input_order))
        if self.input_order is InputOrder.AFTER_BOTH and len(self.vin_diff_values_v) < 3:
            raise ValueError("comparator inputs after both of the first two need a third")
        if not math.isfinite(float(self.temperature_c)):
            raise ValueError("comparator temperature must be finite")
        for name in (
            "reset_time_s",
            "evaluation_time_s",
            "transition_time_s",
            "source_resistance_ohm",
            "source_capacitance_f",
            "output_load_f",
            "noise_fmax_hz",
        ):
            if not math.isfinite(float(getattr(self, name))) or float(getattr(self, name)) <= 0.0:
                raise ValueError(f"comparator {name} must be finite and positive")
        if len(self.clkb_inverter) != 2 or min(int(size) for size in self.clkb_inverter) < 1:
            raise ValueError("comparator clkb inverter must be a positive width and length")
        if self.clock_fanout is not None and not (
            float(self.clock_fanout) > 1.0 and float(self.clock_last_fanout) > 0.0
        ):
            raise ValueError("comparator clock fanouts must be positive, the taper's above 1")
        if self.waveform_sample_interval_s is not None and not float(self.waveform_sample_interval_s) > 0.0:
            raise ValueError("comparator waveform_sample_interval_s must be positive or None")
        if float(self.transition_time_s) >= min(float(self.reset_time_s), float(self.evaluation_time_s)):
            raise ValueError("comparator transition must be shorter than reset and evaluation")

    @property
    def cycle_s(self) -> float:
        """One decision: the reset, then the evaluation."""
        return float(self.reset_time_s) + float(self.evaluation_time_s)

    @property
    def points(self) -> list[tuple[float, float]]:
        """The input points, (common mode, differential input), the common modes outer."""
        return [(float(cm), float(diff)) for cm in self.vin_cm_values_v for diff in self.vin_diff_values_v]

    @property
    def trial_point(self) -> np.ndarray:
        """Each decision's input point (an index into ``points``), in the order the testbench applies
        them: at each common mode, ``BLOCKED`` holds every input for all its decisions, ``SHUFFLED``
        steps through every input once a pass (``conversions`` passes) in a fresh random order (a
        fixed seed), so that noise slower than a pass moves every input alike instead of whole
        points of the curve, ``CYCLED`` once a pass in the order given, and ``AFTER_BOTH`` each
        input but the first two after the first and again after the second, once a pass."""
        inputs = len(self.vin_diff_values_v)
        rng = np.random.default_rng(0)
        order = []
        for common_mode in range(len(self.vin_cm_values_v)):
            first = common_mode * inputs
            if self.input_order is InputOrder.BLOCKED:
                order.append(np.repeat(np.arange(inputs), self.conversions) + first)
            elif self.input_order is InputOrder.CYCLED:
                order.append(np.tile(np.arange(inputs), self.conversions) + first)
            elif self.input_order is InputOrder.AFTER_BOTH:
                rest = np.arange(2, inputs)
                bracketed = np.stack([np.zeros_like(rest), rest, np.ones_like(rest), rest], axis=1).ravel()
                order.append(np.tile(bracketed, self.conversions) + first)
            else:
                order.append(np.concatenate([rng.permutation(inputs) for _ in range(self.conversions)]) + first)
        return np.concatenate(order).astype(np.int64)

    @property
    def trial_start_s(self) -> np.ndarray:
        """Each decision's cycle start, its reset's beginning."""
        return np.arange(len(self.trial_point)) * self.cycle_s

    @property
    def decision_time_s(self) -> np.ndarray:
        """When each decision is read: just before its evaluation ends (two input transitions)."""
        return self.trial_start_s + self.cycle_s - 2 * float(self.transition_time_s)

    @property
    def stop_s(self) -> float:
        """The run's length: every decision's cycle."""
        return len(self.trial_point) * self.cycle_s
