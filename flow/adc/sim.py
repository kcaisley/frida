"""ADC testbench and its Spectre run (``simulate``; the named runs that use them are
``flow.adc.sweep``'s), with the sequencer rows and the stimulus that drive them.

The sequencer's four rows (``AdcSequence``) and the complete named four-channel catalogue
(``SEQUENCES``): names describe period length, INIT/SAMP widths, and recurring SAR words relative
to COMP rising. Every catalogue sequence starts at INIT rising; all four rows share that origin.
The continuous 160-symbol recipes give every terminal COMP pulse a complete word by shortening the
historical 24-symbol sample. Historical captures may retain a different cyclic RAM phase. Their
INIT-associated LOGIC pulse spans symbols 2--5; padded 256-symbol recipes retain the historical
one-symbol marker at symbol 3. Channel rows are private; callers select complete sequences below.

The stimulus as a behavioral conversion sees it: a differential source's value over time
(``calc_source_value``) and the interface waveform a behavioral capture stores
(``build_adc_interface_wave``).
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from itertools import pairwise
from pathlib import Path
from typing import Protocol

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import p
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow import capdac, comp
from flow.adc.params import TbParams
from flow.adc.subckt import (
    Adc,
    AdcNets,
    adc_nets,
    adc_pex,
    adc_port_aliases,
    adc_stages,
    digital_netlist,
    frida1_net_aliases,
    frida2_net_aliases,
    generated_net_aliases,
)
from flow.circuit.ports import testbench_from_ports
from flow.pipeline import Wave


class SequenceParams(Protocol):
    seq_init_pattern: str
    seq_samp_pattern: str
    seq_comp_pattern: str
    seq_logic_pattern: str


@dataclass(frozen=True)
class AdcSequence:
    """Four equal-length binary rows, with optional whitespace for readability."""

    init: str
    samp: str
    comp: str
    logic: str

    @classmethod
    def from_tb_params(cls, params: SequenceParams) -> "AdcSequence":
        return cls(*(getattr(params, f"seq_{field.name}_pattern") for field in fields(cls)))

    @classmethod
    def continuous(cls, stages: int) -> "AdcSequence":
        """Return the continuous recipe for ``stages`` capacitors: INIT 4, SAMP 20, one 8-symbol word per decision.

        COMP is high for the first four symbols of each word, LOGIC for the last
        four, and one LOGIC pulse inside INIT loads the A state. For 16 stages it
        equals ``symbol160_init4_samp20_comp11110000_logic00001111``.
        """

        symbols = 24 + 8 * (stages + 1)
        init = "1" * 4 + "0" * (symbols - 4)
        samp = "0" * 4 + "1" * 20 + "0" * (symbols - 24)
        comp = "0" * 24 + "11110000" * (stages + 1)
        logic = "0011110000000000000000000000" + "11110000" * stages + "0000"
        return cls(init=init, samp=samp, comp=comp, logic=logic[:symbols])

    def as_tb_fields(self) -> dict[str, str]:
        return {f"seq_{field.name}_pattern": getattr(self, field.name) for field in fields(self)}

    def advance(self, symbols: int) -> "AdcSequence":
        """Apply the existing common phase advance to all four rows."""
        symbols %= len(self.init)
        return AdcSequence(*(row[symbols:] + row[:symbols] for row in (self.init, self.samp, self.comp, self.logic)))

    def relative_to_init(self) -> "AdcSequence":
        """Compare cyclic recipes independently of their programmed phase."""
        edges = self.init[-1] + self.init
        if edges.count("01") != 1:
            raise ValueError("sequence requires one INIT rising edge per period")
        return self.advance(edges.index("01"))

    @property
    def conversion_symbols(self) -> int:
        """INIT rise to final COMP fall, rounded up to its eight-symbol word.

        Use INIT as the word origin so a common hardware phase advance does
        not change the conversion duration. LOGIC and idle padding do not count.
        """
        comp = self.relative_to_init().comp
        if "1" not in comp:
            raise ValueError("conversion requires an active COMP pulse")
        return ((comp.rindex("1") + 1 + 7) // 8) * 8

    @property
    def logic_timing(self) -> tuple[float, float]:
        """Average decision interval and median COMP-to-LOGIC delay, in symbols.

        Pair updates inside each decision interval; exclude the initialization
        pulse and the final decision, which has no SAR update.
        """
        from flow.analysis import calc

        comp_bits = np.fromiter((int(bit) for bit in self.comp), dtype=np.int8)
        logic_bits = np.fromiter((int(bit) for bit in self.logic), dtype=np.int8)
        # Prepend the cyclic predecessor and place each threshold crossing at its symbol boundary.
        symbols = np.arange(len(self.comp) + 1) - 0.5
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

    def __post_init__(self) -> None:
        for field in fields(self):
            row = "".join(getattr(self, field.name).split())
            if not row or set(row) - {"0", "1"}:
                raise ValueError("sequence rows must be non-empty binary strings")
            object.__setattr__(self, field.name, row)
        lengths = {len(getattr(self, field.name)) for field in fields(self)}
        if len(lengths) != 1 or len(self.init) % 8:
            raise ValueError("sequence rows must have equal lengths divisible by eight")


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


# Complete four-channel sequences. No aliases or generated cross products.
symbol256_init8_samp16_comp11110000_logic01111000 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start1_width4_train29_width4_pulses16,
)

symbol256_init8_samp16_comp11110000_logic00111100 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start2_width4_train30_width4_pulses16,
)

symbol256_init8_samp16_comp11110000_logic00011110 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start3_width4_train31_width4_pulses16,
)

# Historical default timing (formerly "baseline").
symbol256_init8_samp16_comp11110000_logic00001111 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start4_width4_train32_width4_pulses16,
)

symbol256_init8_samp16_comp11110000_logic10000111 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start5_width4_train33_width4_pulses16,
)

# Historical fixed-input control (formerly "original").
symbol256_init8_samp16_comp11110000_logic11000011 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start6_width4_train34_width4_pulses16,
)

symbol256_init8_samp16_comp11110000_logic11100001 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width4_train36_width4_pulses16,
    logic=_logic256_start7_width4_train35_width4_pulses16,
)

symbol160_init4_samp20_comp11110000_logic00001111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train28_width4_pulses16,
)

symbol160_init4_samp20_comp11110000_logic00000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train29_width3_pulses16,
)

symbol160_init4_samp20_comp11110000_logic00000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train30_width2_pulses16,
)

symbol160_init4_samp20_comp11110000_logic00000001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train31_width1_pulses16,
)

symbol160_init4_samp20_comp11110000_logic10000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train29_width4_pulses16,
)

symbol160_init4_samp20_comp11110000_logic11000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train30_width4_pulses16,
)

symbol160_init4_samp20_comp11110000_logic11100001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width4_train32_width4_pulses16,
    logic=_logic160_start2_width4_train31_width4_pulses16,
)

symbol160_init4_samp20_comp11111000_logic00001111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train28_width4_pulses16,
)

symbol160_init4_samp20_comp11111000_logic00000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train29_width3_pulses16,
)

symbol160_init4_samp20_comp11111000_logic00000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train30_width2_pulses16,
)

symbol160_init4_samp20_comp11111000_logic00000001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train31_width1_pulses16,
)

symbol160_init4_samp20_comp11111000_logic10000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train29_width4_pulses16,
)

symbol160_init4_samp20_comp11111000_logic11000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train30_width4_pulses16,
)

symbol160_init4_samp20_comp11111000_logic11100001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width5_train32_width5_pulses16,
    logic=_logic160_start2_width4_train31_width4_pulses16,
)

symbol160_init4_samp20_comp11111100_logic00001111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train28_width4_pulses16,
)

symbol160_init4_samp20_comp11111100_logic00000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train29_width3_pulses16,
)

symbol160_init4_samp20_comp11111100_logic00000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train30_width2_pulses16,
)

symbol160_init4_samp20_comp11111100_logic00000001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train31_width1_pulses16,
)

symbol160_init4_samp20_comp11111100_logic10000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train29_width4_pulses16,
)

symbol160_init4_samp20_comp11111100_logic11000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train30_width4_pulses16,
)

symbol160_init4_samp20_comp11111100_logic11100001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train31_width4_pulses16,
)

symbol160_init4_samp20_comp11111110_logic00001111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train28_width4_pulses16,
)

symbol160_init4_samp20_comp11111110_logic00000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train29_width3_pulses16,
)

symbol160_init4_samp20_comp11111110_logic00000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train30_width2_pulses16,
)

symbol160_init4_samp20_comp11111110_logic00000001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train31_width1_pulses16,
)

symbol160_init4_samp20_comp11111110_logic10000111 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train29_width4_pulses16,
)

symbol160_init4_samp20_comp11111110_logic11000011 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train30_width4_pulses16,
)

symbol160_init4_samp20_comp11111110_logic11100001 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width7_train32_width7_pulses16,
    logic=_logic160_start2_width4_train31_width4_pulses16,
)

symbol256_init4_samp20_comp11110000_logic00001111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train28_width4_pulses16,
)

symbol256_init4_samp20_comp11110000_logic00000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train29_width3_pulses16,
)

symbol256_init4_samp20_comp11110000_logic00000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train30_width2_pulses16,
)

symbol256_init4_samp20_comp11110000_logic00000001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train31_width1_pulses16,
)

symbol256_init4_samp20_comp11110000_logic10000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train29_width4_pulses16,
)

symbol256_init4_samp20_comp11110000_logic11000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train30_width4_pulses16,
)

symbol256_init4_samp20_comp11110000_logic11100001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width4_train32_width4_pulses16,
    logic=_logic256_start3_width1_train31_width4_pulses16,
)

symbol256_init4_samp20_comp11111000_logic00001111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train28_width4_pulses16,
)

symbol256_init4_samp20_comp11111000_logic00000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train29_width3_pulses16,
)

symbol256_init4_samp20_comp11111000_logic00000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train30_width2_pulses16,
)

symbol256_init4_samp20_comp11111000_logic00000001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train31_width1_pulses16,
)

symbol256_init4_samp20_comp11111000_logic10000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train29_width4_pulses16,
)

symbol256_init4_samp20_comp11111000_logic11000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train30_width4_pulses16,
)

symbol256_init4_samp20_comp11111000_logic11100001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width5_train32_width5_pulses16,
    logic=_logic256_start3_width1_train31_width4_pulses16,
)

symbol256_init4_samp20_comp11111100_logic00001111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train28_width4_pulses16,
)

symbol256_init4_samp20_comp11111100_logic00000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train29_width3_pulses16,
)

symbol256_init4_samp20_comp11111100_logic00000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train30_width2_pulses16,
)

symbol256_init4_samp20_comp11111100_logic00000001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train31_width1_pulses16,
)

symbol256_init4_samp20_comp11111100_logic10000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train29_width4_pulses16,
)

symbol256_init4_samp20_comp11111100_logic11000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train30_width4_pulses16,
)

symbol256_init4_samp20_comp11111100_logic11100001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width6_train32_width6_pulses16,
    logic=_logic256_start3_width1_train31_width4_pulses16,
)

symbol256_init4_samp20_comp11111110_logic00001111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train28_width4_pulses16,
)

symbol256_init4_samp20_comp11111110_logic00000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train29_width3_pulses16,
)

symbol256_init4_samp20_comp11111110_logic00000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train30_width2_pulses16,
)

symbol256_init4_samp20_comp11111110_logic00000001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train31_width1_pulses16,
)

symbol256_init4_samp20_comp11111110_logic10000111 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train29_width4_pulses16,
)

symbol256_init4_samp20_comp11111110_logic11000011 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train30_width4_pulses16,
)

symbol256_init4_samp20_comp11111110_logic11100001 = AdcSequence(
    init=_init256_start0_width4,
    samp=_samp256_start4_width20,
    comp=_comp256_start24_width7_train32_width7_pulses16,
    logic=_logic256_start3_width1_train31_width4_pulses16,
)

# Historical extended-COMP comparison.
symbol256_init8_samp16_comp11111100_logic00000010 = AdcSequence(
    init=_init256_start0_width8,
    samp=_samp256_start8_width16,
    comp=_comp256_start28_width6_train36_width6_pulses16,
    logic=_logic256_start6_width4_train34_width1_pulses16,
)

# Historical continuous 100-ns comparison at 1600 MBd.
symbol160_init4_samp24_comp11111100_logic00000010 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width24,
    comp=_comp160_start28_width6_train36_width6_pulses16,
    logic=_logic160_start2_width4_train34_width1_pulses16,
)

# Keep the 100-ns period and give the final COMP pulse all six high symbols.
symbol160_init4_samp20_comp11111100_logic00000010 = AdcSequence(
    init=_init160_start0_width4,
    samp=_samp160_start4_width20,
    comp=_comp160_start24_width6_train32_width6_pulses16,
    logic=_logic160_start2_width4_train30_width1_pulses16,
)


# Flat catalogue for callers that select several complete sequences.
SEQUENCES = (
    ("symbol256_init8_samp16_comp11110000_logic01111000", symbol256_init8_samp16_comp11110000_logic01111000),
    ("symbol256_init8_samp16_comp11110000_logic00111100", symbol256_init8_samp16_comp11110000_logic00111100),
    ("symbol256_init8_samp16_comp11110000_logic00011110", symbol256_init8_samp16_comp11110000_logic00011110),
    ("symbol256_init8_samp16_comp11110000_logic00001111", symbol256_init8_samp16_comp11110000_logic00001111),
    ("symbol256_init8_samp16_comp11110000_logic10000111", symbol256_init8_samp16_comp11110000_logic10000111),
    ("symbol256_init8_samp16_comp11110000_logic11000011", symbol256_init8_samp16_comp11110000_logic11000011),
    ("symbol256_init8_samp16_comp11110000_logic11100001", symbol256_init8_samp16_comp11110000_logic11100001),
    ("symbol160_init4_samp20_comp11110000_logic00001111", symbol160_init4_samp20_comp11110000_logic00001111),
    ("symbol160_init4_samp20_comp11110000_logic00000111", symbol160_init4_samp20_comp11110000_logic00000111),
    ("symbol160_init4_samp20_comp11110000_logic00000011", symbol160_init4_samp20_comp11110000_logic00000011),
    ("symbol160_init4_samp20_comp11110000_logic00000001", symbol160_init4_samp20_comp11110000_logic00000001),
    ("symbol160_init4_samp20_comp11110000_logic10000111", symbol160_init4_samp20_comp11110000_logic10000111),
    ("symbol160_init4_samp20_comp11110000_logic11000011", symbol160_init4_samp20_comp11110000_logic11000011),
    ("symbol160_init4_samp20_comp11110000_logic11100001", symbol160_init4_samp20_comp11110000_logic11100001),
    ("symbol160_init4_samp20_comp11111000_logic00001111", symbol160_init4_samp20_comp11111000_logic00001111),
    ("symbol160_init4_samp20_comp11111000_logic00000111", symbol160_init4_samp20_comp11111000_logic00000111),
    ("symbol160_init4_samp20_comp11111000_logic00000011", symbol160_init4_samp20_comp11111000_logic00000011),
    ("symbol160_init4_samp20_comp11111000_logic00000001", symbol160_init4_samp20_comp11111000_logic00000001),
    ("symbol160_init4_samp20_comp11111000_logic10000111", symbol160_init4_samp20_comp11111000_logic10000111),
    ("symbol160_init4_samp20_comp11111000_logic11000011", symbol160_init4_samp20_comp11111000_logic11000011),
    ("symbol160_init4_samp20_comp11111000_logic11100001", symbol160_init4_samp20_comp11111000_logic11100001),
    ("symbol160_init4_samp20_comp11111100_logic00001111", symbol160_init4_samp20_comp11111100_logic00001111),
    ("symbol160_init4_samp20_comp11111100_logic00000111", symbol160_init4_samp20_comp11111100_logic00000111),
    ("symbol160_init4_samp20_comp11111100_logic00000011", symbol160_init4_samp20_comp11111100_logic00000011),
    ("symbol160_init4_samp20_comp11111100_logic00000001", symbol160_init4_samp20_comp11111100_logic00000001),
    ("symbol160_init4_samp20_comp11111100_logic10000111", symbol160_init4_samp20_comp11111100_logic10000111),
    ("symbol160_init4_samp20_comp11111100_logic11000011", symbol160_init4_samp20_comp11111100_logic11000011),
    ("symbol160_init4_samp20_comp11111100_logic11100001", symbol160_init4_samp20_comp11111100_logic11100001),
    ("symbol160_init4_samp20_comp11111110_logic00001111", symbol160_init4_samp20_comp11111110_logic00001111),
    ("symbol160_init4_samp20_comp11111110_logic00000111", symbol160_init4_samp20_comp11111110_logic00000111),
    ("symbol160_init4_samp20_comp11111110_logic00000011", symbol160_init4_samp20_comp11111110_logic00000011),
    ("symbol160_init4_samp20_comp11111110_logic00000001", symbol160_init4_samp20_comp11111110_logic00000001),
    ("symbol160_init4_samp20_comp11111110_logic10000111", symbol160_init4_samp20_comp11111110_logic10000111),
    ("symbol160_init4_samp20_comp11111110_logic11000011", symbol160_init4_samp20_comp11111110_logic11000011),
    ("symbol160_init4_samp20_comp11111110_logic11100001", symbol160_init4_samp20_comp11111110_logic11100001),
    ("symbol256_init4_samp20_comp11110000_logic00001111", symbol256_init4_samp20_comp11110000_logic00001111),
    ("symbol256_init4_samp20_comp11110000_logic00000111", symbol256_init4_samp20_comp11110000_logic00000111),
    ("symbol256_init4_samp20_comp11110000_logic00000011", symbol256_init4_samp20_comp11110000_logic00000011),
    ("symbol256_init4_samp20_comp11110000_logic00000001", symbol256_init4_samp20_comp11110000_logic00000001),
    ("symbol256_init4_samp20_comp11110000_logic10000111", symbol256_init4_samp20_comp11110000_logic10000111),
    ("symbol256_init4_samp20_comp11110000_logic11000011", symbol256_init4_samp20_comp11110000_logic11000011),
    ("symbol256_init4_samp20_comp11110000_logic11100001", symbol256_init4_samp20_comp11110000_logic11100001),
    ("symbol256_init4_samp20_comp11111000_logic00001111", symbol256_init4_samp20_comp11111000_logic00001111),
    ("symbol256_init4_samp20_comp11111000_logic00000111", symbol256_init4_samp20_comp11111000_logic00000111),
    ("symbol256_init4_samp20_comp11111000_logic00000011", symbol256_init4_samp20_comp11111000_logic00000011),
    ("symbol256_init4_samp20_comp11111000_logic00000001", symbol256_init4_samp20_comp11111000_logic00000001),
    ("symbol256_init4_samp20_comp11111000_logic10000111", symbol256_init4_samp20_comp11111000_logic10000111),
    ("symbol256_init4_samp20_comp11111000_logic11000011", symbol256_init4_samp20_comp11111000_logic11000011),
    ("symbol256_init4_samp20_comp11111000_logic11100001", symbol256_init4_samp20_comp11111000_logic11100001),
    ("symbol256_init4_samp20_comp11111100_logic00001111", symbol256_init4_samp20_comp11111100_logic00001111),
    ("symbol256_init4_samp20_comp11111100_logic00000111", symbol256_init4_samp20_comp11111100_logic00000111),
    ("symbol256_init4_samp20_comp11111100_logic00000011", symbol256_init4_samp20_comp11111100_logic00000011),
    ("symbol256_init4_samp20_comp11111100_logic00000001", symbol256_init4_samp20_comp11111100_logic00000001),
    ("symbol256_init4_samp20_comp11111100_logic10000111", symbol256_init4_samp20_comp11111100_logic10000111),
    ("symbol256_init4_samp20_comp11111100_logic11000011", symbol256_init4_samp20_comp11111100_logic11000011),
    ("symbol256_init4_samp20_comp11111100_logic11100001", symbol256_init4_samp20_comp11111100_logic11100001),
    ("symbol256_init4_samp20_comp11111110_logic00001111", symbol256_init4_samp20_comp11111110_logic00001111),
    ("symbol256_init4_samp20_comp11111110_logic00000111", symbol256_init4_samp20_comp11111110_logic00000111),
    ("symbol256_init4_samp20_comp11111110_logic00000011", symbol256_init4_samp20_comp11111110_logic00000011),
    ("symbol256_init4_samp20_comp11111110_logic00000001", symbol256_init4_samp20_comp11111110_logic00000001),
    ("symbol256_init4_samp20_comp11111110_logic10000111", symbol256_init4_samp20_comp11111110_logic10000111),
    ("symbol256_init4_samp20_comp11111110_logic11000011", symbol256_init4_samp20_comp11111110_logic11000011),
    ("symbol256_init4_samp20_comp11111110_logic11100001", symbol256_init4_samp20_comp11111110_logic11100001),
    ("symbol256_init8_samp16_comp11111100_logic00000010", symbol256_init8_samp16_comp11111100_logic00000010),
    ("symbol160_init4_samp20_comp11111100_logic00000010", symbol160_init4_samp20_comp11111100_logic00000010),
)


def is_valid_adc_tb_params(params: TbParams) -> bool:
    """Check DUT, view, supplies, sequencer rows, and sweep length before generation.

    PEX file existence, cell contents, and signoff require the selected file and
    are checked by the caller. This predicate only examines parameter values.
    """
    nets = adc_nets(adc_stages(params.dut))
    # the extracted views are FRIDA's, 16 stages
    if params.view != "hdl21gen" and adc_stages(params.dut) != 16:
        return False
    if not math.isfinite(params.waveform_sample_interval_s) or params.waveform_sample_interval_s <= 0:
        return False
    if params.view not in {"frida1", "frida2", "hdl21gen"}:
        return False
    if params.view == "frida2" and params.pex_cell != "adc_12b_17step":
        return False
    if params.view == "hdl21gen" and params.pex_cell:
        return False
    # the generated ADC wires the subtraction in (its difference plates switch opposite the main
    # ones): a run of it at dac_diffcaps 0 would be decoded and analyzed as adding them
    if params.view == "hdl21gen" and not params.dac_diffcaps:
        return False
    if params.conversions <= 0:
        return False
    try:
        symbol_rate = float(params.symbol_rate)
        if not math.isfinite(symbol_rate) or symbol_rate <= 0.0:
            return False
        supplies = [net.name for net in nets.signals.values() if net.usage == h.Usage.POWER]
        for name in (*supplies, "vin_cm"):
            source = getattr(params, name)
            if source.dc is None or not math.isfinite(float(source.dc)):
                return False
    except (TypeError, ValueError, OverflowError):
        # These sources must be numeric; unresolved HDL21 literals cannot set timing or levels.
        return False
    supply_parasitics = (
        params.supply_series_resistance_ohm,
        params.supply_series_inductance_h,
        params.supply_decoupling_capacitance_f,
    )
    if any(not math.isfinite(value) or value < 0.0 for value in supply_parasitics):
        return False
    if any(supply_parasitics) and not all(value > 0.0 for value in supply_parasitics):
        return False
    if len(params.supply_noise_rms_v) != 3 or any(
        not math.isfinite(value) or value < 0.0 for value in params.supply_noise_rms_v
    ):
        return False
    if not math.isfinite(params.supply_noise_bandwidth_hz) or params.supply_noise_bandwidth_hz <= 0.0:
        return False
    for net in nets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (nets.vin_p, nets.vin_n):
            continue
        value = getattr(params, net.name)
        if net.width == 1:
            if value not in (0, 1):
                return False
        elif len(value) != net.width or any(bit not in (0, 1) for bit in value):
            return False
    patterns = tuple(
        getattr(params, f"{net.name}_pattern")
        for net in nets.signals.values()
        if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
    )
    if any(not pattern or set(pattern) - {"0", "1"} for pattern in patterns):
        return False
    if len({len(pattern) for pattern in patterns}) != 1 or len(patterns[0]) % 8:
        return False
    # one COMP pulse a decision: a decision a stage and the last one
    comp = params.seq_comp_pattern
    if sum(bit == "1" and before == "0" for before, bit in zip(comp[-1] + comp[:-1], comp, strict=True)) != (
        adc_stages(params.dut) + 1
    ):
        return False
    if isinstance(params.vin_diff, hs.LinearSweep):
        try:
            start, stop, step = (
                float(value) for value in (params.vin_diff.start, params.vin_diff.stop, params.vin_diff.step)
            )
        except (TypeError, ValueError, OverflowError):
            return False
        if not all(math.isfinite(value) for value in (start, stop, step)) or step == 0.0:
            return False
        if start != stop and (stop > start) != (step > 0):
            return False
        # Inclusive staircase endpoints must contain exactly one level per conversion.
        if not math.isclose((stop - start) / step, params.conversions - 1, rel_tol=0.0, abs_tol=1e-9):
            return False
        if len(patterns[0]) / symbol_rate <= float(100 * p):
            return False
    return True


# Generated DUTs are compiled in place and must not survive in a cached testbench.
def testbench(params: TbParams, *, pex_netlist: Path | None = None) -> h.Module:
    """Generate a complete ADC testbench for the selected DUT view."""

    if not is_valid_adc_tb_params(params):
        raise ValueError(f"Invalid ADC testbench params: {params}")
    if (params.view != "hdl21gen") != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")

    nets = adc_nets(adc_stages(params.dut))
    if pex_netlist is None:
        ports = {name: net for name, net in nets.signals.items() if net.vis == h.Visibility.PORT}
    else:
        aliases = adc_port_aliases(params.view)
        selected = {net.parent if isinstance(net, h.Slice) else net for net in aliases}
        ports = {name: net for name, net in nets.signals.items() if net in selected}
    tb, connections = testbench_from_ports(f"AdcTb_{params.view}", ports)
    tb.vin_cm, tb.vin_diff = h.Signals(2)
    symbol_period_s = 1.0 / float(params.symbol_rate)
    pattern_period_s = len(params.seq_init_pattern) * symbol_period_s
    transition_s = min(float(100 * p), symbol_period_s / 20.0)
    rlc_enabled = params.supply_series_resistance_ohm > 0.0
    supplies = (net for net in nets.signals.values() if net.usage == h.Usage.POWER)
    for rail, noise_rms_v in zip(supplies, params.supply_noise_rms_v, strict=True):
        rail_name = rail.name
        source_params = getattr(params, rail_name)
        rail = connections[rail_name]
        source_node = h.Signal(name=f"{rail_name}_source") if rlc_enabled else rail
        if rlc_enabled:
            series_node = h.Signal(name=f"{rail_name}_series")
            setattr(tb, f"{rail_name}_source", source_node)
            setattr(tb, f"{rail_name}_series", series_node)
            setattr(
                tb,
                f"r{rail_name}",
                h.Resistor(r=params.supply_series_resistance_ohm)(p=source_node, n=series_node),
            )
            setattr(
                tb,
                f"l{rail_name}",
                h.Inductor(l=params.supply_series_inductance_h)(p=series_node, n=rail),
            )
            setattr(
                tb,
                f"c{rail_name}",
                h.Capacitor(c=params.supply_decoupling_capacitance_f)(p=rail, n=tb.vss),
            )
        if noise_rms_v > 0.0:
            noise_density_v2_per_hz = noise_rms_v**2 / params.supply_noise_bandwidth_hz
            tb.literals.append(
                h.Literal(
                    f"v{rail_name} ({source_node.name} {tb.vss.name}) vsource dc={float(source_params.dc):.12g} "
                    f"noisevec=[0 {noise_density_v2_per_hz:.12g} "
                    f"{params.supply_noise_bandwidth_hz:.12g} {noise_density_v2_per_hz:.12g}]"
                )
            )
        else:
            setattr(tb, f"v{rail_name}", h.Vdc(source_params)(p=source_node, n=tb.vss))
    tb.vvin_cm = h.Vdc(params.vin_cm)(p=tb.vin_cm, n=tb.vss)
    if isinstance(params.vin_diff, h.Vdc.Params):
        tb.vvin_diff = h.Vdc(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vsin.Params):
        tb.vvin_diff = h.Vsin(
            voff=params.vin_diff.voff,
            vamp=params.vin_diff.vamp,
            freq=params.vin_diff.freq,
            td=0.0 if params.vin_diff.td is None else params.vin_diff.td,
            phase=0.0 if params.vin_diff.phase is None else params.vin_diff.phase,
        )(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, hs.LinearSweep):
        wave = h.Pwl.staircase(
            start=params.vin_diff.start,
            stop=params.vin_diff.stop,
            step=params.vin_diff.step,
            dwell=pattern_period_s,
            transition=100 * p,
            transition_at="end",
        )
        tb.vvin_diff = h.Vpwl(wave=wave)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vpwl.Params):
        tb.vvin_diff = h.Vpwl(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    else:
        raise TypeError(f"unsupported ADC differential source {type(params.vin_diff).__name__}")
    tb.evin_p = h.Vcvs(gain=0.5)(p=tb.vin_p, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)
    tb.evin_n = h.Vcvs(gain=-0.5)(p=tb.vin_n, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)

    for canonical in nets.signals.values():
        if canonical.vis != h.Visibility.PORT or canonical.usage != h.Usage.CLOCK:
            continue
        net = connections[canonical.name]
        pattern = getattr(params, f"{canonical.name}_pattern")
        setattr(
            tb,
            f"v{net.name}",
            h.Vbit(
                data=pattern,
                period=symbol_period_s,
                val0=0.0,
                val1=float(params.vdd_d.dc),
                delay=0.0,
                rise=transition_s,
                fall=transition_s,
                rptstart=1,
                rpttimes=-1,
            )(p=net, n=tb.vss),
        )
    for net in nets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (nets.vin_p, nets.vin_n):
            continue
        value = getattr(params, net.name)
        if net.width == 1:
            tb.add(h.Vdc(dc=float(params.vdd_d.dc) * value)(p=connections[net.name], n=tb.vss), name=f"v{net.name}")
        else:
            for stage, state in enumerate(value):
                tb.add(
                    h.Vdc(dc=float(params.vdd_d.dc) * state)(p=connections[net.name][stage], n=tb.vss),
                    name=f"v{net.name}_{stage}",
                )

    if pex_netlist is None:
        tb.xadc = Adc(params.dut)(**connections)
    else:
        module = adc_pex(pex_netlist, params.pex_cell or "adc_1layer_radix17")
        pex_connections = {
            physical: connections[net.parent.name][net.index] if isinstance(net, h.Slice) else connections[net.name]
            for net, physical in aliases.items()
        }
        if set(pex_connections) != set(module.ports):
            raise ValueError(
                f"External interface {module.name}: missing {set(pex_connections) - set(module.ports)}, "
                f"unknown {set(module.ports) - set(pex_connections)}"
            )
        tb.xadc = module()(**pex_connections)
    return tb


def adc_signal_names(tb: h.Module, view: str, *, save_supply_voltages: bool = False, nets=AdcNets) -> dict[str, str]:
    """Resolve canonical observations once for both Save and raw conversion; ``nets`` are the
    ADC's (``adc_nets`` of its stage count). The generated ADC holds its nets itself but for its
    bottom plates, which are its DAC's sides' (``generated_net_aliases``; a plate its array has none
    of, a unit capacitor's difference plate, is not saved); an extracted view's are RC terminals of
    its extraction (``frida1_net_aliases``, ``frida2_net_aliases``)."""
    if view not in {"hdl21gen", "frida1", "frida2"}:
        raise ValueError(f"Unsupported ADC view {view!r}")
    generated = view == "hdl21gen"
    aliases: Mapping[h.Signal | h.Slice, str | None] = (
        generated_net_aliases(tb.xadc.of, nets)
        if generated
        else frida1_net_aliases()
        if view == "frida1"
        else frida2_net_aliases()
    )
    names = {"time": "time"}
    for schema, prefix in ((nets, ""), (comp.Nets, "comp.")):
        for net in schema.signals.values():
            if not net.props.get("save"):
                continue
            testbench_net = schema is nets and net.vis == h.Visibility.PORT and net.width == 1
            path = "xtop" if testbench_net else f"xtop.{tb.xadc.name}"
            bits = [net] if net.width == 1 else [net[stage] for stage in range(net.width)]
            # by its own name, the testbench's or the generated ADC's, where no alias binds it
            named = testbench_net or (generated and not any(bit in aliases for bit in bits))
            if named:
                scope = tb if testbench_net else tb.xadc.of
                if schema is comp.Nets:
                    path += f".{scope.xcomp.name}"
                    scope = scope.xcomp.of
                actual = scope.namespace[net.name]
                if actual.width != net.width:
                    raise ValueError(f"Generated width differs from canonical net {net.name}")
            for stage, canonical in enumerate(bits):
                if named:
                    raw = f"{path}.{actual.name}" + (f"_{stage}" if net.width > 1 else "")
                elif (alias := aliases[canonical]) is not None:
                    raw = f"{path}.{alias}"
                else:
                    continue  # a plate the generated ADC's array has none of
                label = f"{prefix}{net.name}" + (f"[{stage}]" if net.width > 1 else "")
                if raw in names or label in names.values():
                    raise ValueError(f"Duplicate probe binding: {raw} -> {label}")
                names[raw] = label
    for net in nets.signals.values():
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
            if save_supply_voltages:
                names[f"xtop.{tb.namespace[net.name].name}"] = net.name
    return names


def calc_pwl_value(source: h.Vpwl.Params, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a PWL source that repeats after its last time point."""

    if isinstance(source.wave, str):
        values = np.asarray([float(value) for value in source.wave.split()], dtype=np.float64)
        pwl_time_s, pwl_value_v = values[0::2], values[1::2]
    else:
        pwl_time_s = np.asarray([float(time) for time, _value in source.wave.points], dtype=np.float64)
        pwl_value_v = np.asarray([float(value) for _time, value in source.wave.points], dtype=np.float64)
    period_s = pwl_time_s[-1] - pwl_time_s[0]
    return np.interp(pwl_time_s[0] + np.mod(time_s - pwl_time_s[0], period_s), pwl_time_s, pwl_value_v)


def calc_source_value(source, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a DC, sine, or repeating PWL differential source."""

    if isinstance(source, h.Vpwl.Params):
        return calc_pwl_value(source, time_s)
    if isinstance(source, h.Vsin.Params):
        return float(source.voff) + float(source.vamp) * np.sin(
            2.0 * np.pi * float(source.freq) * time_s + np.deg2rad(float(source.phase or 0.0))
        )
    return np.full_like(time_s, float(source.dc), dtype=np.float64)


def build_adc_interface_wave(
    params: TbParams,
    bout: Sequence[int],
    *,
    conversion_index: int = 0,
    samples_per_symbol: int = 4,
) -> Wave:
    """Build one dense behavioral ADC-interface waveform from test parameters."""

    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    bout_array = np.asarray(bout, dtype=np.uint8)
    if bout_array.ndim != 1 or np.any((bout_array != 0) & (bout_array != 1)):
        raise ValueError("Bout must be one binary decision vector")

    sequence_length = len(params.seq_init_pattern)

    seq_comp, seq_logic = (
        np.repeat(
            np.fromiter((int(bit) for bit in getattr(params, f"seq_{name}_pattern")), dtype=np.uint8),
            samples_per_symbol,
        )
        for name in ("comp", "logic")
    )
    comp_symbols = seq_comp.reshape(sequence_length, samples_per_symbol)[:, 0]
    falling_symbols = np.flatnonzero((comp_symbols[:-1] == 1) & (comp_symbols[1:] == 0)) + 1
    if len(falling_symbols) < len(bout_array):
        raise ValueError(
            f"sequencer has {len(falling_symbols)} comparator decisions, but Bout contains {len(bout_array)} bits"
        )
    comp_out_symbols = np.zeros(sequence_length, dtype=np.uint8)
    state = 0
    decision_index = 0
    for symbol in range(sequence_length):
        if decision_index < len(bout_array) and symbol == falling_symbols[decision_index]:
            state = int(bout_array[decision_index])
            decision_index += 1
        comp_out_symbols[symbol] = state

    symbol_period_s = 1.0 / float(params.symbol_rate)
    time_s = np.arange(sequence_length * samples_per_symbol, dtype=np.float64)
    time_s *= symbol_period_s / samples_per_symbol
    vin_diff_v = calc_source_value(params.vin_diff, time_s + conversion_index * sequence_length * symbol_period_s)
    logic_high_v = float(params.vdd_d.dc)
    return Wave(
        record_index=np.asarray([conversion_index], dtype=np.int64),
        time_s=time_s,
        v={
            "vin_diff": vin_diff_v[None, :],
            AdcNets.seq_comp.name: (logic_high_v * seq_comp)[None, :],
            AdcNets.seq_logic.name: (logic_high_v * seq_logic)[None, :],
            AdcNets.comp_out.name: (logic_high_v * np.repeat(comp_out_symbols, samples_per_symbol))[None, :],
        },
    )


def simulate(
    tb: TbParams,
    run_dir: Path,
    *,
    pex_netlist: Path | None = None,
    noise: bool = False,
    check: bool = False,
    expected_disconnect: bool = False,
) -> tuple[Path, dict[str, str]]:
    """Execute one configured ADC experiment, not an entire campaign.

    Targets define the experiment: they construct complete testbench parameters,
    select explicit PEX inputs and noise settings, and submit independent cases
    concurrently. This executor owns the shared mechanics: generate/compile the
    testbench, validate extracted interfaces, build the Spectre simulation, run
    short diagnostics or the full simulation, and return the raw path and probe bindings.
    Flavor/rate sweeps and campaign selection belong in the named runs (``flow.adc.sweep``),
    not in additional flavor-specific wrappers.
    """

    if not is_valid_adc_tb_params(tb):
        raise ValueError(f"Invalid ADC testbench params: {tb}")
    nets = adc_nets(adc_stages(tb.dut))

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    # Fixed budgets paired with the target pools: four x six or three x eight.
    spectre_threads = 6 if tb.view == "frida1" else 8
    if (tb.view != "hdl21gen") != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")
    metadata = {
        "target": run_dir.name,
        "view": tb.view,
        "conversions": tb.conversions,
        "symbol_rate_hz": float(tb.symbol_rate),
        "weights": list(capdac.Model.weights(tb.dut.cdac)),
        "spectre_threads": spectre_threads,
        "check": check,
        "transient_noise": noise and not check,
        "expected_historical_disconnect": expected_disconnect,
        "sequencer": {
            net.name.removeprefix("seq_"): {"pattern": getattr(tb, f"{net.name}_pattern")}
            for net in nets.signals.values()
            if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
        },
    }
    if pex_netlist is not None:
        if not pex_netlist.is_file() or not pex_netlist.stat().st_size:
            raise FileNotFoundError(pex_netlist)
        from pdk.tsmc65.calibre.ringfmom import validate_extracted_netlist

        validate_extracted_netlist(pex_netlist.read_text())
        if tb.pex_cell == "adc_12b_17step":
            summary_path = pex_netlist.parent / "signoff_summary.json"
            summary = json.loads(summary_path.read_text())
            known_disconnect = (
                expected_disconnect
                and tb.view == "frida1"
                and pex_netlist.stem in ("frida1_2layer_radix17.pex", "frida1_2layer_radix20.pex")
                and summary.get("warnings") == ["expected LVS mismatch: disconnected historical MOM layer"]
            )
            if summary["lvs_correct"] is not True and not known_disconnect:
                raise ValueError(f"unaccepted LVS result in {summary_path}")
            if Path(summary["pex_netlist"]).name != pex_netlist.name:
                raise ValueError(f"PEX input differs from {summary_path}")
            if (
                "pex_sha256" in summary
                and summary["pex_sha256"] != hashlib.sha256(pex_netlist.read_bytes()).hexdigest()
            ):
                raise ValueError(f"PEX content differs from signed-off input in {summary_path}")
        metadata.update(
            pex_netlist=str(pex_netlist),
            pex_sha256=hashlib.sha256(pex_netlist.read_bytes()).hexdigest(),
        )

    h.pdk.set_default(tsmc65.pdk_logic)
    bench = testbench(tb, pex_netlist=pex_netlist)
    h.pdk.compile(bench)
    signal_names = adc_signal_names(
        bench, tb.view, save_supply_voltages=bool(tb.supply_series_resistance_ohm), nets=nets
    )
    if pex_netlist is not None:
        text = pex_netlist.read_text().replace("\\\n", " ")
        nodes = set(text.replace("\\", "").split())
        missing = [name for name in signal_names if name.startswith("xtop.xadc.") and name[10:] not in nodes]
        if missing:
            raise ValueError(f"PEX waveform nodes missing: {missing}")

    save_targets = [re.sub(r"([/<>-])", r"\\\1", raw_name) for raw_name in signal_names if raw_name != "time"]
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
    ]
    if pex_netlist is not None:
        attrs.append(hs.Include(path=pex_netlist))
    else:
        # the digital block's standard cells (the generated ADC's only ones: its DAC's drivers are
        # the PDK's transistors), the library the site includes and the regular-Vth one, each once
        library_cells = site.install.include_stdcell()
        attrs.append(library_cells)
        standard_cells = (
            *(path for path in site.STANDARD_CELL_SPICE_NETLISTS if path != library_cells.path),
            digital_netlist(adc_stages(tb.dut))[0],
        )
        attrs.append(
            h.Literal(
                "\n".join(
                    (
                        "simulator lang=spice",
                        *(f'.include "{path}"' for path in standard_cells),
                        "simulator lang=spectre",
                    )
                )
            )
        )
    attrs.extend(
        (hs.Options(name="temp", value=25.0), hs.Options(name="save", value="selected"), hs.Save(save_targets))
    )
    tstop_s = 100e-9 if check else tb.conversions * len(tb.seq_init_pattern) / float(tb.symbol_rate)
    if not check:
        first_comp_symbol = tb.seq_comp_pattern.index("01") + 1
        # Save the next B0 edge plus a symbol of margin, without completing
        # or decoding an extra conversion. The original noise bandwidth stays fixed.
        tstop_s += (first_comp_symbol + 1) / float(tb.symbol_rate)
    metadata["final_decision_time_reference"] = "next_init_seq_logic_rising_threshold"
    tran_options = {
        "strobeperiod": tb.waveform_sample_interval_s,
        "maxstep": tb.waveform_sample_interval_s,
        "strobeoutput": "strobeonly",
    }
    # Preserve the supply experiment's frequency settings without silently
    # enabling device transient noise, which its previous runner did not enable.
    if not check and (noise or any(tb.supply_noise_rms_v) or tb.supply_series_resistance_ohm):
        tran_options.update(
            noisefmin=1.0 / (tb.conversions * len(tb.seq_init_pattern) / float(tb.symbol_rate)),
            noisefmax="25G",
            noiseseed=1,
        )
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd_a xtop.vdd_d xtop.vdd_dac 0]\n"
                "check_rcdelay static_rcdelay node=[*] maxnrise=20 maxnfall=20\n"
                "check_stack static_stack count=3\n"
                "check_topology static_topology node=[*] pin2gnd=on\n"
                "check_nodecap dyn_nodecap node=[xtop.vin_p xtop.vin_n xtop.comp_out] time=[50n 99n]\n"
                "check_setuphold dyn_setuphold node=[xtop.comp_out] ref_node=xtop.seq_logic "
                "setup_time=50p hold_time=50p\n"
                "check_power dyn_subcktpwr inst=[xtop.xadc] depth=1 port=[*] power=on"
            )
        )
    attrs.append(hs.Tran(tstop=tstop_s, name="tran", noise=noise and not check, options=tran_options))
    simulation = hs.Sim(tb=bench, attrs=attrs)
    options = SimOptions(
        simulator=SupportedSimulators.SPECTRE,
        fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
        rundir=run_dir,
        simulator_args=(
            "+preset=mx",
            f"+mt={spectre_threads}",
            "+lqtimeout",
            "3600",
            "+escchars",
            "+log",
            "spectre.log",
            *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
        ),
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(json.dumps(metadata, indent=2) + "\n")
    simulation.run(options)
    return run_dir / "netlist.raw", signal_names
