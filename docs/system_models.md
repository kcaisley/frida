- Allpix offers pixel level simulation and TCAD integration, but to what degree does it allow one to diagnose sytem level issues, or even to optimize pixels?
- Verilator and CocoTb allow for testbenching and digital verification
- predict system level performance from device level models
- using (and writing where necessary) system level models
- are these models flexible and mechanistic enough that they could then be used for optimization and tuning of systems, as well as achitecture exporation?
- I need to examine the chip level studies of RD53, Monopix, and everything in-between.
- bottom up and town down generation fill different niches here.




# Issues:

## in-sensor
depletion depth and breakdown, field strength for drift, charge cloud generation, radiation degradation, temperature

guard ring construction

## signal path
noise, linearity, non-linearty/degradation due to temperature, power drop/integrity, radiation damage, ground bounce, substrate coupling, capacitive coupling, threshold dispersion

## readout 

timing closure, functional verification, SEUs, data bottle necking, power dissapation

different ending schemes, packet header overhead,


# applications:
codify decades of achitecture and characterization knowledge in system level modeling and optimization
RD53 future redesign in 28nm
obelix
DMC65

how long does a system level cocotB simulation take?
Can you connect Allpix and CocoTB? (this has sensor, amplification, and readout combined?)

think of the design that dominic did, how could we have already provided the infrastructure for that?


The hint is to understand different things that needed to be fabricated and measured to be sure they worked well.

variation of spatial resolution across chip (Rasmus)

gmsh/scare used for weighting field calc? Still need Allpix/Geant for charge collection sim?

different front end designs and coupling (AC vs DC coupling), 



measurement types:
- 
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


sweep the intjection charge, to tget a per pixel threshold, then calculated chip wide

general func
pilup
timing
dispersion and temporal dispersion