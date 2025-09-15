# Multi-Domain Power Distribution Network for FRIDA Chip
# Top-level 1mm x 1mm die with pad ring and multiple power domains

####################################
# Global connections
####################################
# Digital domain connections
add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern {^vdd_d$} -power
add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern {^vss_d$} -ground

# Analog domain connections  
add_global_connection -net {vdd_a} -inst_pattern {.*} -pin_pattern {^vdd_a$} -power
add_global_connection -net {vss_a} -inst_pattern {.*} -pin_pattern {^vss_a$} -ground

# I/O domain connections
add_global_connection -net {vdd_io} -inst_pattern {.*} -pin_pattern {^vdd_io$} -power
add_global_connection -net {vss_io} -inst_pattern {.*} -pin_pattern {^vss_io$} -ground

# DAC domain connections
add_global_connection -net {vdd_dac} -inst_pattern {.*} -pin_pattern {^vdd_dac$} -power
add_global_connection -net {vss_dac} -inst_pattern {.*} -pin_pattern {^vss_dac$} -ground

global_connect

####################################
# Multiple voltage domains for chip
####################################
set_voltage_domain -name {DIGITAL} -power {vdd_d} -ground {vss_d}
set_voltage_domain -name {ANALOG} -power {vdd_a} -ground {vss_a}
set_voltage_domain -name {IO} -power {vdd_io} -ground {vss_io}
set_voltage_domain -name {DAC} -power {vdd_dac} -ground {vss_dac}

####################################
# Multi-domain PDN grids for chip
####################################
# Digital domain grid (core logic and SPI)
define_pdn_grid -name {digital_grid} -voltage_domains {DIGITAL}

# Analog domain grid (ADC analog blocks)  
define_pdn_grid -name {analog_grid} -voltage_domains {ANALOG}

# I/O domain grid (pad ring and I/O cells)
define_pdn_grid -name {io_grid} -voltage_domains {IO}

# DAC domain grid (capacitor arrays and drivers)
define_pdn_grid -name {dac_grid} -voltage_domains {DAC}

####################################
# Power stripe definitions
####################################
# Digital domain stripes (M4 vertical, M3 horizontal)
# Chip core area ~800um x 800um, so larger pitch needed
add_pdn_stripe -grid {digital_grid} -layer {M4} -width {2.0} -pitch {100.0} -offset {50.0} -nets {vdd_d vss_d}
add_pdn_stripe -grid {digital_grid} -layer {M3} -width {2.0} -pitch {80.0} -offset {40.0} -nets {vdd_d vss_d}

# Analog domain stripes (M8 vertical, M7 horizontal for maximum isolation)
# Dedicated high-level metal layers to minimize digital noise coupling
add_pdn_stripe -grid {analog_grid} -layer {M8} -width {4.0} -pitch {200.0} -offset {100.0} -nets {vdd_a vss_a}
add_pdn_stripe -grid {analog_grid} -layer {M7} -width {4.0} -pitch {150.0} -offset {75.0} -nets {vdd_a vss_a}

# I/O domain stripes (M6 vertical, M5 horizontal for pad ring)
# Cover pad ring area around chip perimeter
add_pdn_stripe -grid {io_grid} -layer {M6} -width {3.0} -pitch {120.0} -offset {60.0} -nets {vdd_io vss_io}
add_pdn_stripe -grid {io_grid} -layer {M5} -width {3.0} -pitch {100.0} -offset {50.0} -nets {vdd_io vss_io}

# DAC domain stripes (M5 vertical, M4 horizontal)
# Intermediate isolation level between analog and digital
add_pdn_stripe -grid {dac_grid} -layer {M5} -width {1.5} -pitch {80.0} -offset {40.0} -nets {vdd_dac vss_dac}
add_pdn_stripe -grid {dac_grid} -layer {M4} -width {1.5} -pitch {60.0} -offset {30.0} -nets {vdd_dac vss_dac}

####################################
# Via connections between metal layers
####################################
# Digital domain connections
add_pdn_connect -grid {digital_grid} -layers {M3 M4}
add_pdn_connect -grid {digital_grid} -layers {M2 M3}
add_pdn_connect -grid {digital_grid} -layers {M1 M2}

# Analog domain connections (isolated high-level metals)
add_pdn_connect -grid {analog_grid} -layers {M7 M8}
add_pdn_connect -grid {analog_grid} -layers {M6 M7}
add_pdn_connect -grid {analog_grid} -layers {M5 M6}

# I/O domain connections (for pad ring)
add_pdn_connect -grid {io_grid} -layers {M5 M6}
add_pdn_connect -grid {io_grid} -layers {M4 M5}
add_pdn_connect -grid {io_grid} -layers {M3 M4}

# DAC domain connections
add_pdn_connect -grid {dac_grid} -layers {M4 M5}
add_pdn_connect -grid {dac_grid} -layers {M3 M4}
add_pdn_connect -grid {dac_grid} -layers {M2 M3}

####################################
# Special handling for pad connections
####################################
# Connect pad power to respective domains at top metal layers
add_pdn_connect -grid {io_grid} -layers {M8 M9} -cut_pitch 4.0
add_pdn_connect -grid {analog_grid} -layers {M8 M9} -cut_pitch 4.0
add_pdn_connect -grid {digital_grid} -layers {M4 M9} -cut_pitch 2.0
add_pdn_connect -grid {dac_grid} -layers {M5 M9} -cut_pitch 2.0