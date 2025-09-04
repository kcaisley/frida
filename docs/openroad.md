# Tool Portability Analysis

## Tool-Portable Files (Industry Standard)

**Completely Portable:**
- `constraint.sdc` - Synopsys Design Constraints format supported by all major tools (Cadence Innovus, Synopsys ICC2/Fusion Compiler, OpenROAD)
- `*.v` - Verilog RTL files are portable across all synthesis tools
- `*.lef` - Library Exchange Format is industry standard (Cadence, Synopsys, OpenROAD)
- `*.lib` - Liberty timing format is industry standard

## Tool-Specific Files

**OpenROAD-Specific:**
- `tracks.info` - OpenROAD's custom format for routing track definitions
  - Cadence equivalent: Track information embedded in technology LEF file or specified via Innovus TCL commands (`createTrack`)
  - Synopsys equivalent: Technology file (`.tf`) or ICC2 technology library

**Mixed (Tool-Specific Syntax, Portable Concept):**
- `pdn.tcl` - Power Distribution Network script
  - Concept is portable but syntax differs significantly
  - Cadence: Uses `addRing`, `addStripe`, `sroute` commands
  - Synopsys: Uses `create_pg_std_cell_conn_pattern`, `compile_pg` commands
  - OpenROAD: Uses `pdngen` with different syntax
- `setRC.tcl` - RC extraction configuration
  - OpenROAD: `set_wire_rc -layer M1 -resistance 50e-3`
  - Cadence: `setExtractRCMode` and technology files
  - Synopsys: Technology files and `set_parasitic_parameters`


# Synthesis

- Input Files: adc.v, salogic.v, clkgate.v, capdriver.v, comp.v, sampswitch.v, caparray.v, constraint.sdc, tcbn65lpwc.lib, tcbn65lp_9lmT2.lef
- Flow Config Files: designs/tsmc65/adc/config.mk, platforms/tsmc65/config.mk, platforms/tsmc65/setRC.tcl, platforms/tsmc65/tapcell.tcl, platforms/tsmc65/pdn.tcl  
- Output Files: results/tsmc65/adc/base/1_synth.v, results/tsmc65/adc/base/1_synth.sdc, results/tsmc65/adc/base/1_2_yosys.v, results/tsmc65/adc/base/1_1_yosys_canonicalize.rtlil, results/tsmc65/adc/base/clock_period.txt, results/tsmc65/adc/base/mem.json
- Report/Collateral Files: reports/tsmc65/adc/base/synth_stat.txt, reports/tsmc65/adc/base/synth_check.txt, logs/tsmc65/adc/base/1_1_yosys_canonicalize.log, logs/tsmc65/adc/base/1_2_yosys.log, objects/tsmc65/adc/base/lib/tcbn65lpwc.lib, objects/tsmc65/adc/base/abc.constr


Note: Capacitor arrays are placed physically above in M5-M8 metal layers.

- Input Files: results/tsmc65/adc/base/1_synth.v, results/tsmc65/adc/base/1_synth.sdc, constraint.sdc, tcbn65lp_9lmT2.lef
- Flow Config Files: designs/tsmc65/adc/config.mk, platforms/tsmc65/config.mk
- Output Files: results/tsmc65/adc/base/2_floorplan.v, results/tsmc65/adc/base/2_floorplan.sdc, results/tsmc65/adc/base/2_floorplan.def
- Report/Collateral Files: reports/tsmc65/adc/base/2_floorplan.rpt, logs/tsmc65/adc/base/2_1_floorplan.log

# Placement

- Input Files: results/tsmc65/adc/base/2_floorplan.v, results/tsmc65/adc/base/2_floorplan.sdc, results/tsmc65/adc/base/2_floorplan.def
- Flow Config Files: designs/tsmc65/adc/config.mk, platforms/tsmc65/config.mk  
- Output Files: results/tsmc65/adc/base/3_place.v, results/tsmc65/adc/base/3_place.sdc, results/tsmc65/adc/base/3_place.def
- Report/Collateral Files: reports/tsmc65/adc/base/3_place.rpt, logs/tsmc65/adc/base/3_1_place.log, logs/tsmc65/adc/base/3_2_place_iop.log

