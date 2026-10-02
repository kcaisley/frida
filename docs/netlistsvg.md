# Digital netlistsvg diagrams

Save this as `write_json.tcl`, replacing the input file, top module, and JSON output placeholders.

```tcl
yosys -import
read_verilog path/to/input.v
prep -top top_module
techmap
opt
write_json path/to/netlist.json
```

For SystemVerilog, use `read_verilog -sv path/to/input.sv` instead; Yosys supports a subset of the language.

Read child files with `read_verilog -lib path/to/child.v` before the top file to keep their modules as boxes.

If a child is already loaded, run `blackbox child_module` before `prep`.

Run the script with Yosys; add other Verilog files to `read_verilog` when needed.

```bash
yosys -Q -q -c write_json.tcl
```

Point netlistsvg to the [digital skin](images/netlistsvg/style.svg) and the JSON output.

```bash
npx --yes netlistsvg@1.0.2 path/to/netlist.json --skin path/to/style.svg -o path/to/diagram.svg
```

The [SVG helper](images/netlistsvg/postprocess.py) reads JSON for bus widths, then adds width marks and 0/1 tie bars to the SVG.

```bash
python3 path/to/postprocess.py path/to/diagram.svg path/to/netlist.json
```
