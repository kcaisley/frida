# Design of a compact SAR ADC {#sec-design}

::: todo
- The chapter's plan: the method, then each block's design space with its model, its optimization rule and its sweep, then FRIDA-1's instance in each grid, then the converter assembled from them.
:::

## Methodology {#sec-methodology}

::: todo
- Why a pipeline: the blocks' trade-offs cross each other, so each is characterized the same way in every process before the converter is assembled from them.
- The chapter's claim: each block's analytic model, flipped around, gives its optimization rule, and the sweep across processes and topologies checks it.
:::

### The block pipeline {#sec-pipeline}

A building block runs as one pipeline: its design parameters make a circuit, testbench runs of it are simulated, each run's raw output is read as a measurement, analyses turn measurements into results, and the results become the block's metrics, its figures and the record of one instance of its design space.
Each step is a file of the block's folder, and the names in each file are the same in every block.
The comparator is the first block on it, the sampling switch the second, the capacitive DAC the third and the ADC, assembled from them, the fourth.

An instance's steps are one chain, each after the steps whose outputs it takes: the netlist, the pre-layout simulation, the layout, its DRC and LVS, the extraction, the post-layout simulation of the extracted netlist, and the record, from which the figures and the viewer's table are drawn.
A run's bounds reject a design as early as its evidence allows: each step names what it adds, so a design whose gates alone exceed an area bound is out before it is simulated.

