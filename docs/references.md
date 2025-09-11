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