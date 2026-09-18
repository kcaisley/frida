# Usage

ADC capacitor stages, comparator decisions, and output codes follow the
[project-wide ADC convention](adc_conventions.md): C0 is the largest and first
capacitor, B0..B16 are chronological decisions, and DOUT is the 12-bit result
formed from all 17 decisions.

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

The MOSFET primitive generator is a directly executable module:

```bash
uv run python -m flow.mosfet.primitive \
  [-t <tech>] [-m <mode>] [-v] [-o <dir>]

```

Capacitor layouts are generated only as arrays; the standalone unit-capacitor
layout exporter has been removed. The process-independent capacitor-array block
is `flow.caparray` (formerly `flow.cdac`). `CapArrayConfig` holds electrical sizing;
`CapArray(CapArrayParams(...))` generates the passive main/diff network, and
`CapArrayLayout(CapArrayLayoutParams(...))` generates its layout. The separate
`flow.capdriver.CapDriver` generates generic standard-cell XOR drivers and
requires PDK compilation. `DrivenCapArray(CapArrayConfig(...))` retains the
simplified integrated simulation wrapper, with inversion tied low. Existing
`cdac` parameter fields and CDAC measurement names remain unchanged; the HDF5
reader migrates saved parameter type names from the old module.

The process-independent FRIDA capacitor-array runners are:

```bash
uv run python -m flow.caparray.layout
uv run python -m flow.caparray.layout caparray_1layer_radix17
uv run python -m flow.caparray.layout caparray_2layer_radix17
uv run python -m flow.caparray.layout caparray_3layer_radix17
```

Each target visibly constructs its electrical `CapArrayConfig`, unit family, and
metal stack. The generator derives every physical distance from the selected
PDK, builds the complete `1..coarse_weight` unit family, partitions arbitrary
positive electrical weights through the shared netlist decomposition, and
adds routing, shield taps, connection stacks, and pins. A named target always
runs `gdscheck`, foundry Calibre DRC/LVS, and xACT PEX. Results are written to
`build/layout/caparray/<target>/<timestamp>/`.

FRIDA-2/CDAC targets now use the shared `ringfmom.cdl` ideal/LVS model and
three recognition purposes, with a read-only foundry LVS include and explicit
3D xACT extraction. See [ringfmom integration](../pdk/tsmc65/calibre/ringfmom.md)
for model limits, diagnostics, and PEX double-counting protection. Nominal C
uses the same affine fit as LVS: 0.17L + 0.03, 0.34L + 0.06, and 0.51L + 0.12
for one, two, and three active layers (C in fF, full inner-finger L in um).
Each physical main/diff finger receives one intercept, including every coarse
chunk and minimum-length tail; it is not a single offset per electrical net.
This replaces generic `unit_cap` sizing only for these generated ringfmom
arrays; historical FRIDA-1 and generic HDL21 sizing are unchanged.
LVS measures geometry independently and its 5% tolerance is unchanged.
All ten recorded xACT 3D samples per stack, including 0.52/51.72 um endpoints,
agree within 2%; this is in-sample agreement, not independent qualification.
New PEX remains gated on LVS; simulation targets still pin the previously
reviewed extraction timestamps.

ADC layout validation and extraction use the same named-target convention as
simulation. Omitting the target lists the four archived FRIDA-1 ADCs and three
generated FRIDA-2 stacks:

```bash
uv run python -m flow.adc.layout
uv run python -m flow.adc.layout frida1_1layer_radix17
uv run python -m flow.adc.layout frida1_2layer_radix20
uv run python -m flow.adc.layout frida2_2layer_radix17
uv run python -m flow.adc.layout frida2_3layer_radix17
```

A target always generates and runs the complete signoff sequence. The DRC
stage includes the PDK-local `gdscheck` ADC suite before foundry Calibre DRC.
Results are isolated beneath `build/layout/adc/<target>/<timestamp>/`. Each
result contains the exact GDS and source CDL used, a recognition-only GDS diff
where applicable, generated decks and logs, DRC/LVS reports, coupling and
net-summary reports, and the final RC-plus-coupling `*.pex.netlist`. xACT stops
unless its own conductive-source LVS comparison is correct.

