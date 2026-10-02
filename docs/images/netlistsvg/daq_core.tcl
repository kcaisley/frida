# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/daq_core.tcl
yosys -import
read_verilog -I libs/basil/basil/firmware/modules design/fpga/daq_core.v
blackbox seq_gen spi gpio fast_spi_rx
prep -top daq_core
select daq_core
write_json -selected docs/images/netlistsvg/daq_core_netlistsvg.json
