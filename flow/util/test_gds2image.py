"""Tests for the layout image tool."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from klayout import db

from flow.util.gds2image import Overlay, _metal_levels, _style, _view, gds_to_png_with_pdk_style, render_png

TECH = import_module("pdk.tsmc65.layout.tech")  # the palette the renders use
METALS = [TECH.LAYERS[f"M{k}"] for k in range(1, 7)]


def _gds(path: Path, levels: int, size: int = 5000) -> Path:
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    top.shapes(layout.layer(*TECH.LAYERS["OD"])).insert(db.Box(0, 0, size, size))
    for k, (ly, dt) in enumerate(METALS[:levels]):
        top.shapes(layout.layer(ly, dt)).insert(db.Box(k * 300, 0, k * 300 + 200, size))
    layout.write(str(path))
    return path


def _dither(view, name: str) -> int:
    return next(lp.dither_pattern for lp in view.each_layer() if lp.name == name)


def test_auto_metals_solid_for_a_block_hatched_for_a_full_stack(tmp_path):
    block, chip = _gds(tmp_path / "block.gds", 3), _gds(tmp_path / "chip.gds", 6)
    view = _view(block, "tsmc65")
    assert _metal_levels(view) == {1, 2, 3}
    _style(view, metals="auto")
    assert _dither(view, "M1.drawing") == 0
    view = _view(chip, "tsmc65")
    hatch = _dither(view, "M1.drawing")
    _style(view, metals="auto")
    assert _dither(view, "M1.drawing") == hatch != 0
    view = _view(chip, "tsmc65")
    _style(view, metals="solid")
    assert _dither(view, "M6.drawing") == 0


def test_render_single_and_side_by_side(tmp_path):
    a, b = _gds(tmp_path / "a.gds", 3), _gds(tmp_path / "b.gds", 2, size=3000)
    one = render_png(
        [(a, None)], tmp_path / "one.png", width=400, overlays=[Overlay(db.Region(db.Box(0, 0, 1000, 1000)))]
    )
    two = render_png([(a, "A"), (b, "B")], tmp_path / "two.png", width=800)
    assert one.exists() and two.exists()
    assert not (tmp_path / "one.gds").exists()  # the composed layout is temporary


def test_legacy_helper_keeps_its_interface(tmp_path):
    png = gds_to_png_with_pdk_style(_gds(tmp_path / "c.gds", 2), tech="tsmc65", out_dir=tmp_path, width=200, height=200)
    assert png == tmp_path / "c.png" and png.exists()
