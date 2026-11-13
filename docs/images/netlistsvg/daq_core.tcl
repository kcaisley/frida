# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/daq_core.tcl
yosys -import
# the Basil modules as pyproject.toml's daq_core design lists them (no `include`s)
read_verilog -I libs/basil/basil/firmware/modules libs/basil/basil/firmware/modules/seq_gen/seq_gen.v libs/basil/basil/firmware/modules/spi/spi.v libs/basil/basil/firmware/modules/gpio/gpio.v libs/basil/basil/firmware/modules/fast_spi_rx/fast_spi_rx.v design/fpga/daq_core.v
blackbox seq_gen spi gpio fast_spi_rx
prep -top daq_core
select daq_core
write_json -selected docs/images/netlistsvg/daq_core_netlistsvg.json
