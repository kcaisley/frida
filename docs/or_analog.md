# Copied and reformatting from the Appendix of PH Wei's 2021 Thesis 

Cadence Innovus Settings and Scripts
ALOE generates tcl scripts to interface with Cadence Innovus; the arguments of the scripts are either
read from a master text file or entered through the GUI, as discussed in Appendix B. Because the
user inputs are minimal, and ALOE lacks the timing library, the Innovus command usage in ALOE
is atypical of what is used in a common digital PnR flow. In the following codes, variables are
preceded with a “$” symbol. Codes A.1 and A.2 show how optional floorplan and pin sides can be
specified in Innovus without using a strict .io file that confines their absolute numbers and locations.
Code A.3 shows how ALOE automatically sets up non-default net widths and spacings for the two
sample nets. Multiple non-default rules can be automatically generated from the master input file.
Controlled by the evolutionary algorithm, the net weight generation script is shown in Code A.4,
where each net is assigned to its unique group.

Program Code A.1: Auto-generated floorplanning script in ALOE

floorPlan -r $aspect_ratio $total_utilization 0.0 0.0 0.0 0.0



Program Code A.2: Auto-generated pin side assignment in ALOE:

createPinGroup leftPin -cell $block_name \
-spacing 1 -optimizeOrder
addPinToPinGroup -pinGroup leftPin \
-cell $block_name \


-pin $pin_name
createPinGuide -pinGroup leftPin \
-cell $block_name \
-edge 0 \
-layer $layer_list



Program Code A.4: Auto-generated net weight assignment in ALOE.

add_ndr -name M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x \
-generate_via -width_multiplier {M2 2 M3 2 M4 2 M5 2} \
-spacing_multiplier {M2 2 M3 2 M4 2 M5 2}

setAttribute -net $net0 \
-non_default_rule M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x \
-bottom_preferred_routing_layer $routing_layer_bottom \


-preferred_routing_layer_effort high
setAttribute -net $net1 \
-non_default_rule M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x\
-bottom_preferred_routing_layer $routing_layer_bottom \
-preferred_routing_layer_effort high
Program Code A.3: Auto-generated net width assignment in ALOE.
createNetGroup $group_name
specifyNetWeight $net_name $net_weight



Because AMS circuit netlists tend to be smaller than their digital counterparts, we trade runtime
for optimal multiple-via dropping and highest technological compliance. Importantly, we need to
choose the extraction engine with the highest accuracy to enable the RC-based ranking. Code A.5
shows key settings that enables better-performing AMS layouts in Cadence Innovus. Code A.6
shows the swap cell function (3.6), executed with engineering-change-order (ECO) commands.



Program Code A.5: Key settings for physical-only AMS layouts in FinFET CMOS.APPENDIX A. CADENCE INNOVUS SETTINGS AND SCRIPTS
setDesignMode -process $process_node
setPlaceMode -coreEffort high \


-place_detail_color_aware_legal true
setNanoRouteMode -drouteAutoStop false \
-drouteExpAdvancedMarFix true \
-drouteFixAntenna true \
-drouteUseMultiCutViaEffort high \
-routeWithTimingDriven false \
-routeWithSiDriven false \
-routeAutoPinAccessForBlockPin true \
-routeConcurrentMinimizeViaCountEffort high \
-routeExpAdvancedTechnology true
setExtractRCMode -engine postRoute \
-effortLevel high \
-coupled true \
-qrcCmdFile $fqrc



Program Code A.6: Swap cell function:

proc swapCellsOnNet {netName tail} {
setEcoMode -updateTiming false
setEcoMode -LEQCheck false
setEcoMode -batchMode true
setEcoMode -honorFixedStatus false
setEcoMode -honorDontUse false
setEcoMode -honorDontTouch false
setEcoMode -refinePlace false
setEcoMode -replicatedModules true
deselectAll
selectInstOnNet $netName
foreach instPtr [dbGet selected] {
set instCellName [dbGet $instPtr.cell.name]
if ![string match *$tail $instCellName] {
set instName [dbGet $instPtr.name]
set tiedCell [concat $instCellName$tail]
ecoChangeCell -inst $instName -cell $tiedCell
unset tiedCell
unset instName
}
unset instCellName
}

deselectAll

}
proc swap_cells {args} {
parse_proc_arguments -args $args options
# Set default values
set $options(-net) "VDD"
set $options(-tail) "_tied"
# Swap cells
swapCellsOnNet $options(-net) $options(-tail)
}
define_proc_arguments swap_cells \
-info "Writes TCL scripts to run.\n" \
-define_args \
{{-net "net name" "none" string required}
{-tail "tied cell identifying string" "none" string optional}
}




# Custom Placement and Routing in OpenROAD

This document summarizes the capabilities and limitations of OpenROAD for custom placement and routing, particularly for analog or symmetrically-constrained designs.

## Manual Cell Placement

### Support: YES ✅

OpenROAD fully supports manual cell placement through the OpenDB API.

### API Methods

