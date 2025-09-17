# FRIDA Top-Level Macro Placement Script for IHP-SG13G2
# 16 ADC instances arranged in 4x4 grid
# 1.5mm x 1.5mm die with 1000x1000 core area

# ADC macro specifications:
# - Macro size: assume 150x150 micrometers each (dummy black box size)
# - Grid: 4x4 array with 100μm spacing between macro centers
# - Core area: 1000x1000μm (250,250 to 1250,1250)
# - Center the 4x4 grid within the core area

puts "Placing 16 ADC macros in explicit 4x4 grid with 100um spacing"

# Calculate grid positioning:
# Die area: 1500×1500, Core area: 250,250 to 1250,1250
# I/O pad ring extends ~150μm into core, so usable area is roughly 400,400 to 1100,1100 (700×700μm)
# ADC macro size: 150μm × 150μm
# 4x4 grid with tighter 160μm pitch to fit in smaller usable area
# Grid total span: 3 * 160μm = 480μm
# Available core width: 700μm, grid needs: 480μm + 150μm = 630μm
# Margin on each side: (700 - 630) / 2 = 35μm
# Grid starts at: 400 + 35 = 435, so positions: 435, 595, 755, 915

# Define 4x4 grid positions (moved inward to avoid I/O pad ring)
set grid_positions {
    {0 435 435} {1 595 435} {2 755 435} {3 915 435}
    {4 435 595} {5 595 595} {6 755 595} {7 915 595}
    {8 435 755} {9 595 755} {10 755 755} {11 915 755}
    {12 435 915} {13 595 915} {14 755 915} {15 915 915}
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