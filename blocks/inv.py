"""
Inverter gate subcircuit definition.

Static topology - ports/devices pre-filled (no generate_topology needed).
"""

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "inv",
    "ports": {"in": "I", "out": "O", "vdd": "B", "vss": "B"},
    "instances": {
        # NMOS pull-down (conducts when in is high)
        "MN": {"dev": "nmos", "pins": {"d": "out", "g": "in", "s": "vss", "b": "vss"}},
        # PMOS pull-up (conducts when in is low)
        "MP": {"dev": "pmos", "pins": {"d": "out", "g": "in", "s": "vdd", "b": "vdd"}},
    },
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "inst_params": [
        # Defaults for all nmos/pmos instances
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        # Override specific instances with sweeps
        {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": [1, 2, 4, 8, 12, 16], "type": ["lvt", "svt"]},
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

# Testbench timing parameters
_sim_stop = 200  # ns
_clk_period = 100  # ns

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
            "per": _clk_period,
        },
        "Cload": {
            "dev": "cap",
            "pins": {"p": "out", "n": "vss"},
            "params": {"c": 1e-15},
        },
        "Xdut": {
            "cell": "inv",
            "pins": {"in": "in", "out": "out", "vdd": "vdd", "vss": "vss"},
        },
    },
    "analyses": {"tran1": {"type": "tran", "stop": _sim_stop, "step": 0.1}},
    "corner": ["tt"],
    "temp": [27],
}


# ========================================================================
# PyOPUS analyses configuration
# Simulation time: 200ns (2 clock periods at 100ns)
analyses = {
    "tran": {
        "saves": ["all()"],
        "command": "tran(stop=200e-9, errpreset='conservative')",
    }
}


# PyOPUS measures configuration
# Measure functions are defined in flow/measure.py
measures = {
    "tphl_ns": {
        "analysis": "tran",
        "expression": "m.inv_tphl_ns(v, scale, 'in', 'out')",
    },
    "tplh_ns": {
        "analysis": "tran",
        "expression": "m.inv_tplh_ns(v, scale, 'in', 'out')",
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


# PyOPUS Visualisation Configuration

visualisation = {
    "graphs": {
        "transient": {
            "title": "Inverter Transient Response",
            "shape": {"figsize": (10, 6), "dpi": 100},
            "axes": {
                "signals": {
                    "subplot": (2, 1, 1),
                    "xlabel": "Time [ns]",
                    "ylabel": "Voltage [V]",
                    "legend": True,
                    "grid": True,
                },
                "current": {
                    "subplot": (2, 1, 2),
                    "xlabel": "Time [ns]",
                    "ylabel": "Current [uA]",
                    "grid": True,
                },
            },
        },
        "delays": {
            "title": "Propagation Delay Summary",
            "shape": {"figsize": (8, 6)},
            "axes": {
                "bar": {
                    "subplot": (1, 1, 1),
                    "xlabel": "Configuration",
                    "ylabel": "Delay [ns]",
                    "grid": True,
                }
            },
        },
    },
    "traces": {
        "vin": {
            "graph": "transient",
            "axes": "signals",
            "xresult": "time",
            "yresult": "v_in",
        },
        "vout": {
            "graph": "transient",
            "axes": "signals",
            "xresult": "time",
            "yresult": "v_out",
        },
    },
}
