# FRIDA Top-Level Macro Placement Script for IHP-SG13G2
# 16 ADC instances arranged in 4x4 grid
# 1.6mm x 1.6mm die with 1000x1000 core area

# ADC macro specifications:
# - Macro size: assume 150x150 micrometers each (dummy black box size)
# - Grid: 4x4 array with 220μm spacing between macro centers
# - Core area: 1000x1000μm (300,300 to 1300,1300)
# - Center the 4x4 grid horizontally, position 120μm higher than previous

puts "Placing 16 ADC macros in explicit 4x4 grid with 220um spacing"

# Calculate grid positioning:
# Core area: 300,300 to 1300,1300 (1000×1000μm usable)
# Core center: (800, 800)
# 4x4 grid with 220μm pitch, centered horizontally, shifted up 120μm
# X positions: 395, 615, 835, 1055 (centered around 800)
# Y positions: 465, 685, 905, 1125 (previous + 120μm)

# Define 4x4 grid positions (centered horizontally, moved up 120μm)
set grid_positions {
    {0 395 465} {1 615 465} {2 835 465} {3 1055 465}
    {4 395 685} {5 615 685} {6 835 685} {7 1055 685}
    {8 395 905} {9 615 905} {10 835 905} {11 1055 905}
    {12 395 1125} {13 615 1125} {14 835 1125} {15 1055 1125}
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