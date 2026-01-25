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
    "instances": {},  # Empty - computed by generate_topology()
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
    "inst_params": [
        # Defaults for all nmos/pmos/cap instances
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        {"instances": {"cap": "all"}, "c": 1, "m": 1},
        # Override specific instances with sweeps
        {"instances": {"nmos": ["M_preamp_diff+", "M_preamp_diff-"], "pmos": ["M_preamp_diff+", "M_preamp_diff-"]}, "w": [4, 8], "type": ["lvt"]},
        {"instances": {"nmos": ["M_preamp_tail", "M_preamp_bias"], "pmos": ["M_preamp_tail", "M_preamp_bias"]}, "w": [2, 4], "l": [2]},
        {"instances": {"nmos": ["M_preamp_rst+", "M_preamp_rst-"], "pmos": ["M_preamp_rst+", "M_preamp_rst-"]}, "w": [2], "type": ["lvt"]},
        {
            "instances": {"nmos": ["Ma_latch+", "Ma_latch-", "Mb_latch+", "Mb_latch-"], "pmos": ["Ma_latch+", "Ma_latch-", "Mb_latch+", "Mb_latch-"]},
            "w": [1, 2, 4],
            "type": ["lvt"],
        },
    ],
}


def gen_topo_subckt(
    preamp_diffpair: str,
    preamp_bias: str,
    comp_stages: str,
    latch_pwrgate_ctl: str,
    latch_pwrgate_node: str,
    latch_rst_extern_ctl: str,
    latch_rst_intern_ctl: str,
) -> tuple[dict, dict] | tuple[None, None]:
    """
    Compute ports and instances for given topo_params combination.

    Called by generate_topology() for each cartesian product combo.
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
    instances = {}
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
        instances["M_preamp_diff+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "in+", "s": "tail", "b": "vss"},
        }
        instances["M_preamp_diff-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "in-", "s": "tail", "b": "vss"},
        }
        instances["M_preamp_tail"] = {
            "dev": "nmos",
            "pins": {"d": "tail", "g": "clk", "s": "vss", "b": "vss"},
        }
    elif preamp_bias == "dynbias":
        # NMOS input, with dynamic biasing
        instances["M_preamp_diff+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "in+", "s": "tail", "b": "vss"},
        }
        instances["M_preamp_diff-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "in-", "s": "tail", "b": "vss"},
        }
        instances["M_preamp_tail"] = {
            "dev": "nmos",
            "pins": {"d": "tail", "g": "clk", "s": "vcap", "b": "vss"},
        }
        instances["M_preamp_bias"] = {
            "dev": "nmos",
            "pins": {"d": "vcap", "g": "clk", "s": "vss", "b": "vss"},
        }
        instances["C_preamp_bias"] = {
            "dev": "cap",
            "pins": {"p": "vcap", "n": "vdd"},
            "c": 1,
        }

    # LOAD DEVICES (clocked, opposite type from input pair - PMOS for NMOS input)
    instances["M_preamp_rst+"] = {
        "dev": "pmos",
        "pins": {"d": "out-", "g": "clk", "s": "vdd", "b": "vdd"},
    }
    instances["M_preamp_rst-"] = {
        "dev": "pmos",
        "pins": {"d": "out+", "g": "clk", "s": "vdd", "b": "vdd"},
    }

    # LATCH STAGE
    if comp_stages == "singlestage":
        # Strong-arm configuration: direct connection with cross-coupled latch and clocked pullup reset
        # Cross-coupled PMOS latch
        instances["Ma_latch+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "out+", "s": "vdd", "b": "vdd"},
        }
        instances["Ma_latch-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "out-", "s": "vdd", "b": "vdd"},
        }
        # Cross-coupled NMOS latch
        instances["Mb_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "out+", "s": "vss", "b": "vss"},
        }
        instances["Mb_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "out-", "s": "vss", "b": "vss"},
        }
        # Clocked reset (PMOS pullups, active low on clkb)
        instances["M_latch_int_rst+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "clkb", "s": "vdd", "b": "vdd"},
        }
        instances["M_latch_int_rst-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "clkb", "s": "vdd", "b": "vdd"},
        }
    elif comp_stages == "doublestage":
        # Double-stage configuration with powergate options
        # Core cross-coupled CMOS latch (always present)
        instances["Ma_latch+"] = {
            "dev": "pmos",
            "pins": {"d": "latch-", "g": "latch+", "s": "latch_vdd", "b": "vdd"},
        }
        instances["Ma_latch-"] = {
            "dev": "pmos",
            "pins": {"d": "latch+", "g": "latch-", "s": "latch_vdd", "b": "vdd"},
        }
        instances["Mb_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "latch-", "g": "latch+", "s": "latch_vss", "b": "vss"},
        }
        instances["Mb_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "latch+", "g": "latch-", "s": "latch_vss", "b": "vss"},
        }

        # Connection from preamp to latch
        instances["M_preamp_to_latch+"] = {
            "dev": "nmos",
            "pins": {"d": "latch-", "g": "out-", "s": "vss", "b": "vss"},
        }
        instances["M_preamp_to_latch-"] = {
            "dev": "nmos",
            "pins": {"d": "latch+", "g": "out+", "s": "vss", "b": "vss"},
        }

        # POWERGATE CONFIGURATION
        if latch_pwrgate_node == "external":
            # Powergate at external node (between preamp and latch or at supply)
            if latch_pwrgate_ctl == "clocked":
                instances["M_latch_ext_powergate+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "clk", "s": "vdd", "b": "vdd"},
                }
                instances["M_latch_ext_powergate-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "clk", "s": "vdd", "b": "vdd"},
                }
            elif latch_pwrgate_ctl == "signalled":
                instances["M_latch_ext_powergate+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "latch-", "s": "vdd", "b": "vdd"},
                }
                instances["M_latch_ext_powergate-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch_vdd", "g": "latch+", "s": "vdd", "b": "vdd"},
                }
            # External reset (if not noreset)
            if latch_rst_extern_ctl == "clocked":
                instances["M_latch_ext_rst+"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch-", "g": "clkb", "s": "latch_vdd", "b": "vdd"},
                }
                instances["M_latch_ext_rst-"] = {
                    "dev": "pmos",
                    "pins": {"d": "latch+", "g": "clkb", "s": "latch_vdd", "b": "vdd"},
                }
            elif latch_rst_extern_ctl == "signalled":
                instances["M_latch_ext_rst+"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": "latch-",
                        "g": "latch-",
                        "s": "latch_vdd",
                        "b": "vdd",
                    },
                }
                instances["M_latch_ext_rst-"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": "latch+",
                        "g": "latch+",
                        "s": "latch_vdd",
                        "b": "vdd",
                    },
                }
            # No vss connection needed, use direct vss
            instances["M_latch_vss_conn+"] = {
                "dev": "nmos",
                "pins": {"d": "latch_vss", "g": "vdd", "s": "vss", "b": "vss"},
            }
            instances["M_latch_vss_conn-"] = {
                "dev": "nmos",
                "pins": {"d": "latch_vss", "g": "vdd", "s": "vss", "b": "vss"},
            }

        elif latch_pwrgate_node == "internal":
            # Powergate at internal node (no external reset, stacking at bottom)
            # Direct vdd connection
            instances["M_latch_vdd_conn+"] = {
                "dev": "pmos",
                "pins": {"d": "latch_vdd", "g": "vss", "s": "vdd", "b": "vdd"},
            }
            instances["M_latch_vdd_conn-"] = {
                "dev": "pmos",
                "pins": {"d": "latch_vdd", "g": "vss", "s": "vdd", "b": "vdd"},
            }
            # Powergate at vss side
            if latch_pwrgate_ctl == "clocked":
                instances["M_latch_int_powergate"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss", "g": "clk", "s": "vss", "b": "vss"},
                }
            elif latch_pwrgate_ctl == "signalled":
                instances["M_latch_int_powergate+"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss+", "g": "latch+", "s": "vss", "b": "vss"},
                }
                instances["M_latch_int_powergate-"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch_vss-", "g": "latch-", "s": "vss", "b": "vss"},
                }

        # INTERNAL RESET (always present, always pulldown)
        if latch_rst_intern_ctl == "clocked":
            if latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled":
                # Stack reset on top of signalled powergate
                instances["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "clkb",
                        "s": "latch_vss+",
                        "b": "vss",
                    },
                }
                instances["M_latch_int_rst-"] = {
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
                instances["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch-", "g": "clkb", "s": "latch_vss", "b": "vss"},
                }
                instances["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {"d": "latch+", "g": "clkb", "s": "latch_vss", "b": "vss"},
                }
        elif latch_rst_intern_ctl == "signalled":
            if latch_pwrgate_node == "internal" and latch_pwrgate_ctl == "signalled":
                # Stack reset on top of signalled powergate
                instances["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch_vss",
                        "g": "latch-",
                        "s": "latch_vss+",
                        "b": "vss",
                    },
                }
                instances["M_latch_int_rst-"] = {
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
                instances["M_latch_int_rst+"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch-",
                        "g": "latch-",
                        "s": "latch_vss",
                        "b": "vss",
                    },
                }
                instances["M_latch_int_rst-"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": "latch+",
                        "g": "latch+",
                        "s": "latch_vss",
                        "b": "vss",
                    },
                }

        # Output buffers from latch to final output
        instances["Ma_latch_out+"] = {
            "dev": "pmos",
            "pins": {"d": "out-", "g": "latch-", "s": "vdd", "b": "vdd"},
        }
        instances["Ma_latch_out-"] = {
            "dev": "pmos",
            "pins": {"d": "out+", "g": "latch+", "s": "vdd", "b": "vdd"},
        }
        instances["Mb_latch_out+"] = {
            "dev": "nmos",
            "pins": {"d": "out-", "g": "latch-", "s": "vss", "b": "vss"},
        }
        instances["Mb_latch_out-"] = {
            "dev": "nmos",
            "pins": {"d": "out+", "g": "latch+", "s": "vss", "b": "vss"},
        }

    # If PMOS input, swap everything
    if preamp_diffpair == "pmosinput":
        swapped_instances = {}
        for dev_name, dev_info in instances.items():
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

            swapped_instances[new_dev_name] = new_dev_info

        instances = swapped_instances

    return ports, instances


# Testbench parameters
_n_common_modes = 5
_n_diff_voltages = 10
_n_samples = 10
_clk_period = 10

# Derived timing: each CM level holds for (n_diff * n_samples * clk_period) time units
_cycles_per_diff = _n_samples
_cycles_per_cm = _n_diff_voltages * _cycles_per_diff
_tstep_per_cm = _cycles_per_cm * _clk_period  # 1000 time units per CM level
_tstep_per_diff = _cycles_per_diff * _clk_period  # 100 time units per diff level
_total_diff_steps = _n_common_modes * _n_diff_voltages  # 50 total diff steps
_total_time = _n_common_modes * _tstep_per_cm  # 5000 time units total


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
#
# Total: 5 × 10 × 10 = 500 comparisons per run
# Clock period: 10 time units → 5000 time units total per run
tb = {
    "instances": {
        # Power supplies
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
        # Common-mode voltage source (swept across 5 levels)
        # Each level held for 1000 time units (10 diff × 10 samples × 10 clk)
        "Vcm": {
            "dev": "vsource",
            "pins": {"p": "vcm", "n": "gnd"},
            "wave": "pwl",
            "params": {
                "type": "step",
                "vstart": 0.3,
                "vstep": 0.1,
                "tstep": _tstep_per_cm,
                "count": _n_common_modes,
            },
        },
        # === INPUT SIGNAL PATH (Vin side) ===
        # Differential input: in+ = vcm + vdiff (swept across 10 levels per CM)
        # Sweeps -0.05 to +0.05 (normalized), 50 total steps (5 CM × 10 diff)
        "Vdiff": {
            "dev": "vsource",
            "pins": {"p": "vin_src", "n": "vcm"},
            "wave": "pwl",
            "params": {
                "type": "step",
                "vstart": -0.05,
                "vstop": 0.05,
                "tstep": _tstep_per_diff,
                "count": _total_diff_steps,
            },
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
            "params": {"dc": 0.0},
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
            "params": {
                "v1": 0,
                "v2": 1.0,
                "td": 0.5,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 4,  # 40% duty cycle high (evaluation phase)
                "per": _clk_period,
            },
        },
        # Complementary clock (inverted)
        "Vclkb": {
            "dev": "vsource",
            "pins": {"p": "clkb", "n": "gnd"},
            "wave": "pulse",
            "params": {
                "v1": 1.0,
                "v2": 0,
                "td": 0.5,
                "tr": 0.1,
                "tf": 0.1,
                "pw": 4,
                "per": _clk_period,
            },
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
            "cell": "comp",
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
}

# ========================================================================
# PyOPUS Analyses Configuration
# ========================================================================

# PyOPUS analyses for comparator (transient only)
analyses = {
    "tran": {
        "saves": ["all()"],
        # Total time: 5 common modes × 1000 tstep = 5000 normalized units = 5µs
        "command": "tran(stop=5e-6, errpreset='conservative')",
    }
}


# PyOPUS measures configuration
# Measure functions are defined in flow/measure.py
measures = {
    "offset_mV": {
        "analysis": "tran",
        "expression": "m.comp_offset_mV(v, scale, 'in+', 'in-', 'out+', 'out-')",
    },
    "delay_ns": {
        "analysis": "tran",
        "expression": "m.comp_delay_ns(v, scale, 'clk', 'out+', 'out-')",
    },
    "settling_ns": {
        "analysis": "tran",
        "expression": "m.comp_settling_ns(v, scale, 'out+', 'out-', 0.01)",
    },
    "overshoot_pct": {
        "analysis": "tran",
        "expression": "m.comp_overshoot_pct(v, scale, 'out+', 'out-')",
    },
    "power_uW": {
        "analysis": "tran",
        "expression": "m.avg_power_uW(v, i, scale, 'vdd')",
    },
    "slew_Vns": {
        "analysis": "tran",
        "expression": "m.slew_rate_Vns(v, scale, 'out+', 'rising')",
    },
}


# ========================================================================
# PyOPUS Visualisation Configuration
# ========================================================================

visualisation = {
    "graphs": {
        "transient": {
            "title": "Comparator Transient Response",
            "shape": {"figsize": (10, 6), "dpi": 100},
            "axes": {
                "signals": {
                    "subplot": (2, 1, 1),
                    "xlabel": "Time [s]",
                    "ylabel": "Voltage [V]",
                    "legend": True,
                    "grid": True,
                },
                "clock": {
                    "subplot": (2, 1, 2),
                    "xlabel": "Time [s]",
                    "ylabel": "Voltage [V]",
                    "grid": True,
                },
            },
        },
        "summary": {
            "title": "Performance Summary",
            "shape": {"figsize": (8, 6)},
            "axes": {
                "bar": {
                    "subplot": (1, 1, 1),
                    "xlabel": "Configuration",
                    "ylabel": "Offset [mV]",
                    "grid": True,
                }
            },
        },
    },
    "styles": [
        {
            "pattern": ("^.*", "^.*", "^.*", "^.*"),
            "style": {"color": "blue", "linestyle": "-"},
        },
    ],
    "traces": {
        "inp": {
            "graph": "transient",
            "axes": "signals",
            "xresult": "time",
            "yresult": "v_inp",
        },
        "outp": {
            "graph": "transient",
            "axes": "signals",
            "xresult": "time",
            "yresult": "v_outp",
        },
        "clk": {
            "graph": "transient",
            "axes": "clock",
            "xresult": "time",
            "yresult": "v_clk",
        },
    },
}
