import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import behavioral

params = {
    "ADC": {},
    "COMP": {},
    "CDAC": {},
}

# ADC parameters
params["ADC"]["sampling_frequency"] = 10.0e6  # sampling rate in Hz
params["ADC"]["use_calibration"] = False  # account for cap error when calculating re-analog results

# Comparator parameters
params["COMP"]["offset_voltage"] = 0  # offset voltage in Volts
params["COMP"]["common_mode_dependent_offset_gain"] = 0.0  # common mode voltage gain
params["COMP"]["threshold_voltage_noise"] = 0  # RMS noise voltage in Volts

# CDAC parameters
params["CDAC"]["positive_reference_voltage"] = 1.2  # reference voltage in Volts
params["CDAC"]["negative_reference_voltage"] = 0.0  # reference voltage in Volts
params["CDAC"]["reference_voltage_noise"] = 0  # reference voltage noise in Volts
params["CDAC"]["unit_capacitance"] = 1e-15  # roughly 1um^2 MOM cap
params["CDAC"]["use_individual_weights"] = True  # use array values to build cap array
params["CDAC"]["individual_weights"] = []
params["CDAC"]["capacitor_mismatch_error"] = 0.0  # mismatch error in percent of the unit cap
params["CDAC"]["settling_time"] = 0.0e-9  # TBD: individual settling errors per capacitor?
params["CDAC"]["switching_strat"] = 'monotonic'  # used to determined initial starting voltages

# Basic case: 12-bit split capacitor design
params["ADC"]["resolution"] = 12
params["COMP"]["threshold_voltage_noise"] = 0e-3
params["COMP"]["capacitor_mismatch_error"] = 4
params["CDAC"]["parasitic_capacitance"] = params["CDAC"]["unit_capacitance"] 
params["CDAC"]["reference_voltage_noise"] = 0.5e-3
params["CDAC"]["settling_time"] = 0.5e-9
params["CDAC"]["individual_weights"] = [896, 512 , 288, 160, 80, 48, 24, 16, 8, 6, 3, 2, 2, 1, 1]
params["CDAC"]["array_size"] = len(params["CDAC"]["individual_weights"])
adc1 = behavioral.SAR_ADC(params)
# Use filename as testcase name
testcase = os.path.splitext(os.path.basename(__file__))[0]
# Fast simulation parameters for debugging
adc1.compile_results(testcase=testcase, values_per_bin=10, num_samples=1000, samples_per_bin=1)

print(f"{testcase} analysis completed. Results saved to /results directory.")