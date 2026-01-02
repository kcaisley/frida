def subcircuit():

    # Tech agnostic subcircuit netlist description
    topology = {
        'subckt': 'comp_doubletail',
        'ports': {'in_p': 'I', 'in_n': 'I', 'out_p': 'O', 'out_n': 'O', 'clk': 'I', 'clk_b': 'I', 'vdd': 'B', 'vss': 'B'},
        'devices': {
            # First stage (input stage)
            # Tail transistor
            'MNtail1': {'dev': 'nmos', 'pins': {'d': 'tail1', 'g': 'clk', 's': 'vss', 'b': 'vss'}},

            # Input differential pair
            'MNinn': {'dev': 'nmos', 'pins': {'d': 'midn', 'g': 'in_n', 's': 'tail1', 'b': 'vss'}},
            'MNinp': {'dev': 'nmos', 'pins': {'d': 'midp', 'g': 'in_p', 's': 'tail1', 'b': 'vss'}},

            # First stage PMOS loads (reset when clk low)
            'MPswMN': {'dev': 'pmos', 'pins': {'d': 'midn', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},
            'MPswMP': {'dev': 'pmos', 'pins': {'d': 'midp', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},

            # Second stage (output stage with cross-coupled latch)
            # Tail transistor for second stage
            'MNtail2': {'dev': 'nmos', 'pins': {'d': 'tail2', 'g': 'clk_b', 's': 'vss', 'b': 'vss'}},

            # Cross-coupled NMOS pair
            'MNnfbn': {'dev': 'nmos', 'pins': {'d': 'out_p', 'g': 'out_n', 's': 'midn', 'b': 'vss'}},
            'MNnfbp': {'dev': 'nmos', 'pins': {'d': 'out_n', 'g': 'out_p', 's': 'midp', 'b': 'vss'}},

            # Output reset switches
            'MPswon': {'dev': 'pmos', 'pins': {'d': 'out_n', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},
            'MPswop': {'dev': 'pmos', 'pins': {'d': 'out_p', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},

            # Cross-coupled PMOS latch
            'MPpfbn': {'dev': 'pmos', 'pins': {'d': 'out_n', 'g': 'out_p', 's': 'vdd', 'b': 'vdd'}},
            'MPpfbp': {'dev': 'pmos', 'pins': {'d': 'out_p', 'g': 'out_n', 's': 'vdd', 'b': 'vdd'}}
        }
    }

    # Technology agnostic device sweeps
    sweep = {
        'tech': ['tsmc65', 'tsmc28', 'tower180'],
        'defaults': {
            'nmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1},
            'pmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1}
        },
        'sweeps': [
            {'devices': ['MNinp', 'MNinn'], 'w': [2, 4, 8, 16], 'type': ['lvt', 'svt']},
            {'devices': ['MNtail1'], 'w': [2, 4], 'l': [4, 8]}
        ]
    }

    return topology, sweep


def testbench():

    # Tech agnostic testbench netlist description
    topology = {
        'testbench': 'tb_comp_doubletail',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
            'Xdut': {'dev': 'comp_doubletail', 'pins': {'in_p': 'in_p', 'in_n': 'in_n', 'out_p': 'out_p', 'out_n': 'out_n', 'clk': 'clk', 'clk_b': 'clk_b', 'vdd': 'vdd', 'vss': 'vss'}}
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
                'stop': 35000,  # 35us = 5 common-mode * 17 differential * 20 cycles * 20ns
                'step': 1  # 1ns step
            }
        }
    }

    return topology
