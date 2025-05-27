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
# params["ADC"]["resolution"] = 12    #FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases
# params["COMP"]["threshold_voltage_noise"] = 0e-3
# params["COMP"]["capacitor_mismatch_error"] = 4
# params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] # 1e-15 unit cap, in Farads at the output of the CDAC, using this just to complete dynamic range
# params["CDAC"]["reference_voltage_noise"] = 0.5e-3
# params["CDAC"]["settling_time"] = 0.5e-9
# params["CDAC"]["individual_weights"] = [896, 512 , 288, 160, 80, 48, 24, 16, 8, 6, 3, 2, 2, 1, 1]
# params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])    #FIXME: shouldn't be a parameter, should be calc'd internally
# adc1 = behavioral.SAR_ADC(params)
# adc1.compile_results("./writing/caeleste3/", "base")


params["ADC"]["resolution"] = 12    #FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases
params["COMP"]["threshold_voltage_noise"] = 0e-3
params["COMP"]["capacitor_mismatch_error"] = 4
params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] # 1e-15 unit cap, in Farads at the output of the CDAC, using this just to complete dynamic range
params["CDAC"]["reference_voltage_noise"] = 0
params["CDAC"]["settling_time"] = 0.5e-9
# params["CDAC"]["individual_weights"] = [2**6, 2**6, 2**6, 2**5, 2**4, 2**3, 2**2, 2**2, 2**1, 2**0, 2**-1, 2**-1, 2**-2, 2**-3, 2**-4, 2**-4]
params["CDAC"]["individual_weights"] = [2**10, 2**10, 2**10, 2**9, 2**8, 2**7, 2**7, 2**6, 2**5, 2**4, 2**4, 2**3, 2**2, 2**1, 2**1, 2**0]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])    #FIXME: shouldn't be a parameter, should be calc'd internally
adc2 = behavioral.SAR_ADC(params)
adc2.compile_results("./writing/caeleste3/", "caeleste_2")