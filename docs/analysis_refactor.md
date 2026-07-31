# Typed measurement and analysis refactor

## Goal

Replace the generic `RunData -> DataTable -> AnalysisResult` hierarchy with
independent, circuit-specific measurement and analysis dataclasses. A
measurement contains its test parameters, run information, captured results,
and required time-domain waveforms. Analysis functions consume one or more
typed measurements and return one typed result. Plot functions consume the
original measurements and their typed analysis result so test conditions
remain available for labels and annotations.

The intended flow is:

```text
physical scan / behavioral model / SPICE simulation
    -> one typed HDF5 measurement file
    -> MeasAdcExt / MeasAdcInt / MeasCompExt / ...
    -> analyze_adc_*() / analyze_comp_*()
    -> AnalysisAdc* / AnalysisComp*
    -> plot_adc_*() / plot_comp_*()
```

There is no master measurement class, generic table class, analysis request,
plot request, plan dispatcher, or inheritance hierarchy.

## Migration scope

The current `flow/analysis` package was introduced only in the immediately
preceding commits and should be treated as a disposable prototype. This
refactor may replace the directory wholesale. No existing file layout, public
API, generic contract, compatibility layer, or import path needs to remain.

Useful numerical behavior is ported deliberately into the new typed functions
and checked against its existing tests or golden results. That does not require
retaining any of the current implementation around it. When the migration is
complete, no stale module, wrapper, alias, or compatibility shim from the
prototype remains.

## Package organization

```text
flow/analysis/
    types.py       typed measurement sections and analysis dataclasses
    io.py          shared HDF5 read/write and acquisition-wave adapters
    measure.py     small numerical waveform helpers
    adc.py         typed ADC analyses
    comp.py        typed comparator analyses
    plots.py       typed ADC, comparator, and waveform plots
    runner.py      manually invoked, explicitly named analysis pipelines
flow/spice/
    io.py          Spectre raw reader and typed measurement conversion
```

`flow/analysis/io.py` owns the shared measurement-file boundary for every
backend. Physical scans, behavioral simulations, and SPICE post-processing
construct the appropriate typed measurement and pass it to the same HDF5
writer. It also converts scope records and behavioral interface traces into
the arrays required by typed measurements. It does not acquire hardware or run
a simulator.

`flow/spice/io.py` owns Spectre-specific result parsing. The current ADC PEX
decks select `rawfmt=nutascii`, not NUTBIN, so the reader streams NUTASCII text
records and retains only the requested signals. It converts comparator output
waveforms into typed ADC decisions and delegates HDF5 persistence to the shared
writer above. Dense SPICE waveforms may be retained for fewer conversions than
the complete DAQ result, which keeps large transient-noise conversions
practical without changing ADC analyses.

Rail-power readbacks are only produced when the raw file contains explicitly
saved supply-current signals. The existing June 2026 ADC PEX decks define the
supply-voltage setpoints but their raw files do not save source currents, so
their power is unavailable and is not inferred from unrelated waveforms.

CDAC and sampler analysis modules will be added when real analyses and data
exist; their measurement types are defined now.

## HDF5 measurement format

One logical measurement is one `.h5` file. No separate JSON or CSV sidecar and
no JSON blob inside the HDF5 file are required.

The file root has four native HDF5 groups:

```text
/info
/param
/daq
/wave
```

`/info` contains small facts identifying the run:

```text
/info/schema_version       integer scalar
/info/measurement_type     UTF-8 scalar, for example "MeasAdcExt"
/info/backend              UTF-8 scalar: "physical", "behavioral", or "spice"
/info/timestamp_utc        UTF-8 scalar
/info/instruments          optional nested instrument or simulator identities
/info/readbacks            optional nested supply and instrument readbacks
```

`/param` is the complete normalized representation of the exact
`AdcTbParams` instance used for an ADC run. It is not a second, independently
maintained selection of fields. Nested parameter classes become nested HDF5
groups, scalar fields become scalar datasets, and fixed-width tuples become
one-dimensional datasets. HDL21 source unions become a group containing a
source `type` and that source's parameters in SI units. An absent optional
field represents `None`.

For other measurement classes, `/param` stores the corresponding complete
block-level testbench parameter class in the same manner. Large captured
vectors and waveforms never go into `/info` or `/param`.

### Dense triggered waveforms

Triggered scope records and post-processed SPICE conversions use dense
waveform datasets:

```text
/wave/conversion_index    int64,   shape (W,)
/wave/time_s              float64, shape (Ts,)
/wave/<signal>            float64, shape (W, Ts)
```

