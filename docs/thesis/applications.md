# Applications {#sec-applications}

CMOS sensors have fundamentally changed scientific imaging since their introduction in the early 1990s.
Detector dynamic range has substantially improved over this period, spanning single-electron signals and incident fluence rates above 10^12^ primary electrons/cm²/s [@philipp2022].
In contrast, the specification of frame rate has seen comparatively less advancement, as increasing it requires not just better pixel design but also system-level optimization of the readout circuits.
As increasingly sophisticated imaging modalities have been introduced, the challenge of faster readout has come to the foreground as a major limitation of current-generation microelectronics.

This chapter is the only one about the application, and its job is to set the targets for the electronics that follow.
@sec-frame-rate and @sec-counting derive the resolution and frame rate from the physics: why fast imaging needs a multi-bit conversion of every pixel in every frame.
@sec-arrangements and @sec-placement describe how sensor and readout are built and packaged, and where in that assembly a converter can sit.
@sec-budgets turns both into the area, power and data budgets that every converter must respect.

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
The cost moves from the pixel to the converter: every pixel needs a multi-bit conversion in every frame.

## Sensor and readout arrangements {#sec-arrangements}

Where a converter can be placed, and how much area and power it may take, follows from how the sensor and its readout are built.
There are two arrangements.

In a monolithic sensor, charge is collected in the same CMOS substrate that holds the readout circuits.
Monolithic sensors are often very thin, and so cannot typically absorb all of an incident electron's energy; the proportion of energy deposited then varies between particles even of the same energy, a variation called Landau noise, following a Landau distribution.
Fine pitches are possible because no interconnect is needed between sensor and circuit: monolithic electron cameras reach pixel pitches of 10 µm and below [@bammes2023; @ercius2024].

In a hybrid detector, the sensor is a separate, fully depleted diode array, bonded pixel by pixel to a readout chip of the same pitch [@llopart2022; @philipp2022].
The sensor material and thickness can then be chosen for the particle: silicon for electrons, and silicon or high-Z materials such as CdTe for X-rays.
Thinner sensors (below about 150 µm) reduce the multiple scattering of keV electrons, and so are often targeted by commercial sensors; MeV electrons scatter less and deposit about five times less energy per unit length, so a thicker sensor (about 500 µm) is more desirable there.
A hybrid configuration also allows in-pixel digital storage, so higher-rate counting can be reached: pile-up is limited only by a single pixel's dead time, with multiple hits read out digitally per frame.

The connection between sensor and readout sets the smallest pixel a hybrid can have.
Bump bonds range from indium and fine-pitch solder at about 20 µm pitch to standard solder at about 200 µm.
Wafer bonding and through-silicon vias (TSVs) shorten and thin the assembly: where a bump-bonded chip and sensor are typically 300 µm and 150 µm thick, wafer bonding with TSVs allows them to be thinned to about 20 µm and 100 µm.
Redistribution layers, an extra metal level added after fabrication, remap the spacing of the top-metal pads in either a 2-D or a 3-D assembly.
Sensors can be made very large, but readout chips are limited in size by the reticle, so large detectors tile many chips; TSVs that carry the chip's connections to its back side make that tiling gapless [@cordia2024].

## Where the converters go {#sec-placement}

Within either arrangement, a converter can be placed at four levels: in the pixel, under the pixel in a hybrid or silicon-on-insulator stack, at the periphery matched to the columns, or at the periphery and redistributed, often off-chip.
Each step outward gives the converter more room and makes it serve more pixels.

A pixel-parallel converter gets one pixel's area, the pitch squared, and has to share it with the front end: 3025 µm² in total at a 55 µm pitch, the Timepix pitch [@llopart2022].
It needs only to convert once per frame.
A column-parallel converter sits at the edge of the array and digitizes one row after another; it gains area along the column direction but must convert as many times per frame as the rows it serves.
The sampling time of each ADC must be slow enough to achieve the resolution needed for each pixel, but the aggregate rate must be fast enough to read out the entire pixel array within a frame.

Column-parallel readout has its own speed limit.
The settling time of the row selection and of the pixels themselves determines how quickly a row can be read out; reading several rows at once, with extra ADCs per column, works around that limit, though four-fold may be the practical limit.
Each added converter per column must then fit within the column pitch.

## Budgets {#sec-budgets}

The next frontier of high-performance imaging involves systems pushing above the boundary of 100,000 frames per second.
Achieving this requires overcoming a bottleneck: the ADCs must digitize large pixel arrays within the limitations of power dissipation and silicon area.
For example, a 1 Mpixel array of 1024 × 1024 pixels operating at 100,000 frames per second produces over 100 billion pixel samples per second.
Digitizing this stream requires approximately 10,000 ADC channels operating at 10 MS/s.
Assuming 1 mW per channel, the ADCs alone dissipate over 10 W.

### Power density

Power is limited per unit area, because the heat must be removed where it is generated.
One beautiful interrelation of detectors is that the power dissipation limit derives directly from spatial-resolution limits: cooling systems add mass, and mass increases multiple scattering.
Hybrid pixel readout chips dissipate in the range 0.25–0.6 W/cm² [@ballabriga2011; @sriskaran2024; @llopart2022].
At 0.6 W/cm² and a 50 µm pitch, the 40,000 pixels in each square centimetre can spend about 15 µW each.
We don't want to conserve power for its own sake; we just can't exceed our thermal limits.
Power consumption is a budget for performance.

### Area per converter

Area matters as much as power.
CMOS image sensors are large arrays of repeated structures, so small area improvements scale across the whole array, and an efficient ADC that occupies too much silicon cannot be distributed through a tightly constrained readout at all.
As an example, consider a readout chip serving a 64 × 512 region of 60 × 60 µm pixels, read in four-fold columns: 256 effective columns, each with its own ADC, arranged 16 × 16.
Each ADC may then span four pixel rows, a width of 4 × 60 = 240 µm, and if square an area of 57,600 µm² (0.0576 mm²), before any of that area is given to the pixel front ends, references or data transmission.
Moving conversion closer to the pixel shrinks that allowance towards the pixel's own area.

### Data off the chip

Every converted sample has to leave the chip.
A 1 Mpixel array at 100,000 frames per second and 12 bits per sample produces 1.2 Tb/s, so the converter fabric must deliver an aggregate throughput above 1000 Gbps, carried by many multi-gigabit serial links whose own power and area come out of the same budgets.

These budgets set what the converter must achieve: a resolution sufficient to count every particle in a frame, a rate that reads the array within a frame, and an area and power small enough to repeat thousands of times within the chip's footprint and thermal limit.
@sec-adcs compares what published converters achieve against them, and turns them into the specification for this work.
