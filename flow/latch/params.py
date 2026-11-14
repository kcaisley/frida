"""The latch's parameters: its design (``Params``), one run of its testbench (``TbParams``), and the
sweeps every latch is characterized over.

One bench serves every design (``Bench.TIMING``): complementary clocks, data a set offset before
each capturing edge, an initial reset, set and reset pulses for an SR latch; the other
(``Bench.UPSET``) strikes the storage node of a latch that holds a 1. Each instance is run over the
supply (``SUPPLY_SWEEP``, fractions of its own), a latch or flip-flop over the data offset
(``DATA_OFFSET_SWEEP_S``), a flip-flop or divider over the clock period (``PERIOD_SWEEP_S``), and a
C2MOS or DICE latch without reset over a strike's charge (``UPSET_CHARGES_C``).
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
# the strike's double-exponential current: its rise and fall time constants
UPSET_RISE_S = 5e-12
UPSET_FALL_S = 50e-12
# the supply at 90 and 110 % of its own besides nominal: never past the models' limits
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the data edge from 200 ps after to 300 ps before each capturing edge, in 25 ps steps
DATA_OFFSET_SWEEP_S = tuple(round(offset * 1e-12, 15) for offset in range(-200, 301, 25))
# the clock from 1 ns to 30 ps
PERIOD_SWEEP_S = (1e-9, 500e-12, 300e-12, 200e-12, 150e-12, 100e-12, 70e-12, 50e-12, 30e-12)
# the strikes, 1 to 200 fC: a minimum-size node's critical charge is a few femtocoulombs
UPSET_CHARGES_C = tuple(charge * 1e-15 for charge in (1, 2, 3, 5, 7, 10, 20, 50, 100, 200))


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the latch's testbench (flow.latch.sim.testbench): the latch ``params`` in ``pdk``
    at supply ``vdd``, ``cload_f`` on q and qb. On the timing bench (``Bench.TIMING``) its clock of
    ``clock_period_s``, its data crossing mid-supply ``data_offset_s`` before each capturing edge,
    rst high for the first ``reset_time_s``, an SR latch's set and reset every ``data_period_s``,
    every source's edges ``transition_time_s``, ``cycles`` clock cycles after the reset. On the
    upset bench (``Bench.UPSET``) a strike of ``charge_c`` on the storage node at ``upset_time_s``.
    Spectre writes its output every ``waveform_sample_interval_s`` and steps no further."""

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
        edge = 2 * float(self.transition_time_s)
        if float(self.transition_time_s) <= 0 or min(float(self.clock_period_s), float(self.data_period_s)) <= edge:
            raise ValueError("latch periods must exceed both transitions, which must be positive")
        if abs(float(self.data_offset_s)) >= float(self.clock_period_s) / 2 + float(self.transition_time_s):
            raise ValueError("latch data offset must lie within half a clock period of the capturing edge")
        if float(self.reset_time_s) < 0 or self.cycles < 3:
            raise ValueError("latch reset time must be non-negative and the run at least three cycles")
        if self.bench is Bench.UPSET:
            if self.params.style not in UPSET_NODE or self.params.flop or self.params.reset:
                raise ValueError("the upset bench strikes a C2MOS or DICE latch without reset")
            closed = 1e-9 + 2 * float(self.transition_time_s)
            if not (float(self.charge_c) > 0 and float(self.upset_time_s) > closed):
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
