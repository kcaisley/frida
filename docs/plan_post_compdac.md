# Post-comparator/CDAC scan refactoring plan

Status: complete; every implementation and regression gate passed.

This checklist covers the post-bring-up cleanup of `scan_adc.py`,
`scan_comp.py`, and `scan_cdac.py`. The refactor must preserve the campaigns,
sequencer programs, FastRX interpretation, measurement quality, and analysis
results which are working now. The only intentional behavioral change is the
uniform board safety policy described below. Production RTL, analysis
algorithms, measurement dataclasses, and HDF5 schemas are out of scope.

## Locked design decisions

- [x] Treat campaign axes as local scan recipes, not as new parameter classes.
  Each expanded `AdcTbParams` continues to describe one fixed physical point.
- [x] Do not add `CompSweepParams`, an acquisition-policy dataclass, or a
  scan-plan dataclass. HDL21 inputs remain `*TbParams` and `*Params`; scan
  outputs remain `Meas*` dataclasses.
- [x] Keep the current board `"00"`, 1.6 GBd symbol rate, ADC dimensions, and
  CDAC flavor selection inside the existing point builders for now. Revisit
  builder templates only when another physical board is introduced.
- [x] Keep recognizable Basil calls, waits, safety ordering, and `try/finally`
  shutdown in each scan runner. Shared modules contain only pure packing,
  alignment, and decoding calculations.
- [x] Interpret the three regression targets as `scan_adc.py`, `scan_comp.py`,
  and `scan_cdac.py`.

## Dataclass and function-organization guardrails

The implementation must preserve the repository's simple data flow:

```text
HDL21 input parameters -> physical or simulated producer -> Meas* -> Analysis*
```

- [x] Use `*TbParams` only for parameters which describe a complete HDL21
  testbench or top-level physical-chip configuration. Use `*Params` only for
  parameters of a netlisted subcircuit or another genuine nested design
  boundary.
- [x] Preserve the established parameter stacks:

  - physical chip, generated ADC, and whole-chip PEX:
    `AdcTbParams -> AdcParams -> CompParams/CdacParams`;
  - standalone comparator simulation:
    `CompTbParams -> CompParams`;
  - standalone CDAC simulation:
    `CdacTbParams -> CdacParams`.

- [x] Do not introduce scan-policy, campaign-axis, sweep, sequence, supply,
  timing, or scheduler dataclasses. In particular, do not add
  `CompSweepParams`, `AdaptiveSweepParams`, `AcquisitionPolicy`, or a generic
  scan-plan record.
- [x] Keep every physical campaign expansion function returning complete
  `AdcTbParams` points. A point contains one fixed DC/AC/ramp source and its
  executed acquisition metadata; lists of voltages or common modes belong to
  the recipe which expands those points.
- [x] Keep scan results in the existing measurement hierarchy:
  `MeasAdcExt`, `MeasCompExt`, and `MeasCdacExt` for physical external
  measurements, with the existing `Meas*Int` types for internal simulation
  observability. Do not add an intermediate scan-result or capture-result
  dataclass.
- [x] Keep analysis outputs in the existing `Analysis*` dataclasses and keep
  analysis code consuming `Meas*` objects. This refactor must not add an
  alternate dictionary, tuple, or ad hoc record path between acquisition and
  analysis.
- [x] Do not change the meaning of `Ext`/`Int`: it continues to describe
  external versus internal observability, not physical versus simulated
  origin.
- [x] Do not add any new dataclass in this refactor. Move the existing
  `FastRxCaptureAlignment` record to neutral ownership unchanged; it remains a
  justified internal calculation result rather than a parameter or
  measurement type.
- [x] Prefer a few direct functions with clear ownership. Do not create a
  helper merely to rename one Basil call, bundle a short visible hardware
  sequence, hold one constant, or serve one call site.
- [x] Keep one-off Basil operations, waits, output-enable ordering, current
  limits, and shutdown behavior directly visible in each scan runner.
- [x] Retain or move a helper only when it is an existing reusable pure
  calculation, decoder, formatter, alignment search, or atomic protocol which
  Basil does not provide. This plan authorizes moving existing FastRX helpers
  and consolidating the two existing sequencer formatters into one generic
  packer; it does not authorize opportunistic helper creation elsewhere.
