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


def test_adc_layout_rejects_boundary_changes() -> None:
    with pytest.raises(ValueError, match="pin-and-boundary compatible"):
        AdcLayout(
            AdcLayoutParams("adc"),
            template=_layout(top="adc", block="placeholder"),
            replacements={"placeholder": _replacement(boundary_right=105)},
        )


def test_adc_layout_allows_annotation_locations_layers_and_duplicates() -> None:
    replacement = _replacement(pin_x=55)
    cell = replacement.top_cell()
    old_pin = replacement.layer(134, 0)
    new_pin = replacement.layer(136, 0)
    cell.shapes(new_pin).insert(cell.shapes(old_pin))
    cell.shapes(old_pin).clear()
    cell.shapes(new_pin).insert(db.Text("cap_topplate", db.Trans(60, 5)))
    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": replacement},
    )
    assert result.cell("replacement") is not None


def test_adc_layout_rejects_changed_terminal_names() -> None:
    replacement = _replacement()
    cell = replacement.top_cell()
    cell.shapes(replacement.layer(134, 0)).insert(db.Text("wrong_net", db.Trans(50, 5)))
    with pytest.raises(ValueError, match="pin-and-boundary compatible"):
        AdcLayout(
            AdcLayoutParams("adc"),
            template=_layout(top="adc", block="placeholder"),
            replacements={"placeholder": replacement},
        )


def test_adc_layout_params_require_a_top_cell() -> None:
    assert is_valid_adc_layout_params(AdcLayoutParams("adc"))
    assert not is_valid_adc_layout_params(AdcLayoutParams(""))
