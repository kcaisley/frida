"""The sequencer's analysis results (``flow.seqgen.analysis``), pure data: an oscilloscope's
capture of its serialized outputs (``AnalysisCapture``), the eyes folded from such captures
(``AnalysisSymbolEye``: every symbol of a pattern; ``AnalysisWord``: every repetition of one word),
and a converter's comparator output decoded by the scope against FastRX's decode
(``AnalysisScopeBits``). A map is each cell's share of the symbols or words folded into it, read at
the centre of its time cells, NaN where none passes (a map's empty cell)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from flow.pipeline import Analysis, MeasInfo, Wave


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCapture(Analysis):
    """One oscilloscope capture of the sequencer's serialized outputs on the bench: its record's
    traces by net (``wave``: ``seq_init``, ``seq_comp``, ...) and the sequence it played (``param``:
    the testbench parameters the sequencer was programmed with, its ``symbol_rate`` and its
    ``seq_*_pattern`` rows)."""

    info: MeasInfo
    param: Any
    wave: Wave


@dataclass(frozen=True, slots=True)
class AnalysisSymbolEye(Analysis):
    """Every symbol of one pattern played at one symbol rate (``symbol_rate_hz``), each folded from
    half a unit interval (UI) before its boundary to a UI and a half after it: each cell's share of
    the symbols (``density``, a row a voltage cell; ``time_ui``: the cells' edges in UI from the
    boundary; ``voltage_v``: in V; ``symbols`` folded), and the eye's height at its centre
    (``calc.eyeHeightAtXY``, half a UI after the boundary, about the level midway between the
    samples' 5th and 95th percentiles; NaN where the eye is closed there)."""

    symbol_rate_hz: float
    symbols: int
    eye_height_v: float
    time_ui: np.ndarray
    voltage_v: np.ndarray
    density: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisWord(Analysis):
    """Every complete repetition of one serializer word (``word``: its eight symbols, from the
    pattern's first rise) played at one symbol rate, each folded from 0.2 UI before its start to 0.2
    UI after its end: each cell's share of the words (``density``; ``position_ui``: the cells' edges
    in symbols from the word's start; ``voltage_v``; ``words`` folded)."""

    symbol_rate_hz: float
    word: str
    words: int
    position_ui: np.ndarray
    voltage_v: np.ndarray
    density: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisScopeBits(Analysis):
    """One converter capture's comparator output (COMP_OUT) decoded by the scope, a decision at a
    time, aligned with the FastRX word of the same conversion (``fastrx_bits``): the scope's bits,
    its thresholds, each decision's COMP rise and the instant and value it was decoded at, and
    COMP_OUT over the record's decisions (``time_s``, ``comp_out_v``: from four decisions before the
    first COMP rise to the last decision's end) at ``symbol_rate_hz``."""

    scope_bits: np.ndarray
    fastrx_bits: np.ndarray
    comp_threshold_v: float
    comp_out_threshold_v: float
    comp_edge_times_s: np.ndarray
    sample_times_s: np.ndarray
    sample_values_v: np.ndarray
    symbol_rate_hz: float
    time_s: np.ndarray
    comp_out_v: np.ndarray

    @property
    def mismatch_mask(self) -> np.ndarray:
        """One flag for each disagreement between both decoders."""

        return self.scope_bits != self.fastrx_bits

    @property
    def mismatch_count(self) -> int:
        """The number of scope/FastRX bit disagreements."""

        return int(np.count_nonzero(self.mismatch_mask))

    @property
    def scope_bit_string(self) -> str:
        """The scope's decisions in acquisition order."""

        return "".join("1" if bit else "0" for bit in self.scope_bits)

    @property
    def fastrx_bit_string(self) -> str:
        """FastRX's decisions in acquisition order."""

        return "".join("1" if bit else "0" for bit in self.fastrx_bits)
