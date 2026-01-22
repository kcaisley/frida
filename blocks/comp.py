"""
Comparator subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/devices
for each comparator configuration.

Topo params:
    preamp_diffpair: 'nmosinput' or 'pmosinput' - input differential pair type
    preamp_bias: 'stdbias' or 'dynbias' - whether to use dynamic biasing
    comp_stages: 'singlestage' or 'doublestage' - comparator architecture
    latch_pwrgate_ctl: 'clocked' or 'signalled' - powergate control type
    latch_pwrgate_node: 'external' or 'internal' - powergate position
    latch_rst_extern_ctl: 'clocked', 'signalled', or 'noreset' - external reset type
    latch_rst_intern_ctl: 'clocked' or 'signalled' - internal reset type
"""

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "comp",
    "ports": {},  # Empty - computed by generate_topology()
    "devices": {},  # Empty - computed by generate_topology()
    "meta": {},
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "topo_params": {
        "preamp_diffpair": ["nmosinput", "pmosinput"],
        "preamp_bias": ["stdbias", "dynbias"],
        "comp_stages": ["singlestage", "doublestage"],
        "latch_pwrgate_ctl": ["clocked", "signalled"],
        "latch_pwrgate_node": ["external", "internal"],
        "latch_rst_extern_ctl": ["clocked", "signalled", "noreset"],
        "latch_rst_intern_ctl": ["clocked", "signalled"],
    },
    "dev_params": {
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "cap": {"c": 1, "m": 1},
    },
    "inst_params": [
        {"devices": ["M_preamp_diff+", "M_preamp_diff-"], "w": [4, 8], "type": ["lvt"]},
        {"devices": ["M_preamp_tail", "M_preamp_bias"], "w": [2, 4], "l": [2]},
        {"devices": ["M_preamp_rst+", "M_preamp_rst-"], "w": [2], "type": ["lvt"]},
        {
            "devices": ["Ma_latch+", "Ma_latch-", "Mb_latch+", "Mb_latch-"],
            "w": [1, 2, 4],
            "type": ["lvt"],
        },
    ],
}


