# Analysis plot gallery

This is a manually maintained visual index of plots produced by the named
targets in `flow.analysis.runner`. The relative links point into the local,
ignored `build/analysis` tree, so they work in this checkout but are not
expected to resolve on GitHub.

When a target is rerun, update its output-directory timestamp and image links
here. CSV artifacts are intentionally omitted.

## ADC transfer curve

Target: `adc_transfer_curve`

Output: `build/analysis/adc/20260808_0049`

![ADC00 transfer curve](../../build/analysis/adc/20260808_0049/adc00_transfer_curve.png)

## ADC ramp nonlinearity

Target: `adc_ramp_nonlinearity`

Output: `build/analysis/adc/20260812_1238`

### ADC00

![ADC00 ramp transfer](../../build/analysis/adc/20260812_1238/adc00_ramp_transfer.png)

![ADC00 ramp histogram](../../build/analysis/adc/20260812_1238/adc00_ramp_histogram.png)

![ADC00 ramp weights](../../build/analysis/adc/20260812_1238/adc00_ramp_weights.png)

![ADC00 ramp nonlinearity](../../build/analysis/adc/20260812_1238/adc00_ramp_nonlinearity.png)

### ADC01

![ADC01 ramp transfer](../../build/analysis/adc/20260812_1238/adc01_ramp_transfer.png)

![ADC01 ramp histogram](../../build/analysis/adc/20260812_1238/adc01_ramp_histogram.png)

![ADC01 ramp weights](../../build/analysis/adc/20260812_1238/adc01_ramp_weights.png)

![ADC01 ramp nonlinearity](../../build/analysis/adc/20260812_1238/adc01_ramp_nonlinearity.png)

### ADC02

![ADC02 ramp transfer](../../build/analysis/adc/20260812_1238/adc02_ramp_transfer.png)

![ADC02 ramp histogram](../../build/analysis/adc/20260812_1238/adc02_ramp_histogram.png)

![ADC02 ramp weights](../../build/analysis/adc/20260812_1238/adc02_ramp_weights.png)

![ADC02 ramp nonlinearity](../../build/analysis/adc/20260812_1238/adc02_ramp_nonlinearity.png)

### ADC03

![ADC03 ramp transfer](../../build/analysis/adc/20260812_1238/adc03_ramp_transfer.png)

![ADC03 ramp histogram](../../build/analysis/adc/20260812_1238/adc03_ramp_histogram.png)

![ADC03 ramp weights](../../build/analysis/adc/20260812_1238/adc03_ramp_weights.png)

![ADC03 ramp nonlinearity](../../build/analysis/adc/20260812_1238/adc03_ramp_nonlinearity.png)

## ADC calibration

Target: `adc_calibration`

Output: `build/analysis/adc/20260817_1317`

![ADC00 calibration weights](../../build/analysis/adc/20260817_1317/adc00_calibration_weights.png)

![ADC00 calibration transfer](../../build/analysis/adc/20260817_1317/adc00_calibration_transfer.png)

![ADC00 calibration code density](../../build/analysis/adc/20260817_1317/adc00_calibration_code_density.png)

![ADC00 calibration INL and DNL](../../build/analysis/adc/20260817_1317/adc00_calibration_inl_dnl.png)

## Post-filter ADC00 fixed-input noise

Target: `adc00_fixed_input_noise`

Output: `build/analysis/adc/20260819_1728`

![ADC00 50 mV noise versus conversion rate](../../build/analysis/adc/20260819_1728/adc00_50mv_noise_vs_conversion_rate.png)

![ADC00 50 mV output-code distributions](../../build/analysis/adc/20260819_1728/adc00_50mv_output_code_distributions.png)

![ADC00 50 mV 2 MSPS decision-path density](../../build/analysis/adc/20260819_1728/adc00_50mv_2msps_decision_path_density.png)

![ADC00 50 mV 6 MSPS decision-path density](../../build/analysis/adc/20260819_1728/adc00_50mv_6msps_decision_path_density.png)

![ADC00 50 mV 10 MSPS decision-path density](../../build/analysis/adc/20260819_1728/adc00_50mv_10msps_decision_path_density.png)

## ADC noise versus conversion rate

Target: `adc_noise_vs_rate`

Output: `build/analysis/adc/20260819_0138`

![ADC00 noise versus conversion rate](../../build/analysis/adc/20260819_0138/adc00_noise_vs_conversion_rate.png)

![ADC01 noise versus conversion rate](../../build/analysis/adc/20260819_0138/adc01_noise_vs_conversion_rate.png)

## ADC code distributions and decision paths

Target: `adc_code_distributions`

Output: `build/analysis/adc/20260819_0141`

### Physical ADC distributions

![ADC00 50 mV output-code distributions](../../build/analysis/adc/20260819_0141/adc00_50mv_dc_output_code_distributions.png)

![ADC00 100 mV output-code distributions](../../build/analysis/adc/20260819_0141/adc00_100mv_dc_output_code_distributions.png)

![ADC01 50 mV output-code distributions](../../build/analysis/adc/20260819_0141/adc01_50mv_dc_output_code_distributions.png)

![ADC01 100 mV output-code distributions](../../build/analysis/adc/20260819_0141/adc01_100mv_dc_output_code_distributions.png)

### Physical ADC decision paths

![ADC00 50 mV 2 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc00_50mv_2msps_decision_path_density.png)

![ADC00 50 mV 10 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc00_50mv_10msps_decision_path_density.png)

![ADC00 100 mV 2 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc00_100mv_2msps_decision_path_density.png)

