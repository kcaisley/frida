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

# ADC analog input pins - 16 pairs of vin_p/vin_n (M4)
# Arranged in 4x4 grid above ADC instances
# Instance 0 (bottom-left) to Instance 15 (top-right)

# Row 0 (bottom) - Instances 0-3
place_pin -pin_name {vin_p} -layer M6 -location {105.925 203.455}
place_pin -pin_name {vin_n} -layer M6 -location {133.715 203.455}
place_pin -pin_name {vin_p} -layer M6 -location {205.925 203.455}
place_pin -pin_name {vin_n} -layer M6 -location {233.715 203.455}
place_pin -pin_name {vin_p} -layer M6 -location {305.925 203.455}
place_pin -pin_name {vin_n} -layer M6 -location {333.715 203.455}
place_pin -pin_name {vin_p} -layer M6 -location {405.925 203.455}
place_pin -pin_name {vin_n} -layer M6 -location {433.715 203.455}

# Row 1 - Instances 4-7
place_pin -pin_name {vin_p} -layer M6 -location {105.925 303.455}
place_pin -pin_name {vin_n} -layer M6 -location {133.715 303.455}
place_pin -pin_name {vin_p} -layer M6 -location {205.925 303.455}
place_pin -pin_name {vin_n} -layer M6 -location {233.715 303.455}
place_pin -pin_name {vin_p} -layer M6 -location {305.925 303.455}
place_pin -pin_name {vin_n} -layer M6 -location {333.715 303.455}
place_pin -pin_name {vin_p} -layer M6 -location {405.925 303.455}
place_pin -pin_name {vin_n} -layer M6 -location {433.715 303.455}

# Row 2 - Instances 8-11
place_pin -pin_name {vin_p} -layer M6 -location {105.925 403.455}
place_pin -pin_name {vin_n} -layer M6 -location {133.715 403.455}
place_pin -pin_name {vin_p} -layer M6 -location {205.925 403.455}
place_pin -pin_name {vin_n} -layer M6 -location {233.715 403.455}
place_pin -pin_name {vin_p} -layer M6 -location {305.925 403.455}
place_pin -pin_name {vin_n} -layer M6 -location {333.715 403.455}
place_pin -pin_name {vin_p} -layer M6 -location {405.925 403.455}
place_pin -pin_name {vin_n} -layer M6 -location {433.715 403.455}

# Row 3 (top) - Instances 12-15
place_pin -pin_name {vin_p} -layer M6 -location {105.925 503.455}
place_pin -pin_name {vin_n} -layer M6 -location {133.715 503.455}
place_pin -pin_name {vin_p} -layer M6 -location {205.925 503.455}
place_pin -pin_name {vin_n} -layer M6 -location {233.715 503.455}
place_pin -pin_name {vin_p} -layer M6 -location {305.925 503.455}
place_pin -pin_name {vin_n} -layer M6 -location {333.715 503.455}
place_pin -pin_name {vin_p} -layer M6 -location {405.925 503.455}
place_pin -pin_name {vin_n} -layer M6 -location {433.715 503.455}

