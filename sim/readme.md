Python code for SAR ADC functional modelling.

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




To do:
- double conversion
- ENOB (done)
- FoMs (FOM (E/conv): done)
- Energy per conversion (done)

BSS - has top plate sampling 
