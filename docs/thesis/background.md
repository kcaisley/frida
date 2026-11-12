# Background and motivation {#sec-background}

CMOS sensors have fundamentally changed scientific imaging since their introduction in the early 1990s.
Detector dynamic range has substantially improved over this period, spanning single-electron signals and incident fluence rates above 10^12^ primary electrons/cm²/s [@philipp2022].
In contrast, the specification of frame rate has seen comparatively less advancement, as increasing it requires not just better pixel design but also system-level optimization of the readout circuits.
As increasingly sophisticated imaging modalities have been introduced, the challenge of faster readout has come to the foreground as a major limitation of current-generation microelectronics.

This chapter makes the case for the converter studied in this thesis in three steps.
@sec-frame-rate explains why frame rate matters, and @sec-counting why a fast imager needs multi-bit conversion in or near every pixel rather than single-bit counting.
@sec-need-adc turns the resulting array-level requirements into a budget for a single analog-to-digital converter (ADC).
@sec-survey then compares that budget with two decades of published converters across architectures and process nodes, and @sec-position states where this work aims to sit.

## Frame rate is time resolution {#sec-frame-rate}

Chips built for electron microscopy have focused on sensitivity and dynamic range, but much less on frame rate.
Frame rate is time resolution: there are dynamic processes, mostly very small, which are interesting to record over time.
Key examples are in-situ and liquid-phase electron microscopy, including the nucleation and growth of nanoparticles, battery systems, catalysis, biomolecules, and organic systems.

A number of recent detector applications now demand continuous frame acquisition above 1000 fps, while maintaining enough sensitivity and dynamic range to resolve individual particles.
In four-dimensional scanning transmission electron microscopy (4D-STEM), diffraction images record the angular distribution of scattered electrons at each probe position; rapid acquisition allows a complete spatial scan to be collected in a short time [@ercius2024].
In X-ray imaging under the high photon fluence of continuous-wave free-electron lasers and diffraction-limited synchrotrons, short integration windows limit the number of photons accumulated per frame, reducing the overlap of photon signals and the risk of sensor saturation [@cordia2024].
Stroboscopic electron microscopy collects images at successive pump–probe delays to reconstruct a time-resolved sequence, effectively making a movie of repeatable dynamics; faster detector readout supports efficient collection of these image series [@lau2020].

## Counting and integrating pixels {#sec-counting}

A unifying factor of detectors for high-energy particles is that they have a high signal-to-noise ratio, and very often little information of interest is encoded in the energy domain.
We are therefore typically more concerned with counting accurately: good detective quantum efficiency and good linearity.
There are two ways to do so.

Higher-speed in-pixel counting, or column-adjacent electron counting, has captured the larger portion of the engineering mindshare and market share.
It simplifies the operation of each pixel and reduces the design space to that of a single-bit quantizer, a discriminator.
Counting is especially beneficial where hits must be read out with fine spatial resolution (small and many pixels) and the hit rate is sparse.
The alternative integrates the charge of many particles in each pixel during a frame and digitizes the total with a multi-bit ADC, while still resolving a single particle.
The comparison is similar to multi-bit modulation in wired and wireless data links, which offers a data-rate improvement over single-bit signalling at the expense of design complexity, since the bit-error-rate requirement must then be met by managing noise and distortion in both the time and amplitude domains.

The hit rate a pixel sees is the incident fluence multiplied by the pixel area.
@fig-hit-rate places present-day sources on that scale: transmission electron microscopes deliver up to about 10^8^ electrons/mm²/s, and fourth-generation synchrotrons and continuous-wave free-electron lasers 10^10^–10^11^ photons/mm²/s.
At 10^10^ particles/mm²/s, a 100 µm pixel is hit 10^8^ times per second.

