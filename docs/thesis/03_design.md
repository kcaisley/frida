# Design of a compact SAR ADC {#sec-design}

::: todo

- The chapter's plan: each block's circuit, its analytic and statistical model, and the sizing rule the model gives when flipped around; then how the blocks' noise, energy and area add up in a converter: the design as it was done before the sweeps of @sec-frida2.
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
A switch with $R_\mathrm{on} \approx 1$ kΩ into $C = 1.64$ pF has $\tau = 1.64$ ns, and needs more than $9\tau$, 15 ns, of tracking for 12 bits.

::: todo

- @eq-tracking flipped into the sizing rule: the largest $R_\mathrm{on}$ (and so the smallest switch) whose signal-dependent lag stays within the noise budget at the input's highest slew.
- Sampling switch non-linearity sets a speed × resolution frontier.
:::

### Charge injection {#sec-samp-injection}

::: todo

- The charge each device injects, roughly half its channel charge $W L C_\mathrm{ox} (V_{GS} - V_t)$, and why the transmission gate's complementary devices largely cancel.
:::

### Sampling noise {#sec-samp-noise}

The switch's thermal noise, filtered by the bandwidth it sets itself, leaves a noise on the held voltage set by the capacitance alone [citation needed]:
$$
\sigma_\mathrm{sample} = \sqrt{\frac{2kT}{C}}
$$ {#eq-ktc-samp}
differentially, for a capacitance $C$ per side.
Here $C$ is the capacitive DAC's: for a 12-bit array kT/C is about 50 µV, 0.17 LSB.
The capacitance itself is the DAC's to choose, in @sec-cdac-noise.

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

Every width times $k$ multiplies $C_{PQ}$, and with it the charge drawn per decision, by $k$.
So the noise falls as $1/\sqrt{k}$ and the energy rises as $k$, keeping the delay:
$$
E \propto k, \qquad \sigma \propto \frac{1}{\sqrt{k}} \quad\Rightarrow\quad E\,\sigma^2 = \text{const.}
$$ {#eq-comp-scaling}
The product $E\,\sigma^2$ is the comparator's figure of merit: scaling a design moves it along a line of constant $E\,\sigma^2$, and only a better topology moves the line.

::: todo

- The noise floor the families approach, $\sigma = \sqrt{a^2/k + f^2}$, and where it comes from.
:::

### Regeneration and metastability {#sec-comp-metastability}

Once integration ends, the cross-coupled pair amplifies the difference exponentially with a time constant $\tau$, set by its own capacitance over its transconductance.
An input $v$ is resolved to a logic level in [@razavi2015]
$$
t_\mathrm{d}(v) = t_0 + \tau \ln\frac{V_0}{|v|},
$$ {#eq-regeneration}
so the delay grows only logarithmically as the input falls, and a decision whose delay exceeds the window the SAR loop allows is late.

::: todo

- @eq-regeneration flipped: the window per decision sets the smallest input that resolves, and so the decision-error rate per conversion.
:::

### Kickback and offset {#sec-comp-kickback}

::: todo

- Kickback: the inputs' largest excursion over a decision, driven as a DAC's top plates; how it depends on the CDAC's state.
- Offset: systematic only in simulation; how offset relates to sampling noise and CDAC error, and why a SAR tolerates it (a shift of every code).
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

::: {#fig-cdac-limits plot="cdac_limits"}
The noise and the matching limits on the total capacitance.
:::

::: todo

- Which limit binds at 10, 12 and 14 bits for the matching coefficients published for MOM capacitors (up to 0.22 %·√fF [@harpe2019], 0.85 %·√fF [@tripathi2014]).
:::

### Breaking the scaling: difference capacitors {#sec-cdac-difference}

To break the direct relation between the total capacitance and the mismatch of the smallest capacitors, three strategies exist to construct the smaller bits: scaling down the switching voltage, scaling with a bridge capacitor, and scaling with the difference between two capacitors [@harpe2019].

The CDAC uses fringe metal–oxide–metal capacitors with capacitance determined by finger length, drawing on the unit-length capacitor approach [@harpe2019].
Small effective weights are formed from the difference between two capacitors switched in opposite directions: $C_\mathrm{eff} = C_\mathrm{main} - C_\mathrm{diff}$.
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

::: {#fig-rec-adc-redundancy plot="rec_adc_redundancy"}
A 12-bit array of 17 decisions (MSB redistribution): each stage's error tolerance (@eq-margin).
:::

::: {#fig-rec-adc-mismatch-margin plot="rec_adc_mismatch_margin"}
A 12-bit array of 17 decisions (MSB redistribution): each stage's margin over its weight's mismatch σ (@eq-calibratable).
:::

Three schemes redistribute the binary array's units: MSB split splits the most significant binary weights into halves, which gives the free first comparison and the decisions after it their tolerance; LSB split splits the least significant weights of at least 2, a tolerance only at the LSB end; MSB redistribution is this work's paired overlay, a run of paired powers of two taken from the MSB and added from the third stage on, its tolerance spread over the whole chain.

Redundant capacitor weights spread a 12-bit conversion over more comparator decisions, 17 in @fig-rec-adc-redundancy, from which a normalized 12-bit result is reconstructed.
At 10 MS/s a conversion lasts 100 ns, permitting approximately 5 ns per decision after sampling and initialization overhead.
Overlapping decision ranges allow later comparisons to correct some earlier errors caused by noise or incomplete settling, with a correction margin that depends on the stage and error magnitude.

::: todo

- @eq-calibratable as the sizing rule: for a given $A$ and $C_u$, the fewest extra decisions that keep $q_k/\sigma_{w_k} \geq 3$.
- Redundancy and time: it shortens a conversion where DAC settling dominates, not where the latch delay does, since it cannot undo a metastable decision [@chang2013].
- Redundancy in the last 1–2 bits relaxes comparator noise beyond quantization noise (@sec-comp-optimization).
- The three calibrations: CDAC S-curves, least squares on a known ramp, and Chang's algorithm [@chang2013].
:::

### Switching scheme {#sec-cdac-switching}

This work uses a modified monotonic, single-side switching procedure, building on the monotonic switching scheme [@liu2010].
Programmable initial capacitor states provide a means to adjust the comparator common-mode trajectory.
Although other switching schemes can reduce theoretical switching energy further, the small array capacitance makes simple rail-driven CMOS switching attractive.

Each decision moves the top plate by the bottom-plate steps it switches, weighted by their capacitance over the total, and draws from the reference the charge those plates take:
$$
\Delta V_\mathrm{top} = \frac{\sum_i C_i\,\Delta V_{\mathrm{bot},i}}{C_\mathrm{tot}}, \qquad Q_\mathrm{ref} = \sum_{i \in \mathrm{ref}} C_i \left(\Delta V_{\mathrm{bot},i} - \Delta V_\mathrm{top}\right).
$$ {#eq-switching}

::: todo

- Switching energy per conversion for monotonic against Vcm-based switching, and the common-mode drift it costs the comparator [@chang2013; @liu2010].
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

## Clocking and sequencing {#sec-clocking}

::: todo

- The SAR loop's timing: sample, then per decision a comparator evaluation, a logic update and a DAC settling, within one conversion period.
- Synchronous against asynchronous control: what each needs (an external fast clock, or a self-timed loop), and what each costs in an array of thousands of converters.
- Could asynchronous operation be beneficial, and also not cause issues in an array?
:::

### Synchronous control {#sec-clocking-sync}

Synchronous control supports implementation with conventional digital synthesis and place-and-route tools.

### Timing budget {#sec-clocking-budget}

Each decision must fit the comparator's delay at its input (@eq-regeneration), the logic's clock-to-output and the DAC's settling (@eq-driver) within its share of the conversion.

## Assembling the converter {#sec-adc}

::: todo

- The assembly problem: pick a sampler, a comparator and an array per process and resolution so that the noise, the area and the power budgets of @sec-specs are all met.
- The trade-off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a different relationship between these: large CDACs have worse speed, but large comparators and sampling switches can typically improve it.
:::

### The noise budget {#sec-adc-noise}

The quantization noise and the three thermal noises, track-and-hold, DAC and comparator, add as powers, since there is no amplification in the circuit:
$$
\sigma_\mathrm{tot}^2 = \frac{\mathrm{LSB}^2}{12} + \frac{2kT}{C} + \sigma_\mathrm{comp}^2 + \sigma_\mathrm{ref}^2.
$$ {#eq-noise-budget}
Each source that adds one quantization noise power costs the converter
$$
\mathrm{ENOB} = N - \frac{1}{2}\log_2\!\left(1 + \sum_i \frac{\sigma_i^2}{\mathrm{LSB}^2/12}\right),
$$ {#eq-enob-budget}
half a bit for one such source, and about 0.8 bit for three equal ones at 0.71 of the quantization noise each.
The reference may add at most half the quantization noise power from its output resistance and half from its noise.

::: todo

- @eq-enob-budget flipped: given the area and power caps, how much of the budget each block gets.
:::

### Energy {#sec-adc-energy}

The energy per conversion sums the three supplies: the comparator's decisions on the analog rail, the logic's registers and clock on the digital rail, and the DAC's charge from the reference (@eq-switching) with its drivers' transitions:
$$
E_\mathrm{conv} = (M + 1)E_\mathrm{dec} + E_\mathrm{logic} + V_\mathrm{ref}\,Q_\mathrm{DAC} + E_\mathrm{drivers},
$$ {#eq-energy}
for $M$ capacitor stages.

::: todo

- The logic's share and what dynamic or TSPC logic would save.
- Energy against rate: static against dynamic consumption.
:::

### Area {#sec-adc-area}

::: todo

- An area budget for the full converter: the array (@fig-cdac-area), the comparator's cap per resolution (15, 20, 63 µm a side), the sampler, the drivers and the logic.
:::
