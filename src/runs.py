import behavioral
import matplotlib.pyplot as plt

params = {
    "ADC": {
        # "resolution": 8,  # resolution of the ADC
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
        # "array_size": None,    # NOTE: this param is N but get recomputed to M if radix != 2, and array_N_M_expansion = True
        # "array_N_M_expansion": False,
        "use_individual_weights": True,  # use array values to build cap array
        # "radix": None,  # for the cap values (use_individual_weights = False)
        "individual_weights": [],
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
        "switching_strat": 'monotonic',     # used to determined initial starting voltages
    }
}

# Basic case, without any
params["ADC"]["resolution"] = 10    #FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases
params["COMP"]["threshold_voltage_noise"] = 0e-3
params["COMP"]["capacitor_mismatch_error"] = 0
params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] # 1e-15 unit cap, in Farads at the output of the CDAC, using this just to complete dynamic range
params["CDAC"]["reference_voltage_noise"] = 0e-3
params["CDAC"]["settling_time"] = 0.0e-9
params["CDAC"]["individual_weights"] = [256, 128, 64, 32, 16, 8, 4, 2, 1]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])    #FIXME: shouldn't be a parameter, should be calc'd internally
adc1 = behavioral.SAR_ADC(params)
adc1.compile_results("/users/kcaisley/helena/talks/caeleste2/", "behavioral_10b_ideal")

# # Okay, let's try some thermal noise. Based on my simulation with device noise enabled, I observed 1-2mV of noise
# # A 10-bit design has roughly 1mV bin sizes, so we'd expext this will totally ruin our design.
# params["COMP"]["threshold_voltage_noise"] = 2e-3
# params["CDAC"]["reference_voltage_noise"] = 0e-3
# adc2 = behavioral.SAR_ADC(params)
# adc2.compile_results("/users/kcaisley/helena/talks/caeleste2/", "behavioral_10b_devnoise")


# # Okay, and while reference noise adds in parallel, we'd expect it to less severe for inputs that are close to mid supply.
# params["COMP"]["threshold_voltage_noise"] = 0e-3
# params["CDAC"]["reference_voltage_noise"] = 3e-3
# adc2 = behavioral.SAR_ADC(params)
# adc2.compile_results("/users/kcaisley/helena/talks/caeleste2/", "behavioral_10b_refnoise")


# Okay, okay now let's add both together but use some redundancy to fix it
params["COMP"]["threshold_voltage_noise"] = 2e-3
params["CDAC"]["reference_voltage_noise"] = 3e-3
params["CDAC"]["individual_weights"] = [192, 128, 64, 56, 32, 16, 8, 7, 4, 2, 1, 1]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
adc3 = behavioral.SAR_ADC(params)
adc3.compile_results("/users/kcaisley/helena/talks/caeleste2/", "behavioral_10b_noisy_scadec")