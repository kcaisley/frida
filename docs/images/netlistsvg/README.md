# Netlistsvg diagram collection

Run from the repository root to regenerate the figures, PNG previews, and symbol catalogs.

```bash
python3 docs/images/netlistsvg/render.py
```

Include the analog and digital A/B comparisons using their saved JSON inputs.

```bash
python3 docs/images/netlistsvg/render.py --comparisons
```

Refresh the comparison JSON from the current ADC and DAQ Verilog first.

```bash
python3 docs/images/netlistsvg/render.py --comparisons --refresh-json
```

Render an individual digital JSON using the custom skin, bus labels, and tie symbols.

```bash
python3 docs/images/netlistsvg/render.py path/to/netlist.json --output path/to/diagram.pdf
```

Regenerate the skins from their geometry and bundled Latin Modern Mono font.

```bash
python3 docs/images/netlistsvg/generate_circuitikz_skins.py
```

`style.svg` is the digital skin; `circuitikz_analog.svg` is the analog skin. The helpers, font, and font license are alongside them. The original `preamp_netlistsvg.svg` is the curated FSIC figure; `preamp_custom.svg` is generated from the same Verilog with the custom analog skin. The two hand-drawn preamps retain their Circuitikz TeX sources.

`comparisons/` contains the saved analog and digital A/B figures, including archived and current-source digital inputs. `preamp_comparison/` also compares the old automatic analog renderer. `examples/` contains symbol demos, the exported HDL21 comparator, hierarchy examples, the tutorial fixtures, and the OBELIX RX reference Tcl and JSON. The OBELIX Tcl requires the separate `obelix1-daq` checkout and the Basil submodule.

The rendering commands require Yosys, Node/npm, netlistsvg 1.0.2 through npx, librsvg (`rsvg-convert`), Poppler (`pdftocairo`), and TeX Live (`pdflatex`). See [the generic Verilog tutorial](../../netlistsvg.md) for the basic Yosys-to-JSON flow.

The exported comparator example is diagram-only structural Verilog. Its capacitor B pin is declared as an output for netlistsvg placement, including a connection to the vss input, so Verilator digital elaboration reports ASSIGNIN. The hierarchy and tie examples pass Verilator in Verilog-2005 mode; the analog renderer is checked by the integration tests.
