# Abstract


Semiconductor pixel radiation detectors are widely used in the natural, physical, and medical sciences. For applications requiring tagging of individual particles with better than 10 µm spatial resolution and less than 1 µs temporal resolution, but with sparse hit occupancy and relaxed energy resolution, event-based counting detectors remain a reliable and common choice. By contrast, when particles need not be individually differentiated (in time or space), hit-rates are above 100 MHz/cm (without external trigger), and spatial resolution below 10 um are paramount, frame-based integrating-mode readouts are better-suited.

These frame-based architectures are especially advantageous for imaging-modes used in electron microscopy and X-ray imaging. In an experimental setting, fast frame rates allow for real time in-situ observations. Potential subjects include rapid chemical processes, molecular dynamics of proteins, crystal nucleation and growth, material phase transitions, thermal conductivity, charge transfer, and mechanical strain.

Our work pursues the possibility of a single-reticle array exceeding 1 Mpixel with a continuous frame-rate surpassing 100,000 fps, which would be unprecedented. For the conjunction of these two specifications to be met, this presentation will present initial investigations into a compact and power efficient bank of column-parallel data converters, which at 10-12 bit resolution churn out a combined data rate exceeding 1000 Gbps. To fit within the constraints of a chip-bottom, the converter fabric must consume less than 1 W/cm^2 and have an effective ADC sampling rate density above 5 ksps/μm^2. Successive approximation ADCs are identified as the optimal choice, and various topologies and techniques will be analyzed to meet our goals.

Extras:
ADCs are also used in the case of 

Historically, the highest frame rates haves been achieved by buffering and duty cycle readout, either in-pixel in the analog domain, or in-matrix or in the chip periphery in the digital domain.

There are multiple components which together to determine the read out rate, which in-term deterine the frame. These including clock distribution, column sequencer, global shutter in-pixel transistor, clolumn drain line, column buffer, and ADC, and serializer, and serial driver, and wireline inteface. Of these, in most applications areas typically the most critic limiting factor is the 


# Terminology

## Switching schemes (reducing power)

- Conventional (essentially [McCreary 1975](library/1975_James_McCreary_conventional_0%.pdf), with differential config)
- Split capacitor switching technique [2005 Brian Ginsburg](library/2005_Brian_Ginsburg-split_cap37%-charge_sharing24%-two_step10%.pdf) Showed three switching stragegies for reducing energy: 2-step, charge sharing, and split capacitor). The best was 'split capacitor', with a 37% energy reduction.
- Monotonic switching (aka 'set and down') [2010 C.C. Liu](library/2010_Chun-Cheng_Liu_monotonic_aka_set&down_switching_81%.pdf) 86% energy reduction. Only allows 'H->L' transistions on the plates. One disadvantage is continuous dropping of common mode.
- MCS: Merged capacitor switching [2010 Hariprasath](library/2010_Venkatram_Hariprasath_merged_cap_switching_93%_(Vcm-based).pdf)
- Vcm-based: [Yan Zhu 2010](library/2010_Yan_Zhu_Vcm-based_switching_87%.pdf), 87% reduction
- IMCS: Inverted merged capacitor swithing [2013 Albert Hsu](library/2013_Albert_Hsu_MIT_disseration_SAR_calibration.pdf)
- BSS: Bidirectional single-side switching [2014 Long Chen](library/2014_Long_Chen_bidirectional_singleside_switching.pdf) Is it similar to monotonic, except that the MSB starts at the opposite polarity to center the common-mode better.
- CAS: Charge-average switching [2013 C.C.Hsieh](library/2013_CY_Liou_CCHsieh_charge_average_switching_CAS.pdf)
- CRS: Correlated reverse switching [2015 Jen-Huan Tsai](library/2015_Jen-Huan_Tsai_correlated_reverse_switching_wADEC.pdf) Similar to BSS, but splits up the MSB cap?
- Merge-and-split [2015 Jin-Yi Lin](library/2015_Jin-Yi_Lin_merge&split_switching.pdf)


## Redundancy

- I think these are all basically the same, in their redundancy benefits:
    - non-binary, sub-radix 2
    - double conversion
    - post-conversion

- [2014 Franz Kuttner](library/2004_Franz_Kuttner_subradix2_nonbinary.pdf): Is first to use redundancy via non-binary subradix 2
- [2013 Boris Murman](library/2013_Boris_Murmann_non_binary_survey.pdf):
- [2014 T. Waho](library/2014_T_Waho_nonbinary_redundancy_survey.pdf):
- [2015 C.C. Liu](library/2015_CC_Liu_redundancy.pdf):

## Digital error correction (DEC)

- Terms:
    - Addition-only DEC
    - adaptive equalization
    - 

