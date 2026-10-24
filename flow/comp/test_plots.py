"""The lab's comparator figures (``python -m flow plot comp FIGURE --from <captures>``) on synthetic
captures, as the bench scans write them: each point one ``AnalysisDecisions`` file."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow import plot
from flow.analysis.io import read_analysis, write_analysis
from flow.pipeline import MeasInfo
from flow.scans.scan_comp import _build_comp_params

from .analysis import analyze_sampling_noise
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
        dut=params.tb.dut.comp,
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
    run = write(tmp_path / "scan", [capture(adc, cm, v) for adc in (0, 1) for cm in (0.6, 0.8, 1.0) for v in INPUTS_V])
    paths = plot.figures("comp", [run], ["common_mode", "common_mode_scurves"], backend="web", out_dir=tmp_path / "out")
    # each figure for each channel
    assert sorted(path.name for path in paths) == sorted(
        f"{name}_board0_channel{adc}.json" for name in ("common_mode", "common_mode_scurves") for adc in (0, 1)
    )
    import json

    figure = json.loads((tmp_path / "out" / "common_mode_board0_channel1.json").read_text())
    assert figure["x"] == pytest.approx([0.6, 0.8, 1.0])
    assert figure["series"]["noise"] == pytest.approx([SIGMA_V * 1e3] * 3, rel=0.25)
    assert figure["series"]["offset"] == pytest.approx([0.06, 0.08, 0.1], abs=0.1)


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
