# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/adc_digital.tcl
yosys -import
read_verilog -lib design/hdl/clkgate.v design/hdl/salogic.v design/hdl/sampdriver.v
read_verilog design/hdl/adc_digital.v
prep -top adc_digital
select adc_digital
write_json -selected docs/images/netlistsvg/adc_digital_netlistsvg.json
