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

::: todo

- Where FRIDA-1's switch sits on @fig-samp-ron-width and what the 12-bit track time (@eq-settle) asks of it.
- The measured counterpart in @sec-frida1-measurements.
:::

### Comparator {#sec-frida1-comp}

FRIDA-1's comparator is the grid's `frida1` instance, a StrongARM.
In TSMC65 it measures 246 µV of input-referred noise, a negligible systematic offset, 292 fJ per decision, 2.0 ns at 0.5 mV, a regeneration time constant of 194 ps, 6.9 mV of kickback, and 157 µm² of layout: an $E\sigma^2$ of about 18 fJ·mV², against 3.3 for the best TSMC65 designs (@fig-comp-energy-noise).
In TSMC28 the same sizing measures 530 µV and 80 fJ; in the 130–180 nm processes and TPSC65 its latch lengths do not decide within the clock.

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

::: todo

- @eq-calibratable applied to FRIDA-1's weights: each stage's margin over its weight's sigma.
- The measured weights of @sec-frida1-measurements against these.
:::

### The assembled converter {#sec-frida1-adc}

The generated FRIDA design composes these three instances: its behavioral record gives 10.04 ENOB, 28.9 pJ per conversion (289 µW at 10 MS/s) and 0.76 LSB of noise (sampler 0.50, comparator 0.71), with the ladder of @fig-adc-ladder.
These single-instance predictions are what @sec-frida1-measurements compares the silicon against.

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
