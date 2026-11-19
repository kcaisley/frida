"""The comparator's parameters: its design (``Params``, every one of which builds), one run of its
testbench (``TbParams``), and the testbench every comparator is tested on.

Every comparator is tested the same way, so that comparators compare: the clock (``RESET_S`` of
reset, then ``EVALUATION_S`` of evaluation), the inputs driven through ``SOURCE_RESISTANCE_OHM`` onto
``SOURCE_CAPACITANCE_F`` a side (a source as quiet and stiff as a CDAC's top plate, so the noise is
the comparator's own), and the stimuli the characterization takes: the delay over the input
(``METASTABILITY_RUN_V``), a transient-noise S-curve (``SCURVE_V``, ``SCURVE_DECISIONS`` a point in
shuffled passes), kickback onto a DAC-like source (``KICKBACK_SOURCE``), over the common mode
(``CM_SWEEP``) and the supply (``SUPPLY_SWEEP``), the held outputs toggling (each of
``METASTABILITY_V`` and ``SMALL_V`` after ``LARGE_V`` of either sign), a small input after a full-scale
one (``ADC_FULL_SCALE``), the slow corner and the converter's clocks (``ClockDrive``).

The behavioral model (``flow.comp.model``) estimates a StrongARM's noise from its sizing with the
rough device constants here (``W_MIN_UM`` to ``COX_F_PER_UM2``).

Every constant and default that states a rule carries its source beside it (docs/references.md),
its terms as this bench's and this circuit's names, and where it holds.
"""

import math
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth
from pydantic import PositiveInt

from flow import pipeline
from flow.circuit.spectre import Accuracy


class Latch(Enum):
    """The comparator's latch, its stages after the input pair: each a topology of its own, which the
    generator builds (``flow.comp.subckt``); a latch from a paper is one more member."""

    # [Razavi-ADC] Sec. 5.8.3, Fig. 5.37, p. 94: the StrongArm comparator, one stage, the
    # cross-coupled pair stacked on the input pair
    STRONGARM = auto()
    # [Schinkel] Fig. 2, p. 90: the double-tail latch, a second stage with its own clocked tail
    DOUBLE_TAIL = auto()
    # [Schinkel] Fig. 2, p. 90, the double tail; frida adds its latch's init devices driven by the
    # input pair's drains instead of the clock (self-timed)
    DOUBLE_TAIL_SELF_TIMED = auto()
    # [vanElzakker] Fig. 7, p. 1010: the two-stage dynamic comparator, its inner on devices
    # signaled by the first stage, a clocked reset
    DOUBLE_TAIL_MODIFIED = auto()
    # [vanElzakker] Fig. 7, p. 1010, the modified double tail; frida adds its inner init devices
    # driven by the input pair's drains instead of the clock (self-timed)
    DOUBLE_TAIL_MODIFIED_SELF_TIMED = auto()
    # not in the reference texts: a cascoded input pair, a regenerating second stage and a clocked
    # latch (frida's own)
    TRIPLE_TAIL = auto()


class Bias(Enum):
    # [Bindra] Fig. 3, p. 2: the dynamic-bias preamplifier, its tail a capacitor reset to ground
    DYNAMIC = auto()
    # [Razavi-ADC] Sec. 5.8.3, Fig. 5.37, p. 94: the input pair's tail a clocked switch
    SWITCHED = auto()


class InputOrder(StrEnum):
    """How a testbench run steps its inputs (``TbParams.trial_point``), at each common mode: its
    members compare equal to their names in lower case, as a run's JSON writes them."""

    BLOCKED = auto()  # every input held for all its decisions, in the order given
    SHUFFLED = auto()  # every input once a pass, each pass in a fresh random order
    CYCLED = auto()  # every input once a pass, each pass in the order given
    # every input but the first two after each of them in turn (the first, the input, the second,
    # the input), the inputs in the order given, once a pass: an input whose decision is either
    # follows one of the other
    AFTER_BOTH = auto()


