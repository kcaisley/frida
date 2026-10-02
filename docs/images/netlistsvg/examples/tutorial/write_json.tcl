# Regenerate from the FRIDA root:
# yosys -Q -q -c docs/images/netlistsvg/examples/tutorial/write_json.tcl
# npx --yes netlistsvg@1.0.2 docs/images/netlistsvg/examples/tutorial/netlist.json --skin docs/images/netlistsvg/style.svg -o docs/images/netlistsvg/examples/tutorial/diagram.svg
# python3 docs/images/netlistsvg/postprocess.py docs/images/netlistsvg/examples/tutorial/diagram.svg docs/images/netlistsvg/examples/tutorial/netlist.json
yosys -import
read_verilog docs/images/netlistsvg/examples/tutorial/compmux.v
prep -top compmux
techmap
opt
write_json docs/images/netlistsvg/examples/tutorial/netlist.json
