def subcircuit():

    # Tech agnostic subcircuit netlist description
    topology = {
        'subckt': 'gate_nand2',
        'ports': {'a': 'I', 'b': 'I', 'out': 'O', 'vdd': 'B', 'vss': 'B'},
        'devices': {
            # NMOS pull-down network (series - both must be high for low output)
            'MNa': {'dev': 'nmos', 'pins': {'d': 'net1', 'g': 'a', 's': 'vss', 'b': 'vss'}},
            'MNb': {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'b', 's': 'net1', 'b': 'vss'}},

            # PMOS pull-up network (parallel - either low gives high output)
            'MPa': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'a', 's': 'vdd', 'b': 'vdd'}},
            'MPb': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'b', 's': 'vdd', 'b': 'vdd'}}
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
            {'devices': ['MNa', 'MNb', 'MPa', 'MPb'], 'w': [1, 2, 4, 8]}
        ]
    }

    return topology, sweep


def testbench():

    # Tech agnostic testbench netlist description
    topology = {
        'testbench': 'tb_gate_nand2',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
            'Va': {'dev': 'vsource', 'pins': {'p': 'a', 'n': 'gnd'}, 'wave': 'pulse', 'v1': 0, 'v2': 1.0, 'td': 0, 'tr': 1, 'tf': 1, 'pw': 50, 'per': 100},
            'Vb': {'dev': 'vsource', 'pins': {'p': 'b', 'n': 'gnd'}, 'wave': 'pulse', 'v1': 0, 'v2': 1.0, 'td': 0, 'tr': 1, 'tf': 1, 'pw': 100, 'per': 200},
            'Cload': {'dev': 'cap', 'pins': {'p': 'out', 'n': 'vss'}, 'params': {'c': 1e-15}},
            'Xdut': {'dev': 'gate_nand2', 'pins': {'a': 'a', 'b': 'b', 'out': 'out', 'vdd': 'vdd', 'vss': 'vss'}}
        },
        'analyses': {
            'tran1': {
                'type': 'tran',
                'stop': 400,
                'step': 0.1
            }
        }
    }

    return topology
