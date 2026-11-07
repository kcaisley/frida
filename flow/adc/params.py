"""The ADC's parameters: its design (``Params``, every combination of which builds; FRIDA-1's four
fabricated converters, ``Fabricated``, each one of them, ``valid`` only in TSMC65) and one run of it
(``TbParams``: its PDK and design, which simulator converts it and on which top, its stimulus, its
supplies, the sequencer's four lines as ``h.Vbit`` sources playing a recipe's rows, ``Recipe``, and
the behavioral converter's knobs); the design space's resolutions and FRIDA-1's converter in it
(``RESOLUTIONS``, ``FRIDA1_*``); the behavioral converter's constants (``flow.adc.sim``'s): its
testbench's common mode, what it can quiet (``Quiet``), the CDAC draw it calibrates on, and the
reference study's decoupling, budget and grids (``REFERENCE_*``); and the campaign's
(``flow.adc.sweep.runs``): its rates, input frequencies and conversion counts, the mismatch
study's coefficients, the levels of the noise over the input, the Hsu study's quiet sources and the
ENOB ladder (``LADDER``, its captures ``LADDER_NAMES``); and the record's figures'
(``flow.adc.plots``): the decision paths drawn and the Pelgrom coefficients the predicted mismatch is
drawn over.

The sequencer's recipes (``Recipe``) are its four rows, INIT, SAMP, COMP and LOGIC, each a binary
pattern of symbols: names describe period length, INIT/SAMP widths, and recurring SAR words relative
to COMP rising. Every recipe starts at INIT rising; all four rows share that origin. The continuous
160-symbol recipes give every terminal COMP pulse a complete word by shortening the historical
24-symbol sample. Historical captures may retain a different cyclic RAM phase. Their
INIT-associated LOGIC pulse spans symbols 2--5; padded 256-symbol recipes retain the historical
one-symbol marker at symbol 3. A run plays its rows on four bit sources (``TbParams.seq_*``, an
``h.Vbit`` each: one symbol a period, between ground and the digital supply, repeated from the
start); ``TbParams.sequenced`` sets them, ``TbParams.continuous`` to the generated converter's
continuous rows at any stage count.
"""

import math
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from itertools import pairwise
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import m, p
from pydantic import PositiveInt

from flow import capdac, comp, pipeline, samp


class Fabricated(Enum):
    """FRIDA-1's four fabricated converters: its DAC drawn in one or two metal layers, at radix 17
    (capdac's defaults: MSB redistribution with 5 extra cycles) or 20. Each is one ``Params``
    (``params``), simulated on its extraction (``Extraction``) and laid out from its tape-out
    sources."""

    FRIDA1_1LAYER_RADIX17 = auto()
    FRIDA1_1LAYER_RADIX20 = auto()
    FRIDA1_2LAYER_RADIX17 = auto()
    FRIDA1_2LAYER_RADIX20 = auto()

    @property
    def layers(self) -> int:
        """The metal layers its DAC's capacitors are drawn in."""
        match self:
            case Fabricated.FRIDA1_1LAYER_RADIX17 | Fabricated.FRIDA1_1LAYER_RADIX20:
                return 1
            case Fabricated.FRIDA1_2LAYER_RADIX17 | Fabricated.FRIDA1_2LAYER_RADIX20:
                return 2

    @property
    def radix(self) -> int:
        """Its DAC's radix, as the tape-out names it."""
        match self:
            case Fabricated.FRIDA1_1LAYER_RADIX17 | Fabricated.FRIDA1_2LAYER_RADIX17:
                return 17
            case Fabricated.FRIDA1_1LAYER_RADIX20 | Fabricated.FRIDA1_2LAYER_RADIX20:
                return 20

    @property
    def weights(self) -> tuple[int, ...] | None:
        """Its DAC's weights, C15 first: capdac's own (None) at radix 17, the radix-20 array's."""
        match self.radix:
            case 17:
                return None
            case _:
                return (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)

    @property
    def params(self) -> "Params":
        """The converter as a design: FRIDA-1's 12 bits, sampler and comparator, on its DAC."""
        return Params(**_fabricated_parts(self), fabricated=self)


def _fabricated_parts(member: Fabricated) -> dict[str, Any]:
    """A fabricated converter's parts: what its ``Params`` holds besides ``fabricated``."""
    return {
        "adc_bits": FRIDA1_BITS,
        "cdac": capdac.Params(weights=member.weights),
        "samp": samp.FRIDA1,
        "comp": comp.FRIDA1,
    }