**Setting Cell Position:**
```python
# Python
inst.setLocation(x, y)  # Coordinates in DBU (Database Units)
inst.setPlacementStatus(odb.dbPlacementStatus.LOCKED)
```

```tcl
# TCL
set inst [odb::dbInst_create $block $master "inst_name"]
$inst setLocation $x $y
$inst setPlacementStatus LOCKED
```

### Placement Status Options

| Status | Description | Movable by Placer? |
|--------|-------------|-------------------|
| `NONE` | Not placed | N/A |
| `UNPLACED` | Arbitrary placement | Yes |
| `SUGGESTED` | Suggested placement | Yes |
| `PLACED` | Cell is placed | Yes |
| `LOCKED` | Fixed position | **No** |
| `FIRM` | Cannot be moved | **No** |
| `COVER` | Cover cell | **No** |

**Key Point:** Use `LOCKED` or `FIRM` status to fix cells at manual positions.

### Placer Behavior

Both global placement (GPL) and detailed placement (DPL) respect cell placement status:
- Cells with `LOCKED` or `FIRM` status are NOT moved
- Cells with `PLACED` status CAN be moved during optimization
- Manual placements are preserved through incremental placement

### Key Files

- Manual placement API: `~/work/OpenROAD/src/odb/include/odb/db.h:2706-2778`
- GPL header: `~/work/OpenROAD/src/gpl/include/gpl/Replace.h`
- DPL header: `~/work/OpenROAD/src/dpl/include/dpl/Opendp.h`

## Routing Guides and Position Control

### Support: YES ✅

Both global and detailed routers have explicit position-based guide systems.

### Global Router (GRT) Guides

**Data Structure:**
- `GSegment`: Route segments with explicit positions
  - `(init_x, init_y, init_layer) → (final_x, final_y, final_layer)`
- `GRoute`: Vector of GSegments forming complete routing path

**Commands:**
```tcl
# Read/write guides
read_guides file_name
write_global_route_segments file_name

# Route with guides
global_route -guide_file output.guide
```

### Detailed Router (DRT) Guides

**frGuide Class:**
```cpp
class frGuide {
  odb::Point getBeginPoint() const;
  odb::Point getEndPoint() const;
  frLayerNum getBeginLayerNum() const;
  frLayerNum getEndLayerNum() const;
  bool hasRoutes() const;
  std::vector<std::unique_ptr<frConnFig>> getRoutes() const;
}
```

- Guides define spatial regions and layers for routing
- Each net can have multiple guides
- Guides are fundamental to detailed routing flow

### Available Routing Commands

**Global Routing:**
```tcl
global_route [-guide_file out_file] \
             [-congestion_iterations iterations] \
             [-grid_origin {x y}] \
             [-allow_congestion] \
             [-resistance_aware]

set_global_routing_layer_adjustment layer adjustment
set_global_routing_region_adjustment {x1 y1 x2 y2} -layer layer -adjustment adj
set_routing_layers [-signal min-max] [-clock min-max]
```

**Detailed Routing:**
```tcl
detailed_route [-output_maze file] \
               [-output_drc file] \
               [-output_guide_coverage file] \
               [-min_access_points count]
```

## Symmetric Routing

### Support: NO ❌

**OpenROAD does NOT have native symmetric routing capabilities.**

Extensive search found no support for:
- ❌ Symmetric routing features
- ❌ Net pair definitions or constraints
- ❌ Differential pair support
- ❌ Analog-specific routing (only antenna repair exists)

### What Would Be Needed

To implement symmetric routing in OpenROAD would require:

1. **Net Pairing API** - Define which nets must route symmetrically
2. **Symmetric Constraint** - New constraint type in constraint system
3. **Coupled Router** - Router phase that routes paired nets together
4. **Verification** - Check that paired routes are symmetric

**Files that would need modification:**
- `/home/kcaisley/work/OpenROAD/src/drt/src/db/obj/frNet.h` - Add net pair pointer
- `/home/kcaisley/work/OpenROAD/src/drt/src/db/tech/frConstraint.h` - Add symmetric constraint
- Routing algorithms in DRT to handle coupled routing

### Workaround: Manual Guide-Based Approach

While not native, you can enforce symmetry using guides:

**Workflow:**
1. Route one net of the symmetric pair
2. Extract routing guides
3. Geometrically transform (mirror) guides for paired net
4. Apply transformed guides to second net
5. Route with guides constraining the path

**Python Implementation Approach:**
```python
from openroad import Design
import odb

# 1. Route first net normally
design = Design()
design.readDef("design.def")
grt = design.getGlobalRouter()
grt.globalRoute()

# 2. Extract routing for net1
block = design.getBlock()
net1 = block.findNet("signal_p")
# Extract guide coordinates from net1

# 3. Mirror coordinates for symmetric net
symmetry_axis_x = 1000  # Your symmetry axis
for guide in net1_guides:
    begin = guide.getBeginPoint()
    end = guide.getEndPoint()

    # Mirror x-coordinates across symmetry axis
    x_begin_mirror = 2 * symmetry_axis_x - begin.getX()
    x_end_mirror = 2 * symmetry_axis_x - end.getX()

    # Create mirrored guide for net2
    # (Would need custom code to create and apply guides)

# 4. Apply guides and route
grt.readGuides("mirrored_guides.guide")
drt = design.getTritonRoute()
drt.detailedRoute()
```

