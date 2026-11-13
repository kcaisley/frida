# FRIDA-1: a first generation 65 nm prototype {#sec-frida1}

FRIDA-1 is a 1 × 1 mm test chip in 65 nm with 16 ADC channels, submitted in October 2025 and received in March 2026.
Its four ADC flavors cross one- and two-layer capacitor arrays with two weight radixes.

## FRIDA-1 in the design space {#sec-frida1-design}

### Sampling switch {#sec-frida1-samp}

FRIDA-1's sampler is the grid's transmission gate of 32 units without dummies.
In TSMC65 into 1 pF it measures 460 Ω at mid-supply and 553 Ω at most over the input, a 346 MHz bandwidth, a largest pedestal of 0.75 mV, and 12.9 µm² of layout.
The same sizing measures 535 Ω in TSMC28 and 690 Ω in IHP130, and 236–331 Ω (at mid-supply) in TPSC65, LF150 and Tower180.

: FRIDA-1's sampler in its grid, TSMC65, into 1 pF. {#tbl-frida1-samp}

| | FRIDA-1 (TGATE, 32) | TGATE, 128 | Bootstrap, 160 |
|:--|--:|--:|--:|
| R_on, mid-supply / max (Ω) | 460 / 553 | 118 | 36 |
| Largest pedestal (mV) | 0.75 | | 10.3 |
| Layout (µm²) | 12.9 | | |

The pipeline measures the on-resistance from the track phase's time constant into a 1 pF load, between the 1/e and 1/e² crossings of a step, so that the edge's delay is excluded: $R_\mathrm{on} = \tau / C_\mathrm{load}$, an upper bound since the switch's own capacitance is included.
In TSMC65 into 1 pF, a transmission gate of 32 units measures 130–550 Ω (highest at mid-supply), the NMOS switch from 140 Ω to open above 0.7 V, the bootstrapped one 140–230 Ω at 32 units and 30–45 Ω at 160.

