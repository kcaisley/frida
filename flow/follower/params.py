"""The follower's parameters: its design (``Params``), one run of its testbench (``TbParams``), and
the bench every follower is characterized on.

Every follower is characterized the same way, so that followers compare: typical models at 25 C,
from an ideal input source (R_S = 0) into ``LOAD_F``, its current sources biased from references
carrying ``IREF_A`` at the current-source width ``IREF_W`` (the current in proportion to the
design's own width), over the input level (``VIN_SWEEP``, fractions of the supply) with the AC
stimulus on the input, over ``FSTART_HZ`` to ``FSTOP_HZ``, the input swept in DC from ground to the
supply by ``VIN_DC_STEP`` of it in one of those runs; at each level the nominal input may take
(``NOMINAL_VIN``: the analysis takes the one nearest the middle of the measured input range) the
supply at ``SUPPLY_SWEEP`` of its own, the input held where its input device's source rides, and a
step of ``VIN_STEP`` of the supply (by topology) up and back down (``STEP_PERIOD_S``,
``TRANSITION_S`` edges, Spectre's output every ``STROBE_S``), and the same step at half its size.
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline


class Topology(Enum):
    """Follower topology."""

    # [Razavi-Analog] Fig. 3.37, p. 69: the source follower with a transistor as its current source
    SOURCE = auto()  # the input device and a current source on the output
    # not in the reference texts: the flipped voltage follower, a source follower whose input
    # device's drain current is fixed and whose drain drives a shunt device on the output (named,
    # not analysed, in [Pelgrom] Fig. 10.12, p. 488)
    FLIPPED = auto()  # the input device, a current source into its drain, a shunt device it drives


class Stimulus(Enum):
    """What one run of the testbench drives, and so which analyses it holds."""

    # the AC stimulus on the input: the response, and every source's transfer to the output (the
    # supplies', and the output test current's: the output impedance)
    INPUT = auto()
    STEP = auto()  # the input stepping up about its level and back down: a transient


@h.paramclass
class Params:
    """The follower: its topology, its input device's type and its devices' sizes as positive
    multiples of the PDK's unit width and minimum length (``in_w`` 8 is 8 unit widths, ``in_l`` 1
    the minimum length), so that one design ports across PDKs. Every Params the class admits
    builds: an output sink (``sink``) belongs to a ``Topology.FLIPPED`` follower alone. The shunt
    device (``fb_w``, ``fb_l``) sizes only a flipped follower."""

    topology = h.Param(dtype=Topology, desc="Follower topology", default=Topology.SOURCE)
    input_xtors = h.Param(dtype=MosType, desc="Input device type (NMOS or PMOS)", default=MosType.NMOS)
    sink = h.Param(dtype=bool, desc="An extra current source on the output (flipped follower)", default=False)
    in_w = h.Param(dtype=PositiveInt, desc="Input device width multiplier", default=16)
    in_l = h.Param(dtype=PositiveInt, desc="Input device length multiplier", default=1)
    bias_w = h.Param(dtype=PositiveInt, desc="Current source width multiplier", default=8)
    bias_l = h.Param(dtype=PositiveInt, desc="Current source length multiplier", default=4)
    fb_w = h.Param(dtype=PositiveInt, desc="Shunt device width multiplier", default=16)
    fb_l = h.Param(dtype=PositiveInt, desc="Shunt device length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)

    def __post_init__(self) -> None:
        if self.sink and self.topology is not Topology.FLIPPED:
            raise ValueError("an output sink belongs to a flipped follower")


pipeline.Params.register(Params)


# the bench (its choices, not in the reference texts): 100 fF, the references' 20 uA at a current
# source 16 units wide (a source follower) or 8 (a flipped one), 1 kHz to 100 GHz at 20 points a
# decade
LOAD_F = 100e-15
IREF_A = 20e-6
IREF_W = {Topology.SOURCE: 16, Topology.FLIPPED: 8}
FSTART_HZ = 1e3
FSTOP_HZ = 1e11
POINTS_PER_DECADE = 20
# the input from ground to the supply in twelfths; the levels the nominal input may take, 2/12 to
# 10/12 of the supply, each with its step and its supply corners run (where a follower follows
# depends on its devices' thresholds, so on the kit, not on the supply alone: the analysis takes
# the level nearest the middle of the measured input range, analysis.analyze_characteristic)
VIN_SWEEP = tuple(step / 12 for step in range(13))
NOMINAL_VIN = VIN_SWEEP[2:11]
# the middle level's run sweeps its input in DC from ground to the supply, in steps of a 480th of
# the supply (2.5 mV at 1.2 V): the characteristic and its gain over the input level
VIN_DC_STEP = 1 / 480
# the supply at 90 and 110 % of its own besides nominal: never past the models' limits
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the step about the nominal input, as a share of the supply: a quarter for a source follower, an
# eighth for a flipped one (whose input range is narrower); a 20 ns period, 10 ps edges (the
# input's transition times t_r, t_f: [Baker] Fig. 10.9, p. 333), a sample every 5 ps
VIN_STEP = {Topology.SOURCE: 1 / 4, Topology.FLIPPED: 1 / 8}
STEP_PERIOD_S = 20e-9
TRANSITION_S = 10e-12
STROBE_S = 5e-12


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the follower's testbench (flow.follower.sim.testbench), on the kit's typical
    models at 25 C: the follower ``params`` in ``pdk`` at supply ``vdd`` into ``cload_f``, its
    input at ``vin_v`` from an ideal source (R_S = 0), its bias references fed
    ``iref_a``, driven as ``stimulus`` says: the AC stimulus on the input (swept ``fstart_hz`` to
    ``fstop_hz``, ``points_per_decade`` a decade; where ``dc_step_v`` is not 0, the input swept in
    DC from ground to the supply by it too), or the input stepping by ``step_v`` about
    ``vin_v``, up a quarter of ``step_period_s`` in and back down three quarters in
    (``transition_time_s`` edges), the transient running on to ``tran_stop_s``, so that each edge
    has half a period to settle, Spectre writing its output every ``waveform_sample_interval_s``
    (its strobe period, the output at the strobes alone). ``vdd`` and ``vin_v`` are the kit's and
    the design's (``runs.testbenches`` sets them); ``step_v`` is positive in a step run alone and
    ``dc_step_v`` is 0 outside a run with the AC stimulus on the input; the rest is the bench every
    follower is characterized on unless given."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    stimulus: Stimulus = Stimulus.INPUT
    vdd: float
    cload_f: float = LOAD_F
    vin_v: float
    iref_a: float = IREF_A
    fstart_hz: float = FSTART_HZ
    fstop_hz: float = FSTOP_HZ
    points_per_decade: int = POINTS_PER_DECADE
    dc_step_v: float = 0.0
    step_v: float = 0.0
    step_period_s: float = STEP_PERIOD_S
    transition_time_s: float = TRANSITION_S
    waveform_sample_interval_s: float = STROBE_S

    @property
    def tran_stop_s(self) -> float:
        """The transient's end: a quarter period past the period, half a period after the fall as
        after the rise."""
        return 5 * float(self.step_period_s) / 4

    def __post_init__(self) -> None:
        values = (self.vdd, self.cload_f, self.vin_v, self.iref_a)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("follower testbench values must be finite")
        if min(float(self.vdd), float(self.cload_f), self.iref_a) <= 0:
            raise ValueError("follower supply, load, and reference current must be positive")
        if not 0 <= float(self.vin_v) <= float(self.vdd):
            raise ValueError("follower input must lie between the rails")
        if not 0 < self.fstart_hz < self.fstop_hz or self.points_per_decade < 1:
            raise ValueError("follower frequency sweep must rise from a positive start")
        if not 0 <= self.dc_step_v < float(self.vdd) or self.dc_step_v and self.stimulus is not Stimulus.INPUT:
            raise ValueError("the follower's DC sweep steps the input of an AC run by less than the supply")
        if (float(self.step_v) > 0) is not (self.stimulus is Stimulus.STEP) or float(self.step_v) < 0:
            raise ValueError("the follower's input steps by a positive step in a step run alone")
        if self.stimulus is Stimulus.STEP:
            low, high = float(self.vin_v) - float(self.step_v) / 2, float(self.vin_v) + float(self.step_v) / 2
            if not 0 <= low < high <= float(self.vdd):
                raise ValueError("the follower input step must rise and stay between the rails")
            if (
                not 0 < 4 * float(self.transition_time_s) < float(self.step_period_s)
                or self.waveform_sample_interval_s <= 0
            ):
                raise ValueError("the follower step needs short edges in its period and a positive record interval")
            if self.waveform_sample_interval_s > float(self.transition_time_s):
                raise ValueError("the follower step's record interval must resolve its edges")