class Validity(StrEnum):
    """What an S-curve's fit is (``AnalysisOffsetNoise.validity``): its members compare equal to
    their names in lower case, as a record's JSON writes them."""

    VALID = auto()  # the Gaussian of most likelihood, its transition resolved by the inputs
    UNBRACKETED = auto()  # the curve never crosses one of its 16 %, 50 % or 84 % points
    NON_MONOTONIC = auto()  # a significant reversal between neighbouring inputs
    UNRESOLVED = auto()  # more than 1 % of the decisions unresolved
    # fewer than two inputs inside the transition (a share strictly between 0 and 1): its width
    # is below the inputs' spacing there, so the noise is not measured
    UNDERSAMPLED = auto()
    # a curve pinned below 0.1 (above 0.9) where a neighbouring common mode's offset lies in its
    # inputs' span (``AnalysisCommonMode``)
    STUCK_LOW = "stuck-low"
    STUCK_HIGH = "stuck-high"


class ClockDrive(Enum):
    """How a testbench run drives the comparator's two clocks (``TbParams.clock_drive``)."""

    # each clock from an inverter chain of its own on the comparator's supply, the two chains
    # matched and their sources complementary
    CHAINS = auto()
    # as the converter clocks it (flow.adc.subckt): clk from its chain on a supply of its own (the
    # converter's digital block drives it), clkb from clk through one inverter on the comparator's
    # supply
    CONVERTER = auto()


class OutputStage(Enum):
    """The output stage's two views, the same gates and wiring (``subckt``): the simulations netlist
    ``TRANSISTORS``, the layout draws ``STDCELLS`` (``layout_view``). Their sizes are set apart
    (``srlatch_n_w`` and ``srlatch_p_w`` against the cells' drives), so the two are one circuit only
    where those widths are what the cells draw: the latch nodes' load, the outputs' delay and the
    toggling energy differ between them otherwise (readme.md)."""

    TRANSISTORS = auto()  # decision inverters, SR latch and buffers drawn transistor by transistor
    STDCELLS = auto()  # the same gates as generic logic cells at fixed drives, mapped to a library by the PDK


