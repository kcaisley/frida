"""The sampling switch's parameters: its design (``Params``), one run of its testbench (``TbParams``),
and the benches every switch is characterized on.

Every switch is characterized the same way, so that switches compare: into ``LOAD_F`` (about the
CDAC it samples onto) at a ``LEVEL_PERIOD_S`` clock (``LEVEL_TRACK_S`` tracking, ``TRANSITION_S``
edges; a run's own defaults are the plain ``PERIOD_S`` and ``TRACK_S``), its input stepping by
``SMALL_STEP`` of the supply onto its level in the middle of each track phase (the settled
switch's time constant) and off it in the middle of each hold phase, ``PERIODS`` periods, Spectre's output every ``STROBE_S``; over the input level (``VIN_SWEEP``, fractions of the supply, and the supply
less half the step, ``VIN_TOP``, the top of the ADC's swing) and over the supply (``SUPPLY_SWEEP``,
fractions of its own) at the nominal input (``NOMINAL_VIN`` of the nominal supply); at the process
corners and the hot temperature (``HOT_C``); at the ADC's timing (``ADC_TRACK_S``,
``ADC_PERIOD_S``, ``ADC_PERIODS`` periods, its output every ``ADC_STROBE_S``): its acquisition of a
full-scale step (``ADC_FULL_SCALE``, at the nominal and the highest supply), its droop over the hold, a sine of the ADC's swing (``ADC_CM``,
``SINE_AMPLITUDE``, ``SINE_SAMPLES`` samples, tones ``SINE_CYCLES``) and its held output stepped as
the ADC's first decision steps it, at the lowest level a side reaches (``VIN_BOTTOM``) and at the
common mode; its complementary clock an edge late.

The behavioral model (``flow.samp.model``) derives the switch's triode conductances from its sizing
with the rough device constants here (``W_MIN_UM`` to ``PMOS_K_A_PER_V2``); a bootstrapped switch's
boost capacitor and bottom-plate switch are sized together (``_bootstrapped``) from the unit
capacitances (``GATE_F`` to ``BOTTOM_F``) and the load, and ``valid`` admits a bootstrapped design
that meets the sizing's conditions.
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
    are FRIDA-1's fabricated sampler, a transmission gate of 32 units a side. The bootstrap's helpers,
    capacitor and bottom-plate switch (``boot_w``, ``cap_w``, ``cap_l``, ``bot_l``) size only a
    ``SwitchType.BOOTSTRAP``."""

    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.TGATE)
    mos_w = h.Param(dtype=PositiveInt, desc="Width multiplier (x Wmin)", default=32)
    mos_l = h.Param(dtype=PositiveInt, desc="Length multiplier (x Lmin)", default=1)
    mos_vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)
    dummy = h.Param(dtype=bool, desc="Half-size dummies on vout, clocked opposite their switch", default=False)
    boot_w = h.Param(dtype=PositiveInt, desc="Bootstrap helper device width multiplier", default=4)
    cap_w = h.Param(dtype=PositiveInt, desc="Bootstrap MOS capacitor width multiplier", default=16)
    cap_l = h.Param(dtype=PositiveInt, desc="Bootstrap MOS capacitor length multiplier", default=8)
    bot_l = h.Param(dtype=PositiveInt, desc="Bootstrap bottom-plate switch length multiplier", default=1)

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
# not in the reference texts: the level runs' clock, tracking twice the bench's time before the
# same hold: T_track = 2 TRACK_S, T = PERIOD_S + TRACK_S, so that the input's step in the middle of
# the track phase leaves the bench's own TRACK_S to read the time constant over (a tau up to half
# of it reaches its second e-fold) after as long for the gate drive to settle
# Terms: T_track the clock's high time, T its period, of the level, supply, corner and skew runs.
# Holds for: a gate drive settled within TRACK_S of the clock's rise (flow.samp.analysis._settled_s).
LEVEL_TRACK_S = 2 * TRACK_S
LEVEL_PERIOD_S = PERIOD_S + TRACK_S
TRANSITION_S = 50e-12
PERIODS = 6
STROBE_S = 5e-12
# the input over 1/12 to 11/12 of the supply, its middle the nominal point, and the transients the
# record keeps for the viewer (the lowest, the middle and the highest input)
VIN_SWEEP = tuple(step / 12 for step in range(1, 12))
NOMINAL_VIN = 0.5
WAVE_VIN = (VIN_SWEEP[0], NOMINAL_VIN, VIN_SWEEP[-1])
# [Razavi-ADC] Example 3.6, p. 28: R_on read with a small (10 mV) difference across the switch
# Terms: the difference is the level runs' input step, SMALL_STEP of the supply (10 mV of 1.2 V),
#   onto the level in mid-track and off it in mid-hold (flow.samp.sim.testbench).
# Ours against the source: the source holds the difference still and reads V/I; ours steps it and
#   reads the output's time constant into the load (flow.samp.analysis.analyze_track).
# Holds for: a step small against the on-resistance's change over the input, so that a level's
#   resistance is the resistance at that level.
SMALL_STEP = 1 / 120
# not in the reference texts: the highest and lowest input level of the level runs, from flow.adc's
# runs: its 0.7 V common mode of 1.2 V (flow.adc.params.TbParams.vin_cm) and its sawtooth of 1.05
# times the full scale (flow.adc.sim.behavioral_testbenches), which reaches 1.19 V a side
# Terms: VIN_TOP the supply less half the level runs' step (that run steps half as far, so its
#   input reaches the supply and no further); ADC_CM the common mode over the supply; VIN_BOTTOM
#   as far below the common mode as VIN_TOP is above it.
# Holds for: flow.adc's default converter at its kit's nominal supply; fractions of the supply here.
VIN_TOP = 1 - SMALL_STEP / 2
ADC_CM = 7 / 12
VIN_BOTTOM = 2 * ADC_CM - VIN_TOP
# not in the reference texts: the supply corners, 90 and 110 % of the kit's nominal supply besides
# the nominal one, the input at its nominal level
# Terms: the factors of the bench's vdd over the kit's nominal supply.
# Holds for: every kit: never past the models' limits (a kit's device models may warn above 110 %);
#   the largest is the stress limit's corner (flow.circuit.oppoint.SUPPLY_CORNER_MAX).
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# not in the reference texts: the hot corner, 125 C (the usual upper junction temperature of a
# kit's models), where leakage and the on-resistance are largest
# Terms: the temperature of the ``hot``, ``droop_hot`` and DAC runs (flow.samp.runs.testbenches).
# Holds for: a kit whose models reach 125 C.
HOT_C = 125.0
# not in the reference texts: the ADC's sampling, from flow.adc.params: 20 symbols tracking of a
# 160-symbol conversion at 1.6 GHz, T_track = 20 / 1.6 GHz, T = 160 / 1.6 GHz (a sample every
# 100 ns, f_s = 10 MS/s)
# Terms: the symbol rate flow.adc.params.TbParams.symbol_rate; the symbols its default recipe's
#   SAMP row (20 high) and length (160).
# Holds for: flow.adc's default recipe; the runs three conversions long (the first starts from the
#   operating point), their output every 50 ps.
ADC_TRACK_S = 12.5e-9
ADC_PERIOD_S = 100e-9
ADC_PERIODS = 3
ADC_STROBE_S = 50e-12
# not in the reference texts: the ADC's full scale a side over the supply, from flow.adc: its
# default 12-bit converter's differential full scale of +-0.94 V at 1.2 V
# (flow.adc.sim._Converter.full_scale_v) is +-0.47 V on each side about the common mode
# Terms: 0.47 V a side's full-scale amplitude, 1.2 V the supply it is stated at.
# Holds for: flow.adc's default array (flow.capdac.Params()); the full-scale step's levels are
#   ADC_CM -+ ADC_FULL_SCALE of the supply (flow.samp.runs.testbenches).
ADC_FULL_SCALE = 0.47 / 1.2
# not in the reference texts: Spectre's gmin for the runs that read a hold's leakage (the droop):
# its default, 1e-12 S across every junction and channel, draws I = gmin V = 1e-12 S x 0.6 V =
# 0.6 pA from a held 0.6 V
# Terms: V the held output (vout), gmin the simulator's shunt across MN's and MP's junctions.
# Holds for: the droop and DAC runs (flow.samp.runs.testbenches), which run at this gmin instead.
LEAKAGE_GMIN_S = 1e-18
# not in the reference texts: the fraction of its track-end value within which a switch's
# gate-source voltage counts as settled (flow.samp.analysis.analyze_track): the on-resistance of a
# device in deep triode goes as 1 / (V_GS - V_TH) ([Razavi-Analog] Eq. (2.11), p. 15), so 2 % of
# V_GS is under 4 % of R_on at an overdrive above half of V_GS
# Terms: V_GS the saved gate (a bootstrap's ``gate``, else the clock) over vin.
# Ours against the source: the level runs' step (SMALL_STEP of the supply, under 1 % of a boosted
#   V_GS) moves a bootstrap's V_GS by up to its own size until the bottom plate has followed
#   ([Razavi-ADC] Sec. 3.8.3, p. 51: the bootstrapping path's bandwidth); the band holds that.
# Holds for: an overdrive above half of V_GS as tracking ends.
VGS_SETTLED = 0.02
# not in the reference texts: the least share of its largest value the track error may still have
# where the gate drive settles, e^-4, for a time constant to be read from there: below it the
# output had settled before the gate drive did, and what is left follows the gate's own settling
# Terms: the track error |vout - vin| of flow.samp.analysis.analyze_track, its largest in the phase.
# Holds for: the level runs' step and the simulator's tolerances (errors of microvolts and above).
ERROR_SETTLED = math.exp(-4)
# [Razavi-ADC] Eq. (3.81), p. 54: acquisition to half an LSB, V_FS / 2^(N+1), at these resolutions N
# Terms: V_FS taken as the supply (flow.samp.analysis.analyze_acquisition); N in bits.
# Holds for: the resolutions flow.adc's converters come in (10, 12 and 14 bits).
ACQUISITION_BITS = (10, 12, 14)
# not in the reference texts: a sine of the ADC's swing a side, a fraction of the supply: its full
# scale 0.5 dB below, ADC_FULL_SCALE x 10^(-0.5/20) (0.44 V of 1.2 V), about its common mode
# Terms: flow.adc's sine (flow.adc.sim.behavioral_testbenches: amplitude_v).
# Holds for: SINE_SAMPLES samples at the ADC's timing, SINE_CYCLES cycles in them (a low tone and
#   one near Nyquist).
SINE_AMPLITUDE = 0.37
SINE_SAMPLES = 32
SINE_CYCLES = (1, 15)
# not in the reference texts: rough 65-nm device constants, for the behavioral model's triode
# conductances from the switch's sizing where none is given (flow.samp.model.Model.conductances)
# Terms: W_MIN_UM and L_MIN_UM the width and the length one size unit stands for; k' = mu C_ox of
#   each device type ([Razavi-ADC] Eq. (3.23), p. 27).
# Holds for: a rough estimate only; a characterized switch does not use them.
W_MIN_UM = 0.12
L_MIN_UM = 0.06
NMOS_K_A_PER_V2 = 300e-6
PMOS_K_A_PER_V2 = 100e-6
# not in the reference texts: rough 65-nm unit capacitances, the parameters of a bootstrap's sizing
# (``_bootstrapped``) beside its load: a gate's per unit area (a unit of width by a unit of length:
# 12 fF/um2 x W_MIN_UM x L_MIN_UM), a gate's overlap of its source or its drain per unit width
# (0.3 fF/um), a source's or drain's junction per unit width (0.25 fF/um), and the boost
# capacitor's channel to the substrate per unit area (a tenth of its gate's)
# Terms: C_ox W L and W C_ov of [Razavi-ADC] Eq. (3.69), p. 49, per size unit; C_DB of its C_p.
# Holds for: a kit whose unit capacitances lie near these; another kit's sizes follow from its own.
GATE_F = 86e-18
OVERLAP_F = 36e-18
JUNCTION_F = 30e-18
BOTTOM_F = 8.6e-18
# not in the reference texts: a bootstrap's helpers against its helper width (boot_w), own choices
# Terms: the precharge device Mpre PRECHARGE_W helpers wide (it holds boot_top at vdd while the gate
#   charges from it); the boost capacitor Mcap BOOST_CAP_L units long.
# Holds for: the bootstrapped switch as flow.samp.subckt.netlist builds it; ``_boosted_f`` counts
#   Mpre's share of the boosted nodes' load by PRECHARGE_W.
PRECHARGE_W = 8
BOOST_CAP_L = 16
# [Razavi-ADC] Eq. (3.70), p. 50: V_b' = C_b / (C_b + C_G1 + C_G2 + C_p) V_DD, held at 0.9 V_DD or more
# Terms: BOOST_MIN the least V_b' / V_DD; C_b, C_G1, C_G2 and C_p as ``_boost_f`` and
#   ``_boosted_f`` count them.
# Ours against the source: the count leaves out the n-wells of Mgate and Mpre on the top plate and
#   the wiring; BOOST_UNCOUNTED of the counted load again stands for them.
# Holds for: every bootstrapped design ``valid`` admits, at every input level of the level runs.
BOOST_MIN = 0.9
BOOST_UNCOUNTED = 1 / 3
# not in the reference texts: own derivation, from the square law ([Razavi-Analog] Eq. (2.8), p. 14)
# at one gate drive: the bottom plate (Q) rises no faster than the switch moves its output where
# I_2 / C_Q <= I_1 / C_L, the currents of Mbot_in and MN at V_GS = V_b', so with I going as W / L
# (W / L)_2 / C_Q <= (W / L)_1 / (BOTTOM_LIFT C_L): L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q
# Terms: M1 MN (mos_w by mos_l), M2 Mbot_in (boot_w by bot_l), C_Q the bottom plate's capacitance to
#   the substrate (``_bottom_f``), C_L the load on vout; BOTTOM_LIFT the long Mbot_in's current a
#   square over the minimum-length MN's, whose carriers' velocity saturates.
# Ours against the source: the square law has no velocity saturation; BOTTOM_LIFT of 2 stands for it.
# Holds for: the load the design is sized for (LOAD_F unless given) or a larger one; a smaller load
#   lets the gate lead the output again.
BOTTOM_LIFT = 2.0
# not in the reference texts: the largest gate of the bottom-plate switch over the switch's own,
# C_G2 <= BOTTOM_GATE_MAX C_G1: past it the boost circuit outgrows the switch it boosts and its
# gate's fall as holding starts couples the bottom plate below 0 V through C_G2
# Terms: C_G1 MN's gate, C_G2 Mbot_in's gate (``_gate_f`` of each).
# Holds for: stated as ``valid``'s condition; a narrower switch than it admits has no bootstrap.
BOTTOM_GATE_MAX = 2.0


