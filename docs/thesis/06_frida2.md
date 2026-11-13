# FRIDA-2: optimized converters across processes and resolutions {#sec-frida2}

::: todo

- The chapter's claim: with FRIDA-1's lessons, each block is re-optimized from the full system's view, and the whole converter becomes the object of an optimization search, generated for every process and resolution.
:::

## The block pipeline and its sweeps {#sec-methodology}

::: todo

- Why a pipeline: the blocks' trade-offs cross each other, so each is characterized the same way in every process before the converter is assembled from them.
- The chapter's claim: each block's analytic model, flipped around, gives its optimization rule, and the sweep across processes and topologies checks it.
:::

### The block pipeline {#sec-pipeline}

A building block runs as one pipeline: its design parameters make a circuit, testbench runs of it are simulated, each run's raw output is read as a measurement, analyses turn measurements into results, and the results become the block's metrics, its figures and the record of one instance of its design space.
Each step is a file of the block's folder, and the names in each file are the same in every block.
The comparator is the first block on it, the sampling switch the second, the capacitive DAC the third and the ADC, assembled from them, the fourth.

An instance's steps are one chain, each after the steps whose outputs it takes: the netlist, its simulation, and the record, from which the figures and the viewer's table are drawn; the layout steps after it are the subject of @sec-frida2-layout.
A run's bounds reject a design as early as its evidence allows: each step names what it adds, so a design whose gates alone exceed an area bound is out before it is simulated.

::: todo

- The six processes (180, 150, 130 and 65 nm twice, 28 nm) and what is held the same across them: testbenches, supply corners at 90/100/110 %, the same area caps.
- The behavioral model each block derives from its own characterization, and how the converter is composed from them (@sec-adc).
:::

### Optimizing a block {#sec-optimizing}

An optimization run is to a problem's space what a grid's steps are to its designs: its problem in one process is a study, its budget's trials asked asynchronously across a process pool, so a slow design holds no other.
The objective is the problem's cost, the product of its cost metrics, each to its weight, with a saturating factor where a cost has a scale; each bound's violation is a named constraint, and a design that misses a bound completes infeasible.