@h.paramclass
class Params:
    """ADC parameters."""

    # Top-level ADC parameter
    adc_bits = h.Param(dtype=PositiveInt, desc="Nominal normalized ADC resolution", default=12)
    # Component parameters
    cdac = h.Param(dtype=capdac.Params, desc="CDAC parameters", default=capdac.Params())
    samp = h.Param(dtype=samp.Params, desc="Sampler parameters", default=samp.FRIDA1)
    comp = h.Param(dtype=comp.Params, desc="Comparator parameters", default=comp.FRIDA1)
    fabricated = h.Param(
        dtype=Fabricated | None, desc="FRIDA-1's fabricated converter this design is; None if generated", default=None
    )

    def __post_init__(self) -> None:
        # the converter resolves what its array is sized and weighted for; any array of capdac's is
        # one, its model, its blocks' geometry and its netlist (flow.adc.subckt.netlist: two of the
        # array's sides) capdac's
        if self.adc_bits != self.cdac.bits:
            raise ValueError(f"a {self.adc_bits}-bit converter takes a {self.adc_bits}-bit array, not {self.cdac.bits}")
        # a fabricated converter is its tape-out's, part for part
        if self.fabricated is not None:
            parts = _fabricated_parts(self.fabricated)
            if any(getattr(self, name) != value for name, value in parts.items()):
                raise ValueError(f"{self.fabricated.name} is FRIDA-1's converter: its parts are {parts}")


pipeline.Params.register(Params)


def valid(params: Params, pdk: str) -> bool:
    """Whether ``params`` is a design in ``pdk``: a fabricated converter in TSMC65 alone, its
    tape-out's process; a generated one in any."""
    return params.fabricated is None or pdk == "tsmc65"


# The design space's resolutions (``flow.adc.sweep.converters``: a space each); FRIDA-1's converter:
# its array (``capdac.frida1``: 12 bits in 16 stages, MSB redistribution with 5 extra cycles, at two
# of the 12-bit least switched capacitance; capdac's defaults)
RESOLUTIONS = (10, 12, 14)
FRIDA1_BITS = 12
FRIDA1_ARRAY = capdac.frida1()


class Simulator(Enum):
    """What converts a run: the behavioral converter (``flow.adc.sim``'s), or Spectre on the
    netlist of its top (``flow.adc.sim.simulate``)."""

    BEHAVIORAL = auto()
    SPECTRE = auto()


class Extraction(Enum):
    """The extraction a fabricated converter's Spectre run simulates: the tape-out's own, or the
    one its layout's signoff gives (``flow.adc.layout``)."""

    TAPEOUT = auto()
    SIGNOFF = auto()


class Probes(Enum):
    """What a Spectre run saves: every probed node, or the codes alone (the sequencer, the
    comparator's output, the input and the supplies' currents)."""

    NODES = auto()
    CODES = auto()


class Quiet(Enum):
    """What the behavioral converter can silence or make ideal: the sampling noise (kT/C and the
    aperture jitter), the sampler (a perfect track-and-hold, no on-resistance), the comparator (no
    noise, never late) or its noise alone (its delay stays)."""

    SAMPLING = auto()
    SAMPLER = auto()
    COMPARATOR = auto()
    COMPARATOR_NOISE = auto()


class Recipe(Enum):
    """The sequencer's complete four-row recipes by name (the module's docstring); no aliases or
    generated cross products. ``rows`` gives a recipe's (INIT, SAMP, COMP, LOGIC)."""

    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC01111000 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00111100 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00011110 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC10000111 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11000011 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11100001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC10000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC11000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC11100001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00001111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC10000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC11000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC11100001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00001111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC10000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11100001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00001111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000001 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC10000111 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC11000011 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC11100001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00001111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC10000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC11000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC11100001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00001111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC10000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC11000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC11100001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00001111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC10000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC11000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC11100001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00001111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000001 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC10000111 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC11000011 = auto()
    SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC11100001 = auto()
    SYMBOL256_INIT8_SAMP16_COMP11111100_LOGIC00000010 = auto()
    SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000010 = auto()
    SYMBOL160_INIT4_SAMP24_COMP11111100_LOGIC00000010 = auto()

    @property
    def rows(self) -> tuple[str, str, str, str]:
        """The recipe's binary rows, INIT, SAMP, COMP and LOGIC, a symbol a character."""
        return _recipes[self]

    @property
    def conversion_symbols(self) -> int:
        """Its conversion's symbols (``TbParams.conversion_symbols``)."""
        return _conversion_symbols(self.rows)


# INIT channel patterns.
_init256_start0_width8 = (
    "11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_init160_start0_width4 = (
    "11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 "
).replace(" ", "")

_init256_start0_width4 = (
    "11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")


# SAMP channel patterns.
_samp256_start8_width16 = (
    "00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_samp160_start4_width20 = (
    "00001111 11111111 11111111 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 "
).replace(" ", "")

_samp256_start4_width20 = (
    "00001111 11111111 11111111 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_samp160_start4_width24 = (
    "00001111 11111111 11111111 11110000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 "
).replace(" ", "")


# COMP channel patterns.
_comp256_start28_width4_train36_width4_pulses16 = (
    "00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp160_start24_width4_train32_width4_pulses16 = (
    "00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 "
).replace(" ", "")

_comp160_start24_width5_train32_width5_pulses16 = (
    "00000000 00000000 00000000 11111000 11111000 11111000 11111000 11111000 "
    "11111000 11111000 11111000 11111000 11111000 11111000 11111000 11111000 "
    "11111000 11111000 11111000 11111000 "
).replace(" ", "")

_comp160_start24_width6_train32_width6_pulses16 = (
    "00000000 00000000 00000000 11111100 11111100 11111100 11111100 11111100 "
    "11111100 11111100 11111100 11111100 11111100 11111100 11111100 11111100 "
    "11111100 11111100 11111100 11111100 "
).replace(" ", "")

