# EDET DCD + DMC

- EDET does time-resolved spectroscopy, does it measure after illumination?
- Good for study dynamics of chemical processes, protein folding.
- The spacial resolution of electron beam illuminated systems has already seen good improvements, I think down to the atomic scale?
- But 'real time' vs 'stroboscopic' imaging of system dynamics is still unsolved.
- 1Mpixel @ 80 kHz
- Backthinning + minimal support reduces multiple and back scattering -> good spatial resolution
- In pixel signal compression -> DR is single primary $e^-$, or from $100$ -> $8\times10^5$ $e^-$ (poisson limited)
- 



DCD is 8-bit, uses a 



Slides on early EDET system is [Epp VERTEX 2016](https://indico.cern.ch/event/452781/contributions/2297602/)

Main EDET sensor paper is [Predikaka TNS 2020](https://doi.org/10.1016/j.nima.2019.162544)

Full system is explained in preprint [Fischer TWEPP 2007](https://indico.cern.ch/event/11994/contributions/84416/)

## DCD

DCDe is an increased dynamic range version DCD [Peric TNS 2010](https://doi.org/10.1109/TNS.2010.2040487)









Particle detector for tracking are weird, as they don't form images, are single particle sensitive, and they are event-based triggering-based, rather than frame based

# AGIPD:
Hybrid system w/ bump bonds, 200um pitch, 

4.5 MHz (pulse separation of by 220 ns) for up to 2,700 pulses (total train 600 µs)
10Hz repetition (10ms), so there is 99.4 ms of spacing after start of new train

[](https://photon-science.desy.de/research/technical_groups/detectors/projects/agipd/index_eng.html)

EDET

# Cordia
at Desy



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



# DEPFET (BELLE II)

[](https://iopscience.iop.org/article/10.1088/1748-0221/6/01/C01085)

Stuff at linear accelerators
Stuff at syncrotron light sources

Are cyclic ADCs used in all of these?

Not considered (as they are trackers)

# Monolithic
OBELIX monolithic (BELLE II)
ALPIDE (ALICE)
TJMonopix
LFMonopix
![Ivan 2021](./image-6.png)
from [I. Caicedo 2018](https://arxiv.org/pdf/1902.03679.pdf)
Tangerine

0.1-0.7w /cm2 typical? Is this for monolithic or hybrid?
Obelix has no pll


# Hybrid Tracker LHC
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

