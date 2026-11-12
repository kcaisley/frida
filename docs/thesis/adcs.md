# Analog-to-digital converters {#sec-adcs}

The previous chapter ended with a converter that must be repeated thousands of times in a readout chip: it must resolve every particle in a frame, keep up with the frame rate, and fit within an area and power set by the pixel pitch and the chip's thermal limit.
This thesis is about building that converter as small as possible.
This chapter breaks the field of analog-to-digital converters down into the metrics that compare them (@sec-metrics) and the architectures that implement them (@sec-architectures), uses two decades of published designs to show why the successive-approximation (SAR) architecture is the one to target (@sec-survey, @sec-why-sar), and then states the specification this work designs for (@sec-specs).

## Metrics {#sec-metrics}

An $N$-bit converter divides its full-scale range into $2^N$ levels of one least-significant bit (LSB) each.
Even an ideal converter makes an error of up to half an LSB, which for a busy input behaves as noise of $\mathrm{LSB}/\sqrt{12}$ RMS.
A real converter adds thermal noise, mismatch and distortion, and its effective number of bits follows from the measured signal-to-noise-and-distortion ratio of a full-scale sine wave,
$$
\mathrm{ENOB} = \frac{\mathrm{SNDR} - 1.76\,\mathrm{dB}}{6.02\,\mathrm{dB}}.
$$ {#eq-enob}

There is a reason dynamic range is not the most important specification to quote for a data converter: dynamic range is relatively easy to increase, since an input out of range can simply be amplified to fit. What doesn't come cheaply is the LSB.

Resolution comes at a price in power and speed.
The Walden figure of merit [@walden1999]
$$
\mathrm{FoM_W} = \frac{P}{f_\mathrm{s} \cdot 2^\mathrm{ENOB}}
$$ {#eq-walden}
expresses that price as the energy spent per effective conversion step at power $P$ and sampling rate $f_\mathrm{s}$.
It is the conventional way to compare converters across resolutions and speeds.

For a detector it is not enough.
A converter that repeats thousands of times is also judged by its area $A$, and by the sampling-rate density $f_\mathrm{s} / A$: how much conversion rate each square micrometre of silicon delivers.
Throughout this thesis area is treated as a first-class metric beside energy, and measured from the laid-out converter rather than estimated from its transistors.

## Architectures {#sec-architectures}

Every converter compares its input against references; the architectures differ in how many comparisons they make at once, how many they make in sequence, and what they need besides the comparator to make them.
@tbl-architectures summarizes the main families.

: The main ADC architectures for an $N$-bit conversion: comparator decisions made per sample, the clock cycles they take, and what dominates their area. {#tbl-architectures}

| Architecture | Decisions per sample | Cycles per sample | Dominant area |
|:--|:--|:--|:--|
| Flash | $2^N - 1$ in parallel | 1 | comparator bank, reference ladder |
| Single-slope (ramp) | 1, repeated | up to $2^N$ | counter, shared ramp generator |
| SAR | 1, repeated | $N$ | capacitive DAC |
| Pipeline | a few per stage | 1 (latency $N$ stages) | residue amplifiers |
| Pipelined SAR | SAR stages | a few | DAC, one residue amplifier |
| Delta-sigma | 1 per oversampled cycle | oversampling ratio | loop filter, decimation filter |
| Time-based (VCO) | counted phase | oversampled | oscillators, counters |

A flash converter compares the input against all $2^N - 1$ thresholds at once.
It is the fastest architecture, but its comparators, and their area and power, grow exponentially with resolution, limiting it to about six to eight bits.

A single-slope converter compares the input against a ramp and counts clock cycles until they cross.
Its per-channel circuit is one comparator and a counter, which is why it dominates the column readout of commercial image sensors.
It needs up to $2^N$ clock cycles per conversion: a 12-bit conversion at 10 MS/s would need a 41 GHz counter clock.

A SAR converter performs a binary search with one comparator, setting one bit per cycle by switching a capacitive digital-to-analog converter (CDAC) that holds the sampled input.
It needs $N$ cycles per conversion, has no static bias current in its core, and consists mostly of switches, capacitors and logic, which improve with each process node [@murmann2016].

A pipeline converter resolves a few bits per stage and amplifies the residue to the next stage, completing one conversion per clock with a latency of several stages.
In general, arbitrarily high resolution is achievable up to the noise floor at the maximum single-stage speed, if one is willing to spend more power: pipelining is a way to improve resolution at a fixed speed by spending more power.
Its residue amplifiers bring static power and area.
The pipelined SAR combines the two, with SAR stages joined by a single residue amplifier.

A delta-sigma converter samples far above the signal bandwidth with a coarse quantizer in a feedback loop, shaping its quantization noise out of band and filtering it away digitally.
It reaches the highest resolutions, but needs many cycles per output sample and a continuous input, and so suits a single continuous signal rather than a sequence of multiplexed pixels.
Time-based converters quantize in time or phase rather than voltage, with oscillators and counters that scale well with process, but at modest resolution.

## Survey {#sec-survey}

The survey of ADC performance at the ISSCC and VLSI symposia maintained by Murmann [@murmann_survey] places these architectures side by side.
To compare like with like, the designs here are restricted to those occupying at most 0.25 mm², resolving at least 6 effective bits at a Nyquist rate of at least 0.1 MS/s, and spending at most 1 nJ per conversion: 270 designs from 2002 to 2026, 89 of them SAR converters.
Each design is coloured by its process node and marked by its architecture; in the web edition, hovering over a point shows its paper, and clicking it links to the paper.

::: {#fig-survey-rate plot="survey_enob_vs_rate"}
Effective resolution against Nyquist conversion rate for the selected survey designs [@murmann_survey], coloured by process node and marked by architecture. The large marker is this work's design goal.
:::

@fig-survey-rate shows the familiar division of the resolution–speed plane.
Delta-sigma converters hold the high-resolution corner, pipelines and time-interleaved designs the high-speed one, and SAR and pipelined-SAR converters cover the middle, where the design goal lies.

::: {#fig-survey-energy plot="survey_enob_vs_energy"}
Effective resolution against energy per Nyquist conversion, $P / f_\mathrm{s,nyq}$, for the same designs. The large marker is this work's design goal.
:::

The energy per conversion in @fig-survey-energy shows the cost of each additional bit.
Digital power grows linearly with resolution, while analog power grows exponentially, since mismatch and noise must each be halved for every added bit.
At high resolution the comparator and capacitive DAC therefore dominate, while at low resolution the analog blocks scale down and the digital logic dominates.

::: {#fig-survey-area plot="survey_fomw_vs_area"}
Walden figure of merit (@eq-walden) against reported converter area for the same designs. The large marker is this work's design goal.
:::

The conventional comparison stops at energy; @fig-survey-area adds area, and the two axes pull apart.
Of the 270 designs only 34 occupy 0.01 mm² or less, and 24 of these are SAR or pipelined-SAR converters; the 12 that also reach 10 effective bits are all SAR-based, and all in 40 nm or finer processes.
Only two designs improve on the design goal in both figure of merit and area.

Process node sets much of this picture.
Across the selected designs, the median figure of merit falls from 86 fJ per step in 90 nm and older processes to 41 fJ in 55–65 nm and about 18–20 fJ in 45 nm and below, while the median area shrinks from 90,200 µm² to 70,000 µm² and 23,650 µm².
Architecture matters as much: the median SAR converter occupies 30,000 µm² at 21 fJ per step and the median pipelined SAR 40,000 µm² at 8.5 fJ, against 85,000 µm² for continuous-time delta-sigma and 115,000 µm² for pipelined converters.

## Why SAR {#sec-why-sar}

The survey and the application point the same way.
A SAR converter reaches 10–12 effective bits at 1–100 MS/s, the region the application needs; it is the most compact architecture at that resolution; its energy is spent dynamically, so it scales with the conversion rate and consumes little between conversions; and each conversion is independent of the last, so one converter can serve a column of multiplexed pixels.
Its circuits are mostly switches, capacitors and logic, which shrink with the process, and a design can be carried between technologies.

What remains is to make it small.
The trade-off between performance (noise, linearity, speed) and cost (power, area) in a SAR ADC is tricky, because each block has a different relationship between them.
The capacitive DAC's total capacitance often dominates the area and is a large part of the power: without noise shaping or cancellation, kT/C sampling noise sets a lower limit on the converter's error through the total capacitance, but a conventional CDAC scaled down by capacitor size alone suffers severe mismatch in its smallest capacitors.
The sampling switch, comparator and logic have their own trade-offs between noise, speed, energy and area.
Finding the smallest converter is therefore an optimization across all four blocks at once, and across process nodes; the following chapters develop it.

## Specification {#sec-specs}

@tbl-specs collects the specification, each line derived from the application in @sec-applications.

: Specification of the converter developed in this work. {#tbl-specs}

| Quantity | Target | Derived from |
|:--|:--|:--|
| Resolution | 12 bit nominal, 11 ENOB | counting every particle up to thousands per frame (@eq-integrating) |
| Conversion rate | 10 MS/s | 1 Mpixel at 100,000 frames per second over about 10,000 converters (@sec-budgets) |
| Area | ≤ 3600 µm² (60 × 60 µm) | one converter per pixel pitch, tiled in the column region (@sec-placement) |
| Power | ≤ 100 µW | 10,000 converters within about 1 W (@sec-budgets) |
| Walden FoM | ≤ 4.9 fJ/step | the three lines above (@eq-walden) |
| Sampling-rate density | ≥ 2.8 kS/s/µm² | rate over area |
| Process | 65 nm prototype; 180, 130, 65 and 28 nm studied | mature nodes used for detector readout |

The converter this thesis develops is a differential SAR ADC, prototyped in 65 nm but with an architecture portable between process nodes.
Its central contribution is the combination of a compact capacitor implementation, redundant conversion, and digital control suitable for dense tiling; no published design in a 55–65 nm process reaches the region of @fig-survey-area it aims for.

It builds on earlier detector-readout work from the research group.
An earlier 8-bit SAR ADC demonstrated low-power conversion at 10 MS/s in a compact channel, but offered lower resolution [@kishishita2013].
The CoRDIA ADC demonstrated more than 10 effective bits at 2.5 MS/s with approximately 24 µW consumption, but occupied 80 × 330 µm [@cordia2024].
The DCD current-mode ADC established a successful multichannel readout approach for DEPFET detectors, with 8-bit conversion [@peric2010].
These designs provide relevant precedents, while leaving scope for the combination of resolution, throughput, power and channel footprint pursued here.

::: {.openitems}
Open items in this draft:

- The design goal's power differs between sources: 100 µW (`readme.md`, `phys/adc_survey.py`, used here), 200 µW (the readme's comparison table), 500 µW (`docs/report.md`), and "below 1 mW per channel" (`docs/report.md`). The readme's "above 5 ksps/µm²" also differs from the 2.8 kS/s/µm² of 10 MS/s in 60 × 60 µm.
- The CoRDIA ADC is described as 8-bit at 10 MS/s, as 10-bit (ENOB 8.8) at 30 µW, and as more than 10 effective bits at about 24 µW in different notes; the text above follows `docs/report.md`.
- The beam-source fluences in @fig-hit-rate need references, as do the bump-bond pitches and sensor thicknesses in @sec-arrangements.
- The area example in @sec-budgets should name the system it is taken from, if that is public.
:::
