"""The FMOM length and spacing fit and its plots, on test structures of known capacitance."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.momcap.analysis import MeasMomcap, analyze_momcap_fit
from flow.momcap.layout import MomTestParams, MomUnit
from flow.momcap.plots import plot_momcap_fit, plot_momcap_scaling, plot_momcap_spacing
from flow.momcap.subckt import MomStyle


def _structure(
    unit: MomUnit, length_um: float, space_nm: int = 100, *, alpha: float = 10e-15, beta: float = 0.07e-15
) -> MeasMomcap:
    """A structure whose plates follow C = (alpha / s + beta) L + 0.03 fF exactly (a difference
    unit's two pairs on a 33 um span), with a shield capacitance of a tenth of that."""

    diff_um = 33 - length_um if unit.style == MomStyle.DIFFERENCE else 0
    per_length = alpha / space_nm + beta
    c = per_length * length_um + 0.03e-15
    readbacks = {"c_a_b_f": c, "c_a_shield_f": c / 20, "c_b_shield_f": c / 20, "c_top_inner_f": c, "c_top_main_f": c}
    readbacks |= {"c_top_diff_f": per_length * diff_um + 0.03e-15, "c_top_shield_f": c / 10, "space_nm": space_nm}
    return MeasMomcap(
        group=None,
        index=None,
        dut=unit,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 18, tzinfo=UTC), readbacks=readbacks),
        param=MomTestParams(unit, round(length_um * 1000), round(diff_um * 1000), space_nm),
        trial_index=np.arange(1),
    )


def _family(unit: MomUnit, **kwargs) -> list[MeasMomcap]:
    return [
        _structure(unit, length, space, **kwargs)
        for space, lengths in ((100, (1, 2, 4, 8, 16, 32)), (150, (2, 8, 32)), (300, (2, 8, 32)))
        for length in lengths
    ]


@pytest.mark.parametrize("style", tuple(MomStyle))
def test_fit_recovers_the_spacing_model(style: MomStyle) -> None:
    fit = analyze_momcap_fit(_family(MomUnit("tsmc65", style, 2)))
    assert fit.alpha_f_nm_per_um == pytest.approx(10e-15, rel=1e-6)
    assert fit.beta_f_per_um == pytest.approx(0.07e-15, rel=1e-6)
    assert fit.gamma_f == pytest.approx(0.03e-15, rel=1e-6)
    assert fit.min_space_nm == 100
    assert fit.slope_f_per_um == pytest.approx(0.17e-15, rel=1e-6)
    assert np.max(np.abs(fit.fit_error)) < 1e-9
    assert list(fit.spacings_nm) == [100, 150, 300]
    assert fit.spacing_slopes_f_per_um == pytest.approx([0.17e-15, 10e-15 / 150 + 0.07e-15, 10e-15 / 300 + 0.07e-15])
    assert fit.spacing_intercepts_f == pytest.approx([0.03e-15] * 3)
    # a difference unit gives both its fingers' points
    assert len(fit.length_um) == (24 if style == MomStyle.DIFFERENCE else 12)


def test_every_plot_renders(tmp_path: Path) -> None:
    fits = [
        analyze_momcap_fit(_family(MomUnit(pdk, style, layers), alpha=alpha))
        for pdk, alpha in (("tsmc65", 10e-15), ("tsmc28", 6e-15))
        for style in MomStyle
        for layers in (1, 2)
    ]
    paths = (
        *plot_momcap_fit(fits[:6], title="fit", output_path=tmp_path / "fit"),
        *plot_momcap_spacing(fits[:6], title="spacing", output_path=tmp_path / "spacing"),
        *plot_momcap_scaling(fits, labels=[fit.dut.technology for fit in fits], output_path=tmp_path / "scaling"),
    )
    assert paths and all(path.exists() for path in paths)
