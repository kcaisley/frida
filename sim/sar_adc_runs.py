from sar_adc_sim import *
import matplotlib.pyplot as plt

params = {
    "ADC": {
        "resolution": 8,                    # resolution of the ADC
        "sampling_frequency": 10.0e+6,      # sampling rate in Hz
        "aperture_jitter": 0.0e-12,         # aperture jitter in seconds (TBD)
        "use_calibration": True,            # use weights including mismatch errors for the result calculation
    },
    "COMP": {
        "offset_voltage": 0.0e-3,           # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain 
        "threshold_voltage_noise": 0.0e-3,  # RMS noise voltage in Volts
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,  # reference voltage in Volts
        "negative_reference_voltage": 0.0,  # reference voltage in Volts
        "reference_voltage_noise": 0.0e-3,  # reference voltage noise in Volts
        "unit_capacitance": 6.75e-16,        # unit capacitance in Farads
        "use_individual_weights": False,    # use array values to build the capacitor array
        "array_size": 8,                    # number of capacitors in the array = resolution-1 for binary weighted or larger for unitary weights and/or redundant conversions
        "individual_weights": [8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 2, 2, 2, 1, 1],  # capacitor weights in unit capacitance (use_individual_weights = True)
        "parasitic_capacitance": 0,         # parasitic capacitance in Farads at the output of the CDAC
        "radix": 1.85,                      # radix of the CDAC, for automatic calculation of the capacitor array values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,    # mismatch error in percent of the unit capacitor
        "settling_time": 0.0e-9,            # settling time in seconds (TBD: individual settling errors per capacitor?)
    }
}

adc = SAR_ADC_BSS(params)
adc.sample_and_convert_bss(1.2, 0.80, do_plot=True, do_calculate_energy=True)
adc.calculate_nonlinearity(do_plot=True)

params2 = {
    "ADC": {
        "resolution": 8,                    # resolution of the ADC
        "sampling_frequency": 10.0e+6,      # sampling rate in Hz
        "aperture_jitter": 0.0e-12,         # aperture jitter in seconds (TBD)
        "use_calibration": True,            # use weights including mismatch errors for the result calculation
    },
    "COMP": {
        "offset_voltage": 0.0e-3,           # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain 
        "threshold_voltage_noise": 0.0e-3,  # RMS noise voltage in Volts
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,  # reference voltage in Volts
        "negative_reference_voltage": 0.0,  # reference voltage in Volts
        "reference_voltage_noise": 0.0e-3,  # reference voltage noise in Volts
        "unit_capacitance": 6.75e-16,        # unit capacitance in Farads
        "use_individual_weights": False,    # use array values to build the capacitor array
        "array_size": 8,                    # number of capacitors in the array = resolution-1 for binary weighted or larger for unitary weights and/or redundant conversions
        "individual_weights": [8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 2, 2, 2, 1, 1],  # capacitor weights in unit capacitance (use_individual_weights = True)
        "parasitic_capacitance": 0,         # parasitic capacitance in Farads at the output of the CDAC
        "radix": 2,                      # radix of the CDAC, for automatic calculation of the capacitor array values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,    # mismatch error in percent of the unit capacitor
        "settling_time": 0.0e-9,            # settling time in seconds (TBD: individual settling errors per capacitor?)
    }
}

adc2 = SAR_ADC_BSS(params2)
adc2.sample_and_convert_bss(1.2, 0.80, do_plot=True, do_calculate_energy=True)
adc2.calculate_nonlinearity(do_plot=True)

plt.show()