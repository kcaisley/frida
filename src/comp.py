from typing import Any


def generate_topology(
    preamp_diffpair: str, 
    preamp_bias: str,
    comp_stages: str,
    latch_pwrgate_ctl: str,
    latch_pwrgate_node: str,
    latch_rst_extern_ctl: str,
    latch_rst_intern_ctl: str
) -> dict[str, Any]:
    """
    Generate comparator topology based on parameters.

    Args:
        preamp_diffpair: 'nmosinput' or 'pmosinput' - determines input differential pair type
        preamp_bias: 'stdbias' or 'dynbias' - whether to use dynamic biasing with capacitor
        comp_stages: 'singlestage' or 'doublestage' - if singlestage, use strong-arm direct connection (ignores latch params)
        latch_pwrgate_ctl: 'clocked' or 'signalled' - type of powergate control
        latch_pwrgate_node: 'external' or 'internal' - where powergate is positioned
        latch_rst_extern_ctl: 'clocked', 'signalled', or 'noreset' - external reset type (only if latch_pwrgate_node='external')
        latch_rst_intern_ctl: 'clocked' or 'signalled' - internal reset type (always present)

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
            devices['MN_preamp_bias'] = {'dev': 'nmos', 'pins': {'d': 'vcap', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
            devices['C_preamp_bias'] = {'dev': 'cap', 'pins': {'p': 'vcap', 'n': 'vdd'}, 'c': 1}
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
            devices['MP_preamp_bias'] = {'dev': 'pmos', 'pins': {'d': 'vcap', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
            devices['C_preamp_bias'] = {'dev': 'cap', 'pins': {'p': 'vcap', 'n': 'vss'}, 'c': 1}
    
    # LOAD DEVICES (clocked, opposite type from input pair)
    if preamp_diffpair == 'nmosinput':
        devices['MP_preamp_rst_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
        devices['MP_preamp_rst_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
    elif preamp_diffpair == 'pmosinput':
        devices['MN_preamp_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'clkb', 's': 'vss', 'b': 'vss'}}
        devices['MN_preamp_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'clkb', 's': 'vss', 'b': 'vss'}}
    
    # LATCH STAGE
    if comp_stages == 'singlestage':
        # Strong-arm configuration: direct connection with cross-coupled latch and clocked pullup reset
        # Cross-coupled PMOS latch
        devices['MP_latch_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'outp', 's': 'vdd', 'b': 'vdd'}}
        devices['MP_latch_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'outn', 's': 'vdd', 'b': 'vdd'}}
        # Cross-coupled NMOS latch
        devices['MN_latch_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'outp', 's': 'vss', 'b': 'vss'}}
        devices['MN_latch_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'outn', 's': 'vss', 'b': 'vss'}}
        # Clocked reset (PMOS pullups, active low on clkb)
        devices['MP_latch_int_rst_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
        devices['MP_latch_int_rst_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
    elif comp_stages == 'doublestage':
        # Double-stage configuration with powergate options
        # Core cross-coupled CMOS latch (always present)
        devices['MP_latch_p'] = {'dev': 'pmos', 'pins': {'d': 'latchn', 'g': 'latchp', 's': 'latch_vdd', 'b': 'vdd'}}
        devices['MP_latch_n'] = {'dev': 'pmos', 'pins': {'d': 'latchp', 'g': 'latchn', 's': 'latch_vdd', 'b': 'vdd'}}
        devices['MN_latch_p'] = {'dev': 'nmos', 'pins': {'d': 'latchn', 'g': 'latchp', 's': 'latch_vss', 'b': 'vss'}}
        devices['MN_latch_n'] = {'dev': 'nmos', 'pins': {'d': 'latchp', 'g': 'latchn', 's': 'latch_vss', 'b': 'vss'}}
        
        # Connection from preamp to latch
        devices['MN_preamp_to_latch_p'] = {'dev': 'nmos', 'pins': {'d': 'latchn', 'g': 'outn', 's': 'vss', 'b': 'vss'}}
        devices['MN_preamp_to_latch_n'] = {'dev': 'nmos', 'pins': {'d': 'latchp', 'g': 'outp', 's': 'vss', 'b': 'vss'}}
        
        # POWERGATE CONFIGURATION
        if latch_pwrgate_node == 'external':
            # Powergate at external node (between preamp and latch or at supply)
            if latch_pwrgate_ctl == 'clocked':
                devices['MP_latch_ext_powergate_p'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
                devices['MP_latch_ext_powergate_n'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
            elif latch_pwrgate_ctl == 'signalled':
                devices['MP_latch_ext_powergate_p'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'latchn', 's': 'vdd', 'b': 'vdd'}}
                devices['MP_latch_ext_powergate_n'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'latchp', 's': 'vdd', 'b': 'vdd'}}
            # External reset (if not noreset)
            if latch_rst_extern_ctl == 'clocked':
                devices['MP_latch_ext_rst_p'] = {'dev': 'pmos', 'pins': {'d': 'latchn', 'g': 'clkb', 's': 'latch_vdd', 'b': 'vdd'}}
                devices['MP_latch_ext_rst_n'] = {'dev': 'pmos', 'pins': {'d': 'latchp', 'g': 'clkb', 's': 'latch_vdd', 'b': 'vdd'}}
            elif latch_rst_extern_ctl == 'signalled':
                devices['MP_latch_ext_rst_p'] = {'dev': 'pmos', 'pins': {'d': 'latchn', 'g': 'latchn', 's': 'latch_vdd', 'b': 'vdd'}}
                devices['MP_latch_ext_rst_n'] = {'dev': 'pmos', 'pins': {'d': 'latchp', 'g': 'latchp', 's': 'latch_vdd', 'b': 'vdd'}}
            # No vss connection needed, use direct vss
            devices['MN_latch_vss_conn_p'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'vdd', 's': 'vss', 'b': 'vss'}}
            devices['MN_latch_vss_conn_n'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'vdd', 's': 'vss', 'b': 'vss'}}
            
        elif latch_pwrgate_node == 'internal':
            # Powergate at internal node (no external reset, stacking at bottom)
            # Direct vdd connection
            devices['MP_latch_vdd_conn_p'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'vss', 's': 'vdd', 'b': 'vdd'}}
            devices['MP_latch_vdd_conn_n'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'vss', 's': 'vdd', 'b': 'vdd'}}
            # Powergate at vss side
            if latch_pwrgate_ctl == 'clocked':
                devices['MN_latch_int_powergate'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
            elif latch_pwrgate_ctl == 'signalled':
                devices['MN_latch_int_powergate_p'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss_p', 'g': 'latchp', 's': 'vss', 'b': 'vss'}}
                devices['MN_latch_int_powergate_n'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss_n', 'g': 'latchn', 's': 'vss', 'b': 'vss'}}
        
        # INTERNAL RESET (always present, always pulldown)
        if latch_rst_intern_ctl == 'clocked':
            if latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled':
                # Stack reset on top of signalled powergate
                devices['MN_latch_int_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clkb', 's': 'latch_vss_p', 'b': 'vss'}}
                devices['MN_latch_int_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clkb', 's': 'latch_vss_n', 'b': 'vss'}}
            elif not (latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled'):
                devices['MN_latch_int_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'latchn', 'g': 'clkb', 's': 'latch_vss', 'b': 'vss'}}
                devices['MN_latch_int_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'latchp', 'g': 'clkb', 's': 'latch_vss', 'b': 'vss'}}
        elif latch_rst_intern_ctl == 'signalled':
            if latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled':
                # Stack reset on top of signalled powergate
                devices['MN_latch_int_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'latchn', 's': 'latch_vss_p', 'b': 'vss'}}
                devices['MN_latch_int_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'latchp', 's': 'latch_vss_n', 'b': 'vss'}}
            elif not (latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled'):
                devices['MN_latch_int_rst_p'] = {'dev': 'nmos', 'pins': {'d': 'latchn', 'g': 'latchn', 's': 'latch_vss', 'b': 'vss'}}
                devices['MN_latch_int_rst_n'] = {'dev': 'nmos', 'pins': {'d': 'latchp', 'g': 'latchp', 's': 'latch_vss', 'b': 'vss'}}
        
        # Output buffers from latch to final output
        devices['MP_latch_out_p'] = {'dev': 'pmos', 'pins': {'d': 'outn', 'g': 'latchn', 's': 'vdd', 'b': 'vdd'}}
        devices['MP_latch_out_n'] = {'dev': 'pmos', 'pins': {'d': 'outp', 'g': 'latchp', 's': 'vdd', 'b': 'vdd'}}
        devices['MN_latch_out_p'] = {'dev': 'nmos', 'pins': {'d': 'outn', 'g': 'latchn', 's': 'vss', 'b': 'vss'}}
        devices['MN_latch_out_n'] = {'dev': 'nmos', 'pins': {'d': 'outp', 'g': 'latchp', 's': 'vss', 'b': 'vss'}}
    
    # Build final topology
    topology = {
        "subckt": "comp",
        "ports": ports,
        "devices": devices,
        "meta": {
            "preamp_diffpair": preamp_diffpair,
            "preamp_bias": preamp_bias,
            "comp_stages": comp_stages,
            "latch_pwrgate_ctl": latch_pwrgate_ctl,
            "latch_pwrgate_node": latch_pwrgate_node,
            "latch_rst_extern_ctl": latch_rst_extern_ctl,
            "latch_rst_intern_ctl": latch_rst_intern_ctl,
        },
    }
    
    return topology


def subcircuit():
    """
    Generate all comparator topologies for all parameter combinations.
    
    Sweeps:
        preamp_diffpair: 'nmosinput' or 'pmosinput'
        preamp_bias: 'stdbias' or 'dynbias'
        comp_stages: 'singlestage' or 'doublestage'
        latch_pwrgate_ctl: 'clocked' or 'signalled'
        latch_pwrgate_node: 'external' or 'internal'
        latch_rst_extern_ctl: 'clocked', 'signalled', or 'noreset'
        latch_rst_intern_ctl: 'clocked' or 'signalled'
    
    Returns:
        List of (topology, sweep) tuples
    """
    # Sweep parameters
    preamp_diffpair_list = ['nmosinput', 'pmosinput']
    preamp_bias_list = ['stdbias', 'dynbias']
    comp_stages_list = ['singlestage', 'doublestage']
    latch_pwrgate_ctl_list = ['clocked', 'signalled']
    latch_pwrgate_node_list = ['external', 'internal']
    latch_rst_extern_ctl_list = ['clocked', 'signalled', 'noreset']
    latch_rst_intern_ctl_list = ['clocked', 'signalled']
    
    # Generate all configurations
    all_configurations = []
    
    for preamp_diffpair in preamp_diffpair_list:
        for preamp_bias in preamp_bias_list:
            for comp_stages in comp_stages_list:
                for latch_pwrgate_ctl in latch_pwrgate_ctl_list:
                    for latch_pwrgate_node in latch_pwrgate_node_list:
                        for latch_rst_extern_ctl in latch_rst_extern_ctl_list:
                            for latch_rst_intern_ctl in latch_rst_intern_ctl_list:
                                # Skip invalid combinations
                                if comp_stages == 'singlestage':
                                    # For single stage, latch params don't matter, only generate once
                                    if latch_pwrgate_ctl != 'clocked' or latch_pwrgate_node != 'external' or latch_rst_extern_ctl != 'clocked' or latch_rst_intern_ctl != 'clocked':
                                        continue
                                elif comp_stages == 'doublestage':
                                    # For double stage, external reset only valid if powergate is external
                                    if latch_pwrgate_node == 'internal' and latch_rst_extern_ctl != 'noreset':
                                        continue
                                    # If powergate is external, must have some kind of external reset or noreset is valid
                                    # (actually noreset is valid for external powergate)
                                
                                # Generate topology for this configuration
                                topology = generate_topology(
                                    preamp_diffpair=preamp_diffpair,
                                    preamp_bias=preamp_bias,
                                    comp_stages=comp_stages,
                                    latch_pwrgate_ctl=latch_pwrgate_ctl,
                                    latch_pwrgate_node=latch_pwrgate_node,
                                    latch_rst_extern_ctl=latch_rst_extern_ctl,
                                    latch_rst_intern_ctl=latch_rst_intern_ctl
                                )
                                
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
                                        {'devices': ['MN_preamp_tail', 'MN_preamp_bias', 'MP_preamp_tail', 'MP_preamp_bias'], 'w': [2, 4], 'l': [1, 2]},
                                        {'devices': ['MP_preamp_rst_p', 'MP_preamp_rst_n', 'MN_preamp_rst_p', 'MN_preamp_rst_n'], 'w': [2, 4, 8], 'type': ['lvt', 'svt']},
                                        {'devices': ['MP_latch_p', 'MP_latch_n', 'MN_latch_p', 'MN_latch_n'], 'w': [1, 2, 4], 'type': ['lvt', 'svt']}
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