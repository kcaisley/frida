"""Strict, technology-neutral ADC layout assembly."""

from __future__ import annotations

from dataclasses import dataclass

from klayout import db


@dataclass(frozen=True)
class AdcLayoutParams:
    """Parameters for assembling prebuilt ADC layout blocks."""

    top_cell: str


def is_valid_adc_layout_params(params: AdcLayoutParams) -> bool:
    """Return whether an ADC assembly parameter set is valid."""

    return isinstance(params.top_cell, str) and bool(params.top_cell.strip())


def _calc_interface_signature(layout: db.Layout, cell: db.Cell) -> tuple[object, ...]:
    """Describe the exact pin and boundary geometry of one replaceable block."""

    pins: list[tuple[tuple[int, int], tuple[tuple[str, int, int], ...], str]] = []
    for layer_index in layout.layer_indices():
        info = layout.get_info(layer_index)
        labels = tuple(
            sorted(
                (shape.text.string, shape.text.x, shape.text.y)
                for shape in cell.shapes(layer_index).each()
                if shape.is_text()
            )
        )
        if labels:
            conductor = db.Region()
            for shape in cell.shapes(layer_index).each():
                if shape.is_polygon():
                    conductor.insert(shape.polygon)
                elif shape.is_box():
                    conductor.insert(shape.box)
                elif shape.is_path():
                    conductor.insert(shape.path.polygon())
            pins.append(((info.layer, info.datatype), labels, conductor.merged().to_s()))
    boundary = cell.bbox()
    boundary_signature = () if boundary.empty() else (boundary.left, boundary.bottom, boundary.right, boundary.top)
    return tuple(sorted(pins)), boundary_signature


def AdcLayout(
    params: AdcLayoutParams,
    *,
    template: db.Layout,
    replacements: dict[str, db.Layout],
) -> db.Layout:
    """Replace compatible direct child blocks without moving or editing them.

    Each replacement layout must contain exactly one top cell with pins and a
    boundary; unreferenced unit-library cells are ignored. The block's database
    unit, pin labels, pin positions, pin shapes, and boundary must be identical
    to the corresponding template cell. Instance transforms are preserved
    verbatim.
    """

    if not is_valid_adc_layout_params(params):
        raise ValueError(f"Invalid ADC layout params: {params}")
    if not replacements:
        raise ValueError("ADC assembly requires at least one replacement")
    source_top = template.cell(params.top_cell)
    if source_top is None or source_top not in template.top_cells():
        raise ValueError(f"template has no top cell {params.top_cell!r}")

    output = template.dup()
    top = output.cell(params.top_cell)
    if top is None:
        raise RuntimeError("duplicated template lost its requested top cell")

    for placeholder_name, replacement_layout in replacements.items():
        if not placeholder_name:
            raise ValueError("replacement placeholder names must be nonempty")
        replacement_tops = [
            cell for cell in replacement_layout.top_cells() if all(_calc_interface_signature(replacement_layout, cell))
        ]
        if len(replacement_tops) != 1:
            raise ValueError(
                f"replacement for {placeholder_name!r} must have exactly one top cell with pins and a boundary; "
                f"found {[cell.name for cell in replacement_tops]}"
            )
        replacement_source = replacement_tops[0]
        if replacement_layout.dbu != output.dbu:
            raise ValueError(f"replacement {replacement_source.name!r} uses a different database unit")
        placeholder = output.cell(placeholder_name)
        if placeholder is None:
            raise ValueError(f"template has no placeholder cell {placeholder_name!r}")

        instances = [instance for instance in top.each_inst() if instance.cell_index == placeholder.cell_index()]
        if not instances:
            raise ValueError(f"top cell has no direct {placeholder_name!r} instances")
        if _calc_interface_signature(output, placeholder) != _calc_interface_signature(
            replacement_layout, replacement_source
        ):
            raise ValueError(
                f"replacement {replacement_source.name!r} is not pin-and-boundary compatible with {placeholder_name!r}"
            )

        imported = output.create_cell(f"__replacement_{placeholder_name}")
        imported.copy_tree(replacement_source)
        transforms = tuple(instance.trans for instance in instances)
        for instance in instances:
            instance.cell_index = imported.cell_index()
        if tuple(instance.trans for instance in instances) != transforms:
            raise RuntimeError(f"replacement changed a {placeholder_name!r} instance transform")
        output.delete_cell(placeholder.cell_index())
        imported.name = replacement_source.name

    return output