@h.paramclass
class Params:
    """The comparator: its latch, input pair and bias, any combination of them, and its device sizes
    as positive multiples of the PDK's unit width and minimum length (w = 10: ten unit widths), so
    that one design ports across PDKs. Every Params the class admits builds; the defaults are the
    characterization's short-channel sizes, at which ``Params(latch=...)`` is a topology's reference.
    What a grid or an optimization varies is a space of it (``pipeline.widen``: runs.py)."""

    latch = h.Param(dtype=Latch, desc="Latch topology", default=Latch.STRONGARM)
    input_pair = h.Param(dtype=MosType, desc="Input pair type (NMOS or PMOS)", default=MosType.NMOS)
    bias = h.Param(
        dtype=Bias,
        desc="The input pair's tail: a clocked switch, or a switch onto C_TAIL (dynamic bias)",
        default=Bias.SWITCHED,
    )
    output_stage = h.Param(
        dtype=OutputStage,
        desc="Output stage implementation (a view: layout draws both)",
        default=OutputStage.TRANSISTORS,
    )

    # device sizes, in unit widths and minimum lengths
    # not in the reference texts: the defaults, the characterization's short-channel sizes (frida's
    # own): the input pair (Mdiff_p/n) 32 units two lengths long on a tail (Mtail) half as wide and
    # as long, every reset and latch device 8 units at the minimum length. Two of their ratios
    # meet a source:
    # [Razavi-ADC] Fig. 7.4, p. 131: the output inverters with W_P = 2 W_N (srlatch_p_w = 2
    # srlatch_n_w, every gate of the output stage)
    # [Bindra] Sec. V, p. 6: C_TAIL / C_P = 3.5 for a 0.5 V fall of the drains; the defaults' 100
    # over 60 fF departs from it (bias_c_ff, preamp_c_ff: a grid sets its own, runs.dynamic_bias)
    # Holds in any PDK (a unit is the kit's unit width and minimum length); a width is netlisted
    # at the nearest even count of whole-unit fingers (flow.circuit.devices.fingers), so an odd
    # one is drawn a unit off
    diffpair_w = h.Param(dtype=PositiveInt, desc="Diff pair width multiplier", default=32)
    diffpair_l = h.Param(dtype=PositiveInt, desc="Diff pair length multiplier", default=2)
    tail_w = h.Param(dtype=PositiveInt, desc="Tail width multiplier", default=16)
    tail_l = h.Param(dtype=PositiveInt, desc="Tail length multiplier", default=2)
    rst_w = h.Param(dtype=PositiveInt, desc="Reset device width multiplier", default=8)
    rst_l = h.Param(dtype=PositiveInt, desc="Reset device length multiplier", default=1)
    latch_on_w = h.Param(dtype=PositiveInt, desc="Latch evaluation-side width multiplier", default=8)
    latch_on_l = h.Param(dtype=PositiveInt, desc="Latch evaluation-side length multiplier", default=1)
    latch_init_w = h.Param(dtype=PositiveInt, desc="Latch precharge-side width multiplier", default=8)
    latch_init_l = h.Param(dtype=PositiveInt, desc="Latch precharge-side length multiplier", default=1)
    srlatch_n_w = h.Param(dtype=PositiveInt, desc="Output SR-latch NMOS width multiplier", default=4)
    srlatch_p_w = h.Param(dtype=PositiveInt, desc="Output SR-latch PMOS width multiplier", default=8)
    vth = h.Param(dtype=MosVth, desc="Every device's Vth", default=MosVth.LOW)

    # the dynamic bias's capacitors, MOS capacitors of nominal capacitance (unused with a switched tail)
    preamp_c_ff = h.Param(
        dtype=PositiveInt,
        desc="Dynamic bias: the MOS capacitance added to each input-pair drain, to its evaluation rail (fF)",
        default=60,
    )
    bias_c_ff = h.Param(dtype=PositiveInt, desc="Dynamic bias: C_TAIL, the tail's MOS capacitance (fF)", default=100)


def layout_view(params: Params) -> Params:
    """The comparator as laid out: its output stage the PDK's library cells (``OutputStage``'s
    STDCELLS view; the simulations draw it transistor by transistor)."""
    return Params(**{**params.__dict__, "output_stage": OutputStage.STDCELLS})


# the parameters that make a comparator's devices and their wiring; a dynamic bias adds its capacitors
STRUCTURE = ("latch", "input_pair", "bias")


pipeline.Params.register(Params)


# not in the reference texts: the fabricated FRIDA-1 comparator's sizes (a StrongARM: single stage,
# NMOS input, switched tail), as given. Holds as drawn, not as simulated: a width is netlisted at
# the nearest even count of whole-unit fingers (flow.circuit.devices.fingers), so its odd widths
# are simulated a unit off: the tail (Mtail, which sets the delay) 6 units wide for its 5, the
# pair and the latch's pairs a unit narrower or wider by the kit's fingers; the clock's load
# (sim._clock_chains) counts the sizes given here
FRIDA1 = Params(
    diffpair_w=37,
    tail_w=5,
    rst_w=8,
    latch_on_w=25,
    latch_init_w=33,
    srlatch_n_w=4,
    srlatch_p_w=8,
    diffpair_l=5,
    tail_l=13,
    rst_l=1,
    latch_on_l=6,
    latch_init_l=17,
    latch=Latch.STRONGARM,
    input_pair=MosType.NMOS,
    bias=Bias.SWITCHED,
)


