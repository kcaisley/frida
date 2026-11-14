"""The amplifier's parameters: its design (``Params``, every one of which builds), one run of its
testbench (``TbParams``), and the bench every amplifier is characterized on.

Every amplifier is characterized the same way, so that amplifiers compare: ``LOAD_F`` on each
output, its tail carrying ``ISS_A``, its cascode biases ``VCASN`` and ``VCASP`` of the supply, a
differential output held at ``VOUT_CM`` of the supply by an ideal common-mode feedback of gain
``CMFB_GAIN``; the small-signal bench from ``FSTART_HZ`` to ``FSTOP_HZ``, over the input common
mode (``CM_SWEEP``, fractions of the supply) and over the supply (``SUPPLY_SWEEP``, fractions of
its own) at mid-supply input (``NOMINAL_CM``); and, for a single-ended output in unity-gain
feedback, an input step of ``STEP`` of the supply and an input sine of amplitude ``SINE`` of the
supply at ``SINE_HZ``.
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline


class Topology(Enum):
    """The amplifier's first stage."""

    # [Razavi-Analog] Fig. 5.22, p. 147: five-transistor OTA
    FIVE_T = auto()  # tail, input pair, current-mirror load: one output, outp
    # [Razavi-Analog] Fig. 9.8(b), p. 350: telescopic cascode op amp with differential output
    TELESCOPIC = auto()  # tail, input pair, cascodes on both, current-source load: outp and outn
    # [Razavi-Analog] Fig. 9.15, p. 357: folded-cascode op amp
    FOLDED = auto()  # tail, input pair folded into cascoded current sources: outp and outn
    # not in the reference texts: complementary input pairs whose two tails are biased from the
    # amplifier's own inp-side drains (M. Bazes, IEEE J. Solid-State Circuits 26(2), 1991)
    SELF_BIASED = auto()  # complementary pairs, both tails driven by one side's drain: outp


class Bench(Enum):
    """Which testbench a run is: the open-loop small-signal one (operating point, AC response,
    transfer functions and noise), or a transient of the amplifier in unity-gain feedback, its
    input stepping or carrying a sine."""

    AC = auto()
    STEP = auto()
    SINE = auto()


@h.paramclass
class Params:
    """The amplifier: its first stage (``Topology``) with an NMOS or PMOS input pair, an optional
    common-source second stage on each output, and its device sizes as positive multiples of the
    PDK's unit width and minimum length (w = 8: eight unit widths), so that one design ports across
    PDKs. Every Params the class admits builds; the defaults are the five-transistor amplifier
    with an NMOS input."""

    topology = h.Param(dtype=Topology, desc="Amplifier topology", default=Topology.FIVE_T)
    input_xtors = h.Param(dtype=MosType, desc="Input pair type (NMOS or PMOS)", default=MosType.NMOS)
    two_stage = h.Param(dtype=bool, desc="A common-source second stage on each output", default=False)
    miller = h.Param(dtype=h.Prefixed, desc="Miller capacitor of the second stage (0: none)", default=0 * f)

    # device sizes, in unit widths and minimum lengths
    in_w = h.Param(dtype=PositiveInt, desc="Input pair width multiplier", default=16)
    in_l = h.Param(dtype=PositiveInt, desc="Input pair length multiplier", default=2)
    tail_w = h.Param(dtype=PositiveInt, desc="Tail width multiplier", default=16)
    tail_l = h.Param(dtype=PositiveInt, desc="Tail length multiplier", default=4)
    load_w = h.Param(dtype=PositiveInt, desc="Load (mirror or current source) width multiplier", default=16)
    load_l = h.Param(dtype=PositiveInt, desc="Load length multiplier", default=4)
    cas_w = h.Param(dtype=PositiveInt, desc="Cascode width multiplier", default=16)
    cas_l = h.Param(dtype=PositiveInt, desc="Cascode length multiplier", default=1)
    stage2_w = h.Param(dtype=PositiveInt, desc="Second-stage input width multiplier", default=16)
    stage2_l = h.Param(dtype=PositiveInt, desc="Second-stage length multiplier", default=2)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)

    def __post_init__(self) -> None:
        # the self-biased amplifier has both input types: its input type is NMOS by convention
        if self.topology is Topology.SELF_BIASED and self.input_xtors is not MosType.NMOS:
            raise ValueError("the self-biased amplifier has both input pairs: its input type is NMOS")
        if float(self.miller) < 0 or (float(self.miller) > 0 and not self.two_stage):
            raise ValueError("a Miller capacitor is positive and belongs to a second stage")


pipeline.Params.register(Params)


