"""Literal ADC channel patterns and the complete named four-channel catalogue.

Names describe period length, INIT/SAMP widths, and recurring SAR words
relative to COMP rising. Every catalogue sequence starts at INIT rising;
all four rows share that origin. The continuous 160-symbol recipes give every
terminal COMP pulse a complete word by shortening the historical 24-symbol sample.
Historical captures may retain a different cyclic RAM phase.
Their INIT-associated LOGIC pulse spans symbols 2--5; padded 256-symbol
recipes retain the historical one-symbol marker at symbol 3.
Channel rows are private; callers select complete sequences below.
"""

from dataclasses import dataclass, fields
from itertools import pairwise
from typing import Protocol

import numpy as np


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
