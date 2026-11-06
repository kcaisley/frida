"""The sequencer's analyses on synthetic captures: its serializer's output as the bench's scope
records it (an ideal two-level signal sampled ten times a symbol), and a converter capture's
comparator output decoded by the scope against FastRX's."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow import adc
from flow.adc.test_analysis import adc_measurement
from flow.analysis.types import MeasAdc
from flow.pipeline import MeasInfo, Wave
from flow.scans.test_serdes import SERDES_EYE_PATTERN

from .analysis import analyze_scope_bits, analyze_symbol_eye, analyze_word
from .types import AnalysisCapture


def serializer_capture(rate_hz: float, pattern: str, *, first: int, symbols: float, marker: str | None = None):
    """One record of the serializer playing ``pattern`` (repeating) at ``rate_hz``, its time 0 at the
    pattern's symbol ``first`` (where the scope triggers), from two symbols before it for
    ``symbols`` symbols, ten samples a symbol, each level ±0.5 V; with ``marker``, a second output
    (``seq_init``) playing that pattern alongside."""
    position = np.arange(-20, round(10 * symbols)) / 10
    index = np.mod(np.floor(position).astype(int) + first, len(pattern))
    level = {"seq_comp": pattern} | ({"seq_init": marker} if marker else {})
    return AnalysisCapture(
        group=None,
        index=None,
        dut=None,
        info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 9, 1, tzinfo=UTC)),
        param=adc.TbParams(
            symbol_rate=rate_hz,
            seq_init_pattern=marker or "0" * len(pattern),
            seq_samp_pattern="0" * len(pattern),
            seq_comp_pattern=pattern,
            seq_logic_pattern="0" * len(pattern),
        ),
        wave=Wave(
            record_index=np.asarray([0]),
            time_s=position / rate_hz,
            v={
                net: np.where(np.fromiter((row[i] == "1" for i in index), bool), 0.5, -0.5)[None, :]
                for net, row in level.items()
            },
        ),
    )


def word_pattern(high: int) -> str:
    """``test_serdes_output_words``'s pattern: a word of ``high`` high symbols of eight, played thirty
    times between idle words."""
    word = "1" * high + "0" * (8 - high)
    return "0" * 8 + word * 30 + "0" * 8


@pytest.mark.parametrize("high", range(1, 8))
def test_a_words_repetitions_after_the_trigger_fold_at_its_start(high: int) -> None:
    """The scope triggers on the pattern's first rise: the 29 repetitions after the trigger's fold
    from 0.2 UI before each start, every word once in each time cell, its high symbols high."""
    word = analyze_word([serializer_capture(320e6, word_pattern(high), first=8, symbols=250)])
    assert word.word == "1" * high + "0" * (8 - high) and word.words == 29
    assert word.symbol_rate_hz == 320e6
    assert word.position_ui[0] == pytest.approx(-0.2) and word.position_ui[-1] == pytest.approx(8.2)
    assert word.density.shape == (len(word.voltage_v) - 1, len(word.position_ui) - 1)
    np.testing.assert_allclose(np.nansum(word.density, axis=0), 1.0)
    centres = (word.position_ui[:-1] + word.position_ui[1:]) / 2
    high_row = int(np.searchsorted(word.voltage_v, 0.5)) - 1
    inside = np.isfinite(word.density[high_row])
    assert np.all(inside[(centres > 0.1) & (centres < high - 0.1)])
    assert not np.any(inside[(centres > high + 0.1) & (centres < 7.9)])


def test_a_words_captures_share_one_pattern_and_rate() -> None:
    with pytest.raises(ValueError, match="one pattern at one symbol rate"):
        analyze_word(
            [
                serializer_capture(320e6, word_pattern(3), first=8, symbols=250),
                serializer_capture(960e6, word_pattern(3), first=8, symbols=250),
            ]
        )


@pytest.mark.parametrize("rate_hz", (320e6, 960e6, 1600e6))
def test_every_symbol_of_the_eye_pattern_folds_at_its_boundary(rate_hz: float) -> None:
    """All 256 symbols of the pattern holding every nonconstant eight-symbol context fold, aligned
    by the marker (high the pattern's first eight symbols); an ideal output's eye is open its whole
    swing, 1 V, at its centre."""
    marker = "1" * 8 + "0" * 248
    eye = analyze_symbol_eye([serializer_capture(rate_hz, SERDES_EYE_PATTERN, first=0, symbols=260, marker=marker)])
    assert eye.symbols == 256
    assert eye.eye_height_v == pytest.approx(1.0)
    assert eye.time_ui[0] == pytest.approx(-0.5) and eye.time_ui[-1] == pytest.approx(1.5)
    assert eye.density.shape == (160, 140)
    np.testing.assert_allclose(np.nansum(eye.density, axis=0), 1.0)


def test_a_symbol_eye_takes_a_pattern_of_every_context() -> None:
    capture = serializer_capture(320e6, "01" * 128, first=0, symbols=260, marker="1" * 8 + "0" * 248)
    with pytest.raises(ValueError, match="every nonconstant eight-symbol word"):
        analyze_symbol_eye([capture])


@pytest.mark.parametrize("symbol_rate_hz", (800.0e6, 1600.0e6))
@pytest.mark.parametrize("comp_high_symbols", (4, 5, 6, 7))
@pytest.mark.parametrize("link_delay_periods", (None, 1.2))
def test_scope_wave_decode_matches_fastrx_with_normal_and_inverted_probe(
    symbol_rate_hz: float, comp_high_symbols: int, link_delay_periods: float | None
) -> None:
    expected_bits = np.asarray(([1, 0] * 8) + [1], dtype=np.uint8)
    decision_period_s = 8.0 / symbol_rate_hz
    first_rise_s = 0.2 * decision_period_s
    time_s = np.arange(-0.2, 19.8, 0.002) * decision_period_s
    comp_v = np.where(
        (time_s >= first_rise_s)
        & (np.mod(time_s - first_rise_s, decision_period_s) < comp_high_symbols / 8.0 * decision_period_s),
        1.2,
        0.0,
    )
    comp_out_v = np.zeros_like(time_s)
    for index, bit in enumerate(expected_bits):
        # Late decisions still resolve before 7/8, independently of COMP width.
        edge_s = (
            first_rise_s + (index + (0.85 if link_delay_periods is None else link_delay_periods)) * decision_period_s
        )
        comp_out_v[(time_s >= edge_s) & (time_s < edge_s + decision_period_s)] = 1.2 * bit

    base = adc_measurement([100], sample_rate_hz=symbol_rate_hz / 256.0, observed_adc=1)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    normal = replace(
        base,
        bout=expected_bits[np.newaxis, :],
        wave=replace(
            base.wave,
            time_s=time_s,
            v={
                **base.wave.v,
                "vin_diff": np.zeros((1, len(time_s))),
                "seq_comp": comp_v[np.newaxis, :],
                "seq_logic": np.zeros((1, len(time_s))),
                "comp_out": comp_out_v[np.newaxis, :],
            },
        ),
    )
    assert normal.wave is not None
    offset_periods = 7.0 / 8.0
    if link_delay_periods is not None:
        # A real propagation delay can exceed one decision period at high baud.
        # The legacy reference samples the wrong bit; explicit latency fixes it.
        assert analyze_scope_bits(normal).mismatch_count > 0
        normal = replace(
            normal,
            info=replace(
                normal.info,
                readbacks={
                    "scope_comp_out_delay_s": link_delay_periods * decision_period_s,
                },
            ),
        )
        assert normal.wave is not None
        offset_periods = link_delay_periods + 0.5
    normal_analysis = analyze_scope_bits(normal)

    assert normal_analysis.scope_bit_string == "10101010101010101"
    assert normal_analysis.fastrx_bit_string == normal_analysis.scope_bit_string
    assert normal_analysis.mismatch_count == 0
    np.testing.assert_allclose(
        normal_analysis.sample_times_s,
        first_rise_s + (np.arange(17) + offset_periods) * decision_period_s,
        rtol=0,
        atol=0.002 * decision_period_s,
    )
    # COMP_OUT shown from four decisions before the first COMP rise (the record's start, here) to
    # the end of the last decision
    assert normal_analysis.symbol_rate_hz == symbol_rate_hz
    assert normal_analysis.time_s[0] == pytest.approx(time_s[0])
    assert normal_analysis.time_s[-1] == pytest.approx(
        first_rise_s + 17 * decision_period_s, abs=0.002 * decision_period_s
    )
    assert len(normal_analysis.comp_out_v) == len(normal_analysis.time_s)

    assert normal.wave is not None
    inverted = replace(
        normal,
        info=replace(normal.info, readbacks=normal.info.readbacks | {"scope_comp_out_inverted": True}),
        wave=replace(normal.wave, v={**normal.wave.v, "comp_out": (1.2 - comp_out_v)[np.newaxis, :]}),
    )
    inverted_analysis = analyze_scope_bits(inverted)
    assert inverted_analysis.scope_bit_string == normal_analysis.scope_bit_string
    assert inverted_analysis.mismatch_count == 0

    # A triggered scope record can refer to a later FastRX conversion.
    later = replace(
        normal,
        param=replace(normal.param, tb=replace(normal.param.tb, conversions=2)),
        conversion_index=np.array([0, 1]),
        bout=np.stack((1 - expected_bits, expected_bits)),
        dout_raw=np.repeat(normal.dout_raw, 2),
        dout=np.repeat(normal.dout, 2),
        vin_diff_v=np.repeat(normal.vin_diff_v, 2),
        wave=replace(normal.wave, record_index=np.array([1])),
    )
    assert analyze_scope_bits(later).mismatch_count == 0


def test_a_capture_reads_back_with_the_sequence_it_played(tmp_path) -> None:
    """``test_serdes`` writes each capture as a record: its traces and the sequence it played read
    back, and the eye folds the same from it."""
    from flow.analysis.io import read_analysis, write_analysis

    capture = serializer_capture(960e6, word_pattern(5), first=8, symbols=250)
    write_analysis(tmp_path / "capture_000.h5", capture)
    loaded = read_analysis(tmp_path / "capture_000.h5")
    assert isinstance(loaded, AnalysisCapture)
    # (the parameters by field: hdl21 cannot compare a prefixed number this large to itself)
    assert float(loaded.param.symbol_rate) == float(capture.param.symbol_rate) == 960e6
    assert loaded.param.seq_comp_pattern == capture.param.seq_comp_pattern and loaded.info.backend == "physical"
    np.testing.assert_array_equal(loaded.wave.v["seq_comp"], capture.wave.v["seq_comp"])
    word, again = analyze_word([capture]), analyze_word([loaded])
    assert again.words == word.words == 29
    np.testing.assert_array_equal(again.density, word.density)