- [Wenbo Liu 2007 ISCAS Urbana](https://doi.org/10.1109/ICASIC.2007.4415624): An Equalization-Based Adaptive Digital Background Calibration Technique for Successive Approximation Analog-to-Digital Converters
- [Wenbo Liu 2009 ISSCC Urbana](https://doi.org/10.1109/ISSCC.2009.4977318): Implementation of above, with less detail 

## Other terms
- Latch offet. [Murmann 2006](https://doi.org/10.1109/TCSII.2006.883204) analyzed regenerative latch offset from load cap mismatch
- NOTE: Split capacitor array (SCA) != split capacitor switching technique
- Top & bottom plate sampling
- Top & bottm plate switching
- Noise minimum shift (Caeleste, pg 26) An alternative to reference voltage regulation. When CDAC values are close to mid-scale, an equal number of capacitors are connected to Vhigh vs Vlow reference voltages, and the sensitivity to noise on the reference voltage is minimized. This technique add an additional capacitor array which  of the input to minimized noise in each measurement.
- Split capacitors (statically biased caps, Caeleste pg58, p116). Similar to above, but divides caps into two, and sets them to different biases to improve noise
- Interleaving: Multiple ADCs operating in parrallel, sampling out of phase. Mainly necessary for >100Ms/s, at the expense of power and area. Not useful for our applications.
- Pipelining: Multiple sub-ADCs, operating sequentially. Similarly allows for greating speed, at higher power and area costs. Not necessary for our applications.

# Design targets

| Design                  | EDET DCD    | CoRDIA     | pre-Helena | Helena      |
|-------------------------|-------------|------------|------------|-------------|
| ADC resolution          | 8-bit       | 10-bit     | 8-bit      | 10-bit      |
| Conversion rate         | 10 MHz      | 2.5MHz     | 5 MHz      | 10 MHz      |
| Area of one ADC         | 100x200 μm² | 80x330 μm² | 60x800 μm² | 20x100 μm²  |
| Power of one ADC        | 1800 μW     | 30 μW      | 700 μW     | 100 μW      |
| FOM_csa (conv/sec/area) | 500 Hz/μm²  | 95 Hz/μm²  | 105 Hz/μm² | 5000 Hz/μm² |
| FOM_epc (energy/conv)   | 180 pJ      | 12 pJ      | 155 pJ     | 10 pJ       |
| FOM_ppa (power/area)    | 9.0 W/cm²   | 0.11 W/cm² | 1.45 W/cm² | 5.0 W/cm²   |
| ADC qty Mpix @ 100 KHz  | 10000       | 40000      | 20000      | 10000       |
| ADCs total pixel rate   | 100 Gpx/s   | 100 Gpx/s  | 100 Gpx/s  | 100 Gpx/s   |
| ADCs total data rate    | 800 Gb/s    | 1 Tb/s     | 800 Gb/s   | 1 Tb/s      |
| ADCs total area         | 2.0 cm²     | 10.5 cm²   | 9.6 cm²    | 0.2 cm²     |
| ADCs total power        | 35.0 W      | 1.2 W      | 14 W       | 1.0 W       |

# Design techniques

- ✅ Unary, double conversion, and non-binary steps (typically x1.8 smaller)
- ✅ RDAC for powering lower voltage LSBs vs attenuating cap
- ❕ MoM != MIM, and POD is best  @ 4fF in μm²
- ❌ MoM caps are only 0.6-0.8 fF in the same μm², with worse variation
- ❕ Most non-linearity comes from capacitor mismatch, but isn't a huge deal
- ❕ Gain loss comes from parasitic capacitance
- ✅ Double sample, and use differential cap array
- ✅ Auto-zero comparator, and use a basic dynamic/clocked latch design
- ❌ Async jeapordizes stability of neighbors
- ✅ Share sequencer across all ADCs
- ❌ Interleaving typically not worth it
- ✅ 7-8 Gbps JESD204B w/ 8b/10b encoding

# Capacitors types
You can create capacitor plates with poly, metal, and diffusion. 

Typically the common combinations are:

- Poly-diffusion, aka MOS varactor or 'MOSCAP' with poly over n-wells (actually implanted not diffused). Typically the term Varactor is used in RF applications, where the structure will be done differenclty. ITRS 2011 puts this at 7-11 fF/μm²
- Poly-diffusion cap, where you use a field oxide instead of the standard FET gate
- 'Accumulation cap' which is a poly-diffusion (POD) cap, but with the S and D connection. Only using G to Bulk capacitance
- MIM caps, are created with metal layers, but place an intermetidate metal layer closer, and use a special insulator (silicon nitride, tantalum pentoxide Insulators (e.g., Si3N4 or Ta2O5)). ITRS 2011 puts this at 5-7 fF/μm²
- Metal-metal, aka metal-fringe-capacitor (MFC), availabe in TJ180. These can be multiple layers, or just a single layer. There are several variations, with intedigitated fingers with via between, or with vias only on the edges, and fingers rotated each and other layers called an 'RTMOM'. In TSMC65, this is covered [here](/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/PDK_doc/TSMC_DOC_WM/PDK/crtmom_rf_device_route_guidance_for_RF_application.pdf). ITRS 2011 puts this at 5-7 fF/μm²?
- Poly-poly caps can be as simple as two large rectangles, on two seperate poly layers. Called 'POP' caps. Need to have a poly2 layer.

Tower 65nm seems to have nmoscap, moscaps, pmos caps (all these are varactors), mimcap, mimpcap 3T, RTMOM, and MIM. List is [here](/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/PDK_doc/TSMC_DOC_WM/PDK/CRN65LP_v1d7a_pdkFSAChecklist.pdf).

Tower 180nm Accumulation caps, MIM caps, and MFCs are covered [here](/eda/kits/TOWER/ts18is_6M1L_2014/HOTCODE/models/ts18sl/v4.9.3/docs/DRS2_0018_B_manual.pdf).

A common way to increase the density of decoupling capacitors. Stack MOM on top of device capacitors (make sure they are connected in parallel and not series).