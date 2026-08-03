# Flow code audit

Date: 2026-08-03

This document records a read-only audit of `flow/` before its next cleanup.
Nothing listed here was removed as part of the audit. Candidates were checked
with import searches, entry-point searches, test collection, and:

```bash
uvx vulture flow --min-confidence 80
uvx vulture flow --min-confidence 60
uv run ruff check flow
uv run pytest --collect-only -q
```

Static unused-code reports are only supporting evidence. HDL21 module
attributes, dataclass fields, pytest markers, dynamically selected runner
functions, and scripts invoked by external tools frequently appear unused to
static analysis even when they are active.

## High-confidence cleanup

### Obsolete FastRX debug scan

`flow/scans/scan_compout.py` is a fixed-pattern, manually configured debug
scan. It hardcodes an RX_SEN start word and does not use the current calculated
capture alignment.

Its useful coverage is superseded by:

- `flow/scans/test_fastrx.py`, which verifies exact FastRX bit order, framing,
  word count, and overflow behavior through the FPGA-internal loopback;
- `flow/scans/loopback_fastrx.py`, which compares the physical comparator
  waveform against FastRX across symbol rates and logic offsets and writes the
  typed HDF5 result.

The file can be removed after updating the reference in
`flow/scans/test_seqgen.py`.

### Unused numerical helpers

The following functions in `flow/analysis/measure.py` have no production
callers and no tests:

- `diff_to_single()`
- `quantize_to_bits()`
- `redundant_bits_to_code()`
- `code_to_voltage()`
- `compute_static_error()`
- `compute_enob_fft()`
- `mc_statistics()`

`compute_static_error()` and `compute_enob_fft()` also duplicate numerical work
now owned by the typed ADC analyses in `flow/analysis/adc.py`.

The following functions are called only by tests of themselves, not by a
measurement analysis or runner:

- `amplitude_spectrum()`
- `sample_at_edges()`
- `measure_offset_crossing()`
- `measure_charge_injection()`
- `endpoint_linearity()`
- `statistics()`

They should be removed until a real analysis requires them. The currently used
shared numerical surface is `find_crossings()`, `measure_settling()`,
`measure_delay()`, `measure_average_power()`, `histogram_inl_dnl()`, and
`find_code_transitions()`.

### Unused registries, wrappers, and constants

- `PARAMETER_TYPES` in `flow/analysis/types.py` is unused. Parameter
  reconstruction now uses the qualified type stored in HDF5.
- `get_adc_weights()` in `flow/adc/subckt.py` is a one-line NumPy wrapper used
  only by its test. Call `get_cdac_weights(params.cdac)` directly.
- `MIN_SYMBOL_RATE_BPS`, `MAX_SYMBOL_RATE_BPS`, and `PLL_FREQUENCY_TABLE` in
  `flow/scans/plldrp.py` have no callers.
- `PllFrequency` and `build_pll_frequency_table()` are used only by their
  software test. That test can exercise `calculate_pll_frequency()` directly
  if the standalone table API is not wanted.
- Two mocked `selected_view` parameters in `flow/adc/test_sim.py` are unused;
  Vulture reports both with 100 percent confidence.
- `group_idx` in `flow/cdac/layout.py` and `site_w` in
  `flow/layout/msor.py` are unused local variables.

## Behavioral ADC cleanup

`flow/adc/behavioral.py` is the largest concentration of outdated code. The
current behavioral adapter uses model construction, `sample_and_convert()`,
`calculate_result()`, and the CDAC/comparator conversion core. It does not use
the file's embedded plotting and reporting system.

Removable portions include:

- `CDAC.calculate_nonlinearity()`;
- `SAR_ADC.update_parameters()` and `print_parameter_list()`;
- the ADC nonlinearity, ENOB, energy, redundancy, and transfer plotting
  methods;
- `compile_results()` and its Markdown report writer;
- the unused plotting branch of `sample_and_convert()` if ad-hoc model plots
  are no longer required.

Some dormant paths are already inconsistent. The generated-array branch
references the deleted `array_N_M_expansion` option, and
`print_parameter_list()` references attributes that the current CDAC model
does not define. The embedded plots also bypass `flow.analysis` and its shared
Nord styling.

The active behavioral core should remain. Removing its private analysis and
reporting code should reduce the file from about 1,100 lines to roughly
400--450 lines without changing the current `flow/scans/scan_behavioral.py`
result.

`scan_behavioral.py` itself is active but transitional. It currently runs one
hardcoded conversion, constructs a second dictionary-shaped parameter model,
and overwrites `build/behavioral_scan/adc_00.h5`. It should eventually consume
explicit `AdcTbParams` cases and use the same timestamped, named-run convention
as physical and SPICE acquisition.

## Probable removals requiring confirmation

- `flow/util/gds.py` and `flow/util/lyt.py` have no production callers or
  documented commands. Only their unit tests import them.
- `flow/util/network.py` is an undocumented standalone command. It duplicates
  hardcoded FPGA and scope addresses instead of reading the instrument maps.
  Either document it as a deliberate site diagnostic and read shared
  configuration, or remove it in favor of the hardware connectivity tests.

## Test organization

`flow/layout/tech.py` contains `test_rule_deck()` and `test_remap_layers()`, but
normal repository test discovery does not collect them. Move them to
`flow/layout/test_tech.py`.

`flow/layout/serialize.py` contains `test_serialize()`. It is collected only
because `serialize.py` is specially included in `pyproject.toml`. Move it to
`flow/layout/test_serialize.py`; production modules should not double as test
modules.

The PDK `layout.py` tests are a separate organization decision and are outside
this `flow/` audit.

## Active but architecturally old

The comparator, sampler, and CDAC simulation commands remain on the generic
block-sweep architecture in:

- `flow/comp/sim.py`
- `flow/samp/sim.py`
- `flow/cdac/sim.py`
- `flow/circuit/commands.py`
- `flow/circuit/netlist.py`

These paths are live and cannot be deleted yet. They still construct anonymous
parameter sweeps, share the `min`/`max` command interface, and discard returned
simulation results instead of converting them into typed HDF5 measurements.
They should eventually adopt explicit named cases, like `flow/adc/sim.py`, and
produce the corresponding block measurement types.

Once those three blocks migrate, the legacy variant-selection, filename,
summary, and command-dispatch portions of `flow/circuit` can be reconsidered.

## Intentional code to retain

The following appear orphaned to an import graph but have deliberate roles:

- `flow/layout/msor.py` runs inside OpenROAD and is not imported as Python;
- hardware loopback scripts are direct command entry points;
- `flow/cdac/layout.py` is explicitly transitional but still owns unique
  FRIDA array placement, shielding, routing, via, and pin generation;
- comparator measurement types, analyses, and plots are an incomplete but
  intentional vertical slice awaiting real measurement producers;
- HDL21 instance attributes and analysis declarations reported by Vulture are
  consumed by HDL21 metaclasses and netlisting;
- waveform fields reported by Vulture are part of the typed HDF5 contract.

## Documentation consistency

The audit found three stale `flow.<block>.testbench` references in
`docs/cosim0.md`. They were corrected to `flow.<block>.sim` alongside this
record because they directly described the renamed entry points.

## Estimated reduction

Removing only high-confidence dead code should eliminate about 900 lines.
Including the probable utility removals would bring the reduction closer to
1,100 lines. The active generic block-simulation migration would be a separate
refactor and is not included in this estimate.
