"""The sequencer's analyses: eyes of its serialized outputs from the bench's oscilloscope captures
(``AnalysisCapture``), and the scope's decode of a converter's comparator output against FastRX's.

An eye folds a capture's output at a period with ``calc.eyeDiagram`` (complete windows only),
reads each window at the centre of every time cell (``calc.value``), counts them in voltage cells
with ``calc.histogram2D`` (each cell a share of the windows) and measures its opening with
``calc.eyeHeightAtXY``: every symbol of a pattern that holds every nonconstant eight-symbol context
(``analyze_symbol_eye``), or every repetition of one eight-symbol word (``analyze_word``). Captures
are found by net (``seq_init``: the pattern's marker; ``seq_comp``: the output) and read their
sequence from the parameters they were programmed with; a logic level is the middle of a trace's
percentiles, and a trace swinging less than 50 mV is not a logic signal.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.analysis.types import MeasAdc
from flow.pipeline import analysis, measurement_identity

from .types import AnalysisCapture, AnalysisScopeBits, AnalysisSymbolEye, AnalysisWord


@analysis
def analyze_symbol_eye(captures: Sequence[AnalysisCapture]) -> AnalysisSymbolEye:
    """Every symbol of a pattern, folded from half a UI before its boundary to a UI and a half after
    it: the captures of one rate, each a record of the pattern's marker (``seq_init``, high from its
    start) and the output (``seq_comp``) playing a 256-symbol pattern that holds every nonconstant
    eight-symbol context and no constant one.

    Each record is aligned at the pattern's first rise into four ones (the marker's rise nearest
    the trigger, plus that symbol's place, to the output's nearest rise, within a UI); the pattern
    and one symbol after it are folded, its complete two-UI windows a symbol each. The map is 140
    cells over the two UI by 160 over the samples' range and a twentieth of it either side."""

    identity = measurement_identity(captures)
    rate_hz, pattern = _played(captures)
    if len(pattern) != 256 or set(pattern) != {"0", "1"}:
        raise ValueError("a symbol eye takes one binary 256-symbol pattern")
    words = {(pattern + pattern)[index : index + 8] for index in range(256)}
    if len(words) != 254 or words & {"00000000", "11111111"}:
        raise ValueError("a symbol eye's pattern must hold every nonconstant eight-symbol word")
    anchor = next(index for index in range(256) if pattern[index - 1] == "0" and pattern[index : index + 4] == "1111")
    ui_s = 1.0 / rate_hz
    traces = []
    for number, capture in enumerate(captures):
        time_s = capture.wave.time_s
        marker_v, output_v = capture.wave.v["seq_init"][0], capture.wave.v["seq_comp"][0]
        marker_level = _level(marker_v, (0.1, 99.9), f"capture {number}'s marker")
        output_level = _level(output_v, (5, 95), f"capture {number}'s output")
        marker_edges = calc.cross(marker_v, time_s, marker_level, edge="rising")
        output_edges = calc.cross(output_v, time_s, output_level, edge="rising")
        if not len(marker_edges) or not len(output_edges):
            raise ValueError(f"capture {number} lacks a marker or an output rise")
        expected_s = calc.xmin(np.abs(marker_edges), marker_edges) + anchor * ui_s
        anchor_s = calc.xmin(np.abs(output_edges - expected_s), output_edges)
        if abs(anchor_s - expected_s) > ui_s:
            raise ValueError(f"capture {number} cannot align the output to its pattern")
        start_s = anchor_s - anchor * ui_s - 0.5 * ui_s
        traces += _fold(output_v, time_s, start_s, start_s + (len(pattern) + 1) * ui_s, 2 * ui_s, ui_s)
    if not traces:
        raise ValueError(f"the captures at {rate_hz / 1e6:g} MBd hold no complete symbol")
    samples_v = np.concatenate([trace[:, 1] for trace in traces])
    low_v, high_v = np.percentile(samples_v, (5, 95))
    folded = np.vstack([part for trace in traces for part in (trace, np.full((1, 2), np.nan))][:-1])
    time_ui = np.linspace(-0.5, 1.5, 141)
    voltage_v = _cells(samples_v, 160)
    return AnalysisSymbolEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        symbol_rate_hz=rate_hz,
        symbols=len(traces),
        eye_height_v=calc.eyeHeightAtXY(folded, ui_s, float((low_v + high_v) / 2)),
        time_ui=time_ui,
        voltage_v=voltage_v,
        density=_density(traces, ui_s, 0.5, time_ui, voltage_v),
    )


