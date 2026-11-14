"""The latch's parameters: its design (``Params``), one run of its testbench (``TbParams``), and the
sweeps every latch is characterized over.

One bench serves every design (``Bench.TIMING``): complementary clocks, data a set offset before
each capturing edge, an initial reset, set and reset pulses for an SR latch, each input the design
does not use held at a fixed level; the other (``Bench.UPSET``) strikes the storage node holding a
0 of a latch that holds a 1. Each instance is run over the supply (``SUPPLY_SWEEP``, fractions of
its own), a latch or flip-flop over the data offset (``DATA_OFFSET_SWEEP_S``), a flip-flop or
divider over the clock period (``PERIOD_SWEEP_S``) and at a slow clock, and a C2MOS or DICE latch
without reset over a strike's charge (``UPSET_CHARGES_C``).
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosVth
from pydantic import PositiveInt

from flow import pipeline


class Style(Enum):
    """Latch topology."""

    CLOCKED = auto()  # static C2MOS latch, transparent while clk is high
    TSPC = auto()  # true single-phase clock flip-flop, dynamic: clk alone, no reset
    DICE = auto()  # dual interlocked storage cell latch, transparent while clk is high
    SR_NAND = auto()  # cross-coupled NAND gates: active-low s and r
    SR_NOR = auto()  # cross-coupled NOR gates: active-high s and r


class Bench(Enum):
    """Which testbench a run is."""

    TIMING = auto()  # clocks, data a set offset before each capturing edge, set and reset pulses
    UPSET = auto()  # a latch holding a 1, its storage node struck by a current pulse


# the styles a clock drives: latches, flip-flops and dividers
CLOCKED_STYLES = (Style.CLOCKED, Style.TSPC, Style.DICE)


@h.paramclass
class Params:
    """The latch: its topology and its devices' sizes as positive multiples of the PDK's unit width
    and minimum length (``n_w`` 4 means four unit widths, ``l`` 1 the minimum length), so that one
    design ports across PDKs. Every Params the class admits builds: a divider is a flip-flop; an SR
    latch has no clock, so no flip-flop, divider or reset; a TSPC circuit is a flip-flop without
    reset, a DICE one a latch without reset. The defaults are the static C2MOS latch."""

    style = h.Param(dtype=Style, desc="Latch style", default=Style.CLOCKED)
    flop = h.Param(dtype=bool, desc="Master-slave flip-flop on the rising clk edge", default=False)
    divider = h.Param(dtype=bool, desc="Divide by two: the flip-flop's qb drives its d", default=False)
    reset = h.Param(dtype=bool, desc="Asynchronous active-high reset to q low", default=False)
    n_w = h.Param(dtype=PositiveInt, desc="Forward, write and output NMOS width multiplier", default=4)
    p_w = h.Param(dtype=PositiveInt, desc="Forward, write and output PMOS width multiplier", default=8)
    fb_n_w = h.Param(dtype=PositiveInt, desc="Feedback (DICE: storage) NMOS width multiplier", default=2)
    fb_p_w = h.Param(dtype=PositiveInt, desc="Feedback (DICE: storage) PMOS width multiplier", default=4)
    l = h.Param(dtype=PositiveInt, desc="Length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)

    def __post_init__(self) -> None:
        if self.divider and not self.flop:
            raise ValueError("a divider is a flip-flop")
        if self.style is Style.TSPC and (not self.flop or self.reset):
            raise ValueError("a TSPC circuit is a flip-flop without reset")
        if self.style is Style.DICE and (self.flop or self.reset):
            raise ValueError("a DICE circuit is a latch without reset")
        if self.style not in CLOCKED_STYLES and (self.flop or self.divider or self.reset):
            raise ValueError("an SR latch has no clock: no flip-flop, divider or reset")


pipeline.Params.register(Params)


# the storage node holding a 0 while a latch holds a 1: the one a strike must charge to flip it
UPSET_NODE = {Style.CLOCKED: "qb", Style.DICE: "x1"}
# not in the reference texts: the strike's double-exponential current, its rise and fall time
# constants (the single-event upset literature's particle-strike model)
UPSET_RISE_S = 5e-12
UPSET_FALL_S = 50e-12
# not in the reference texts: the supply at 90 and 110 % of its own besides nominal, never past
# the models' limits (the repository's supply corners)
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# [Baker] Fig. 13.25, p. 401: setup, d applied t_s before the clock edge (positive offsets)
# [Baker] Fig. 13.26, p. 402: hold, d kept t_h after it (negative offsets)
# the data edge from 100 ps after to 300 ps before each capturing edge, in 10 ps steps: setup and
# hold are found to within one step
DATA_OFFSET_SWEEP_S = tuple(round(offset * 1e-12, 15) for offset in range(-100, 301, 10))
# [Razavi-PLL] Sec. 15.1, p. 454: a divider is tested from low frequencies up, a static failure
# told from one at speed
# not in the reference texts: the clock from 1 ns to 29.4 ps, each period 10 % shorter than the one
# before (three significant digits), so that f_max is found to within 10 %
PERIOD_SWEEP_S = tuple(float(f"{1e-9 / 1.1**step:.3g}") for step in range(38))
# not in the reference texts: the strikes, 1 to 208 fC, each 10 % above the one before (three
# significant digits): the critical charge is found to within 10 %
UPSET_CHARGES_C = tuple(float(f"{1.1**step:.3g}") * 1e-15 for step in range(57))


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the latch's testbench (flow.latch.sim.testbench): the latch ``params`` in ``pdk``
    at supply ``vdd``, ``cload_f`` on q and on qb (on both benches). On the timing bench
    (``Bench.TIMING``) its clock of ``clock_period_s``, its data crossing mid-supply
    ``data_offset_s`` before each capturing edge, rst high for the first ``reset_time_s``, an SR
    latch's set and reset every ``data_period_s``, ``cycles`` clock cycles after the reset. Every
    pulse source ramps linearly from one level to the other in ``transition_time_s``: Spectre's
    rise and fall, the whole 0 to 100 % ramp, so its 10 to 90 % transition time is 0.8 times it.
    On the upset bench (``Bench.UPSET``) the latch open with d high until ``write_time_s``, then
    holding, and a strike of ``charge_c`` on the storage node holding a 0 at ``upset_time_s``.
    Spectre writes its output every ``waveform_sample_interval_s`` (its strobe: the points the run
    keeps, not a bound on its own time steps)."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    bench: Bench = Bench.TIMING
    vdd: float = 1.2
    cload_f: float = 2e-15
    clock_period_s: float = 2e-9
    data_offset_s: float = 0.5e-9
    data_period_s: float = 5.2e-9
    reset_time_s: float = 0.5e-9
    transition_time_s: float = 50e-12
    cycles: int = 8
    charge_c: float = 0.0
    write_time_s: float = 1e-9
    upset_time_s: float = 2e-9
    waveform_sample_interval_s: float = 1e-12

    def __post_init__(self) -> None:
        values = (
            self.waveform_sample_interval_s,
            self.vdd,
            self.cload_f,
            self.clock_period_s,
            self.data_offset_s,
            self.data_period_s,
            self.reset_time_s,
            self.transition_time_s,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("latch testbench values must be finite")
        if min(float(self.vdd), float(self.cload_f), float(self.waveform_sample_interval_s)) <= 0:
            raise ValueError("latch supply, load, and sample interval must be positive")
        transition = float(self.transition_time_s)
        if transition <= 0:
            raise ValueError("latch transitions must be positive")
        # the clocks' flat top, T/2 - t_r, must be positive (sim.testbench)
        if float(self.clock_period_s) <= 2 * transition:
            raise ValueError("latch clock period must exceed two transitions")
        # the set and reset pulses, each a quarter of the data period at the top and both edges,
        # must fit between each other: data_period_s / 4 >= 2 t_r
        if float(self.data_period_s) < 8 * transition:
            raise ValueError("latch set and reset period must be at least eight transitions")
        if abs(float(self.data_offset_s)) >= float(self.clock_period_s) / 2 + float(self.transition_time_s):
            raise ValueError("latch data offset must lie within half a clock period of the capturing edge")
        if float(self.reset_time_s) < 0 or self.cycles < 3:
            raise ValueError("latch reset time must be non-negative and the run at least three cycles")
        if self.bench is Bench.UPSET:
            if self.params.style not in UPSET_NODE or self.params.flop or self.params.reset:
                raise ValueError("the upset bench strikes a C2MOS or DICE latch without reset")
            closed = float(self.write_time_s) + 2 * transition
            if not (float(self.write_time_s) > 0 and float(self.charge_c) > 0 and float(self.upset_time_s) > closed):
                raise ValueError("the strike must carry charge and come after the latch closes")
        elif float(self.charge_c):
            raise ValueError("a strike's charge belongs to the upset bench")

    @property
    def stop_s(self) -> float:
        """The run's length: the reset and ``cycles`` clock cycles; an SR latch's, three set and
        reset periods; the upset bench's, twice the strike time."""
        if self.bench is Bench.UPSET:
            return 2 * float(self.upset_time_s)
        if self.params.style not in CLOCKED_STYLES:
            return 3 * float(self.data_period_s)
        return float(self.reset_time_s) + (self.cycles + 1) * float(self.clock_period_s)
