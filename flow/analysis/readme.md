# Analysis development contracts

The analysis pipeline has one explicit direction:

```text
hardware or simulator -> typed HDF5 -> Meas* -> analyze_* -> Analysis* -> plot_*
```

Each HDF5 file represents one logical measurement and stores native `/info`,
`/param`, `/daq`, and `/wave` groups.  Producers construct a concrete typed
measurement and call `write_measurement()`; `flow/spice/io.py` owns conversion
from simulator raw data.  The analysis layer does not control hardware, start
simulators, or depend on sidecar manifests.

Reusable analysis functions accept concrete `Meas*` values and explicit
keyword parameters, perform numerical work, and return a concrete `Analysis*`
dataclass.  Keep small shared numerical primitives in `measure.py`; do not add
a generic measurement superclass, request/dispatcher framework, table/dict
result contract, or wrappers that merely rename existing quantities.  Arrays
are NumPy arrays with shape, dtype, and finite-value invariants checked at the
typed boundary.

Plot functions load no files and calculate no analysis metrics.  They consume
typed measurements and/or completed analysis results, then return the paths of
the artifacts they wrote.  Analysis runners explicitly select reviewed input
files or run directories and orchestrate load, analyze, plot, and export.  New
measurements or simulations never silently replace an accepted analysis input;
updating that selection is a deliberate review step.  Runner functions may be
long when their orchestration remains linear and self-contained.

Tests should exercise each analyzer using the same concrete measurement types
used in production, validate dataclass invariants, and test plotting separately
from numerical results.  For fitted calibration, final acceptance metrics
should eventually come from a separately acquired validation run: freeze all
weights and model choices learned from the training run, then apply them to the
validation run without refitting.

## Runtime follow-up

Keep analysis serial until profiling justifies added concurrency.  A future
bounded worker pool may decode independent HDF5 files or analyze independent
ADCs, and independent per-ADC plots may be rendered before a comparison plot.
Any such change must preserve deterministic ordering and numerical equivalence.
Use the existing 6,024-file comparator campaign and 10,040-point CDAC campaign
as benchmarks; their many small HDF5/dataclass decodes dominate more than BLAS
work, so increasing NumPy threads alone is unlikely to help.
