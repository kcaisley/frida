import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import behavioral
import spice
import matplotlib.pyplot as plt
import math
import pandas as pd

plt.rc("figure", figsize=(8.27, 11.69))  # format all plots as A4 portrait
os.environ["XDG_SESSION_TYPE"] = "xcb" # silence "Warning: Ignoring XDG_SESSION_TYPE=wayland on Gnome"
pd.set_option('display.precision', 8)
pd.options.mode.copy_on_write = True

# eventually, need to pull the init code out, so that

params = {
    "ADC": {
        "resolution": 8,  # resolution of the ADC
        "sampling_frequency": 10.0e6,  # sampling rate in Hz
        "aperture_jitter": 0.0e-12,  # aperture jitter in seconds (TBD)
        "use_calibration": False,  # account for cap error when calculating re-analog results
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
        "unit_capacitance": 0.8167e-15,  # unit capacitance in Farads (~0.8167 allows for Ctot per branch to ~100fF)
        "array_size": 8,    # NOTE: this param is N but get recomputed to M if radix != 2, and array_N_M_expansion = True
        "array_N_M_expansion": False,
        "use_individual_weights": False,  # use array values to build cap array
        "individual_weights": [],   # This can't be
        "parasitic_capacitance": 5.00e-14,  # in Farads at the output of the CDAC
        "radix": 1.80,  # for the cap values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
        "switching_strat": 'monotonic',     #used to determined initial starting voltages
    },
    "TESTBENCH": {
        'simulation_times':        [0,   6000e-6],  # starting and ending sim times, matching with bottom voltages to make pwl
        "positive_input_voltages": [0.2, 1.2],      # starting and ending voltages of the pwl voltage waveform
        "negative_input_voltages": [1.2, 0.2],
        "spicedir": None,   # Use this to write netlist from template
        "rawdir": None,     # Use this to set set SPICE output dir, and to read for parsing.
    },
}

# sets the caps from top to bottom, as fractions of 100fF
# This doesn't work because it has to be integers
# params["CDAC"]["individual_weights"] = [(100e-15 / 2 / (params["CDAC"]["radix"] ** i) ) for i in range(params["CDAC"]["array_size"])]

adc = behavioral.SAR_ADC(params)

# Create the behavioral simulation DataFrame
behavioral_df = pd.DataFrame(columns=["time", "inp", "inn", "Dout"])

num_rows = int(params["TESTBENCH"]["simulation_times"][1] * params["ADC"]["sampling_frequency"])

# FIXME: This could be simplified, as we already find the time step below, so we can just increment it to calculate the time step
# note the -1 missing, which we include in the expression below...
behavioral_df["time"] = [params["TESTBENCH"]["simulation_times"][0] + i * (params["TESTBENCH"]["simulation_times"][1] - params["TESTBENCH"]["simulation_times"][0]) / (num_rows) for i in range(num_rows)]
# Round the 'time' column to the nearest 1e-7, or whatever the sampling frequency
behavioral_df["time"] = behavioral_df["time"].round(int(-math.log10(1/params["ADC"]["sampling_frequency"])))

behavioral_df["inp"] = [params["TESTBENCH"]["positive_input_voltages"][0] + i * (params["TESTBENCH"]["positive_input_voltages"][1] - params["TESTBENCH"]["positive_input_voltages"][0]) / (len(behavioral_df) - 1) for i in range(len(behavioral_df))]
behavioral_df["inn"] = [params["TESTBENCH"]["negative_input_voltages"][0] + i * (params["TESTBENCH"]["negative_input_voltages"][1] - params["TESTBENCH"]["negative_input_voltages"][0]) / (len(behavioral_df) - 1) for i in range(len(behavioral_df))]
behavioral_df["Vin"] = behavioral_df["inp"] - behavioral_df["inn"]

dout_series = pd.Series(index=behavioral_df.index, dtype=float)

adc.sample_and_convert(
        0.792,
        0.6104,
        # 0.8,
        # 0.6,
        do_plot=True,
        do_calculate_energy=False,
        do_normalize_result=False,
)

print("Running conversions for behavioral sim...")
for i in range(len(behavioral_df)):
    dout_series[i] = adc.sample_and_convert(
        behavioral_df.iloc[i]["inp"],
        behavioral_df.iloc[i]["inn"],
        do_plot=False,
        do_calculate_energy=False,
        do_normalize_result=False,
)

behavioral_df["Dout"] = dout_series

# Drop this for now, to make the analysis easier
behavioral_df = behavioral_df.drop(columns=['time'])

print("-----Behavioral dataframe-----")
print(behavioral_df)

# FIXME: rawfile, use radix from params, etc
# FIXME: note I'm overwri
spice_df = spice.parse_to_df(rawfile='spiceout/SB_saradc8_radixN_1.8/SB_saradc8_radixN_1.8.csv', radix=params["CDAC"]["radix"], array_size=params["CDAC"]["array_size"], time=2000e-6, vdd=params["CDAC"]["positive_reference_voltage"])
spice_df = spice_df.drop(columns=['comz_p', 'comz_n', 'data<0>', 'data<1>', 'data<2>', 'data<3>', 'data<4>', 'data<5>', 'data<6>', 'data<7>'])
spice_df = spice_df.drop(columns=['Time'])

