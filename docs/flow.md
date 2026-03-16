# Analog PnR Flow Comparison

Comparison of floorplanning, placement, and routing across OpenROAD, ALIGN,
and MAGICAL — evaluated for analog transistor-level design.

## Phase 1: Floorplanning & Technology Definition

### 1.1 Placement Grid

How each tool defines the placement grid that cells snap to.

| | OpenROAD | ALIGN | MAGICAL |
|---|---|---|---|
| **Command** | `floorplan.initFloorplan(...)` | Implicit from `layers.json` `Pitch` fields + `PlaceOnGrid` constraint | Implicit from `gridStep` in netlist header |
| **Source** | LEF `SITE` definition (height × width) | `layers.json` → `grid_unit_x`, `grid_unit_y` derived from M1/M2 pitch | `gridStep` = routing pitch (set once, flows everywhere) |
| **Grid model** | **Row-based**: fixed-height rows of site tiles. Cells tile left-to-right within rows. Row height = site height = N tracks (typically 7T–12T in digital; could be any multiple for analog). | **2D free placement**: no rows. Blocks placed anywhere in the plane, snapped to grid pitch by ILP binary variables. Per-block `PlaceOnGrid` constraint can set custom pitch + allowed offsets. | **2D free placement**: no rows. IdeaPlaceEx places cells freely, snaps to `gridStep`. Boundary aligned to `gridStep` multiples post-placement. |
| **Module** | `ifp` ([InitFloorplan.tcl#L15](file:///home/kcaisley/libs/OpenROAD/src/ifp/src/InitFloorplan.tcl#L15)) | `PnRDB` + `placer` ([Placer.cpp#L11](file:///home/kcaisley/libs/ALIGN-public/PlaceRouteHierFlow/placer/Placer.cpp#L11), [ILP_solver.cpp#L504](file:///home/kcaisley/libs/ALIGN-public/PlaceRouteHierFlow/placer/ILP_solver.cpp#L504)) | `flow/python/Placer.py` ([Placer.py#L22](file:///home/kcaisley/libs/MAGICAL/flow/python/Placer.py#L22)) |
| **Separate step?** | Yes — must run before placement | No — enforced during ILP placement solve | No — parameter passed into placement solve |
| **Complexity** | Deterministic formula: enumerate rows from `core_area.y` to top, each row = one site height. O(n_rows). | ILP adds binary variables per block per allowed offset. O(n_blocks × n_offsets). | Single scalar parameter; snapping is O(1) per cell. |

**OpenROAD Python API:**

```python
from openroad import Tech, Design
import odb

tech = Tech()
design = Design(tech)
floorplan = design.getFloorplan()

site = floorplan.findSite("unit")  # LEF SITE name → defines row height & width

# Option A: auto-size from utilization (requires netlist to be loaded)
space = design.micronToDBU(2.0)    # core margin in DBU
floorplan.initFloorplan(
    30,          # utilization (percent)
    0.5,         # aspect_ratio (width / height)
    space,       # bottom margin (DBU)
    space,       # top margin (DBU)
    space,       # left margin (DBU)
    space,       # right margin (DBU)
    site,        # LEF SITE object
)

# Option B: explicit die and core rectangles
die  = odb.Rect(design.micronToDBU(0),  design.micronToDBU(0),
                design.micronToDBU(200), design.micronToDBU(200))
core = odb.Rect(design.micronToDBU(10), design.micronToDBU(10),
                design.micronToDBU(190), design.micronToDBU(190))
floorplan.initFloorplan(die, core, site)
```

**ALIGN constraint JSON:**

```json
{
    "constraint": "PlaceOnGrid",
    "direction": "V",
    "pitch": 80,
    "ored_terms": [{"offsets": [0, 40], "scalings": [1, -1]}]
}
```

**MAGICAL Python API:**

```python
placer = IdeaPlaceEx()
placer.solve(gridStep)   # gridStep read from netlist file header
```

---

### 1.2 Routing Grid (Tracks)

How each tool defines the routing track grid (layer directions, pitch, width).

| | OpenROAD | ALIGN | MAGICAL |
|---|---|---|---|
| **Command** | `floorplan.makeTracks(...)` | Implicit from `layers.json` | Implicit from LEF layer definitions |
| **Source** | LEF `LAYER` pitch + offset, or explicit overrides | `layers.json` per-layer: `Pitch`, `Width`, `Offset`, `Direction`, `MinL`, `MaxL` | LEF `LAYER` section → `pitch`, `width`, `spacing`, `direction` parsed by Limbo |
| **What it defines** | Track positions per metal layer (H or V). Each track = a legal wire center-line. Does NOT set wire width or NDRs — those come from LEF `LAYER` rules. | Full metal stack: track pitch, width, min/max length, direction, color assignment. The `DefaultCanvas` class builds metal generators from this. | Layer pitch, width, spacing, direction, EOL rules. Router uses `gridStep` for the A* grid. |
| **NDR support** | NDRs are defined separately via `create_ndr` in the `drt` module, not in `ifp`. | NDR via `HananRouter` `LayerCost` with per-layer direction constraints | `--spec` file per-net: custom `minWidth`, `minCuts` |
| **Module** | `ifp` ([InitFloorplan.tcl#L191](file:///home/kcaisley/libs/OpenROAD/src/ifp/src/InitFloorplan.tcl#L191)) | `align/primitive/default/canvas.py` ([canvas.py#L12](file:///home/kcaisley/libs/ALIGN-public/align/primitive/default/canvas.py#L12)) | `parser/parLef.cpp` ([parLef.cpp#L279](file:///home/kcaisley/libs/MAGICAL/anaroute/src/parser/parLef.cpp#L279)) |
| **Separate step?** | Yes — typically called right after `initFloorplan` | No — read once when PDK is loaded | No — parsed from LEF at startup |

**OpenROAD Python API:**

```python
db_tech = tech.getTech()
floorplan = design.getFloorplan()

# Option A: auto from all LEF layers (uses LAYER pitch/offset from LEF)
floorplan.makeTracks()

# Option B: auto from LEF for one layer
m1 = db_tech.findLayer("Metal1")
floorplan.makeTracks(m1)

# Option C: explicit pitch and offset per layer (values in DBU)
x_offset = design.micronToDBU(0.0)
x_pitch  = design.micronToDBU(0.42)
y_offset = design.micronToDBU(0.0)
y_pitch  = design.micronToDBU(0.42)
floorplan.makeTracks(m1, x_offset, x_pitch, y_offset, y_pitch)
```

**ALIGN `layers.json` (excerpt):**

```json
{
    "M1": {
        "Direction": "v",
        "Pitch": 80,
        "Width": 40,
        "Offset": 40,
        "MinL": 200,
        "MaxL": 2000
    }
}
```

**MAGICAL LEF (parsed automatically):**

```
LAYER M1
    TYPE ROUTING ;
    DIRECTION VERTICAL ;
    PITCH 0.08 ;
    WIDTH 0.04 ;
    SPACING 0.04 ;
END M1
```

---

### 1.3 Bounding Box / Die Area

How the cell or block boundary is determined.

| | OpenROAD | ALIGN | MAGICAL |
|---|---|---|---|
| **Auto-sizing** | `initFloorplan(utilization, aspect_ratio, ...)`: `core_area = Σ(cell_areas) / (utilization/100)`, then `width = √(core_area × r)`, `height = width / r`. Rows quantize the final dimensions. | SA + ILP minimize area subject to `Boundary` and `AspectRatio` constraints. Actual area is emergent from the sequence-pair floorplan. | Emergent: die = placement result + area-dependent spacing buffer from lookup table. `upscaleBBox()` rounds to `gridStep` multiples. |
| **Explicit sizing** | `initFloorplan(die_rect, core_rect, site)` | `Boundary` constraint: `{"const_name": "Boundary", "max_width": W, "max_height": H}` | No explicit sizing — always emergent. |
| **Aspect ratio** | `aspect_ratio` parameter (single value) | `{"const_name": "AspectRatio", "ratio_low": 0.5, "ratio_high": 2.0}` — range, not single value | No aspect ratio control. |
| **Module** | `ifp` | `PnRDB/ReadConstraint.cpp` ([ReadConstraint.cpp#L527](file:///home/kcaisley/libs/ALIGN-public/PlaceRouteHierFlow/PnRDB/ReadConstraint.cpp#L527), [#L604](file:///home/kcaisley/libs/ALIGN-public/PlaceRouteHierFlow/PnRDB/ReadConstraint.cpp#L604)) | `flow/python/Placer.py` ([Placer.py#L162](file:///home/kcaisley/libs/MAGICAL/flow/python/Placer.py#L162)) |
| **Algorithm** | Deterministic formula (no optimization) | Part of SA + ILP placement objective: area + aspect_ratio penalty + boundary violation penalty | N/A — computed post-placement |

**OpenROAD Python API:** See section 1.1 — both sizing modes are overloads of
`floorplan.initFloorplan()`.

**ALIGN constraint JSON:**

```json
[
    {"const_name": "Boundary", "max_width": 10000, "max_height": 5000},
    {"const_name": "AspectRatio", "ratio_low": 0.5, "ratio_high": 2.0}
]
```

**MAGICAL:** No user input — boundary computed automatically.

---

### 1.4 Pin Placement

How I/O pins are assigned to positions on the cell/block boundary.

| | OpenROAD | ALIGN | MAGICAL |
|---|---|---|---|
| **Dedicated step?** | **Yes** — `place_pins` is a standalone step after floorplan init | **No** — pin positions specified by user constraint, not optimized | **Partially** — IO pin positions optimized by IdeaPlaceEx during placement, but only at top-level hierarchy |
| **Automatic placement** | `design.getIOPlacer().runHungarianMatching()`: assigns all unplaced pins to die-boundary slots | None — `PortLocation` is user-specified only | `openVirtualPinAssignment()`: placer assigns IO pins to boundary positions during solve |
| **Manual placement** | `design.getIOPlacer().placePin(bterm, layer, x, y, w, h, ...)` | `PortLocation` constraint per pin | Not supported — always automatic |
| **Module** | `ppl` ([IOPlacer.tcl#L222](file:///home/kcaisley/libs/OpenROAD/src/ppl/src/IOPlacer.tcl#L222), [ppl_aux.py#L9](file:///home/kcaisley/libs/OpenROAD/src/ppl/test/ppl_aux.py#L9)) | `PnRDB/ReadConstraint.cpp` ([ReadConstraint.cpp#L358](file:///home/kcaisley/libs/ALIGN-public/PlaceRouteHierFlow/PnRDB/ReadConstraint.cpp#L358)) | `flow/python/Placer.py` ([Placer.py#L107](file:///home/kcaisley/libs/MAGICAL/flow/python/Placer.py#L107)) |
| **Algorithm** | **Hungarian matching** (Munkres, O(n³)) for optimal pin-to-slot assignment. Optional **Simulated Annealing** refinement via `set_simulated_annealing`. | No algorithm — positions are declarative (12 boundary regions). | Part of IdeaPlaceEx analytical/SA solve — simultaneous with cell placement. |
| **Objective** | Minimize total HPWL across all pin-to-instance nets. SA adds swap/move perturbations with `exp(-ΔC/T)` acceptance. | N/A | Minimize HPWL (integrated with placement objective). |
| **Pin symmetry** | **`set_io_pin_constraint -mirrored_pins {pin1 pin2 ...}`** (TCL) or **`bterm1.setMirroredBTerm(bterm2)`** (Python/ODB). Pairs are placed symmetrically across the die center axis. The Hungarian matcher co-optimizes both pins in a pair, adding the mirrored HPWL cost to the assignment matrix. Must be called **before** `place_pins`. | No pin-level symmetry. Pin positions are fixed by user constraint. Block-level symmetry is separate. | **Implicit**: net symmetry from `.symnet` files propagates — if nets `VINP`/`VINN` are symmetric, their IO pins are placed symmetrically by the placer. |
| **Constraints** | Exclude regions, pin grouping/ordering, corner avoidance, minimum distance, mirrored pairs | 12 boundary regions: `TL, TC, TR, RT, RC, RB, BR, BC, BL, LB, LC, LT` | `setIoPinBoundaryExtension(dist)`, `setIoPinInterval(spacing)` |

**OpenROAD Python API (automatic pin placement):**

```python
from openroad import Design
import odb

io_placer = design.getIOPlacer()
params = io_placer.getParameters()
db_tech = design.getTech().getDB().getTech()
block = design.getBlock()

# Configure layers for pin placement
hor_layer = db_tech.findLayer("Metal3")
ver_layer = db_tech.findLayer("Metal2")
io_placer.addHorLayer(hor_layer)
io_placer.addVerLayer(ver_layer)

# Configure spacing
params.setCornerAvoidance(design.micronToDBU(1.0))
params.setMinDistance(design.micronToDBU(2.0))

# Run automatic placement (Hungarian matching)
io_placer.runHungarianMatching()
```

**OpenROAD Python API (manual single-pin placement):**

```python
bterm = block.findBTerm("CLK")
layer = db_tech.findLayer("Metal3")
x = design.micronToDBU(100.0)
y = design.micronToDBU(0.0)
w = design.micronToDBU(0.1)
h = design.micronToDBU(0.5)
io_placer.placePin(bterm, layer, x, y, w, h,
                   False,  # force_to_die_boundary
                   False)  # placed_status
```

**OpenROAD Python API (mirrored/symmetric pins):**

```python
# Set up mirrored pin pairs before calling runHungarianMatching().
# Paired pins are placed symmetrically across the die center axis.
# The list must contain an even number of pins — each consecutive
# pair (pin1, pin2), (pin3, pin4), ... is mirrored.

block = design.getBlock()

bterm_inp = block.findBTerm("INP")
bterm_inn = block.findBTerm("INN")
bterm_inp.setMirroredBTerm(bterm_inn)   # ODB call, sets both directions

bterm_outp = block.findBTerm("OUTP")
bterm_outn = block.findBTerm("OUTN")
bterm_outp.setMirroredBTerm(bterm_outn)

# Now run placement — matcher will co-optimize mirrored pairs
io_placer.runHungarianMatching()
```

**OpenROAD Python API (pin region constraints):**

```python
# Constrain specific pins to a die edge region
# (Python equivalent of set_io_pin_constraint -pin_names ... -region ...)
edge = io_placer.getEdge("left")
begin = design.micronToDBU(10.0)
end = design.micronToDBU(50.0)
constraint_region = block.findConstraintRegion("left", begin, end)
pin_list = [block.findBTerm("VDD"), block.findBTerm("VSS")]
block.addBTermsToConstraint(pin_list, constraint_region)

# Exclude a region from pin placement
io_placer.excludeInterval(edge, begin, end)

# Group pins to be placed adjacent on boundary
group = [block.findBTerm("D0"), block.findBTerm("D1"),
         block.findBTerm("D2"), block.findBTerm("D3")]
block.addBTermGroup(group, True)  # True = ordered ascending by position
```

**OpenROAD Python API (SA refinement):**

```python
# Optional: simulated annealing refinement after Hungarian matching
# (TCL: set_simulated_annealing -temperature 1.0 -max_iterations 5000 ...)
# Must be configured via evalTclString — no direct Python binding:
design.evalTclString(
    "set_simulated_annealing -temperature 1.0 "
    "-max_iterations 5000 -perturb_per_iter 10 -alpha 0.99"
)
design.evalTclString(
    "place_pins -hor_layers Metal3 -ver_layers Metal2 -annealing"
)
```

**ALIGN constraint JSON:**

```json
{"const_name": "PortLocation", "terminal_name": "VOUT", "location": "TC"}
```

**MAGICAL `.symnet` file (drives pin symmetry):**

```
VINP VINN
VOUTP VOUTN
```

**MAGICAL Python API:**

```python
placer.openVirtualPinAssignment()
placer.setIoPinBoundaryExtension(12 * gridStep)
placer.setIoPinInterval(10 * gridStep)
placer.markIoNet(netIdx)
# After solve:
pin_x, pin_y = placer.readoutIoPins(netIdx)
is_vertical = placer.isIoPinVertical(netIdx)
```

---

### Phase 1 Summary

| Aspect | OpenROAD | ALIGN | MAGICAL |
|---|---|---|---|
| **Flow model** | Sequential discrete steps: `ifp` → `ppl` → placement | Fused: constraints parsed, then SA+ILP solves placement + floorplan together | Fused: IdeaPlaceEx solves placement + IO pins together |
| **Grid** | Row-based (SITE height), explicit init | 2D free, pitch from `layers.json`, grid-snap via ILP | 2D free, single `gridStep` param |
| **Bounding box** | Formula or explicit coords | Constrained (max W/H, aspect ratio range), optimized | Emergent from placement |
| **Pin placement** | Dedicated optimizer (Hungarian + SA) | User-specified regions only | Co-optimized with placement |
| **Pin symmetry** | `setMirroredBTerm()` pairs + `-mirrored_pins` constraint | None at pin level | Via `.symnet` net symmetry |
| **Analog suitability** | Modular — each step is replaceable. Row model works if cells share a common height. Pin optimizer is strong. Mirrored pins are natively supported. | Good symmetry at block level. Pin placement is weak (no optimization). | Best pin story for analog (auto + symmetric). No user control over die area. |
