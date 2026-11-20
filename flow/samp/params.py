"""The sampling switch's parameters: its design (``Params``), one run of its testbench (``TbParams``),
and the benches every switch is characterized on.

Every switch is characterized the same way, so that switches compare: into ``LOAD_F`` (about the
CDAC it samples onto) at a ``LEVEL_PERIOD_S`` clock (``LEVEL_TRACK_S`` tracking, ``TRANSITION_S``
edges; a run's own defaults are the plain ``PERIOD_S`` and ``TRACK_S``), its input stepping by
``SMALL_STEP`` of the supply onto its level a ``TRACK_S`` before each track phase ends (the settled
switch's time constant) and off it in the middle of each hold phase, ``PERIODS`` periods, Spectre's
output every ``STROBE_S``; over the input level (``VIN_SWEEP``, fractions of the supply, and the
supply less half the step, ``VIN_TOP``, the top of the ADC's swing) and over the supply
(``SUPPLY_SWEEP``, fractions of its own) at the nominal input (``NOMINAL_VIN`` of the nominal
supply); at the process corners and the hot temperature (``HOT_C``); at the ADC's timing
(``ADC_TRACK_S``, ``ADC_PERIOD_S``, ``ADC_PERIODS`` periods, its output every ``ADC_STROBE_S``): its
acquisition of a full-scale step (``ADC_FULL_SCALE``, at the nominal and the highest supply), its
droop over the hold, a sine of the ADC's swing (``ADC_CM``, ``SINE_AMPLITUDE``, ``SINE_SAMPLES``
samples, tones ``SINE_CYCLES``) and its held output stepped as the ADC's first decision steps it, at
the lowest level a side reaches (``VIN_BOTTOM``) and at the common mode; its complementary clock an
edge late.

The behavioral model (``flow.samp.model``) derives the switch's triode conductances from its sizing
with the rough device constants here (``W_MIN_UM`` to ``PMOS_K_A_PER_V2``); a bootstrapped switch's
boost capacitor and bottom-plate switch are sized together (``_bootstrapped``) from the unit
capacitances (``GATE_F`` to ``BOTTOM_F``), the long device's current a square over the short one's
(``BOTTOM_LIFT``) and the load, and ``valid`` admits a bootstrapped design that meets the sizing's
conditions.
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
        # not in the reference texts: a dummy is half its switch in whole units, mos_w // 2 >= 1
        # Terms: mos_w MN's (MP's) width; the dummy's flow.samp.subckt.netlist's ``half``.
        # Holds for: a switch of two units or more ([Razavi-ADC] Sec. 3.7, p. 42: W_3 = 0.5 W_1).
        if self.dummy and self.mos_w < 2:
            raise ValueError("a dummy is half its switch: the switch needs at least 2 width units")


pipeline.Params.register(Params)


FRIDA1 = Params()  # the fabricated FRIDA-1 sampler: transmission gate, 32 units each

# not in the reference texts: the bench's load, 1 pF on vout, a round value above the array it
# samples onto: flow.adc's default array (flow.capdac.Params()) loads a side with 0.74 pF, its
# main and difference plates (capdac.Model.plates_f)
# Terms: C_H of [Razavi-Analog] Eq. (13.31), p. 552 and C_1 of [Razavi-ADC] Eq. (3.26), p. 29: the
#   bench's ``cload`` on vout (TbParams.cload).
# Ours against the source: none; a round value, not the array's own.
# Holds for: the record's figures as stated into 1 pF. The on-resistance does not depend on it; the
#   time constant, the bandwidth, the pedestal and the droop do (flow.samp.model rescales the
#   pedestal to the load it is given and computes kT/C for it); a bootstrap is sized for it and
#   holds for it or a smaller load (``_bottom_length``).
LOAD_F = 1e-12
# not in the reference texts: the bench's plain clock and output, own choices: a 10 ns period,
# half of it tracking; clock edges of 50 ps (a 65-nm inverter's edge into a few gates); six
# periods, the first left out of every figure; Spectre's output every 5 ps
# Terms: T ``PERIOD_S``, the clock's high time ``TRACK_S`` (the track phase between the clock's
#   mid-supply crossings is its high time and one edge; the hold between the clock's edges
#   T - TRACK_S - 2 TRANSITION_S), the edge ``TRANSITION_S`` (rise and fall alike, the input's step
#   too unless a run gives its own), ``PERIODS`` periods, the output every ``STROBE_S``.
# Ours against the source: none (a bench's timing).
# Holds for: an exponential error's time constant read to within 2.2 % from two output intervals
#   (10 ps) on and 1.1 % from three (15 ps) on (own derivation: the window's start and its e-fold
#   are interpolated linearly between samples, flow.samp.analysis.analyze_track, and an
#   exponential is convex between them; the worst over where the two fall between samples), one
#   up to TRACK_S / 2 read at all; an error that is not one exponential over the window reads its
#   two-point e-fold, which a log-linear fit over the same window may differ from by a few per
#   cent at the shortest time constants; a run gives its own timing where it differs (the level
#   runs' below, the ADC's).
PERIOD_S = 10e-9
TRACK_S = 5e-9
# not in the reference texts: the level runs' clock, tracking four times the bench's time before
# the same hold: T_track = 4 TRACK_S, T = T_track + PERIOD_S - TRACK_S, the input's step in the
# track phase TRACK_S before it ends (flow.samp.runs.testbenches: TbParams.track_step_s), so that
# the step leaves the bench's own TRACK_S to read the time constant over (a tau up to half of it
# reaches its second e-fold) after three times as long for the gate drive to settle
# Terms: T_track the clock's high time, T its period, of the level, supply, corner and skew runs;
#   the hold, T - T_track, the plain bench's.
# Ours against the source: none (a bench's timing). A bootstrap's gate drive settles as its bottom
#   plate reaches the input through the long bottom-plate switch (``_bottom_length``), sized with
#   the 65-nm units in every kit: slower in a kit with larger unit capacitances.
# Holds for: a gate drive settled within 3 TRACK_S of the clock's rise
#   (flow.samp.analysis._settled_s); a level where it is not has no time constant (NaN).
LEVEL_TRACK_S = 4 * TRACK_S
LEVEL_PERIOD_S = LEVEL_TRACK_S + PERIOD_S - TRACK_S
TRANSITION_S = 50e-12
PERIODS = 6
STROBE_S = 5e-12
# not in the reference texts: the level runs' input levels, 1/12 to 11/12 of the supply in twelfths
# (VIN_TOP below is the twelfth), and the nominal one, mid-supply, where a transmission gate's
# on-resistance is near its largest ([Razavi-Analog] Fig. 13.17(b), p. 549); the transients the
# record keeps for the viewer are the lowest, the nominal and the highest of them
# Terms: fractions of the bench's supply; the level a run's every track phase ends on
#   (TbParams.input_voltage).
# Ours against the source: none (a bench's grid).
# Holds for: every "at the nominal input" figure (ron_ohm, bandwidth_hz, pedestal_v,
#   energy_per_cycle_j, the supply and corner runs) is at half the supply, a twelfth of the supply
#   below the ADC's common mode (ADC_CM).
VIN_SWEEP = tuple(step / 12 for step in range(1, 12))
NOMINAL_VIN = 0.5
WAVE_VIN = (VIN_SWEEP[0], NOMINAL_VIN, VIN_SWEEP[-1])
# [Razavi-ADC] Example 3.6, p. 28: R_on read with a small (10 mV) difference across the switch
# Terms: the difference is the level runs' input step, SMALL_STEP of the supply (10 mV of 1.2 V),
#   onto the level inside the track phase (TbParams.track_step_s) and off it in mid-hold (flow.samp.sim.testbench), the hold step
#   no faster than the converter's input (flow.samp.runs.testbenches).
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
# kit's models), where a single device's leakage and an NMOS or bootstrapped switch's
# on-resistance are largest
# Terms: the temperature of the ``hot``, ``droop_hot`` and DAC runs (flow.samp.runs.testbenches).
# Ours against the source: none.
# Holds for: a kit whose models reach 125 C. A transmission gate's on-resistance near mid-supply
#   is set by the slow corner, not by the temperature (the two devices' thresholds fall as their
#   mobilities do), and the droop of a switch with dummies, whose gates' currents oppose its
#   junctions', need not be largest hot.
HOT_C = 125.0
# not in the reference texts: the ADC's sampling, from flow.adc.params: 20 symbols tracking of a
# 160-symbol conversion at 1.6 GHz, T_track = 20 / 1.6 GHz, T = 160 / 1.6 GHz (a sample every
# 100 ns, f_s = 10 MS/s)
# Terms: the symbol rate flow.adc.params.TbParams.symbol_rate; the symbols its default recipe's
#   SAMP row (20 high) and length (160).
# Ours against the source: none.
# Holds for: flow.adc's default recipe; the runs three conversions long (ADC_PERIODS: the first
#   starts from the operating point and is left out, two holds are read), their output every 50 ps
#   (ADC_STROBE_S: a held output and a sine of at most half the sample rate, straight lines over
#   an interval).
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
# not in the reference texts: Spectre's gmin for the characterization's runs, which read a hold's
# leakage (the droop) and the off switch's conduction (the feedthrough): its default, 1e-12 S
# across every junction and channel, draws I = gmin V = 1e-12 S x 0.6 V = 0.6 pA from a held
# 0.6 V, and across an off switch passes gmin Delta t / C_H = 1e-12 S x 2.5 ns / 1 pF = 2.5e-9 of
# an input step to the held output in 2.5 ns
# Terms: V the held output (vout), gmin the simulator's shunt across MN's and MP's junctions and
#   channels; Delta t the hold left after the input's step, C_H the load.
# Holds for: every run of flow.samp.runs.testbenches, which run at this gmin instead.
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
# Terms: V_FS the full scale a side, the full-scale step the run takes
#   (flow.samp.analysis.analyze_acquisition: tb.input_step_v); N in bits.
# Ours against the source: none.
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
# Ours against the source: the square law's k' alone: no mobility degradation, no rise of the
#   threshold with the source above the bulk, no source and drain resistance, each of which a
#   65-nm switch has (the readme's calibrations).
# Holds for: the size unit exactly; the conductances as a rough estimate only, the on-resistance
#   they give low against a simulated 65-nm switch's (the readme's calibrations). A
#   characterized switch does not use them.
W_MIN_UM = 0.12
L_MIN_UM = 0.06
NMOS_K_A_PER_V2 = 300e-6
PMOS_K_A_PER_V2 = 100e-6
# not in the reference texts: rough 65-nm unit capacitances, the parameters of a bootstrap's sizing
# (``_bootstrapped``) beside its load: a gate's per unit area (a unit of width by a unit of
# length: 13 fF/um2 x W_MIN_UM x L_MIN_UM), the part of a unit of length its channel is short of
# the drawn gate ([Razavi-Analog] Sec. 2.1.2, p. 8: L_eff = L_drawn - 2 L_D), a gate's overlap of
# its source or its drain per unit width (0.3 fF/um), a source's or drain's junction per unit
# width (0.25 fF/um), and the boost capacitor's channel to the substrate per unit area
# Terms: C_ox W L and W C_ov of [Razavi-ADC] Eq. (3.69), p. 49, per size unit (GATE_F, OVERLAP_F);
#   2 L_D GATE_SHORT of a unit of length; C_DB of the source's C_p per unit width (JUNCTION_F);
#   Mcap's channel to the substrate (BOTTOM_F).
# Ours against the source: one number each for capacitances that move with their bias: a
#   junction's and the channel-to-substrate's are means over a reverse bias from 0 V to the
#   supply, larger at 0 V and smaller at the supply.
# Holds for: a 65-nm kit, whose simulated gates, overlaps and junctions they stand for (the
#   readme's calibrations: how far each is off its simulated value). Every kit's
#   bootstrap is sized with these (``valid``): the boost ratio, C_b over its load, is a ratio of
#   like capacitances and carries over; the bottom-plate rule (``_bottom_length``) is in farads
#   and is calibrated on these alone, so in a kit with larger unit capacitances Mbot_in comes out
#   longer than its own rule asks.
GATE_F = 93e-18
GATE_SHORT = 0.28
OVERLAP_F = 36e-18
JUNCTION_F = 30e-18
BOTTOM_F = 8.6e-18
# not in the reference texts: a bootstrap's helpers against its helper width (boot_w), own choices
# Terms: the precharge device Mpre PRECHARGE_W helpers wide (it holds boot_top at vdd while the gate
#   charges from it); the boost capacitor Mcap BOOST_CAP_L units long.
# Ours against the source: [Razavi-ADC] Fig. 3.41(b), p. 48 sizes neither.
# Holds for: the bootstrapped switch as flow.samp.subckt.netlist builds it; ``_fixed_f`` counts
#   Mpre's share of the boosted nodes' load by PRECHARGE_W.
PRECHARGE_W = 8
BOOST_CAP_L = 16
# [Razavi-ADC] Eq. (3.70), p. 50: V_b' = C_b / (C_b + C_G1 + C_G2 + C_p) V_DD, held at 0.9 V_DD or more
# Terms: BOOST_MIN the least V_b' / V_DD; C_b ``_boost_f``; C_G1 + C_G2 + C_p ``_boosted_f``, every
#   device on the boosted nodes in the netlist.
# Ours against the source: the count holds devices only; BOOST_UNCOUNTED of it again stands for
#   what a layout adds, the n-wells of Mgate and Mpre on the top plate and the wiring.
# Holds for: every bootstrapped design ``valid`` admits, at every input level of the level runs,
#   on its parameters (a kit's fingering builds a width a few per cent off its parameter).
BOOST_MIN = 0.9
BOOST_UNCOUNTED = 1 / 3
# not in the reference texts: own derivation. While the bottom plate (Q) rises from 0 V to the
# input, A rides C_b's charge above it, A = Q + V_b', so MN's oxide at its output end carries
# A - vout = V_b' + (Q - vout): no more than V_b' while Q stays below vout. Q starts below it (0 V
# against the held output) and cannot pass it if, where Q = vout, it rises no faster. There Mbot_in
# and MN have the same gate, drain (vin) and source voltages, so with the drain current going as
# W / L ([Razavi-Analog] Eq. (2.8), p. 14), I_2 / C_Q <= I_1 / C_L is
# BOTTOM_LIFT (W / L)_2 / C_Q <= (W / L)_1 / C_L: L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q
# Terms: M1 MN (mos_w by mos_l), M2 Mbot_in (boot_w by bot_l), Q boot_bot, A gate; C_Q what Mbot_in
#   charges as Q rises (``_bottom_f``), C_L the load on vout; BOTTOM_LIFT the long Mbot_in's
#   current a square over the minimum-length MN's at one bias.
# Ours against the source: the square law gives both the same current a square. A minimum-length
#   MN's carriers' velocity saturates and its threshold is above a long device's, so it carries
#   less a square: BOTTOM_LIFT is the largest ratio of the two currents a square over the supply,
#   the corners and the temperature in a 65-nm kit, the 32-unit design's two devices at one bias
#   (the readme's calibrations). [Razavi-ADC]
#   Eq. (3.79), (3.80), p. 52 ask the opposite of this device, a small R_on2 + R_on3, so that V_GS
#   follows the input up to the bootstrapping path's zero: a long M2 trades that bandwidth for the
#   gate's rise.
# Holds for: the load the design is sized for (LOAD_F unless given) or a smaller one (a larger
#   load slows the output and lets the bottom plate pass it); a held output above 0 V (VIN_BOTTOM
#   of the supply or more in the ADC); an input far below the bootstrapping path's zero,
#   omega_z = 1 / (C_b (R_on2 + R_on3)) ([Razavi-ADC] Eq. (3.79), p. 52), R_on2 Mbot_in's and
#   R_on3 Mgate's resistance (above it V_GS no longer follows the input).
#   Before Q reaches vout its slope may be the larger: Mbot_in's source starts at 0 V and MN's at
#   the held output, so MN has the smaller gate drive until then.
BOTTOM_LIFT = 3.0
# not in the reference texts: the largest gate of the bottom-plate switch over the switch's own,
# C_G2 <= BOTTOM_GATE_MAX C_G1: past it the boost circuit outgrows the switch it boosts and its
# gate's fall as holding starts couples the bottom plate below 0 V through C_G2
# Terms: C_G1 MN's gate, C_G2 Mbot_in's gate (``_gate_f`` of each).
# Ours against the source: none (the source's M2 is a minimum-length device).
# Holds for: stated as ``valid``'s condition; a narrower switch than it admits has no bootstrap.
BOTTOM_GATE_MAX = 2.0


def _gate_f(
    width: int, length: int, *, gate_f: float = GATE_F, short: float = GATE_SHORT, overlap_f: float = OVERLAP_F
) -> float:
    """A gate's capacitance while its channel is on: ``width`` by ``length`` size units."""
    # [Razavi-ADC] Eq. (3.69), p. 49: C_G = (W L) C_ox + 2 W C_ov of a device in deep triode
    # Terms: W ``width`` in size units; L the channel's length, ``length`` less ``short`` of a unit
    #   ([Razavi-Analog] Sec. 2.1.2, p. 8: L_eff = L_drawn - 2 L_D); C_ox W L a unit ``gate_f``;
    #   C_ov W a unit ``overlap_f``.
    # Ours against the source: the source writes L for the channel's length; ours takes the
    #   drawn length in units and the side diffusion off it.
    # Holds for: MN, Mbot_in and Mgate while tracking (their channels on); Mcap, its channel
    #   inverted; a 65-nm kit's gates from one unit long to sixteen (the readme's calibrations).
    return width * ((length - short) * gate_f + 2 * overlap_f)


