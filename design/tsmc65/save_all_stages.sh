#!/bin/bash
# save_all_stages.sh - Generate images for each flow stage

FLOW_HOME="$HOME/OpenROAD-flow-scripts/flow"
OPENROAD_EXE="$HOME/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad"

RESULTS_DIR="$FLOW_HOME/results/tsmc65/frida_adc_digital/base"
OUTPUT_DIR="${1:-/home/kcaisley/frida/docs/images}"

mkdir -p "$OUTPUT_DIR"

# 2_0: boundary box and rows only, no pins, no tracks
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 2_0 (boundary + rows)..."
read_db $RESULTS_DIR/2_1_floorplan.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* true} -display_option {Misc/Instances/Pins false} -display_option {Nets/* false} -display_option {Instances/* false} -display_option {Misc/Scale\ bar true} $OUTPUT_DIR/2_0_floorplan.png
puts "Saved 2_0_floorplan.png"
EOF

# 2_3_floorplan_tapcell: pins and placement blockages, no tracks, no rows
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 2_3_floorplan_tapcell..."
read_db $RESULTS_DIR/2_3_floorplan_tapcell.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* false} -display_option {Nets/* false} -display_option {Shape\ Types/* false} -display_option {Instances/* false} -display_option {Misc/Instances/Pins true} -display_option {Misc/Instances/Blockages true} $OUTPUT_DIR/2_3_floorplan_tapcell.png
puts "Saved 2_3_floorplan_tapcell.png"
EOF

# 2_4_floorplan_pdn: power grid, blockages, pins, no tracks, no rows
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 2_4_floorplan_pdn..."
read_db $RESULTS_DIR/2_4_floorplan_pdn.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* false} -display_option {Instances/* false} -display_option {Misc/Instances/Pins true} -display_option {Misc/Instances/Blockages true} -display_option {Misc/Scale\ bar true} $OUTPUT_DIR/2_4_floorplan_pdn.png
puts "Saved 2_4_floorplan_pdn.png"
EOF

# 3_1_place_gp_skip_io: show everything
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 3_1_place_gp_skip_io..."
read_db $RESULTS_DIR/3_1_place_gp_skip_io.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* false} -display_option {Misc/Scale\ bar true} $OUTPUT_DIR/3_1_place_gp_skip_io.png
puts "Saved 3_1_place_gp_skip_io.png"
EOF

# 3_3_place_gp: show everything
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 3_3_place_gp..."
read_db $RESULTS_DIR/3_3_place_gp.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* false} -display_option {Misc/Scale\ bar true} $OUTPUT_DIR/3_3_place_gp.png
puts "Saved 3_3_place_gp.png"
EOF

# 3_5_place_dp: show everything
$OPENROAD_EXE -no_init -exit <<EOF
puts "Processing 3_5_place_dp..."
read_db $RESULTS_DIR/3_5_place_dp.odb
save_image -width 3840 -display_option {* true} -display_option {Tracks/* false} -display_option {Rows/* false} -display_option {Misc/Scale\ bar true} $OUTPUT_DIR/3_5_place_dp.png
puts "Saved 3_5_place_dp.png"
EOF

# 4_1_cts: show clock tree with timing-based colored display
cat > /tmp/cts_image.tcl <<TCLEOF
puts "Processing 4_1_cts..."
read_liberty $FLOW_HOME/platforms/tsmc65/lib/tcbn65lplvtwc.lib
read_db $RESULTS_DIR/4_1_cts.odb
read_sdc $RESULTS_DIR/3_place.sdc
estimate_parasitics -placement
set_propagated_clock [all_clocks]
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Nets/Clock" visible true
gui::set_display_controls "Instances/StdCells/Clock tree/*" visible true
gui::set_display_controls "Instances/StdCells/Sequential" visible true
gui::set_display_controls "Misc/Scale bar" visible true
gui::show_widget "Clock Tree Viewer"
gui::select_clockviewer_clock seq_update
gui::fit
save_image -width 3840 $OUTPUT_DIR/4_1_cts.png
puts "Saved 4_1_cts.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/cts_image.tcl

echo "Done! Images saved to $OUTPUT_DIR"
