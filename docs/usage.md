# Usage

FRIDA uses a `flow` CLI with four subcommands:

```
flow primitive   Generate layout primitives
flow netlist     Generate netlists
flow layout      Run place-and-route via OpenROAD
flow simulate    Run simulations
```

Run from the repo root with `uv run`:

```bash
uv run flow netlist -c comp -t ihp130
```

## Subcommands

### `flow primitive`

Generate layout primitives (GDS).

```bash
flow primitive -c <cell> -t <tech> -m <mode> [-v] [-o <dir>]
```

| Flag | Values | Default |
|------|--------|---------|
| `-c, --cell` | `mosfet`, `momcap` | (required) |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-v, --visual` | (flag) | off |
| `-o, --out` | output directory | `build` |

Example:

```bash
uv run flow primitive -c mosfet -t ihp130 -m max -v
```

### `flow netlist`

Generate netlists at varying levels of scope.

```bash
flow netlist -c <cell> -t <tech> -m <mode> [-f <fmt>] [--scope <scope>] [--montecarlo] [-o <dir>]
```

| Flag | Values | Default |
|------|--------|---------|
| `-c, --cell` | `samp`, `comp`, `cdac`, `adc` | (required) |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `max` |
| `-f, --fmt` | `spectre`, `ngspice`, `cdl`, `verilog` | `spectre` |
| `--scope` | `dut`, `stim`, `full` | `full` |
| `--montecarlo` | (flag) | off |
| `-o, --out` | output directory | `build/<cell>` |

The `--mode` flag controls how many parameter variants are generated:
`max` writes all valid combinations, while `min` writes only the first 10.

The `--scope` flag controls what is included in the generated netlist:

| Scope | Contents |
|-------|----------|
| `dut` | Subcircuit definitions only (DUT hierarchy) |
| `stim` | DUT subcircuits + testbench wrapper with stimulus sources and DUT instantiation |
| `full` | Complete simulator input: stim + analysis statements, options, and save commands |

The `cdl` and `verilog` formats only support `--scope=dut`. The `--montecarlo`
flag requires `--scope=full`.

Examples:

```bash
# Full sim-input netlist for comparator (all variants, default scope)
uv run flow netlist -c comp -t ihp130

# DUT-only subcircuit definitions in Verilog
uv run flow netlist -c comp -t ihp130 --scope dut -f verilog

# Testbench with stimulus but no analysis commands
uv run flow netlist -c adc -t tsmc65 --scope stim

# Full sim-input with Monte Carlo wrapper
uv run flow netlist -c comp -t ihp130 --montecarlo
```

### `flow layout`

Run place-and-route via OpenROAD. Requires `openroad` on `PATH`.

```bash
flow layout -c <cell> -t <tech> [-o <dir>]
```

| Flag | Values | Default |
|------|--------|---------|
| `-c, --cell` | `comp` | (required) |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-o, --out` | output directory | `build` |

Example:

```bash
uv run flow layout -c comp -t ihp130
```

### `flow simulate`

Generate netlists and run simulation. Requires a supported simulator on `PATH`
(or use `--host` for remote execution).

```bash
flow simulate -c <cell> -t <tech> -m <mode> [-s <sim>] [--host <host>] [--montecarlo] [-o <dir>]
```

| Flag | Values | Default |
|------|--------|---------|
| `-c, --cell` | `samp`, `comp`, `cdac`, `adc` | (required) |
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-s, --simulator` | `spectre`, `ngspice`, `xyce` | `spectre` |
| `--host` | remote hostname | local |
| `--montecarlo` | (flag) | off |
| `-o, --out` | output directory | `build/<cell>` |

Examples:

```bash
# Local Spectre simulation
uv run flow simulate -c comp -t ihp130 -m min -s spectre