::: {#fig-hit-rate plot="hit_rate_vs_fluence"}
Per-pixel hit rate against incident particle fluence for pixel pitches from 100 µm down to 10 µm. The markers along the bottom place the fluence of present photon sources (squares) and electron microscopes (circles).
:::

A counting pixel must finish processing one hit before it can register the next.
Modelling the arrivals as a Poisson process with mean rate $\mu$ and the front end as non-paralyzable with dead time $t_\mathrm{d}$, the probability that a hit overlaps a previous one is $1 - e^{-\mu t_\mathrm{d}}$ [@ballabriga2021].
Accepting a fraction $f$ of overlapping hits limits the rate to
$$
\mu_\mathrm{max} = \frac{-\ln(1-f)}{t_\mathrm{d}},
$$ {#eq-pileup}
about 4.2 Mcps for a 25 ns dead time at $f = 10\,\%$.
An integrating pixel has no dead time between hits; its limit is the number of levels its ADC can distinguish in one frame time $T_\mathrm{frame}$,
$$
\mu_\mathrm{max} = \frac{2^N - 1}{T_\mathrm{frame}}
$$ {#eq-integrating}
for an $N$-bit conversion with single-particle resolution.

::: {#fig-counting-rate plot="counting_rate_limits"}
The highest hit rate per pixel that can be counted. Left: an integrating pixel, limited by its ADC's levels per frame (@eq-integrating). Right: a counting pixel, limited by pile-up within its front-end dead time (@eq-pileup), with the rates reported for SPHIRD [@grybos2023], KITE [@zambon2023], Medipix4 [@sriskaran2024], Timepix4 [@llopart2022], IBEX [@bochenek2018], PILATUS3 [@loeliger2012], EIGER [@dinapoli2010] and Medipix3 [@ballabriga2011].
:::

@fig-counting-rate compares the two.
The fastest counting chips reach a few tens of Mcps per pixel.
A 12-bit integrating pixel read at 100,000 frames per second (a 10 µs frame) can count up to 4 × 10^8^ hits per second, an order of magnitude beyond them, and still resolve every particle.
These problems are therefore best solved by integrating-mode sensors, where multiple particles are measured per frame, but still with single-particle resolution.
With the generous signal-to-noise ratio of direct electron detectors, single-electron resolution has been readily achieved, and so the next question becomes how quickly and how compactly the pixels can be read out.

::: aside
If we target single-electron sensitivity, the ADC can act as a multi-bit electron counter: rather than reading out full ADC resolution, it can simply report the number of electrons.
Sub-electron resolution remains useful for position localization.
:::

Frame-based radiation detectors with integrating front ends are especially well suited to applications like electron microscopy and X-ray imaging, where hit rates are high and spatial resolution should be maximized with simple pixels.
The cost is moved from the pixel to the converter: every pixel needs a multi-bit conversion in every frame.

## The need for compact ADCs {#sec-need-adc}

The next frontier of high-performance imaging involves systems pushing above the boundary of 100,000 frames per second.
Achieving this requires overcoming a bottleneck: the ADCs must digitize large pixel arrays within the limitations of power dissipation and silicon area.
For example, a 1 Mpixel array of 1024 × 1024 pixels operating at 100,000 frames per second produces over 100 billion pixel samples per second.
Digitizing this stream requires approximately 10,000 ADC channels operating at 10 MS/s.
Assuming 1 mW per channel, the ADCs alone dissipate over 10 W.

The sampling time of each ADC must be slow enough to achieve the resolution needed for each pixel, but the aggregate rate must be fast enough to read out the entire pixel array within a frame.
This project therefore pursues a single-reticle array larger than 1 Mpixel with a continuous frame rate above 100,000 fps.
To meet those array-level goals, the converter fabric must deliver an aggregate throughput above 1000 Gbps while staying within a 1 W/cm² power-density budget at the bottom of the chip.

::: aside
Power consumption should not simply be blindly reduced: it is a budget for performance.
:::

Area matters as much as power.
CMOS image sensors are large arrays of repeated structures, so small area improvements scale across the whole array, and a converter that does not fit the pixel or column pitch cannot be distributed through the readout at all.
As an example, consider a readout chip serving a 64 × 512 region of 60 × 60 µm pixels, read in four-fold columns: 256 effective columns, each with its own ADC, arranged 16 × 16.
Each ADC may then span four pixel rows, a width of 4 × 60 = 240 µm, and if square an area of 57,600 µm² (0.0576 mm²), before any of that area is given to the pixel front ends, references, or data transmission.

The extremity of these requirements is best judged with a performance heuristic, the Walden figure of merit [@walden1999]
$$
\mathrm{FoM_W} = \frac{P}{f_\mathrm{s} \cdot 2^\mathrm{ENOB}},
$$ {#eq-walden}
the energy spent per effective conversion step at power $P$, sampling rate $f_\mathrm{s}$, and effective number of bits ENOB.
The converter this thesis develops is designed for a nominal 12-bit output (11 effective bits) at 10 MS/s within 100 µW and a 60 × 60 µm footprint, an $\mathrm{FoM_W}$ of 4.9 fJ per conversion step.

## Review of ADC architectures and process nodes {#sec-survey}

The survey of ADC performance at the ISSCC and VLSI symposia maintained by Murmann [@murmann_survey] provides the efficiency context for this target.
To compare like with like, the designs here are restricted to those occupying at most 0.25 mm², resolving at least 6 effective bits at a Nyquist rate of at least 0.1 MS/s, and spending at most 1 nJ per conversion: 270 designs from 2002 to 2026, 89 of them SAR converters.
Each design is coloured by its process node and marked by its architecture; in the web edition, hovering over a point shows its paper, and clicking it links to the paper.

::: {#fig-survey-rate plot="survey_enob_vs_rate"}
Effective resolution against Nyquist conversion rate for the selected survey designs [@murmann_survey], coloured by process node and marked by architecture. The large marker is this work's design goal.
:::

@fig-survey-rate shows the familiar division of the resolution–speed plane.
Delta-sigma converters hold the high-resolution corner, pipelines and time-interleaved designs the high-speed one, and SAR and pipelined-SAR converters cover the middle, where the design goal lies.
In general, arbitrarily high resolution is achievable up to the noise floor at the maximum single-stage speed, if one is willing to spend more power on pipelining: pipelining is a way to improve resolution at a fixed speed by spending more power.

::: {#fig-survey-energy plot="survey_enob_vs_energy"}
Effective resolution against energy per Nyquist conversion, $P / f_\mathrm{s,nyq}$, for the same designs. The large marker is this work's design goal.
:::

The energy per conversion in @fig-survey-energy shows the cost of each additional bit.
The trade-off between performance (noise, linearity, speed) and cost (power, area) in a SAR ADC is tricky, because each block has a different relationship between them.
Digital power grows linearly with resolution, while analog power grows exponentially, since mismatch and noise must each be halved for every added bit.
At high resolution the comparator and capacitive DAC therefore dominate, while at low resolution the analog blocks scale down and the digital logic dominates.

::: {#fig-survey-area plot="survey_fomw_vs_area"}
Walden figure of merit (@eq-walden) against reported converter area for the same designs. The large marker is this work's design goal.
:::

The conventional comparison stops at energy.
For a detector it cannot: an efficient ADC that occupies too much silicon cannot be distributed throughout a tightly constrained readout, so @fig-survey-area adds area to the comparison.
The two axes pull apart.
Of the 270 designs only 34 occupy 0.01 mm² or less, and 24 of these are SAR or pipelined-SAR converters; the 12 that also reach 10 effective bits are all SAR-based, and all in 40 nm or finer processes.
Only two designs improve on the design goal in both figure of merit and area.

Process node sets much of this picture.
Across the selected designs, the median figure of merit falls from 86 fJ per step in 90 nm and older processes to 41 fJ in 55–65 nm and about 18–20 fJ in 45 nm and below, while the median area shrinks from 90,200 µm² to 70,000 µm² and 23,650 µm².
Architecture matters as much: the median SAR converter occupies 30,000 µm² at 21 fJ per step and the median pipelined SAR 40,000 µm² at 8.5 fJ, against 85,000 µm² for continuous-time delta-sigma and 115,000 µm² for pipelined converters.
Detector readout, however, is rarely built in the newest node: the designs it relies on are fabricated in mature 65–180 nm processes that offer radiation tolerance, multi-project access, and established sensor integration.
The same high-level converter concept can be carried between technologies; the point is not push-button portability but making the design intent easier to preserve and re-target.
This motivates the comparison across 180, 130, 65 and 28 nm processes developed in the following chapters.

## Position of this work {#sec-position}

We address this requirement with a differential successive-approximation-register (SAR) ADC, prototyped in 65 nm but with an architecture portable between process nodes.
It is designed for a nominal 12-bit output at up to 10 MS/s in a channel of about 60 × 60 µm.
Its central contribution is the combination of a compact capacitor implementation, redundant conversion, and digital control suitable for dense tiling.
The area comparison of @fig-survey-area therefore complements the conventional Walden metric and identifies the compact, efficient region this work seeks to occupy; no published design in a 55–65 nm process reaches it.

The design builds on earlier detector-readout work from the research group.
An earlier 8-bit SAR ADC demonstrated low-power conversion at 10 MS/s in a compact channel, but offered lower resolution [@kishishita2013].
The CoRDIA ADC demonstrated more than 10 effective bits at 2.5 MS/s with approximately 24 µW consumption, but occupied 80 × 330 µm [@cordia2024].
The DCD current-mode ADC established a successful multichannel readout approach for DEPFET detectors, with 8-bit conversion [@peric2010].
These designs provide relevant precedents, while leaving scope for the combination of resolution, throughput, power, and channel footprint pursued here.

::: {.openitems}
**Open items in this draft**

- The design goal's power differs between sources: 100 µW (`readme.md`, `phys/adc_survey.py`, used here), 200 µW (the readme's comparison table), 500 µW (`docs/report.md`), and "below 1 mW per channel" (`docs/report.md`). The survey marker and @eq-walden follow `phys/adc_survey.py`.
- The CoRDIA ADC is described as 8-bit at 10 MS/s, as 10-bit (ENOB 8.8) at 30 µW, and as more than 10 effective bits at about 24 µW in different notes; the text above follows `docs/report.md`.
- The beam-source fluences in @fig-hit-rate need references.
- The worked readout-chip example in @sec-need-adc should name the system it is taken from, if that is public.
:::
