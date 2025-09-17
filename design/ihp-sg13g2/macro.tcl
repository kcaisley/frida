# FRIDA Top-Level Macro Placement Script for IHP-SG13G2
# 16 ADC instances arranged in 4x4 grid
# 1.5mm x 1.5mm die with 1000x1000 core area

# ADC macro specifications:
# - Macro size: assume 150x150 micrometers each (dummy black box size)
# - Grid: 4x4 array with 100μm spacing between macro centers
# - Core area: 1000x1000μm (250,250 to 1250,1250)
# - Center the 4x4 grid within the core area

puts "Placing 16 ADC macros in explicit 4x4 grid with 220um spacing"

# Calculate grid positioning:
# Die area: 1500×1500, Core area: 250,250 to 1250,1250
# I/O pad ring extends ~150μm into core, so usable area is roughly 400,400 to 1100,1100 (700×700μm)
# ADC macro size: 150μm × 150μm
# 4x4 grid with 220μm pitch for better routing and power distribution
# Core area: 250,250 to 1250,1250 (1000×1000μm usable)
# Grid total span: 3 * 220μm = 660μm
# Grid needs: 660μm + 150μm (macro width) = 810μm total
# Available: 1000μm, margin: (1000-660)/2 = 170μm on each side
# Start position: 250 + 170 = 420μm, positions: 420, 640, 860, 1080

# Define 4x4 grid positions (centered in core area)
set grid_positions {
    {0 420 420} {1 640 420} {2 860 420} {3 1080 420}
    {4 420 640} {5 640 640} {6 860 640} {7 1080 640}
    {8 420 860} {9 640 860} {10 860 860} {11 1080 860}
    {12 420 1080} {13 640 1080} {14 860 1080} {15 1080 1080}
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