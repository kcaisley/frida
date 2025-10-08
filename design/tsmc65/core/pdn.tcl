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

# set_voltage_domain is non-physical, but adding it causes the DEf file to have a ROUTED keyword without a value which breaks it