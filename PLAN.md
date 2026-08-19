# Unified plotting style and API refactor

## Summary

Standardize every active first-party plot—excluding the legacy behavioral model—on the thesis-tested presentation:

- Exact 9.6 × 5.4 inch, 16:9 canvas.
- Exactly 1920×1080 pixels for PNG at 200 DPI.
- Black text; 13 pt titles and 11 pt labels, ticks, legends, and information boxes.
- Figure titles positioned consistently near the panels.
- PNG, PDF, and SVG from one shared save function.
- Fully opaque data artists.
- Categorical palette ordered Nord blue → orange → green → purple → yellow → cyan → red → teal.
- Continuous spectrum map ordered Nord blue → orange → yellow.

The diff-amp proof currently uses 13 pt titles and 11 pt supporting text, which becomes approximately 8.4 pt and 7.1 pt at thesis text width. That becomes the repository-wide standard. :codex-annotation{index="1"}

Replace relative `fontsize="small"` values with explicit 11 pt sizes. Currently `small` is relative to the base font; with a 13 pt base it would resolve to about 10.8 pt, but an explicit size makes the contract unambiguous. :codex-annotation{index="2"}

The shared analysis module currently has 16 exact-canvas plots, 10 tightly cropped plots, and one fixed-size GIF. The result will be one exact-canvas policy for every retained plot; `tight_layout()` will arrange contents inside the canvas, while `bbox_inches=None` preserves dimensions. :codex-annotation{index="3"} :codex-annotation{index="20"}

## Shared style and rendering

- Replace `NORD_COLORS` with a single exported `CURVE_COLORS` categorical palette and add a shared blue → orange → yellow `SPECTRUM_COLOR_MAP`. The Matplotlib axes cycle will use `CURVE_COLORS`, so ordinary curves no longer set individual colors manually. :codex-annotation{index="5"}
- Retain individual Nord constants only as the centralized definitions from which the palette, grid, spine, and semantic colors are built.
- Use the first three palette entries consistently for Analog, Digital, and DAC where rail identity matters; functions will unpack them from the palette instead of embedding color constants. :codex-annotation{index="12"}
- Remove translucency from curves, markers, histograms, violins, filled distributions, and stacked power components. Use outlines, solid light palette entries, or hatching where overlapping series need differentiation. Grid lines and diagnostic guide regions may remain visually light. :codex-annotation{index="6"}
- Replace every nonstandard active figure size—including 8×5, 8×4.5, 8.5×5.5, 9×9, 9.6×7.2, and 16×9—with `FULL_HD_FIGSIZE`. :codex-annotation{index="13"} :codex-annotation{index="16"} :codex-annotation{index="21"}
- Make the shared save function the only save implementation. It will always use the shared DPI, white background, exact canvas, and supplied formats.
- Keep `output_path` keyword-only on every plotter because it makes runner artifact naming explicit. No plotter will silently add ADC suffixes or otherwise rewrite the requested stem. :codex-annotation{index="14"}
- Document this typography, palette, opacity, canvas, and save contract in the analysis README.

## Plotting APIs and typed data flow

- Rename sequence arguments uniformly:
  - `measurements` → `msmt_list`.
  - `measurement_groups` → `msmt_list2d`.
  - `analyses` → `analysis_list`.  
  :codex-annotation{index="10"} :codex-annotation{index="15"} :codex-annotation{index="17"} :codex-annotation{index="18"}
- Keep validation and derivation in measurement dataclasses or `analyze_*` functions. Plotters consume completed typed data and will not reproduce acquisition or alignment checks.

### Waveforms

- Add a validated generic waveform analysis type containing one aligned time axis, one to four named traces, units, and derived context text.
- Replace both `plot_scope_waveforms()` and `plot_measurement_waveforms()` with one shared `plot_waveforms(analysis, *, output_path, formats)` renderer.
- Add pure conversion routines for:
  - A typed measurement record plus optional record/signal selection.
  - Raw aligned Basil scope waveforms plus their track mapping.
- The selection and alignment checks currently inside the plotter move to those conversion routines; the renderer itself receives only the typed waveform result.
- Update the SERDES, diff-amp, FastRX, and analysis call sites to construct this typed result. The raw scope renderer cannot simply be deleted today because the SERDES and diff-amp hardware pytest targets use it, so those callers are migrated first. :codex-annotation{index="23"}
- Remove the unused `plot_adc_fastrx_scope_comparison()` and its unowned scope/FastRX bit, edge-time, and sample-value arguments. The actively produced typed FastRX measurement artifacts remain. :codex-annotation{index="4"}

### ADC plots

