# Usage

ADC capacitor stages, comparator decisions, and output codes follow the [project-wide ADC convention](adc_conventions.md): C0 is the largest and first capacitor, B0..B16 are chronological decisions, and DOUT is the 12-bit result formed from all 17 decisions.

`python -m flow` is the one entry point; bare, it prints its usage, its steps and the blocks it runs. A block on the [pipeline](pipeline.md) (the comparator, the sampling switch, the capacitive DAC and the ADC) is run one run at a time through its steps, `python -m flow --block B --run R [--from STEP] [--to STEP]` ([Running a block](pipeline.md#running-a-block)): `--run` names a run of the block's `runs.py` (a `@single` design, a `@grid`, or an `@optimize`, whose study the optimizer runs), `python -m flow --block comp --run topologies --to results` characterizes one of the comparator's grids (each design laid out, signed off, extracted and simulated again: its record's metrics post-layout), and the same for `samp`, `capdac` and `adc`; `--to presim`, then `--from results --to results`, records the pre-layout simulation alone. Each step is one tool, configured in its own Python files (the block's, the kit's), and what a run runs in and on (its PDKs, workers, budget) in its `runs.py`, not by flags of the CLI. Tab completes it in bash once `eval "$(python -m flow --completion)"` has run (workspace.sh does): the flags, the blocks after `--block`, a block's runs after `--run`, the steps after `--from` and `--to`. The viewer keeps its own command (`python -m flow web.serve`). The blocks not yet on the pipeline wait for their port: their `targets.py` are no longer run by the CLI. Physical scans keep their own runner (`python -m flow.scans.<scan>`), their figures `python -m flow.plot <block> <captures>`, and the file tools (`flow.util.netlist`, `flow.util.gds2image`, ...) are Python functions.

There is no installed `flow` executable or separate build-system orchestration layer. Run commands from the repository root through `uv`, for example:

```bash
uv run python -m flow
uv run python -m flow --block comp --run frida1 --to results
```

Digital lint, simulation, synthesis, and implementation use their stock tools directly.

## Layouts

A layout is four of the CLI's steps ([pipeline](pipeline.md)): `layout` (ALIGN, or the block's own `lay_out`), then `drc`, `lvs` and `pex`, each one tool on the GDS, each into its own folder of the instance (`layout/`, `drc/`, `lvs/`, `pex/`), each made once (make's rule):

```bash
uv run python -m flow --block comp --run frida1 --to pex               # laid out by ALIGN, signed off, extracted, in its PDKs
uv run python -m flow --block comp --run frida1 --to lvs               # no extraction
uv run python -m flow --block comp --run frida1 --from drc --to pex    # its signoff again, where its folders were deleted
uv run python -m flow --block capdac --run arrays --to pex             # a grid
uv run python -m flow --block samp --run frida1 --to postsim            # its runs again, its extraction back-annotated
```

The comparator, the sampler and the converter's DAC (capdac's, `flow/capdac`) are laid out by the shared layout step, each as its generator places it (`flow.layout.hdl21align.place` in its `subckt.py`; ALIGN places a generator that states nothing): `layout/netlist/` holds the ALIGN and LVS netlists, `layout/align/input/` ALIGN's design directory (the design by its instance, `<block>_<name>`: a top cell of its own), `layout/align/` ALIGN's work and the GDS (`layout/align_<router>/` where the PDK's router failed and the other drew it). ALIGN's inputs are made within the layout step alone, ALIGN with them (the netlist step's are the simulated circuit's), and ALIGN places a generator that states nothing; a placement left to ALIGN where a generator states one is no option of the CLI. DRC, LVS and PEX run the checker the kit names (`flow.layout.signoff.checker`): the open tools by default (gdscheck's DRC, the kit's KLayout LVS, KLayout-PEX by FasterCap, or by its 2.5-D engine where the kit's `signoff.engine(block)` names it: the capacitive DAC in TSMC65), the kit's Calibre where its `signoff.checker(block)` says so. Each step joins its outcome to the instance's record, which the viewer's table shows.

`postsim` runs an instance's simulations again with its open extraction back-annotated onto the schematic (each layout net found on its schematic net through LVS's database, the capacitors in a flat copy of each testbench's DUT), into `postsim/<run>/`, which the results step records as the instance's record (`instance.json`, `evidence` `postlayout`), the pre-layout metrics of the same names beside them (`prelayout`); its `annotation` (and `postsim/step.json`) states the extraction's total, the part on schematic nets, and the nets with none (and those the simulated DUT lacks), which fail the step past 5 % of the total. The ADC's FRIDA-1 extractions, devices and RC, are not back-annotated: the circuit step simulates them. An extraction made before its nets' probes (`pex/kpex/<stem>.probes.json`) is refused: delete `pex/` and extract again. The record holds both, so the two compare metric by metric.

The fabricated FRIDA-1 ADC's four flavors are single designs of the ADC's runs, laid out by its own flow (`flow/adc/layout.py`'s `lay_out`, which the layout step runs in place of ALIGN's), which plans their signoff (`layout/signoff.json`, `flow.layout.signoff.write_plan`: the sources, the LVS expectation and the kit's Calibre options and waivers); the drc, lvs and pex steps run that plan's Calibre DRC, LVS and xRC, each in its own folder:

```bash
for flavor in frida1_1layer_radix17 frida1_1layer_radix20 frida1_2layer_radix17 frida1_2layer_radix20; do
    uv run python -m flow --block adc --run $flavor --to pex
done
```

Each reads its fabricated inputs from the TSMC65 kit's tape-out folder (`site.FRIDA1`), not the repository: `frida-1.gds`, the flavor's source netlist `<flavor>.src.net`, and its capacitor array's LVS source, frozen once from the retired array generator (`<array>.lvs.cdl`, the array's subcircuit with its MOM units as the kit's LVS recognizes them, and `<array>.pins.json`, its pins to the fabricated macro's: stage C0 is the macro's pin 15). Each always runs the complete signoff sequence. The DRC stage includes the PDK-local `gdscheck` ADC suite before foundry Calibre DRC. The layout's files go beneath `build/adc/<run>/tsmc65/<name>/layout/` and each signoff tool's beneath its step's folder (`drc/`, `lvs/`, `pex/`), the instance's record beside them (`instance.json`, the layout's signoff and extraction, which a signoff run of the converter finds by `flow.sweep.lookup.laid_out`; the layout runs from before the steps, `build/adc/layout/<timestamp>/`, are found too). Each result contains the exact GDS and source CDL used, a recognition-only GDS diff, generated decks and logs, DRC/LVS reports, coupling and net-summary reports, and the final RC-plus-coupling `*.pex.netlist`. xRC stops unless its own conductive-source LVS comparison is correct.

The run-local layout copy adds only PDK-local non-mask MOM recognition shapes; the archived source and GDS are never modified. The normal LVS source contains the intended per-layer capacitor network. Thus the old one-layer layout must report `CORRECT`, while the known disconnected upper layer in an old two-layer layout must report the expected connectivity warning. The separate conductive PEX source omits the electrically empty CDAC wrappers so the extractor extracts the fabricated connectivity.

FRIDA-2 is generated whole: its earlier template-swapped layouts and their extracted view are gone. Any other converter's layout is its blocks side by side, unconnected (`lay_out`, from the blocks' own layouts by `flow.sweep.lookup.laid_out`): DRC alone checks it.

The building blocks not yet on the pipeline (`flow.delay`, `flow.latch`, `flow.ota`, `flow.follower`, `flow.idac`, `flow.cml`, `flow.pi`, `flow.clkgen`, `flow.lvshift`, `flow.ringamp`, `flow.csa`, `flow.disc`, `flow.schmitt`, `flow.bias`) wait for their port: the CLI runs them no more.

The tools come from the environment: `ALIGN_HOME` (an ALIGN install with its own Python, default `/local/kcaisley/layout-eval/ALIGN-public` on juno and asiclab003) and `IHP_OPEN_PDK` (a full IHP-Open-PDK checkout for ihp130's KLayout decks). Each PDK's signoff provider, `pdk/<pdk>/signoff.py`, runs gdscheck on the kit's DRC file, `pdk/<kit>/gdscheck/drc.yaml` (its `core` and `antenna` suites where it has them, else `main`, else its precheck), and then Calibre (Assura for LF150 LVS, the KLayout decks for ihp130).

## Circuit simulation

ADC, comparator, sampler, and CDAC simulations are the presim step of their blocks; `python -m flow --block <block> --run <run> --to presim --dry-run` lists the designs and runs without generating or running anything.

The comparator, the sampling switch and the capacitive DAC follow the [block pipeline](pipeline.md): their stage files from parameters to records, characterized instance by instance by the CLI's netlist, sim and record steps (`python -m flow --block comp --run topologies --to results`, `samp`, `capdac`). The other blocks' characterization campaigns (`<block>_characterization` in their `sim.py`) wait for their port to the pipeline.

Each target owns its reviewed parameter recipe. Short, noise-free Spectre diagnostics call the same simulation function with `check=True`, through pytest only (the ADC's: one check of each top, generated, tape-out and signoff, in `flow/adc/test_sim.py`):

```bash
source /eda/local/scripts/cadence_2024-25.sh
uv run pytest -m spectre
# Select just the ADC's tops, if needed:
uv run pytest -m spectre -k 'each_top'
```

Allow roughly one hour for the full Spectre suite on asiclab003; runtime depends on the host and available resources. Run the full group occasionally or after broad simulation-flow changes, not after every edit. For routine changes, use `-k` to select the tests covering the affected block or experiment. "Short" describes the simulated time, not the wall-clock runtime of extracted circuits.

The `spectre` group is excluded by default and requires no custom pytest flag. It covers the maintained ADC and building-block targets, and one short run of the comparator's pipeline (simulated and read). Artifacts and diagnostic reports remain beneath timestamped `build/diagnostics/` directories. Missing Spectre or an unavailable PDK installation skips with a reason; missing configured inputs, invalid decks, license failures, and simulator errors fail. Circuit-check findings remain available in reports; these diagnostics are not comprehensive circuit signoff. There are no CLI diagnostic flags, netlist-only modes, or separate check targets.

The ADC's Spectre runs are its circuit step: each instance's `spice_*` runs (`flow/adc/runs.py`'s `testbenches` at `Level.CIRCUIT` that its full ones are not), simulated into `circuit/<run>/` and recorded again with its behavioral ones in the instance's record, a candidate's and FRIDA-1's extractions' under the same names. The circuit step runs on a `@single` alone; in a run whose presim step is complete it simulates the circuit runs alone:

```bash
# FRIDA-1's sizing generated, then its four fabricated converters on their extractions
uv run python -m flow --block adc --run frida1 --to circuit
for flavor in frida1_1layer_radix17 frida1_1layer_radix20 frida1_2layer_radix17 frida1_2layer_radix20; do
    uv run python -m flow --block adc --run $flavor --to circuit
done
```

The ADC's runs are read by its own reader (`flow.adc.sim.read`: a Spectre run's transient decoded as conversions, a behavioral run's capture as written); the comparator's and the sampler's runs are read as measurements on the simulator's own time axis (`flow.pipeline.read`, [pipeline](pipeline.md)). A lab study names its accepted runs on the command line (`python -m flow.plot adc <run>`, [flow/adc/readme.md](../flow/adc/readme.md)).

Every simulation builds one native HDL21 `Sim` per parameter variant and calls `Sim.run()` or `hs.run()` with the run's folder (`presim/<run>/`) as the VLSIR run directory. ADC batches and the CLI's instances use isolated spawned processes, one Spectre thread each. The ADC converts the returned transient to typed HDF5 before releasing it. VLSIR retains the generated `netlist.scs` in every run directory, so a separate netlist-writing layer or target is unnecessary.

Concurrency and each case's Spectre `+mt` setting are visible in the block's `sim.py`, which owns its runs. Simulation targets require `spectre` on `PATH`; source `design/spice/workspace.sh` first when necessary.

## Design-space sweeps

Each `flow/<block>/runs.py` gives the block's runs, each by its function's name: single designs (`flow.pipeline.single`), grids (`grid`) and optimizations (`optimize`), each in the PDKs it names or every PDK whose kit is here, its `params.valid(params, pdk)` leaving out what does not work in a PDK. An instance is its parameters, nothing else: its id is `<pdk>__<digest>`, the digest the first 12 hex digits of the SHA-1 of its flat parameters, the same digest the behavioral models look a characterization up by. Each design runs its steps in a fresh process of its own, at most the run's workers at once (36 by default, `flow.pipeline.DEFAULT_WORKERS`: a Spectre X run holds 3 of the server's 120 licences):

```sh
uv run python -m flow --block comp --run topologies --to results        # every PDK the comparator admits
uv run python -m flow --block comp --run frida1 --to results            # one design
uv run python -m flow --block comp --run topologies --to results        # again: that run resumed, what is complete skipped
uv run python -m flow --block comp --run topologies --from table --to table   # the viewer's table, nothing run
rm -r build/comp/topologies/*/*/record                                 # then: recorded again from its kept measurements
uv run python -m flow --block comp --run topologies --from results --to table
uv run python -m flow --block comp --run topologies --to results --dry-run    # what would run, about how many simulator runs
uv run python -m flow --block comp --run adc_12bit                     # an optimization: its study, its budget's trials
uv run python -m flow web.serve
```

A run is dated under its name, `build/<block>/<run>/<stamp>/`; a single design is a run of its own (a `@single`), a grid's design no run alone. A run that exists is resumed: a step skips a design whose output is complete and not older than its inputs, so a run that stopped resumes; delete a step's folder, or the run's, to make it again. The table and the behavioral models' lookup (`flow.sweep.lookup`) take each instance's newest record across the block's runs, so a run of some designs or layouts alone leaves the others' from the runs before (the table: the run's records first, a newer record of an instance's layout alone joining its layout to it). `--from table --to table` exports what the runs hold: each run's own table (the viewer's Run picks one, the latest by default, a crashed or rerun run's still there). A results step whose output is complete is skipped too: delete `results/` to analyse the kept measurements again.

Each design runs in `build/<block>/<run>/<pdk>/<name>/` (a single's by its name, a grid's by its digest), a folder a step: `netlist/` (the circuit as simulated, `<block>.cdl`, and its size, `geometry.json`), `presim/<run>/` (each testbench run's simulator files and its kept measurement, `result.h5`), `circuit/<run>/`, `results/`, and beside them its record, `instance.json`: its id, name, label, parameters, its scalar metrics (its compiled netlist's size among them: its child cells where it has any, its devices and their area), its condition sweeps and the measurements whose waveforms the viewer shows. Each step's folder holds its `step.json` (when it finished, its seconds, its error). A step that fails records its error (a characterization's in `instance.json` too, so the table shows it) and is made again by the next command. The viewer (`flow/web`, `python -m flow web.serve`) shows one of a block's runs (its Run: the run's name, then its dated folder) as one table of the instances' parameters and results and a scatter plot of any metric against any other, a point coloured by its PDK and shaped by its topology; View shows an instance's story, the steps it went through from top to bottom, each its state (ok, failed, rejected, skipped or not run), time and warnings beside what it made (the netlist and schematic, the waveforms, the layout in 2-D and 3-D, DRC's violations, LVS's verdict, the extraction's nets, the analyses, post-layout solid beside pre-layout dotted), Compare several side by side. Runs from before the steps (`<run>/<pdk>/<digest>/instance.json` alone) stay readable where they are.

The PDK packages give each simulator what it reads: `Install.simulation_includes(corner, simulator, mismatch=False)`. `pdk/test_spice.py` loads every device and standard cell each package wraps in Spectre and ngspice (`-m site_pdk`); ngspice runs TSMC65, IHP130 and TPSC65. `flow.mosfet` characterizes every PDK's core devices in both.

## Netlist conversion

Netlist utilities are functions of `flow.util.netlist`:

```python
from pathlib import Path
from flow.util.netlist import cdl_to_sp, clean_cdl, oa_to_cdl

oa_to_cdl("frida", "core", Path("build/netlist"), cdslib=Path("cadence/cds.lib"))
cdl_to_sp(Path("design/spice/core.cdl"), Path("build/netlist/core.sp"))
clean_cdl(Path("design/spice/core.cdl"), Path("build/netlist/core.sp"),
          verilog=Path("design/hdl/frida_core.v"), module="frida_core")
```

`clean_cdl` removes filler and decap instances and normalizes OpenROAD hierarchy names. Pass `verilog` and `module` together to reorder the subcircuit ports using a Verilog module declaration.

## Digital checks

The normal software test suite includes both SPI-register implementations as cocotb tests. It uses Icarus by default:

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

Verible, Verilator, Yosys, and OpenROAD can likewise be run directly for linting, synthesis, and physical implementation. Each PDK's OpenROAD setup is in `pdk/<pdk>/openroad/`; the TSMC65 flow notes are in the private `pdk/tsmc65/docs/openroad.md`.

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

It records one four-million-conversion sawtooth capture per ADC for transfer, code-density, DNL, and INL analysis. The stored DOUT is retained as the uncalibrated result; BOUT can also be decoded in memory with the measured P/N CDAC weights for the switching direction selected by each element's programmed A-state. The A-state determines the direction of any physical change: an element initially at zero can only rise, while one initially at one can only fall. BOUT separately selects the final states imposed by the SAR logic: `P_final = 1 - BOUT` and `N_final = BOUT`. Therefore BOUT does not always mean "move P" or "move N". For one capacitor pair, the calibrated weight is the distance between its two possible BOUT endpoints, equal to the sum of its direction-matched P and N movements. Its calibration figures compare this CDAC-based decoder with the ramp-derived calibration methods.

The ramp's own figures (`code_density`, `inl`, `dnl` among `python -m flow.plot adc <run>`'s) plot each ADC's uncalibrated code density and INL/DNL. It assumes uniform ramp occupancy, excludes eight conversions after each detected flyback and excludes saturated endpoints from linearity. It does not reconstruct absolute voltage or require CDAC files.

The digital-calibration flow compares three ways to derive backend BOUT weights for ADC00 (`flow/adc/analysis.py`). `adc.analyze_calibration1` uses the direction-matched physical CDAC S-curves, `adc.analyze_calibration2` performs a nonnegative fit against the known ramp, and `adc.analyze_calibration3` extracts the all-zero/all-one prefix thresholds described by Hsu. None changes the analog ADC. The two ramp-derived methods use disjoint training and validation cycles, and the threshold method preserves nominal ratios once the measured steps become noise-limited.

```bash
mkdir build/study_calibration && ln -s <ramp run> <cdac runs> <comparator runs> build/study_calibration/
uv run python -m flow.plot adc build/study_calibration
uv run python -c 'from pathlib import Path; from flow import plot; plot.figures("adc", [Path("build/study_calibration")], ["code_density", "inl_calibrated", "dnl_calibrated", "ramp_transfer"], priors=True)'
```

All three analyses return the same typed 17-weight result: each calibration's weights are a figure (`calibration_weights`, the figures step's over a study's folder of links to the runs it takes), and, with the optional priors taken (`flow.plot.figures(..., priors=True)`), the ramp's transfer, code density and INL/DNL decoded by each calibration (the runs: [flow/adc/readme.md](../flow/adc/readme.md)). Every weight vector sums to 4095; rounding to a 12-bit integer is deferred until the final backend output.

`flow/scans/map_scope.yaml` only says how to reach the oscilloscope (Basil transfer layer and driver). Each scan or test declares its own probe hookup as a literal `{signal: channel}` mapping next to its Basil calls; edit that mapping when probes move. The standard ADC hookup is `vin_diff` (TDP3500) on CH1, COMP on CH2, LOGIC on CH3, and COMP_OUT on CH4. `scan_adc_noctl` uses INIT on CH1, COMP_OUT on CH2, COMP on CH3, and LOGIC on CH4. The serializer clock, output-word, and symbol-eye tests use differential probes on the PCB clocks: INIT, SAMP, COMP, and LOGIC on CH1--CH4.

Run one explicitly named physical campaign through the shared scan runner:

```bash
uv run python -m flow.scans.runner adc_sequence_static
uv run python -m flow.scans.runner adc_sample_rate_static
uv run python -m flow.scans.runner adc_ramp_code_density
uv run python -m flow.scans.runner comp_common_mode
uv run python -m flow.scans.runner cdac_cap_mismatch
```

Use `--help` to list every maintained ADC, comparator, CDAC, and repair target. ADC campaigns write `build/scan_adc/<timestamp>_<target>/0000_capture.h5`, `0001_capture.h5`, etc. The file index identifies a capture within the run; ADC selection, full sequence rows, stimulus, rails and rates are in the HDF5. Every runner keeps its selected ADCs visible beside a commented all-16 option for the longer scans. Acquisition creates no plots; its runs are drawn by `python -m flow <block> --from figures --to figures --run <run>`.

`adc_sequence_static` uses manual 50 mV differential input, 700 mV common mode, and 1.2 V rails. Its temporary initialization check scans ADC00–03 and the seven PEX comparison sequences at 2/6/10 nominal MSPS, with 100,000 conversions per point (84 captures). Their INIT-associated LOGIC pulse rises at symbol 2 and stays high through symbol 5; all recurring decision pulses retain their positions. The runner has TODOs to restore all 29 continuous sequences and all 16 ADCs after this check. These 160-symbol recipes repeat at 2/6/10 MSPS for the three baud rates. The first 28 already end with a full COMP word. The historical 24-symbol-SAMP recipe is replaced by a 20-symbol-SAMP recipe with its COMP and LOGIC train four symbols earlier, giving the final COMP pulse its full word. The 2026-09-25 168-symbol padded captures remain available as historical data. Nominal MSPS uses a fixed 160-symbol reference for every recipe: 2/6/10 MSPS means 320/960/1600 MBd. Actual active conversion and repetition rates remain separate saved quantities; no recipe-specific baud-rate adjustment is applied. Pass an existing `run_dir` when calling the Python runner function to resume a contiguous prefix of completed captures. The corrected 2026-09-26 campaign (29 one-symbol-INIT-LOGIC recipes on all 16 ADCs at 2/6/10 MSPS) is drawn by the sequence maps, one per ADC and one for the chip (`sequence_enob`, `sequence_plausible`, `sequence_shift`: `python -m flow adc --from figures --to figures --run <run>`). Its fixed-input ENOB is noise-equivalent, not spectral. The 2026-09-25 padded captures remain available as historical data.

`adc_sample_rate_static` uses the same manual setup for ADC00–03 and 39 rates from 0.5 to 10 nominal MSPS in 0.25-MSPS steps, with 1,000 conversions per point. Its 4–5 sequence choices remain TODO: the CLI stops before hardware access until its local shortlist contains the selected complete named sequences. Both use `scan_adc_noctl`, including one four-channel scope record per point and the existing scope/FastRX bit comparison after startup-frame alignment. Scope records and comparison status/mismatch counts are saved in HDF5.

`adc_activity_noise` compares one active ADC with all 16 active. Transfer and ramp-code-density acquisitions remain separate.

Some combinations deliberately raise LOGIC before COMP falls; the full cross product is retained to investigate both pulse width and relative edge timing. The names encode the complete configuration, for example `symbol160_init4_samp20_comp11111100_logic11000011`. Independent channel rows are private to the recipe table; callers select complete named recipes (`flow.adc.params.Recipe`). The simulation runner selects its comparison recipes by name. It controls only the FPGA, with no instrument connections or scope capture.

For this investigation, compare full code histograms and B0--B16 trajectories against the historical control at the same symbol rate. Check RMS noise, the entire populated code span, rare distant bins, and repeated late-bit tails; low RMS alone is not evidence of a healthy conversion. The screening target is RMS at most 2 LSB and full populated span at most 4 LSB, with a non-stuck trajectory. Keep every acquired code when computing these metrics. Acquisition and analysis are separate: the completed measurement runs are named to the figures step (`--run <run>`), and the PEX cases are the fabricated instances' circuit runs. Review candidate recipes with repeated captures before accepting recovered performance.

Scope/FastRX verification at 1600 MBd does not validate 960 MBd automatically. Before accepting the slower results, compare simultaneous scope and FastRX records using the rate-specific receiver model and verify COMP/LOGIC pulse levels. A 960 MBd active conversion lasts about 166.7 ns, so a 120 ns scope window cannot include all seventeen decisions. Retain the 7/8 scope reference as a separate timing diagnostic, rather than treating its differences as FastRX decode failures.

The target function owns the complete parameter recipe. ADC targets iterate their flat list and pass one configuration plus its lifecycle position to the acquisition module; comparator and CDAC targets pass their complete lists. Each run writes one typed HDF5 measurement per parameter variant below a fresh timestamped `build/scan_adc/`, `build/scan_comp/`, or `build/scan_cdac/` directory. The individual scan modules are libraries and do not provide command-line entry points.

Behavioral and SPICE-backed runs write the same measurement schema; the ADC's circuit runs are its instances' `spice_*` runs (above). Each fixed-input case uses 100 conversions, 50 mV differential input, 700 mV common mode, 1.2 V supplies, and transient device noise; the seven continuous timings (`spice_sequence_*`) run on each flavor's layout's signoff extraction.

The ADC's lab studies are its figures of these captures: `python -m flow.plot adc <run>` (a study of several runs: a folder of links to them), each board and channel's captures made into each figure as the ADC's analyses chain them (a figure a capture, a sweep over the rate, a calibration or a decoding), written into `build/analysis/adc/`. [flow/adc/readme.md](../flow/adc/readme.md) lists each study's command with its runs; the runs are named on the command line, never in the source. The sequence study's PEX cases are FRIDA-1's fabricated instances' circuit runs, their figures the record's (`python -m flow --block adc --run <flavor> --from figures --to figures`, into each instance's `figures/`).

`flow.adc.params` holds the explicit named channel rows and the 66 named, rate-independent four-channel recipes (`Recipe`; the catalogue's 65 and one historical continuous recipe). Each recipe contains four equally sized INIT, SAMP, COMP and LOGIC rows: 160 symbols for the continuous recipes, 256 for the padded recipes. A run's sequencer is four bit sources (`TbParams.seq_init` to `seq_logic`, each an `h.Vbit.Params`: a row as its `data`, one symbol a `period`); the simulation and scan runners set them from a recipe at a symbol rate (`TbParams.sequenced`), and the FPGA packing reads each line's `data`. Testbenches and FPGA packing consume the final rows without per-signal phase parameters. All catalogue rows start at INIT rising. The historical INIT8 recipes are rotated eight symbols earlier on all four channels, preserving relative timing and period length. Historical saved data remains unchanged and readable. Hardware ADC acquisition preserves all four rows exactly. FastRX alignment adjusts only RX_SEN placement and comparator IDELAY. A wrapped receive window can require dropping a partial receive frame, but no ADC control rotation or startup-conversion discard is applied. Set `fastrx_capture=FastRxCapture(comp_delay_taps, rx_sen_start_word)` in the physical parameters (combined taps 0..62), or use a characterized sequence-length, first-COMP-edge, and baud profile in `map_board.yaml`. Missing profiles fail before instrument setup; single-stage calibration cannot be reused. Historical result directories keep their old names; new simulation directories use the full sequence names.

The seven continuous timings (the `spice_sequence_<comp>_<logic>` runs of `flow/adc/runs.py`) are seven 160-symbol `Recipe`s of `flow/adc/params.py`, each played by its run's four sequencer lines. INIT is four symbols high and SAMP is high on symbols 4--23. All 17 COMP words begin at symbol 24 + 8k, so the last word occupies symbols 152--159 before the next INIT at 160. Each recurring LOGIC pulse is four symbols wide. For COMP widths 4, 5, and 6, LOGIC starts either at the first low COMP symbol or one symbol later. COMP 7/8 uses only the first-low-symbol case: another symbol of delay would put LOGIC rising at the next COMP rising edge. Newly generated 160-symbol runs use a separate INIT-associated B16 readout LOGIC pulse over symbols 2--5. Stored results from before it keep the earlier one-symbol pulse at symbol 3.

| COMP word | LOGIC at first low symbol | LOGIC one symbol later |
| --- | --- | --- |
| `11110000` | `00001111` | `10000111` |
| `11111000` | `10000111` | `11000011` |
| `11111100` | `11000011` | `11100001` |
| `11111110` | `11100001` | excluded: coincides with next COMP rise |

At 1600 MBd, one symbol is 0.625 ns and every recipe repeats in 100 ns. The final COMP pulse has its full eight-symbol word; the 7/8 recipe has only one low symbol for reset. The seven recipes give 28 FRIDA-1 PEX cases, with 100 conversions per case. Each case is a run of its fabricated instance, recorded with the instance's other runs in its sweep run's record. Each host uses at most 24 simulator threads. A run's `input.json` records its testbench, the four sequencer lines with it. The decoder reads B0--B15 at the SEQ_LOGIC rising threshold crossing, linearly located in the saved transient, rather than ahead of that edge. This external-clock reference does not model the SAR registers' local clock delay or setup/hold behavior. B16 has no DAC update: it is observed at the following INIT's LOGIC rising threshold. Missing final observations are excluded and recorded, never replaced with an earlier read. New runs save a partial next cycle for this observation and the next-COMP diagnostic. The sequence maps use the saved physical codes and readout checks; the circuit runs' figures use the codes their records decode. Neither re-decodes nor replaces stored codes. Rebuild older simulation HDF5 files before using the new `/wave/voltage` and `/wave/current` format. New conversions consume VLSIR `TranResult` values and retain the required next-cycle tail in the same waveform records. Simulator maximum steps and output spacing are both controlled by `waveform_sample_interval_s` (10 ps by default). The timing closure (`adc.analyze_timing_closure`: internal resolution, SR agreement, LOGIC setup, CDAC settling and observed COMP reset edges) and its summary (`adc.analyze_timing_summary`) need a run's internal nodes; both setup requirements default to 200 ps, and missing observations cannot pass. B16 has no CDAC update. It does not model a separate physical output-capture register. Verify capture, clock skew, and first-record startup in simulation before accepting this timing.

For every flavor, its record draws each timing's decision paths (`spice_sequence_<comp>_<logic>_trajectory`, `_trajectory_final`, `_trajectory_codes`) and its sequencer. The first, middle and last stage's settling (`cdac_settling_first`, `_middle`, `_last`: comparator outputs, DAC states and drivers, and top-plate residuals over the conversions with complete LOGIC captures) needs a run that saves its nodes (`Probes.NODES`), and is drawn from such a run's captures (the figures step over its `--run <run>`). Both read stored results; no simulation is rerun. In the comparator row, solid blue/orange traces are the buffered P/N outputs; dotted blue/orange traces are the internal cross-coupled regenerative nodes when those signals were saved.

The sampling noise (`adc.analyze_sampling_noise`, figure `sampling_noise`) compares held differential voltages with common 25 µV bins and shared axes, with each capture's sample SD, mean and offset and one observed level and timestamp per conversion in its result. It interpolates the P/N CDAC voltages exactly 1 ns after SAMP falls, including cases where COMP has already fired. Equal window-start and window-stop values record this instantaneous observation. This requires the same fixed input across the saved conversions. Each histogram is centered on its own mean; the offset is retained in the CSV. The spread may include comparator activity, so it is not isolated kT/C or final output-code noise. Values stay in volts/µV: converting to LSB requires a separately measured input-code gain. It uses the saved waveform records.

Worker preflight uses these diagnostic tests: it checks the actual extracted port order and internal waveform nodes, generates the complete input, and runs short Spectre diagnostics. Require passing tests, not skipped prerequisites, before deploying a long campaign. Each case records its PEX SHA-256. A worker snapshot must include each fabricated flavor's signoff run (`build/adc/layout/<run>/`: its signoff summary and PEX netlist). Only the two historical two-layer targets may accept the explicitly recorded disconnect warning.

A signoff run is its instance's newest standing layout (`flow.sweep.lookup.laid_out`), and each run checks its LVS verdict and its extraction's SHA-256 before it simulates. To replace it, lay the flavor out again (`python -m flow --block adc --run <flavor> --to pex`) and review the new signoff run. `adc.simulate()` (`flow/adc/sim.py`) executes one run; the testbenches of `flow/adc/runs.py` own the experiment parameters, and the CLI's sim and circuit steps the concurrent submission.

The standard sequence has a 100 ns active conversion window at a 1.6 GHz symbol rate, followed by padding to a 160 ns record. Thus “10 MS/s” describes the active timing, not a continuous 100 ns sampling interval. The analysis uses all 100 decision records and writes both B0-first 17-bit decisions and decoded 12-bit outputs. Run long campaigns in detached worker sessions and copy results back before selecting them for analysis.

## Remote simulation

`flow.circuit.remote` wraps SSH, rsync, and tmux; the existing simulation targets still define the experiments and their concurrency. FTD host/path conventions are documented at the top of that module, not fixed in its configuration. Start from the primary checkout on asiclab003 and check capacity first:

```python
from flow.circuit.remote import status
print(status("juno", setup="/eda/local/scripts/cadence_2024-25.sh"))
```

This shows CPU topology/load, memory, busy processes, and the issued/in-use counts for `Virtuoso_Multi_mode_Simulation` and `Spectre_XPS`. Pass `license_features=(...)` to inspect different FlexNet features. These are shared license pools, not reservations. The server comes from the worker environment's `CDS_LIC_FILE` or `LM_LICENSE_FILE`, or an explicit `license_server` override. Review other users' load and the runner's multicore license needs before launching; the tool does not allocate resources.

After committing the source and submodule changes, launch the circuit simulator's runs of single designs:

```python
from flow.circuit.remote import launch
launch(
    ["frida1_1layer_radix17", "frida1_1layer_radix20", "frida1_2layer_radix17", "frida1_2layer_radix20"],
    host="jupiter",
    work_root="/local/kcaisley",
    setup="/eda/local/scripts/cadence_2024-25.sh",
)
```

The worker runs `python -m flow --block <block> --run <name> --to circuit`, one a design, in its snapshot, after the block's focused tests and its Spectre diagnostic (the ADC's: each top's Spectre checks). `block` defaults to `adc`; use `comp` or `samp` for the others. The fabricated converters' extractions come from the PDK's site (`site.FRIDA1`) and their layouts' signoff runs (`python -m flow --block adc --run <flavor> --to pex`), which `inputs` adds to the snapshot where the worker cannot see them. Analysis is a separate explicit figures step (`python -m flow --block <block> --run <name> --from figures --to figures`), not a collection hook. The selected PDK submodule defaults to `tsmc65`; foundry installations and absolute site inputs are not copied and must already be accessible on the trusted worker. No PDK data goes to public CI.

The worker parent directory must already exist. Each launch creates a fresh snapshot there from clean tracked source, dependencies, `uv.lock`, and explicit build inputs, without a `.git` directory, virtual environment, or old results. The remote tmux session installs from the lockfile, runs focused unit tests and the block's Spectre diagnostic, then the instances' circuit runs. Skipped diagnostics, missing inputs, and simulator/license errors prevent the full run. Existing Spectre processes owned by the same user also stop preflight; other users' resource use needs the manual review above.

The printed local `build/remote/<session>/` directory contains the revision and input-path manifest, file list, and one shell bootstrap, not campaign-specific Python scripts. Its detached local tmux collector checks every 30 minutes. Once the whole run exits, it copies the run's records (`results/<block>/<run>/`), raw results, HDF5, diagnostics, and logs into `results/`, including failed-run artifacts. `collected.json` records worker and final exit codes. Name a reviewed result directory to the figures step (`python -m flow <block> --from figures --to figures --run <dir>`); collection never draws anything.

Collection can also be resumed explicitly if the local collector was lost:

```python
from pathlib import Path
from flow.circuit.remote import collect
collect(Path("build/remote/<session>"), watch=True)
```

Without `watch=True`, this checks once and copies if finished. Transport failures are retried in watch mode; simulations are never automatically restarted and remote snapshots are never deleted. Leave both machines powered on. Use tmux and the worker's `build/remote/run.log` for live progress; `collector.log` records local collection progress. Historical one-off recovery scripts are not used.

## Environment setup

Clone with submodules, create the environment, and run the software checks:

```bash
git clone --recursive git@github.com:kcaisley/frida.git
cd frida
uv sync
uv run pytest
```

Cadence Spectre, ngspice, Xyce, Icarus, KLayout, and OpenROAD are external executables. Install only the tools needed for the workflows you run and make them available on `PATH`.