def generate_topology(
    preamp_diffpair: str,
    preamp_bias: str,
    comp_stages: str,
    latch_pwrgate_ctl: str,
    latch_pwrgate_node: str,
    latch_rst_extern_ctl: str,
    latch_rst_intern_ctl: str,
) -> tuple[dict, dict] | tuple[None, None]:
    """
    Compute ports and devices for given topo_params combination.

    Called by expand_topo_params() for each cartesian product combo.
    Returns (None, None) for invalid combinations to skip.

    Args:
        preamp_diffpair: 'nmosinput' or 'pmosinput' - determines input differential pair type
        preamp_bias: 'stdbias' or 'dynbias' - whether to use dynamic biasing with capacitor
        comp_stages: 'singlestage' or 'doublestage' - if singlestage, use strong-arm direct connection (ignores latch params)
        latch_pwrgate_ctl: 'clocked' or 'signalled' - type of powergate control
        latch_pwrgate_node: 'external' or 'internal' - where powergate is positioned
        latch_rst_extern_ctl: 'clocked', 'signalled', or 'noreset' - external reset type (only if latch_pwrgate_node='external')
        latch_rst_intern_ctl: 'clocked' or 'signalled' - internal reset type (always present)

    Returns:
        Tuple of (ports, devices) or (None, None) for invalid combinations
    """
    # Skip invalid combinations
    if comp_stages == "singlestage":
        # For single stage, latch params don't matter, only generate once
        if (
            latch_pwrgate_ctl != "clocked"
            or latch_pwrgate_node != "external"
            or latch_rst_extern_ctl != "clocked"
            or latch_rst_intern_ctl != "clocked"
        ):
            return None, None
    elif comp_stages == "doublestage":
        # For double stage, external reset only valid if powergate is external
        if latch_pwrgate_node == "internal" and latch_rst_extern_ctl != "noreset":
            return None, None

    # Initialize topology components
    devices = {}
    ports = {
        "in+": "I",
        "in-": "I",
        "out+": "O",
        "out-": "O",
        "clk": "I",
        "clkb": "I",
        "vdd": "B",
        "vss": "B",
    }

    # Generate entire topology assuming NMOS input, will swap at end if PMOS

    # INPUT DIFFERENTIAL PAIR (assuming NMOS)
    if preamp_bias == "stdbias":
        # NMOS input, no dynamic biasing
        devices["M_preamp_diff+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "in+", "s": "tail", "b": "vss"},
        }
        devices["M_preamp_diff-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "in-", "s": "tail", "b": "vss"},
        }
        devices["M_preamp_tail"] = {
            "dev": "nmos",
            "pins": {"d": "tail", "g": "clk", "s": "vss", "b": "vss"},
        }
    elif preamp_bias == "dynbias":
        # NMOS input, with dynamic biasing
        devices["M_preamp_diff+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "in+", "s": "tail", "b": "vss"},
        }
        devices["M_preamp_diff-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "in-", "s": "tail", "b": "vss"},
        }
        devices["M_preamp_tail"] = {
            "dev": "nmos",
            "pins": {"d": "tail", "g": "clk", "s": "vcap", "b": "vss"},
        }
        devices["M_preamp_bias"] = {
            "dev": "nmos",
            "pins": {"d": "vcap", "g": "clk", "s": "vss", "b": "vss"},
        }
        devices["C_preamp_bias"] = {
            "dev": "cap",
            "pins": {"p": "vcap", "n": "vdd"},
            "c": 1,
        }

    # LOAD DEVICES (clocked, opposite type from input pair - PMOS for NMOS input)
    devices["M_preamp_rst+"] = {
        "dev": "pmos",
        "pins": {"d": "out-", "g": "clk", "s": "vdd", "b": "vdd"},
    }
    devices["M_preamp_rst-"] = {
        "dev": "pmos",
        "pins": {"d": "out+", "g": "clk", "s": "vdd", "b": "vdd"},
    }

    # LATCH STAGE
    if comp_stages == "singlestage":
        # Strong-arm configuration: direct connection with cross-coupled latch and clocked pullup reset
        # Cross-coupled PMOS latch
        devices["Ma_latch+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "out+", "s": "vdd", "b": "vdd"},
        }
        devices["Ma_latch-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "out-", "s": "vdd", "b": "vdd"},
        }
        # Cross-coupled NMOS latch
        devices["Mb_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "out+", "s": "vss", "b": "vss"},
        }
        devices["Mb_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "out-", "s": "vss", "b": "vss"},
        }
        # Clocked reset (PMOS pullups, active low on clkb)
        devices["M_latch_int_rst+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "clkb", "s": "vdd", "b": "vdd"},
        }
        devices["M_latch_int_rst-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "clkb", "s": "vdd", "b": "vdd"},
        }
    elif comp_stages == "doublestage":
        # Double-stage configuration with powergate options
        # Core cross-coupled CMOS latch (always present)
        devices["Ma_latch+"] = {
            "dev": "pmos",
            "pins": {"d": "latch-", "g": "latch+", "s": "latch_vdd", "b": "vdd"},
        }
        devices["Ma_latch-"] = {
            "dev": "pmos",
            "pins": {"d": "latch+", "g": "latch-", "s": "latch_vdd", "b": "vdd"},
        }
        devices["Mb_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "latch-", "g": "latch+", "s": "latch_vss", "b": "vss"},
        }
        devices["Mb_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "latch+", "g": "latch-", "s": "latch_vss", "b": "vss"},
        }

        # Connection from preamp to latch
        devices["M_preamp_to_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "latch-", "g": "out-", "s": "vss", "b": "vss"},
        }
        devices["M_preamp_to_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "latch+", "g": "out+", "s": "vss", "b": "vss"},
        }

        # POWERGATE CONFIGURATION
        if latch_pwrgate_node == "external":
            # Powergate at external node (between preamp and latch or at supply)
            if latch_pwrgate_ctl == "clocked":
                devices["M_latch_ext_powergate+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "clk", "s": "vdd", "b": "vdd"},
                }
                devices["M_latch_ext_powergate-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "clk", "s": "vdd", "b": "vdd"},
                }
            elif latch_pwrgate_ctl == "signalled":
                devices["M_latch_ext_powergate+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "latch-", "s": "vdd", "b": "vdd"},
                }
                devices["M_latch_ext_powergate-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "latch+", "s": "vdd", "b": "vdd"},
                }
            # External reset (if not noreset)
            if latch_rst_extern_ctl == "clocked":
                devices["M_latch_ext_rst+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch-", "g": "clkb", "s": "latch_vdd", "b": "vdd"},
                }
                devices["M_latch_ext_rst-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch+", "g": "clkb", "s": "latch_vdd", "b": "vdd"},
                }
            elif latch_rst_extern_ctl == "signalled":
                devices["M_latch_ext_rst+"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": "latch-",
                        "g": "latch-",
                        "s": "latch_vdd",
                        "b": "vdd",
                    },
                }
                devices["M_latch_ext_rst-"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": "latch+",
                        "g": "latch+",
                        "s": "latch_vdd",
                        "b": "vdd",
                    },
                }
            # No vss connection needed, use direct vss
            devices["M_latch_vss_conn+"] = {
                "dev": "nmos",
                "pins": {"d": "latch_vss", "g": "vdd", "s": "vss", "b": "vss"},
            }
            devices["M_latch_vss_conn-"] = {
                "dev": "nmos",
                "pins": {"d": "latch_vss", "g": "vdd", "s": "vss", "b": "vss"},
            }

        elif latch_pwrgate_node == "internal":
            # Powergate at internal node (no external reset, stacking at bottom)
            # Direct vdd connection
            devices["M_latch_vdd_conn+"] = {
                "dev": "pmos",
                "pins": {"d": "latch_vdd", "g": "vss", "s": "vdd", "b": "vdd"},
            }
            devices["M_latch_vdd_conn-"] = {
                "dev": "pmos",
                "pins": {"d": "latch_vdd", "g": "vss", "s": "vdd", "b": "vdd"},
            }
            # Powergate at vss side
            if latch_pwrgate_ctl == "clocked":
                devices["M_latch_int_powergate"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss", "g": "clk", "s": "vss", "b": "vss"},
                }
            elif latch_pwrgate_ctl == "signalled":
                devices["M_latch_int_powergate+"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss+", "g": "latch+", "s": "vss", "b": "vss"},
                }
                devices["M_latch_int_powergate-"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss-", "g": "latch-", "s": "vss", "b": "vss"},
                }

        # INTERNAL RESET (always present, always pulldown)
        if latch_rst_intern_ctl == "clocked":
            if latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled":
                # Stack reset on top of signalled powergate
                devices["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "clkb",
                        "s": "latch_vss+",
                        "b": "vss",
                    },
                }
                devices["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "clkb",
                        "s": "latch_vss-",
                        "b": "vss",
                    },
                }
            elif not (
                latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled"
            ):
                devices["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch-", "g": "clkb", "s": "latch_vss", "b": "vss"},
                }
                devices["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch+", "g": "clkb", "s": "latch_vss", "b": "vss"},
                }
        elif latch_rst_intern_ctl == "signalled":
            if latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled":
                # Stack reset on top of signalled powergate
                devices["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "latch-",
                        "s": "latch_vss+",
                        "b": "vss",
                    },
                }
                devices["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "latch+",
                        "s": "latch_vss-",
                        "b": "vss",
                    },
                }
            elif not (
                latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled"
            ):
                devices["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch-",
                        "g": "latch-",
                        "s": "latch_vss",
                        "b": "vss",
                    },
                }
                devices["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch+",
                        "g": "latch+",
                        "s": "latch_vss",
                        "b": "vss",
                    },
                }

        # Output buffers from latch to final output
        devices["Ma_latch_out+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "latch-", "s": "vdd", "b": "vdd"},
        }
        devices["Ma_latch_out-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "latch+", "s": "vdd", "b": "vdd"},
        }
        devices["Mb_latch_out+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "latch-", "s": "vss", "b": "vss"},
        }
        devices["Mb_latch_out-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "latch+", "s": "vss", "b": "vss"},
        }

    # If PMOS input, swap everything
    if preamp_diffpair == "pmosinput":
        swapped_devices = {}
        for dev_name, dev_info in devices.items():
            # Swap device name prefix Ma <-> Mb for cross-coupled pairs
            if dev_name.startswith("Ma_"):
                new_dev_name = "Mb_" + dev_name[3:]
            elif dev_name.startswith("Mb_"):
                new_dev_name = "Ma_" + dev_name[3:]
            else:
                new_dev_name = dev_name

            # Swap device type nmos <-> pmos
            new_dev_info = dev_info.copy()
            if "dev" in new_dev_info:
                if new_dev_info["dev"] == "nmos":
                    new_dev_info["dev"] = "pmos"
                elif new_dev_info["dev"] == "pmos":
                    new_dev_info["dev"] = "nmos"

            # Swap pin connections vdd <-> vss and clk <-> clkb
            if "pins" in new_dev_info:
                new_pins = {}
                for pin_name, pin_conn in new_dev_info["pins"].items():
                    if pin_conn == "vdd":
                        new_pins[pin_name] = "vss"
                    elif pin_conn == "vss":
                        new_pins[pin_name] = "vdd"
                    elif pin_conn == "clk":
                        new_pins[pin_name] = "clkb"
                    elif pin_conn == "clkb":
                        new_pins[pin_name] = "clk"
                    else:
                        new_pins[pin_name] = pin_conn
                new_dev_info["pins"] = new_pins

            swapped_devices[new_dev_name] = new_dev_info

        devices = swapped_devices

    return ports, devices


