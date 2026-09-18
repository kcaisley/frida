# Analysis development contracts

The analysis pipeline has one explicit direction:

```text
hardware or simulator -> typed HDF5 -> Meas* -> analyze_* -> Analysis* -> plot_*
```

Each HDF5 file represents one logical measurement and stores native `/info`,
`/param`, `/daq`, and `/wave` groups. Producers construct a concrete typed
measurement and call `write_measurement()`; `flow/circuit/results.py` owns conversion
from simulator raw data. The analysis layer does not control hardware, start
simulators, or depend on sidecar manifests.

Reusable analysis functions accept concrete `Meas*` values and explicit
keyword parameters, perform numerical work, and return a concrete `Analysis*`
dataclass. Keep small shared numerical primitives in `measure.py`; do not add
a generic measurement superclass, request/dispatcher framework, table/dict
result contract, or wrappers that merely rename existing quantities. Arrays
are NumPy arrays with shape, dtype, and finite-value invariants checked at the
typed boundary. Decode simulated ADC observations once during conversion.
Trust the measurement's validated sample arrays rather than repeating their
shape and finite-value checks. Edge pairing and observation selection belong
to analysis. Derived analysis caches are not additional measurement types.

Plot functions load no files and calculate no analysis metrics. They consume
typed measurements and/or completed analysis results, then return the paths of
the artifacts they wrote. Analysis runners explicitly select reviewed input
files or run directories and orchestrate load, analyze, plot, and export. New
measurements or simulations never silently replace an accepted analysis input;
updating that selection is a deliberate review step. Runner functions may be
long when their orchestration remains linear and self-contained.

All active plots use the shared presentation and saver in `plots.py`: a fixed
9.6 × 5.4 inch canvas, black 12 pt titles, black 10 pt labels/ticks/legends,
7 pt information boxes, white axes by default, off-white legend and information
boxes, and the shared major/minor grid colors. Density-focused plots use the
Nord light-blue axes background. Data lines are 1 pt wide and markers are 4 pt.
PNG output is 500 DPI (4800×2700); major and minor ticks are 2.5 pt and 1.5 pt
long; PDF and SVG remain vector.
`PLOT_PNGS`, `PLOT_PDFS`, and `PLOT_SVGS` are the only format switches. Plot
callers pass one suffixless `output_path`, and the saver must not crop or resize
the canvas.

Ordinary series follow `CURVE_COLORS`; ordered density and spectrum data use
`SPECTRUM_COLOR_MAP`. Supply rails are always added as Analog, Digital, and DAC
so they receive blue, orange, and green consistently. Data artists are opaque.
Information boxes contain only concise measurement setup that is not already
in the title, axes, or legend; numerical results belong in the plotted data or
short legend labels. Renderers trust their typed inputs and limit their work to
unit conversion, text formatting, and drawing.

Tests should exercise each analyzer using the same concrete measurement types
used in production, validate dataclass invariants, and test plotting separately
from numerical results. For fitted calibration, final acceptance metrics
should eventually come from a separately acquired validation run: freeze all
weights and model choices learned from the training run, then apply them to the
validation run without refitting.

## Runtime follow-up

Keep analysis serial until profiling justifies added concurrency. A future
bounded worker pool may decode independent HDF5 files or analyze independent
ADCs, and independent per-ADC plots may be rendered before a comparison plot.
Any such change must preserve deterministic ordering and numerical equivalence.
Use the existing 6,024-file comparator campaign and 10,040-point CDAC campaign
as benchmarks; their many small HDF5/dataclass decodes dominate more than BLAS
work, so increasing NumPy threads alone is unlikely to help.

## Study entrypoints

All analysis runners end in `_study` and have exactly
`(output_dir: Path) -> tuple[Path, ...]`. Their input directories and selection
limits are explicit in their bodies/docstrings. The argument is output-only;
no newest-run discovery, input overrides, or analysis immediately after collection.
`main()` selects one study and creates its timestamped output directory.
Keep orchestration in each study; ask before extracting shared runner helpers.
Existing numerical analyzers and plotters remain reusable.

| Study | Selected coverage |
| --- | --- |
| `adc_transfer_curve_study` | Known-voltage ADC00 DC steps; archived directory currently missing locally. |
| `adc_ramp_nonlinearity_study` | ADC00--03 uniform sawtooth, code-density INL/DNL without absolute voltage reconstruction. |
| `adc_calibration_study` | ADC00 ramp and CDAC A-state threshold acquisitions; all three calibration methods. |
| `adc_sequence_study` | ADC03 56 patterns plus control at 10/6 active MSPS, and seven PEX flavors x four sequences; no 2-MSPS measurement sweep yet. |
| `adc_sample_rate_study` | ADC00/01 DC and sine sweeps plus ADC00's 800-mV control; only the historical INIT8/SAMP16 control pattern is selected, at 0.3125--6.25 actual MSPS. |
| `adc_power_study` | Instrumented ADC00/01 fixed-input rate sweeps and ADC00 reference points, with three supply readbacks. |

Consolidated acquisition directories can contain both DC and sine measurements.
The sample-rate study selects DC and sine by their typed stimulus for the
respective panels; the power study selects instrumented DC. A reviewed mixed
rate directory can therefore be pinned in both rate-study input selections.
No saved campaign is renamed or automatically selected.

