- High energy electrons or x-ray photons (10s - 100skV) are used over visible lights, to improve the spatial resolutions.
- And the optics and sensor then work together to target spatial resolutions on the nanometer level.
- And so the main thrust in the scientific  of the past 20 years has been to build detectors with spatial resolutions which support that goal, mainly by reducing pixel pitch, reducing charge sharing which would 'blur' out hits between pixels, and making sure you then read each pixel with super low noises.
- This out well, especially if you cryo-genically freeze your sample today the field has managed to take images at the sub angstrom level which is pretty wild.
- What chips built for electron microscopy haven't focused on though is framerate. Images are taken very slowly, and if these is a concept of 'framerate' it's often to then composited from multiple angles to improve spatial resolution image.



- Frame-rate = time resolution. You can see the cool applications of this with slom-footable in visible light cameras, which has all sort of interseting scientific applications.
- If we could do the same with electron microscopy there are dynamic processes, mostly very small which are interesting to record over time. A key example here is in-situ and liquid-phase electron microscopy including nucleation and growth of nanoparticles, battery systems, catalysis, biomolecules, and organic systems.

So if we could maintain

# XFEL beams

Original XFEl operates at 17.5 GeV per e-, and 27khz (but with a duty cycle), with 100fs precision per pulse.

Beam is 'nearly' coherent, so you can perform single-shot coherent imaging.

Duty cycle is 600us with 2700 pulses in it, so 200ns between pulses (5MHz rate)

Then then the remaining 99.4ms of the 100ms window is a readout time.


The Continuous Wave (CW) upgrade of the Eu XFEL will give it 100-200kHz operation, with 100 fs resolution pulses still.

Beam lines at LCLS range from 3-15 GeV, and has both a 120 Hz (copper accelerator) and 1 MHz (super-conducting accelerator) repetition rates

![Alt text](images/xfel-specs.png)


# Fundamentals

These energies are for all particle in a bunch, added up.

High-repetition rate single-shot imaging detectors.

The interaction of X-ray photons with matter is much weaker than electrons, so if you want to do Coherent Diffraction Imaging, you need *a lot* of particle. This is what an XFEL is for.


The MeV-UED experiement at SLAC is an Electron Camera.  Diffraction and microscopy are two techniques, depenting on structure size. The ultrafast aspects are 'UED' and 'UEM'. It has high spatial resolution (< 0.5 Å), large momentum-transfer range (0.5 to 12 Å-1), high elastic scattering cross sections, high temporal resolution (< 150 fs FWHM), with the additional benefits of relatively large penetration depths (> 100 nm) and negligible sample damage

Diffraction imaging (ultrafast/time-resolved), single shot

You need keV electrons to go below 1 angstrom, and Mev, to go below 1/100 of angstrom

"As the EDET DH80k camera does real-space imaging in integrating mode, no data reduction is possible."

Without any camera lenses, molecular movies rely on coherent waves where X-ray are deflected by electron shells, but more enegetic electrons make it all the way to the nucleus before scattering.

