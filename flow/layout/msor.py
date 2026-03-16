"""OpenROAD analog place-and-route script.

Runs inside ``openroad -exit -python``.  Receives a path to a JSON
configuration file on sys.argv[1].

    openroad -exit -python flow/layout/msor.py config.json
"""

import json
import sys
from pathlib import Path

import odb
import openroad
from openroad import Tech, Design

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())

tech_lefs: list[str] = cfg["tech_lefs"]
macro_lefs: list[str] = cfg["macro_lefs"]
verilog: str = cfg["verilog"]
top_module: str = cfg["top_module"]

die_area: list[float] = cfg["die_area"]
core_area: list[float] = cfg["core_area"]
site_name: str = cfg["site_name"]

tracks: dict[str, dict] = cfg.get("tracks", {})

pin_hor_layer: str = cfg["pin_hor_layer"]
pin_ver_layer: str = cfg["pin_ver_layer"]
pin_constraints: list[dict] = cfg.get("pin_constraints", [])
mirrored_pins: list[list[str]] = cfg.get("mirrored_pins", [])

output_def: str = cfg["output_def"]

# ── Load technology and design ──────────────────────────────────────

tech = Tech()
for lef in tech_lefs:
    tech.readLef(lef)
for lef in macro_lefs:
    tech.readLef(lef)

design = Design(tech)
design.readVerilog(verilog)
design.link(top_module)

db_tech = tech.getTech()
block = design.getBlock()

# ── Placement grid (rows from SITE) ────────────────────────────────

floorplan = design.getFloorplan()
site = floorplan.findSite(site_name)

die_rect = odb.Rect(
    design.micronToDBU(die_area[0]),
    design.micronToDBU(die_area[1]),
    design.micronToDBU(die_area[2]),
    design.micronToDBU(die_area[3]),
)
core_rect = odb.Rect(
    design.micronToDBU(core_area[0]),
    design.micronToDBU(core_area[1]),
    design.micronToDBU(core_area[2]),
    design.micronToDBU(core_area[3]),
)
floorplan.initFloorplan(die_rect, core_rect, site)

# ── Routing grid (tracks) ──────────────────────────────────────────

if tracks:
    for layer_name, t in tracks.items():
        layer = db_tech.findLayer(layer_name)
        floorplan.makeTracks(
            layer,
            design.micronToDBU(t["x_offset"]),
            design.micronToDBU(t["x_pitch"]),
            design.micronToDBU(t["y_offset"]),
            design.micronToDBU(t["y_pitch"]),
        )
else:
    floorplan.makeTracks()

# ── Pin placement ───────────────────────────────────────────────────

io_placer = design.getIOPlacer()

hor_layer = db_tech.findLayer(pin_hor_layer)
ver_layer = db_tech.findLayer(pin_ver_layer)
io_placer.addHorLayer(hor_layer)
io_placer.addVerLayer(ver_layer)

for pc in pin_constraints:
    edge_name = pc["edge"]
    edge = io_placer.getEdge(edge_name)
    die = block.getDieArea()

    if edge_name in ("top", "bottom"):
        begin = die.xMin()
        end = die.xMax()
    else:
        begin = die.yMin()
        end = die.yMax()

    region = block.findConstraintRegion(edge_name, begin, end)
    bterms = [block.findBTerm(n) for n in pc["pins"]]
    bterms = [b for b in bterms if b is not None]
    block.addBTermsToConstraint(bterms, region)

for pair in mirrored_pins:
    a = block.findBTerm(pair[0])
    b = block.findBTerm(pair[1])
    if a is not None and b is not None:
        a.setMirroredBTerm(b)

io_placer.runHungarianMatching()

# ── Output ──────────────────────────────────────────────────────────

design.writeDef(output_def)
