"""Fringe MOM capacitor cells drawn from the PDK's ``tech`` values, as stems rectangles.

The same cell model as the row cells (``rowcell.Cell`` of ``Rect``), in integer nanometres, so
capacitors are drawn by the engine the ALIGN flow draws its transistor cells with. The values come from the PDK's ``tech`` (``RULES``, ``LAYERS``, ``MFG_GRID``,
``MOM_LAYERS``), read when a function is called; a PDK names no capacitor device. Two families:

- test structures (``mom_geometry``): the dimensions of the three FMOM styles on the top 1-3
  ``MOM_LAYERS``, which ALIGN's ``MomUnit`` generator draws (``flow/layout/align/pdk/mom.py``).
  Their extraction (``flow.momcap``) gives the PDK's capacitance model;
- the CDAC (``difference_geometry``, ``difference_unit``, ``caparray_cells``): difference units of
  a weight family over a shield mesh, with two-cut access landings down to the route metal, side
  by side sharing their ring walls, and the array's buses, top-plate stack and shield taps.

Pins are ``kind="pin"`` rectangles on a metal's ``.PIN`` layer, labelled with their net at their
centre (``to_klayout``).
"""

from __future__ import annotations

import math

import tech
from rowcell import Cell

STYLES = ("difference", "ring", "strip")
# the terminals each style pins (and SHIELD), in the order its plates are listed
TERMINALS = {"difference": ("TOP", "MAIN", "DIFF"), "ring": ("TOP", "INNER"), "strip": ("A", "B")}