Final utilization: 46% (target density 65%)
Cell placement: 219 instances placed within 50x50µm digital core area

# Clock Tree Synthesis (CTS)

- Input Files: results/tsmc65/adc/base/3_place.v, results/tsmc65/adc/base/3_place.sdc, results/tsmc65/adc/base/3_place.def
- Flow Config Files: designs/tsmc65/adc/config.mk, platforms/tsmc65/config.mk, platforms/tsmc65/cts.tcl
- Output Files: results/tsmc65/adc/base/4_cts.v, results/tsmc65/adc/base/4_cts.sdc, results/tsmc65/adc/base/4_cts.def
- Report/Collateral Files: reports/tsmc65/adc/base/4_cts.rpt, logs/tsmc65/adc/base/4_1_cts.log

Clock domains implemented:
- seq_init_clk: 100ns period, 0.1ns uncertainty
- seq_samp_clk: 50ns period, 0.1ns uncertainty  
- seq_comp_clk: 20ns period, 0.1ns uncertainty
- seq_update_clk: 40ns period, 0.1ns uncertainty
- Clock groups: Asynchronous between all domains

Clock buffers inserted: 31 BUFFD2 cells across 7 clock networks

# Routing Grid Configuration

Critical debugging step to resolve pin access errors:

- Problem: Empty TRACKS_INFO_FILE causing routing grid alignment issues
- Solution: Created platforms/tsmc65/tracks.info based on TSMC65 LEF specifications
- Track definitions extracted from tcbn65lp_9lmT2.lef:
  - M1: Y-direction tracks at 0.000µm offset, 0.200µm pitch
  - M2: X-direction tracks at 0.100µm offset, 0.200µm pitch
  - M3: Y-direction tracks at 0.000µm offset, 0.200µm pitch
  - M4-M9: Alternating X/Y directions with appropriate offsets and pitches

Manufacturing grid alignment: 0.005µm (5nm)
Database units: 2000 DB units per micron

# RC Extraction Configuration

Updated platforms/tsmc65/setRC.tcl for proper OpenROAD compatibility:
- Fixed format from set_layer_rc to set_wire_rc
- Added TSMC65-appropriate resistance/capacitance values:
  - M1: 50mΩ/square, 60fF/µm
  - M2-M9: Scaled values based on metal layer characteristics
- Corrected via definitions to match TSMC65 naming conventions

# Library Mismatch Resolution

Critical discovery: GDS file used LVT (Low Voltage Threshold) library variants while LEF/Liberty files used standard library variants.

**Problem Identified:**
- GDS file (`tcbn65lplvt.gds`) contains cells like `AN2D4LVT`, `BUFFD8LVT`, `CKBD16LVT`
- Original configuration used standard library files with cells like `AN2D4`, `BUFFD8`, `CKBD16`
- This mismatch caused routing failures and pin access errors

**Solution Applied:**
Updated platforms/tsmc65/config.mk to use matching LVT library files:
- `LIB_FILES = /eda/kits/TSMC/65LP/2024/digital/Front_End/timing_power_noise/NLDM/tcbn65lplvt_220a/tcbn65lplvtwc.lib`
- `LEF_FILES = /eda/kits/TSMC/65LP/2024/digital/Back_End/lef/tcbn65lplvt_200a/lef/tcbn65lplvt_9lmT2.lef`
- `GDS_FILES = /eda/kits/TSMC/65LP/2024/digital/Back_End/gds/tcbn65lplvt_200a/tcbn65lplvt.gds`

Updated all cell references to LVT variants:
- Clock buffers: `BUFFD2LVT`, `BUFFD4LVT`, `BUFFD8LVT`, etc.
- Tie cells: `TIELLVT`, `TIEHLVT` instead of `TIEL`, `TIEH`
- Fill cells: `FILL*LVT` pattern
- Tap cells: `GFILLLVT` instead of `GFILL`

# Pin Access Analysis for Multi-Width Cells

**Key Insight:** TSMC65LP library contains cells of different widths that affect pin access:

