params = {
    "ADC": {
        "resolution": 8,  # resolution of the ADC
        "sampling_frequency": 10.0e6,  # sampling rate in Hz
        "use_calibration": False,  # account for cap error when calculating re-analog results
    },
    "COMP": {
        "offset_voltage": None,  # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain
        "threshold_voltage_noise":None,  # RMS noise voltage in Volts
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,  # reference voltage in Volts
        "negative_reference_voltage": 0.0,  # reference voltage in Volts
        "reference_voltage_noise": None,  # reference voltage noise in Volts
        "unit_capacitance": 1e-15, # roughly 1um^2 MOM cap
        "array_size": None,    # NOTE: this param is N but get recomputed to M if radix != 2, and array_N_M_expansion = True
        "array_N_M_expansion": False,
        "use_individual_weights": False,  # use array values to build cap array
        "individual_weights": [],
        "parasitic_capacitance": 5.00e-14,  # in Farads at the output of the CDAC
        "radix": None,  # for the cap values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
        "switching_strat": 'monotonic',     # used to determined initial starting voltages
    },
    # Note that I shouldn't have to manually provide simulation_time and inputs, as these could be calculated given parasitic capacitance
    "TESTBENCH": {
        'simulation_times':        [0,   6000e-6],  # starting and ending sim times, matching with bottom voltages to make pwl
        "positive_input_voltages": [0.2, 1.2],      # starting and ending voltages of the pwl voltage waveform
        "negative_input_voltages": [1.2, 0.2],
        "spicedir": None,   # Use this to write netlist from template
        "rawdir": None,     # Use this to set set SPICE output dir, and to read for parsing.
    },
}

# Define the values to loop through
threshold_voltage_noises = [0e-3, 2e-3, 4e-3] # mV noise
reference_voltage_noises = [0e-3, 2e-3, 4e-3] # mV noise, note that this is ameliorated by larger total CDAC capacitance
capacitor_mismatch_error = [0.0, 0.5, 1.0]  # stdev of mismatch in percentage
offset_voltages = [0e-3, 2e-3, 4e-3] # not really sure about this number, but could simulate it.
settling_times = [0, 5e-9, 10e-9] # The CDAC time constant. Based on 2X ideal simulation, I expect the settling time to be on order of single digit ns, so ~ 5ns. We assume drivers are sized to ensure equal settling time on each node.



array_sizes = [10,12,16,20] # number of capacitor bit positions, this is used to find percentage settling. More than 20 doesn't make sense as
array_size = 16
for i in range(2**array_size):
    repeat_points = [int(bit) for bit in bin(i)[2:].zfill(array_size)]
    print(repeat_points)



# Wait, even if the settling time constant is the same for all caps, for large voltage steps (in MSBs) the error in absolute mV will be largest

# Loop through the values and modify the dictionary
# for a in threshold_voltage_noises:
#     for b in reference_voltage_noises:
#         # Update the values in the dictionary
#         params["COMP"]["threshold_voltage_noise"] = a
#         params["CDAC"]["reference_voltage_noise"] = b

# After building a database of values, try using `scipy.optimize` library to find the right values.
