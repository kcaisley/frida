# Applications {#sec-applications}

CMOS sensors have fundamentally changed scientific imaging since their introduction in the early 1990s.
Detector dynamic range has substantially improved over this period, spanning single-electron signals and incident fluence rates above 10^12^ primary electrons/cm²/s [@philipp2022].
In contrast, the specification of frame rate has seen comparatively less advancement, as increasing it requires not just better pixel design optimization but also system-level optimization of readout circuits.
However, as increasingly sophisticated imaging modalities have been introduced, the challenge of faster readout design has come to the foreground as a major limitation in current generation microelectronics hardware.

[Paragraph outlining the chapter: from the physics to the resolution and frame rate, from the packaging to the area and power per converter.]

## Frame rate is time resolution {#sec-frame-rate}

What chips built for electron microscopy haven't focused on, though, is frame rate.
Frame rate is time resolution.
There are dynamic processes, mostly very small, which are interesting to record over time.
A key example here is in-situ and liquid-phase electron microscopy, including nucleation and growth of nanoparticles, battery systems, catalysis, biomolecules, and organic systems.

A number of recent detector applications now demand continuous frame acquisition above 1000 fps, while maintaining enough sensitivity and dynamic range to resolve individual particles.
In four-dimensional scanning transmission electron microscopy (4D-STEM), diffraction images record the angular distribution of scattered electrons at each probe position; rapid acquisition allows a complete spatial scan to be collected in a short time [@ercius2024].
In X-ray imaging under the high photon fluence of continuous-wave free-electron lasers and diffraction-limited synchrotrons, short integration windows limit the number of photons accumulated per frame, reducing overlap of photon signals and the risk of sensor saturation [@cordia2024].
Stroboscopic electron microscopy collects images at successive pump–probe delays to reconstruct a time-resolved sequence, effectively making a movie of repeatable dynamics.
Faster detector readout supports efficient collection of these image series [@lau2020].

