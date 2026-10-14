# ruff: noqa  -- adapted from ALIGN's Bulk65nm mock PDK (star imports, ALIGN style)
"""Row-cell MOS primitives for ALIGN: one transistor or a matched pair per cell, one or more standard-cell rows tall.

The geometry is the stems engine's (flow/layout/stems/rowcell.py, shared with the laygo and
cIcCreator flows; pairs such as ALIGN's DP, CMC and CCP are ``rowcell.mos_row``), drawn with
the PDK's ``tech`` (this generated PDK directory's ``stems.json`` says where it is): VSS rail
and P+ tap at the bottom, VDD rail and N+ tap at the top, so NMOS, PMOS and the library's
standard cells abut in any order and supplies connect by abutment. Each primitive asks the
placer for standard-cell rows (``PlaceOnGrid``: y on a two-row pitch, flipped on the odd
rows), so VSS lands on even rail lines and VDD on odd ones.
The supply pins are the M2 straps over the rails; the design leaves vdd/vss unrouted
(``DoNotRoute``), and ``align/post.py`` closes the rails across placement gaps.

ALIGN's connectivity check bins every metal by its centre line (M1 vertical, M2
horizontal) and needs each via on such a line, hence the M1 stubs under the rail vias.
Its grid DRC does not apply to these off-grid cells (Calibre signs off), so it is off.
"""

import json
import os
import sys
from pathlib import Path

from align.cell_fabric import transformation
from align.cell_fabric.generators import Region, Via
from align.primitive.default.canvas import DefaultCanvas
from align.schema.constraint import OffsetsScalings, PlaceOnGrid

_STEMS = json.loads((Path(__file__).resolve().parent / "stems.json").read_text())  # written by make_pdk.py
sys.path[:0] = [_STEMS["layout"], _STEMS["stems"]]  # the PDK's tech and paths, then the engine
import rowcell
from tech import XPITCH

LAYERS = {
    "OD": "Active",
    "PO": "Poly",
    "CO": "V0",
    "M1": "M1",
    "V1": "V1",
    "M2": "M2",
    "V2": "V2",
    "M3": "M3",
    "NW": "Nwell",
    "PP": "Pselect",
    "NP": "Nselect",
    "VTN": "Lvt",
    "VTP": "Slvt",
    "BND": "Boundary",
    **_STEMS.get("extra", {}),  # the PDK's own markers on spare ALIGN layers (make_pdk.py)
}
X_GRID = 2 * XPITCH  # two M3 pitches: symmetric pairs need widths of equal parity on the placement grid


def row_constraints():
    return [
        PlaceOnGrid(
            direction="H", pitch=2 * rowcell.H, ored_terms=[OffsetsScalings(offsets=[0], scalings=[1, -1])]
        ).dict()
    ]


class RowCanvas(DefaultCanvas):
    """Canvas that takes plain rowcell rectangles."""

    def __init__(self, pdk):
        super().__init__(pdk)
        for layer in (
            "Active",
            "Poly",
            "Nselect",
            "Pselect",
            "Nwell",
            "Lvt",
            "Slvt",
            *_STEMS.get("extra", {}).values(),
        ):
            self.addGen(Region(layer.lower(), layer, h_grid=self.m2.clg, v_grid=self.m1.clg))
        self.addGen(
            Via(
                "v0",
                "V0",
                h_clg=self.m2.clg,
                v_clg=self.m1.clg,
                WidthX=self.pdk["V0"]["WidthX"],
                WidthY=self.pdk["V0"]["WidthY"],
            )
        )
        self.metadata = {"constraints": [] if os.environ.get("STEMS_NO_GRID") else row_constraints()}

    def gen_data(self, *, run_drc=True, **kwargs):
        # ALIGN's grid DRC does not apply to these off-grid cells (Calibre signs off); keep an
        # error list, ALIGN's checker appends router findings to it
        data = super().gen_data(run_drc=False, **kwargs)
        if self.drc is None:
            self.drc = type("NoDRC", (), {"errors": [], "num_errors": property(lambda s: len(s.errors))})()
        return data

    def computeBbox(self):
        if self.bbox is None:
            super().computeBbox()

    def draw(self, rects, net_map=lambda n: n):
        for r in rects:
            net = r.term if r.term else net_map(r.net)
            pin = r.kind == "pin" and net is not None and ":" not in net
            self.terminals.append(
                {
                    "netName": net,
                    "layer": LAYERS[r.layer],
                    "rect": [r.x0, r.y0, r.x1, r.y1],
                    "netType": "pin" if pin else "blockage" if r.kind == "blockage" else "drawing",
                }
            )


