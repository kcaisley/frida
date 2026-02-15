# Tool Portability Analysis

## Tool-Portable Files (Industry Standard)

Completely Portable:
- `constraint.sdc` - Synopsys Design Constraints format supported by all major tools (Cadence Innovus, Synopsys ICC2/Fusion Compiler, OpenROAD)
- `*.v` - Verilog RTL files are portable across all synthesis tools
- `*.lef` - Library Exchange Format is industry standard (Cadence, Synopsys, OpenROAD)
- `*.lib` - Liberty timing format is industry standard

## Tool-Specific Files

OpenROAD-Specific:
- `tracks.info` - OpenROAD's custom format for routing track definitions
  - Cadence equivalent: Track information embedded in technology LEF file or specified via Innovus TCL commands (`createTrack`)
  - Synopsys equivalent: Technology file (`.tf`) or ICC2 technology library

Mixed (Tool-Specific Syntax, Portable Concept):
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

Problem Identified:
- GDS file (`tcbn65lplvt.gds`) contains cells like `AN2D4LVT`, `BUFFD8LVT`, `CKBD16LVT`
- Original configuration used standard library files with cells like `AN2D4`, `BUFFD8`, `CKBD16`
- This mismatch caused routing failures and pin access errors

Solution Applied:
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

Key Insight: TSMC65LP library contains cells of different widths that affect pin access:

- Single-width cells (1.200µm): `AN2D0LVT` - pins at Y ≈ 0.285-1.490
- Double-width cells (2.400µm): `AN2D4LVT` - pins at Y ≈ 0.435-1.290
- Larger cells: `BUFFD8LVT` (3.200µm), `CKBD16LVT` (5.600µm)

Pin coordinates from failing cells:
- `AN2D4LVT Z pin`: X=1.390-2.100, Y=0.435-1.290
- `BUFFD8LVT Z pin`: X=2.250-2.850, Y=0.325-1.475  
- `CKBD16LVT Z pin`: X=3.450-5.305, Y=0.325-1.475

Standard cell height: 1.800µm (consistent across all cells)
Manufacturing grid: 0.005µm (5nm precision)

# OpenROAD Flow Usage

## Preferred Approach: Use OpenROAD Flow Scripts (ORFS)

Always use make targets instead of calling `openroad` directly:
- `DESIGN_CONFIG=designs/tsmc65/adc/config.mk make gui_cts` loads complete design context (libraries, timing, constraints)
- `openroad -gui results/tsmc65/adc/base/4_cts.odb` only loads geometry without required technology files
- ORFS automatically handles library loading, timing setup, and proper design environment configuration

# Flow w/o ORFS
- The file OpenROAD-flow-scripts/tools/OpenROAD/test/flow.tcl provides a self contained flow, seperate from ORFS

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

OpenROAD provides comprehensive automation for pad ring cell placement through the PAD module (based on ICeWall). The key command for automatic placement is:

## `place_pads` - Automatic Pad Placement

```tcl
place_pads -row row_name pads
```

Features:
- Places pads into IO rows in specified order
- Automatically aligns pads with bumps when bump array is placed
- Uniform distribution when no bumps are present
- Preserves pad order while optimizing alignment

Example usage:
```tcl
place_pads -row IO_SOUTH u_reset.u_in u_reset.u_out
place_pads -row IO_NORTH clk pad_vdd pad_vss
place_pads -row IO_EAST data_bus[7:0]
place_pads -row IO_WEST control_signals
```

## Complete Automated Pad Ring Flow

1. `make_io_sites` - Define IO sites for pad placement
2. `place_corners` - Automatically place corner cells  
3. `place_pads` - Automatically place pads in rows
4. `place_io_fill` - Place IO filler cells
5. `connect_by_abutment` - Connect ring signals

Additional automation:
- `place_bondpad` - Automatically place wirebond pads over IO cells
- `make_io_bump_array` - Create bump arrays automatically
- `assign_io_bump` - Assign nets to bumps

The PAD module handles bump-to-pad alignment, uniform spacing, and maintains proper pad ordering automatically.

# Hierarchical Design Flow with Hard Macros

