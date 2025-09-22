# FRIDA Top-Level Macro Placement Script for TSMC65
# 16 ADC instances arranged in 4x4 grid
# 1mm x 1mm die with 600x600 core area

# ADC macro specifications:
# - Macro size: assume 60x60 micrometers each (black box size)
# - Grid: 4x4 array with 100μm spacing between macro centers
# - Core area: 600x600μm (200,200 to 800,800)
# - Center the 4x4 grid in the core area

puts "Placing 16 ADC macros in explicit 4x4 grid with 100um spacing"

# Calculate grid positioning:
# Core area: 200,200 to 800,800 (600×600μm usable)
# Core center: (500, 500)
# 4x4 grid with 100μm pitch, centered
# Grid span: 3×100 = 300μm, so grid goes from 350 to 650
# X positions: 350, 450, 550, 650 (centered around 500)
# Y positions: 350, 450, 550, 650 (centered around 500)

# Define 4x4 grid positions (centered in core area)
set grid_positions {
    {0 350 350} {1 450 350} {2 550 350} {3 650 350}
    {4 350 450} {5 450 450} {6 550 450} {7 650 450}
    {8 350 550} {9 450 550} {10 550 550} {11 650 550}
    {12 350 650} {13 450 650} {14 550 650} {15 650 650}
}

# Get all ADC macro instances from the database and sort them
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