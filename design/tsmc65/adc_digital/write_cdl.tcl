# CDL netlist generation for adc_digital design
# Generates CDL with power rails and all connectivity

write_cdl -masters "/home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/tcbn65lplvt_200a.spi /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/fillers.cdl" \
  $::env(RESULTS_DIR)/6_final.cdl

# Strip all filler and decap instances from CDL
exec grep -Ev "XFILLER.*FILL1LVT|XFILLER.*DCAPLVT|XFILLER.*DCAP4LVT|XFILLER.*DCAP8LVT|XFILLER.*DCAP16LVT|XFILLER.*DCAP32LVT|XFILLER.*DCAP64LVT" $::env(RESULTS_DIR)/6_final.cdl > $::env(RESULTS_DIR)/6_final_nofill.cdl
exec mv $::env(RESULTS_DIR)/6_final_nofill.cdl $::env(RESULTS_DIR)/6_final.cdl

# Add vdd_d vss_d to the .SUBCKT port list (after the last signal port)
exec sed -i {s/^+ seq_comp seq_init seq_samp seq_update$/+ seq_comp seq_init seq_samp seq_update vdd_d vss_d/} $::env(RESULTS_DIR)/6_final.cdl

# Copy CDL to frida/spice directory
exec cp $::env(RESULTS_DIR)/6_final.cdl /home/kcaisley/frida/spice/adc_digital.cdl
puts "Copied CDL to /home/kcaisley/frida/spice/adc_digital.cdl (filler removed, vdd_d/vss_d ports added)"
