# Usage

FRIDA commands run through the Python module that owns the operation:

```text
python -m flow.<block>.primitive
python -m flow.<block>.sim
python -m flow.util.netlist
python -m flow.scans.<scan>
```

There is no installed `flow` executable or separate build-system orchestration
layer. Run commands from the repository root through `uv`, for example:

```bash
uv run python -m flow.comp.sim --help
uv run python -m flow.comp.sim
```

Digital lint, simulation, synthesis, and implementation use their stock tools
directly.

## Layout primitives

The MOSFET and MOM-capacitor generators are directly executable modules:

```bash
uv run python -m flow.mosfet.primitive \
  [-t <tech>] [-m <mode>] [-v] [-o <dir>]

uv run python -m flow.momcap.primitive \
  [-t <tech>] [-m <mode>] [-v] [-o <dir>]
```

The transitional TSMC65 FRIDA capacitor-array generator is also preserved as:

```bash
uv run python -m flow.cdac.layout [-t tsmc65] <output.gds>
```

`flow.momcap.primitive` is the maintained source of truth for an individual
MOM capacitor. The CDAC layout module retains unique array placement, shielding,
via, routing, and pin logic, but still duplicates the older single-capacitor
geometry and must eventually instantiate the maintained MOM generator.

| Option | Values | Default |
|---|---|---|
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-v, --visual` | render the generated GDS | off |
| `-o, --out` | output directory | `build` |

```bash
uv run python -m flow.mosfet.primitive -t ihp130 -m max -v
```

## Circuit netlists

Each circuit testbench module generates its own netlists:

```bash
uv run python -m flow.<block>.sim netlist \
  [-t <tech>] [-m <mode>] [-f <format>] \
  [--scope <scope>] [--montecarlo] [-o <dir>]
```

This flag-driven interface remains for `samp` and `cdac`. Comparator generation
uses reviewed, zero-argument named targets instead:

```bash
# Fabricated-size comparator core only
uv run python -m flow.comp.sim frida65_baseline_netlist

# All 297 production decks, without simulation
uv run python -m flow.comp.sim frida65_candidate_decks
```

The generic sampler/CDAC netlist command uses the following options; they do
not apply to the named comparator targets.

| Option | Values | Default |
|---|---|---|
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `max` |
| `-f, --fmt` | `spectre`, `ngspice`, `verilog` | `spectre` |
| `--scope` | `dut`, `stim`, `full` | `full` |
| `--montecarlo` | add Monte Carlo analysis | off |
| `-o, --out` | output root | `build` |

`min` writes the first ten parameter variants; `max` writes all valid
variants. Results are written below `<output root>/<block>/`.

| Scope | Contents |
|---|---|
| `dut` | DUT subcircuit hierarchy only |
| `stim` | DUT plus testbench wrapper and stimulus |
| `full` | complete simulator input, including analyses and save commands |

`verilog` only supports `--scope dut`. Monte Carlo requires `--scope full`.

```bash
# CDAC stimulus wrapper without analysis commands
uv run python -m flow.cdac.sim netlist -t tsmc65 --scope stim
```

## Circuit simulation

The sampler and CDAC testbench modules retain the generic SPICE interface:

```bash
uv run python -m flow.<block>.sim simulate \
  [-t <tech>] [-m <mode>] [-s <simulator>] \
  [--montecarlo] [-o <dir>]
```

| Option | Values | Default |
|---|---|---|
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-s, --simulator` | `spectre`, `ngspice`, `xyce` | `spectre` |
| `--montecarlo` | add Monte Carlo analysis | off |
| `-o, --out` | output directory | `build` |

Simulation requires the selected simulator executable on `PATH` and a
configured simulation host.

```bash
# Full transient-noise FRIDA-size baseline
uv run python -m flow.comp.sim frida65_baseline_noise

# Two deterministic campaign shards, intended for separate simulation hosts
uv run python -m flow.comp.sim frida65_candidates_shard0
uv run python -m flow.comp.sim frida65_candidates_shard1

# After both shards have been collected under build/comp
uv run python -m flow.comp.sim frida65_reconvert_h5
uv run python -m flow.analysis.runner comp_candidate_sweep
```

Comparator cases are resumable beneath
`build/comp/frida65_candidate_scurve_power/candidates/`. Each completed case
contains `input.scs`, `result.raw`, `spectre.log`, and typed `result.h5` files.
The analysis target requires the complete 297-case manifest and writes its
Σ(W×L)-ordered noise, power, and settling comparison beneath
`build/analysis/comp`. It also writes a noise-versus-power trade-off plot for
valid, resolved candidates, with settling encoded by color and the fabricated
FRIDA comparator highlighted.

## Netlist conversion

Netlist utilities are subcommands of their owning module:

```bash
uv run python -m flow.util.netlist oa-to-cdl \
  --cdslib cadence/cds.lib --lib frida --cell core \
  --outdir build/netlist

uv run python -m flow.util.netlist cdl-to-sp \
  design/spice/core.cdl build/netlist/core.sp

uv run python -m flow.util.netlist clean-cdl \
  design/spice/core.cdl build/netlist/core.sp \
  --verilog design/hdl/frida_core.v --module frida_core
```

`clean-cdl` removes filler and decap instances and normalizes OpenROAD
hierarchy names. Pass `--verilog` and `--module` together to reorder the
subcircuit ports using a Verilog module declaration.

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
linting, synthesis, and physical implementation. The OpenROAD configuration is
under `design/`; see [`openroad.md`](openroad.md) for project-specific notes.

## ADC scans

Hardware acquisition is a direct Basil module:

```bash
uv run python -m flow.scans.scan_adc
```

Define the sweep in `flow/scans/params.py::build_variants()`. Each run writes
one typed HDF5 measurement per parameter variant below a fresh timestamped
`build/scan_adc/` directory. Each file contains the complete parameters,
instrument readbacks, all ADC conversions, and representative scope waveforms;
there is no separate CSV or manifest.

Behavioral and SPICE-backed scans use the same acquisition schema. The ADC
Spectre flow exposes one fixed-input noise campaign for each DUT view:

```bash
uv run python -m flow.scans.scan_behavioral
uv run python -m flow.adc.sim hdl21gen_noise_vs_rate
uv run python -m flow.adc.sim frida65a_noise_vs_rate
```

Add `--check` to generate every deck in one campaign and run one representative
100 ns case without transient noise. Results are written below
`build/adc/<target>/<YYYYMMDD_HHMM>/`; omitting the target lists all choices.

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
