"""
Sampling switch subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/devices
for each switch_type variant.
"""

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "samp",
    "ports": {},      # Empty - computed by generate_topology()
    "devices": {},    # Empty - computed by generate_topology()
    "meta": {},
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "topo_params": {
        "switch_type": ["nmos", "pmos", "tgate"]
    },
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1}
    },
    "inst_params": [
        {"devices": ["MN", "MP"], "w": [5, 10, 20, 40], "l": [1, 2]}
    ]
}


def generate_topology(switch_type: str) -> tuple[dict, dict]:
    """
    Compute ports and devices for given switch_type.

    Called by expand_topo_params() for each topo_params combination.

    Args:
        switch_type: 'nmos', 'pmos', or 'tgate' - determines switch implementation

    Returns:
        Tuple of (ports, devices)
    """
    # Common ports for all switch types
    ports = {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"}

    # Initialize devices
    devices = {}

    if switch_type == 'nmos':
        # NMOS pass transistor (conducts when clk is high)
        # Note: clk_b pin unused (left floating for interface compatibility)
        devices['MN'] = {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'clk', 's': 'in', 'b': 'vss'}}

    elif switch_type == 'pmos':
        # PMOS pass transistor (conducts when clk_b is low)
        # Note: clk pin unused (left floating for interface compatibility)
        devices['MP'] = {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'clk_b', 's': 'in', 'b': 'vdd'}}

    elif switch_type == 'tgate':
        # Transmission gate (NMOS + PMOS in parallel)
        devices['MN'] = {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'clk', 's': 'in', 'b': 'vss'}}
        devices['MP'] = {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'clk_b', 's': 'in', 'b': 'vdd'}}

    return ports, devices


"""
Sample-and-Hold Testbench:

Tests sampling switch at multiple input frequencies and amplitudes.

Test structure:
- DC voltage staircase + sine wave sources at 10MHz, 100MHz, 200MHz, 500MHz, 1GHz
- Source impedance (1kΩ) and load capacitor (1pF)
- Clock signals for sampling (50% duty cycle, 100ns period)
- Monte Carlo analysis with process variations

Characterizes switch performance: bandwidth, THD, settling time
"""

# Monolithic testbench struct (static topology - uses switch_type for matching only)
tb = {
    "devices": {
        'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
        'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
        'Vin_dc': {
            'dev': 'vsource',
            'pins': {'p': 'in_driver', 'n': 'gnd'},
            'wave': 'pwl',
            'points': [0, 0, 1, 0, 1, 0.1, 21, 0.1, 21, 0.2, 41, 0.2, 41, 0.3, 61, 0.3, 61, 0.4, 81, 0.4, 81, 0.5, 101, 0.5, 101, 0.6, 121, 0.6, 121, 0.7, 141, 0.7, 141, 0.8, 161, 0.8, 161, 0.9, 181, 0.9, 181, 1.0, 201, 1.0, 201, 0.5, 250, 0.5]
        },
        'Vin_10M': {'dev': 'vsource', 'pins': {'p': 'in_driver', 'n': 'gnd'}, 'wave': 'sine', 'dc': 0.5, 'ampl': 0.5, 'freq': 10e6, 'delay': 201},
        'Vin_100M': {'dev': 'vsource', 'pins': {'p': 'in_driver', 'n': 'gnd'}, 'wave': 'sine', 'dc': 0.5, 'ampl': 0.5, 'freq': 100e6, 'delay': 226},
        'Vin_200M': {'dev': 'vsource', 'pins': {'p': 'in_driver', 'n': 'gnd'}, 'wave': 'sine', 'dc': 0.5, 'ampl': 0.5, 'freq': 200e6, 'delay': 251},
        'Vin_500M': {'dev': 'vsource', 'pins': {'p': 'in_driver', 'n': 'gnd'}, 'wave': 'sine', 'dc': 0.5, 'ampl': 0.5, 'freq': 500e6, 'delay': 276},
        'Vin_1G': {'dev': 'vsource', 'pins': {'p': 'in_driver', 'n': 'gnd'}, 'wave': 'sine', 'dc': 0.5, 'ampl': 0.5, 'freq': 1e9, 'delay': 301},
        'Rsrc': {'dev': 'res', 'pins': {'p': 'in_driver', 'n': 'in'}, 'params': {'r': 1e3}},
        'Cload': {'dev': 'cap', 'pins': {'p': 'out', 'n': 'vss'}, 'params': {'c': 1e-12}},
        'Vclk': {'dev': 'vsource', 'pins': {'p': 'clk', 'n': 'gnd'}, 'wave': 'pulse', 'v1': 0, 'v2': 1.0, 'td': 0, 'tr': 0, 'tf': 0, 'pw': 50, 'per': 100},
        'Vclk_b': {'dev': 'vsource', 'pins': {'p': 'clk_b', 'n': 'gnd'}, 'wave': 'pulse', 'v1': 1.0, 'v2': 0, 'td': 0, 'tr': 0, 'tf': 0, 'pw': 50, 'per': 100},
        'Xdut': {'dev': 'samp', 'pins': {'in': 'in', 'out': 'out', 'clk': 'clk', 'clk_b': 'clk_b', 'vdd': 'vdd', 'vss': 'vss'}}
    },
    "analyses": {
        'mc1': {
            'type': 'montecarlo',
            'numruns': 20,
            'seed': 12345,
            'variations': 'all'
        },
        'tran1': {
            'type': 'tran',
            'stop': 326,
            'strobeperiod': 50,
            'noisefmax': 10e9,
            'noiseseed': 1,
            'param': 'isnoisy',
            'param_vec': [0, 1, 201, 0]
        }
    },
    "corner": ["tt"],
    "temp": [27],
    "topo_params": {
        "switch_type": ["nmos", "pmos", "tgate"]
    }
}


def measure(raw, subckt_json, tb_json, raw_file):
    """
    Measure sampling switch simulation results.

    TODO: This function needs to be fleshed out and completed.
    """
    from flow.measure import read_traces, quantize, diff, comm, write_analysis
    import numpy as np

    time, vin, vout, vclk, vclkb, vdda, vssa = read_traces(raw)

    qvclk = quantize(vclk, bits=1, max=1.2, min=0)
    vdiff = diff(vin, vout)
    vcomm = comm(vin, vout)

    max_error_V = float(np.max(np.abs(vdiff)))
    rms_error_V = float(np.sqrt(np.mean(vdiff**2)))

    write_analysis(raw_file, time, vin, vout, vclk, vclkb, vdda, vssa, qvclk, vdiff, vcomm, max_error_V, rms_error_V)
