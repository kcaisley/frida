"""Tests for shared HDL21 netlist utilities."""

import hdl21 as h

from .netlist import pwl_points_to_wave


def test_pwl_points_to_wave_matches_hdl21_vpwl_format() -> None:
    """Format point pairs for HDL21's string-valued Vpwl parameter."""

    wave = pwl_points_to_wave([(0.0, 0.0), (1e-9, 1.2)])
    assert wave == "0.000000000000e+00 0.000000e+00 1.000000000000e-09 1.200000e+00"
    assert h.Vpwl.Params(wave=wave).wave == wave
