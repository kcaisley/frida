# Notes for Caeleste meeting

- Challenges I want to prevent: dynamic errors (thermal, settling, supply/refernce noise) and static error
  - First let's figure out how bad these are in a 10-bit design (taking a )
  - Calibration is costly, so can we do this in hardware with just DEC. Maybe some offline
  - systematic errors = accuracy, random errors = precision.
  - Calibration a subset of error correction targeted at systematic errors, can be done via lookup tables,
  - error correction can be used for both: oversampling and averaging can reduce random errors,
  - Redundant circuitry or digital post-processing (e.g., error-correcting codes) may address either type depending on implementation.

- strategies for solving these:
  - Take smaller steps (when LSB is big)
  - have overlap in path finding algorithm
  - This costs time, but we have some wiggle-room ourselves

- I've also looked at:
  - Unit cap design: just show 3 different types
  - How small can we make the unit caps? (125aF for unit caps in 10-bit design). Explain how switched cap noise works. (we can't do it twice: average or CDS, since we don't have time budget)

JH Tsai 2015:
- SC-ADEC is for the dynamic errors, and correlated reverse switching for the static errors
- I'm not sure I understand HS Tsai's perspective on the subtle different between sub-radix 2 vs radix 2 extended search.  guess that the strategy of taking lots of small steps only makes sense (th)
- Liu 2010 worked well, but cost extra capacitors. This extra total capcitance didn't even improve mismatch, and so the only benefit was the error correction plus slightly lower sampling noise, but at the cost of slower settling, higher power, and larger area. Thus I think we should just consider approaches which use the same total unit capacitance as the binary design.
- The other paper that did something similar was SH Cho 2011 multistep addition only DEC. Here I don't think they added any extra caps though. In a 10-bit design, each single ended DAC has 2^9 = 512 caps. The only special thing is that they are partitioned in a funky way.
- Fig 23b shows us pretty much the smallest SAR ADC (in 65nm?) running at 10MHz was 250x50um. So P. Harpe's 2019 paper at 36um ^2 was very much state of the art.


Papers with merge or split caps in title name:
split capacitor array DAC - Gisburg 2007
merge and split switching - JY Lin 2015
merged capacitor switching - V Hariparsath 2010
inverter merged capacitor switching - A Hsu 2013
correlated reverse switching - JH Tsai 2015


### Questions for Hans:

In CC Liu 2015, the section III math for MSB capacitor first states it is `B10 = 2**8 - 2**4`.
Then later the MSB is `B11 = 480` and the `MSB-1 = just 2**8`???? How does this math work out? Do the earlier examples not assume 2**N-1 caps per CDAC side?

CC Liu 2015 Equation #1 seems wrong to me? C/C is normalized, so you can't subtract C right?

What is the D= BW^T expression used by J Tsai on Page 1? I don't understand the term coding offset? D is output bit depth, B is the raw bits. W is the weight.

2015 JH Tsai pg. 3 says that 'differential arch' allows DAC to be 9-bit, in a 10-bit ADC. This contrasts what we stated before in the meeting? I thought it was more to do with the top-side sampling, where the comparator is connected to the same node as the sampled voltage.
2011 SH Cho pg. 2 claims the 'dual reference voltages' is what allows them to have a 9-bit DAC for a 10-bit ADC.


# Notes @ DPG

Calibration and error correction are two distinct issues

Linearity degrades quantization noise, but can be calibrated.

Errors are random.

Q: Settling error are actually repeatable, and so they aren't dynamic errors are they? A: No, they are dynamic, because if you rerun the same bit step the same mistake won't be made twice as it is already settles. Murman 2013 states. "The DAC error is indistinguishable from errors made in the quantizer itself."

Also, realized that reference settling depends on drive strength to these nodes, and so power and area budget has to be spent making reference settling fast enough.

Since DAC settling has to be within 1/2 of LSB in time, we can for example say that a 240Mhz with 10-bit designed accuracy has to settle within:

0.5/240e6/10 which is 0.2 ns

To consider matching DNL/INL impact, we can find we need all caps to be within 1/2LSB 99.7%, aka 3sigma

Also process variation can lead to reference buffer mismatch.

Also, rememember that when scaling the caps to the kT/C limit, this is based on the entire total CDAC capacitance. And it is determined at sampling time, before CDAC switching.
Expression is `Vrms_noise = math.sqrt(k*T/Ctot)` and `Vrms_noise` << `Vref / 2**N` bit resolution, by a factor of 5 or so.

