# Multi-Domain Power Distribution Network for FRIDA ADC
# Supports analog, digital, and DAC power domains

####################################
# Global connections
####################################
# Standard cell power connections 
# Capdriver standard cells use vdd_dac domain
add_global_connection -net {vdd_dac} -inst_pattern {.*capdriver.*} -pin_pattern {^VDD$} -power
add_global_connection -net {vss_dac} -inst_pattern {.*capdriver.*} -pin_pattern {^VSS$} -ground

# All other standard cells use vdd_d domain
add_global_connection -net {vdd_d} -pin_pattern {^VDD$} -power
add_global_connection -net {vss_d} -pin_pattern {^VSS$} -ground

# Module-level power connections (for macros with explicit power pins)
add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern {^vdd_d$} -power
add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern {^vss_d$} -ground

# Analog domain connections  
add_global_connection -net {vdd_a} -inst_pattern {.*} -pin_pattern {^vdd_a$} -power
add_global_connection -net {vss_a} -inst_pattern {.*} -pin_pattern {^vss_a$} -ground

# DAC domain connections
add_global_connection -net {vdd_dac} -inst_pattern {.*} -pin_pattern {^vdd_dac$} -power
add_global_connection -net {vss_dac} -inst_pattern {.*} -pin_pattern {^vss_dac$} -ground

global_connect

####################################
# Multiple voltage domains
####################################
set_voltage_domain -name {Core} -power {vdd_d} -ground {vss_d}
set_voltage_domain -name {ANALOG} -power {vdd_a} -ground {vss_a}  
set_voltage_domain -name {DAC} -power {vdd_dac} -ground {vss_dac}

####################################
# Multi-domain PDN grids
####################################
# Digital domain grid (most standard cells)
define_pdn_grid -name {digital_grid} -voltage_domains {Core}

# Add M1 followpins for digital standard cells
add_pdn_stripe -grid {digital_grid} -layer {M1} -width {0.17} -followpins

# Digital domain stripes (M4 vertical, M3 horizontal)
add_pdn_stripe -grid {digital_grid} -layer {M4} -width {0.48} -pitch {55.0} -offset {2.5}
add_pdn_stripe -grid {digital_grid} -layer {M3} -width {0.48} -pitch {25.0} -offset {12.5}

# Digital domain connections
add_pdn_connect -grid {digital_grid} -layers {M1 M3}
add_pdn_connect -grid {digital_grid} -layers {M3 M4}

# DAC domain grid (capdriver standard cells)
define_pdn_grid -name {dac_grid} -voltage_domains {DAC}

# Add M1 followpins for DAC standard cells  
add_pdn_stripe -grid {dac_grid} -layer {M1} -width {0.17} -followpins

# DAC domain stripes (same layers as digital, but separate nets due to physical separation)
add_pdn_stripe -grid {dac_grid} -layer {M4} -width {0.48} -pitch {40.0} -offset {20.0}
add_pdn_stripe -grid {dac_grid} -layer {M3} -width {0.48} -pitch {30.0} -offset {15.0}

# DAC domain connections
add_pdn_connect -grid {dac_grid} -layers {M1 M3}
add_pdn_connect -grid {dac_grid} -layers {M3 M4}

# Analog domain grid (analog macros only - no standard cells)
define_pdn_grid -name {analog_grid} -voltage_domains {ANALOG}

# Analog domain stripes (M6 vertical, M5 horizontal for isolation from digital/DAC)
add_pdn_stripe -grid {analog_grid} -layer {M6} -width {0.48} -pitch {30.0} -offset {15.0}
add_pdn_stripe -grid {analog_grid} -layer {M5} -width {0.48} -pitch {20.0} -offset {10.0}

# Analog domain connections
add_pdn_connect -grid {analog_grid} -layers {M5 M6}