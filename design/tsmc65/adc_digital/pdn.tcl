add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern VDD -power
add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern VSS -ground

global_connect

set_voltage_domain -power vdd_d -ground vss_d
define_pdn_grid -name "Core" -pins {M4}


# pitch 11.11 is a dummy value, as we are only add one stripe per command
add_pdn_stripe -grid "Core" -layer M4 -width 0.4 -offset 1.3 -number_of_straps 1 -nets {vdd_d} -pitch 11.11
add_pdn_stripe -grid "Core" -layer M4 -width 0.4 -offset 2.1 -number_of_straps 1 -nets {vss_d} -pitch 11.11

add_pdn_stripe -grid "Core" -layer M4 -width 0.4 -offset 57.9 -number_of_straps 1 -nets {vss_d} -pitch 11.11
add_pdn_stripe -grid "Core" -layer M4 -width 0.4 -offset 58.7 -number_of_straps 1 -nets {vdd_d} -pitch 11.11

# M1 horizontal stripes for standard cell power (follows standard cell rows)
# PDN will naturally avoid the dummy macro instances placed in analog regions
add_pdn_stripe -grid "Core" -layer M1 -followpins -width 0.33

# Connect M1 to M4 through intermediate layers
add_pdn_connect -grid "Core" -layers {M1 M4}

puts "NOTE: creating M1 strips following pins, which unfortunatley are ignoring all manuallly placed blockages and obstructions"