import behavioral
import matplotlib.pyplot as plt

params = {
    "ADC": {
        "sampling_frequency": 10.0e6,  # sampling rate in Hz
        "use_calibration": False,  # account for cap error when calculating re-analog results
    },
    "COMP": {
        "offset_voltage": 0,  # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain
        "threshold_voltage_noise": 0,  # RMS noise voltage in Volts
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,  # reference voltage in Volts
        "negative_reference_voltage": 0.0,  # reference voltage in Volts
        "reference_voltage_noise": 0,  # reference voltage noise in Volts
        "unit_capacitance": 1e-15, # roughly 1um^2 MOM cap
        "use_individual_weights": True,  # use array values to build cap array
        "individual_weights": [],
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
        "switching_strat": 'monotonic',     # used to determined initial starting voltages
    }
}

# Basic case, without anything
params["ADC"]["resolution"] = 12    #FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases
params["COMP"]["threshold_voltage_noise"] = 0e-3
params["COMP"]["capacitor_mismatch_error"] = 4
params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] # 1e-15 unit cap, in Farads at the output of the CDAC, using this just to complete dynamic range
params["CDAC"]["reference_voltage_noise"] = 0.5e-3
params["CDAC"]["settling_time"] = 0.5e-9
params["CDAC"]["individual_weights"] = [896, 512 , 288, 160, 80, 48, 24, 16, 8, 6, 3, 2, 2, 1, 1]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])    #FIXME: shouldn't be a parameter, should be calc'd internally
adc1 = behavioral.SAR_ADC(params)
adc1.compile_results("~/frida/docs/aida2025/", "12b_splitcap")

# -------------------- noise errors ------------------

# # Okay, let's try some thermal noise. Based on my simulation with device noise enabled, I observed 1-2mV of noise
# # A 10-bit design has roughly 1mV bin sizes, so we'd expext this will totally ruin our design.
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# adc2 = behavioral.SAR_ADC(params)
# adc2.compile_results("~/frida/docs/images/", "behavioral_10b_devnoise")


# # Okay, and while reference noise adds in parallel, we'd expect it to less severe for inputs that are close to mid supply.
# params["COMP"]["threshold_voltage_noise"] = 0e-3
# params["CDAC"]["reference_voltage_noise"] = 5e-3
# adc3 = behavioral.SAR_ADC(params)
# adc3.compile_results("~/frida/docs/images/", "behavioral_10b_refnoise")


# # Now let's add the two noise sources above together, for a worse case.
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 5e-3
# adc4 = behavioral.SAR_ADC(params)
# adc4.compile_results("~/frida/docs/images/", "behavioral_10b_noisy")


# # Okay, and let's try the most basic form of redundancy, with post conversion
# # my theory is that this will actually fix basic random noises.
# params["CDAC"]["individual_weights"] = [256, 128, 64, 32, 16, 8, 4, 2, 1, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc5 = behavioral.SAR_ADC(params)
# adc5.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_postconv")


# # my hypothesis is that having redundancy earlier in the chain won't make a difference for this noise?
# # this is CC Liu 2010, where the sum is above the 9-bit limit
# params["CDAC"]["individual_weights"] = [256, 128, 64, 64, 32, 16, 8, 8, 4, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc6 = behavioral.SAR_ADC(params)
# adc6.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_bincomp")


# # Okay, now let's try the CC Liu 2015 binary scaled recombination method
# params["CDAC"]["individual_weights"] = [240, 128, 64, 36, 20, 10, 6, 3, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc7 = behavioral.SAR_ADC(params)
# adc7.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_binrecomb")


# # Okay, now let's try the HS Tsai 2015 SC-ADEC
# params["CDAC"]["individual_weights"] = [192, 128, 64, 56, 32, 16, 8, 7, 4, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc8 = behavioral.SAR_ADC(params)
# adc8.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_scadec")


# # We can also break apart just the MSB? My hypothesis is that this won't do much for device/reference noise
# params["CDAC"]["individual_weights"] = [128, 128, 128, 64, 32, 16, 8, 4, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc9 = behavioral.SAR_ADC(params)
# adc9.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_splitmsb")


# # radix 1.75 but without any constraint on the sum, but normalized nearest unit level
# params["CDAC"]["individual_weights"] = [269, 154, 88, 50, 28, 16, 9, 5, 3, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc10 = behavioral.SAR_ADC(params)
# adc10.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_radix175")


# # radix 1.75 normalized so that the total is still 511 (bottom scaling falls apart)
# params["CDAC"]["individual_weights"] = [220, 126, 72, 40, 22, 14, 7, 4, 3, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# adc11 = behavioral.SAR_ADC(params)
# adc11.compile_results("~/frida/docs/images/", "behavioral_10b_noisy_radix175norm")


# # -------------------- settling error ------------------

# params["CDAC"]["individual_weights"] = [256, 128, 64, 32, 16, 8, 4, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 1.0e-9
# adc12 = behavioral.SAR_ADC(params)
# adc12.compile_results("~/frida/docs/images/", "behavioral_10b_seterror")

# # Try fixing with CC Liu 2015 Bin recomb
# params["CDAC"]["individual_weights"] = [240, 128, 64, 36, 20, 10, 6, 3, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 1.0e-9
# adc13 = behavioral.SAR_ADC(params)
# adc13.compile_results("~/frida/docs/images/", "behavioral_10b_seterror_binrecomb")

# # Try fixing with MSBs divided
# params["CDAC"]["individual_weights"] = [128, 128, 128, 64, 32, 16, 8, 4, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 1.0e-9
# adc14 = behavioral.SAR_ADC(params)
# adc14.compile_results("~/frida/docs/images/", "behavioral_10b_seterror_splitmsb")


# # -------------------- mismatch error ------------------

# params["CDAC"]["individual_weights"] = [256, 128, 64, 32, 16, 8, 4, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 0e-9
# params["COMP"]["capacitor_mismatch_error"] = 2 # This is percent?
# adc15 = behavioral.SAR_ADC(params)
# adc15.compile_results("~/frida/docs/images/", "behavioral_10b_mismatch")

# # Try fixing with CC Liu 2015 Bin recomb
# params["CDAC"]["individual_weights"] = [240, 128, 64, 36, 20, 10, 6, 3, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 1.0e-9
# params["ADC"]["use_calibration"] = True,  # account for cap error when calculating re-analog results
# adc16 = behavioral.SAR_ADC(params)
# adc16.compile_results("~/frida/docs/images/", "behavioral_10b_mismatch_binrecomb")

# # radix 1.75 normalized so that the total is still 511 (bottom scaling falls apart)
# params["CDAC"]["individual_weights"] = [220, 126, 72, 40, 22, 14, 7, 4, 3, 2, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# params["CDAC"]["settling_time"] = 1.0e-9
# params["ADC"]["use_calibration"] = True,  # account for cap error when calculating re-analog results
# adc17 = behavioral.SAR_ADC(params)
# adc17.compile_results("~/frida/docs/images/", "behavioral_10b_mismatch_radix175norm")