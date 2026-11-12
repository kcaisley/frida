# FRIDA-1: a first generation 65 nm prototype {#sec-frida1}

FRIDA-1 is a 1 × 1 mm test chip in 65 nm with 16 ADC channels, submitted in October 2025 and received in March 2026.
Its four ADC flavors cross one- and two-layer capacitor arrays with two weight radixes.

::: {#fig-frida1-core src="../images/frida_core.png"}
FRIDA-1's core: the ADC channels and their shared periphery.
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

::: {#fig-frida1-padring src="../images/frida_padring.png"}
FRIDA-1's pad ring.
:::

::: todo

- The chip-level power grids and a labeled pad ring.
:::

### Top-level layout and fabricated prototype

::: {#fig-frida1-top src="../images/frida_top.png"}
FRIDA-1's top-level layout.
:::

::: {#fig-frida1-die src="../images/frida_dieshot.png"}
A photograph of the fabricated FRIDA-1 die.
:::

::: {#fig-frida1-cob src="../images/frida_cob.jpg"}
FRIDA-1 mounted on its chip-on-board carrier.
:::