_comp160_start24_width7_train32_width7_pulses16 = (
    "00000000 00000000 00000000 11111110 11111110 11111110 11111110 11111110 "
    "11111110 11111110 11111110 11111110 11111110 11111110 11111110 11111110 "
    "11111110 11111110 11111110 11111110 "
).replace(" ", "")

_comp256_start24_width4_train32_width4_pulses16 = (
    "00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp256_start24_width5_train32_width5_pulses16 = (
    "00000000 00000000 00000000 11111000 11111000 11111000 11111000 11111000 "
    "11111000 11111000 11111000 11111000 11111000 11111000 11111000 11111000 "
    "11111000 11111000 11111000 11111000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp256_start24_width6_train32_width6_pulses16 = (
    "00000000 00000000 00000000 11111100 11111100 11111100 11111100 11111100 "
    "11111100 11111100 11111100 11111100 11111100 11111100 11111100 11111100 "
    "11111100 11111100 11111100 11111100 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp256_start24_width7_train32_width7_pulses16 = (
    "00000000 00000000 00000000 11111110 11111110 11111110 11111110 11111110 "
    "11111110 11111110 11111110 11111110 11111110 11111110 11111110 11111110 "
    "11111110 11111110 11111110 11111110 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp256_start28_width6_train36_width6_pulses16 = (
    "00000000 00000000 00000000 00001111 11001111 11001111 11001111 11001111 "
    "11001111 11001111 11001111 11001111 11001111 11001111 11001111 11001111 "
    "11001111 11001111 11001111 11001111 11000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_comp160_start28_width6_train36_width6_pulses16 = (
    "00000000 00000000 00000000 00001111 11001111 11001111 11001111 11001111 "
    "11001111 11001111 11001111 11001111 11001111 11001111 11001111 11001111 "
    "11001111 11001111 11001111 11001111 "
).replace(" ", "")


# LOGIC channel patterns.
_logic256_start1_width4_train29_width4_pulses16 = (
    "01111000 00000000 00000000 00000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start2_width4_train30_width4_pulses16 = (
    "00111100 00000000 00000000 00000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width4_train31_width4_pulses16 = (
    "00011110 00000000 00000000 00000001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start4_width4_train32_width4_pulses16 = (
    "00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 "
    "11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start5_width4_train33_width4_pulses16 = (
    "00000111 10000000 00000000 00000000 01111000 01111000 01111000 01111000 "
    "01111000 01111000 01111000 01111000 01111000 01111000 01111000 01111000 "
    "01111000 01111000 01111000 01111000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start6_width4_train34_width4_pulses16 = (
    "00000011 11000000 00000000 00000000 00111100 00111100 00111100 00111100 "
    "00111100 00111100 00111100 00111100 00111100 00111100 00111100 00111100 "
    "00111100 00111100 00111100 00111100 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start7_width4_train35_width4_pulses16 = (
    "00000001 11100000 00000000 00000000 00011110 00011110 00011110 00011110 "
    "00011110 00011110 00011110 00011110 00011110 00011110 00011110 00011110 "
    "00011110 00011110 00011110 00011110 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic160_start2_width4_train28_width4_pulses16 = (
    "00111100 00000000 00000000 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00000000 "
).replace(" ", "")

_logic160_start2_width4_train29_width3_pulses16 = (
    "00111100 00000000 00000000 00000111 00000111 00000111 00000111 00000111 "
    "00000111 00000111 00000111 00000111 00000111 00000111 00000111 00000111 "
    "00000111 00000111 00000111 00000000 "
).replace(" ", "")

_logic160_start2_width4_train30_width2_pulses16 = (
    "00111100 00000000 00000000 00000011 00000011 00000011 00000011 00000011 "
    "00000011 00000011 00000011 00000011 00000011 00000011 00000011 00000011 "
    "00000011 00000011 00000011 00000000 "
).replace(" ", "")

_logic160_start2_width4_train31_width1_pulses16 = (
    "00111100 00000000 00000000 00000001 00000001 00000001 00000001 00000001 "
    "00000001 00000001 00000001 00000001 00000001 00000001 00000001 00000001 "
    "00000001 00000001 00000001 00000000 "
).replace(" ", "")

_logic160_start2_width4_train29_width4_pulses16 = (
    "00111100 00000000 00000000 00000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000000 "
).replace(" ", "")

_logic160_start2_width4_train30_width4_pulses16 = (
    "00111100 00000000 00000000 00000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000000 "
).replace(" ", "")

_logic160_start2_width4_train31_width4_pulses16 = (
    "00111100 00000000 00000000 00000001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100000 "
).replace(" ", "")