For FRIDA-1, the run-local layout copy adds only PDK-local non-mask MOM
recognition shapes; the archived source and GDS are never modified. The normal
LVS source contains the intended per-layer capacitor network. Thus the old
one-layer layout must report `CORRECT`, while the known disconnected upper
layer in an old two-layer layout must report the expected connectivity warning.
The separate conductive PEX source omits the electrically empty CDAC wrappers
so xACT extracts the fabricated connectivity.

The FRIDA-2 targets regenerate their CDAC GDS and ideal per-chunk MOM source
network from the target's `CapArrayConfig` and PDK rules, then perform strict block
substitution in `build/frida-2-template.gds`. The assembler requires identical
database units, boundaries, pin names, pin positions, and pin shapes. It never
edits, moves, or reroutes layout; any required template adjustment is made
manually in KLayout. The M5-M7 caparray itself contains no M3 and uses M4 as a
partitioned shared layer: 100 nm plate routes occupy the two edge corridors
while the shield remains beneath the central capacitor body.

| Option | Values | Default |
|---|---|---|
| `-t, --tech` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` | `ihp130` |
| `-m, --mode` | `min`, `max` | `min` |
| `-v, --visual` | render the generated GDS | off |
| `-o, --out` | output directory | `build` |

```bash
uv run python -m flow.mosfet.primitive -t ihp130 -m max -v
```

## Circuit simulation targets

ADC, comparator, sampler, and CDAC simulations use the same named-target
interface. Omitting the target prints the choices without generating or
running anything:

```bash
uv run python -m flow.adc.sim
uv run python -m flow.comp.sim
uv run python -m flow.samp.sim
uv run python -m flow.caparray.sim
```

Each target owns its reviewed parameter recipe. Short, noise-free Spectre
diagnostics use the same Python target with `check=True`, through pytest only:

```bash
source /eda/local/scripts/cadence_2024-25.sh
uv run pytest -m spectre
# Select just one worker campaign's preflight, if needed:
uv run pytest -m spectre -k 'adc-frida2_sequence'
```

Allow roughly one hour for the full Spectre suite on asiclab003; runtime depends
on the host and available resources. Run the full group occasionally or after
broad simulation-flow changes, not after every edit. For routine changes, use
`-k` to select the tests covering the affected block or experiment. "Short"
describes the simulated time, not the wall-clock runtime of extracted circuits.

The `spectre` group is excluded by default and requires no custom pytest flag.
It covers the maintained ADC, comparator, sampler and capacitor-array targets,
including six representative comparator cases. Artifacts and diagnostic reports remain beneath timestamped
`build/diagnostics/` directories. Missing Spectre or an unavailable PDK installation
skips with a reason; missing configured inputs, invalid decks, license failures,
and simulator errors fail. Circuit-check findings remain available in reports;
these diagnostics are not comprehensive circuit signoff. There are no CLI
diagnostic flags, netlist-only modes, or separate check targets.

## Circuit simulation

Simulation targets use the same interface and always create a fresh complete
run beneath `build/sim/adc/<YYYYMMDD_HHMMSS>_<target>/` for ADCs.
Other blocks retain `build/sim/<module>/<target>/<YYYYMMDD_HHMMSS>/`:

```bash
# Reviewed ADC campaigns
uv run python -m flow.adc.sim hdl21_sample_rate
uv run python -m flow.adc.sim frida1_sample_rate
uv run python -m flow.adc.sim frida1_sequence
uv run python -m flow.adc.sim frida2_sequence
uv run python -m flow.adc.sim hdl21_transfer_curve
uv run python -m flow.adc.sim frida1_transfer_curve

# Comparator campaigns
uv run python -m flow.comp.sim hdl21_comp_perf_vs_size
uv run python -m flow.comp.sim frida1_fixed_input_noise

