#!/bin/bash
# save_all_stages.sh - Generate images for each flow stage

FLOW_HOME="$HOME/OpenROAD-flow-scripts/flow"
OPENROAD_EXE="$HOME/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad"

RESULTS_DIR="$FLOW_HOME/results/tsmc65/frida_adc_digital/base"
OUTPUT_DIR="${1:-/home/kcaisley/frida/docs/images}"

mkdir -p "$OUTPUT_DIR"

# 2_0: boundary box and rows only, no pins, no tracks
cat > /tmp/2_0_image.tcl <<TCLEOF
puts "Processing 2_0 (boundary + rows)..."
read_db $RESULTS_DIR/2_1_floorplan.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible true
gui::set_display_controls "Misc/Instances/Pins" visible false
gui::set_display_controls "Nets/*" visible false
gui::set_display_controls "Instances/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/2_0_floorplan.png
puts "Saved 2_0_floorplan.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/2_0_image.tcl

# 2_4_floorplan_pdn: power grid, blockages, pins, no tracks, no rows
cat > /tmp/2_4_image.tcl <<TCLEOF
puts "Processing 2_4_floorplan_pdn..."
read_db $RESULTS_DIR/2_4_floorplan_pdn.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Instances/*" visible false
gui::set_display_controls "Misc/Instances/Pins" visible true
gui::set_display_controls "Misc/Instances/Blockages" visible true
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/2_4_floorplan_pdn.png
puts "Saved 2_4_floorplan_pdn.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/2_4_image.tcl

# 3_1_place_gp_skip_io: show everything
cat > /tmp/3_1_image.tcl <<TCLEOF
puts "Processing 3_1_place_gp_skip_io..."
read_db $RESULTS_DIR/3_1_place_gp_skip_io.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/3_1_place_gp_skip_io.png
puts "Saved 3_1_place_gp_skip_io.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/3_1_image.tcl

# 3_3_place_gp: show everything
cat > /tmp/3_3_image.tcl <<TCLEOF
puts "Processing 3_3_place_gp..."
read_db $RESULTS_DIR/3_3_place_gp.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/3_3_place_gp.png
puts "Saved 3_3_place_gp.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/3_3_image.tcl

# 3_5_place_dp: show everything, no placement blockages
cat > /tmp/3_5_image.tcl <<TCLEOF
puts "Processing 3_5_place_dp..."
read_db $RESULTS_DIR/3_5_place_dp.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Instances/Blockages" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/3_5_place_dp.png
puts "Saved 3_5_place_dp.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/3_5_image.tcl

# 4_1_cts: show clock tree with timing-based colored display, no placement blockages
cat > /tmp/cts_image.tcl <<TCLEOF
puts "Processing 4_1_cts..."
read_liberty $FLOW_HOME/platforms/tsmc65/lib/tcbn65lplvtwc.lib
read_db $RESULTS_DIR/4_1_cts.odb
read_sdc $RESULTS_DIR/3_place.sdc
estimate_parasitics -placement
set_propagated_clock [all_clocks]
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Instances/Blockages" visible false
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

# 5_1_grt: show global routing with selected net
# NOTE: Route guides are not exposed in the TCL API.
# The "Show Route Guides" button in the inspector calls gui->addRouteGuides(net)
# but this function is not available via TCL commands.

# 5_2_route: detailed routing, no placement blockages
cat > /tmp/5_2_image.tcl <<TCLEOF
puts "Processing 5_2_route..."
read_db $RESULTS_DIR/5_2_route.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Heat Maps/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Instances/Blockages" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/5_2_route.png
puts "Saved 5_2_route.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/5_2_image.tcl

# 5_3_fillcell: fill cells added, no placement blockages
cat > /tmp/5_3_image.tcl <<TCLEOF
puts "Processing 5_3_fillcell..."
read_db $RESULTS_DIR/5_3_fillcell.odb
gui::set_display_controls "Misc/Background" color white
gui::set_display_controls "*" visible true
gui::set_display_controls "Tracks/*" visible false
gui::set_display_controls "Rows/*" visible false
gui::set_display_controls "Heat Maps/*" visible false
gui::set_display_controls "Misc/GCell grid" visible false
gui::set_display_controls "Misc/Instances/Blockages" visible false
gui::set_display_controls "Misc/Scale bar" visible true
gui::fit
save_image -width 3840 $OUTPUT_DIR/5_3_fillcell.png
puts "Saved 5_3_fillcell.png"
exit
TCLEOF
$OPENROAD_EXE -gui /tmp/5_3_image.tcl

echo "Done generating images!"

# Post-process: crop 400 pixels from left and right
echo "Cropping images (removing 400px from left and right)..."
IMAGES_TO_CROP=(
    "2_0_floorplan.png"
    "2_4_floorplan_pdn.png"
    "3_1_place_gp_skip_io.png"
    "3_3_place_gp.png"
    "3_5_place_dp.png"
    "4_1_cts.png"
    "4_1_cts_alt.png"
    "5_1_routeguides_global.png"
    "5_2_route.png"
    "5_3_fillcell.png"
    "6_2_thermal.png"
)
for img in "${IMAGES_TO_CROP[@]}"; do
    if [ -f "$OUTPUT_DIR/$img" ]; then
        echo "  Cropping $img..."
        convert "$OUTPUT_DIR/$img" -shave 400x0 "$OUTPUT_DIR/$img"
    else
        echo "  Skipping $img (not found)"
    fi
done

echo "Done! Images saved to $OUTPUT_DIR"
