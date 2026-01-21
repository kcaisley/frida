from typing import Any


def generate_topology() -> dict[str, Any]:
    """
    Generate 2-input NAND gate topology.

    Returns:
        dict with 'subckt', 'ports', 'devices', 'meta'
    """

    # Initialize topology components
    ports = {"a": "I", "b": "I", "out": "O", "vdd": "B", "vss": "B"}

    devices = {
        # NMOS pull-down network (series - both must be high for low output)
        'MNa': {'dev': 'nmos', 'pins': {'d': 'net1', 'g': 'a', 's': 'vss', 'b': 'vss'}},
        'MNb': {'dev': 'nmos', 'pins': {'d': 'out', 'g': 'b', 's': 'net1', 'b': 'vss'}},

        # PMOS pull-up network (parallel - either low gives high output)
        'MPa': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'a', 's': 'vdd', 'b': 'vdd'}},
        'MPb': {'dev': 'pmos', 'pins': {'d': 'out', 'g': 'b', 's': 'vdd', 'b': 'vdd'}}
    }

    # Build final topology
    topology = {
        "subckt": "gate_nand2",
        "ports": ports,
        "devices": devices,
        "meta": {
            "gate_type": "nand2",
        },
    }

    return topology


def subcircuit():
    """
    Generate NAND2 gate topology.

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
            {'devices': ['MNa', 'MNb', 'MPa', 'MPb'], 'w': [1, 2, 4, 8, 12, 16], 'type': ['lvt', 'svt']}
        ]
    }

    all_configurations.append((topology, sweep))

    return all_configurations


def testbench():
    """
    Tech agnostic testbench netlist description.

    Returns:
        List of (topology, sweep) tuples
    """
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
        },
        'meta': {
            'gate_type': 'nand2'
        }
    }

    # Testbench sweep: corner, temp, and device globals
    sweep = {
        "corner": ["tt"],
        "temp": [27],
        "globals": {
            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        }
    }

    return [(topology, sweep)]
