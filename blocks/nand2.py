"""
NAND2 gate subcircuit definition.

Static topology with pre-filled ports and devices.
No generate_topology() needed - expand_topo_params() will skip Stage 1.
"""

# Merged subckt struct with topology and sweeps combined
subckt = {
    "cellname": "nand2",
    "ports": {"a": "I", "b": "I", "out": "O", "vdd": "B", "vss": "B"},
    "instances": {
        # NMOS pull-down network (series - both must be high for low output)
        "MNa": {"dev": "nmos", "pins": {"d": "net1", "g": "a", "s": "vss", "b": "vss"}},
        "MNb": {"dev": "nmos", "pins": {"d": "out", "g": "b", "s": "net1", "b": "vss"}},
        # PMOS pull-up network (parallel - either low gives high output)
        "MPa": {"dev": "pmos", "pins": {"d": "out", "g": "a", "s": "vdd", "b": "vdd"}},
        "MPb": {"dev": "pmos", "pins": {"d": "out", "g": "b", "s": "vdd", "b": "vdd"}},
    },
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "inst_params": [
        # Defaults for all nmos/pmos instances
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        # Override specific instances with sweeps
        {
            "instances": {"nmos": ["MNa", "MNb"], "pmos": ["MPa", "MPb"]},
            "w": [1, 2, 4, 8, 12, 16],
            "type": ["lvt", "svt"],
        },
    ],
}


"""
NAND2 Testbench:

Tests NAND2 gate functionality with digital input stimuli.

Test structure:
- Two input pulse sources (a, b) with different periods
- Load capacitor on output
- Transient analysis to capture logic transitions

Verifies truth table: out = ~(a & b)
"""

# Monolithic testbench struct (static topology - no topo_params)
tb = {
    "instances": {
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
        "Va": {
            "dev": "vsource",
            "pins": {"p": "a", "n": "gnd"},
            "wave": "pulse",
            "v1": 0,
            "v2": 1.0,
            "td": 0,
            "tr": 1,
            "tf": 1,
            "pw": 50,
            "per": 100,
        },
        "Vb": {
            "dev": "vsource",
            "pins": {"p": "b", "n": "gnd"},
            "wave": "pulse",
            "v1": 0,
            "v2": 1.0,
            "td": 0,
            "tr": 1,
            "tf": 1,
            "pw": 100,
            "per": 200,
        },
        "Cload": {
            "dev": "cap",
            "pins": {"p": "out", "n": "vss"},
            "params": {"c": 1e-15},
        },
        "Xdut": {
            "cell": "nand2",
            "pins": {"a": "a", "b": "b", "out": "out", "vdd": "vdd", "vss": "vss"},
        },
    },
}


# ========================================================================
# PyOPUS analyses configuration
# Simulation time: 400ns (covers 2 full cycles of both inputs)
analyses = {
    "tran": {
        "saves": ["all()"],
        "command": "tran(stop=400e-9, errpreset='conservative')",
    }
}


# PyOPUS measures configuration
# Measure functions are defined in flow/measure.py
measures = {
    "tphl_ns": {
        "analysis": "tran",
        "expression": "m.nand2_tphl_ns(v, scale, 'a', 'b', 'out')",
    },
    "tplh_ns": {
        "analysis": "tran",
        "expression": "m.nand2_tplh_ns(v, scale, 'a', 'b', 'out')",
    },
    "trise_ns": {
        "analysis": "tran",
        "expression": "m.rise_time_ns(v, scale, 'out', 0.1, 0.9)",
    },
    "tfall_ns": {
        "analysis": "tran",
        "expression": "m.fall_time_ns(v, scale, 'out', 0.1, 0.9)",
    },
    "power_uW": {
        "analysis": "tran",
        "expression": "m.avg_power_uW(v, i, scale, 'vdd')",
    },
    "voh_V": {
        "analysis": "tran",
        "expression": "m.voh_V(v, 'out')",
    },
    "vol_V": {
        "analysis": "tran",
        "expression": "m.vol_V(v, 'out')",
    },
}
