# Particles worth measuring

![](../../images/elementary%20particle.png)
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


## Applications What needs to be measured, and with what precisions

Discuss applications, and their desired precisions, what is limiting bottleneck right now

Explain sometimes the particle itself is work measuring, other times it gives implicit information about another

# Scope: My research interest

Systems that push against afformentioned bottlenecks by monolitic integration (w/ optimization)

Narrow in on particle detection for HEP and electron microscopes?

The intersection of the application and the system type leads us to examine the class of particle detectors: pixel detectors

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


![Alt text](notes/charon.png)

electric field can't be generated in metals, as the conduction and valence band are overlapped
there are no 'carriers'weighting field and shockely ramo theorem

Short article on epitaxial layers on top of substrate, for pixel dectors: https://meroli.web.cern.ch/lecture_CMOS_APS_epilayer.html


# From pixel charge to digital readout

Then explain, mathematically how an AFE is trying to extract certain deried measureable parameters from the signal waveform.

Connect this with the applications sensor above. (maybe even move applications areas down here, at least for those that fall under the scope of pixel detectors)

Don't get into the ideal transfer funciton or anything yet.
