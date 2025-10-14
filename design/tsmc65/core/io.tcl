# Custom I/O Placement for FRIDA Core Design
# Explicit pin placement using place_pin command
# Die area: 540x540um

# Left side - Early phase clock sequencing signals (M3)
place_pin -pin_name seq_init -layer M3 -location {0.0 260.0} -force_to_die_boundary
place_pin -pin_name seq_samp -layer M3 -location {0.0 81.0} -force_to_die_boundary

# Right side - Late phase clock sequencing signals (M3)
place_pin -pin_name seq_comp -layer M3 -location {540.0 260.0} -force_to_die_boundary
place_pin -pin_name seq_logic -layer M3 -location {540.0 81.0} -force_to_die_boundary

# Bottom side - SPI interface (M2, spaced 1um from x=140.1 to 143.1)
place_pin -pin_name spi_sclk -layer M2 -location {140.1 0.0} -force_to_die_boundary
place_pin -pin_name spi_sdi -layer M2 -location {141.1 0.0} -force_to_die_boundary
place_pin -pin_name spi_sdo -layer M2 -location {142.1 0.0} -force_to_die_boundary
place_pin -pin_name spi_cs_b -layer M2 -location {143.1 0.0} -force_to_die_boundary

# Bottom side - Comparator output and reset (M2)
place_pin -pin_name comp_out -layer M2 -location {300.1 0.0} -force_to_die_boundary
place_pin -pin_name reset_b -layer M2 -location {139.1 0.0} -force_to_die_boundary
