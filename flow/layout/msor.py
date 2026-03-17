"""OpenROAD analog place-and-route script.

Runs inside ``openroad -exit -python``.  Receives a path to a JSON
configuration file on sys.argv[1].

    openroad -exit -python flow/layout/msor.py config.json
"""

import json
import math
import sys
from pathlib import Path

import odb
import openroad
import pdn

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())

tech_lefs: list[str] = cfg["tech_lefs"]
macro_lefs: list[str] = cfg["macro_lefs"]
verilog: str = cfg["verilog"]
top_module: str = cfg["top_module"]

utilization: float = cfg["utilization"]
aspect_ratio: float = cfg["aspect_ratio"]
core_margin: float = cfg["core_margin"]
site_name: str = cfg["site_name"]
symmetry_axis: str = cfg.get("symmetry_axis", "vertical")

pin_hor_layer: str = cfg["pin_hor_layer"]
pin_ver_layer: str = cfg["pin_ver_layer"]
pins: list[dict] = cfg.get("pins", [])

output_def: str = cfg["output_def"]

# ── Load technology and design ──────────────────────────────────────

tech = openroad.Tech()
for lef in tech_lefs:
    tech.readLef(lef)
for lef in macro_lefs:
    tech.readLef(lef)

design = openroad.Design(tech)
design.readVerilog(verilog)
design.link(top_module)

db_tech = tech.getTech()
block = design.getBlock()

# ── Placement grid (rows from SITE) ────────────────────────────────
# The SITE defines a 2D placement grid:
#   - Vertically: rows are tiled at site_height intervals within the core area.
#   - Horizontally: cells snap to site_width intervals within each row.
# Our "unit" site is 5nm x 5nm (= manufacturing grid), so placement is
# essentially unconstrained. Digital sites are larger (e.g. 0.19 x 2.72 um).

floorplan = design.getFloorplan()

site = floorplan.findSite(site_name)
margin = design.micronToDBU(core_margin)
site_h = site.getHeight()
site_w = site.getWidth()

# Compute die size from utilization, then snap dimensions:
#   - Height: round up to nearest row (site_h multiple)
#   - Width: round up to nearest M4 track pitch (so power straps land on edges)
m4_pitch = db_tech.findLayer("Metal4").getPitchX()

cell_area = sum(
    inst.getMaster().getWidth() * inst.getMaster().getHeight()
    for inst in block.getInsts()
)
core_area = cell_area / (utilization / 100.0)
core_w = int(math.sqrt(core_area / aspect_ratio))
core_h = int(core_w * aspect_ratio)
core_h = math.ceil(core_h / site_h) * site_h
core_w = math.ceil(core_w / m4_pitch) * m4_pitch

die_rect = odb.Rect(0, 0, core_w + 2 * margin, core_h + 2 * margin)
core_rect = odb.Rect(margin, margin, margin + core_w, margin + core_h)
floorplan.initFloorplan(die_rect, core_rect, site)

# ── Routing grid (tracks from LEF) ─────────────────────────────────
# For each ROUTING layer in the tech LEF, creates a dbTrackGrid with both:
#   - X pattern (vertical tracks): origin + count + pitch from LEF PITCHX/OFFSETX
#   - Y pattern (horizontal tracks): origin + count + pitch from LEF PITCHY/OFFSETY
# Tracks that would violate min-width at die edges are trimmed.
# The router and pin placer use these grids to snap wires and pin slots.

floorplan.makeTracks()

# ── Pin placement (symmetric) ─────────────────────────────────────
# Strategy:
#   1. Exclude the mirrored half of the die boundary.
#   2. Constrain primary pins to their edges on the primary half.
#   3. Run Hungarian matching on primaries + solo pins.
#   4. Read back primary positions, reflect across axis, place mirror partners.
#
# Hungarian algorithm (ppl module, HungarianMatching.cpp):
#   - Enumerate candidate slots on available (non-excluded) boundary segments.
#   - Build cost matrix: HPWL of each pin's net at each slot.
#   - Solve min-cost assignment via Munkres (O(n^3), exact).

io_placer = design.getIOPlacer()

hor_layer = db_tech.findLayer(pin_hor_layer)
ver_layer = db_tech.findLayer(pin_ver_layer)
io_placer.addHorLayer(hor_layer)
io_placer.addVerLayer(ver_layer)

die = block.getDieArea()
sym_x = (die.xMin() + die.xMax()) // 2
sym_y = (die.yMin() + die.yMax()) // 2

