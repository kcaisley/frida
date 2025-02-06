import behavioral
import matplotlib.pyplot as plt
import os

plt.rc("figure", figsize=(8.27, 11.69))  # format all plots as A4 portrait
os.environ["XDG_SESSION_TYPE"] = "xcb" # silence "Warning: Ignoring XDG_SESSION_TYPE=wayland on Gnome"

params = {
    "ADC": {
        "resolution": 8,  # resolution of the ADC
        "sampling_frequency": 10.0e6,  # sampling rate in Hz
        "aperture_jitter": 0.0e-12,  # aperture jitter in seconds (TBD)
        "use_calibration": True,  # account for cap error when calculating re-analog results
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
        "array_size": 8,    # NOTE: this param is N but get increased to M if radix != 2
        "use_individual_weights": False,  # use array values to build cap array
        "individual_weights": [],   # This can't be 
        "parasitic_capacitance": 0,  # in Farads at the output of the CDAC
        "radix": 1.80,  # for the cap values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
    },
}

# sets the caps from top to bottom, as fractions of 100fF
# This doesn't work because it has to be integers
# params["CDAC"]["individual_weights"] = [(100e-15 / 2 / (params["CDAC"]["radix"] ** i) ) for i in range(params["CDAC"]["array_size"])]

adc = behavioral.SAR_ADC(params)

adc.sample_and_convert(input_voltage_p=1.2, input_voltage_n=0.80, do_plot=True, do_calculate_energy=True)
# adc.calculate_nonlinearity(do_plot=True)

# adc.sample_and_convert_bss(0.65, 0.0, do_plot=True, do_calculate_energy=True) # plot SAR iterations, for one input
# adc.calculate_conversion_energy(do_plot=True)  # calculate conversion energy
# adc.plot_transfer_function()  # plot transfer function
# adc.calculate_nonlinearity(do_plot=True)  # calculate DNL/INL
# adc.calculate_enob(do_plot=True) # calculate ENOB

adc.compile_results()  # essentially includes everything above

# CDAC only
# dac = behavioral.CDAC_BSS(params, adc)
# dac.calculate_nonlinearity(do_plot=True)

plt.show()

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

