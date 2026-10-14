"""Routes for gen.py's placement: every net's M2 pins joined on M2/M3 (flow/layout/stems/rowroute.py).

The cells' pins are M2 bars; their final positions follow from the placement (gen.py's
``_place.json``: cicpy stacks a column's cells in order and mirrors every other column) and
the cells themselves. Supplies: an M3 trunk over each edge cell's supply pads (VSS one EDGE_STEP
in from either block end, VDD two), a VIA2 on every rail line of the net. Ports leave on M3
at the top or bottom edge as the floorplan's ``escape`` says. The result goes into the object
file as ``addRectangles`` / ``addPortRectangles``, turned back into the transposed frame cicpy
draws in.

Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/cic/build.py calls it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import netcells
import rowcell
import rowroute
from tech import BAR_END, M3W, V2

H = rowcell.H
A = 10


def route(pdk: str, out: Path, floorplan: Path, netlist: Path | None = None) -> None:
    """Add the routes to gen.py's object file in ``out``; ``netlist`` as gen.py's."""

    name = out.name
    obj_path = out / f"{name}.json"
    obj = json.loads(obj_path.read_text())
    inner = name.upper() + "_T"
    place = json.loads((out / f"{name}_place.json").read_text())
    columns, W = place["columns"], place["length"]
    nrows = len(columns)
    Ht = nrows * H
    fp = json.loads(floorplan.read_text())
    insts = {i.name: i for i in netcells.parse(netcells.floorplan_netlist(floorplan, pdk, netlist)[1])[2]}
    up = {p: True for p in fp["escape"]["up"]} | {p: False for p in fp["escape"]["down"]}

    def back(x0, y0, x1, y1):  # final -> transposed
        return (y0, W - x1, y1, W - x0)

    # ---- the cells' M2 (and their M3 jumpers, kept off), in the final frame: row c is column c,
    # odd columns mirrored in y
    blocked, pins, cell_m3 = [], defaultdict(list), []
    for c, col in enumerate(columns):
        for s in col:
            if s["dev"]:
                cell = netcells.cell_of(insts[s["dev"]])
            elif s["cell"].startswith("PH_stdedge_") or s["cell"].startswith("PH_edge_"):
                cell = netcells.edge(int(s["h"]), std=s["cell"].startswith("PH_stdedge_"))
            else:
                continue  # fillers: rails only
            x_lo = W - s["y0"] - s["h"]
            for r in cell.rects:
                if r.layer == "M3":
                    x0, x1 = (
                        (cell.width - r.x1, cell.width - r.x0)
                        if s["mirror"] or s["cell"].endswith("_MY")
                        else (r.x0, r.x1)
                    )
                    y0, y1 = (H - r.y1, H - r.y0) if c % 2 else (r.y0, r.y1)
                    cell_m3.append(((x_lo + (x0 + x1) // 2) // rowroute.P3, c * H + y0, c * H + y1))
                if r.layer != "M2":
                    continue
                x0, x1 = (
                    (cell.width - r.x1, cell.width - r.x0) if s["mirror"] or s["cell"].endswith("_MY") else (r.x0, r.x1)
                )
                y0, y1 = (H - r.y1, H - r.y0) if c % 2 else (r.y0, r.y1)
                box = (x_lo + x0, c * H + y0, x_lo + x1, c * H + y1)
                net = (r.net or "").split("__")[0]
                blocked.append((net, *box))
                if r.kind == "pin" and r.net and "__" not in r.net and net not in ("vdd", "vss"):
                    pins[net].append((box[0], box[2], (box[1] + box[3]) // 2))

    # ---- supplies: M3 trunks over the edge cells' pads, a VIA2 on every rail line of the net
    extra, keep3, port_rects = [], list(cell_m3), []
    hw = M3W // 2
    step = netcells.EDGE_STEP
    for net, xs, parity in (("vss", (step, W - step), 0), ("vdd", (2 * step, W - 2 * step), 1)):
        for x in xs:
            keep3.append((x // rowroute.P3, 0, Ht))
            extra.append(("M3", (x - hw, -BAR_END, x + hw, Ht + BAR_END)))  # encloses the outer rails' VIA2
            for k in range(parity, nrows + 1, 2):
                y = k * H
                extra.append(("VIA2", (x - V2 // 2, y - V2 // 2, x + V2 // 2, y + V2 // 2)))
        port_rects.append((net, "M3", (xs[0] - hw, 0, xs[0] + hw, Ht)))

    def attempt(order):
        router = rowroute.Router(blocked, W, Ht, m3_keep=keep3)
        for net in order:
            if len(pins[net]) > 1 or net in up:
                router.route(net, pins[net])
        ports = []
        for net, is_up in up.items():
            if net in pins:
                m, lo, hi = router.escape(net, is_up)
                ports.append((net, "M3", (m * rowroute.P3 - hw, lo, m * rowroute.P3 + hw, hi)))
        return router, ports

    # most pins first; the net that fails goes first next time (rip up and retry)
    order = sorted(pins, key=lambda n: (-len(pins[n]), n))
    for _ in range(30):
        try:
            router, ports = attempt(order)
            break
        except AssertionError as err:
            failed = str(err).split(":")[0]
            print(f"retry: {err}"[:160])
            order = [failed] + [n for n in order if n != failed]
    else:
        raise RuntimeError(f"{name}: no net order routes")

    rects = [(layer, box) for layer, *box in router.rects] + extra
    as_cic = lambda b: [b[0] * A, b[1] * A, (b[2] - b[0]) * A, (b[3] - b[1]) * A]
    add = [[layer, *as_cic(back(*b))] for layer, b in rects]
    add_ports = [[layer, *as_cic(back(*b)), "", net] for net, layer, b in port_rects + ports]
    cell = next(c for c in obj["cells"] if c["name"] == inner)
    cell.setdefault("afterRoute", {})["addRectangles"] = add
    cell["afterRoute"]["addPortRectangles"] = add_ports
    obj_path.write_text(json.dumps(obj, indent=1) + "\n")
    print(f"{name}: routed {sum(1 for n in pins if len(pins[n]) > 1)} nets, {len(add)} shapes, {len(add_ports)} ports")
