# Intro.
- talk about chip design challenge, and in particular the design of high speed image sensors.
- I'm most interested in sensors for scientific imagining. In scientific imaging one is typically are interested in looking at very big things, or very small things. I'm interested in the latter, where:

# Slide 1:
- High energy electrons or x-ray photons (10s - 100skV) are used over visible lights, to improve the spatial resolutions.
- And the optics and sensor then work together to target spatial resolutions on the nanometer level.
- And so the main thrust in the scientific  of the past 20 years has been to build detectors with spatial resolutions which support that goal, mainly by reducing pixel pitch, reducing charge sharing which would 'blur' out hits between pixels, and making sure you then read each pixel with super low noises.
- This out well, especially if you cryo-genically freeze your sample today the field has managed to take images at the sub angstrom level which is pretty wild.
- What chips built for electron microscopy haven't focused on though is framerate. Images are taken very slowly, and if these is a concept of 'framerate' it's often to then composited from multiple angles to improve spatial resolution image.



- Frame-rate = time resolution. You can see the cool applications of this with slom-footable in visible light cameras, which has all sort of interseting scientific applications.
- If we could do the same with electron microscopy there are dynamic processes, mostly very small which are interesting to record over time. A key example here is in-situ and liquid-phase electron microscopy including nucleation and growth of nanoparticles, battery systems, catalysis, biomolecules, and organic systems.

So if we could maintain



# Side 2:

- But we can't simply take standard high resolution chips architectures and run them faster. There are two reasons this doesn't work with the typical architecture, considering the just the analog front end up to the ADC.
- 1. Could could try reduce the bit-depth of each ADC. But experimental applications typically require a certain contrast, and contrast depends on the number of particles you can count per frame. So we have to simply read pixels faster.
- 2. Sampling each pixel faster requires faster ADCs, or more ADCs. This takes extra power and area.
- 3. Data transfer and storage is a whole other problem, requiring multiple links and probably caching.

For context, we can see this actually play out in our mobile phones. The most common resolution is 12MP, which can be read out at 60fps. But if we want to take a slo-mo video at 240Hz, we're typically only get a 2-3 MP image. And you'll notice the individual frames of this 240Hz video are

- So let's see if we can find out, how fast can we probably go? Given the constraits of today CMOS imaging processes, and experiemental constraint on power, performance, and area what would the ADCs need to be capable of.

## Let's make a budget

Time for some back-of-the-envelope calculations, or to be more fancy 'chip architecture'.

How big would our detector be?
Assuming we want a 1024 array, and want it 2-side buttable to reach a 4k array, this means we just have

Reticle limit is on the order of 22x22mm

Small pixel pitches are generally good for spatial resolution, and the more pixels you can fit on a sensor of a given dimension the larger field of view you can also half of your subject. But due to our desire for high frame rates, and the fact that electrons self disperse energy in a spread region around the track through the sensor, we will limit our pixel pitch to around to 15 micro meters

Assuming a full reticle design, this gives us like 6-7 mm in the chip peripheray


- This bank of ADCs produces a 'data apacolypse'. For comparison, ATLAS inner tracker is ~10000 Gb/s but after triggering is only ~ 100 Gb/s? [check]


If I want 100kfps 8-fold readout with ADCs will cover my needs, if they run at 12.5 Msps: 8*(12.5e6/100e3) = 1000 pix/sec
But since I will do two columns per ADC bank, then not that I will actually need to stack 16 ADCs.

These 16 would probably need to fit in 3-4 mm at the bottom of the chip, and so a height of 250 um would be the max, with a double width of two columns so 30um.

This only gives ~7500 micro meters for each ADC, which is roughly the area of three analog islands in RD5A, 6 pixels in TJ monopix2, or a single pixel of Lfmonopix2.

We'll need about half the area for

To meet my target of 10pJ per conversion, I would need to consume just around 100uW, which is a factor 4x to 10x lower that what I see here: https://arxiv.org/pdf/2312.14592

Actually this paper shows that at 10MHz sampling frequency, the power is close to 100uW, so I'm convinced the power and area are possible.

We can find the energy though. If our caps fill half the ADC area, we have 3000um^2 * 0.5fF/um^2 = 750fF per branch. In monotonic switching one branches' worth of capacitance will switch to ground in total. Using the expression W = 1/2 * CV^2 and a supply voltage of 1.2. We have:

Energy = 0.5*(750e-15)*1.2**2 = 0.54e-12 or 0.5pJ. This is low!

The only question is, is 750fF per branch enough to reach 10-bits of resolution? We might need 30% more area, or so.


#### Serial link
Just as a note, depending on the link length and type it's common for power to be consumed at roughly single digit pJ per bit.


# Slides 3: Okay let's design an ADC:

I've focused on SAR ADCs

redundancy:
One of the massive challenges with noise and


So we have a performance, power, and area challenge here. Can we meet the budget?
As a technical note, the results here are produced from a mixture of SPICE and Behavioral modeling (using Verilog-A and Python).


# end notes:

Buffer and caching in SRAM and DRAM are something which will depend on application
Monolithic vs seperate provides addition challenges




300keV
cryogenically freeze
0.5anstrong spatial resolution, cryoem

pulsed electrons at 100k per second (shutter) (time clock waveforms)


Pixel matrix
- This determines spatial resolution
- 22um of full recticle available
- 10-15um pitch is good for spatial, any less is dominated by charge sharing
- This leaves 6-7um on the chip edges for other circuits,


remove facts before adding adding data rates and configs

One reason I find this quite cool, is that in all of intergeatef chip design this is really the only class of chip which has millions of sensors, and thus needs 1000s of adcs



#comments

focus on results, focus on methodology

- appears to be very difficult but feasible
- adc hitting 2 of these 3 have been made, but not all three
- an array this large has never been built

- Behavioral modeling