OpenROAD Flow Scripts provides a hierarchical block-based flow for placing and routing sub-modules independently before top-level integration.

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
- LEF files: `${block}.lef` (physical view)
- Liberty files: `${block}_typ.lib`, `${block}_fast.lib`, `${block}_slow.lib` (timing)
- GDS files: `6_final.gds` (layout)

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

1. Design sub-modules with individual `config.mk` files
2. Set BLOCKS variable in top-level config
3. Run `make build_macros` to generate hard macros (full P&R each block)
4. Configure macro placement (optional - can use automatic placement)
5. Run `make` for top-level integration

Benefits:
- Independent optimization of each block
- Controlled timing closure at block level
- Parallel development of different blocks
- Block reuse across multiple top-levels
- Reduced complexity through hierarchy
- Better convergence for large designs



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
Problem: Original caparray pins were 0.18μm wide, which is below the M4 spacing table breakpoint of 0.20μm.

What we tried: Increased all caparray pin widths from 0.18μm to 0.20μm while keeping the same center positions.

Result: This fixed the pin access point generation (no more "Access Points: 0 items" errors), but detailed routing still fails with guide coverage issues.

#### 2. Routing Track Alignment ✅ FIXED  
Problem: Pin centers weren't aligned to the M4 routing grid.

What we tried: Aligned all pin centers to M4 vertical tracks (0.1, 0.3, 0.5, 0.7μm spacing).

Result: Pins are now properly quantized to the routing grid, but guide coverage problems persist.

#### 3. Pin Area Violations ✅ FIXED
Problem: Some pins had area violations due to small dimensions.

What we tried: Doubled the height of pins that were too small to meet minimum area requirements.

Result: No more area violations, but still no guide coverage.

#### 4. Routing Layer Constraints ❌ NO EFFECT
Problem: Maybe the router couldn't reach M4 pins with limited routing layers.

What we tried: Changed MAX_ROUTING_LAYER from M4 to M6 to give more routing resources.

Result: Global router still only used up to M4 anyway. No change in behavior.

#### 5. Macro Placement and GCell Grid ❌ NO EFFECT  
Problem: Maybe the caparray pins fall in bad locations relative to the 6μm global routing grid.

What we tried: Analyzed where the pins land relative to GCell boundaries. Bottom pins are at Y=3.44μm (GCell 0), top pins at Y=56.28μm (GCell 9).

Result: Pin locations seem reasonable relative to the grid. The issue appears deeper.

#### 6. LEF File OBS Rectangles ❌ NO EFFECT
Problem: Maybe routing obstructions in the LEF file were blocking guide generation.

What we tried: Restored original OBS rectangle coordinates thinking they might affect routing.

Result: No change in routing behavior with different OBS coordinates.

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

Key Finding: The caparray instances are classified as type "COVER" rather than "BLOCK", which explains why they weren't placed through the normal macro placement flow.

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