def _gate_f(width: int, length: int, *, gate_f: float = GATE_F, overlap_f: float = OVERLAP_F) -> float:
    """A gate's capacitance while its channel is on: ``width`` by ``length`` size units."""
    # [Razavi-ADC] Eq. (3.69), p. 49: C_G = (W L) C_ox + 2 W C_ov of a device in deep triode
    # Terms: W, L ``width`` and ``length`` in size units; C_ox W L a unit ``gate_f``; C_ov W a unit
    #   ``overlap_f``.
    # Holds for: MN and Mbot_in while tracking (their channels on); Mcap, its channel inverted.
    return width * (length * gate_f + 2 * overlap_f)


def _boost_f(params: Params, *, gate_f: float = GATE_F, overlap_f: float = OVERLAP_F) -> float:
    """A bootstrap's boost capacitor C_b: Mcap's gate over its channel."""
    # [Razavi-ADC] Eq. (3.70), p. 50: C_b, here a MOS capacitor's gate, (W L) C_ox + 2 W C_ov
    # Terms: Mcap, cap_w by cap_l, its gate boot_top (P), its channel, source and drain boot_bot (Q).
    # Holds for: Mcap inverted, its gate a supply above its channel (hold and track alike).
    return _gate_f(params.cap_w, params.cap_l, gate_f=gate_f, overlap_f=overlap_f)


