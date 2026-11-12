# FRIDA-1: A first generation 65 nm prototype {#sec-frida-1-a-first-generation-65-nm-prototype}

## Implementation of the building blocks selected in the preceding design chapter {#sec-implementation-of-the-building-blocks-selected-i}

### Sampling switch and comparator

- The sampling switch and comparator layouts were manually laid out using a traditional analog-on-top flow. Both were customized from previous designs originating in Cordia.
- We used these designs because their architectures and device sizes were already close to the optima found in the preceding optimization steps.

### Capacitor drivers and array

- The drivers were sized from standard cells.
- The capacitor array was generated directly from its specification to GDS using a Python script and the KLayout Python API.

### Digital control logic

- The digital control logic was implemented entirely in Verilog. An OpenROAD flow converted it to layout, leaving gaps for the analog blocks.

## ADC block assembly and channel layout {#sec-adc-block-assembly-and-channel-layout}

### Assembling the ADC block

- Assemble the individual building blocks into the ADC channel, placing the manually laid-out analog blocks in the gaps left by the digital layout.
- Place the capacitor array above the drivers and logic, with a shielding plate between them.
- Explain the strategy for isolating the power grids and routing the supplies within the channel.

### Physical verification and completed channel layout

- Check layout connectivity, DRC, LVS, and extraction of the assembled channel.
- End with the ADC channel-level layout, showing the building-block placement, capacitor array, shielding, and power grids.


The prototype channel layout measures 60.5 × 63.5 µm, or approximately 3,800 µm², satisfying the intended compact form factor.

::: {#fig-frida1-channel placeholder="Rendered layout of one FRIDA-1 ADC channel (docs/images/report/frida1_adc_channel.png, to be reduced for the page)."}
Rendered layout of one FRIDA-1 ADC channel.
:::

Within this channel footprint, the capacitor structures occupy upper metal layers, allowing active circuitry to be placed beneath them. This overlap reduces the footprint that would otherwise be required by separate capacitor and circuit regions.

## Chip-level arrangement and hierarchical assembly of the prototype {#sec-chip-level-arrangement-and-hierarchical-assembly}

### Configuration and sequencing

- A synthesized SPI register controls the configuration bits of each ADC.
- The decision was made to apply the four ADC sequences externally, so four LVDS inputs were included.

### Analog inputs and comparator-output readout

- The ADC inputs were connected directly to a shared wire bus. The sampling switches of the ADCs choose which ADC is sampling from that bus.
- The ADC outputs were not resampled on-chip. Instead, the positive-polarity comparator outputs drive medium-performance LVDS transmitters directly for external measurement.
- The SAR logic is still on-chip, but the external DAQ system must acquire each comparator output serially in real time.

### Top-level power grids, pad ring, and assembly

- Explain the chip-level power grids and show a labeled pad ring of the chip.
- The top level was assembled hierarchically with OpenROAD, using the ADC block as a hardened macro with a LEF view.

### Top-level layout and fabricated prototype

- End with the top-level layout and an image of the fabricated prototype received in spring 2026.
