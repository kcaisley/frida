"""Tests for PDK supply-rail metadata on Install classes."""

from importlib import import_module

from hdl21.pdk import Corner


def _install_class(tech: str):
    """Import and return the Install class for a given PDK."""
    return import_module(f"pdk.{tech}.pdk_logic").Install


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
    from flow.flow.params import SupplyVals

    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        cls = _install_class(tech)
        expected = cls.supply_voltage(Corner.TYP, "VDD")
        vals = SupplyVals.corner(Corner.TYP, tech_name=tech)
        assert float(vals.VDD) == expected
