"""MOS capacitor analysis and plots on synthetic admittances of known capacitance and loss."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.moscap.analysis import MeasMosCap, analyze_moscap_cv
from flow.moscap.plots import plot_moscap_cv, plot_moscap_frequency, plot_moscap_quality
from flow.moscap.sim import MosCapTbParams
from flow.moscap.subckt import CASES


def _series_rc(capacitance_f: float, resistance_ohm: float, *, case: str = "cap_n", bias: float = 1.2) -> MeasMosCap:
    """A capacitor in series with a resistor, with 1 nA of leakage."""
    frequency_hz = np.logspace(6, 11, 51)
    admittance = 1 / (resistance_ohm + 1 / (2j * np.pi * frequency_hz * capacitance_f))
    params = (
        MosCapTbParams(moscap=CASES[case], vdd=bias, vtop=0.0)
        if case.startswith("decap")
        else MosCapTbParams(moscap=CASES[case], vtop=max(bias, 0.0), vbot=max(-bias, 0.0))
    )
    return MeasMosCap(
        group=None,
        index=None,
        dut=params.moscap,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC),
            readbacks={"op_leakage_a": 1e-9, "bias_mv": round(bias * 1e3)},
        ),
        param=params,
        frequency_hz=frequency_hz,
        conductance_s=np.real(admittance),
        susceptance_s=np.imag(admittance),
    )


def test_capacitance_quality_resistance_and_corner() -> None:
    result = analyze_moscap_cv([_series_rc(25e-15, 1000.0, bias=bias) for bias in (-1.2, 1.2)])
    assert result.bias_v == pytest.approx([-1.2, 1.2])
    assert result.capacitance_f == pytest.approx([25e-15, 25e-15], rel=1e-6)
    assert result.loss_frequency_hz == pytest.approx(1e9)
    assert result.series_resistance_ohm == pytest.approx([1000.0, 1000.0])
    # a series RC's quality factor 1 / (2 pi f R C) reaches 1 at 1 / (2 pi R C), 6.4 GHz
    assert result.quality == pytest.approx(1 / (2 * np.pi * 1e9 * 1000.0 * 25e-15), rel=1e-6)
    assert result.corner_hz == pytest.approx(1 / (2 * np.pi * 1000.0 * 25e-15), rel=0.01)
    assert result.leakage_a == pytest.approx([1e-9, 1e-9])


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    decap = analyze_moscap_cv([_series_rc(20e-15 * bias, 10.0, case="decap_n", bias=bias) for bias in (0.6, 1.2)])
    cap = analyze_moscap_cv([_series_rc(5e-15 + 10e-15 * (bias > 0), 5.0, bias=bias) for bias in (-1.2, 0.0, 1.2)])
    paths = (
        *plot_moscap_cv([decap, cap], labels=["a", "b"], output_path=tmp_path / "cv"),
        *plot_moscap_frequency([decap, cap], labels=["a", "b"], output_path=tmp_path / "frequency"),
        *plot_moscap_quality([decap, cap], labels=["a", "b"], output_path=tmp_path / "quality"),
    )
    assert paths and all(path.exists() for path in paths)