`W` is the number of stored waveform records and `Ts` is the number of samples
in each record. `waveform[record, :]` is therefore one ordinary one-dimensional
NumPy waveform. `conversion_index[record]` identifies the corresponding DAQ
row.

For physical ADC measurements, every stored waveform record contains the four
currently observable differential signals:

- `vin_diff_v`
- `seq_comp_v`
- `seq_logic_v`
- `comp_out_v`

At least one waveform record is required. `W` may be smaller than the total
number of ADC conversions, allowing representative scope captures to accompany
100k--1M conversion datasets.

Scope captures already have a regular time axis. SPICE adaptive-time results
are split into individual conversions and linearly interpolated onto one
regular, relative `time_s` axis during scan post-processing. The original
simulator raw file remains the lossless source if adaptive samples are needed
later.

Waveform datasets use HDF5 chunking by record and compression so reading
`signal[record, :]` does not load every waveform record.

Waveform names use quantity suffixes consistently: voltage signals end in
`_v`, current signals end in `_i`, and time axes end in `_s`. The units are
therefore apparent without spelling both the quantity and unit separately.

### ADC DAQ representation

ADC comparator decisions are numeric rather than strings:

```text
/daq/conversion_index    int64,   shape (N,)
/daq/bout                uint8,   shape (N, 17), values restricted to 0 or 1
/daq/dout_raw            int64,   shape (N,)
/daq/dout                int64,   shape (N,)
/daq/vin_diff_v          float64, shape (N,)
```

`conversion_index` is the complete row identifier shared by physical,
behavioral, and SPICE measurements. The FastRX packet's 4-bit `identifier` is
instead a fixed hardware-source identifier, and its frame counter wraps. The
physical acquisition validates both fields before accepting the data.

`MeasAdcExt` additionally retains `/daq/fastrx_word` as a `uint32` array for
low-level hardware debugging. The source identifier, wrapping frame counter,
and packed comparator data remain derivable from that raw word and are not
duplicated as canonical DAQ arrays. In particular, the former `spi` field was
only the 17 captured comparator bits packed into an integer; it was unrelated
to the slow-control SPI block and duplicated `bout`. `MeasAdcInt` does not
invent a FastRX word for simulation data.

## Measurement dataclasses

All vector and waveform fields use typed NumPy arrays. Run information shared
by every measurement is represented by one small common dataclass:

```python
@dataclass(frozen=True, slots=True)
class MeasInfo:
    schema_version: int
    measurement_type: str
    backend: Literal["physical", "behavioral", "spice"]
    timestamp_utc: datetime
    instruments: dict[str, str]
    readbacks: dict[str, str | int | float | bool]
    source_path: Path | None = None
```

`source_path` records where a loaded measurement came from. The reader
populates it from its input path; it is not persisted inside the file as a
machine-specific path.

Every measurement dataclass is composed from the same four semantic sections:

```python
info: MeasInfo
param: AdcTbParams | corresponding block testbench parameter class
daq: AdcDaq | corresponding circuit-specific DAQ dataclass
wave: AdcExtWave | corresponding circuit-specific waveform dataclass
```

The DAQ and waveform containers are small typed dataclasses rather than
dictionaries. A container is shared between external and internal
measurements when its actual fields are identical; otherwise each measurement
type has a circuit-specific container. This preserves static field names
without creating one master container full of unrelated optional signals.

This composition mirrors the four HDF5 groups without exposing HDF5 objects.
Each measurement class validates that `info.measurement_type` matches its
concrete class. The nested DAQ and waveform classes validate their array
dtypes, dimensionality, aligned field lengths, waveform shape `(W, Ts)`,
increasing `time_s`, and valid waveform-to-DAQ indices.

### I/O boundary and in-memory representation

`io.py` exposes one shared serializer and one shared reader:

```python
write_measurement(path: Path, msmt: Measurement) -> Path
read_measurement(path: Path) -> Measurement
```

`Measurement` is a union type alias over the concrete `MeasAdcExt`,
`MeasAdcInt`, `MeasCompExt`, `MeasCompInt`, `MeasSampInt`, `MeasDacExt`,
and `MeasDacInt` dataclasses. It is not a master class or inheritance
hierarchy. The reader inspects `/info/measurement_type` internally and returns
the corresponding concrete dataclass.

The in-memory object does not expose `h5py.Group`, `h5py.Dataset`, attributes,
or file paths as its data API, and it is not an untyped dictionary. HDF5 is
only the persistent representation. The same semantic grouping is retained
through ordinary typed Python composition. After loading, parameters are
typed parameter objects, run information is stored in `MeasInfo`, and all DAQ
and waveform vectors are NumPy arrays. Code therefore uses:

