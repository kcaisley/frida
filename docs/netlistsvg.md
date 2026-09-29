# Digital netlistsvg diagrams

Run these commands from the FRIDA repository root; `compmux.v` is a self-contained example.

```bash
mkdir -p build/analysis/netlistsvg_tutorial
yosys -Q -q -p 'read_verilog design/hdl/compmux.v; prep -top compmux; techmap; opt; write_json build/analysis/netlistsvg_tutorial/compmux.json'
```

netlistsvg uses the checked-in digital skin for symbols, wires, and labels.

```bash
npx --yes netlistsvg@1.0.2 build/analysis/netlistsvg_tutorial/compmux.json --skin flow/util/skins/circuitikz_openroad.svg -o build/analysis/netlistsvg_tutorial/compmux.svg
```

The SVG helper draws 0/1 tie bars and bus-width marks in the output image.

```bash
python3 flow/util/skins/postprocess_digital_svg.py build/analysis/netlistsvg_tutorial/compmux.svg build/analysis/netlistsvg_tutorial/compmux.json
```

Replace the Verilog path and top module for another design, and include its required source files in `read_verilog`.
