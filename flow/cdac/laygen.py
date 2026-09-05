"""Process-independent physical generator for the FRIDA unit-length CDAC.

Electrical weights come from :mod:`flow.cdac.subckt`. Physical dimensions
come from the selected PDK rule deck; this module contains only dimensionless
topology choices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from klayout import db

from flow.layout.dsl import GenericLayers, load_generic_layers
from flow.layout.tech import NewRuleDeck, remap_layers

from .subckt import CdacParams, _calc_weight_partitions, get_cdac_weights, is_valid_cdac_params


@dataclass(frozen=True)
class UnitLengthCapFamilyParams:
    """Dimensionless choices shared by a family of weighted unit cells."""

    coarse_weight: int = 64
    tail_landings: int = 1
    edge_dummy_units: int = 1
    shield_bridge_tracks: int = 15
    side_access_tracks: int = 5


@dataclass(frozen=True)
class CdacLayoutParams:
    """Electrical and physical configuration for a MOM CDAC.

    ``route_layer == shield_layer`` selects a partitioned shared metal layer:
    the shield occupies the central capacitor body while rule-derived routing
    corridors at both ends remain available for the plate buses and vias.
    """

    cdac: CdacParams
    family: UnitLengthCapFamilyParams
    technology: str
    route_layer: int
    shield_layer: int
    active_layers: tuple[int, ...]
    top_cell: str


@dataclass(frozen=True)
class _UnitGeometry:
    """Rule-derived geometry, stored in integer nanometres."""

    grid: int
    finger_width: int
    gap: int
    end_gap: int
    track_pitch: int
    weight_step: int
    tail_length: int
    nominal_length: int
    ring_width: int
    outer_width: int
    outer_height: int
    unit_pitch: int
    via_cut: int
    via_pitch: int
    via_landing: int
    via_opposite_enclosure: int
    via_minimum_enclosure: int
    landing_short: int
    landing_long: int
    shield_spacing: int
    shield_cutout_width: int
    shield_bridge_ys: tuple[int, ...]
    side_extension: int


def is_valid_cdac_layout_params(params: CdacLayoutParams) -> bool:
    """Validate one complete process-independent CDAC layout configuration."""

    family = params.family
    if not is_valid_cdac_params(params.cdac):
        return False
    if not params.technology or not params.top_cell:
        return False
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (
            family.coarse_weight,
            family.tail_landings,
            family.shield_bridge_tracks,
            family.side_access_tracks,
        )
    ):
        return False
    if (
        isinstance(family.edge_dummy_units, bool)
        or not isinstance(family.edge_dummy_units, int)
        or family.edge_dummy_units < 0
    ):
        return False
    if params.route_layer != 4 or params.shield_layer not in (4, 5):
        return False
    if not params.active_layers or any(layer not in (5, 6, 7) for layer in params.active_layers):
        return False
    if tuple(sorted(set(params.active_layers))) != params.active_layers:
        return False
    if params.active_layers != tuple(range(params.active_layers[0], params.active_layers[-1] + 1)):
        return False
    return params.route_layer <= params.shield_layer < params.active_layers[0]


def _snap_up(value: int, grid: int) -> int:
    return ((value + grid - 1) // grid) * grid


def _required_rule(value: int | None, description: str) -> int:
    if value is None:
        raise ValueError(f"PDK rule deck is missing {description}")
    return value


def _calc_unit_geometry(params: CdacLayoutParams, rules: NewRuleDeck) -> _UnitGeometry:
    """Derive the complete unit geometry from PDK rules and track counts."""

    grid = _required_rule(rules.manufacturing_grid, "manufacturing grid")
    metal_rules = [getattr(rules, f"M{layer}") for layer in params.active_layers]
    stack_metal_rules = [
        getattr(rules, f"M{layer}") for layer in range(params.route_layer, params.active_layers[-1] + 1)
    ]
    track_pitch = max(_required_rule(rule.pitch, "active-metal pitch") for rule in metal_rules)
    min_width = max(_required_rule(rule.width, "active-metal minimum width") for rule in metal_rules)
    # Widths used about a centre line must be an even number of grids so that
    # both edges remain on the manufacturing grid.
    centered_grid = 2 * grid
    finger_width = _snap_up(min_width, centered_grid)
    weight_step = _snap_up(2 * track_pitch, grid)

    via_rules = [getattr(rules, f"VIA{layer}") for layer in range(params.route_layer, params.active_layers[-1])]
    via_cut = max(
        _required_rule(rule.cut_width if rule.cut_width is not None else rule.width, "via cut width")
        for rule in via_rules
    )
    via_spacing = max(
        _required_rule(getattr(rule.spacing, f"VIA{layer}", None), "via cut spacing")
        for layer, rule in zip(range(params.route_layer, params.active_layers[-1]), via_rules, strict=True)
    )
    via_pitch = _snap_up(via_cut + via_spacing, centered_grid)
    enclosure_rules = [rule.via_enclosure for rule in via_rules]
    if any(rule is None for rule in enclosure_rules):
        raise ValueError("PDK rule deck is missing a via-enclosure alternative")
    opposite = max(rule.opposite for rule in enclosure_rules if rule is not None)
    minimum = max(rule.minimum for rule in enclosure_rules if rule is not None)
    via_landing = _snap_up(via_pitch + via_cut + 2 * opposite, centered_grid)
    landing_short = _snap_up(max(finger_width, via_cut + 2 * minimum), centered_grid)
    min_metal_area = max(_required_rule(rule.area, "stack-metal minimum area") for rule in stack_metal_rules)
    area_limited_length = (min_metal_area + landing_short - 1) // landing_short
    landing_long = _snap_up(max(via_landing, area_limited_length), centered_grid)
    # The shortest finger accommodates the complete two-cut access landing.
    tail_length = params.family.tail_landings * landing_long
    nominal_length = tail_length + params.family.coarse_weight * weight_step
    longest_parallel_run = nominal_length + params.family.coarse_weight * weight_step

    layer_gaps: list[int] = []
    for layer, rule in zip(params.active_layers, metal_rules, strict=True):
        spacing = _required_rule(
            getattr(rule.spacing, f"M{layer}", None),
            "active-metal spacing",
        )
        for conditional in rule.parallel_spacing:
            if finger_width > conditional.min_width and longest_parallel_run > conditional.min_parallel_run_length:
                spacing = max(spacing, conditional.spacing)
        layer_gaps.append(spacing)
    gap = _snap_up(
        max(layer_gaps),
        grid,
    )
    # The narrow fingers can invoke a larger dense line-end spacing even when
    # their long sidewalls retain the ordinary same-layer spacing.  Keep the
    # two distances independent instead of widening every conductor.
    end_gap = _snap_up(
        max(
            [
                gap,
                *(
                    rule.spacing
                    for metal in metal_rules
                    for rule in metal.end_of_line
                    if finger_width < rule.max_edge_length
                ),
            ]
        ),
        grid,
    )

    ring_width = finger_width
    inner_width = finger_width + 2 * gap
    inner_height = 2 * nominal_length + 3 * end_gap
    outer_width = inner_width + 2 * ring_width
    outer_height = inner_height + 2 * ring_width
    unit_pitch = outer_width - ring_width
    shield_spacing = _required_rule(
        getattr(getattr(rules, f"M{params.shield_layer}").spacing, f"M{params.shield_layer}", None),
        "shield-metal spacing",
    )
    shield_rules = getattr(rules, f"M{params.shield_layer}")
    shield_cutout_width = landing_short + 2 * shield_spacing
    enclosed_area = _required_rule(shield_rules.enclosed_area, "shield minimum enclosed area")
    bridge_pitch = params.family.shield_bridge_tracks * track_pitch
    hole_height = _snap_up((enclosed_area + gap - 1) // gap, grid)
    if bridge_pitch - ring_width < hole_height:
        raise ValueError("shield bridge pitch leaves holes below the PDK minimum enclosed area")
    bridge_extent = (outer_height - 4 * ring_width - end_gap - hole_height) // 2
    bridge_count = bridge_extent // bridge_pitch
    if bridge_count < 1:
        # A short family can fit just one bridge from each end, with no
        # intervening same-half holes. Keep its central hole and access clear.
        bridge_count = 1
        bridge_pitch = (bridge_extent // grid) * grid
        if bridge_pitch < landing_long + end_gap:
            raise ValueError("unit family is too short for the shield and plate access")
    bridge_ys = tuple(
        sorted(
            [ring_width + end_gap + k * bridge_pitch for k in range(1, bridge_count + 1)]
            + [outer_height - 2 * ring_width - k * bridge_pitch for k in range(1, bridge_count + 1)]
        )
    )
    mesh_density = 1.0 - (2 * gap / outer_width) * (1 - ring_width / bridge_pitch)
    max_density = shield_rules.max_density
    if max_density is not None and mesh_density > max_density:
        raise ValueError("rule-derived shield mesh does not satisfy the maximum-density rule")

    return _UnitGeometry(
        grid=grid,
        finger_width=finger_width,
        gap=gap,
        end_gap=end_gap,
        track_pitch=track_pitch,
        weight_step=weight_step,
        tail_length=tail_length,
        nominal_length=nominal_length,
        ring_width=ring_width,
        outer_width=outer_width,
        outer_height=outer_height,
        unit_pitch=unit_pitch,
        via_cut=via_cut,
        via_pitch=via_pitch,
        via_landing=via_landing,
        via_opposite_enclosure=opposite,
        via_minimum_enclosure=minimum,
        landing_short=landing_short,
        landing_long=landing_long,
        shield_spacing=shield_spacing,
        shield_cutout_width=shield_cutout_width,
        shield_bridge_ys=bridge_ys,
        side_extension=params.family.side_access_tracks * track_pitch + ring_width,
    )


def _um(value_nm: float) -> float:
    """Convert integer-nanometre rule values to KLayout D-geometry microns."""

    return float(value_nm) / 1000.0


def _metal(generic: GenericLayers, number: int) -> db.LayerInfo:
    return getattr(generic, f"M{number}")


def _pin(generic: GenericLayers, number: int) -> db.LayerInfo:
    return getattr(generic, f"PIN{number}")


def _via(generic: GenericLayers, lower_metal: int) -> db.LayerInfo:
    return getattr(generic, f"VIA{lower_metal}")


def _insert_box(cell: db.Cell, layer: db.LayerInfo, x0: float, y0: float, x1: float, y1: float) -> None:
    cell.shapes(layer).insert(db.DBox(x0, y0, x1, y1))


def _insert_ring(cell: db.Cell, layer: db.LayerInfo, width: float, height: float, thickness: float) -> None:
    _insert_box(cell, layer, 0, 0, width, thickness)
    _insert_box(cell, layer, 0, height - thickness, width, height)
    _insert_box(cell, layer, 0, thickness, thickness, height - thickness)
    _insert_box(cell, layer, width - thickness, thickness, width, height - thickness)


def _access_centers(geometry: _UnitGeometry) -> tuple[float, float, float]:
    """Centers of the two-cut via arrays, toward the outside of each landing."""
    x = _um(geometry.ring_width + geometry.gap + geometry.finger_width / 2)
    bottom = _um(geometry.ring_width + geometry.end_gap + geometry.via_landing / 2)
    top = _um(geometry.outer_height) - bottom
    return x, bottom, top


def _landing_box(
    cell: db.Cell,
    layer: db.LayerInfo,
    x: float,
    y: float,
    geometry: _UnitGeometry,
    *,
    horizontal: bool = False,
) -> None:
    short = _um(geometry.landing_short)
    long = _um(geometry.landing_long)
    width, height = (long, short) if horizontal else (short, long)
    _insert_box(cell, layer, x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def _via_box(
    cell: db.Cell,
    layer: db.LayerInfo,
    x: float,
    y: float,
    geometry: _UnitGeometry,
    *,
    rows: int = 2,
    columns: int = 1,
) -> None:
    half = _um(geometry.via_cut) / 2
    pitch = _um(geometry.via_pitch)
    for row in range(rows):
        for column in range(columns):
            cx = x + (column - (columns - 1) / 2) * pitch
            cy = y + (row - (rows - 1) / 2) * pitch
            _insert_box(cell, layer, cx - half, cy - half, cx + half, cy + half)


def _insert_shield(
    cell: db.Cell,
    layer: db.LayerInfo,
    geometry: _UnitGeometry,
    *,
    shared_routing: bool,
) -> None:
    """Mesh of longitudinal strips and symmetric bridges with open M4 corridors."""
    width = _um(geometry.outer_width)
    height = _um(geometry.outer_height)
    ring = _um(geometry.ring_width)
    inner_x = ring + _um(geometry.gap)
    if shared_routing:
        bottom = _um(geometry.shield_bridge_ys[0])
        top = _um(geometry.shield_bridge_ys[-1]) + ring
        inner_bottom, inner_top = bottom, top
    else:
        bottom, top = 0.0, height
        inner_bottom = _um(geometry.ring_width + 2 * geometry.end_gap + geometry.landing_long)
        inner_top = height - inner_bottom
        _insert_box(cell, layer, 0, 0, width, ring)
        _insert_box(cell, layer, 0, height - ring, width, height)
    _insert_box(cell, layer, 0, bottom, ring, top)
    _insert_box(cell, layer, width - ring, bottom, width, top)
    _insert_box(cell, layer, inner_x, inner_bottom, inner_x + _um(geometry.finger_width), inner_top)
    for bridge_y in geometry.shield_bridge_ys:
        y = _um(bridge_y)
        _insert_box(cell, layer, 0, y, width, y + ring)


def _insert_recognition_marker(
    cell: db.Cell,
    generic: GenericLayers,
    tag_layer: db.LayerInfo,
    geometry: _UnitGeometry,
    y0: float,
    y1: float,
    *,
    side: str,
) -> None:
    """Mark one inner/top-plate pair and reach the shield without another plate."""

    inset = _um(geometry.grid)
    ring = _um(geometry.ring_width)
    band = db.DBox(inset, y0, _um(geometry.unit_pitch) - inset, y1)
    if side == "main":
        tail_x0, tail_x1 = inset, ring / 2 - inset
    elif side == "diff":
        tail_x0, tail_x1 = ring / 2 + inset, ring - inset
    else:
        raise ValueError(f"unknown recognition side {side!r}")
    center_y = _um(geometry.outer_height) / 2
    tail = db.DBox(tail_x0, min(y0, center_y), tail_x1, max(y1, center_y))
    for layer in (generic.MOM_RECOG, tag_layer):
        cell.shapes(layer).insert(band)
        cell.shapes(layer).insert(tail)
    # The device body must span both capacitor terminals, whereas the bulk
    # selector touches only the shield.  Keeping these purposes separate
    # prevents route-metal crossings inside the body from becoming spurious
    # bulk terminals after the CDAC is integrated into its ADC.
    shield_bottom = _um(geometry.shield_bridge_ys[0]) + inset
    shield_top = _um(geometry.shield_bridge_ys[-1] + geometry.ring_width) - inset
    cell.shapes(generic.MOM_RECOG_SHIELD).insert(
        db.DBox(tail_x0, max(tail.bottom, shield_bottom), tail_x1, min(tail.top, shield_top))
    )


def _build_unit_cell(
    layout: db.Layout,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
    weight: int,
) -> db.Cell:
    """Build one weighted main/diff unit across the selected active stack."""

    suffix = "_".join(f"m{layer}" for layer in params.active_layers)
    name = f"frida_mom_w{weight}_{suffix}" if weight else f"frida_mom_dummy_{suffix}"
    cell = layout.create_cell(name)
    width = _um(geometry.outer_width)
    height = _um(geometry.outer_height)
    ring = _um(geometry.ring_width)
    gap = _um(geometry.gap)
    end_gap = _um(geometry.end_gap)
    finger = _um(geometry.finger_width)
    nominal = _um(geometry.nominal_length)
    delta = _um(weight * geometry.weight_step)
    x0 = ring + gap
    inner_y0 = ring + end_gap
    bottom_y1 = inner_y0 + nominal + delta
    top_y0 = inner_y0 + nominal + end_gap + delta
    top_y1 = height - ring - end_gap

    for metal_number in params.active_layers:
        layer = _metal(generic, metal_number)
        _insert_ring(cell, layer, width, height, ring)
        _insert_box(cell, layer, x0, inner_y0, x0 + finger, bottom_y1)
        _insert_box(cell, layer, x0, top_y0, x0 + finger, top_y1)

    # Each stacked capacitor gets a spatially disjoint recognition body. The
    # common generic purpose identifies FRIDA MOMs; PDK-local tag purposes
    # pick the active metal without allowing Calibre to combine stacked terminals.
    band_height = finger
    band_step = band_height + _um(geometry.grid)
    main_marker_y = inner_y0 + _um(geometry.tail_length)
    diff_marker_y = top_y0 if weight == params.family.coarse_weight else top_y1 - _um(geometry.tail_length)
    # Edge dummies have intentionally floating inner plates and no source
    # devices, following the historical LVS recognition convention.
    for index, metal_number in enumerate(params.active_layers if weight else ()):
        main_y0 = main_marker_y + index * band_step
        diff_y0 = diff_marker_y + index * band_step
        tag_layer = getattr(generic, f"MOM_RECOG_M{metal_number}")
        _insert_recognition_marker(
            cell,
            generic,
            tag_layer,
            geometry,
            main_y0,
            main_y0 + band_height,
            side="main",
        )
        _insert_recognition_marker(
            cell,
            generic,
            tag_layer,
            geometry,
            diff_y0,
            diff_y0 + band_height,
            side="diff",
        )

    _insert_shield(
        cell,
        _metal(generic, params.shield_layer),
        geometry,
        shared_routing=params.route_layer == params.shield_layer,
    )
    access_x, bottom_access, top_access = _access_centers(geometry)
    extension = _um(geometry.landing_long - geometry.via_landing) / 2
    for access_y, landing_y in ((bottom_access, bottom_access + extension), (top_access, top_access - extension)):
        for metal_number in range(params.route_layer, params.active_layers[0]):
            _landing_box(cell, _metal(generic, metal_number), access_x, landing_y, geometry)
        for lower_metal in range(params.route_layer, params.active_layers[-1]):
            _via_box(cell, _via(generic, lower_metal), access_x, access_y, geometry)

    return cell


def _build_unit_library(
    layout: db.Layout,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
) -> dict[int, db.Cell]:
    """Build every legal positive unit weight through ``coarse_weight``."""

    return {
        weight: _build_unit_cell(layout, generic, params, geometry, weight)
        for weight in range(1, params.family.coarse_weight + 1)
    }


def _ordered_groups(weights: list[int], chunks: list[list[int]]) -> list[tuple[int, int, list[int]]]:
    """Return ``(stage, electrical_weight, chunks)`` in physical order.

    Electrical indices remain chronological: C0 is the largest and is
    switched first. Physical groups retain the fabricated arrangement with
    small capacitors on the local left and large capacitors on the right.
    Equal weights put the later stage farther left.
    """

    groups = [(stage, weight, sorted(group)) for stage, (weight, group) in enumerate(zip(weights, chunks))]
    return sorted(groups, key=lambda item: (item[1], -item[0]))


def _add_route_pins(
    top: db.Cell,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
    placed_groups: list[tuple[int, int, int, int]],
) -> None:
    route = _metal(generic, params.route_layer)
    pin = _pin(generic, params.route_layer)
    x_local, bottom_y, top_y = _access_centers(geometry)
    pitch = _um(geometry.unit_pitch)
    height = _um(geometry.landing_long)
    end_margin = _um(geometry.landing_short) / 2
    pin_size = _um(max(geometry.grid, geometry.finger_width))
    extension = _um(geometry.landing_long - geometry.via_landing) / 2

    for stage, _weight, first_position, group_size in placed_groups:
        x0 = first_position * pitch + x_local - end_margin
        x1 = (first_position + group_size - 1) * pitch + x_local + end_margin
        for kind, y in (("main", bottom_y), ("diff", top_y)):
            landing_y = y + extension if kind == "main" else y - extension
            _insert_box(top, route, x0, landing_y - height / 2, x1, landing_y + height / 2)
            center_x = first_position * pitch + x_local
            label = f"cap_botplate_{kind}<{stage}>"
            top.shapes(pin).insert(db.DText(label, db.DTrans(center_x, y)))
            _insert_box(
                top,
                pin,
                center_x - pin_size / 2,
                y - pin_size / 2,
                center_x + pin_size / 2,
                y + pin_size / 2,
            )


def _add_topplate_access(
    top: db.Cell,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
    array_right: float,
) -> None:
    """Add the right-side topplate bar, layer stitch, and route pin."""

    ring = _um(geometry.ring_width)
    pad = _um(geometry.via_landing)
    stack_left = array_right + _um(geometry.shield_cutout_width)
    stack_x = stack_left + pad / 2
    _, _, upper_access = _access_centers(geometry)
    y = upper_access - _um(geometry.landing_long + geometry.via_opposite_enclosure)
    bar_bottom = _um(geometry.outer_height) - ring

    for metal_number in range(params.route_layer, params.active_layers[-1] + 1):
        layer = _metal(generic, metal_number)
        if metal_number in params.active_layers:
            _insert_box(top, layer, 0, bar_bottom, stack_left, bar_bottom + pad)
            _insert_box(top, layer, stack_left, y - pad / 2, stack_left + pad, bar_bottom + pad)
        _insert_box(top, layer, stack_left, y - pad / 2, stack_left + pad, y + pad / 2)
    for lower_metal in range(params.route_layer, params.active_layers[-1]):
        _via_box(top, _via(generic, lower_metal), stack_x, y, geometry, columns=2)

    pin = _pin(generic, params.route_layer)
    top.shapes(pin).insert(db.DText("cap_topplate", db.DTrans(stack_x, y)))
    _insert_box(top, pin, stack_x - ring / 2, y - ring / 2, stack_x + ring / 2, y + ring / 2)


def _add_shield_taps(
    top: db.Cell,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
    array_right: float,
    output_right: float,
) -> None:
    """Connect the lower shield to route metal through repeated right taps."""

    route = _metal(generic, params.route_layer)
    pin = _pin(generic, params.route_layer)
    ring = _um(geometry.ring_width)
    tap_x = array_right - ring / 2
    ys = [_um(y) + ring / 2 for y in geometry.shield_bridge_ys]
    for index, y in enumerate(ys):
        for metal_number in range(params.route_layer, params.shield_layer):
            _landing_box(top, _metal(generic, metal_number), tap_x, y, geometry, horizontal=True)
        for lower_metal in range(params.route_layer, params.shield_layer):
            _via_box(top, _via(generic, lower_metal), tap_x, y, geometry, rows=1)
        start_x = array_right if params.route_layer == params.shield_layer else tap_x
        _insert_box(top, route, start_x, y - ring / 2, output_right, y + ring / 2)
        if index == len(ys) // 2:
            top.shapes(pin).insert(db.DText("cap_shieldplate", db.DTrans(output_right - ring / 2, y)))
            _insert_box(top, pin, output_right - ring, y - ring / 2, output_right, y + ring / 2)


def CdacLayout(params: CdacLayoutParams) -> db.Layout:
    """Build one arbitrary-width, rule-derived unit-length capacitor array."""

    if not is_valid_cdac_layout_params(params):
        raise ValueError(f"Invalid CDAC layout params: {params}")
    pdk_layout = import_module(f"pdk.{params.technology}.layout")
    rules = pdk_layout.rule_deck()
    geometry = _calc_unit_geometry(params, rules)
    weights = get_cdac_weights(params.cdac)
    partitioned = _calc_weight_partitions(weights, params.family.coarse_weight)
    ordered = _ordered_groups(weights, partitioned)

    layout = db.Layout()
    layout.dbu = pdk_layout.DBU
    generic = load_generic_layers(layout)
    top = layout.create_cell(params.top_cell)
    unit_library = _build_unit_library(layout, generic, params, geometry)
    if params.family.edge_dummy_units:
        unit_library[0] = _build_unit_cell(layout, generic, params, geometry, 0)

    position = 0
    for _ in range(params.family.edge_dummy_units):
        top.insert(db.DCellInstArray(unit_library[0].cell_index(), db.DTrans(_um(position * geometry.unit_pitch), 0)))
        position += 1
    placed_groups: list[tuple[int, int, int, int]] = []
    for stage, weight, group in ordered:
        first_position = position
        for chunk in group:
            top.insert(
                db.DCellInstArray(
                    unit_library[chunk].cell_index(),
                    db.DTrans(_um(position * geometry.unit_pitch), 0),
                )
            )
            position += 1
        placed_groups.append((stage, weight, first_position, len(group)))

    for _ in range(params.family.edge_dummy_units):
        top.insert(db.DCellInstArray(unit_library[0].cell_index(), db.DTrans(_um(position * geometry.unit_pitch), 0)))
        position += 1

    _add_route_pins(top, generic, params, geometry, placed_groups)
    array_right = _um((position - 1) * geometry.unit_pitch + geometry.outer_width)
    output_right = array_right + _um(geometry.side_extension)
    _add_topplate_access(top, generic, params, geometry, array_right)
    _add_shield_taps(top, generic, params, geometry, array_right, output_right)
    _insert_box(
        top,
        generic.PR_BOUNDARY,
        0,
        0,
        output_right,
        _um(geometry.outer_height - geometry.ring_width + geometry.via_landing),
    )

    remap_layers(layout, pdk_layout.layer_map())
    return layout


def _layout_manifest(params: CdacLayoutParams) -> dict[str, Any]:
    """Return a serializable electrical, decomposition, stack, and rule manifest."""

    if not is_valid_cdac_layout_params(params):
        raise ValueError(f"Invalid CDAC layout params: {params}")
    pdk_layout = import_module(f"pdk.{params.technology}.layout")
    weights = get_cdac_weights(params.cdac)
    chunks = _calc_weight_partitions(weights, params.family.coarse_weight)
    geometry = _calc_unit_geometry(params, pdk_layout.rule_deck())
    return {
        "technology": params.technology,
        "top_cell": params.top_cell,
        "weights_by_stage": weights,
        "partitioned_weights_by_stage": chunks,
        "physical_chunk_count": sum(len(group) for group in chunks),
        "edge_dummy_count": 2 * params.family.edge_dummy_units,
        "placed_unit_count": sum(len(group) for group in chunks) + 2 * params.family.edge_dummy_units,
        "port_count": 2 * len(weights) + 2,
        "unit_family": asdict(params.family),
        "stack": {
            "route_layer": params.route_layer,
            "shield_layer": params.shield_layer,
            "active_layers": list(params.active_layers),
        },
        "derived_geometry_nm": asdict(geometry),
    }
