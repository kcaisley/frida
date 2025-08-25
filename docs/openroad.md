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

# Floorplan

Mixed-signal layout with digital logic constrained to 40x40µm using M1-M3 layers:

```
┌─────────┐ ┌────────────┐ ┌─────────┐                      
│         │ │            │ │         │                      
│         │ │ Comparator │ │         │                      
│Switch P │ │  (20x20µm) │ │Switch N │                      
│(10x20µm)│ │            │ │(10x20µm)│                      
└─────────┘ └────────────┘ └─────────┘                      
┌────────────────────────────────────┐                      
│  (sampswitches and comp connect)   │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│          Digital Logic             │                     
│         (50x50µm max)              │                      
│        (M1-M3 layers)              │                      
│                                    │                      
│(cap array              (cap array  │                      
│ P connect)              N connect) │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│                                    │                      
│             (SPI and config bits)  │                      
└────────────────────────────────────┘                      
```

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
