# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/adc_top.tcl
yosys -import
read_verilog -lib design/hdl/clkgate.v design/hdl/salogic.v design/hdl/capdriver.v design/hdl/sampdriver.v design/hdl/caparray.v design/hdl/sampswitch.v design/hdl/comp.v
read_verilog design/hdl/adc.v
prep -top adc
select adc
write_json -selected docs/images/netlistsvg/adc_top_netlistsvg.json