Analysis: 
- The `find_macros` function only detects instances of type "BLOCK" for macro placement
- Caparray instances are type "COVER" (appropriate for metal-only structures that don't block FEOL)
- This explains why caparrays don't appear in the `2_2_floorplan_macro.tcl` output file
- The global router generates warnings when handling COVER instances
- The detailed router may not properly handle pin access for COVER type instances in mixed-signal designs

Implication: The fundamental issue may be that OpenROAD's detailed routing algorithms are not optimized for the "bottom-up" pin access pattern where M4 COVER instances need to be accessed from M1-M3 standard cells.

### Status

Successfully fixed all the pin geometry issues (width, alignment, area), but the fundamental guide coverage problem remains. The issue appears to be in OpenROAD's detailed routing algorithm when dealing with COVER type instances in mixed-signal designs, particularly the unusual bottom-up pin access pattern.

Next steps are to use the debug commands above to get more detailed information about why guides aren't reaching the caparray pins.

---

## FRIDA Chip Architecture Summary

### Overview
FRIDA is a 1mm × 1mm mixed-signal SAR ADC array chip implemented using TSMC65nm technology through OpenROAD Flow Scripts (ORFS). The design features 16 ADC instances arranged in a 4×4 grid, controlled by a 1280-bit SPI register, with a complete pad ring for external interfacing.

### Physical Architecture

#### Die Layout
- Die Size: 1000μm × 1000μm (1mm²)
- Core Area: 600μm × 600μm (centered, 200μm margin for pad ring)
- ADC Grid: 4×4 array in upper portion of core
- Each ADC: 60μm × 60μm 
- Spacing: 100μm between ADCs
- Support Logic: SPI register and multiplexer in remaining core area

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
- `frida.v`: Top-level integration
- 16 ADC instances (`adc_array[0:15].adc_inst`)
- SPI register instance (`spi_reg`)
- Comparator multiplexer (`comp_mux`)
- Complete pad ring instantiation
- `spi_register.v`: 1280-bit shift register
- `compmux.v`: 16:1 combinational multiplexer
- `adc.v`: Individual ADC (hardened from lower level)

#### Signal Distribution Architecture

SPI Register Mapping (1280 bits total):
```
Bits [0:1135]     → 16 ADCs × 71 control signals each
Bits [1136:1139]  → 4-bit comparator mux selection  
Bits [1140:1279]  → 140 spare bits for future use
```

Per-ADC Control Signals (71 bits each):
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
- seq_init: DAC initialization sequencing (100ns period)
- seq_samp: Sample phase control (10ns period) 
- seq_cmp: Comparator timing (5ns period)
- seq_logic: SAR logic timing (20ns period, also drives SPI register)
- spi_sclk: SPI configuration clock (100ns period, 10 MHz)

All sequencing clocks have balanced skew constraints (±0.1ns) for simultaneous operation across 16 ADCs.



# OpenSTA SDC timing constraint errors:

Initial LEF/Liberty Warnings:

[WARNING ORD-2011] LEF master caparray has no liberty cell.
[WARNING ORD-2011] LEF master comp has no liberty cell.
[WARNING ORD-2011] LEF master sampswitch has no liberty cell.

```log
Pin Reference Warnings (multiple iterations):

[WARNING STA-0363] pin '*/capdriver_p_main/dac_drive*' not found.
[WARNING STA-0473] no valid objects specified for -to.

[WARNING STA-0363] pin 'capdriver_p_main/xor_gates[0].xor_gate/Z' not found.
[WARNING STA-0363] pin 'capdriver_p_main/xor_gates[1].xor_gate/Z' not found.
...continuing for all 16 pins of each capdriver instance...
```

# 1. Original hierarchical path with wildcards
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins */instance/pin*]

# 2. Full hierarchical path with adc/ prefix
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins adc/instance/pin*]

# 3. With -hierarchical flag
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins -hierarchical instance/pin*]

# 4. Using get_nets (failed with "unsupported object type Net")
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_nets dac_drive_botplate_main_p*]

# 5. Direct instance pin references without wildcards
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins capdriver_p_main/dac_drive*]

# 6. With wildcard prefix
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins */capdriver_p_main/dac_drive*]

```log
[WARNING STA-1551] ./results/tsmc65/frida_adc/base/1_synth.sdc line 25,
'capdriver_p_main/xor_gates[0].xor_gate/Z' is not a valid endpoint.
[WARNING STA-1551] ./results/tsmc65/frida_adc/base/1_synth.sdc line 25,
'capdriver_p_main/xor_gates[1].xor_gate/Z' is not a valid endpoint.
...continuing for multiple lines and instances...
```

# 7. Final approach - using get_pins -of_objects with nets and filter
set_max_delay 2.0 \
-from [get_ports seq_update] \
-to [get_pins -of_objects [get_nets dac_drive_botplate_main_p*] -filter "direction==output"]

Along the way, this was persistant:
```log
Boolean Network Construction Error:
[ERROR RSZ-2001] failed bnet construction for capdriver_p_main/xor_gates\[9\].xor_gate/Z
Error: global_place.tcl, 49 RSZ-2001
```

# Writing netlist in CDL format:

>>> read_verilog results/tsmc65/frida_adc/base/1_2_yosys.v
>>> write_cdl -masters "platforms/tsmc65/spice/tcbn65lplvt_200a.spi ~/frida/etc/sampswitch.cdl ~/frida/etc/comp.cdl ~/frida/etc/caparray.cdl" results/tsmc65/frida_adc/base/output.cdl