def _boost_f(
    params: Params, *, gate_f: float = GATE_F, short: float = GATE_SHORT, overlap_f: float = OVERLAP_F
) -> float:
    """A bootstrap's boost capacitor C_b: Mcap's gate over its channel."""
    # [Razavi-ADC] Eq. (3.70), p. 50: C_b, here a MOS capacitor's gate, (W L) C_ox + 2 W C_ov
    # Terms: Mcap, cap_w by cap_l, its gate boot_top (P), its channel, source and drain boot_bot (Q).
    # Ours against the source: the source's C_b is a plain capacitor; ours a transistor's gate,
    #   whose channel to the substrate loads the bottom plate (``_bottom_f``).
    # Holds for: Mcap inverted, its gate V_b' or more above its channel (hold and track alike).
    return _gate_f(params.cap_w, params.cap_l, gate_f=gate_f, short=short, overlap_f=overlap_f)


def _fixed_f(
    params: Params,
    *,
    gate_f: float = GATE_F,
    short: float = GATE_SHORT,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
) -> float:
    """A bootstrap's C_p: the capacitance of the boosted nodes (``gate`` and ``boot_top``) to
    nodes that do not move with the bottom plate, and of the pull-down stack's nodes, which
    charge from ``gate``."""
    # [Razavi-ADC] Fig. 3.45, p. 50: C_p, the parasitics at the boosted nodes P and A, C_DB5 +
    # C_DB3 + C_SB3 + C_GD7 + C_DB7 of the source's devices (its C_GS3 + C_GD3: ``_boosted_f``)
    # Terms, from the netlist (flow.samp.subckt.netlist), each a helper (boot_w) wide unless said:
    #   - Mpre (M5, PRECHARGE_W helpers): its gate (on ``gate``) over its drain on vdd, and its
    #     drain's junction to its well on boot_top (C_DB5);
    #   - Mgate_top (ours in M7's place): its drain's junction on ``gate`` (C_DB7);
    #   - the pull-down stack's nodes gate_top, gate_mid and gate_off, charged from ``gate``
    #     through Mgate_top as it rises: their ten junctions (Mgate_top's source; Mgate_drop's and
    #     Mgate_pass's drains and sources; Mgate_cas's drain and source; Mgate_off's drain;
    #     Mgate_off_dummy's drain and source), the five overlaps of gates that stay put
    #     (Mgate_pass's and Mgate_cas's two each on vdd, Mgate_off's on clk_b) and
    #     Mgate_off_dummy's gate, its channel on.
    # Ours against the source: M3's and M5's source junctions are none in ours (Mgate's and
    #   Mpre's sources are their wells, on boot_top); the source's M5 has its gate on the boosted
    #   node too and leaves its overlap of V_DD out; the stack's nodes are ours. They rise to less
    #   than ``gate`` (a threshold or more below; gate_off no further than a threshold below
    #   vdd), so counting them whole bounds their charge from above.
    # Holds for: tracking, the gate settled; devices only (BOOST_UNCOUNTED: wells and wiring).
    helper = params.boot_w
    precharge = PRECHARGE_W * helper * (overlap_f + junction_f)
    stack = helper * (11 * junction_f + 5 * overlap_f) + _gate_f(
        helper, 1, gate_f=gate_f, short=short, overlap_f=overlap_f
    )
    return precharge + stack


