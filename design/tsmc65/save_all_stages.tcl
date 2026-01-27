# save_all_stages.tcl - Run from inside OpenROAD GUI
# Usage: set output_dir "/path/to/images"; source /path/to/save_all_stages.tcl

set results_dir "$::env(HOME)/OpenROAD-flow-scripts/flow/results/tsmc65/frida_adc_digital/base"

if {![info exists output_dir]} {
    set output_dir "/home/kcaisley/frida/docs/images"
}

# Create output directory if it doesn't exist
file mkdir $output_dir

set stages {
    2_1_floorplan
    2_2_floorplan_macro
    2_3_floorplan_tapcell
    2_4_floorplan_pdn
    2_floorplan
    3_1_place_gp_skip_io
    3_2_place_iop
    3_3_place_gp
    3_4_place_resized
    3_5_place_dp
    3_place
    4_1_cts
    4_cts
    5_1_grt
    5_2_route
    5_3_fillcell
    5_route
    6_1_fill
    6_final
}

foreach stage $stages {
    set odb_file "$results_dir/${stage}.odb"

    if {[file exists $odb_file]} {
        puts "Loading $stage..."
        read_db $odb_file
        gui::fit
        save_image -resolution 0.5 "$output_dir/${stage}.webp"
        puts "Saved ${stage}.webp"
    } else {
        puts "Skipping $stage - file not found"
    }
}

puts "Done! Images saved to $output_dir"