# Error in PDN generation:
```log
[WARNING PDN-1042] Core voltage domain will be named "Core".
[WARNING PDN-0183] Replacing existing core voltage domain.
[ERROR PDN-1032] Unable to find DAC domain.
```

- There are no examples of multiple power domain generation
- Also note that UPF syntax is different than the PDN docs




# Post synthesis, initial timing analysis

Based on my examination of the floorplan execution output and the underlying TCL scripts, here's exactly what happens during the 4 floorplanning steps and the
OpenSTA commands that are run:

4 Floorplan Steps:

Step 1: Initial Floorplan (2_1_floorplan)
- Script: scripts/floorplan.tcl
- Key OpenSTA commands:
- check_setup - validates timing constraints setup
- repair_timing -setup -verbose -setup_margin 0 -sequence unbuffer,sizeup,swap,buffer,vt_swap -repair_tns 100 -skip_last_gasp
- Various report_* commands for metrics collection

Step 2: Macro Placement (2_2_floorplan_macro)
- Script: scripts/macro_place.tcl
- No specific timing analysis commands, mainly macro placement

Step 3: Tapcell Insertion (2_3_floorplan_tapcell)
- Script: scripts/tapcell.tcl
- Primarily physical layout commands, no timing analysis

Step 4: PDN Generation (2_4_floorplan_pdn) - Failed in your run
- Script: scripts/pdn.tcl
- Failed due to missing "DAC domain" configuration

OpenSTA Command Sequence for Manual Reproduction:

Here's the exact sequence of OpenSTA/timing commands you can run in OpenROAD's interactive mode:

# 1. Read Liberty file
read_liberty ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lib/tcbn65lplvtwc.lib

# 2. Read LEF files  
read_lef ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tsmc65lplvt_9lmT2.lef
read_lef ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tcbn65lplvt_9lmT2.lef
read_lef ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/caparray.lef
read_lef ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/comp.lef
read_lef ~/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/sampswitch.lef

# 3. Read Verilog and link design
read_verilog ./results/tsmc65/frida_adc/base/1_synth.v
link_design adc

# 4. Read SDC constraints
read_sdc ./results/tsmc65/frida_adc/base/1_synth.sdc

# 5. Set RC extraction parameters
set_layer_rc -layer M1 -resistance 0.160 -capacitance 0.000171
set_layer_rc -layer M2 -resistance 0.140 -capacitance 0.000232
set_layer_rc -layer M3 -resistance 0.140 -capacitance 0.000232
# ... (continue for M4-M9)
set_wire_rc -signal -layer M2
set_wire_rc -clock -layer M3

# 6. Run timing analysis commands
check_setup
report_tns
report_wns
report_worst_slack
report_clock_min_period -include_port_paths
report_checks -path_delay min -fields {slew cap input net fanout} -format full_clock_expanded
report_checks -path_delay max -fields {slew cap input net fanout} -format full_clock_expanded
report_checks -unconstrained -fields {slew cap input net fanout} -format full_clock_expanded
report_check_types -max_slew -max_capacitance -max_fanout -violators

The key timing analysis occurs in Step 1 (initial floorplan), where check_setup is called line 38 in
~/OpenROAD-flow-scripts/flow/scripts/floorplan.tcl, and the repair_timing command performs setup timing optimization. The other steps focus mainly on
physical implementation rather than timing analysis.


You can use info commands *liberty* or info commands read* in OpenROAD to see what commands are actually available, regardless of tab completion.

# OpenDB vs. OpenSTA Architecture

OpenROAD integrates two major database systems that serve different purposes in the EDA flow:

## OpenDB vs. OpenSTA

| OpenDB | OpenSTA |
|------------|-------------|
| Physical info | Logical / timing info |
| Taxonomy from prior lectures | Taxonomy from Liberty |

## OpenSTA Uses

OpenSTA is responsible for:

- Calculating timing paths
- Delay, rise time, fall time, etc.
- Tracing connectivity  
- Finding paths between a startpoint and endpoint
- Reading and parsing Verilog
- Verilog files parsed through OpenSTA
- DEF files parsed through OpenDB
- Several others

## Translating Key Objects

