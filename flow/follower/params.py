"""The follower's parameters: its design (``Params``), one run of its testbench (``TbParams``), and
the bench every follower is characterized on.

Every follower is characterized the same way, so that followers compare: into ``LOAD_F``, its
current sources biased from references carrying ``IREF_A`` at the current-source width
``IREF_W`` (the current in proportion to the design's own width), over the input level
(``VIN_SWEEP``, fractions of the supply) with the AC stimulus on the input and on a test current
into the output (through ``TEST_OHM``), each over ``FSTART_HZ`` to ``FSTOP_HZ``; at its nominal
input (``NOMINAL_VIN``, where a follower of its topology and input type follows) over the supply
(``SUPPLY_SWEEP``, fractions of its own), and there a step of ``VIN_STEP`` of the supply up and
back down (``STEP_PERIOD_S``, ``TRANSITION_S`` edges, Spectre's output every ``STROBE_S``).
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

    INPUT = auto()  # the AC stimulus on the input: the response and the supply's transfer to the output
    OUTPUT = auto()  # the AC stimulus on a test current into the output: the output impedance
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


# the bench: 100 fF, the references' 20 uA at a current source 16 units wide (a source follower)
# or 8 (a flipped one), the test current through 1 Mohm, 1 kHz to 100 GHz at 20 points a decade
LOAD_F = 100e-15
IREF_A = 20e-6
IREF_W = {Topology.SOURCE: 16, Topology.FLIPPED: 8}
TEST_OHM = 1e6
FSTART_HZ = 1e3
FSTOP_HZ = 1e11
POINTS_PER_DECADE = 20
# the input from ground to the supply in twelfths; each follower's nominal input, where one of its
# topology and input type follows: an NMOS source follower high, a PMOS one low, the flipped ones
# in their narrower range
VIN_SWEEP = tuple(step / 12 for step in range(13))
NOMINAL_VIN = {
    (Topology.SOURCE, MosType.NMOS): 9 / 12,
    (Topology.SOURCE, MosType.PMOS): 3 / 12,
    (Topology.FLIPPED, MosType.NMOS): 6 / 12,
    (Topology.FLIPPED, MosType.PMOS): 3 / 12,
}
# the supply at 90 and 110 % of its own besides nominal, the input at its share of it: never past
# the models' limits
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the step: a quarter of the supply about the nominal input, a 20 ns period, 10 ps edges, a sample
# every 5 ps
VIN_STEP = 1 / 4
STEP_PERIOD_S = 20e-9
TRANSITION_S = 10e-12
STROBE_S = 5e-12


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the follower's testbench (flow.follower.sim.testbench): the follower ``params``
    in ``pdk`` at supply ``vdd`` into ``cload_f``, its input at ``vin_v``, its bias references fed
    ``iref_a``, driven as ``stimulus`` says: the AC stimulus on the input, or on a test current
    into the output through ``test_resistance_ohm`` (both swept ``fstart_hz`` to ``fstop_hz``,
    ``points_per_decade`` a decade), or the input stepping by ``step_v`` about ``vin_v``, up a
    quarter of ``step_period_s`` in and back down three quarters in (``transition_time_s``
    edges), Spectre writing its output every ``waveform_sample_interval_s`` and stepping no
    further; on the bench every follower is characterized on unless given."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    stimulus: Stimulus = Stimulus.INPUT
    vdd: float = 1.2
    cload_f: float = LOAD_F
    vin_v: float = 0.9
    iref_a: float = IREF_A
    test_resistance_ohm: float = TEST_OHM
    fstart_hz: float = FSTART_HZ
    fstop_hz: float = FSTOP_HZ
    points_per_decade: int = POINTS_PER_DECADE
    step_v: float = 0.3
    step_period_s: float = STEP_PERIOD_S
    transition_time_s: float = TRANSITION_S
    waveform_sample_interval_s: float = STROBE_S

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
        if self.stimulus is Stimulus.STEP:
            low, high = float(self.vin_v) - float(self.step_v) / 2, float(self.vin_v) + float(self.step_v) / 2
            if not 0 <= low < high <= float(self.vdd):
                raise ValueError("the follower input step must rise and stay between the rails")
            if (
                not 0 < 4 * float(self.transition_time_s) < float(self.step_period_s)
                or self.waveform_sample_interval_s <= 0
            ):
                raise ValueError("the follower step needs short edges in its period and a positive record interval")