- [x] Inline the short A-state sequence and the small batching/checkpoint rules
  as specified below, even though this intentionally duplicates a few lines
  between comparator and CDAC orchestration. Local visibility is preferred to
  another abstraction for these cases.
- [x] Keep `_convert_dac_rail_percent_to_codes()` in `scan_cdac.py` and call it
  from comparator recipe construction. It remains a substantial pure CDAC
  calculation with unit coverage, not a literal or a new parameter class.
- [x] Treat `PvtParams` and existing implementation records as narrowly scoped
  exceptions already established elsewhere; do not use them as precedent for
  adding new scan infrastructure types.

## Phase 0: capture the working baseline

- [x] Record `git status --short --untracked-files=all`, the changed-file
  statistics, Python version, and dependency lock state before editing. Do not
  clean or overwrite the existing dirty worktree.
- [x] Run the focused software tests before editing:

  ```text
  uv run pytest -q flow/scans/test_helpers.py flow/scans/test_seqgen.py
  uv run pytest -q flow/scans/test_fastrx.py -m "not hw"
  uv run pytest -q flow/scans/test_comp.py flow/scans/test_cdac.py
  ```

- [x] Run `uv run pytest -q` and record its complete pass/skip/deselection
  counts as the minimum post-refactor test baseline.
- [x] Create an ignored baseline directory beneath
  `build/regression/post_compdac/before/`. Do not add captured data or generated
  regression artifacts to Git.
- [x] Serialize a canonical fingerprint of every current ADC campaign point
  from `scan_adc.build_variants()`, including point order and every
  `AdcTbParams` field.
- [x] Serialize canonical fingerprints of comparator smoke, offset,
  common-mode, sampling-noise, and sampling-noise-repair variants. Preserve
  point order, campaign cardinality, fixed voltages, conversions, CDAC states,
  sampling mode, sequence strings, and sweep provenance fields.
- [x] Serialize canonical fingerprints of CDAC smoke, commissioning, and
  capacitor variants, plus representative outputs of the coarse/fine adaptive
  scheduler for bracketed, unbracketed, boundary, and resumed curves.
- [x] Save the exact sequencer byte arrays and FastRX alignment result for at
  least these representative configurations:

  - one normal ADC conversion with its complete RX_SEN window;
  - one comparator track point and one hold point;
  - one comparator/CDAC A-state setup preamble with RX_SEN disabled;
  - one CDAC 1-to-0 point and one 0-to-1 point;
  - both radix17 and radix20 ADC flavors where the derived capture width can
    differ.

- [x] Run the accepted analysis targets against their existing immutable HDF5
  inputs and save machine-readable numerical summaries beneath the baseline
  directory:

  ```text
  uv run python -m flow.analysis.runner adc_noise_vs_rate
  uv run python -m flow.analysis.runner comp_system_common_mode
  uv run python -m flow.analysis.runner comp_system_sampling_noise
  uv run python -m flow.analysis.runner cdac_system_cap_mismatch
  ```

  Intentional storage deviation: the already accepted pre-refactor renderings
  remained in their stable `build/analysis` directories instead of being
  duplicated beneath `before/`. The numerical oracle is under `before/`; all
  regenerated post-refactor artifacts are under `after/`.

- [x] For ADC analysis, save the analyzed conversion rates, sample counts,
  means, RMS noise, and any reported ENOB/code-distribution values. For
  comparator analysis, save every curve's ADC index, campaign axes, validity,
  P16/P50/P84, threshold, and input-referred noise. For CDAC analysis, save
  every fitted transition and extracted main, differential, combined, and
  direction-bias value.
- [x] Treat numerical analysis summaries—not PNG checksums—as the regression
  oracle. Images can contain renderer metadata even when their data are
  identical.

## Phase 1: move scan constants to their owners

### Comparator recipes

- [x] Remove `SCAN_OUTDIR` from module scope and define the default
  `build/scan_comp` root inside `run_scan()` where it is used.
- [x] Make the 100 uV step and 1,000 trials local to each comparator campaign
  expansion function which creates those complete fixed points. Continue to
  record `sweep_step_v=100e-6`, `conversions=1000`, and `sweep_stage="fine"`
  in every generated point.
