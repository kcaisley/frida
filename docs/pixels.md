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


# Noise and other terms
[Lexicon of terms](https://caeleste.be/lexicon/)

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