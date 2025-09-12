import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import behavioral
import matplotlib.pyplot as plt

params = {
    "ADC": {},
    "COMP": {},
    "CDAC": {},
}

# ADC parameters
params["ADC"]["sampling_frequency"] = 10.0e6  # sampling rate in Hz
params["ADC"]["use_calibration"] = False  # account for cap error when calculating re-analog results
params["ADC"]["resolution"] = 12  # FIXME: I should remove this resolution term from the top level, as it doesn't seem to work for all cases

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
params["CDAC"]["individual_weights"] = []  # Will fill this later
params["CDAC"]["parasitic_capacitance"] = 0  # reduces trans func slope
params["CDAC"]["capacitor_mismatch_error"] = 0.0  # mismatch error in percent of the unit cap
params["CDAC"]["settling_time"] = 0.0e-9  # TBD: individual settling errors per capacitor?
params["CDAC"]["switching_strat"] = 'monotonic'  # used to determined initial starting voltages
params["CDAC"]["array_size"] = 16  # number of stages in CDAC

# Initialize ADCs
params["CDAC"]["individual_weights"] = [64, 64, 64, 32, 16, 8, 4, 4, 2, 1, 0.5, 0.5, 0.25, 0.125, 0.0625, 0.0625]
adc1 = behavioral.SAR_ADC(params)

params["CDAC"]["individual_weights"] = [64, 64, 64, 32, 16, 8, 8, 4, 2, 1, 1, 0.5, 0.25, 0.125, 0.125, 0.0625]
adc2 = behavioral.SAR_ADC(params)

params["CDAC"]["individual_weights"] = [64, 64, 64, 32, 18, 12, 8, 4, 2, 1.5, 1, 0.5, 0.25, 0.1875, 0.125, 0.0625]
adc3 = behavioral.SAR_ADC(params)

# Normalizing to weights[-1] would be:
# norm = [i / weights[-1] for i in weights]

# Calculate data without plotting
adc1.calculate_redundancy(do_plot=False)
adc2.calculate_redundancy(do_plot=False)
adc3.calculate_redundancy(do_plot=False)

# Get step_ticks (assuming same for all ADCs)
step_ticks = list(range(len(adc1.redundancy)))

# Manually plot all on the same figure
fig, ax = plt.subplots(figsize=(10, 8))
ax.plot(step_ticks, adc1.redundancy, 'o-', label="ADC 1")
ax.plot(step_ticks, adc2.redundancy, 'o-', label="ADC 2")
ax.plot(step_ticks, adc3.redundancy, 'o-', label="ADC 3")


ax.set_xlabel("Conversion Cycle [i]")
ax.set_ylabel("Error Tolerance [%]")
ax.set_ylim(-35, 55)
ax.grid(True)
ax.legend(loc="upper right")
plt.title("Relative Error Tolerance @ Cycle [i] in Percent [%]")

# Force integer x-axis ticks (since step_ticks are integers)
ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

plt.tight_layout()

# Create results directory
import os
results_dir = os.path.join(os.getcwd(), "results")
os.makedirs(results_dir, exist_ok=True)

plt.savefig(os.path.join(results_dir, "redundancy.pdf"))
plt.close()  # Close the figure instead of showing it