- [x] Make the `0.7, 0.8, 0.9, 1.0, 1.1, 1.2 V` common-mode axis and the
  `0..25 mV` differential grid local to `build_common_mode_variants()`.
- [x] Make the offset campaign's common mode and differential grid local to
  `build_offset_variants()`. Comparator scans remain fixed-grid scans and must
  not acquire a CDAC-style adaptive coarse stage.
- [x] Make the `0, 25, 50, 75, 100%` complementary P/N coupling axis, 0.7 V
  common mode, track/hold modes, and `0..25 mV` grid local to
  `build_sampling_noise_variants()`.
- [x] Make the two maintained repair selections local to
  `build_sampling_noise_repair_variants()`; the repair builder continues to
  filter complete curves generated by the normal sampling recipe.
- [x] Continue calculating the balanced CDAC state with
  `_convert_dac_rail_percent_to_codes(50, weights)`. Do not restore a literal
  radix-dependent bit string.

### CDAC recipes and timing strings

- [x] Remove `SCAN_OUTDIR` from module scope and define the default
  `build/scan_cdac` root inside `run_scan()`.
- [x] Keep the CDAC-only adaptive scheduler in `scan_cdac.py`. Make its 1 mV /
  128-trial coarse policy, 100 uV / 1,000-trial fine policy, and 10%/90%
  probability bracket values local to the scheduler functions which use them.
- [x] Remove `CDAC_SAMPLE_WORDS`. Construct the existing 32-word CDAC timing
  directly in `_build_cdac_params()` as explicit binary-string runs, matching
  the style of the ADC default sequences.
- [x] Preserve the current zero-based word placement exactly: INIT and the
  initial LOGIC event at word 1, SAMP high for words 3 through 19 inclusive,
  the A-to-B LOGIC event at word 21, and the sole COMP event at word 26.
- [x] Derive the informational sample aperture from the stored
  `seq_samp_pattern` and `symbol_rate`. The present pattern must still report
  136 asserted sample symbols / 1.6 GBd = 85 ns.
- [x] Do not add `sample_aperture_s` to `AdcTbParams`: the four explicit
  `seq_*_pattern` fields remain the authoritative HDL21-digestible timing
  inputs.

### Visible acquisition policy

- [x] Remove `build_trial_batches()` and inline its small rule in both
  comparator and CDAC runners: non-fine points use one batch; a fine point is
  split into consecutive 100-trial batches plus any remainder.
- [x] Remove `should_time_distribute_fine_point()` and inline its rule in both
  runners: at most one fine point per curve is time-distributed when the first
  batch probability lies inclusively between 0.15 and 0.85.
- [x] Keep the 0.5 s interval local beside the conditional batch sleep in each
  runner. Ordinary fine points retain zero inter-batch sleep; the selected
  checkpoint retains nine 0.5 s intervals.
- [x] Keep the 0.1 s input-settling wait local beside each AWG update in both
  runners. Do not shorten or remove it.
- [x] Continue persisting the executed batch sizes, checkpoint interval,
  settling duration, elapsed capture time, FastRX loss count, and SPI mismatch
  count in measurement readbacks.

## Phase 2: give shared pure code neutral ownership

### FastRX calculations

- [x] Add `flow/scans/fastrx.py` and move these existing definitions into it
  without changing their calculation or return values:

  - `FastRxCaptureAlignment`;
  - `calculate_fastrx_capture_alignment()`;
  - `calculate_single_sample_fastrx_capture_alignment()`;
  - `convert_fastrx_words_to_adc()`;
  - `convert_fastrx_words_to_comp()`.

- [x] Update all scan modules, behavioral callers, and tests to import moved
  names directly from `flow.scans.fastrx`. Do not leave compatibility
  re-exports in `scan_adc.py` or `scan_comp.py`.
- [x] Keep `convert_dac_caps_to_adc_weights()` and
  `convert_dout_to_normalized_dout()` in `scan_adc.py`. They are general ADC
  reconstruction calculations also used by the behavioral scan, not FastRX
  transport APIs.