def _boosted_f(
    params: Params,
    *,
    gate_f: float = GATE_F,
    short: float = GATE_SHORT,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
) -> float:
    """What a bootstrap's boost capacitor shares its charge with while tracking: every device on
    the boosted nodes (``gate`` and ``boot_top``, joined by Mgate)."""
    # [Razavi-ADC] Eq. (3.70), p. 50: C_G1 + C_G2 + C_p, what C_b shares its charge with on the
    # boosted node (C_G1 + C_G2 by Eq. (3.69), p. 49)
    # [Razavi-ADC] Fig. 3.45, p. 50: C_GS3 + C_GD3 among the boosted node's parasitics
    # Terms, from the netlist (flow.samp.subckt.netlist): C_G1 MN's gate; C_G2 Mbot_in's gate, bot_l
    #   long; C_GS3 + C_GD3 Mgate's gate, between boot_top and gate_ctl, which sits at vdd with
    #   boot_top while holding (0 V across it) and on the bottom plate while tracking (V_b' across
    #   it): charged from 0 V to V_b' as C_G1 and C_G2 are; the rest of C_p ``_fixed_f``.
    # Ours against the source: the source's M3 has its gate on the clock, ours on a node that
    #   follows the bottom plate: the same charge. Mpre conducts until the gate is a threshold
    #   below the supply, so part of this charge comes from the supply: the count bounds the loss
    #   from above.
    # Holds for: tracking, the gate settled; devices only (BOOST_UNCOUNTED: wells and wiring).
    units = {"gate_f": gate_f, "short": short, "overlap_f": overlap_f}
    switch = _gate_f(params.mos_w, params.mos_l, **units)
    bottom = _gate_f(params.boot_w, params.bot_l, **units)
    top = _gate_f(params.boot_w, 1, **units)
    return switch + bottom + top + _fixed_f(params, junction_f=junction_f, **units)


