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
A transmission gate's two devices conduct in parallel, the NMOS (gate at $V_\mathrm{DD}$) strongest at a low input and the PMOS (gate at ground) at a high one [@razavi2025, p. 32; @pelgrom2022, p. 390]:
$$
G(v) = \mu_\mathrm{n} C_\mathrm{ox} \left(\frac{W}{L}\right)_\mathrm{n} \max\!\left(V_\mathrm{DD} - v - V_\mathrm{TH,n}, 0\right) + \mu_\mathrm{p} C_\mathrm{ox} \left(\frac{W}{L}\right)_\mathrm{p} \max\!\left(v - |V_\mathrm{TH,p}|, 0\right), \qquad R_\mathrm{on}(v) = \frac{1}{G(v)}.
$$ {#eq-ron}
With equal device strengths, $\mu_\mathrm{n}(W/L)_\mathrm{n} = \mu_\mathrm{p}(W/L)_\mathrm{p}$, the conductance is constant where both devices conduct; body effect and short-channel effects leave its resistance highest near mid-supply [@razavi2025, p. 32], and it falls as $1/W$.
A bootstrapped switch holds its gate a fixed voltage above the input, so its overdrive, and with it $R_\mathrm{on}$, no longer depends on the input [@razavi2025, p. 45]; with a bootstrap capacitor $C_\mathrm{b}$ shared with the gate's capacitances $C_\mathrm{G}$ and a parasitic $C_\mathrm{p}$ [@razavi2025, p. 50],
$$
R_\mathrm{on} = \frac{1}{\mu_\mathrm{n} C_\mathrm{ox} (W/L)\left(V_\mathrm{b} - V_\mathrm{TH}\right)}, \qquad V_\mathrm{b} = \frac{C_\mathrm{b}}{C_\mathrm{b} + C_\mathrm{G} + C_\mathrm{p}}\,V_\mathrm{DD},
$$ {#eq-ron-boot}
left input-dependent only through the threshold's body effect [@pelgrom2022, p. 399].

### Tracking error and distortion {#sec-samp-distortion}

While tracking, the held node follows the input through the switch's time constant.
To first order, for $\omega_\mathrm{in} R_\mathrm{on} C \ll 1$, it lags the input by $\tau = R_\mathrm{on}(v)\,C$ [@razavi2025, p. 30], and a timing error $t_\mathrm{j}$ adds its own step [@razavi2025, p. 55], so the sample taken at $t_\mathrm{s}$ is
$$
v_\mathrm{held} = v_\mathrm{in}(t_\mathrm{s}) + \left(t_\mathrm{j} - R_\mathrm{on}(v_\mathrm{in})\,C\right)\left.\frac{dv_\mathrm{in}}{dt}\right|_{t_\mathrm{s}} + v_\mathrm{n},
$$ {#eq-tracking}
with $t_\mathrm{j}$ one sample's timing error (its rms value $\sigma_\mathrm{j}$ is the aperture jitter) and $v_\mathrm{n}$ the sampled noise.
Because $R_\mathrm{on}$ depends on the input, the lag is signal-dependent: it is the switch's distortion, and the on-resistance, not the capacitance, sets its limit for a given capacitor.
For a transmission gate driven by a full-scale differential sine its resistance varies as $R_\mathrm{on} = R_0 + R_1 \cos 2\omega_\mathrm{in} t + \dots$, which leaves a third harmonic [@razavi2025, p. 34]
$$
\mathrm{HD}_3 \approx \tfrac{1}{2}\,\omega_\mathrm{in} R_1 C,
$$ {#eq-hd3}
and the timing error alone limits a sine at $f_\mathrm{in}$ to [@pelgrom2022, p. 360; @razavi2025, p. 56]
$$
\mathrm{SNR}_\mathrm{j} = \frac{1}{\left(2\pi f_\mathrm{in}\sigma_\mathrm{j}\right)^2}.
$$ {#eq-jitter}

Settling a full-scale step to half an LSB of an $N$-bit converter takes [@razavi2025, p. 54; @pelgrom2022, p. 390]
$$
t_\mathrm{track} \geq R_\mathrm{on,max}\,C \ln 2^{N+1} = (N + 1) \ln 2 \; R_\mathrm{on,max}\,C,
$$ {#eq-settle}
about $9\tau$ for 12 bits.
A switch with $R_\mathrm{on} \approx 1$ kΩ into $C = 1.64$ pF has $\tau = 1.64$ ns, and needs more than $9\tau$, 15 ns, of tracking for 12 bits.

::: todo

- @eq-tracking flipped into the sizing rule: the largest $R_\mathrm{on}$ (and so the smallest switch) whose signal-dependent lag stays within the noise budget at the input's highest slew.
- Sampling switch non-linearity sets a speed × resolution frontier: @eq-hd3 at the quantization level; Razavi's 10-bit example asks $R_1 C \leq T_\mathrm{CK}/2000$ at Nyquist [@razavi2025, p. 34], and a complementary switch alone is inadequate above about 6 bits of linearity [@razavi2015bootstrap, p. 13].
:::

### Charge injection {#sec-samp-injection}

When the switch opens, its gate couples onto the held node through the overlap capacitance $C_\mathrm{ov}$ per width, and about half of its channel charge leaves through the held node [@pelgrom2022, p. 384]:
$$
\Delta V = -\frac{W C_\mathrm{ov} V_\mathrm{DD} + \tfrac{1}{2} W L C_\mathrm{ox} \left(V_\mathrm{DD} - v_\mathrm{in} - V_\mathrm{TH}\right)}{C}.
$$ {#eq-pedestal}
The pedestal times the switch's time constant depends on the technology alone, with all the channel charge taken onto $C$ [@razavi2025, p. 38]:
$$
\Delta V \cdot \tau = \frac{L^2}{\mu_\mathrm{n}}.
$$ {#eq-speed-precision}

::: todo

- The charge each device injects, roughly half its channel charge $W L C_\mathrm{ox} (V_\mathrm{GS} - V_\mathrm{TH})$ @eq-pedestal, and the transmission gate: its two devices' charges cancel at only one input level, where $W_\mathrm{n} L_\mathrm{n} (V_\mathrm{DD} - v - V_\mathrm{TH,n}) = W_\mathrm{p} L_\mathrm{p} (v - |V_\mathrm{TH,p}|)$ [@razavi2017, p. 554], and differential sampling removes the common part [@razavi2025, p. 41].
:::

### Sampling noise {#sec-samp-noise}

The switch's thermal noise, filtered by the bandwidth it sets itself, leaves a noise on the held voltage set by the capacitance alone: its density $4kTR_\mathrm{on}$ through the $R_\mathrm{on}C$ low-pass integrates to [@razavi2025, p. 39; @pelgrom2022, p. 350]
$$
\int_0^\infty \frac{4kTR_\mathrm{on}}{1 + \left(2\pi f R_\mathrm{on} C\right)^2}\,df = \frac{kT}{C},
$$ {#eq-ktc}
and between the two sides of a differential sampler, for a capacitance $C$ per side [@razavi2025, p. 41; @pelgrom2022, p. 355],
$$
\sigma_\mathrm{sample} = \sqrt{\frac{2kT}{C}}.
$$ {#eq-ktc-samp}
Here $C$ is the capacitive DAC's: for 1.64 pF per side $\sigma_\mathrm{sample}$ is about 71 µV, 0.24 LSB of a 1.2 V span at 12 bits.
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

A StrongARM integrates until its drains, P and Q, have fallen by the threshold $V_\mathrm{THN}$ of the cross-coupled NMOS that then turns on; with a tail current $I_\mathrm{SS}$ and a capacitance $C_\mathrm{P}$ at each drain this takes, and gains the input by [@razavi2025, p. 116]
$$
t_\mathrm{int} = \frac{2C_\mathrm{P}V_\mathrm{THN}}{I_\mathrm{SS}}, \qquad A_0 = \frac{2g_\mathrm{m}V_\mathrm{THN}}{I_\mathrm{SS}}.
$$ {#eq-strongarm-integration}
A dynamic bias stops the input pair once the charge shared with C_TAIL has lowered the drains' common mode by at most [@bindra2018, p. 1906]
$$
\Delta V_\mathrm{CM} = \frac{C_\mathrm{TAIL}}{C_\mathrm{TAIL} + 2C_\mathrm{P}}\,V_\mathrm{DD}.
$$ {#eq-dynamic-bias}

::: todo

- How a StrongARM decides: reset, integration on the drains' capacitance @eq-strongarm-integration, regeneration in the cross-coupled pair.
- What the double tail separates (integration from regeneration), and what the dynamic bias stops (the input pair, once its drains have fallen by @eq-dynamic-bias).
:::

### Noise from the integration capacitance {#sec-comp-noise}

During integration the input pair discharges the capacitance $C_\mathrm{P}$ at each of its drains, and its thermal noise is integrated with the signal.
For a StrongARM the input-referred noise is [@razavi2025, p. 116]
$$
\sigma^2 = \frac{2kT}{C_\mathrm{P}}\, r\left(\gamma + \frac{r}{4}\right), \qquad r = \frac{(V_\mathrm{GS} - V_\mathrm{TH})_\mathrm{in}}{V_\mathrm{THN}},
$$ {#eq-strongarm-noise}
the first term the input pair's, the second the drains' reset kT/C, with $V_\mathrm{THN}$ the threshold of the cross-coupled NMOS whose turn-on ends integration.
An earlier form has twice the first term [@razavi2015, p. 15]; the factor depends on the noise bandwidth taken for an integration time $T$, $1/(2T)$ or $1/T$ [@pelgrom2022, p. 629].
So the noise power falls as $1/C_\mathrm{P}$: the integration capacitance sets the comparator's noise, as the sampling capacitance sets the sampler's.

Every width times $k$ multiplies $C_\mathrm{P}$, and with it the charge drawn per decision, by $k$.
So the noise falls as $1/\sqrt{k}$ and the energy rises as $k$, keeping the delay:
$$
E \propto k, \qquad \sigma \propto \frac{1}{\sqrt{k}} \quad\Rightarrow\quad E\,\sigma^2 = \text{const.}
$$ {#eq-comp-scaling}
The product $E\,\sigma^2$ is the comparator's figure of merit [@tang2020, p. 1016]: scaling a design moves it along a line of constant $E\,\sigma^2$, and only a better topology, supply or input-pair bias moves the line.
A StrongARM draws $E \approx (C_\mathrm{X} + 2C_\mathrm{P})\,V_\mathrm{DD}^2$ per decision, as three of its four nodes, both drains and one latch output of capacitance $C_\mathrm{X}$, fall to ground and are precharged again [@razavi2025, p. 97], and with $n$ the subthreshold slope factor its figure of merit and a dynamic bias's are [@tang2020, p. 1016]
$$
E\sigma^2\big|_\mathrm{SA} = \frac{4nkT\,V_\mathrm{DD}^2}{V_\mathrm{THN}}\,\frac{I_\mathrm{D}}{g_\mathrm{m}}, \qquad E\sigma^2\big|_\mathrm{DB} = 4nkT\,V_\mathrm{DD}\,\frac{I_\mathrm{D}}{g_\mathrm{m}},
$$ {#eq-comp-fom}
so the dynamic bias gains $V_\mathrm{DD}/V_\mathrm{THN}$ at an equal $g_\mathrm{m}/I_\mathrm{D}$.

::: todo

- The noise floor the families approach, $\sigma = \sqrt{a^2/k + f^2}$, and where it comes from.
:::

### Regeneration and metastability {#sec-comp-metastability}

Once integration ends, the cross-coupled pair amplifies the difference exponentially with a time constant $\tau \approx C_\mathrm{X}/g_\mathrm{m}$, set by its own capacitance over its transconductance [@razavi2025, p. 78].
An input $v$, gained by $A_0$ @eq-strongarm-integration, is resolved to a logic level in [@razavi2025, p. 109; @bankman2019, p. 89]
$$
t_\mathrm{d}(v) = t_0 + \tau \ln\frac{V_\mathrm{DD}}{A_0|v|},
$$ {#eq-regeneration}
so the delay grows only logarithmically as the input falls, and a decision whose delay exceeds the window the SAR loop allows is late.
Within a regeneration window $T_\mathrm{m}$, an input spread evenly over $\pm\Delta V$ stays unresolved with probability [@razavi2025, p. 112]
$$
P_\mathrm{err} = \frac{0.9\,V_\mathrm{DD}}{A_0\,\Delta V}\,e^{-T_\mathrm{m}/\tau}.
$$ {#eq-metastability}

::: todo

- @eq-regeneration flipped: the window per decision sets the smallest input that resolves, $V_\mathrm{DD}\,e^{-(T - T_\mathrm{FIX})/\tau}$ for a window $T$ less a fixed delay $T_\mathrm{FIX}$ [@bankman2019, p. 90], and so, with @eq-metastability at $\Delta V$ of half an LSB, the decision-error rate per conversion.
:::

### Kickback and offset {#sec-comp-kickback}

A device pair's threshold mismatch falls with its gate area [@pelgrom2022, p. 311; @razavi2025, p. 107],
$$
\sigma_{\Delta V_\mathrm{TH}} = \frac{A_{V_\mathrm{TH}}}{\sqrt{WL}},
$$ {#eq-avt}
and a StrongARM's offset is the input pair's mismatch with the latch's divided by the integration gain [@razavi2025, p. 93; @pelgrom2022, p. 617]:
$$
\sigma_\mathrm{os}^2 = \sigma_{\Delta V_\mathrm{TH},\mathrm{in}}^2 + \frac{\sigma_{\Delta V_\mathrm{TH},\mathrm{latch}}^2}{A_0^2}.
$$ {#eq-offset}

::: todo

- Kickback: the inputs' largest excursion over a decision, driven as a DAC's top plates; how it depends on the CDAC's state.
- Offset: systematic only in simulation; how offset relates to sampling noise and CDAC error, and why a SAR tolerates it (a shift of every code): it adds to the input without DNL and narrows the range to $V_\mathrm{FS} - V_\mathrm{OS}$, though it moves with the input common mode [@razavi2025, p. 321].
:::

## Capacitive DAC {#sec-cdac}

The capacitor digital-to-analog converter (CDAC) holds the sampled input on its top plates and, by switching its bottom plates between the reference rails, subtracts each trial weight from it.
CDAC total capacitance often dominates area usage and is a large portion of the power budget.
Assuming no noise shaping or cancellation, kT/C sampling noise provides the theoretical limit on ADC error, and is determined by $C_\mathrm{tot}$.
However, a conventional CDAC implemented with capacitor scaling alone exhibits severe mismatch in its LSB capacitors as its $C_\mathrm{tot}$ is shrunk.
This chapter writes down the two limits, noise and matching, as minimum capacitances, and the redundancy that lets calibration recover what matching leaves.

### Top-plate sampling {#sec-cdac-top-plate}

In most SAR implementations the CDAC switches are connected to the capacitor bottom plates (named for their closer proximity to the transistors) and the comparator to the shared top plate.
Top-plate sampling allows a comparator decision to be taken without first switching the CDAC, so an $N$-bit ADC needs only an $(N-1)$-bit CDAC, $N_\mathrm{DAC} = N - 1$, halving its area [@liu2010]; it also simplifies the switch layout and logic for the bottom plates, as fewer voltages need to be distributed across the array.
Bottom-plate sampling can in some configurations improve linearity, as all charge summing happens on the same end of each capacitor.

### The noise limit: minimum capacitance {#sec-cdac-noise}

The differential sampling noise on a capacitance $C$ per side is @eq-ktc-samp $\sqrt{2kT/C}$, and the quantization noise of an ideal $N$-bit converter is $\sigma_\mathrm{q} = \mathrm{LSB}/\sqrt{12}$ @eq-quantization, with $\mathrm{LSB} = V_\mathrm{FS}/2^N$ for a differential full-scale span $V_\mathrm{FS}$, $2V_\mathrm{ref}$ for an ideal array switched between ground and $V_\mathrm{ref}$ [@razavi2025, p. 346].
Setting the two equal gives the least capacitance per side that adds no more noise power than quantization does [@razavi2025, p. 316]:
$$
C_\mathrm{min} = \frac{24\,kT}{\mathrm{LSB}^2} = \frac{24\,kT\,4^N}{V_\mathrm{FS}^2} = \frac{6\,kT\,4^N}{V_\mathrm{ref}^2},
$$ {#eq-cmin-noise}
at 300 K 26 fF at 10 bits and $V_\mathrm{ref} = 1$ V, 6.7 pF at 14.
It quadruples with every bit, and at it the converter loses half a bit [@razavi2025, p. 316]:
$$
\mathrm{ENOB} = N - \frac{1}{2}\log_2\!\left(1 + \frac{2kT/C}{\mathrm{LSB}^2/12}\right).
$$ {#eq-enob-ktc}

::: {#fig-enob-ctot plot="enob_ctot"}
ENOB with quantization and kT/C noise only @eq-enob-ktc against the capacitance per side, for 10, 12 and 14 bits on a 1.2 V differential full scale. Each marker is that resolution's minimum, @eq-cmin-noise, where the converter loses half a bit.
:::

Capacitance also establishes the sampling-noise budget.
For an illustrative 800 fF capacitance per differential branch at 300 K, the ideal differential sampling noise is $\sigma_\mathrm{sample} = \sqrt{2kT/C} \approx 102$ µV RMS.
For an assumed 1.2 V differential full-scale span, ideal 12-bit quantization noise is $\sigma_\mathrm{q} = (1.2\,\mathrm{V}/2^{12})/\sqrt{12} \approx 85$ µV RMS.
Sampling noise is therefore already comparable to quantization noise at this capacitance, making capacitor sizing consequential for effective resolution.

### The matching limit {#sec-cdac-matching}

A capacitor's random mismatch shrinks with its size.
For a metal fringe capacitor the relative standard deviation scales with the square root of its capacitance [@pelgrom1989; @tripathi2014, p. 2241; @pelgrom2022, p. 299]:
$$
\frac{\sigma_C}{C} = \frac{A_C}{\sqrt{C}},
$$ {#eq-pelgrom}
with $C$ in fF and $A_C$ the matching coefficient of a single capacitor in %·√fF; a coefficient given for a pair's difference, as Pelgrom's is, is $\sqrt{2}$ times a single capacitor's [@pelgrom2022, p. 299].

In a binary array of $N_\mathrm{DAC}$ bits of unit capacitors $C_\mathrm{u}$ the largest error falls at the mid-code transition, where the MSB capacitor, $2^{N_\mathrm{DAC}-1}$ units, is compared against all the others, $2^{N_\mathrm{DAC}-1} - 1$ units.
Their difference has a standard deviation, in LSB [@tripathi2014thesis, p. 28],
$$
\sigma_\mathrm{mid} = \frac{A_C}{\sqrt{C_\mathrm{u}}}\sqrt{2^{N_\mathrm{DAC}-1} + \left(2^{N_\mathrm{DAC}-1} - 1\right)} = \frac{A_C}{\sqrt{C_\mathrm{u}}}\sqrt{2^{N_\mathrm{DAC}} - 1},
$$ {#eq-midcode}
and the integral error at mid-scale [@razavi2025, p. 217]
$$
\sigma_\mathrm{INL} = \frac{1}{2}\sqrt{2^{N_\mathrm{DAC}}}\,\frac{A_C}{\sqrt{C_\mathrm{u}}}.
$$ {#eq-inl-sigma}
Flipped around, a target $\sigma_\mathrm{mid}$ (a quarter LSB keeps four sigma within one) sets the least unit capacitor, and with it the least total per side [@pelgrom2022, p. 768]:
$$
C_\mathrm{u} \geq \left(2^{N_\mathrm{DAC}} - 1\right)\left(\frac{A_C}{\sigma_\mathrm{mid}}\right)^2, \qquad C_\mathrm{tot} = 2^{N_\mathrm{DAC}} C_\mathrm{u}.
$$ {#eq-cmin-matching}
Matching asks for $4^N$ as noise does, but with the coefficient $A_C^2$ in place of $kT/V_\mathrm{ref}^2$; whichever is larger in a given process sets the array.

::: {#fig-cdac-limits plot="cdac_limits"}
The noise and the matching limits on the total capacitance per side, with top-plate sampling ($N_\mathrm{DAC} = N - 1$): @eq-cmin-noise, and @eq-cmin-matching at $\sigma_\mathrm{mid}$ of a quarter LSB for two published single-capacitor coefficients.
:::

::: todo

- Which limit binds at 10, 12 and 14 bits for the matching coefficients published for MOM capacitors (up to 0.22 %·√fF [@harpe2019], 0.85 %·√fF [@tripathi2014, p. 2241]).
:::

### Breaking the scaling: difference capacitors {#sec-cdac-difference}

To break the direct relation between the total capacitance and the mismatch of the smallest capacitors, three strategies exist to construct the smaller bits: scaling down the switching voltage, scaling with a bridge capacitor, and scaling with the difference between two capacitors [@harpe2019].

The CDAC uses fringe metal–oxide–metal capacitors with capacitance determined by finger length, drawing on the unit-length capacitor approach [@harpe2019].
Small effective weights are formed from the difference between two capacitors switched in opposite directions: $C_\mathrm{eff} = C_\mathrm{main} - C_\mathrm{diff}$ [@harpe2019, p. 638].
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

- The mismatch of a difference weight: both elements' errors add, so $\sigma(C_\mathrm{eff}) = A_C\sqrt{C_\mathrm{main} + C_\mathrm{diff}}$, large against the weight itself; why redundancy and calibration are therefore part of the design, not an afterthought. For the whole array the full scale goes as $C_\mathrm{eff}/C_\mathrm{tot}$ and the DNL's sigma as $\sqrt{C_\mathrm{tot}/C_\mathrm{eff}}$ [@harpe2019, p. 638].
- MOM structures: unit-length strips, three metal layers, the 2:1 outline per branch.
:::

### Redundancy and calibration {#sec-redundancy}

Errors in ADC digitization fall into static errors (accuracy), limited by manufacturing variability that produces repeatable errors characterized by INL and DNL, mainly capacitor mismatch and comparator offset; and dynamic errors (precision), limited by random transient variations: sampling noise, comparator noise, reference noise, and insufficient settling time.
Techniques that correct static errors are termed calibration, and only a certain magnitude of mismatch can be calibrated, determined by the radix of the system: a binary-weighted (radix-2) ADC can only calibrate up to 1 LSB worth of capacitor variation, whereas a sub-radix-2 design can tolerate more.

A redundant array spreads the binary DAC's weight over more decisions than bits.
With top-plate sampling and no over-range, its $M$ weights $w_0 \dots w_{M-1}$, in LSB, sum to $2^{N-1} - 1$ and each is no larger than all the weights after it plus one [@ogawa2009, p. 67]:
$$
\sum_{k=0}^{M-1} w_k = 2^{N-1} - 1, \qquad w_k \leq \sum_{j > k} w_j + 1.
$$ {#eq-redundancy}
The extra decisions never add capacitance.
With a constant radix $\alpha < 2$, $K$ decisions resolve at most [@chang2013, p. 69]
$$
N \leq \log_2 \frac{\alpha^K + \alpha - 2}{\alpha - 1}
$$ {#eq-radix}
bits.
A wrong decision at stage $k$ is corrected by the later ones as long as its error lies within the stage's redundancy margin [@ogawa2009, p. 67]
$$
q_k = \sum_{j > k} w_j - w_k + w_{M-1},
$$ {#eq-margin}
in which Ogawa's last comparison's LSB is written as the last weight, $w_{M-1}$; the margin is zero at every stage of a binary array: binary weights tolerate no error, and their static mismatch can only be calibrated where it happens to fall within one LSB.

What calibration cannot recover is a missing level: a code no decision path reaches, the widest path over a code minus one [@chang2013].
Calibration is possible where every stage's margin covers the error of the steps it spans.
That margin, stage $k$'s step against all the later ones, has the standard deviation $\sigma_{q_k} = \frac{A_C}{\sqrt{C_\mathrm{u}}}\sqrt{\sum_{j \geq k} w_j}$ in LSB, with $(C_{\mathrm{main},j} + C_{\mathrm{diff},j})/C_\mathrm{u}$ in place of $w_j$ for a difference weight; the least redundancy that keeps an array calibratable at $z$ standard deviations is the one that gives
$$
q_k \geq z\,\sigma_{q_k} \quad \text{at every stage } k,
$$ {#eq-calibratable}
a margin over mismatch as in Chang's criterion, which takes a size-independent relative error instead [@chang2013, p. 71].

::: {#fig-rec-adc-redundancy plot="rec_adc_redundancy"}
A 12-bit array of 17 decisions (MSB redistribution): each stage's error tolerance @eq-margin.
:::

::: {#fig-rec-adc-mismatch-margin plot="rec_adc_mismatch_margin"}
A 12-bit array of 17 decisions (MSB redistribution): each stage's margin over the margin's mismatch σ @eq-calibratable.
:::

Three schemes redistribute the binary array's units: MSB split splits the most significant binary weights into halves, which gives the free first comparison and the decisions after it their tolerance; LSB split splits the least significant weights of at least 2, a tolerance only at the LSB end; MSB redistribution is this work's paired overlay, a run of paired powers of two taken from the MSB and added from the third stage on, its tolerance spread over the whole chain.

Redundant capacitor weights spread a 12-bit conversion over more comparator decisions, 17 in @fig-rec-adc-redundancy, from which a normalized 12-bit result is reconstructed.
At 10 MS/s a conversion lasts 100 ns, permitting approximately 5 ns per decision after sampling and initialization overhead.
Overlapping decision ranges allow later comparisons to correct some earlier errors caused by noise or incomplete settling, with a correction margin that depends on the stage and error magnitude.

::: todo

- @eq-calibratable as the sizing rule: for a given $A_C$ and $C_\mathrm{u}$, the fewest extra decisions that keep $q_k/\sigma_{q_k} \geq 3$.
- Redundancy and time: it shortens a conversion where DAC settling dominates, not where the latch delay does, since it cannot undo a metastable decision [@chang2013].
- Redundancy in the last 1–2 bits relaxes comparator noise beyond quantization noise (@sec-comp-optimization).
- The three calibrations: CDAC S-curves, least squares on a known ramp, and Chang's algorithm [@chang2013].
:::

### Switching scheme {#sec-cdac-switching}

This work uses a modified monotonic, single-side switching procedure, building on the monotonic switching scheme [@liu2010].
Programmable initial capacitor states provide a means to adjust the comparator common-mode trajectory.
Although other switching schemes can reduce theoretical switching energy further, the small array capacitance makes simple rail-driven CMOS switching attractive.

Each decision moves the top plate by the bottom-plate steps it switches, weighted by their capacitance over the top plate's total $C_\mathrm{top}$, its parasitic included, and draws from the reference the charge taken by the plates on the reference after the step [@mccreary1975, p. 372; @ginsburg2005, p. 185; @pelgrom2022, p. 753]:
$$
\Delta V_\mathrm{top} = \frac{\sum_i C_i\,\Delta V_{\mathrm{bot},i}}{C_\mathrm{top}}, \qquad Q_\mathrm{ref} = \sum_{i \in \mathrm{ref}} C_i \left(\Delta V_{\mathrm{bot},i} - \Delta V_\mathrm{top}\right).
$$ {#eq-switching}
Averaged over equally likely codes, with $C$ the unit capacitor, conventional switching [@ginsburg2005], monotonic switching [@liu2010] and Vcm-based switching [@zhu2010] draw [@lin2015, p. 71]
$$
E_\mathrm{conv} = \sum_{i=1}^{N} 2^{N+1-2i}\left(2^i - 1\right) C V_\mathrm{ref}^2, \qquad E_\mathrm{mono} = \sum_{i=1}^{N-1} 2^{N-2-i}\, C V_\mathrm{ref}^2, \qquad E_\mathrm{Vcm} = \sum_{i=1}^{N-1} 2^{N-2-2i}\left(2^i - 1\right) C V_\mathrm{ref}^2.
$$ {#eq-switching-energy}

::: {#fig-switching-energy-code plot="switching_energy_code"}
Reference energy per conversion over the output code of an ideal 10-bit differential array, by charge accounting at each switching event @eq-switching: conventional switching with $N$-bit arrays [@ginsburg2005], monotonic [@liu2010] and Vcm-based [@zhu2010] with $(N-1)$-bit arrays and top-plate sampling. The means, 1363.3, 255.5 and 170.2 C·Vref², are those of @eq-switching-energy; the Vcm rail's energy is counted at its voltage.
:::

::: {#fig-switching-energy-bits plot="switching_energy_bits"}
Mean reference energy per conversion against resolution for the three schemes of @fig-switching-energy-code. Each approaches a constant times $2^N$: $\tfrac{4}{3}\,2^N$, $2^N/4$ and $2^N/6$ C·Vref².
:::

::: todo

- @fig-switching-energy-code and @fig-switching-energy-bits read: where each scheme spends its charge over the code, and what the factor between them is worth against the comparator's and the logic's energy @eq-energy.
- The common-mode drift monotonic switching costs the comparator, and what the modified single-side procedure and the programmable initial state change [@chang2013; @liu2010].
:::

### Drivers and settling {#sec-cdac-settling}

A stage's bottom plate settles first order through its driver.
To settle a stage of weight $w_k$, in LSB, to half an LSB takes [@pelgrom2022, p. 764; @razavi2025, p. 54]
$$
n_k = \ln\!\left(2\,w_k\right)
$$ {#eq-driver}
time constants, $\ln 2^{N+1}$ for a full-scale step, into the plate in series with the rest of the array, $C_\mathrm{plate}(C_\mathrm{top} - C_\mathrm{plate})/C_\mathrm{top}$ [@razavi2025, p. 215; @pelgrom2022, p. 763]; each driver is sized for that within its share of the decision time, tapering by fanout 4 from a minimum flip-flop [@chang2013].

### Top-plate parasitics and full scale {#sec-cdac-parasitic}

The top plate's parasitic capacitance divides every step: the full scale is the reference times the switched capacitance over the top plate's total [@razavi2025, p. 218; @harpe2019, p. 638],
$$
V_\mathrm{FS} = 2V_\mathrm{ref}\,\frac{\sum C_\mathrm{main} - \sum C_\mathrm{diff}}{C_\mathrm{top}}.
$$ {#eq-full-scale}

## Clocking and sequencing {#sec-clocking}

::: todo

- The SAR loop's timing: sample, then per decision a comparator evaluation, a logic update and a DAC settling, within one conversion period.
- Synchronous against asynchronous control: what each needs (an external fast clock, or a self-timed loop), and what each costs in an array of thousands of converters.
- Could asynchronous operation be beneficial, and also not cause issues in an array?
:::

### Synchronous control {#sec-clocking-sync}

Synchronous control supports implementation with conventional digital synthesis and place-and-route tools.

### Timing budget {#sec-clocking-budget}

Each decision must fit the comparator's delay at its input @eq-regeneration, the logic's clock-to-output and the DAC's settling @eq-driver within its share of the conversion.

## Assembling the converter {#sec-adc}

::: todo

- The assembly problem: pick a sampler, a comparator and an array per process and resolution so that the noise, the area and the power budgets of @sec-specs are all met.
- The trade-off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a different relationship between these: large CDACs have worse speed, but large comparators and sampling switches can typically improve it.
:::

### The noise budget {#sec-adc-noise}

The quantization noise and the three thermal noises, track-and-hold, reference and comparator, add as powers, since there is no amplification in the circuit [@pelgrom2022, p. 439; @razavi2025, p. 321]:
$$
\sigma_\mathrm{tot}^2 = \frac{\mathrm{LSB}^2}{12} + \frac{2kT}{C} + \sigma_\mathrm{comp}^2 + \sigma_\mathrm{ref}^2.
$$ {#eq-noise-budget}
Each source that adds one quantization noise power costs the converter
$$
\mathrm{ENOB} = N - \frac{1}{2}\log_2\!\left(1 + \sum_i \frac{\sigma_i^2}{\mathrm{LSB}^2/12}\right),
$$ {#eq-enob-budget}
half a bit for one such source, and about two thirds of a bit for three equal ones at 0.71 of the quantization noise each, half its power.
The reference may add at most half the quantization noise power from its output resistance and half from its noise.

::: todo

- @eq-enob-budget flipped: given the area and power caps, how much of the budget each block gets.
:::

### Energy {#sec-adc-energy}

The energy per conversion sums the three supplies: the comparator's decisions on the analog rail, the logic's registers and clock on the digital rail, and the DAC's charge from the reference @eq-switching with its drivers' transitions:
$$
E_\mathrm{conv} = (M + 1)E_\mathrm{dec} + E_\mathrm{logic} + V_\mathrm{ref}\,Q_\mathrm{DAC} + E_\mathrm{drivers},
$$ {#eq-energy}
for $M$ capacitor stages and $M + 1$ decisions.

::: todo

- The logic's share and what dynamic or TSPC logic would save.
- Energy against rate: static against dynamic consumption.
:::

### Area {#sec-adc-area}

::: todo

- An area budget for the full converter: the array (@fig-cdac-area), the comparator's cap per resolution (15, 20, 63 µm a side), the sampler, the drivers and the logic.
:::