- Derive ADC titles from `msmt`, `msmt_list`, backend, ADC index, campaign, and analyzed rate. Remove externally supplied `title` arguments from ADC noise, distribution, power-sweep, and power-waveform plotters. :codex-annotation{index="7"} :codex-annotation{index="9"}
- Remove the test-only quadratic guide feature.
- Move comparison-series labels into the completed `AnalysisAdcNoiseSweep` result, populated and validated by the comparison analysis. Remove `quadratic_guide` and `series_labels` from the plotting signature. :codex-annotation{index="8"}
- Make `plot_adc_power_sweep()` render exactly one physical ADC or one simulation source per call. The analysis runner will group the data and pass explicit output stems such as `..._adc00`, eliminating output-path mutation inside the plotter.
- Make `plot_adc_power_waveform()` use record zero and derive its title from the SPICE measurement and analyzed conversion rate; remove `title` and `record_index` from its signature. :codex-annotation{index="11"}
- Split the overloaded static/ramp nonlinearity renderer into two public typed functions rather than using a union argument with a conditionally required analysis.
- Delete `plot_adc_noise_violin_sweep()` and its runner/test call sites. Retain `plot_adc_noise_distribution_sweep()` as the single raw histogram representation.
- Delete the decision-density GIF and its runner/test call sites. Inline the complete density rendering into `plot_adc_decision_path_density()`, eliminating `_draw_adc_decision_path_density()`. :codex-annotation{index="22"}

### Comparator and CDAC plots

- Replace `plot_comp_campaign()` plus its two private renderers with two self-contained public functions:
  - `plot_comp_sampling_campaign(msmt_list2d, analysis_list, *, output_path, formats)`
  - `plot_comp_common_mode_campaign(msmt_list2d, analysis_list, *, output_path, formats)`
- Update the two analysis-runner targets to call the appropriate function directly. The campaign differences remain necessary, but the dispatcher/private-renderer architecture does not. :codex-annotation{index="19"}
- Render both functions on the shared Full-HD canvas with 11 pt annotations instead of `x-small`/`xx-small`.
- Convert CDAC and comparator colors to the categorical palette and continuous spectrum map; remove literal black data-series formats and translucent fills.

### Diff-amp analysis

- Move `DiffampNoiseAnalysis` to the shared analysis types as `AnalysisDiffampNoise`.
- Move `analyze_diffamp_noise()` into an analysis module and `plot_diffamp_noise()` into the shared plotting module.
- Keep the hardware pytest target as the acquisition runner; no analysis-runner target is required.
- Reduce the plot signature to `plot_diffamp_noise(analysis: AnalysisDiffampNoise, *, output_path: Path, formats: Sequence[str] = DEFAULT_FORMATS) -> tuple[Path, ...]`.
- Use the global style directly and remove its local font, black-text, save-format, and canvas overrides. :codex-annotation{index="24"}

## Physics plots

- Leave the survey and detector-model functions in `phys/`, but import the shared canvas, DPI, formats, typography, categorical palette, spectrum map, axes/grid/legend styling, and save function. :codex-annotation{index="25"}
- Map technology categories and pixel pitches onto `CURVE_COLORS` in stable order, beginning blue, orange, green, purple, and yellow.
- Make `plot_hit_rate_vs_fluence()` and `plot_max_counting_rate_vs_window()` accept keyword-only `output_path` and `formats` arguments and return `tuple[Path, ...]`.
- Convert both to Full HD, 11/13 pt typography, opaque data, white-background PNG/PDF/SVG, and shared save behavior. :codex-annotation{index="27"}
- Keep `plot_tradeoff()` configurable because it is a generic survey renderer, but route its style and save behavior entirely through the shared implementation.
- Make the physics entry points create timestamped `build/<target>/<datetime>` directories and pass explicit stems to the plotting functions.
- Do not modify any plotting or reporting code in `flow/adc/behavioral.py`; it remains a separate future cleanup. :codex-annotation{index="26"}

## Test plan

- Update the shared plot assertion so every retained PNG must be exactly 1920×1080 and every plot returns PNG, PDF, and SVG.
- Assert the exact global font sizes, black text, categorical palette order, and blue → orange → yellow spectrum endpoints.
- Inspect representative data artists to ensure their effective alpha is fully opaque.
- Test typed waveform construction from both measurement records and synthetic Basil scope captures, including misaligned traces and more than four requested traces.
- Test derived titles for physical ADC, SPICE ADC, comparator campaigns, and power waveforms.
- Test that ADC power plotting no longer rewrites output stems.
- Test the two flattened comparator campaign functions independently.
- Remove tests for the deleted FastRX comparison renderer, violin plot, quadratic guide, comparator dispatcher, density GIF, and raw scope renderer.
- Add rendering tests for both physics-model figures and the survey renderer.
- Rebuild the one-page thesis proof and visually inspect the diff-amp plot, a four-panel waveform, a comparator campaign, a decision-density heat map, and both physics figures.
- Run focused analysis/plot/runner/scan tests, `ruff`, `ty`, repository pre-commit hooks, and the full non-hardware pytest suite.
