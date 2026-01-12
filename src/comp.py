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
    ports = {"in+": "I", "in-": "I", "out+": "O", "out-": "O", "clk": "I", "clkb": "I", "vdd": "B", "vss": "B"}

    # Generate entire topology assuming NMOS input, will swap at end if PMOS

    # INPUT DIFFERENTIAL PAIR (assuming NMOS)
    if preamp_bias == 'stdbias':
        # NMOS input, no dynamic biasing
        devices['M_preamp_diff+'] = {'dev': 'nmos', 'pins': {'d': 'out-', 'g': 'in+', 's': 'tail', 'b': 'vss'}}
        devices['M_preamp_diff-'] = {'dev': 'nmos', 'pins': {'d': 'out+', 'g': 'in-', 's': 'tail', 'b': 'vss'}}
        devices['M_preamp_tail'] = {'dev': 'nmos', 'pins': {'d': 'tail', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
    elif preamp_bias == 'dynbias':
        # NMOS input, with dynamic biasing
        devices['M_preamp_diff+'] = {'dev': 'nmos', 'pins': {'d': 'out-', 'g': 'in+', 's': 'tail', 'b': 'vss'}}
        devices['M_preamp_diff-'] = {'dev': 'nmos', 'pins': {'d': 'out+', 'g': 'in-', 's': 'tail', 'b': 'vss'}}
        devices['M_preamp_tail'] = {'dev': 'nmos', 'pins': {'d': 'tail', 'g': 'clk', 's': 'vcap', 'b': 'vss'}}
        devices['M_preamp_bias'] = {'dev': 'nmos', 'pins': {'d': 'vcap', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
        devices['C_preamp_bias'] = {'dev': 'cap', 'pins': {'p': 'vcap', 'n': 'vdd'}, 'c': 1}

    # LOAD DEVICES (clocked, opposite type from input pair - PMOS for NMOS input)
    devices['M_preamp_rst+'] = {'dev': 'pmos', 'pins': {'d': 'out-', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
    devices['M_preamp_rst-'] = {'dev': 'pmos', 'pins': {'d': 'out+', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}

    # LATCH STAGE
    if comp_stages == 'singlestage':
        # Strong-arm configuration: direct connection with cross-coupled latch and clocked pullup reset
        # Cross-coupled PMOS latch
        devices['Ma_latch+'] = {'dev': 'pmos', 'pins': {'d': 'out-', 'g': 'out+', 's': 'vdd', 'b': 'vdd'}}
        devices['Ma_latch-'] = {'dev': 'pmos', 'pins': {'d': 'out+', 'g': 'out-', 's': 'vdd', 'b': 'vdd'}}
        # Cross-coupled NMOS latch
        devices['Mb_latch+'] = {'dev': 'nmos', 'pins': {'d': 'out-', 'g': 'out+', 's': 'vss', 'b': 'vss'}}
        devices['Mb_latch-'] = {'dev': 'nmos', 'pins': {'d': 'out+', 'g': 'out-', 's': 'vss', 'b': 'vss'}}
        # Clocked reset (PMOS pullups, active low on clkb)
        devices['M_latch_int_rst+'] = {'dev': 'pmos', 'pins': {'d': 'out-', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
        devices['M_latch_int_rst-'] = {'dev': 'pmos', 'pins': {'d': 'out+', 'g': 'clkb', 's': 'vdd', 'b': 'vdd'}}
    elif comp_stages == 'doublestage':
        # Double-stage configuration with powergate options
        # Core cross-coupled CMOS latch (always present)
        devices['Ma_latch+'] = {'dev': 'pmos', 'pins': {'d': 'latch-', 'g': 'latch+', 's': 'latch_vdd', 'b': 'vdd'}}
        devices['Ma_latch-'] = {'dev': 'pmos', 'pins': {'d': 'latch+', 'g': 'latch-', 's': 'latch_vdd', 'b': 'vdd'}}
        devices['Mb_latch+'] = {'dev': 'nmos', 'pins': {'d': 'latch-', 'g': 'latch+', 's': 'latch_vss', 'b': 'vss'}}
        devices['Mb_latch-'] = {'dev': 'nmos', 'pins': {'d': 'latch+', 'g': 'latch-', 's': 'latch_vss', 'b': 'vss'}}

        # Connection from preamp to latch
        devices['M_preamp_to_latch+'] = {'dev': 'nmos', 'pins': {'d': 'latch-', 'g': 'out-', 's': 'vss', 'b': 'vss'}}
        devices['M_preamp_to_latch-'] = {'dev': 'nmos', 'pins': {'d': 'latch+', 'g': 'out+', 's': 'vss', 'b': 'vss'}}

        # POWERGATE CONFIGURATION
        if latch_pwrgate_node == 'external':
            # Powergate at external node (between preamp and latch or at supply)
            if latch_pwrgate_ctl == 'clocked':
                devices['M_latch_ext_powergate+'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
                devices['M_latch_ext_powergate-'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}}
            elif latch_pwrgate_ctl == 'signalled':
                devices['M_latch_ext_powergate+'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'latch-', 's': 'vdd', 'b': 'vdd'}}
                devices['M_latch_ext_powergate-'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'latch+', 's': 'vdd', 'b': 'vdd'}}
            # External reset (if not noreset)
            if latch_rst_extern_ctl == 'clocked':
                devices['M_latch_ext_rst+'] = {'dev': 'pmos', 'pins': {'d': 'latch-', 'g': 'clkb', 's': 'latch_vdd', 'b': 'vdd'}}
                devices['M_latch_ext_rst-'] = {'dev': 'pmos', 'pins': {'d': 'latch+', 'g': 'clkb', 's': 'latch_vdd', 'b': 'vdd'}}
            elif latch_rst_extern_ctl == 'signalled':
                devices['M_latch_ext_rst+'] = {'dev': 'pmos', 'pins': {'d': 'latch-', 'g': 'latch-', 's': 'latch_vdd', 'b': 'vdd'}}
                devices['M_latch_ext_rst-'] = {'dev': 'pmos', 'pins': {'d': 'latch+', 'g': 'latch+', 's': 'latch_vdd', 'b': 'vdd'}}
            # No vss connection needed, use direct vss
            devices['M_latch_vss_conn+'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'vdd', 's': 'vss', 'b': 'vss'}}
            devices['M_latch_vss_conn-'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'vdd', 's': 'vss', 'b': 'vss'}}

        elif latch_pwrgate_node == 'internal':
            # Powergate at internal node (no external reset, stacking at bottom)
            # Direct vdd connection
            devices['M_latch_vdd_conn+'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'vss', 's': 'vdd', 'b': 'vdd'}}
            devices['M_latch_vdd_conn-'] = {'dev': 'pmos', 'pins': {'d': 'latch_vdd', 'g': 'vss', 's': 'vdd', 'b': 'vdd'}}
            # Powergate at vss side
            if latch_pwrgate_ctl == 'clocked':
                devices['M_latch_int_powergate'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clk', 's': 'vss', 'b': 'vss'}}
            elif latch_pwrgate_ctl == 'signalled':
                devices['M_latch_int_powergate+'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss+', 'g': 'latch+', 's': 'vss', 'b': 'vss'}}
                devices['M_latch_int_powergate-'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss-', 'g': 'latch-', 's': 'vss', 'b': 'vss'}}

        # INTERNAL RESET (always present, always pulldown)
        if latch_rst_intern_ctl == 'clocked':
            if latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled':
                # Stack reset on top of signalled powergate
                devices['M_latch_int_rst+'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clkb', 's': 'latch_vss+', 'b': 'vss'}}
                devices['M_latch_int_rst-'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'clkb', 's': 'latch_vss-', 'b': 'vss'}}
            elif not (latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled'):
                devices['M_latch_int_rst+'] = {'dev': 'nmos', 'pins': {'d': 'latch-', 'g': 'clkb', 's': 'latch_vss', 'b': 'vss'}}
                devices['M_latch_int_rst-'] = {'dev': 'nmos', 'pins': {'d': 'latch+', 'g': 'clkb', 's': 'latch_vss', 'b': 'vss'}}
        elif latch_rst_intern_ctl == 'signalled':
            if latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled':
                # Stack reset on top of signalled powergate
                devices['M_latch_int_rst+'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'latch-', 's': 'latch_vss+', 'b': 'vss'}}
                devices['M_latch_int_rst-'] = {'dev': 'nmos', 'pins': {'d': 'latch_vss', 'g': 'latch+', 's': 'latch_vss-', 'b': 'vss'}}
            elif not (latch_pwrgate_node == 'internal' and latch_pwrgate_ctl == 'signalled'):
                devices['M_latch_int_rst+'] = {'dev': 'nmos', 'pins': {'d': 'latch-', 'g': 'latch-', 's': 'latch_vss', 'b': 'vss'}}
                devices['M_latch_int_rst-'] = {'dev': 'nmos', 'pins': {'d': 'latch+', 'g': 'latch+', 's': 'latch_vss', 'b': 'vss'}}

        # Output buffers from latch to final output
        devices['Ma_latch_out+'] = {'dev': 'pmos', 'pins': {'d': 'out-', 'g': 'latch-', 's': 'vdd', 'b': 'vdd'}}
        devices['Ma_latch_out-'] = {'dev': 'pmos', 'pins': {'d': 'out+', 'g': 'latch+', 's': 'vdd', 'b': 'vdd'}}
        devices['Mb_latch_out+'] = {'dev': 'nmos', 'pins': {'d': 'out-', 'g': 'latch-', 's': 'vss', 'b': 'vss'}}
        devices['Mb_latch_out-'] = {'dev': 'nmos', 'pins': {'d': 'out+', 'g': 'latch+', 's': 'vss', 'b': 'vss'}}

    # If PMOS input, swap everything
    if preamp_diffpair == 'pmosinput':
        swapped_devices = {}
        for dev_name, dev_info in devices.items():
            # Swap device name prefix Ma <-> Mb for cross-coupled pairs
            if dev_name.startswith('Ma_'):
                new_dev_name = 'Mb_' + dev_name[3:]
            elif dev_name.startswith('Mb_'):
                new_dev_name = 'Ma_' + dev_name[3:]
            else:
                new_dev_name = dev_name

            # Swap device type nmos <-> pmos
            new_dev_info = dev_info.copy()
            if 'dev' in new_dev_info:
                if new_dev_info['dev'] == 'nmos':
                    new_dev_info['dev'] = 'pmos'
                elif new_dev_info['dev'] == 'pmos':
                    new_dev_info['dev'] = 'nmos'

            # Swap pin connections vdd <-> vss and clk <-> clkb
            if 'pins' in new_dev_info:
                new_pins = {}
                for pin_name, pin_conn in new_dev_info['pins'].items():
                    if pin_conn == 'vdd':
                        new_pins[pin_name] = 'vss'
                    elif pin_conn == 'vss':
                        new_pins[pin_name] = 'vdd'
                    elif pin_conn == 'clk':
                        new_pins[pin_name] = 'clkb'
                    elif pin_conn == 'clkb':
                        new_pins[pin_name] = 'clk'
                    else:
                        new_pins[pin_name] = pin_conn
                new_dev_info['pins'] = new_pins

            swapped_devices[new_dev_name] = new_dev_info

        devices = swapped_devices

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
                                        {'devices': ['M_preamp_diff+', 'M_preamp_diff-'], 'w': [4, 8], 'type': ['lvt']},
                                        {'devices': ['M_preamp_tail', 'M_preamp_bias'], 'w': [2, 4], 'l': [2]},
                                        {'devices': ['M_preamp_rst+', 'M_preamp_rst-'], 'w': [2], 'type': ['lvt']},
                                        {'devices': ['Ma_latch+', 'Ma_latch-', 'Mb_latch+', 'Mb_latch-'], 'w': [1, 2, 4], 'type': ['lvt']}
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
            'Xdut': {'dev': 'comp', 'pins': {'in+': 'in+', 'in-': 'in-', 'out+': 'out+', 'out-': 'out-', 'clk': 'clk', 'clkb': 'clkb', 'vdd': 'vdd', 'vss': 'vss'}}
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