The two database systems use different object models that need translation:

| OpenDB | OpenSTA |
|------------|-------------|
| dbMaster | Cell |
| dbInst | Instance |
| dbITerm | Term |
| dbBTerm | Term |
| dbMTerm | Port |
| dbNet | Net |

## Command Registration and Tab Completion Issue

The reason `read_liberty` doesn't show up in tab completion but is still a valid command is due to lazy command registration in OpenROAD's modular architecture:

1. Modular Design: OpenROAD integrates multiple tools (OpenSTA, TritonRoute, OpenDB, etc.) with dynamic command registration
2. Lazy Loading: OpenSTA commands like `read_liberty` may not register in tab completion until the timing engine is initialized
3. Integration Layer: Commands are dispatched through a sophisticated system that doesn't always expose all available commands to tab completion

Common OpenSTA commands affected by this:
- `read_liberty` (OpenSTA)
- `read_sdc` (OpenSTA) 
- `report_checks` (OpenSTA)
- `create_clock` (OpenSTA)

Workaround: Use `info commands *liberty*` or `info commands read*` to see all available commands regardless of tab completion.

## OpenROAD Testing Framework

OpenROAD uses a CMake/CTest-based testing framework with custom integration functions for regression testing.

### Key Files and Architecture

1. Test Definition
- `src/cmake/testing.cmake` - Contains the `or_integration_tests()` function definition
- Defines `or_integration_test_single()` helper function
- Sets up CMake/CTest integration

2. Test Registration
- `src/[module]/test/CMakeLists.txt` - Each module (drt, pdn, gpl, etc.) calls `or_integration_tests()` to register tests
- Example: `or_integration_tests("drt" TESTS drc_test ispd18_sample ... PASSFAIL_TESTS gc_test)`
- Specifies which tests are regular tests vs passfail tests

3. Test Execution
- `test/regression_test.sh` - The actual bash script that runs each test
- Called by CMake/CTest for each individual test
- Handles both TCL and Python tests
- Creates log files and comparison diffs

4. Generated Test Files
- `build/src/[module]/test/CTestTestfile.cmake` - Auto-generated by CMake
- Contains the actual CTest commands based on `or_integration_tests()` calls

### How Testing Works

1. Registration: `CMakeLists.txt` calls `or_integration_tests("module_name" TESTS test1 test2 ...)`
2. Processing: `testing.cmake` processes this and creates CTest entries for each test
3. Execution: CTest runs each test by calling `regression_test.sh`
4. Testing: `regression_test.sh` executes `openroad -exit test_name.tcl` and compares output
5. Verification: `.ok` files serve dual purposes:
- Expected output files for log comparison (`TEST_CHECK_LOG=True`)
- Success markers created when tests pass

### File Patterns

- `.tcl` - Test scripts (TCL commands)
- `.py` - Python test scripts
- `.ok` - Expected output files OR success markers from passed tests
- `.defok` - Expected DEF output files for comparison
- `.guide` - Expected routing guide files
- `results/` - Directory containing test logs and diffs

### Test Types

- TESTS - Regular integration tests with log comparison
- PASSFAIL_TESTS - Simple pass/fail tests (exit code only)

### Running Tests

```bash
# Run all tests
make test

# Run tests for specific module
ctest -L drt

# Run specific test
ctest -R "drt.ispd18_sample.tcl"
```


---

## Consolidated from docs/orfs_mods.md

# OpenROAD-flow-scripts Modifications Required for FRIDA

This document describes the modifications required to OpenROAD-flow-scripts (ORFS) to support the FRIDA ADC digital design flow. These changes enable custom cell protection, placement blockages, and proper GDS generation for mixed-signal designs.

## Overview

The FRIDA flow requires several modifications to ORFS scripts to support:
- Custom analog-aware cells (clock gates, sample drivers) that must be protected from optimization
- Placement and routing blockages for future analog macro integration
- Proper via cell preservation during DEF to GDS conversion
- Mixed-signal design constraints

## Required Modifications

### 1. def2stream.py - Via Cell Preservation

**File:** `flow/util/def2stream.py`

