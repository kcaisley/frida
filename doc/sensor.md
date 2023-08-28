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

Some variations of the arch. are putting a current source in feedback with $C_{f}$, or placing a AC-coupling capacitor on the input of the amplifier. Also, placing something in feedback is a great way to also build a hi-pass filter, which eliminates the leakage baseline, and any left over signal.


# Images sensors:

Cyclic ADC is like SAR, but amplifier error signal instead of reference voltage

On sensor ADC, comes in 3 main layout configurations:
![Alt text](image.png)

The full-well capacity (FWC) is the largest charge a pixel can hold before saturation which results in degradation of the signal. When the charge in a pixel exceeds the saturation level, the charge starts to fill adjacent pixels, a process known as Blooming.

![](image-1.png)