::: {#fig-applications image="app_tem app_4dstem app_xray app_stroboscopic" cols="2"}
Imaging applications: (a) transmission electron microscopy; (b) 4D-STEM; (c) X-ray diffraction at a synchrotron or free-electron laser; (d) in-situ and stroboscopic electron microscopy.
:::

[Section explaining each imaging mode and the frame rate, dose rate and pixel pitch it asks of the detector.]

## Counting and integrating pixels {#sec-counting}

A unifying factor of detectors of high-energy particles is that they have a high spectral SNR, and very often have little information of interest encoded in that domain.
And so we are typically more concerned with just counting accurately (good DQE and good linearity).

Higher speed in-pixel counting, or column adjacent electron counting readout, has grabbed a larger portion of the engineering mindshare (and market share), as it simplifies the operation of each pixel, and reduces the problem design space to that of a single-bit quantization.
These are especially beneficial in instances where particle hit rate should be read out with high resolution requirement (small and many pixels), with very sparse hit rates.
This is similar to how multi-bit quantization in wired and wireless data links offers a data rate improvement over single-bit, at the expense of increased design complexity, due to the need to satisfy BER requirements by considering signal to noise and distortion in both temporal and amplitude domains.

::: {#fig-hit-rate plot="hit_rate_vs_fluence"}
Per-pixel hit rate against incident particle fluence for pixel pitches from 100 µm to 10 µm, with the fluence of photon sources (squares) and electron microscopes (circles).
:::

We model particle arrivals as a Poisson process with average rate $\mu$, each hit occupying the front end for a fixed dead time $t_\mathrm{d}$ (non-paralyzable) [@ballabriga2021].
The probability that a hit overlaps with a previous one is $1 - e^{-\mu t_\mathrm{d}}$, and for an allowed overlap fraction $f$
$$
\mu_\mathrm{max} = \frac{-\ln(1-f)}{t_\mathrm{d}}.
$$ {#eq-pileup}
An integrating pixel with an $N$-bit conversion per frame time $T_\mathrm{frame}$ can count up to
$$
\mu_\mathrm{max} = \frac{2^N - 1}{T_\mathrm{frame}}.
$$ {#eq-integrating}

::: {#fig-counting-rate plot="counting_rate_limits"}
Maximum hit rate per pixel. Left: integrating, @eq-integrating. Right: discriminating, @eq-pileup at 10 % pile-up, with SPHIRD [@grybos2023], KITE [@zambon2023], Medipix4 [@sriskaran2024], Timepix4 [@llopart2022], IBEX [@bochenek2018], PILATUS3 [@loeliger2012], EIGER [@dinapoli2010] and Medipix3 [@ballabriga2011].
:::

[Paragraph reading @fig-hit-rate and @fig-counting-rate against each other.]

These problems are best solved by integrating mode sensors, where multiple particles are measured per frame, but still with single electron resolution.
With the generous SNR provided by direct electron detectors, single electron resolution has been readily achieved, and so the next question becomes how quickly and compactly (with low pixel pitch) we can read out these.

If we are targeting single electron sensitivity, can we perhaps build an ADC which acts as a multi-bit quantizer, and which can, rather than reading out full ADC resolution, simply report the number of electrons?
Sub-electron energy resolution is still useful for position localization.

Frame-based radiation detectors with integrating front-ends are especially well-suited for applications like electron microscopy and X-ray imaging, where hit rates are high and spatial resolution should be maximized with simple pixels.

## Sensor and readout arrangements {#sec-arrangements}

[Section introducing the arrangements of sensor and readout: monolithic, sensor and readout chips side by side on one package, and hybrid stacks.]

Monolithic sensors are often very thin and so can't typically absorb 100 % of incident electron energy; therefore there is some variation in the proportion of energy left between particles, even with the same energy.
This is called Landau noise and follows a Landau distribution.

::: {#fig-monolithic image="chip_monolithic"}
A monolithic imager.
:::

::: {#fig-side-by-side image="chip_side_by_side"}
Sensor and readout chips side by side on one package.
:::

We can get higher rate electron counting if we use a hybrid readout configuration to allow in-pixel digital storage.
This can typically operate at a much higher effective hit rate, as the frame versus beam current trade-off is relaxed.
Instead, pile-up (i.e. coincidence) is limited by a single pixel's dead time, with multiple hits able to be read out digitally per frame.
Event-based readout is possible in both hybrid and monolithic architectures, and is exclusively used with counting detection.
The difference is that hit counts aren't digitally buffered for the subsequent frame, but instead are sparsely transmitted out as they occur.

::: {#fig-hybrid image="chip_hybrid"}
A hybrid stack.
:::

Thinner sensors (below 150 µm) will reduce the multiple scattering of keV electrons, so this is often targeted by commercial sensors.
MeV electrons have less multiple scattering, and as they deposit about five times less energy per unit length, a thicker sensor (about 500 µm) is more desirable.

[Section on interconnect: bump bonding, wafer bonding and TSVs, and the pixel pitch they allow.]

Redistribution layers are a post-metallization layer which can be used to remap the spacing of top metal traces, in either 3D or 2D integrations.
In bump bonding, chip and sensor are typically 300 µm and 150 µm thick respectively; with wafer bonding and TSVs, the chip and sensor can be thinned to 20 µm and 100 µm.
Sensors can be made very large, but chips are often limited in size; therefore we have concepts like quad modules.

## Where the converters go {#sec-placement}

ADCs can be placed in-pixel, under-pixel (SOI), under-pixel (hybrid), at the periphery matched to the columns, or at the periphery and redistributed (often off chip).

::: {#fig-column-parallel image="chip_column_parallel"}
A monolithic imager with column-parallel ADCs and serializers.
:::

The sampling time of an ADC must be slow enough to achieve the resolution needed for each pixel, but the aggregate rate must be fast enough to achieve the readout time of the entire pixel array.

The settling time of the row switching and the pixels determines how quickly a row can be read out.
Just reading multiple rows at once, with extra ADCs, is a workaround for this speed limit, but four-fold may be the practical limit.

[Section on pixel-parallel against column-parallel conversion and multiplexing.]

## Budgets {#sec-budgets}

The next frontier of high-performance imaging involves systems pushing above the boundary of 100,000 frames per second.
Achieving this requires overcoming a bottleneck: the analog-to-digital converters (ADCs) must digitize large pixel arrays within the limitations of power dissipation and silicon area.
For example, a 1 Mpixel array comprising 1024 × 1024 pixels and operating at 100,000 frames per second will produce over 100 billion pixel samples per second.
Digitizing this stream would then require approximately 10,000 ADC channels operating at 10 MS/s.
Assuming 1 mW per channel, the ADCs alone dissipate over 10 W.

### Power density

One beautiful interrelation of detectors is that the power dissipation limit is directly derived from spatial noise limitations, because cooling systems add mass that increases multiple scattering.
In a 1 cm² area we have 40,000 pixels with 50 µm pitch; given a total power of 0.6 W/cm², we can spend around 0.6 W / 40,000 = 15 µW per pixel.
What matters is how this power dissipates into heat, which limits the pitch of the pixels.
We don't want to conserve power, we just can't exceed our thermal limits.
Power consumption is a budget for performance!

### Area per converter

CMOS image sensors are large arrays of repeated structures.
Most blocks are roughly square, and exact geometry is less critical than in RF design.
Small area improvements scale across the array.
Area is essential to this argument: an efficient ADC that occupies too much silicon cannot be distributed throughout a tightly constrained detector readout.

[Worked example of the area available per ADC in a column-parallel readout chip.]

### Data off the chip

This project pursues a single-reticle array larger than 1 Mpixel with a continuous frame rate above 100,000 fps.
To meet those array-level goals, the converter fabric must deliver aggregate throughput above 1000 Gbps while staying within a 1 W/cm² chip-bottom power-density budget.

[Section on serial links and their share of the power and area budget.]
