"""Tests for PDK infrastructure: supply-rail metadata and walker scaling."""

from importlib import import_module

import hdl21 as h
import pytest
from hdl21.pdk import Corner

# ── helpers ───────────────────────────────────────────────────────────────────


def _install_class(tech: str):
    """Import and return the Install class for a given PDK."""
    return import_module(f"pdk.{tech}.pdk_logic").Install


# ── supply-rail metadata ─────────────────────────────────────────────────────


def test_supply_rails_have_vdd() -> None:
    """Each supported PDK exposes at least one VDD rail entry."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        assert "VDD" in cls.SUPPLY_RAILS, f"{tech} missing VDD in SUPPLY_RAILS"
        assert cls.SUPPLY_RAILS["VDD"]["nominal"] > 0.0


def test_install_supply_voltage_corner_mapping() -> None:
    """Install.supply_voltage() maps corners to min/nominal/max."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        vdd = cls.SUPPLY_RAILS["VDD"]
        assert cls.supply_voltage(Corner.SLOW, "VDD") == vdd["min"]
        assert cls.supply_voltage(Corner.TYP, "VDD") == vdd["nominal"]
        assert cls.supply_voltage(Corner.FAST, "VDD") == vdd["max"]


def test_supplyvals_resolves_via_install() -> None:
    """SupplyVals.corner() resolves VDD through Install.supply_voltage()."""
    from flow.circuit.params import SupplyVals

    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        expected = cls.supply_voltage(Corner.TYP, "VDD")
        vals = SupplyVals.corner(Corner.TYP, tech_name=tech)
        assert float(vals.VDD) == expected


# ── walker scaling of unitless MOS dimensions ────────────────────────────────


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