# Remote simulation on jupiter
uv run flow simulate -c comp -t tsmc65 -s spectre --host jupiter
```

### `flow scan`

Measure or simulate the fabricated prototype ASIC in the full DUT harness, under various test modes.

```bash
flow scan --sequence [required]
```

```bash
--emulate [true,false] # configurations either physical hardware measurement, or emulated cosimulation with cocotb. Default is false, meaning physical hardware.
--channel [0,1,2,3,..15] # determines which channels receive sequencer, and which channel the compmux enables, goes into spi register.
--dacstate [four 16 bit numbers written in binary notation] # goes into spi register, states the dacp and dacn A (init state, always used) and B (final state, which is only used in dacmode=calib)
--dacmode [normal,calib] # whether to enable normal operation, or A->B state calibration mode. These are values in the spi register.
--diffcaps [true,false] # goes into spi register
--input [manual,ramp,sine,dc]  # determines an input sequencer from the external power supply. Manual meas I externally set it. the others come from a preset. list of input sequences, which are aligned to the sequence. Default is manual.
--sequence [none, adc, comp, calib] # determines which sequence to apply (in the hdl sequencer)
--rate [integer] # full sequence runs per second. Determines both the divider for the repeat rate of the sequencer, and the update rate on the input voltage]
--cycles [integer] # default = 1, for each input, number of repetitions of the sequencer/inputs. If more than one channel is selected, that provides a higher level of sweep.
--results [default=false, true]. # Determine if results are written just in output, or if they are actually saved to the files system in the path defined in the cli (I think the default is in frida/build/?)
```

# Installation

## Python Environment

FRIDA uses [`uv`](https://docs.astral.sh/uv/) to manage Python dependencies.
Clone the repo, install dependencies, and run the smoketest suite:

```bash
git clone --recursive git@github.com:kcaisley/frida.git
cd frida
uv sync
uv run pytest
```

`uv sync` creates a virtualenv and installs all pinned dependencies from the
lockfile. `uv run pytest` runs the test suite as a quick sanity check that the
environment is set up correctly.

## Spectre

FRIDA uses Cadence Spectre for signoff-oriented analog simulations. Ensure it
is installed and visible on `PATH` on whichever host runs the simulations.

```bash
which spectre
spectre -W
```

## Ngspice

FRIDA can also use `ngspice` for open-source simulation flows. The commands
below build from source; use either the Ubuntu path or the RHEL path depending
on your OS.

```bash
# Ubuntu 24.04 dependency install
sudo apt-get update
sudo apt-get install -y \
  build-essential autoconf automake libtool bison flex \
  libx11-6 libx11-dev libxaw7 libxaw7-dev libxmu6 libxmu-dev \
  libxext6 libxext-dev libxft2 libxft-dev \
  libfontconfig1 libfontconfig1-dev libxrender1 libxrender-dev \
  libfreetype6 libfreetype-dev libreadline8 libreadline-dev

# RHEL 9 dependency install
sudo dnf install -y epel-release
sudo dnf install -y \
  gcc gcc-c++ make autoconf automake libtool bison flex \
  libX11 libX11-devel libXaw libXaw-devel libXmu libXmu-devel \
  libXext libXext-devel libXft libXft-devel \
  fontconfig fontconfig-devel freetype freetype-devel \
  libXrender libXrender-devel readline-devel

# Clone and build
mkdir -p ~/libs
git clone https://git.code.sf.net/p/ngspice/ngspice ~/libs/ngspice
cd ~/libs/ngspice
./autogen.sh
mkdir -p release
cd release
../configure --with-x --enable-xspice --enable-cider --enable-openmp --with-readline=yes
make -j"$(nproc)"
sudo make install
sudo ldconfig

# Verify
which ngspice
ngspice --version
```

For waveform viewing, [`gaw`](https://www.rvq.fr/linux/gaw.php) is useful.
When producing raw binary files, ensure `utf_8` encoding is used for the
plaintext section.

## OpenROAD

FRIDA's digital implementation flow uses OpenROAD. The commands below clone,
build, and install system-wide to `/usr/local` following the upstream
[Build Guide](https://openroad.readthedocs.io/en/latest/user/Build.html).

```bash
git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git ~/libs/OpenROAD
cd ~/libs/OpenROAD

sudo ./etc/DependencyInstaller.sh -base
./etc/DependencyInstaller.sh -common -local
./etc/Build.sh
sudo make -C build install

# Verify
which openroad
openroad -version
```

## Remote SpiceServer Setup (for `--host`)

Use this when FRIDA runs on one machine and simulations run on a remote host
through `spice_server`.

Detailed build/runtime instructions and known-issue notes are in:

- [`docs/spice_server.md`](spice_server.md)