- **Single-width cells** (1.200µm): `AN2D0LVT` - pins at Y ≈ 0.285-1.490
- **Double-width cells** (2.400µm): `AN2D4LVT` - pins at Y ≈ 0.435-1.290
- **Larger cells**: `BUFFD8LVT` (3.200µm), `CKBD16LVT` (5.600µm)

Pin coordinates from failing cells:
- `AN2D4LVT Z pin`: X=1.390-2.100, Y=0.435-1.290
- `BUFFD8LVT Z pin`: X=2.250-2.850, Y=0.325-1.475  
- `CKBD16LVT Z pin`: X=3.450-5.305, Y=0.325-1.475

Standard cell height: 1.800µm (consistent across all cells)
Manufacturing grid: 0.005µm (5nm precision)

# OpenROAD Flow Usage

## Preferred Approach: Use OpenROAD Flow Scripts (ORFS)

**Always use make targets** instead of calling `openroad` directly:
- `DESIGN_CONFIG=designs/tsmc65/adc/config.mk make gui_cts` loads complete design context (libraries, timing, constraints)
- `openroad -gui results/tsmc65/adc/base/4_cts.odb` only loads geometry without required technology files
- ORFS automatically handles library loading, timing setup, and proper design environment configuration

# Flow w/o ORFS
- The file OpenROAD-flow-scripts/tools/OpenROAD/test/flow.tcl provides a self contained flow, seperate from ORFS

# OpenROAD for analog design:
- PH Wei 2021 suggested not to try to manually control placement
    - But to instead randomly change the 'net weight' (is this just for routing, or also placement??)
    - They did split specific blocks in half though, to then ensure a mirrored layout
    - StemCell mapper decomposes netlists into 
    - .lef files are still useful, but .lib files aren't useful for this flow
    - StemCells are: LEF (FEOL+2BEOL layers) + GDS layout + CDL netlist
- Q: What does the 'netlist' that openroad acts on (post synthesis) even look like? Is it veriog, or something else?
- Q: Does OpenRoad have net weighting, manual positioning, ECO/swapping, and wire widths commands? I think these are all necessary



# Clock tree synthesis:
Clock Network Hierarchy

My 4 Input Clocks:
- seq_init
- seq_samp
- seq_comp
- seq_update

Pass through 6 Clock Gates in clkgate.v:
- seq_init + en_init → clk_init (98 sinks)
- seq_samp + en_samp_p → clk_samp_p (no sinks found in CTS)
- seq_samp + en_samp_n → clk_samp_n (no sinks found in CTS)
- seq_comp + en_comp → clk_comp (no sinks found in CTS)
- seq_update + en_update_p → clk_update_p (32 sinks)
- seq_update + en_update_n → clk_update_n (32 sinks)

Plus 2 original inputs recognized as clocks:
- seq_samp (2 sinks) - drives the sampling clock gates
- seq_update (2 sinks) - drives the update clock gates

Plus 17 Internal Clock Nets (_077_, _210_, etc.):
These are derived clocks created during synthesis when:
1. Logic optimization splits or duplicates clock paths
2. Clock gating logic gets transformed into complex logic trees
3. The SAR logic's complex always @(posedge clk_update) with internal if (clk_init) creates mixed clock domains

What are "Sinks" and "Clusters"?

Sinks = Clock endpoints (flip-flop clock pins, latch enable pins)
- clk_init → 98 sinks (all the flip-flops in both salogic_p and salogic_n that reset)
- clk_update_p → 32 sinks (16 dac_state + 16 dac_cycle registers in salogic_p)
- clk_update_n → 32 sinks (16 dac_state + 16 dac_cycle registers in salogic_n)
- _210_ → 16 sinks (likely one of the SAR logic register arrays)
- _077_ → 16 sinks (likely the other SAR logic register array)


Key Files for Clock Network Analysis:

1. Clock Tree Synthesis Log (Most Detailed)

File: /flow/logs/tsmc65/adc/base/4_1_cts.log
- Shows all 23 clock nets with sink counts
- Details H-Tree topology generation
- Sink clustering and placement regions
- Buffer insertion statistics

2. CTS Final Report

