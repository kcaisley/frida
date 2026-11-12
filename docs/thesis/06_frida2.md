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
