# Verilog Simulation (HDL)
```bash
cd hdl/
make simulate mod=<module_name>    # Compile and simulate with iverilog
make synth mod=<module_name>       # Synthesize with yosys
make wave mod=<module_name>        # View waveforms with gtkwave
make list                          # List available modules
make clean                         # Clean generated files
```


- Verilog modules use parameterized designs (e.g., `Madc` for ADC resolution)
- SPICE netlist post-processing removes Yosys parameterization artifacts for clean simulation
- Standard Verilog for RTL, with testbenches suffixed `_tb.v`
- gtkwave is a great waveform viewer
- `iverilog`, `vvp` - Icarus Verilog simulator
- `yosys` - Open-source synthesis tool

- `hdl/adc.v`: Top-level ADC module with configurable resolution
- `hdl/salogic.v`: SAR algorithm digital control logic
- `hdl/comp.v`: Comparator interface and timing
- `hdl/Makefile`: Comprehensive build system for Verilog simulation/synthesis