- [x] Keep Basil FastRX enable/reset, FIFO reads, overflow checks, and capture
  loops visible in each physical scan; do not wrap them in `fastrx.py`.

### Generic sequencer packing

- [x] Add `flow/scans/seqgen.py` with one generic
  `convert_params_to_seqgen_fmt(params, rx_sen_pattern)` function. Generalize
  the existing ADC formatter rather than creating multiple wrapper APIs.
- [x] Define `rx_sen_pattern` as a binary string containing exactly one bit per
  eight-symbol sequencer word. Validate its length, binary contents, and the
  required trailing low word before packing it into control byte lane four.
- [x] Preserve phase rotation, serializer bit order, eight-byte word layout,
  RX_SEN bit position, and RX_TEST-low behavior exactly.
- [x] Have `scan_adc.py` construct a contiguous RX_SEN string whose asserted
  width equals the already validated FPGA `DATA_SIZE`/ADC capture width.
- [x] Have comparator and CDAC measurement paths construct an RX_SEN string
  with exactly one asserted word at the selected alignment point.
- [x] Remove `convert_params_to_single_sample_seqgen_fmt()` and update every
  caller to use the generic packer. Do not keep re-export shims.

### Explicit A-state preamble

- [x] Remove `compose_comp_a_state_setup_params()`; this short recipe does not
  justify a specialized function.
- [x] In both `scan_comp.py` and `scan_cdac.py`, construct the same preamble
  visibly at the hardware call site using local binary strings:

  - INIT is high only in word 1;
  - SAMP is low in word 0 and high for every remaining word;
  - COMP remains low for the complete preamble;
  - LOGIC is `00001111` only in word 1;
  - all four preamble phase delays are zero;
  - RX_SEN is low for every preamble word.

- [x] Use `dataclasses.replace()` locally to apply those temporary sequence
  strings to the current point before generic packing. The programmed
  `dac_astate_p/n` values remain in the original `AdcTbParams` and SPI image.
- [x] Intentionally repeat this small sequence description in the comparator
  and CDAC runners instead of importing comparator policy into CDAC or adding
  a comparator-specific preset to `seqgen.py`.

## Phase 3: make physical voltage safety consistent

- [x] In `map_board.yaml`, add `minimum_voltage_v: 1.1`, change
  `maximum_voltage_v` to `1.3`, and add `signal_headroom_v: 0.05` under the
  board's supply limits. Preserve current current limits, voltage ranges,
  loaded-voltage tolerance, and calibration tables.
- [x] Apply the 1.1--1.3 V range independently to programmable `VDD_A`,
  `VDD_D`, and `VDD_DAC` in all three physical scans.
- [x] Continue requiring `params.vdd_io` to equal the board's fixed 1.2 V
  `VDD_IO`; it is not one of the three programmable rails.
- [x] Do not apply the 1.1 V lower ASIC-supply limit to the separate Vin_cm
  source. Its programmed setpoint remains governed by its calibration and the
  safe non-negative source range.
- [x] For every planned physical point, calculate actual pin voltages as
  `Vin_p = Vin_cm + Vin_diff/2` and `Vin_n = Vin_cm - Vin_diff/2`. Validate both
  pins against `-signal_headroom_v .. actual VDD_A + signal_headroom_v`.
- [x] For fixed-grid comparator and CDAC points, validate the point voltage and
  stored sweep endpoints. For ADC DC/AC/ramp campaigns, retain the existing
  source-specific extrema calculation and apply the same final pin bounds.
- [x] Confirm that the official `Vin_cm=1.2 V`, `Vin_diff=25 mV` comparator
  endpoint is accepted because its highest pin is 1.2125 V, below 1.25 V for
  `VDD_A=1.2 V`.
- [x] Remove the comparator campaign-specific near-rail exception and the old
  fixed 10 mV guard. All campaigns use the same board-map headroom rule.
- [x] Preserve the stricter CDAC top-plate rule: every predicted before/after
  plate voltage must remain within `0.4 V .. actual VDD_A`. Signal-pin
  headroom does not relax this internal operating constraint.
- [x] Perform all static supply, calibration, signal-pin, and CDAC-plate checks
  before creating a run directory, importing GPIB/Basil hardware, or enabling
  an instrument.
