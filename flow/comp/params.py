"""The comparator's parameters: its design (``Params``, every one of which builds), one run of its
testbench (``TbParams``), and the testbench every comparator is tested on.

Every comparator is tested the same way, so that comparators compare: the clock (``RESET_S`` of
reset, then ``EVALUATION_S`` of evaluation), the inputs driven through ``SOURCE_RESISTANCE_OHM`` onto
``SOURCE_CAPACITANCE_F`` a side (a source as quiet and stiff as a CDAC's top plate, so the noise is
the comparator's own), and the stimuli the characterization takes: the delay over the input
(``METASTABILITY_RUN_V``), a transient-noise S-curve (``SCURVE_V``, ``SCURVE_DECISIONS`` a point in
shuffled passes), kickback onto a DAC-like source (``KICKBACK_SOURCE``), over the common mode
(``CM_SWEEP``) and the supply (``SUPPLY_SWEEP``).
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline


class Latch(Enum):
    """The comparator's latch, its stages after the input pair: each a topology of its own, which the
    generator builds (``flow.comp.subckt``); a latch from a paper is one more member."""

    STRONGARM = auto()  # one stage: the cross-coupled pair stacked on the input pair
    DOUBLE_TAIL = auto()  # Schinkel: a second stage with its own clocked tail, shared by both halves
    DOUBLE_TAIL_SELF_TIMED = auto()  # the double tail's latch released by the input pair's drains
    DOUBLE_TAIL_MODIFIED = auto()  # van Elzakker: signaled inner on devices, a clocked reset
    DOUBLE_TAIL_MODIFIED_SELF_TIMED = auto()  # the modified latch with signaled inner init devices
    TRIPLE_TAIL = auto()  # a cascoded input pair, a regenerating second stage and a clocked latch


class Bias(Enum):
    DYNAMIC = auto()
    SWITCHED = auto()


class OutputStage(Enum):
    TRANSISTORS = auto()  # decision inverters, SR latch and buffers drawn transistor by transistor
    STDCELLS = auto()  # the same stage as generic logic cells, mapped to a library by the PDK


@h.paramclass
class Params:
    """The comparator: its latch, input pair and bias, any combination of them, and its device sizes
    as positive multiples of the PDK's unit width and minimum length (w = 10: ten unit widths), so
    that one design ports across PDKs. Every Params the class admits builds; the defaults are the
    characterization's short-channel sizes, at which ``Params(latch=...)`` is a topology's reference.
    What a grid or a search varies is a space of it (``pipeline.vary``: sweep.py, opt.py)."""

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


# the parameters that make a comparator's devices and their wiring (a floorplan's
# case is found by them: flow.comp.layout.layout_floorplan); a dynamic bias adds its capacitors
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
# the clock drivers' taper (TbParams.clock_fanout): fanout 4 a stage, the last stage's input at least
# half the clocked gates (fanout 2: a fanout of 4 or more into the comparator is too slow an edge);
# their energy is the comparator's, their area is not (the converter's digital control drives it)
CLOCK_FANOUT = 4.0
CLOCK_LAST_FANOUT = 2.0
# Spectre's output and its largest step: 2 ps for the noise-free runs (their delays within 0.1 % of a
# 1 ps step's), 10 ps for the transient-noise S-curves (whose noise up to 25 GHz bounds the step to
# 20 ps already). On Spectre's own steps (``waveform_sample_interval_s=None``) the delays came
# 1 to 6 % short and the energy per decision 1.3 to 2.7 times too large
STROBE_S = 2e-12
NOISE_STROBE_S = 10e-12
# the supply's charge, integrated by the simulator (exact at any output step): the supply source's
# current mirrored onto this capacitor, whose voltage is the charge drawn since the run began over it
CHARGE_METER_F = 1e-12
CHARGE_METER = "qmeter"  # its node, as a measurement names it
# the input source: 1 ohm onto 100 fF a side, as quiet and stiff as a CDAC's top plate (1 kohm added
# its own thermal noise, about 0.2 mV a side, and let the input pair's kickback pull the input);
# for kickback, 1 pF a side behind 1 Mohm (a microsecond's time constant: the charge a decision
# kicks onto them stays)
SOURCE_RESISTANCE_OHM = 1.0
SOURCE_CAPACITANCE_F = 100e-15
KICKBACK_SOURCE = (1e6, 1e-12)
# the stimuli, each a fraction of the PDK's core supply or an input in volts: the nominal common
# mode and its sweep (3/8 to 5/8 of the supply), the supply sweep (90 to 120 %), the small and large
# inputs (the slowest and fastest response)
NOMINAL_CM = 13 / 24
CM_SWEEP = (9 / 24, 11 / 24, 13 / 24, 15 / 24)
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
SMALL_V, LARGE_V = 0.5e-3, 100e-3
# the delay over the input, one noise-free decision each: each of METASTABILITY_V after its negative,
# so that every decision but the first follows one of the other sign (a latch the reset leaves
# holding its last decision, which inputs of one sign cannot show, decides it again, or late), and
# no input steps by more than twice the next one (the source settles within the reset)
METASTABILITY_V = (0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3, 30e-3, 100e-3)
METASTABILITY_RUN_V = tuple(v for value in METASTABILITY_V for v in (-value, value))
# the S-curve: 0 and 16 magnitudes from 5 uV to 3 mV a side (33 points, log-spaced, finest at the
# centre), reading 10 uV to 1.5 mV of noise: 15 points within 2 sigma of a 37 uV comparator (a 14-bit
# converter's quantization noise), 29 of a 560 uV one (10 bits), the span wide enough for 1 mV of
# offset; SCURVE_DECISIONS at each, a pass through every input at a time in a fresh random order
# (input_order "shuffled"), so that noise slower than a pass moves every input alike: one reading's
# noise scatters by about 4 % (one sigma) between noise seeds
SCURVE_UV = (5, 10, 15, 20, 25, 35, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 3000)
SCURVE_V = (*(-round(uv * 1e-6, 9) for uv in reversed(SCURVE_UV)), 0.0, *(round(uv * 1e-6, 9) for uv in SCURVE_UV))
SCURVE_DECISIONS = 80

# The optimization's problems (flow.comp.opt): a comparator for a converter of each resolution. Its
# noise at most the converter's quantization noise (LSB / sqrt(12), every noise source about equal
# to it), the LSB twice the full scale over 2^bits, the full scale ADC_FULL_SCALE of the supply (the
# converter's arrays reach at least 80 % of the reference: flow.adc.sweep); its layout within a
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
INPUT_ORDERS = ("blocked", "shuffled")


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the comparator's testbench (flow.comp.sim.testbench): the comparator ``params``
    in ``pdk`` at supply ``vdd``, ``conversions`` decisions at each input point (each common mode in
    ``vin_cm_values_v`` by each differential input in ``vin_diff_values_v``), held for all their
    decisions (``input_order`` "blocked") or stepped through once a pass in a fresh random order
    ("shuffled"), on the clock and source every comparator is tested at unless given; with
    transient noise where ``noise``. Spectre writes its output every ``waveform_sample_interval_s``
    and steps no further (``STROBE_S``); None keeps its own steps."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    vdd: float = 1.2
    vin_cm_values_v: tuple[float, ...] = (0.65,)
    vin_diff_values_v: tuple[float, ...] = (0.0,)
    conversions: int = 1
    input_order: str = "blocked"
    noise: bool = False
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
        if self.input_order not in INPUT_ORDERS:
            raise ValueError(f"comparator input order must be one of {INPUT_ORDERS}")
        for name in (
            "reset_time_s",
            "evaluation_time_s",
            "transition_time_s",
            "source_resistance_ohm",
            "source_capacitance_f",
            "output_load_f",
        ):
            if not math.isfinite(float(getattr(self, name))) or float(getattr(self, name)) <= 0.0:
                raise ValueError(f"comparator {name} must be finite and positive")
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
        them: at each common mode, ``blocked`` holds every input for all its decisions, ``shuffled``
        steps through every input once a pass (``conversions`` passes) in a fresh random order (a
        fixed seed), so that noise slower than a pass moves every input alike instead of whole
        points of the curve."""
        inputs = len(self.vin_diff_values_v)
        rng = np.random.default_rng(0)
        order = []
        for common_mode in range(len(self.vin_cm_values_v)):
            first = common_mode * inputs
            if self.input_order == "blocked":
                order.append(np.repeat(np.arange(inputs), self.conversions) + first)
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