# the bench: 50 fF on each output, a 40 uA tail, the cascodes an eighth of the supply above (NMOS)
# and below (PMOS) its middle, a differential output held at mid-supply by a feedback of gain 100
LOAD_F = 50e-15
ISS_A = 40e-6
VCASN = 5 / 8
VCASP = 3 / 8
VOUT_CM = 1 / 2
CMFB_GAIN = 100.0
# the small-signal sweep: 1 kHz to 100 GHz, twenty points a decade
FSTART_HZ = 1e3
FSTOP_HZ = 1e11
POINTS_PER_DECADE = 20
# the input common mode over 1/6 to 5/6 of the supply, its middle the nominal point; the supply at
# 90 and 110 % of its own besides nominal, the common modes at mid-supply: never past the models'
# limits
CM_SWEEP = tuple(step / 24 for step in range(4, 21, 2))
NOMINAL_CM = 0.5
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the input common-mode range: where the low-frequency gain is no further below its mid-supply value
GAIN_DROP_DB = 6.0
# the unity-gain benches, about mid-supply: a step of a quarter of the supply up and back down
# (a 20 ns period, 10 ps edges, a sample every 5 ps), and a sine of a tenth of the supply at 10 MHz
# (ten periods, the first two settling, a sample every 100 ps)
STEP = 1 / 4
STEP_PERIOD_S = 20e-9
TRANSITION_S = 10e-12
STROBE_S = 5e-12
SINE = 1 / 10
SINE_HZ = 10e6
SINE_PERIODS = 10
SINE_STROBE_S = 100e-12


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the amplifier's testbench (flow.ota.sim.testbench): the amplifier ``params`` in
    ``pdk`` at supply ``vdd`` with ``cload_f`` on each output, its inputs at the common mode
    ``vin_cm_v``, its bias references carrying ``iss_a``, its cascodes at ``vcasn_v`` and
    ``vcasp_v``, a differential output held at ``vout_cm_v`` by a feedback of ``cmfb_gain``.
    ``bench`` picks the run: the small-signal one over ``fstart_hz`` to ``fstop_hz``
    (``Bench.AC``), or the unity-gain transient of a single-ended amplifier, its input stepping
    ``vin_step_v`` about the common mode once a ``step_period_s`` (``Bench.STEP``) or carrying a
    sine of ``vin_amplitude_v`` at ``vin_frequency_hz`` for ``sine_periods`` periods
    (``Bench.SINE``). Spectre writes a transient every ``waveform_sample_interval_s`` and steps no
    further."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    bench: Bench = Bench.AC
    vdd: float = 1.2
    cload_f: float = LOAD_F
    vin_cm_v: float = 0.6
    iss_a: float = ISS_A
    vcasn_v: float = 0.75
    vcasp_v: float = 0.45
    vout_cm_v: float = 0.6
    cmfb_gain: float = CMFB_GAIN
    fstart_hz: float = FSTART_HZ
    fstop_hz: float = FSTOP_HZ
    points_per_decade: int = POINTS_PER_DECADE
    vin_step_v: float = 0.3
    vin_amplitude_v: float = 0.12
    vin_frequency_hz: float = SINE_HZ
    sine_periods: int = SINE_PERIODS
    step_period_s: float = STEP_PERIOD_S
    transition_time_s: float = TRANSITION_S
    waveform_sample_interval_s: float = STROBE_S

    def __post_init__(self) -> None:
        values = (self.vdd, self.cload_f, self.vin_cm_v, self.vcasn_v, self.vcasp_v, self.vout_cm_v)
        if not all(math.isfinite(float(value)) for value in (*values, self.cmfb_gain, self.iss_a)):
            raise ValueError("amplifier testbench values must be finite")
        if min(float(self.vdd), float(self.cload_f), self.cmfb_gain, self.iss_a) <= 0:
            raise ValueError("amplifier supply, load, common-mode feedback gain and bias current must be positive")
        if not all(0 <= float(value) <= float(self.vdd) for value in values[2:]):
            raise ValueError("amplifier input, bias and output common-mode voltages must lie between the rails")
        if not 0 < self.fstart_hz < self.fstop_hz or self.points_per_decade < 1:
            raise ValueError("amplifier frequency sweep must rise from a positive start")
        if self.bench is Bench.AC:
            return
        swing = float(self.vin_step_v) / 2 if self.bench is Bench.STEP else float(self.vin_amplitude_v)
        if not self.single_ended:
            raise ValueError("the amplifier's unity-gain bench needs a single-ended output")
        if not 0 <= float(self.vin_cm_v) - swing < float(self.vin_cm_v) + swing <= float(self.vdd):
            raise ValueError("the amplifier's unity-gain input must stay between the rails")
        if not 0 < 4 * float(self.transition_time_s) < float(self.step_period_s):
            raise ValueError("the amplifier's step needs short edges in its period")
        if self.vin_frequency_hz <= 0 or self.sine_periods < 3 or self.waveform_sample_interval_s <= 0:
            raise ValueError("the amplifier's sine needs a positive frequency, three periods and a record interval")

    @property
    def single_ended(self) -> bool:
        """Whether the amplifier has one output, ``outp``: a mirror load's, or the self-biased one's."""
        return self.params.topology in (Topology.FIVE_T, Topology.SELF_BIASED)

    @property
    def stop_s(self) -> float:
        """A unity-gain transient's length: one step period, or the sine's periods."""
        if self.bench is Bench.STEP:
            return float(self.step_period_s)
        return self.sine_periods / self.vin_frequency_hz