- [x] Apart from helper imports and this preflight move, preserve
  `scan_adc.py`'s current Basil configuration, sequencer repetition, FastRX
  capture, scope acquisition, persistence, and shutdown order.

## Phase 4: regression gates after each refactoring stage

- [x] After campaign-localization edits, regenerate the ADC/comparator/CDAC
  parameter fingerprints and compare them field-for-field and point-for-point
  with the baseline. Stop immediately on any unplanned difference.
- [x] After `seqgen.py` extraction, compare every representative packed byte
  array exactly. Differences in any serializer byte, RX_SEN word, sequence
  size, or phase-adjusted pattern are regressions.
- [x] After `fastrx.py` extraction, compare every alignment field exactly and
  run the existing valid, malformed-identifier, discontinuous-frame,
  nonzero-unused-bit, rollover, and missing-word decoder tests.
- [x] Add exact tests for the explicit CDAC timing positions and the derived
  85 ns sample aperture. Tests must not import a replacement
  `CDAC_SAMPLE_WORDS` constant.
- [x] Add exact tests for the generic sequencer packer with an ADC window, a
  one-word comparator capture, an all-zero setup capture, phase rotation,
  invalid mask length, non-binary mask data, and an asserted final word.
- [x] Add pre-hardware safety tests for supply values at 1.1 and 1.3 V, values
  just outside both limits, fixed/mismatched VDD_IO, both ±50 mV signal
  boundaries, points just beyond them, and the official 1.2 V/25 mV campaign
  endpoint.
- [x] Add CDAC tests proving that the ±50 mV signal allowance does not bypass
  the independent 0.4 V/top-of-VDD_A plate-voltage rejection.
- [x] Rerun the focused software tests after each phase rather than waiting for
  the entire refactor to finish.

## Phase 5: end-to-end analysis regression

- [x] Rerun the same four accepted analysis targets into
  `build/regression/post_compdac/after/` without modifying or rewriting their
  source HDF5 files.
- [x] Compare ADC numerical summaries element-for-element with the baseline.
  Means, RMS values, conversion-rate axes, sample counts, and derived metrics
  must be identical because neither measurement data nor ADC analysis changes.
- [x] Compare comparator curve membership, decision polarity, validity class,
  P16/P50/P84, threshold, and input-referred noise element-for-element with the
  baseline for both common-mode and sampling-noise campaigns.
- [x] Compare CDAC curve selection, fitted transitions, extracted capacitance
  terms, side asymmetry, and direction bias element-for-element with the
  baseline.
- [x] Require identical analysis artifact names and counts and inspect the
  regenerated 2x4 comparator/CDAC plot sets for missing curves, changed axes,
  or styling regressions. Do not require byte-identical PNG files.
- [x] If an analysis result differs, first verify input-file membership and
  point ordering, then parameter reconstruction, then decoder/sequence
  fingerprints. Do not accept a tolerance or update the baseline until the
  difference has a concrete intended cause.

## Phase 6: final verification and documentation

- [x] Run the complete non-hardware suite with `uv run pytest -q`. The final
  pass count must be at least the recorded baseline, with no new unexpected
  skips or deselections.
- [x] Run Ruff on every changed Python file and `git diff --check`.
- [x] Inspect tracked and untracked state with the repository cleanup commands
  in `AGENTS.md`; preserve all unrelated user changes and ignored local tools.
- [x] Update `flow/scans/readme.md` so helper ownership points to `fastrx.py`
  and `seqgen.py`, while ADC code weighting remains attributed to
  `scan_adc.py`.
- [x] Update this document as work proceeds by changing a box to `[x]` only
  after its stated regression gate passes. Record command results and any
  intentional deviations adjacent to the relevant item.
- [x] After all software and bit-level parity gates pass, run a bounded fresh
  physical regression which writes new HDF5 data. Recapture one representative
  ADC noise point, one complete comparator S-curve, and one complete CDAC
  transition curve; analyze each through the normal typed `Meas* -> Analysis*`
  path and compare measurement quality with accepted pre-refactor captures.
- [x] Require zero FastRX losses and SPI mismatches in every fresh point. Check
  ADC input-referred and scope noise within 10%, comparator threshold within
  100 uV and noise within 10%, and the CDAC transition within one 100 uV fine
  grid step with normalized step magnitude within 1%.

