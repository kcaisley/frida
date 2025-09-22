# Cap Driver Power Domain Placement Script for FRIDA ADC IHP-SG13G2
# Creates separate power domain for cap drivers with vdd_dac/vss_dac
# Places cap drivers in dedicated area at bottom 3/4 of core with isolation blockages
# Based on TASKS.md requirements and floorplan.md power domain separation

puts "Setting up separate power domain for cap drivers with isolation blockages"

# Get database handle
set db [ord::get_db]
set block [[$db getChip] getBlock]

# ================================================================
# Step 1: Define Cap Driver Power Domain Area
# ================================================================

# ADC core area dimensions (adapted for IHP-SG13G2: 60x60 with 2μm margins)
set core_area_x1 2
set core_area_y1 2
set core_area_x2 58
set core_area_y2 58

# Cap driver domain: bottom portion (roughly 3/4 up from bottom)
# This aligns with your floorplan showing cap drivers below comparator
set capdriver_domain_x1 $core_area_x1
set capdriver_domain_y1 $core_area_y1
set capdriver_domain_x2 $core_area_x2
set capdriver_domain_y2 [expr $core_area_y1 + ($core_area_y2 - $core_area_y1) * 0.35]  # Bottom 35% of core

puts "Cap driver power domain: ($capdriver_domain_x1, $capdriver_domain_y1) to ($capdriver_domain_x2, $capdriver_domain_y2)"

# Find all capdriver instances
set capdriver_instances {}
foreach inst [$block getInsts] {
    set inst_name [$inst getName]
    if {[string match "*capdriver*" $inst_name]} {
        lappend capdriver_instances $inst_name
        puts "Found capdriver instance: $inst_name"
    }
}

puts "Found [llength $capdriver_instances] capdriver instances for vdd_dac domain"

# ================================================================
# Step 2: Create Power Domain Isolation Blockages
# ================================================================

puts "Creating row-wide blockages to isolate cap driver power domain..."

# Create horizontal blockage row to separate cap driver domain from main logic
# This prevents power domain mixing during placement
set isolation_y [expr $capdriver_domain_y2 + 1.0]  # 1μm above cap driver domain
set isolation_height 2.0  # 2μm wide isolation strip

puts "Creating isolation blockage at Y=${isolation_y}, height=${isolation_height}"

if {[catch {
    create_blockage -region [list $core_area_x1 $isolation_y $core_area_x2 [expr $isolation_y + $isolation_height]] -hard
    puts "✓ Created hard blockage to isolate vdd_dac domain from vdd_d domain"
} result]} {
    puts "Warning: Could not create isolation blockage: $result"
}

# ================================================================
# Step 3: Manual Placement of Cap Driver Instances
# ================================================================

# Force cap driver instances into their dedicated power domain area
foreach capdriver_inst $capdriver_instances {
    puts "Placing $capdriver_inst in vdd_dac power domain"

    # Calculate placement position within cap driver domain
    # Distribute cap drivers evenly across the domain width
    set num_capdrivers [llength $capdriver_instances]
    set inst_index [lsearch $capdriver_instances $capdriver_inst]

    # Place cap drivers side by side in the dedicated domain
    set inst_width [expr ($capdriver_domain_x2 - $capdriver_domain_x1) / $num_capdrivers]
    set inst_x [expr $capdriver_domain_x1 + ($inst_index * $inst_width)]
    set inst_y [expr $capdriver_domain_y1 + 3.0]  # 3μm from bottom for routing space

    puts "Placing $capdriver_inst at ($inst_x, $inst_y) in vdd_dac domain"

    # Place the entire cap driver instance in the domain
    if {[catch {
        place_inst -inst $capdriver_inst -location [list $inst_x $inst_y] -orientation R0 -status PLACED
        puts "✓ Successfully placed $capdriver_inst in vdd_dac domain"
    } result]} {
        puts "Warning: Could not place cap driver instance $capdriver_inst: $result"
        continue
    }

    # ================================================================
    # Step 4: Place XOR Gates within Cap Driver Power Domain
    # ================================================================

    # Now place individual XOR gates within the cap driver instance
    # These will inherit the vdd_dac power domain from their parent instance
    set xor_width 0.48   ; # IHP-SG13G2 minimal XOR cell width
    set xor_height 3.33  ; # IHP-SG13G2 standard cell height (sg13g2_stdcell)
    set spacing_x 0.72   ; # 1.5x cell width for routing space
    set spacing_y 4.2    ; # 1.25x cell height for routing space

    # Starting position relative to capdriver instance (aligned to placement grid)
    set start_x [expr $inst_x + 1.0]  ; # Small offset within cap driver area
    set start_y [expr $inst_y + 1.0]  ; # Small offset within cap driver area

    puts "Placing 16 XOR gates for $capdriver_inst in vdd_dac domain"

    # Place 16 XOR gates in 4x4 arrangement within the power domain
    for {set i 0} {$i < 16} {incr i} {
        set row [expr $i / 4]
        set col [expr $i % 4]

        set xor_x [expr $start_x + ($col * $spacing_x)]
        set xor_y [expr $start_y + ($row * $spacing_y)]

        # Ensure XOR gates stay within the cap driver power domain
        if {$xor_y > $capdriver_domain_y2} {
            puts "Warning: XOR gate $i would exceed power domain boundary, adjusting placement"
            set xor_y [expr $capdriver_domain_y2 - $xor_height]
        }

        # XOR gate instance name pattern from TASKS.md
        set xor_inst_name "${capdriver_inst}/xor_gates\\[${i}\\].xor_gate.xor_cell"

        puts "  XOR[$i]: $xor_inst_name at ($xor_x, $xor_y) in vdd_dac domain"

        # Place XOR gate with IHP-SG13G2 cell type
        if {[catch {place_inst -name $xor_inst_name -origin [list $xor_x $xor_y] -orientation R0 -status PLACED -cell sg13g2_xor2_1} result]} {
            # Try alternative placement method
            if {[catch {place_inst -inst $xor_inst_name -location [list $xor_x $xor_y] -orientation R0 -status PLACED} result2]} {
                puts "  Error: Could not place XOR gate $xor_inst_name: $result2"
            } else {
                puts "  ✓ Placed XOR gate $xor_inst_name in vdd_dac domain"
            }
        } else {
            puts "  ✓ Placed XOR gate $xor_inst_name in vdd_dac domain"
        }
    }
}

