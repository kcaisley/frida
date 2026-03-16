########################################################################
# OpenROAD Analog Place-and-Route Script for FRIDA Comparator
#
# This is a hand-written TCL script that serves as the "target output"
# for the FRIDA TCL generation flow. The automated flow will eventually
# produce a script like this from:
#   1. Constraint objects (flow/constraint/)
#   2. VLSIR artifacts (LEF, Verilog)
#   3. TCL emitter (flow/openroad/)
#
# Usage:
#   openroad flow.tcl
#
# Inputs (all in same directory):
#   sg13g2_tech.lef    - IHP SG13G2 technology LEF (from PDK)
#   sg13g2_macros.lef  - Macro LEF for sg13_lv_nmos / sg13_lv_pmos
#   comp.v             - Structural Verilog netlist of comparator
#
# Output:
#   comp_placed_routed.def  - Placed and routed DEF
#
########################################################################

set script_dir [file dirname [file normalize [info script]]]

# ── 1. Read Design ────────────────────────────────────────────────────

read_lef $script_dir/sg13g2_tech.lef
read_lef $script_dir/sg13g2_macros.lef
read_verilog $script_dir/comp.v
link_design Comp

# ── 2. Floorplan ──────────────────────────────────────────────────────
#
# 15 instances × 3.020 × 3.060 um each ≈ 138 um² total cell area
# 8 rows × 4.0 um pitch = 32 um + margins → 35 um tall
# Width: symmetric pairs + buffer offset → 35 um wide

initialize_floorplan \
    -die_area  "0 0 35 35" \
    -core_area "1 1 34 34" \
    -site      unit

# ── 3. Track Setup ────────────────────────────────────────────────────
#
# Create routing tracks matching the tech LEF layer definitions.
# Format: make_tracks <layer> -x_offset <um> -x_pitch <um>
#                              -y_offset <um> -y_pitch <um>

make_tracks Metal1  -x_offset 0 -x_pitch 0.42  -y_offset 0 -y_pitch 0.42
make_tracks Metal2  -x_offset 0 -x_pitch 0.48  -y_offset 0 -y_pitch 0.48
make_tracks Metal3  -x_offset 0 -x_pitch 0.42  -y_offset 0 -y_pitch 0.42
make_tracks Metal4  -x_offset 0 -x_pitch 0.48  -y_offset 0 -y_pitch 0.48
make_tracks Metal5  -x_offset 0 -x_pitch 0.42  -y_offset 0 -y_pitch 0.42

# ── 4. Pin Placement ──────────────────────────────────────────────────
#
# PortLocation constraints: inputs on left, outputs on right,
# clock on bottom, power on top.
# Corresponds to: PortLocation("inp", LEFT), etc.

set_io_pin_constraint -pin_names {inp inn}          -region left:*
set_io_pin_constraint -pin_names {outp outn}        -region right:*
set_io_pin_constraint -pin_names {clk clkb}         -region bottom:*
set_io_pin_constraint -pin_names {vdd vss}          -region top:*

place_pins -hor_layers Metal3 -ver_layers Metal2

# ── 5. Fixed Placements (SymmetricBlocks + Order) ─────────────────────
#
# These correspond to constraint objects:
#   SymmetricBlocks(pairs=[("mdiff_p", "mdiff_n")], axis=VERTICAL)
#   SymmetricBlocks(pairs=[("mrst_p", "mrst_n")], axis=VERTICAL)
#   SymmetricBlocks(pairs=[("ma_p", "ma_n")], axis=VERTICAL)
#   SymmetricBlocks(pairs=[("mb_p", "mb_n")], axis=VERTICAL)
#   Order(instances=["mtail", "mdiff_p", "mrst_p", "ma_p"],
#         direction=BOTTOM_TO_TOP)
#
# Symmetry axis at x = 17.5 um (center of 35 um die)
# Cell width = 3.020 um, cell height = 3.060 um
# Row pitch = 4.0 um (cell height + ~1 um routing channel)
# Left cell x = axis - cell_w - gap/2, right cell x = axis + gap/2
#
# Vertical stacking from bottom (8 rows):
#   row 0: mtail (centered)
#   row 1: mdiff_p / mdiff_n
#   row 2: mrst_p / mrst_n
#   row 3: mlatch_rst_p / mlatch_rst_n
#   row 4: ma_p / ma_n
#   row 5: mb_p / mb_n
#   row 6: mbuf_outp_top / mbuf_outn_top
#   row 7: mbuf_outp_bot / mbuf_outn_bot

set block [ord::get_db_block]

# Helper: place an instance and lock it
proc place_and_lock {block name x y} {
    set inst [$block findInst $name]
    if {$inst == "NULL"} {
        puts "WARNING: instance $name not found"
        return
    }
    $inst setLocation [expr {int($x * 1000)}] [expr {int($y * 1000)}]
    $inst setPlacementStatus "LOCKED"
    puts "  Placed $name at ($x, $y) LOCKED"
}

puts "\n── Manual placement ──"

# Symmetry axis at x = 17.5 um (center of 35 um die)
set sym_x    17.5
set cell_w    3.020
set cell_h    3.060
set half_w   [expr {$cell_w / 2.0}]
set gap       1.0
set x_left   [expr {$sym_x - $cell_w - $gap / 2.0}]
set x_right  [expr {$sym_x + $gap / 2.0}]
set x_center [expr {$sym_x - $half_w}]

