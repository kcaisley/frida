"""The delay line and ring oscillator's parameters: its design (``Params``), one run of its
testbench (``TbParams``), and the bench every chain is characterized on.

Every chain is characterized the same way, so that chains compare: over the supply
(``SUPPLY_SWEEP``, fractions of the PDK's own) at the nominal control (``NOMINAL_CONTROL`` of
the PDK's supply), and, a chain with a control (starved, or on a shared tail), over the control
(``CONTROL_SWEEP``, fractions of the supply) at the PDK's supply; its gain about the nominal
control from the points either side of it (``GAIN_POINTS``).
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosVth
from pydantic import PositiveInt

from flow import pipeline


class Stage(Enum):
    INVERTER = auto()  # one CMOS inverter per chain and stage
    COUPLED = auto()  # a pseudo-differential stage with weak cross-coupled inverters across its outputs


class Control(Enum):
    NONE = auto()  # the stages' sources on the rails
    STARVED = auto()  # each inverter between an NMOS foot (vbn) and a PMOS head (vbp)
    TAIL = auto()  # every NMOS source on one shared tail, an NMOS gated by vctrl


@h.paramclass
class Params:
    """The delay line or ring oscillator: its topology and its devices' sizes as positive multiples
    of the PDK's unit width and minimum length (``inv_n_w`` 4 is four unit widths, ``inv_l`` 1 the
    minimum length), so that one design ports across PDKs. Every Params the class admits builds; the
    defaults are a five-stage inverter delay line.

    A coupled stage and an injection device need both chains; a ring needs an inversion around the
    loop, so a single-ended ring has an odd number of stages (a differential one crosses its chains
    at the end) and at least two; an injection device belongs to a ring."""

    # Topology parameters
    stage = h.Param(dtype=Stage, desc="Stage type", default=Stage.INVERTER)
    control = h.Param(dtype=Control, desc="Delay control", default=Control.NONE)
    stages = h.Param(dtype=PositiveInt, desc="Number of stages", default=5)
    differential = h.Param(dtype=bool, desc="Two chains, inp to outp and inn to outn", default=False)
    ring = h.Param(dtype=bool, desc="The last stage drives the first (an oscillator)", default=False)
    inject = h.Param(dtype=bool, desc="Injection device across the first stage's outputs (ring)", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    inv_n_w = h.Param(dtype=PositiveInt, desc="Inverter NMOS width multiplier", default=4)
    inv_p_w = h.Param(dtype=PositiveInt, desc="Inverter PMOS width multiplier", default=8)
    inv_l = h.Param(dtype=PositiveInt, desc="Inverter length multiplier", default=1)
    fb_n_w = h.Param(dtype=PositiveInt, desc="Coupling inverter NMOS width multiplier", default=2)
    fb_p_w = h.Param(dtype=PositiveInt, desc="Coupling inverter PMOS width multiplier", default=4)
    starve_n_w = h.Param(dtype=PositiveInt, desc="Starving NMOS width multiplier", default=4)
    starve_p_w = h.Param(dtype=PositiveInt, desc="Starving PMOS width multiplier", default=8)
    starve_l = h.Param(dtype=PositiveInt, desc="Starving device length multiplier", default=2)
    tail_w = h.Param(dtype=PositiveInt, desc="Shared tail width multiplier", default=16)
    tail_l = h.Param(dtype=PositiveInt, desc="Shared tail length multiplier", default=2)
    en_w = h.Param(dtype=PositiveInt, desc="Ring enable device width multiplier", default=2)
    inj_w = h.Param(dtype=PositiveInt, desc="Injection device width multiplier", default=4)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)

    def __post_init__(self) -> None:
        if (self.stage is Stage.COUPLED or self.inject) and not self.differential:
            raise ValueError("a coupled stage and an injection device need both chains (differential)")
        if self.inject and not self.ring:
            raise ValueError("an injection device belongs to a ring")
        if self.ring and not self.differential and self.stages % 2 == 0:
            raise ValueError("a single-ended ring needs an odd number of stages: an inversion around the loop")
        if self.ring and self.stages < 2:
            raise ValueError("a ring needs at least two stages")


pipeline.Params.register(Params)


# the supply at 90 and 110 % of its own besides nominal: never past the models' limits
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the control from 5/12 of the supply to all of it, its nominal 8/12, and the points either side
# of the nominal that the gain about it is taken from
CONTROL_SWEEP = tuple(step / 12 for step in range(5, 13))
NOMINAL_CONTROL = 8 / 12
GAIN_POINTS = (7 / 12, 9 / 12)


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the chain's testbench (flow.delay.sim.testbench): the chain ``params`` in ``pdk``
    at supply ``vdd`` with ``cload_f`` on each output. ``vcont_v`` sets every analog control at
    once: ``vbn`` and ``vctrl`` to it and ``vbp`` to the supply minus it. A ring's enable rises
    after ``enable_delay_s`` and a kick-start then holds the outputs apart for ``kick_time_s``; a
    delay line's complementary input clock has the period ``clock_period_s``; both edge in
    ``transition_time_s``. ``vinj_v`` is the injection input's level. The transient runs
    ``stop_time_s``; Spectre writes its output every ``waveform_sample_interval_s`` and steps no
    further."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    vdd: float = 1.2
    vcont_v: float = 0.8
    cload_f: float = 2e-15
    kick_time_s: float = 1e-9
    vinj_v: float = 0.0
    clock_period_s: float = 4e-9
    transition_time_s: float = 50e-12
    enable_delay_s: float = 1e-9
    stop_time_s: float = 40e-9
    waveform_sample_interval_s: float = 2e-12

    def __post_init__(self) -> None:
        values = (
            self.waveform_sample_interval_s,
            self.vdd,
            self.vcont_v,
            self.cload_f,
            self.kick_time_s,
            self.vinj_v,
            self.clock_period_s,
            self.transition_time_s,
            self.enable_delay_s,
            self.stop_time_s,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("delay testbench values must be finite")
        if min(float(self.vdd), float(self.cload_f), float(self.kick_time_s), self.waveform_sample_interval_s) <= 0:
            raise ValueError("delay supply, loads, and sample interval must be positive")
        if not 0 <= float(self.vcont_v) <= float(self.vdd):
            raise ValueError("delay control voltage must lie between the rails")
        if float(self.clock_period_s) <= 2 * float(self.transition_time_s) or float(self.transition_time_s) <= 0:
            raise ValueError("delay input period must exceed both transitions, which must be positive")
        if not 0 <= float(self.enable_delay_s) < float(self.stop_time_s):
            raise ValueError("delay enable must rise within the transient")
