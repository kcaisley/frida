# Design of a compact SAR ADC {#sec-design-of-a-compact-sar-adc}

## Study of a sampling switch {#sec-study-of-a-sampling-switch}

A sampling switch is a circuit element which allows a continuously varying input voltage to be intermittently sampled and held constantly. During the “track” phase, a switch, typically constructed from MOS channels, is allowed to conduct, and The size of the capacitance alone determines the average expected sampling error from thermal noise, since increasing the series resistance of the switch generates thermal noise but also limits noise bandwidth. This building block is found in nearly all ADC architectures. There are three other non-idealities which one must worry about: First, the RC time constant of the switch and sampling capacitor though also set a bandwidth limit on the switch, causing distortion with increasing input signal speeds. Second, since the Rds_on of the transistor is determined by its gate–source voltage, the input signal level affects the effective RD, causing the sampling error to also be signal amplitude dependent. And thirdly the parasitic capacitance of the switch itself can cause charge injection The proper design of sampling switches is heavily predicated on how fast the switch needs to operate.

### On-resistance and acquisition bandwidth

#### Device size and input-voltage dependence

[Section explaining device size and input-voltage dependence.]

#### Simple switch versus bootstrapped switch

[Section explaining simple switch versus bootstrapped switch.]

### Sampling noise

[Section explaining thermal-noise and capacitance limits.]

[Section explaining extracted held-level noise and comparator contributions.]

### Dynamic sampling error

#### Settling error versus sampling-window duration

[Section explaining settling error versus sampling-window duration.]

#### Input bandwidth and effective-resolution limits

[Section explaining input bandwidth and effective-resolution limits.]

## Study of a dynamic comparator {#sec-study-of-a-dynamic-comparator}

### Architectures

#### Regeneration, reset, and output retention

[Section explaining regeneration, reset, and output retention.]

#### Kickback and its dependence on CDAC state

[Section explaining kickback and its dependence on CDAC state.]

### Input-referred noise

#### Standalone and full-ADC noise simulations

[Section explaining standalone and full-ADC noise simulations.]

### Input offset voltage

#### Offset relative to sampling noise and CDAC error

[Section explaining offset relative to sampling noise and CDAC error.]

### Clock rate and metastability

#### Evaluation-time and input-overdrive dependence

[Section explaining evaluation-time and input-overdrive dependence.]

#### Comparator, logic, and CDAC timing margins

[Section explaining comparator, logic, and CDAC timing margins.]

#### Metastability versus incomplete output-latch transfer

[Section explaining metastability versus incomplete output-latch transfer.]

### Power consumption

[Section explaining power consumption.]

### Layout area

[Section explaining layout area.]

## Study of a compact CDAC array {#sec-study-of-a-compact-cdac-array}

### Capacitor styles

#### MIM capacitors

[Section explaining MIM capacitors.]

#### MOS capacitors

[Section explaining MOS capacitors.]

#### POD capacitors

[Section explaining POD capacitors.]

#### MOM capacitors

[Section explaining MOM capacitors.]

#### FMOM capacitors

[Section explaining FMOM capacitors.]

### Capacitance density, shielding, and parasitics

#### Connected-layer extraction and capacitance partition

[Section explaining connected-layer extraction and capacitance partition.]

#### Input attenuation and usable voltage range

[Section explaining input attenuation and usable voltage range.]

### Capacitance budget and weight architecture

#### Sampling-noise and mismatch constraints

