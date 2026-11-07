"""The comparator's figures: the lab's (``python -m flow plot comp FIGURE --from <captures>``) on
synthetic captures, as the bench scans write them (each point one ``AnalysisDecisions`` file), the
record's noise and offset over the common mode the same specs; and the comparator inside a
converter, from its scope records and a simulation's latches."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

import flow.analysis.plots as analysis_plots
from flow import adc, plot
from flow.adc.test_analysis import adc_timing_measurement
from flow.analysis.io import read_analysis, write_analysis
from flow.pipeline import MeasInfo, Plot
from flow.scans.scan_comp import _build_comp_params

from . import plots
from .analysis import (
    analyze_common_mode,
    analyze_edge_eye,
    analyze_offset_noise,
    analyze_response,
    analyze_sampling_noise,
    analyze_scope_edges,
)
from .test_analysis import repeated, scope_records
from .types import AnalysisDecisions

SIGMA_V = 0.5e-3


def capture(adc: int, vin_cm_v: float, vin_diff_v: float, **scan) -> AnalysisDecisions:
    """One captured point: 400 decisions of a comparator with ``SIGMA_V`` of noise and an offset of
    a tenth of the common mode in mV."""
    params = _build_comp_params(
        adc_index=adc,
        campaign=scan.pop("campaign", "comp_common_mode"),
        sampling_mode=scan.pop("sampling_mode", "track"),
        sweep_stage="fixed",
        vin_cm_v=vin_cm_v,
        vin_diff_v=vin_diff_v,
        conversions=400,
        **scan,
    )
    rng = np.random.default_rng([round(vin_diff_v * 1e7) + 100_000, adc, round(vin_cm_v * 1e3)])
    probability = 0.5 * (1 + math.erf((vin_diff_v - vin_cm_v * 1e-4) / (SIGMA_V * math.sqrt(2))))
    return AnalysisDecisions(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.params.comp,
        info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 5, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(400),
        vin_diff_v=np.full(400, vin_diff_v),
        vin_cm_v=np.full(400, vin_cm_v),
        decision=(rng.random(400) < probability).astype(np.uint8),
    )


def write(run: Path, captures: list[AnalysisDecisions]) -> Path:
    for number, item in enumerate(captures):
        write_analysis(run / f"{number:05d}_adc{item.index:02d}.h5", item)
    return run


INPUTS_V = np.linspace(-2e-3, 2e-3, 21)


def test_a_capture_reads_back_with_where_it_came_from(tmp_path: Path) -> None:
    path = write(tmp_path, [capture(0, 0.7, 0.0)]) / "00000_adc00.h5"
    loaded = read_analysis(path)
    assert isinstance(loaded, AnalysisDecisions) and loaded.info.source_path == path


def test_the_common_mode_figures_from_a_campaigns_captures(tmp_path: Path) -> None:
    """A campaign's captures draw the record's own noise and offset over the common mode, in volts,
    and its S-curves as a map, a row a common mode."""
    import json

    names = ("noise_cm", "offset_cm", "common_mode_scurves")
    run = write(tmp_path / "scan", [capture(adc, cm, v) for adc in (0, 1) for cm in (0.6, 0.8, 1.0) for v in INPUTS_V])
    paths = plot.figures("comp", [run], names, backend="web", out_dir=tmp_path / "out")
    # each figure for each channel
    assert sorted(path.name for path in paths) == sorted(
        f"{name}_board0_channel{adc}.json" for name in names for adc in (0, 1)
    )
    noise, offset, scurves = (
        json.loads((tmp_path / "out" / f"{name}_board0_channel1.json").read_text()) for name in names
    )
    assert noise["x"] == offset["x"] == pytest.approx([0.6, 0.8, 1.0])
    assert noise["series"]["noise"] == pytest.approx([SIGMA_V] * 3, rel=0.25)
    assert offset["series"]["offset"] == pytest.approx([0.06e-3, 0.08e-3, 0.1e-3], abs=0.1e-3)
    assert scurves["y_labels"] == ["0.6 V", "0.8 V", "1 V"]
    heatmap = scurves["heatmap"]
    assert len(heatmap["x"]) == len(INPUTS_V) + 1 and heatmap["x"][0] < INPUTS_V[0] < heatmap["x"][1]
    assert heatmap["z"][0][0] == pytest.approx(0.0, abs=0.01) and heatmap["z"][2][-1] == pytest.approx(1.0, abs=0.01)


def test_the_records_noise_and_offset_are_its_s_curves_fits() -> None:
    """A characterization's noise and offset over the common mode, from its S-curves'
    common-mode analysis (as a capture's), are each S-curve's own fit, NaN where it is not valid."""
    curves = [
        [capture(0, cm, v) for v in INPUTS_V * scale]
        for cm, scale in ((0.45, 1.0), (0.55, 1.0), (0.65, 0.05), (0.75, 1.0))
    ]
    fits = [analyze_offset_noise(curve) for curve in curves]
    assert [fit.validity for fit in fits] == ["valid", "valid", "unbracketed", "valid"]
    common_mode = analyze_common_mode([item for curve in curves for item in curve])
    noise, offset = plots.plot_noise_cm(common_mode), plots.plot_offset_cm(common_mode)
    assert noise.x == offset.x == [fit.vin_cm_v for fit in fits]
    for figure, key, values in (
        (noise, "noise", [f.noise_sigma_v for f in fits]),
        (offset, "offset", [f.offset_v for f in fits]),
    ):
        expected = [value if fit.validity == "valid" else math.nan for value, fit in zip(values, fits, strict=True)]
        np.testing.assert_array_equal(figure.series[key], expected)
    assert offset.title == "Offset over the common mode"


def test_the_sampling_figures_take_a_correction_runs_curves(tmp_path: Path) -> None:
    def curve(coupling: float, mode: str, cm: float) -> list[AnalysisDecisions]:
        return [
            capture(2, cm, v, campaign="comp_sampling_noise", sampling_mode=mode, requested_dac_rail_percent=coupling)
            for v in INPUTS_V
        ]

    base = write(tmp_path / "run1", [*curve(25.0, "track", 0.7), *curve(25.0, "hold", 0.7)])
    # a later run (by its folder) re-measures the hold curve, here as if at another common mode (another
    # offset)
    correction = write(tmp_path / "run2", curve(25.0, "hold", 0.9))
    paths = sorted([*base.glob("*.h5"), *correction.glob("*.h5")])
    captures = [item for path in paths if isinstance(item := read_analysis(path), AnalysisDecisions)]
    result = analyze_sampling_noise(captures)
    assert result.sampling_mode == ("hold", "track") and result.coupling_percent.tolist() == [25.0, 25.0]
    assert result.offset_v[0] == pytest.approx(0.9e-4, abs=0.1e-3)  # the correction's
    paths = plot.figures("comp", [base, correction], ["sampling_noise"], out_dir=tmp_path / "out")
    assert [path.suffix for path in paths] == [".pdf"]


def test_the_cli_draws_a_single_s_curve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    import flow
    from flow import __main__ as cli

    run = write(tmp_path / "behavioral", [capture(0, 0.7, v) for v in INPUTS_V])
    out = tmp_path / "out"
    monkeypatch.setattr(flow, "new_run", lambda *parts: out)
    monkeypatch.setattr(sys, "argv", ["flow", "plot", "comp", "offset_noise", "--from", str(run)])
    cli.main()
    assert capsys.readouterr().out.split() == [str(out / "offset_noise_board0_channel0.pdf")]
    with pytest.raises(LookupError, match="no figure"):
        plot.figures("comp", [run], ["no_such_figure"], out_dir=out)


def campaign_curve(campaign: str, mode: str, vin_cm_v: float, center_v: float, coupling: float | None = None):
    """One curve of a campaign at one ADC: 100 decisions at each of three inputs about ``center_v``,
    none, half and all of them high."""
    measurements = []
    for vin_diff_v, ones in ((center_v - 1.0e-3, 0), (center_v, 50), (center_v + 1.0e-3, 100)):
        params = _build_comp_params(
            adc_index=0,
            campaign=campaign,
            sampling_mode=mode,
            sweep_stage="fixed",
            vin_cm_v=vin_cm_v,
            vin_diff_v=vin_diff_v,
            conversions=100,
            requested_dac_rail_percent=coupling,
        )
        measurements.append(
            AnalysisDecisions(
                group=params.board_id,
                index=params.observed_adc,
                dut=params.tb.params.comp,
                info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 5, tzinfo=UTC)),
                param=params,
                trial_index=np.arange(100),
                vin_diff_v=np.full(100, vin_diff_v),
                vin_cm_v=np.full(100, vin_cm_v),
                decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
            )
        )
    return measurements


def canvas(figure: Plot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``figure`` renders on the analysis plots' canvas (4800 x 2700 at their resolution)."""
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    png = next(path for path in plot.render(figure, tmp_path / figure.name) if path.suffix == ".png")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_campaigns_figures_keep_every_common_mode_and_coupling(tmp_path: Path, monkeypatch) -> None:
    """Every common mode a campaign took is a row of its S-curves and a point of its noise and
    offset, the lowest too; every coupling and mode a row of the sampling S-curves and a category
    of their offset and noise, a curve's hold offset its track one's and the pedestal."""
    common = [campaign_curve("comp_common_mode", "track", cm, 10.0e-3) for cm in (0.6, 0.7, 0.8, 1.0)]
    common_mode = analyze_common_mode([item for curve in common for item in curve])
    scurves = plots.plot_common_mode_scurves(common_mode)
    assert scurves.y_labels == ["0.6 V", "0.7 V", "0.8 V", "1 V"]
    assert scurves.heatmap is not None and scurves.heatmap.x == pytest.approx([8.5e-3, 9.5e-3, 10.5e-3, 11.5e-3])
    assert scurves.heatmap.z == [[0.0, 0.5, 1.0]] * 4
    assert plots.plot_noise_cm(common_mode).x == pytest.approx([0.6, 0.7, 0.8, 1.0])
    assert plots.plot_offset_cm(common_mode).series["offset"] == pytest.approx([10.0e-3] * 4)
    for figure in (scurves, plots.plot_noise_cm(common_mode)):
        canvas(figure, tmp_path, monkeypatch)

    couplings = (0.0, 25.0, 50.0, 75.0, 100.0)
    sampling = analyze_sampling_noise(
        [
            item
            for coupling in couplings
            for mode in ("track", "hold")
            for item in campaign_curve(
                "comp_sampling_noise",
                mode,
                0.7,
                10.0e-3 + coupling * 5.0e-6 + (0.2e-3 if mode == "hold" else 0.0),
                coupling,
            )
        ]
    )
    names = [f"{coupling:g}/{100 - coupling:g} % {mode}" for coupling in couplings for mode in ("hold", "track")]
    sampling_scurves = plots.plot_sampling_noise_scurves(sampling)
    offset, noise = plots.plot_sampling_offset(sampling), plots.plot_sampling_noise(sampling)
    assert sampling_scurves.y_labels == offset.x_labels == noise.x_labels == names
    # the hold curves' offset, the track ones' and a 0.2 mV pedestal; 5 uV more for each % of coupling
    pairs = np.asarray(offset.series["offset"]).reshape(5, 2)
    np.testing.assert_allclose(pairs[:, 0] - pairs[:, 1], 0.2e-3, atol=1e-9)
    np.testing.assert_allclose(pairs[:, 1], 10.0e-3 + np.asarray(couplings) * 5.0e-6, atol=1e-9)
    assert list(noise.series) == ["noise"] and len(noise.series["noise"]) == 10
    for figure in (sampling_scurves, offset, noise):
        canvas(figure, tmp_path, monkeypatch)


def test_an_s_curve_marks_its_offset_and_shades_its_noise() -> None:
    curve = [capture(0, 0.7, v) for v in INPUTS_V]
    fit = analyze_offset_noise(curve)
    figure = plots.plot_offset_noise(fit)
    assert list(figure.series) == ["P(high)"] and figure.x == pytest.approx(INPUTS_V)
    assert [(marker.at, marker.label) for marker in figure.x_markers] == [(fit.offset_v, "Offset")]
    assert [(band.low, band.high) for band in figure.x_bands] == [
        (pytest.approx(fit.offset_v - fit.noise_sigma_v), pytest.approx(fit.offset_v + fit.noise_sigma_v))
    ]
    # an unbracketed curve: no offset to mark
    unbracketed = analyze_offset_noise([capture(0, 0.7, v) for v in INPUTS_V * 0.05])
    assert unbracketed.validity == "unbracketed"
    assert not plots.plot_offset_noise(unbracketed).x_markers and not plots.plot_offset_noise(unbracketed).x_bands


def test_the_comparators_output_in_a_converters_scope_records(tmp_path: Path, monkeypatch) -> None:
    """COMP_OUT folded at every decision's COMP rise and over the conversion, each a map with COMP's
    high phases shaded (a decision's named), and each decision's delays as a map with their median."""
    edges = analyze_scope_edges([adc.analyze_conversions(record) for record in scope_records()])
    eye, timing, response = (
        plots.plot_scope_eye(edges),
        plots.plot_scope_timing(edges),
        plots.plot_scope_response(edges),
    )
    assert eye.title == "Measured decision eye: 4 records × 17 decisions"
    assert eye.heatmap is not None and eye.heatmap.log and len(eye.heatmap.z) == len(edges.voltage_v) - 1
    assert [(band.low, band.label) for band in eye.x_bands] == [(0.0, "COMP high")]
    assert [band.label for band in timing.x_bands] == [f"B{d}" if d % 4 == 0 else "" for d in range(17)]
    assert response.x_ticks == "step" and response.x == list(map(float, range(17)))
    assert math.isnan(response.series["Median"][3]) and response.series["Median"][0] == pytest.approx(
        5.5e-9, abs=0.1e-9
    )
    assert response.heatmap is not None and response.heatmap.x == pytest.approx(np.arange(18) - 0.5)
    for figure in (eye, timing, response):
        canvas(figure, tmp_path, monkeypatch)
    assert sorted(path.name for path in tmp_path.glob("*.pdf")) == [
        "scope_eye.pdf",
        "scope_response.pdf",
        "scope_timing.pdf",
    ]


def test_a_simulated_converters_latches_over_each_decision(tmp_path: Path, monkeypatch) -> None:
    """The SR latch's output and the XC latch's |P - N|, folded at each clock rise and over the
    conversion, every conversion's; each one's response by decision; drawn on the canvas."""
    eye = analyze_edge_eye(adc.analyze_conversions(repeated(adc_timing_measurement())))
    response = analyze_response(adc.analyze_conversions(adc_timing_measurement()))
    figures = [
        plots.plot_sr_eye(eye),
        plots.plot_xc_eye(eye),
        plots.plot_sr_timing(eye),
        plots.plot_xc_timing(eye),
        plots.plot_sr_response(response),
        plots.plot_xc_response(response),
    ]
    assert [figure.name for figure in figures] == [
        "sr_eye",
        "xc_eye",
        "sr_timing",
        "xc_timing",
        "sr_response",
        "xc_response",
    ]
    assert figures[0].title == "Simulated decision eye of the SR latch: 2 conversions × 17 decisions"
    assert figures[1].y_label == "XC latch |P − N| (V)"
    assert [band.label for band in figures[2].x_bands] == [f"B{d}" if d % 4 == 0 else "" for d in range(17)]
    assert all(figure.heatmap is not None for figure in figures)
    # a held decision has no response: its median is NaN
    assert math.isnan(figures[4].series["Median"][1])
    for figure in figures:
        canvas(figure, tmp_path, monkeypatch)


def test_a_latch_with_no_timed_response_draws_its_median_alone(tmp_path: Path, monkeypatch) -> None:
    from dataclasses import replace

    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    # the XC latch never parts: neither rail crosses half the supply
    stuck = {**measurement.wave.v, "comp.latch_p": np.full_like(measurement.wave.v["comp.latch_p"], 0.6)}
    stuck["comp.latch_n"] = stuck["comp.latch_p"]
    response = analyze_response(adc.analyze_conversions(replace(measurement, wave=replace(measurement.wave, v=stuck))))
    figure = plots.plot_xc_response(response)
    assert figure.title.endswith(": none timed") and figure.heatmap is None
    assert all(math.isnan(value) for value in figure.series["Median"])
    canvas(figure, tmp_path, monkeypatch)
