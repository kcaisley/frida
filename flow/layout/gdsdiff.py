"""KLayout-native geometric GDS comparison.

Diff output follows the convention used by the historical FRIDA helper:
source layer ``L`` is written on ``L + 1000`` with datatype 0 for common
geometry, 1 for old-only geometry, and 2 for new-only geometry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from klayout import db


def _top_cell(layout: db.Layout, requested: str | None) -> db.Cell:
    if requested is not None:
        cell = layout.cell(requested)
        if cell is None:
            raise ValueError(f"GDS does not contain requested top cell {requested!r}")
        return cell
    tops = list(layout.top_cells())
    if len(tops) != 1:
        names = ", ".join(cell.name for cell in tops)
        raise ValueError(f"GDS has {len(tops)} top cells ({names}); specify the top cell")
    return tops[0]


def _layer_specs(layout: db.Layout) -> dict[tuple[int, int], int]:
    return {(layout.get_info(index).layer, layout.get_info(index).datatype): index for index in layout.layer_indexes()}


def _region(cell: db.Cell, layer_index: int | None, scale: float) -> db.Region:
    if layer_index is None:
        return db.Region()
    region = db.Region(cell.begin_shapes_rec(layer_index)).merged()
    if scale != 1.0:
        region.transform(db.ICplxTrans(scale, 0, False, 0, 0))
    return region


def _bbox_um(cell: db.Cell) -> list[float]:
    box = cell.dbbox()
    return [box.left, box.bottom, box.right, box.top]


def gds_diff(
    old_path: Path,
    new_path: Path,
    output_path: Path,
    *,
    old_top: str | None = None,
    new_top: str | None = None,
) -> dict[str, Any]:
    """Write a flattened geometric diff and return its area summary."""

    old = db.Layout()
    new = db.Layout()
    old.read(str(old_path))
    new.read(str(new_path))
    old_cell = _top_cell(old, old_top)
    new_cell = _top_cell(new, new_top)
    old_layers = _layer_specs(old)
    new_layers = _layer_specs(new)

    result = db.Layout()
    result.dbu = min(old.dbu, new.dbu)
    diff_cell = result.create_cell("GDS_DIFF")
    summary: dict[str, Any] = {
        "old": str(old_path),
        "new": str(new_path),
        "old_top": old_cell.name,
        "new_top": new_cell.name,
        "old_bbox_um": _bbox_um(old_cell),
        "new_bbox_um": _bbox_um(new_cell),
        "layers": {},
    }
    old_scale = old.dbu / result.dbu
    new_scale = new.dbu / result.dbu
    area_scale = result.dbu * result.dbu
    for layer, datatype in sorted(set(old_layers) | set(new_layers)):
        old_region = _region(old_cell, old_layers.get((layer, datatype)), old_scale)
        new_region = _region(new_cell, new_layers.get((layer, datatype)), new_scale)
        common = old_region & new_region
        old_only = old_region - new_region
        new_only = new_region - old_region
        regions = (common, old_only, new_only)
        labels = ("common", "old_only", "new_only")
        area = {label: region.area() * area_scale for label, region in zip(labels, regions, strict=True)}
        summary["layers"][f"{layer}/{datatype}"] = area
        for diff_datatype, (label, region) in enumerate(zip(labels, regions, strict=True)):
            if region.is_empty():
                continue
            output_layer = result.layer(db.LayerInfo(layer + 1000, diff_datatype, f"L{layer}D{datatype}_{label}"))
            # Keep every GDS boundary below the legacy record-size limit.
            # This mirrors the 4000-point limit used by the historical gdspy
            # helper while preserving the exact boolean result.
            diff_cell.shapes(output_layer).insert(region.break_polygons(4000, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(output_path))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a geometric GDS diff")
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--old-top")
    parser.add_argument("--new-top")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    summary = gds_diff(
        args.old,
        args.new,
        args.output,
        old_top=args.old_top,
        new_top=args.new_top,
    )
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
