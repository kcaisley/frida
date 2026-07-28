# Unified analysis and plotting migration

## Goal

FRIDA currently has overlapping measurement, analysis, plotting, and result-I/O
implementations in `flow/circuit` and `flow/scans`. Consolidate them into one
backend-neutral post-processing pipeline:

```text
physical / behavioral / SPICE output
    -> RunData
    -> AnalysisResult
    -> plots and AnalysisReport
```

The same pipeline must support complete ADC runs and individual comparator,
CDAC, and sampler characterization. Public post-processing entry points accept
one typed request object and return one typed result object. Internal numerical
kernels may continue to accept arrays and scalars directly.

## Shared data model

Use a small set of reusable dataclasses rather than separate input and output
classes for every block and every calculation:

- `DataColumn`: one named NumPy array and its unit.
- `DataTable`: a group of aligned columns, such as `waveforms`,
  `conversions`, `spectrum`, or `linearity`.
- `RunData`: backend, block, source paths, normalized parameter snapshot, and
  data tables.
- `Metric`: one named scalar value and its unit.
- `AnalysisRequest`: one or more `RunData` objects and one analysis
  specification.
- `AnalysisResult`: reusable metrics and result tables.
- `PlotRequest` and `PlotArtifacts`: analysis results, output settings, and
  generated paths.
- `AnalysisPlan` and `AnalysisReport`: explicit sources, analysis jobs,
  in-memory results, and requested plot artifacts.

`RunData.block` identifies whether the run concerns an ADC, comparator, CDAC,
or sampler. Each analysis validates the canonical columns it requires.
Backend adapters translate scope channel names, HDL21 signal names, Spectre
signal names, and scan CSV columns into these canonical columns.

All numerical data uses SI units internally. HDL21 parameter objects are
normalized to backend-neutral plain data at the adapter boundary, so the
analysis package does not depend on HDL21 parameter classes.

Only genuinely different algorithm families receive small typed settings
records, for example event timing, histogram, sine/FFT, settling, and fitting
settings.

## First phase: refactor in place

The first phase changes behavior and APIs while files remain in their existing
directories. This keeps the functional diff separate from the later moves.

### Result adapters

Consolidate raw-result reading and normalization around the existing scan
result code. Support:

- current ADC conversion CSV and manifest files;
- historical ADC CSV column names;
- oscilloscope CSV files and in-memory Basil waveforms;
- HDL21 `SimResult` objects;
- Spectre NUTASCII results;
- in-memory behavioral-model arrays.

Each adapter produces `RunData`. Raw signal names are mapped to canonical names
at this boundary rather than inside measurement or plotting functions.

### Shared measurements

Refactor `flow/circuit/measure.py` into shared numerical kernels and typed
public measurement entry points for:

- threshold crossings and edge sampling;
- amplitude spectra;
- delay and settling time;
- average power;
- offset and charge injection;
- Monte Carlo statistics.

Remove simulator-specific extraction from the numerical measurement layer.
Simulator extraction belongs in the result adapters.

### ADC and block analyses

Refactor the active scan analysis around `AnalysisRequest` and
`AnalysisResult`.

ADC analyses include:

- transfer functions and output distributions;
- endpoint and code-density INL/DNL;
- decision paths;
- unified sine-fit and FFT analysis, including SNR, SNDR, THD, ENOB, fitted
  waveform, residuals, and spectrum;
- trends versus input frequency, conversion rate, timing offset, or another
  explicit sweep axis.

Block analyses use the same contracts:

- comparator offset, noise, delay, metastability, and power;
- CDAC transfer, mismatch, settling, and power;
- sampler settling, dynamic error, charge injection, noise, and power.

Block-specific analyses compose the generic measurement kernels rather than
adding wrappers which only rename values or change units.

### Plotting

Consolidate plotting into the active scan plotting implementation:

- plotting functions consume `RunData` or `AnalysisResult`;
- plotting functions do not read CSV files or calculate measurements;
- shared time-domain, frequency-domain, histogram, transfer, linearity,
  decision-path, dynamic-performance, and Monte Carlo renderers retain the
  current visual style;
- output formats are configurable and default to PNG, PDF, and SVG.

Migrate any useful behavior from `flow/circuit/plot.py`, then remove that
duplicate implementation.

### Explicit analysis plans

An `AnalysisPlan` explicitly names every source, analysis job, and plot job.
No analysis is inferred automatically from stimulus metadata.

The runner:

1. loads each source once;
2. validates the required tables and columns;
3. executes named jobs in dependency order;
4. renders requested plots;
5. returns an `AnalysisReport` containing the normalized runs, numerical
   results, and requested plot paths.

Raw scan CSV files and their scan-level `manifest.json` remain the source of
truth. Numerical analyses remain in memory and do not create derived CSV or
JSON files. Plotting writes image files only when a plot job explicitly
requests them.

## Second phase: mechanical package move

After the first phase passes all tests, move the finalized modules and their
tests into:

```text
flow/analysis/
    models.py
    io.py
    measure.py
    adc.py
    blocks.py
    plot.py
    runner.py
```

The second phase contains only file moves, import changes, and removal of
obsolete exports from `flow.circuit` and `flow.scans`. It must not alter
algorithms, metrics, or plot behavior. No compatibility import shims are kept.

Use `git diff --find-renames` to review the move independently from the
functional refactor.

## Tests and acceptance criteria

- Validate table alignment, units, finite numerical values, required columns,
  and JSON parameter snapshots.
- Prove that equivalent physical, behavioral, and SPICE inputs produce
  equivalent `RunData`.
- Test each measurement kernel with synthetic signals whose answers are known.
- Test ADC transfer, missing-code, INL/DNL, sine-fit, FFT, decision-path, and
  sweep analyses.
- Test comparator, CDAC, and sampler analyses.
- Test plot creation, labels, selected series, axis scaling, and configurable
  formats without pixel-level image comparisons.
- Test a complete mixed-backend `AnalysisPlan`, including explicit plot
  artifacts and in-memory result dependencies.
- Retain compatibility tests for historical ADC CSV data.
- Verify that the second-phase move leaves numerical results and artifacts
  unchanged.
- Run the complete software pytest suite.
- Require `ty` to pass for `flow/analysis`.

The migration does not change physical scan sequencing, behavioral models, or
SPICE testbenches beyond adopting the shared result contract.