![ADC00 100 mV 10 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc00_100mv_10msps_decision_path_density.png)

![ADC01 50 mV 2 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc01_50mv_2msps_decision_path_density.png)

![ADC01 50 mV 10 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc01_50mv_10msps_decision_path_density.png)

![ADC01 100 mV 2 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc01_100mv_2msps_decision_path_density.png)

![ADC01 100 mV 10 MSPS decision paths](../../build/analysis/adc/20260819_0141/adc01_100mv_10msps_decision_path_density.png)

### HDL21-generated ADC simulation

![HDL21 2 MSPS output-code histogram](../../build/analysis/adc/20260819_0141/spice_hdl21gen_2msps_output_code_histogram.png)

![HDL21 2 MSPS decision paths](../../build/analysis/adc/20260819_0141/spice_hdl21gen_2msps_decision_paths.png)

![HDL21 6 MSPS output-code histogram](../../build/analysis/adc/20260819_0141/spice_hdl21gen_6msps_output_code_histogram.png)

![HDL21 6 MSPS decision paths](../../build/analysis/adc/20260819_0141/spice_hdl21gen_6msps_decision_paths.png)

![HDL21 10 MSPS output-code histogram](../../build/analysis/adc/20260819_0141/spice_hdl21gen_10msps_output_code_histogram.png)

![HDL21 10 MSPS decision paths](../../build/analysis/adc/20260819_0141/spice_hdl21gen_10msps_decision_paths.png)

## ADC power versus conversion rate

Target: `adc_power_vs_rate`

Output: `build/analysis/adc/20260819_1734`

### Measured power

![ADC00 power versus conversion rate](../../build/analysis/adc/20260819_1734/adc_power_vs_conversion_rate_adc00.png)

![ADC01 power versus conversion rate](../../build/analysis/adc/20260819_1734/adc_power_vs_conversion_rate_adc01.png)

### Simulated power

![Ideal SPICE power versus conversion rate](../../build/analysis/adc/20260819_1734/spice_ideal_power_vs_conversion_rate.png)

![PEX SPICE power versus conversion rate](../../build/analysis/adc/20260819_1734/spice_pex_power_vs_conversion_rate.png)

![Ideal SPICE 10 MSPS supply power](../../build/analysis/adc/20260819_1734/spice_ideal_10msps_supply_power.png)

![PEX SPICE 10 MSPS supply power](../../build/analysis/adc/20260819_1734/spice_pex_10msps_supply_power.png)

### Measured dynamic detail

![ADC00 80 MBd sine waveforms](../../build/analysis/adc/20260819_1734/adc00_80mbd_sine_waveforms.png)

![ADC00 80 MBd sine fit and spectrum](../../build/analysis/adc/20260819_1734/adc00_80mbd_sine_fit_and_spectrum.png)

![ADC01 80 MBd sine waveforms](../../build/analysis/adc/20260819_1734/adc01_80mbd_sine_waveforms.png)

![ADC01 80 MBd sine fit and spectrum](../../build/analysis/adc/20260819_1734/adc01_80mbd_sine_fit_and_spectrum.png)

## ADC comparator-to-logic timing

Target: `adc_noise_vs_comp_time`

Output: `build/analysis/adc/20260819_0036`

![ADC00 noise versus conversion rate and logic offset](../../build/analysis/adc/20260819_0036/adc00_noise_vs_conversion_rate_and_logic_offset.png)

![ADC01 noise versus conversion rate and logic offset](../../build/analysis/adc/20260819_0036/adc01_noise_vs_conversion_rate_and_logic_offset.png)

## Comparator common mode

Target: `comp_system_common_mode`

Output: `build/analysis/comp/20260819_0100`

![ADC00 comparator common mode](../../build/analysis/comp/20260819_0100/adc00_comparator_common_mode.png)

![ADC01 comparator common mode](../../build/analysis/comp/20260819_0100/adc01_comparator_common_mode.png)

![ADC02 comparator common mode](../../build/analysis/comp/20260819_0100/adc02_comparator_common_mode.png)

![ADC03 comparator common mode](../../build/analysis/comp/20260819_0100/adc03_comparator_common_mode.png)

## Comparator sampling noise

Target: `comp_system_sampling_noise`

Output: `build/analysis/comp/20260819_1729`

![ADC00 comparator sampling noise](../../build/analysis/comp/20260819_1729/adc00_comparator_sampling_noise.png)

![ADC01 comparator sampling noise](../../build/analysis/comp/20260819_1729/adc01_comparator_sampling_noise.png)

![ADC02 comparator sampling noise](../../build/analysis/comp/20260819_1729/adc02_comparator_sampling_noise.png)

![ADC03 comparator sampling noise](../../build/analysis/comp/20260819_1729/adc03_comparator_sampling_noise.png)

## Comparator candidate sweep

Target: `comp_candidate_sweep`

Output: `build/analysis/comp/20260819_0206`

![Comparator candidate noise, power, and settling](../../build/analysis/comp/20260819_0206/comp_candidate_noise_power_settling.png)

![Comparator candidate noise-power trade-off](../../build/analysis/comp/20260819_0206/comp_candidate_noise_power_tradeoff.png)

## CDAC capacitor mismatch

Target: `cdac_system_cap_mismatch`

No accepted runner-generated plot directory is currently present under
`build/analysis`. Run the target and add its ADC00--ADC03 mismatch plots and
shared comparison plot here.

## Aggregate target

`adc_rate_characterization` reruns `adc_noise_vs_rate`,
`adc_code_distributions`, and `adc_power_vs_rate`; its outputs are represented
in the corresponding sections above.
