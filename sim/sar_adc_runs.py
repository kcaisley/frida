from sar_adc_sim import SAR_ADC_BSS
import matplotlib.pyplot as plt

params = {
    "ADC": {
        "resolution": 8,  # resolution of the ADC
        "sampling_frequency": 10.0e6,  # sampling rate in Hz
        "aperture_jitter": 0.0e-12,  # aperture jitter in seconds (TBD)
        "use_calibration": True,  # use weights w/ mismatch errors
    },
    "COMP": {
        "offset_voltage": 0.0e-3,  # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain
        "threshold_voltage_noise": 0.0e-3,  # RMS noise voltage in Volts
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,  # reference voltage in Volts
        "negative_reference_voltage": 0.0,  # reference voltage in Volts
        "reference_voltage_noise": 0.0e-3,  # reference voltage noise in Volts
        "unit_capacitance": 6.75e-16,  # unit capacitance in Farads
        "use_individual_weights": False,  # use array values to build cap array
        "array_size": 8,
        "individual_weights": [
            8192,
            4096,
            2048,
            1024,
            512,
            256,
            128,
            64,
            32,
            16,
            8,
            2,
            2,
            2,
            1,
            1,
        ],  # capacitor weights in unit capacitance (use_individual_weights = True)
        "parasitic_capacitance": 0,  # in Farads at the output of the CDAC
        "radix": 1.85,  # for the cap values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
    },
}

adc = SAR_ADC_BSS(params)
adc.sample_and_convert_bss(
    input_voltage_p=1.2, input_voltage_p=0.80, do_plot=True, do_calculate_energy=True
)
adc.calculate_nonlinearity(do_plot=True)

params2 = {
    "ADC": {
        "resolution": 8,
        "sampling_frequency": 10.0e6,
        "aperture_jitter": 0.0e-12,
        "use_calibration": True,
    },
    "COMP": {
        "offset_voltage": 0.0e-3,
        "common_mode_dependent_offset_gain": 0.0,
        "threshold_voltage_noise": 0.0e-3,
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,
        "negative_reference_voltage": 0.0,
        "reference_voltage_noise": 0.0e-3,
        "unit_capacitance": 6.75e-16,
        "use_individual_weights": False,
        "array_size": 8,
        "individual_weights": [
            8192,
            4096,
            2048,
            1024,
            512,
            256,
            128,
            64,
            32,
            16,
            8,
            2,
            2,
            2,
            1,
            1,
        ],
        "parasitic_capacitance": 0,
        "radix": 2,
        "capacitor_mismatch_error": 0.0,
        "settling_time": 0.0e-9,
    },
}

adc2 = SAR_ADC_BSS(params2)
adc2.sample_and_convert_bss(1.2, 0.80, do_plot=True, do_calculate_energy=True)
adc2.calculate_nonlinearity(do_plot=True)

plt.show()
