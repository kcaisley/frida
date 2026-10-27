# The block pipeline

A building block runs as one pipeline: its design parameters make a circuit, testbench runs of it are simulated, each run's raw output is read as a measurement, analyses turn measurements into results, and the results become the block's metrics, its figures and the record of one instance of its design space. Each step is a file of the block's folder, and the names in each file are the same in every block, so `comp.Params`, `comp.netlist` and `comp.analyze_offset_noise` are read by their namespace. A block contributes data and stage functions only; the CLI (`python -m flow`) is the one entry point. The comparator (`flow/comp`) is the first block on it, the sampling switch (`flow/samp`) the second and the CDAC (`flow/cdac`) the third; the others follow one by one (`MIGRATED` in [`flow/test_pipeline.py`](../flow/test_pipeline.py)).

## Stages

Each stage imports only the stages above it in this table.

| File | Gives | What |
| --- | --- | --- |
| `params.py` | `Params`, `TbParams`, `valid(params, pdk=None)`, enums, constants | The design (an hdl21 paramclass, registered as a `flow.pipeline.Params`) and one testbench run of it (a frozen dataclass deriving `flow.pipeline.TbParams`: at least its `pdk` and its design, `params`); the run's schedule (which input each decision sees) is a property of `TbParams`. `valid` says whether a design can be built and, given a PDK, whether it works there: the rule and a small table of per-PDK limits. A parameter an optimization searches is declared with `flow.pipeline.knob` and its domain (`Choice`, `Int`: per-PDK bounds, a log scale, a `when` that names the designs it is used in): `Params` itself is the search space. |
| `subckt.py` | `Nets`, `netlist(params) -> h.Module` | The circuit: its nets, the generator. |
| `sim.py` | `testbench(tb) -> h.Module`, `simulate(tb, run_dir) -> Path` | The testbench of one run, and its simulation, which leaves the raw output on disk and parses nothing. Which signals are saved is declared here, from `Nets`. |
| `types.py` | `Analysis<Thing>`, `Metrics` | The block's results: frozen dataclasses deriving `flow.pipeline.Analysis`, data only; and its metrics, a frozen dataclass deriving `flow.pipeline.Metrics`, each field declared with `flow.pipeline.metric` and which way is better (`lower`, `higher`, `true` for a flag that must hold, `none` for a number only reported). |
| `analysis.py` | `@analysis analyze_<thing>(meas, *, prior) -> Analysis<Thing>`, `metrics(...) -> Metrics` | One measurement (or a sequence) in, prior results by keyword, one result out; an analysis may group its input and apply the block's other analyses to each group. `metrics` gives the record's numbers (a block not yet typed: `dict[str, float]`), None where the runs of a level did not measure one. |
| `plots.py` | `@plot plot_<thing>(result) -> Plot` | Each figure as a `flow.pipeline.Plot` spec, from results alone. |
| `sweep.py` | `@family` and `@named` functions, `runs(pdk, params, level=Level.FULL) -> dict[str, TbParams]`, `record(measurements) -> Record` | The design space, the runs that characterize one instance at a level (`flow.pipeline.Level`: `SCREEN` the quick ones, `SEARCH` what an optimization needs, `FULL` all, each including the levels below), and its record from the runs of any level (which also names the runs whose waveforms the viewer shows); a design that fails is recorded so, not raised. Nothing else: no module constants. |
| `opt.py` (optional) | `@problem` functions | What an optimization of the block minimizes and must meet (`flow.pipeline.Problem`): costs and bounds by metric name, parameters held; a function of a few knobs like a family, `adc(bits=12)`, given the PDK where it takes one. A block sized by its sweep alone has none. |

An analysis and a figure declare their stage with `flow.pipeline`'s `@analysis` and `@plot`: each checks its function when the module is imported (one measurement or result in, earlier results by keyword, an `Analysis` out; results in, a `Plot` out), so a block that breaks the contract does not import, and their types let ty reject an analysis that returns anything but an `Analysis`. Module constants live in `params.py` (the design's and the testbench's) and `sim.py` (what a run saves) alone.

