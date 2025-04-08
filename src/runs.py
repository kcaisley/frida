import behavioral
import matplotlib.pyplot as plt

params = {
    "ADC": {
        "resolution": 8,  # resolution of the ADC
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

# Define the values to loop through
# threshold_voltage_noises = [0e-3, 2e-3, 4e-3] # mV noise
# reference_voltage_noises = [0e-3, 2e-3, 4e-3] # mV noise, note that this is ameliorated by larger total CDAC capacitance
# capacitor_mismatch_error = [0.0, 0.5, 1.0]  # stdev of mismatch in percentage
# offset_voltages = [0e-3, 2e-3, 4e-3] # not really sure about this number, but could simulate it.
# settling_times = [0, 5e-9, 10e-9] # The CDAC time constant. Based on 2X ideal simulation, I expect the settling time to be on order of single digit ns, so ~ 5ns.
# We assume drivers are sized to ensure equal settling time on each node.

# array_sizes = [10,12,16,20] # number of capacitor bit positions, this is used to find percentage settling. More than 20 doesn't make sense as
# array_size = 16
# for i in range(2**array_size):
#     repeat_points = [int(bit) for bit in bin(i)[2:].zfill(array_size)]
#     print(repeat_points)

# Wait, even if the settling time constant is the same for all caps, for large voltage steps (in MSBs) the error in absolute mV will be largest

# Loop through the values and modify the dictionary
# for a in threshold_voltage_noises:
#     for b in reference_voltage_noises:
#         # Update the values in the dictionary
#         params["COMP"]["threshold_voltage_noise"] = a
#         params["CDAC"]["reference_voltage_noise"] = b

# After building a database of values, try using `scipy.optimize` library to find the right values.


# plt.rc("figure", figsize=(8.27, 11.69))  # format all plots as A4 portrait
# plt.rcParams['savefig.dpi'] = 300        # Default dpi
# plt.rcParams['savefig.bbox'] = 'tight'   # Default bbox_inches

params["ADC"]["resolution"] = 10    #FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases
params["COMP"]["threshold_voltage_noise"] = 0e-3
params["COMP"]["capacitor_mismatch_error"] = 0
params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] # 1e-15 unit cap, in Farads at the output of the CDAC, using this just to complete dynamic range
params["CDAC"]["reference_voltage_noise"] = 0e-3
params["CDAC"]["settling_time"] = 0.0e-9
params["CDAC"]["individual_weights"] = [256, 128, 64, 32, 16, 8, 4, 2, 1]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])    #FIXME: shouldn't be a parameter, should be calc'd internally

adc1 = behavioral.SAR_ADC(params)

adc1.compile_results()

params["COMP"]["threshold_voltage_noise"] = 10e-3

adc2 = behavioral.SAR_ADC(params)
adc2.compile_results()