For the comparator of an $N$-bit converter the cost is
$$
J = E \cdot A^{\,a} \cdot \left(1 + \frac{\sigma^2}{\sigma_q^2}\right)^{g}, \qquad \sigma_q = \frac{2\,V_\mathrm{FS}}{2^N \sqrt{12}},
$$ {#eq-cost}
the energy per decision $E$ times the area $A$ times a saturating noise factor: the last factor is the converter's noise power over its quantization noise alone, near 1 where the converter no longer gains from a quieter comparator.
A design that only scales settles at
$$
\frac{\sigma}{\sigma_q} = \frac{1}{\sqrt{g/(1+a) - 1}},
$$ {#eq-cost-optimum}
0.71 for the weights used, $a = 1$ and $g = 6$.

::: todo

- Why a product of factors rather than a weighted sum: scale-free, so the same weights hold in every process.
- The search (Optuna's TPE) and its budget; the warm start from the grid.
:::

### Comparing across processes and topologies {#sec-top-level}

::: {#fig-top-level plot="top_level"}
Every block's designs across processes and topologies.
:::

::: todo

- How to read the top-level figure: a process's frontier, and which topology sets it.
- What a figure of merit per block means: R_on·C for the switch, E·σ² for the comparator, capacitance per bit for the DAC.
:::

## Optimizing each block for the system {#sec-frida2-blocks}

::: todo

- The sampler: sized against the converter's tracking-error budget (@eq-tracking), not alone; the bootstrap where the transmission gate costs bits.
- The comparator: optimized per resolution (@sec-comp-optimization), the dynamic bias where it lowers $E\sigma^2$.
- The array: sized from both limits (@eq-cmin-noise, @eq-cmin-matching) with the redundancy that keeps it calibratable (@eq-calibratable).
- The sequencer and logic: from the measured timing limits (@sec-meas-sequence).
:::

### Sampling switch {#sec-frida2-samp}

::: {#fig-samp-ron-width plot="samp_ron_width"}
Transmission-gate on-resistance at mid-supply against width in six processes, with the triode rule's $R_\mathrm{on} \propto 1/W$ (@eq-ron).
:::

@fig-samp-ron-width checks @eq-ron across processes: in every one the measured resistance falls as $1/W$ over a factor of sixteen in width.

::: {#fig-samp-boost plot="samp_boost_pedestal"}
Bootstrapped switches in six processes: the largest pedestal against the on-resistance. A lower resistance is a wider switch, which injects more charge when it opens.
:::

::: todo

- @fig-samp-boost read as the trade-off: on-resistance against pedestal, set by width.
:::

::: todo

- The behavioral ADC's measured cost: in the 14-bit converters, the widest bootstrap still costs 2.2 bits in IHP130 (6.5 pF) and 3.3 bits in TPSC65 (5.7 pF), which therefore need a wider sampler.
:::

### Choosing a switch per process {#sec-samp-choice}

The remaining architecture similarly prioritizes compactness: transmission-gate sampling switches, top-plate sampling, and a single-stage StrongARM comparator avoid a bootstrapped sampler, an internal input buffer, and a dedicated intermediate common-mode reference generator.
The front end must nevertheless provide suitable input common mode and settling.

::: todo

- The rule per resolution and process: transmission gate where its mid-supply $R_\mathrm{on}$ settles within the track time, bootstrap above.
- The area each choice costs, and the switch's share of the converter's area.
:::

### Comparator {#sec-frida2-comp}

::: {#fig-comp-energy-noise plot="comp_energy_noise"}
Energy per decision against input-referred noise for every comparator in six processes, marked by latch, with lines of constant $E\sigma^2$ (@eq-comp-scaling). Scaling moves a design along a line; the topology and the process set which line.
:::

The characterization confirms @eq-comp-scaling: every width times $k$ divides the noise by about $\sqrt{k}$ (toward a floor) and multiplies the energy by $k$, keeping the delay.
In TSMC65 the energy times noise power of the dynamic bias is 3.9 to 4.3 fJ·mV², of the base StrongARM 5.8 to 7.5.
The dynamic bias's input pair integrates in weak inversion and spends only the charge C_TAIL sets, which is why it sits on a lower line.

::: todo

- @fig-comp-energy-noise read per process: the best $E\sigma^2$ per process (3.3 fJ·mV² in TSMC65, 3.8 in TSMC28, 5.6 in LF150, 16–20 in the 130 and 180 nm processes) and why the older processes sit higher.
:::

The estimate runs a median 4.4 times high against the transient-noise simulation, so it ranks sizings loosely.

#### How a comparator is characterized {#sec-comp-characterization}

Each instance is characterized at the nominal common mode: the delay and energy at 0.5 mV and 100 mV, the delay over 0.1–100 mV (its metastability and regeneration time constant), the kickback, and the offset and noise from a transient-noise S-curve: 0 and 25 µV to 3 mV a side, 33 points, 80 decisions a point in passes through every input in a fresh random order, fitted by the Gaussian of most likelihood.
One noise reading scatters by about 4 % (one sigma) between seeds.
One clock is 1 ns of reset, then 4 ns of evaluation, and the converter allows about 2 ns.

The energy per decision is the supply's charge over a decision's cycle, read off a charge meter the simulator integrates, at the supply's voltage, averaged over the decisions that follow one at the same input.
Each clock reaches the comparator through an inverter chain on the comparator's supply, tapering by fanout 4 to a last stage at fanout 2, so that the energy per decision counts the clock (a long-tailed StrongARM's nearly doubles).

::: todo

- The measured regeneration time constants per process (40–100 ps in TSMC28 to 250–500 ps at 130–180 nm at 0.2 mV).
:::

### Comparator optimization per resolution {#sec-comp-optimization}

The comparator of an $N$-bit converter is optimized for the cost of @eq-cost: least energy times area times a saturating noise factor, the noise within the converter's quantization noise, the layout within 15, 20 or 63 µm a side at 10, 12 or 14 bits, the 0.5 mV delay within 2 ns.
A design that only scales settles at $\sigma/\sigma_q = 0.71$ (@eq-cost-optimum).

In TSMC65 the best 10-bit comparator is a StrongARM at 214 fJ, 157 µm², 185 µV and 0.58 ns; the best 12-bit one a StrongARM at 620 fJ, 277 µm², 100 µV and 1.28 ns.
No 14-bit design met its bounds within the area cap: the quietest found was 39.3 µV, a dynamic bias at 3374 µm².

::: {#fig-comp-optimization placeholder="The 12-bit optimization in TSMC65: cost against trial, and the feasible designs' energy against noise, with the optimum marked."}
The comparator optimization for a 12-bit converter.
:::

::: todo

- Why 14 bits is infeasible within 63 µm a side: @eq-comp-scaling at the 14-bit noise bound.
- Redundancy in the last 1–2 bits can relax comparator noise beyond the quantization noise, with more power for a few extra steps only (@sec-redundancy).
:::

### Capacitive DAC {#sec-frida2-cdac}

Every array of the design space is sized from @eq-cmin-noise at one or two times the minimum, and its layout area follows it (@fig-cdac-area).

::: {#fig-cdac-area plot="capdac_area_bits"}
CDAC layout area per side against resolution for the 121 arrays of the design space, at one and two times @eq-cmin-noise, in difference and in unit capacitors, with the rule's $4^N$.
:::

::: {#fig-cdac-gap plot="capdac_gap_redundancy"}
The 95th percentile of the gap no calibration recovers, at a matching coefficient of 1 %·√fF, against the number of redundant decisions, for every array of the design space, marked by scheme. Binary arrays leave 1.5–3 LSB; enough redundancy, placed at the most significant stages, brings it under one LSB.
:::

The arrays of the design space reach 55–65 % of the reference in full scale at 10 bits and 73–76 % at 12 and 14.

::: todo

- The design space's two weight builds compared: at 1 % mismatch unit capacitors leave less to calibrate than difference strips (12 bits at twice the minimum: 0.43 against 0.83 LSB).
:::

::: todo

- The pipeline's linearized prediction (every code's DNL and INL sigma from every plate's error) against its SPICE Monte Carlo, and where @eq-midcode is the worst code.
- The pipeline computes each stage's margin over sigma (@eq-calibratable), but no solver picks the scheme yet.
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
