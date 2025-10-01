# Currently triggered by a command added in floorplan.tcl:
# as this should run after `link_design` but before `initialize_floorplan`

# See example: tools/OpenROAD/src/ifp/test/init_floorplan9.tcl

# A digital domain called CORE already exists, by default

# Top 1 row
create_voltage_domain DAC_TOP -area {0 55.8 60 59.4}

# analog macro area
create_voltage_domain ANALOG -area {20 28 40 48}

# create_voltage_domain DIGITAL -area {0 5.4 60 54.0}

# Bottom 1 row
create_voltage_domain DAC_BOTTOM -area {0 0 60 3.6}

puts "create_voltage_domains completed. (This should be be after link_design, but before initialize_floorplan)"