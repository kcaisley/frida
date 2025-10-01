# Read LEF files (technology first, then standard cells, then custom cells)
read_lef /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tsmc65_tech.lef
read_lef /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tsmc65_stdcell.lef

# Read liberty timing file
# I think this actually isn't necessary?
read_liberty /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lib/tcbn65lplvttc.lib

# Read Verilog netlist
read_verilog /home/kcaisley/OpenROAD-flow-scripts/flow/results/tsmc65/frida_adc_digital/base/1_2_yosys.v

# Link the design - this creates the network database needed for CDL conversion
link_design adc_digital

# Write CDL with master SPICE files
write_cdl -masters "/home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/spice/tcbn65lplvt_200a.spi" /home/kcaisley/OpenROAD-flow-scripts/flow/results/tsmc65/frida_adc/base/adc_digital.cdl

exit