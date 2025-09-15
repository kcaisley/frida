# Basic Power Distribution Network for FRIDA ADC
# Single domain approach for initial implementation

####################################
# Global connections
####################################
# Standard cell power connections - all use vdd_d/vss_d for now
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
# Single voltage domain
####################################
set_voltage_domain -name {Core} -power {vdd_d} -ground {vss_d}

####################################
# Basic PDN grid
####################################
# Core domain grid (all standard cells)
define_pdn_grid -name {core_grid} -voltage_domains {Core}

# Add Metal1 followpins for standard cells
add_pdn_stripe -grid {core_grid} -layer {Metal1} -width {0.17} -followpins

# Core domain stripes (Metal4 vertical, Metal3 horizontal)
add_pdn_stripe -grid {core_grid} -layer {Metal4} -width {0.48} -pitch {40.0} -offset {20.0}
add_pdn_stripe -grid {core_grid} -layer {Metal3} -width {0.48} -pitch {30.0} -offset {15.0}

# Core domain connections
add_pdn_connect -grid {core_grid} -layers {Metal1 Metal3}
add_pdn_connect -grid {core_grid} -layers {Metal3 Metal4}