::: {#fig-pipeline placeholder="The block pipeline: params, netlist, presim, layout, DRC, LVS, PEX, postsim, results, with the evidence each step adds and the bounds it can judge."}
The block pipeline.
:::

::: todo
- The six processes (180, 150, 130 and 65 nm twice, 28 nm) and what is held the same across them: testbenches, supply corners at 90/100/110 %, the same area caps.
- The open tools for layout and signoff (ALIGN placement, KLayout LVS and extraction) and what remains kit-specific.
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

::: {#fig-top-level placeholder="The top-level comparison: each block's figure of merit against its area, coloured by process and marked by topology, from every block's records (the viewer's scatter, drawn for print)."}
Every block's designs across processes and topologies.
:::

::: todo
- How to read the top-level figure: a process's frontier, and which topology sets it.
- What a figure of merit per block means: R_on·C for the switch, E·σ² for the comparator, capacitance per bit for the DAC.
:::

## Sampling switch {#sec-sampling-switch}

A sampling switch is a circuit element which allows a continuously varying input voltage to be intermittently sampled and held constant.
During the track phase a switch, typically constructed from MOS channels, is allowed to conduct; the size of the capacitance alone determines the average expected sampling error from thermal noise, since increasing the series resistance of the switch generates thermal noise but also limits noise bandwidth.
This building block is found in nearly all ADC architectures.
There are three other non-idealities which one must worry about.
First, the RC time constant of the switch and sampling capacitor sets a bandwidth limit on the switch, causing distortion with increasing input signal speeds.
Second, since the on-resistance of the transistor is determined by its gate–source voltage, the input signal level affects it, causing the sampling error to also be signal-amplitude dependent.
And third, the switch itself injects charge onto the held node when it opens.
The proper design of sampling switches is heavily predicated on how fast the switch needs to operate.

::: {#fig-samp-topologies placeholder="Circuit diagrams (circuitikz): NMOS, transmission-gate and bootstrapped switches onto the sampling capacitor, with half-size dummies."}
The sampling switches studied: NMOS, transmission gate, and bootstrapped NMOS.
:::

### On-resistance {#sec-samp-ron}

In triode, each device of the switch conducts in proportion to its width over its length and to its gate overdrive.
A transmission gate's two devices conduct in parallel, the NMOS strongest at a low input and the PMOS at a high one [citation needed]:
$$
G(v) = k_n' \frac{W}{L} \max(V_G - v - V_{tn}, 0) + k_p' \frac{W}{L} \max(v - V_{tp}, 0), \qquad R_\mathrm{on}(v) = \frac{1}{G(v)}.
$$ {#eq-ron}
Its resistance is therefore highest near mid-supply, and falls as $1/W$.
A bootstrapped switch holds its gate a fixed voltage above the input, so its overdrive, and with it $R_\mathrm{on}$, no longer depends on the input.

The pipeline measures the on-resistance from the track phase's time constant into a 1 pF load, between the 1/e and 1/e² crossings of a step, so that the edge's delay is excluded: $R_\mathrm{on} = \tau / C_\mathrm{load}$, an upper bound since the switch's own capacitance is included.
In TSMC65 into 1 pF, FRIDA-1's transmission gate measures 130–550 Ω (highest at mid-supply), the NMOS switch from 140 Ω to open above 0.7 V, the bootstrapped one 140–230 Ω at 32 units and 30–45 Ω at 160.

::: {#fig-samp-ron-width plot="samp_ron_width"}
Transmission-gate on-resistance at mid-supply against width in six processes, with the triode rule's $R_\mathrm{on} \propto 1/W$ (@eq-ron).
:::

@fig-samp-ron-width checks @eq-ron across processes: in every one the measured resistance falls as $1/W$ over a factor of sixteen in width.

### Tracking error and distortion {#sec-samp-distortion}

While tracking, the held node follows the input through the switch's time constant.
To first order it lags the input by $\tau = R_\mathrm{on}(v)\,C$, so the sample taken is
$$
v_\mathrm{held} = v_\mathrm{in} + \left(t_j - R_\mathrm{on}(v_\mathrm{in})\,C\right)\frac{dv_\mathrm{in}}{dt} + v_n,
$$ {#eq-tracking}
with $t_j$ the aperture jitter and $v_n$ the sampled noise.
Because $R_\mathrm{on}$ depends on the input, the lag is signal-dependent: it is the switch's distortion, and the on-resistance, not the capacitance, sets its limit for a given capacitor.

Settling a full-scale step to half an LSB of an $N$-bit converter takes
$$
t_\mathrm{track} \geq R_\mathrm{on}\,C \ln\!\left(2^{N+1}\right)
$$ {#eq-settle}
[citation needed]: about $9\tau$ for 12 bits.
FRIDA-1's switch, with $R_\mathrm{on} \approx 1$ kΩ into $C = 1.64$ pF, has $\tau = 1.64$ ns, and needs more than $9\tau$, 15 ns, of tracking for 12 bits.

::: todo
- @eq-tracking flipped into the sizing rule: the largest $R_\mathrm{on}$ (and so the smallest switch) whose signal-dependent lag stays within the noise budget at the input's highest slew.
- The behavioral ADC's measured cost: in the 14-bit converters, the widest bootstrap still costs 2.2 bits in IHP130 (6.5 pF) and 3.3 bits in TPSC65 (5.7 pF), which therefore need a wider sampler.
- Sampling switch non-linearity sets a speed × resolution frontier.
:::

### Charge injection {#sec-samp-injection}

::: {#fig-samp-boost plot="samp_boost_pedestal"}
Bootstrapped switches in six processes: the largest pedestal against the on-resistance. A lower resistance is a wider switch, which injects more charge when it opens.
:::

Pedestals stay within ±0.7 mV for the transmission gates and reach −2 mV for the NMOS switches at 32 units, growing with the width (−10 mV at 160).
Half-size dummies take the transmission gate's largest pedestal from 0.75 to 0.03 mV, and nearly double its area.

::: todo
- The charge each device injects, roughly half its channel charge $W L C_\mathrm{ox} (V_{GS} - V_t)$, and why the transmission gate's complementary devices largely cancel.
- @fig-samp-boost read as the trade-off: on-resistance against pedestal, set by width.
:::

### Sampling noise {#sec-samp-noise}

The switch's thermal noise, filtered by the bandwidth it sets itself, leaves a noise on the held voltage set by the capacitance alone [citation needed]:
$$
\sigma_\mathrm{sample} = \sqrt{\frac{2kT}{C}}
$$ {#eq-ktc-samp}
differentially, for a capacitance $C$ per side.
For FRIDA-1, $C$ is the capacitive DAC's: kT/C is about 50 µV, 0.17 LSB.
The capacitance itself is the DAC's to choose, in @sec-cdac-noise.

### Choosing a switch per process {#sec-samp-choice}

The remaining architecture similarly prioritizes compactness: transmission-gate sampling switches, top-plate sampling, and a single-stage StrongARM comparator avoid a bootstrapped sampler, an internal input buffer, and a dedicated intermediate common-mode reference generator.
The front end must nevertheless provide suitable input common mode and settling.

::: todo
- The rule per resolution and process: transmission gate where its mid-supply $R_\mathrm{on}$ settles within the track time, bootstrap above.
- The area each choice costs, and the switch's share of the converter's area.
:::

### FRIDA-1 in the grid {#sec-frida1-samp}

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

## Dynamic comparator {#sec-comparator}

::: todo
- The comparator's job in a SAR loop: one decision per cycle on a small differential input, no static current.
- Why its noise matters most at high resolution: typically at high resolutions comparator noise is the trickiest to reduce on a fixed power budget.
:::

### Architectures {#sec-comp-architectures}

Six latches are studied, each on an NMOS or PMOS input pair, with a switched tail or a dynamic bias: the StrongARM, the double tail [@schinkel2007] and its self-timed form, the modified double tail [@elzakker2010] and its self-timed form, and the triple tail.
Every one of the 24 combinations is built.
With a dynamic bias [@bindra2018], a capacitor C_P loads the input pair's drains and a capacitor C_TAIL sits under its tail switch.

::: {#fig-comp-topologies placeholder="Circuit diagrams (circuitikz): StrongARM, double tail, modified double tail, and the dynamic bias's C_P and C_TAIL."}
The comparator latches studied.
:::

::: todo
- How a StrongARM decides: reset, integration on the drains' capacitance, regeneration in the cross-coupled pair.
- What the double tail separates (integration from regeneration), and what the dynamic bias stops (the input pair, once its drains have fallen by a fraction C_TAIL/C_P sets).
:::

### Noise from the integration capacitance {#sec-comp-noise}

During integration the input pair discharges the capacitance at its drains, $C_{PQ}$, and its thermal noise is integrated with the signal.
For a StrongARM the input-referred noise is [@razavi2015]
$$
\sigma^2 = r\left(\frac{4kT\gamma}{C_{PQ}} + \frac{r\,kT}{2\,C_{PQ}}\right), \qquad r = \frac{V_{GS} - V_{TH}}{V_{TH}},
$$ {#eq-strongarm-noise}
so the noise power falls as $1/C_{PQ}$: the integration capacitance sets the comparator's noise, as the sampling capacitance sets the sampler's.
The estimate runs a median 4.4 times high against the transient-noise simulation, so it ranks sizings loosely.

Every width times $k$ multiplies $C_{PQ}$, and with it the charge drawn per decision, by $k$.
So the noise falls as $1/\sqrt{k}$ and the energy rises as $k$, keeping the delay:
$$
E \propto k, \qquad \sigma \propto \frac{1}{\sqrt{k}} \quad\Rightarrow\quad E\,\sigma^2 = \text{const.}
$$ {#eq-comp-scaling}
The product $E\,\sigma^2$ is the comparator's figure of merit: scaling a design moves it along a line of constant $E\,\sigma^2$, and only a better topology moves the line.

::: {#fig-comp-energy-noise plot="comp_energy_noise"}
Energy per decision against input-referred noise for every comparator in six processes, marked by latch, with lines of constant $E\sigma^2$ (@eq-comp-scaling). Scaling moves a design along a line; the topology and the process set which line.
:::

The characterization confirms @eq-comp-scaling: every width times $k$ divides the noise by about $\sqrt{k}$ (toward a floor) and multiplies the energy by $k$, keeping the delay.
In TSMC65 the energy times noise power of the dynamic bias is 3.9 to 4.3 fJ·mV², of the base StrongARM 5.8 to 7.5.
The dynamic bias's input pair integrates in weak inversion and spends only the charge C_TAIL sets, which is why it sits on a lower line.

::: todo
- @fig-comp-energy-noise read per process: the best $E\sigma^2$ per process (3.3 fJ·mV² in TSMC65, 3.8 in TSMC28, 5.6 in LF150, 16–20 in the 130 and 180 nm processes) and why the older processes sit higher.
- The noise floor the families approach, $\sigma = \sqrt{a^2/k + f^2}$, and where it comes from.
:::

### Regeneration and metastability {#sec-comp-metastability}

Once integration ends, the cross-coupled pair amplifies the difference exponentially with a time constant $\tau$, set by its own capacitance over its transconductance.
An input $v$ is resolved to a logic level in [@razavi2015]
$$
t_\mathrm{d}(v) = t_0 + \tau \ln\frac{V_0}{|v|},
$$ {#eq-regeneration}
so the delay grows only logarithmically as the input falls, and a decision whose delay exceeds the window the SAR loop allows is late.
The pipeline measures $\tau$ from the delays at two small inputs, $\tau = (t_1 - t_2)/\ln(v_2/v_1)$, and extrapolates below the smallest input measured with @eq-regeneration.
In the behavioral converter a late decision is held: the SR latch keeps its previous value.

::: todo
- @eq-regeneration flipped: the window per decision sets the smallest input that resolves, and so the decision-error rate per conversion.
- The measured regeneration time constants per process (40–100 ps in TSMC28 to 250–500 ps at 130–180 nm at 0.2 mV).
:::

### Characterization {#sec-comp-characterization}

Each instance is characterized at the nominal common mode: the delay and energy at 0.5 mV and 100 mV, the delay over 0.1–100 mV (its metastability and regeneration time constant), the kickback, and the offset and noise from a transient-noise S-curve: 0 and 25 µV to 3 mV a side, 33 points, 80 decisions a point in passes through every input in a fresh random order, fitted by the Gaussian of most likelihood.
One noise reading scatters by about 4 % (one sigma) between seeds.
One clock is 1 ns of reset, then 4 ns of evaluation, and the converter allows about 2 ns.

The energy per decision is the supply's charge over a decision's cycle, read off a charge meter the simulator integrates, at the supply's voltage, averaged over the decisions that follow one at the same input.
Each clock reaches the comparator through an inverter chain on the comparator's supply, tapering by fanout 4 to a last stage at fanout 2, so that the energy per decision counts the clock (a long-tailed StrongARM's nearly doubles).

::: {#fig-comp-scurve placeholder="One comparator's transient-noise S-curve with its fitted Gaussian, and its noise and offset over the common mode (the pipeline's per-record plots)."}
A comparator's S-curve and its noise over the common mode.
:::

### Optimization per resolution {#sec-comp-optimization}

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

### Kickback and offset {#sec-comp-kickback}

::: todo
- Kickback: the inputs' largest excursion over a decision, driven as a DAC's top plates; how it depends on the CDAC's state.
- Offset: systematic only in simulation; how offset relates to sampling noise and CDAC error, and why a SAR tolerates it (a shift of every code).
:::

### FRIDA-1 in the grid {#sec-frida1-comp}

FRIDA-1's comparator is the grid's `frida1` instance, a StrongARM.
In TSMC65 it measures 246 µV of input-referred noise, a negligible systematic offset, 292 fJ per decision, 2.0 ns at 0.5 mV, a regeneration time constant of 194 ps, 6.9 mV of kickback, and 157 µm² of layout: an $E\sigma^2$ of about 18 fJ·mV², against 3.3 for the best TSMC65 designs (@fig-comp-energy-noise).
In TSMC28 the same sizing measures 530 µV and 80 fJ; in the 130–180 nm processes and TPSC65 its latch lengths do not decide within the clock.

::: todo
- Why FRIDA-1's comparator sits where it does on @fig-comp-energy-noise, and what the optimized 12-bit design (620 fJ, 100 µV, 277 µm²) changes.
- The pre-extraction estimate for the fabricated comparator (177 µV, 18 × 18 µm) against the grid's 246 µV.
:::

## Capacitive DAC {#sec-cdac}

The capacitor digital-to-analog converter (CDAC) holds the sampled input on its top plates and, by switching its bottom plates between the reference rails, subtracts each trial weight from it.
CDAC total capacitance often dominates area usage and is a large portion of the power budget.
Assuming no noise shaping or cancellation, kT/C sampling noise provides the theoretical limit on ADC error, and is determined by $C_\mathrm{tot}$.
However, a conventional CDAC implemented with capacitor scaling alone exhibits severe mismatch in its LSB capacitors as its $C_\mathrm{tot}$ is shrunk.
This chapter writes down the two limits, noise and matching, as minimum capacitances, and the redundancy that lets calibration recover what matching leaves.

### Top-plate sampling {#sec-cdac-top-plate}

In most SAR implementations the CDAC switches are connected to the capacitor bottom plates (named for their closer proximity to the transistors) and the comparator to the shared top plate.
Top-plate sampling allows a comparator decision to be taken without first switching the CDAC, so an $N$-bit ADC needs only an $(N-1)$-bit CDAC, halving its area [@liu2010]; it also simplifies the switch layout and logic for the bottom plates, as fewer voltages need to be distributed across the array.
Bottom-plate sampling can in some configurations improve linearity, as all charge summing happens on the same end of each capacitor.

### The noise limit: minimum capacitance {#sec-cdac-noise}

The differential sampling noise on a capacitance $C$ per side is (@eq-ktc-samp) $\sqrt{2kT/C}$, and the quantization noise of an ideal $N$-bit converter is $\mathrm{LSB}/\sqrt{12}$ [@walden1999], with $\mathrm{LSB} = 2V_\mathrm{ref}/2^N$.
Setting the two equal gives the least capacitance per side that adds no more noise power than quantization does:
$$
C_\mathrm{min} = \frac{24\,kT}{\mathrm{LSB}^2} = \frac{6\,kT\,4^N}{V_\mathrm{ref}^2},
$$ {#eq-cmin-noise}
26 fF at 10 bits and 1 V, 6.7 pF at 14 [citation needed].
It quadruples with every bit, and at it the converter loses half a bit:
$$
\mathrm{ENOB} = N - \frac{1}{2}\log_2\!\left(1 + \frac{2kT/C}{\mathrm{LSB}^2/12}\right).
$$ {#eq-enob-ktc}

::: {#fig-enob-ctot plot="enob_ctot"}
ENOB with quantization and kT/C noise only (@eq-enob-ktc) against the capacitance per side, for 10, 12 and 14 bits on a 1.2 V differential full scale. Each marker is that resolution's minimum, @eq-cmin-noise, where the converter loses half a bit.
:::

Capacitance also establishes the sampling-noise budget.
For an illustrative 800 fF capacitance per differential branch at 300 K, the ideal differential sampling noise is $\sigma_\mathrm{sample} = \sqrt{2kT/C} \approx 102$ µV RMS.
For an assumed 1.2 V differential full-scale span, ideal 12-bit quantization noise is $\sigma_\mathrm{quant} = (1.2\,\mathrm{V}/2^{12})/\sqrt{12} \approx 85$ µV RMS.
Sampling noise is therefore already comparable to quantization noise at this capacitance, making capacitor sizing consequential for effective resolution.
The prototype's nominal physical capacitance, including both members of the difference pairs, is approximately 1.88 pF per branch; the same ideal estimate gives approximately 66 µV RMS, before comparator noise and other nonidealities are included.

Every array of the design space is sized from @eq-cmin-noise at one or two times the minimum, and its layout area follows it (@fig-cdac-area).

::: {#fig-cdac-area plot="capdac_area_bits"}
CDAC layout area per side against resolution for the 121 arrays of the design space, at one and two times @eq-cmin-noise, in difference and in unit capacitors, with the rule's $4^N$.
:::

### The matching limit {#sec-cdac-matching}

A capacitor's random mismatch shrinks with its size.
For a metal fringe capacitor the relative standard deviation scales with the square root of its capacitance [@pelgrom1989; @tripathi2014]:
$$
\frac{\sigma_C}{C} = \frac{A}{\sqrt{C / 1\,\mathrm{fF}}},
$$ {#eq-pelgrom}
with $A$ the matching coefficient in %·√fF.

In a binary array of unit capacitors $C_u$ the largest error falls at the mid-code transition, where the MSB capacitor, $2^{N-1}$ units, is compared against all the others, $2^{N-1} - 1$ units.
Their difference has a standard deviation, in LSB,
$$
\sigma_\mathrm{mid} = \frac{A}{\sqrt{C_u / 1\,\mathrm{fF}}}\sqrt{2^{N-1} + \left(2^{N-1} - 1\right)} = \frac{A}{\sqrt{C_u / 1\,\mathrm{fF}}}\sqrt{2^N - 1}.
$$ {#eq-midcode}
Flipped around, a target $\sigma_\mathrm{mid}$ (a quarter LSB keeps four sigma within one) sets the least unit capacitor, and with it the least total:
$$
C_u \geq \left(2^N - 1\right)\left(\frac{A}{\sigma_\mathrm{mid}}\right)^2 \mathrm{fF}, \qquad C_\mathrm{tot} \geq 2^N C_u.
$$ {#eq-cmin-matching}
Matching asks for $4^N$ as noise does, but with the coefficient $A^2$ in place of $kT/V_\mathrm{ref}^2$; whichever is larger in a given process sets the array.

::: {#fig-cdac-limits placeholder="The two minimum capacitances, @eq-cmin-noise and @eq-cmin-matching, against resolution, for published matching coefficients (0.22 to 0.85 %·√fF), with each design's array marked."}
The noise and the matching limits on the total capacitance.
:::

::: todo
- Which limit binds at 10, 12 and 14 bits for the matching coefficients published for MOM capacitors (up to 0.22 %·√fF [@harpe2019], 0.85 %·√fF [@tripathi2014]).
- The pipeline's linearized prediction (every code's DNL and INL sigma from every plate's error) against its SPICE Monte Carlo, and where @eq-midcode is the worst code.
:::

### Breaking the scaling: difference capacitors {#sec-cdac-difference}

To break the direct relation between the total capacitance and the mismatch of the smallest capacitors, three strategies exist to construct the smaller bits: scaling down the switching voltage, scaling with a bridge capacitor, and scaling with the difference between two capacitors [@harpe2019].

The CDAC uses fringe metal–oxide–metal capacitors with capacitance determined by finger length, drawing on the unit-length capacitor approach [@harpe2019].
Small effective weights are formed from the difference between two capacitors switched in opposite directions: $C_\mathrm{eff} = C_\mathrm{main} - C_\mathrm{diff}$.
The prototype's smallest effective weight is 0.8 fF, obtained from nominal 26.4 fF and 25.6 fF elements.
This avoids relying on an individually fabricated capacitor of the same small value, while retaining a compact array without a bridge-capacitor divider or additional scaled reference voltages.
The benefit comes with sensitivity to matching between the paired elements, which must be assessed through extraction, modeling, and calibration.

::: {#fig-capacitor-views src="../images/report/capacitor_views"}
Plan and three-dimensional views of a shortened main/difference MOM capacitor cell, with the shared surrounding electrode in blue and independent inner electrodes in orange.
:::

The capacitor illustration presents side-by-side plan and perspective views of the same shortened geometry.
A blue surrounding common electrode couples to independent orange main and difference electrodes.
Opposite switching produces the effective weight of element $N$, $C_{\mathrm{eff},N} = C_{N,\mathrm{main}} - C_{N,\mathrm{diff}}$.
The perspective shows three metal layers connected by vias, while the plan shows their shared footprint and via locations.

::: todo
- The mismatch of a difference weight: both elements' errors add, so $\sigma(C_\mathrm{eff}) = A\sqrt{(C_\mathrm{main} + C_\mathrm{diff})\cdot 1\,\mathrm{fF}}$, large against the weight itself; why redundancy and calibration are therefore part of the design, not an afterthought.
- The design space's two weight builds compared: at 1 % mismatch unit capacitors leave less to calibrate than difference strips (12 bits at twice the minimum: 0.43 against 0.83 LSB).
- MOM structures: unit-length strips, three metal layers, the 2:1 outline per branch.
:::

### Redundancy and calibration {#sec-redundancy}

Errors in ADC digitization fall into static errors (accuracy), limited by manufacturing variability that produces repeatable errors characterized by INL and DNL, mainly capacitor mismatch and comparator offset; and dynamic errors (precision), limited by random transient variations: sampling noise, comparator noise, reference noise, and insufficient settling time.
Techniques that correct static errors are termed calibration, and only a certain magnitude of mismatch can be calibrated, determined by the radix of the system: a binary-weighted (radix-2) ADC can only calibrate up to 1 LSB worth of capacitor variation, whereas a sub-radix-2 design can tolerate more.

A redundant array spreads the binary DAC's weight over more decisions than bits.
Its weights $w_k$ sum to $2^{N-1} - 1$ units and each is no larger than all the weights after it plus one [@ogawa2010]:
$$
\sum_k w_k = 2^{N-1} - 1, \qquad w_k \leq \sum_{j > k} w_j + 1.
$$ {#eq-redundancy}
The extra decisions never add capacitance.
A wrong decision at stage $k$ is corrected by the later ones as long as its error lies within the stage's redundancy margin [@ogawa2010]
$$
q_k = \sum_{j > k} w_j - w_k + w_{M-1},
$$ {#eq-margin}
which is zero at every stage of a binary array: binary weights tolerate no error, and their static mismatch can only be calibrated where it happens to fall within one LSB.

What calibration cannot recover is a missing level: a code no decision path reaches, the widest path over a code minus one [@chang2013].
Calibration is possible where every stage's margin covers its weight's error.
With $\sigma_{w_k} = \frac{A}{\sqrt{C_u/1\,\mathrm{fF}}}\sqrt{w_k}$ in units, the least redundancy that keeps an array calibratable at $z$ standard deviations is the one that gives
$$
q_k \geq z\,\sigma_{w_k} \quad \text{at every stage } k.
$$ {#eq-calibratable}

::: {#fig-cdac-gap plot="capdac_gap_redundancy"}
The 95th percentile of the gap no calibration recovers, at a matching coefficient of 1 %·√fF, against the number of redundant decisions, for every array of the design space, marked by scheme. Binary arrays leave 1.5–3 LSB; enough redundancy, placed at the most significant stages, brings it under one LSB.
:::

Three schemes redistribute the binary array's units: MSB split splits the most significant binary weights into halves, which gives the free first comparison and the decisions after it their tolerance; LSB split splits the least significant weights of at least 2, a tolerance only at the LSB end; MSB redistribution is FRIDA's paired overlay, a run of paired powers of two taken from the MSB and added from the third stage on, its tolerance spread over the whole chain.

Redundant capacitor weights spread FRIDA-1's conversion over 17 comparator decisions, from which a normalized 12-bit result is reconstructed.
At 10 MS/s a conversion lasts 100 ns, permitting approximately 5 ns per decision after sampling and initialization overhead.
Overlapping decision ranges allow later comparisons to correct some earlier errors caused by noise or incomplete settling, with a correction margin that depends on the stage and error magnitude.

::: todo
- @eq-calibratable as the sizing rule: for a given $A$ and $C_u$, the fewest extra decisions that keep $q_k/\sigma_{w_k} \geq 3$; the pipeline computes each stage's margin over sigma, but no solver picks the scheme yet.
- Redundancy and time: it shortens a conversion where DAC settling dominates, not where the latch delay does, since it cannot undo a metastable decision [@chang2013].
- Redundancy in the last 1–2 bits relaxes comparator noise beyond quantization noise (@sec-comp-optimization).
- The three calibrations: CDAC S-curves, least squares on a known ramp, and Chang's algorithm [@chang2013].
:::

### Switching scheme {#sec-cdac-switching}

FRIDA uses a modified monotonic, single-side switching procedure, building on the monotonic switching scheme [@liu2010].
Programmable initial capacitor states provide a means to adjust the comparator common-mode trajectory.
Although other switching schemes can reduce theoretical switching energy further, the small array capacitance makes simple rail-driven CMOS switching attractive.

Each decision moves the top plate by the bottom-plate steps it switches, weighted by their capacitance over the total, and draws from the reference the charge those plates take:
$$
\Delta V_\mathrm{top} = \frac{\sum_i C_i\,\Delta V_{\mathrm{bot},i}}{C_\mathrm{tot}}, \qquad Q_\mathrm{ref} = \sum_{i \in \mathrm{ref}} C_i \left(\Delta V_{\mathrm{bot},i} - \Delta V_\mathrm{top}\right).
$$ {#eq-switching}

::: todo
- Switching energy per conversion for monotonic against Vcm-based switching, and the common-mode drift it costs the comparator [@chang2013; @liu2010].
- The initial state (16'h5555 in FRIDA-1) and what it does to the common-mode trajectory, power and noise; measured evidence is still missing.
:::

### Drivers and settling {#sec-cdac-settling}

A stage's bottom plate settles first order through its driver.
To settle a stage of weight $w$ to half an LSB of the whole array $W$ takes
$$
n = \ln\!\left(2^{N+1}\frac{w}{W}\right)
$$ {#eq-driver}
time constants, into the plate in series with the rest of the array, $C_\mathrm{plate}(C_\mathrm{top} - C_\mathrm{plate})/C_\mathrm{top}$; each driver is sized for that within its share of the decision time, tapering by fanout 4 from a minimum flip-flop [@chang2013].

### Top-plate parasitics and full scale {#sec-cdac-parasitic}

The top plate's parasitic capacitance divides every step: the full scale is the reference times the switched capacitance over the total load, $V_\mathrm{FS} = V_\mathrm{ref}(\sum C_\mathrm{main} - \sum C_\mathrm{diff})/C_\mathrm{load}$.
The arrays reach 55–65 % of the reference at 10 bits and 73–76 % at 12 and 14; FRIDA-1's extracted array 0.73.

: Held sampling noise against the extracted load per side for FRIDA-1's four array flavors, 100 conversions each at 50 mV input. {#tbl-held-noise}

| Design | Load per side (fF) | Held differential SD (µV) |
|:--|--:|--:|
| FRIDA-1 1L R17 | 527.7 | 116.9 |
| FRIDA-1 1L R20 | 527.7 | 127.2 |
| FRIDA-1 2L R17 (disconnected) | 499.7 | 109.9 |
| FRIDA-1 2L R20 (disconnected) | 499.6 | 102.7 |

The extracted `main − diff` relative weights matched the intended weights well after normalization; the absolute effective capacitance scale was about 16.1 % of the intended behavioral value.
The nominal two-layer flavors have disconnected upper plates, so their extracted capacitance matched the one-layer one rather than adding a parallel layer.

### FRIDA-1 in the grid {#sec-frida1-cdac}

FRIDA-1's array is the grid's `frida1` instance: 12 bits, MSB redistribution with 5 redundant decisions (17 in all), at twice the noise minimum (@eq-cmin-noise), in difference capacitors.
Extracted in TSMC65, its gain is 0.73 (a 0.68 V full scale), its largest stage settles in 0.28 ns with a step error of 0.017 LSB, and it takes 645 µm² of layout per side.
At a matching coefficient of 1 %·√fF its 95th-percentile uncalibratable gap is 0.27 LSB and its INL with the design weights 2.4 LSB (@fig-cdac-gap).

::: todo
- @eq-calibratable applied to FRIDA-1's weights: each stage's margin over its weight's sigma.
- The measured weights of @sec-frida1-measurements against these.
:::

## Clocking and sequencing {#sec-clocking}

::: todo
- The SAR loop's timing: sample, then per decision a comparator evaluation, a logic update and a DAC settling, within one conversion period.
- Synchronous against asynchronous control: what each needs (an external fast clock, or a self-timed loop), and what each costs in an array of thousands of converters.
- Could asynchronous operation be beneficial, and also not cause issues in an array?
:::

### Synchronous control {#sec-clocking-sync}

Synchronous control supports implementation with conventional digital synthesis and place-and-route tools.
A one-hot stage selector advances through 16 capacitor-control stages, followed by a terminal comparison that contributes to the decoded result without switching another capacitor.
Initialization loads the programmed starting state into all driver registers and seeds the selector with stage 0 active; subsequent logic-clock edges shift this one-hot enable through the chain.

::: {#fig-adc-timing-clocking src="../images/report/adc_timing"}
Initialization, sampling, comparator, and logic timing waveforms.
:::

The sequencer is a set of named recipes over four lines, INIT, SAMP, COMP and LOGIC, each a pattern of symbols at the sequencer's symbol rate: four symbols of INIT, twenty of SAMP, then one eight-symbol word per decision, COMP high for the first four symbols and LOGIC for the last four.

::: {#fig-sequences placeholder="The sequencer's recipes as timing diagrams (docs/images/sequences, drawn from the recipes): COMP duty and LOGIC phase."}
The sequences studied.
:::

### Timing budget {#sec-clocking-budget}

Each decision must fit the comparator's delay at its input (@eq-regeneration), the logic's clock-to-output and the DAC's settling (@eq-driver) within its share of the conversion.

::: todo
- The timing-closure margins the behavioral model checks: 200 ps logic and CDAC setup, 0.3 V latch resolution, 1 mV CDAC tolerance.
- The ENOB over sequence and symbol rate (the sequence map), and which recipe the timing allows at 10 MS/s.
:::

### Extracted sequences {#sec-clocking-pex}

::: {#fig-pex-sequences placeholder="The post-layout sequence study: COMP duty 50 to 87.5 % and LOGIC phase 180 to 315° across seven array flavors, with code spread and timing-error counts (docs/thesis/adc_pex_sequence_reference.tex)."}
Extracted converters over the comparator duty cycle and logic phase.
:::

### Measured sequences

The sequences FRIDA-1 measures are in @sec-meas-sequence.

## Assembling the converter {#sec-adc}

::: todo
- The assembly problem: pick a sampler, a comparator and an array per process and resolution so that the noise, the area and the power budgets of @sec-specs are all met.
- The trade-off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a different relationship between these: large CDACs have worse speed, but large comparators and sampling switches can typically improve it.
:::

### The behavioral converter {#sec-adc-behavioral}

The behavioral converter composes the blocks' models, each from its own characterization: the sampler's on-resistance over the input and its kT/C (@sec-sampling-switch), the comparator's noise, offset and delay over the input (@sec-comparator), and the array's plates as drawn, with each stage's step, delay and settling as the DAC's characterization measured them (@sec-cdac).
It runs the SAR loop on them.
The comparator's measured delay over the input decides when a decision is late, and its SR latch then holds the last one; each stage's plates move after its driver's delay and settle with its own time constant.

::: {#fig-adc-architecture src="../images/report/adc_architecture"}
Circuitikz schematic of the differential ADC, redundant capacitor weights, synchronous SAR registers, and main/difference capacitor pair.
:::

The circuit diagram shows the differential architecture.
Each capacitor cell contains a main capacitor and a difference capacitor, with the effective weight shown above it.
Complementary rail drivers connect directly to the enabled decision registers.
The first three capacitor stages and the final stage are shown; three dots denote the omitted stages 3–14.
Complementary comparator outputs feed the decision registers, and a dedicated clock input controls evaluation.
Weighted decoding is external to the prototype ADC macro.

### The noise budget {#sec-adc-noise}

The quantization noise and the three thermal noises, track-and-hold, DAC and comparator, add as powers, since there is no amplification in the circuit:
$$
\sigma_\mathrm{tot}^2 = \frac{\mathrm{LSB}^2}{12} + \frac{2kT}{C} + \sigma_\mathrm{comp}^2 + \sigma_\mathrm{ref}^2.
$$ {#eq-noise-budget}
Each source that adds one quantization noise power costs the converter
$$
\mathrm{ENOB} = N - \frac{1}{2}\log_2\!\left(1 + \sum_i \frac{\sigma_i^2}{\mathrm{LSB}^2/12}\right),
$$ {#eq-enob-budget}
half a bit for one such source, and about 0.8 bit for three equal ones at 0.71 of the quantization noise each (@eq-cost-optimum).
The reference may add at most half the quantization noise power from its output resistance and half from its noise.

The behavioral model measures the budget as a ladder: the 10 MS/s sine from quantization alone, then adding the sampler's tracking error, its kT/C noise and jitter, the DAC's settling, the comparator's delay and its noise in turn.

::: {#fig-adc-ladder placeholder="The ENOB ladder of the generated FRIDA design (TSMC65): quantization 11.99 bits, then the sampler's tracking error −1.65, kT/C −0.06, settling 0, comparator timing −0.02, comparator noise −0.22, ending at 10.04."}
The ENOB budget, one impairment at a time.
:::

For the generated FRIDA design the ladder ends at 10.04 bits: the sampler's tracking error costs the most (1.65 bits), the comparator's noise 0.22, kT/C 0.06.
Its noise is 0.76 LSB, the sampler 0.50 and the comparator 0.71.

::: todo
- Why the tracking error dominates here: the transmission gate's mid-supply $R_\mathrm{on}$ into the 12-bit array (@eq-tracking), and the bootstrap's recovery.
- @eq-enob-budget flipped: given the area and power caps, how much of the budget each block gets.
:::

### Energy {#sec-adc-energy}

The energy per conversion sums the three supplies: the comparator's decisions on the analog rail, the logic's registers and clock on the digital rail, and the DAC's charge from the reference (@eq-switching) with its drivers' transitions:
$$
E_\mathrm{conv} = (M + 1)E_\mathrm{dec} + E_\mathrm{logic} + V_\mathrm{ref}\,Q_\mathrm{DAC} + E_\mathrm{drivers},
$$ {#eq-energy}
for $M$ capacitor stages.
The generated FRIDA design spends about 28.9 pJ per conversion, 289 µW at 10 MS/s; the SAR logic dominates.

::: todo
- The logic's share and what dynamic or TSPC logic would save.
- Energy against rate: static against dynamic consumption.
:::

### Area {#sec-adc-area}

::: todo
- An area budget for the full converter: the array (@fig-cdac-area), the comparator's cap per resolution (15, 20, 63 µm a side), the sampler, the drivers and the logic; no full-converter layout exists yet beyond the blocks side by side.
- The generated design: 2760 µm² of layout, 540 µm² of devices.
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

### FRIDA-1 in the grid {#sec-frida1-adc}

The generated FRIDA design composes these three instances: its behavioral record gives 10.04 ENOB, 28.9 pJ per conversion (289 µW at 10 MS/s) and 0.76 LSB of noise (sampler 0.50, comparator 0.71), with the ladder of @fig-adc-ladder.
These single-instance predictions are what @sec-frida1-measurements compares the silicon against.