Thinner sensors (<150um) will reduce the multiple scattering of keV electrons, so this is targetted by commerical sensors often, but for the TEAM1k project (which was also used in SLAC's MeV-UED) MeV electrons are used. Thesehave less multiple scattering, and as they deposit ~5x less energy per unit length, a thicker sensor (~500um) is more desirable (see Bethe-Bloch, 1953).

In addition to time-resolved ultrafast microscopy/diffraction imaging to understand structure, you can also to ultra fast spectroscopy to understand energy.
It looks like the main mode of spectroscopy is attenuation/energy loss based, and uses photoelectrons. From a thesis: "The spectroscopic probe comprises time-resolved photo-electron spectroscopy and momentum-resolved photoion spectroscopy, while our structural probe makes use of ultrafast electron diffraction"

Pump probe techniques are important here, because you can choose at what moment to exite the system, and then shortly probe it after.


# detector

What application / illumination sources?

A 0.1 nm wavelength photon is E = (4e-15)*300e6/(0.1e-9) = 12 keV
A 0.1 nm wl electrons is E = 100 eV


'Electron imaging' is better for table-top applications. Photons can reach super shot time scales, but struggle with spatial resolution, and have often have to impart all of their particles in one focused bunch, to get the same spatial resolution as e-, as otherwise the sample will be destroyed before the enough aggregate stats are built up.

Photon light science can only be done where there is a high-energy syncrotron and light source.





# A really bad outline

Detector and imaging systems
Imaging with 


Radiation Imaging

Electrons vs Photons
Particle detection

Detector Sensors
Material (stop), Pixel Pitch, Thickness, Internal Gain, set and reset, Biasing, temporal response and resolution (or lack thereof, if integrating), energy response and resolution (or lack thereof, if avalanche)

Readout Circuit
hybrid vs monolithic materials, pixel-parallel circuits, column/row parallel circuits, array-parallel: power, pitch pitch, 

high dynamic range: adaptive amplifier gain, scaled sensors, 

integration time 



# Single particle counting:

these can be optimized for larger structure tomography, or for single particle analysis



# Liquid cell in-situ EM has low dose rate requirements

# Levin 2020, an example beam dose would be 500 e- per A^2 (1s exposure) # 300keV

# KITE, Dectris 2023 has 10^8 cts/s/pix, which corresponds to a 300 keV electron beam current of 14 pA/pix
# This was for 100um pitch pixels

# Denes TEAM 2023 mentions 1800 e− / Å^2 @ 200kEV.

# Therefore I think we can expect 2000 e- / Å^2 @ 300 kEV, o


# Lexicon
- photodiode (PD): most common structure used for light detection. Has PIN and pinner variants, used in both CIS and CCDs. Discussed in [El Gamel Lecture 1](https://isl.stanford.edu/~abbas/ee392b/lect01.pdf)

- photogate: 2nd most common structure for photo sensing. Basic structure used for originally CCDS (although since Interline Transfer is introduced, these now used a PD as the sensing element)

- pinned photodiode (PPD): massively important invention which reduces noise 
![alt text](images/pinned.png)


- charge-domain binning









- floating diffusion (somehow related to [floating gate MOSFET](https://en.wikipedia.org/wiki/Floating-gate_MOSFET)). FD is where charge stored for readout, modeled as parasitic diode + parasitic gate gap and parasitic drain/source?

- deep trench isolation (DTI)

- [Surface-Channel Versus Buried-Channel Devices](https://www.iue.tuwien.ac.at/phd/habas/node9.html): Can be used for 3T or 4T transistors, or even the the photogate or transfer gate in a pixel. [more on usage as sensor](http://www.cse.msu.edu/~stockman/CV/Figures/Fig2/CCD)

- TF-PPD (thin-film deposited pinned-photodiode): an experimental photodiode which can actually be deposited on the surface of an already commercially fabricated cmos ROIC. Allows exotic materials like indium-gallium-zinc transistors and quantum dot photodiodes


- Random telegraph signal

- reset noise: A type of readout noise, so it only affects integrating operation

- Landau noise: in thin sensors, where HEP isn't fully stopped, a variable amount of charge will be deposited. In integrating operation, this will manifest a certain amount of noise (See B.D. Levin's [explanation here](https://iopscience.iop.org/article/10.1088/2515-7639/ac0ff9#jpmaterac0ff9s1-3)).




other useful features:

high resistivity epitxial


Charge-couple device 


# Terms

shot noise?
fano noise
landau fluctuations
dark noise/dark current
1/f noise (i.e. flicker noise)

kTC noise/thermal noise

CDS -> cancels FPN but not kTC noise
DSNU -> Dark Signal Non Uniformity, expressed in [V/s]RMS or VRMS. The spatial noise due to the pixel-to-pixel non-uniformity of the dark current.

ENC	(term coined in HE physics) Equivalent Noise Charge. Unit [electrons]. ENC=TN+FPN


shot noise (in e- source): fluctuation in quantity of carriers, per unit time. Modeled 	 as a discrete Poisson dist/process. The less events there are on average, the bigger role the shot noise will play. It applies to the keV source, as well as the electronics.

with scintilator + CCD, we would get noise/loss from e- -> photon conversion, and then fiberoptic coupling, but we can ignore these in a direct electron detector

Monolithic sensors are often very thin and so can't typically absorb 100% of incident e- energy, therefore there is some variation in the proportion of energy left, between particles even with the same energy. This is called 'Landau noise' and follows a Landau distribution.

Integrating readout will introduce a 'readout' and 'reset' noise, the latter of which may be able to be corrected by CDS.

If we reduce the beam current, we can operated a frame-based readout in 'counting' mode rather than 'integrating' mode. Counting modes have limitations (on speed vs beam current, to avoid pileup i.e. coincidence loss) but if applicable can eliminate readout and Landau noise.

We can get higher rate electron counting, if we used a hybrid readout configuration to allow in-pixel digital storage. This typically can operated at a much higher effective hit rate, as the frame vs beam current trade off is relaxed. Instead pile-up (i.e. coincidence) is limited on a single pixel dead time, with multiple hits able to be read-out digitally per frame.

Event-based readout is possible in both hybrid and monolithic architectures, any is (I think) exclusively used with counting detection. The difference is that hit counts aren't digitally buffered for the subsequent frame, but instead are sparsely transmitted out as they occur.


# Electronic noise:

With macroscopic devices, it’s fairly easy to imagine how circuit diagrams correspond to what we physically see.

But this becomes more complicated when dealing with integrated systems, as intentional structures are often overlapping and combined, with unintentional structures often being of similar magnitude.

Full circuit loops with band diagram all the way around.



Thermal noise: Structures with non-abrupt potential drops across them are typically conductors or single type semiconductor with measurable currents. Thermal agitation (random variations in drift). Resistors and capacitor structure (which have parasitic resistance) exhibit this. Constant regardless of current, so large DC currents will drown this out.

Shot noise: Structures with large potential change barrier like PN and schottky junctions exhibit shot noise,

Partition noise:
Noise from fluctuations in splitting a currenr between branches.

—the previous noises are inherent to the ideal structures of devices, while the following are from impurities / intentionally placed defects (but which still have this negative side effect)——

For flicker noise: In electronic devices, it shows up as a low-frequency phenomenon, as the higher frequencies are overshadowed by white noise from other sources. In oscillators, however, the low-frequency noise can be mixed up to frequencies close to the carrier, which results in oscillator phase noise. Large DC currents make this worse.

Burst noise: (modeled by random telegraph process) occurs from trapping and releasing of carriers by defect or surfaces contamination in thin films. Small effect; or order of 100uV, but can matter sometimes


# In HEP, seperate sensors are typically made by:

FBK - fondazione bruno kessler

IMB-CNM-CSIC - Institute of Microelectronics of Barcelona



# Readout techniques

- Buffered direct injection

[Paper on photodiode modeling](https://apps.citius.usc.es/fd/media/publications/1344/final/tese_beatrizblanco_20210618112104311.pdf)



# Sensor Material Systems
HgCdTe (MCT or CMT) - MIR, 
InGaAs - NIR
Ge - X-ray, Visible and NIR
Si - X-ray, Visible, NIR
SiC - X-ray and UV
CdZeTe & CdTe - X-ray and Gamma, 'high-Z' material



# PN junctions:

Pn junction
Charge carrier density, with and without external bias, and thermal generation.
Minority injection
Carrier currents under fwd and rev bias
Continuity equation for steady state condition
Finally, we have derived drift and diffusion current
Can also add term to the above equation, to model generation and recombination of carriers
Einstein equation
Diffusion length is characteristic
Assuming: low injections, and no generation in space charge region, we get the Shockley equation


Reverse effect:
impact ionization avalanche breakdown
Thermal breakdown
Tunneling
Zener can take advantage


Two caps:
Junction cap (exists differently in forward and reverse bias)
diffusion cap (only in fwd bias)

The small signal model of Cj is the local derivative (slope), whereas a larger signal model can be made via a linear approximation between a starting and ending g bias point.

Photovoltaic operation mode is when there is no applied reverse bias.

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


![alt text](images/depfet_model.png)

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


![](images/em_phenomena.png)
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


### Process in TPSco 65 nm?

- DESY has done Tangerine work
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

- 


- FLAMES: on-chip 12-bit SAR ADCs w/ offchip LVDS drivers


Analytic instrumentation market 47-50 billion in 2023
roughly 55% hardware, 25% services, 20% software

microscopy (10 B)
	optical (5 B)
	electron (4 B)
	others, x-ray, (1B)

polymerase chain reaction (PCR), (atomic & molecular) spectroscopy, (mass, NMR, and  spectrometry, microscopy, (liquid) chromatography, flow cytometry, sequencing, microarray, and other technologies.



Spectroscopy is frequency resolved , where microscopy is spatially resolved. Both could be temporally resolved too.

A spectrometer is any instrument that’s used to measure the variation of a physical characteristic over a given range, i.e. a spectrum. This could be a mass-to-charge ratio spectrum in a mass spectrometer, the variation of nuclear resonant frequencies in a nuclear magnetic resonance (NMR) spectrometer, or the change in the absorption and emission of light with wavelength in an optical spectrometer. The mass spectrometer, NMR spectrometer and the optical spectrometer are the three most common types of spectrometers found in research labs around the world.


The concept of Bragg x-ray diffraction applies equally to neutron diffraction and approximately to electron diffraction.[4] In all these the wavelengths are comparable with inter-atomic distances (~ 150 pm) and thus are an excellent probe for this length scale. Many other types of matter waves have also been shown to diffract.

More formally, bragg-diffraction is a subset of compton in-elastic scattering

three-dimensional structural data of molecules generally containing at least carbon and hydrogen, comprising a wide range of organic, metal-organic and organometallic molecules.The data, typically obtained (99%) by X-ray crystallography and less frequently by electron diffraction or neutron diffraction.

end users: life sciences/biotech, pharmaceuticals, oil and gas, food & beverage testing, environmental monitoring, and material science, water and wastewater


Light matter interaction is the core of all analytic instrumentation, save those that rely of mechanical matter vibrations like sound.

On the front end, light (optical, x-ray, gamma photons) or matter (neutrons/electrons) are either the immediate object of interest, or a secondary signal either...
emitted: luminescence (cold electromagnetic radiation, including flourescnce, phosphorescnce, etc), incandescence (thermal EM radiaiton), 
refracted/diffracted/transmitted/attenutated 

Absorbtion spectroscopy

scattering

lasers are 'stimulated light radiation, which are then amplified'. 

FELs, are related to lasers, but are more tunable and more powerful. They are tunable from microwave -> X-ray (Xfel)

electron beam, either linear or circular, can be bent to get x-ray synchrotron radiation

A large fraction of experiments using synchrotron light involve probing the structure of matter from the sub-nanometer level of electronic structure to the micrometer and millimeter levels important in medical imaging. Synchrotron is one of the most expensive kinds of light source known, but it is practically the only viable luminous source of wide-band radiation in far infrared wavelength range for some applications, such as far-infrared absorption spectrometry. 


resulting diffraction, scattering or secondary radiation


light-matter interaction

low energy: photoelectric effect
mid energy: thompson scattering (classical), compton scattering (QM)
high energy: pair production, photodisintergration, photofission

https://physics.stackexchange.com/questions/165814/whats-the-difference-between-microscopy-and-spectroscopy

Photons can interact with matter at the atomic level (e.g. photoelectric effect and Rayleigh scattering), at the nucleus, or with just an electron (Pair production and the Compton effect)

Bethe–Bloch formula governs mean energy loss of swift charged particles through matter (protons, alpha particles, atomic ions). The Bethe formula is only valid for energies high enough so that the charged atomic particle (the ion) does not carry any atomic electrons with it. At smaller energies, when the ion carries electrons, this reduces its charge effectively, and the stopping power is thus reduced. But even if the atom is fully ionized, corrections are necessary.

For electrons, despite them qualifying as charged, the energy loss is slightly different due to their small mass (requiring relativistic corrections) and their indistinguishability, and since they suffer much larger losses by Bremsstrahlung, terms must be added to account for this. 

The material is completely described by the 'mean excitation energy' I, where I = 10eV * Z, and the Z is the atomic number of the materials atoms. The Bethe formula is only valid for energies high enough so that the charged atomic particle (the ion) does not carry any atomic electrons with it. At smaller energies, when the ion carries electrons, this reduces its charge effectively, and the stopping power is thus reduced. But even if the atom is fully ionized, corrections are necessary. The most probable energy loss differs from the mean energy loss and is described by the Landau-Vavilov distribution.[3]


FEL and syncrotrons, can be used to study a wide range of application:

bright and fast X-rays are good for crystallography, protein imaging, etc

Scatting is more complicated than

Diffraction is in-elastic scatting, and is only useful for a regular crystalline samples

scattering is elastic, and is better for amorphous materials

Small-angle X-ray scattering (SAXS), is good for examining the size, shape, and suface of nano-sized features. The small angle reduces x-ray penetration to the point of almost total reflection.

Nuclear magnetic resonance spectroscopy methods encounter problems with macromolecules of higher molecular mass (> 30–40 kDa). However, owing to the random orientation of dissolved or partially ordered molecules, the spatial averaging leads to a loss of information in SAXS compared to crystallography. 

When working with standard light imaging, feature resolution will be limited to the diffraction length (wavelength) of the light in the far-field. (in the near field, we can circumvent this). Far-field imaging techniques are most desirable for imaging objects that are large compared to the illumination wavelength but that contain fine structure. This includes nearly all biological applications in which cells span multiple wavelengths but contain structure down to molecular scales. In recent years several techniques (like STEM microscope) have shown that sub-diffraction limited imaging is possible over macroscopic distances.

The same equations apply to other wave-based sensors, such as radar and the human ear.

As opposed to light waves (i.e., photons), massive particles have a different relationship between their quantum mechanical wavelength and their energy. This relationship indicates that the effective "de Broglie" wavelength is inversely proportional to the momentum of the particle. For example, an electron at an energy of 10 keV has a wavelength of 0.01 nm, allowing the electron microscope (SEM or TEM) to achieve high resolution images. Other massive particles such as helium, neon, and gallium ions have been used to produce images at resolutions beyond what can be attained with visible light. Such instruments provide nanometer scale imaging, analysis and fabrication capabilities at the expense of system complexity.

For example, visible light has a wavelength of about 4000 to 7000 ångström, which is three orders of magnitude longer than the length of typical atomic bonds and atoms themselves (about 1 to 2 Å). Therefore, a conventional optical microscope cannot resolve the spatial arrangement of atoms in a crystal.

Electrons can be focused using magnetic or (sometimes) electrostatic lenses, generically called electron optics. Focusing X-rays with conventional optical lenses can be a challenge. Scientists have had some success focusing X-rays with microscopic Fresnel zone plates made from gold and also with long, tapered capillaries that achieve critical-angle reflection.[4] Diffracted X-ray or neutron beams cannot be focused to produce images, so the sample structure must be reconstructed from the diffraction (constructive interference) pattern.

From: https://en.wikipedia.org/wiki/Transmission_electron_microscopy
TEM instruments have multiple operating modes including conventional imaging, scanning TEM imaging (STEM), diffraction, spectroscopy, and combinations of these. Even within conventional imaging, there are many fundamentally different ways that contrast is produced, called "image contrast mechanisms". Contrast can arise from position-to-position differences in the thickness or density ("mass-thickness contrast"), atomic number ("Z contrast", referring to the common abbreviation Z for atomic number), crystal structure or orientation ("crystallographic contrast" or "diffraction contrast"), the slight quantum-mechanical phase shifts that individual atoms produce in electrons that pass through them ("phase contrast"), the energy lost by electrons on passing through the sample ("spectrum imaging") and more. Each mechanism tells the user a different kind of information, depending not only on the contrast mechanism but on how the microscope is used—the settings of lenses, apertures, and detectors. What this means is that a TEM is capable of returning an extraordinary variety of nanometer- and atomic-resolution information, in ideal cases revealing not only where all the atoms are but what kinds of atoms they are and how they are bonded to each other. For this reason TEM is regarded as an essential tool for nanoscience in both biological and materials fields.

From the same above:
The de Broglie wavelength of electrons is many orders of magnitude smaller than that for light, theoretically allowing for imaging at atomic scales. (Even for electrons with a kinetic energy of just 1 electronvolt the wavelength is already as short as 1.18 nm.)

https://en.wikipedia.org/wiki/Bragg%27s_law
Bragg's law covers coherent scattering of waves from a large crystal lattice, can be user to study structures beyond the diffraction imaging limit. Such law had initially been formulated for X-rays upon crystals. However, it applies to all sorts of quantum beams, including neutron and electron waves at atomic distances if there are a large number of atoms, as well as visible light with artificial periodic microscale lattices. 

[](https://en.wikipedia.org/wiki/Crystallography)
Crystallographers often explicitly state the type of beam used, as in the terms X-ray crystallography, neutron diffraction and electron diffraction. These three types of radiation interact with the specimen in different ways.
- X-rays interact with the spatial distribution of electrons in the sample.
- Electrons are charged particles and therefore interact with the total charge distribution of both the atomic nuclei and the electrons of the sample.
- Neutrons are scattered by the atomic nuclei through the strong nuclear forces, but in addition, the magnetic moment of neutrons is non-zero. They are therefore also scattered by magnetic fields. When neutrons are scattered from hydrogen-containing materials, they produce diffraction patterns with high noise levels. However, the material can sometimes be treated to substitute deuterium for hydrogen. Because of these different forms of interaction, the three types of radiation are suitable for different crystallographic studies.

From here, look at the article on x-ray, electron, and neutron diffraction. How thin do samples need to be?


# Cryo-EM, a new type of microscopy


# Detectors for Transmission electron microscopes:

Previously, a Scintillator would convert ionizing radiation to visible light, which would then hit sensor

Now we use CMOS image sensors, which provide a higher readout rate and which are less succeptible to 'blooming', which is the overflow of charge into adjacent pixels.

With a CMOS we can do direct electron detection (rather than using a scintilator).

Dectris offers direct electron and direct X-ray detectors.




micrograph

in both cryo-em and crystallography, you're relying on many copies in order to build a 

you get a electron density map, in cryo-em: coulomb potential map.

X-ray and electrons interact with different parts of atoms, but mainly the electrons

Electron of atoms are deflecting (scattering) the incoming x-rays, which then add constructively to give diffraction patterns

things like proteins are hard to measure, because they're too irregular for x-ray crystallography. This is where Cryo-em comes it.


With cryo-EM, our electrons with both the valence electrons, as well as the charge of the nucleus.

In either case, these procedures yield maps, which then can be reconstructed into stick or ribbon based models.

An angstrom is 0.1 nm.

nobel prize in chemistry 1999 for femto second Pump probe

A particle traveling at the speed of light can only cover the width of a water molecule in the duration of an attosecond

AMO physics is 'at energy scales around several electron volts', but are the particle sources also such low energy? Electron microscopys are are 100's of keV.

time scales for molecule - molecule interaction are orders of magnitude longer than the fast atomic or molecular dynamics.


Unlike X-rays, which diffract from the electron density in a crystal, electrons are scattered elastically by the Coulomb potential, which is related to the density through Poisson’s equation and includes the nuclear contribution. Electrons are much more strongly scattered than X-rays and have much smaller wavelengths. (This leads to a very ‘flat’ Ewald sphere and the simultaneous excitation of many Bragg beams.) Electron sources have comparable brightness to third-generation synchrotrons fitted with an undulator, so that Bragg intensities are very high. Because of their limited penetration, samples for transmission electron microscopes (TEMs) usually have thicknesses of less than a micron, while for interpretable atomic resolution images, thicknesses of tens of nanometres are preferred.


Experimental Method in condensed matter physics



Can you exhaustively check the below list for techniques related to X-ray and electron imaging and spectroscopy modalities? 


Dark-field vs bright field imaging
direct electron detection
topographic contrast vs material constrast vs element analysis?
Scanning vs transmission vs scanning transmission
Secondary (SE) vs backscattered electrons (BSE)

        
Topography Techniques:

    Transmission Electron Microscopy (TEM) (1931): Reveals internal structure and composition at the nanoscale by transmitting electrons through a thin specimen.
    Scanning Electron Microscopy (SEM) (1935): Generates surface imaging and topography by detecting secondary electrons emitted from the sample under electron beam bombardment.
    Laue Diffraction (1912): Applies crystallography using X-rays to study the arrangement of atoms in crystals.
    Scanning Tunneling Microscopy (STM) (1981): Provides surface topography at the atomic scale by measuring tunneling current between a sharp tip and the sample surface.
    Atomic Force Microscopy (AFM) (1986): Scanning probe microscopy (SPM). Captures surface topography at the nanoscale using a sharp tip that interacts with the sample's surface forces.
    4D STEM (Four-Dimensional Scanning Transmission Electron Microscopy) (2003): Enables structural and compositional mapping with high spatial and temporal resolution.

Material Contrast Techniques:
    Small-Angle X-ray Scattering (SAXS) (1925): Analyzes structural features of nanoscale materials using scattered X-rays.
    Back-scattered Electron Imaging (1961): Offers material contrast based on variations in atomic number using backscattered electrons.
    Micro-Electron Diffraction (MicroED) (2000s): Utilizes electron diffraction for crystallography at the nanoscale.
    Cryo-EM (1975): Captures images of biological samples at cryogenic temperatures.
    Laue Diffraction (1912): Applies crystallography using X-rays to study the arrangement of atoms in crystals.

Element Analysis Techniques:

    X-ray Fluorescence (1913): Identifies and quantifies elements in a sample by measuring emitted fluorescent X-rays.
    Energy Dispersive X-ray Spectroscopy (EDS) (1969): Performs elemental analysis of samples by detecting characteristic X-rays.
    Wavelength-dispersive X-ray spectroscopy (WDS)
    
    
Spectroscopy Techniques:

    Ultrafast Transient Absorption (1970s): Probes ultrafast dynamics in the time domain.
    Two-Photon Photoelectron Spectroscopy (1980s): Examines electronic properties using two-photon absorption.
    Time-Resolved Photoelectron Spectroscopy (1980s): Investigates electronic transitions with time resolution.
    Pump Probe (1984): Studies ultrafast processes in materials by exciting and probing with short laser pulses.
    Single Particle Analysis (SPA) (1980s): Reconstructs 3D structures of individual particles.



Ptychography (1990s): Achieves high-resolution imaging of the internal structure of materials. Ptychography is a computation method for microscopy, which can be used for visible light, UV, X-rays, or electrons. Ptychography solves for the phase induced by the real part of the refractive index of the specimen, as well as absorption (the imaginary part of the refractive index). This is crucial for seeing transparent specimens that do not have significant natural absorption contrast, for example biological cells (at visible light wavelengths),[24] thin high-resolution electron microscopy specimens,[25] and almost all materials at hard X-ray wavelengths.
    
Ultrafast Electron Diffraction (UED)
X-ray Free-Electron Laser (X-ray FEL) (2009): Enables ultrafast imaging and structural studies using intense X-ray pulses.
Chirped Pulse Amplification
Direction Electron Detection
X-ray power diffraction
THz, optical, and IR spectroscopy (these aren't spatially resolved, and not often temporally)


An exhaustive list of techniques for generating, amplifying, modulating, accelerating, and focusing electron and x-ray beams, lasers, and pulses, including those that allow for ultrafast pulses:

Electron Beams:
Generation:

    Thermionic Emission: (1883) Emission of electrons from a heated cathode.
    Field Emission: (1928) Extraction of electrons through a high electric field.
    Photoemission: (Early 20th century) Ejection of electrons using photons.

Amplification:

    Traveling-Wave Tube (TWT): (1940s) Amplification of microwave signals.
    Klystron: (1937) Linear beam microwave amplifier.

Modulation:

    Electron Gun Modulation: Ongoing. Control of electron emission with external signals.
    Pulse Generators: Ongoing. Production of short-duration pulses in electron beams.

Acceleration:

    Linear Accelerators (LINAC): (1928) Acceleration of electrons in a straight line.
    Cyclotron: (1932) Circular acceleration of electrons using a magnetic field.

Focusing:

    Magnetic Lenses: Ongoing. Use of magnetic fields to focus electron beams.
    Electrostatic Lenses: Ongoing. Use of electric fields to focus electron beams.
    Quadrupole Lenses: Ongoing. Focusing based on a combination of electric and magnetic fields.

X-ray Beams:
Generation:

    X-ray Tubes: (1895) Production of X-rays through the collision of high-speed electrons with a metal target.
    Synchrotron Radiation: (1940s) Emission of X-rays from charged particles in magnetic fields.

Modulation:

    X-ray Pulsars: Ongoing. Production of modulated X-ray beams from rotating neutron stars.

Focusing:

    X-ray Optics: Ongoing. Use of mirrors, lenses, or crystals to focus X-ray beams.

Lasers:
Generation:

    Ruby Laser: (1960) Generation of laser light using a synthetic ruby crystal.
    Gas Lasers (HeNe, CO2, Argon): (1960s) Generation of laser light using gas discharges.

Amplification:

    Laser Amplifiers: Ongoing. Increase in the power of laser beams using amplification techniques.

Modulation:

    Acousto-Optic Modulators (AOM): (1960s) Modulation of laser beams using acoustic waves.

Ultrafast Pulses:

    Mode-Locked Lasers: (1964) Production of ultrashort pulses by locking the phases of laser modes.
    Femtosecond Lasers: (1980s) Production of pulses with durations in the femtosecond range.

Focusing:

    Laser Beam Shaping: Ongoing. Use of lenses and mirrors to focus or shape laser beams.
    Adaptive Optics: (1953) Adjustment of the shape of optical elements to optimize beam focus.

Ultrafast Pulses (Electron and X-ray Sources):

    Free Electron Laser (FEL): (1977) Generation of intense, coherent X-ray pulses with high tunability.
    Attosecond Pulses: (2001) Extremely short pulses in the attosecond (10^-18 seconds) range.


## Particles worth measuring

![](images/particles.png)
Notes: 

- Leptons/antileptons have no strong interaction
- 
Order of detection:
1. Charged Hadrons (Proton, Pion, etc) and charged Leptons (Electron, Muon, and Tau) are detected in silicon tracker. BUT: Neutral Hadrons (Neutrons, etc) and Neutral Leptons (All three Neutrino) and photons are not detected in silicon tracker as they uncharged
2. Photons and electrons are stopped in electromagnetic calorimeter, protons aren't stopped but are 'visible'.
3. Charged and neutral hadrons are stopped in hadron calorimeter
4. Muons are stopped in the muon outer layers. Neutrinos of all three types pass through with no interaction

**Composite Particles**
Hadrons (Made of Quarks, almost always unstable when 'free')
- Baryons (Odd quarks, usually 3)
	- Protons
	- Neutrons
	- +Exotic Baryons
- Mesons- Even quarks, usually 2, stable only ns before decay
	- Pions
	- Kaons



# how to detect:

Material systems

In metals, the outermost electrons are delocalized and form a sea of electrons that are free to move throughout the material. This delocalization means that the outer electrons are less tightly bound to individual atoms compared to the electrons in semiconductor materials. As a result, high-energy particles have less interaction cross section with the electrons in metals because they are less likely to scatter off the loosely bound electrons.
Also, in metals, I think that the conduction band overlapping with the valence (no distinct bandgap) means that incident high energy particle tend to excite electrons in the conduction band, rather than create electron hole pairs in the valence.


photoelectric effect vs compton scattering vs pair-production

How does the [photovoltaic effect](https://en.wikipedia.org/wiki/Photovoltaic_effect) work by comparison?



Infrared, visible light, and X-ray imaging are quite common. But UV isn't. This is has a couple reasons. One is that UV light is attenuated by the atmosphere, which means there is less of it for applications like ground based imaging of space. Another reason is that a significant challenge for UV imaging is the fact that glass absorbs UV light. Therefore, only specially designed optics made with very pure  glass (silica) with few impurities can fully take advantage of the full  UV exposure being imaged. Impurities such as iron and sodium are common  within glass and are the cause of most UV absorption. [Source](https://www.lumenera.com/blog/how-imaging-with-ultra-violet-light-reveals-hidden-details)

>  Shorter wavelength photons (400 nanometers and below) are either reflected or absorbed into the gate region of the CCD. Longer wavelength photons (between 400 and 700 nanometers) have a high probability of generating an electron within the charge well. As photon wavelength exceeds 700 nanometers, the probability becomes greater that the photon will pass directly through the CCD without being absorbed. The spectral sensitivity of the CCD differs from that of a simple silicon photodiode detector because the CCD surface has channels used for charge transfer that are shielded by polysilicon gate electrodes, thin films of silicon dioxide, and a silicon nitride passivation layer. 

![Uv light](~/frida/docs/images/uv_detection.png)

https://micro.magnet.fsu.edu/primer/java/digitalimaging/ccd/quantum/



## Energy resolution

![alt text](images/spectrum.png)


Kalpha and Kbeta emit the characteristic energy, and we see them in full absorption at those two lines

The flat background baseline is 'particle absorbption from scatting'

The energy noise is measured by 'fitting a gaussian' to the low energy peak

## Applications What needs to be measured, and with what precisions

Discuss applications, and their desired precisions, what is limiting bottleneck right now

Explain sometimes the particle itself is work measuring, other times it gives implicit information about another

# From source to deposition charge to propogation charge to pixel charge:

- Show how various state of the art sensors classes transform particle hits to pixel charge.
- Don't discuss optimization, just take sensors "for what they are", as optimized by others.
- Display simulation results in a consistent manner for different sensors types, against various incident particle types and conditions.
- Then discuss how the sensor has already modified the properties of the 

*Topics:*

Interaction with matter. Particles, charged or neutral, can only be detected via interaction with matter.

The Bethe-Bloch formula determines the *average* energy loss per path length, by the mechanism of ionization.

Of course, this radiation also deteriorate the sensors, as will be discussed in later sections.

Geant4 provides modeling from the initial source, be it and electron or hadron beamline, or radioactive source. It simulates the move of incident particles, as then pass through the sensor and calculates their energy deposition.

Based on this, the creation of electron hole pairs can be computed. [Lachnit, 2021, p37](https://www.physi.uni-heidelberg.de/Publications/BachelorLachnit.pdf)

[Allpix²](https://allpix-squared.docs.cern.ch/) then provides several models for propogation of this charge in the sensor.

At it's core it relies on an accurate model of pixels is done via TCAD simulation, including electric field and doping profiles. This is essentially the a set of  a FE or FD discretation approach for creating a mesh, then together evalutated with a quasi stationary solver.

Allpix² then builds on top of this core.

We don't need more complicated EM solver types like, Finite-differences-time domain (FDTD), Method of Moments (MoM), or equivalently, Boundary Element Method (BEM). [More info on these.](https://www.matecdev.com/posts/differences-fdtd-fem-mom.html)


![Alt text](images/tcad_types.png)

electric field can't be generated in metals, as the conduction and valence band are overlapped
there are no 'carriers'weighting field and shockely ramo theorem

Short article on epitaxial layers on top of substrate, for pixel dectors: https://meroli.web.cern.ch/lecture_CMOS_APS_epilayer.html



# Masks

Wafer are like 200-300mm nowadays, but only processing 
Older wafer are 16in (40mm), which is only used by small foundaries with outdated tech
A mask is used for a single die area, and the light is scaled down by a factor of about 10.
Then the mask/reticle are stepped across the wafer, which is typically the bottle neck in manufacturing, as other processing steps are often wafer-wide.

# Sensors mechanical

At the edge of sensors you have the implanted guard ring structures, which gently diffusion the lateral pixel bias field.
Sensors can be made very large, but chips are often limited in size. Therefore we have concepts like quad modules.
At the edge regions between chips, the pixels are either:

- just larger
- or you have the intermediate orphan pixels attached to an interior pixel, a couple positions away, which isn't likely to be activated at the same time.

So different techniques to tile them are:

- Tipping and overlapping
- Back and front side of a support, two allow overlaps
- No overlapping on one layer, but various layers in detector are offset

# Charge signal formation

The primary particle will not always make a simple cloud shape
For example, if it passed between two pixels (at edge) or even four (at corners), it can make 1/4 of the charge.
A low energy photon will just product a small 1-2eV signal via the photo effect
A high energy photon, from X-ray or Gamma, will produce a ~60keV charge, but this then will collide with other atoms and produce a bunch of knock on carriers in a weird shape.
Another issue is that the vertical fields bend toward the collection nodes as they reach the 'top' of the substrate, which leave a 'dead zone' between pixels. Any carriers generated here will take a much longer time to be collected as drift will be minimal.

# Readout

Pixel sensor typically have a capacitance of $Cd = ~50$ fF
The sensor can be modeled as a current source in parallel
To fully read out this charge, we need either a resistive or large capacitive load.

- Large resistor could work, but it hasn't been used
- Large capacitor is possible, but is better achieve using a miller capacitance in feedback, where $Ctot = C_{f}*(A_{0}+1)$. 
  Signal charge is normally around 1fC
  What is the bias voltage across the detector?
  What is the leakage current typically/approx?

Hans wrote that $V = Q/C$, which is true, but this seems to imply that having a large cap actually reduces the voltage signal?

Some variations of the arch. are putting a current source in feedback with $C_{f}$, or placing an AC-coupling capacitor on the input of the amplifier. Also, placing something in feedback is a great way to also build a hi-pass filter, which eliminates the leakage baseline, and any left over signal.


# Images sensors:

Cyclic ADC is like SAR, but amplifier error signal instead of reference voltage

On sensor ADC, comes in 3 main layout configurations:
![Alt text](images/pixel_array.png)

The full-well capacity (FWC) is the largest charge a pixel can hold before saturation which results in degradation of the signal. When the charge in a pixel exceeds the saturation level, the charge starts to fill adjacent pixels, a process known as Blooming.

![](images/pixel_fwc.png)



# Scientific imaging needs:


![Phenomenon timescales](images/timescale.png)

*Timescales for phenomena studied in materials science (red), life sciences (blue), semiconductor (gray), and nanotechnology (green). Accessible timescales of complementary UTEM techniques are also superimposed.*

Are time scales the same thing as temporal resolution?

![Field resolutions](images/resolution.png)

Yellow area: high time resolution, continously high repeated measurements (real and k-space)
Pinkg region: very high single-shot time resolution, but stroboscopic slower repetition  (k-space only)





# EDET & Belle: DCD + DMC + DEPFET
DCD 1 + Switcher3: [P. Fischer TWEPP 2007](https://indico.cern.ch/event/11994/contributions/84416/)
DCD Belle: [I. Peric TNS 2010](https://doi.org/10.1109/TNS.2010.2040487)
DCD2 + ASM Belle: [M. Koch Thesis 2011](https://cds.cern.ch/record/1380639?ln=en)
DCD2: [P. Fischer JINST 2011](https://doi.org/10.1088/1748-0221/6/01/C01085)
EDET prototype: [S. Epp VERTEX 2016](https://indico.cern.ch/event/452781/contributions/2297602/)
EDET prototype: [S. Epp IWDDA 2016](https://indico.mpp.mpg.de/event/4247/contributions/9603/)
Belle Modules: [F. Mueller Thesis 2017](https://www.mpp.mpg.de/~cmk/Belle/Thesis_Mueller_Felix.pdf)
EDET80k summary [MPG HPP HLL](https://www.hll.mpg.de/3051199/EDET80k)
EDET80k sensor [M. Predikaka JNIMA 2020](https://doi.org/10.1016/j.nima.2019.162544)


- EDET does time-resolved spectroscopy, does it measure after illumination?
- Good for study dynamics of chemical processes, protein folding.
- The spacial resolution of electron beam illuminated systems has already seen good improvements, I think down to the atomic scale?
- But 'real time' vs 'stroboscopic' imaging of system dynamics is still unsolved.
- Backthinning + minimal support reduces multiple and back scattering -> good spatial resolution
- In pixel signal compression -> DR is single primary $e^-$, or from $100$ -> $8\times10^5$ $e^-$ (poisson limited)

EDET is normally used for 'shadow' based imaging, with either electrons or photons (soft Xrays). Electrons have a very high depositied energy, and so if you're using them in a TEM configuration you need to make sure the dynamic range of the DEPFET pixel won't saturate. When doing Xray imaging, with a source coming from a syncrotron (for example) you instead have a different deposited energy pattern, which is the 'Fourier transform' of the incoming particle energy. It's used in drug discovery and material science.

DEPFETS could also be used for space based imaging, where the object of interest is the source itself.

DEPFETs in EDET and Belle2 uses a quad-grouped rolling shutter. In Belle2, this works for tracking because it's already a 'quasi' continuous beam with a 2ns bunch crossing, but the hit rate is so low, that the inner layers don't need to 'disentangle' nearly as many events. Finally, the outer layers actually take multiple samples along the deposited charge waveform, and so they are doing the job of getting precise timing information.

Sampling time of ADC but be slow enough to achive resolution needed for each pixel, but the aggregate rate must be fast enough to achive readout time of the entire pixel array.

- DCD1: TNS 2010. 72 ADC channels each with 140um x 110um. Contains two cyclic ADCs in parrallel, 8-bit, 660 SNR (56 dB), 320ns (3.125 MHz) conversion time, 40um x 55 um, 1mW power, 180nm. At this time, DEPFET array produced 400 pA /e in sensor. Input signal range Dynamic range is from +- 8uA, with a 64nA LSB. The measurement takes 8 cycles, each 40ns (25 MHz) long, for a total of 320ns for 8bit precision. (They also built a fast variant, with 20ns per bit, for 160ns sampling time for 8-bit resolution)

- DCD2: An in-between chip revision, not documented specifically in a paper.

- DCDB: Revision for Belle, 180UMC, increased to 256 channels (JINST 2011). Total chip area was 3200 x 5000 um. 16 by 16 ADC array, with each measuring 200 um x 180 um. 256 ADC channels, at same data rate as DCD1, requires eight 8-bit links. Each ADC presents a byte of data every 320ns. This is means each ADC is clocking out a parrallel byte at 3.125 MHz. 32 of these channels are serialized together. The ADC conversion time is increased now to 100ns (10MHz), which is like 3 times faster than DCD1. Total power per channel is 4mW.

- DCDB + DHPT65: T. Kishishita 2012 for Belle. 256 ADC in, 4:1 mux for 64 links -> DHPT, then with 1.6GHz single serial output (1.28Gbps after 20% overhead), 12-15m twisted pair. They used four DCDB + DHPT pairs. Shooting for 20 us per frame (50 kHz frame rate). The row time is the same as EDET, it's just 

Pixel array for Belle module is 768 px rows, x 256px columns. Four rows are read out at a time, though. Therefore, 4 DCD + DHPT channels are used. No correlated double sampling is used.

> Readout timing: The most challenging aspect is the frame readout time of 20 µs, which would translate on a full module with 1536 (768x2) pixels to a row time of only 13 ns (76.8 MHz). This timing is impossible to achieve (cf. measurements in Section 7.1) due to intrinsic settling times of the DEPFET sensor and the readout chips. The time constraint is however relaxed by splitting the module in half using readout chips at both sides, and implementing a high degree of parallelization by using a four-fold pixel arrangement(Figure 12). This results in a factor of eight gained in speed, translating to a row time of 104.2 ns (9.6 MHz). To gain additional time, the DEPFET typical sample-clear-sample (double sampling, see Section 2.2.3) readout operation has been abandoned in favor of the faster sample-clear (single sampling) sequence.

- EDET project starts: ~ 80 kHz frame rate (actually 78.125 kHz/12.8 us frame time). 512x512 pixel in a quadrant. Twice many columns as Belle, and I think still readout four rows at a time, so this is why 2*4 = 8 DCD + DMC chips are needed. To sanity check: 512 row read in groups of four (512/4=128), with each ADC at 100ns sampling time sampling time, gives us 12.8 us frametime (78.125 kHz frame rate).

- DCDE is an increased dynamic range version DCD. It's being used in EDET (Koffmane, 2019)


# For FRIDA

We have 512 x 512, but each of the 8 chips is responsible for a 64 x 512 region of pixels. Each pixel is 60 x 60 µm, so that means that the width for the 64 pixel section is 3.84 mm. This is much less than the maximum ~20mm full reticle size. But that's okay, as we can reduce our design complexity and improve yield.

We have fourfold column readout though, so it more like we're reading a 256 wide x 128 tall pixel array.

Each of these 256 effective columns gets an ADC, which are fit in 16x16 configuration. Thus each ADC is limited to 64/16=4 pixel rows. That means each ADC must fit a 4*60 = 240µm width, and we assume they are square, a 57600 µm² or 0.0576 mm² area.


which takes 100ns to sample at 8-bit resolution, and that the full 64 x 512 region needs to be readout in 12.8 us frametime (78.125 kHz frame rate). 

ENOB * 6.02 + 1.76 -> SNR

8 * 6.02 + 1.76 -> 50 dB
10 * 6.02 + 1.76 -> 62 dB

Previously, in TSMC 65: 12.5 Ms/s, 8-bit, 40x70um size, 40 uW at 1.2V. 

100ns is 100 Ms/S.

Energy per conversion is 40e-6/12.5e6 = 3.2e-12 J.


at a ~80kHz full frame rate (12.8 us). The end application is for a high-performance transmission electron microscopy camera.

The ROICs will be bonded around the periphery of the sensor arrays substrate. Each is only responsible for reading a subsection of the array measuring 256 column x 128 rows, with one ADC per column. Based on the frame time ADC must capture the drain current in less than 100ns, at 10 bit resolution. The area per ADC should be around 0.0576 mm² area (240µm * 240µm, assuming it's square).






Are cyclic ADCs used in all of these? When I hear 'residual' and 'algorithmic ADC', what should this mean to me?

So what have we learned:

- The settling time of the switcher and DEPFET pixels determines how quickly a row can be readout.
  - approx 50ns settling appeared to be the speed limit in 2010. Can we improve on this?
  - So making the ADCs faster than 10 Mhz doesn't look like it would help.
  - But maybe switcher could be faster, or maybe the settling time of the DEPFET array has improved in the past 15 years?
  - Just reading multiple rows in at once, with extra ADCs, is a work around for the 'speed limit', but 4-fold may be the pratical limit.
  - What physical processes would be then measurable, if the frame rate were to improve?
- The on chip memory density/capacity determines how many frames can be buffered before the system has to pause.
  - Would this be beneficial to increase?
  - Do we really need a 3.2 Ghz PLL, if we can readout the frames as slowly as necessary?
  - What is the downstream PHY capable of, and how long/what type are the cables
- Would timing information be helpful? (I think not, as it's in imaging mode.)
- What determines/limits the spatial resolution? Does framerate affect that? Would it help if it were improved?
  - If ADCs were faster, but the frame time was the same, perhaps we could oversample or correlated double sample the pixel current
  - This would not improve temporary resolution, but would get us better SNR. 



# Notes from meeting, Oct 10
-The dynamics of the collection electrode are very slow, relative to the injection charge. Ie the dominant pole is the electronics. Therefore the shaped of the transient of the current injection isn’t important, and can be modeled as anything. The area is all that matters. This is why injection circuits can be built the way they are. Perhaps this would not be true for timing sensitive systems?
- First order description of a detector front end is just noise and threshold. Second order is amplitude dependent time walk.
- TOT information is mainly just used for calibration. However, it can be used to provide a slight improvement for particle identification in assistance to the calorimeters, and in the case of a particle that just arcs through the inner tracker, only, without passing into the calorimeters, it can identify that too. These would be heavy particles?
- EDET and current PXD system are very similar
Cordia has ADC which could be built into new EDET
You could have the DCD and DHPT all on one chip in EDET
- The Cordia project has a very, very large dynamic range from 10photons to 10000, and so it needs an adaptive real time gain scaling, incase a hit gets close to saturating.
- VTX Obelix is a monolithic chip for Belle upgrade, which has a column based VCO for timing at 320MHz.
- Timepix has a local VCO for timing.
- The Belle DCD had a data rate of 2.5 MS/s, with 10 bit of resolution, while the EDET DCD needs 10MS/s
- Tracking systems are of low commercial appeal, so maybe I should focus more on imagers. EDET and Timepix are two examples.
- The two main ongoing monolithic detector projects are the RD 50 projects and the Obelix projects. I’m not sure how Liverpool fits in here, perhaps it’s part of the RD 50? 
- Is allpix useful for imaging systems?
- Snoeyes is well known for leading the Alpide design project.
- The ASM is specially made in a proprietary process by a research lab. Is it by MPG HLL? It has DEPFETs and had flip chips for Switcher, DCD and DMC/DHPT chips.
- The inventor of DEPFETs is a TCAD guy, now working on EDET.











# AGIPD:
Find more stuff like this:
- Stuff at linear accelerators
- Stuff at syncrotron light sources

Hybrid system w/ bump bonds, 200um pitch, 

4.5 MHz (pulse separation of by 220 ns) for up to 2,700 pulses (total train 600 µs)
10Hz repetition (10ms), so there is 99.4 ms of spacing after start of new train

[](https://photon-science.desy.de/research/technical_groups/detectors/projects/agipd/index_eng.html)

EDET

# Cordia
at Desy

Cordia 10 MS/s 8-bit charge-redist ADC [Tetsuichi, Hemprek, Krueger, JNIMA 2013](https://doi.org/10.1016/j.nima.2013.05.192)

# Medipix/Timepix



| Chip | Year | Node |
| ---- | ---- | ---- |
|  Medipix4 | 2021 | 130 |
| Timepix4 | 2019 | 65 |
| Timepix2 | 2018 | 130 |
| Medipix3 | 2011 | 130 |
| Timepix3 | 2013 | 130 |
| Timepix1 | 2006 | 250 |
| Medipix2 | 2004 | 250 |
| Medipix1 | 1998 | 1000 |

Timepix4 specs: `3.58*10^6 hits/mm^2/s	195ps LSB	ToA 23bit DR (1.6ms)	80e- LSB	15-bit DR	5 x 10^9 hits/mm2 /s`





# Monolithic
OBELIX monolithic (BELLE II)
ALPIDE (ALICE)
TJMonopix
LFMonopix
![Ivan 2021](images/monopix_specs.png)
from [I. Caicedo 2018](https://arxiv.org/pdf/1902.03679.pdf)
Tangerine

0.1-0.7w /cm2 typical? Is this for monolithic or hybrid?
Obelix has no pll


# Hybrid Tracker LHC

Particle detector for tracking are weird, as they don't form images, are single particle sensitive, and they are event-based triggering-based, rather than frame based

FE-I4 (ATLAS LHC)
RD53 (CMS + ATLAS HL-LHC)


0.1-0.7w /cm2 typical? Is this for monolithic or hybrid?



Pixel sensor FOM:

focus on charge based sensor readout. Must ignore different input sensors, as ADCs foms typically do?
REduce down to individual pixek, but specify area + power per
Factor out monolitichi/hybrid specific parameters
Single-shot pulse signal: SNR isn't useful, as signal+noise is measured in energy, not power?
ADC FOMs factor out dynamic range by making to a part of the the distoritaion (via SNDR), do I have this luxury? ADCs and assume a sinusoidal input, but I don't have that?

In a single pulse system, can the accuracy of the energy measurement be made arbitrarily accurate by stretching the pulse out over a longer period of time, or larger period of amplitude?

No, I don’t believe so, because even if the input was ideally noise free, there is no such thing as noise free amplification. In any case, post amplification the signal to noise ratio of the signal fed to the quantizer, now full-scale.



---

### From other notes:

RDL/Passivation to connect resistors on the top, costs $4600


AIDA 28nm

SPAD sensors
Normal CMOS image sensors?


			Tracking Mode (Data Driven Readout)					Imaging/Counting Mode (Frame-Based Readout)					
Pixel Pitch	Pixels	Sensi. Area.	Max Hit Rate	Time Res.	Time DR	Energy Res.	Energy DR	Max Hit Rate	Particle Counts			Readout Type	Tiling Sides


RD53: 500mW per square centimeter, as -20C must be maintained to prevent thermal runaway damage
In hybrid sensors current is ~nA, but voltage is higher, which means it still consumes 50% of total power



multiple scattering is worse in e+ e- colliders like Belle


In systems that are DC coupled, which is the majority of the sensors, any additional current will manifest as error signal in the integration period, and so you need a compensation circuit. It sounds like charge-sensitive amplifiers somehow manage to work around this partially, by somehow ignoring the dc component using their 'bandpass' characteristic. But I suppose this isn't perfect?

The other approach, which has been tried, is AC coupling the sensor which prevents the DC leakage from affecting the readout electronics. However, this will form a capacitive divider with the pixel sensor capacitance. The ratio of sensor_cap:coupling_cap roughly forms the ratio of signal loss so a much larger coupling cap is needed. For example a 1:10 ratio means that 10% of the signal charge is lost (I think???).  Seeing as typical pixels have a capacitance on the order of 50fF, we would need a coupling capacitance of around 5 pF (100x) in order to get around only a 1% loss in the sensor's signal charge.


high hitrate, limited IO, not all hits read, but don't know which until tracker informs. 

majority of hits never read out, but we can't know which hits to discard until we recieve the tracking data. Can't read out all though as digital IO limit. Therefor a huge amount of chip are and space is spent holding the potential hit data in memories, which then are mostly discarded when tracking data is recieved after a fixed delay. Some people have investigated different ways of acquiring simple tracking information on-chip, so that a larger portion of the hits can be discarded immediately.



The reason the first bit of measurement in the discriminator is so high precision is that we are just using the device for tracking. Energy resolution is just a secondary feature, mainly used for calibration and characterization, with the built in injection circuit

---

# Long 'detector signal chain essay'
The purpose of this essay will be to study and quantify the design space of pixel detector systems, including the creation of a FOM. It will draw upon comparisons with other data conversion circuits like Image Sensors, ADCs, and TDCs.

To do this, we must build a model or incident radiation's interaction with matter. This model is in contrast to the discipling of 'gaussian/geometric optics' where beams of light are geometric light rays. This has the concept of [focal and image planes](https://en.wikipedia.org/wiki/Cardinal_point_(optics)#Focal_planes), etc. (Focal plane is the same as image plane but just in case on image coming from infinity.) By contrast are interested in single quanta detection. The other domain of this is the detection medium, which we'll model with a staring/plane array.

What we need to do is fix a temperature, a sensor material, and incoming particle type/energy range direction and radiation environment.

Then we create parametric limits on the thickness (to ensure energy loss doesn't dominate resolution of measuring particle direction, momentum, and energy.)

What resolution on energy does the calorimeter provide? Can a tracking sensor ever provide that?





A detector, vs imager, is something which has the concept of 'detection efficiency' take all the way to the quanta. We want every incident particle interacting with the sensor, and generating signal charge.



We want to measure particle kinematics, so particle direction, momentum, and energy. But we need to strip down and simplify this model to the context of what is definable in a single chip. We're going to abstract away the dimensions of:
- multiple layers increase in precision
- mass's decrease on precision
- recovery time/bunch crossing effect on pile-up/and  -> probability of loss of detection

So we'll essentially compress it down into: power budget, mass budget, detection efficiency by setting a limit below which these parameters will not be the bottleneck on performance.

The first constraint is precision for a single particle, passing through a plane array sensor. 

Basically, you want a high detection probability (low noise, )


There is a correspondence/connection between:

**Detector**: granularity, ENC, detection efficiency, timing resolution, timewalk, power per cm^2

**Imagers**: Noise Equivalent Quanta, Detective Quantum Efficiency, and Quantum Effienciy.

**ADCs**: Technology (getting better or worse?) vs architecture front, ENOB, Nyquist limit, fundamental limit on kT noise, 

* https://www.analog.com/en/technical-articles/a-12-b-10-gss-interleaved-pipeline-adc-in-28-nm-cmos-tech.html
* https://ewh.ieee.org/r5/dallas/sscs/slides/20120829dallas.pdf
* http://www.hit.bme.hu/~papay/edu/DSP/adc2000.htm
* https://www.youtube.com/watch?v=doTHd0W9QhA

In general, arbitrarily high resolution is achievable up to the noise floor, at the maximum single stage speed can be achieved, if you if you are willing to spend more power via pipelines. Put differently, pipe-lining is a way to improve resolution, at a fixed speed, by spending more power. It is limited by device noise, most probably dominated by the those in the first stage. 

Double sampling, flat-field correction, dark frame subtration, noise shaping, and oversampling are a way to reduce noise, by taking subsequent measurements. Correlated double sample is primarily to fixed each pixel's offset (although it does a bit of noise shaping), just as flat-field correction and dark frame subtraction.

* Dark frame correction corrects variations in thermal noise, which originates from lattice vibrations, and occurs every when there is no signal exposure. In devices where charge is passed from pixels, pixels at the end of the chain will have worse additive thermal noise as they are bucket brigaded the longest along the array. In images this is possible, because images are integrated, and so we will be able to measure a higher than average noise power over the integration period in those pixels. ADCs, the equivalent to this thermal noise problem is solved by noise shaping, where again multiple measurements are averaged to improve confidence in the measurement. This comes at the expense of added power (I think, obviously?) as you must oversample.
  * I'm not sure how the 'order' of the noise shaping affects this.
* Flat field correction, in turn, fixes sensitivity variation which originates from random offsets in the devices, but not dynamic noise sources, typically. (Of course this will change with environmental conditions and radiation damage, etc.) 
* In imaging, the additive error (dark current noise power) and multiplicative effect are removed via the expression $(input-dark)/(flatfield)$. Notes that the input frame and dark frame should have had the same exposure time.
* Note that these are post processing techniques, not in hardware, and that they are both removing 'fixed pattern noise' in the sensor. The hardware equivalent to this is pixel calibration techniques, although this mainly applies to sensitivity i.e. threshold tuning. I don't know if there's a good way to correct 'hot pixels' as detectors are inherently single shot. I think that this latter parameter is expressed as ENC?

 For example, if a single stage has an uncertainty, 

The can be done either by improving a single stage, or by chaining 

I'm adding TDC's in here, because their single shot precision requirement helps me connect to 

Also, I think I can take an ADC and reduce it down to a 1-bit design, in order to better compare it to a detector.... Meaning I can look at the charts of ADCs, but at the 1-bit level to understand the theoretical limits?

>  What is the poisson limit? The Poisson limit is a statistical concept that describes the behavior of a counting process when the number of events being counted is large and the probability of any one event occurring is small. In this limit, the counting process can be well-approximated by a Poisson distribution, which describes the probability of a certain number of events occurring in a given time period or space. 
>
> In the Poisson limit, the variance of the counting process is approximately equal to the mean of the process, which means that the standard deviation of the counting process is proportional to the square root of the mean. This has important implications for the measurement of low light levels, as it means that the signal-to-noise ratio (SNR) of the measurement is proportional to the square root of the number of photons detected.
>
> For example, in a typical photon-counting experiment, the number of photons detected in a given time period will be proportional to the intensity of the light source multiplied by the detection efficiency of the detector. In the Poisson limit, the distribution of the number of photons detected will be well-approximated by a Poisson distribution, and the standard deviation of the number of photons detected will be proportional to the square root of the mean. This means that as the intensity of the light source decreases, the SNR of the measurement will also decrease, and the measurement will become increasingly noisy.
>
> The Poisson limit is an important concept in many areas of physics and engineering, particularly in the measurement of low light levels and the detection of weak signals. Understanding the Poisson limit can help researchers to design experiments and instruments that are optimized for low light-level measurements and other applications where signal-to-noise ratio is critical.

In pixel detectors, ENC or Equivalent Noise Charge (ENC), which is defined as the
input charge for which the front-end Signal-to-Noise ratio is equal to 1. It's not 'dependent' on input charge level, because it, itself, is specified at a certain input charge level. But perhaps it's dependent on the threshold level? Yes I think it is. So we can compare the 

| Parameters | ADCs | TDCs | Imagers | Detectors |
| -------- | --- | --- | ----- | ------- |
|            |       |       |         |           |
|            |       |       |         |           |
|            |       |       |         |           |
|            |       |       |         |           |
|            |       |       |         |           |
|            |       |       |         |           |

This might be worth a read: https://ieeexplore.ieee.org/document/5204577/

More importantly though, I want to examine this paper from Andrea Galliani: https://www.mdpi.com/2079-9292/12/9/2054

I met him at CERN! This would be super helpful, as it would allow me to compare the performance of such a design against that I can do with a VCO. I need to look at the linearity, speed, size, signal to noise ratio, etc. It's only 6.5 um by 22.5 um! It consumes 2.2uA, which works out to 2uW off a 0.9V supply.

A... also rivetti's groups is at it as well: https://iopscience.iop.org/article/10.1088/1748-0221/17/03/C03022 It uses 1.2-> 2.5 W/cm^2:

> The Timespot1 ASIC has been tested in standalone configuration. The TDC resolution is below
> 50 ps, with an average of 23 ps. From the point of view of the AFE the resolution has been
> quantified to be under 100 ps with an average of 43 ps. All measures have been performed within
> the specified power consumption constraint of 40 μW per pixel. The tests illustrated in the present
> paper show the possibility of improving the performance of the proposed architecture with minor
> corrections. Measurements with the actual sensor matrix and particle generated signals will be
> performed in the near future.

# Discoveries

VCOs **have** been used for CSAs in detectors: https://oparu.uni-ulm.de/xmlui/handle/123456789/3224;jsessionid=123DA682C20AD08FC79D12EFCDEFCD98

And here is an interesting paper, talking about similar problems but for mass spectrometers: https://nano.lab.indiana.edu/wp-content/uploads/2020/07/Todd_2020_JASMS.pdf




# Alice power consumption

In Alice, 

One statistic: In ALICE, water cooling is not needed if power consumption is < 20 mW/cm^2



# Monopix2 Notes

* The resistivity and the voltage determines how much you can deplete. Depletion is necessary because it allows all of your signal to be swept by drift, rather than some of it being collected by diffusion.
* The limit on voltage is the punch through effect, where the diode break down. Is this the dielectric breaking down? 

* Ivan Peric first published work on HV-CMOS, where people said 'well it doesn't matter if you have high-resistivity, because we can just apply a large external voltage to modern processes

* Other people, around the same time (2005-ish) said, whoah, wait, what if you just tuned the resistivity, but doesn't use a high voltage. They created what's called "HR-CMOS" detectors.
* These two detectors camps acted similarly after being irradiated, but did differ some during the beginning of their operation.

* Over time, these two MAPS camps have come together, and the byproduct is detectors with both HR and HV. Primarily these ones of interest are TJMonopix and LFMonopix/MALTA. (MALTA is essentially the same, but has had peripheral circuits designed.) Dr. Norbert Wermes likes to call this 'DMAPS', or Depletable Monolithic Active Pixel Sensors, as the combination of HV and HR allows for full or near full depletion.
* The Czochralski (CZ) method is a way to make substrates. It can be used to make high or low resistivity substrates. The alternative is using an epitaxial layer, which allows for a high-quality but thin layer of high resistivity material to construct a portion of the diode.
* LF monopix
  * Large fill factor, RO electronics are actually inside the collection node, which is sort of 'underneath'
  * Rev2 versions tested are backthinned to 100um thick, to reduce material
  * uses a standard CSA, as the large collection format creates a large pixel capacitance (~250 fF).
  * Power consumption of 370 mW/cm^2 or 28 uW /pixel. 
* TJ monopix
  * is a Small Fill Factor design, which has only a portion of it's pixel area action as the collection node.
  * Electronics are fully seperated from collection node
  * Process modification used to enhance charge collection ability... I this the epitaxy?
  * Additionally, it is a bit strange because it has two opposing voltage applied, rather than one large bias voltage. (How big is this voltage?).
  * One issue with this is the fact that small collection node causes some areas to be far from the node, and the horizontal field isn't strong enough to sweep up the charge properly. 
    * Some process modification, with either an opposite doped region, or just no epitaxial deposition (allowing regular p type to remain) counteracts this by removing the areas that were previous acting as dead-zones trapping signal charge
  * Uses the concept of 

Talking more with Ivan, there were three original flavors. 180nm from AMS/TSI, which has been led by Ivan Peric, and which became ATLAS pix. (peric also made Deptfet and FEI3) It has been customized for many different applications now, all under the HVCMOS label. Then there was the TJMonopix/TJMalta which family which started at CERN, in ALICE, and as a non-rad hard design with epitaxial layer (not called TJ), but then which received process modifications (intermediate n layer and end stops) to become the rad-hard TJ family. It was worked on by Ivan,It competed with ATLAS pix for the outerlayer of the ATLAS HLC upgrade, but neither won, as the whole ATLAS detector is now just RD53. The only potential outlet for TJ technology now is the Belle upgrade. This is called the 'Obelix' project. Finally the LFMonopix family, which doesn't have any process modifications, and which is large fill-factor like ATLASpix. This design has been tested in a  progression has been the major responsibility of Toko, Ivan, and Lars.

I should check who worked on what, like Kunis, Kostas, Piotr, Tomek?

#### Questions:

* Is the TDAC in both LF/TJ reused across the entire array? How is that calibration done? Is this essentially just 'flat-field' correction from basic image processors?

* What exactly is the punch through effect?

* What is the power consumption per pixel and per cm^2 for RD53? How does the width of the sensor stack compare?

* Christian is testing...if the epi layer is fully depleting?

* What is 'collection efficiency?' How does it relate to charge trapping?

* What is threshold overdrive, how does it relate to speed, and why is it measured in electrons?

* How does the size of a capacitor affect noise? What is 'equivalent noise charge'?
* Threshold dispersions/tuning (~100e)
* How does a beam telescope work? How do you ensure even energy of particles hitting the sensor? Is it one particle at a time, or a calibrated and continous fixed flux? How does a beam telescope differ from 

* For time walk calculations, is the 'seed pixel' considered the pixel with the highest value hit, and assumed to have 'no time walk' as a reference?



I'm reading about Noise Equivalent Quanta, Detective Quantum Efficiency, and Quantum Effienciy. The difference is, these are imaging measurements. We are no-fundamentally 'imagining', because we aren't reflecting particle off something, to measure something else. We want to learn about the particles themselves. This means our system measurement is 'single shot'. We don't to take another frame, in order to improve SNR. (Or do we??..) Also, we have radiation to deal with, and the fact that our measurements are 



# Pixel Detector Figure of Merit

"Imagers with larger numbers of pixels are considered to offer superior  spatial resolution, for example. But in order to increase the pixel  number without increasing the chip size, the size of pixel is reduced.  Does this imply finer details in the resulting images? A small pixel  also means less area for the photogeneration process or a loss of signal strength. In addition, smaller pixels may have higher cross-coupling,  so what impact would it have on image quality? Also, how do common  parameters like signal-to-noise ratio (SNR), dark current, fill factor,  full-well capacity, and sensitivity interact with image quality? Is  there any imager performance tradeoff involved among different  categories? How can one tell which imager has a better design?"

Basically though we can boil it down to spacial resolution, temporal resolution,  and dynamic range. But there is a complicated interplay between these.

But also power needs to be part of this.

For example, if pixels are smaller, more charge will be shared between  adjacent pixels when a particle hits, which produces signals closer to  the noise floor and with slower rise times more susceptible to jitter.  But also, quantization noise is reduced, as the nominal pixel size is  decreased. Ultimately we will be limited by the larger of the two error  sources, and so one must not be singularly focused on improving one at  the expense of the other.

One beautiful  interrelation of detectors is that the power dissipation limit is  directly derived from spatial noise limitations, because cooling systems add mass that increase multiple scattering.

Probably Assuming analysis on a certain recovery time for the pixel and on a  certain technology is necessary, as otherwise two much differs. Perhaps  the design should also be fixed to a certain sensor tech, and only  consider 








## from RD53A Specs 2015:

"following discussions with ATLAS and CMS sensor developers, for RD53A we have assumed sensors have less than 100 fF per pixel and deliver a single pixel signal greater than 600 e− in at least one pixel for 99% of incident particles"


* 4uA per pixel in analog circuits
* <1 % hit loss from in pixel pile up
* noise occupancy per pixel < 10^-6, for 50fF load, in a 25ns interval
* <500mA/cm^2 limit, so 0.6 W/cm^2 if it were at 1.2V supply
* min threshold of 600e- and min in-time (<25ns timewalk) threshold of 1200e-.
* all these specs must be met at 500Mrad dose

signal to noise ratio: quantization noise and jitter/noise can be combined into one measurement

pixel pitch/area may also be able to be combined into this parameter too, as the spacial resolution of the pixels ultimately just allows for

It looks like, depending on the mode of operation, about 600e- of resolution and >= 4 bits of resolution are needed.

At a 600e- input threshold, 99% of hits are detected, within 25ns, and 

At 900e- threshold, 50% of hits are detected in any time, and at (+300e-) 1200e- 50% of hits are detected within 25ns. Only 1% of hits are allowed to be lost due to pileup. And with this threshold, only <10-6 of hits can be false positive.

10^-6 probability of false hit corresponds to a Gaussian tail beyond 4.75σ, with a 600e- threshold this gives us an input-referred ENC << 126e-. (<< as threshold dispersion across the chip add in quadrature). So think like 70e- ENC.

Total recovery time is <1 us.

Assuming 25ns bunch crossing, we have a 40 MHz operating frequency. The TOT speed is 40 or 80 MHz, and has a 4b readout.

Let's assume a high-resolution TDC (TOT or TOA) in-pixel; ideally on the order of 10-40ps RMS. It should be the input jitter of the signal will be around 50ps RMS. 

> Hit rate: up to 3 GHz/cm^2 (75 kHz average pixel hit rate). This is less useful for considering pileup, but is good for knowing digital link capacity needed.

The TOT was designed with a 4-bit counter (16 total counts). By setting the counter rate (40 MHZ) and return-to-baseline dissipator (respecting pile-up limits) we can tune how much input ke- corresponds to which bin. So for the first 8 counts, we want to reach 12ke-, for a gain of 1.5ke- per LSB in this region. For counts 8-15 though,  (above 12ke-) the gain increase by 4X, to 6ke- per LSB. 1.5×8+6×8 = 60ke total dynamic range, therefore.

With this system, the quantization noise LSB/2 = 750 e- (midrise quantizer) is going to dominate the input noise. The input noise is like ~100e?

But remember the system isn't just a charge and TOA digitized, it also needs to reject false noise hits below a certain threshold. This is unusual from a circuit perspective.

# Explainer for in-time threshold

In-time threshold, means a hit which can be correctly assigned to the correct 25ns bunch id. Hits close to the threshold may take a long time to be detected.

![Alt text](images/pixel_intimethresh.png)

In this example, a signal will be detected with 50% probability if it is 3000e-, but assuming any time delay is permissable. If we instead want to have that within 20ns, we find the 50% detection probability at that point is 1.7ke- (overdrive) higher at 4700e- at the *in-time threshold.*

## questions:

* are the values for threshold (i.e. 600e-) input referred?
* why is power limited to 0.5-1.0W per cm^2?   A: Because of the 

### Some calculations from the above

In a 1cm^2 area we have 40,000 pixels w/ 50um pitch
Therefore, given total power of 0.6 W/cm^2, so we can spend around 0.6W/40000 = 15 uW per 'pixel'.
Of course, the pixel has some digital periphery, and power is lower when there is no hit. So assuming that only 5uW can be consumed by the analog, 

## Power, cont:

* Pixel energy consumption inactive baseline when no in-pixel hit arrives

* Pixel energy consumption rise per hit (for a certain size, above threshold) actually doesn't matter, what matters is how this then dissipates into heat, which limits the pitch of the pixels. We don't want to conserve power, we just can't exceed our thermal limits.

Actually no, the power consumption should not simply be blindly reduced. Power consumption is a budget for performance! So assume a constant maximum power budget?, and simply optimize the best ways to spend this budget? Or perhaps increasing the decreasing power budget does actually improve performance, because mass matters?


Deadtime? Is there any need to have pixel dead times less than 25ns in the application of the LHC? 

Assuming each pixel produces data with the same number of output bits, we can therefore assume a fixed amount of area is necessary per pixel for data read-out, and we can abstract this

Should radiation hardness be a factor? Or should be simply just perform our measurements after a certain amount of radiation damage? I think the latter case is better.

Assume a standardized jitter for clocks available across the pixel matrix

# More basic approach

To optimize the circuit, I need a good equivalent circuit model for the characteristics of the signal, including noise, distortion, and detector capacitance. I know that the most basic detector is a PN junction? Or is it?

In any case, once I have an equivalent model, I believe it will be in the form of a current source with finite output impedance.

My goal is to measure the integrated area of a pulse, relative to some baseline.
Once issues with that is processing time. I have to observe a signal to it's completion to make a statement about it's integrated area.
There are different camps here. On camp integrates (accumulates) in a continuous fashion, and then measures (digitizes) the integrated quantity
Another camp integrates in smaller intervals, relative to the system dynamics, digitizes each, and adds up the result.
Image/video sensors are a example of the latter, as the signal of interest is generally continually present and varying, and so the system just defines a rate for sampling, relative probably to the rate of dynamics in the light signal of interest. If you're interested in faster changing events, you have to sample faster.

What does sampling theory tell us about pulse signals through, localized in time. Are we still faithfully trying to 'recreate' that waveform? Perhaps not.


# Comparison of RD53 Front-ends:

https://agenda.infn.it/event/22737/contributions/113830/attachments/72078/90767/2020-04-20_RD53_frontEnds.pdf

https://www.mdpi.com/2079-9292/12/9/2054

https://indico.cern.ch/event/806731/contributions/3503810/attachments/1926267/3188644/vertex_gaioni.pdf

# Things I'm interested in exploring:

The pixel detector system is interesting.

- It's asynchronously triggered, but needs to be well calibrated across an entire array.
- It doesn't integrate hits over time, but instead need to have single hit sensitivity
- Again, it's asynchronously triggered, but has a 25ns window in which it is free to digitize the signal. This means a signal *can* be freely expanded into this window.
- The initial threshold of ~600e needs to have a high precision, in that input noise referred noise must be < ~75e (<10^-6 errors, accounting for noise and static/dynamic threshold dispersion). Does it make sense to talk about a SNR here? What about a resolution or a LSB? It's a 1-bit quantizer?
- But then the subsequent conversions of higher amplitudes are of a LSB of around 1.5 ke- with 5-6 bits. What's the noise spec here? I think the SNR is like 35dB?
- And furthermore, there is a potentially a TOA digitization which is being maybe desired. This would have maybe a 1-2ns dynamic range. The input jitter would be arond 50ps RMS, with the TDC capable of around 20ps RMS.

*Therefore:*

- Can a VCO be used as the initial integrator? Let's examine it's transfer function. It's a leaky integrator, and can have a very high gain.
- If we still need a miller capacitance, perhaps we can still use the digital VCO output to create one?
- Can we reuse the high precision discriminator (1-bit quantizer) for subsequent digitization. I'm thinking something like an asynchronous delta-signal modulator. Measure change in input signal in unit interval, digitize with 1-bit quantizer, then feed this back to input to
  - digitally subtract from VCO output, if using that
  - or use DAC to convert to voltage, and analogly subtract from CSE output (which is buffered)

# making sense of SNR and ENOB

For ADCs, it doesn't make much sense to specify the dynamic range often, as an input signal that is out of range can simply be amplified to fit within the full scale input range. (This amplification has some linearity(distortion) and noise penalty of course.)

Therefore we often compare converters at some nominal input signal range.

SNR of a signal make sense. But for a data converter, you need to essentially fix an input signal level for which you desire to measure. For example, if you have a TDC where you can add as many delay stages as you want, if you don't scale a signal, having more stages won't help, and if you do scale (amplify it), you will reduce the dynamic range while 

There is a reason dynamic range is not the most important spec to quote for a data converter, and that's because dynamic range is relatively easy to increase. For a TDC, for example, you can just add more stages. What doesn't come cheaply is LSB. 

> A converter’s differential linearity must be <1 LSB regardless of the specified resolution. Also, a converter’s integral linearity determines its distortion performance, so converters with higher resolution can achieve higher SFDR.

In SNR, you are computing a relative ratio; it's unitless. Therefore, 


# Bump bonding technologies

Indium
– small: 20μm pitch, 10μm diameter; electroplated
– soft, low soldering temperature (<180°C)
Goldstud
– 50μm diameter, 70μm pitch
– modified gold ball/wedge wirebonding process
– slow sequential bumping process; high force flip-chip; >300°C
Solder
– minimum: 20μm pitch, 15μm diameter; standard: 200μm pitch / 100μm dia
– Chip-on-Board: 300-500μm diameter
– evaporation, electroplating, screen printing, ball drop, jetting
– Eutectic, High-Lead, Lead-free solder alloys; >200°C soldering
more...
– Cu-Pillar
– Solid-Liquid Interdiffusion (SLID): High Temperatur (600°C) applications

# TSVs

Redistribution layers are a post metalization layer which can be used to remap the spacing of top metal traces, either in 3D or 2D integrations. They're being using for Obelix, but not for thin hybrid.

What is the difference between a DMAPS sensor, and a DEPFET? Is front gate, vs back gate amplification the only difference?

Via last technology is being used for the thin hybrid project.

Bonding and thinning of entire wafers is done before dicing.

Minimum TSV pitch in the IZM process is 20 um.

There is filling between wafer bonded layers, which is typically poly-silicon? (maybe?)

chip and sensor in bump-bonding are 300um and 150um respectively. With wafer bonding and TSV, the chip and sensor can be thinning to 20um and 100um, respectively.

# Guard rings and sensors:

On the sides and tops of the chips, surface damage occurs which reduces the impedance and causes super drastic transitions in the field strength, which can lead to breakdown. Oxide breakdown is at ~700V for a 300nm thick oxide, or 7V for a 3nm oxide.

Guard rings help smooth this transisition in the precense of defects, to avoid breakdown. 


# Questions:

Can TSV and wafer bonding (thin hybrid) be used with Silicon only, or also with Ge, GaAs, CdTe, Diamond? TSV and wafer bonding (limits on process?) Available in 28nm or 65nm?. It looks like maybe so: With 'Vist-last' TSVs provided by CEA-Leti and Fraunhofer IZM. Bonn-IZM project is already in this vein.


It's [often said](doi.org/10.1088/1748-0221/11/01/C01007) that TimePix chips are for spectroscopic X-ray imaging, but I don't understand how their counting discriminator can perform spectroscopy. Perhaps as it can look at TOT?

Where do the wafer for ATLAS come from? Are they LFoundary based?

When we say 'back-scattering' is bad, is this in the sensor volume? Can we improve this by thinning the sensor but having bump bonds? Despite this supposed issue, there appear to be several examples of hybrid-detectors which are 

How to integrate with Allpix? Can Allpix be used to Xray and Electron detectors? How does it compare with Pyxel or Fluka 2005?

Is CdTe used for Xray or electron? -> For X-ray. Silicon or High-Z are used for Electrons.

What is the architecture of TJMonopix and LF-Monopix. -> I know, at least, that LF has flip-flops in pixel.

Are digital CMOS image sensors now the state of the art? How are the three layer stack chips organized? Is what happens before the DRAM?

Why is silicon Depfet used for EDET? How does it compare to what Dectris is doing? -> Dectris uses Silicon and High-Z, in hybrid bump bonded mode.

Is silicon DEPFET essentially just equivalent to an APS array? How about a 

Is the counting vs integrating perspective accurate? When to use which?

Let’s look at Peter Fischers presentation again. Was he making direct detection, counting optical photon ROICs?

What other companies are in the same space as Dectris?

Can we really not vertically integrate the EDET ROIC? Timepix3 and Dectris chip have been successfully used for direct electron detection in a stacked mode.

Dectris Arina appears to be the high frequency (120kHz) X-ray detector, with the KITE ASIC. I can 'count every single electron, up to 10pA/pixel' and has 'noise free readout'. It has Silicon or high-Z sensors, with 100um pitch. 192x192 pixels with 20mm x 20mm sensor size. It uses hybrid-pixel technology. KITE is the ASIC behind ARINA. '10us dwell times' 10^8 el/s/pixel.


Epitaxial wafer, vs Czochralski, vs SOI
3 layer process



# Early notes from Asianometry video
CCD in invented in 1970s
companies get it: GE, IBM, hughes, TI, RCA, fairchild, philips, hitachi, thompson, intel, sony
CMOS first started in 1960 (IBM 1964 scanister)
19060s 1st gen was passive pixel technology (1T per pixel, a passive switch). But a small charge, into a big wire, means lots of noise.
Hitachi tried for the longest, but flicker noise was a problem
1990s presented 2nd gen APS, as fabs caught up to make multi Ts per pixel
JPL's Eric Fossum created the photogate APS and correlated double sampling
Fossum then commercialized as Photobit, aquired by micron 2001, aptina spin off, then re-aquired by ON semiconductor in 2014.
Early fill factors were as poor as 26%, compared to CCDs 100%




# 21 december 2023
I. MacLaren, 2020, https://doi.org/10.1063/5.0026992
DEDs allow the 'whole back focal plane' to be captured
abberation correction was known but not achieved until 2000, which revolutionized both imaging and spectroscopy with TEM, allowing direct imaging of atomic lattice in crystals, and very thin non-crystalline materials
abberation correction also allowed increased beam current
geometric vs chromatic abberation, johnson noise -> these limit spacial resolution
k-space information can be obtained from angular-resolved scattered electrons

What is the 'back-focal plane' of a probe?

Electronic readout (in 1 dimension) first came to scanning, but even in this domain, useful information in the surrounding area of the beam exists (annular dark field and back-scattered diffraction patterns) and so we'd benefit from having 2D sensors in this area.




# noise, etc on Jan 1 2024
Mode of operation of detector affects how other noise sources contribute

dark current andnoise: can be fixed by dark subtraction, I guess this is just the 'baseline' leakage?
landau noise: variability in deposited energy (happens in integrating sensors, can be normalized out by counting sensors)


readout noise: (can be removed by thresholding?)


shot noise: temperature/frequency independent, applies to DC currents and HF alike (white noise). Therefore, at low temperature, as high frequencies, the shot noise may dominate, as flicker and Johnson noise reduce.
flicker noise (pink, 1/f noise): spectrally dependent, decreases with frequency 
Johnson-Nyquist (thermal) noise: increases with temperature

Normal shot noise is the square root of the signal? Something like that.

fano factor is a correction term to shot noise processes, which fits (recudes) the shot noise (which normally has a variance = value) to physical processes where one particle is producing others. For examples, charged particles creating ions in a gas, charged particles hitting a solid state detector, or visible light hitting a CCD or CMOS sensor.

In the case of a metal wire, the mutual coulomb repulsion between electrons regulates their spacing, and so there is almost not shot noise. But in cases where the carriers individually overcome a potential energy barrier, say a PN juction, this repulsive-cancellation doesn't occur.

Shot noise is distinct from thermal (Johnson-Nyquist) noise, as the latter occurs even without DC voltage or current flowing.  For example, a disconnected resistor, at thermal equilibrium, still internally has Johnson-Nyquist noise. However both are white noises, as so are difficult to disentangle even through their physical origins are different.



# measurement types:

- test beam w/ beam telescope
  - measure spacial resolution, relative to telescope track (rasmus)
  - temporal resolution, of time stamp relative to trigger logic unit
  - efficiency (% of hit) (is there a hit, where there is supposed to be one?)
  - noise occupancy (false positive)
- in-pixel injection
- injection + xray beam
  - pile-up testing
- xray beam
- desktop souce
  - spectroscopy lines?
- neutron and proton and x-ray irradiation
  - irradiation with neutrons to 10 15 n eq cm −2 NIEL (portion of energy that doesn't go into ionization, but displacement damage)
- sweep the intjection charge, to tget a per pixel threshold, then calculated chip wide
- general func
- pileup
- timing
- dispersion and temporal dispersion

# newer notes

Gatan K2 vs DE-12

At 2023 IWORID, [McMullan discussed](https://indico.cern.ch/event/1247911/contributions/5404765/attachments/2674086/4636395/iworid_2023_mcmullan.pdf) Timepix vs Gatan (K2/K3), Direct Electron (DE20), and ThermoScientific(Falcon)

Hybrid integrtion, used by CERN Medipix/Timepix, Thermo Fisher EMPAD, JEOL 4D Canvas, Gatan Stela,
Dectris QUADRO/ELA, ASI EM – CheeTah , Quantum Detectors Merlin EM [as shared by Amit Kohn](http://www.ismicroscopy.org.il/ism2022/files/2022/05/03-ISM2022-pre-meeting-workshop-Amit-Kohn-Cameras-and-Detectors.pdf)

Monolithic: Gatan K3, Thermo Fisher Falcon, Direct Electron DE-12, DE-20, etc


# older
Essentially, we need to look at the single shot precision/dispersion of the threshold, expressed in input referred charge, rather than, rather than any sort of continuous time resolution.
This is going to matter more based on the noise of the system, then the 'number of the bits' of the output, as not all systems have output.
All of our systems are 'single-shot', but readout can be either frame-based, or event based.
	If event based, the 'dead time' is the 'data rate'
	If frame based, we take the frame time as the data rate

Like data transfer systems, we must compare the system at a certain 'error-rate', and at a current hit rate (data rate!)

A low threshold improves detection efficiency and timing precision (from time walk), but also increases noise hit rate. In general, for timing precision/time walk, if we know what our minimum signal is, we can specify 99% of Siganl mxt be >2 threshold


The dispersion (pixel to pixel variation), even after calibration, limits how low you can set the global threshold.


dynamic range
Noise / precision
input energy → signal gain TF (not including sensor)				With hybrid, pair them with an ideal sensor, for DEPFET and monolithic, keep it seperate.
				
Power consumption unit area
Maximum hit rate (is this the same as dynamic range)
				
				
Need to be able to comment on DEPFET peformance.


thoughts on FOM:



Don’t try to mechanistically model, the intermediate components of the system, just look at the aggregate performance. Then simply categorized by type of architecture to understand how different architecture and performance.

Examine the aggregate performance between the signal at the collection electrode, and the point at which the signal becomes digitized.


Don’t be fooled by thinking DEPFET is something particularly special. It’s just an integrating sensor. I do need to understand how to compare integrating sensors versus pulses reset sensors.

But again, to reiterate, from Signal and systems perspective, there is no difference between an increasing current as a function of input charge, or an increasing voltage as a function of integrating input charge.

The way that I deal with an integrating front end versus a pulp front end is the fact that there are not a property of the system I am trying to characterize itself. They come before. I’m looking at a system from the performance perspective of the initial signal after sensor, either occur or voltage be at a pulse or an integrating curve. Then, with no respect to the input signal I’m going to characterize the transfer function of the black box system then I can double back to the characteristics of the input signal, and show how different systems extract the characteristics of these pulses better . 

In reality, this will be a difficult thing to calculate, because most systems are characterized in ag Their actual sensor. But perhaps I can disentangle we’ll see.

A pixel detector is a signal processing block that takes as an input, a pulse or rising curve, and yield three different measurement classes out. One must must consider both single shot and continuous measurement precisions.


I care about the transfer function of area (energy) to digital, and time to 


If a front end has a count mode, but then a data-driven readout, you must interpret the deadtime/in-time threshold as the 'frequency' limit of the system.

Essentially a signal which has a limit on how fast it can measure particles, essentially has a limit on how 'quickly' it can observe incremental units of charge be added.


# further thoughts:

it doesn't make sense to account for anything before the transduction from incident particles to charge current at the collection electrode.

But I do need to account for the fact that there will be some background noise. This is the input referred ENC.


Taking many, many, many particles to improve an image is essentially 'oversampling'.

But if you need to have lots of samples, in a small amount of time, you need more dynamic range.

I think all that matters is the 'dispersion' and the 'bin size'


We won't care about charge sharing yet, and will only consider the simplest model of 2D geometry (the bin size) and pixel count (number of bins). There is such thing as optical gain and noise, so it's the same.

(In reality, late the position dependent charge sharing will cause problems in the other two domains. But for now we'll just look at one pixel, and consider the measurement of energy(spectral) and timing. 

Assuming the particle is centered in the pixel sensor, and the the charge cloud is placed a constant distance from the collection electrode.

The reason by brain is hurting is that knowing the noise and the threshold dispersion is not enough. They are still in the analog domain.

There are 'integrating ADCs'.

Threshold dispersion is the (fixed patter) variation from pixel to pixel, electronic noise is run time varitiation due to transient.

If we assume that the design of the detector is quantization noise limited.

We don't need, quickly, a precise measurement of a particle's energy  across a wide dynamic range. And so in scientific applications we can control our source signal, and so with the right gain setting, can achieve *essentially* noise free readout. As long as measurement times are relaxed, with a fixed energy source, we can improve our knowledge of the energy spectrum by slowly shifting a single low noise threshold.

This means that the real challenge is in understanding the characteristics of extremely dynamic systems, above 100 kHz.

If our beam is still monochromatic and known, 



I think, as most beams are monochromatic in energy, there almost no application in which measuring the energy of an individual electron or photon is necessary.

I recall reading about applications where particle hit rate must be limited. (perhaps biological samples?)



If the beam isn't monochromatic, and if our experiment is 'single-shot' then we get back to the world of interest. We can't repeat the same

Fundamentally, the energy of particles is quantized and fairly easy to control. And so the real dimensions of the system simplify to time and place. Energy is useful to understand the

In order to see something on a short time scale, without bluring, and to then observe that structure over time, we must

In the basic electron microscopy book, ultrafast time resolved electron microscopy gets just a short little section. This is because you can't create beams of electrons that are temporally clumped beyond a couple nano seconds. Therfore, you either need to relax you time bin, to improve your spatial measurment (via more particles) or via versa. state of the are is 10-100 ns and ~10 nm resolution.


I want to build the best detector possible for single particle imaging.


##

I'm not working on [Scanning mode, or diffraction based electron microscopy](https://myscope.training/TEM_Introduction_to_TEM)

Focusing in on [TEM](https://myscope.training/TEM_Introduction_to_TEM), there are many types:

- Standard (bright field, thin sample, not diffraction limited, no scanning)
- CryoTEM
- DarkField TEM (only considers scattered electrons)
- Scanning TEM (requires a thin sample, unlike SEM)
- Diffraction TEM (only makes sense with low rates, to build diffraction pattern)
- 


In material science, in situ TEM research is frequently used to study mixtures and colloids, metals and ceramics, catalysts, batteries, solar cells, electronic devices, nanomaterials, corrosion, polymers and semiconductors, and more. In the life sciences, in situ TEM has been employed for studying structural biology, protein transport, cancer therapies, cellular depredation, drug delivery, and particle reconstruction.



## optical microscopy

flourecense microscopy is:
20x magnification, equivalent to 0.325 micron per pixel



From images from Sascha Epp, in a 64x128 EDET testbed:
~500 nm of sample mapped across 128 pixels, so about ~4nm per pixel

In EDET, each pixel is 50um

Therefore, 4nm image section maginifed across a 50000nm pixel:
12500x magnification, with 4nm per pixel
