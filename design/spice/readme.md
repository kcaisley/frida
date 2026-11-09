# SPICE Simulation Runtimes

## Campaign interface

Each block on the pipeline owns its reviewed runs in `flow/<block>/runs.py` (`runs`) and their testbenches and simulation in `flow/<block>/sim.py`, where `<block>` is `adc`, `comp`, `capdac` or `samp`. The CLI's sim step simulates them:

```bash
uv run python -m flow --block <block> --run <run> --to sim
```

`python -m flow --block <block> --run <run> --to sim --dry-run` lists the designs and their runs without running any (a run: a `@single`, `@grid` or `@optimize` of the block's `runs.py`, by name). Each design's run writes into its own folder of the run's dated folder, `build/<block>/<run>/<stamp>/<pdk>/<name>/sim/<testbench>/`; a run is never overwritten, only resumed where its output is incomplete. Every run uses the native HDL21 `Sim.run()` or `hs.run()` API with its folder as the VLSIR run directory. Its raw output is read as a typed measurement and kept as HDF5 (`result.h5`), then removed; each generated deck and simulator log stays beside it.

The blocks' `sim.py` state their concurrency and per-case Spectre `+mt` settings at the call sites which own that resource policy. Spectre jobs use `+lqtimeout 3600` so a temporarily exhausted license queue does not immediately fail a run. An analysis names its run (`--run`), or takes the latest and says which; creating new simulation data never changes an older run's inputs.

## Transient noise

The current FRIDA ADC and comparator noise campaigns use Spectre transient noise. ngspice 45.2 cannot substitute for these campaigns: its device-model noise is available to frequency-domain `.noise` analysis, but intrinsic MOS, resistor, and BJT noise is not injected into transient analysis. ngspice's `trnoise` keyword applies only to explicit voltage and current sources, and Monte Carlo process mismatch is not transient noise. A calibrated `trnoise` source can model an external or input-referred noise source, but it is not an equivalent device-level noise simulation.

## Measured runtimes

Rough wall-clock costs for FRIDA ADC simulations (TSMC 65 nm, Spectre 24.10, asiclab003).

A PEX-extracted transient with no noise (154.88 µs sweep, 121 ADC conversions) takes about 1h 25m wall time — roughly 33 wall seconds per µs of simulated time, or 42 seconds per conversion. The equivalent transient-noise PEX run takes 22h 22m — roughly 520 wall seconds per µs, or 11 minutes per conversion. Transient noise is about 16× more expensive than a noiseless PEX sweep.

As a rough rule of thumb: budget ~30 wall seconds per µs for PEX noiseless transients, and ~500 wall seconds per µs for PEX transient-noise. Schematic-level runs (no parasitics) are much cheaper — a comparator transient over 11 µs finishes in ~12 seconds, and a small delay sim over 36 ns finishes in ~1 second.
