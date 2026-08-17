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

ADC, comparator, sampler, and CDAC simulations use the same named-target
interface. Omitting the target prints the choices without generating or
running anything:

```bash
uv run python -m flow.adc.sim
uv run python -m flow.comp.sim
uv run python -m flow.samp.sim
uv run python -m flow.cdac.sim
```

Each target owns its reviewed parameter recipe and either prepares every deck
or runs every case. Netlist-only targets exercise the complete testbench and
parameter expansion without launching Spectre:

```bash
# ADC generated-view and extracted-view campaign decks
uv run python -m flow.adc.sim hdl21gen_noise_vs_rate_netlists
uv run python -m flow.adc.sim frida65a_noise_vs_rate_netlists

# All 297 comparator candidate decks
uv run python -m flow.comp.sim frida65_candidate_netlists

# Standalone sampler and CDAC decks
uv run python -m flow.samp.sim frida65_baseline_netlist
uv run python -m flow.cdac.sim frida65_baseline_netlist

# Fabricated-size comparator core netlist
uv run python -m flow.comp.sim frida65_baseline_netlist
```

## Circuit simulation

Simulation targets use the same interface and always create a fresh complete
run beneath `build/sim/<module>/<YYYYMMDD_HHMMSS>/`:

```bash
# Short executable checks
uv run python -m flow.adc.sim hdl21gen_noise_smoke
uv run python -m flow.adc.sim frida65a_noise_smoke
uv run python -m flow.comp.sim frida65_candidate_smoke

# Reviewed ADC noise campaigns
uv run python -m flow.adc.sim hdl21gen_noise_vs_rate
uv run python -m flow.adc.sim frida65a_noise_vs_rate

# Comparator campaigns
uv run python -m flow.comp.sim frida65_baseline_noise
uv run python -m flow.comp.sim frida65_candidates

# First standalone block-level simulations
uv run python -m flow.samp.sim frida65_baseline_transient
uv run python -m flow.cdac.sim frida65_baseline_transient
```

The ADC and comparator runners convert completed raw results to typed HDF5 in
each case directory. Sampler and CDAC retain the Spectre raw result and log;
their first standalone simulations do not yet have a measurement schema or an
analysis consumer. The comparator analysis validates the 297 typed HDF5 files
and their embedded candidate metadata directly, without a separate campaign
manifest. Accepted analysis directories remain explicit paths in
`flow.analysis.runner` and are updated manually after reviewing a run.

Executable targets intentionally write a compact standalone Spectre input and
invoke Spectre directly. This keeps the exact deck, log, raw data, and typed
HDF5 conversion together in each case directory. The shared code only
serializes a completed HDL21 `Sim`; campaign selection, parameters, and
execution remain owned by the named module target.

Each module sets `MAX_PARALLEL_SIMULATIONS` and
`SPECTRE_THREADS_PER_SIMULATION` at the top of its runner. The first limits the
number of concurrently executing cases; the second becomes Spectre's `+mt`
value for each case. Set their product to the intended total CPU allocation.
Simulation targets require `spectre` on `PATH`; source
`design/spice/workspace.sh` first when necessary.

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

Hardware acquisition uses explicit targets in the physical scan runner:

```bash
uv run python -m flow.scans.runner --help
```

The explicit ADC00--ADC03 slow-ramp campaign uses the same acquisition path:

```bash
uv run python -m flow.scans.runner adc_ramp_code_density
```

It records one four-million-conversion sawtooth capture per ADC for transfer,
code-density, DNL, and INL analysis. The stored DOUT is retained as the
uncalibrated result; BOUT can also be decoded in memory with the measured P/N
CDAC weights for the switching direction selected by each element's programmed
A-state. The A-state determines the direction of any physical change: an
element initially at zero can only rise, while one initially at one can only
fall. BOUT separately selects the final states imposed by the SAR logic:
`P_final = 1 - BOUT` and `N_final = BOUT`. Therefore BOUT does not always mean
"move P" or "move N". For one capacitor pair, the calibrated weight is the
distance between its two possible BOUT endpoints, equal to the sum of its
direction-matched P and N movements. The `adc_ramp_nonlinearity` analysis runner
performs this decoding.

```bash
uv run python -m flow.analysis.runner adc_ramp_nonlinearity
```

The maintained runner pins one reviewed ADC00--ADC03 ramp directory and the
reviewed CDAC campaign directories. It validates transport counters and capture
lengths, excludes eight conversions after each detected sawtooth flyback,
requires both decodings to be monotonic within 2 LSB, and writes the plots plus
one consolidated metrics CSV below a fresh `build/analysis/adc/` directory.

The digital-calibration flow compares three ways to derive backend BOUT weights
for ADC00. `calibration1.py` uses the direction-matched physical CDAC S-curves,
`calibration2.py` performs a nonnegative fit against the known ramp, and
`calibration3.py` extracts the all-zero/all-one prefix thresholds described by
Hsu. None changes the analog ADC. The two ramp-derived methods use disjoint
training and validation cycles, and the threshold method preserves nominal
ratios once the measured steps become noise-limited.

```bash
uv run python -m flow.analysis.runner adc_calibration
```

All three analyses return the same typed 17-weight result. The runner writes a
shared weight comparison, transfer, code-density, and INL/DNL plots plus metrics
and normalized-weight CSV files below one fresh `build/analysis/adc/` directory.
Every weight vector sums to 4095; rounding to a 12-bit integer is deferred until
the final backend output.

Run one explicitly named physical campaign through the shared scan runner:

```bash
uv run python -m flow.scans.runner adc_sine_conversion_rate
uv run python -m flow.scans.runner adc_fixed_input_noise_50mv
uv run python -m flow.scans.runner adc_ramp_code_density
uv run python -m flow.scans.runner comp_common_mode
uv run python -m flow.scans.runner cdac_cap_mismatch
```

Use `--help` to list every maintained ADC, comparator, CDAC, and repair target.
The target function owns the complete parameter recipe and passes its flat list
to the corresponding acquisition module. Each run writes one typed HDF5
measurement per parameter variant below a fresh timestamped `build/scan_adc/`,
`build/scan_comp/`, or `build/scan_cdac/` directory. The individual scan modules
are libraries and do not provide command-line entry points.

Behavioral and SPICE-backed scans use the same acquisition schema. The ADC
Spectre flow exposes one fixed-input noise campaign for each DUT view:

```bash
uv run python -m flow.scans.scan_behavioral
uv run python -m flow.adc.sim hdl21gen_noise_vs_rate
uv run python -m flow.adc.sim frida65a_noise_vs_rate
```

Use the corresponding `_netlists` target to generate every deck without
simulation, or the `_noise_smoke` target to run one short case without
transient noise. Results are written below a fresh
`build/sim/adc/<YYYYMMDD_HHMMSS>/`; omitting the target lists all choices.

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
