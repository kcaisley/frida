# SPICE Simulation Runtimes

## Campaign interface

Each circuit-level simulation module owns its reviewed campaigns in
`flow/<module>/sim.py`, where `<module>` is `adc`, `comp`, `cdac`, or `samp`.
Run a named target with:

```bash
uv run python -m flow.<module>.sim <target>
```

Running without a target lists the available targets. Each target constructs
complete typed testbench parameters and writes a new, timestamped run beneath
`build/sim/<module>/<timestamp>/`; a target never overwrites a previous run.
Netlist-only targets generate the same parameterized Spectre decks without
starting a large campaign. Simulation targets retain the deck, simulator log,
and raw output together. ADC and comparator campaigns additionally convert
the raw results to the shared typed HDF5 measurement format; isolated sampler
and CDAC campaigns currently retain their raw simulator results.

Each module sets `MAX_PARALLEL_SIMULATIONS` and
`SPECTRE_THREADS_PER_SIMULATION` near the top of its simulation runner. Their
product is the campaign CPU budget. Spectre jobs use `+lqtimeout 3600` so a
temporarily exhausted license queue does not immediately fail a run. Analysis
runners deliberately name accepted simulation run directories; creating new
simulation data does not silently change analysis inputs.

## Transient noise

The current FRIDA ADC and comparator noise campaigns use Spectre transient
noise. ngspice 45.2 cannot substitute for these campaigns: its device-model
noise is available to frequency-domain `.noise` analysis, but intrinsic MOS,
resistor, and BJT noise is not injected into transient analysis. ngspice's
`trnoise` keyword applies only to explicit voltage and current sources, and
Monte Carlo process mismatch is not transient noise. A calibrated `trnoise`
source can model an external or input-referred noise source, but it is not an
equivalent device-level noise simulation.

## Measured runtimes

Rough wall-clock costs for FRIDA ADC simulations (TSMC 65 nm, Spectre 24.10, asiclab003).

A PEX-extracted transient with no noise (154.88 µs sweep, 121 ADC conversions) takes about 1h 25m wall time — roughly 33
wall seconds per µs of simulated time, or 42 seconds per conversion. The equivalent transient-noise PEX run takes 22h
22m — roughly 520 wall seconds per µs, or 11 minutes per conversion. Transient noise is about 16× more expensive than a
noiseless PEX sweep.

As a rough rule of thumb: budget ~30 wall seconds per µs for PEX noiseless transients, and ~500 wall seconds per µs for
PEX transient-noise. Schematic-level runs (no parasitics) are much cheaper — a comparator transient over 11 µs finishes
in ~12 seconds, and a small delay sim over 36 ns finishes in ~1 second.
