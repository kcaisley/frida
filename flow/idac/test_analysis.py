"""Current source analyses and plots on synthetic sweeps of known current, resistance, and leakage."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.idac.analysis import MeasIdac, analyze_idac_output, analyze_idac_steering
from flow.idac.plots import plot_idac_bias, plot_idac_iv, plot_idac_steering
from flow.idac.sim import IdacTbParams
from flow.idac.subckt import CASES


def _sweep(iref: float, current_a: float, resistance_ohm: float, *, en: bool = True, case: str = "nmos_steer"):
    """An NMOS unit: no current below 0.2 V, then ``current_a`` at 0.6 V with ``resistance_ohm``;
    enabled into out, disabled into dump with 1 pA left on out."""
    vout_v = np.linspace(0.0, 1.2, 49)
    current = np.where(vout_v < 0.2, current_a * vout_v / 0.2, current_a + (vout_v - 0.6) / resistance_ohm)
    params = IdacTbParams(idac=CASES[case], iref=iref, en=en)
    out, dump = (
        (current, np.zeros_like(vout_v)) if en else (np.full_like(vout_v, 1e-12), np.full_like(vout_v, current_a))
    )
    return MeasIdac(
        group=None,
        index=None,
        dut=params.idac,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC),
            readbacks={"bias": f"iref{round(iref * 1e9)}na"},
        ),
        param=params,
        vout_v=vout_v,
        out_current_a=out,
        dump_current_a=dump,
        supply_current_a=np.zeros_like(vout_v),
        vbias_v=np.full_like(vout_v, 0.45),
    )


def test_current_resistance_compliance_and_steering() -> None:
    on = analyze_idac_output([_sweep(5e-6, 50e-6, 200e3), _sweep(10e-6, 100e-6, 100e3)])
    assert on.current_a == pytest.approx([50e-6, 100e-6])
    assert on.output_resistance_ohm == pytest.approx([200e3, 100e3], rel=1e-3)
    # within 5 %: down to the knee at 0.2 V, up to 0.6 V + 5 % of the current times the resistance
    assert on.compliance_low_v == pytest.approx([0.2, 0.2], abs=0.026)
    assert on.compliance_high_v == pytest.approx([1.1, 1.1], abs=0.026)
    steering = analyze_idac_steering(
        [_sweep(5e-6, 50e-6, 200e3, en=False), _sweep(10e-6, 100e-6, 100e3, en=False)], on=on
    )
    assert steering.on_off_ratio == pytest.approx([50e6, 100e6])
    assert steering.total_change == pytest.approx([0.0, 0.0], abs=1e-6)
    with pytest.raises(ValueError, match="bias order"):
        analyze_idac_steering([_sweep(10e-6, 100e-6, 100e3, en=False), _sweep(5e-6, 50e-6, 200e3, en=False)], on=on)


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    on = analyze_idac_output([_sweep(iref, 10 * iref, 1.0 / iref) for iref in (2e-6, 5e-6, 10e-6)])
    off = [_sweep(iref, 10 * iref, 1.0 / iref, en=False) for iref in (2e-6, 5e-6, 10e-6)]
    paths = (
        *plot_idac_iv([on], labels=["a"], output_path=tmp_path / "iv"),
        *plot_idac_bias([on], labels=["a"], output_path=tmp_path / "bias"),
        *plot_idac_steering([analyze_idac_steering(off, on=on)], labels=["a"], output_path=tmp_path / "steering"),
    )
    assert paths and all(path.exists() for path in paths)
