"""laygo technology for a design in standard-cell rows: one fixed template per netlist instance.

The row cells (flow/layout/stems) are complete transistors or the PDK's standard cells with
their pins on M2 and both supply rails, so laygo only places them in rows and routes M2/M3;
it does not generate transistors here. Each template is named after its instance and its
pins after the nets (``pins_of(net)`` in the design script finds them by name). Filler
templates (rails and taps only) close the rows to the block width. The YAML (uploaded to
the hosted laygo server) uses the server's layer names (server.py); post.py swaps in the PDK's
cells from the GDS written here.

Grids: placement one row tall (laygo flips odd rows, MX), x on the PDK's XPITCH; routing M2
on every PITCH track of a row pair (rail lines included), M3 on XPITCH.

Also writes the design script <design>.py from design_template.py (rows, pins, nets, escapes, tech values);
``first`` (nets) routes those nets first (laygo/build.py: the nets that failed), ``shuffle`` (a seed)
the others in a shuffled order. Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/laygo/build.py
calls it.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from pathlib import Path

import klayout.db as kdb
import netcells
import rowcell
import tech
import yaml
from tech import BAR_END, M2_MIN_LEN, M2_SPACE, M2W, M3W, PITCH, V1, V2, XPITCH

from flow.layout.laygo.server import SERVER_PDK, server_names

HERE = Path(__file__).resolve().parent
M3_PITCH = getattr(tech, "M3_PITCH", XPITCH)  # M3 routing tracks: the cell grid unless the PDK routes finer
SERVER = server_names()  # our metal names -> the server's layer names
FILL_MAX = 20000


class Via:
    """A via template: the cut and the two metals around it (lower vertical or horizontal)."""

    def __init__(
        self, layout, name: str, cut: str, lo: str, hi: str, lo_vertical: bool, size: int, widths: tuple[int, int]
    ):
        self.name = name
        cell = layout.create_cell(name)
        box = lambda layer, *xy: cell.shapes(layout.layer(*rowcell.GLAYERS[layer])).insert(kdb.Box(*xy))
        box(cut, -size // 2, -size // 2, size // 2, size // 2)
        for layer, vertical, w in ((lo, lo_vertical, widths[0]), (hi, not lo_vertical, widths[1])):
            box(layer, *((-w // 2, -BAR_END, w // 2, BAR_END) if vertical else (-BAR_END, -w // 2, BAR_END, w // 2)))


def routing(h_elems, h_layer, h_width, h_scope, v_pitch, v_layer, v_width, via_name, v_offset=0):
    ext = lambda n, v: [v] * n
    hl = [[SERVER[h_layer], "drawing"]] * len(h_elems)
    return {
        "type": "routing",
        "primary_grid": "horizontal",
        "horizontal": {
            "elements": h_elems,
            "scope": [0, h_scope],
            "layer": hl,
            "pin_layer": hl,
            "width": ext(len(h_elems), h_width),
            "extension": ext(len(h_elems), BAR_END),
            "extension0": ext(len(h_elems), M2_MIN_LEN // 2),  # zero-length M2 pins meet the M2 area
            "ycolor": ext(len(h_elems), "not MPT"),
        },
        "vertical": {
            "elements": [v_offset % v_pitch],
            "scope": [0, v_pitch],
            "layer": [[SERVER[v_layer], "drawing"]],
            "pin_layer": [[SERVER[v_layer], "drawing"]],
            "width": [v_width],
            "extension": [BAR_END],
            "extension0": [BAR_END],
            "xcolor": ["not MPT"],
        },
        "via": {"map": [[via_name] for _ in h_elems]},
    }


def pins(cell: rowcell.Cell) -> dict:
    out = {}
    for net, rects in cell.pins.items():
        r = rects[0]
        out[net] = {"layer": [SERVER[r.layer], "drawing"], "netname": net, "xy": [[r.x0, r.y0], [r.x1, r.y1]]}
        # the net's other M2 bars (joined to that pin inside the cell, a diode's gate and drain say):
        # keep-outs, so other nets' routes stay clear of them
        for i, r in enumerate((r for r in rects[1:] if r.layer == "M2"), 1):
            out[f"{net}__pin_{i}"] = {
                "layer": [SERVER[r.layer], "drawing"],
                "netname": f"{net}__pin_{i}",
                "xy": [[r.x0, r.y0], [r.x1, r.y1]],
            }
    for i, r in enumerate(r for r in cell.rects if r.kind == "stub" and r.layer == "M2"):  # keep-outs, blocked
        out[f"{r.net}{i}"] = {
            "layer": [SERVER[r.layer], "drawing"],
            "netname": r.net,
            "xy": [[r.x0, r.y0], [r.x1, r.y1]],
        }
    # the cell's other M2 (the edge cells' supply pads, far-rail landings, cross-couplings): keep-outs
    # under names of their own, so the routers' bars and branches keep the M2 space to them
    for i, r in enumerate(r for r in cell.rects if r.kind == "drawing" and r.layer == "M2" and r.net):
        out[f"{r.net}__m2_{i}"] = {
            "layer": [SERVER[r.layer], "drawing"],
            "netname": f"{r.net}__m2_{i}",
            "xy": [[r.x0, r.y0], [r.x1, r.y1]],
        }
    # the cell's own M3 (jumpers, far-rail ties): keep-outs the design script books on their M3 tracks,
    # under names of their own (route_net would take a pin of the net's name as one to route to)
    for i, r in enumerate(r for r in cell.rects if r.layer == "M3"):
        out[f"{r.net}__m3_{i}"] = {
            "layer": [SERVER[r.layer], "drawing"],
            "netname": f"{r.net}__m3_{i}",
            "xy": [[r.x0, r.y0], [r.x1, r.y1]],
        }
    return out


def build(
    pdk: str,
    floorplan: Path,
    out_dir: Path,
    netlist: Path | None = None,
    first: Sequence[str] = (),
    shuffle: int = 0,
) -> None:
    """Write the templates GDS, the laygo YAML and the design script into ``out_dir``.
    ``netlist``: the design's netlist (default: the floorplan's); ``first``: nets to route first;
    ``shuffle``: a seed for the order of the others (0: most pins first)."""

    out_dir.mkdir(parents=True, exist_ok=True)
    lib = f"{pdk}_microtemplates_dense"
    fp = json.loads(floorplan.read_text())
    name, src = netcells.floorplan_netlist(floorplan, pdk, netlist)
    _, _, insts = netcells.parse(src)
    layout = kdb.Layout()
    layout.dbu = 0.001
    std = kdb.Layout()
    std.read(str(netcells.STD_GDS))
    templates = {}
    for inst in insts:
        cell = netcells.cell_of(inst)
        netcells.draw(layout, kdb, cell, inst, std)
        templates[inst.name] = {
            "pins": pins(cell),
            "unit_size": [cell.width, rowcell.H],
            "xy": [[0, 0], [cell.width, rowcell.H]],
        }
    for w in range(XPITCH, FILL_MAX + 1, XPITCH):
        for cell in (netcells.filler(w), netcells.std_fill(w)):  # analog rows / standard-cell rows
            netcells.draw(layout, kdb, cell, std_lib=std)
            templates[cell.name] = {"pins": pins(cell), "unit_size": [w, rowcell.H], "xy": [[0, 0], [w, rowcell.H]]}
    for cell in (netcells.edge(), netcells.edge(std=True)):
        netcells.draw(layout, kdb, cell, std_lib=std)
        templates[cell.name] = {
            "pins": pins(cell),
            "unit_size": [cell.width, rowcell.H],
            "xy": [[0, 0], [cell.width, rowcell.H]],
        }
    vias = [
        Via(layout, "via_12_0", "V1", "M1", "M2", True, V1, (rowcell.M1W, M2W)),
        Via(layout, "via_23_0", "V2", "M2", "M3", False, V2, (M2W, M3W)),
    ]
    templates.update({v.name: {"pins": {}} for v in vias})
    layout.write(str(out_dir / f"{name}_templates.gds"))

    tracks = list(range(0, 2 * rowcell.H, getattr(tech, "PIN_PITCH", PITCH)))  # pins may sit between routing tracks
    grids = {
        "placement_basic": {
            "type": "placement",
            "pins": {},
            "horizontal": {"elements": [0], "scope": [0, rowcell.H]},
            "vertical": {"elements": [0], "scope": [0, XPITCH]},
        },
        "routing_23_cmos": routing(tracks, "M2", M2W, 2 * rowcell.H, M3_PITCH, "M3", M3W, "via_23_0"),
    }
    ref = yaml.safe_load((HERE / "server_reference.yaml").read_text())
    laygo_tech = {
        "export": ref["export"],
        "export_template": ref["export_template"],
        "grids": {lib: grids},
        "templates": {lib: templates},
    }
    (out_dir / f"{name}_laygo.yaml").write_text(
        f"# laygo technology for {name} in {pdk} standard-cell rows, generated by flow/layout/laygo/rowtemplates.py.\n"
        f"# {SERVER_PDK} layer names (the server's layermap); post.py restores {pdk}.\n"
        + yaml.safe_dump(laygo_tech, sort_keys=False)
    )
    # the design script: design_template.py with this design's rows, template pins, nets and port escapes
    rows = fp["rows"]
    tpins = {n: sorted(templates[n]["pins"]) for row in rows for n in row}
    signals = {n for i in insts for n in i.nets.values()} - {"vdd", "vss"}
    std_nets = {n for i in insts if i.kind != "mos" for n in i.nets.values()} & signals
    up, down = fp["escape"]["up"], fp["escape"]["down"]
    ports = [p for p in up + down if p in signals]
    npins = lambda n: -sum(n in i.nets.values() for i in insts)  # most pins first: they have the fewest options
    nets = (
        sorted(std_nets - set(ports), key=lambda n: (npins(n), n))
        + sorted(std_nets & set(ports))
        + sorted(signals - std_nets - set(up))
        + [p for p in up if p in signals and p not in std_nets]
    )
    early = [n for n in first if n in nets]  # nets that failed before: first
    rest = [n for n in nets if n not in early]
    nets = early + (random.Random(shuffle).sample(rest, len(rest)) if shuffle else rest)
    escapes = [(p, p in up) for p in ports]
    tech_values = {
        "H": rowcell.H,
        "PITCH": PITCH,
        "XPITCH": XPITCH,
        "END": BAR_END,
        "HW2": M2W // 2,
        "SP": M2_SPACE,
        "MIN": M2_MIN_LEN,
        # a bar's end to a pin bar on its track (pins booked END wider): the PDK's, else dense line ends
        "CLEAR": getattr(tech, "LAYGO_CLEAR", BAR_END + 2 * M2_SPACE),
        "LINE_END": getattr(tech, "LAYGO_LINE_END", True),  # the PDK has a dense line-end rule on M2
        "GAP3": getattr(tech, "LAYGO_GAP3", 2 * M2_SPACE),
        "EDGE_W": netcells.EDGE_W,
        "EDGE_STEP": netcells.EDGE_STEP,
        "M3_PITCH": M3_PITCH,  # M3 keep-out between booked segments
    }
    script = (
        (HERE / "design_template.py")
        .read_text()
        .replace("__CELLNAME__", name)
        .replace("__ROWS__", json.dumps(rows))
        .replace("__PINS__", json.dumps(tpins))
        .replace("__TECH__", repr(tech_values))
        .replace("__NETS__", repr(nets))
        .replace("__ESCAPES__", repr(tuple(escapes)))
    )
    (out_dir / f"{name}.py").write_text(script)
    print(f"{name}: {len(insts)} instance templates, {FILL_MAX // XPITCH} fillers, design script {name}.py")