def _bottom_f(
    params: Params,
    *,
    gate_f: float = GATE_F,
    short: float = GATE_SHORT,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
    bottom_f: float = BOTTOM_F,
) -> float:
    """What a bootstrap's bottom-plate switch charges as the bottom plate (``boot_bot``, Q) rises:
    its capacitance to the substrate, the control node it carries and, through the boost
    capacitor, the boosted nodes' capacitance to nodes that stay put."""
    # not in the reference texts: own count from the netlist (flow.samp.subckt.netlist), C_Q =
    # (W L)_cap C_bottom + (2 W_cap + 5 W_helper) C_j + C_ctl + C_b C_A / (C_b + C_A)
    # Terms: Mcap's channel to the substrate (cap_w by cap_l) and its source's and drain's
    #   junctions (each cap_w wide); the junctions of Mbot's, Mbot_in's and Mctl_on's drains and
    #   of Mctl_cap's drain and source on boot_bot (each boot_w wide; Mctl_cap's gate, on
    #   gate_ctl, rises with Q, its channel off: its capacitance to the substrate, a few per cent
    #   of its oxide's and under one per cent of C_Q, is left out); C_ctl the node gate_ctl, which
    #   Mctl_on joins to boot_bot while tracking, and the clocks' overlaps of the two: the
    #   junctions of Mctl_p's drain, Mctl_on's source and Mctl_dummy's two (three helper widths),
    #   the overlaps of Mctl_p's gate (clk) and of Mctl_on's (two) and Mbot's gates (clk_b), and
    #   Mctl_dummy's gate, half a helper wide, its channel on; C_A what the boosted nodes, which
    #   rise with Q through C_b, have to nodes that stay put: ``_fixed_f`` and MN's and Mbot_in's
    #   overlaps of vin.
    # Ours against the source: [Razavi-ADC] Example 3.22, p. 51 names the capacitor's parasitic as
    #   what the input must drive, without a value.
    # Holds for: a MOS boost capacitor whose channel is its bottom plate; a rising step, MN's
    #   channel moving with the output (in a falling step MN's whole gate stays on vin and C_Q is
    #   larger); the mean over Q's rise from 0 V to the supply (larger at 0 V, smaller at the
    #   supply: the readme's calibrations).
    units = {"gate_f": gate_f, "short": short, "overlap_f": overlap_f}
    helper = params.boot_w
    substrate = params.cap_w * params.cap_l * bottom_f + (2 * params.cap_w + 5 * helper) * junction_f
    control = helper * (3 * junction_f + 4 * overlap_f) + _gate_f(helper, 1, **units) / 2
    boost = _boost_f(params, **units)
    still = _fixed_f(params, junction_f=junction_f, **units) + (params.mos_w + helper) * overlap_f
    return substrate + control + boost * still / (boost + still)