Beside them: `layout.py` (beside `sim.py`: it imports `params.py` and `subckt.py`; `layout_named` lays out a named instance, `layout_netlist` and `layout_floorplan` give the sweep's layout step its netlists), and `model.py` (above `sweep.py`: the behavioral model from an instance's record); `opt.py` sits beside `model.py`. No `targets.py`.

A family is a function of a few named knobs returning the block's `Params`; `@family(knob=values, ...)` sweeps it over the product of its knobs' values (`pdks=` keeps a product to the PDKs it names, and a knob's values may be a function of the PDK; stacked decorators join their products), and calling it, `comp.dynamic_bias(ratio=3.5, k=2)`, gives one instance. `@named` gives one fixed instance a name (`@named(swept=False)`: named, for a layout, but not swept). The runner expands both and keeps in each PDK what `params.valid(params, pdk)` admits. An instance is its parameters: its digest is its identity, its family and knobs (`dynamic_bias(ratio=3.5, k=2)`) only a label. A design that is the PDK's own (the CDAC's plates, extracted in it) takes the PDK as a knob whose value is the PDK's: `cdac.adc_array(pdk=..., array=...)`, `@family(pdk=lambda pdk: (pdk,), ...)`.

Between `sim.py` and `analysis.py` sits one function every block shares, `flow.pipeline.read(raw, tb) -> Meas`: every saved signal on the simulator's time axis (`time_s`, voltages `v`, supply currents `i` by net name), the run's `TbParams` and identity. Readback never resamples; an analysis that needs uniform samples makes them itself. How finely the simulator writes its output is the run's (`TbParams`): the comparator's runs strobe it every 2 ps, as on the simulator's own steps its delays and energy came out wrong, the sampler's every 5 ps. The raw file is removed once read.

A lab capture meets a simulation in a result, not a measurement: the comparator's bench scans write `comp.AnalysisDecisions` (each trial's input and decision), which `comp.analyze_decisions` gives for a simulation, and the offset, noise, S-curve and common-mode analyses take those.

## Running a block

```sh
python -m flow run <block> [--pdk P ...] [--instance I ...] [--missing] [--workers N]
python -m flow layout <block> [--pdk P ...] [--instance I ... [--auto]] [--workers N]
python -m flow table <block> [--workers N]
python -m flow plot <block> [FIGURE ...] --from DIR [--from DIR ...] [--backend matplotlib|web]
python -m flow opt <block> --problem P [--pdk P] [--budget N] [--workers N] [--best N]
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
- A block with an `opt.py` (`flow/test_pipeline.py`): its `Params` declares domains, every combination of its choices is valid, its design space lies inside the domains, a knob whose `when` is false leaves the circuit unchanged, its metrics are typed, and its problems name metrics and bound only those with a direction.

## Optimizing a block

`python -m flow opt` is to the parameter space what `run` is to the families (`flow.opt.runner`): one problem of the block in one PDK is a study (Optuna's TPE sampler, `build/opt/<block>/<pdk>/<problem>.db`), asked asynchronously across a process pool, so a slow design holds no other. A design is evaluated once by its compiled netlist's hash (`build/opt/<block>/<pdk>/evals/<hash>/`), shared by every problem of the block and rescored when a new study starts: the screen's runs, its layout by its structure's hand-written floorplan where the problem bounds area (a design whose gates alone exceed the bound is out before simulating), then the search's runs if no bound is broken yet. The objective is the problem's cost (`pipeline.objective`: the product of its cost metrics, each to its weight, a saturating factor where a cost has a scale, in their units: a comparator's J um^2), each bound's violation a named constraint (`pipeline.violations`); a design that misses a bound completes infeasible, its cost infinite, and only a broken evaluation fails.
