# The block pipeline

A building block runs as one pipeline: its design parameters make a circuit, testbench runs of it are simulated, each run's raw output is read as a measurement, analyses turn measurements into results, and the results become the block's metrics, its figures and the record of one instance of its design space. Each step is a file of the block's folder, and the names in each file are the same in every block, so `comp.Params`, `comp.netlist` and `comp.analyze_offset_noise` are read by their namespace. A block contributes data and stage functions only; the CLI (`python -m flow`) is the one entry point. The comparator (`flow/comp`) is the first block on it, the sampling switch (`flow/samp`) the second and the CDAC (`flow/cdac`) the third; the others follow one by one (`MIGRATED` in [`flow/test_pipeline.py`](../flow/test_pipeline.py)).

## Stages

Each stage imports only the stages above it in this table.

| File | Gives | What |
| --- | --- | --- |
| `params.py` | `Params`, `TbParams`, `valid(params, pdk=None)`, enums, constants | The design (an hdl21 paramclass, registered as a `flow.pipeline.Params`) and one testbench run of it (a frozen dataclass deriving `flow.pipeline.TbParams`: at least its `pdk` and its design, `params`); the run's schedule (which input each decision sees) is a property of `TbParams`. `valid` says whether a design can be built and, given a PDK, whether it works there: the rule and a small table of per-PDK limits. |
| `subckt.py` | `Nets`, `netlist(params) -> h.Module` | The circuit: its nets, the generator. |
| `sim.py` | `testbench(tb) -> h.Module`, `simulate(tb, run_dir) -> Path` | The testbench of one run, and its simulation, which leaves the raw output on disk and parses nothing. Which signals are saved is declared here, from `Nets`. |
| `types.py` | `Analysis<Thing>` | The block's results: frozen dataclasses deriving `flow.pipeline.Analysis`, data only. |
| `analysis.py` | `@analysis analyze_<thing>(meas, *, prior) -> Analysis<Thing>`, `metrics(...) -> dict[str, float]` | One measurement (or a sequence) in, prior results by keyword, one result out; an analysis may group its input and apply the block's other analyses to each group. `metrics` gives the record's numbers. |
| `plots.py` | `@plot plot_<thing>(result) -> Plot` | Each figure as a `flow.pipeline.Plot` spec, from results alone. |
| `sweep.py` | `@family` and `@named` functions, `runs(pdk, params) -> dict[str, TbParams]`, `record(measurements) -> Record` | The design space, the runs that characterize one instance, and its record (which also names the runs whose waveforms the viewer shows). Nothing else: no module constants. |

An analysis and a figure declare their stage with `flow.pipeline`'s `@analysis` and `@plot`: each checks its function when the module is imported (one measurement or result in, earlier results by keyword, an `Analysis` out; results in, a `Plot` out), so a block that breaks the contract does not import, and their types let ty reject an analysis that returns anything but an `Analysis`. Module constants live in `params.py` (the design's and the testbench's) and `sim.py` (what a run saves) alone.

Beside them: `layout.py` (beside `sim.py`: it imports `params.py` and `subckt.py`; `layout_named` lays out a named instance, `layout_netlist` and `layout_floorplan` give the sweep's layout step its netlists), and `model.py` (above `sweep.py`: the behavioral model from an instance's record). No `targets.py`.

A family is a function of a few named knobs returning the block's `Params`; `@family(knob=values, ...)` sweeps it over the product of its knobs' values (`pdks=` keeps a product to the PDKs it names, and a knob's values may be a function of the PDK; stacked decorators join their products), and calling it, `comp.dynamic_bias(ratio=3.5, k=2)`, gives one instance. `@named` gives one fixed instance a name (`@named(swept=False)`: named, for a layout, but not swept). The runner expands both and keeps in each PDK what `params.valid(params, pdk)` admits. An instance is its parameters: its digest is its identity, its family and knobs (`dynamic_bias(ratio=3.5, k=2)`) only a label. A design that is the PDK's own (the CDAC's plates, extracted in it) takes the PDK as a knob whose value is the PDK's: `cdac.adc_array(pdk=..., array=...)`, `@family(pdk=lambda pdk: (pdk,), ...)`.

Between `sim.py` and `analysis.py` sits one function every block shares, `flow.pipeline.read(raw, tb) -> Meas`: every saved signal on the simulator's time axis (`time_s`, voltages `v`, supply currents `i` by net name), the run's `TbParams` and identity. A Monte Carlo of operating points (Spectre's `montecarlo` with `savefamilyplots=yes`: a plot `mc-<run>_<analysis>` a run) reads as one measurement whose signals hold a value a run, in order (`time_s` empty, `readbacks["runs"]` their count; hdl21's `MonteCarlo` takes the statement's `options`). Readback never resamples; an analysis that needs uniform samples makes them itself. How finely the simulator writes its output is the run's (`TbParams`): the comparator's runs strobe it every 2 ps, as on the simulator's own steps its delays and energy came out wrong, the sampler's every 5 ps. The raw file is removed once read.

A lab capture meets a simulation in a result, not a measurement: the comparator's bench scans write `comp.AnalysisDecisions` (each trial's input and decision), which `comp.analyze_decisions` gives for a simulation, and the offset, noise, S-curve and common-mode analyses take those.

## Running a block

```sh
python -m flow run <block> [--pdk P ...] [--instance I ...] [--missing] [--workers N]
python -m flow layout <block> [--pdk P ...] [--instance I ... [--auto]] [--workers N]
python -m flow table <block> [--workers N]
python -m flow plot <block> [FIGURE ...] --from DIR [--from DIR ...] [--backend matplotlib|web]
```

`run` characterizes the design space (or the instances picked: a name, a label or a digest) into a fresh `build/sweep/<block>/<run>`; the sweep runner (`flow.sweep.runner`) simulates each of an instance's `runs`, reads each and hands the measurements to `record`. `layout` lays out the newest run's instances by ALIGN, or named instances by all three tools. `table` exports the viewer's tables. `plot` draws a sweep run's records' figures, or the figures of a directory of captures: each `plot_<thing>` whose result an analysis of the block gives from a sequence of captures, for each board and channel. A block not on the pipeline keeps `python -m flow <block>.<target>` until it moves; the CLI takes a verb as its first word, a target otherwise.

## Figures

`plots.py` returns specs only. The viewer draws a record's from their JSON with Plotly; `flow.plot.render(plot, path)` draws any with matplotlib in the analysis plots' style.

## Checks

Pre-commit and CI hold a migrated block to this:

- [`flow/test_pipeline.py`](../flow/test_pipeline.py): the stage files, the public names each defines, their signatures, no nested functions, in `types.py`, `analysis.py` and `plots.py` no private helpers and no file I/O, `sweep.py` only families, named instances, `runs` and `record`, no `targets.py`, and no run and no path under `build/` named in the block's code. Its known-violations list only shrinks.
- import-linter (`[tool.importlinter]` in `pyproject.toml`): the stage order, and that `flow.pipeline` imports no block.
- Ruff ICN003: outside the block, `from flow import comp` and `comp.Params`, never `from flow.comp import Params`; inside it the stages import each other relatively.
- ty on the base module and the block's stage files.