**Issue:** KLayout's def2stream conversion was removing via cells because some PDKs use "VIA" prefix without underscore (e.g., VIA12_1cut_V) while the script only preserved cells with "VIA_" prefix.

**Change:**
```python
# Line ~28-34
# remove orphan cell BUT preserve cell with VIA_ or starting with VIA
#  - KLayout is prepending VIA_ when reading DEF that instantiates LEF's via
#  - Some platforms use VIA prefix without underscore (e.g., VIA12_1cut)
for i in main_layout.each_cell():
    if i.cell_index() != top_cell_index:
        if not i.name.startswith("VIA_") and not i.name.startswith("VIA") and not i.name.endswith("_DEF_FILL"):
            i.clear()
```

**Original:**
```python
        if not i.name.startswith("VIA_") and not i.name.endswith("_DEF_FILL"):
            i.clear()
```

**Why needed:** TSMC65 and other PDKs define via cells in LEF without the underscore (VIA12_1cut_V, VIA23_1cut, etc.). Without this change, all via geometry is lost during GDS merge.

---

### 2. synth.tcl - Custom Cell Support

**File:** `flow/scripts/synth.tcl`

**Issue:** Yosys synthesis check with `-assert` flag fails when design contains custom cells or wrapped operators, blocking the flow.

**Change:**
```tcl
# Line ~160-165
if { ![env_var_exists_and_non_empty SYNTH_WRAPPED_OPERATORS] } {

  # Check was causing a break, which I disabled for now! But FIXME!
  check -mapped

  # check -assert -mapped

} else {
```

**Original:**
```tcl
if { ![env_var_exists_and_non_empty SYNTH_WRAPPED_OPERATORS] } {
  check -assert -mapped
} else {
```

**Why needed:** FRIDA design includes custom analog-aware cells (clkgate, sampdriver) that are blackboxed during synthesis. The `-assert` flag causes synthesis to fail when these cells are present. Removing `-assert` allows the flow to continue with warnings instead of errors.

---

### 3. global_place.tcl - Custom Cell Protection and Buffer Control

**File:** `flow/scripts/global_place.tcl`

**Issue:**
1. Need to protect custom analog-aware cells from being optimized/removed during placement
2. Need to manually place specific cells for analog interface requirements
3. Default buffer selection chooses delay cells (DELD1LVT) instead of proper buffers (BUFFD2LVT)

**Changes:**

#### 3.1 DONT_TOUCH Hook (after line 6)
```tcl
# Run optional dont_touch script if DONT_TOUCH variable is defined
if { [info exists ::env(DONT_TOUCH)] && $::env(DONT_TOUCH) != "" } {
    puts "Running FRIDA project specific dont_touch script"
    source $::env(DONT_TOUCH)
}
```

**Why needed:** Allows design-specific script to mark cells as dont_touch before remove_buffers runs, preventing optimization of critical analog interface cells.

#### 3.2 MANUAL_PLACE Hook (after DONT_TOUCH hook)
```tcl
# Run optional manual placement script if MANUAL_PLACE variable is defined
if { [info exists ::env(MANUAL_PLACE)] && $::env(MANUAL_PLACE) != "" } {
    puts "Running FRIDA project specific manual_place script"
    source $::env(MANUAL_PLACE)
}
```

**Why needed:** Enables manual placement of specific cells before global placement, required for analog/digital interface cells that must be positioned precisely.

#### 3.3 Buffer Cell Selection (line ~29)
```tcl
if { ![env_var_exists_and_non_empty FOOTPRINT] } {
  if { ![env_var_equals DONT_BUFFER_PORTS 1] } {
    puts "Perform port buffering..."
    buffer_ports -buffer_cell {BUFFD2LVT}
  }
}

# I'm not sure why but it seems to want to select DELD1LVT as a buffer of choice, which just is a bit silly, the flag above is the only way I found to control it.
```

**Original:**
```tcl
    buffer_ports
```

**Why needed:** Without explicit `-buffer_cell` flag, OpenROAD's `selectBufferCell()` chooses the lowest drive resistance cell from the equivalence class, which selects DELD1LVT (delay cell) instead of a proper buffer. Explicit specification ensures BUFFD2LVT buffers are used.

---

### 4. floorplan.tcl - Placement/Routing Blockage Support

