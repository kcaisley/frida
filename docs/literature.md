# Review articles
- [[P Harpe 2022]](https://doi.org/10.1109/OJSSCS.2022.3211482)
- [[A Sanyal - N Sun 2022]](https://doi.org/10.1109/TCSI.2022.3166792)

# Total capacitance minimization
CDAC total capacitance often dominates area usage and is a large portion of power budget. Assuming no noise-shaping/cancellation, kT/C sampling noise provides theoretical limit on ADC error, and is determined by Ctot. However, a conventional CDAC implemented with capacititor scaling alone exhibits severe mismatch in it's LSB caps as it's Ctot is shrunk. To break the direct relation between the Ctot and the mismatch of the smallest caps, three stragies exist to construct the smaller bits:
- Scaling down switching voltage, strategy used in SASC via an RDAC
- Scaling using a "bridge capacitor", common strategy, example [[J Liu - S Sun 2022]]()
- Scaling using the difference between two capacitors [[P Harpe 2022]](https://ieeexplore.ieee.org/document/9805764) and [[P Harpe 2018]](https://ieeexplore.ieee.org/document/8540794)

# Top-plate vs bottom-plate sampling
In most SAR implementations, the CDAC switches are connected to the capacitor 'bottom-plates' (named due to closer proximity to FEOL) and the comparator is connected to the shared capacitor 'top-plate' (named for being higher in metal stack up). However, a non-trivial design choice exists as to whether the sampling switches should be connected to this top-plate of bottom-plate of the CDAC. The advantages of each boil down to:
- Top plate sampling:
  - Allows a comparator decision to be taken without needing to first switching the CDAC, thus requiring only a N bit ADC with only N-1 bit CDAC. This reduces area of the CDAC by a factor of 2 [[CC Liu 2010]](https://ieeexplore.ieee.org/document/5437496)
  - Simplifies switch layout and logic for the CDAC bottom-plates, as fewer voltages voltage busses need to be distributed across the array [[C Wulff]](https://doi.org/10.1109/JSSC.2017.2685463)
- Bottom plate sampling:
  - In some configurations can improve linearity, as all charge summing happens on the same end of the CDAC capacitor [[Z Liu 2025, Sec 4.2.1]](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2025/EECS-2025-21.html)

# Error correction and calibration, and their relation to redundancy
Errors in ADC digitization can be categorized into:
1. Static errors, aka accuracy, limited by manufacturity variability that produce repeatable errors as characterized by INL/DNL. Main sources are capacitor mismatch and comparator input offset.
2. Dynamic errors, aka precision, limited by random transient variations. Sources include input sampling noise, comparator noise, and to a lesser degree noise on the DAC bottom plate from reference supply and switch thermal noise. Additionally, depending on the resolution and sampling speed, insufficient time for DAC and comparator latch settling essentially manifests as an error signal. While these are in principle deterministic, since they depend on both input signal and DAC switching sequence, and also vanish during the subsequent conversion step, means they are also typically modeled as a random variable.

**Error correction strategies** refers to techniques for correcting dynamic errors, namely wrong decisions by the comparator. They are (mostly) of a digital nature and don't directly address transient non-idealities of circuit components, instead relying on additional measurement bits beyond the minimum N required for an N-bit converter. Error correction should be distinguished from more analog techniques (e.g. CDS) that instead reduce the chance of an error happening in the first place. Producing the additional bits which are needed to correct errors can be achieved in a couple ways, by either using multiple comparators, or more commonly by making additional decision cycles. Additional decision cycles can be interspersed throughouts the original cycless, or be added at the end, however, critically the input range they compare must overlap or be adjecent with the range where an error originally occured to be able to correct it. This approach of generating extra bits of information is called **redundancy.**
  - Binary scaled repeated conversions [[CC Liu, 2010]](https://doi.org/10.1109/ISSCC.2010.5433970)
  - Binary weighted sub-radix 2, with addition-only logic [[CC Liu, 2014]](https://doi.org/10.1109/ASSCC.2014.7008864)
  - Addition-only logic, in a CIS [[S Xie - A Theuwissen 2019]](https://doi.org/10.1109/TCSII.2019.2928204)

By contrast, techniques for correcting static errors are termed **calibration**. It exhibits a important property, **calibratability** which states that only a certain magnitude of mismatch can be calibrated, determined by the radix of the system. A binary weighted (radix-2) ADC can only calibrate up to 1 LSB worth of capacitor variation, whereas sub-radix-2 design can tolerate move. A sub-radix-2 design by definition is a design which produces additional output bits, therefore it should be noted that **redundancy** is also key to ensuring a design with larger capacitor mismatches is still calibratable. [[A Hsu, 2013, Ch 3]](https://dspace.mit.edu/handle/1721.1/82177)


# Calibration strategies
Calibration strategies are commonly categorized across two axes: analog vs digital, and foreground vs background:
- Foreground calibration uses an initial phase where a known input signal (typically ramp or sinusoidal) is applies to measure the deviation of the ADC weights from the design values. This calibration data can then be used as either:
    - **Analog foreground calibration**, where circuit elements (capacitors, comparator) in the SAR digitization feedback loop are tune to reduce mismatch. 'Analog' is a bit of a misnomer, as most calibration circuits internal to an ADC are mixed-signal.
    - Or as **digital foreground calibration**, where a post-digital processing block, independent of the ADC, corrects the codes via a 'lookup table' or similar. [[J Liu - N Sun 2020]](https://doi.org/10.1109/JSSC.2020.3016656)
- Background calibration requires no seperate calibration phase. This means that the circuit continually calibrates over time, although it will be less accurate for a short interval after startup.
    - In **analog background calibration**, analog components are tuned over time [[M Ding - P Harpe, 2015]](https://doi.org/10.1109/JSSC.2016.2609849).
    - By contrast, in **digital background calibration**, the output codes captured overtime are transparently examined and compared against an expectation of what the code density should look like. In some instaces as small pseudo-random pertubation signal is applied at the input of the ADC during normal operation, to provide a reference for the calibration routine, although this comes at the cost of tampering with the input node. [[A Hsu, 2013, Ch 4]](https://dspace.mit.edu/handle/1721.1/82177)

# Switching strategies
Given a set weights in the CDAC have been determined, there are different ways to efficiently switch capacitors to produce those DAC levels. These can generally be divided into strategies which require a common mode voltage, typically called 'Vcm switching' strategies, and those which function with only a VDD/VSS rail. The latter is of more interest, since we are aiming for a compact design.

  - For an analysis and explanation of switching strategy energy efficiency [[A Hsu, 2013, Ch 5]](https://dspace.mit.edu/handle/1721.1/82177)
  - The original paper on monotonic (aka 'send-and-down') switching [[CC Liu 2010]](https://doi.org/10.1109/JSSC.2010.2042254)
  - A variation on monotonic switching, which keeping the commonmode voltage closer to mid-supply, called **bidirectional single side** switching [[L Chen - N Sun, 2014]](https://doi.org/10.1109/ESSCIRC.2014.6942061)
  - A more complicated switching strategy called MCS, too complicated for CIS, but the review of other switching stragies is worth ready [JH Tsai 2015](https://doi.org/10.1109/JSSC.2015.2413850)


# Here lies messy notes below

I want to target 12-bit precision, as this is more generally useful, and it better places me compared the state of the art:

- CC Liu 2010
    - The follow up 2015 paper seems to indicate (pg 3) that the inserted compensative capacitors add to the sampling capacitance (as I thought) but they don't add to the input range of the DAC. Why is the the case? Will need to come back to this.

- Hsu 2013
    - Intro "Our goal is to create an ADC that runs faster than 10 MS/s at more than 10b ENOB, while achieving FoM lower than 50f J/conv.-step."
    - For FRIDA: 12-bit, 400uW, 10MS/s gives: `400e-6/(2**12 * 10e6)` = 9.7 fJ/conv-step
    - pg53: ENOB, SNDR, SFDR = dynamic metrics, while INL/DNL, offset, and gain errors are static metrics
    - pg57: even 1% mismatch will (given enough instances) yeild below 11ENOB in 12-bit ADC. Remembers that the static linearity sets the baselines ENOB, even if one runs as slow as possible.
    - Note that even at slow speeds, one needs a input switch, and then references and comparator which are all three designed to not degrade the precision substationally
    - Then after all of this, dynamic errors accumulate on top. But we're running slow enough that they should be the secondary issue?
    - Calibration: analog(tuning caps) vs digital forground (pre-measurement w/ RAM) vs digital background (doesn't interupt)
        - Within digital background calibration: injected calibration signal, adaptive equalization w/ reference ADC, and Hsu's statistical approach
        - for FRIDA, need to verify: Can we use Hsu' method III?, since we have a one-shot channel and we so we don't really have input statistics? I think Theuwissen 2019 might be an answer here.
    - pg141: Section 5.1.2 develops a better way to make a main-sub-dac array (bridge capacitor) improving on mismatch and overange issues of past designs
    - pg146: redunc
    - Hsu' final architecture is: IMCS switching, 4x repeated bits (16 cycles for 12 bit accuracy), bridge cap for shrinking arch, asynchronous operation with ready generator, and 11fF MOM caps with 1.5 pF total array capacitance
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


- CC Liu 2015
    - Top plate sampling and monotonic switching only require `2**9` caps in each side for 10-bit ADC (references CC Liu 2010)
    - Sampling capacitance is 300 fF for 2^9 caps (is this in both sides?) in an (each side) area of 25um by 10um, which is roughly 0.58fF per unit cap, with 1.2um^2
    - NOTE: There were roughly 200 fF of parasitic capacitance, which is probably partially due to the top plate being outside / exposed

- JH Tsai 2015
    - AH! The bidirectional switching in this paper and Chen-Sanyal-Sun 2014 are essentially the same. This paper just uses it on more bit positions
    	- Actually there is another difference: BSS paper uses bottom plate sampling with a CM setting on the top plate
	- This paper has a more complicated MCS component for correcting 1LSB worth of cap non-linearity
	- But overall it has a simple design
	- I will uses the top-plate sampling bi-directional switching
	- And I will also use the SC-ADEC (split capacitor addition only digital error correction) which is the same essentially at CC Liu 2015.
	- Not how he certainly has several spots only the chain where the radix between two bits is 2. This shows all that matters in the sum of remaining is greater.
	- this paper plus CC Liu 2015 are essentially a combination of the repeated levels strat (CC Liu 2010 and , plus the sub-radix 2 (rounded) strat (Kuttner 2005)
    - doesn't use calibration, but achieves a small fast 10b design
    - They first split MSB up, using what they call SC-ADEC (split cap - addition only digital error correction), but it's the same as CC Liu 2015
    - They then used a monotonic switching scheme, and add to their new technique called CRS, but also suggested it could be used with MCS from V. Haripasath 2010 (but this is a Vcm technique, so I don't think I want to use it)
    - pg9,sec C: the CRS and SC-ADEC strat can be independently applied to a given switching scheme
    - "The differential realization reduces the hardware of the DAC" by one bit, which confuses me a bit as I thought it was top plate sampling related
    - pg 5 "Over-/under-ﬂow removals are typically employed for designs that use extra redundant capacitors" which is why splitting the MSB is better
    - Is the base switching scheme monotonics, bss, or something else?

- Chen-Saynyal-Sun, BSS, 2014
    - Does Bss benefit here? yes, it maintains the common mode better
    - JH Tsai took it even further, buy adding 2 more bits that swing up at some point along the chain. That way the positive swing also isn't big.
    - Also this paper using a Vcm voltage in two places, plus it uses bottom plate sampling. I will just take the bidirectional single-side idea.
    - I would prefer not to use bottom-plate sampling as it requires a Vcm voltage, and I think it makes the input sampling switching more complicated?

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
    - Older notes, before I found the main paper:
      - Take for example the Phantom TMX 7510. The sensor is 1280 wide, vs 800 tall, with the ADCs are along the long edge.
      - It has 40000 12-bit ADCs, each converting in 523 ns (1912kHz). It's rated at 25 Gpix/s
      - It looks like there are banks of ADCs on both sides, but thinking of them being on each once, we can calculate we have 32 ADC per pixel column.
      - At the base rate of 76000 frames per second, that gives ~13158ns per frame. Since we can assume that the 800 vertical pixels are being shared between 32 ADCs, therefore we have 25 pixels per ADC being read, which again works out to ~13075 per frame.
      - 1024000×12×76000 = 933888000000, or 934 Gbps. Also, it's stated that 160 links at 5Gbps are used. Dividing the rate by 160 gives ~5.83Gbps, so this checks out.
      - With half the ADCS on each side, and half the IO on each side, we can assume 80 IO channels, being shared between 1280 half-height columns. This gives 16 half-height columns per IO, with 16 ADCs being connected. Therefore a 256:1 serializer would be needed, with the inputs running at ~1912 KHz * 12bit = ~22.9Mbps.
      - The package has 50 pins on each side, with all four pins covered, for a total of 200 pins. Therefore some of the high speed IO are clearly transferring horizontally.
      - Also of interest is the 18.5 µm pixel pitch. This means the active area is 15mm x 24mm. Therefore the two circuit areas, by visual inspection look to be 5mm x 24mm. If we assume only 60% of that is availabe for ADCs, and that each ADC is double the column width. That means you need to fit 2x400 pixels being read out by 2x16 ADC into and area that is 2x18.5µm * 3000µm. This gives 37x93.75 or ~ 40x100µm per ADC.
      - By comparison, our design spec is for something with half the area, at 20x100 μm². This took a design team at Forza a signifigant amount of work to achieve, so we are certainly in for a complicated battle.
      - By the comparison, the 1024x1024 µm pitch Celeritas camera peaks at 2Gpix per second

- Harpe 2022
    - pg1: immediately points out that for high resolutions >11ENOB, oversampling (Harpe 2014) or sampling noise cancellation(Sanyal Sun 2022) should be used
        - But that for lower ENOB <11, the minimum Unit cap (constrained by Ctot/2**N, for a given sampling noise) you could use typically isn't feasible
    - Achieved 10-11 ENOB in 0.001mm^2, while staying below 
    - The thing I want to try is applying his idea, but incorporating sub-radix2 redundancy, async clocking, digital background calibration to enabled a high-density array without noise issues
    - Also, I might be able to run faster than 12-bit? Since redundancy doesn't just enable mismatch calibration, but also can correct transient errors from transient noise and dynamic settling?
    - Used 'dynamic logic' to reduce circuit size, I can do the same later-on
    - Harpe ran slow enough, and sized comparators strongly enough, and decoupled power supply well enough that transient noise and dynamic switching errors shouldn't be a big issues, which is why he didn't use redundancy.
    	- Then after this, the mismatch of the capacitors was essentially good enough for his target ENOB.
        - But I want to perhaps go for close to 12-bit ENOB, with small caps, and so I'm interested in adding redundancy to allow calibration of my small capacitors.
    - A 'modified conventional switching is used' (from Harpe 2011) but is low power since the caps are so small
        - Each side has 21 elements, with 9.2fF cap (C + C'), and 10Mhz, so power would be estimated as `2*21 * 9.2e-15 * 1.2**2 *10e6` = ~5uW
        - This is exactly on the money, as power is measured at ~5uW as well
    - Also, total capacitance for sampling purposes is simply the number of units times the (C + C')
    - Q: does monotonic switching, bidrectional, mcs, etc have a place here? Is my expected power just `2*75 * 20e-15 * 1.2**2 *10e6` = ~45uW?

- Pelgrom 2022 textbook
    - pg 750: 
    - pg 768: In a basic SAR w/o calibration Ctot required for mismatch linearity is typically 10X that for noise.
        - For example, 10-bit SAR Ctot 50fF for sampling but ~500fF for mismatch are required
        - A 12-bit SAR would require 16x more at 800fF and 
    -  

- J.Liu - S.Sun 2022 kT/C noise cancelling SAR 13-bit
    - uses only 240fF of differential sampling capacitance, 591uW power, 
    - As pointed out by Pelgrom Textbook, pg 768 in a basic SAR w/o calibration Ctot required for mismatch linearity is typically 10X that for noise.
    - If implemented correctly, calibration can relax this, meaning sampling noise become the limit (re-stated by Ding-Hoffman 2018)
        - How did this paper actually first beat the linearity aspect?
        - They used four aspects:
            - bridge-capacitor for the last 5 bits, with a multiplier of 32x. So MSB is 64*32 = 2048 weighted
                - 128 unit cap before bridge have 0.8fF unit value, givine only 120fF per branch, or 240fF differential
            - 3 extra capacitors for 13+3 redundancy
            - only 2^12 total bit weights, instead of 2^13. Like monotonic, etc!
            - forground calibration, based on S.-W. Chen and R. Brodersen 
    - Used a standard strong-ARM latch, roughly 10um x 10um
    - pg2 states bottom plate sampling is typically used for high-resolution designs. 

- Tang & Sanyun & Sun 2022 Review:
    - pg3: Refernce decoupling cap is often designed larger than CDAC
    - pg3: the DAC switches actually add noise! In line with the reference buffer itself
    - pg3: but in low-medium speed designs, the bandwidth of the switches is high but comp is small. So most noise is rejected

    - pg6: redundancy in the last 1-2 bits can allow you to relax comparator noise beyond quantization noise, and then simply increase comparator power for a certain number of additional steps. It equivalently reloats critical decisions to the LSBs. What this means is that in an ideally sized normal SAR only one decision will be critical, but it could occur anywhere. Redundancy allows one to essentially recover this mistake on the last bit, meaning the rest of the chain need not worry.
    - pg3: "In a well designed SAR ADC, SNDR should be limited by noise not distortion"
        - And within noise, good designs shouldn't be dominated by reference or dac switch noise. But by sampling and comparator noise.
    - pg9: dummy cells measuring several um have found to be necessary to reduce edge effects
    - pg9: mitigating capacitor mismatch, can be partially accomplished via switching strategy avoiding the biggest swings voltage
        - But calibration of the capacitors themselves (see Ding 2015) of calibration only of the digital weights is necessary for high resolution.
        - When the the sampling node can't be measured directly, calibratability is a requirement for both the strats above
        - See Ding 2018 for on-chip LMS engine calibration. Off-chip paper is only 6-bit so I didn't read

- IMASENIC Sagara
    - One design had 6 ADCs per column, each running at 1Mhz 11-bit resolution.
    - Assuming 20e-3/2052 = ~10um pixel pitch, each ADC is roughly 5um by 30um from the photo?
    - This makes the combined column parralle block be 10um x 90um, or ~ 0.001um^2 similar to H in area, but only 6MHz and 
    - Not sure about the power

- Zhaokai Liu 2025:
    - Talks a lot about the linearity requirements of high resolution ADCs, and how bottom-plate sampling helps enable this
    - I'm not sure if this applies to my use case though. I need to read more.

- Our past Cordia design:
    - Currently we have a 130uV noise, 30uW 2-3ns comparator, measurring 36x18um this wouldn't fit well in a 10-bit design, but would fit well under a 12-bit Harpe-style CDAC
    - also, given the speed, we could likely run a bit faster since 10Mhz = 100ns period
    - Note that (1.2/(2**12))/math.sqrt(12) = gives a quantization noise of 84uV. So our comparator has about 1.6x the noise it should to stay below the quantization. Can we simply 2.5x the power consumption, somehow, to get 1.6x lower noise? (using quadratic power fo linear noise improvement)
    - Also, did we not ever measure the capacitor mismatch or check the calibratability offered by the Cordia SAR?

- Garcia-Sciveres 2023:
    - "The reason why the digital-only isolation is better than the double isolation might be that the noise is coupling through the metal stack rather through the substrate. In this case the double isolation has a higher impedance analog ground that is easier to shake by noise coming from the metal stack."


# Readings just on calibration:

- 2010 Wenbo Liu Thesis
    - Three strategies:
        - ch4: peturbation-based digital calibration
        - ch5: bit-wise-correlation based (BWC)
        - ch6: equalization based (I believe this is using 2nd calibration ADC, so it adds hardware)
        - realtime calibration using LMS engine, and a 'BWC' (bit-wise correlation based) signal. Appears to be either sine wave, ramp, or gaussian noise, but all appear to be the same for training.
    - Also, he talks about calibratability
        - Essentially, final output of DAC must be less than 1 LSB away from true value. In other words, conversion must be 'successful'
        - In this case, errors caused by dac mitmatch are FATAL. A certain degree of mismatch will not cause a >1 LSB error though.
    - sub-radix2 is not the only way to relax the issue where greater than Cunit variation in any cap will cause a non-calibratable ADC static error.
        - Any design where each Ci < sum(Ci+1 to C_N) is satisfied will with increasing ratio improve mismatch tolerance
        - In line with the above, binary compensation or binary recombination also satisfy this
        - Understand: that we typically examine the for non-linearity concerns MSB, because that is the capacitor is most likely to exceed 1unit cap of error, and thus have a missing level
- 2013 A Hsu (Again)
    - Calibratibility
        - pg72 Fig3-7 and Eq3.14 give radix (and alternatively # of steps) for calibratability in 12-bit design 
    - Foreground vs background means just wether or not calibration is done before normal data capture, or during
    - Analog calibration means it is turning physical device capacitances or comparator offset.
        - Forground analog calibration is the typical method, tuning caps
        - Typically costs case analog calibration reduces speed and/or adds circuti noise
        - Ding-Harpe 2015 is an example of background analog calibration, since it doesn't interrupt calibration, but will see a short calibration error which improves after a couple milliseconds
    - Digital forground uses a known ramp or sine input, or histogram stats method with gaussian input
        - in either case, values are stored in a RAM an applied afterward in feed-forward
        - can't track parameter drift during operation
    - Digital background means it runs transparently in background
        - either with a test input tone superimposed, or just using the input signal as a stimulus i.e. 'adaptive equalization'
        - in the later case, adapt eq. can be done using seperate ADC to measure input, or in fancy implementations no additional hardware
        - digital background calibration, with adpat. eq. but no added HW typically require uniformity of input signal
    - The LMS strategy is/can be used in both foreground and digital calibration
- 2006 Chen-Brodersen
    - Does digital foreground calibration, using either ramp or sinewave
    - uses LMS loop with an adaptive FIR filter as it is easiest hardware implementation, although hints that 'orthogonality principle' could also be used in software
- 2015 Ding-Harpe Background calibration
    

# Reading / simulating list:
- Finish calculating allowed device mismatch from A Hsu's diagram, and make sure our caps follow that radix
- Map this to the BinRecomb weighting from CC Liu
- Build it into the unit-length caps from P Harpe, and understand if we need 2^N-1 per side of 2^N with it's switching from earlier P Harpe paper
- Double check against Pelgrom and Tripathi (0.85 % × 1 𝑓𝐹 𝑜𝑟 1.9 % × 1 𝜇𝑚) to make sure my caps will meet calibratibility

- Calculate power-consumption from swithing

- Given 5-10ps sampling, and ~500pF Ctot per branch, and <10uV settling needed, how bit can our sampling resistor be?
- Check this in simulation for a basic transmission gate, with sweep of Vgs including 0.6V Vgs

- Read more thoroughly about top-side vs bottom side sampling linearity issues, from Zhaokai Liu 2025

- Double check the various calibration strats in Pelgrom textbook, and finish reading chapter.
- Double check Tang-Sanyal-Sun for calibration idea (searching for foreground calibration, in particular)

- Figure out the feedback digital logic, and include any programmability which I need for testing

# Things to actually test:
- How many mismatch does our actual capacitor array have with the different types?
    - Can I measure this without probing or driving DAC caps arbitrarily?
- How does the performance deteriorate with varying reference voltage noises?
    - This would allow us to understand how an array would perform, given power consumption of each design, and parasitics of power network
- Does placing active devices under capacitor array cause noise
    - Do a layout with and without the under cell design
- Is our comparator suffciently linear/low noise?
- How fast can we go, before performance really begins to deteriorate?
    - Will help us understand potential impact of different speeds, and also async operation timing budget
- Testing calibration
    - Test gaussian, ramp, and sine-wave based foreground digital calibration
    - Then figure out if this could be switched a background operating, without peterbation or extra ADC, using just pixel signal input statistics (certainly not uniformly distributed, or known, but is is maybe not even 'smoooth' following A Hsu 2013's specifications)

# Future things to try, potential issues to resolve
- Will our top-side sampling limit linearity
- Will our current (I think basic switch w/o bootstraping) be linear enough for our design
- Could asynchronous operation be benefiticial, and also not-cause issues in an array?
- Could we realistically implement some form of on-chip calibration (foreground or background, digital/analog)
- Could we potentially benefit from one of the additional switching techniques? (which reduce power and/or improve linearity)
    - Right now our power budget even with the 12-bit design is okay around ~300uW
- Try dynamic logic (Harpe 2022 pg4, Baker2019 chp14,) true single phase clocking (TSPC) logic (Baker, Wulff)
- Three standard strategies for improved linearity (Pelgrom pg750): Bootstrapped switch, differential operation, bottom plate sampling

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


- Always bottom plate switch
- Bottom plate sampling might be useful above 12-bit 
- Basic NMOS sampling good for low resolution


# Cap layout
- Zhaokai 2025 uses bottom inside, top outside, with veritcal crossbars to increase cap density (pg 92)
- Tianyang 2020 uses top plate inside (M4 and M5), with bottom plate creating a bottom plane, side walls, and top plane creating a full box around
    - The row is 1u x 25um, but the unit cap cap only uses 5um of this (two of 10 boxes)
    - plates are 120nm apart, horizontall on same metal layer
- P. Harpe 2018 uses bottom inside, top plate outside. (M4-5 are ground shield, M6-7 are actual caps)
    - plates are 130nm apart, 
- C. Wulff 2017: M1 bottom plate routing, M2 shielding, M3-M4 tied-together bottom plate finger, M4 top plate wrapping around
    - 32 unit caps organized in one group, meaning 5 LSBs fit in one group.
    - Then the MSB use multiples of this, with bit5 in particular uses a half-grounded group.

# P Harpe ADC tutorial:
- The trade off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a difference relationship between these. For example large CDACs have worse speed, but large comparators and sampling switches can typically improve the speed.
- The quantization noise, and 3 thermal noises T+H, DAC, comparator add linearly (assuming noise is expressed in power), since there is no amplification in the circuit. Not all ADCs are this way.
- Typically at high resolutions comparator noise is the trickest to reduce, on a fixed power budget
- Sampling switch non-linearity sets a speed x resolution frontier
- digital is linearity with N, analog power is exponential with N (due to mismatch/noise)
    - So @ high resolution, analog comp or DAC dominates
    - but @ low resolution analog really scales down, so digital dominates, limited to the minimum values for the analog blocks.

SAR ADC Limiting Factors (10-12 bit ADCs):

| Factor | Limiting Block |
|--------|----------------|
| Noise | Comparator, DAC |
| Linearity | DAC, T&H |
| Speed | Delay of blocks, T&H |
| Area | DAC |
| Power | Comparator |

*Note: Within each category, blocks are listed in order of importance. Also analysis is simplified for 10-12 bit ADCs.*

- Clock boosting and bootstrapping are two alternative to transmission gates. Clock boosting can drive too high though, and so bootstrapping is better (and more linear)
- Capacitive coupling and leakage across sampling switch are mostly an issue with ADC with dynamic input signals (which we won't have)
    - one interesting thing to note, is that with shrinking nodes both leakage and capacitive coupling (smaller D/S spacing!) get worse
- The DAC noise is actually composed of the reference noise plus the dac reference noise!
- Both input buffers and reference buffers depend on C_tot, so making Ctot smaller reduces the performance required of these buffers
