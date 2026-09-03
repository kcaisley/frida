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
    tail_tracks: int = 5
    shield_edge_clear_rows: int = 2


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
    shield_tap_count: int = 8


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
    via_opposite_enclosure: int
    via_minimum_enclosure: int
    landing_short: int
    landing_long: int
    shield_spacing: int
    shield_cutout_width: int
    shield_cutout_height: int
    shield_mesh_bridge: int
    shield_edge_clearance: int


def is_valid_cdac_layout_params(params: CdacLayoutParams) -> bool:
    """Validate one complete process-independent CDAC layout configuration."""

    family = params.family
    if not is_valid_cdac_params(params.cdac):
        return False
    if not params.technology or not params.top_cell:
        return False
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (family.coarse_weight, family.tail_tracks, family.shield_edge_clear_rows, params.shield_tap_count)
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
    tail_length = _snap_up(params.family.tail_tracks * track_pitch, grid)
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

    via_rules = [getattr(rules, f"VIA{layer}") for layer in range(params.route_layer, params.active_layers[-1])]
    via_cut = max(
        _required_rule(rule.cut_width if rule.cut_width is not None else rule.width, "via cut width")
        for rule in via_rules
    )
    enclosure_rules = [rule.via_enclosure for rule in via_rules]
    if any(rule is None for rule in enclosure_rules):
        raise ValueError("PDK rule deck is missing a via-enclosure alternative")
    opposite = max(rule.opposite for rule in enclosure_rules if rule is not None)
    minimum = max(rule.minimum for rule in enclosure_rules if rule is not None)

    ring_width = finger_width
    inner_width = finger_width + 2 * gap
    inner_height = 2 * nominal_length + 3 * end_gap
    outer_width = inner_width + 2 * ring_width
    outer_height = inner_height + 2 * ring_width
    unit_pitch = outer_width - ring_width
    landing_short = _snap_up(max(finger_width, via_cut + 2 * minimum), centered_grid)
    min_metal_area = max(_required_rule(rule.area, "stack-metal minimum area") for rule in stack_metal_rules)
    area_limited_length = (min_metal_area + landing_short - 1) // landing_short
    landing_long = _snap_up(
        max(via_cut + 2 * opposite, area_limited_length),
        centered_grid,
    )
    shield_spacing = _required_rule(
        getattr(getattr(rules, f"M{params.shield_layer}").spacing, f"M{params.shield_layer}", None),
        "shield-metal spacing",
    )
    shield_rules = getattr(rules, f"M{params.shield_layer}")
    shield_cutout_width = landing_short + 2 * shield_spacing
    enclosed_area = _required_rule(shield_rules.enclosed_area, "shield minimum enclosed area")
    cutout_area = enclosed_area + landing_short * landing_long
    shield_cutout_height = _snap_up(
        max(landing_long + 2 * shield_spacing, (cutout_area + shield_cutout_width - 1) // shield_cutout_width),
        centered_grid,
    )
    mesh_density = 1.0 - (shield_cutout_width / outer_width) * (
        shield_cutout_height / (shield_cutout_height + ring_width)
    )
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
        via_opposite_enclosure=opposite,
        via_minimum_enclosure=minimum,
        landing_short=landing_short,
        landing_long=landing_long,
        shield_spacing=shield_spacing,
        shield_cutout_width=shield_cutout_width,
        shield_cutout_height=shield_cutout_height,
        shield_mesh_bridge=ring_width,
        shield_edge_clearance=params.family.shield_edge_clear_rows * (shield_cutout_height + ring_width),
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
    x = _um(geometry.ring_width + geometry.gap + geometry.finger_width / 2)
    bottom = _um(
        max(
            geometry.ring_width + geometry.end_gap + geometry.landing_long / 2,
            geometry.ring_width + geometry.shield_cutout_height / 2,
        )
    )
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


def _via_box(cell: db.Cell, layer: db.LayerInfo, x: float, y: float, geometry: _UnitGeometry) -> None:
    half = _um(geometry.via_cut) / 2
    _insert_box(cell, layer, x - half, y - half, x + half, y + half)


def _shield_polygon(geometry: _UnitGeometry, *, shared_routing: bool) -> db.DPolygon:
    width = _um(geometry.outer_width)
    height = _um(geometry.outer_height)
    x, bottom, top = _access_centers(geometry)
    hole_w = _um(geometry.shield_cutout_width)
    hole_h = _um(geometry.shield_cutout_height)
    bridge = _um(geometry.shield_mesh_bridge)

    if shared_routing:
        # The route and shield intentionally share one mask layer.  Clear the
        # complete upper and lower routing corridors instead of surrounding
        # each landing with shield metal, which would short the horizontal
        # plate buses as soon as they leave their local cutouts.
        clearance = _um(geometry.shield_edge_clearance)
        shield_bottom = clearance
        shield_top = height - clearance
        if shield_top <= shield_bottom:
            raise ValueError("rule-derived shared route/shield corridors consume the shield")
        polygon = db.DPolygon(
            [
                db.DPoint(0, shield_bottom),
                db.DPoint(0, shield_top),
                db.DPoint(width, shield_top),
                db.DPoint(width, shield_bottom),
            ]
        )
        slot_y = shield_bottom + bridge
        slot_limit = shield_top - bridge
        while slot_y + hole_h <= slot_limit:
            polygon.insert_hole(
                [
                    db.DPoint(x - hole_w / 2, slot_y),
                    db.DPoint(x + hole_w / 2, slot_y),
                    db.DPoint(x + hole_w / 2, slot_y + hole_h),
                    db.DPoint(x - hole_w / 2, slot_y + hole_h),
                ]
            )
            slot_y += hole_h + bridge
        return polygon

    polygon = db.DPolygon([db.DPoint(0, 0), db.DPoint(0, height), db.DPoint(width, height), db.DPoint(width, 0)])
    access_holes = (
        (bottom - hole_h / 2, bottom + hole_h / 2),
        (top - hole_h / 2, top + hole_h / 2),
    )
    for y0, y1 in access_holes:
        polygon.insert_hole(
            [
                db.DPoint(x - hole_w / 2, y0),
                db.DPoint(x + hole_w / 2, y0),
                db.DPoint(x + hole_w / 2, y1),
                db.DPoint(x - hole_w / 2, y1),
            ]
        )
    slot_y = access_holes[0][1] + bridge
    slot_limit = access_holes[1][0] - bridge
    while slot_y + hole_h <= slot_limit:
        polygon.insert_hole(
            [
                db.DPoint(x - hole_w / 2, slot_y),
                db.DPoint(x + hole_w / 2, slot_y),
                db.DPoint(x + hole_w / 2, slot_y + hole_h),
                db.DPoint(x - hole_w / 2, slot_y + hole_h),
            ]
        )
        slot_y += hole_h + bridge
    return polygon


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
    cell.shapes(generic.MOM_RECOG_SHIELD).insert(tail)


def _build_unit_cell(
    layout: db.Layout,
    generic: GenericLayers,
    params: CdacLayoutParams,
    geometry: _UnitGeometry,
    weight: int,
) -> db.Cell:
    """Build one weighted main/diff unit across the selected active stack."""

    suffix = "_".join(f"m{layer}" for layer in params.active_layers)
    cell = layout.create_cell(f"frida_mom_w{weight}_{suffix}")
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
    for index, metal_number in enumerate(params.active_layers):
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

    cell.shapes(_metal(generic, params.shield_layer)).insert(
        _shield_polygon(geometry, shared_routing=params.route_layer == params.shield_layer)
    )
    access_x, bottom_access, top_access = _access_centers(geometry)
    for access_y in (bottom_access, top_access):
        for metal_number in range(params.route_layer, params.active_layers[0]):
            _landing_box(cell, _metal(generic, metal_number), access_x, access_y, geometry)
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
    """Return ``(bit, electrical_weight, chunks)`` in physical order."""

    n_bits = len(weights)
    groups = [(n_bits - 1 - index, weight, sorted(group)) for index, (weight, group) in enumerate(zip(weights, chunks))]
    return sorted(groups, key=lambda item: (item[1], item[0]))


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
    height = _um(geometry.finger_width)
    end_margin = _um(geometry.landing_short) / 2
    pin_size = _um(max(geometry.grid, geometry.finger_width))

    for bit, _weight, first_position, group_size in placed_groups:
        x0 = first_position * pitch + x_local - end_margin
        x1 = (first_position + group_size - 1) * pitch + x_local + end_margin
        for kind, y in (("main", bottom_y), ("diff", top_y)):
            _insert_box(top, route, x0, y - height / 2, x1, y + height / 2)
            center_x = (x0 + x1) / 2
            label = f"cap_botplate_{kind}<{bit}>"
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
) -> float:
    """Add the right-side topplate bar, layer stitch, and route pin."""

    ring = _um(geometry.ring_width)
    pitch = _um(geometry.track_pitch)
    gap = _um(geometry.gap)
    opposite = _um(geometry.via_opposite_enclosure)
    stack_x = array_right + gap + _um(geometry.landing_short) / 2
    y = _um(geometry.outer_height) - _um(geometry.landing_long) / 2
    output_right = array_right + pitch + opposite

    for metal_number in range(params.route_layer, params.active_layers[-1] + 1):
        layer = _metal(generic, metal_number)
        if metal_number in params.active_layers:
            _insert_box(top, layer, array_right - ring, y - ring / 2, stack_x, y + ring / 2)
        _landing_box(top, layer, stack_x, y, geometry)
    for lower_metal in range(params.route_layer, params.active_layers[-1]):
        _via_box(top, _via(generic, lower_metal), stack_x, y, geometry)

    route = _metal(generic, params.route_layer)
    pin = _pin(generic, params.route_layer)
    _insert_box(top, route, stack_x, y - ring / 2, output_right, y + ring / 2)
    top.shapes(pin).insert(db.DText("cap_topplate", db.DTrans(output_right - ring / 2, y)))
    _insert_box(top, pin, output_right - ring, y - ring / 2, output_right, y + ring / 2)
    return output_right


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
    height = _um(geometry.outer_height)
    tap_x = array_right - ring / 2
    tap_height = _um(geometry.landing_short)
    grid = _um(geometry.grid)
    ys = [
        round((height * (index + 1) / (params.shield_tap_count + 1)) / grid) * grid
        for index in range(params.shield_tap_count)
    ]
    for index, y in enumerate(ys):
        for metal_number in range(params.route_layer, params.shield_layer):
            _landing_box(top, _metal(generic, metal_number), tap_x, y, geometry, horizontal=True)
        for lower_metal in range(params.route_layer, params.shield_layer):
            _via_box(top, _via(generic, lower_metal), tap_x, y, geometry)
        _insert_box(top, route, tap_x, y - tap_height / 2, output_right, y + tap_height / 2)
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

    position = 0
    placed_groups: list[tuple[int, int, int, int]] = []
    for bit, weight, group in ordered:
        first_position = position
        for chunk in group:
            top.insert(
                db.DCellInstArray(
                    unit_library[chunk].cell_index(),
                    db.DTrans(_um(position * geometry.unit_pitch), 0),
                )
            )
            position += 1
        placed_groups.append((bit, weight, first_position, len(group)))

    _add_route_pins(top, generic, params, geometry, placed_groups)
    array_right = _um((position - 1) * geometry.unit_pitch + geometry.outer_width)
    output_right = _add_topplate_access(top, generic, params, geometry, array_right)
    _add_shield_taps(top, generic, params, geometry, array_right, output_right)
    _insert_box(top, generic.PR_BOUNDARY, 0, 0, output_right, _um(geometry.outer_height))

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
        "weights_msb_first": weights,
        "partitioned_weights_msb_first": chunks,
        "physical_chunk_count": sum(len(group) for group in chunks),
        "port_count": 2 * len(weights) + 2,
        "unit_family": asdict(params.family),
        "stack": {
            "route_layer": params.route_layer,
            "shield_layer": params.shield_layer,
            "active_layers": list(params.active_layers),
        },
        "derived_geometry_nm": asdict(geometry),
    }