@analysis
def analyze_word(captures: Sequence[AnalysisCapture]) -> AnalysisWord:
    """Every complete repetition of one eight-symbol word, folded from 0.2 UI before its start to
    0.2 UI after its end: the captures of one rate and word, each a record of the output
    (``seq_comp``) triggered at the pattern's first rise, which starts the word's repetitions.

    The pattern's word is its eight symbols from that rise; its repetitions after the first (the
    trigger's) are folded from the output's rise nearest the trigger, a word apart. The map is 168
    cells over the 8.4 UI by 80 over the samples' range and a twentieth of it either side."""

    identity = measurement_identity(captures)
    rate_hz, pattern = _played(captures)
    rise = pattern.find("1")
    word = pattern[rise : rise + 8]
    if rise < 0 or len(word) != 8:
        raise ValueError("a word's pattern holds a rise and the eight symbols after it")
    repeats = next(count for count in range(len(pattern)) if pattern[rise + 8 * count : rise + 8 * count + 8] != word)
    ui_s = 1.0 / rate_hz
    traces = []
    for number, capture in enumerate(captures):
        time_s = capture.wave.time_s
        output_v = capture.wave.v["seq_comp"][0]
        rises = calc.cross(output_v, time_s, _level(output_v, (5, 95), f"capture {number}"), edge="rising")
        if not len(rises):
            raise ValueError(f"capture {number} has no rise")
        # the words after the trigger's, the last too: each from 0.2 UI before its start, 8.4 UI
        # long, the folding to the last one's end (a window it cuts short is left out)
        start_s = calc.xmin(np.abs(rises), rises) + 8 * ui_s - 0.2 * ui_s
        stop_s = start_s + (8 * (repeats - 2) + 8.4) * ui_s
        traces += _fold(output_v, time_s, start_s, stop_s, 8.4 * ui_s, 8 * ui_s)
    if not traces:
        raise ValueError(f"the captures of {word} at {rate_hz / 1e6:g} MBd hold no complete word")
    samples_v = np.concatenate([trace[:, 1] for trace in traces])
    position_ui = np.linspace(-0.2, 8.2, 169)
    voltage_v = _cells(samples_v, 80)
    return AnalysisWord(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        symbol_rate_hz=rate_hz,
        word=word,
        words=len(traces),
        position_ui=position_ui,
        voltage_v=voltage_v,
        density=_density(traces, ui_s, 0.2, position_ui, voltage_v),
    )


