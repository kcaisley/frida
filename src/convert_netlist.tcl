# Read LEF files (technology first, then standard cells, then custom cells)
read_lef /home/kcaisley/asiclab/tech/tsmc65/lef/tsmc65lplvt_9lmT2.lef
read_lef /home/kcaisley/asiclab/tech/tsmc65/lef/tcbn65lplvt_9lmT2.lef
read_lef /home/kcaisley/asiclab/tech/tsmc65/lef/sampswitch.lef
read_lef /home/kcaisley/asiclab/tech/tsmc65/lef/comp.lef
read_lef /home/kcaisley/asiclab/tech/tsmc65/lef/caparray.lef

# Read liberty timing file
# I think this actually isn't necessary?
read_liberty /home/kcaisley/asiclab/tech/tsmc65/lib/tcbn65lplvttc.lib

# Read Verilog netlist
read_verilog /home/kcaisley/OpenROAD-flow-scripts/flow/results/tsmc65/frida_adc/base/1_2_yosys.v

# Link the design - this creates the network database needed for CDL conversion
link_design adc

# Write CDL with master SPICE files
write_cdl -masters "/home/kcaisley/asiclab/tech/tsmc65/spice/tcbn65lplvt_200a.spi /home/kcaisley/frida/etc/sampswitch.cdl /home/kcaisley/frida/etc/comp.cdl /home/kcaisley/frida/etc/caparray.cdl" results/tsmc65/frida_adc/base/output.cdl

exit