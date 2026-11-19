"""The sampling switch's parameters: its design (``Params``), one run of its testbench (``TbParams``),
and the benches every switch is characterized on.

Every switch is characterized the same way, so that switches compare: into ``LOAD_F`` (about the
CDAC it samples onto) at a ``PERIOD_S`` clock (``TRACK_S`` tracking, ``TRANSITION_S`` edges), its
input stepping by ``SMALL_STEP`` of the supply once a period, ``PERIODS`` periods, Spectre's output
every ``STROBE_S``; over the input level (``VIN_SWEEP``, fractions of the supply, and the supply
less half the step, ``VIN_TOP``, the top of the ADC's swing) and over the supply (``SUPPLY_SWEEP``,
fractions of its own) at the nominal input (``NOMINAL_VIN`` of the nominal supply); at the process
corners and the hot temperature (``HOT_C``); at the ADC's timing (``ADC_TRACK_S``,
``ADC_PERIOD_S``, ``ADC_PERIODS`` periods, its output every ``ADC_STROBE_S``): its acquisition of a
full-scale step, its droop over the hold, a sine of the ADC's swing (``ADC_CM``,
``SINE_AMPLITUDE``, ``SINE_SAMPLES`` samples, tones ``SINE_CYCLES``) and its held output stepped as
the ADC's first decision steps it, at the lowest level a side reaches (``VIN_BOTTOM``) and at the
common mode; its complementary clock an edge late.

The behavioral model (``flow.samp.model``) derives the switch's triode conductances from its sizing
with the rough device constants here (``W_MIN_UM`` to ``PMOS_K_A_PER_V2``).
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosVth
from pydantic import PositiveInt

from flow import pipeline


class SwitchType(Enum):
    """Sampling switch topology."""

    NMOS = auto()
    PMOS = auto()
    TGATE = auto()
    BOOTSTRAP = auto()  # the NMOS switch, its gate boosted one supply above the input while tracking


class Stimulus(Enum):
    """What the testbench's input does: a level stepping once a period (``STEP``), or a sine
    (``SINE``)."""

    STEP = auto()
    SINE = auto()


@h.paramclass
class Params:
    """The sampling switch: its topology and its devices' sizes as positive multiples of the PDK's
    unit width and minimum length (``mos_w`` 32 is about 4 um in FRIDA65A, ``mos_l`` 1 its minimum
    length), so that one design ports across PDKs. Every Params the class admits builds; the defaults
    are FRIDA-1's fabricated sampler, a transmission gate of 32 units a side. The bootstrap's helpers
    and capacitor (``boot_w``, ``cap_w``, ``cap_l``) size only a ``SwitchType.BOOTSTRAP``."""

    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.TGATE)
    mos_w = h.Param(dtype=PositiveInt, desc="Width multiplier (x Wmin)", default=32)
    mos_l = h.Param(dtype=PositiveInt, desc="Length multiplier (x Lmin)", default=1)
    mos_vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)
    dummy = h.Param(dtype=bool, desc="Half-size dummies on vout, clocked opposite their switch", default=False)
    boot_w = h.Param(dtype=PositiveInt, desc="Bootstrap helper device width multiplier", default=4)
    cap_w = h.Param(dtype=PositiveInt, desc="Bootstrap MOS capacitor width multiplier", default=16)
    cap_l = h.Param(dtype=PositiveInt, desc="Bootstrap MOS capacitor length multiplier", default=8)

    def __post_init__(self) -> None:
        # a dummy is half its switch, in whole units
        if self.dummy and self.mos_w < 2:
            raise ValueError("a dummy is half its switch: the switch needs at least 2 width units")


pipeline.Params.register(Params)


FRIDA1 = Params()  # the fabricated FRIDA-1 sampler: transmission gate, 32 units each

# the bench: 1 pF at a 10 ns clock (5 ns tracking), 50 ps edges, six periods, a sample every 5 ps
LOAD_F = 1e-12
PERIOD_S = 10e-9
TRACK_S = 5e-9
TRANSITION_S = 50e-12
PERIODS = 6
STROBE_S = 5e-12
# the input over 1/12 to 11/12 of the supply, its middle the nominal point, and the transients the
# record keeps for the viewer (the lowest, the middle and the highest input)
VIN_SWEEP = tuple(step / 12 for step in range(1, 12))
NOMINAL_VIN = 0.5
WAVE_VIN = (VIN_SWEEP[0], NOMINAL_VIN, VIN_SWEEP[-1])
# the level runs' input step, a fraction of the supply: small against the on-resistance's change
# over the input, so that each level's resistance is the resistance at that level
SMALL_STEP = 1 / 120
# the supply less half the step, the highest level: the ADC's swing reaches 1.19 V of 1.2 V a side
# (flow.adc: 0.7 V common mode, its sawtooth 1.05 times the full scale); its lowest, as far below
# the ADC's common mode (0.7 V of 1.2 V) as the highest is above it
VIN_TOP = 1 - SMALL_STEP / 2
ADC_CM = 7 / 12
VIN_BOTTOM = 2 * ADC_CM - VIN_TOP
# the supply at 90 and 110 % of its own besides nominal, the input at its nominal level: never past
# the models' limits (a kit's device models may warn above 110 %)
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# the hot corner (the models' usual junction limit), where leakage and the on-resistance are largest
HOT_C = 125.0
# the ADC's sampling: 20 symbols tracking of a 160-symbol conversion at 1.6 GHz (flow.adc.params);
# its runs three conversions long (the first starts from the operating point), their output every
# 50 ps
ADC_TRACK_S = 12.5e-9
ADC_PERIOD_S = 100e-9
ADC_PERIODS = 3
ADC_STROBE_S = 50e-12
# Spectre's gmin for the runs that read a hold's leakage (the droop): its default, 1e-12 S across
# every junction and channel, draws 1e-12 S x 0.6 V = 0.6 pA from a held 0.6 V
LEAKAGE_GMIN_S = 1e-18
# the bootstrap's bottom-plate switch's resistance over its switch's, times its boost capacitor's
# area in unit areas (flow.samp.subckt._bottom_length): the 32-unit bootstrapped switch's
# (flow.samp.runs.bootstrap), its bottom-plate switch at the helpers' width and 8 units long (64
# times the switch's resistance) under a boost capacitor of 96 by 16 units
BOTTOM_LIFT = 64 * 96 * 16
# acquisition to half an LSB of the supply, at these resolutions (bits)
ACQUISITION_BITS = (10, 12, 14)
# a sine of the ADC's swing a side, fractions of the supply: about its common mode, 0.44 V (its
# 12-bit full scale, 0.94 V differential, 0.5 dB below), SINE_SAMPLES samples at the ADC's timing,
# SINE_CYCLES cycles in them (a low tone and one near Nyquist)
SINE_AMPLITUDE = 0.37
SINE_SAMPLES = 32
SINE_CYCLES = (1, 15)
# Rough 65-nm device constants, for the behavioral model's triode conductances from the switch's
# sizing where none is given (flow.samp.model.Model.conductances): the width and the length one size
# unit stands for, and each device type's k'
W_MIN_UM = 0.12
L_MIN_UM = 0.06
NMOS_K_A_PER_V2 = 300e-6
PMOS_K_A_PER_V2 = 100e-6


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the sampler's testbench (flow.samp.sim.testbench): the switch ``params`` in ``pdk``
    at supply ``vdd``, process ``corner`` and ``temperature_c`` into ``cload``; its input at
    ``input_voltage`` or, with an ``input_step_v``, stepping by it once a period in the middle of
    each hold phase, or (``stimulus`` SINE) a sine about ``input_voltage`` of ``sine_amplitude_v``
    at ``sine_frequency_hz``; its clock tracking while high (``clock_high_time_s`` of each
    ``clock_period_s``), the complement ``clock_skew_s`` later; with a ``dac_step_v``, half the load
    driven so that the held output steps by it a quarter into each hold and back before the next
    track (the DAC's first step); ``periods`` periods; on the bench every switch is characterized
    on unless given. Spectre writes its output every ``waveform_sample_interval_s`` and steps no
    further, at its own gmin or ``gmin_s``; with ``oppoint`` it also saves every transistor's
    operating values (PSF ASCII)."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    vdd: float = 1.2
    corner: h.pdk.Corner = h.pdk.Corner.TYP
    temperature_c: float = 25.0
    cload: float = LOAD_F
    stimulus: Stimulus = Stimulus.STEP
    input_voltage: float = 0.6
    input_step_v: float = 0.1
    sine_amplitude_v: float = 0.0
    sine_frequency_hz: float = 0.0
    clock_period_s: float = PERIOD_S
    clock_high_time_s: float = TRACK_S
    clock_transition_time_s: float = TRANSITION_S
    clock_delay_s: float = 0.0
    clock_skew_s: float = 0.0
    dac_step_v: float = 0.0
    periods: int = PERIODS
    waveform_sample_interval_s: float = STROBE_S
    oppoint: bool = False
    gmin_s: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.vdd,
            self.temperature_c,
            self.cload,
            self.input_voltage,
            self.input_step_v,
            self.sine_amplitude_v,
            self.sine_frequency_hz,
            self.clock_period_s,
            self.clock_high_time_s,
            self.clock_transition_time_s,
            self.clock_delay_s,
            self.clock_skew_s,
            self.dac_step_v,
            self.waveform_sample_interval_s,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("sampler testbench values must be finite")
        if not 0.0 < float(self.clock_high_time_s) < float(self.clock_period_s):
            raise ValueError("sampler clock high time must lie inside one period")
        if float(self.clock_transition_time_s) <= 0.0 or float(self.clock_delay_s) < 0.0:
            raise ValueError("sampler clock transition must be positive and delay non-negative")
        if float(self.clock_skew_s) < 0.0:
            raise ValueError("sampler clock skew must be non-negative")
        if float(self.vdd) <= 0 or float(self.cload) <= 0 or float(self.waveform_sample_interval_s) <= 0:
            raise ValueError("sampler supply, load and waveform spacing must be positive")
        if float(self.input_step_v) < 0 or self.periods <= 0:
            raise ValueError("sampler input step must be non-negative and the periods positive")
        if self.stimulus is Stimulus.SINE and (self.sine_amplitude_v <= 0 or self.sine_frequency_hz <= 0):
            raise ValueError("a sine's amplitude and frequency must be positive")
        if self.gmin_s is not None and not 0.0 < float(self.gmin_s) < 1e-9:
            raise ValueError("sampler gmin must be positive and below 1 nS")

    @property
    def stop_s(self) -> float:
        """The run's length: every period."""
        return self.periods * float(self.clock_period_s)
