def subcircuit():

    # Tech agnostic subcircuit netlist description
    topology = {
        'subckt': 'gate_inv',
        'ports': {'in': 'I', 'out': 'O', 'vdd': 'B', 'vss': 'B'},
        'devices': {
            # NMOS pull-down (conducts when in is high)
            'MN': {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'in', 's': 'vss', 'b': 'vss'}},

            # PMOS pull-up (conducts when in is low)
            'MP': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'in', 's': 'vdd', 'b': 'vdd'}}
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
            {'devices': ['MN', 'MP'], 'w': [1, 2, 4, 8]}
        ]
    }

    return topology, sweep


def testbench():

    # Tech agnostic testbench netlist description
    topology = {
        'testbench': 'tb_gate_inv',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
            'Vin': {'dev': 'vsource', 'pins': {'p': 'in', 'n': 'gnd'}, 'wave': 'pulse', 'v1': 0, 'v2': 1.0, 'td': 0, 'tr': 1, 'tf': 1, 'pw': 50, 'per': 100},
            'Cload': {'dev': 'cap', 'pins': {'p': 'out', 'n': 'vss'}, 'params': {'c': 1e-15}},
            'Xdut': {'dev': 'gate_inv', 'pins': {'in': 'in', 'out': 'out', 'vdd': 'vdd', 'vss': 'vss'}}
        },
        'analyses': {
            'tran1': {
                'type': 'tran',
                'stop': 200,
                'step': 0.1
            }
        }
    }

    return topology
