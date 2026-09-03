"""Tests for the KLayout-native GDS diff."""

from pathlib import Path

from klayout import db

from .gdsdiff import gds_diff


def _write_gds(path: Path, *, width_um: float, dbu: float) -> None:
    layout = db.Layout()
    layout.dbu = dbu
    cell = layout.create_cell("TOP")
    width = round(width_um / dbu)
    height = round(0.1 / dbu)
    cell.shapes(layout.layer(7, 0)).insert(db.Box(0, 0, width, height))
    layout.write(str(path))


def test_gds_diff_reports_common_and_added_geometry(tmp_path: Path) -> None:
    old = tmp_path / "old.gds"
    new = tmp_path / "new.gds"
    output = tmp_path / "diff.gds"
    _write_gds(old, width_um=0.1, dbu=0.001)
    _write_gds(new, width_um=0.2, dbu=0.0005)

    summary = gds_diff(old, new, output)

    assert output.exists()
    assert summary["layers"]["7/0"] == {
        "common": 0.01,
        "old_only": 0.0,
        "new_only": 0.01,
    }
