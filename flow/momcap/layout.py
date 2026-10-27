"""Fringe MOM capacitor test structures, drawn by ALIGN from a PDK's rules.

``MomUnit`` names a unit family (PDK, style, layer count); ``MomGeometry`` is its process
dimensions, which ``flow/layout/stems/capcell.py`` derives from ``pdk.<tech>.layout.tech``
(``RULES``, ``MFG_GRID``, ``MOM_LAYERS``): the minimum finger width, the spacing it needs, the
line-end gap, and the via between stacked plates. ``mom_unit_layout`` draws one test structure at a
plate length and spacing with the PDK's ALIGN generator (``MomUnit`` in
``flow/layout/align/pdk/mom.py``, on cell_fabric grids): the same plates on the top ``layers`` of
``MOM_LAYERS``, the plates of one terminal joined through a column of single vias at their
terminal end, over a shield plate on the metal below, every terminal a labelled pin. The labels
are what a layout-only extraction (``flow.layout.signoff.run_layout_pex``) names its nets by.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from klayout import db

from flow.layout.align.run import Drawing, draw, drawn_only
from flow.layout.pdkproc import in_pdk, pdk_value
from flow.momcap.subckt import MomStyle


@dataclass(frozen=True)
class MomUnit:
    """A unit family: the PDK, the style, and how many of the PDK's MOM metals it stacks."""

    technology: str
    style: MomStyle
    layers: int


@dataclass(frozen=True)
class MomTestParams:
    """One test structure: a unit, its plate lengths and its plate spacing (nm).

    ``length_nm`` is the inner finger's (``RING``), the main finger's (``DIFFERENCE``) or the
    strips' (``STRIP``); ``diff_length_nm`` the difference finger's (``DIFFERENCE`` only);
    ``space_nm`` the plates' spacing, 0 for the PDK's minimum.
    """

    unit: MomUnit
    length_nm: int
    diff_length_nm: int = 0
    space_nm: int = 0


@dataclass(frozen=True)
class MomGeometry:
    """A unit family's process dimensions (nm); ``space`` the drawn spacing, ``min_space`` the PDK's."""

    grid: int
    metals: tuple[int, ...]
    shield: int
    width: int
    min_space: int
    space: int
    end_gap: int
    via_cut: int
    via_end: int
    min_length: int


# the terminals each style labels (``SHIELD`` too), in the order its plates are listed
TERMINALS = {
    MomStyle.DIFFERENCE: ("TOP", "MAIN", "DIFF"),
    MomStyle.RING: ("TOP", "INNER"),
    MomStyle.STRIP: ("A", "B"),
}


def mom_geometry(unit: MomUnit, space_nm: int = 0) -> MomGeometry:
    """A unit family's dimensions, from its PDK's rules (``capcell.mom_geometry``)."""

    return MomGeometry(**in_pdk(unit.technology, "capcell", "mom_geometry", unit.layers, space_nm))


def mom_unit_layout(params: MomTestParams, top_cell: str) -> db.Layout:
    """Draw one test structure with the PDK's ALIGN generator (``MomUnit``): its plates on every
    stacked metal, joined by vias, over its shield, labelled; ALIGN's abstract layers and pin
    purpose left out, as its layouts' post step leaves them out (``flow/layout/align/post.py``)."""

    unit = params.unit
    pdk = unit.technology
    hold = mom_geometry(unit, params.space_nm).min_length
    if params.length_nm < hold or (unit.style == MomStyle.DIFFERENCE and params.diff_length_nm < hold):
        raise ValueError(f"plates shorter than {hold} nm cannot hold their vias")
    arguments = {
        "style": unit.style.name.lower(),
        "layers": unit.layers,
        "length": params.length_nm,
        "diff_length": params.diff_length_nm,
        "space": params.space_nm,
    }
    with tempfile.TemporaryDirectory() as scratch:
        pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, Path(scratch) / "pdk")
        (gds,) = draw(pdk_dir, [Drawing("MomUnit", "unit", arguments, Path(scratch) / f"{top_cell}.gds", top_cell)])
        layout = db.Layout()
        layout.read(str(gds))
    drawn_only(layout, set(pdk_value(pdk, "tech", "LAYERS").values()))
    return layout
