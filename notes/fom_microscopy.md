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