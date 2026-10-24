"""The comparator's parameters: its design (``Params``), one run of its testbench (``TbParams``),
which designs the generator builds (``valid``), and the testbench every comparator is tested on.

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
from typing import Any

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth

from flow import pipeline


class Stages(Enum):
    SINGLE = auto()
    DOUBLE = auto()
    TRIPLE = auto()


class Bias(Enum):
    DYNAMIC = auto()
    SWITCHED = auto()


class State(Enum):
    CLOCK = auto()
    SIGNAL = auto()
    OMIT = auto()


class OutputStage(Enum):
    TRANSISTORS = auto()  # decision inverters, SR latch and buffers drawn transistor by transistor
    STDCELLS = auto()  # the same stage as generic logic cells, mapped to a library by the PDK


@h.paramclass
class Params:
    """Comparator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for a 65nm node)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for a 65nm node)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    comp_stages = h.Param(dtype=Stages, desc="Comparator stages", default=Stages.SINGLE)

    preamp_diff_xtors = h.Param(
        dtype=MosType,
        desc="Input diff pair type (NMOS or PMOS)",
        default=MosType.NMOS,
    )
    preamp_bias = h.Param(dtype=Bias, desc="Biasing type", default=Bias.SWITCHED)

    # Latch transistor pairs — each can be clocked, signaled, or omitted
    latch_outer_on_xtors = h.Param(dtype=State, desc="Outer on devices", default=State.OMIT)
    latch_inner_on_xtors = h.Param(dtype=State, desc="Inner on  devices", default=State.OMIT)
    latch_outer_init_xtors = h.Param(dtype=State, desc="Outer init devices", default=State.OMIT)
    latch_inner_init_xtors = h.Param(dtype=State, desc="Inner init devices", default=State.CLOCK)
    output_stage = h.Param(dtype=OutputStage, desc="Output stage implementation", default=OutputStage.TRANSISTORS)
    latch_tail_shared = h.Param(
        dtype=bool, desc="One clocked outer tail shared by both latch halves (double tail)", default=False
    )

    # Device sizing (multipliers of Wmin/Lmin)
    diffpair_w = h.Param(dtype=int, desc="Diff pair width multiplier", default=32)
    diffpair_l = h.Param(dtype=int, desc="Diff pair length multiplier", default=4)
    diffpair_vth = h.Param(dtype=MosVth, desc="Diff pair Vth", default=MosVth.LOW)

    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=4)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=16)
    tail_vth = h.Param(dtype=MosVth, desc="Tail Vth", default=MosVth.LOW)

    rst_w = h.Param(dtype=int, desc="Reset device width multiplier", default=8)
    rst_l = h.Param(dtype=int, desc="Reset device length multiplier", default=1)
    rst_vth = h.Param(dtype=MosVth, desc="Reset Vth", default=MosVth.LOW)

    latch_on_w = h.Param(dtype=int, desc="Latch evaluation-side width multiplier", default=4)
    latch_on_l = h.Param(dtype=int, desc="Latch evaluation-side length multiplier", default=1)
    latch_init_w = h.Param(dtype=int, desc="Latch precharge-side width multiplier", default=4)
    latch_init_l = h.Param(dtype=int, desc="Latch precharge-side length multiplier", default=1)
    latch_vth = h.Param(dtype=MosVth, desc="Latch Vth", default=MosVth.LOW)

    srlatch_n_w = h.Param(
        dtype=int,
        desc="Output SR-latch NMOS width multiplier",
        default=4,
    )
    srlatch_p_w = h.Param(
        dtype=int,
        desc="Output SR-latch PMOS width multiplier",
        default=8,
    )

    # Added after the first sweeps: at their defaults each instance is as before (flow.sweep leaves
    # them out of an instance's identity there)
    preamp_c_ff = h.Param(
        dtype=int,
        desc="MOS capacitance on each input-pair drain to its evaluation rail (nominal fF; 0: the devices' own alone)",
        default=0,
    )
    latch_tail_w = h.Param(
        dtype=int,
        desc="Width multiplier of the clocked latch tail (a double tail's shared tail, a triple tail's "
        "second-stage tail), both halves together; 0: twice latch_on_w",
        default=0,
    )
    bias_c_ff = h.Param(dtype=int, desc="Dynamic bias: the tail's MOS capacitance (nominal fF)", default=100)