class MOSGenerator(RowCanvas):
    def __init__(self, pdk, height, fin, gate, gateDummy, shared_diff, stack, bodyswitch, **kwargs):
        self.primitive_parameters = kwargs.get("primitive_parameters") or {}
        self.primitive_constraints = kwargs.get("primitive_constraints", [])
        super().__init__(pdk)

    def addNMOSArray(self, x_cells, y_cells, pattern, vt_type, connections, **parameters):
        self._build("n", connections, y_cells)

    def addPMOSArray(self, x_cells, y_cells, pattern, vt_type, connections, **parameters):
        self._build("p", connections, y_cells)

    def _build(self, pol, connections, rows=1):
        devs = [k for k in self.primitive_parameters if k != "model"]  # ALIGN's order: M1, M2
        nets = {dev: {pin: n for n, conn in connections.items() for d, pin in conn if d == dev} for dev in devs}
        if any(nets[dev]["B"] in ("SN", "SP") for dev in devs):  # a logic gate (user_template.sp)
            return self._logic(devs, nets, connections)
        assert len(devs) in (1, 2), f"one device or a pair per row primitive, got {devs}"
        nm = lambda v: int(round(float(v) * 1e9 / 5)) * 5
        devices, bulk = [], set()
        for dev in devs:
            par = self.primitive_parameters[dev]
            net = {pin: n for n, conn in connections.items() for d, pin in conn if d == dev}
            inst = f"{dev}_X0_Y0"
            self.subinsts[inst].parameters.update(par)
            nf = int(par.get("NF", 1)) * int(par.get("M", 1))
            devices.append(rowcell.Dev(inst, nm(par["L"]), nm(par["W"]), nf, net["D"], net["G"], net["S"]))
            bulk.add(net["B"])
        assert len(bulk) == 1, f"{devs}: the bulk is the cell's rail, got {bulk}"
        b = bulk.pop()
        # folded over the rows ALIGN chose among gen_param.fold_rows' variants (one: mos_row)
        cell = rowcell.mos_rows(
            devs[0] if len(devs) == 1 else "_".join(devs),
            pol,
            devices,
            rows,
            grid=X_GRID,
            vss=b if pol == "n" else None,
            vdd=b if pol == "p" else None,
        )
        self.draw(cell.rects)
        self.bbox = transformation.Rect(0, 0, cell.width, rows * rowcell.H)

    def _logic(self, devs, nets, connections):
        """INV, NAND2, NOR2: NMOS (bulk SN) and PMOS (bulk SP) in one row, logiccell.py."""
        import logiccell  # a PDK with logic cells (its tech has their values)

        nm = lambda v: int(round(float(v) * 1e9 / 5)) * 5
        rows = []
        for dev in devs:
            par = self.primitive_parameters[dev]
            inst = f"{dev}_X0_Y0"
            self.subinsts[inst].parameters.update(par)
            n = nets[dev]
            rows.append(
                logiccell.LDev(
                    inst,
                    "n" if n["B"] == "SN" else "p",
                    nm(par["L"]),
                    nm(par["W"]),
                    int(par.get("NF", 1)) * int(par.get("M", 1)),
                    n["D"],
                    n["G"],
                    n["S"],
                )
            )
        cell = logiccell.logic("_".join(devs), rows, grid=X_GRID, vss="SN", vdd="SP", ports=set(connections))
        self.draw(cell.rects)
        self.bbox = transformation.Rect(0, 0, cell.width, rowcell.H)
