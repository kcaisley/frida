Here's the plan for designing my ADC:

I want to target 12-bit precision, as this is more generally useful, and it better places me compared the state of the art:

- Hsu 2013
    - Intro "Our goal is to create an ADC that runs faster than 10 MS/s at more than 10b ENOB, while achieving F oM lower than 50f J/conv.-step."
    - For FRIDA: 12-bit, 400uW, 10MS/s gives: `400e-6/(2**12 * 10e6)` = 9.7 fJ/conv-step
    - pg53: ENOB, SNDR, SFDR = dynamic metrics, while INL/DNL, offset, and gain errors are static metrics
    - pg57: even 1% mismatch will (given enough instances) yeild below 11ENOB in 12-bit ADC. Remembers that the static linearity sets the baselines ENOB, even if one runs as slow as possible.
    - Note that even at slow speeds, one needs a input switch, and then references and comparator which are all three designed to not degrade the precision substationally
    - Then after all of this, dynamic errors accumulate on top. But we're running slow enough that they should be the secondary issue?
    - Calibration: analog(tuning caps) vs digital forground (pre-measurement w/ RAM) vs digital background (doesn't interupt)
        - Within digital background calibration: injected calibration signal, adaptive equalization w/ reference ADC, and Hsu's statistical approach
        - for FRIDA, need to verify: Can we use Hsu' method III?, since we have a one-shot channel and we so we don't really have input statistics? I think Theuwissen 2019 might be an answer here.
    - Hsu' final arch was: IMCS switching, 4x repeated bits (16 cycles for 12 bit accuracy), bridge cap for shrinking arch, asynchronous operation with ready generator, and 11fF MOM caps with 1.5 pF total array capacitance
    - Hsu's measurement results were: 8.2b precision before calibration, 10.9b ENOB after. 2.1mW consumption for a FoM of 22fJ / conv step.
    - pg180 Hsu also talked extensively about stategies for the test chip and surounding setup. I should examine these before submitting.

- Wulff 2017
    - 28nm FD-SOI node, 15uW total power, with 3.5 fJ/conv-step at 20Msps, given a 0.7V supply, 0.003 mm^2 area (39um x 80um) with 9-bit design -> 7.9-bit ENOB
    - top plate sampling, bottom plate switching, with top plate wrapping around and bottom plate internal

- Theuwissen 2019
    - Cap redundant bits provide transient error correction with on-chip addition-only DEC, for settling errors of comparator dynamic offset (from drain-source voltage variations)
    - "In addition, a digital background calibration was employed off-chip to further improve the ADC’s INL and SNR, by calibrating the gain mismatches of each capacitor."
    - the DBC requires no extra hardware, and essentially works by buildin statistics in the output data

- Harpe 2022
    - Achieved 10-11 ENOB in 0.001mm^2, while staying below 
    - The thing I want to try is applying his idea, but incorporating sub-radix2 redundancy, async clocking, digital background calibration to enabled a high-density array without noise issues
    - Also, I might be able to run faster than 12-bit? Since redundancy doesn't just enable mismatch calibration, but also can correct transient errors from transient noise and dynamic settling?
    - Used 'dynamic logic' to reduce circuit size, I can do the same later-on
    - Harpe ran slow enough, and sized comparators strongly enough, and decoupled power supply well enough that transient noise and dynamic switching errors shouldn't be a big issues, which is why he didn't use redundancy. Then after this, the mismatch of the capacitors was essentially good enough for his target ENOB.
        - But I want to perhaps go for close to 12-bit ENOB, with small caps, and so I'm interested in adding redundancy to allow calibration of my small capacitors.

- JH Tsai 2015
 - doesn't use calibraiton, but achieves a small fast 10b design
 - They first split MSB up, using what they call SC-ADEC (split cap - addition only digital error correction), but it's the same as CC Liu 2015
 - They used a monotonic switching scheme, with the CRS, but also suggested it could be used with MCS from V. Haripasath 2010 (but this is a Vcm technique, so I don't think I want to use it)


- From collaboration: Currently targetting 12-bit in 16 steps
    - so I'd like to demonstrate that I can build a similarly or even more performant design with my own strategy

- The Cordia design:
    - Currently we have a 130uV noise, 30uW 2-3ns comparator, measurring 36x18um this wouldn't fit well in a 10-bit design, but would fit well under a 12-bit Harpe-style CDAC
    - also, given the speed, we could likely run a bit faster since 10Mhz = 100ns period
    - Note that (1.2/(2**12))/math.sqrt(12) = gives a quantization noise of 84uV. So our comparator has about 1.6x the noise it should to stay below the quantization. Can we simply 2.5x the power consumption, somehow, to get 1.6x lower noise? (using quadratic power fo linear noise improvement)
    - Also, did we not ever measure the capacitor mismatch or check the calibratability offered by the Cordia SAR?

- Garcia-Sciveres 2023:
    - "The reason why the digital-only isolation is better than the double isolation might be that the noise is coupling through the metal stack rather through the substrate. In this case the double isolation has a higher impedance analog ground that is easier to shake by noise coming from the metal stack."


# Others:

Bonn 2013 ADC
Firlej AGH 2023, 21.5fJ/ conv-step, 10bit 55Mhz, 0.048mm^2 area (560 μm × 80 μm), 9.45 ENOB
Forza 80kfps


- Ding-Harpe 2017 and CC Liu 2010 add doubled capacitors, which makes logic nice, but causes overage in codes
- CC Liu 2015 and JH Tsai 2015 fix this, by respecting total bit weights. I need to reach 


Webb 2024 - Matching Improvements in Capacitor Arrays for Precision Charge Redistribution SAR ADCs. https://doi.org/10.1109/ICECS61496.2024.10848714 Can email Webb to get a paper.

