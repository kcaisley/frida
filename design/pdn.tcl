# Minimal Power Distribution Network for FRIDA ADC
# Single domain with minimal grid for testing

####################################
# Global connections
####################################
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground
global_connect

####################################
# Single voltage domain
####################################
set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

####################################
# Minimal PDN grid
####################################
define_pdn_grid -name {grid} -voltage_domains {CORE}

# Vertical M4 strips at design edges only
# Design width is 60µm, so pitch of ~55µm puts strips only at edges
add_pdn_stripe -grid {grid} -layer {M4} -width {0.48} -pitch {55.0} -offset {2.5} -nets {VDD VSS}

# Horizontal M3 strips spanning the design
# Design height is 55µm, so pitch of ~25µm gives a few horizontal strips
add_pdn_stripe -grid {grid} -layer {M3} -width {0.48} -pitch {25.0} -offset {12.5} -nets {VDD VSS}

# Connect M4 vertical strips to M3 horizontal strips
add_pdn_connect -grid {grid} -layers {M3 M4}

# Connect M3 strips down to M1 standard cell power rails
add_pdn_connect -grid {grid} -layers {M1 M3}