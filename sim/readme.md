Python code for SAR ADC functional modelling.

# Pseudocode
```
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
