"""Tests for shared parameter helpers."""

from importlib import import_module

import pytest
from hdl21.pdk import Corner

from .params import SupplyVals


@pytest.mark.parametrize(
    "tech_name, expected_typ",
    [
        ("ihp130", 1.2),
        ("tsmc65", 1.2),
        ("tsmc28", 0.9),
        ("tower180", 1.8),
    ],
)
def test_supplyvals_corner_uses_pdk_metadata(tech_name: str, expected_typ: float) -> None:
    """SupplyVals should resolve VDD from per-PDK supply metadata."""
    package = f"pdk.{tech_name}"
    module_name = f"{package}.pdk_logic"
    try:
        import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name in {package, module_name}:
            pytest.skip(f"{package} is unavailable; initialize the {package.replace('.', '/')} git submodule")
        raise

    vals = SupplyVals.corner(Corner.TYP, tech_name=tech_name)
    assert float(vals.VDD) == pytest.approx(expected_typ)
