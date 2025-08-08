## Architecture

The codebase is organized around a multi-stage design workflow:

1. Design Generation (`src/`): Python scripts for behavioral modeling, CDAC design, and SPICE netlist generation
2. HDL Implementation (`hdl/`): Verilog RTL modules for digital logic and SPICE netlists for analog blocks
3. Analysis Tools (`src/utils/`, `src/runs/`): Post-simulation analysis and visualization utilities
4. Process Integration (`tech/`): PDK-specific configuration files (symlinked for tsmc28, tsmc65, nopdk)

Key architectural components:
- CDAC (Capacitive DAC): Binary-weighted and redundant weight generation algorithms
- SAR Logic: Digital control for successive approximation algorithm
- Comparator: High-speed differential comparator with strongarm latch
- Switch Control: Sampling and DAC switching logic

## Build Commands

### Verilog Simulation (HDL)
```bash
cd hdl/
make simulate mod=<module_name>    # Compile and simulate with iverilog
make synth mod=<module_name>       # Synthesize with yosys
make wave mod=<module_name>        # View waveforms with gtkwave
make list                          # List available modules
make clean                         # Clean generated files
```

Common modules: `adc`, `salogic`, `comp`, `caparray`, `spi`

## Key Files and Their Purpose

- `src/cdac.py`: CDAC weight generation with redundancy algorithms
- `src/spice.py`: SPICE simulation result analysis and visualization
- `src/behavioral.py`: High-level ADC behavioral models
- `hdl/adc.v`: Top-level ADC module with configurable resolution
- `hdl/salogic.v`: SAR algorithm digital control logic
- `hdl/comp.v`: Comparator interface and timing
- `hdl/Makefile`: Comprehensive build system for Verilog simulation/synthesis

## Environment Setup

### Required Tools
The following tools must be in `$PATH`:
- `klayout` - Layout viewer and editor
- `ngspice` - Open-source SPICE simulator
- `spectre` - Cadence SPICE simulator (commercial)
- `iverilog`, `vvp` - Icarus Verilog simulator
- `yosys` - Open-source synthesis tool
- `gtkwave` - Waveform viewer

### Python Dependencies
```bash
# Activate virtual environment first
source .venv313/bin/activate
pip install klayout spicelib blosc2 wavedrom PyQt5 numpy matplotlib pytest cocotb cocotbext-spi
```

## File Formats and Conventions

- SPICE netlists: `.sp` extension, compatible with both ngspice and spectre
- Raw files: Binary simulation results, use `nutbin` format for cross-tool compatibility
- Layout files: GDS format for physical design data
- Verilog: Standard SystemVerilog for RTL, with testbenches suffixed `_tb.v`

## Development Notes

- The project supports multiple PDKs through symlinked `tech/` directories
- SPICE simulations output to `raw` binary format for broad tool compatibility
- Verilog modules use parameterized designs (e.g., `Madc` for ADC resolution)
- SPICE netlist post-processing removes Yosys parameterization artifacts for clean simulation

## Git Commit Message Format

Follow these rules on each commit:

0. Don't add attributions to Claude in the commit messages, it really makes the commit history messy.
1. First line: 80 characters or less, summarize the general work done without making massive assumptions about purpose
2. Subsequent lines: Format with `- ` prefix, one entry per type of change made
3. Multiple files, one change type: Counts as one entry
4. One file, multiple change types: Create separate entries if changes are significant
5. Always push: After creating a commit, immediately push to origin with `git push`