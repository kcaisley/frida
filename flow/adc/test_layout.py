"""Tests for strict ADC block replacement."""

import pytest
from klayout import db

from .laygen import AdcLayout, AdcLayoutParams, is_valid_adc_layout_params


def _layout(*, top: str, block: str, pin_x: int = 50, boundary_right: int = 100) -> db.Layout:
    layout = db.Layout()
    layout.dbu = 0.001
    parent = layout.create_cell(top)
    child = layout.create_cell(block)
    pin = layout.layer(db.LayerInfo(134, 0))
    boundary = layout.layer(db.LayerInfo(108, 0))
    child.shapes(pin).insert(db.Box(pin_x - 5, 0, pin_x + 5, 10))
    child.shapes(pin).insert(db.Text("cap_topplate", db.Trans(pin_x, 5)))
    child.shapes(boundary).insert(db.Box(0, 0, boundary_right, 100))
    parent.insert(db.CellInstArray(child.cell_index(), db.Trans(1000, 2000)))
    parent.insert(db.CellInstArray(child.cell_index(), db.Trans(db.Trans.M90, 3000, 2000)))
    return layout


def _replacement(*, pin_x: int = 50, boundary_right: int = 100) -> db.Layout:
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("replacement")
    pin = layout.layer(db.LayerInfo(134, 0))
    boundary = layout.layer(db.LayerInfo(108, 0))
    cell.shapes(pin).insert(db.Box(pin_x - 5, 0, pin_x + 5, 10))
    cell.shapes(pin).insert(db.Text("cap_topplate", db.Trans(pin_x, 5)))
    cell.shapes(boundary).insert(db.Box(0, 0, boundary_right, 100))
    return layout


def test_adc_layout_ignores_unreferenced_unit_library_cells() -> None:
    replacement = _replacement()
    replacement.create_cell("unused_unit")

    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": replacement},
    )

    assert [instance.cell.name for instance in result.cell("adc").each_inst()] == ["replacement", "replacement"]


def test_adc_layout_replaces_compatible_blocks_and_preserves_transforms() -> None:
    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": _replacement()},
    )
    instances = list(result.cell("adc").each_inst())
    assert [instance.cell.name for instance in instances] == ["replacement", "replacement"]
    assert tuple(instance.trans for instance in instances) == (
        db.Trans(1000, 2000),
        db.Trans(db.Trans.M90, 3000, 2000),
    )
    assert result.cell("placeholder") is None


@pytest.mark.parametrize(("pin_x", "boundary_right"), ((55, 100), (50, 105)))
def test_adc_layout_rejects_interface_changes(pin_x: int, boundary_right: int) -> None:
    with pytest.raises(ValueError, match="pin-and-boundary compatible"):
        AdcLayout(
            AdcLayoutParams("adc"),
            template=_layout(top="adc", block="placeholder"),
            replacements={"placeholder": _replacement(pin_x=pin_x, boundary_right=boundary_right)},
        )


def test_adc_layout_params_require_a_top_cell() -> None:
    assert is_valid_adc_layout_params(AdcLayoutParams("adc"))
    assert not is_valid_adc_layout_params(AdcLayoutParams(""))