puts "Completed cap driver power domain setup with isolation blockages"

# ================================================================
# Step 5: Power Domain Coordination Requirements
# ================================================================

puts "
⚠️  COORDINATION REQUIRED FOR PROPER POWER DOMAIN IMPLEMENTATION:

1. MACRO PLACEMENT (macro.tcl):
   • Ensure analog macros (caparray, comp, sampswitch) are placed
     ABOVE the isolation blockage at Y > [expr $isolation_y + $isolation_height]
   • This prevents them from being in the vdd_dac domain

2. PDN GRID GENERATION (pdn.tcl):
   • Create separate vdd_dac/vss_dac stripes ONLY in cap driver domain:
     Region: ($capdriver_domain_x1, $capdriver_domain_y1) to ($capdriver_domain_x2, $capdriver_domain_y2)
   • Create vdd_d/vss_d stripes ONLY above isolation blockage:
     Region: ($core_area_x1, [expr $isolation_y + $isolation_height]) to ($core_area_x2, $core_area_y2)
   • NO OVERLAP between power domains to prevent shorts!

3. PLACEMENT COORDINATION:
   • Cap driver instances: MANUALLY placed in bottom domain (✓ Done)
   • Other digital logic: Will be automatically placed above blockage
   • Analog macros: Must be placed above blockage in separate script

NEXT STEPS:
1. Update macro.tcl to respect power domain boundaries
2. Update pdn.tcl to create domain-specific power stripes
3. Verify no power domain overlap during PDN generation
"

# ================================================================
# Step 6: Horizontal Strip Blockages for Track Isolation
# ================================================================

puts "Creating horizontal strip blockages across track rows..."

# IHP-SG13G2 standard cell height = 3.33μm, so track pitch ≈ 0.48μm (finer routing grid)
# For 60x60 core area (Y = 2 to 58), calculate track positions
set track_pitch 0.48
set core_bottom 2.0
set core_top 58.0

# Calculate track row positions (3rd from bottom and 3rd from top)
set track_3rd_from_bottom [expr $core_bottom + (3 * $track_pitch)]  # ~3.44μm
set track_3rd_from_top [expr $core_top - (3 * $track_pitch)]        # ~56.56μm

# Strip height = 1 track pitch
set strip_height $track_pitch

puts "Creating horizontal blockage strips at track rows:"
puts "  3rd from bottom: Y = $track_3rd_from_bottom"
puts "  3rd from top: Y = $track_3rd_from_top"

# Create horizontal strip blockage - 3rd track from bottom
if {[catch {
    create_blockage -region [list $core_area_x1 $track_3rd_from_bottom $core_area_x2 [expr $track_3rd_from_bottom + $strip_height]] -soft
    puts "✓ Created horizontal strip blockage at 3rd track from bottom (Y=${track_3rd_from_bottom})"
} result]} {
    puts "Warning: Could not create bottom strip blockage: $result"
}

# Create horizontal strip blockage - 3rd track from top
if {[catch {
    create_blockage -region [list $core_area_x1 $track_3rd_from_top $core_area_x2 [expr $track_3rd_from_top + $strip_height]] -soft
    puts "✓ Created horizontal strip blockage at 3rd track from top (Y=${track_3rd_from_top})"
} result]} {
    puts "Warning: Could not create top strip blockage: $result"
}

puts "Completed power domain setup and analog macro protection"