# not in the reference texts: the bench's clock, RESET_S of reset (clk low) then EVALUATION_S of
# evaluation (clk high), the same for every comparator: the evaluation twice the time the
# converter allows a decision (DECISION_S: flow.adc), so that a comparator it could use decides
# well inside it. Holds for every run that gives no clock of its own (TbParams.reset_time_s,
# evaluation_time_s)
RESET_S = 1e-9
EVALUATION_S = 4e-9
# not in the reference texts: twice the reset and twice the evaluation, the clock a comparator's
# decisions are checked against (analysis.analyze_clock_check): a comparator that neither phase of
# the bench's clock shapes decides alike on both
CHECK_CLOCK_S = (2 * RESET_S, 2 * EVALUATION_S)
# not in the reference texts: the edges of the clocks' sources and of each input step, 0 to 100 %
# (TbParams.transition_time_s). The comparator's own clock edge is its chain's
# (sim._clock_chains); the input's step (sim.testbench) and the read (TbParams.decision_time_s)
# are placed by it
TRANSITION_S = 20e-12
# [Baker] Eq. (11.20), p. 360: a buffer's taper, A = (C_load / C_in1)^(1/N), each stage A times
# the one before (its terms as the bench's: sim._clock_chains)
# not in the reference texts: the two values. CLOCK_FANOUT, the largest A a chain takes (the
# source's least delay is at A = e, Eq. (11.25), p. 360: 4 takes fewer stages). CLOCK_LAST_FANOUT,
# the clocked gates over the last stage's input, 2 (the source's last stage drives A times its
# input, Eq. (11.19), p. 360): a sharper edge into the comparator than the stages before it see.
# The drivers' energy is counted as the comparator's, their area is not (the converter's digital
# control drives the clock). Holds where TbParams.clock_fanout is given (None: ideal sources)
CLOCK_FANOUT = 4.0
CLOCK_LAST_FANOUT = 2.0
# not in the reference texts: the simulator's output step (Spectre's strobe period,
# TbParams.waveform_sample_interval_s). STROBE_S, the noise-free runs': a delay is read between
# two of its points (readme.md: the error it leaves). NOISE_STROBE_S, the transient-noise
# S-curves': half a period of the noise's bandwidth, 1 / (2 TbParams.noise_fmax_hz), the step the
# noise sources need; the two are set together (test_params checks the default)
STROBE_S = 2e-12
NOISE_STROBE_S = 5e-12
# not in the reference texts: the supply's charge, its current's integral, V(qmeter) x
# CHARGE_METER_F: the current of the supply's source (vvdd: the comparator's and its clock
# chains') mirrored by a unity-gain current-controlled source onto this capacitor (sim.METER) and
# integrated by the simulator on its own steps, so exact at any output step. Not metered:
# vdd_clock, the supply of clk's chain where the converter drives the clocks
# (ClockDrive.CONVERTER)
CHARGE_METER_F = 1e-12
CHARGE_METER = "qmeter"  # its node, as a measurement names it
# [Razavi-Analog] Eq. (7.16), p. 228: a resistor's thermal noise, 4kT R a hertz
# R: SOURCE_RESISTANCE_OHM a side (rsrc_p, rsrc_n: 2 R between the inputs), onto
# SOURCE_CAPACITANCE_F a side (csrc_p, csrc_n). The source adds none of its own where 4kT (2 R)
# NBW is far below the comparator's noise power, NBW the comparator's noise bandwidth, 1 / (2
# T_int) of its integration time ([vanElzakker] Eq. (5), (6), (11), p. 1011: the DAC's noise
# resistance far below the comparator's); the total on the capacitor is kT/C a side at any R
# ([Razavi-Analog] Eq. (7.23), p. 229), spread to 1 / (2 pi R C), far above that band at 1 ohm.
# Stiff besides: a decision's kickback returns through R within R C, 0.1 ps
SOURCE_RESISTANCE_OHM = 1.0
SOURCE_CAPACITANCE_F = 100e-15
# not in the reference texts: the kickback run's source (ohm, F a side), a DAC's top plates left
# to themselves: tau = R C = 1 us, far above the cycle (TbParams.cycle_s), so the charge a decision
# kicks onto the inputs stays for the decisions after it ([Razavi-ADC] Sec. 5.7.4, p. 88 has the
# kickback's currents through the source's impedance); kickback_v and kickback_diff_v are the
# voltages on this source alone
KICKBACK_SOURCE = (1e6, 1e-12)
# not in the reference texts: the input common mode as a fraction of the PDK's core supply, the
# bench's own: NOMINAL_CM (13/24: 0.65 V of 1.2 V) and its sweep, 3/8 to 5/8 in twelfths
NOMINAL_CM = 13 / 24
CM_SWEEP = (9 / 24, 11 / 24, 13 / 24, 15 / 24)
# not in the reference texts: the supply's corners, 90 and 110 % of the nominal besides it, the
# flow's own (flow.circuit.oppoint.SUPPLY_CORNER_MAX): never past the largest, above which a kit's
# device models may warn
SUPPLY_SWEEP = (0.9, 1.0, 1.1)
# [Razavi-ADC] Sec. 7.3, p. 131: the comparator's speed at a small input (the source: half an LSB)
# not in the reference texts: the two inputs, the bench's own: SMALL_V, the slow response the
# metrics name (about one LSB of a 12-bit converter here, runs.adc_12bit, not the source's half),
# and LARGE_V, a fast one
SMALL_V, LARGE_V = 0.5e-3, 100e-3
# not in the reference texts: the span about the offset over which the delay law of [Razavi-ADC]
# Eq. (7.6), p. 136 is fitted (analysis._regeneration) and the model's delay table extrapolated
# (model._tau): the inputs at most this far from the offset. The bench's own choice, with
# METASTABILITY_V's spacing: at least two inputs lie within it whatever the offset up to 12 mV
REGENERATION_SPAN_V = 3e-3
# not in the reference texts: the delay curve's inputs, one noise-free decision each, each of
# METASTABILITY_V after its negative, so that every decision but the first follows one of the other
# sign (a latch the reset leaves holding its last decision, which inputs of one sign cannot show,
# decides it again, or late). 1 to 3 mV apart from 2 to 15 mV: a systematic offset up to 12 mV
# either way leaves an input within 2 mV of it on each side and at least two within
# REGENERATION_SPAN_V, which the fit of the offset with the time constant needs
# (analysis.analyze_metastability)
METASTABILITY_V = (0.1e-3, 0.3e-3, 1e-3, 2e-3, 3e-3, 4e-3, 6e-3, 8e-3, 10e-3, 12e-3, 15e-3, 30e-3, 100e-3)
METASTABILITY_RUN_V = tuple(v for value in METASTABILITY_V for v in (-value, value))
# not in the reference texts: the S-curve's inputs, 0 and 16 magnitudes from 5 uV to 3 mV a side
# (33 points, log-spaced, finest at the centre), for 10 uV to 1.5 mV of noise; SCURVE_DECISIONS at
# each, a pass through every input at a time in a fresh random order (InputOrder.SHUFFLED), so that
# noise slower than a pass moves every input alike (readme.md: a reading's scatter between seeds).
# [Razavi-ADC] Eq. (12.6), p. 239: the quantization noise, LSB / sqrt(12)
# the quietest and the loudest comparator the grid is laid for: 15 points lie within 2 sigma of a
# 14-bit converter's (34 uV at a 1.2 V supply, runs.adc_14bit), 29 of a 10-bit one's (541 uV)
SCURVE_UV = (5, 10, 15, 20, 25, 35, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 3000)
SCURVE_V = (*(-round(uv * 1e-6, 9) for uv in reversed(SCURVE_UV)), 0.0, *(round(uv * 1e-6, 9) for uv in SCURVE_UV))
SCURVE_DECISIONS = 80

