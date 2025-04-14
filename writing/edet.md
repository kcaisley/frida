# DEPFET control 
common clear gate

gate set
gate clear


Switcher ASIC sets
clear on	18V		A seconds gate wich enabled a transistor path to attact the charges out of the internal gate.
clear off	2-3V
gate on 	-5 to -3V
gate off	5V

HV -80V		sets p+ baside wealky to around ~80V, when the depletion reaches it
bulk +10
drift -5V
source 6V (reference) of depfet xtor 


![alt text](img/depfet_model.png)

[Fischer 2007](../../library_detectors/BELLE/2007_Fischer_Steering_Readout_DEPFET.pdf) provides a readout sequence of 

In our system, we have 512x512 pixels per quadrant, electrically organized as 128 rows by 2048 columns.
We have 8 chips with 16x16=256 ADCs, which yeilds the necessary 2048 ADCs, with one per column drain line.
Internally we know this is organized into 8 banks of 2x16 ADCs, with each ADC having a bump bond.

Therefore, my challenege is to see if I can get through 128 pixel, with per pixel time faster than 100ns. My silicon area to work with is roughly 200x180 micrometers. I want to measure 

## EDET meeting notes:

Some questions:
Understanding the difference between TIA vs a more standard readout
Noise sources, drain line resistances/capacitances
applications of real time imaging. Spacial resolution, vs single shot time resolution, vs frame rate
Characteristics of the electron source, magnification, 
data availability (signal current vs total charge, w/ gq extraction)
Can slides be posted on indico?

Johannes:
2d simulation of capacitance and g_q
transfer to 3D Oscar simulations
Capacitances change (increase) as total charge increases
Modeling this capacitance is super important, as it tells how charge partitions between different regions of the depfet, which helps understand how gq charges
plots of capacitance of region vs total charge
model of total capacitance vs injected charge

But gq is not only a function of capacitance,
we normally think of depfet in small signal model, but in large signal the internal gate charge modulations the channel pinch off
So why are we getting mostly linear amplification (constant gq in a local region) at all? Perhaps there's some effect cancellations?

Alexander Baehr (2d device simulations) and Reiner Richter?
origin

noise spectral density setup exists

15 year ago, mateo took spectral noise density





# The source and optics
DEPFET is a general HLL creation, but where will EDET likely be physically setup? Will more than one be made?
What are the characteristics of the electron source and optics? Energy resolution, spatial resolution, stroboscopic rate, single-shot precision?

Is it planned to use the electron beam in a orthoganal transmission through the sample?