So for a 10-bit design, with 1.2 supply `Vrms_noise` << 1mV and for a 12-bit design `Vrms_noise` << `0.2mV`.

This means the total and unit caps should be, assuming binary weigthing are:

10-bit: `math.sqrt((1.38e-23 * 300)/(100e-15)) < 0.2 * 1000uV` so Ctotal > 100fF and Cunit > 100aF
12-bit: `math.sqrt((1.38e-23 * 300)/(100e-15)) < 0.2 * 200uV` so Ctotal > 4096fF and Cunit > 1fF

With traditional unit caps it wouldn't be possible to get to the minimum size of 100aF for the 10-bit case,
and for the 12-bit the 1fF unit caps are feasible but the total area would be to large for our < 7500 um^2 target.
Perhaps P. Harpe 2018 makes these more feasible? In short, in order for a SAR ADC to be most optimized, the unit capacitance should ideally be equal to the kT/C noise limit. However in processes > 28nm, this has typically not been able to be achieved due to poor matching of unit caps. Harpe 2018 makes ~100 aF unit caps feasible within the matching limit.

But for a 12-bit design, would smaller this help us at all? Our unit caps already need to be roughly 1fF. I think so, if we make the smallest 3-4 LSBs scale by length instead of units.

From page 4, we can find that that there is a 0.5um by 30um cap structure with a total capcitance of roughly 9.2fF.
To get it to act as a 125fF cap, the length difference is 0.2um.
To get it to act as a 1fF cap, the length difference is 1.6um.
And the max value is 8fF, with a length difference of 12.8 um.

This means the first four caps can be implemented in 30*0.5 * 4 caps with good linearity The 30 * 0.5 unit also now becomes the unit cap with a density of approx 0.5 fF per um^2.

Note how the conventional requires two 2^N DACs, which is the same as 2^(N+1)
The monotonic ADC needs two 2^(N-1) DACs, which is 2^N. We confirm the latter looking at

In a 12-bit DAC we count the first 3 as binary caps Nb, and the 12-3 = 9 Nu remaining caps as unary. If obliged to do a conventional switching for this design,
that means we have `2*Nb + 2**(Nu+1)` unit length caps making up the array so `2*3 + 2**(9+1)` which is 1030. Since each of these are 0.5um high, this would be like 30um * 500um which is too big.

We're mistaken here though, because we're basing the design on the 1fF unit cap. This is wrong. We just need the total sampling capacitance to be > 4096fF.

This is extremely tricky though, with the layout densities of approx 0.5 fF per um^2. We should go back to the drawing board.

I believe that CC Liu 2016 achieved a high desity design in 2015. Let's check. They have a two 8um*25um cap arrays with a combined capacitance of 300 fF which is 0.75fF/um^2.

