# CDL netlist generation for adc_digital design
# Generates CDL with power rails and all connectivity

write_cdl -masters "$::env(HOME)/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/tcbn65lplvt_200a.spi $::env(HOME)/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/fillers.cdl" \
  $::env(RESULTS_DIR)/6_final.cdl

# Reorder .SUBCKT ports to match Verilog module definition
# This creates single-line format, adds *.PININFO, and cleans fillers/separators
# Power pins (vdd_d/vss_d) from `ifdef USE_POWER_PINS in Verilog
exec python3 $::env(HOME)/OpenROAD-flow-scripts/flow/designs/tsmc65/frida/clean_cdl.py \
    $::env(HOME)/frida/rtl/adc_digital.v \
    $::env(RESULTS_DIR)/6_final.cdl \
    $::env(HOME)/frida/spice/adc_digital.cdl \
    adc_digital

puts "CDL netlist generated with Verilog port order and hierarchical separators cleaned"
