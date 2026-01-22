"""
Inverter gate subcircuit definition.

Static topology - ports/devices pre-filled (no generate_topology needed).
"""

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "inv",
    "ports": {"in": "I", "out": "O", "vdd": "B", "vss": "B"},
    "devices": {
        # NMOS pull-down (conducts when in is high)
        "MN": {"dev": "nmos", "pins": {"d": "out", "g": "in", "s": "vss", "b": "vss"}},
        # PMOS pull-up (conducts when in is low)
        "MP": {"dev": "pmos", "pins": {"d": "out", "g": "in", "s": "vdd", "b": "vdd"}},
    },
    "meta": {},
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [
        {"devices": ["MN", "MP"], "w": [1, 2, 4, 8, 12, 16], "type": ["lvt", "svt"]}
    ],
}


"""
Inverter Testbench:

Tests inverter functionality with digital input stimulus.

Test structure:
- Input pulse source with 100ns period
- Load capacitor on output
- Transient analysis to measure propagation delay and transitions

Verifies basic inverter operation: out = ~in
"""

# Monolithic testbench struct (static topology - no topo_params)
tb = {
    "devices": {
        "Vvdd": {
            "dev": "vsource",
            "pins": {"p": "vdd", "n": "gnd"},
            "wave": "dc",
            "dc": 1.0,
        },
        "Vvss": {
            "dev": "vsource",
            "pins": {"p": "vss", "n": "gnd"},
            "wave": "dc",
            "dc": 0.0,
        },
        "Vin": {
            "dev": "vsource",
            "pins": {"p": "in", "n": "gnd"},
            "wave": "pulse",
            "v1": 0,
            "v2": 1.0,
            "td": 0,
            "tr": 1,
            "tf": 1,
            "pw": 50,
            "per": 100,
        },
        "Cload": {
            "dev": "cap",
            "pins": {"p": "out", "n": "vss"},
            "params": {"c": 1e-15},
        },
        "Xdut": {
            "dev": "inv",
            "pins": {"in": "in", "out": "out", "vdd": "vdd", "vss": "vss"},
        },
    },
    "analyses": {"tran1": {"type": "tran", "stop": 200, "step": 0.1}},
    "corner": ["tt"],
    "temp": [27],
}


def measure(raw, subckt_json, tb_json, raw_file):
    """
    Measure inverter simulation results.

    TODO: Implement measurement logic using flow/measure functions
    """
    from flow.measure import write_analysis

    # TODO: Read traces, calculate metrics (delay, rise/fall times, power, etc.)
    # TODO: Use calc_*() functions from flow/measure

    results = {}
    write_analysis(raw_file, results)

    return results
