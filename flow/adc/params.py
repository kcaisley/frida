"""The ADC's parameters: its design (``Params``, every combination of which builds) and one generated
testbench (``TbParams``: the view it simulates, its stimulus, its supplies and its sequencer rows,
by default the default recipe's, ``sim.symbol256_init8_samp16_comp11110000_logic00001111``); the
design space's resolutions and FRIDA-1's converter in it (``RESOLUTIONS``, ``FRIDA1_*``); the
behavioral model's constants (``flow.adc.model``): its testbench's common mode, the reference it
converts on (``Reference``), what it can quiet, the CDAC draw it calibrates on, and the reference
study's decoupling, budget and grids (``REFERENCE_*``); and the campaign's
(``flow.adc.sweep.campaign``): its rates, input frequencies and conversion counts, the mismatch
study's coefficients, the levels of the noise over the input, the Hsu study's quiet sources, the
ENOB ladder (``LADDER``, its captures ``LADDER_NAMES``) and one capture (``Capture``: its testbench
and the model's knobs); and the record's figures' (``flow.adc.plots``): the decision paths drawn and
the Pelgrom coefficients the predicted mismatch is drawn over.
"""

from dataclasses import dataclass

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import G, m
from pydantic import PositiveInt

from flow import capdac, comp, pipeline, samp


@h.paramclass
class Params:
    """ADC parameters."""

    # Top-level ADC parameter
    adc_bits = h.Param(dtype=PositiveInt, desc="Nominal normalized ADC resolution", default=12)
    # Component parameters
    cdac = h.Param(dtype=capdac.Params, desc="CDAC parameters", default=capdac.Params())
    samp = h.Param(dtype=samp.Params, desc="Sampler parameters", default=samp.FRIDA1)
    comp = h.Param(dtype=comp.Params, desc="Comparator parameters", default=comp.FRIDA1)

    def __post_init__(self) -> None:
        # the converter resolves what its array is sized and weighted for; any array of capdac's is
        # one, its model, its blocks' geometry and its netlist (flow.adc.subckt.Adc: two of the
        # array's sides) capdac's
        if self.adc_bits != self.cdac.bits:
            raise ValueError(f"a {self.adc_bits}-bit converter takes a {self.adc_bits}-bit array, not {self.cdac.bits}")


pipeline.Params.register(Params)

# The design space's resolutions (``flow.adc.sweep.converters``: a space each); FRIDA-1's converter:
# its array (``capdac.frida1``: 12 bits in 16 stages, MSB redistribution with 5 extra cycles, at two
# of the 12-bit least switched capacitance; capdac's defaults)
RESOLUTIONS = (10, 12, 14)
FRIDA1_BITS = 12
FRIDA1_ARRAY = capdac.frida1()


