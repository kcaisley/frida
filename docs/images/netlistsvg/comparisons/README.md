# Netlistsvg A/B renderings

Run `python render.py` from this directory to regenerate every comparison.

`analog/comparison.pdf` compares the curated FSIC preamp figure with the new
skin; `analog/analog_catalog.pdf` shows the full analog symbol kit.
Digital A/B figures render the same JSON with netlistsvg's default
and FRIDA skins. DAQ inputs retain only the top module and shorten
generated `$paramod` type names. All `inout` block pins are mapped
to right-side `output` ports for presentation, since netlistsvg lacks
bidirectional placement by `prepare_digital_json.py`. The archived
patched JSON had already turned `inout` pins into inputs; this script
restores those directions from the unpatched JSON first.
The original and patched DAQ inputs become
identical after that mapping, so their A/B pages match exactly.
Current-source figures regenerate JSON from `design/hdl/adc_digital.v`
and `design/fpga/daq_core.v` with Yosys. The archived DAQ JSON has
24 top ports and one GPIO; current Verilog has 33 ports and three.
The current and archived ADC digital top-level renders are identical.
The FRIDA skin adds bus widths to block pins and terminals and draws a
diagonal width tick on each bus without changing the routing stroke.
`checked_in.pdf` retains the original documentation figure where present.
