# FRIDA Top-Level Macro Placement Script for TSMC65
# 16 ADC instances arranged in 4x4 grid in upper 2/3 of die
# 540x540 core area

# ADC macro specifications:
# - Macro size: 60x60 micrometers each
# - Grid: 4x4 array placed in upper 2/3 of die (y: 180-540, 360um height)
# - Core area: 540x540μm (0,0 to 540,540)
# - X spacing: 135μm pitch (540/4)
# - Y spacing: 100μm pitch

puts "Placing 16 ADC macros in 4x4 grid in upper 2/3 of die"

# Calculate grid positioning:
# Die area: 0 0 540 540
# Macro size: 60um × 60um (centers offset by ±30um)
# X centers: 89.6, 189.6, 289.6, 389.6 (100um pitch, shifted left 0.4um)
# Y centers: 140, 240, 340, 440 (100um pitch, range 140-440)
#   Row 0 @ y=140: spans 110-170
#   Row 1 @ y=240: spans 210-270
#   Row 2 @ y=340: spans 310-370
#   Row 3 @ y=440: spans 410-470

# Define 4x4 grid positions
set grid_positions {
    {0 89.6 140} {1 189.6 140} {2 289.6 140} {3 389.6 140}
    {4 89.6 240} {5 189.6 240} {6 289.6 240} {7 389.6 240}
    {8 89.6 340} {9 189.6 340} {10 289.6 340} {11 389.6 340}
    {12 89.6 440} {13 189.6 440} {14 289.6 440} {15 389.6 440}
}

# Get all macro instances from the database
set db [ord::get_db]
set block [[$db getChip] getBlock]
set adc_instances {}

foreach inst [$block getInsts] {
    set inst_name [$inst getName]
    if {[string match "*adc_array*adc_inst" $inst_name]} {
        lappend adc_instances $inst_name
    }
}

# Sort instances by extracting index number
set sorted_instances {}
for {set i 0} {$i < 16} {incr i} {
    foreach inst_name $adc_instances {
        # Extract the exact index using regex to avoid partial matches
        if {[regexp {adc_array\\\[(\d+)\\\]\.adc_inst} $inst_name full_match index]} {
            if {$index == $i} {
                lappend sorted_instances $inst_name
                break
            }
        }
    }
}

puts "Found [llength $sorted_instances] ADC macro instances"

# Place each ADC macro at the specified location
foreach position $grid_positions {
    set index [lindex $position 0]
    set x_pos [lindex $position 1]
    set y_pos [lindex $position 2]

    if {$index < [llength $sorted_instances]} {
        set inst_name [lindex $sorted_instances $index]

        puts "Placing $inst_name at ($x_pos, $y_pos) with orientation R0"

        # Use place_macro command to explicitly place the macro
        if {[catch {place_macro -macro_name $inst_name -location [list $x_pos $y_pos] -orientation R0} result]} {
            puts "Warning: Could not place macro $inst_name: $result"
        } else {
            puts "Successfully placed macro $inst_name"
        }
    }
}

puts "Completed explicit placement of 16 ADC macros in 4x4 grid"