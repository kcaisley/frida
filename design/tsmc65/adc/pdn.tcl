# Example: tools/OpenROAD/src/ppl/test/sky130hd/sky130hd.pdn.tcl
# N add_global_connection, 1 global_connect, 1 define_pdn_grid, N add_pdn_stripe, N add_pdn_connect
# for each macro then: 1 define_pdn_grid, 1 add_pdn_connect

# Example: tools/OpenROAD/src/pdn/test/asap7_M1_M3_followpins_staggered.tcl
# after read_lef , read_def:
# add_global_connection, set_voltage_domain, define_pdn_grid, add_pdn_stripe, add_pdn_connect
# only then run pdngen

add_global_connection -net vdd_d -pin_pattern VDD -power
add_global_connection -net vss_d -pin_pattern VSS -ground

add_global_connection -net vdd_dac -inst_pattern {.*capdriver.*} -pin_pattern VDD -power
add_global_connection -net vss_dac -inst_pattern {.*capdriver.*} -pin_pattern VSS -ground

add_global_connection -net vdd_a -pin_pattern vdd_a -power
add_global_connection -net vss_a -pin_pattern vss_a -ground


# Set voltage domains
# TEMP_ANALOG region created with the create_voltage_domain command
set_voltage_domain -name DIGITAL -power vdd_d -ground VSS
set_voltage_domain -region ANALOG -power VIN -ground VSS

# only 1 time
global_connect
