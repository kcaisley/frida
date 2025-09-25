# FRIDA Top-Level Macro Placement Script for TSMC65
# 16 ADC instances arranged in 4x4 grid
# 1mm x 1mm die with 520x540 core area

# ADC macro specifications:
# - Macro size: 60x60 micrometers each (black box size)
# - Grid: 4x4 array with 100μm spacing between macro centers
# - Core area: 520x540μm (240,300 to 760,840)
# - Center the 4x4 grid in the core area

puts "Placing 16 ADC macros in explicit 4x4 grid with 100um spacing"

# Calculate grid positioning:
# Core area: 240,300 to 760,840 (520×540μm usable)
# Core center: (500, 570)
# 4x4 grid with 100μm pitch, centered
# Grid span: 3×100 = 300μm
# X positions: 290, 410, 530, 650 (120μm spacing)
# Y positions: 350, 470, 590, 710 (120μm spacing)

# Define 4x4 grid positions (centered in core area)
set grid_positions {
    {0 290 350} {1 410 350} {2 530 350} {3 650 350}
    {4 290 470} {5 410 470} {6 530 470} {7 650 470}
    {8 290 590} {9 410 590} {10 530 590} {11 650 590}
    {12 290 710} {13 410 710} {14 530 710} {15 650 710}
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