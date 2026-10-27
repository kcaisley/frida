"""Fringe MOM capacitors' geometry from the PDK's ``tech`` values (``RULES``, ``LAYERS``,
``MFG_GRID``, ``MOM_LAYERS``), read when a function is called, in integer nanometres; a PDK names
no capacitor device. ALIGN's generators (``flow/layout/align/pdk/mom.py``) draw them:

- test structures (``mom_geometry``): the dimensions of the three FMOM styles on the top 1-3
  ``MOM_LAYERS`` (``MomUnit``). Their extraction (``flow.momcap``) gives the PDK's capacitance model;
- the CDAC (``difference_geometry``, ``caparray_plan``): difference units of a weight family over a
  shield mesh, with two-cut access landings down to the route metal, side by side sharing their
  ring walls (``DifferenceUnit``), and the array's buses, top-plate stack and shield taps
  (``ArrayWiring``).
"""

from __future__ import annotations

import tech


def _snap(value: int, grid: int) -> int:
    return -(-value // grid) * grid


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
    ``caparray_plan`` ``tied_dummies`` (the edge dummies' fingers on the top plate) and
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


def access_centers(g: dict) -> tuple[float, float, float]:
    """Centres of the two-cut via arrays, toward the outside of each landing."""
    x = g["ring_width"] + g["gap"] + g["finger_width"] / 2
    bottom = g["ring_width"] + g["end_gap"] + g["via_landing"] / 2
    return x, bottom, g["outer_height"] - bottom


def caparray_plan(spec: dict) -> dict:
    """A CDAC's drawing, for ALIGN's generators: its geometry, its units by name (each one's
    weight, tied, unary length; every weight to the coarse one) and their placements (name, x)."""

    route, shield, active = spec["route"], spec["shield"], tuple(spec["active"])
    g = difference_geometry(spec["family"], route, shield, active)
    coarse = spec["family"]["coarse_weight"]
    tied = spec["family"].get("tied_dummies", False)
    unary = spec["family"].get("unary_length")
    suffix = "_".join(f"m{layer}" for layer in active)
    units = {}
    for weight in sorted(set(spec["order"]) | set(range(1, coarse + 1))):
        length = unary if weight == coarse else None
        dummy = "frida_mom_dummy_tied" if tied else "frida_mom_dummy"
        name = f"frida_mom_w{weight}{'u' if length else ''}_{suffix}" if weight else f"{dummy}_{suffix}"
        units[weight] = {"name": name, "weight": weight, "tied": tied, "unary_length": length}
    placements = [(units[weight]["name"], position * g["unit_pitch"]) for position, weight in enumerate(spec["order"])]
    # the shield's strip under the fingers, where its metal's holes may be as narrow as a gap; the
    # PDK's MOM recognition layers, where its LVS recognizes a unit as a device
    strip = g["gap"] >= _rules(f"M{shield}").get("hole_width", 0)
    marks = [name for name in ("MOM_RECOG", "MOM_RECOG_INNER", "MOM_RECOG_SHIELD") if tech.LAYERS.get(name)]
    return {"geometry": g, "strip": strip, "marks": marks, "units": list(units.values()), "placements": placements}
