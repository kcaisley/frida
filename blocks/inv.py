"""
Inverter gate subcircuit definition.

Static topology - ports/devices pre-filled (no generate_topology needed).
"""

import numpy as np

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
# PyOPUS Analyses Configuration
# ========================================================================

analyses = {
    "tran": {
        "saves": ["all()"],
        "command": f"tran(stop={_sim_stop}e-9, errpreset='conservative')",
    }
}

# Variables accessible in measure expressions
variables = {
    "vdd": 1.2,
    "sim_stop": _sim_stop,
    "clk_period": _clk_period,
}


# ========================================================================
# PyOPUS Measures Configuration
# ========================================================================

measures = {
    # Propagation delay (high-to-low)
    "tphl_ns": {
        "analysis": "tran",
        "expression": """
vin = v('in')
vout = v('out')
vdd = param.get('vdd', 1.2)

# m.Tdelay(y, x, level, edge)
# Delay from input rising to output falling
tphl = m.Tdelay(vout, scale(), vdd/2, 'falling')
__result = tphl * 1e9 if tphl is not None else float('nan')
""",
    },
    # Propagation delay (low-to-high)
    "tplh_ns": {
        "analysis": "tran",
        "expression": """
vin = v('in')
vout = v('out')
vdd = param.get('vdd', 1.2)

# Delay from input falling to output rising
tplh = m.Tdelay(vout, scale(), vdd/2, 'rising')
__result = tplh * 1e9 if tplh is not None else float('nan')
""",
    },
    # Rise time (10% to 90%)
    "trise_ns": {
        "analysis": "tran",
        "expression": """
vout = v('out')

# m.TriseTime(y, x, l1, l2)
trise = m.TriseTime(vout, scale(), 0.1, 0.9)
__result = trise * 1e9 if trise is not None else float('nan')
""",
    },
    # Fall time (90% to 10%)
    "tfall_ns": {
        "analysis": "tran",
        "expression": """
vout = v('out')

# m.TfallTime(y, x, l1, l2)
tfall = m.TfallTime(vout, scale(), 0.1, 0.9)
__result = tfall * 1e9 if tfall is not None else float('nan')
""",
    },
    # Average power
    "power_uW": {
        "analysis": "tran",
        "expression": """
import numpy as np
time = scale()
ivdd = -i('vdd')
vdd = param.get('vdd', 1.2)

# Average power over simulation
__result = np.mean(ivdd) * vdd * 1e6
""",
    },
    # Output high voltage
    "voh_V": {
        "analysis": "tran",
        "expression": """
import numpy as np
vout = v('out')
vdd = param.get('vdd', 1.2)

# Max output voltage (should be ~VDD)
__result = float(np.max(vout))
""",
    },
    # Output low voltage
    "vol_V": {
        "analysis": "tran",
        "expression": """
import numpy as np
vout = v('out')

# Min output voltage (should be ~0)
__result = float(np.min(vout))
""",
    },
}


# ========================================================================
# Custom measure() function for fallback mode
# ========================================================================


def measure(raw, subckt_json, tb_json, raw_file):
    """
    Measure inverter simulation results.

    Extracts propagation delays, rise/fall times, and power consumption.
    """
    from flow.measure import read_traces

    # Read simulation traces
    traces = read_traces(raw)
    time = traces[0]

    # Get trace names to find input and output
    trace_names = raw.get_trace_names()
    vin = None
    vout = None
    ivdd = None

    for name in trace_names:
        name_lower = name.lower()
        if "in" in name_lower and "out" not in name_lower:
            vin = raw.get_wave(name)
        elif "out" in name_lower:
            vout = raw.get_wave(name)
        elif "vdd" in name_lower and name.startswith("i"):
            ivdd = raw.get_wave(name)

    if vin is None or vout is None:
        return {"error": "Could not find input/output traces"}

    # Get VDD from subckt or use default
    vdd = 1.2
    tech = subckt_json.get("tech", "tsmc65")
    if tech == "tsmc28":
        vdd = 0.9
    elif tech == "tower180":
        vdd = 1.8

    threshold = vdd / 2

    # Find propagation delays
    # tphl: input rises, output falls
    # tplh: input falls, output rises

    # Find rising edges of input
    vin_above = vin > threshold
    vin_rising = np.where(np.diff(vin_above.astype(int)) > 0)[0]
    vin_falling = np.where(np.diff(vin_above.astype(int)) < 0)[0]

    # Find falling/rising edges of output
    vout_above = vout > threshold
    vout_rising = np.where(np.diff(vout_above.astype(int)) > 0)[0]
    vout_falling = np.where(np.diff(vout_above.astype(int)) < 0)[0]

    # Calculate tphl (input rising -> output falling)
    tphl = float("nan")
    if len(vin_rising) > 0 and len(vout_falling) > 0:
        for in_idx in vin_rising:
            # Find next output falling edge
            out_indices = vout_falling[vout_falling > in_idx]
            if len(out_indices) > 0:
                out_idx = out_indices[0]
                tphl = float((time[out_idx] - time[in_idx]) * 1e9)  # ns
                break

    # Calculate tplh (input falling -> output rising)
    tplh = float("nan")
    if len(vin_falling) > 0 and len(vout_rising) > 0:
        for in_idx in vin_falling:
            # Find next output rising edge
            out_indices = vout_rising[vout_rising > in_idx]
            if len(out_indices) > 0:
                out_idx = out_indices[0]
                tplh = float((time[out_idx] - time[in_idx]) * 1e9)  # ns
                break

    # Calculate rise/fall times (10% to 90%)
    voh = float(np.max(vout))
    vol = float(np.min(vout))
    v10 = vol + 0.1 * (voh - vol)
    v90 = vol + 0.9 * (voh - vol)

    trise = float("nan")
    tfall = float("nan")

    if len(vout_rising) > 0:
        # Find a rising transition
        for idx in vout_rising:
            # Look for 10% and 90% crossings
            start = max(0, idx - 10)
            end = min(len(vout), idx + 100)
            segment = vout[start:end]

            try:
                idx_10 = start + np.where(segment > v10)[0][0]
                idx_90 = start + np.where(segment > v90)[0][0]
                if idx_90 > idx_10:
                    trise = float((time[idx_90] - time[idx_10]) * 1e9)
                    break
            except (IndexError, ValueError):
                pass

    if len(vout_falling) > 0:
        # Find a falling transition
        for idx in vout_falling:
            start = max(0, idx - 10)
            end = min(len(vout), idx + 100)
            segment = vout[start:end]

            try:
                idx_90 = start + np.where(segment < v90)[0][0]
                idx_10 = start + np.where(segment < v10)[0][0]
                if idx_10 > idx_90:
                    tfall = float((time[idx_10] - time[idx_90]) * 1e9)
                    break
            except (IndexError, ValueError):
                pass

    # Calculate power
    power_uW = float("nan")
    if ivdd is not None:
        power_uW = float(np.mean(-ivdd) * vdd * 1e6)

    results = {
        "vdd": vdd,
        "tphl_ns": tphl,
        "tplh_ns": tplh,
        "tp_avg_ns": (tphl + tplh) / 2 if not (np.isnan(tphl) or np.isnan(tplh)) else float("nan"),
        "trise_ns": trise,
        "tfall_ns": tfall,
        "voh_V": voh,
        "vol_V": vol,
        "power_uW": power_uW,
    }

    return results


# ========================================================================
# PyOPUS Visualisation Configuration
# ========================================================================

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