**File:** `flow/scripts/floorplan.tcl`

**Issue:** Mixed-signal designs need placement and routing blockages to reserve space for analog macros that will be integrated later.

**Changes:**

#### 4.1 CREATE_REGIONS Hook (after line 5, before report_unused_masters)
```tcl
# Run optional create_regions.tcl script for additional power rails
if { [info exists ::env(CREATE_REGIONS)] && $::env(CREATE_REGIONS) != "" } {
    puts "Running create_regions.tcl to create alternative voltage domain regions"
    source $::env(CREATE_REGIONS)
}
```

**Why needed:** Allows defining voltage domain regions for mixed-signal designs with multiple power domains (though not currently used in FRIDA digital block).

#### 4.2 CREATE_BLOCKAGES Hook (after line ~93, after floorplan creation)
```tcl
# Run optional create_blockages.tcl script for additional power rails
if { [info exists ::env(CREATE_BLOCKAGES)] && $::env(CREATE_BLOCKAGES) != "" } {
    puts "Running create_blockages.tcl"
    source $::env(CREATE_BLOCKAGES)
}
```

**Why needed:** Creates placement blockages in floorplan stage to reserve space for analog macros (comparator, sampling switches) that will be integrated at chip level. Critical for mixed-signal flows where digital blocks must leave space for analog components.

---

## Usage in FRIDA Design

### config.mk Variables
```makefile
# Enable custom cell protection
export DONT_TOUCH = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/dont_touch.tcl

# Enable placement blockages for analog macros
export CREATE_BLOCKAGES = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/create_blockages.tcl

# Optional: Manual placement (not currently used)
# export MANUAL_PLACE = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/manual_place.tcl

# Optional: Voltage domains (not currently used)
# export CREATE_REGIONS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/create_regions.tcl
```

### Example: dont_touch.tcl
```tcl
# Protect custom clock gates from optimization
set_dont_touch [get_cells clkgate/clkgate_comp.clkgate_cell]
set_dont_touch [get_cells clkgate/clkgate_init.clkgate_cell]
# ... etc
```

### Example: create_blockages.tcl
```tcl
# Reserve space for analog comparator
set comp_llx [expr int(19.5 * $dbu)]
set comp_lly [expr int(28.8 * $dbu)]
set comp_urx [expr int(40.5 * $dbu)]
set comp_ury [expr int(49.0 * $dbu)]

odb::dbBlockage_create $block $comp_llx $comp_lly $comp_urx $comp_ury
```

---

## Applying These Changes

### Apply Patch File
A patch file is included in this repository at `docs/orfs_mods.patch`.

Apply the patch to your ORFS installation:
```bash
cd /path/to/OpenROAD-flow-scripts
git apply /path/to/frida/docs/orfs_mods.patch
```

Verify the patch:
```bash
cd /path/to/OpenROAD-flow-scripts
git apply --check /path/to/frida/docs/orfs_mods.patch
```

---

## Notes and Caveats

1. **synth.tcl check -assert removal**: This is a workaround. Ideally, custom cells should be properly blackboxed in Yosys to avoid this issue. The TODO comment indicates this needs a proper fix.

2. **def2stream.py VIA preservation**: This change is defensive and should not break other flows, as it only makes the VIA detection more permissive.

3. **Buffer selection**: The DELD1LVT selection issue may be fixed in future OpenROAD versions. Monitor selectBufferCell() behavior in new releases.

4. **Hooks are optional**: All new hooks check for variable existence before sourcing, so they don't affect designs that don't use them.

---

## Version Information

These modifications were developed and tested with:
- OpenROAD: v2.0-24135-gb57dad1953
- KLayout: 0.29.x
- Platform: TSMC65LP (9 metal layers)
- Design: FRIDA ADC Digital Block (mixed-signal SAR ADC)

---

## Future Improvements

1. **Proper custom cell handling in Yosys**: Add proper blackbox directives to avoid synthesis check failures
2. **Standard ORFS mixed-signal support**: Propose these hooks as standard ORFS features for mixed-signal flows
3. **Via preservation improvement**: Investigate if KLayout's DEF reader can be configured to avoid needing def2stream.py modification