# Applications
High framerates with integrating mode readout would seem to imply high-dosage. Would biological samples still tolerate this? What sort of DQE do we need? (read that 20-100 el/Å2 is max for cryo-EM bio samples vs 200 primaries of 300ke per pixel in your presentations?
How does a pixel pitch of 60um correspond to the spatial resolution of different applications? I understand that you want to balance between charge sharing (negative for energy resolution) and 
How does the single-shot precision vs framerate of the detector compare?
base-pairing dynamics and ubiquitous nature of DNA interactions
DNA origami/drug delivery/


# EDET
How will a clock be syncronized to source?
Do we plan to use any ADF/HAADF sensors around? 
What sort of energy resolution do we expect/need from EDET?
If my math is right, a 300keV e- primary loses about 16kEv worth of energy in 50um of Si, this produces around 5000e- of signal. It seems noise is often on the order of 
spectrally there is amazing performance from the beam, so sensor will dominate


# Discussion with Sascha Epp
we'd also use it for other electron beams
femto second diffraction, way less ____ involved

200fs electron beams, with few electrons to avoid repulsion spatially, 
only need kHz repetition rate
repeatable/reversible excitations

at euXFEL they want pump probe, but xrays don't excite the core. So you could excite with flash, and probe it with our electrons
terra incognita


other people: smaller pixels, 


IN TEM, detector refresh rate deteremienrs resolution, in 12
small molecular things are repeatable, and so we can construct a movie from multiple events
the story of EDET is though is non-repeatable dynamics: examples 
the source can be pulsed to aid the sensor in gett
four fold read-out, neighbors?
contrast is low due to carbon in celluar, and radiation tolerance is low
so we won't start with this ^ as it's challenging
instead liquid-phase, thin layer of liquid, for example nano-particle gold growth in solution
    they can grow differently, in different shapes, which affects their dynamics. We can see this.
    another good example is battery research: one challege is cathode and anode observation. Can help us see failure, lithum-phosphate,

energy loss in sample is totally covered in landau noise, we care only about change in position of single particle.
therefore, what we really need to be able to do is just accuracly know the number of particles without error
I dourki has MPSD perspective
if the electron is splitting into three pixels, (solved in thesis) with homogenous resolution

there's also a master's thesis of Martin, coving


The lense is electron/mangmetics solinoid, arrangement of coils 
source -> condensor lense -> objective lense -> orthoganl beam
beam shifter allows chopping the beam


the source/optics totally outperformas the sensors
we have less total pixels
small field of view doesn't affect the physics, just helpful to not miss stuff

I dourki talks about backscattering and

we expect 10nm resolution. Ele a factor of 1-million means 1 nm disk on samples in 1mm disk on sensor
in principle you can zoom in for ever, but at some point the electron optics will fail to magnify

for example: 1nm disk on sample with 100 electrons, 1million is 1mm on the sensor (166pixel), would old only 1-2 electrons at the sensor isn't enough for contrast. You need like 10 or more electrons at least.

and we can't just produce more electrons as the sample per area crhomatics abberations,
and we are dumping many electrons so we are wasting our intensity

as you increase magnifigcation, you need more source intensity to arrive at the same contrast per pixel in the sensor. Unfortunatley, as the intensity is increased, the source's spatial resolution and the resolution in the optics begins to degrade. 

There also maybe be a limit on how high the source can go, especially considering post chopper that we a wasting a bunch of electrons.

# questions for Hans
Why can't they make the pixels smaller? I know pitch vs depth should be roughly square. But the still the sensor is 30um thin potentially, but the pitch is 60um?


A unifying factor of detectors of high-energy particles is that they have a high spectral SNR, and very often have little information of interested encoded in that domain. And so we are typically more concerned with just counting accurately. (Good DQE and good linearity)

Why is CDS needed if there is such a high signal? Is it more to perform offset for array wide normalization?



# Other detectors

how quickly are other designs getting their data out? And how does this compare to commerical high-speed image sensors?

Company			System			Array Size      Array Pitch 	Frame Rate		Pixel Rate

Direct Electron	DE-20       5120x3840       6.4um   25      491Mpx/s

Direct Electron	Celeritas XS    1024*1024      15		
FEI 	Falcon-II   4096x4096       14.0um  18
Gatan 	K2 Summit   3838x3710       5.0um   400
MPG 	EDET        1024x1024       60um    10000   91Gpx/s

For the celeritas XS, we have four 512 by 512 sections, and each of these can read at 


For the TEAM 4d, they state 576*576*87000=28864512000 = 28.8 gigapixels per second

So the bit depth must be 480000000000 / (576*576*87000) = about 16 bit

But they are quote at saying 12 bit resolution 


EDET has 1024*1024*78000 = 81788928000 = 81 Gigapixels per second



# 2024 Turchetta

What is the different between a 'most probable energy loss', a MIP, and the minimum energy loss point on a plot of the Bethe-Bloch formula.

# 2017 Goji Etoh

In 2017, state of the art is roughly 10^10 pixels per second. So roughly 10^4 fps for 10^6 pixels.

I'm chasing above 10^11 pixels (100,000 Mpx/s) per second.


# In-situ applications

`pdfgrep -r "in situ |in-situ" .`

In-situ applications are measured in:
2014 Campbell: phase change materials, solidification of metals and alloys, mophological instabilities, crystallization, reactive multilayer films
2013 Paton: a thesis w/ table labeling some detectors as in situ
2021 Spurgen: 
2021 Levin: talks about all sorts of in situ material science applications. Probably has the best summary
2020 Pu: Summary of nucleantion, growth, assembly, dissolution, nano particles/materials
2020 Dourki: liquid cell
2022 Predikaka: 
2022 Printer: colloidal particle grown

```
pdfgrep -r "liquid-cell|liquid cell|liquid phase|liquid-phase|LP-EM" .
```

liquid phase or liquid-phase

so can probably just search for `liquid`

as in LCEM: liquid cell electron microscopy


![](img/em_phenomena.png)
[From King 2005](../../library_detectors/electron_detectors/2005_King_Microscopy_phenomena.pdf)


# EDEt Dynamic range
From [Predikaka 2022](../../library_detectors/electron_detectors/2022_Predikaka_Thesis_EDET.pdf)
Capacity of EDET pixels is ~100 electrons, which means that you can image thing that produce a low contrast, like biological samples, as they have 'low-Z' materials?

'It will contribute the most to the time-resolved imaging experiments and to the study of fast dynamics in biological systems.'
But really? Can it tolerate the dose?

Gatan K3 having 5um pitch was needed to be found from email exchange with Gatan?



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


This high spatial (nanometer) and temporal resolution (10e-6 to 10e-15) microscope has numerous potential applications for the study of structural and electronic phase transformations, catalytic activity in nanoparticles and nucleation and growth.[Campbell 2006](../../library_detectors/electron_detectors/2006_G_Campbell_pratical_TR_EM.pdf)


Just shortening frame time, or light exposure time doesn't work well, as noise grows. Instead use pulse electron sources [Campbell 2014](../../library_detectors/electron_detectors/2014_Campbell_time_resolved_EM_insitu.pdf)

Recording multiple frames can be done in a stroboscopic pulse train by steering the resulting electron pulses into different portions of the second on different times, using an orthogonal pair of electroscatic deflection plates. In this case, the resolution is limited by the subdivided regions, and the stabiliting time of the defletion plate power supplies. [Campbell 2014](../../library_detectors/electron_detectors/2014_Campbell_time_resolved_EM_insitu.pdf)



Suffice to say, the following are in our speed range (and tolerate):

Dislocation dynamics at conventional strain-rates
nanomaterial synthesis and manipulation. Or in other terms: Nucleation and growth of things like nano-particle, and nano-tubes. These can be 'functionalized'
Dynamics of structural biology: proteins, enzymes, ligands, DNA? These can be aided by filling them with high-Z gold nano particles, to increase contrast.
Battery science: delithium anodes, charging discharging/cycling, dendrite formation, breakdown of lithium ion trasport (battery failure), microdischarge events
Other softmaterials like plastics (biological samples are considered soft)

Things like the below are too fast for us:
Phase transformations: Phase change materials (useful for optical storage, and future PC memories from Intel) use phase change
melting and resolivat
magnetics switching







# Electron Detector  Ideas

Next generation improvements to detector readout for time-resolved electron microscopy in applications where detector speed would realistically allow improvements in observation capabilities. System like EDET target this, but other systems can be configured to operate in this mode. That being said, most system wills either do at very reduced array size (limiting FOV) or perhaps at a very low hit rate (which limits contrast) which are both necessary for biological applications.

One outstanding question if it this case of biological imagine will required rates so high, that very few frames will be able to accumulated before serious radiation damage is attained (again we are not in cryo mode, so biological samples are super rad-sensitive). If this is the case, perhaps we don't need that big of a FWC anyways? It looks like the DEPFET can handle 100-200 electrons.

system integration possibilities: including SOI vertical integration of detectors, regular monolithic integration (on TSPco 65nm??) with in-pixel digitization, or perhaps even 3D hybrid with wafer-bonding? Does this reduce the scattering problem? I guess the radiation hardness and thickness (with back-thinning) both aren't a problem but scatting I'm not sure about?

Kernel based readout of the pixels, so that array size can be restricted in exchange for higher frame rate

Global shutter to reduce motion blur, and maybe can it also to improve readout speed? Can MOSFET process support an extra MOSFET?

correlated double sampling to reduce read-noise

Ways to eliminate pedestal current? Saved value, vs real-time pre-measurement (sort of like cds!)

Ways to improve dynamic range: Different capacitors, separate detectors, either with combined well transfer, auto-adjusting gain, or transistor implemented overflow with intemediated biased transfer gates. 

If we are targeting single electron sensitivity, can we perhaps build an ADC which acts as a multie bit quantizer, and which can (rather than reading out) full ADC resolution, can simply report the number of electrons? We're honestly quite close to that, as 8-bit gives us 256 levels (And looks like the DEPFET can handle FWC of 100-200 electrons.) Plus we must consider that having sub-electron energy resolution is useful for postiion localization.

Different ADC architectures: SAR, vs pipline, vs cyclical?

High speed continuous capabilitiy. Replace SRAM with high-speed serializer, etc?

### Modeling and simulation and optimization

- Devices models of DEPFET device and sensor
- TCAD modeling of sensors
- Verilog-A modeling of full system chain, for simulation and optimization
- generation of analog building blocks?
- Simulation of hits with Allpix2 + Geant4 (better than Casino?)

### Serializer and wireline link:

Each quandrant of EDET is currently producing: (512*512)×8×78000fps = 163577856000 = 163 Gbps

Cordia and Timepix4 (in 65nm) uses a novel low power serializer developed at Nikhef (GWT originally for Velopix, which was based on Timepix3 itself):

- Each link configurable bandwidth from 40Mbps to 10.24Gbps
- Uses 16 links: 8 in each side

As an alternative, CERN has designed the ASIC -> FPGA family called DART28.

It has 25.6 Gbps per link: https://indico.cern.ch/event/1255624/contributions/5443774/

https://iopscience.iop.org/article/10.1088/1748-0221/19/03/C03013/pdf

https://doi.org/10.1088/1748-0221/19/03/C03013

https://doi.org/10.1088/1748-0221/19/02/C02030

### Process in TPSco 65 nm?

- DESY has done Tangerine work
- Nikhef has done 10.24Gbps data serializer and Wireline Transmitter (for ALICE ITS3)
- BNL has done [SAQRADC](https://indico.cern.ch/event/1255624/contributions/5445285/) with 10-bit precision, but only 500 kS/s
- ALICE/CERN has done some work on changing the collection node, for higher bias, lower detector capacitance, etc
  - https://indico.cern.ch/event/1255624/contributions/5443773/
  - https://indico.cern.ch/event/1255624/contributions/5443893/

- And for the above, here is the two originating papers in 180nm:
  - https://doi.org/10.1016/j.nima.2017.07.046
  - https://doi.org/10.1088/1748-0221/14/05/C05013

### There are three proposals:

Propose work on a 65nm DEPFET readout chip, with building blocks that are re-usable to their 

Full on chip-design in a monolithic system is expensive, so they certainly wouldn't take on 

Examining their previously designed systems for on chip/off-chip ADCs:

- ELFIS2: In Lfoundry? Uses a companion ADc. Has 4 quads, where each has 1024x1024 pixels @ 12-bit and 140fps. 1024 * 1024 * 140fps = 146,800,640 pix/s. Checking this we have 8 channels per quad, each at 40 MHz pixel rate, for max 320,000,000 pix/s. Not sure why there is such a higher rate available?
- XS018 technology used for CASPAR2
- FLAMES: on-chip 12-bit SAR ADCs w/ offchip LVDS drivers
- 