# Row pitch = cell_h + routing channel
set row_pitch 4.0

# Y positions: 8 rows starting at y = 1.0
set y0  1.0
set y1  [expr {$y0 + 1 * $row_pitch}]
set y2  [expr {$y0 + 2 * $row_pitch}]
set y3  [expr {$y0 + 3 * $row_pitch}]
set y4  [expr {$y0 + 4 * $row_pitch}]
set y5  [expr {$y0 + 5 * $row_pitch}]
set y6  [expr {$y0 + 6 * $row_pitch}]
set y7  [expr {$y0 + 7 * $row_pitch}]

# Row 0: Tail (centered on symmetry axis)
place_and_lock $block mtail $x_center $y0

# Row 1: Differential pair (symmetric)
place_and_lock $block mdiff_p $x_left  $y1
place_and_lock $block mdiff_n $x_right $y1

# Row 2: Reset/load devices (symmetric)
place_and_lock $block mrst_p $x_left  $y2
place_and_lock $block mrst_n $x_right $y2

# Row 3: Latch reset devices (symmetric)
place_and_lock $block mlatch_rst_p $x_left  $y3
place_and_lock $block mlatch_rst_n $x_right $y3

# Row 4: Latch PMOS cross-coupled pair (symmetric)
place_and_lock $block ma_p $x_left  $y4
place_and_lock $block ma_n $x_right $y4

# Row 5: Latch NMOS cross-coupled pair (symmetric)
place_and_lock $block mb_p $x_left  $y5
place_and_lock $block mb_n $x_right $y5

# Row 6: Output buffer tops (symmetric, wider spread)
set buf_offset 5.0
place_and_lock $block mbuf_outp_top [expr {$sym_x - $cell_w - $buf_offset}] $y6
place_and_lock $block mbuf_outn_top [expr {$sym_x + $buf_offset}]           $y6

# Row 7: Output buffer bottoms (symmetric, wider spread)
place_and_lock $block mbuf_outp_bot [expr {$sym_x - $cell_w - $buf_offset}] $y7
place_and_lock $block mbuf_outn_bot [expr {$sym_x + $buf_offset}]           $y7

# ── 6. NDR Setup (RouteConstraint) ────────────────────────────────────
#
# Corresponds to:
#   RouteConstraint(nets=["outp_int", "outn_int"],
#                   min_layer="Metal2", max_layer="Metal4",
#                   width_mult=2, spacing_mult=2)

# Note: NDR commands may not work without a liberty file in OpenROAD.
# Leaving them here as the target for what the generator should emit.

# add_ndr -name ndr_diff \
#     -width_multiplier  "Metal2:2 Metal3:2 Metal4:2" \
#     -spacing_multiplier "Metal2:2 Metal3:2 Metal4:2"
#
# assign_ndr -ndr ndr_diff -net outp_int
# assign_ndr -ndr ndr_diff -net outn_int

# ── 7. Net Weights (NetPriority) ──────────────────────────────────────
#
# Corresponds to:
#   NetPriority(nets=["outp_int", "outn_int"], priority=10)
#   NetPriority(nets=["tail"], priority=5)
#   NetPriority(nets=["clk", "clkb"], priority=8)
#
# Net weighting affects global placement (GPL) and routing congestion.
# In OpenROAD these are set via the Replace API, not plain TCL.
# Leaving as comments — the real script would use Python API for this.

# set_net_weight outp_int 10
# set_net_weight outn_int 10
# set_net_weight tail     5
# set_net_weight clk      8
# set_net_weight clkb     8

# ── 8. Global Placement ──────────────────────────────────────────────
#
# Since all instances are LOCKED, the global placer has nothing to move.
# We still run it to initialize internal data structures that the router
# expects. Skip if OpenROAD complains about no movable instances.

# global_placement -density 0.3 -overflow 0.1

# ── 9. Detail Placement ──────────────────────────────────────────────

# detailed_placement  — skip: all instances are LOCKED
check_placement -verbose

# ── 10. Set Routing Layers ────────────────────────────────────────────

set_routing_layers -signal Metal1-Metal5

# ── 11. Global Routing ────────────────────────────────────────────────

global_route -allow_congestion \
             -verbose

# ── 12. Symmetric Routing Workaround ─────────────────────────────────
#
# OpenROAD has NO native symmetric routing support.
# The workaround (from or_analog.md) is:
#   1. Route net_a (e.g. outp_int)
#   2. Extract routing guides for net_a
#   3. Mirror guide coordinates about symmetry axis
#   4. Apply mirrored guides to net_b (outn_int)
#   5. Re-route net_b with constrained guides
#
# This requires Python ODB scripting and is NOT automatable in pure TCL.
# Leaving as a comment block for future implementation.
#
# TODO: Implement guide-mirror approach for SymmetricNets constraint
#       SymmetricNets(nets=[("outp_int", "outn_int")], axis=VERTICAL)

# ── 13. Detail Routing ────────────────────────────────────────────────

detailed_route

# ── 14. Output ────────────────────────────────────────────────────────

write_def $script_dir/comp_placed_routed.def

puts "\n══════════════════════════════════════════════════════════════"
puts "  Done. Output: $script_dir/comp_placed_routed.def"
puts "══════════════════════════════════════════════════════════════\n"

exit