_logic256_start3_width1_train28_width4_pulses16 = (
    "00010000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 "
    "00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train29_width3_pulses16 = (
    "00010000 00000000 00000000 00000111 00000111 00000111 00000111 00000111 "
    "00000111 00000111 00000111 00000111 00000111 00000111 00000111 00000111 "
    "00000111 00000111 00000111 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train30_width2_pulses16 = (
    "00010000 00000000 00000000 00000011 00000011 00000011 00000011 00000011 "
    "00000011 00000011 00000011 00000011 00000011 00000011 00000011 00000011 "
    "00000011 00000011 00000011 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train31_width1_pulses16 = (
    "00010000 00000000 00000000 00000001 00000001 00000001 00000001 00000001 "
    "00000001 00000001 00000001 00000001 00000001 00000001 00000001 00000001 "
    "00000001 00000001 00000001 00000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train29_width4_pulses16 = (
    "00010000 00000000 00000000 00000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000111 10000111 10000111 10000111 10000111 "
    "10000111 10000111 10000111 10000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train30_width4_pulses16 = (
    "00010000 00000000 00000000 00000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000011 11000011 11000011 11000011 11000011 "
    "11000011 11000011 11000011 11000000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start3_width1_train31_width4_pulses16 = (
    "00010000 00000000 00000000 00000001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100001 11100001 11100001 11100001 11100001 "
    "11100001 11100001 11100001 11100000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic256_start6_width4_train34_width1_pulses16 = (
    "00000011 11000000 00000000 00000000 00100000 00100000 00100000 00100000 "
    "00100000 00100000 00100000 00100000 00100000 00100000 00100000 00100000 "
    "00100000 00100000 00100000 00100000 00000000 00000000 00000000 00000000 "
    "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
).replace(" ", "")

_logic160_start2_width4_train34_width1_pulses16 = (
    "00111100 00000000 00000000 00000000 00100000 00100000 00100000 00100000 "
    "00100000 00100000 00100000 00100000 00100000 00100000 00100000 00100000 "
    "00100000 00100000 00100000 00100000 "
).replace(" ", "")

_logic160_start2_width4_train30_width1_pulses16 = (
    "00111100 00000000 00000000 00000010 00000010 00000010 00000010 00000010 "
    "00000010 00000010 00000010 00000010 00000010 00000010 00000010 00000010 "
    "00000010 00000010 00000010 00000000 "
).replace(" ", "")

# Each recipe's rows, (INIT, SAMP, COMP, LOGIC)
_recipes = {
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC01111000: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start1_width4_train29_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00111100: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start2_width4_train30_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00011110: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start3_width4_train31_width4_pulses16,
    ),
    # Historical default timing (formerly "baseline").
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start4_width4_train32_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC10000111: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start5_width4_train33_width4_pulses16,
    ),
    # Historical fixed-input control (formerly "original").
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11000011: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start6_width4_train34_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11100001: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width4_train36_width4_pulses16,
        _logic256_start7_width4_train35_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train28_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train29_width3_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train30_width2_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00000001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train31_width1_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC10000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train29_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC11000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train30_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC11100001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width4_train32_width4_pulses16,
        _logic160_start2_width4_train31_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00001111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train28_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train29_width3_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train30_width2_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC00000001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train31_width1_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC10000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train29_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC11000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train30_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC11100001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width5_train32_width5_pulses16,
        _logic160_start2_width4_train31_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00001111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train28_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train29_width3_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train30_width2_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train31_width1_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC10000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train29_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train30_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11100001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train31_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00001111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train28_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train29_width3_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train30_width2_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC00000001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train31_width1_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC10000111: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train29_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC11000011: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train30_width4_pulses16,
    ),
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC11100001: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width7_train32_width7_pulses16,
        _logic160_start2_width4_train31_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00001111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train28_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train29_width3_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train30_width2_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC00000001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train31_width1_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC10000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train29_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC11000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train30_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11110000_LOGIC11100001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width4_train32_width4_pulses16,
        _logic256_start3_width1_train31_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00001111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train28_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train29_width3_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train30_width2_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC00000001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train31_width1_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC10000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train29_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC11000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train30_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111000_LOGIC11100001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width5_train32_width5_pulses16,
        _logic256_start3_width1_train31_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00001111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train28_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train29_width3_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train30_width2_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC00000001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train31_width1_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC10000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train29_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC11000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train30_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111100_LOGIC11100001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width6_train32_width6_pulses16,
        _logic256_start3_width1_train31_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00001111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train28_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train29_width3_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train30_width2_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC00000001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train31_width1_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC10000111: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train29_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC11000011: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train30_width4_pulses16,
    ),
    Recipe.SYMBOL256_INIT4_SAMP20_COMP11111110_LOGIC11100001: (
        _init256_start0_width4,
        _samp256_start4_width20,
        _comp256_start24_width7_train32_width7_pulses16,
        _logic256_start3_width1_train31_width4_pulses16,
    ),
    # Historical extended-COMP comparison.
    Recipe.SYMBOL256_INIT8_SAMP16_COMP11111100_LOGIC00000010: (
        _init256_start0_width8,
        _samp256_start8_width16,
        _comp256_start28_width6_train36_width6_pulses16,
        _logic256_start6_width4_train34_width1_pulses16,
    ),
    # Keep the 100-ns period and give the final COMP pulse all six high symbols.
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000010: (
        _init160_start0_width4,
        _samp160_start4_width20,
        _comp160_start24_width6_train32_width6_pulses16,
        _logic160_start2_width4_train30_width1_pulses16,
    ),
    # Historical continuous 100-ns comparison at 1600 MBd.
    Recipe.SYMBOL160_INIT4_SAMP24_COMP11111100_LOGIC00000010: (
        _init160_start0_width4,
        _samp160_start4_width24,
        _comp160_start28_width6_train36_width6_pulses16,
        _logic160_start2_width4_train34_width1_pulses16,
    ),
}

