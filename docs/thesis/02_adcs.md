# Analog-to-digital converters {#sec-adcs}

::: todo

- Paragraph introducing the chapter: the field of ADCs, the architectures, the survey that points to SAR, and the specification derived from @sec-applications.
:::

## Metrics {#sec-metrics}

### Quantization, noise, and effective number of bits

::: todo

- Section explaining quantization noise, SNDR and ENOB.
:::

With the quantization error uniform within $\pm\mathrm{LSB}/2$ and independent of the input, an $N$-bit quantizer of differential full-scale span $V_\mathrm{FS}$, $\mathrm{LSB} = V_\mathrm{FS}/2^N$, adds the noise power [@pelgrom2022, p. 433; @razavi2025, p. 239]
$$
\sigma_\mathrm{q}^2 = \frac{\mathrm{LSB}^2}{12} = \left(\frac{V_\mathrm{FS}}{2^N\sqrt{12}}\right)^2,
$$ {#eq-quantization}
and a full-scale sine over it reaches [@pelgrom2022, p. 436; @razavi2025, p. 240]
$$
\mathrm{SNR} = 6.02\,N + 1.76\,\mathrm{dB}.
$$ {#eq-snr-ideal}
The effective number of bits follows from the signal-to-noise-and-distortion ratio of a full-scale sine wave [@walden1999; @pelgrom2022, p. 439; @razavi2025, p. 248]:
$$
\mathrm{ENOB} = \frac{\mathrm{SNDR} - 1.76\,\mathrm{dB}}{6.02\,\mathrm{dB}}.
$$ {#eq-enob}
Static linearity is read on the input axis, from the input $V_j$ at which the output steps to code $j$ [@razavi2025, pp. 242--244]:
$$
\mathrm{DNL}_j = V_j - V_{j-1} - \mathrm{LSB}, \qquad \mathrm{INL}_j = V_j - j\,\mathrm{LSB}.
$$ {#eq-dnl-inl}

For ADCs, it doesn't make much sense to specify the dynamic range often, as an input signal that is out of range can simply be amplified to fit within the full-scale input range.
(This amplification has some linearity, distortion, and noise penalty of course.)
There is a reason dynamic range is not the most important spec to quote for a data converter, and that's because dynamic range is relatively easy to increase.
What doesn't come cheaply is LSB.

### Energy, area, and figures of merit

Understanding the extremity of our design requirements can best be done with a performance heuristic, the Walden figure of merit [@walden1999], in the inverted form the survey uses, with $f_\mathrm{s}$ the Nyquist rate [@pelgrom2022, p. 461]:
$$
\mathrm{FoM_W} = \frac{P}{f_\mathrm{s} \cdot 2^\mathrm{ENOB}}.
$$ {#eq-walden}

The Schreier figure of merit, used beside it in the survey for noise-limited designs [@murmann_survey; @pelgrom2022, p. 459], is
$$
\mathrm{FoM_S} = \mathrm{SNDR} + 10 \log_{10}\frac{f_\mathrm{s}/2}{P}.
$$ {#eq-schreier}
Thermal noise bounds the power of any converter at a given bandwidth $\mathrm{BW}$ and signal-to-noise ratio [@pelgrom2022, p. 458]:
$$
P \geq 8kT \cdot \mathrm{BW} \cdot \mathrm{SNR}.
$$ {#eq-thermal-bound}

::: todo

- Section on area and sampling-rate density as metrics beside energy.
:::

## Architectures {#sec-architectures}

::: todo

- Section introducing the basic ADC architectures: flash, single-slope, SAR, pipeline, pipelined SAR, delta-sigma and time-based, with a block diagram of each.
:::

::: {#fig-architectures placeholder="Block diagrams of the basic ADC architectures: flash, single-slope, SAR, pipeline, delta-sigma."}
The basic ADC architectures.
:::

In general, arbitrarily high resolution is achievable up to the noise floor at the maximum single-stage speed, if you are willing to spend more power via pipelines.
Put differently, pipelining is a way to improve resolution, at a fixed speed, by spending more power.

::: todo

- Table comparing the architectures: decisions per sample, cycles per sample, and what dominates their area.
:::

## Survey {#sec-survey}

A survey of state-of-the-art ADC performance over the past two decades [@murmann_survey] provides the efficiency context by comparing effective resolution with conversion energy and the Walden figure of merit with silicon area.
The highlighted marker denotes our design target.

::: {#fig-survey-rate plot="survey_enob_vs_rate"}
Effective resolution against Nyquist conversion rate [@murmann_survey], coloured by process node and marked by architecture, with the design goal.
:::

::: {#fig-survey-energy plot="survey_enob_vs_energy"}
Effective resolution against energy per Nyquist conversion, with the design goal.
:::

::: {#fig-survey-area plot="survey_fomw_vs_area"}
Walden figure of merit against reported ADC area, with the design goal.
:::

::: todo

- Section reading the survey by architecture and by process node.
:::

## Why SAR {#sec-why-sar}

::: todo

- Section on why the SAR architecture fits the application.
:::

The trade-off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a different relationship between these.
Digital power is linear with N, while analog power is exponential with N (due to mismatch and noise).
So at high resolution the analog comparator or DAC dominates, but at low resolution analog really scales down, so digital dominates.

CDAC total capacitance often dominates area usage and is a large portion of the power budget.
Assuming no noise shaping or cancellation, kT/C sampling noise provides the theoretical limit on ADC error, and is determined by $C_\mathrm{tot}$.
However, a conventional CDAC implemented with capacitor scaling alone exhibits severe mismatch in its LSB capacitors as its $C_\mathrm{tot}$ is shrunk.

## Earlier detector ADCs {#sec-earlier}

The design builds on earlier detector-readout work from the research group.

@tbl-earlier lists the achieved specifications of four of them, from their publications, beside the design goal of this work.
The Walden figure of merit @eq-walden and the sampling-rate density $f_\mathrm{s}/A$ are computed from the listed values.

: Earlier detector ADCs of the research group and the design goal of this work. Area is the converter's own layout as published; DCDB's includes its transimpedance input stage. {#tbl-earlier}

| | DCD1 [@peric2010] | DCDB [@knopf2011] | 8-bit SAR [@kishishita2013] | CoRDIA ADC [@cordia2024] | This work (goal) |
|:--|:--|:--|:--|:--|:--|
| Architecture | current-mode cyclic | current-mode cyclic | SAR | SAR | SAR |
| Process | 180 nm | 180 nm | 65 nm | 65 nm | 65 nm |
| Resolution | 8 bit | 8 bit (about 6 ENOB measured) | 8 bit | 11 bit (> 10 ENOB) | 12 bit (11 ENOB) |
| Sampling rate | 3.125 MS/s | 3.125 MS/s measured (10 MS/s target) | 10 MS/s | 2.5 MS/s | 10 MS/s |
| Power | 0.96 mW | 4 mW per channel | 38 µW (simulated) | about 24 µW | 100 µW |
| Layout | 40 × 55 µm | 200 × 180 µm | 40 × 70 µm | 80 × 330 µm | 60 × 60 µm |
| Area | 2200 µm² | 36,000 µm² | 2800 µm² | 26,400 µm² | 3600 µm² |
| Walden FoM | 1.2 pJ/step (8 bit) | 20 pJ/step (6 ENOB) | 15 fJ/step (8 bit) | 9.4 fJ/step (10 ENOB) | 4.9 fJ/step |
| $f_\mathrm{s}/A$ | 1.4 kS/s/µm² | 0.087 kS/s/µm² | 3.6 kS/s/µm² | 0.095 kS/s/µm² | 2.8 kS/s/µm² |

::: todo

- Section analyzing the layout area of these converters against the design goal: where each spends its area, and why resolution and area have so far been traded against each other.
:::

::: {#fig-earlier placeholder="Published layouts of the group's earlier ADCs: the DCD channel floorplan (Peric 2010, Fig. 3), the DCDB layout (Knopf 2011, Fig. 3), the 8-bit SAR channel (Kishishita 2013, Fig. 3), and the CoRDIA ADC chips (Marras 2024, Fig. 2), each redrawn or reproduced with permission."}
Earlier detector ADCs from the research group.
:::

## Specification {#sec-specs}

::: todo

- Section deriving each specification from @sec-applications.
:::

: The design goal. {#tbl-specs}

| Quantity | Target |
|:--|:--|
| Resolution | 12 bit (design), 11 ENOB |
| Sampling rate | 10 MS/s |
| Power | 100 µW |
| Area | 60 × 60 µm (3600 µm²) |
| Process | 65 nm |

We address this requirement by proposing a differential successive-approximation-register (SAR) ADC, prototyped in 65 nm but with an architecture portable between process nodes.
Its central contribution is the combination of a compact capacitor implementation, redundant conversion, and digital control suitable for dense tiling.
The area comparison therefore complements the conventional Walden metric and identifies the compact, efficient region that this work seeks to occupy.

The contributions of this thesis are:

- Background explaining how to derive a data converter specific to a radiation imaging system (pen-and-paper math).
- A set of behavioral models and SPICE simulations to map out the optimization space for SAR ADCs which meet the needs of compact, high-frame-rate image sensors.
- A framework and pipeline for translating that into a fabricatable GDS layout, using mostly open-source tools, across a range of PDKs.
- Two silicon prototypes built with the simulations and pipeline above.
- A hardware DAQ system (COB PCB carrier plus FPGA system, plus control code), with scans to measure all ADC parameters.
- Finally, an analysis of measurements from the first generation.

::: {.openitems}
Open items in this draft:

- The design goal's power differs between sources: 100 µW (`readme.md`, `phys/adc_survey.py`, used here), 200 µW (the readme's comparison table), 500 µW and "below 1 mW per channel" (`docs/report.md`).
- The beam-source fluences in @fig-hit-rate need references.
:::
