# Background

CMOS sensors have fundamentally changed scientific imaging since their introduction in the early 1990s. Detector dynamic range has substantially improved over this period, spanning single-electron signals and incident fluence rates above 10^12 primary electrons/cm²/s [1]. In contrast, the specification of frame rate has seen comparatively less advancement, as increasing it requires not just better pixel design optimization but also system-level optimization of readout circuits. However, as increasingly sophisticated imaging modalities have been introduced, the challenge of faster readout design has come to the foreground as a major limitation in current generation microelectronics hardware.

A number of recent detector applications now demand continuous frame acquisition above 1000 fps, while maintaining enough sensitivity and dynamic range to resolve individual particles. In four-dimensional scanning transmission electron microscopy (4D-STEM), diffraction images record the angular distribution of scattered electrons at each probe position; rapid acquisition allows a complete spatial scan to be collected in a short time [2]. In X-ray imaging under the high photon fluence of continuous-wave free-electron lasers and diffraction-limited synchrotrons, short integration windows limit the number of photons accumulated per frame, reducing overlap of photon signals and the risk of sensor saturation [3]. Stroboscopic electron microscopy collects images at successive pump–probe delays to reconstruct a time-resolved sequence, effectively making a movie of repeatable dynamics. Faster detector readout supports efficient collection of these image series [4].

## Compact data converters for pixel digitization

The next frontier of high-performance imaging involves systems pushing above the boundary of 100,000 frames per second. Achieving this requires overcoming a bottleneck: the analog-to-digital converters (ADCs) must digitize large pixel arrays within the limitations of power dissipation and silicon area. For example, a 1 Mpixel array comprising 1024 × 1024 pixels and operating at 100,000 frames per second will produce over 100 billion pixel samples per second. Digitizing this stream would then require approximately 10,000 ADC channels operating at 10 MS/s. Assuming 1 mW per channel, the ADCs alone dissipate over 10 W. Understanding the extremity of our design requirements can best be done with a performance heuristic: the Walden figure of merit, FoM_W = P / (f_s × 2^ENOB).

![Published ADC effective resolution versus conversion energy, with the FRIDA design target indicated.](images/report/adc_survey_enob_vs_energy.png)

A survey of state-of-the-art ADC performance over the past 2 decades [5] provides the efficiency context by comparing effective resolution with conversion energy and the Walden figure of merit with silicon area. The highlighted marker denotes our design target of a 500 µW, 11-ENOB ADC running at 10 MS/s.

We address this requirement by proposing a differential successive-approximation-register (SAR) ADC, prototyped in 65 nm but with an architecture portable between process nodes. It is designed for a nominal 12-bit output at up to 10 MS/s, a channel area below 0.01 mm², and power below 1 mW per channel. Its central contribution is the combination of a compact capacitor implementation, redundant conversion, and digital control suitable for dense tiling. Area is essential to this argument: an efficient ADC that occupies too much silicon cannot be distributed throughout a tightly constrained detector readout. The area comparison therefore complements the conventional Walden metric and identifies the compact, efficient region that FRIDA seeks to occupy. Demonstrating the final position within that region requires effective resolution and power to be established at the same operating point.

![Published ADC Walden figure of merit versus reported silicon area, with the FRIDA design target indicated.](images/report/adc_survey_fomw_vs_area.png)

The prototype channel layout measures 60.5 × 63.5 µm, or approximately 3,800 µm², satisfying the intended compact form factor.

The design builds on earlier detector-readout work from the research group. An earlier 8-bit SAR ADC [6] demonstrated low-power conversion at 10 MS/s in a compact channel, but offered lower resolution. The CoRDIA ADC [3] demonstrated more than 10 effective bits at 2.5 MS/s with approximately 24 µW consumption, but occupied 80 × 330 µm. The DCD current-mode ADC [7] established a successful multichannel readout approach for DEPFET detectors, with 8-bit conversion. These designs provide relevant precedents, while leaving scope for the combination of resolution, throughput, power, and channel footprint pursued here.

![Rendered layout of one FRIDA-1 ADC channel.](images/report/frida1_adc_channel.png)

Within this channel footprint, the capacitor structures occupy upper metal layers, allowing active circuitry to be placed beneath them. This overlap reduces the footprint that would otherwise be required by separate capacitor and circuit regions.

The capacitor digital-to-analog converter (CDAC) is the principal architectural feature enabling this compact layout. It uses fringe metal–oxide–metal capacitors with capacitance determined by finger length, drawing on the unit-length capacitor approach [8], published in the March 2019 issue of JSSC. Small effective weights are formed from the difference between two capacitors switched in opposite directions: C_eff = C_main − C_diff. The prototype's smallest effective weight is 0.8 fF, obtained from nominal 26.4 fF and 25.6 fF elements. This avoids relying on an individually fabricated capacitor of the same small value, while retaining a compact array without a bridge-capacitor divider or additional scaled reference voltages. The benefit comes with sensitivity to matching between the paired elements, which must be assessed through extraction, modeling, and calibration.