Internal comparator/SAR/CDAC plots and four clock plots require `MeasAdcInt`
and its saved waveform records; DAQ trajectory and distribution plots also accept
`MeasAdcExt`. Outputs are flat. The sequence study preserves the SPICE deck.
Patterns are grouped using complete INIT/SAMP/COMP/LOGIC rows, rather than only
COMP-to-LOGIC delay. Each study compares temporary copies of all four rows
rotated together to INIT rising; common FastRX alignment rotations share a
series, while pulse widths, relative edges and period length remain distinct.
Saved patterns, acquisition phase and decoded samples remain unchanged. This
grouping does not establish that different launch phases behave identically.
New rate panels use actual sequence repetition rate,
including idle padding. Fixed-input ENOB is explicitly noise-equivalent;
spectral ENOB is shown separately. Finite large spreads and later recovered
points stay visible, as do rare histogram bins. Low spread alone does not
establish correct conversion or a working sequence.

Reusable plotting functions need not all appear in these selected studies.
`plot_adc_dynamic` is retained for individual spectral checks in the rate study.
`plot_adc_noise_distribution_grid` requires an all-ADC comparison dataset;
`plot_adc_sampling_noise` is a separate internal held-voltage noise study;
`plot_adc_power_waveform` requires simulated rail-current traces.
`plot_adc_decision_paths` is the line alternative to the retained trajectory
density, and `plot_adc_ramp_weights` is the older alternative to the common
calibration-weight comparison. `combine_adc_noise_comparison` remains available
for its older stimulus/DC/sine/PEX overlay. Their functions and tests remain;
removing unused imports is not a reason to delete them.

`MeasAdcInt` and `MeasCompInt` keep one waveform representation in `/wave`.
`voltage` and `current` map authoritative bundle names to record-by-time arrays.
Examples are `vin_p`, `dac_state_p[0]`, `dac_botplate_n_diff[15]`, and
`comp.latch_p`; ADC comparator internals use the `comp.` scope. Current entries
use the canonical supply name and are positive for current drawn from its source.
Derived input differences are calculated from the saved P/N voltages.

Each target in `adc/sim.py` and `comp/sim.py` invokes conversion and HDF5 writing.
Simulation workers return raw-file locations and bindings or run metadata.
`circuit.results.read_raw_transient` loads a VLSIR `TranResult`; converters map
its raw variable names to the canonical names selected by the save bindings.
The converter rejects missing/unmapped traces and raw time gaps larger than the
requested waveform spacing. It neither adds fictitious timing detail nor reads
old waveform formats as a fallback. Rebuild old simulation HDF5 files from raw
results with an explicitly appropriate sample interval, or rerun simulations
when their saved samples are too coarse for the intended timing measurement.

Both simulator `maxstep` and `strobeperiod` default to 10 ps through
`waveform_sample_interval_s` on the testbench parameters. The HDF5 record spacing
uses the same setting. This is a configurable numerical resolution, not a
validated claim of transistor-level timing accuracy. ADC records retain every
complete decoded conversion, all mapped traces, and a next-cycle tail for B16.
Comparator records retain every trial at the three transition-region points
and a representative trial at other points, with the complete evaluation window.
The record indices identify the retained population.

Ordinary analyses and plots consume the saved measurement without redecoding or
replacing its DAQ codes. `analyze_adc_timing_closure(MeasAdcInt, ...)` returns
`AnalysisAdcTimingClosure`: one row per saved conversion and decision, including
internal resolution time, SR agreement at LOGIC, and LOGIC-to-CDAC settling time.
The setup requirements default to 200 ps before LOGIC and before the next observed
COMP. A repeated SR value is valid; a late polarity reversal, weak resolution,
wrong SR/state value, or insufficient margin fails the corresponding check.
Missing observations produce NaN times and cannot pass. B16 retains its final
SR observation but has no SAR/CDAC update, so that check is inapplicable.

Internal resolution uses a 0.3 V differential threshold; SR and digital states
use 30%/70% rail limits. CDAC settling uses a configurable 1 mV tolerance:
bottom plates must reach the programmed rail, while top plates must remain
within tolerance of their last saved value before COMP. This measures settling
in the observed interval, not accuracy against a separately solved DC target.
Reported times are limited by the saved sample spacing. The sequence study writes
`*_timing_closure.csv` with the measured margins, pass flags, and threshold settings.

ADC edge pairing and nominal sequence timing are private calculations in
`analysis/adc.py`, shared where needed with conversion. `measure.py` retains the
generic numerical primitives; `adc/sequences.py` retains the sequence definitions.
The former capture/apply pipeline and capture-cache format have been removed.
`analyze_measurement_waveforms` can align a stored record to a selected reference
edge, with an optional reference-relative window.

Sampler transient conversion and caparray extraction conversion remain explicit
`NotImplementedError` prototypes. The latter will describe nominal/extracted
capacitances and Monte Carlo variation, rather than transient waveforms.

Saved ADC parameter records containing the old whole-symbol `seq_*_phase_delay_symbols`
fields are migrated at the HDF5 reader boundary by folding each delay into its
binary row. New records store only final rows and the separate symbol rate.
Fractional legacy delays cannot be represented by this interface and raise an
explicit error. The existing sweep result field `logic_phase_delay_symbols`
remains a derived display metric relative to half a decision interval; it is
calculated from row edges, not supplied to acquisition or simulation.