@analysis
def analyze_scope_bits(measurement: MeasAdc) -> AnalysisScopeBits:
    """Decode the scope in the middle of the delayed comparator decision.

    New captures record the characterized COMP-to-COMP_OUT link delay. Older files without that
    field retain their historical 7/8-period reference. This independent scope reference is not the
    physical FastRX sample instant.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("scope/FastRX comparison requires a captured scope waveform")
    tb = measurement.tb
    decisions = measurement.bout.shape[1]
    symbols_per_decision = measurement.symbols_per_decision
    time_s = wave.time_s
    comp_v = wave.v["seq_comp"][0]
    comp_out_v = wave.v["comp_out"][0]
    # Logic levels from the 1st/99th percentiles; at least 100 mV of swing is
    # required before a scope trace is treated as a logic signal.
    comp_low_v, comp_high_v = np.percentile(comp_v, (1.0, 99.0))
    comp_out_low_v, comp_out_high_v = np.percentile(comp_out_v, (1.0, 99.0))
    comp_threshold_v = float((comp_low_v + comp_high_v) / 2.0)
    comp_out_threshold_v = float((comp_out_low_v + comp_out_high_v) / 2.0)
    if comp_high_v - comp_low_v < 0.1:
        raise ValueError("scope COMP waveform does not have a valid logic swing")
    if comp_out_high_v - comp_out_low_v < 0.1:
        raise ValueError("scope COMP_OUT waveform does not have a valid logic swing")

    rising_edges_s = calc.cross(comp_v, time_s, comp_threshold_v, edge="rising")
    rising_edges_s = rising_edges_s[rising_edges_s >= 0.0]
    if len(rising_edges_s) < decisions:
        raise ValueError(f"scope contains only {len(rising_edges_s)} COMP rising edges; expected at least {decisions}")
    comp_edge_times_s = rising_edges_s[:decisions]
    decision_period_s = symbols_per_decision / float(tb.symbol_rate)
    link_delay_s = measurement.info.readbacks.get("scope_comp_out_delay_s")
    # Historical captures sample 7/8 of a decision period after the COMP edge.
    sample_offset_s = (7.0 / 8.0) * decision_period_s
    if link_delay_s is not None:
        link_delay_s = float(link_delay_s)
        if not math.isfinite(link_delay_s) or link_delay_s < 0:
            raise ValueError("scope comparator link delay must be finite and non-negative")
        # Sample mid-decision after the characterized link delay.
        sample_offset_s = link_delay_s + 0.5 * decision_period_s
    sample_times_s = comp_edge_times_s + sample_offset_s
    sample_values_v = calc.value(comp_out_v, time_s, sample_times_s, extrapolate=False)
    scope_bits = np.asarray(sample_values_v) > comp_out_threshold_v
    if measurement.info.readbacks.get("scope_comp_out_inverted") is True:
        scope_bits = ~scope_bits
    # COMP_OUT shown from four decisions before the first COMP rise to the last decision's end
    shown = (time_s >= comp_edge_times_s[0] - 4 * decision_period_s) & (
        time_s <= comp_edge_times_s[-1] + decision_period_s
    )
    identity = measurement.identity
    return AnalysisScopeBits(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        scope_bits=scope_bits,
        fastrx_bits=measurement.bout[measurement.conversion_index == wave.record_index[0]][0].astype(np.bool_),
        comp_threshold_v=comp_threshold_v,
        comp_out_threshold_v=comp_out_threshold_v,
        comp_edge_times_s=comp_edge_times_s,
        sample_times_s=sample_times_s,
        sample_values_v=np.asarray(sample_values_v),
        symbol_rate_hz=float(tb.symbol_rate),
        time_s=time_s[shown],
        comp_out_v=comp_out_v[shown],
    )


def _played(captures: Sequence[AnalysisCapture]) -> tuple[float, str]:
    """The symbol rate and the output's pattern (COMP's row) the captures played, which they share."""
    played = {(float(capture.param.symbol_rate), str(capture.param.seq_comp.data)) for capture in captures}
    if len(played) != 1:
        raise ValueError("an eye takes captures of one pattern at one symbol rate")
    return played.pop()


def _level(values: np.ndarray, percentiles: tuple[float, float], name: str) -> float:
    """A trace's logic level, the middle of its two ``percentiles``; a trace swinging less than
    50 mV between them is not a logic signal."""
    low, high = np.percentile(values, percentiles)
    if high - low < 0.05:
        raise ValueError(f"{name} lacks a logic swing")
    return float((low + high) / 2)


def _fold(
    values: np.ndarray, time_s: np.ndarray, start_s: float, stop_s: float, window_s: float, every_s: float
) -> list[np.ndarray]:
    """A record folded (``calc.eyeDiagram``) into windows ``window_s`` long, one every ``every_s``
    from ``start_s`` to ``stop_s``: each complete window (from its start to its end inside the
    record; the record's own edges cut the others short) a trace of its time from its start and
    its value."""
    eye = calc.eyeDiagram(values, start_s, stop_s, window_s, axis=time_s, trigger_period=every_s)
    separators = np.flatnonzero(np.isnan(eye[:, 0]))
    tolerance_s = 1e-9 * every_s
    return [
        trace
        for first, last in zip(np.r_[0, separators + 1], np.r_[separators, len(eye)], strict=True)
        if len(trace := eye[first:last])
        and math.isclose(trace[0, 0], 0.0, abs_tol=tolerance_s)
        and math.isclose(trace[-1, 0], window_s, abs_tol=tolerance_s)
    ]


def _cells(values_v: np.ndarray, cells: int) -> np.ndarray:
    """The edges of ``cells`` voltage cells over the values' range and a twentieth of it either
    side."""
    low, high = float(np.min(values_v)), float(np.max(values_v))
    margin = 0.05 * (high - low) or 0.05
    return np.linspace(low - margin, high + margin, cells + 1)


def _density(
    traces: list[np.ndarray], ui_s: float, before_ui: float, time_ui: np.ndarray, voltage_v: np.ndarray
) -> np.ndarray:
    """The folded ``traces`` (each its time from its window's start, ``before_ui`` UI before the
    boundary, and its value) as a map: each trace's value at the centre of every cell of ``time_ui``
    (``calc.value``: one a cell, however finely the scope sampled it), counted in the cells of
    ``voltage_v`` (``calc.histogram2D``), each cell's share of the traces: a row a voltage cell, NaN
    where none passes."""
    centres_ui = (time_ui[:-1] + time_ui[1:]) / 2
    values = np.asarray(
        [calc.value(trace[:, 1], trace[:, 0] / ui_s - before_ui, centres_ui, extrapolate=False) for trace in traces]
    )
    column = np.broadcast_to(np.arange(len(centres_ui), dtype=np.float64), values.shape)
    inside = np.isfinite(values)
    counts, _, _ = calc.histogram2D(
        column[inside], values[inside], bins=(np.arange(len(centres_ui) + 1) - 0.5, voltage_v)
    )
    share = counts.T / len(traces)
    return np.where(share > 0, share, np.nan)
