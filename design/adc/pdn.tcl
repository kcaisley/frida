# Multi-Domain Power Distribution Network for FRIDA ADC
# Supports analog, digital, and DAC power domains

####################################
# Global connections
####################################
# Digital domain connections
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
set_voltage_domain -name {DIGITAL} -power {vdd_d} -ground {vss_d}
set_voltage_domain -name {ANALOG} -power {vdd_a} -ground {vss_a}  
set_voltage_domain -name {DAC} -power {vdd_dac} -ground {vss_dac}

####################################
# Multi-domain PDN grids
####################################
# Digital domain grid
define_pdn_grid -name {digital_grid} -voltage_domains {DIGITAL}

# Analog domain grid  
define_pdn_grid -name {analog_grid} -voltage_domains {ANALOG}

# DAC domain grid
define_pdn_grid -name {dac_grid} -voltage_domains {DAC}

# Digital domain stripes (M4 vertical, M3 horizontal)
add_pdn_stripe -grid {digital_grid} -layer {M4} -width {0.48} -pitch {55.0} -offset {2.5} -nets {vdd_d vss_d}
add_pdn_stripe -grid {digital_grid} -layer {M3} -width {0.48} -pitch {25.0} -offset {12.5} -nets {vdd_d vss_d}

# Analog domain stripes (M6 vertical, M5 horizontal for isolation)
add_pdn_stripe -grid {analog_grid} -layer {M6} -width {0.48} -pitch {30.0} -offset {15.0} -nets {vdd_a vss_a}
add_pdn_stripe -grid {analog_grid} -layer {M5} -width {0.48} -pitch {20.0} -offset {10.0} -nets {vdd_a vss_a}

# DAC domain stripes (M4 vertical, M3 horizontal, shared with digital but separate nets)
add_pdn_stripe -grid {dac_grid} -layer {M4} -width {0.48} -pitch {40.0} -offset {20.0} -nets {vdd_dac vss_dac}
add_pdn_stripe -grid {dac_grid} -layer {M3} -width {0.48} -pitch {30.0} -offset {15.0} -nets {vdd_dac vss_dac}

# Digital domain connections
add_pdn_connect -grid {digital_grid} -layers {M3 M4}
add_pdn_connect -grid {digital_grid} -layers {M1 M3}

# Analog domain connections
add_pdn_connect -grid {analog_grid} -layers {M5 M6}
add_pdn_connect -grid {analog_grid} -layers {M3 M5}

# DAC domain connections
add_pdn_connect -grid {dac_grid} -layers {M3 M4}
add_pdn_connect -grid {dac_grid} -layers {M1 M3}