# not in the reference texts: rough device constants of one kit's 65 nm core devices, for the
# behavioral model's noise estimate from a StrongARM's sizing (model.Model.strongarm_noise, which
# takes no PDK: it ranks sizings, it does not predict another kit's noise).
# [Razavi-Analog] Sec. 2.4.2, pp. 29-30: a device's capacitances, the gate's W L C_ox and each
# junction's, proportional to the width
# W_MIN_UM, L_MIN_UM: the width and length a size unit stands for in that kit (each kit's own:
# flow.circuit.devices.core_unit). COX_F_PER_UM2: C_ox, the gate capacitance per area.
# JUNCTION_F_PER_UM: what a drain or source puts on its node per width, an upper estimate within
# a factor of two: it lumps the junction, the gate overlap and wiring, where the junction and the
# overlap of a shared-finger drain alone are about two thirds of it
W_MIN_UM = 0.12
L_MIN_UM = 0.06
JUNCTION_F_PER_UM = 0.8e-15
COX_F_PER_UM2 = 14e-15

# The optimization's problems (flow.comp.runs): a comparator for a converter of each resolution, its
# noise at most the converter's quantization noise (every noise source about equal to it), its
# layout within a square, its delay within the converter's decision time, deciding within the clock.
# [Razavi-ADC] Eq. (12.6), p. 239: the quantization noise power, LSB^2 / 12 (its rms the bound on
# the comparator's noise: runs.adc_10bit has the LSB's terms)
# not in the reference texts: ADC_FULL_SCALE, the converter's full scale a side over its supply
# (its arrays reach at least 80 % of the reference: flow.adc.runs), so the differential full
# scale is twice it
ADC_FULL_SCALE = 0.8
# not in the reference texts: the side of the square a comparator's layout must fit, by the
# converter's bits, the same in every PDK (a denser PDK fits more in it): design budgets, not
# derived (none of the sources or of the block's runs gives them)
AREA_SIDE_UM = {10: 15.0, 12: 20.0, 14: 63.0}
# not in the reference texts: the time the converter allows a decision, the bound on the delay at
# SMALL_V: a fifth inside the 2.5 ns a decision has in flow.adc's sequence at its nominal rate
DECISION_S = 2e-9
# not in the reference texts: the cost, energy x area^AREA_WEIGHT x (1 + (noise /
# LSB-noise)^2)^NOISE_WEIGHT, in J um^2 (flow.pipeline.Problem builds it: a metric with a scale
# enters as (1 + (metric / scale)^2)^weight). The last factor is the converter's noise power over
# its quantization noise alone (Eq. (12.6)), near 1 where it no longer gains from a quieter
# comparator. Its least for a design that only scales, the code's own derivation from two laws:
# [Razavi-ADC] Sec. 5.8.4, p. 97: the power, f_CK (C_X + C_P + C_Q) V_DD^2, so the energy (and
# the area) proportional to the widths' scale s
# [Razavi-ADC] Eq. (6.60), p. 116: the noise power, inversely proportional to C_1, so to 1 / s
# so cost ~ u^-(1 + AREA_WEIGHT) (1 + u)^NOISE_WEIGHT in u = (noise / LSB-noise)^2, least at
# u = 1 / (NOISE_WEIGHT / (1 + AREA_WEIGHT) - 1): noise / LSB-noise = 0.71 with these weights.
# Holds where the laws do: every width scaled together, above the noise's floor, the area's fixed
# part (the output stage) small
AREA_WEIGHT = 1.0
NOISE_WEIGHT = 6.0


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the comparator's testbench (flow.comp.sim.testbench): the comparator ``params``
    in ``pdk`` at supply ``vdd``, its models at ``corner`` and ``temperature_c``, ``conversions``
    decisions at each input point (each common mode in ``vin_cm_values_v`` by each differential
    input in ``vin_diff_values_v``), stepped through as ``input_order`` says, on the clock and source
    every comparator is tested at unless given, its clocks driven as ``clock_drive`` says (clkb
    through ``clkb_inverter`` as the converter drives it); with transient noise up to
    ``noise_fmax_hz`` where ``noise``. Spectre writes its output every ``waveform_sample_interval_s``
    (``STROBE_S``; None keeps its own steps). Each device's operating-point values saved where
    ``device_values`` (``flow.circuit.oppoint.saves``); classic Spectre where the run needs its
    accuracy (``accuracy``), else Spectre X."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    # not in the reference texts: a core supply of 1.2 V and NOMINAL_CM of it where a run gives
    # neither (runs.testbenches gives every run the PDK's supply and its common mode)
    vdd: float = 1.2
    vin_cm_values_v: tuple[float, ...] = (round(NOMINAL_CM * 1.2, 4),)
    vin_diff_values_v: tuple[float, ...] = (0.0,)
    conversions: int = 1
    input_order: InputOrder = InputOrder.BLOCKED
    noise: bool = False
    corner: h.pdk.Corner = h.pdk.Corner.TYP
    temperature_c: float = 25.0
    clock_drive: ClockDrive = ClockDrive.CHAINS
    # not in the reference texts: the converter's clkb inverter (flow.adc.subckt: clk_comp_b), both
    # of its devices this width and length, in unit widths and minimum lengths: the converter's own
    # size, copied here; holds where clock_drive is CONVERTER
    clkb_inverter: tuple[int, int] = (10, 1)
    device_values: bool = False
    accuracy: Accuracy | None = None
    reset_time_s: float = RESET_S
    evaluation_time_s: float = EVALUATION_S
    transition_time_s: float = TRANSITION_S
    source_resistance_ohm: float = SOURCE_RESISTANCE_OHM
    source_capacitance_f: float = SOURCE_CAPACITANCE_F
    # not in the reference texts: the load on each held output (cload_p, cload_n): the converter's
    # logic gate inputs and their wire, taken as 10 fF, the bench's own; the outputs' delay and
    # the toggling energy hold for it
    output_load_f: float = 10e-15
    # the clock's drivers (flow.comp.sim.testbench): each clock an inverter chain from a unit
    # inverter, on the comparator's supply, tapering by clock_fanout a stage to a last stage whose
    # input is clock_last_fanout times smaller than the clocked gates; None, ideal sources (the
    # clock's energy then not counted)
    clock_fanout: float | None = CLOCK_FANOUT
    clock_last_fanout: float = CLOCK_LAST_FANOUT
    waveform_sample_interval_s: float | None = STROBE_S
    # not in the reference texts: transient noise's bandwidth where noise (Spectre's noisefmax),
    # the code's own derivation from
    # [Razavi-ADC] Eq. (6.52), p. 115: white noise integrated for a time T
    # T: the time the input pair (Mdiff_p/n) integrates onto its drains, tens of picoseconds. An
    # integration over T passes sinc^2(f T): a tenth of the variance lies above 1 / T and a
    # fortieth above 4 / T, 100 GHz for 40 ps. Holds for the integration alone: the regeneration
    # after it takes in more of the band (readme.md: the noise read at a quarter of this bandwidth)
    noise_fmax_hz: float = 100e9
    # TODO: matching a building-block Monte Carlo result to a higher-level run
    # by seed and iteration alone is not valid; the two runs draw independent
    # mismatch. Netlisting does not consume these fields yet.
    mc_seed: int | None = None
    mc_index: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.vdd)) or float(self.vdd) <= 0.0:
            raise ValueError("comparator vdd must be finite and positive")
        for name, values in (("common modes", self.vin_cm_values_v), ("differential inputs", self.vin_diff_values_v)):
            floats = tuple(float(value) for value in values)
            if not floats or not all(math.isfinite(value) for value in floats) or len(set(floats)) != len(floats):
                raise ValueError(f"comparator {name} must be finite and unique")
        if self.conversions <= 0:
            raise ValueError("comparator conversions must be positive")
        # an order given by its name (a run's JSON) is its member; any other name raises
        if self.input_order not in tuple(InputOrder):
            raise ValueError(f"comparator input order must be one of {[order.value for order in InputOrder]}")
        object.__setattr__(self, "input_order", InputOrder(self.input_order))
        if self.input_order is InputOrder.AFTER_BOTH and len(self.vin_diff_values_v) < 3:
            raise ValueError("comparator inputs after both of the first two need a third")
        if not math.isfinite(float(self.temperature_c)):
            raise ValueError("comparator temperature must be finite")
        for name in (
            "reset_time_s",
            "evaluation_time_s",
            "transition_time_s",
            "source_resistance_ohm",
            "source_capacitance_f",
            "output_load_f",
            "noise_fmax_hz",
        ):
            if not math.isfinite(float(getattr(self, name))) or float(getattr(self, name)) <= 0.0:
                raise ValueError(f"comparator {name} must be finite and positive")
        if len(self.clkb_inverter) != 2 or min(int(size) for size in self.clkb_inverter) < 1:
            raise ValueError("comparator clkb inverter must be a positive width and length")
        if self.clock_fanout is not None and not (
            float(self.clock_fanout) > 1.0 and float(self.clock_last_fanout) > 0.0
        ):
            raise ValueError("comparator clock fanouts must be positive, the taper's above 1")
        if self.waveform_sample_interval_s is not None and not float(self.waveform_sample_interval_s) > 0.0:
            raise ValueError("comparator waveform_sample_interval_s must be positive or None")
        if float(self.transition_time_s) >= min(float(self.reset_time_s), float(self.evaluation_time_s)):
            raise ValueError("comparator transition must be shorter than reset and evaluation")

    @property
    def cycle_s(self) -> float:
        """One decision: the reset, then the evaluation."""
        # not in the reference texts: the clock's period, the reset then the evaluation; every
        # energy per decision is a cycle's and every power that energy over it
        return float(self.reset_time_s) + float(self.evaluation_time_s)

    @property
    def points(self) -> list[tuple[float, float]]:
        """The input points, (common mode, differential input), the common modes outer."""
        return [(float(cm), float(diff)) for cm in self.vin_cm_values_v for diff in self.vin_diff_values_v]

    @property
    def trial_point(self) -> np.ndarray:
        """Each decision's input point (an index into ``points``), in the order the testbench applies
        them: at each common mode, ``BLOCKED`` holds every input for all its decisions, ``SHUFFLED``
        steps through every input once a pass (``conversions`` passes) in a fresh random order (a
        fixed seed), so that noise slower than a pass moves every input alike instead of whole
        points of the curve, ``CYCLED`` once a pass in the order given, and ``AFTER_BOTH`` each
        input but the first two after the first and again after the second, once a pass."""
        inputs = len(self.vin_diff_values_v)
        rng = np.random.default_rng(0)
        order = []
        for common_mode in range(len(self.vin_cm_values_v)):
            first = common_mode * inputs
            if self.input_order is InputOrder.BLOCKED:
                order.append(np.repeat(np.arange(inputs), self.conversions) + first)
            elif self.input_order is InputOrder.CYCLED:
                order.append(np.tile(np.arange(inputs), self.conversions) + first)
            elif self.input_order is InputOrder.AFTER_BOTH:
                rest = np.arange(2, inputs)
                bracketed = np.stack([np.zeros_like(rest), rest, np.ones_like(rest), rest], axis=1).ravel()
                order.append(np.tile(bracketed, self.conversions) + first)
            else:
                order.append(np.concatenate([rng.permutation(inputs) for _ in range(self.conversions)]) + first)
        return np.concatenate(order).astype(np.int64)

    @property
    def trial_start_s(self) -> np.ndarray:
        """Each decision's cycle start, its reset's beginning."""
        return np.arange(len(self.trial_point)) * self.cycle_s

    @property
    def decision_time_s(self) -> np.ndarray:
        """When each decision is read: just before its evaluation ends (two input transitions)."""
        # not in the reference texts: the read, two transitions before the cycle's end: the next
        # input steps over the first transition of the next cycle and the source clock falls with
        # it (sim.testbench), so the read sees the decision held, a transition clear of both
        return self.trial_start_s + self.cycle_s - 2 * float(self.transition_time_s)

    @property
    def stop_s(self) -> float:
        """The run's length: every decision's cycle."""
        return len(self.trial_point) * self.cycle_s