## Execution record

- Baseline: focused scan tests passed 58 tests with 4 hardware deselections;
  the complete suite passed 235 tests with 19 hardware deselections. Python was
  3.9.25, uv was 0.10.2, and the uv lock hash was
  `f770a532645b3f5d46487b716d473a382121f63935d679b94da0cad0c6e44984`.
- Campaign parity: all 18,379 expanded points across the nine ADC, comparator,
  and CDAC builders match their ordered baseline hashes exactly. No field,
  point count, or point ordering changed.
- Transport parity: representative ADC, track, hold, A-state, CDAC 1-to-0, and
  CDAC 0-to-1 packed sequencer bytes match exactly. Every FastRX alignment
  field matches; only the record's intentional module owner moved. Both board
  flavors contain 16 CDAC elements, so radix17 and radix20 each derive a
  17-bit FastRX capture width.
- Data-model parity: no scan-policy or campaign dataclass was added. The input
  path remains `*TbParams -> *Params`; producers still return the existing
  `MeasAdcExt`, `MeasCompExt`, and `MeasCdacExt` hierarchy; analysis still
  consumes `Meas*` and returns the existing `Analysis*` records. HDF5 schemas
  and analysis algorithms were unchanged.
- Accepted-HDF5 regression: all numerical records matched element-for-element.
  The post-refactor timings include real PNG/PDF/SVG rendering, whereas the
  baseline timings captured the numerical oracle without duplicating plots.

  | Target | Baseline numerical time | Post-refactor analysis + plots | Artifacts |
  | --- | ---: | ---: | ---: |
  | ADC noise vs conversion rate | 115.003 s | 137.854 s | 6 |
  | Comparator common mode | 183.898 s | 216.945 s | 12 |
  | Comparator sampling noise | 316.912 s | 352.635 s | 12 |
  | CDAC A-to-B values | 915.160 s | 971.996 s | 15 |

- All 45 regenerated artifacts have the expected names. ADC plots are
  1920x1080; comparator and CDAC plots are 3200x1800. The complete comparator
  and CDAC sets were visually inspected for missing curves, axes, labels, and
  styling regressions.
- Final verification: focused scan tests passed 69 tests with 4 hardware
  deselections; `uv run pytest -q` passed 246 tests with 19 hardware
  deselections. Ruff passed every changed Python file, `git diff --check`
  passed, the dependency lock hash was unchanged, and tracked/untracked state
  was inspected without cleaning the user's dirty worktree.
- Fresh physical regression: new HDF5 measurements were captured after all
  software parity gates passed:

  ```text
  adc-positive: adc/20260807_153418
  adc-negative: adc/20260807_154154
  comparator: comp/20260807_153632
  cdac: cdac/20260807_153816
  regression: build/regression/post_compdac/physical/20260807
  ```

  The ADC points use ADC00 at 80 MBd with 1,000 conversions. The accepted old
  nominal +50 mV capture physically measured -57.4 mV because it predates the
  intentional input-polarity calibration correction. Fresh +50 mV measured
  +52.3 mV and produced a code above midscale; a fresh mirrored -50 mV point
  measured -61.9 mV and supplied the like-polarity noise comparison. Its
  input-referred noise changed from 1.292 mV RMS to 1.252 mV RMS (-3.07%), and
  scope noise changed by +1.68%.
- The fresh ADC00 comparator curve contains all 251 points from 0 through
  25 mV at 100 uV spacing and 1,000 trials per point. Its threshold changed by
  +6.2 uV, input-referred noise by -3.89%, and summed FastRX capture time by
  -0.49% relative to the accepted curve.
- The fresh ADC00 P-side C16, 1-to-0, `diffcaps=1` CDAC curve completed its
  adaptive coarse/fine acquisition in 26 HDF5 points. Its transition changed
  by +87.8 uV, normalized step magnitude by +0.049%, and summed FastRX capture
  time by +0.54% relative to the accepted curve.
- Every fresh capture had zero FastRX losses and zero SPI mismatches. All
  physical gates passed; the numerical report and representative comparison
  plot are stored in the regression directory above.