The ideal differential sampling noise for a capacitance $C$ per branch at temperature $T$ is
$$
\sigma_\mathrm{sample} = \sqrt{\frac{2kT}{C}},
$$ {#eq-ktc}
[citation needed], and the quantization noise of an ideal $N$-bit converter of full-scale range $V_\mathrm{FS}$ is [@walden1999]
$$
\sigma_\mathrm{quant} = \frac{V_\mathrm{FS} / 2^N}{\sqrt{12}}.
$$ {#eq-quant}

Capacitance also establishes the sampling-noise budget. For an illustrative 800 fF capacitance per differential branch at 300 K, the ideal differential sampling noise is σ_sample = √(2kT/C) ≈ 102 µV RMS. For an assumed 1.2 V differential full-scale span, ideal 12-bit quantization noise is σ_quant = (1.2 V / 2^12) / √12 ≈ 85 µV RMS. Sampling noise is therefore already comparable to quantization noise at this capacitance, making capacitor sizing consequential for effective resolution. The prototype's nominal physical capacitance, including both members of the difference pairs, is approximately 1.88 pF per branch; the same ideal estimate gives approximately 66 µV RMS, before comparator noise and other nonidealities are included.

#### Coarse and fine weight implementation

The capacitor digital-to-analog converter (CDAC) is the principal architectural feature enabling this compact layout. It uses fringe metal–oxide–metal capacitors with capacitance determined by finger length, drawing on the unit-length capacitor approach [@harpe2019], published in the March 2019 issue of JSSC. Small effective weights are formed from the difference between two capacitors switched in opposite directions: C_eff = C_main − C_diff. The prototype's smallest effective weight is 0.8 fF, obtained from nominal 26.4 fF and 25.6 fF elements. This avoids relying on an individually fabricated capacitor of the same small value, while retaining a compact array without a bridge-capacitor divider or additional scaled reference voltages. The benefit comes with sensitivity to matching between the paired elements, which must be assessed through extraction, modeling, and calibration.

::: {#fig-capacitor-views src="../images/report/capacitor_views"}
Plan and three-dimensional views of a shortened main/difference MOM capacitor cell, with the shared surrounding electrode in blue and independent inner electrodes in orange.
:::

The capacitor illustration presents side-by-side plan and perspective views of the same shortened geometry. A blue surrounding common electrode couples to independent orange main and difference electrodes. Opposite switching produces the effective weight of element N, C_eff,N = C_N,main − C_N,diff. The perspective shows three metal layers connected by grey vias, while the plan shows their shared footprint and via locations. Each inner electrode has two vias near its outer end, away from the split between main and difference electrodes.

### Capacitor mismatch

#### Unit-cell and array-level mismatch models

[Section explaining unit-cell and array-level mismatch models.]

#### Node-specific mismatch and predicted nonlinearity

[Section explaining node-specific mismatch and predicted nonlinearity.]

### Switching scheme

#### Energy, control complexity, and common-mode trajectory

FRIDA uses a modified monotonic, single-side switching procedure, building on the monotonic switching scheme [@liu2010]. Programmable initial capacitor states provide a means to adjust the comparator common-mode trajectory. Although other switching schemes can reduce theoretical switching energy further, the small array capacitance makes simple rail-driven CMOS switching attractive. The remaining architecture similarly prioritizes compactness: transmission-gate sampling switches, top-plate sampling, and a single-stage StrongARM comparator avoid a bootstrapped sampler, an internal input buffer, and a dedicated intermediate common-mode reference generator. The front end must nevertheless provide suitable input common mode and settling, and the reference supply must remain sufficiently stable.

#### Initial CDAC state and comparator common mode

[Section explaining initial CDAC state and comparator common mode.]

### Driver sizing and settling time

#### Capacitive load and bit-dependent settling budget

[Section explaining capacitive load and bit-dependent settling budget.]

### Power consumption

[Section explaining power consumption.]

### Layout area

[Section explaining layout area.]

## Study of the complete SAR ADC {#sec-study-of-the-complete-sar-adc}

### CDAC switching scheme

#### Extracted top-plate trajectories and settling

[Section explaining extracted top-plate trajectories and settling.]

### System nonlinearity

#### Transfer gain and full-scale input range

[Section explaining transfer gain and full-scale input range.]

#### Mismatch, parasitics, and INL/DNL simulations

[Section explaining mismatch, parasitics, and INL/DNL simulations.]

### Weight calibration

#### Weight extraction from a ramp and comparator A/B tests

[Section explaining weight extraction from a ramp and comparator A/B tests.]

#### Sensitivity to reference and input noise

[Section explaining sensitivity to reference and input noise.]

### System sampling rate

#### Conversion-path timing budget

[Section explaining conversion-path timing budget.]

#### Noise and distortion versus sampling rate

[Section explaining noise and distortion versus sampling rate.]

### System noise and resolution budget

#### Quantization, sampling, comparator, and reference noise

[Section explaining quantization, sampling, comparator, and reference noise.]

#### Predicted ENOB versus input range and sampling rate

[Section explaining predicted ENOB versus input range and sampling rate.]

### Decision redundancy

#### Error-recovery range of redundant weights

Redundant capacitor weights spread the conversion over 17 comparator decisions, from which a normalized 12-bit result is reconstructed. At 10 MS/s, a conversion lasts 100 ns, permitting approximately 5 ns per decision after sampling and initialization overhead. Overlapping decision ranges allow later comparisons to correct some earlier errors caused by noise or incomplete settling, with a correction margin that depends on the stage and error magnitude. Synchronous control supports implementation with conventional digital synthesis and place-and-route tools. A one-hot stage selector advances through 16 capacitor-control stages, followed by a terminal comparison that contributes to the decoded result without switching another capacitor.

#### Redundant versus minimum-cycle conversion at equal total time

[Section explaining redundant versus minimum-cycle conversion at equal total time.]

#### Effect of redundancy on noise and decision errors

[Section explaining effect of redundancy on noise and decision errors.]

### Control-sequence optimization

#### Sampling-to-first-decision gap

[Section explaining sampling-to-first-decision gap.]

#### Comparator evaluation, reset, and logic duty cycles

[Section explaining comparator evaluation, reset, and logic duty cycles.]

#### Continuous conversion and final-decision decoding

[Section explaining continuous conversion and final-decision decoding.]

### Control logic

::: {#fig-adc-architecture src="../images/report/adc_architecture"}
Circuitikz schematic of the differential ADC, redundant capacitor weights, synchronous SAR registers, and main/difference capacitor pair.
:::

The circuit diagram shows the differential architecture. Each capacitor cell contains a main capacitor and a difference capacitor, with the effective weight shown above it. Complementary rail drivers connect directly to the enabled decision registers. The first three capacitor stages and the final stage are shown; three dots denote the omitted stages 3–14. The central one-hot selector enables one P/N register pair at a time, and the terminal seventeenth comparison contributes to the result without switching another capacitor. Initialization loads the programmed starting state into all driver registers and seeds the selector with stage 0 active. Subsequent logic-clock edges shift this one-hot enable through the chain. Complementary comparator outputs feed the decision registers, and a dedicated clock input controls evaluation. Weighted decoding is external to the prototype ADC macro.

::: {#fig-adc-timing src="../images/report/adc_timing"}
Initialization, sampling, comparator, and logic timing waveforms.
:::

The initialization timing illustrates the synchronous control sequence shown above.

#### SR-latch and SAR-logic propagation delay

[Section explaining SR-latch and SAR-logic propagation delay.]

#### Per-channel programmability and clock synchronization

[Section explaining per-channel programmability and clock synchronization.]

#### Logic contribution to ADC power

[Section explaining logic contribution to ADC power.]

### System power consumption

#### Block-level and full-ADC simulation comparison

[Section explaining block-level and full-ADC simulation comparison.]

#### Energy per conversion versus sampling rate

[Section explaining energy per conversion versus sampling rate.]
