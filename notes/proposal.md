
# Readout circuits for high frame rate electron detector
other keywords: comparative study of, data converters, optimization and analysis, integrating-mode, single-electron sensitivity
Scientific single-particle sensitive integrating-mode readout

most often for in-situ material science applications.

These problems are best solved by integrating mode sensors, where multiple particles are measured per frame, but still with single electron resolution.

Higher speed in-pixel counting, or collumn adjacent electron counting readout has grabbed larger portion of the engineering mindshare (and market share), as they simplying the operation each pixel, and reduce the problem desing space to that of a single-bit quantization. These are especially benefitical in instaces where particle hit rate should be readout with high resolution requirement (small and many pixels), with very spare hit rates, and the desire 
That being said, there will always be a desire for 

Similar to how multi-bit quantization in wired and wireless data links offers a data rate improvement over single-bit, at the expense of increased design complexity due to need to satisfy BER requirements by considering signal to noise and distortion in both temporal and amplitude domains.

Contrast vs dose rate vs problem dynamics vs spatial resolution requirements

With the generous SNR provided by DEDs, single electron resolution has been readily achieved, and so the next question become how quickly and compactly (aka w/ low pixel pixel) can we read out these 

# Review of existing commercial systems


# Signal chain

Sensor types (what is their inherit timing and signal to noise resolution)
Amplification types (C->V and v->C, the above then determines the amplification and buffering necessary to read at full electron resolution)
Buffer types (current vs voltage)
Sampler types ()
ADC achitecture (pipline vs SAR ADC)

then consider each of these with permutations of in-pixel, under-pixel SOI, under pixel hybrid, periphery column matched, and peripherry redistributed ADCS (often off chip)

[Diagrma which shows the various integration possibilites)


# Research outputs:

A concrete comparative analysis and methodology for designing/optimizing layout-aware system models and producing the system design information and netlist colleteral for subsequently correctly implementing these in real fabricated chips.




# Methodology

Correctly evaluating the system performance requires    high-level models which can be trusted to accurately estimate real fabricated chip performance, and which can also be then confidently translated into these systems.

SPICE-type simulation provides the gold standard for accurate circuit level simulation, but there are many different commercially available version of this tool. To start, at the bare minimum we must be able to simulate the compact device models which come with our chosen foundry's PDK. These come in the form of core devices models like BSIM and ideal diode/mosfet/resistor models then with additional macro models lumped element devices to capture device layout-specific parasitics not covered by the core model.

PDKs typically come in two flavors, being the TSMC/Synopysys-backed iPDK format (Tcl based) and the Cadence/Si2-backed OpenPDK (Skill-based) formats. In either case, our devices models are given in a BSIM format, and with macro-model to layout correspondance being covered by Tcl or Skill scripts which don't interact well with anything other than 'big 3' commercial EDA vendor environments.

To pick the best from the crowd, we must consider the fact that we also would hugely benefit from high-level behavioral modeling for analog and digital system.

Analog behavioral modeling can be done with CPPsim, XSPICE 




System performance will be evalutated with manually created SPECTRE simulations, with some models being composed in Verilog-A.

There are many steps fo rhi

Initial sensor performance metrics are critical for optimization, but the design of them are outside the scope of this these. Therefore equivalent circuit macromodels will be built from data gathered from research papers.


#
To do list:
- Understand if verilog-A works as a top level netlist, for both simluation, as well as DRC/LVS.
- To understand how system parameters can be programmatically varied by a python script. What I mean specifically is 
- 