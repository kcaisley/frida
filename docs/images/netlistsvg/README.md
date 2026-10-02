# Netlistsvg diagrams

Regenerate the six diagrams from their current Verilog sources.

```bash
python3 docs/images/netlistsvg/render.py
```

Give diagram names to rebuild only those figures.

```bash
python3 docs/images/netlistsvg/render.py preamp daq_core
```

| Diagram | Verilog source | Skin |
| --- | --- | --- |
| `preamp` | [preamp_netlistsvg.v](preamp_netlistsvg.v) | Analog |
| `adc_digital` | [adc_digital.v](../../../design/hdl/adc_digital.v) | Digital |
| `adc_top` | [adc.v](../../../design/hdl/adc.v) | Digital |
| `daq_core` | [daq_core.v](../../../design/fpga/daq_core.v) | Digital |
| `frida_core_1adc` | [frida_core_1chan.v](../../../design/hdl/frida_core_1chan.v) | Digital |
| `spi_diagram` | [spi.v](../../../design/hdl/spi.v) | Digital |

Run commands from the repository root; each pipeline writes one JSON, SVG, PDF, and PNG beside these scripts.

The digital Tcl files load the required child modules as boxes and select only the top module for JSON export.

`render.py` prepares inout ports for netlistsvg, renders with `style.svg`, and applies `postprocess.py` for tie symbols and bus widths.

The preamp uses `verilog_schematic.py` to normalize MOS devices and render with `circuitikz_analog.svg`.

The handwritten `preamp_test.tex` and `preamp_pmos.tex` figures remain separate Circuitikz sources, built by the documentation makefile.

Regenerate the skins from the bundled font and symbol geometry.

```bash
python3 docs/images/netlistsvg/generate_circuitikz_skins.py
```

Requires Yosys, Node/npm, netlistsvg 1.0.2 through npx, `rsvg-convert`, and `pdftocairo`; DAQ also requires the Basil submodule.

See [the generic Verilog tutorial](../../netlistsvg.md) for the individual Yosys and netlistsvg commands.