Capacitance also establishes the sampling-noise budget. For an illustrative 800 fF capacitance per differential branch at 300 K, the ideal differential sampling noise is σ_sample = √(2kT/C) ≈ 102 µV RMS. For an assumed 1.2 V differential full-scale span, ideal 12-bit quantization noise is σ_quant = (1.2 V / 2^12) / √12 ≈ 85 µV RMS. Sampling noise is therefore already comparable to quantization noise at this capacitance, making capacitor sizing consequential for effective resolution. The prototype's nominal physical capacitance, including both members of the difference pairs, is approximately 1.88 pF per branch; the same ideal estimate gives approximately 66 µV RMS, before comparator noise and other nonidealities are included.

FRIDA uses a modified monotonic, single-side switching procedure, building on the monotonic switching scheme [9]. Programmable initial capacitor states provide a means to adjust the comparator common-mode trajectory. Although other switching schemes can reduce theoretical switching energy further, the small array capacitance makes simple rail-driven CMOS switching attractive. The remaining architecture similarly prioritizes compactness: transmission-gate sampling switches, top-plate sampling, and a single-stage StrongARM comparator avoid a bootstrapped sampler, an internal input buffer, and a dedicated intermediate common-mode reference generator. The front end must nevertheless provide suitable input common mode and settling, and the reference supply must remain sufficiently stable.

Redundant capacitor weights spread the conversion over 17 comparator decisions, from which a normalized 12-bit result is reconstructed. At 10 MS/s, a conversion lasts 100 ns, permitting approximately 5 ns per decision after sampling and initialization overhead. Overlapping decision ranges allow later comparisons to correct some earlier errors caused by noise or incomplete settling, with a correction margin that depends on the stage and error magnitude. Synchronous control supports implementation with conventional digital synthesis and place-and-route tools. A one-hot stage selector advances through 16 capacitor-control stages, followed by a terminal comparison that contributes to the decoded result without switching another capacitor.

![Circuitikz schematic of the differential ADC, redundant capacitor weights, synchronous SAR registers, and main/difference capacitor pair.](images/report/adc_architecture.png)

The circuit diagram shows the differential architecture. Each capacitor cell contains a main capacitor and a difference capacitor, with the effective weight shown above it. Complementary rail drivers connect directly to the enabled decision registers. The first three capacitor stages and the final stage are shown; three dots denote the omitted stages 3–14. The central one-hot selector enables one P/N register pair at a time, and the terminal seventeenth comparison contributes to the result without switching another capacitor. Initialization loads the programmed starting state into all driver registers and seeds the selector with stage 0 active. Subsequent logic-clock edges shift this one-hot enable through the chain. Complementary comparator outputs feed the decision registers, and a dedicated clock input controls evaluation. Weighted decoding is external to the prototype ADC macro.

![Initialization, sampling, comparator, and logic timing waveforms.](images/report/adc_timing.png)

The initialization timing illustrates the synchronous control sequence shown above.

![Plan and three-dimensional views of a shortened main/difference MOM capacitor cell, with the shared surrounding electrode in blue and independent inner electrodes in orange.](images/report/capacitor_views.png)

The capacitor illustration presents side-by-side plan and perspective views of the same shortened geometry. A blue surrounding common electrode couples to independent orange main and difference electrodes. Opposite switching produces the effective weight of element N, C_eff,N = C_N,main − C_N,diff. The perspective shows three metal layers connected by grey vias, while the plan shows their shared footprint and via locations. Each inner electrode has two vias near its outer end, away from the split between main and difference electrodes.

Preliminary prototype measurements indicate approximately 488–494 µW at 10 MS/s and a 1.2 V supply. (Note: Power and performance plots still need to be added. They will show power at 2, 6, and 10 MS/s, fixed-input noise or noise-equivalent resolution versus sample rate, and predicted DNL/INL.)

## References

[1] H. T. Philipp et al., [Very-High Dynamic Range, 10,000 Frames/Second Pixel Array Detector for Electron Microscopy](https://doi.org/10.1017/S1431927622000174), Microscopy and Microanalysis 28, 425–440 (2022).

[2] [The 4D Camera: an 87 kHz direct electron detector for scanning/transmission electron microscopy](https://arxiv.org/abs/2305.11961).

[3] [CoRDIA detector and ADC development, JINST 19, C03006 (2024)](https://doi.org/10.1088/1748-0221/19/03/C03006).

[4] J. W. Lau et al., [Laser-free GHz stroboscopic TEM: components, system integration, and practical considerations for pump–probe measurements](https://www.nist.gov/publications/laser-free-ghz-stroboscopic-tem-components-system-integration-and-practical), Review of Scientific Instruments (2020).

[5] B. Murmann, [ADC Performance Survey](https://github.com/bmurmann/ADC-survey).

[6] T. Kishishita et al., [8-bit SAR ADC for detector readout](https://doi.org/10.1016/j.nima.2013.05.192), Nuclear Instruments and Methods in Physics Research A (2013).

[7] I. Perić et al., [DCD detector-readout ADC](https://doi.org/10.1109/TNS.2010.2040487), IEEE Transactions on Nuclear Science (2010).

[8] P. Harpe, [Unit-length capacitor approach](https://doi.org/10.1109/JSSC.2018.2878830), IEEE Journal of Solid-State Circuits (2019).

[9] C.-C. Liu et al., [Monotonic capacitor switching for SAR ADCs](https://doi.org/10.1109/JSSC.2010.2042254), IEEE Journal of Solid-State Circuits (2010).
