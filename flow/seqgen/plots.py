"""The sequencer's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone: its serialized output's eyes as maps (every symbol of a pattern, folded at its boundary;
every repetition of a word), and a converter capture's comparator output as the scope decodes it,
against FastRX's decode. ``flow.plot.render`` draws them with matplotlib (the scans' tests,
flow/scans/test_serdes.py and test_fastrx.py), the viewer from their JSON."""

from __future__ import annotations

import math

import numpy as np

from flow.pipeline import Heatmap, Marker, Plot, plot

from .types import AnalysisScopeBits, AnalysisSymbolEye, AnalysisWord


@plot
def plot_symbol_eye(eye: AnalysisSymbolEye) -> Plot:
    """Every symbol of a pattern folded at its boundary (``analyze_symbol_eye``): each cell's share of
    the symbols, by decade; the centre, where the eye's height is measured, marked."""
    height = "closed" if not math.isfinite(eye.eye_height_v) else f"{eye.eye_height_v * 1e3:.0f} mV"
    return Plot(
        name="symbol_eye",
        title=f"Serializer symbols at {eye.symbol_rate_hz / 1e6:g} MBd: {eye.symbols:,}, eye height {height}",
        x_label="Time from the symbol boundary (UI)",
        y_label="Output (V)",
        x=[],
        series={},
        x_markers=[Marker(0.5, "Centre")],
        heatmap=_map(eye.time_ui, eye.voltage_v, eye.density, "Share of symbols"),
    )


@plot
def plot_word(word: AnalysisWord) -> Plot:
    """Every repetition of one serializer word folded at its start (``analyze_word``): each cell's
    share of the words, by decade."""
    return Plot(
        name="word",
        title=f"Serializer word {word.word} ({word.word.count('1')} of 8 high) at {word.symbol_rate_hz / 1e6:g} MBd: "
        f"{word.words} words",
        x_label="Symbol position in the word (UI)",
        y_label="Output (V)",
        x=[],
        series={},
        heatmap=_map(word.position_ui, word.voltage_v, word.density, "Share of words"),
    )


@plot
def plot_scope_bits(bits: AnalysisScopeBits) -> Plot:
    """The decisions of one conversion as the scope decodes them and as FastRX did, a row each
    (``analyze_scope_bits``: high where a decision is 1), every disagreement marked."""
    decisions = len(bits.scope_bits)
    return Plot(
        name="scope_bits",
        title=f"Scope and FastRX decisions at {bits.symbol_rate_hz / 1e6:g} MBd: "
        f"{bits.mismatch_count} of {decisions} disagree",
        x_label="Decision (B0 first)",
        y_label="Decoded by",
        x=[],
        series={},
        x_ticks="step",
        y_labels=["FastRX", "Scope"],
        x_markers=[Marker(float(decision)) for decision in np.flatnonzero(bits.mismatch_mask)],
        heatmap=Heatmap(
            x=[decision - 0.5 for decision in range(decisions + 1)],
            y=[-0.5, 0.5, 1.5],
            z=[[float(bit) for bit in row] for row in (bits.fastrx_bits, bits.scope_bits)],
            label="Decision",
        ),
    )


@plot
def plot_scope_samples(bits: AnalysisScopeBits) -> Plot:
    """The comparator output at the scope over the conversion's decisions, each decision's decode
    instant marked with the bit the scope reads there, and the threshold it reads them against."""
    return Plot(
        name="scope_samples",
        title=f"COMP_OUT and its decode at {bits.symbol_rate_hz / 1e6:g} MBd",
        x_label="Time (s)",
        y_label="COMP_OUT at the scope (V)",
        x=[_six(value) for value in bits.time_s],
        series={"COMP_OUT": [_six(value) for value in bits.comp_out_v]},
        x_markers=[
            Marker(_six(at), "1" if bit else "0") for at, bit in zip(bits.sample_times_s, bits.scope_bits, strict=True)
        ],
        y_markers=[Marker(_six(bits.comp_out_threshold_v), "Threshold")],
    )


def _map(x: np.ndarray, y: np.ndarray, z: np.ndarray, label: str) -> Heatmap:
    """An eye's map by decade (its cells' edges ``x`` and ``y``, a row of ``z`` a row of cells), its
    numbers to six significant digits."""
    return Heatmap(
        x=[_six(value) for value in x],
        y=[_six(value) for value in y],
        z=[[_six(value) for value in row] for row in np.asarray(z, dtype=np.float64)],
        label=label,
        log=True,
    )


def _six(value: float) -> float:
    """``value`` to six significant digits (NaN as it is), as the viewer's other exports."""
    value = float(value)
    return float(f"{value:.6g}") if math.isfinite(value) else math.nan