**Note:** This requires custom scripting as there's no built-in API for guide manipulation.

## Python vs TCL API

### Python is MORE Capable ✅

**TCL Interface:**
- Uses wrapper functions around C++ methods
- Only exposes explicitly wrapped commands (~50 functions)
- Limited to predefined command set

**Python Interface:**
- Directly includes C++ header files via SWIG
- Exposes ALL public methods from C++ classes
- Full object-oriented access to OpenROAD internals

### Examples of Python-Only Methods

Methods available in `Replace` class but NOT in TCL:
```python
replace = design.getReplace()
replace.setInitialPlaceMinDiffLength(length)  # Python only
replace.setInitialPlaceMaxSolverIter(iter)    # Python only
replace.setInitialPlaceNetWeightScale(scale)  # Python only
```

### Recommendation for Custom Designs

**Use Python** when you need:
- Direct ODB database manipulation
- Geometric transformations (mirroring, rotation)
- Complex data structure processing
- Custom algorithms (e.g., symmetric guide generation)
- Integration with NumPy/SciPy for matrix operations

**Use TCL** when you need:
- Simple scripting of standard flows
- Compatibility with existing VLSI tool scripts
- Quick interactive commands

## Complete Example: Manual Placement + Routing

### Python Workflow

```python
from openroad import Design, Tech
import odb

# Initialize design
tech = Tech()
tech.readLef("technology.lef")
design = Design(tech)
design.readDef("design.def")

# === MANUAL PLACEMENT ===
block = design.getBlock()

# Get instances
inst1 = block.findInst("cell_a")
inst2 = block.findInst("cell_b")

# Set symmetric positions
inst1.setLocation(1000, 2000)  # DBU coordinates
inst1.setPlacementStatus(odb.dbPlacementStatus.LOCKED)

inst2.setLocation(3000, 2000)  # Mirrored position
inst2.setPlacementStatus(odb.dbPlacementStatus.LOCKED)

# === GLOBAL PLACEMENT (respects locked cells) ===
gpl = design.getReplace()
gpl.setTargetDensity(0.7)
gpl.setTargetOverflow(0.1)
gpl.doNesterovPlace(threads=4)

# === DETAIL PLACEMENT ===
dpl = design.getOpendp()
dpl.detailedPlacement(0, 0)  # 0 = no displacement limit
dpl.checkPlacement(verbose=True)

# === GLOBAL ROUTING ===
grt = design.getGlobalRouter()
grt.globalRoute()

# Save routing guides
grt.writeGuides("routes.guide")

# === DETAIL ROUTING ===
drt = design.getTritonRoute()
drt.detailedRoute()

# Save result
design.writeDef("placed_routed.def")
```

### TCL Workflow

```tcl
# Read design
read_lef technology.lef
read_def design.def

# === MANUAL PLACEMENT ===
set block [ord::get_db_block]
set inst1 [$block findInst "cell_a"]
set inst2 [$block findInst "cell_b"]

# Set positions and lock
$inst1 setLocation 1000 2000
$inst1 setPlacementStatus LOCKED

$inst2 setLocation 3000 2000
$inst2 setPlacementStatus LOCKED

# === GLOBAL PLACEMENT ===
global_placement -density 0.7 -overflow 0.1

# === DETAIL PLACEMENT ===
detailed_placement
check_placement -verbose

# === ROUTING ===
global_route -guide_file routes.guide
detailed_route

# Save result
write_def placed_routed.def
```

## Summary Table

| Feature | GPL | DPL | GRT | DRT | Status |
|---------|-----|-----|-----|-----|--------|
| Manual cell placement | N/A | ✅ | N/A | N/A | Full support via ODB |
| Respects locked cells | ✅ | ✅ | N/A | N/A | Yes |
| Position/guide system | N/A | N/A | ✅ | ✅ | Full support |
| Symmetric net pairing | ❌ | ❌ | ❌ | ❌ | **Not implemented** |
| Guide read/write | N/A | N/A | ✅ | ✅ | Full I/O support |
| Python API | ✅ | ✅ | ✅ | ✅ | Complete |
| TCL API | ✅ | ✅ | ✅ | ✅ | Limited to wrapped commands |

## Conclusion

OpenROAD provides excellent support for:
- ✅ Manual cell placement with position locking
- ✅ Position-based routing via explicit guides
- ✅ Python API with full C++ class access

However, it lacks:
- ❌ Native symmetric/matched net pair routing
- ❌ Differential pair constraints
- ❌ Analog circuit-specific routing features

For custom analog or symmetric designs, you can work around these limitations by:
1. Using manual placement with `LOCKED` status
2. Extracting and transforming routing guides programmatically
3. Leveraging Python API for better control and automation

---

**Document Version:** 1.0
**Last Updated:** 2025-12-19
**OpenROAD Directory:** `/home/kcaisley/work/OpenROAD`