::: {#fig-rec-samp-ron-vin plot="rec_samp_ron_vin"}
A transmission gate of 32 units in TSMC65: On-resistance into 1 pF over the input level.
:::

::: {#fig-rec-samp-track-error-vin plot="rec_samp_track_error_vin"}
A transmission gate of 32 units in TSMC65: Track error at the end of tracking over the input level.
:::

::: {#fig-rec-samp-pedestal-vin plot="rec_samp_pedestal_vin"}
A transmission gate of 32 units in TSMC65: Pedestal over the input level.
:::

Pedestals stay within ±0.7 mV for the transmission gates and reach −2 mV for the NMOS switches at 32 units, growing with the width (−10 mV at 160).
Half-size dummies take the transmission gate's largest pedestal from 0.75 to 0.03 mV, and nearly double its area.

::: todo

- Where FRIDA-1's switch sits on @fig-samp-ron-width and what the 12-bit track time (@eq-settle) asks of it.
- The measured counterpart in @sec-frida1-measurements.
:::

### Comparator {#sec-frida1-comp}

FRIDA-1's comparator is the grid's `frida1` instance, a StrongARM.
In TSMC65 it measures 246 µV of input-referred noise, a negligible systematic offset, 292 fJ per decision, 2.0 ns at 0.5 mV, a regeneration time constant of 194 ps, 6.9 mV of kickback, and 157 µm² of layout: an $E\sigma^2$ of about 18 fJ·mV², against 3.3 for the best TSMC65 designs (@fig-comp-energy-noise).
In TSMC28 the same sizing measures 530 µV and 80 fJ; in the 130–180 nm processes and TPSC65 its latch lengths do not decide within the clock.

::: {#fig-rec-comp-noise-cm plot="rec_comp_noise_cm"}
A StrongARM comparator in TSMC65: Input-referred noise over the common mode.
:::

::: {#fig-rec-comp-metastability plot="rec_comp_metastability"}
A StrongARM comparator in TSMC65: Delay over the input (nominal common mode).
:::

The pipeline measures $\tau$ from the delays at two small inputs, $\tau = (t_1 - t_2)/\ln(v_2/v_1)$, and extrapolates below the smallest input measured with @eq-regeneration.

::: {#fig-rec-comp-scurve plot="rec_comp_scurve"}
A StrongARM comparator in TSMC65: Decision probability (nominal common mode, transient noise).
:::

::: {#fig-rec-comp-energy-supply plot="rec_comp_energy_supply"}
A StrongARM comparator in TSMC65: Energy per decision over the supply.
:::

::: todo

- Why FRIDA-1's comparator sits where it does on @fig-comp-energy-noise, and what the optimized 12-bit design (620 fJ, 100 µV, 277 µm²) changes.
- The pre-extraction estimate for the fabricated comparator (177 µV, 18 × 18 µm) against the grid's 246 µV.
:::

### Capacitor array {#sec-frida1-cdac}

::: {#fig-rec-adc-calibration-weights plot="rec_adc_calibration_weights"}
The generated FRIDA converter (behavioral): Weight error of the extracted array.
:::

::: {#fig-rec-adc-inl plot="rec_adc_inl"}
The generated FRIDA converter (behavioral): Ramp INL, design weights.
:::

::: {#fig-rec-adc-inl-calibrated plot="rec_adc_inl_calibrated"}
The generated FRIDA converter (behavioral): Ramp INL, calibrated.
:::

FRIDA-1's array is the grid's `frida1` instance: 12 bits, MSB redistribution with 5 redundant decisions (17 in all), at twice the noise minimum (@eq-cmin-noise), in difference capacitors.
Extracted in TSMC65, its gain is 0.73 (a 0.68 V full scale), its largest stage settles in 0.28 ns with a step error of 0.017 LSB, and it takes 645 µm² of layout per side.
At a matching coefficient of 1 %·√fF its 95th-percentile uncalibratable gap is 0.27 LSB and its INL with the design weights 2.4 LSB (@fig-cdac-gap).

The prototype's nominal physical capacitance, including both members of the difference pairs, is approximately 1.88 pF per branch; the same ideal estimate gives approximately 66 µV RMS, before comparator noise and other nonidealities are included.

The prototype's smallest effective weight is 0.8 fF, obtained from nominal 26.4 fF and 25.6 fF elements.

::: {#fig-rec-capdac-mismatch-inl plot="rec_capdac_mismatch_inl"}
A 12-bit array of 17 decisions in TSMC65: Worst INL with the design weights (95th percentile) over Pelgrom's coefficient.
:::

::: {#fig-rec-adc-mismatch-dnl plot="rec_adc_mismatch_dnl"}
The assembled 12-bit converter (behavioral): Worst DNL over the Pelgrom coefficient (predicted 95th percentile).
:::

::: {#fig-rec-capdac-mismatch-gap plot="rec_capdac_mismatch_gap"}
A 12-bit array of 17 decisions in TSMC65: Unrecoverable code width after ideal calibration (95th percentile).
:::

::: {#fig-rec-capdac-dac-inl plot="rec_capdac_dac_inl"}
A 12-bit array of 17 decisions in TSMC65: DAC INL by code, the 95th-percentile run at the middle condition.
:::

::: {#fig-rec-capdac-settling-stage plot="rec_capdac_settling_stage"}
A 12-bit array of 17 decisions in TSMC65: Settling to half an LSB by stage (the slower direction).
:::

::: todo

- The initial state (16'h5555) and what it does to the common-mode trajectory, power and noise; measured evidence is still missing.
:::

::: todo

- @eq-calibratable applied to FRIDA-1's weights: each stage's margin over its weight's sigma.
- The measured weights of @sec-frida1-measurements against these.
:::

### The assembled converter {#sec-frida1-adc}

The generated FRIDA design composes these three instances: its behavioral record gives 10.04 ENOB, 28.9 pJ per conversion (289 µW at 10 MS/s) and 0.76 LSB of noise (sampler 0.50, comparator 0.71), with the ladder of @fig-adc-ladder.
These single-instance predictions are what @sec-frida1-measurements compares the silicon against.

#### The behavioral converter {#sec-adc-behavioral}

The behavioral converter composes the blocks' models, each from its own characterization: the sampler's on-resistance over the input and its kT/C (@sec-sampling-switch), the comparator's noise, offset and delay over the input (@sec-comparator), and the array's plates as drawn, with each stage's step, delay and settling as the DAC's characterization measured them (@sec-cdac).
It runs the SAR loop on them.
The comparator's measured delay over the input decides when a decision is late, and its SR latch then holds the last one; each stage's plates move after its driver's delay and settle with its own time constant.

In the behavioral converter a late decision is held: the SR latch keeps its previous value.

::: {#fig-adc-architecture src="../images/report/adc_architecture"}
Circuitikz schematic of the differential ADC, redundant capacitor weights, synchronous SAR registers, and main/difference capacitor pair.
:::

The circuit diagram shows the differential architecture.
Each capacitor cell contains a main capacitor and a difference capacitor, with the effective weight shown above it.
Complementary rail drivers connect directly to the enabled decision registers.
The first three capacitor stages and the final stage are shown; three dots denote the omitted stages 3–14.
Complementary comparator outputs feed the decision registers, and a dedicated clock input controls evaluation.
Weighted decoding is external to the prototype ADC macro.

The behavioral model measures the budget as a ladder: the 10 MS/s sine from quantization alone, then adding the sampler's tracking error, its kT/C noise and jitter, the DAC's settling, the comparator's delay and its noise in turn.

::: {#fig-adc-ladder plot="adc_ladder"}
The ENOB budget, one impairment at a time.
:::

::: {#fig-rec-adc-enob-rate plot="rec_adc_enob_rate"}
The assembled 12-bit converter (behavioral): ENOB over the conversion rate.
:::

::: {#fig-rec-adc-spectrum-low plot="rec_adc_spectrum_low"}
The assembled 12-bit converter (behavioral): Spectrum at 10 MS/s, low input frequency.
:::

::: {#fig-rec-adc-noise-spectrum plot="rec_adc_noise_spectrum"}
The assembled 12-bit converter (behavioral): Output-code noise: 0.77 LSB rms = lines 0.00 ⊕ white 0.77.
:::

For the generated FRIDA design the ladder ends at 10.04 bits: the sampler's tracking error costs the most (1.65 bits), the comparator's noise 0.22, kT/C 0.06.
Its noise is 0.76 LSB, the sampler 0.50 and the comparator 0.71.

::: todo

- Why the tracking error dominates here: the transmission gate's mid-supply $R_\mathrm{on}$ into the 12-bit array (@eq-tracking), and the bootstrap's recovery.
:::

::: {#fig-rec-adc-trajectory plot="rec_adc_trajectory"}
The assembled 12-bit converter (behavioral): Decision paths at one input.
:::

::: {#fig-rec-adc-hsu-rate plot="rec_adc_hsu_rate"}
The assembled 12-bit converter (behavioral): Integrated error over the conversion rate.
:::

::: todo

- The timing-closure margins the behavioral model checks: 200 ps logic and CDAC setup, 0.3 V latch resolution, 1 mV CDAC tolerance.
- The ENOB over sequence and symbol rate (the sequence map), and which recipe the timing allows at 10 MS/s.
:::

::: {#fig-rec-adc-power-rate plot="rec_adc_power_rate"}
The assembled 12-bit converter (behavioral): Supply power over the conversion rate.
:::

The generated FRIDA design spends about 28.9 pJ per conversion, 289 µW at 10 MS/s; the SAR logic dominates.

::: {#fig-rec-adc-reference-noise plot="rec_adc_reference_noise"}
The assembled 12-bit converter (behavioral): ENOB lost to the reference's noise, sampler and comparator ideal.
:::

## Implementation of the building blocks {#sec-frida1-blocks}

### Sampling switch and comparator {#sec-frida1-samp-comp}

The sampling switch and comparator layouts were manually laid out using a traditional analog-on-top flow.
We used these designs because their architectures and device sizes were already close to the optima found in the preceding optimization steps (@sec-frida1-samp, @sec-frida1-comp).

::: {#fig-frida1-comp src="figures/layout_frida1_comp.png"}
FRIDA-1's comparator layout.
:::

::: {#fig-frida1-comp-iso src="figures/layout3d_frida1_comp.png"}
FRIDA-1's comparator in an isometric view of its layers.
:::

::: {#fig-frida1-samp src="figures/layout_frida1_samp.png"}
FRIDA-1's sampling switch layout.
:::

::: {#fig-frida1-samp-iso src="figures/layout3d_frida1_samp.png"}
FRIDA-1's sampling switch in an isometric view of its layers.
:::

### Capacitor drivers and array {#sec-frida1-cdac-impl}

The drivers were sized from standard cells.
The capacitor array was generated directly from its specification to GDS using a Python script and the KLayout Python API.

::: {#fig-frida1-capdriver src="figures/layout_frida1_capdriver.png"}
FRIDA-1's capacitor drivers.
:::

::: {#fig-frida1-capdriver-iso src="figures/layout3d_frida1_capdriver.png"}
FRIDA-1's capacitor drivers in an isometric view of their layers.
:::

::: {#fig-frida1-caparray src="figures/layout_frida1_caparray.png"}
FRIDA-1's capacitor array, metals M2 to M7.
:::

::: {#fig-frida1-caparray-iso src="figures/layout3d_frida1_caparray.png"}
FRIDA-1's capacitor array in an isometric view of its layers.
:::

: Held sampling noise against the extracted load per side for FRIDA-1's four array flavors, 100 conversions each at 50 mV input. {#tbl-held-noise}

| Design | Load per side (fF) | Held differential SD (µV) |
|:--|--:|--:|
| FRIDA-1 1L R17 | 527.7 | 116.9 |
| FRIDA-1 1L R20 | 527.7 | 127.2 |
| FRIDA-1 2L R17 (disconnected) | 499.7 | 109.9 |
| FRIDA-1 2L R20 (disconnected) | 499.6 | 102.7 |

The extracted `main − diff` relative weights matched the intended weights well after normalization; the absolute effective capacitance scale was about 16.1 % of the intended behavioral value.
The nominal two-layer flavors have disconnected upper plates, so their extracted capacitance matched the one-layer one rather than adding a parallel layer.

### Digital control logic {#sec-frida1-logic}

The digital control logic was implemented entirely in Verilog.
An OpenROAD flow converted it to layout, leaving gaps for the analog blocks.

A one-hot stage selector advances through 16 capacitor-control stages, followed by a terminal comparison that contributes to the decoded result without switching another capacitor.
Initialization loads the programmed starting state into all driver registers and seeds the selector with stage 0 active; subsequent logic-clock edges shift this one-hot enable through the chain.

::: {#fig-adc-timing-clocking src="../images/report/adc_timing"}
Initialization, sampling, comparator, and logic timing waveforms.
:::

The sequencer is a set of named recipes over four lines, INIT, SAMP, COMP and LOGIC, each a pattern of symbols at the sequencer's symbol rate: four symbols of INIT, twenty of SAMP, then one eight-symbol word per decision, COMP high for the first four symbols and LOGIC for the last four.

::: {#fig-sequences placeholder="The sequencer's recipes as timing diagrams (docs/images/sequences, drawn from the recipes): COMP duty and LOGIC phase."}
The sequences studied.
:::

::: {#fig-frida1-digital src="figures/layout_frida1_digital.png"}
The ADC channel's digital layout, metals up to M3, with the gaps left for the analog blocks.
:::

## ADC block assembly and channel layout {#sec-frida1-channel}

The individual building blocks are assembled into the ADC channel, the manually laid-out analog blocks placed in the gaps left by the digital layout, and the capacitor array placed above the drivers and logic, with a shielding plate between them.
Within this channel footprint, the capacitor structures occupy upper metal layers, allowing active circuitry to be placed beneath them.
This overlap reduces the footprint that would otherwise be required by separate capacitor and circuit regions.
The prototype channel layout measures 60.5 × 63.5 µm, or approximately 3,800 µm², satisfying the intended compact form factor.

::: {#fig-frida1-adc src="figures/layout_frida1_channel.png"}
One FRIDA-1 ADC channel, the devices and metals up to M4: the building blocks' placement under the capacitor array.
:::

::: {#fig-frida1-adc-3d src="figures/layout3d_frida1_channel.png"}
One FRIDA-1 ADC channel in an isometric view of its layers: the capacitor array above the drivers, the logic and the analog blocks.
:::

::: todo

- The strategy for isolating the power grids and routing the supplies within the channel.
- Physical verification of the assembled channel: connectivity, DRC, LVS, and extraction (@sec-cdac-parasitic, @tbl-held-noise).
:::

### Extracted sequences {#sec-clocking-pex}

::: {#fig-pex-sequences placeholder="The post-layout sequence study: COMP duty 50 to 87.5 % and LOGIC phase 180 to 315° across seven array flavors, with code spread and timing-error counts (docs/thesis/adc_pex_sequence_reference.tex)."}
Extracted converters over the comparator duty cycle and logic phase.
:::

## Chip-level arrangement {#sec-frida1-chip}

### Configuration and sequencing

A synthesized SPI register controls the configuration bits of each ADC.
The decision was made to apply the four ADC sequences externally, so four LVDS inputs were included (@sec-clocking).

### Analog inputs and comparator-output readout

The ADC inputs are connected directly to a shared wire bus; the sampling switches of the ADCs choose which ADC is sampling from that bus.
The ADC outputs are not resampled on-chip.
Instead, the positive-polarity comparator outputs drive medium-performance LVDS transmitters directly for external measurement.
The SAR logic is still on-chip, but the external DAQ system must acquire each comparator output serially in real time.

### Top-level power grids, pad ring, and assembly

The top level was assembled hierarchically with OpenROAD, using the ADC block as a hardened macro with a LEF view.

::: {#fig-frida1-padring src="figures/layout_frida1_padring.png"}
FRIDA-1's pad ring: the top level without its core.
:::

::: todo

- The chip-level power grids and a labeled pad ring.
:::

### Top-level layout and fabricated prototype

::: {#fig-frida1-top src="figures/layout_frida1_top.png"}
FRIDA-1's top-level layout.
:::

::: {#fig-frida1-die src="../images/frida_dieshot.png"}
A photograph of the fabricated FRIDA-1 die.
:::

::: {#fig-frida1-cob src="../images/frida_cob.jpg"}
FRIDA-1 mounted on its chip-on-board carrier.
:::