# the sequencer's four lines, the ADC's clock inputs (``flow.adc.subckt.Nets``), in the rows' order
_lines = ("seq_init", "seq_samp", "seq_comp", "seq_logic")


def _line(row: str, symbol_rate: float, high_v: float) -> h.Vbit.Params:
    """One sequencer line playing ``row`` at ``symbol_rate``: a bit source of one symbol a period,
    between ground and ``high_v``, with edges of a twentieth of a symbol (at most 100 ps), repeated
    from the start."""
    period_s = 1.0 / float(symbol_rate)
    transition_s = min(float(100 * p), period_s / 20.0)
    return h.Vbit.Params(
        data=row,
        period=period_s,
        val0=0.0,
        val1=high_v,
        delay=0.0,
        rise=transition_s,
        fall=transition_s,
        rptstart=1,
        rpttimes=-1,
    )


def _default_line(index: int) -> h.Vbit.Params:
    """A line of the default recipe at the default rate and supply."""
    return _line(Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111.rows[index], 1.6e9, 1.2)


def _conversion_symbols(rows: tuple[str, ...]) -> int:
    """INIT rise to final COMP fall, rounded up to its eight-symbol word.

    Use INIT as the word origin so a common hardware phase advance does
    not change the conversion duration. LOGIC and idle padding do not count.
    """
    comp = TbParams.from_init(rows)[2]
    if "1" not in comp:
        raise ValueError("conversion requires an active COMP pulse")
    return ((comp.rindex("1") + 1 + 7) // 8) * 8


def _continuous_rows(stages: int) -> tuple[str, str, str, str]:
    """The continuous recipe for ``stages`` capacitors: INIT 4, SAMP 20, one 8-symbol word per
    decision; COMP high for the first four symbols of each word, LOGIC for the last four, and one
    LOGIC pulse inside INIT loads the A state. For 16 stages it equals
    ``SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111``."""
    symbols = 24 + 8 * (stages + 1)
    init = "1" * 4 + "0" * (symbols - 4)
    samp = "0" * 4 + "1" * 20 + "0" * (symbols - 24)
    comp = "0" * 24 + "11110000" * (stages + 1)
    logic = "0011110000000000000000000000" + "11110000" * stages + "0000"
    return init, samp, comp, logic[:symbols]


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the ADC: the design ``params`` in ``pdk``, converted by ``simulator`` (Spectre on
    the generated netlist, or a fabricated converter's ``extraction``, which such a run requires;
    Spectre with transient noise where ``transient_noise``, its short static and dynamic checks alone
    where ``check``), its stimulus, supplies and sequencer lines, and the behavioral converter's knobs
    (``flow.adc.sim``'s: its capacitors drawn from ``mismatch_seed`` at ``unit_mismatch``, or its
    DAC's SPICE draw where ``drawn``; its noise seed, the mismatch seed where None; what it keeps
    ``quiet``; its settling time constants' scale, 1 its array's own, 0 ideal; the reference as a
    driver of output resistance ``reference_r_ohm`` onto a decoupling ``reference_c_f`` with white
    noise ``reference_noise_v`` at the node, all 0 an ideal one), which only a behavioral run takes."""

    pdk: str
    params: Params
    simulator: Simulator = Simulator.BEHAVIORAL
    extraction: Extraction | None = None
    probes: Probes = Probes.NODES
    transient_noise: bool = False
    check: bool = False
    waveform_sample_interval_s: float = 10e-12  # maximum raw step and stored waveform spacing
    symbol_rate: float = 1.6e9  # the sequencer's DDR symbol rate (Hz)
    conversions: int = 10_000
    en_init: int = 1
    en_samp_p: int = 1
    en_samp_n: int = 1
    en_comp: int = 1
    en_update: int = 1
    dac_mode: int = 1  # comparator-driven DAC mode
    # differential capacitor controls (the generated ADC wires them in: a run of it takes 1)
    dac_diffcaps: int = 1
    dac_astate_p: tuple[int, ...] = (0, 1) * 8  # C0 first
    dac_bstate_p: tuple[int, ...] = (0,) * 16
    dac_astate_n: tuple[int, ...] = (0, 1) * 8
    dac_bstate_n: tuple[int, ...] = (0,) * 16
    vdd_a: h.Vdc.Params = field(default_factory=lambda: h.Vdc.Params(dc=1200 * m))
    vdd_d: h.Vdc.Params = field(default_factory=lambda: h.Vdc.Params(dc=1200 * m))
    vdd_dac: h.Vdc.Params = field(default_factory=lambda: h.Vdc.Params(dc=1200 * m))
    # the lumped bond-wire and chip-level PDN per supply rail: series resistance and inductance, and
    # the local decoupling (all three or none)
    supply_series_resistance_ohm: float = 0.0
    supply_series_inductance_h: float = 0.0
    supply_decoupling_capacitance_f: float = 0.0
    # added RMS noise on VDD_A, VDD_D and VDD_DAC, flat over the bandwidth
    supply_noise_rms_v: tuple[float, ...] = (0.0, 0.0, 0.0)
    supply_noise_bandwidth_hz: float = 25.0e9
    vin_cm: h.Vdc.Params = field(default_factory=lambda: h.Vdc.Params(dc=700 * m))
    vin_diff: h.Vdc.Params | h.Vsin.Params | h.Vpwl.Params | hs.LinearSweep = field(
        default_factory=lambda: h.Vdc.Params(dc=0.0)
    )
    # the sequencer's four lines (``_line``), the default recipe's rows at the default rate
    seq_init: h.Vbit.Params = field(default_factory=lambda: _default_line(0))
    seq_samp: h.Vbit.Params = field(default_factory=lambda: _default_line(1))
    seq_comp: h.Vbit.Params = field(default_factory=lambda: _default_line(2))
    seq_logic: h.Vbit.Params = field(default_factory=lambda: _default_line(3))
    # TODO: matching a building-block Monte Carlo result to a higher-level run
    # by seed and iteration alone is not valid; the two runs draw independent
    # mismatch. Netlisting does not consume these fields yet.
    mc_seed: int | None = None  # Spectre Monte Carlo seed; None for nominal
    mc_index: int | None = None  # Spectre Monte Carlo iteration; None for nominal
    # the behavioral converter's knobs
    mismatch_seed: int = 0
    noise_seed: int | None = None
    unit_mismatch: float = 0.0
    quiet: frozenset[Quiet] = frozenset()
    tau_scale: float = 1.0
    drawn: bool = False
    reference_r_ohm: float = 0.0
    reference_c_f: float = 0.0
    reference_noise_v: float = 0.0

    def __post_init__(self) -> None:
        stages = self.stages
        if self.extraction is not None and (self.simulator is not Simulator.SPECTRE or self.params.fabricated is None):
            raise ValueError("an extraction is a fabricated converter's, simulated in Spectre")
        if self.simulator is Simulator.SPECTRE and self.params.fabricated is not None and self.extraction is None:
            raise ValueError(f"a Spectre run of {self.params.fabricated.name} simulates an extraction of it")
        behavioral = (
            self.mismatch_seed,
            self.noise_seed,
            self.unit_mismatch,
            self.quiet,
            self.tau_scale,
            self.drawn,
            self.reference_r_ohm,
            self.reference_c_f,
            self.reference_noise_v,
        )
        if self.simulator is not Simulator.BEHAVIORAL and behavioral != (
            0,
            None,
            0.0,
            frozenset(),
            1.0,
            False,
            0.0,
            0.0,
            0.0,
        ):
            raise ValueError("the behavioral converter's knobs are a behavioral run's")
        if self.simulator is not Simulator.SPECTRE and (self.transient_noise or self.check):
            raise ValueError("transient noise and the checks are a Spectre run's")
        if not all(isinstance(item, Quiet) for item in self.quiet):
            raise ValueError(f"quiet takes Quiet members, not {sorted(map(repr, self.quiet))}")
        if not math.isfinite(self.waveform_sample_interval_s) or self.waveform_sample_interval_s <= 0:
            raise ValueError("the waveform sample interval must be finite and positive")
        if self.conversions <= 0:
            raise ValueError("a run converts at least once")
        if not isinstance(self.symbol_rate, float):
            raise TypeError(f"the symbol rate is a float (Hz), not {type(self.symbol_rate).__name__}")
        symbol_rate = self.symbol_rate
        if not math.isfinite(symbol_rate) or symbol_rate <= 0.0:
            raise ValueError("the symbol rate must be finite and positive")
        for name in ("vdd_a", "vdd_d", "vdd_dac", "vin_cm"):
            source = getattr(self, name)
            if source.dc is None or not math.isfinite(float(source.dc)):
                raise ValueError(f"{name} must be a finite DC level")
        parasitics = (
            self.supply_series_resistance_ohm,
            self.supply_series_inductance_h,
            self.supply_decoupling_capacitance_f,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in parasitics):
            raise ValueError("the supply network's R, L and C must be finite and non-negative")
        if any(parasitics) and not all(value > 0.0 for value in parasitics):
            raise ValueError("the supply network takes its R, L and C together")
        if len(self.supply_noise_rms_v) != 3 or any(
            not math.isfinite(value) or value < 0.0 for value in self.supply_noise_rms_v
        ):
            raise ValueError("the supply noise is three finite non-negative RMS values")
        if not math.isfinite(self.supply_noise_bandwidth_hz) or self.supply_noise_bandwidth_hz <= 0.0:
            raise ValueError("the supply noise bandwidth must be finite and positive")
        for name in ("en_init", "en_samp_p", "en_samp_n", "en_comp", "en_update", "dac_mode", "dac_diffcaps"):
            if getattr(self, name) not in (0, 1):
                raise ValueError(f"{name} is 0 or 1")
        for name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
            value = getattr(self, name)
            if len(value) != stages or any(bit not in (0, 1) for bit in value):
                raise ValueError(f"{name} holds a bit for each of the {stages} capacitors")
        rows = self.rows
        if any(not row or set(row) - {"0", "1"} for row in rows):
            raise ValueError("the sequencer's rows are non-empty binary strings")
        if len({len(row) for row in rows}) != 1 or len(rows[0]) % 8:
            raise ValueError("the sequencer's rows have equal lengths of whole words")
        for name in _lines:
            line = getattr(self, name)
            if float(line.period) != 1.0 / symbol_rate:
                raise ValueError(f"{name} plays a symbol a period of the symbol rate: TbParams.sequenced sets it")
            if float(line.delay) != 0.0 or line.rptstart != 1 or line.rpttimes >= 0:
                raise ValueError(f"{name} repeats its row from the start")
        if isinstance(self.vin_diff, hs.LinearSweep):
            try:
                start, stop, step = (
                    float(value) for value in (self.vin_diff.start, self.vin_diff.stop, self.vin_diff.step)
                )
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("a staircase input takes numeric start, stop and step") from error
            if not all(math.isfinite(value) for value in (start, stop, step)) or step == 0.0:
                raise ValueError("a staircase input's start, stop and step are finite, its step not 0")
            if start != stop and (stop > start) != (step > 0):
                raise ValueError("a staircase input steps towards its stop")
            # inclusive staircase endpoints: one level a conversion
            if not math.isclose((stop - start) / step, self.conversions - 1, rel_tol=0.0, abs_tol=1e-9):
                raise ValueError("a staircase input holds one level a conversion")
            if len(rows[0]) / symbol_rate <= float(100 * p):
                raise ValueError("a staircase input's conversion is longer than its 100 ps step")

    @property
    def rows(self) -> tuple[str, str, str, str]:
        """The sequencer's rows its four lines play: INIT, SAMP, COMP and LOGIC."""
        return tuple(getattr(self, name).data for name in _lines)

    def sequenced(
        self, rows: tuple[str, str, str, str] | None = None, *, symbol_rate: float | None = None
    ) -> "TbParams":
        """This run with its sequencer's four lines playing ``rows`` (INIT, SAMP, COMP, LOGIC: a
        recipe's, ``Recipe.rows``; its own where None) at ``symbol_rate`` (its own where None),
        between ground and its digital supply."""
        rows = self.rows if rows is None else rows
        symbol_rate = self.symbol_rate if symbol_rate is None else symbol_rate
        high_v = float(self.vdd_d.dc)
        lines = {name: _line("".join(row.split()), symbol_rate, high_v) for name, row in zip(_lines, rows, strict=True)}
        return replace(self, symbol_rate=symbol_rate, **lines)

    def continuous(self, stages: int) -> "TbParams":
        """This run on the continuous recipe for ``stages`` capacitors (``_continuous_rows``), at its
        symbol rate."""
        return self.sequenced(_continuous_rows(stages))

    def advance(self, symbols: int) -> "TbParams":
        """This run with its four rows advanced by ``symbols``, together (a common phase advance)."""
        symbols %= len(self.rows[0])
        return self.sequenced(tuple(row[symbols:] + row[:symbols] for row in self.rows))  # ty: ignore[invalid-argument-type]

    @staticmethod
    def from_init(rows: tuple[str, ...]) -> tuple[str, ...]:
        """Four rows advanced to their INIT row's one rising edge, so cyclic recipes compare
        independently of their programmed phase."""
        edges = rows[0][-1] + rows[0]
        if edges.count("01") != 1:
            raise ValueError("sequence requires one INIT rising edge per period")
        shift = edges.index("01") % len(rows[0])
        return tuple(row[shift:] + row[:shift] for row in rows)

    @property
    def rows_from_init(self) -> tuple[str, ...]:
        """Its rows advanced to INIT's rise (``from_init``)."""
        return TbParams.from_init(self.rows)

    @property
    def conversion_symbols(self) -> int:
        """INIT rise to final COMP fall, rounded up to its eight-symbol word (``_conversion_symbols``)."""
        return _conversion_symbols(self.rows)

    @property
    def logic_timing(self) -> tuple[float, float]:
        """Average decision interval and median COMP-to-LOGIC delay, in symbols.

        Pair updates inside each decision interval; exclude the initialization
        pulse and the final decision, which has no SAR update.
        """
        from flow.analysis import calc

        _, _, comp_row, logic_row = self.rows
        comp_bits = np.fromiter((int(bit) for bit in comp_row), dtype=np.int8)
        logic_bits = np.fromiter((int(bit) for bit in logic_row), dtype=np.int8)
        # Prepend the cyclic predecessor and place each threshold crossing at its symbol boundary.
        symbols = np.arange(len(comp_row) + 1) - 0.5
        comp_signal = np.r_[comp_bits[-1], comp_bits]
        comp_edges = calc.cross(comp_signal, symbols, 0.5, edge="rising")
        logic_edges = calc.cross(np.r_[logic_bits[-1], logic_bits], symbols, 0.5, edge="rising")
        if len(comp_edges) < 2:
            raise ValueError("sequence requires at least two COMP rising edges")
        delays = [
            float(updates[0] - start)
            for start, stop in pairwise(comp_edges)
            if len(updates := logic_edges[(logic_edges >= start) & (logic_edges < stop)])
        ]
        if not delays:
            raise ValueError("sequence has no LOGIC rising edge between COMP decisions")
        return 1.0 / calc.frequency(comp_signal, symbols, threshold=0.5), float(np.median(delays))

    @property
    def stages(self) -> int:
        """The capacitors a side, each switched by one decision."""
        return len(capdac.Model.weights(self.params.cdac))

    @property
    def decisions(self) -> int:
        """A conversion's comparator decisions: one a stage and the last."""
        return self.stages + 1

    @property
    def sample_rate_hz(self) -> float:
        """The true sampling rate, the sequencer's idle padding included."""
        return float(self.symbol_rate) / len(self.rows[0])

    @property
    def expected_disconnect(self) -> bool:
        """Whether the run's extraction keeps the two-layer flavors' disconnected historical MOM
        layer, which their signoff accepts."""
        fabricated = self.params.fabricated
        return self.extraction is Extraction.SIGNOFF and fabricated is not None and fabricated.layers == 2


# FRIDA's input common mode at TSMC65's 1.2 V supply, scaled with the PDK's supply elsewhere
VIN_CM_FRACTION = 0.700 / 1.2


# the array a converter calibrates on (``flow.adc.sim``'s converter, its ``drawn``): of its DAC's Monte Carlo
# (``flow.capdac.sweep.runs``), the middle condition's draw (0.5 %·sqrt(fF); no gradient, as its
# plates stand at no place until the layout places them) at the 90th percentile of what no
# calibration recovers
DRAWN_RUN = "mc_a5"
DRAWN_PERCENTILE = 90.0

# The reference study (the ``ref_*`` runs of ``flow.adc.sweep.runs``, ``analyze_reference``): the
# share of the converter's footprint its layout fills with decap cells (front-end-of-line area under
# the routing)
DECAP_COVERAGE = 0.30
# the share of the quantization noise power each of the two may add (together all of it)
REFERENCE_SHARE = 0.5
# its runs' grids, two points a decade, each requirement interpolated between them: the white
# noise at the node (V RMS) and the driver's output resistance (ohm)
REFERENCE_NOISE_V = np.logspace(-6, -2, 9)
REFERENCE_R_OUT_OHM = np.logspace(-1, 5, 13)
# what the reference's study silences or makes ideal in the converter
REFERENCE_QUIET = frozenset({Quiet.SAMPLER, Quiet.SAMPLING, Quiet.COMPARATOR})

# The record's figures (``flow.adc.plots``): the decision paths drawn, the last decisions' zoom and at
# most this many distinct paths a plot; and the predicted mismatch's Pelgrom coefficients, 0.02 to
# 1 %·sqrt(fF), as fractions
FINAL_DECISIONS = 6
MAX_PATHS = 400
PELGROM_AXIS = np.geomspace(0.0002, 0.01, 41)
# A top plate has settled (``flow.adc.analysis.analyze_cdac_settling``) once it stays within this of
# its final value, well under an LSB of the reference; its figures mark it
CDAC_SETTLING_TOLERANCE_V = 1e-3

# The campaign (``flow.adc.sweep.runs``): every run the record needs.
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
# the predicted mismatch statistics' Pelgrom coefficient, 0.10 %·sqrt(fF): an assumed matching of a unit
# capacitor, not a measured one
UNIT_MISMATCH = 0.0010
# the mismatch study's Pelgrom coefficients: the assumed 0.10 % and Tripathi and Murmann's 0.85 %
# (TCAS-I 2014, single-layer lateral MOM), around and between
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
HSU_QUIET = frozenset({Quiet.SAMPLING, Quiet.COMPARATOR_NOISE})
HSU_REFERENCE_QUIET = frozenset({Quiet.SAMPLING, Quiet.COMPARATOR})
# the ENOB ladder: the nominal rate's sine converted with the model's impairments added one at a
# time, each step (its key in the metrics, its label, the sources it keeps quiet, ``Quiet``, and
# its settling's scale) the last one with one more: the tracking
# error of the sampler's on-resistance, its kT/C noise and aperture jitter, the DAC's settling (with
# its drivers' delay), the comparator's delay (a late decision holds the last bit) and its noise,
# on an ideal reference (the reference study, the ``ref_*`` runs, varies it). The last step is the
# converter as the sine at the nominal rate has it.
LADDER = (
    ("quantization", "Quantization", frozenset({Quiet.SAMPLER, Quiet.SAMPLING, Quiet.COMPARATOR}), 0.0),
    ("sampler", "+ Sampling error", frozenset({Quiet.SAMPLING, Quiet.COMPARATOR}), 0.0),
    ("sampling_noise", "+ Sampling noise", frozenset({Quiet.COMPARATOR}), 0.0),
    ("settling", "+ DAC settling", frozenset({Quiet.COMPARATOR}), 1.0),
    ("comparator_timing", "+ Comp. timing", frozenset({Quiet.COMPARATOR_NOISE}), 1.0),
    ("comparator_noise", "+ Comp. noise", frozenset(), 1.0),
)

# the ENOB ladder's captures by name, a step each (``LADDER``), quantization alone first: the last,
# every impairment on, is the sine at the nominal rate (``rate_10``)
LADDER_NAMES = (*(f"ladder_{step}" for step in range(len(LADDER) - 1)), f"rate_{NOMINAL_RATE_HZ / 1e6:g}")