def _boosted_f(
    params: Params, *, gate_f: float = GATE_F, overlap_f: float = OVERLAP_F, junction_f: float = JUNCTION_F
) -> float:
    """What a bootstrap's boost capacitor shares its charge with while tracking: the capacitance on
    the boosted nodes (``gate`` and ``boot_top``, joined by Mgate) that the count holds."""
    # [Razavi-ADC] Eq. (3.69), p. 49 and Fig. 3.45, p. 50: C_G1 + C_G2 + C_p on the boosted node
    # Terms, from the netlist (flow.samp.subckt.netlist): C_G1 MN's gate; C_G2 Mbot_in's gate;
    #   C_p the rest on ``gate`` and ``boot_top``: Mpre's gate over its drain on vdd (its channel is
    #   off, its source and well on boot_top) and Mgate_top's drain junction to the substrate.
    # Ours against the source: the source's C_p has M3's and M5's junctions, which ours ties to
    #   wells on boot_top (no charge), and M7's drain, ours Mgate_top's; the source's M5 has its
    #   gate on the boosted node too and leaves it out, ours counts its overlap of vdd. Mgate's gate
    #   (gate_ctl) follows the bottom plate, so its gate capacitance adds to C_b, not to the load.
    #   Mpre conducts until the gate is a threshold below the supply, so part of this charge comes
    #   from the supply: the count bounds the loss from above.
    # Holds for: tracking, the gate settled; the n-wells on boot_top and the wiring are not counted
    #   (BOOST_UNCOUNTED).
    switch = _gate_f(params.mos_w, params.mos_l, gate_f=gate_f, overlap_f=overlap_f)
    bottom = _gate_f(params.boot_w, params.bot_l, gate_f=gate_f, overlap_f=overlap_f)
    rest = PRECHARGE_W * params.boot_w * overlap_f + params.boot_w * junction_f
    return switch + bottom + rest


