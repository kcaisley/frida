"""
Tests for netlist utilities.
"""

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f

from ..samp.subckt import SampParams
from .netlist import (
    get_param_axes,
    params_to_filename,
    pwl_points_to_wave,
    wrap_monte_carlo,
)


def test_pwl_points_to_wave_matches_hdl21_vpwl_format() -> None:
    """Format point pairs for HDL21's string-valued Vpwl parameter."""

    wave = pwl_points_to_wave([(0.0, 0.0), (1e-9, 1.2)])
    assert wave == "0.000000000000e+00 0.000000e+00 1.000000000000e-09 1.200000e+00"
    assert h.Vpwl.Params(wave=wave).wave == wave


def test_wrap_monte_carlo_nests_and_replaces_inner_analysis() -> None:
    """Monte Carlo contains, rather than accompanies, each supported inner analysis."""

    analyses = (
        hs.Tran(tstop=1e-9),
        hs.Dc(var="x", sweep=hs.PointSweep([1.0])),
        hs.Ac(sweep=hs.LogSweep(start=1.0, stop=1e9, npts=10)),
    )
    for analysis in analyses:
        sim = hs.Sim(tb=h.Module(name="Tb"), attrs=[analysis])
        wrap_monte_carlo(sim, npts=7, seed=11)

        assert not any(isinstance(attr, (hs.Tran, hs.Dc, hs.Ac)) for attr in sim.attrs)
        monte_carlo = next(attr for attr in sim.attrs if isinstance(attr, hs.MonteCarlo))
        assert monte_carlo.inner == [analysis]
        assert monte_carlo.npts == 7
        assert monte_carlo.seed == 11


def test_params_to_filename_samp_defaults():
    """Test filename generation for default SampParams."""
    params = SampParams()
    filename = params_to_filename("samp", params, "ihp130")
    assert filename == "samp_tgate_32_1_low_ihp130.sp"


def test_params_to_filename_prefixed_value():
    """Ensure prefixed values are filename-safe."""

    @h.paramclass
    class DummyParams:
        cap = h.Param(dtype=h.Scalar, desc="cap", default=1 * f)

    filename = params_to_filename("dummy", DummyParams(), "ihp130")
    assert "*" not in filename
    assert " " not in filename


def test_get_param_axes_counts():
    """Test parameter axes extraction."""
    params_list = [
        SampParams(),
        SampParams(switch_type=SampParams().switch_type, mos_w=20),
    ]
    axes = get_param_axes(params_list)
    assert "switch_type" in axes
    assert "mos_w" in axes
    assert len(axes["mos_w"]) == 2