# the parameters that make a comparator's devices and their wiring (a hand-written floorplan's
# case is found by them: flow.comp.layout.layout_floorplan); an explicit C_P adds two capacitors
STRUCTURE = (
    "comp_stages",
    "preamp_diff_xtors",
    "preamp_bias",
    "latch_outer_on_xtors",
    "latch_inner_on_xtors",
    "latch_outer_init_xtors",
    "latch_inner_init_xtors",
    "latch_tail_shared",
    "preamp_c_ff",
)


# where not every size decides within the evaluation (EVALUATION_S) in a PDK, what does: the longest
# latch devices (``latch_l``: latch_on_l and latch_init_l) and tail (``tail_l``), in minimum lengths,
# and the dynamic bias's range of C_TAIL over C_P (``ratio``: bias_c_ff over preamp_c_ff; None, no
# dynamic bias)
LIMITS: dict[str, dict[str, Any]] = {
    "tsmc28": {"tail_l": 32, "ratio": (0, 3)},
    "tpsc65": {"latch_l": 1, "ratio": (2.5, math.inf)},
    "ihp130": {"latch_l": 1, "tail_l": 34, "ratio": None},
    "lf150": {"latch_l": 1, "tail_l": 34, "ratio": (5, math.inf)},
    "tower180": {"latch_l": 1, "tail_l": 4, "ratio": None},
}


def valid(param: Params, pdk: str | None = None) -> bool:
    """Whether the comparator can be built (``_valid_structure``) and, given its PDK, decides within
    the evaluation there (``LIMITS``)."""
    if not _valid_structure(param):
        return False
    limits = LIMITS.get(pdk or "", {})
    ratio = limits.get("ratio", (0, math.inf))
    return (
        max(param.latch_on_l, param.latch_init_l) <= limits.get("latch_l", math.inf)
        and param.tail_l <= limits.get("tail_l", math.inf)
        and (
            param.preamp_bias != Bias.DYNAMIC
            or (ratio is not None and ratio[0] <= param.bias_c_ff / max(param.preamp_c_ff, 1) <= ratio[1])
        )
    )