# Compute testbench PWL waveforms (static, computed at module load)
_n_common_modes = 5
_n_diff_voltages = 10
_n_samples = 10
_clk_period = 10

# Common-mode voltages (fractions of VDD)
_cm_voltages = [0.3, 0.4, 0.5, 0.6, 0.7]

# Differential voltages (in volts, relative to VDD=1.0)
_diff_min = -0.05  # -50mV
_diff_max = 0.05  # +50mV
_diff_step = (_diff_max - _diff_min) / (_n_diff_voltages - 1)
_diff_voltages = [_diff_min + i * _diff_step for i in range(_n_diff_voltages)]

# Build PWL points for common-mode sweep
_vcm_points = []
_t = 0
_cycles_per_diff = _n_samples
_cycles_per_cm = _n_diff_voltages * _cycles_per_diff

for _cm in _cm_voltages:
    _duration = _cycles_per_cm * _clk_period
    _vcm_points.extend([_t, _cm, _t + _duration, _cm])
    _t += _duration

# Build PWL points for differential voltage sweep
_vdiff_points = []
_t = 0

for _cm_idx in range(_n_common_modes):
    for _diff in _diff_voltages:
        _duration = _cycles_per_diff * _clk_period
        _vdiff_points.extend([_t, _diff, _t + _duration, _diff])
        _t += _duration

