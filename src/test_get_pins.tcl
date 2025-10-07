read_lef /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tsmc65_tech.lef
read_lef /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/tsmc65_stdcell.lef
read_lef /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lef/adc.lef
read_liberty /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lib/tcbn65lplvttc.lib
read_liberty /home/kcaisley/OpenROAD-flow-scripts/flow/platforms/tsmc65/lib/adc.lib
read_verilog /home/kcaisley/OpenROAD-flow-scripts/flow/results/tsmc65/core/base/1_synth.v
link_design frida_core


current_design frida_core
create_clock -name "seq_init" -period 5.000 [get_ports "seq_init"]
set_driving_cell -lib_cell "CKBD24LVT" [get_ports "seq_init"]
set adc_seq_init_pins [get_pins -hierarchical "adc_array\[*\].adc_inst/seq_init"]
set_max_delay 1.100 -from [get_ports seq_init] -to $adc_seq_init_pins -ignore_clock_latency