File: /flow/reports/tsmc65/adc/base/4_cts_final.rpt
- Clock skew analysis between domains
- Setup/hold timing paths showing clock buffer chains
- Power consumption breakdown (41.6% from clock network!)
- Example path: seq_update → clkbuf_0_seq_update → clkgate → clk_update_p → clkbuf_0_clk_update_p

3. Clock Visualization Images

Files: /flow/reports/tsmc65/adc/base/cts_*.webp
- cts_seq_init.webp / cts_seq_init_layout.webp
- cts_seq_samp.webp / cts_seq_samp_layout.webp
- cts_seq_comp.webp / cts_seq_comp_layout.webp
- cts_seq_update.webp / cts_seq_update_layout.webp
- final_clocks.webp - shows all clock trees together

4. Synthesized Netlist

File: /flow/results/tsmc65/adc/base/1_synth.v
- Shows actual clock gate instances and connections
- Maps input clocks to internal nets (seq_update → clk_update_p)

5. OpenROAD Database Files

Files: /flow/results/tsmc65/adc/base/*.odb
- 4_1_cts.odb - Database after clock tree synthesis
- Can open in OpenROAD GUI to visualize clock networks interactively

From the 4_cts_final.rpt, you can see the clock buffer hierarchy:
seq_update → clkbuf_0_seq_update → clkbuf_1_1__f_seq_update → 
clkgate.clkgate_update_p.clkgate → clk_update_p → 
clkbuf_0_clk_update_p → clkbuf_2_3__f_clk_update_p

This shows why you have so many buffers - each of the 23 clock nets gets its own H-tree with multiple levels of
buffering for timing balance.

# Automatic Pad Ring Placement

OpenROAD provides comprehensive automation for pad ring cell placement through the **PAD module** (based on ICeWall). The key command for automatic placement is:

## `place_pads` - Automatic Pad Placement

```tcl
place_pads -row row_name pads
```

**Features:**
- Places pads into IO rows in specified order
- Automatically aligns pads with bumps when bump array is placed
- Uniform distribution when no bumps are present
- Preserves pad order while optimizing alignment

**Example usage:**
```tcl
place_pads -row IO_SOUTH u_reset.u_in u_reset.u_out
place_pads -row IO_NORTH clk pad_vdd pad_vss
place_pads -row IO_EAST data_bus[7:0]
place_pads -row IO_WEST control_signals
```

## Complete Automated Pad Ring Flow

1. **`make_io_sites`** - Define IO sites for pad placement
2. **`place_corners`** - Automatically place corner cells  
3. **`place_pads`** - Automatically place pads in rows
4. **`place_io_fill`** - Place IO filler cells
5. **`connect_by_abutment`** - Connect ring signals

**Additional automation:**
- **`place_bondpad`** - Automatically place wirebond pads over IO cells
- **`make_io_bump_array`** - Create bump arrays automatically
- **`assign_io_bump`** - Assign nets to bumps

The PAD module handles bump-to-pad alignment, uniform spacing, and maintains proper pad ordering automatically.

# Hierarchical Design Flow with Hard Macros

OpenROAD Flow Scripts provides a **hierarchical block-based flow** for placing and routing sub-modules independently before top-level integration.

## BLOCKS Variable Configuration

Define sub-modules using the `BLOCKS` variable in your top-level `config.mk`:

```make
# In your top-level design config.mk
export DESIGN_NICKNAME = my_soc_design
export BLOCKS = cpu_core memory_controller dsp_engine io_interface
```

## Directory Structure

```
flow/designs/PLATFORM/my_soc_design/
├── config.mk              # Top-level configuration
├── cpu_core/
│   └── config.mk           # Sub-module configuration
├── memory_controller/
│   └── config.mk           # Sub-module configuration
├── dsp_engine/
│   └── config.mk           # Sub-module configuration
└── io_interface/
    └── config.mk           # Sub-module configuration
```

## Automatic File Generation

The flow automatically generates and links these files for each block:
- **LEF files**: `${block}.lef` (physical view)
- **Liberty files**: `${block}_typ.lib`, `${block}_fast.lib`, `${block}_slow.lib` (timing)
- **GDS files**: `6_final.gds` (layout)

## Build Process

```bash
# Build all sub-modules first (place & route each block)
make build_macros

# Then build top-level with hard macros
make
```

## Key Variables for Hard Macro Integration

The flow (might??) automatically populates these variables for the top-level:

```make
# Automatically populated from BLOCKS
ADDITIONAL_LEFS += $(BLOCK_LEFS)      # Physical views
ADDITIONAL_LIBS += $(BLOCK_TYP_LIBS)  # Timing models  
ADDITIONAL_GDS += $(BLOCK_GDS)        # Layout files
```

## Macro Placement Control

Control hard macro placement using:

```make
# Manual placement file (coordinates)
export MACRO_PLACEMENT = $(DESIGN_HOME)/macro_placement.cfg

# Or TCL-based placement (more flexible)
export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/macro_placement.tcl
```

## Example from mock-array design:

```make
# designs/asap7/mock-array/config.mk
export BLOCKS = Element

ifneq ($(BLOCKS),)
  export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/asap7/mock-array/macro-placement.tcl
  export PDN_TCL = $(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl
endif
```

## Complete Hierarchical Workflow

1. **Design sub-modules** with individual `config.mk` files
2. **Set BLOCKS variable** in top-level config
3. **Run `make build_macros`** to generate hard macros (full P&R each block)
4. **Configure macro placement** (optional - can use automatic placement)
5. **Run `make`** for top-level integration

**Benefits:**
- **Independent optimization** of each block
- **Controlled timing closure** at block level
- **Parallel development** of different blocks
- **Block reuse** across multiple top-levels
- **Reduced complexity** through hierarchy
- **Better convergence** for large designs



# Routing Issues

## Antenna Properties
My macro pins are missing:
- ANTENNADIFFAREA (for diffusion area)
- ANTENNAGATEAREA (for gate area)

These are required by OpenROAD for:
1. Pin access point generation
2. Antenna violation analysis
3. Proper routing connectivity

## Caparray Pin Guide Coverage Problems

The OpenROAD detailed router fails to route the caparray (capacitor array) pins in our mixed-signal SAR ADC design. The routing consistently fails with guide coverage errors for all caparray pins.

### Error Messages

The main errors we see during detailed routing:

```
[WARNING DRT-0215] Pin caparray_p/cap_botplate_main[0] not covered by guide.
[WARNING DRT-0215] Pin caparray_p/cap_botplate_diff[0] not covered by guide.
[WARNING DRT-0215] Pin caparray_n/cap_botplate_main[0] not covered by guide.
[ERROR DRT-0218] Guide is not connected to design.
```

This pattern repeats for all 32 bottom plate pins (16 main + 16 diff) across both caparray_p and caparray_n instances, plus the 4 top plate pins.

The routing fails immediately in the first iteration of detailed routing, even though:
- Global routing completes successfully (520 nets routed)
- Pin access generation works fine (#macroNoAp = 0)

### Things We Investigated and Fixed

#### 1. Pin Width Issues ✅ FIXED
**Problem**: Original caparray pins were 0.18μm wide, which is below the M4 spacing table breakpoint of 0.20μm.

**What we tried**: Increased all caparray pin widths from 0.18μm to 0.20μm while keeping the same center positions.

**Result**: This fixed the pin access point generation (no more "Access Points: 0 items" errors), but detailed routing still fails with guide coverage issues.

#### 2. Routing Track Alignment ✅ FIXED  
**Problem**: Pin centers weren't aligned to the M4 routing grid.

**What we tried**: Aligned all pin centers to M4 vertical tracks (0.1, 0.3, 0.5, 0.7μm spacing).

**Result**: Pins are now properly quantized to the routing grid, but guide coverage problems persist.

#### 3. Pin Area Violations ✅ FIXED
**Problem**: Some pins had area violations due to small dimensions.

**What we tried**: Doubled the height of pins that were too small to meet minimum area requirements.

**Result**: No more area violations, but still no guide coverage.

#### 4. Routing Layer Constraints ❌ NO EFFECT
**Problem**: Maybe the router couldn't reach M4 pins with limited routing layers.

**What we tried**: Changed MAX_ROUTING_LAYER from M4 to M6 to give more routing resources.

**Result**: Global router still only used up to M4 anyway. No change in behavior.

#### 5. Macro Placement and GCell Grid ❌ NO EFFECT  
**Problem**: Maybe the caparray pins fall in bad locations relative to the 6μm global routing grid.

**What we tried**: Analyzed where the pins land relative to GCell boundaries. Bottom pins are at Y=3.44μm (GCell 0), top pins at Y=56.28μm (GCell 9).

**Result**: Pin locations seem reasonable relative to the grid. The issue appears deeper.

#### 6. LEF File OBS Rectangles ❌ NO EFFECT
**Problem**: Maybe routing obstructions in the LEF file were blocking guide generation.

**What we tried**: Restored original OBS rectangle coordinates thinking they might affect routing.

**Result**: No change in routing behavior with different OBS coordinates.

### Current Theory: Bottom-Up Pin Access

The most likely issue is that our mixed-signal design has an unusual pin access pattern. The caparray pins are on M4, but they need to be accessed from below (M1-M3 standard cell routing). Most OpenROAD designs access pins from above (higher metal layers).

This "bottom-up" access pattern might be confusing the detailed router's guide generation algorithm.

### Debug Commands for Investigation

The following debug commands should be run in the OpenROAD GUI to understand what's happening:

```tcl
# Basic diagnostic - try to get guide coverage file before crash
detailed_route -output_drc ./debug_drc.rpt -output_guide_coverage ./debug_coverage.csv -droute_end_iter 1 -verbose 2

# Force via access from M3 layer  
detailed_route -via_access_layer M3 -output_guide_coverage ./coverage_via_m3.csv -droute_end_iter 1

# Via-in-pin constraints for M4 pins
detailed_route -via_in_pin_bottom_layer M3 -via_in_pin_top_layer M4 -output_guide_coverage ./coverage_via_in_pin.csv -droute_end_iter 1

# Skip pin access entirely (nuclear option)
detailed_route -no_pin_access -output_guide_coverage ./coverage_no_pa.csv -droute_end_iter 1
```

The guide coverage CSV file should tell us exactly which pins are missing coverage and potentially why.

### Root Cause Discovery: COVER vs BLOCK Instance Types

**Key Finding**: The caparray instances are classified as type "COVER" rather than "BLOCK", which explains why they weren't placed through the normal macro placement flow.

From `flow/logs/tsmc65/adc/base/6_report.log`:
```
Cell type report:                       Count       Area
  Macro                                     3     428.55
  Cover                                     2    1951.84
```

And from `flow/logs/tsmc65/adc/base/5_1_grt.log`:
```
[INFO GRT-0118] Macros: 3
[WARNING GRT-0034] Net connected to instance of class COVER added for routing.
[WARNING GRT-0034] Net connected to instance of class COVER added for routing.
[WARNING GRT-0034] Net connected to instance of class COVER added for routing.
...
(67+ identical warnings for COVER instances)
```

**Analysis**: 
- The `find_macros` function only detects instances of type "BLOCK" for macro placement
- Caparray instances are type "COVER" (appropriate for metal-only structures that don't block FEOL)
- This explains why caparrays don't appear in the `2_2_floorplan_macro.tcl` output file
- The global router generates warnings when handling COVER instances
- The detailed router may not properly handle pin access for COVER type instances in mixed-signal designs

**Implication**: The fundamental issue may be that OpenROAD's detailed routing algorithms are not optimized for the "bottom-up" pin access pattern where M4 COVER instances need to be accessed from M1-M3 standard cells.

### Status

Successfully fixed all the pin geometry issues (width, alignment, area), but the fundamental guide coverage problem remains. The issue appears to be in OpenROAD's detailed routing algorithm when dealing with COVER type instances in mixed-signal designs, particularly the unusual bottom-up pin access pattern.

Next steps are to use the debug commands above to get more detailed information about why guides aren't reaching the caparray pins.

---

## FRIDA Chip Architecture Summary

### Overview
**FRIDA** is a 1mm × 1mm mixed-signal SAR ADC array chip implemented using TSMC65nm technology through OpenROAD Flow Scripts (ORFS). The design features 16 ADC instances arranged in a 4×4 grid, controlled by a 1280-bit SPI register, with a complete pad ring for external interfacing.

### Physical Architecture

#### Die Layout
- **Die Size**: 1000μm × 1000μm (1mm²)
- **Core Area**: 600μm × 600μm (centered, 200μm margin for pad ring)
- **ADC Grid**: 4×4 array in upper portion of core
  - Each ADC: 60μm × 60μm 
  - Spacing: 100μm between ADCs
- **Support Logic**: SPI register and multiplexer in remaining core area

#### Pad Ring (22 Total Pads)
| Pad Type | Count | Purpose |
|----------|--------|---------|
| LVDS_RX_CUP_pad | 4 | Sequencing clocks (seq_init, seq_samp, seq_cmp, seq_logic) |
| LVDS_TX_CUP_pad | 1 | Comparator data output (comp_out_p/n) |
| CMOS_IO_CUP_pad | 5 | SPI interface + reset (spi_sclk, spi_sdi, spi_sdo, spi_cs_b, reset_b) |
| PASSIVE_CUP_pad | 1 | Analog input (vin_p/vin_n differential) |
| POWER_CUP_pad | 4 | Power supplies (vdd_a, vdd_d, vdd_io, vdd_dac) |
| GROUND_CUP_pad | 4 | Ground supplies (vss_a, vss_d, vss_io, vss_dac) |

### Digital Architecture

#### Hierarchical Design Structure
```
frida/ (top-level)
├── config.mk (1mm² die, hierarchical flow)
├── constraint.sdc (timing constraints)
├── io.tcl (pad placement)
└── adc/ (hardened block)
    ├── config.mk (60μm² core, analog macros)
    ├── constraint.sdc (ADC timing)
    ├── io.tcl (ADC I/O)
    ├── macro_placement.cfg (analog macro positions)
    └── pdn.tcl (power distribution)
```

#### Verilog Module Hierarchy
- **`frida.v`**: Top-level integration
  - 16 ADC instances (`adc_array[0:15].adc_inst`)
  - SPI register instance (`spi_reg`)
  - Comparator multiplexer (`comp_mux`)
  - Complete pad ring instantiation
- **`spi_register.v`**: 1280-bit shift register
- **`compmux.v`**: 16:1 combinational multiplexer
- **`adc.v`**: Individual ADC (hardened from lower level)

#### Signal Distribution Architecture

**SPI Register Mapping (1280 bits total)**:
```
Bits [0:1135]     → 16 ADCs × 71 control signals each
Bits [1136:1139]  → 4-bit comparator mux selection  
Bits [1140:1279]  → 140 spare bits for future use
```

**Per-ADC Control Signals (71 bits each)**:
```
adc_XX_en_init        → Enable initialization (1 bit)
adc_XX_en_samp_p/n    → Enable sampling pos/neg (2 bits)  
adc_XX_en_comp        → Enable comparator (1 bit)
adc_XX_en_update      → Enable update logic (1 bit)
adc_XX_dac_mode       → DAC mode control (1 bit)
adc_XX_dac_astate_p   → DAC A state positive [15:0] (16 bits)
adc_XX_dac_bstate_p   → DAC B state positive [15:0] (16 bits)
adc_XX_dac_astate_n   → DAC A state negative [15:0] (16 bits)
adc_XX_dac_bstate_n   → DAC B state negative [15:0] (16 bits)
adc_XX_dac_diffcaps   → Differential capacitor mode (1 bit)
Total: 71 bits × 16 ADCs = 1136 bits
```

#### Clock Distribution
- **seq_init**: DAC initialization sequencing (100ns period)
- **seq_samp**: Sample phase control (10ns period) 
- **seq_cmp**: Comparator timing (5ns period)
- **seq_logic**: SAR logic timing (20ns period, also drives SPI register)
- **spi_sclk**: SPI configuration clock (100ns period, 10 MHz)

All sequencing clocks have balanced skew constraints (±0.1ns) for simultaneous operation across 16 ADCs.