_total_time = _t


# Monolithic testbench struct (static topology - no topo_params)
# Comparator testbench for characterization (per Practical Hint 12.2):
#
# IMPORTANT: Source impedances (Zin) on both inputs are critical!
# Ideal voltage sources suppress kick-back -> over-optimistic results.
#
# Test structure:
# - 5 common-mode voltages: 0.3, 0.4, 0.5, 0.6, 0.7 × VDD
# - 10 differential voltages at each: -50mV to +50mV (~11mV steps)
# - 10 clock cycles (samples) at each point
# - 10 Monte Carlo runs
#
# Total: 5 × 10 × 10 = 500 comparisons per MC run
# Clock period: 10 time units → 5000 time units total per run
tb = {
    "devices": {
        # Power supplies
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
        # Common-mode voltage source (swept across 5 levels)
        "Vcm": {
            "dev": "vsource",
            "pins": {"p": "vcm", "n": "gnd"},
            "wave": "pwl",
            "points": _vcm_points,
        },
        # === INPUT SIGNAL PATH (Vin side) ===
        # Differential input: in+ = vcm + vdiff (swept across 10 levels per CM)
        "Vdiff": {
            "dev": "vsource",
            "pins": {"p": "vin_src", "n": "vcm"},
            "wave": "pwl",
            "points": _vdiff_points,
        },
        # Source impedance on signal input (models DAC/SHA output impedance)
        # Critical for accurate kick-back modeling!
        "Rsrc_p": {
            "dev": "res",
            "pins": {"p": "vin_src", "n": "in+"},
            "params": {"r": 1e3},
        },
        "Csrc_p": {
            "dev": "cap",
            "pins": {"p": "in+", "n": "gnd"},
            "params": {"c": 100e-15},
        },
        # === REFERENCE PATH (Vref side) ===
        # Reference: in- = vcm (no differential offset on reference side)
        "Vref": {
            "dev": "vsource",
            "pins": {"p": "vref_src", "n": "vcm"},
            "wave": "dc",
            "dc": 0.0,
        },
        # Source impedance on reference input (must match signal side!)
        "Rsrc_n": {
            "dev": "res",
            "pins": {"p": "vref_src", "n": "in-"},
            "params": {"r": 1e3},
        },
        "Csrc_n": {
            "dev": "cap",
            "pins": {"p": "in-", "n": "gnd"},
            "params": {"c": 100e-15},
        },
        # === CLOCK SIGNALS ===
        "Vclk": {
            "dev": "vsource",
            "pins": {"p": "clk", "n": "gnd"},
            "wave": "pulse",
            "v1": 0,
            "v2": 1.0,
            "td": 0.5,
            "tr": 0.1,
            "tf": 0.1,
            "pw": 4,  # 40% duty cycle high (evaluation phase)
            "per": _clk_period,
        },
        # Complementary clock (inverted)
        "Vclkb": {
            "dev": "vsource",
            "pins": {"p": "clkb", "n": "gnd"},
            "wave": "pulse",
            "v1": 1.0,
            "v2": 0,
            "td": 0.5,
            "tr": 0.1,
            "tf": 0.1,
            "pw": 4,
            "per": _clk_period,
        },
        # === OUTPUT LOADING ===
        "Cload_p": {
            "dev": "cap",
            "pins": {"p": "out+", "n": "vss"},
            "params": {"c": 10e-15},
        },
        "Cload_n": {
            "dev": "cap",
            "pins": {"p": "out-", "n": "vss"},
            "params": {"c": 10e-15},
        },
        # === DUT ===
        "Xdut": {
            "dev": "comp",
            "pins": {
                "in+": "in+",
                "in-": "in-",
                "out+": "out+",
                "out-": "out-",
                "clk": "clk",
                "clkb": "clkb",
                "vdd": "vdd",
                "vss": "vss",
            },
        },
    },
    "analyses": {
        "mc1": {
            "type": "montecarlo",
            "numruns": 10,
            "seed": 12345,
            "variations": "all",
        },
        "tran1": {
            "type": "tran",
            "stop": _total_time,
            "strobeperiod": _clk_period / 2,
            "noisefmax": 10e9,
            "noiseseed": 1,
        },
    },
    "corner": ["tt"],
    "temp": [27],
}