@h.paramclass
class TbParams:
    """Parameters which determine one generated ADC testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=10e-12
    )
    view = h.Param(dtype=str, desc="ADC implementation: frida1, frida2, or hdl21gen", default="hdl21gen")
    pex_cell = h.Param(
        dtype=str,
        desc="Calibre-extracted cell; empty selects adc_1layer_radix17 for frida1",
        default="",
    )
    dut = h.Param(dtype=Params, desc="ADC DUT parameters", default=Params())
    symbol_rate = h.Param(dtype=h.Scalar, desc="DDR symbol rate", default=1.6 * G)
    conversions = h.Param(dtype=int, desc="Number of conversions", default=10_000)
    en_init = h.Param(dtype=int, desc="Enable initialization clock", default=1)
    en_samp_p = h.Param(dtype=int, desc="Enable positive sampling clock", default=1)
    en_samp_n = h.Param(dtype=int, desc="Enable negative sampling clock", default=1)
    en_comp = h.Param(dtype=int, desc="Enable comparator clock", default=1)
    en_update = h.Param(dtype=int, desc="Enable DAC-update clock", default=1)
    dac_mode = h.Param(dtype=int, desc="Select comparator-driven DAC mode", default=1)
    dac_diffcaps = h.Param(
        dtype=int,
        desc="Enable differential capacitor controls (no effect in the generated ADC, which wires them in)",
        default=1,
    )
    dac_astate_p = h.Param(dtype=tuple[int, ...], desc="C0-first positive DAC A state", default=(0, 1) * 8)
    dac_bstate_p = h.Param(dtype=tuple[int, ...], desc="C0-first positive DAC B state", default=(0,) * 16)
    dac_astate_n = h.Param(dtype=tuple[int, ...], desc="C0-first negative DAC A state", default=(0, 1) * 8)
    dac_bstate_n = h.Param(dtype=tuple[int, ...], desc="C0-first negative DAC B state", default=(0,) * 16)
    vdd_a = h.Param(dtype=h.Vdc.Params, desc="Analog supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_d = h.Param(dtype=h.Vdc.Params, desc="Digital supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_dac = h.Param(dtype=h.Vdc.Params, desc="DAC supply", default=h.Vdc.Params(dc=1200 * m))
    supply_series_resistance_ohm = h.Param(
        dtype=float,
        desc="Lumped bond-wire and chip-level PDN series resistance per supply rail",
        default=0.0,
    )
    supply_series_inductance_h = h.Param(
        dtype=float,
        desc="Lumped bond-wire and chip-level PDN series inductance per supply rail",
        default=0.0,
    )
    supply_decoupling_capacitance_f = h.Param(
        dtype=float,
        desc="Local chip-level decoupling capacitance per supply rail",
        default=0.0,
    )
    supply_noise_rms_v = h.Param(
        dtype=tuple[float, ...],
        desc="Added RMS noise on VDD_A, VDD_D, and VDD_DAC",
        default=(0.0, 0.0, 0.0),
    )
    supply_noise_bandwidth_hz = h.Param(
        dtype=float,
        desc="Flat bandwidth over which each added supply-noise RMS value is defined",
        default=25.0e9,
    )
    vin_cm = h.Param(dtype=h.Vdc.Params, desc="Input common mode", default=h.Vdc.Params(dc=700 * m))
    vin_diff = h.Param(
        dtype=h.Vdc.Params | h.Vsin.Params | h.Vpwl.Params | hs.LinearSweep,
        desc="Differential input stimulus",
        default=h.Vdc.Params(dc=0.0),
    )
    # the default recipe's rows (sim.symbol256_init8_samp16_comp11110000_logic00001111; test_params.py)
    seq_init_pattern = h.Param(
        dtype=str,
        desc="INIT sequence",
        default=(
            "11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_samp_pattern = h.Param(
        dtype=str,
        desc="SAMP sequence",
        default=(
            "00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_comp_pattern = h.Param(
        dtype=str,
        desc="COMP sequence",
        default=(
            "00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 "
            "00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 "
            "00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_logic_pattern = h.Param(
        dtype=str,
        desc="LOGIC sequence",
        default=(
            "00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 "
            "11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 "
            "11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    # TODO: matching a building-block Monte Carlo result to a higher-level run
    # by seed and iteration alone is not valid; the two runs draw independent
    # mismatch. Netlisting does not consume these fields yet.
    mc_seed = h.Param(dtype=int | None, desc="Spectre Monte Carlo seed; None for nominal", default=None)
    mc_index = h.Param(dtype=int | None, desc="Spectre Monte Carlo iteration; None for nominal", default=None)


# FRIDA's input common mode at TSMC65's 1.2 V supply, scaled with the PDK's supply elsewhere
VIN_CM_FRACTION = 0.700 / 1.2


@dataclass(frozen=True)
class Reference:
    """The DAC's reference (VDD_DAC) as its buffer would supply it: a driver of output resistance
    ``r_ohm`` onto a decoupling capacitance ``c_f`` (each switch draws its charge from the
    capacitance, the driver restores it with R C: a code-dependent dip at the next comparison), and
    white noise ``noise_v`` RMS at the node at each decision. Zero is ideal: no dip without both,
    no noise."""

    r_ohm: float = 0.0
    c_f: float = 0.0
    noise_v: float = 0.0


IDEAL_REFERENCE = Reference()
# what ``flow.adc.model.Model.behavioral``'s ``quiet`` silences or makes ideal
QUIET = frozenset({"sampler", "sampling", "comparator", "comparator_noise"})
# the array a converter calibrates on (``flow.adc.model.Model.drawn``): of its DAC's Monte Carlo
# (``flow.capdac.sweep.runs``), the middle condition's draw (0.5 %·sqrt(fF); no gradient, as its
# plates stand at no place until the layout places them) at the 90th percentile of what no
# calibration recovers
DRAWN_RUN = "mc_a5"
DRAWN_PERCENTILE = 90.0

# The reference study (``flow.adc.model.Model.reference_requirements``): the share of the
# converter's footprint its layout fills with decap cells (front-end-of-line area under the routing)
DECAP_COVERAGE = 0.30
# the share of the quantization noise power each of the two may add (together all of it)
REFERENCE_SHARE = 0.5
# the figures' grids, two points a decade: the white noise at the node (V RMS) and the driver's
# output resistance (ohm)
REFERENCE_NOISE_V = np.logspace(-6, -2, 9)
REFERENCE_R_OUT_OHM = np.logspace(-1, 5, 13)
# halvings of a grid step in the bisection (to about 4 % of the value)
REFERENCE_HALVINGS = 5
# what the reference's study silences or makes ideal in the converter (of ``QUIET``)
REFERENCE_QUIET = ("sampler", "sampling", "comparator")

# The record's figures (``flow.adc.plots``): the decision paths drawn, the last decisions' zoom and at
# most this many distinct paths a plot; and the predicted mismatch's Pelgrom coefficients, 0.02 to
# 1 %·sqrt(fF), as fractions
FINAL_DECISIONS = 6
MAX_PATHS = 400
PELGROM_AXIS = np.geomspace(0.0002, 0.01, 41)
# A top plate has settled (``flow.adc.analysis.analyze_cdac_settling``) once it stays within this of
# its final value, well under an LSB of the reference; its figures mark it
CDAC_SETTLING_TOLERANCE_V = 1e-3

# The campaign (``flow.adc.sweep.campaign``): every capture the record needs.
# 1 to 10 MS/s in 1 MS/s steps, the rates the ADC is meant to run at, then on to 100 MS/s: where
# the DAC's settling or the comparator's delay starts to cost codes, and whether redundancy recovers
# them
RATES_HZ = tuple(rate * 1e6 for rate in (*range(1, 11), 12, 15, 20, 25, 30, 40, 50, 60, 80, 100))
FIN_RATES_HZ = (2e6, 6e6, 10e6)
# odd cycle counts in 8,192 conversions, coprime with it, from 0.4 % to 49 % of the rate
FIN_CYCLES = (31, 101, 257, 509, 1021, 1531, 2039, 3067, 4013)
SINE_CONVERSIONS = 8_192
RAMP_CONVERSIONS = 1 << 19
NOMINAL_RATE_HZ = 10e6
# Harpe's unit-length MOM mismatch (0.10 %·sqrt(fF)): the predicted mismatch statistics' coefficient
UNIT_MISMATCH = 0.0010
# the mismatch study's Pelgrom coefficients: Harpe's 0.10 % (JSSC 2018, unit-length MOM, 65 nm)
# and Tripathi and Murmann's 0.85 % (TCAS-I 2014, single-layer lateral MOM), around and between
MISMATCH_COEFFICIENTS = (0.0005, 0.0010, 0.0020, 0.0040, 0.0085)
# draws a coefficient where the campaign is asked for the Monte Carlo (``mismatch_draws``); none by
# default: the figures predict the mismatch's statistics from the capacitances instead
MISMATCH_DRAWS = 0
VALIDATION_DRAWS = 25
MISMATCH_CONVERSIONS = 1 << 16
# the noise over the input: this many DC levels over +-INPUT_NOISE_SPAN of the full scale, each held
# for INPUT_NOISE_CONVERSIONS conversions
INPUT_NOISE_LEVELS = 9
INPUT_NOISE_SPAN = 0.9
INPUT_NOISE_CONVERSIONS = 512
# the Hsu study's noise switched off, the comparator's delay kept (or, for the reference, ideal)
HSU_QUIET = ("sampling", "comparator_noise")
HSU_REFERENCE_QUIET = ("sampling", "comparator")
# the ENOB ladder: the nominal rate's sine converted with the model's impairments added one at a
# time, each step (its key in the metrics, its label, the sources it keeps quiet, as
# ``Model.behavioral``'s, and its settling's scale) the last one with one more: the tracking
# error of the sampler's on-resistance, its kT/C noise and aperture jitter, the DAC's settling (with
# its drivers' delay), the comparator's delay (a late decision holds the last bit) and its noise,
# on an ideal reference (the reference study, Model.reference_requirements, varies it). The last step is the
# converter as the sine at the nominal rate has it.
LADDER = (
    ("quantization", "Quantization", ("sampler", "sampling", "comparator"), 0.0),
    ("sampler", "+ Sampling error", ("sampling", "comparator"), 0.0),
    ("sampling_noise", "+ Sampling noise", ("comparator",), 0.0),
    ("settling", "+ DAC settling", ("comparator",), 1.0),
    ("comparator_timing", "+ Comp. timing", ("comparator_noise",), 1.0),
    ("comparator_noise", "+ Comp. noise", (), 1.0),
)

# the ENOB ladder's captures by name, a step each (``LADDER``), quantization alone first: the last,
# every impairment on, is the sine at the nominal rate (``rate_10``)
LADDER_NAMES = (*(f"ladder_{step}" for step in range(len(LADDER) - 1)), f"rate_{NOMINAL_RATE_HZ / 1e6:g}")


@dataclass(frozen=True)
class Capture:
    """One capture: its testbench, its capacitor draw (``seed``, at ``unit_mismatch``; or the CDAC's
    SPICE draw, ``drawn``), its noise seed, whether it has noise at all, the sources it silences
    otherwise (``quiet``, as ``Model.behavioral``'s) and its DAC settling time constants' scale
    (1: the array's own, 0: ideal settling, the Hsu study's reference)."""

    tb: TbParams
    seed: int = 0
    noise_seed: int | None = None
    unit_mismatch: float = 0.0
    noise_free: bool = False  # no sampling or comparator noise: the capacitors' nonlinearity alone
    quiet: tuple[str, ...] = ()
    tau_scale: float = 1.0
    drawn: bool = False
