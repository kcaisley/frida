# CDL netlist generation for adc_digital design
# Generates CDL with power rails and all connectivity

write_cdl -masters "$::env(HOME)/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/tcbn65lplvt_200a.spi $::env(HOME)/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/fillers.cdl" \
  $::env(RESULTS_DIR)/6_final.cdl

# Strip all filler and decap instances from CDL
exec grep -Ev "XFILLER.*FILL1LVT|XFILLER.*DCAPLVT|XFILLER.*DCAP4LVT|XFILLER.*DCAP8LVT|XFILLER.*DCAP16LVT|XFILLER.*DCAP32LVT|XFILLER.*DCAP64LVT" $::env(RESULTS_DIR)/6_final.cdl > $::env(RESULTS_DIR)/6_final_nofill.cdl
exec mv $::env(RESULTS_DIR)/6_final_nofill.cdl $::env(RESULTS_DIR)/6_final.cdl

# Clean hierarchical separators for Cadence SPICE-In compatibility
# Remove all backslashes, replace / with _, then clean up double underscores
exec sed -i {s/\\//g; s/\//\_/g; s/__/_/g} $::env(RESULTS_DIR)/6_final.cdl

# Reorder .SUBCKT ports to match Verilog module definition
# This also adds vdd_d/vss_d from the `ifdef USE_POWER_PINS section
exec python3 $::env(HOME)/frida/design/tsmc65/reorder_subckt_ports.py \
    $::env(HOME)/frida/rtl/adc_digital.v \
    $::env(RESULTS_DIR)/6_final.cdl \
    $::env(HOME)/frida/spice/adc_digital.cdl \
    adc_digital

puts "CDL netlist generated with Verilog port order and hierarchical separators cleaned"
