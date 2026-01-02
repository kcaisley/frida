def subcircuit():

    # Tech agnostic subcircuit netlist description
    topology = {
        'subckt': 'comp_tripletail',
        'ports': {'in_p': 'I', 'in_n': 'I', 'out_p': 'O', 'out_n': 'O', 'clk': 'I', 'clk_b': 'I', 'vdd': 'B', 'vss': 'B'},
        'devices': {
            # Left tail transistor
            'MNtailL': {'dev': 'nmos', 'pins': {'d': 'tailL', 'g': 'clk', 's': 'vss', 'b': 'vss'}},

            # Input differential pair (left side)
            'MNinnL': {'dev': 'nmos', 'pins': {'d': 'xn', 'g': 'in_n', 's': 'tailL', 'b': 'vss'}},
            'MNinpL': {'dev': 'nmos', 'pins': {'d': 'xp', 'g': 'in_p', 's': 'tailL', 'b': 'vss'}},

            # Center cross-coupled pair with dedicated tails
            'MNtailCN': {'dev': 'nmos', 'pins': {'d': 'tailCN', 'g': 'clk_b', 's': 'vss', 'b': 'vss'}},
            'MNtailCP': {'dev': 'nmos', 'pins': {'d': 'tailCP', 'g': 'clk_b', 's': 'vss', 'b': 'vss'}},
            'MNxcn': {'dev': 'nmos', 'pins': {'d': 'yn', 'g': 'xn', 's': 'tailCN', 'b': 'vss'}},
            'MNxcp': {'dev': 'nmos', 'pins': {'d': 'yp', 'g': 'xp', 's': 'tailCP', 'b': 'vss'}},

            # Right tail transistor
            'MNtailR': {'dev': 'nmos', 'pins': {'d': 'tailR', 'g': 'clk', 's': 'vss', 'b': 'vss'}},

            # Cross-coupled output pair
            'MNnfbn': {'dev': 'nmos', 'pins': {'d': 'out_p', 'g': 'out_n', 's': 'yp', 'b': 'vss'}},
            'MNnfbp': {'dev': 'nmos', 'pins': {'d': 'out_n', 'g': 'out_p', 's': 'yn', 'b': 'vss'}},

            # Reset switches
            'MPswon': {'dev': 'pmos', 'pins': {'d': 'out_n', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},
            'MPswop': {'dev': 'pmos', 'pins': {'d': 'out_p', 'g': 'clk', 's': 'vdd', 'b': 'vdd'}},

            # PMOS latch
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
            {'devices': ['MNinpL', 'MNinnL'], 'w': [2, 4, 8, 16], 'type': ['lvt', 'svt']},
            {'devices': ['MNtailL', 'MNtailR'], 'w': [2, 4], 'l': [4, 8]}
        ]
    }

    return topology, sweep


def testbench():

    # Tech agnostic testbench netlist description
    topology = {
        'testbench': 'tb_comp_tripletail',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
            'Xdut': {'dev': 'comp_tripletail', 'pins': {'in_p': 'in_p', 'in_n': 'in_n', 'out_p': 'out_p', 'out_n': 'out_n', 'clk': 'clk', 'clk_b': 'clk_b', 'vdd': 'vdd', 'vss': 'vss'}}
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
