from typing import Any


def generate_topology() -> dict[str, Any]:
    """
    Generate inverter gate topology.

    Returns:
        dict with 'subckt', 'ports', 'devices', 'meta'
    """

    # Initialize topology components
    ports = {"in": "I", "out": "O", "vdd": "B", "vss": "B"}

    devices = {
        # NMOS pull-down (conducts when in is high)
        'MN': {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'in', 's': 'vss', 'b': 'vss'}},

        # PMOS pull-up (conducts when in is low)
        'MP': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'in', 's': 'vdd', 'b': 'vdd'}}
    }

    # Build final topology
    topology = {
        "subckt": "gate_inv",
        "ports": ports,
        "devices": devices,
        "meta": {
            "gate_type": "inv",
        },
    }

    return topology


def subcircuit():
    """
    Generate inverter gate topology.

    Returns:
        List of (topology, sweep) tuples (1 configuration)
    """
    # Generate all configurations
    all_configurations = []

    # Generate topology
    topology = generate_topology()

    # Technology agnostic device sweeps
    sweep = {
        'tech': ['tsmc65', 'tsmc28', 'tower180'],
        'globals': {
            'nmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1},
            'pmos': {'type': 'lvt', 'w': 1, 'l': 1, 'nf': 1}
        },
        'selections': [
            {'devices': ['MN', 'MP'], 'w': [1, 2, 4, 8, 12, 16], 'type': ['lvt', 'svt']}
        ]
    }

    all_configurations.append((topology, sweep))

    return all_configurations


def testbench():
    """
    Tech agnostic testbench netlist description.
    """
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
