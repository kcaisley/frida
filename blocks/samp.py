"""
Sampling switch subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/devices
for each switch_type variant.
"""

from typing import Any

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "samp",
    "ports": {},  # Empty - computed by generate_topology()
    "instances": {},  # Empty - computed by generate_topology()
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "topo_params": {"switch_type": ["nmos", "pmos", "tgate"]},
    "inst_params": [
        # Defaults for all nmos/pmos instances
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        # Override specific instances with sweeps
        {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": [5, 10, 20, 40], "l": [1, 2]},
    ],
}


def gen_topo_subckt(switch_type: str) -> tuple[dict[str, str], dict[str, Any]]:
    """
    Compute ports and instances for given switch_type.

    Called by generate_topology() for each topo_params combination.

    Args:
        switch_type: 'nmos', 'pmos', or 'tgate' - determines switch implementation

    Returns:
        Tuple of (ports, instances)
    """
    # Common ports for all switch types
    ports = {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"}

    # Initialize instances
    instances = {}

    if switch_type == "nmos":
        # NMOS pass transistor (conducts when clk is high)
        # Note: clk_b pin unused (left floating for interface compatibility)
        instances["MN"] = {
            "dev": "nmos",
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
        }

    elif switch_type == "pmos":
        # PMOS pass transistor (conducts when clk_b is low)
        # Note: clk pin unused (left floating for interface compatibility)
        instances["MP"] = {
            "dev": "pmos",
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
        }

    elif switch_type == "tgate":
        # Transmission gate (NMOS + PMOS in parallel)
        instances["MN"] = {
            "dev": "nmos",
            "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
        }
        instances["MP"] = {
            "dev": "pmos",
            "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
        }

    return ports, instances


"""
Sample-and-Hold Testbench:

Tests sampling switch at multiple input frequencies and amplitudes.

Test structure:
- DC voltage staircase + sine wave sources at 10MHz, 100MHz, 200MHz, 500MHz, 1GHz
- Source impedance (1kΩ) and load capacitor (1pF)
- Clock signals for sampling (50% duty cycle, 100ns period)
- Monte Carlo analysis with process variations

Characterizes switch performance: bandwidth, THD, settling time
"""

# Monolithic testbench struct (static topology - uses switch_type for matching only)
tb = {
    "instances": {
        "Vvdd": {
            "dev": "vsource",
            "pins": {"p": "vdd", "n": "gnd"},
            "wave": "dc",
            "params": {"dc": 1.0},
        },
        "Vvss": {
            "dev": "vsource",
            "pins": {"p": "vss", "n": "gnd"},
            "wave": "dc",
            "params": {"dc": 0.0},
        },
        # DC voltage staircase (explicit points - simple case)
        "Vin_dc": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "pwl",
            "points": [
                0, 0, 1, 0,
                1, 0.1, 21, 0.1,
                21, 0.2, 41, 0.2,
                41, 0.3, 61, 0.3,
                61, 0.4, 81, 0.4,
                81, 0.5, 101, 0.5,
                101, 0.6, 121, 0.6,
                121, 0.7, 141, 0.7,
                141, 0.8, 161, 0.8,
                161, 0.9, 181, 0.9,
                181, 1.0, 201, 1.0,
                201, 0.5, 250, 0.5,
            ],
        },
        "Vin_10M": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "sine",
            "params": {"dc": 0.5, "ampl": 0.5, "freq": 10e6, "delay": 201},
        },
        "Vin_100M": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "sine",
            "params": {"dc": 0.5, "ampl": 0.5, "freq": 100e6, "delay": 226},
        },
        "Vin_200M": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "sine",
            "params": {"dc": 0.5, "ampl": 0.5, "freq": 200e6, "delay": 251},
        },
        "Vin_500M": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "sine",
            "params": {"dc": 0.5, "ampl": 0.5, "freq": 500e6, "delay": 276},
        },
        "Vin_1G": {
            "dev": "vsource",
            "pins": {"p": "in_driver", "n": "gnd"},
            "wave": "sine",
            "params": {"dc": 0.5, "ampl": 0.5, "freq": 1e9, "delay": 301},
        },
        "Rsrc": {
            "dev": "res",
            "pins": {"p": "in_driver", "n": "in"},
            "params": {"r": 1e3},
        },
        "Cload": {
            "dev": "cap",
            "pins": {"p": "out", "n": "vss"},
            "params": {"c": 1e-12},
        },
        "Vclk": {
            "dev": "vsource",
            "pins": {"p": "clk", "n": "gnd"},
            "wave": "pulse",
            "params": {"v1": 0, "v2": 1.0, "td": 0, "tr": 0, "tf": 0, "pw": 50, "per": 100},
        },
        "Vclk_b": {
            "dev": "vsource",
            "pins": {"p": "clk_b", "n": "gnd"},
            "wave": "pulse",
            "params": {"v1": 1.0, "v2": 0, "td": 0, "tr": 0, "tf": 0, "pw": 50, "per": 100},
        },
        "Xdut": {
            "cell": "samp",
            "pins": {
                "in": "in",
                "out": "out",
                "clk": "clk",
                "clk_b": "clk_b",
                "vdd": "vdd",
                "vss": "vss",
            },
        },
    },
}


# PyOPUS analyses configuration
# Simulation covers: DC staircase (0-250) + sine tests (201-326 normalized time)
# With tstep=1ns, total sim time = 326ns
analyses = {
    "tran": {
        "saves": ["all()"],
        "command": "tran(stop=326e-9, errpreset='conservative')",
    }
}


# PyOPUS measures configuration
# Measure functions are defined in flow/measure.py
measures = {
    "ron_ohm": {
        "analysis": "tran",
        "expression": "m.samp_on_resistance(v, scale, 'in', 'out', 'clk')",
    },
    "settling_ns": {
        "analysis": "tran",
        "expression": "m.samp_settling_time(v, scale, 'out', 0.01)",
    },
    "charge_injection_mV": {
        "analysis": "tran",
        "expression": "m.samp_charge_injection(v, scale, 'out', 'clk')",
    },
}
