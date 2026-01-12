from typing import Any


def generate_topology(preamp_diffpair: str, preamp_bias: str) -> dict[str, Any]:
    """
    Generate comparator topology based on parameters.

    Args:
        preamp_diffpair: 'nmosinput' or 'pmosinput' - determines input differential pair type
        preamp_bias: 'stdbias' or 'dynbias' - whether to use dynamic biasing with capacitor

    Returns:
        dict with 'subckt', 'ports', 'devices', 'meta'
    """
    
    # Initialize topology components
    devices = {}
    ports = {"inp": "I", "inn": "I", "outp": "O", "outn": "O", "clk": "I", "clkb": "I", "vdd": "B", "vss": "B"}
    
    # INPUT DIFFERENTIAL PAIR
    if preamp_diffpair == 'nmosinput':
        if preamp_bias == 'stdbias':
            # NMOS input, no dynamic biasing
            devices['MN_preamp_diff_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'inp', 's': 'tail', 'b': 'vss'}}
            devices['MN_preamp_diff_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'inn', 's': 'tail', 'b': 'vss'}}
            devices['MN_preamp_tail'] = {'dev': 'nmos', 'pins': {'d': 'tail', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
        elif preamp_bias == 'dynbias':
            # NMOS input, with dynamic biasing
            devices['MN_preamp_diff_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'inp', 's': 'tail', 'b': 'vss'}}
            devices['MN_preamp_diff_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'inn', 's': 'tail', 'b': 'vss'}}
            devices['MN_preamp_tail'] = {'dev': 'nmos', 'pins': {'d': 'tail', 'g': 'clk', 's': 'vcap', 'b': 'vss'}}
            devices['MN_preamp_dynbias'] = {'dev': 'nmos', 'pins': {'d': 'vcap', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
            devices['C_preamp_dynbias'] = {'dev': 'cap', 'pins': {'p': 'vcap', 'n': 'vdd'}, 'c': 1}
    elif preamp_diffpair == 'pmosinput':
        if preamp_bias == 'stdbias':
            # PMOS input, no dynamic biasing
            devices['MP_preamp_diff_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'inp', 's': 'tail', 'b': 'vdd'}}
            devices['MP_preamp_diff_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'inn', 's': 'tail', 'b': 'vdd'}}
            devices['MP_preamp_tail'] = {'dev': 'pmos', 'pins': {'d': 'tail', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
        elif preamp_bias == 'dynbias':
            # PMOS input, with dynamic biasing
            devices['MP_preamp_diff_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'inp', 's': 'tail', 'b': 'vdd'}}
            devices['MP_preamp_diff_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'inn', 's': 'tail', 'b': 'vdd'}}
            devices['MP_preamp_tail'] = {'dev': 'pmos', 'pins': {'d': 'tail', 'g': 'clkb', 's': 'vcap', 'b': 'vdd'}}
            devices['MP_preamp_dynbias'] = {'dev': 'pmos', 'pins': {'d': 'vcap', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
            devices['C_preamp_dynbias'] = {'dev': 'cap', 'pins': {'p': 'vcap', 'n': 'vss'}, 'c': 1}
    
    # LOAD DEVICES (clocked, opposite type from input pair)
    if preamp_diffpair == 'nmosinput':
        devices['MP_preamp_rst_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
        devices['MP_preamp_rst_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
    elif preamp_diffpair == 'pmosinput':
        devices['MN_preamp_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'clkb', 's': 'vss', 'b': 'vss'}}
        devices['MN_preamp_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'clkb', 's': 'vss', 'b': 'vss'}}
    
    # Build final topology
    topology = {
        "subckt": "comp",
        "ports": ports,
        "devices": devices,
        "meta": {
            "preamp_diffpair": preamp_diffpair,
            "preamp_bias": preamp_bias,
        },
    }
    
    return topology


def subcircuit():
    """
    Generate all comparator topologies for all parameter combinations.
    
    Sweeps:
        preamp_diffpair: 'nmosinput' or 'pmosinput'
        preamp_bias: 'stdbias' or 'dynbias'
    
    Returns:
        List of (topology, sweep) tuples (2 × 2 = 4 base configs)
    """
    # Sweep parameters
    preamp_diffpair_list = ['nmosinput', 'pmosinput']
    preamp_bias_list = ['stdbias', 'dynbias']
    
    # Generate all configurations
    all_configurations = []
    
    for preamp_diffpair in preamp_diffpair_list:
        for preamp_bias in preamp_bias_list:
            # Generate topology for this configuration
            topology = generate_topology(preamp_diffpair=preamp_diffpair, preamp_bias=preamp_bias)
            
            # Technology agnostic device sweeps
            sweep = {
                'tech': ['tsmc65', 'tsmc28', 'tower180'],
                'defaults': {
                    'nmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1},
                    'pmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1},
                    'cap': {'c': 1, 'm': 1}
                },
                'sweeps': [
                    {'devices': ['MN_preamp_diff_p', 'MN_preamp_diff_n', 'MP_preamp_diff_p', 'MP_preamp_diff_n'], 'w': [2, 4, 8, 16], 'type': ['lvt', 'svt']},
                    {'devices': ['MN_preamp_tail', 'MN_preamp_dynbias', 'MP_preamp_tail', 'MP_preamp_dynbias'], 'w': [2, 4], 'l': [1, 2]},
                    {'devices': ['MP_preamp_rst_p', 'MP_preamp_rst_n', 'MN_preamp_rst_p', 'MN_preamp_rst_n'], 'w': [2, 4, 8], 'type': ['lvt', 'svt']}
                ]
            }
            
            all_configurations.append((topology, sweep))
    
    return all_configurations


def testbench():
    """
    Tech agnostic testbench netlist description.
    """
    topology = {
        'testbench': 'tb_comp',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
            'Xdut': {'dev': 'comp', 'pins': {'inp': 'inp', 'inn': 'inn', 'outp': 'outp', 'outn': 'outn', 'clk': 'clk', 'clkb': 'clkb', 'vdd': 'vdd', 'vss': 'vss'}}
        },
        'analyses': {
            'mc1': {
                'type': 'montecarlo',
                'numruns': 20,
                'seed': 12345,
                'variations': 'all'
            },
            'tran1': {
                'type': 'tran',
                'stop': 35000,
                'step': 1
            }
        }
    }
    
    return topology