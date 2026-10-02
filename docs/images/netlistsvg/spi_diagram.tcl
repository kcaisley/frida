# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/spi_diagram.tcl
yosys -import
read_verilog design/hdl/spi.v
prep -top spi_register
select spi_register
write_json -selected docs/images/netlistsvg/spi_diagram.json
