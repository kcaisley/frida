# Run from the repository root: yosys -Q -q -c docs/images/netlistsvg/frida_core_1adc.tcl
yosys -import
read_verilog -lib design/hdl/adc.v design/hdl/spi.v
read_verilog -D COCOTBEXT_AMS design/hdl/frida_core_1chan.v
prep -top frida_core_1chan
select frida_core_1chan
write_json -selected docs/images/netlistsvg/frida_core_1adc_netlistsvg.json
