add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern VDD -power
add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern VSS -ground

# ADC analog pins - global connections for all ADC instances
add_global_connection -net {vin_p} -pin_pattern {vin_p} -power
add_global_connection -net {vin_n} -pin_pattern {vin_n} -power
add_global_connection -net {vdd_a} -pin_pattern {vdd_a} -power
add_global_connection -net {vss_a} -pin_pattern {vss_a} -ground
add_global_connection -net {vdd_d} -pin_pattern {vdd_d} -power
add_global_connection -net {vss_d} -pin_pattern {vss_d} -ground
add_global_connection -net {vdd_dac} -pin_pattern {vdd_dac} -power
add_global_connection -net {vss_dac} -pin_pattern {vss_dac} -ground

global_connect

set_voltage_domain -power vdd_d -ground vss_d -secondary_power {vdd_a vdd_dac vss_a vss_dac}
define_pdn_grid -name "Core" -pins {M8}

# Three concentric rings
# Outermost ring: vdd_dac/vss_dac (DAC) - 2um from core edge
add_pdn_ring -grid "Core" -layers {M8 M9} -widths 4.0 -spacings 1.0 -core_offsets 26.0 -nets {vdd_dac vss_dac}

# Middle ring: vdd_a/vss_a (analog) - 6um from core edge
add_pdn_ring -grid "Core" -layers {M8 M9} -widths 4.0 -spacings 1.0 -core_offsets 15.0 -nets {vdd_a vss_a}

# Innermost ring: vdd_d/vss_d (digital) - 10um from core edge
add_pdn_ring -grid "Core" -layers {M8 M9} -widths 4.0 -spacings 1.0 -core_offsets 4.0 -nets {vdd_d vss_d}


# Vertical power stripes on M8 for each power domain
add_pdn_stripe -grid "Core" -layer M8 -width 2.0 -pitch 100.0 -offset 41.0 -number_of_straps 4 -nets {vdd_d} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 2.0 -pitch 100.0 -offset 47.0 -number_of_straps 4 -nets {vss_d} -extend_to_core_ring

add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 55.5 -number_of_straps 4 -nets {vdd_d} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 57.5 -number_of_straps 4 -nets {vss_d} -extend_to_core_ring

add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 78.0 -number_of_straps 4 -nets {vss_a} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 80.0 -number_of_straps 4 -nets {vdd_a} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 82.0 -number_of_straps 4 -nets {vss_dac} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 84.0 -number_of_straps 4 -nets {vdd_dac} -extend_to_core_ring

add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 86.0 -number_of_straps 4 -nets {vdd_dac} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 88.0 -number_of_straps 4 -nets {vss_dac} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 90.0 -number_of_straps 4 -nets {vdd_a} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 92.0 -number_of_straps 4 -nets {vss_a} -extend_to_core_ring

add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 112.5 -number_of_straps 4 -nets {vss_d} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 1.0 -pitch 100.0 -offset 114.5 -number_of_straps 4 -nets {vdd_d} -extend_to_core_ring

add_pdn_stripe -grid "Core" -layer M8 -width 2.0 -pitch 100.0 -offset 123.0 -number_of_straps 4 -nets {vss_d} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M8 -width 2.0 -pitch 100.0 -offset 129.0 -number_of_straps 4 -nets {vdd_d} -extend_to_core_ring

# Horizontal power strips,
add_pdn_stripe -grid "Core" -layer M9 -width 4.0 -spacing 1.0 -pitch 100.0 -offset 71.0 -number_of_straps 4 -nets {vdd_d vss_d} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M9 -width 4.0 -spacing 1.0 -pitch 100.0 -offset 82.0 -number_of_straps 4 -nets {vdd_dac vss_dac} -extend_to_core_ring
add_pdn_stripe -grid "Core" -layer M9 -width 4.0 -spacing 1.0 -pitch 100.0 -offset 93.0 -number_of_straps 4 -nets {vdd_a vss_a} -extend_to_core_ring


# M1 horizontal stripes for standard cell power (follows standard cell rows)
add_pdn_stripe -grid "Core" -layer M1 -followpins -width 0.33

# add_pdn_stripe -grid "Core" -layer M1 -width 0.33 -pitch 3.6 -offset 0 -spacing 1.8 -nets {vdd_d vss_d}

# Connect M8 stripes to M9 rings
add_pdn_connect -grid "Core" -layers {M8 M9}

# Connect M1 to M8 through intermediate layers
add_pdn_connect -grid "Core" -layers {M1 M8}

# pdngen is automatically called by flow in scripts/pdn.tcl, line 6
