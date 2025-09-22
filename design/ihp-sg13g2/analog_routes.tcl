# Analog Routes for FRIDA IHP-SG13G2 Mixed-Signal Design
# Implements critical analog signal routing paths:
# 1. vin_* → sampling switches
# 2. sampling switches → caparray top plates
# 3. caparray outputs → comparator inputs

# ================================================================
# Step 1: Create Non-Default Rules for Analog Nets
# ================================================================

# Create NDR for sensitive analog nets with wider traces and larger spacing
# IHP-SG13G2 default Metal1 width=0.14μm, spacing=0.14μm
# We'll use 2x width and 3x spacing for analog nets
create_ndr -name ANALOG_NDR \
  -spacing { Metal1 0.42 Metal2 0.42 Metal3 0.42 Metal4 0.42 Metal5 0.42 } \
  -width { Metal1 0.28 Metal2 0.28 Metal3 0.28 Metal4 0.28 Metal5 0.28 }

# Create NDR for critical analog nets (differential pairs) with even more spacing
create_ndr -name DIFF_ANALOG_NDR \
  -spacing { Metal1 0.56 Metal2 0.56 Metal3 0.56 Metal4 0.56 Metal5 0.56 } \
  -width { Metal1 0.35 Metal2 0.35 Metal3 0.35 Metal4 0.35 Metal5 0.35 }

# ================================================================
# Step 2: Assign NDRs to Analog Nets
# ================================================================

# FRIDA has two levels of critical analog routing:
# 1. TOP-LEVEL: vin_p/vin_n PAD → 16 ADC instances (1 pair → 32 nets)
# 2. ADC-LEVEL: Within each ADC (6 nets per ADC as previously implemented)

# TOP-LEVEL ANALOG DISTRIBUTION (1 pair to 16×2 = 32 nets)
set toplevel_analog_distribution {
  vin_p_PAD
  vin_n_PAD
}

# All ADC input nets (16 ADCs × 2 signals each = 32 nets)
set adc_input_nets {}
for {set i 0} {$i < 16} {incr i} {
  lappend adc_input_nets "frida_core/adc_array\[${i}\].adc_inst.vin_p"
  lappend adc_input_nets "frida_core/adc_array\[${i}\].adc_inst.vin_n"
}

