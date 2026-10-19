"""Cascode bias analyses and plots on synthetic mirror characteristics of known compliance."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.bias.analysis import MeasBias, analyze_bias_mirror
from flow.bias.plots import plot_bias_mirror, plot_bias_reference, plot_bias_supply
from flow.bias.sim import BiasTbParams
from flow.bias.subckt import CASES


def _bias(
    iref: float, *, vdd: float = 1.2, n_knee: float = 0.2, p_knee: float = 0.3, resistance: float = 1e6
) -> MeasBias:
    """Test mirrors that carry the reference current at mid-supply, rising by 1/resistance per
    volt, and fall linearly to zero below ``n_knee`` (NMOS) or within ``p_knee`` of the supply (PMOS)."""
    params = BiasTbParams(bias=CASES["wide"], vdd=vdd, iref=iref, vout_step_v=round(vdd / 48, 6))
    vout = np.linspace(0.0, vdd, 49)
    n = (iref + (vout - vdd / 2) / resistance) * np.clip(vout / n_knee, 0, 1)
    p = (iref - (vout - vdd / 2) / resistance) * np.clip((vdd - vout) / p_knee, 0, 1)
    readbacks = {"op_tn_v": 0.15, "op_tp_v": vdd - 0.2, "op_vbn_v": 0.45, "op_vcasn_v": 0.65, "op_vbp_v": 0.7}
    readbacks |= {"op_vcasp_v": 0.5, "op_supply_current_a": 3 * iref}
    return MeasBias(
        group=None,
        index=None,
        dut=params.bias,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC), readbacks=readbacks),
        param=params,
        vout_v=vout,
        n_current_a=n,
        p_current_a=p,
    )


def test_ratio_resistance_compliance_and_headroom() -> None:
    mirror = analyze_bias_mirror([_bias(10e-6), _bias(1e-6, resistance=1e7)])
    assert mirror.n_ratio == pytest.approx([1.0, 1.0])
    assert mirror.p_ratio == pytest.approx([1.0, 1.0])
    assert mirror.n_output_resistance_ohm == pytest.approx([1e6, 1e7], rel=1e-6)
    assert mirror.p_output_resistance_ohm == pytest.approx([1e6, 1e7], rel=1e-6)
    # within 5 % of the mid-supply current: down to 0.2 V less, the knee's 5 %, for the NMOS mirror
    assert mirror.n_compliance_v[0] == pytest.approx(0.2, abs=0.026)
    assert mirror.p_compliance_v[0] == pytest.approx(0.9, abs=0.026)
    assert mirror.n_headroom_v == pytest.approx([0.15, 0.15]) and mirror.p_headroom_v == pytest.approx([0.2, 0.2])
    assert mirror.supply_current_a == pytest.approx([30e-6, 3e-6])
    assert mirror.n_iv_ratio.shape == mirror.vout_v.shape == (2, 49)


def test_points_on_different_supplies_keep_their_own_grids() -> None:
    mirror = analyze_bias_mirror([_bias(10e-6, vdd=0.9), _bias(10e-6, vdd=1.3)])
    assert mirror.vout_v[:, -1] == pytest.approx([0.9, 1.3])
    assert mirror.p_compliance_v == pytest.approx([0.6, 1.0], abs=0.03)
    assert mirror.n_ratio == pytest.approx([1.0, 1.0])


def test_comparison_plots_render(tmp_path: Path) -> None:
    mirror = analyze_bias_mirror([_bias(iref) for iref in (1e-6, 10e-6, 50e-6)])
    paths = (
        *plot_bias_mirror([mirror], labels=["a"], output_path=tmp_path / "mirror"),
        *plot_bias_reference([mirror], labels=["a"], output_path=tmp_path / "reference"),
        *plot_bias_supply(
            [analyze_bias_mirror([_bias(10e-6, vdd=vdd) for vdd in (0.9, 1.2)])],
            labels=["a"],
            output_path=tmp_path / "supply",
        ),
    )
    assert paths and all(path.exists() for path in paths)
