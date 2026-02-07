"""
Tests for netlist utilities.
"""

import hdl21 as h
from hdl21.prefix import f

from ..samp.samp import SampParams
from .netlist import (
    generate_staircase_pwl,
    get_param_axes,
    params_to_filename,
)


def test_generate_staircase_pwl():
    """Test staircase PWL generation."""
    points = generate_staircase_pwl(
        v_start=0.0,
        v_stop=1.0,
        v_step=0.1,
        t_step=1e-6,
        t_rise=1e-9,
    )

    assert len(points) > 0
    assert points[0] == (0.0, 0.0)

    voltages = [v for t, v in points]
    for i in range(len(voltages) - 1):
        assert voltages[i] <= voltages[i + 1]


def test_params_to_filename_samp_defaults():
    """Test filename generation for default SampParams."""
    params = SampParams()
    filename = params_to_filename("samp", params, "ihp130")
    assert filename == "samp_nmos_10_1_low_ihp130.sp"


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
        SampParams(switch_type=SampParams().switch_type, w=20),
    ]
    axes = get_param_axes(params_list)
    assert "switch_type" in axes
    assert "w" in axes
    assert len(axes["w"]) == 2
