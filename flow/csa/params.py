"""The charge-sensitive amplifier's parameters: its design (``Params``), one run of its testbench
(``TbParams``), and the bench every amplifier is characterized on.

Every amplifier is characterized the same way, so that amplifiers compare: ``CDET_F`` of detector
on its input, the charge injected through ``CINJ_F`` by a voltage step, ``CLOAD_F`` on its output;
its load's reference fed ``IREF_A``, its feedback discharging at ``IFB_A``, the input device's
drain ``VDS_IN_V`` off its rail, the Krummenacher reference at ``VREF`` of the supply. A charge run
(``Stimulus.CHARGE``) injects one of ``CHARGES_C`` at ``INJECT_TIME_S`` (the reset opens at
``RESET_TIME_S``, ``TRANSITION_S`` edges), the transient running to ``STOP_TIME_S``, Spectre's
output every ``STROBE_S``; a noise run (``Stimulus.NOISE``) has no charge and gives the output
noise from ``FSTART_HZ`` to ``FSTOP_HZ``, ``POINTS_PER_DECADE`` a decade. Over the supply
(``SUPPLY_SWEEP``, fractions of its own) the smallest charge's response and the noise again.
"""

import math
from dataclasses import dataclass, field, replace
from enum import Enum, auto

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline


class Feedback(Enum):
    """The discharge across the feedback capacitor."""

    KRUMMENACHER = auto()  # a differential pair against vref, its tail current returning the input
    CONTINUOUS = auto()  # one long device across cf, its gate on vfb
    RESET = auto()  # a switch across cf, its gate on vfb


class Stimulus(Enum):
    """What one run of the testbench drives, and so which analyses it holds."""

    CHARGE = auto()  # a charge injected through the injection capacitor: a transient
    NOISE = auto()  # no charge: the operating point and the output noise


@h.paramclass
class Params:
    """The charge-sensitive amplifier: its input device's type, its feedback, its feedback
    capacitor (for simulation: the row cells draw MOS only) and its devices' sizes as positive
    multiples of the PDK's unit width and minimum length (``in_w`` 24 is 24 unit widths, ``in_l``
    1 the minimum length), so that one design ports across PDKs. Every Params the class admits
    builds; the defaults are the NMOS-input Krummenacher amplifier. The Krummenacher's tail, mirror
    and filter (``tail_w`` to ``filter_l``) size only a ``Feedback.KRUMMENACHER``."""

    input_xtors = h.Param(dtype=MosType, desc="Input device type (NMOS or PMOS)", default=MosType.NMOS)
    feedback = h.Param(dtype=Feedback, desc="Discharge across the feedback capacitor", default=Feedback.KRUMMENACHER)
    cf = h.Param(dtype=h.Prefixed, desc="Feedback capacitor, for simulation (0: none)", default=5 * f)
    in_w = h.Param(dtype=PositiveInt, desc="Input device width multiplier", default=24)
    in_l = h.Param(dtype=PositiveInt, desc="Input device length multiplier", default=2)
    cas_w = h.Param(dtype=PositiveInt, desc="Cascode width multiplier", default=8)
    cas_l = h.Param(dtype=PositiveInt, desc="Cascode length multiplier", default=2)
    load_w = h.Param(dtype=PositiveInt, desc="Current-source load width multiplier", default=8)
    load_l = h.Param(dtype=PositiveInt, desc="Current-source load length multiplier", default=8)
    fb_w = h.Param(dtype=PositiveInt, desc="Feedback pair, long device or switch width multiplier", default=2)
    fb_l = h.Param(dtype=PositiveInt, desc="Feedback device length multiplier", default=8)
    tail_w = h.Param(dtype=PositiveInt, desc="Krummenacher tail and mirror width multiplier", default=2)
    tail_l = h.Param(dtype=PositiveInt, desc="Krummenacher tail and mirror length multiplier", default=16)
    filter_w = h.Param(dtype=PositiveInt, desc="Krummenacher mirror filter capacitor width multiplier", default=16)
    filter_l = h.Param(dtype=PositiveInt, desc="Krummenacher mirror filter capacitor length multiplier", default=32)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)

    def __post_init__(self) -> None:
        if float(self.cf) < 0:
            raise ValueError("the feedback capacitor must not be negative")


pipeline.Params.register(Params)


def layout_view(params: Params) -> Params:
    """The amplifier as laid out: without its feedback capacitor, which the row cells do not draw."""
    return replace(params, cf=0 * f)