def _bottom_f(params: Params, *, bottom_f: float = BOTTOM_F, junction_f: float = JUNCTION_F) -> float:
    """What a bootstrap's bottom-plate switch charges as the bottom plate rises: the capacitance of
    ``boot_bot`` (Q) to the substrate."""
    # not in the reference texts: own count from the netlist (flow.samp.subckt.netlist), C_Q =
    # (W L)_cap C_bottom + 2 W_cap C_j + 3 W_helper C_j
    # Terms: Mcap's channel to the substrate (cap_w by cap_l) and its source's and drain's
    #   junctions (each cap_w wide); the junctions of Mbot's and Mbot_in's drains and Mctl_on's
    #   drain on boot_bot (each boot_w wide).
    # Ours against the source: [Razavi-ADC] Example 3.22, p. 51 names the capacitor's parasitic as
    #   what the input must drive, without a value.
    # Holds for: a MOS boost capacitor whose channel is its bottom plate.
    return params.cap_w * params.cap_l * bottom_f + (2 * params.cap_w + 3 * params.boot_w) * junction_f


def _bottom_length(
    params: Params, load_f: float, *, bottom_f: float = BOTTOM_F, junction_f: float = JUNCTION_F
) -> float:
    """The least length of a bootstrap's bottom-plate switch (Mbot_in), in units, at which the
    bottom plate rises no faster than the switch moves its output into ``load_f`` (``BOTTOM_LIFT``)."""
    # not in the reference texts: L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q (BOTTOM_LIFT's
    # derivation)
    # Terms: W_2 boot_w, L_1 mos_l, W_1 mos_w, C_L ``load_f``, C_Q ``_bottom_f``.
    # Holds for: ``load_f`` or a larger load on vout.
    bottom = _bottom_f(params, bottom_f=bottom_f, junction_f=junction_f)
    return BOTTOM_LIFT * params.boot_w * params.mos_l / params.mos_w * load_f / bottom


