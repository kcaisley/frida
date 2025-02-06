import behavioral
import matplotlib.pyplot as plt
import os
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
        "unit_capacitance": 6.75e-16,  # unit capacitance in Farads
        "array_size": 8,
        "use_individual_weights": False,  # use array values to build cap array
        "individual_weights": [0],
        "parasitic_capacitance": 0,  # in Farads at the output of the CDAC
        "radix": 1.80,  # for the cap values (use_individual_weights = False)
        "capacitor_mismatch_error": 0.0,  # mismatch error in percent of the unit cap
        "settling_time": 0.0e-9,  # TBD: individual settling errors per capacitor?
    },
}

adc2 = behavioral.SAR_ADC_BSS(params)
# adc2.sample_and_convert_bss(input_voltage_p=1.2, input_voltage_n=0.80, do_plot=True, do_calculate_energy=True)
adc2.calculate_nonlinearity(do_plot=True)

plt.show()