# there are two issues with the current SPICE dataset: 1) The dout polarity is swapped, and our data is single sided right now.
# Let's make up some data to fix this for now (FIXME!!!!)
spice_df["Dout"] = (-1 * spice_df["Dout"]) - 0.5
spice_negative = spice_df.iloc[::-1].reset_index(drop=True)

spice_df["Dout"] = -1 * (spice_df["Dout"])
spice_df.loc[:, ['inp', 'inn']] = spice_df.loc[:, ['inn', 'inp']].values
spice_positive = spice_df
# Stack the DataFrames on top of each other
spice_df = pd.concat([spice_negative, spice_positive], ignore_index=True)
# Reset the index
spice_df = spice_df.reset_index(drop=True)
spice_df["Vin"] = spice_df["inp"] - spice_df["inn"]

print("-----SPICE dataframe-----")
print(spice_df)

# Drop rows where Dout is greater than 0.83 or less than -0.83
behavioral_df = behavioral_df.drop(behavioral_df[(behavioral_df["Vin"] > 0.6) | (behavioral_df["Vin"] < -0.6)].index)
behavioral_df = behavioral_df.reset_index(drop=True)

behavioral_df, behavioral_dout_rounded_histo, behavioral_dout_averaged, behavioral_rms_dnl = spice.df_linearity_analyze(behavioral_df)

spice_df, spice_dout_rounded_histo, spice_dout_averaged, spice_rms_dnl = spice.df_linearity_analyze(spice_df)


print("-----Behavioral dataframe-----")
print(behavioral_df)

print("-----SPICE dataframe-----")
print(spice_df)

# fig1, ax1 = spice.plot_df_linearity(behavioral_df, behavioral_dout_rounded_histo, behavioral_dout_averaged, behavioral_rms_dnl, title="behavioral")

# fig2, ax2 = spice.plot_df_linearity(spice_df, spice_dout_rounded_histo, spice_dout_averaged, spice_rms_dnl, title="spice")


# FIXME: I should just be able to bundle these different data points together:
spice.plot_df_linearity_compare(behavioral_df, behavioral_dout_rounded_histo, behavioral_dout_averaged, behavioral_rms_dnl, spice_df, spice_dout_rounded_histo, spice_dout_averaged, spice_rms_dnl)

plt.show()

# adc.sample_and_convert(input_voltage_p=1.2, input_voltage_n=0.0, do_plot=True, do_calculate_energy=True)
# adc.calculate_nonlinearity(do_plot=True)

# adc.sample_and_convert_bss(0.65, 0.0, do_plot=True, do_calculate_energy=True) # plot SAR iterations, for one input
# adc.calculate_conversion_energy(do_plot=True)  # calculate conversion energy
# adc.plot_transfer_function()  # plot transfer function
# adc.calculate_nonlinearity(do_plot=True)  # calculate DNL/INL
# adc.calculate_enob(do_plot=True) # calculate ENOB

# adc.compile_results()  # essentially includes everything above

# CDAC only
# dac = behavioral.CDAC_BSS(params, adc)
# dac.calculate_nonlinearity(do_plot=True)

# Old code blocks for reference

######################################################################################
# Performance analysis
######################################################################################

# calculate and gather all performance parameters


# parametric ENOB calculation

# adc_b  = SAR_ADC_BSS(params)
# adc_nb = SAR_ADC_BSS(params)
# enob_b  = []
# enob_nb = []
# error_array = []
# adc_b.dac.params['use_individual_weights'] = False
# adc_b.dac.params['radix'] = 2
# adc_b.update_parameters()
# adc_nb.dac.params['use_individual_weights'] = False
# adc_nb.dac.params['radix'] = 1.8
# adc_nb.update_parameters()
# # TODO: add more error types and values
# error_index  = 1
# error_steps  = 4
# error_params = [
#   ('capacitor_mismatch_error', ' [%]',    30),
#   ('settling_time',            ' [s]',  5e-9),
#   ('reference_voltage_noise',  ' [V]', 10e-3),
#   ('offset_voltage',           ' [V]',  5e-3),
#   ('threshold_voltage_noise',  ' [V]',  5e-3)
# ]
# error_type, error_unit, error_max_value = error_params[error_index]
# for error in np.arange(0, error_max_value, error_max_value/error_steps):
#   error_array.append(error)
#   adc_b.dac.params[error_type]  = error
#   adc_nb.dac.params[error_type] = error
#   adc_b.update_parameters()
#   adc_nb.update_parameters()
#   adc_b.calculate_enob()
#   adc_nb.calculate_enob()
#   enob_b.append(adc_b.enob)
#   enob_nb.append(adc_nb.enob)
# figure, plot = plt.subplots(1, 1)
# plot.plot(error_array, enob_b, label='Binary weighted capacitors')
# plot.plot(error_array, enob_nb, label='Non-binary weighted capacitors')
# x_label = error_type + error_unit
# plot.set_xlabel(x_label)
# plot.set_ylabel('ENOB')
# plot.legend()