```python
msmt.param.symbol_rate
msmt.info.backend
msmt.daq.conversion_index
msmt.daq.bout
msmt.wave.comp_out_v
```

rather than:

```python
msmt["param"]["symbol_rate"]
msmt["daq"]["bout"]
msmt["wave"]["comp_out_v"]
```

For SPICE, the simulator still creates its native raw output. An adapter in
`io.py` reads that raw output and constructs a typed measurement; the shared
writer then saves it in the uniform HDF5 format. Physical scans similarly
combine Basil DAQ readback and any associated scope records into one
measurement before writing. Behavioral simulations construct the same typed
measurement directly.

### ADC

`MeasAdcExt` contains:

- `info` and ADC testbench `param`;
- `daq`: conversion index, raw FastRX word, `bout`, `dout_raw`, `dout`, and
  per-conversion `vin_diff_v`;
- `wave`: waveform conversion index, shared relative time axis,
  `vin_diff_v`, `seq_comp_v`, `seq_logic_v`, and `comp_out_v`.

`MeasAdcInt` contains:

- `info` and ADC testbench `param`;
- `daq`: conversion index, `bout`, `dout_raw`, `dout`, and `vin_diff_v`;
- `wave`: `vin_p_v`, `vin_n_v`, `seq_init_v`, `seq_samp_v`, `seq_comp_v`,
  `seq_logic_v`, `comp_out_v`, `vdac_p_v`, `vdac_n_v`,
  `clk_samp_p_v`, `clk_samp_n_v`, `clk_comp_v`, `comp_out_p_v`, and
  `comp_out_n_v`, plus `vdd_a_i`, `vdd_d_i`, and `vdd_dac_i`.

### Comparator

`MeasCompExt` contains `info`, comparator testbench `param`, a `daq` section
with trial index, applied `vin_diff_v`, `vin_cm_v`, and binary decision, and a
`wave` section with relative time and external `vin_diff_v`,
comparator-clock, and comparator-output waveforms.

`MeasCompInt` uses the same four sections. Its `daq` contains the same trial
conditions and decisions, while its `wave` additionally contains internal
`vin_p_v`, `vin_n_v`, `clock_v`, `vout_p_v`, `vout_n_v`, `comp_p_v`,
`comp_n_v`, and supply-current waveforms.

Several dozen `MeasCompExt` or `MeasCompInt` instances may represent sweeps of
differential input, common mode, clock rate, temperature, and PVT. Different
analyses consume the same measurement type; measurement types are not split by
analysis.

### Sampler and CDAC

Only `MeasSampInt` is defined for the sampler. Its `daq` contains the trial
index, and its `wave` contains relative time, input and sampled
differential-node waveforms, sampling clocks, and supply current.

`MeasDacExt.daq` contains trial index, positive and negative 16-bit DAC states,
applied differential input, and comparator decision. Its `wave` contains
the external comparator-path signals used to infer capacitor behavior.

`MeasDacInt.daq` contains trial index and positive and negative DAC states. Its
`wave` contains relative time, `vdac_p_v`, `vdac_n_v`, update-clock, and
supply-current waveforms.

No sampler or CDAC analysis functions are introduced in this migration.

## Typed analyses

Public analysis functions take measurement objects directly. Algorithm
options which cannot be derived from the test parameters are small
keyword-only scalar arguments; there are no request or settings classes.

ADC entry points and results are:

- `analyze_adc_transfer(Sequence[MeasAdcExt]) -> AnalysisAdcTransfer`
- `analyze_adc_nonlin(MeasAdcExt) -> AnalysisAdcNonlin`
- `analyze_adc_noise(Sequence[MeasAdcExt]) -> AnalysisAdcNoise`
- `analyze_adc_dynamic(MeasAdcExt) -> AnalysisAdcDynamic`
- `analyze_adc_dynamic_sweep(Sequence[MeasAdcExt]) -> AnalysisAdcDynamicSweep`
- `analyze_adc_decision_paths(MeasAdcExt) -> AnalysisAdcDecisionPaths`

`AnalysisAdcNonlin` supports endpoint and code-density calculations through an
explicit `method` field while sharing typed code, DNL, INL, transition, and
summary fields. Dynamic results retain fitted waveform, residual, spectrum,
SNR, SNDR, THD, SFDR, and ENOB arrays and scalars as named fields.

Comparator entry points use the same measurement input type for several
analyses:

- `analyze_comp_offset_noise(Sequence[MeasCompExt | MeasCompInt])`
  returns `AnalysisCompOffsetNoise`;