# First standalone block-level simulations
uv run python -m flow.samp.sim frida1_transient
uv run python -m flow.caparray.sim frida1_transfer_curve
```

The extracted fixed-input rate sweep groups the one-layer and two-layer radix-17
and radix-20 ADCs beneath one timestamped run. Each flavor has its own named
subdirectory containing the 2, 6, and 10 MS/s results. Independent cases run
concurrently within a fixed worker budget, while retaining one coherent
campaign directory.

The ADC and comparator runners convert completed raw results to typed HDF5 in
each case directory. Sampler and CDAC retain the Spectre raw result and log;
their standalone runners do not yet invoke the existing typed measurement and
analysis path. The comparator analysis validates the 297 typed HDF5 files
and their embedded candidate metadata directly, without a separate campaign
manifest. Accepted analysis directories remain explicit paths in
`flow.analysis.runner` and are updated manually after reviewing a run.

Every executable target builds one native HDL21 `Sim` per parameter variant
and calls `Sim.run()` or `hs.run()` with the timestamped output as the VLSIR
run directory. ADC and comparator batches use isolated spawned processes.
The comparator campaign runs 24 workers with one Spectre thread each; the
single-case sampler and CDAC targets run directly. ADC and comparator convert
the returned transient to typed HDF5 before releasing it; the standalone
sampler and CDAC targets retain the native raw result without converting it.
VLSIR retains the generated `netlist.scs` in every run directory, so a separate
netlist-writing layer or target is unnecessary.

Concurrency and each case's Spectre `+mt` setting are visible in the target
which owns the campaign. Simulation targets require `spectre` on `PATH`; source
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
uv run python -m flow.scans.runner adc_activity_noise
uv run python -m flow.scans.runner adc_transfer_curve
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
direction-matched P and N movements. `adc_calibration_study` compares this
CDAC-based decoder with the ramp-derived calibration methods.

`adc_ramp_nonlinearity_study` independently plots the ADC00--ADC03 uncalibrated
code density and INL/DNL. It assumes uniform ramp occupancy, excludes eight
conversions after each detected flyback and excludes saturated endpoints from
linearity. It does not reconstruct absolute voltage or require CDAC files.

The digital-calibration flow compares three ways to derive backend BOUT weights
for ADC00. `calibration1.py` uses the direction-matched physical CDAC S-curves,
`calibration2.py` performs a nonnegative fit against the known ramp, and
`calibration3.py` extracts the all-zero/all-one prefix thresholds described by
Hsu. None changes the analog ADC. The two ramp-derived methods use disjoint
training and validation cycles, and the threshold method preserves nominal
ratios once the measured steps become noise-limited.

```bash
uv run python -m flow.analysis.runner adc_calibration_study
```

All three analyses return the same typed 17-weight result. The runner writes a
shared weight comparison, transfer, code-density, and INL/DNL plots plus metrics
and normalized-weight CSV files below one fresh `build/analysis/adc/` directory.
Every weight vector sums to 4095; rounding to a 12-bit integer is deferred until
the final backend output.

The `connections` table in `flow/scans/map_scope.yaml` records the actual
oscilloscope hookup. Update it whenever probes move and omit unconnected
signals. Scans derive acquisition and trigger channels from this table;
hardware tests declare required signals with `@pytest.mark.scope_signals(...)`
and skip before hardware initialization when a required probe is absent.
The four-clock test requires INIT, SAMP, COMP, and LOGIC. ADC scope captures
can omit `vin_diff`; its measurement waveform then remains absent.

Run one explicitly named physical campaign through the shared scan runner:

```bash
uv run python -m flow.scans.runner adc_sequence_static
uv run python -m flow.scans.runner adc_sample_rate_static
uv run python -m flow.scans.runner adc_ramp_code_density
uv run python -m flow.scans.runner comp_common_mode
uv run python -m flow.scans.runner cdac_cap_mismatch
```

Use `--help` to list every maintained ADC, comparator, CDAC, and repair target.
ADC campaigns write `build/scan_adc/<timestamp>_<target>/0000_capture.h5`,
`0001_capture.h5`, etc. The file index identifies a capture within the run;
ADC selection, full sequence rows, stimulus, rails and rates are in the HDF5.
Every runner keeps its selected ADCs visible beside a commented all-16 option
for the longer scans. Acquisition creates no plots and does not modify the
analysis studies' pinned input directories.

`adc_sequence_static` uses manual 50 mV differential input, 700 mV common mode,
and 1.2 V rails. It scans all 16 ADCs and all 65 catalogue sequences at
2/6/10 nominal MSPS, with 100,000 conversions per point (3,120 captures).
Nominal MSPS uses a fixed 160-symbol reference for every recipe: 2/6/10 MSPS
means 320/960/1600 MBd. Actual active conversion and repetition rates remain
separate saved quantities; no recipe-specific baud-rate adjustment is applied.

`adc_sample_rate_static` uses the same manual setup for ADC00–03 and 39 rates from
0.5 to 10 nominal MSPS in 0.25-MSPS steps, with 1,000 conversions per point.
Its 4–5 sequence choices remain TODO: the CLI stops before hardware access
until its local shortlist contains the selected complete named sequences.
Both use `scan_adc_noctl`, including one four-channel scope record per point
and the existing scope/FastRX bit comparison after startup-frame alignment.
Scope records and comparison status/mismatch counts are saved in HDF5.

`adc_activity_noise` compares one active ADC with all 16 active. Transfer and ramp-code-density acquisitions remain
separate.

Some combinations deliberately raise LOGIC before COMP falls; the full cross
product is retained to investigate both pulse width and relative edge timing.
The names encode the complete configuration, for example
`symbol160_init4_samp20_comp11111100_logic11000011`. Independent channel rows
are private to the sequence library; callers import complete named sequences
or select them from the flat `SEQUENCES` catalogue. The simulation runner
selects its four comparison recipes by their full names.
It controls only the FPGA, with no instrument connections or scope capture.

For this investigation, compare full code histograms and B0--B16 trajectories
against the historical control at the same symbol rate. Check RMS noise, the
entire populated code span, rare distant bins, and repeated late-bit tails;
low RMS alone is not evidence of a healthy conversion. The screening target is
RMS at most 2 LSB and full populated span at most 4 LSB, with a non-stuck
trajectory. Keep every acquired code when computing these metrics.
Acquisition and analysis are separate. Explicitly select the completed directory
in `adc_sequence_study`, then invoke that study to write its trajectory and
full code-distribution PDFs into one flat analysis output directory. Review
candidate recipes with repeated captures before accepting recovered performance.

Scope/FastRX verification at 1600 MBd does not validate 960 MBd automatically.
Before accepting the slower results, compare simultaneous scope and FastRX
records using the rate-specific receiver model and verify COMP/LOGIC pulse
levels. A 960 MBd active conversion lasts about 166.7 ns, so a 120 ns scope
window cannot include all seventeen decisions. Retain the 7/8 scope reference
as a separate timing diagnostic, rather than treating its differences as
FastRX decode failures.

The target function owns the complete parameter recipe. ADC targets iterate
their flat list and pass one configuration plus its lifecycle position to the
acquisition module; comparator and CDAC targets pass their complete lists.
Each run writes one typed HDF5
measurement per parameter variant below a fresh timestamped `build/scan_adc/`,
`build/scan_comp/`, or `build/scan_cdac/` directory. The individual scan modules
are libraries and do not provide command-line entry points.

Behavioral and SPICE-backed scans use the same acquisition schema. The ADC
Spectre flow exposes one fixed-input noise campaign for each DUT view:

```bash
uv run python -m flow.scans.scan_behavioral
uv run python -m flow.adc.sim hdl21_sample_rate
uv run python -m flow.adc.sim frida1_sample_rate
```

Use the `spectre` pytest group for short diagnostics with circuit checks and
AHDL linting. Normal CLI runs write below a fresh
`build/sim/adc/<YYYYMMDD_HHMMSS>_<target>/`; omitting the target lists all choices.

For the extracted-layout comparison, `frida1_sequence` selects all four
historical flavors and `frida2_sequence` selects the connected one-,
two-, and three-layer radix-17 variants. Each case uses 100 conversions, 50 mV
differential input, 700 mV common mode, 1.2 V supplies, and transient device noise. These reuse
the same testbench and result conversion as the rate-sweep targets.

```bash
uv run pytest -m spectre -k 'adc and sequence'
uv run python -m flow.adc.sim frida1_sequence
uv run python -m flow.adc.sim frida2_sequence
uv run python -m flow.analysis.runner adc_sequence_study
```

The analysis entrypoints select their input directories in source:

```bash
uv run python -m flow.analysis.runner adc_transfer_curve_study
uv run python -m flow.analysis.runner adc_ramp_nonlinearity_study
uv run python -m flow.analysis.runner adc_calibration_study
uv run python -m flow.analysis.runner adc_sequence_study
uv run python -m flow.analysis.runner adc_sample_rate_study
uv run python -m flow.analysis.runner adc_power_study
```

Each takes only `output_dir: Path` in Python. The CLI accepts a study name;
there is no input-directory override. Docstrings identify the selected ADCs,
rate/sequence limits and requirements for `MeasAdcInt` waveform records.
The sequence study includes ADC03's two-speed measurements and the 28 reviewed
PEX cases, with internal-node plots, four clock plots and the
`frida_2_vs_1.tex`/PDF deck. Scope/setup HDF5 files are excluded. Other studies
use the independently pinned historical inputs documented in their docstrings.

`flow.adc.sequences` defines the `AdcSequence` value type and
contains explicit named channel rows and 65 named, rate-independent four-channel
sequences. Whitespace in definitions is removed when the dataclass is constructed.
Each combination contains four equally sized INIT, SAMP, COMP and LOGIC rows:
160 symbols for the continuous recipes, 256 for the padded recipes. The
simulation and scan runners pass those strings into the existing
`seq_*_pattern` parameters and supply `symbol_rate` separately. Testbenches
and FPGA packing consume the final rows without per-signal phase parameters.
All catalogue rows start at INIT rising. The historical INIT8 recipes are
rotated eight symbols earlier on all four channels, preserving relative timing
and period length. Historical saved data remains unchanged and readable.
Hardware ADC acquisition preserves all four rows exactly. FastRX alignment
adjusts only RX_SEN placement and comparator IDELAY. A wrapped receive window
can require dropping a partial receive frame, but no ADC control rotation or
startup-conversion discard is applied. Set `fastrx_capture=FastRxCapture(comp_delay_taps, rx_sen_start_word)`
in the physical parameters (combined taps 0..62), or provide an exact
characterized sequence/baud profile in `map_board.yaml`. Missing profiles fail
before instrument setup; single-stage calibration cannot be reused.
Historical result directories keep their old names; new simulation directories
use the full sequence names.

Both fixed-input targets use `fixed_input_timing_params()` to select the same four complete timing recipes:
`symbol256_init8_samp16_comp11110000_logic11000011`, `symbol256_init8_samp16_comp11111100_logic00000010`,
`symbol160_init4_samp24_comp11111100_logic00000010`, and `symbol160_init4_samp20_comp11111110_logic00000001`. Results
are written beneath `<flavor>/<timing>/`. That is sixteen FRIDA-1 cases and twelve FRIDA-2 cases, each with 100
conversions. The worker limits remain four and three respectively; cases queue within each host's 24-thread budget.
Diagnostics (`check=True`) cover all four recipes. The additions-only targets select the seven 7/8 cases from that same
builder.

`symbol256_init8_samp16_comp11110000_logic11000011` retains the September 5 timing.
`symbol256_init8_samp16_comp11111100_logic00000010` tests extended comparator evaluation: relative to each COMP rising
edge, its eight 0.625 ns slots are:

```text
COMP   11111100
LOGIC  00000010
```

COMP falls with LOGIC rising at the sequencer. LOGIC falls one slot before
the next COMP rising edge. Sampling, COMP rising edges, LOGIC rising edges,
the initialization pulse, noise settings, and the 160 ns record period remain
unchanged from the September 5 baseline. This is an experimental timing
setting, not timing signoff: internal clock skew, decision capture, minimum
pulse widths, comparator reset recovery and DAC settling still need checking.
Other targets retain their existing timing. `input.json` records
all four final sequence patterns for each new run.

`symbol160_init4_samp24_comp11111100_logic00000010` follows `docs/images/adc_sequencer_timing_100ns.tex`, with
time measured from INIT rising: INIT is high at 0--2.5 ns; its initialization
LOGIC pulse is at 1.875--2.5 ns; SAMP is high at 2.5--17.5 ns. COMP rises at
17.5 + 5k ns for k = 0..16. B0--B15 evaluate for 3.75 ns, followed by a
0.625 ns LOGIC update; B16 evaluates for only 2.5 ns and resets at 100 ns,
coincident with the next INIT rising edge. There is no B16 DAC-update pulse.
All four sequences repeat after 160 symbols / 100 ns, so this is true 10 MS/s
throughput (10 us for 100 conversions), rather than the other recipes' padded
160 ns records. The decoder reads B0--B15 at the SEQ_LOGIC rising threshold
crossing, linearly located in the saved transient, rather than ahead of that
edge. This external-clock reference does not model the SAR registers' local
clock delay or setup/hold behavior. B16 has no DAC update: it is observed at
the following INIT's LOGIC rising threshold. Missing final observations are
excluded and recorded, never replaced with an earlier read. New runs save a
partial next cycle for this observation and the next-COMP diagnostic.
`adc_sequence_study` plots the codes and canonical waveform records already
stored in each measurement. It does not re-decode or replace those codes and
does not write capture-analysis caches. Rebuild older simulation HDF5 files
before using the new `/wave/voltage` and `/wave/current` format. New conversions
consume VLSIR `TranResult` values and retain the required next-cycle tail in
the same waveform records. Simulator maximum steps and output spacing are both
controlled by `waveform_sample_interval_s` (10 ps by default). The study also
exports per-decision `*_timing_closure.csv` tables from `analyze_adc_timing_closure`:
internal resolution, SR agreement, LOGIC setup and CDAC settling margins. Both
setup requirements are 200 ps; the table records its voltage tolerances and
sampling interval. Missing observations cannot pass. B16 has no CDAC update.
Run the named target without experiment flags.
It does not model a separate physical output-capture register. Verify capture,
clock skew, and first-record startup in simulation before accepting this timing.

For every completed flavor, this analysis writes the 17-bit/12-bit code list,
the all-conversion decision-path density, and C0/C7/C15 settling
plots showing comparator outputs, DAC states/drivers, and top-plate residuals
over conversions with complete LOGIC captures. It reads existing HDF5
results; no simulation is rerun.
In the comparator row, solid blue/orange traces are the buffered P/N outputs;
dotted blue/orange traces are the internal cross-coupled regenerative nodes
when those signals were saved.

The same target also writes `adc_sampling_noise.pdf`, comparing held
differential voltages with common 25 µV bins and shared axes, plus
`adc_sampling_noise.csv` (sample SD, mean and offset) and
`adc_sampling_levels.csv` (one observed level and timestamp per conversion).
It interpolates the P/N CDAC voltages exactly 1 ns after SAMP falls, including
cases where COMP has already fired. Equal window-start and window-stop values
record this instantaneous observation. This requires the same fixed input
across the saved conversions. Each histogram is centered on its own mean;
the offset is retained in the CSV. The spread may include comparator activity,
so it is not isolated kT/C or final output-code noise. Values stay in volts/µV:
converting to LSB requires a separately measured input-code gain. These sampling
exports use the saved waveform records.

Worker preflight uses these diagnostic tests: it checks the actual extracted
port order and internal waveform nodes, generates the complete input, and runs
short Spectre diagnostics. Require passing tests, not skipped prerequisites,
before deploying a long campaign.
Each case records its PEX SHA-256. A worker snapshot must include the selected
`build/layout/adc/<target>/<timestamp>/` signoff summary and PEX netlist.
Only the two historical two-layer targets may accept the explicitly recorded
disconnect warning; FRIDA-2 requires raw LVS `CORRECT`.

These comparison targets pin their reviewed extraction directories explicitly;
they do not search for the latest extraction. Update those paths deliberately
after reviewing a replacement signoff run. `_run_adc_sim()` executes one case;
the named targets own the experiment parameters and concurrent submission.
Targets are listed in HDL21, FRIDA-1, then FRIDA-2 order, without old-name aliases.

The standard sequence has a 100 ns active conversion window at a 1.6 GHz
symbol rate, followed by padding to a 160 ns record. Thus “10 MS/s” describes
the active timing, not a continuous 100 ns sampling interval. The analysis
uses all 100 decision records and writes both B0-first 17-bit decisions and
decoded 12-bit outputs. Run long campaigns in detached worker sessions and
copy results back before selecting them for analysis.

## Remote simulation CLI

`flow.circuit.remote` wraps SSH, rsync, and tmux; the existing simulation targets
still define the experiments and their concurrency. FTD host/path conventions
are documented at the top of that module, not fixed in its configuration.
Start from the primary checkout on asiclab003 and check capacity first:

```bash
uv run python -m flow.circuit.remote status --host juno \
  --setup /eda/local/scripts/cadence_2024-25.sh