def measure(raw, subckt_json, tb_json, raw_file):
    """
    Measure comparator simulation results using statistical method.

    Per Section 6.4 "Simulation of Comparator Noise":
    - At each (Vcm, Vdiff) test point, count ONEs vs ZEROs across samples
    - n0/n1 ratio maps to Gaussian CDF at -Vdiff, revealing noise σ
    - Offset is where n0 ≈ n1 (50% threshold)

    Test structure: 5 CM × 10 Vdiff × 10 samples = 500 comparisons per MC run
    """
    from flow.measure import read_traces, quantize, write_analysis
    import numpy as np
    from scipy import special  # For inverse error function

    # Test parameters (must match testbench)
    n_common_modes = 5
    n_diff_voltages = 10
    n_samples = 10
    cm_voltages = [0.3, 0.4, 0.5, 0.6, 0.7]
    diff_min, diff_max = -0.05, 0.05
    diff_voltages = np.linspace(diff_min, diff_max, n_diff_voltages)

    # Read simulation traces
    time, vinp, vinn, voutp, voutn, vclk, vclkb, vdda, vssa = read_traces(raw)

    # Quantize signals for digital analysis
    vth = vdda / 2  # Decision threshold
    qvclk = quantize(vclk, bits=1, max=vdda, min=0)
    qvout_diff = (voutp - voutn) > 0  # True = ONE (out+ > out-)

    # Find clock falling edges (end of evaluation phase, sample output here)
    clk_falling = np.where(np.diff(qvclk) < 0)[0]

    # Organize decisions by test point
    # decisions[cm_idx][diff_idx] = list of binary decisions (True/False)
    decisions = [[[] for _ in range(n_diff_voltages)] for _ in range(n_common_modes)]

    for i, sample_idx in enumerate(clk_falling):
        if sample_idx >= len(qvout_diff):
            continue

        # Determine which test point this sample belongs to
        cycle = i
        cm_idx = cycle // (n_diff_voltages * n_samples)
        diff_idx = (cycle % (n_diff_voltages * n_samples)) // n_samples

        if cm_idx < n_common_modes and diff_idx < n_diff_voltages:
            decisions[cm_idx][diff_idx].append(qvout_diff[sample_idx])

    # Analyze each common-mode voltage
    results = {
        "cm_voltages": cm_voltages,
        "diff_voltages": list(diff_voltages),
        "offset_mV": [],  # Offset at each CM
        "sigma_mV": [],  # Estimated noise σ at each CM
        "one_counts": [],  # n1 counts at each test point
    }

    for cm_idx, cm in enumerate(cm_voltages):
        # Count ONEs at each differential voltage
        one_counts = []
        for diff_idx in range(n_diff_voltages):
            n1 = sum(decisions[cm_idx][diff_idx])
            n_total = len(decisions[cm_idx][diff_idx])
            one_counts.append((n1, n_total))

        results["one_counts"].append(one_counts)

        # Find offset: interpolate where P(ONE) = 0.5
        p_one = [n1 / max(n_total, 1) for n1, n_total in one_counts]

        offset = 0.0
        for j in range(1, len(p_one)):
            if (p_one[j - 1] - 0.5) * (p_one[j] - 0.5) <= 0:
                # Linear interpolation
                v1, p1 = diff_voltages[j - 1], p_one[j - 1]
                v2, p2 = diff_voltages[j], p_one[j]
                if p2 != p1:
                    offset = v1 + (0.5 - p1) * (v2 - v1) / (p2 - p1)
                break

        results["offset_mV"].append(float(offset * 1000))

        # Estimate noise σ from transition slope
        # P(ONE) = Φ((Vdiff - offset) / σ) where Φ is Gaussian CDF
        # Use points near 50% transition for best estimate
        sigma_estimates = []
        for j, (p, vdiff) in enumerate(zip(p_one, diff_voltages)):
            if 0.1 < p < 0.9:  # Avoid extremes
                # Φ^(-1)(p) = (Vdiff - offset) / σ
                # σ = (Vdiff - offset) / Φ^(-1)(p)
                phi_inv = np.sqrt(2) * special.erfinv(2 * p - 1)
                if abs(phi_inv) > 0.1:  # Avoid division by small numbers
                    sigma = abs((vdiff - offset) / phi_inv)
                    sigma_estimates.append(sigma)

        sigma = np.median(sigma_estimates) if sigma_estimates else 0.0
        results["sigma_mV"].append(float(sigma * 1000))

    # Summary statistics
    results["mean_offset_mV"] = float(np.mean(results["offset_mV"]))
    results["std_offset_mV"] = float(np.std(results["offset_mV"]))
    results["mean_sigma_mV"] = float(np.mean(results["sigma_mV"]))

    write_analysis(raw_file, results)

    return results