- `analyze_comp_timing(Sequence[MeasCompInt])` returns
  `AnalysisCompTiming`;
- `analyze_comp_power(Sequence[MeasCompInt])` returns
  `AnalysisCompPower`.

The current generic `Metric`, `DataColumn`, `DataTable`, `RunData`,
`AnalysisResult`, enum dispatchers, and specification classes are removed.

## Numerical helpers

`measure.py` contains only small hardware-free calculations with direct array
and scalar arguments. Examples include crossings, sine amplitude/frequency,
delay, settling time, average power, and interpolation onto a requested time
axis. Helpers return one scalar, one array, or a short tuple; analyses assemble
larger typed result dataclasses.

The current private-kernel/public-wrapper pattern is removed. A calculation
has one public numerical implementation rather than an `_implementation()`
plus an `analyze_*()` wrapper around generic requests.

## Plotting

Plot functions have direct typed signatures and receive both the measurement
conditions and the calculated result, for example:

```python
plot_adc_nonlin(
    msmt,
    analysis,
    output_path=...,
)
```

Corresponding functions cover transfer, nonlinearity, noise distribution,
dynamic performance, dynamic sweeps, decision paths, comparator offset/noise,
comparator timing, and comparator power. Raw time-domain waveform plots accept
a measurement and waveform record index without manufacturing an analysis
object.

Plots calculate no numerical metrics and load no files. They return the
generated paths. Output path and optional format selection are ordinary
arguments rather than `PlotSpec` objects.

## Explicit runner functions

`runner.py` is a readable notebook-like collection of named Python functions.
Each function:

1. names every HDF5 input path explicitly relative to:

   ```python
   BASE_PATH = Path(__file__).resolve().parents[2]
   ```

2. loads typed measurements;
3. calls one analysis;
4. calls its plot function beneath the supplied analysis-output directory.

There is no input-file globbing, automatic discovery, or generic plan
executor. A small explicit target table supports a positional command-line
interface:

```bash
uv run python -m flow.analysis.runner physical_adc_plus2_dynamic_rate_sweep
```

Omitting the target runs every registered pipeline. The entry point creates
one `build/analysis/adc/YYYYMMDD_HHMMSS` directory per invocation and passes it
to every selected target, keeping derived plots separate from raw scan data.
It prints one completion line with artifact count and elapsed time per target.
A missing recorded HDF5 input is reported and skipped in the all-target mode;
selecting that same target explicitly remains a hard error.
A real pipeline is added only after its HDF5 capture has been inspected and
its analysis has been validated ad hoc.

## Migration sequence

1. Add `h5py`, implement `types.py`, and test every shape/dtype invariant.
2. Implement source-format adapters plus the shared typed HDF5 writer and
   reader in `flow/analysis/io.py`.
3. Port ADC transfer plus its plot as the first end-to-end vertical slice.
4. Port the remaining ADC analyses and plots without changing their numerical
   results.
5. Port comparator analyses into `comp.py` and split their typed outputs.
6. Update physical, behavioral, and SPICE scans to emit HDF5 measurements.
   SPICE post-processing slices and interpolates conversions before writing.
7. Update loopback scripts to use the typed measurements and direct numerical
   helpers while keeping Basil calls visible.
8. Replace `plot.py` with `plots.py`, replace `models.py` with `types.py`,
   delete `blocks.py`, and remove all generic dispatch contracts and tests.
9. Add explicit runner functions only for newly captured, manually validated
   HDF5 datasets.

No compatibility loader or import shim is retained for the current July
manifest/CSV format.

## Tests and acceptance

- Round-trip each measurement type through HDF5 and require identical NumPy
  dtypes, shapes, values, parameters, run information, and
  waveform-to-DAQ mapping.
- Reject missing required datasets, invalid measurement type, unequal capture
  lengths, non-binary `bout`, invalid waveform shapes, non-increasing time,
  and out-of-range waveform conversion indices.
- Port existing synthetic ADC and comparator numerical tests to typed inputs
  and typed result assertions.
- Verify endpoint and code-density INL/DNL, static distributions, sine fit,
  FFT metrics, dynamic sweeps, and decision paths against current golden
  values.
- Test plot labels derived from measurement parameters and run information,
  selected waveform records, axis scaling, and generated formats without pixel
  comparisons.
- Test SPICE adaptive-time slicing and interpolation with synthetic
  conversions.
- Run Ruff, `ty check flow/analysis`, the ty pre-commit hook, and the complete
  software pytest suite.

The migration is complete when no production code imports the removed generic
analysis contracts, scans emit the new HDF5 schema, and every active analysis
and plot operates on the explicit measurement and analysis dataclasses.