def _snap(value: int, grid: int) -> int:
    return -(-value // grid) * grid


def _nm(value: float) -> int:
    """A coordinate on the database grid, rounded half up as a klayout D-box is."""
    return math.floor(value + 0.5)


def _box(cell: Cell, layer: str, x0: float, y0: float, x1: float, y1: float, net=None, kind="drawing") -> None:
    cell.add(layer, _nm(x0), _nm(y0), _nm(x1), _nm(y1), net, kind)


def _required(value, description: str):
    if value is None:
        raise ValueError(f"PDK rules are missing {description}")
    return value


def _rules(layer: str) -> dict:
    """One layer's entry in the PDK's ``RULES`` (an empty one where the PDK lists none)."""
    return tech.RULES.get(layer, {})


# ---------------------------------------------------------------------------------------------
# test structures


def mom_geometry(layers: int, space: int = 0) -> dict:
    """A test family's dimensions (nm) on the top ``layers`` MOM metals.

    The fingers take the widest minimum width of their metals, or what their vias need (an even
    number of grids, so a centred finger stays on grid), the spacing that width needs alongside a long run (or
    ``space``, where wider), and the line-end gap; the vias between stacked plates the widest cut,
    its end enclosure along the finger, and its side enclosure, which a finger's width must hold.
    """

    if not 1 <= layers <= len(tech.MOM_LAYERS):
        raise ValueError(f"the PDK stacks 1 to {len(tech.MOM_LAYERS)} MOM metals")
    grid = tech.MFG_GRID
    metals = tuple(tech.MOM_LAYERS[-layers:])
    rules = [tech.RULES[f"M{metal}"] for metal in metals]
    width = max(rule["width"] for rule in rules)
    # a finger holds its via's cut and side enclosure where the metal's minimum width does not
    for metal in metals[:-1]:
        via = tech.RULES[f"V{metal}"]
        if "enclosure" not in via:
            raise ValueError(f"the PDK has no V{metal} enclosure rule (layout/tech.py RULES)")
        width = max(width, via["cut"] + 2 * via["enclosure"][1])
    width = _snap(width, 2 * grid)
    minimum = max(rule["space"] for rule in rules)
    for rule in rules:
        # (space, above width, above parallel run length): a long finger meets every run length
        for conditional, above_width, _run in rule.get("parallel_space", ()):
            if width > above_width:
                minimum = max(minimum, conditional)
    # (space, below edge length, extension): a narrow finger's end
    end_gap = max(
        [minimum, *(gap for rule in rules for gap, below, _ext in rule.get("end_of_line", ()) if width < below)]
    )
    via_cut, via_end = 0, 0
    for metal in metals[:-1]:
        via = tech.RULES[f"V{metal}"]
        via_cut, via_end = max(via_cut, via["cut"]), max(via_end, via["enclosure"][0])
    return {
        "grid": grid,
        "metals": metals,
        "shield": tech.MOM_LAYERS[-layers] - 1,
        "width": width,
        "min_space": _snap(minimum, grid),
        "space": _snap(max(minimum, space), grid),
        "end_gap": _snap(end_gap, grid),
        "via_cut": via_cut,
        "via_end": via_end,
        # a finger holds its via column at the end
        "min_length": _snap(max(width, via_cut + 2 * via_end), grid),
    }


# ---------------------------------------------------------------------------------------------
# the CDAC: difference units over a shield mesh


def difference_geometry(family: dict, route: int, shield: int, active: tuple[int, ...]) -> dict:
    """Derive the CDAC unit geometry (nm) from the PDK's rules and the family's track counts.

    ``family``: ``coarse_weight``, ``tail_landings``, ``shield_bridge_tracks``,
    ``side_access_tracks`` and ``weight_step`` (the length a unit of weight adds to the main finger
    and takes from the difference finger, on the grid; None: two tracks), and for
    ``caparray_cells`` ``tied_dummies`` (the edge dummies' fingers on the top plate) and
    ``unary_length`` (the unary units' one finger); the plates on the
    ``active`` metals, the shield on ``shield``, the buses on ``route`` (``route == shield`` shares
    the metal: the shield keeps to the body).
    """

    grid = _required(getattr(tech, "MFG_GRID", None), "manufacturing grid")
    metal_rules = [_rules(f"M{layer}") for layer in active]
    stack_metal_rules = [_rules(f"M{layer}") for layer in range(route, active[-1] + 1)]
    track_pitch = max(_required(rule.get("pitch"), "active-metal pitch") for rule in metal_rules)
    min_width = max(_required(rule.get("width"), "active-metal minimum width") for rule in metal_rules)
    # widths about a centre line are an even number of grids, so both edges stay on grid
    centered_grid = 2 * grid
    # a unit of weight: the main finger that much longer, the difference finger that much shorter
    weight_step = family.get("weight_step") or _snap(2 * track_pitch, grid)
    if weight_step % grid:
        raise ValueError(f"a weight step of {weight_step} nm is off the {grid} nm grid")

    via_rules = [_rules(f"V{layer}") for layer in range(route, active[-1])]
    via_cut = max(_required(rule.get("cut"), "via cut width") for rule in via_rules)
    via_spacing = max(_required(rule.get("space"), "via cut spacing") for rule in via_rules)
    via_pitch = _snap(via_cut + via_spacing, centered_grid)
    # enclosure: (on two opposite sides, on the other two, on all four)
    enclosure_rules = [_required(rule.get("enclosure"), "a via-enclosure alternative") for rule in via_rules]
    opposite = max(rule[0] for rule in enclosure_rules)
    minimum = max(rule[1] for rule in enclosure_rules)
    # a finger holds the access vias' cut and side enclosure, where the metal's minimum width does not
    finger_width = _snap(max(min_width, via_cut + 2 * minimum), centered_grid)
    via_landing = _snap(via_pitch + via_cut + 2 * opposite, centered_grid)
    landing_short = _snap(max(finger_width, via_cut + 2 * minimum), centered_grid)
    min_metal_area = max(_required(rule.get("area"), "stack-metal minimum area") for rule in stack_metal_rules)
    area_limited_length = (min_metal_area + landing_short - 1) // landing_short
    landing_long = _snap(max(via_landing, area_limited_length), centered_grid)
    # the shortest finger holds the complete two-cut access landing
    tail_length = family["tail_landings"] * landing_long
    nominal_length = tail_length + family["coarse_weight"] * weight_step
    longest_parallel_run = nominal_length + family["coarse_weight"] * weight_step

    layer_gaps: list[int] = []
    for rule in metal_rules:
        spacing = _required(rule.get("space"), "active-metal spacing")
        # (space, above width, above parallel run length)
        for conditional, min_width_, min_run in rule.get("parallel_space", ()):
            if finger_width > min_width_ and longest_parallel_run > min_run:
                spacing = max(spacing, conditional)
        layer_gaps.append(spacing)
    gap = _snap(max(layer_gaps), grid)
    # narrow fingers can invoke a larger line-end spacing while their long sidewalls keep the
    # ordinary spacing: the two distances stay independent instead of widening every conductor
    end_gap = _snap(
        max(
            [
                gap,
                *(  # (space, below edge length, extension)
                    space
                    for metal in metal_rules
                    for space, max_edge, _extension in metal.get("end_of_line", ())
                    if finger_width < max_edge
                ),
            ]
        ),
        grid,
    )
    # the top-plate bar widens the units' top ring wall to a via landing, which the difference
    # fingers' ends face along a finger's width
    for rule in metal_rules:
        for conditional, above_width, above_run in rule.get("parallel_space", ()):
            if via_landing > above_width and finger_width > above_run:
                end_gap = max(end_gap, _snap(conditional, grid))

    ring_width = finger_width
    inner_width = finger_width + 2 * gap
    inner_height = 2 * nominal_length + 3 * end_gap
    outer_width = inner_width + 2 * ring_width
    outer_height = inner_height + 2 * ring_width
    unit_pitch = outer_width - ring_width
    shield_rules = _rules(f"M{shield}")
    shield_spacing = _required(shield_rules.get("space"), "shield-metal spacing")
    shield_cutout_width = landing_short + 2 * shield_spacing
    enclosed_area = _required(shield_rules.get("enclosed_area"), "shield minimum enclosed area")
    # the mesh's holes span a gap beside the strip under the fingers, or, where the shield metal's
    # holes must be wider than that, both gaps and the finger (no strip under it)
    hole_width = gap if gap >= shield_rules.get("hole_width", 0) else 2 * gap + finger_width
    hole_height = _snap((enclosed_area + hole_width - 1) // hole_width, grid)
    # the bridges every shield_bridge_tracks tracks, or as many more as the holes need
    bridge_pitch = max(family["shield_bridge_tracks"] * track_pitch, _snap(hole_height + ring_width, track_pitch))
    bridge_extent = (outer_height - 4 * ring_width - end_gap - hole_height) // 2
    bridge_count = bridge_extent // bridge_pitch
    if bridge_count < 1:
        # a short family fits one bridge from each end, with no holes between them in a half;
        # its central hole and access stay clear
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
    max_density = shield_rules.get("max_density")
    if max_density is not None and mesh_density > max_density:
        raise ValueError("rule-derived shield mesh does not satisfy the maximum-density rule")

    return {
        "grid": grid,
        "finger_width": finger_width,
        "gap": gap,
        "end_gap": end_gap,
        "track_pitch": track_pitch,
        "weight_step": weight_step,
        "tail_length": tail_length,
        "nominal_length": nominal_length,
        "ring_width": ring_width,
        "outer_width": outer_width,
        "outer_height": outer_height,
        "unit_pitch": unit_pitch,
        "via_cut": via_cut,
        "via_pitch": via_pitch,
        "via_landing": via_landing,
        "via_opposite_enclosure": opposite,
        "via_minimum_enclosure": minimum,
        "landing_short": landing_short,
        "landing_long": landing_long,
        "shield_spacing": shield_spacing,
        "shield_cutout_width": shield_cutout_width,
        "shield_bridge_ys": bridge_ys,
        "side_extension": family["side_access_tracks"] * track_pitch + ring_width,
    }


def _ring(cell: Cell, layer: str, width: int, height: int, thickness: int, net=None) -> None:
    cell.add(layer, 0, 0, width, thickness, net)
    cell.add(layer, 0, height - thickness, width, height, net)
    cell.add(layer, 0, thickness, thickness, height - thickness, net)
    cell.add(layer, width - thickness, thickness, width, height - thickness, net)


def _access_centers(g: dict) -> tuple[float, float, float]:
    """Centres of the two-cut via arrays, toward the outside of each landing."""
    x = g["ring_width"] + g["gap"] + g["finger_width"] / 2
    bottom = g["ring_width"] + g["end_gap"] + g["via_landing"] / 2
    return x, bottom, g["outer_height"] - bottom


def _landing(cell: Cell, layer: str, x: float, y: float, g: dict, *, horizontal: bool = False) -> None:
    short, long = g["landing_short"], g["landing_long"]
    width, height = (long, short) if horizontal else (short, long)
    _box(cell, layer, x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def _vias(cell: Cell, layer: str, x: float, y: float, g: dict, *, rows: int = 2, columns: int = 1) -> None:
    half, pitch = g["via_cut"] / 2, g["via_pitch"]
    for row in range(rows):
        for column in range(columns):
            cx = x + (column - (columns - 1) / 2) * pitch
            cy = y + (row - (rows - 1) / 2) * pitch
            _box(cell, layer, cx - half, cy - half, cx + half, cy + half)


def _shield(cell: Cell, layer: str, g: dict, *, shared_routing: bool) -> None:
    """A mesh of longitudinal strips and bridges, with open corridors for the access landings."""
    width, height, ring = g["outer_width"], g["outer_height"], g["ring_width"]
    inner_x = ring + g["gap"]
    if shared_routing:
        bottom = g["shield_bridge_ys"][0]
        top = g["shield_bridge_ys"][-1] + ring
        inner_bottom, inner_top = bottom, top
    else:
        bottom, top = 0, height
        inner_bottom = ring + 2 * g["end_gap"] + g["landing_long"]
        inner_top = height - inner_bottom
        cell.add(layer, 0, 0, width, ring)
        cell.add(layer, 0, height - ring, width, height)
    cell.add(layer, 0, bottom, ring, top)
    cell.add(layer, width - ring, bottom, width, top)
    if g["gap"] >= _rules(layer).get("hole_width", 0):
        cell.add(layer, inner_x, inner_bottom, inner_x + g["finger_width"], inner_top)
    for y in g["shield_bridge_ys"]:
        cell.add(layer, 0, y, width, y + ring)


def _recognition(cell: Cell, g: dict, y0: int, y1: int, *, side: str) -> None:
    """One U on the outer ring plus a full inner-finger measurement window.

    Adjacent units own opposite halves of each shared ring wall: the two Us end either side of
    the midpoint, the inner windows follow the actual split. No conducting layer changes.
    """

    inset, ring, pitch, height = g["grid"], g["ring_width"], g["unit_pitch"], g["outer_height"]
    left0, left1 = ring / 2 + inset, ring - inset
    right0, right1 = pitch + inset, pitch + ring / 2 - inset
    band_height = ring / 2 - 2 * inset
    if side == "main":
        band0 = ring / 2 + inset
        leg0, leg1 = band0, height / 2 - inset
    elif side == "diff":
        band0 = height - ring + inset
        leg0, leg1 = height / 2 + inset, band0 + band_height
    else:
        raise ValueError(f"unknown recognition side {side!r}")
    _box(cell, "MOM_RECOG", left0, band0, right1, band0 + band_height)
    _box(cell, "MOM_RECOG", left0, leg0, left1, leg1)
    _box(cell, "MOM_RECOG", right0, leg0, right1, leg1)
    inner_x = ring + g["gap"]
    _box(cell, "MOM_RECOG_INNER", inner_x - inset, y0 - inset, inner_x + g["finger_width"] + inset, y1 + inset)


def difference_unit(
    g: dict,
    route: int,
    shield: int,
    active: tuple[int, ...],
    weight: int,
    tied: bool = False,
    unary_length: int | None = None,
) -> Cell:
    """One weighted CDAC unit (weight 0: an edge dummy, its inner plates floating, or, ``tied``,
    each joined to the ring at its outer end: on the top plate, which it then does not load, the
    same pattern as a unit's with no access to the route metal). ``unary_length``: a unary unit,
    one main finger that long (nm) from the bottom and no difference finger, so nothing of it
    opposes its step; its ring and its length the same as every unit's."""

    suffix = "_".join(f"m{layer}" for layer in active)
    dummy = "frida_mom_dummy_tied" if tied else "frida_mom_dummy"
    name = f"frida_mom_w{weight}{'u' if unary_length else ''}_{suffix}"
    cell = Cell(name if weight else f"{dummy}_{suffix}", g["unit_pitch"])
    width, height, ring = g["outer_width"], g["outer_height"], g["ring_width"]
    x0 = ring + g["gap"]
    inner_y0 = ring + g["end_gap"]
    bottom_y1 = inner_y0 + g["nominal_length"] + weight * g["weight_step"]
    top_y0 = bottom_y1 + g["end_gap"]
    top_y1 = height - ring - g["end_gap"]
    tied = tied and not weight
    if unary_length:
        if not g["tail_length"] <= unary_length <= top_y1 - inner_y0:
            raise ValueError(f"a unary finger of {unary_length} nm does not fit its unit")
        bottom_y1 = inner_y0 + unary_length
    for metal in active:
        _ring(cell, f"M{metal}", width, height, ring)
        cell.add(f"M{metal}", x0, ring if tied else inner_y0, x0 + g["finger_width"], bottom_y1)
        if not unary_length:
            cell.add(f"M{metal}", x0, top_y0, x0 + g["finger_width"], height - ring if tied else top_y1)
    # the PDK's MOM recognition annotations, where its LVS recognizes the unit as a device
    if weight and tech.LAYERS.get("MOM_RECOG"):
        _recognition(cell, g, inner_y0, bottom_y1, side="main")
        if not unary_length:
            _recognition(cell, g, top_y0, top_y1, side="diff")
        inset = g["grid"]
        cell.add(
            "MOM_RECOG_SHIELD",
            inset,
            g["shield_bridge_ys"][0] + inset,
            width - inset,
            g["shield_bridge_ys"][-1] + ring - inset,
        )
    _shield(cell, f"M{shield}", g, shared_routing=route == shield)
    if tied:
        return cell
    access_x, bottom, top = _access_centers(g)
    extension = (g["landing_long"] - g["via_landing"]) / 2
    accesses = (
        ((bottom, bottom + extension),) if unary_length else ((bottom, bottom + extension), (top, top - extension))
    )
    for access_y, landing_y in accesses:
        for metal in range(route, active[0]):
            _landing(cell, f"M{metal}", access_x, landing_y, g)
        for lower in range(route, active[-1]):
            _vias(cell, f"V{lower}", access_x, access_y, g)
    return cell


def caparray_cells(spec: dict) -> tuple[dict[int, Cell], Cell, list[tuple[int, int]]]:
    """A CDAC's units, its top-level wiring and the units' placement.

    ``spec``: ``family``, ``route``, ``shield``, ``active``, ``top`` (the top cell's name),
    ``order`` (the placed chunk weights, left to right, 0 an edge dummy), ``groups`` (per stage:
    its main and difference bus names, first position and chunk count), ``topplate`` and
    ``shieldplate`` (the plate names). Returns the units by weight, the top cell's own wiring, and
    the placements (weight, x).
    """

    route, shield, active = spec["route"], spec["shield"], tuple(spec["active"])
    g = difference_geometry(spec["family"], route, shield, active)
    coarse = spec["family"]["coarse_weight"]
    weights = sorted(set(spec["order"]) | set(range(1, coarse + 1)))
    tied = spec["family"].get("tied_dummies", False)
    # unary units: a chunk of the coarse weight, one main finger and no difference finger
    unary = spec["family"].get("unary_length")
    units = {
        weight: difference_unit(g, route, shield, active, weight, tied, unary if weight == coarse else None)
        for weight in weights
    }
    pitch, ring = g["unit_pitch"], g["ring_width"]
    placements = [(weight, position * pitch) for position, weight in enumerate(spec["order"])]
    top = Cell(spec["top"], 0)
    route_metal, pin = f"M{route}", f"M{route}.PIN"
    x_local, bottom_y, top_y = _access_centers(g)
    extension = (g["landing_long"] - g["via_landing"]) / 2
    pin_half = max(g["grid"], g["finger_width"]) / 2
    for main, diff, first, size in spec["groups"]:
        # the difference bus spans the units with a difference finger (none of a unary stage)
        with_diff = [
            position for position in range(first, first + size) if not (unary and spec["order"][position] == coarse)
        ]
        spans = [(main, bottom_y, bottom_y + extension, first, first + size - 1)]
        if with_diff:
            spans.append((diff, top_y, top_y - extension, with_diff[0], with_diff[-1]))
        for label, y, landing_y, left, right in spans:
            x0 = left * pitch + x_local - g["landing_short"] / 2
            x1 = right * pitch + x_local + g["landing_short"] / 2
            _box(top, route_metal, x0, landing_y - g["landing_long"] / 2, x1, landing_y + g["landing_long"] / 2)
            cx = left * pitch + x_local
            _box(top, pin, cx - pin_half, y - pin_half, cx + pin_half, y + pin_half, label, "pin")

    # the top plate: a bar over the units' top ring walls, down a stack beside the array to the route metal
    array_right = (len(spec["order"]) - 1) * pitch + g["outer_width"]
    output_right = array_right + g["side_extension"]
    pad = g["via_landing"]
    stack_left = array_right + g["shield_cutout_width"]
    stack_x = stack_left + pad / 2
    y = top_y - (g["landing_long"] + g["via_opposite_enclosure"])
    bar_bottom = g["outer_height"] - ring
    for metal in range(route, active[-1] + 1):
        if metal in active:
            _box(top, f"M{metal}", 0, bar_bottom, stack_left, bar_bottom + pad)
            _box(top, f"M{metal}", stack_left, y - pad / 2, stack_left + pad, bar_bottom + pad)
        _box(top, f"M{metal}", stack_left, y - pad / 2, stack_left + pad, y + pad / 2)
    for lower in range(route, active[-1]):
        _vias(top, f"V{lower}", stack_x, y, g, columns=2)
    _box(top, pin, stack_x - ring / 2, y - ring / 2, stack_x + ring / 2, y + ring / 2, spec["topplate"], "pin")

    # the shield: taps on its bridges at the array's right wall, out on route metal, past the top
    # plate's stack: a tap that would meet the stack's pad (a short unit's top bridge) is left out
    tap_x = array_right - ring / 2
    clearance = pad / 2 + ring / 2 + g["shield_spacing"]
    ys = [bridge + ring / 2 for bridge in g["shield_bridge_ys"] if abs(bridge + ring / 2 - y) >= clearance]
    if not ys:
        raise ValueError("unit family is too short for a shield tap beside the top plate's stack")
    for index, y in enumerate(ys):
        for metal in range(route, shield):
            _landing(top, f"M{metal}", tap_x, y, g, horizontal=True)
        for lower in range(route, shield):
            _vias(top, f"V{lower}", tap_x, y, g, rows=1)
        start_x = array_right if route == shield else tap_x
        _box(top, route_metal, start_x, y - ring / 2, output_right, y + ring / 2)
        if index == len(ys) // 2:
            _box(top, pin, output_right - ring, y - ring / 2, output_right, y + ring / 2, spec["shieldplate"], "pin")
    top.add("BND", 0, 0, output_right, g["outer_height"] - ring + g["via_landing"])
    top.width = output_right
    return units, top, placements


def caparray_gds(spec: dict, path: str) -> str:
    """Write a CDAC (``caparray_cells``) to a GDS file: the units as cells, placed in the top."""

    from klayout import db as kdb

    layout = kdb.Layout()
    layout.dbu = tech.DBU
    units, wiring, placements = caparray_cells(spec)
    top = to_klayout(wiring, layout, kdb)
    cells = {weight: to_klayout(unit, layout, kdb) for weight, unit in units.items()}
    for weight, x in placements:
        top.insert(kdb.CellInstArray(cells[weight].cell_index(), kdb.Trans(x, 0)))
    layout.write(path)
    return path


def to_klayout(cell: Cell, layout, kdb):
    """Draw a cell into a klayout Layout on the PDK's layers (``tech.LAYERS``, read when called),
    each pin labelled with its net at its centre; layers the PDK does not draw are skipped."""

    kc = layout.create_cell(cell.name)
    for r in cell.rects:
        if not tech.LAYERS.get(r.layer):
            continue
        shapes = kc.shapes(layout.layer(*tech.LAYERS[r.layer]))
        shapes.insert(kdb.Box(r.x0, r.y0, r.x1, r.y1))
        if r.kind == "pin":
            shapes.insert(kdb.Text(r.net, kdb.Trans((r.x0 + r.x1) // 2, (r.y0 + r.y1) // 2)))
    return kc