def _bottom_length(
    params: Params,
    load_f: float,
    *,
    lift: float = BOTTOM_LIFT,
    gate_f: float = GATE_F,
    short: float = GATE_SHORT,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
    bottom_f: float = BOTTOM_F,
) -> float:
    """The least length of a bootstrap's bottom-plate switch (Mbot_in), in units, at which the
    bottom plate cannot pass the output the switch moves into ``load_f`` (``BOTTOM_LIFT``)."""
    # not in the reference texts: L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q (BOTTOM_LIFT's
    # derivation)
    # Terms: W_2 boot_w and L_2 bot_l, Mbot_in's; L_1 mos_l and W_1 mos_w, MN's; C_L ``load_f``
    #   on vout; C_Q ``_bottom_f``; BOTTOM_LIFT ``lift``.
    # Ours against the source: none (an own rule).
    # Holds for: ``load_f`` or a smaller load on vout: the length grows with the load, and a
    #   larger load than it is sized for slows the output and lets the bottom plate pass it.
    bottom = _bottom_f(
        params, gate_f=gate_f, short=short, overlap_f=overlap_f, junction_f=junction_f, bottom_f=bottom_f
    )
    return lift * params.boot_w * params.mos_l / params.mos_w * load_f / bottom


def _bootstrapped(
    mos_w: int,
    mos_l: int = 1,
    *,
    load_f: float = LOAD_F,
    lift: float = BOTTOM_LIFT,
    gate_f: float = GATE_F,
    short: float = GATE_SHORT,
    overlap_f: float = OVERLAP_F,
    junction_f: float = JUNCTION_F,
    bottom_f: float = BOTTOM_F,
) -> Params:
    """The bootstrapped NMOS switch ``mos_w`` by ``mos_l``, sized for ``load_f`` on its output with
    a kit's unit capacitances and current ratio (the rough 65-nm ones here unless given): its
    helpers an eighth of the switch, none under 4 units (the finest PDK's minimum width); its boost
    capacitor and its bottom-plate switch's length solved together, the shortest bottom-plate
    switch whose gate the capacitor still boosts to ``BOOST_MIN``."""
    # [Razavi-ADC] Eq. (3.70), p. 50: V_b' = C_b / (C_b + C_G1 + C_G2 + C_p) V_DD, solved for C_b:
    # C_b >= BOOST_MIN / (1 - BOOST_MIN) (1 + BOOST_UNCOUNTED) (C_G1 + C_G2 + C_p), with
    # L_2 >= ``_bottom_length``
    # Terms: C_b ``_boost_f`` (cap_w by BOOST_CAP_L); C_G1 + C_G2 + C_p ``_boosted_f``, in which
    #   C_G2 grows with Mbot_in's length bot_l; C_Q ``_bottom_f`` grows with the capacitor.
    # Ours against the source: the source sizes C_b alone; ours has a long M2 whose gate loads the
    #   capacitor and whose length the capacitor's own bottom plate sets, so the two are solved
    #   together: the first bot_l, counting up, that the capacitor sized for it admits.
    # Holds for: ``load_f`` or less on vout; a design ``valid`` admits (BOTTOM_GATE_MAX); the
    #   parameters, in whole size units: a kit's fingering to its row cells builds a width up to
    #   a few per cent off its parameter (a helper up to a seventh), inside BOOST_UNCOUNTED.
    # not in the reference texts: the helpers an eighth of the switch's width, none under 4 units
    # Terms: boot_w, the width of the twelve devices Mbot_in, Mbot, Mgate, Mctl_p, Mctl_on,
    #   Mctl_cap, Mgate_top, Mgate_drop, Mgate_pass, Mgate_cas, Mgate_off and Mgate_off_dummy;
    #   Mctl_dummy is half of it and Mpre PRECHARGE_W times it.
    # Ours against the source: [Razavi-ADC] Fig. 3.41(b), p. 48 gives no sizes.
    # Holds for: a finest PDK whose minimum width is 4 units.
    units = {"gate_f": gate_f, "short": short, "overlap_f": overlap_f}
    boot_w = max(4, mos_w // 8)
    for bot_l in range(1, 4096):
        sized = Params(switch_type=SwitchType.BOOTSTRAP, mos_w=mos_w, mos_l=mos_l, boot_w=boot_w, bot_l=bot_l)
        load = _boosted_f(sized, junction_f=junction_f, **units)
        least = BOOST_MIN / (1 - BOOST_MIN) * (1 + BOOST_UNCOUNTED) * load
        cap_w = math.ceil(least / _gate_f(1, BOOST_CAP_L, **units))
        sized = Params(
            switch_type=SwitchType.BOOTSTRAP,
            mos_w=mos_w,
            mos_l=mos_l,
            boot_w=boot_w,
            cap_w=cap_w,
            cap_l=BOOST_CAP_L,
            bot_l=bot_l,
        )
        if _bottom_length(sized, load_f, lift=lift, junction_f=junction_f, bottom_f=bottom_f, **units) <= bot_l:
            return sized
    raise ValueError(f"no bottom-plate switch under 4096 units lifts a {mos_w} by {mos_l} switch's bottom plate")


def valid(params: Params, pdk: str) -> bool:
    """Whether ``params`` is a design in ``pdk``: every plain switch; a bootstrapped one whose boost
    capacitor holds V_b' at ``BOOST_MIN`` of the supply or more, whose bottom-plate switch is long
    enough for the bench's load (``LOAD_F``) and whose gate is no more than ``BOTTOM_GATE_MAX``
    times the switch's own. Every PDK's bootstrap is judged, as it is sized, by the rough 65-nm
    unit capacitances and current ratio here (``pdk`` selects none of its own: a kit holds none
    yet): the boost condition is a ratio of like capacitances and carries over to another kit;
    the bottom-plate length is calibrated on these alone."""
    if params.switch_type is not SwitchType.BOOTSTRAP:
        return True
    # [Razavi-ADC] Eq. (3.70), p. 50: C_b >= BOOST_MIN / (1 - BOOST_MIN) (1 + BOOST_UNCOUNTED) (C_G1 + C_G2 + C_p)
    # Terms: C_b ``_boost_f`` (Mcap); C_G1 + C_G2 + C_p ``_boosted_f`` (every device on the boosted
    #   nodes: MN's, Mbot_in's and Mgate's gates, Mpre's gate over vdd and its drain's junction,
    #   Mgate_top's drain, the pull-down stack's nodes).
    # Ours against the source: BOOST_UNCOUNTED, for the wells and the wiring.
    # Holds for: the unit capacitances here (GATE_F to BOTTOM_F), the same in every PDK; the
    #   parameters (a kit's fingering builds a width a few per cent off).
    boosted = _boost_f(params) >= BOOST_MIN / (1 - BOOST_MIN) * (1 + BOOST_UNCOUNTED) * _boosted_f(params)
    # not in the reference texts: L_2 at least ``_bottom_length`` at the bench's load, and
    # C_G2 <= BOTTOM_GATE_MAX C_G1 (the constants' derivations)
    # Terms: L_2 bot_l (Mbot_in's length); C_G1, C_G2 ``_gate_f`` of MN and of Mbot_in.
    # Ours against the source: none (own rules).
    # Holds for: the bench's load LOAD_F on vout or a smaller one; a design sized for a larger
    #   load is admitted too.
    lifted = params.bot_l >= _bottom_length(params, LOAD_F)
    bounded = _gate_f(params.boot_w, params.bot_l) <= BOTTOM_GATE_MAX * _gate_f(params.mos_w, params.mos_l)
    return boosted and lifted and bounded


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the sampler's testbench (flow.samp.sim.testbench): the switch ``params`` in ``pdk``
    at supply ``vdd``, process ``corner`` and ``temperature_c`` into ``cload``; its input at
    ``input_voltage`` or, with an ``input_step_v``, stepping by it once a period in the middle of
    each hold phase (over ``input_transition_time_s`` where given, else a clock edge's time) and,
    with a ``track_step_v``, by that once a period inside each track phase, ``track_step_s`` after
    the clock's high time starts (its middle where not given; with both steps equal, every track
    phase ends on ``input_voltage``, reached from below and from above in turn), or (``stimulus`` SINE) a sine about ``input_voltage`` of ``sine_amplitude_v``
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
    track_step_s: float | None = None
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
        # not in the reference texts: the hold-phase change of the input fits the clock's low time,
        # 0 < t_slew <= T - t_high - 3 t_edge: centred half a clock edge before the low time's
        # middle (flow.samp.sim.testbench), it then starts after the clock has fallen and ends
        # before it rises
        # Terms: t_slew input_transition_time_s, T clock_period_s, t_high clock_high_time_s,
        #   t_edge clock_transition_time_s.
        # Holds for: a run that gives its own transition time (the clock's edge otherwise).
        low = float(self.clock_period_s) - float(self.clock_high_time_s) - 3 * float(self.clock_transition_time_s)
        if self.input_transition_time_s is not None and not 0.0 < float(self.input_transition_time_s) <= low:
            raise ValueError("sampler input transition must be positive and fit the clock's low time")
        # not in the reference texts: the track step, a clock edge long and centred t_step after the
        # clock's high time starts (flow.samp.sim.testbench), lies inside it,
        # t_edge / 2 <= t_step <= t_high - t_edge / 2
        # Terms: t_step track_step_s, t_high clock_high_time_s, t_edge clock_transition_time_s.
        # Ours against the source: none (a bench's timing).
        # Holds for: a run that gives the step's instant (the high time's middle otherwise).
        edge = float(self.clock_transition_time_s)
        if self.track_step_s is not None and not (
            edge / 2 <= float(self.track_step_s) <= float(self.clock_high_time_s) - edge / 2
        ):
            raise ValueError("sampler track step must lie inside the clock's high time")
        if self.stimulus is Stimulus.SINE and (self.sine_amplitude_v <= 0 or self.sine_frequency_hz <= 0):
            raise ValueError("a sine's amplitude and frequency must be positive")
        if self.gmin_s is not None and not 0.0 < float(self.gmin_s) < 1e-9:
            raise ValueError("sampler gmin must be positive and below 1 nS")

    @property
    def stop_s(self) -> float:
        """The run's length: every period."""
        return self.periods * float(self.clock_period_s)
