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
    - Noise:
        - pg170: "In our design, we pick the total noise to be roughly equal to 0.15×LSB." This is exactly half the quantization error!

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
    - A 'modified conventional switching is used' (from Harpe 2011) but is low power since the caps are so small
        - Each side has 21 elements, with 9.2fF cap (C + C'), and 10Mhz, so power would be estimated as `2*21 * 9.2e-15 * 1.2**2 *10e6` = ~5uW
        - This is exactly on the money, as power is measured at ~5uW as well
    - Also, total capacitance for sampling purposes is simply the number of units times the (C + C')
    - Q: does monotonic switching, bidrectional, mcs, etc have a place here? Is my expected power just `2*75 * 20e-15 * 1.2**2 *10e6` = ~45uW?

- JH Tsai 2015
    - doesn't use calibration, but achieves a small fast 10b design
    - They first split MSB up, using what they call SC-ADEC (split cap - addition only digital error correction), but it's the same as CC Liu 2015
    - They then used a monotonic switching scheme, and add to their new technique called CRS, but also suggested it could be used with MCS from V. Haripasath 2010 (but this is a Vcm technique, so I don't think I want to use it)
    - pg9,sec C: the CRS and SC-ADEC strat can be independently applied to a given switching scheme
    - "The differential realization reduces the hardware of the DAC" by one bit, which confuses me a bit as I thought it was top plate sampling related
    - pg 5 "Over-/under-ﬂow removals are typically employed for designs that use extra redundant capacitors" which is why splitting the MSB is better
    - Is the base switching scheme monotonics, bss, or something else?

- Chen-Saynyal-Sun, BSS
    - Does Bss benefit here?
    - 

- D. Van Blerkom, Forza, 2021:
    - 40 super blocks, 20 on each side, with 1024 ADCs per superblock. ADCs run at 1.7 Msps.
    - Each super block services 64 columns, for 16 ADC per pixel column. With 416 pixels per column (per side), each ADC is multiplex to 26 of 416 pixels in the column.
    - To find ADC FoM, means the area of the ADC array is 18.54um * 64 columns = 1185um wide
        - I physically measure the superblock on my sceen to be 46mm wide, for a conversion of 25.75um real vs 1mm measured
        - I measure the 256 ADC block then at 19mm by 53mm tall -> 490um by 1365um
        - So for 256 ADC, assuming a square, uses 2612um^2 or ~50um by 50um, including digital section but not ramp generators
        - I think the ADCs only run full rate at 10-bit (since it said depending on row time), and since it's only 52dB at full rate
    - Also we can measure the 4x 6.25Gbps CML serializers and 1x 3.125GHz clock recievers to fit within 28mm*46mm or 720um by 1185um physical.
        - Area above indicates ~400x400um per TX and chip power budet below gives probably <100mW per TX channel
        - Consulting a random example paper: J. Poulton et al, “A 14mW 6.25Gb/s Transceiver in 90nm CMOS" 
            - This paper achieved 14mW RX + TX. TX potion is around 9 mW and measures 320um x 480um. So Forza 2021 is roughly ISSCC SOTA from 2007.
        - At 6.25 Gbit/s likely either a modified JESD204B/C, Sony's SLVS-EC, or OnSemi (prev Aptina's) HiSPi (high speed serial pixel interface) latter looks like it's supported by Intel Cyclone, AMD Xilinx, and Lattice FPGA's
        - The more common MIPI-CSI doesn't have the bandwidth for this, per lane.
        - The JESDB standard appears to have the most open spec, Xilinx provides a free implementation, and also the [JESD204B](https://github.com/enjoy-digital/litejesd204b) project exists.
    - From a power overall, relative to a single ADC:
        - Budgeting 5-10W for the pixel array (just asked chatgpt)
        - Conservatively assuming 50fJ / conv-step, 1.7Msps, 10-bit, 41,000 ADC, we get: 50e-15 * 1.7e6 * 2**10 * 40960 = ~4W for ADCs.
        - And assuming 5W for the digital logic
        - That means, if we neglect the receiver power (actually this is horriblly wrong, as RX is often higher power), the 160 CML transmitters/serialzer can consume ~20W, or ~100mW per RX channel.
        - Each ADC is consuming around ~85uW (50e-15 * 1.7e6 * 2**10 )
        - 256 ADCs : 1 CML driver, meaning single ADCs fraction is using around ~585uW
        - 1 ADC : 26pixels, each pixel is using around 10uW, or ~260uW
        - Digital logic is ~100uW
        - Rounding, relative to ADC channel is 250uW array + 100 uW ADC + 100 uW digital + 550uW driver
        - Or essentially 25% pixels + 10% ADC + 10% digital + 55% cml transmitter


- Tang & Sanyun & Sun 2022 Review:
    - pg3: Refernce decoupling cap is often designed larger than CDAC
    - pg3: the DAC swichinges actually add noise! In line with the reference buffer itself
    - pg3: but in low-medium speed designs, the bandwidth of the switches is high but comp is small. So most noise is rejected

    - pg6: redundancy in the last 1-2 bits can allow you to relax comparator noise beyond quantization noise, and then simply increase comparator power for a certain number of additional steps. It equivalently reloats critical decisions to the LSBs. What this means is that in an ideally sized normal SAR only one decision will be critical, but it could occur anywhere. Redundancy allows one to essentially recover this mistake on the last bit, meaning the rest of the chain need not worry.
    - pg3: "In a well designed SAR ADC, SNDR should be limited by noise not distortion"
        - And within noise, good designs shouldn't be dominated by reference or dac switch noise. But by sampling and comparator noise.
    - pg9: dummy cells measuring several um have found to be necessary to reduce edge effects
    - pg9: mitigating capacitor mismatch, can be partially accomplished via switching strategy avoiding the biggest swings voltage
        - But calibration of the capacitors themselves (see Ding 2015) of calibration only of the digital weights is necessary for high resolution.
        - When the the sampling node can't be measured directly, calibratability is a requirement for both the strats above
        - See Ding 2018 for on-chip LMS engine calibration. Off-chip paper is only 6-bit so I didn't read

- Zhaokai Liu:
    - Talks a lot about the linearity requirements of high resolution ADCs, and how bottom-plate sampling helps enable this
    - I'm not sure if this applies to my use case though. I need to read more.

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


# CDAC design specs:

- We'd like to fit within 100uW - 400uW for the ADC
- We'd like to target 12-bit
- To meet this resolution, at 1.2 supply, voltage noise in RMS for sampling should be less than quantization.
- Quantization itself will result in `(1.2/2**12)/math.sqrt(12)` = 84e-6 or 84 uV of

- To understand how the Ceff vs Ctot works, I need to look at Cu unary and Cb binary caps
- Cbinary are the unit length, 

- M1, M2, M3 for routing: M4, M5 for shielding, M6, M7 for caps, M8 shielding, M9 power, AP ground
- for 12-bit, we only (2**11) - 1 unit capacitors plus a 1LSB dummy per side since we do Top plate sampling (see CC Liu 2015 pg 4, or CC Liu 2010 set-and-down)
- We will have 16 decision cycles, but only 15 CDAC switches similar, so we split the 2**11 capacitors into 15 groups.
- 


`2**7` is divided into 13 seperate portions:

```
+ 2**5 \
+ 2**5 \
+ 2**4 \
+ 2**4 \
+ 2**3 \
+ 2**3 \
+ 2**2 \
+ 2**2 \
+ 2**1 \
+ 2**1 \
+ 2**1 \
+ 2**0 \
+ 2**0
```

```
2**10  - 2**7 \
+ 2**9        \
+ 2**8 + 2**5 \
+ 2**7 + 2**5 \
+ 2**6 + 2**4 \
+ 2**5 + 2**4 \
+ 2**4 + 2**3 \
+ 2**3 + 2**3 \
+ 2**2 + 2**2 \
+ 2**1 + 2**2 \
+ 2**0 + 2**1 \
       + 2**1 \
       + 2**1 \
       + 2**0 \
       + 2**0
```
Yeilds 2047, which with a +1 dummy gives us 2048, or 2**11.