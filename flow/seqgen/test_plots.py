"""The sequencer's figures on the synthetic captures of its analysis tests: the serializer's eyes as
maps and a converter capture's scope decode against FastRX's, each drawn on the analysis plots'
canvas."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

import flow.analysis.plots as analysis_plots
from flow.adc.test_analysis import adc_measurement
from flow.pipeline import Plot
from flow.plot import render
from flow.scans.test_serdes import SERDES_EYE_PATTERN

from . import plots
from .analysis import analyze_scope_bits, analyze_symbol_eye, analyze_word
from .test_analysis import serializer_capture, word_pattern


def canvas(figure: Plot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``figure`` renders on the analysis plots' canvas (4800 x 2700 at their resolution)."""
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    png = next(path for path in render(figure, tmp_path / figure.name) if path.suffix == ".png")
    assert plt.imread(png).shape[:2] == (2700, 4800)


@pytest.mark.parametrize("rate_hz", (320e6, 960e6, 1600e6))
def test_a_rates_symbol_eye_is_a_map_with_its_height(rate_hz: float, tmp_path: Path, monkeypatch) -> None:
    """Each rate's eye a figure of its own (the legacy grid's rows), its symbols and its height in
    its title, its centre marked."""
    marker = "1" * 8 + "0" * 248
    eye = analyze_symbol_eye([serializer_capture(rate_hz, SERDES_EYE_PATTERN, first=0, symbols=260, marker=marker)])
    figure = plots.plot_symbol_eye(eye)
    assert figure.title == f"Serializer symbols at {rate_hz / 1e6:g} MBd: 256, eye height 1000 mV"
    assert figure.heatmap is not None and figure.heatmap.log
    assert len(figure.heatmap.x) == 141 and len(figure.heatmap.z) == 160
    assert [(marker.at, marker.label) for marker in figure.x_markers] == [(0.5, "Centre")]
    canvas(figure, tmp_path, monkeypatch)


def test_each_word_is_a_map_of_its_own(tmp_path: Path, monkeypatch) -> None:
    """Each of the seven words at a rate a figure of its own (the legacy grid's columns), named by
    its high symbols."""
    for high in range(1, 8):
        figure = plots.plot_word(analyze_word([serializer_capture(960e6, word_pattern(high), first=8, symbols=250)]))
        word = "1" * high + "0" * (8 - high)
        assert figure.title == f"Serializer word {word} ({high} of 8 high) at 960 MBd: 29 words"
        assert figure.heatmap is not None and len(figure.heatmap.x) == 169
    canvas(figure, tmp_path, monkeypatch)


def test_the_scope_decode_against_fastrxs(tmp_path: Path, monkeypatch) -> None:
    """The decisions as each decoder reads them, a row each, every disagreement marked; COMP_OUT
    with each decision's decode instant marked by the bit read there and the threshold."""
    expected = np.asarray(([1, 0] * 8) + [1], dtype=np.uint8)
    period_s = 8.0 / 800e6
    time_s = np.arange(-0.2, 19.8, 0.002) * period_s
    comp_v = np.where(
        (time_s >= 0.2 * period_s) & (np.mod(time_s - 0.2 * period_s, period_s) < 0.5 * period_s), 1.2, 0.0
    )
    comp_out_v = np.zeros_like(time_s)
    for index, bit in enumerate(expected):
        edge_s = (0.2 + index + 0.85) * period_s
        comp_out_v[(time_s >= edge_s) & (time_s < edge_s + period_s)] = 1.2 * bit
    base = adc_measurement([100], sample_rate_hz=800e6 / 256.0, observed_adc=1)
    assert base.wave is not None
    fastrx = expected.copy()
    fastrx[[3, 9]] ^= 1  # two decisions FastRX read otherwise
    measurement = replace(
        base,
        bout=fastrx[np.newaxis, :],
        wave=replace(
            base.wave,
            time_s=time_s,
            v={
                **base.wave.v,
                "vin_diff": 0 * comp_v[None, :],
                "seq_comp": comp_v[None, :],
                "seq_logic": 0 * comp_v[None, :],
                "comp_out": comp_out_v[None, :],
            },
        ),
    )
    bits = analyze_scope_bits(measurement)
    decode, samples = plots.plot_scope_bits(bits), plots.plot_scope_samples(bits)
    assert decode.title == "Scope and FastRX decisions at 800 MBd: 2 of 17 disagree"
    assert decode.y_labels == ["FastRX", "Scope"] and decode.x_ticks == "step"
    assert [marker.at for marker in decode.x_markers] == [3.0, 9.0]
    assert decode.heatmap is not None and decode.heatmap.z == [
        fastrx.astype(float).tolist(),
        expected.astype(float).tolist(),
    ]
    assert [marker.label for marker in samples.x_markers] == [str(bit) for bit in expected]
    assert [marker.label for marker in samples.y_markers] == ["Threshold"]
    assert list(samples.series) == ["COMP_OUT"] and len(samples.x) == len(bits.time_s)
    for figure in (decode, samples):
        canvas(figure, tmp_path, monkeypatch)