# Exclude the mirrored half of the die boundary
if symmetry_axis == "vertical":
    io_placer.excludeInterval(io_placer.getEdge("right"), die.yMin(), die.yMax())
    io_placer.excludeInterval(io_placer.getEdge("top"), sym_x, die.xMax())
    io_placer.excludeInterval(io_placer.getEdge("bottom"), sym_x, die.xMax())
else:
    io_placer.excludeInterval(io_placer.getEdge("top"), die.xMin(), die.xMax())
    io_placer.excludeInterval(io_placer.getEdge("right"), sym_y, die.yMax())
    io_placer.excludeInterval(io_placer.getEdge("left"), sym_y, die.yMax())

# Constrain primary pins to the primary half of their edges
mirrors: list[tuple[str, str]] = []
for pin in pins:
    edge = pin["edge"]
    if symmetry_axis == "vertical":
        if edge in ("top", "bottom"):
            begin, end = die.xMin(), sym_x - 1
        else:  # left only (right is excluded)
            begin, end = die.yMin(), die.yMax()
    else:
        if edge in ("left", "right"):
            begin, end = die.yMin(), sym_y - 1
        else:  # bottom only (top is excluded)
            begin, end = die.xMin(), die.xMax()

    region = block.findConstraintRegion(edge, begin, end)
    bterm = block.findBTerm(pin["primary"])
    if bterm is not None:
        block.addBTermsToConstraint([bterm], region)

    if "mirror" in pin:
        mirrors.append((pin["primary"], pin["mirror"]))

# Run Hungarian on primary + solo pins only
io_placer.runHungarianMatching()

# Build a pin → edge lookup for choosing the correct layer
pin_edge_map: dict[str, str] = {}
for pin in pins:
    pin_edge_map[pin["primary"]] = pin["edge"]
    if "mirror" in pin:
        pin_edge_map[pin["mirror"]] = pin["edge"]

# Place mirror partners at reflected positions
for primary_name, mirror_name in mirrors:
    primary_bterm = block.findBTerm(primary_name)
    mirror_bterm = block.findBTerm(mirror_name)
    if primary_bterm is None or mirror_bterm is None:
        continue

    _, px, py = primary_bterm.getFirstPinLocation()

    if symmetry_axis == "vertical":
        mx, my = 2 * sym_x - px, py
    else:
        mx, my = px, 2 * sym_y - py

    edge = pin_edge_map.get(primary_name, "left")
    layer = hor_layer if edge in ("left", "right") else ver_layer
    io_placer.placePin(mirror_bterm, layer, mx, my, 0, 0, True, False)

# ── Power distribution network ────────────────────────────────────
# M1 horizontal followpin rails at each row edge (connect to cell VDD/VSS pins),
# M4 vertical stripes (VDD left, VSS right), via stack M1↔M4.

pdngen = design.getPdnGen()
m1 = db_tech.findLayer("Metal1")
m4 = db_tech.findLayer("Metal4")
vdd_net = block.findNet("vdd")
vss_net = block.findNet("vss")
vdd_net.setSpecial()
vss_net.setSpecial()
vdd_net.setSigType("POWER")
vss_net.setSigType("GROUND")

pdngen.setCoreDomain(vdd_net, None, vss_net, [])
domain = pdngen.findDomain("Core")

pdngen.makeCoreGrid(domain, "analog_grid", pdn.GROUND, [m4], [], None, None, "", [])
grid = pdngen.findGrid("analog_grid")[0]

pdngen.makeFollowpin(grid, m1, design.micronToDBU(0.42), pdn.CORE)

die = block.getDieArea()
strap_width = design.micronToDBU(1.0)

# M4 vertical straps: placed directly via ODB for exact edge alignment.
# PDN's makeStrap always snaps to the track grid, so we bypass it for the straps
# and only use PDN for the M1 followpin rails.
pdngen.buildGrids(False)
pdngen.writeToDb(True)

die = block.getDieArea()
strap_width = design.micronToDBU(1.0)

for net, x_left in [(vdd_net, die.xMin()), (vss_net, die.xMax() - strap_width)]:
    swire = odb.dbSWire.create(net, "ROUTED")
    odb.dbSBox.create(
        swire,
        m4,
        x_left,
        die.yMin(),
        x_left + strap_width,
        die.yMax(),
        "STRIPE",
    )

# ── Output ──────────────────────────────────────────────────────────

design.writeDef(output_def)
odb.write_db(block.getDataBase(), output_def.replace(".def", ".odb"))