```

This shows CPU topology/load, memory, busy processes, and the issued/in-use
counts for `Virtuoso_Multi_mode_Simulation` and `Spectre_XPS`. Repeat
`--license-feature NAME` to inspect different FlexNet features. These are shared
license pools, not reservations. The server comes from the worker environment's
`CDS_LIC_FILE` or `LM_LICENSE_FILE`, or an explicit `--license-server` override.
Review other users' load and the runner's
multicore license needs before launching; the tool does not allocate resources.

After committing the source and submodule changes, launch an existing target:

```bash
uv run python -m flow.circuit.remote launch frida2_sequence \
  --host juno --work-root /local/kcaisley \
  --setup /eda/local/scripts/cadence_2024-25.sh \
  --input build/layout/adc/frida2_1layer_radix17/20260905_193440 \
  --input build/layout/adc/frida2_2layer_radix17/20260905_193629 \
  --input build/layout/adc/frida2_3layer_radix17/20260905_193816
```

Use `frida1_sequence` with `--host jupiter` and its four reviewed input
directories for the historical campaign. Input paths must match those selected
inside the target; the CLI never substitutes newer PEX files. `--block` defaults
to `adc`; use `comp`, `samp`, or `caparray` for other runners. Analysis is a
separate explicitly selected study, not a collection hook. The selected PDK submodule defaults to
`tsmc65`; foundry installations and absolute site inputs are not copied and
must already be accessible on the trusted worker. No PDK data goes to public CI.

The worker parent directory must already exist. Each launch creates a fresh
snapshot there from clean tracked source, dependencies, `uv.lock`, and explicit
build inputs, without a `.git` directory, virtual environment, or old results.
The remote tmux session installs from the lockfile, runs focused unit tests and
the selected Spectre diagnostic, then launches the normal simulation CLI.
Skipped diagnostics, missing inputs, and simulator/license errors prevent the
full run. Existing Spectre processes owned by the same user also stop preflight;
other users' resource use needs the manual review above.

The printed local `build/remote/<session>/` directory contains the revision and
input-path manifest, file list, and one shell bootstrap, not campaign-specific
Python scripts. Its detached local tmux collector checks every 30 minutes. Once
the entire target exits, it copies raw results, HDF5, diagnostics, and logs into
`results/`, including failed-run artifacts. `collected.json` records worker and
final exit codes. Select reviewed result directories in the study source before
invoking the analysis CLI; collection never automatically changes study inputs.

Collection can also be resumed explicitly if the local collector was lost:

```bash
uv run python -m flow.circuit.remote collect build/remote/<session> --watch
```

Without `--watch`, this checks once and copies if finished. Transport failures
are retried in watch mode; simulations are never automatically restarted and
remote snapshots are never deleted. Leave both machines powered on. Use tmux
and the worker's `build/remote/run.log` for live progress; `collector.log` records
local collection progress. Historical one-off recovery scripts are not used.

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