# the bench: 100 fF of detector, the charge through 1 fF, 10 fF of load; the load's reference fed
# 4 uA, the feedback discharging at 10 nA, the input device's drain 150 mV off its rail, the
# Krummenacher reference 45 % of the supply above ground
CDET_F = 100e-15
CINJ_F = 1e-15
CLOAD_F = 10e-15
IREF_A = 4e-6
IFB_A = 10e-9
VDS_IN_V = 0.15
VREF = 0.45
# the charges: a quarter, a half, one and two femtocoulombs (1.6 to 12.5 thousand electrons)
CHARGES_C = (0.25e-15, 0.5e-15, 1e-15, 2e-15)
# the charge run: the reset opens at 10 ns, the charge arrives at 60 ns, the transient runs to
# 500 ns, 100 ps edges, Spectre's output every 50 ps
RESET_TIME_S = 10e-9
INJECT_TIME_S = 60e-9
STOP_TIME_S = 500e-9
TRANSITION_S = 100e-12
STROBE_S = 50e-12
# the noise run: 1 Hz to 1 GHz, ten points a decade
FSTART_HZ = 1.0
FSTOP_HZ = 1e9
POINTS_PER_DECADE = 10
# the supply at 90 and 110 % of its own besides nominal: never past the models' limits
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the responses' detail in the record's figure, sampled from the transient
PULSE_STEP_S = 1e-9


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the amplifier's testbench (flow.csa.sim.testbench): the amplifier ``params`` in
    ``pdk`` at supply ``vdd``, ``cdet_f`` on its input, ``cload_f`` on its output, the charge
    ``charge_c`` (its magnitude) injected through ``cinj_f``; its load's and cascode's references
    fed ``iref_a``, the cascode's leaving the input device ``vds_in_v`` of drain-source voltage, its
    feedback discharging at ``ifb_a``, the Krummenacher reference at ``vref_v``. ``stimulus`` says
    what it drives: the charge (``CHARGE``: the reset opening at ``reset_time_s``, the injection
    step at ``inject_time_s``, ``transition_time_s`` edges, the transient to ``stop_time_s``,
    Spectre writing its output every ``waveform_sample_interval_s``), or no charge (``NOISE``: the
    output noise from ``fstart_hz`` to ``fstop_hz``, ``points_per_decade`` a decade). A reset
    amplifier holds no operating point at rest: it has no noise run."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    stimulus: Stimulus = Stimulus.CHARGE
    vdd: float = 1.2
    cdet_f: float = CDET_F
    cload_f: float = CLOAD_F
    cinj_f: float = CINJ_F
    charge_c: float = 0.5e-15
    vds_in_v: float = VDS_IN_V
    vref_v: float = 0.54
    iref_a: float = IREF_A
    ifb_a: float = IFB_A
    reset_time_s: float = RESET_TIME_S
    inject_time_s: float = INJECT_TIME_S
    stop_time_s: float = STOP_TIME_S
    transition_time_s: float = TRANSITION_S
    waveform_sample_interval_s: float = STROBE_S
    fstart_hz: float = FSTART_HZ
    fstop_hz: float = FSTOP_HZ
    points_per_decade: int = POINTS_PER_DECADE

    def __post_init__(self) -> None:
        values = (self.vdd, self.cdet_f, self.cload_f, self.cinj_f, self.charge_c, self.vds_in_v, self.vref_v)
        values += (self.reset_time_s, self.inject_time_s, self.stop_time_s, self.transition_time_s)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("charge-sensitive amplifier testbench values must be finite")
        if min(float(self.vdd), float(self.cinj_f), self.iref_a, self.ifb_a) <= 0:
            raise ValueError("amplifier supply, injection capacitance and bias currents must be positive")
        if min(float(self.cdet_f), float(self.cload_f), float(self.charge_c)) < 0:
            raise ValueError("amplifier capacitances and charge must not be negative")
        if not (0 < float(self.vds_in_v) < float(self.vdd) and 0 <= float(self.vref_v) <= float(self.vdd)):
            raise ValueError("amplifier bias voltages must lie between the rails")
        edge = float(self.transition_time_s)
        if not 0 < edge < float(self.reset_time_s) < float(self.inject_time_s) < float(self.stop_time_s) - edge:
            raise ValueError("the reset must open and the charge arrive, in that order, within the transient")
        if self.waveform_sample_interval_s <= 0:
            raise ValueError("amplifier record interval must be positive")
        if not 0 < self.fstart_hz < self.fstop_hz or self.points_per_decade < 1:
            raise ValueError("amplifier noise sweep must rise from a positive start")
        if (float(self.charge_c) > 0) is not (self.stimulus is Stimulus.CHARGE):
            raise ValueError("the amplifier's charge is positive in a charge run, and zero in a noise run")
        if self.params.feedback is Feedback.RESET and self.stimulus is Stimulus.NOISE:
            raise ValueError("a reset amplifier holds no operating point for the noise bench")

    @property
    def injection_step_v(self) -> float:
        """The injection step: the charge over the injection capacitance, its sign the one that moves
        the output away from the input device's rail (electrons into an NMOS input, holes into a
        PMOS one)."""
        sign = -1.0 if self.params.input_xtors is MosType.NMOS else 1.0
        return sign * float(self.charge_c) / float(self.cinj_f)