def _bootstrapped(
    mos_w: int,
    mos_l: int = 1,
    *,
    load_f: float = LOAD_F,
    gate_f: float = GATE_F,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
    bottom_f: float = BOTTOM_F,
) -> Params:
    """The bootstrapped NMOS switch ``mos_w`` by ``mos_l``, sized for ``load_f`` on its output with
    a kit's unit capacitances (the rough ones here unless given): its helpers an eighth of the
    switch, none under 4 units (the finest PDK's minimum width); its boost capacitor and its
    bottom-plate switch's length solved together, the shortest bottom-plate switch whose gate the
    capacitor still boosts to ``BOOST_MIN``."""
    # [Razavi-ADC] Eq. (3.70), p. 50, solved for C_b: C_b >= BOOST_MIN / (1 - BOOST_MIN)
    # (1 + BOOST_UNCOUNTED) (C_G1 + C_G2 + C_p), with L_2 >= ``_bottom_length``
    # Terms: C_b ``_boost_f`` (cap_w by BOOST_CAP_L); C_G1 + C_G2 + C_p ``_boosted_f``, in which
    #   C_G2 grows with Mbot_in's length bot_l; C_Q ``_bottom_f`` grows with the capacitor.
    # Ours against the source: the source sizes C_b alone; ours has a long M2 whose gate loads the
    #   capacitor and whose length the capacitor's own bottom plate sets, so the two are solved
    #   together: the first bot_l, counting up, that the capacitor sized for it admits.
    # Holds for: ``load_f`` or more on vout; a design ``valid`` admits (BOTTOM_GATE_MAX).
    # not in the reference texts: the helpers an eighth of the switch's width, none under 4 units
    # Terms: boot_w, the width of Mbot, Mbot_in, Mgate, Mgate_cas, Mgate_off and the Mctl devices.
    # Holds for: a finest PDK whose minimum width is 4 units.
    boot_w = max(4, mos_w // 8)
    for bot_l in range(1, 4096):
        sized = Params(switch_type=SwitchType.BOOTSTRAP, mos_w=mos_w, mos_l=mos_l, boot_w=boot_w, bot_l=bot_l)
        load = _boosted_f(sized, gate_f=gate_f, overlap_f=overlap_f, junction_f=junction_f)
        least = BOOST_MIN / (1 - BOOST_MIN) * (1 + BOOST_UNCOUNTED) * load
        cap_w = math.ceil(least / _gate_f(1, BOOST_CAP_L, gate_f=gate_f, overlap_f=overlap_f))
        sized = Params(
            switch_type=SwitchType.BOOTSTRAP,
            mos_w=mos_w,
            mos_l=mos_l,
            boot_w=boot_w,
            cap_w=cap_w,
            cap_l=BOOST_CAP_L,
            bot_l=bot_l,
        )
        if _bottom_length(sized, load_f, bottom_f=bottom_f, junction_f=junction_f) <= bot_l:
            return sized
    raise ValueError(f"no bottom-plate switch under 4096 units lifts a {mos_w} by {mos_l} switch's bottom plate")


def valid(params: Params, pdk: str) -> bool:
    """Whether ``params`` is a design in ``pdk``: every plain switch; a bootstrapped one whose boost
    capacitor holds V_b' at ``BOOST_MIN`` of the supply or more, whose bottom-plate switch is long
    enough for the bench's load (``LOAD_F``) and whose gate is no more than ``BOTTOM_GATE_MAX``
    times the switch's own (the rough unit capacitances here, in every PDK)."""
    if params.switch_type is not SwitchType.BOOTSTRAP:
        return True
    # [Razavi-ADC] Eq. (3.70), p. 50: C_b >= BOOST_MIN / (1 - BOOST_MIN) (1 + BOOST_UNCOUNTED) (C_G1 + C_G2 + C_p)
    # Terms: C_b ``_boost_f`` (Mcap); C_G1 + C_G2 + C_p ``_boosted_f`` (MN's and Mbot_in's gates, Mpre's
    #   gate over vdd, Mgate_top's drain).
    # Holds for: the unit capacitances here (GATE_F to BOTTOM_F), the same in every PDK.
    boosted = _boost_f(params) >= BOOST_MIN / (1 - BOOST_MIN) * (1 + BOOST_UNCOUNTED) * _boosted_f(params)
    # not in the reference texts: L_2 at least ``_bottom_length`` at the bench's load, and
    # C_G2 <= BOTTOM_GATE_MAX C_G1 (the constants' derivations)
    # Terms: L_2 bot_l (Mbot_in's length); C_G1, C_G2 ``_gate_f`` of MN and of Mbot_in.
    # Holds for: the bench's load LOAD_F on vout; a design sized for a larger load is admitted too.
    lifted = params.bot_l >= _bottom_length(params, LOAD_F)
    bounded = _gate_f(params.boot_w, params.bot_l) <= BOTTOM_GATE_MAX * _gate_f(params.mos_w, params.mos_l)
    return boosted and lifted and bounded


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the sampler's testbench (flow.samp.sim.testbench): the switch ``params`` in ``pdk``
    at supply ``vdd``, process ``corner`` and ``temperature_c`` into ``cload``; its input at
    ``input_voltage`` or, with an ``input_step_v``, stepping by it once a period in the middle of
    each hold phase (over ``input_transition_time_s`` where given, else a clock edge's time) and,
    with a ``track_step_v``, by that once a period in the middle of each track phase (with both
    equal, every track phase ends on ``input_voltage``, reached from below and from above in
    turn), or (``stimulus`` SINE) a sine about ``input_voltage`` of ``sine_amplitude_v``
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
    input_transition_time_s: float | None = None
    track_step_v: float = 0.0
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
            self.track_step_v,
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
        if float(self.input_step_v) < 0 or float(self.track_step_v) < 0 or self.periods <= 0:
            raise ValueError("sampler input steps must be non-negative and the periods positive")
        hold = float(self.clock_period_s) - float(self.clock_high_time_s)
        if self.input_transition_time_s is not None and not 0.0 < float(self.input_transition_time_s) < hold:
            raise ValueError("sampler input transition must be positive and shorter than the hold phase")
        if self.stimulus is Stimulus.SINE and (self.sine_amplitude_v <= 0 or self.sine_frequency_hz <= 0):
            raise ValueError("a sine's amplitude and frequency must be positive")
        if self.gmin_s is not None and not 0.0 < float(self.gmin_s) < 1e-9:
            raise ValueError("sampler gmin must be positive and below 1 nS")

    @property
    def stop_s(self) -> float:
        """The run's length: every period."""
        return self.periods * float(self.clock_period_s)