def _valid_structure(param: Params) -> bool:
    """Check if this topology combination is valid.

    Inner init devices must always exist (CLOCK or SIGNAL, never OMIT).

    Single stage: Both kinds of on devices plus outer init devices must be OMIT.

    Double stage: at least one on device pair must exist, and at least
    one of the four device pairs must be signaled (not just clocked). A shared
    tail is one clocked outer on device, so it excludes outer init devices.

    Triple stage (triple tail): its second and third stages are fixed, so the
    latch device options keep their defaults.
    """
    if param.srlatch_n_w <= 0 or param.srlatch_p_w <= 0:
        return False

    if param.preamp_c_ff < 0 or param.latch_tail_w < 0 or param.bias_c_ff <= 0:
        return False

    if param.latch_inner_init_xtors == State.OMIT:
        return False

    if param.latch_tail_shared and (
        param.comp_stages != Stages.DOUBLE
        or param.latch_outer_on_xtors != State.CLOCK
        or param.latch_outer_init_xtors != State.OMIT
    ):
        return False

    if param.comp_stages == Stages.TRIPLE:
        return (
            param.latch_inner_init_xtors == State.CLOCK
            and param.latch_outer_on_xtors == State.OMIT
            and param.latch_inner_on_xtors == State.OMIT
            and param.latch_outer_init_xtors == State.OMIT
        )

    if param.comp_stages == Stages.SINGLE:
        return (
            param.latch_outer_on_xtors == State.OMIT
            and param.latch_inner_on_xtors == State.OMIT
            and param.latch_outer_init_xtors == State.OMIT
        )
    # outer_init requires outer_on (needs outerp/outern nodes)
    if param.latch_outer_init_xtors != State.OMIT and param.latch_outer_on_xtors == State.OMIT:
        return False

    if param.comp_stages == Stages.DOUBLE:
        has_on = param.latch_outer_on_xtors != State.OMIT or param.latch_inner_on_xtors != State.OMIT
        has_signal = State.SIGNAL in (
            param.latch_outer_on_xtors,
            param.latch_inner_on_xtors,
            param.latch_outer_init_xtors,
            param.latch_inner_init_xtors,
        )
        return has_on and has_signal
    return False


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
    preamp_diff_xtors=MosType.NMOS,
    preamp_bias=Bias.SWITCHED,
    comp_stages=Stages.SINGLE,
    latch_inner_init_xtors=State.CLOCK,
)  # the fabricated FRIDA-1 comparator: single stage, NMOS input, switched tail
# The characterization's six topologies (StrongARM, triple tail, double tail, and the self-timed
# and modified double tails), NMOS input with a switched tail, and the shared short-channel sizing
# they are compared at (flow.comp.sweep builds on both)
TOPOLOGIES = {
    "strongarm": {"comp_stages": Stages.SINGLE},
    "triple_tail": {"comp_stages": Stages.TRIPLE},
    "double_tail": {
        "comp_stages": Stages.DOUBLE,
        "latch_inner_init_xtors": State.SIGNAL,
        "latch_outer_on_xtors": State.CLOCK,
        "latch_tail_shared": True,
    },
    "double_tail_self_timed": {
        "comp_stages": Stages.DOUBLE,
        "latch_inner_init_xtors": State.SIGNAL,
        "latch_outer_on_xtors": State.SIGNAL,
        "latch_outer_init_xtors": State.SIGNAL,
    },
    "double_tail_modified": {
        "comp_stages": Stages.DOUBLE,
        "latch_inner_on_xtors": State.SIGNAL,
        "latch_inner_init_xtors": State.CLOCK,
    },
    "double_tail_modified_self_timed": {
        "comp_stages": Stages.DOUBLE,
        "latch_inner_on_xtors": State.SIGNAL,
        "latch_inner_init_xtors": State.SIGNAL,
    },
}
TOPOLOGY_SIZES = {
    "diffpair_w": 32,
    "diffpair_l": 2,
    "tail_w": 16,
    "tail_l": 2,
    "rst_w": 8,
    "rst_l": 1,
    "latch_on_w": 8,
    "latch_on_l": 1,
    "latch_init_w": 8,
    "latch_init_l": 1,
    "srlatch_n_w": 4,
    "srlatch_p_w": 8,
}


# The clock: 1 ns of reset, then 4 ns of evaluation (a comparator that needs longer is too slow for
# the converter, which allows about 2 ns), and twice both, against which a comparator's decisions
# are checked (flow.comp.analysis.analyze_clock_check)
RESET_S = 1e-9
EVALUATION_S = 4e-9
CHECK_CLOCK_S = (2 * RESET_S, 2 * EVALUATION_S)
TRANSITION_S = 20e-12  # the clock's and the input's edges
# Spectre's output and its largest step: 2 ps for the noise-free runs (their delays within 0.1 % of a
# 1 ps step's), 10 ps for the transient-noise S-curves (whose noise up to 25 GHz bounds the step to
# 20 ps already). On Spectre's own steps (``waveform_sample_interval_s=None``) the delays came
# 1 to 6 % short and the energy per decision 1.3 to 2.7 times too large
STROBE_S = 2e-12
NOISE_STROBE_S = 10e-12
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
# the S-curve: 0 and 16 magnitudes from 25 uV to 3 mV a side (33 points finest at the centre),
# reading 50 uV to 1.5 mV of noise; SCURVE_DECISIONS at each, a pass through every input at a time
# in a fresh random order (input_order "shuffled"), so that noise slower than a pass moves every
# input alike: one reading's noise scatters by about 4 % (one sigma) between noise seeds
SCURVE_UV = (25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 700, 1000, 1400, 2000, 3000)
SCURVE_V = (*(-round(uv * 1e-6, 9) for uv in reversed(SCURVE_UV)), 0.0, *(round(uv * 1e-6, 9) for uv in SCURVE_UV))
SCURVE_DECISIONS = 80
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
