params_wip = {
    "ADC": {
        "bit_size": 8,                        # nominal resolution of the ADC (switching between netlists)
        "sampling_frequency": 10.0e6,         # sampling rate in Hz, used to driver clock sources
        "jitter": 0.0e-12,                    # aperture jitter in seconds (TBD)
        "device_noise": False,                # enables basic gaussian in behavioral model (CDAC, comparator, switch) and transient noise in SPICE
    },
    "TESTBENCH": {
        "positive_input_voltages": [0.2, 1.2, 20e-6],      # start, end (incl.), and step voltage
        "negative_input_voltages": [1.2, 0.2, 20e-6],
        "use_calibration": False,            # account for cap error when calculating Dout (re-analog)
        "pdk_file": "\"~/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib\" tt",
        "spicedir": None,                    # Use this to write netlist from template
        "rawdir": None,                      # Use this to set SPICE output dir, and to read for parsing
    },
    "SWITCH": {
        "offset_voltage": 0.0e-3,            # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain
        "threshold_voltage_noise": True,
        "type": "passive",                   # supports active, passive, or ideal
        "strength": 4,
    },
    "COMP": {
        "offset_voltage": 0.0e-3,            # offset voltage in Volts
        "common_mode_dependent_offset_gain": 0.0,  # common mode voltage gain
        "threshold_voltage_noise": True,
        "strength": 4,                       # used to size some active devices (SPICE only)
    },
    "CDAC": {
        "positive_reference_voltage": 1.2,   # reference voltage in Volts
        "negative_reference_voltage": 0.0,   # reference voltage in Volts
        "reference_voltage_noise": 0.0e-3,   # reference voltage noise in Volts (CDAC)
        "switching_strat": "monotonic",      # {monotonic, bss} used to determined initial starting voltages
        "unit_capacitance": 1e-15,           # unit capacitance
        "target_capacitance": None,          # Used for alternative 
        "array_size": 8,                     # number of capacitor stages
        "array_N_M_expansion": False,        # Sizing strategy where 
        "multiple_conversions": None,        # List bit positions in C array, with number of repetitions at each
        "use_rdac": False,                   # Set bit position which should 
        "use_offset_cap": False,             # set to 0 farads, if disabled
        "use_split_cap": True,               # set to 0 farads, if disabled
        "parasitic_capacitance": 5.00e-14,   # estimate of capacitance at output (added to SPICE and ideal)
        "settling_time": 0.0e-9,             # individual settling errors per capacitor?
    },
}
