# ruff: noqa  -- an ALIGN PDK generator (ALIGN style), run in ALIGN's own Python
"""The poly resistor with ALIGN's layout API: ``ResUnit`` draws the stems resistor row cell
(``flow/layout/stems/rescell.py``: its body, heads, contacts, implant, markers and pins, from the
PDK's ``tech.RES``) on the row-cell canvas (``mos.RowCanvas``: metals as wires, contacts and vias
as vias, the other layers as regions, the markers on their own layers, ``make_pdk.py``).

    ResUnit().unit(400, 4000)   # 400 nm wide, 4 um long

ALIGN also takes a ``ResGenerator`` from every PDK package, for a resistor its placer sizes from a
finFET array; no flow places a resistor through ALIGN, so it refuses.
"""

from pathlib import Path

from align.cell_fabric import transformation
from align.cell_fabric.pdk import Pdk

from .mos import RowCanvas, rowcell
import rescell


class ResUnit(RowCanvas):
    """One resistor row cell (``rescell.res``) on the row-cell canvas."""

    def __init__(self, pdk=None):
        super().__init__(pdk or Pdk().load(Path(__file__).resolve().parent / "layers.json"))

    def unit(self, w, l):
        """A body ``w`` wide and ``l`` long (nm, lengthened to its markers' area)."""
        cell = rescell.res(w, l)
        self.draw(cell.rects)
        rows = max(r.y1 for r in cell.rects if r.layer == "BND") // rowcell.H
        self.bbox = transformation.Rect(0, 0, cell.width, rows * rowcell.H)
        return self

    def gen_data(self, **kwargs):
        data = super().gen_data(**kwargs)
        # ALIGN's writer draws a pin on its pin purpose alone: the pin's metal is drawn as well, as
        # a placed row cell's is (mom.py's units alike)
        data["terminals"] += [
            {**term, "netType": "drawing"}
            for term in data["terminals"]
            if term.get("netType") == "pin" and term["layer"] not in self.rd.skip_layers
        ]
        return data


class ResGenerator:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("no flow places a resistor through ALIGN's placer: draw one with ResUnit")
