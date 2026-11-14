"""The amplifier's parameters: its design (``Params``, every one of which builds), one run of its
testbench (``TbParams``), and the bench every amplifier is characterized on.

Every amplifier is characterized the same way, so that amplifiers compare: ``LOAD_F`` on each
output and its tail carrying ``ISS_A`` at the nominal input common mode, every other bias derived
on the bench from copies of the devices it drives (``flow.ota.sim``); a differential output held by
an ideal common-mode feedback of gain ``CMFB_GAIN``; the small-signal bench from ``FSTART_HZ`` to
``FSTOP_HZ``, at the nominal input common mode, over the input common mode from rail to rail
(``CM_SWEEP``, fractions of the supply) and over the supply (``SUPPLY_SWEEP``, fractions of its
own); and, for a single-ended output in unity-gain feedback, an input step of ``STEP`` of the
supply and an input sine of amplitude ``SINE`` of the supply at ``SINE_HZ``, each inside the input
common-mode range.
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
        differential = self.topology in (Topology.TELESCOPIC, Topology.FOLDED)
        # the bench's common-mode feedback returns its error to the load bias vbp, an NMOS input's
        if differential and self.input_xtors is not MosType.NMOS:
            raise ValueError(
                "a differential amplifier's input pair is NMOS: the bench's feedback drives the load bias vbp"
            )
        # [Razavi-Analog] Fig. 9.7, p. 350: the single-ended amplifiers' unity-gain bench feeds outp
        # back to inn, which a common-source second stage would turn into positive feedback
        if self.two_stage and not differential:
            raise ValueError("a second stage belongs to a differential amplifier: one would invert the unity-gain loop")
        # [Razavi-Analog] Eq. (5.4), p. 136: a mirror copies its current in the ratio of the devices' W/L
        # [Razavi-Analog] Sec. 5.1, p. 138: mirror devices share one length, the ratio set by width
        # the devices on the tail's bias (a folded cascode's bottom sources, a second stage's current
        # sources) copy its current so
        if (self.topology is Topology.FOLDED or self.two_stage) and self.load_l != self.tail_l:
            raise ValueError("the current sources on the tail's bias take the tail's length")


pipeline.Params.register(Params)


# the bench: 50 fF on each output, a 40 uA tail at the nominal input common mode, a differential
# output held by a feedback of gain 100 (a two-stage amplifier's at mid-supply)
LOAD_F = 50e-15
ISS_A = 40e-6
CMFB_GAIN = 100.0
# the small-signal sweep: 1 kHz to 100 GHz, twenty points a decade
FSTART_HZ = 1e3
FSTOP_HZ = 1e11
POINTS_PER_DECADE = 20
# the input common mode from rail to rail in twelfths of the supply; the supply at 90 and 110 % of
# its own besides nominal: never past the models' limits
CM_SWEEP = tuple(step / 12 for step in range(13))
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the unity-gain benches, inside the input common-mode range from the nominal input common mode: a
# step of a sixth of the supply up and back down (a 20 ns period, 10 ps edges, a sample every 5 ps),
# and a sine of a twentieth of the supply at 10 MHz, its swing within the step's (ten periods, the
# first two settling, a sample every 100 ps)
STEP = 1 / 6
STEP_PERIOD_S = 20e-9
TRANSITION_S = 10e-12
STROBE_S = 5e-12
SINE = 1 / 20
SINE_HZ = 10e6
SINE_PERIODS = 10
SINE_STROBE_S = 100e-12
# the harmonics THD counts and the output spectrum's figure shows: to the seventh; the figure's floor
# at -160 dB of the input's amplitude
SPECTRUM_HARMONICS = 7
SPECTRUM_FLOOR_DB = -160.0


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the amplifier's testbench (flow.ota.sim.testbench): the amplifier ``params`` in
    ``pdk`` at supply ``vdd`` with ``cload_f`` on each output. Its bias network sets every bias
    from copies of the devices it drives: the tail carries ``iss_a`` at the nominal input common
    mode, which the network derives (the inputs sit there where ``vin_cm_v`` is None, at
    ``vin_cm_v`` otherwise, the biases staying at the nominal point); a differential output is held
    by an ideal feedback of gain ``cmfb_gain``. ``bench`` picks the run: the small-signal one over
    ``fstart_hz`` to ``fstop_hz`` (``Bench.AC``), or the unity-gain transient of a single-ended
    amplifier, its input stepping ``vin_step_v`` up and back down once a ``step_period_s``
    (``Bench.STEP``) or carrying a sine of ``vin_amplitude_v`` at ``vin_frequency_hz`` for
    ``sine_periods`` periods (``Bench.SINE``), from the nominal input common mode into the input
    pair's range (``vin_low_offset_v``). Spectre writes a transient every
    ``waveform_sample_interval_s`` and steps no further.

    The devices on the tail's bias (a folded cascode's bottom sources, a second stage's current
    sources) carry ``iss_a`` times their width over the tail's, at its length (``Params`` refuses
    another length)."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    bench: Bench = Bench.AC
    vdd: float = 1.2
    cload_f: float = LOAD_F
    vin_cm_v: float | None = None
    iss_a: float = ISS_A
    cmfb_gain: float = CMFB_GAIN
    fstart_hz: float = FSTART_HZ
    fstop_hz: float = FSTOP_HZ
    points_per_decade: int = POINTS_PER_DECADE
    vin_step_v: float = 0.2
    vin_amplitude_v: float = 0.06
    vin_frequency_hz: float = SINE_HZ
    sine_periods: int = SINE_PERIODS
    step_period_s: float = STEP_PERIOD_S
    transition_time_s: float = TRANSITION_S
    waveform_sample_interval_s: float = STROBE_S

    def __post_init__(self) -> None:
        values = (self.vdd, self.cload_f, self.cmfb_gain, self.iss_a, self.vin_step_v, self.vin_amplitude_v)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("amplifier testbench values must be finite")
        if min(float(value) for value in values) <= 0:
            raise ValueError("amplifier supply, load, feedback gain, bias current and stimuli must be positive")
        if self.vin_cm_v is not None and not 0 <= float(self.vin_cm_v) <= float(self.vdd):
            raise ValueError("amplifier input common mode must lie between the rails")
        if not 0 < self.fstart_hz < self.fstop_hz or self.points_per_decade < 1:
            raise ValueError("amplifier frequency sweep must rise from a positive start")
        if self.bench is Bench.AC:
            return
        if not self.single_ended:
            raise ValueError("the amplifier's unity-gain bench needs a single-ended output")
        if self.vin_cm_v is not None:
            raise ValueError("the amplifier's unity-gain stimulus starts from the nominal input common mode")
        if not 0 < 4 * float(self.transition_time_s) < float(self.step_period_s):
            raise ValueError("the amplifier's step needs short edges in its period")
        if self.vin_frequency_hz <= 0 or self.sine_periods < 3 or self.waveform_sample_interval_s <= 0:
            raise ValueError("the amplifier's sine needs a positive frequency, three periods and a record interval")

    @property
    def single_ended(self) -> bool:
        """Whether the amplifier has one output, ``outp``: a mirror load's, or the self-biased one's."""
        return self.params.topology in (Topology.FIVE_T, Topology.SELF_BIASED)

    @property
    def vin_low_offset_v(self) -> float:
        """A unity-gain stimulus's lowest input level relative to the nominal input common mode: an
        NMOS pair's nominal point lies near its range's low end, so the stimulus rises from it; a
        PMOS pair's near its high end, so the stimulus falls to it; the self-biased amplifier's at
        mid-supply, so the stimulus straddles it."""
        swing = float(self.vin_step_v) if self.bench is Bench.STEP else 2 * float(self.vin_amplitude_v)
        if self.params.topology is Topology.SELF_BIASED:
            return -swing / 2
        return 0.0 if self.params.input_xtors is MosType.NMOS else -swing

    @property
    def stop_s(self) -> float:
        """A unity-gain transient's length: one step period, or the sine's periods."""
        if self.bench is Bench.STEP:
            return float(self.step_period_s)
        return self.sine_periods / self.vin_frequency_hz
