"""Tests for PDK walker scaling of unitless generic MOS dimensions."""

from importlib import import_module

import hdl21 as h
import pytest


@pytest.mark.parametrize(
    "tech_name, expected_w_m, expected_l_m",
    [
        ("ihp130", 0.70e-6, 0.13e-6),
        ("tsmc65", 0.24e-6, 0.06e-6),
        ("tsmc28", 0.08e-6, 0.03e-6),
        ("tower180", 0.44e-6, 0.18e-6),
    ],
)
def test_unitless_mos_dimensions_scale_by_pdk_defaults(
    tech_name: str,
    expected_w_m: float,
    expected_l_m: float,
) -> None:
    """
    Unitless `w/l` multipliers are scaled by each PDK's unit-device defaults.

    Example under test:
    - `w=2*UNIT` -> `2 * pdk_default_w`
    - `l=1*UNIT` -> `1 * pdk_default_l`
    """
    pdk_module = import_module(f"pdk.{tech_name}")
    compile_fn = getattr(pdk_module, "compile")

    @h.module
    class Dut:
        d, g, s, b = h.Signals(4)
        m = h.Mos(tp=h.MosType.NMOS, w=2, l=1)(d=d, g=g, s=s, b=b)

    compile_fn(Dut)
    params = Dut.m.of.params
    assert float(params.w) == pytest.approx(expected_w_m)
    assert float(params.l) == pytest.approx(expected_l_m)
