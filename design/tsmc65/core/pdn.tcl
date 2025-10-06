add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern VDD -power
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern VSS -ground

global_connect

# set_voltage_domain is non-physical, but adding it causes the DEf file to have a ROUTED keyword without a value which breaks it