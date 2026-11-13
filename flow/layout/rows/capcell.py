"""Fringe MOM capacitors' geometry from the PDK's ``tech`` values (``RULES``, ``LAYERS``,
``MFG_GRID``, ``MOM_LAYERS``), read when a function is called, in integer nanometres; a PDK names
no capacitor device. ALIGN's generators (``flow/layout/primitives/mom.py``) draw them:

- test structures (``mom_geometry``): the dimensions of the three FMOM styles on the top 1-3
  ``MOM_LAYERS`` (``MomUnit``). Their extraction (``flow.layout.devices.momcap``) gives the PDK's capacitance model;
- an array unit's access and channels on the shield's metal (``mom_access``, ``mom_channel``).
"""

from __future__ import annotations

import tech


def _snap(value: int, grid: int) -> int:
    return -(-value // grid) * grid


# ---------------------------------------------------------------------------------------------
# test structures


def mom_marks(layers: int) -> list[str]:
    """The PDK's MOM recognition layers a unit on its top ``layers`` metals draws: where its LVS
    reads such a unit as a device (``tech.MOM_RECOGNIZED_LAYERS``), none elsewhere (plain metal)."""
    if layers not in getattr(tech, "MOM_RECOGNIZED_LAYERS", ()):
        return []
    return [name for name in ("MOM_RECOG", "MOM_RECOG_INNER", "MOM_RECOG_SHIELD") if tech.LAYERS.get(name)]


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

    def spacing(width: int) -> int:
        """The spacing fingers ``width`` wide need alongside a long run."""
        minimum = max(rule["space"] for rule in rules)
        for rule in rules:
            # (space, above width, above parallel run length): a long finger meets every run length
            for conditional, above_width, _run in rule.get("parallel_space", ()):
                if width > above_width:
                    minimum = max(minimum, conditional)
        return minimum

    # an array's ring unit spans two finger pitches from wall centre to wall centre, and ALIGN
    # places it on whole M3 tracks (its cells' widths): the fingers widened, their spacing kept,
    # until two pitches are, where the narrowest leave them off the tracks
    m3 = getattr(tech, "M3_PITCH", tech.XPITCH)
    widest = width + m3
    while 2 * (width + _snap(max(spacing(width), space), grid)) % m3:
        width += 2 * grid
        if width > widest:
            raise ValueError(f"no finger width puts two MOM pitches on the {m3} nm M3 tracks")
    minimum = spacing(width)
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
        # a finger holds its via column at the end and meets its metals' minimum area
        "min_length": _snap(
            max(width, via_cut + 2 * via_end, -(-max(rule.get("area", 0) for rule in rules) // width)), grid
        ),
    }


def mom_access(layers: int, space: int = 0) -> dict:
    """An array unit's access to its inner plates (nm), on the shield's metal inside the ring: a
    strip under each inner finger as wide as it, the cut between them, the strip's spacing to the
    shield ring alongside and at its end (both the finger's own, ``mom_geometry``, where the access
    metal allows them), and the strip's least length (its cut's end enclosures, its metal's area)."""

    g = mom_geometry(layers, space)
    metal, width = g["shield"], g["width"]
    rule, via = tech.RULES[f"M{metal}"], tech.RULES.get(f"V{metal}", {})
    if "enclosure" not in via:
        raise ValueError(f"the PDK has no V{metal} enclosure rule (layout/tech.py RULES)")
    cut, (end, side) = via["cut"], via["enclosure"][:2]
    if width < max(rule["width"], cut + 2 * side):
        raise ValueError(f"a {width} nm finger is too narrow for its M{metal} access and its V{metal} cut")
    beside = max([rule["space"], *(gap for gap, above, _run in rule.get("parallel_space", ()) if width > above)])
    at_end = max([rule["space"], *(gap for gap, below, _ext in rule.get("end_of_line", ()) if width < below)])
    if g["space"] < beside or g["end_gap"] < at_end:
        raise ValueError(f"the ring's spacing is below M{metal}'s: no access strip fits inside it")
    return {
        "metal": metal,
        "via_cut": cut,
        "via_end": end,
        "min_length": _snap(max(cut + 2 * end, -(-rule.get("area", 0) // width)), g["grid"]),
    }


def mom_channel(layers: int, space: int = 0) -> dict:
    """An array unit's channels (nm) on the shield's metal (``MomUnit._channels``): its bar's height,
    so that the shortest bar (a lone piece at the array's edge: from a spacing past the edge's wall
    to half a spacing short of its other wall's centre) meets the metal's area; the spacing beside a
    bar that tall (``wide``) and at its ends (``space``)."""

    g, a = mom_geometry(layers, space), mom_access(layers, space)
    rule, w = tech.RULES[f"M{a['metal']}"], g["width"]
    outer = 3 * w + 2 * g["space"]
    shortest = (outer - w // 2 - rule["space"] // 2) - (w + rule["space"])
    bar = _snap(max(a["via_cut"] + 2 * a["via_end"], -(-rule.get("area", 0) // shortest)), 2 * g["grid"])
    if any(bar < below for _gap, below, _ext in rule.get("end_of_line", ())):
        raise ValueError(f"a {bar} nm bar meets M{a['metal']}'s line-end rule: no channel fits a unit")
    wide = max([rule["space"], *(gap for gap, above, _run in rule.get("parallel_space", ()) if bar > above)])
    return {**a, "space": rule["space"], "wide": wide, "bar": bar, "area": rule.get("area", 0)}