People who build 12-bit ADCs though typically have a quite large array. For [example in this paper](https://ieeexplore.ieee.org/document/7973044) CDAC cap arrays measures appox 300um x 1500um with 32pF of total sampling capacitance, or 0.1 fF/um^2

The question is, could we accomplish this: for 12-bit kt/C noise compat, if we managed to fit a 4096fF into an area of 30um x 200um, we'd need 0.68fF/um^2 density. This seems on the edge of feasibility, and I'm not sure if it can be done in 65nm CMOS.


I'm focused on the redundacy question. I want to know which types to add, but I'm not sure I exactly understand exactly what it's supposed to fix. From P. Harpe 2018 I see at least it should resolve settling errors (similar to how slowing down clock would). But can it also fix thermal noise errors?

There are two types of error: static and dynamic error, both of which degrade ENOB. One question I have, are settling errors dynamic or static? They are surely transient, but I think they are mostly repeatable, as it's an RC time constant delay?

Let's focus on a 10b target ENOB, and assume unit caps of 1F, with 1024fF of total capacitance.

Step one is to make sure that ENOB is degraded as expected, with the various error sources we can model.

Then step two is to try to recover it, by adding redundancy. We can afford to simply add the extra caps, without worry about the changed total capacitance as between 500-2000fF should fit in our area limit. We do need to account for the fact that redundancy will worsen settling errors.

Reference buffers aren't necessary if running directly off the supply voltage, but in either case large decoupling caps are typically needed to prevent supply voltage variation, which can require a quantity of caps which are larger than the core ADC area itself.

A. Theuwissen in 2019 paper builds an ADEC circuit and contrasts is against:
- JH Thai 2015 uses correlated reverese switching, instead they use conventional switching
- SH Cho 2011 uses multistep addition-only DEC, whereas they use single-step
- CC Liu 2010 needs digital offset compensation, whereas they don't needs straightforward timing DEC

At the moment, CC Liu 2015 and JH Tsai 2015 are the two most important papers for me to understand.

The wild thing, is that neither are mentioned in the Tang-Sanyal-Sun 2022 review article. Maybe it's not that great of a review.

JH Tsai 2015 didn't even use calibration, so maybe it's not really necessary. CC Liu 2015 might use it in some form, but doesn't seem to mention it. Ding-Hoffman 2018 mentions there's essetially two types of calibration: equalization (adaptive, LMS, are related terms) based and correlation-based. I can look into this later.

I'm essentially just interested in error correction, which can come from transient noise sources, or from settling error. These have different characteristics, as Murmann 2013 points out. CC Liu 2010 focused on dynamic settling errors and Giannini 2008 focused on thermal noise.

Murmann 2013 points out that W. Liu 2010 ISSCC is so influential as I think it was the first CMOS SAR design to use *background* digital calibration W Liu previously applied it to pipeline ADCs.

Liu 2011 suggests that in addition to dynamic errors arising from finite switch resistances, supply bounds, supply transiets (in-sufficient nearby decoupling), and device noise (mainly in comparator) that redundancy can also help correct static errors.

Key idea: thermal noise, assuming it's well within an LSB is likely to only cause a 2LSB error. In a binary design, without any redundant range, we're likely to have a single error somewhere in the conversion, which will be almost recovered by the remaining bits, and then an error on the last cyclce. Therefore, having having two bits at the end (Or having only 1 bit, and increases in the comparator power to get the 2nd to last bit RIGHT) is all that's necessary. In short, you will only have 2 close to tripping point cycle..

key idea: however, if you are also suffering from dynamic error, having more redundancy through the chain is beneficital. This is because, if you don't settle, then there's no way to predict the number cycles which are close to tripping points.

MSB caps are essentially saying you want to make sure you get your MSB conversions right? So you're really worried about large dynamic settling errors. In fact we can calculate the

How much redundancy throughout the chain is necessary for a given amount of expected settling error? -> CC Liu 2015 Equation #2
Albert Hsu 2013 also provides equation #3.5 which appears to also calculate the redundancy left in the chain, but in terms of weights, no voltage steps

Key idea: The other reason for redundancy is to allow for 12-bit operation with very small caps.
If we're limited in size, but timing is relatively lenient, we can trade off timing for bit depth by reducing dynamic and static errors with redundancy.
This is what we're doing in our design. We're not really actually pushing our selves in terms of speed at 10MHz, and honestly we're going to have quite small caps.
Comparator noise won't be much of an issue, because our power budget isn't too tight, and our CDAC will be small out of necessity, so low power anyways.
But because we're wanting such a small array (close to kTC noise limit) with maybe even 12-bit precision, we're going to have big linearity issues.

Strategies for digital error correction / redundancy

F Kuttner 2002: Sub-radix 2 with binary weighted


V Giannini 2008: Last bit
CC Liu 2010: Binary compensation

A Hsu 2013:



Albert Hsu's 2013 thesis really provides all the info we need on redundancy being used for thermal and switching errors, then as well as for calibration:

2.3 explains static error, aka gains and offsets erorrs plus non-linearity from mismatch, all of which can be calibrated
2.4 explains dynamic error sources: settling errors, reference noise (from switching through finite impedance with L and C), and also threshold noise in comp (which isn't measured)

3.1 Redundancy can fix dynamic errors: calculate error tolerance windows (eq 3.5)
3.2 redundancy can fix static errors, by enabling background calibration. The reason is that missing codes can be calibrated out, but missing input tripping points can't. So sub-radix ensures we have some DNL below -l but none over +1. In other words one input can map to multiple digital codes, but in no cases do multiple inputs map to the same output code (beyond one LSB). Does this mean graphically that the INL curve should stay over the ideal line, and never fall under?

What did A Hsu say about CC Liu 2010 binary compensation? Nothing!

*C.C. Liu binary compensation 2010 is referenced in:*
Murmann 2013: explained as redundant steps instead of redundant levels. Good for DAC settling which is indistiguisable from quantizer errors.
T Waho 2014: just groups it into a collection of alternatives to subradix 2
Theuwissen 2019: simply contrasts their design against it saying it uses complicated DEC logic
Sanyal Sun 2022: survey just basically says it a way to avoid comparator errors, and so it relaxes the errors made during

*C.C. Liu 2015* is referenced only by P. Harpe 2018: only comments that their cap array is only small because it is in 20nm. If backported it would be too large.


# Design aspects

- Unit cap design / layout
- Comparator design
- CDAC switching schemes
- Sample and hold switch S&H
- Error correction, redundancy and DEC logic
- Digital Calibration (forground vs background)
- Clocking and async designs
- reference buffers



# Older notes

Python code for SAR ADC functional modelling.


codes which show non-monotonic behavior
[1.0, 1.8, 3.24, 5.832000000000001, 10.4976, 18.895680000000002, 34.012224, 61.22200320000001]
comp  data<0>  data<1>  data<2>  data<3>  data<4>  data<5>  data<6>  data<7>       -Vin       Dout
     0        1        1        0        0        1        0        1        1    0.48723  79.564147
     1        1        1        0        0        1        0        1        1    0.48990  80.564147
     0        0        0        1        0        1        0        1        1    0.48993  80.444147
     1        0        0        1        0        1        0        1        1    0.49257  81.444147


# Pseudocode
```python
adc = SAR_ADC()
    SAR_ADC.__init__()
        resolution, cycles, sampling_rate, clock_period, etc...
        CDAC.__init__()
            array_size, unit_cap, radix, parasitics, etc..
            build_capacitor_array(use_radix, systematic_errors)
            settling_time, etc
        diff_input_range, lsb_size
        COMPARATOR.__init__()
            use_offset_error, offset_voltage, common_mode, noise_voltage

SAR_ADC.sample_and_convert_bss(self, voltage_in, plot?, calculate?)
    setup empty dac_out_p/n, comp_result, conversion_energy, total consumed charge,
    set dac_register_p/n to midscale: 1023
    CDAC.update(register_p/n, do_calc_energy) # initial setting
        for cap p/n pair in array, from small->large:
            depending on register_p/n, calculate the delta_output_voltage_p/n
    COMPARATOR.compare(dac_output_p/n, include_noise)  #initial compaision
        return input_voltage_p > input_voltage_n?
    for cap p/n pair:
        CDAC.update #here, all caps will be checked, but in monotonic switching only one will change
        COMPARATOR.compare
```

# To do:
- double conversion
- ENOB (done)
- FoMs (FOM (E/conv): done)
- Energy per conversion (done)

# Questions:

- When debugging the code, I should have an object which has all the related params hinted in the name
- Why is def calculate_nonlinearity() implemented in class CDAC - shouldn't the DAC non-linearity depend on how the caps are switching to make the levels?

class CDAC_BSS(class CDAC)
class SAR_ADC:
    self.dac = CDAC_BSS(params)
class SAR_ADC_BSS(class SAR_ADC):
adc = SAR_ADC_BSS(params)


Physical hardware configurations are parameterized via:
- Different classes
- YAML files params
- main() function call params
- Different init() results
- if/else conditionals within methods


in a differential DAC, the signal


The CDAC itself is charaterized by:
- two input signal nodes
- two input fixed potentials (Vref and gnd, or vdd and gnd)
- two outputs (one of them can be the Vref passed through)
- also note that there, in the case of a series-split CDAC, a second high-impedance node which is connected to nothing
- an array of switching bits (normally just 1-bit per cap, but some arches use two)

- a sample function, a reset function, and an update function (based just on control signals)
	- note how the reset function is the one which computes outputs from inputs

The complicated thing is that a capacitor's ability to add or subtract depends not just on it's value, but on what the initial voltage on the reverse plate was.


The SAR logic is characterized by:
- an input signal from a comparator
- an output signal bus for driving a CDAC switch set
- an output code, which is the final estimate




It makes sense to model these blocks as objects, with:
- function call arguments acting as inputs
- function call returns acting as outputs (maybe being then stored as values in attributes)
- and these functions updating the attributes which are state

Then I think we should models them as a top-level class, which itself can't be instanced.



Some properties which I'm interested in, like energy consumption, get messy to describe, because they are tracking something transient. So instead, perhaps I should instead restrict these to drawing something from a pin.

The other issue is the generation of internal parameters. We know we can create different concrete classes by doing something like inheritance from a base class, but how do we differentiate between parameters which are simulation voltags/current/charge/digital signals, and inputs which are used to parameterize the specifics of the object?

Perhaps anything that's done in parameterization goes into the __init__ method?
Any different which either changes the IO of a block, or changes how those IO behave, should result in different class definitions.
Anything which

Struggling with:
- single and multiple inheritance
- super().
- dataclasses and abstract base classes
- subclassing and superclassing?
- duck typing, to not even need some top-level class
