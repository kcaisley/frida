# ruff: noqa  -- an ALIGN PDK generator (ALIGN style), run in ALIGN's own Python
"""FMOM capacitor units for ALIGN: the test structures (``ring``, ``strip``, ``difference``) as a
generic primitive (a ``Generator`` constraint naming ``MomUnit``), drawn on cell_fabric grids.

The geometry's numbers are the PDK's (``capcell.mom_geometry``: the fingers' width, the spacing,
the line-end gap, the via cut, the metals); the drawing is ALIGN's: the fingers are vertical wires
on a centre-line grid of pitch width + spacing, the ring's bars horizontal wires on a grid of its
two bar centres, every end and every via on a nanometre stop grid, the shield a region on the metal
below. A terminal's pin, a cut-sized square at its via column on the top metal (the shield's in its
margin below the unit's corner), becomes, as ALIGN merges it, its finger: the pin and its label are
the terminal's metal and its centre. Every mask layer agrees shape for shape with the stems
drawing it replaced (``flow.layout.gdsdiff``, all six PDKs); the pin purpose (the ``.PIN``
squares, the labels' place on the terminal) is ALIGN's.

    unit = MomUnit()
    unit.unit("difference", 3, length=8000, diff_length=25000)
    unit.writeGDS(open("momunit.gds", "wb"), macro_name="momunit")
"""

import json
import sys
from pathlib import Path

from align.cell_fabric.generators import Region, Via, Wire
from align.cell_fabric.grid import CenterLineGrid, SingleGrid, UncoloredCenterLineGrid
from align.cell_fabric.pdk import Pdk
from align.primitive.default.canvas import DefaultCanvas

_STEMS = json.loads((Path(__file__).resolve().parent / "stems.json").read_text())  # written by make_pdk.py
sys.path[:0] = [_STEMS["layout"], _STEMS["stems"]]  # the PDK's tech and paths, then the engine
import capcell


class MomUnit(DefaultCanvas):
    """One FMOM test structure on the PDK's top 1-3 MOM metals over its shield."""

    def __init__(self, pdk=None):
        super().__init__(pdk or Pdk().load(Path(__file__).resolve().parent / "layers.json"))
        self.nm = SingleGrid(pitch=1)  # every end, via centre and region corner, in nanometres

    def generate(self, ports, netlist_parameters, netlistdir=None):
        """ALIGN's generic-primitive entry: the unit its netlist parameters name."""
        p = netlist_parameters
        self.unit(p["style"], int(p["layers"]), int(p["length"]), int(p.get("diff_length", 0)), int(p.get("space", 0)))

    def unit(self, style, layers, length, diff_length=0, space=0):
        """``length`` the inner finger's (``ring``), the main finger's (``difference``) or the strips'
        (``strip``), ``diff_length`` the difference finger's, ``space`` the plates' spacing (0: the
        minimum), all in nm."""

        g = capcell.mom_geometry(layers, space)
        w, s, e, hold = g["width"], g["space"], g["end_gap"], g["min_length"]
        if length < hold or (style == "difference" and diff_length < hold):
            raise ValueError(f"plates shorter than {hold} nm cannot hold their vias")
        # the vertical fingers' centre lines: column 0 the left plate, 1 the next, 2 the ring's right bar
        fingers = UncoloredCenterLineGrid(pitch=w + s, width=w, offset=w // 2)
        # (terminal, column, bottom, top, via centre's height or None)
        columns = []
        bars = []  # (terminal, row of the bar grid, x0, x1)
        if style == "strip":
            columns = [("A", 0, 0, length, length - hold // 2), ("B", 1, 0, length, hold // 2)]
            height, outer = length, 2 * w + s
        elif style in ("ring", "difference"):
            height = length + diff_length + 3 * e + 2 * w if style == "difference" else length + 2 * e + 2 * w
            outer = 3 * w + 2 * s
            inner = "MAIN" if style == "difference" else "INNER"
            columns = [
                ("TOP", 0, 0, height, height // 2),
                ("TOP", 2, 0, height, None),
                (inner, 1, w + e, w + e + length, w + e + hold // 2),
            ]
            if style == "difference":
                top = height - w - e
                columns.append(("DIFF", 1, top - diff_length, top, top - hold // 2))
            bars = [("TOP", 0, 0, outer), ("TOP", 1, 0, outer)]
        else:
            raise ValueError(f"unknown FMOM style {style!r}")
        # the ring's bars: centre lines at the bottom bar's and the top bar's
        bar_grid = CenterLineGrid()
        bar_grid.addCenterLine(w // 2, w)
        bar_grid.addCenterLine(height - w // 2, w)
        for metal in g["metals"]:
            layer = f"M{metal}"
            vertical = self.addGen(Wire(f"mom_v{metal}", layer, "v", clg=fingers, spg=self.nm))
            for terminal, column, y0, y1, _via in columns:
                self.addWire(vertical, terminal, column, y0, y1)
            if bars:
                horizontal = self.addGen(Wire(f"mom_h{metal}", layer, "h", clg=bar_grid, spg=self.nm))
                for terminal, row, x0, x1 in bars:
                    self.addWire(horizontal, terminal, row, x0, x1)
        # each terminal's plates joined by a via per metal at its terminal end
        for metal in g["metals"][:-1]:
            via = self.addGen(
                Via(
                    f"mom_via{metal}",
                    f"V{metal}",
                    h_clg=self.nm,
                    v_clg=fingers,
                    WidthX=g["via_cut"],
                    WidthY=g["via_cut"],
                )
            )
            for terminal, column, _y0, _y1, centre in columns:
                if centre is not None:
                    self.addVia(via, terminal, column, centre)
        # every terminal a pin at its via column on the top metal
        pin = Via(
            "mom_pin", f"M{g['metals'][-1]}", h_clg=self.nm, v_clg=fingers, WidthX=g["via_cut"], WidthY=g["via_cut"]
        )
        for terminal, column, _y0, _y1, centre in columns:
            if centre is not None:
                self.transform_and_add(pin.segment(terminal, column, centre, netType="pin"))
        # the shield on the metal below, a spacing past the unit on every side, its pin in the margin
        shield = self.addGen(Region("mom_shield", f"M{g['shield']}", h_grid=self.nm, v_grid=self.nm))
        self.addRegion(shield, "SHIELD", -s, -s, outer + s, height + s)
        corner, half = -(s // 2), max(g["grid"], s // 4)
        self.transform_and_add(
            shield.segment("SHIELD", corner - half, corner - half, corner + half, corner + half, netType="pin")
        )
        self.computeBbox()
        return self

    def gen_data(self, *, run_drc=False, **kwargs):
        # off-grid for ALIGN's own DRC, as the row cells (mos.py): the PDK's checkers sign it off
        data = super().gen_data(run_drc=False, **kwargs)
        if self.drc is None:
            self.drc = type("NoDRC", (), {"errors": [], "num_errors": property(lambda s: len(s.errors))})()
        # a pin is its terminal's metal (ALIGN merges the pin square into the finger it sits on), and
        # ALIGN's writer draws a pin on its pin purpose alone: the metal is drawn as well
        data["terminals"] += [
            {**term, "netType": "drawing"} for term in data["terminals"] if term.get("netType") == "pin"
        ]
        return data
