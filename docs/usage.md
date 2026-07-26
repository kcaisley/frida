# Usage

FRIDA provides a small `flow` command for analog generation, simulation, and
netlist conversion:

```text
flow primitive   Generate layout primitives
flow netlist     Generate circuit and testbench netlists
flow simulate    Run SPICE simulations
flow convert     Convert OA/CDL netlists
```

Run commands from the repository root through `uv`:

```bash
uv run flow --help
uv run flow netlist --help
```

Digital lint, simulation, synthesis, and implementation use their stock tools
directly. There is no separate build-system orchestration layer.

## `flow primitive`

Generate GDS layout primitives:

```bash
uv run flow primitive -c <cell> [-t <tech>] [-m <mode>] [-v] [-o <dir>]
```

| Option | Values | Default |
|---|---|---|
| `-c, --cell` | `mosfet`, `momcap` | required |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-v, --visual` | open the result in KLayout | off |
| `-o, --out` | output directory | `build` |

```bash
uv run flow primitive -c mosfet -t ihp130 -m max -v
```

## `flow netlist`

Generate one or more netlists:

```bash
uv run flow netlist -c <cell> [-t <tech>] [-m <mode>] \
  [-f <format>] [--scope <scope>] [--montecarlo] [-o <dir>]
```

| Option | Values | Default |
|---|---|---|
| `-c, --cell` | `samp`, `comp`, `cdac`, `adc` | required |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `max` |
| `-f, --fmt` | `spectre`, `ngspice`, `verilog` | `spectre` |
| `--scope` | `dut`, `stim`, `full` | `full` |
| `--montecarlo` | add Monte Carlo analysis | off |
| `-o, --out` | output root | `build` |

`min` writes the first ten parameter variants; `max` writes all valid
variants. Results are written below `<output root>/<cell>/`.

| Scope | Contents |
|---|---|
| `dut` | DUT subcircuit hierarchy only |
| `stim` | DUT plus testbench wrapper and stimulus |
| `full` | complete simulator input, including analyses and save commands |

`verilog` only supports `--scope dut`. Monte Carlo requires `--scope full`.

```bash
# Complete Spectre input for all comparator variants
uv run flow netlist -c comp -t ihp130

# DUT-only Verilog
uv run flow netlist -c comp -t ihp130 --scope dut -f verilog

# Stimulus wrapper without analysis commands
uv run flow netlist -c adc -t tsmc65 --scope stim

# Complete input with Monte Carlo analysis
uv run flow netlist -c comp -t ihp130 --montecarlo
```

## `flow simulate`

Generate netlists and run a supported SPICE simulator:

```bash
uv run flow simulate -c <cell> [-t <tech>] [-m <mode>] \
  [-s <simulator>] [--host <host>] [--montecarlo] [-o <dir>]
```

| Option | Values | Default |
|---|---|---|
| `-c, --cell` | `samp`, `comp`, `cdac`, `adc` | required |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-s, --simulator` | `spectre`, `ngspice`, `xyce` | `spectre` |
| `--host` | remote SpiceServer hostname | local |
| `--montecarlo` | add Monte Carlo analysis | off |
| `-o, --out` | output directory | `build` |

Local simulation is restricted to the configured simulation hosts and requires
the selected simulator executable on `PATH`. Supplying `--host` delegates the
run to SpiceServer.

```bash
uv run flow simulate -c comp -t ihp130 -m min -s spectre
uv run flow simulate -c comp -t tsmc65 -s spectre --host jupiter
```

See [`spice_server.md`](spice_server.md) for remote-server setup.

## `flow convert`

Convert an OpenAccess schematic or an existing CDL file:

```bash
uv run flow convert --from <oa|cdl> --to <cdl|sp|sp_clean> \
  --outdir <dir> [source options]
```

| Source | Supported outputs | Required source options |
|---|---|---|
| OpenAccess | `cdl`, `sp`, `sp_clean` | `--cdslib`, `--oalib`, `--oacell` |
| CDL file | `sp`, `sp_clean` | `--file` |

`sp_clean` removes filler and decap instances and normalizes OpenROAD hierarchy
names. To reorder a subcircuit using a Verilog module declaration, pass
`--verilog` and `--module` together.

```bash
uv run flow convert \
  --from cdl --to sp \
  --file design/spice/core.cdl \
  --outdir build/netlist

uv run flow convert \
  --from oa --to sp_clean \
  --cdslib cadence/cds.lib --oalib frida --oacell core \
  --verilog design/hdl/frida_core.v --module frida_core \
  --outdir build/netlist
```

## Digital checks

The normal software test suite includes both SPI-register implementations as
cocotb tests. It uses Icarus by default:

```bash
uv run pytest
uv run pytest -q -s test/test_spi_register.py
```

Use another cocotb-supported simulator through `SIM`:

```bash
SIM=verilator uv run pytest -q -s test/test_spi_register.py
```

The simulator is a system dependency, not a Python package. For Ubuntu:

```bash
sudo apt install iverilog
```

Verible, Verilator, Yosys, and OpenROAD can likewise be run directly for
linting, synthesis, and physical implementation. The existing OpenROAD design
configuration is under `design/`; see [`openroad.md`](openroad.md) for the
project-specific notes.

## ADC scans

Hardware acquisition is a direct Basil workflow rather than a `flow`
subcommand. Define the sweep in `flow/scans/params.py::build_variants()`, then
run:

```bash
uv run python -m flow.scans.scan_adc
```

The script configures the supplies, input stimulus, chip, clocks, sequencer,
and FastRX. Each run writes typed acquisition CSV files and a manifest below a
fresh timestamped `build/scan_adc/` directory.

Behavioral and SPICE-backed scans use the same acquisition schema:

```bash
uv run python -m flow.scans.scan_behavioral
uv run python -m flow.scans.scan_spice
```

## Environment setup

Clone with submodules, create the environment, and run the software checks:

```bash
git clone --recursive git@github.com:kcaisley/frida.git
cd frida
uv sync
uv run pytest
```

Cadence Spectre, ngspice, Xyce, Icarus, KLayout, and OpenROAD are external
executables. Install only the tools needed for the workflows you run and make
them available on `PATH`.
