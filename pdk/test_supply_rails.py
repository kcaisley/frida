"""Tests for PDK-sourced supply-rail metadata helpers."""

from hdl21.pdk import Corner

from pdk import supply_rails, supply_voltage


def _rail_by_name(rails: tuple[dict[str, object], ...], name: str) -> dict[str, object]:
    target = name.upper()
    for rail in rails:
        if str(rail.get("name", "")).upper() == target:
            return rail
    raise AssertionError(f"Missing rail '{name}'")


def test_supply_rails_have_vdd() -> None:
    """Each supported PDK exposes at least one VDD rail entry."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        rails = supply_rails(tech)
        vdd = _rail_by_name(rails, "VDD")
        assert float(vdd["nominal_volts"]) > 0.0


def test_supply_voltage_corner_mapping() -> None:
    """Corner lookup maps to min/nominal/max values for VDD."""
    for tech in ("ihp130", "tsmc65", "tsmc28", "tower180"):
        rails = supply_rails(tech)
        vdd = _rail_by_name(rails, "VDD")
        assert supply_voltage(Corner.SLOW, "VDD", tech) == float(vdd["min_volts"])
        assert supply_voltage(Corner.TYP, "VDD", tech) == float(vdd["nominal_volts"])
        assert supply_voltage(Corner.FAST, "VDD", tech) == float(vdd["max_volts"])