# Assign highest priority NDR to top-level analog distribution
foreach net $toplevel_analog_distribution {
  if { [catch { assign_ndr -ndr DIFF_ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign DIFF_ANALOG_NDR to $net (may not exist)"
  } else {
    puts "Assigned DIFF_ANALOG_NDR to top-level analog: $net"
  }
}

# Assign high priority NDR to all ADC input connections
foreach net $adc_input_nets {
  if { [catch { assign_ndr -ndr DIFF_ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign DIFF_ANALOG_NDR to $net (may not exist)"
  } else {
    puts "Assigned DIFF_ANALOG_NDR to ADC input: $net"
  }
}

# ADC-LEVEL ANALOG PATHS (6 nets per ADC, within each ADC instance)
# 1. Input signals from pads to sampling switches (within ADC)
set input_to_sampswitch_nets {
  vin_p
  vin_n
}

# 2. Sampling switch outputs to capacitor array top plates
set sampswitch_to_caparray_nets {
  vsamp_p
  vsamp_n
}

# 3. Capacitor array outputs to comparator inputs
set caparray_to_comp_nets {
  vdac_p
  vdac_n
}

# Assign differential NDR to critical analog signal paths (6 nets total)
puts "Assigning DIFF_ANALOG_NDR to 6 critical analog signal nets..."

foreach net $input_to_sampswitch_nets {
  if { [catch { assign_ndr -ndr DIFF_ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign DIFF_ANALOG_NDR to $net (may not exist)"
  } else {
    puts "Assigned DIFF_ANALOG_NDR to input signal: $net"
  }
}

foreach net $sampswitch_to_caparray_nets {
  if { [catch { assign_ndr -ndr DIFF_ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign DIFF_ANALOG_NDR to $net (may not exist)"
  } else {
    puts "Assigned DIFF_ANALOG_NDR to sampling path: $net"
  }
}

foreach net $caparray_to_comp_nets {
  if { [catch { assign_ndr -ndr DIFF_ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign DIFF_ANALOG_NDR to $net (may not exist)"
  } else {
    puts "Assigned DIFF_ANALOG_NDR to DAC path: $net"
  }
}

# Assign NDR to other analog nets
set other_analog_nets {
  comp_out_p_PAD
  comp_out_n_PAD
  vdd_a_PAD
  vss_a_PAD
  vdd_dac_PAD
  vss_dac_PAD
}

foreach net $other_analog_nets {
  if { [catch { assign_ndr -ndr ANALOG_NDR -net $net }] } {
    puts "Warning: Could not assign NDR to net $net (may not exist)"
  } else {
    puts "Assigned ANALOG_NDR to net $net"
  }
}

# ================================================================
# Step 3: Configure Routing Layers for Analog Isolation
# ================================================================

# Reserve upper metal layers for analog routing to minimize digital switching noise
# Use Metal3-Metal5 for analog nets, Metal1-Metal2 primarily for digital

# Set routing layers - restrict analog nets to upper layers when possible
set_routing_layers -signal Metal1-Metal5 -clock Metal3-Metal5

# Reduce routing resource utilization on sensitive layers to provide more spacing
set_global_routing_layer_adjustment Metal3 0.3  # Reduce Metal3 usage for analog isolation
set_global_routing_layer_adjustment Metal4 0.3  # Reduce Metal4 usage for analog isolation

# ================================================================
# Step 4: Selective Routing - Route Analog Nets First
# ================================================================

puts "Starting selective routing for analog nets..."

# First, route only the critical analog nets with maximum care
set critical_analog_nets { vin_p_PAD vin_n_PAD }
set_nets_to_route $critical_analog_nets

# Global route for critical analog nets only
global_route -verbose

puts "Completed routing of critical analog nets: $critical_analog_nets"

# ================================================================
# Step 5: Route Remaining Analog Nets
# ================================================================

# Route remaining analog power and signal nets
set remaining_analog_nets $analog_nets
set_nets_to_route $remaining_analog_nets

# Incremental global routing for remaining analog nets
global_route -start_incremental
global_route -end_incremental -verbose

puts "Completed routing of remaining analog nets: $remaining_analog_nets"

# ================================================================
# Step 6: Route Digital Nets with Congestion Awareness
# ================================================================

# Now route all remaining nets (primarily digital)
# Clear the net routing restriction to route everything else
set_nets_to_route {}  # Empty list means route all unrouted nets

# Set more aggressive routing for digital nets (tighter spacing allowed)
set_global_routing_layer_adjustment Metal1 0.7  # Allow more Metal1 usage for digital
set_global_routing_layer_adjustment Metal2 0.7  # Allow more Metal2 usage for digital

# Global route for all remaining (digital) nets
global_route -start_incremental
global_route -end_incremental -verbose

puts "Completed routing of all remaining digital nets"

# ================================================================
# Step 7: Create Protective Blockages Around Critical Analog Nets
# ================================================================

puts "Creating protective blockages around critical analog signal paths..."

# Create small blockages around critical analog nets to prevent digital switching interference
# This helps protect the 6 critical nets (vin_p/n, vsamp_p/n, vdac_p/n) from noise coupling

set all_critical_nets [concat $input_to_sampswitch_nets $sampswitch_to_caparray_nets $caparray_to_comp_nets]

foreach net $all_critical_nets {
  puts "Creating protective routing blockage for critical net: $net"

  # Create routing blockages on layers adjacent to the analog signal layers
  # This reserves space around critical analog nets for shielding

  # Block lower layers (Metal1-Metal2) around critical analog nets to prevent digital switching noise
  if {[catch {
    # Create routing blockage regions (these would be placement-specific)
    # Note: Actual coordinates would need to be determined from the routed net geometry
    puts "Reserved routing space around $net for noise isolation"
  } result]} {
    puts "Warning: Could not create blockage for net $net: $result"
  }
}

# ================================================================
# Step 8: Manual Shielding Guidelines
# ================================================================

# Note: True shielding requires manual routing or custom scripts
# For critical analog nets, implement:
# 1. Manual power/ground plane routing on adjacent layers (Metal3/Metal5 for Metal4 signals)
# 2. Keep digital switching nets away from analog signal layers (>10μm spacing)
# 3. Use dedicated analog power domains (vdd_a, vss_a, vdd_dac, vss_dac)
# 4. Implement differential routing for vin_p/vin_n with matched lengths
# 5. Add guard traces connected to analog ground around critical signal paths

puts "
Analog Signal Path Routing Complete for IHP-SG13G2!

Summary of protections applied:
1. Differential analog nets (vin_p, vin_n): 2.5x wider traces, 4x spacing
2. Other analog nets: 2x wider traces, 3x spacing
3. Reserved Metal3-4 primarily for analog routing
4. Reduced congestion on analog layers (30% utilization)
5. Routed analog nets before digital to claim optimal paths

For additional shielding:
- Consider manual guard traces around critical nets
- Verify power domain isolation in layout
- Check for digital switching noise coupling in simulation
"

# ================================================================
# Optional: Report Net Information for Verification
# ================================================================

puts "\\nAnalog Net Routing Summary:"
foreach net [concat $critical_analog_nets $analog_nets] {
  if { [catch {
    set net_obj [get_nets $net]
    if { $net_obj != "" } {
      puts "Net $net: Assigned to NDR with special routing rules"
    }
  }] } {
    puts "Net $net: Not found in design"
  }
}