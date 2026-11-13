# FRIDA-2: optimized converters across processes and resolutions {#sec-frida2}

::: todo

- The chapter's claim: with FRIDA-1's lessons, each block is re-optimized from the full system's view, and the whole converter becomes the object of an optimization search, generated for every process and resolution.
:::

## Optimizing each block for the system {#sec-frida2-blocks}

::: todo

- The sampler: sized against the converter's tracking-error budget (@eq-tracking), not alone; the bootstrap where the transmission gate costs bits.
- The comparator: optimized per resolution (@sec-comp-optimization), the dynamic bias where it lowers $E\sigma^2$.
- The array: sized from both limits (@eq-cmin-noise, @eq-cmin-matching) with the redundancy that keeps it calibratable (@eq-calibratable).
- The sequencer and logic: from the measured timing limits (@sec-meas-sequence).
:::

## Searching the whole converter {#sec-frida2-search}

::: todo

- The converter as an optimization problem: ENOB, energy and area together, with the blocks' own spaces as its space.
- How the search uses the blocks' records and behavioral models, and what it costs per evaluation.
:::

### Optimized converters per process and resolution {#sec-adc-optimized}

The design space crosses 20 comparators, 5 samplers and 121 arrays, 12,100 converters, in TSMC65; in the other five processes each array is paired with the process's StrongARM noise ladder and the widest bootstrapped switch.

::: {#fig-adc-optimized placeholder="The optimized converters: ENOB against area and energy per conversion, per process and resolution, from the converters grid."}
Optimized converters across processes and resolutions.
:::

::: todo

- The best converter per process at 10, 12 and 14 bits, and which block limits each.
- How the result compares with the survey (@fig-survey-area) and the specification (@tbl-specs).
:::

## Automatic layout {#sec-frida2-layout}

An instance's steps are one chain, each after the steps whose outputs it takes: the netlist, the pre-layout simulation, the layout, its DRC and LVS, the extraction, the post-layout simulation of the extracted netlist, and the record, from which the figures and the viewer's table are drawn.

::: {#fig-pipeline placeholder="The block pipeline: params, netlist, presim, layout, DRC, LVS, PEX, postsim, results, with the evidence each step adds and the bounds it can judge."}
The block pipeline.
:::

::: todo

- The open tools for layout and signoff (ALIGN placement, KLayout LVS and extraction) and what remains kit-specific.
- The generated design: 2760 µm² of layout, 540 µm² of devices.
:::

::: {#fig-gen-samp src="figures/layout_gen_samp.png"}
FRIDA-1's sampler (a transmission gate of 32 units) as the pipeline lays it out in TSMC65.
:::

::: {#fig-gen-samp-iso src="figures/layout3d_gen_samp.png"}
FRIDA-1's sampler (a transmission gate of 32 units) in an isometric view of its layers.
:::

::: {#fig-gen-comp src="figures/layout_gen_comp.png"}
FRIDA-1's comparator as the pipeline lays it out in TSMC65.
:::

::: {#fig-gen-comp-iso src="figures/layout3d_gen_comp.png"}
FRIDA-1's comparator in an isometric view of its layers.
:::

::: {#fig-gen-capdac src="figures/layout_gen_capdac.png"}
FRIDA-1's array, one side, with its drivers, as the pipeline lays it out in TSMC65.
:::

::: {#fig-gen-capdac-iso src="figures/layout3d_gen_capdac.png"}
FRIDA-1's array, one side, with its drivers, in an isometric view of its layers.
:::

::: {#fig-gen-adc src="figures/layout_gen_adc.png"}
The FRIDA converter's blocks side by side as the pipeline lays it out in TSMC65.
:::

::: {#fig-gen-adc-iso src="figures/layout3d_gen_adc.png"}
The FRIDA converter's blocks side by side in an isometric view of its layers.
:::

## Generated converters {#sec-frida2-generated}

::: {#fig-frida2-generated placeholder="The generated converters' layouts: one per process and resolution."}
Generated converters across processes and resolutions.
:::

::: {#fig-frida2-survey placeholder="The survey's plots (@fig-survey-rate, @fig-survey-energy, @fig-survey-area) with every generated converter's predicted point, by process and resolution, beside FRIDA-1's measured one."}
Where the generated converters fall against the state of the art.
:::

::: todo

- Which processes and resolutions reach the compact, efficient region of @fig-survey-area, and which block limits the rest.
- FRIDA-2's layout and its extracted predictions.
:::
