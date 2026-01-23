"""
CDAC subcircuit definition.

Dynamic topology using topo_params - generate_topology() computes ports/devices
for each CDAC configuration.

Topo params:
    n_dac: DAC resolution (7, 9, 11, 13)
    n_extra: Number of extra physical capacitors (0, 2, 4, 6)
    redun_strat: Weight distribution strategy (rdx2, subrdx2, etc.)
    split_strat: Physical implementation (nosplit, vdivsplit, diffcapsplit)
"""

import math
from typing import Any

# Merged subckt struct with topology params and sweeps combined
subckt = {
    "cellname": "cdac",
    "ports": {},  # Empty - computed by generate_topology()
    "instances": {},  # Empty - computed by generate_topology()
    "tech": ["tsmc65", "tsmc28", "tower180"],
    "topo_params": {
        "n_dac": [7, 9, 11, 13],
        "n_extra": [0, 2, 4, 6],
        "redun_strat": ["rdx2", "subrdx2rdst", "subrdx2lim", "subrdx2", "rdx2rpt"],
        "split_strat": ["nosplit", "vdivsplit", "diffcapsplit"],
    },
    "inst_params": [
        # Defaults for all nmos/pmos/cap/res instances
        {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
        {"instances": {"cap": "all"}, "type": ["momcap_1m", "momcap_2m", "momcap_3m"]},
        {"instances": {"res": "all"}, "type": "polyres", "r": 4},
    ],
}


def calc_weights(n_dac: int, n_extra: int, strategy: str) -> list[int] | None:
    """
    Calculate capacitor weights for CDAC.

    Args:
        n_dac: DAC resolution (number of bits)
        n_extra: Number of extra physical capacitors for redundancy
        strategy: 'rdx2', 'subrdx2', 'subrdx2lim', 'subrdx2rdst', 'rdx2rpt'

    Returns:
        List of (n_dac + n_extra) integer weights (in units of Cu), or None for invalid combos
    """
    m_caps = n_dac + n_extra

    if strategy == "rdx2":
        # Standard binary weighting: [2^(n-1), 2^(n-2), ..., 2, 1]
        # Pad with unit caps if n_extra > 0
        weights = [2**i for i in range(n_dac - 1, -1, -1)]
        if n_extra > 0:
            weights.extend([1] * n_extra)
        return weights

    elif strategy == "subrdx2":
        # Each bit is equal to radix^bit up to bit M-1, where radix = 2^(N/M)
        # Round to nearest integer (not floor like normalized)
        radix = 2 ** (n_dac / m_caps)
        weights = [round(radix ** (m_caps - 1 - i)) for i in range(m_caps)]
        return weights

    elif strategy == "subrdx2lim":
        # Sub-radix-2 with unit quantization
        # Radix < 2 provides redundancy for error correction
        radix = 2 ** (n_dac / m_caps)
        weights = [max(1, int(radix ** (m_caps - 1 - i))) for i in range(m_caps)]
        return weights

    elif strategy == "subrdx2rdst":
        # Binary with MSB redistribution for redundancy
        # Split 2^n_redist from MSB and redistribute as pairs
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]

        # Check if MSB would become negative - return None for invalid combinations
        if weights[0] < 2**n_redist:
            return None

        weights[0] -= 2**n_redist  # Subtract from MSB

        # Redundant weights as paired powers of 2
        w_redun = [2**i for i in range(n_redist - 2, -1, -1) for _ in range(2)]
        w_redun += [1, 1]  # Final unit pair

        # Merge: add redundant weights offset by 1 position
        result = [0] * m_caps
        for i, w in enumerate(weights):
            if i < m_caps:
                result[i] += w
        for i, w in enumerate(w_redun):
            if i + 1 < m_caps:
                result[i + 1] += w

        return result

    elif strategy == "rdx2rpt":
        # Generate base radix-2 array, then insert repeated capacitors
        # Extra capacitors are inserted at regular intervals

        # Base radix-2 weights
        base_weights = [2**i for i in range(n_dac - 1, -1, -1)]

        if n_extra == 0:
            return base_weights

        # Calculate spacing for inserted capacitors
        spacing = n_dac // n_extra

        # Calculate which base array positions should be duplicated
        # First duplicate is 1 position from end, then every 'spacing' positions earlier
        duplicate_indices = []
        for k in range(n_extra):
            pos_from_end = 1 + k * spacing
            # Convert to 0-based index in base_weights array
            idx = n_dac - 1 - pos_from_end
            duplicate_indices.append(idx)

        # Sort in ascending order to process from MSB to LSB
        duplicate_indices.sort()

        # Build result by inserting duplicates after their positions
        result = []
        dup_idx = 0
        for i in range(n_dac):
            result.append(base_weights[i])
            # Check if this position should be duplicated
            if dup_idx < len(duplicate_indices) and i == duplicate_indices[dup_idx]:
                result.append(base_weights[i])
                dup_idx += 1

        return result

    else:
        return None  # Unknown strategy


def generate_topology(
    n_dac: int, n_extra: int, redun_strat: str, split_strat: str
) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    """
    Compute ports and instances for given topo_params combination.

    Called by generate_topology() for each cartesian product combo.
    Returns (None, None) for invalid combinations to skip.

    Args:
        n_dac: DAC resolution (number of bits)
        n_extra: Number of extra physical capacitors for redundancy
        redun_strat: Weighting strategy (rdx2, subrdx2*, etc.)
        split_strat: 'nosplit', 'vdivsplit', or 'diffcapsplit'

    Returns:
        Tuple of (ports, instances) or (None, None) for invalid combinations
    """
    # Skip invalid combinations: rdx2 only works with n_extra=0, others only with n_extra>0
    if redun_strat == "rdx2" and n_extra != 0:
        return None, None
    if redun_strat != "rdx2" and n_extra == 0:
        return None, None

    # Calculate weights for this configuration
    weights = calc_weights(n_dac, n_extra, redun_strat)
    if weights is None:
        return None, None

    threshold = 64  # Split threshold (unitless)

    # Initialize topology components
    instances = {}
    ports = {"top": "B", "vdd": "B", "vss": "B"}

    # Generate resistor ladder for vdivsplit (all 64 taps)
    if split_strat == "vdivsplit":
        for i in range(64):
            if i == 0:
                instances[f"R{i}"] = {
                    "dev": "res",
                    "pins": {"p": "vdd", "n": f"tap[{i + 1}]"},
                    "r": 4,
                }
            elif i == 63:
                instances[f"R{i}"] = {
                    "dev": "res",
                    "pins": {"p": f"tap[{i}]", "n": "vss"},
                    "r": 4,
                }
            else:
                instances[f"R{i}"] = {
                    "dev": "res",
                    "pins": {"p": f"tap[{i}]", "n": f"tap[{i + 1}]"},
                    "r": 4,
                }

    # UNIFIED STAGE LOOP - Process all weights regardless of magnitude
    for idx, w in enumerate(weights):
        ports[f"dac[{idx}]"] = "I"

        # First inverter (predriver - always unit sized)
        instances[f"MPbuf{idx}"] = {
            "dev": "pmos",
            "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"},
            "w": 1,
        }
        instances[f"MNbuf{idx}"] = {
            "dev": "nmos",
            "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"},
            "w": 1,
        }

        if split_strat == "nosplit":
            # No Split: c=1 (unit cap), m=weight (multiple instances)
            driver_w = calc_driver_strength(c=1, m=w)
            instances[f"MPdrv{idx}"] = {
                "dev": "pmos",
                "pins": {
                    "d": f"bot[{idx}]",
                    "g": f"inter[{idx}]",
                    "s": "vdd",
                    "b": "vdd",
                },
                "w": driver_w,
            }
            instances[f"MNdrv{idx}"] = {
                "dev": "nmos",
                "pins": {
                    "d": f"bot[{idx}]",
                    "g": f"inter[{idx}]",
                    "s": "vss",
                    "b": "vss",
                },
                "w": driver_w,
            }
            instances[f"Cmain{idx}"] = {
                "dev": "cap",
                "pins": {"p": "top", "n": f"bot[{idx}]"},
                "c": 1,
                "m": w,
            }

        elif split_strat == "vdivsplit":
            # Voltage Divider Split: Decompose weight into coarse + fine parts
            quotient = w // threshold  # Integer division
            remainder = w % threshold  # Modulo

            if quotient > 0:
                # Main capacitor: m=quotient, c=threshold
                driver_w = calc_driver_strength(c=threshold, m=quotient)
                instances[f"MPdrv{idx}"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": f"bot[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": "vdd",
                        "b": "vdd",
                    },
                    "w": driver_w,
                }
                instances[f"MNdrv{idx}"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": f"bot[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": "vss",
                        "b": "vss",
                    },
                    "w": driver_w,
                }
                instances[f"Cmain{idx}"] = {
                    "dev": "cap",
                    "pins": {"p": "top", "n": f"bot[{idx}]"},
                    "c": threshold,
                    "m": quotient,
                }

            if remainder > 0:
                # Fine capacitor: m=1, c=1, driven with reduced voltage from resistor tap
                tap_node = f"tap[{remainder}]"
                driver_w_rdiv = calc_driver_strength(c=1, m=1)
                instances[f"MPrdiv{idx}"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": f"bot_rdiv[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": tap_node,
                        "b": tap_node,
                    },
                    "w": driver_w_rdiv,
                }
                instances[f"MNrdiv{idx}"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": f"bot_rdiv[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": "vss",
                        "b": "vss",
                    },
                    "w": driver_w_rdiv,
                }
                instances[f"Cmain{idx}"] = {
                    "dev": "cap",
                    "pins": {"p": "top", "n": f"bot_rdiv[{idx}]"},
                    "c": 1,
                    "m": 1,
                }

        elif split_strat == "diffcapsplit":
            # Difference Capacitor Split: Decompose weight into coarse + fine parts
            quotient = w // threshold
            remainder = w % threshold

            if quotient > 0:
                # Main coarse cap: m=quotient, c=threshold
                driver_w = calc_driver_strength(c=threshold, m=quotient)
                instances[f"MPdrv{idx}"] = {
                    "dev": "pmos",
                    "pins": {
                        "d": f"bot[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": "vdd",
                        "b": "vdd",
                    },
                    "w": driver_w,
                }
                instances[f"MNdrv{idx}"] = {
                    "dev": "nmos",
                    "pins": {
                        "d": f"bot[{idx}]",
                        "g": f"inter[{idx}]",
                        "s": "vss",
                        "b": "vss",
                    },
                    "w": driver_w,
                }
                instances[f"Cmain{idx}"] = {
                    "dev": "cap",
                    "pins": {"p": "top", "n": f"bot[{idx}]"},
                    "c": threshold,
                    "m": quotient,
                }

                # Diff coarse cap: m=quotient, c=1, driven from intermediate node
                instances[f"Cdiff{idx}"] = {
                    "dev": "cap",
                    "pins": {"p": "top", "n": f"inter[{idx}]"},
                    "c": 1,
                    "m": quotient,
                }

            if remainder > 0:
                # Fine caps use difference capacitor approach
                # Main cap: c=(threshold+1+remainder), diff cap: c=(threshold+1-remainder)
                c_main = threshold + 1 + remainder
                c_diff = threshold + 1 - remainder

                # Only need one driver since both caps share the same node structure
                # Main cap driven to bot node, diff cap from inter node
                if quotient == 0:
                    # No coarse part, so add the main driver
                    driver_w = calc_driver_strength(c=c_main, m=1)
                    instances[f"MPdrv{idx}"] = {
                        "dev": "pmos",
                        "pins": {
                            "d": f"bot[{idx}]",
                            "g": f"inter[{idx}]",
                            "s": "vdd",
                            "b": "vdd",
                        },
                        "w": driver_w,
                    }
                    instances[f"MNdrv{idx}"] = {
                        "dev": "nmos",
                        "pins": {
                            "d": f"bot[{idx}]",
                            "g": f"inter[{idx}]",
                            "s": "vss",
                            "b": "vss",
                        },
                        "w": driver_w,
                    }
                    instances[f"Cmain{idx}"] = {
                        "dev": "cap",
                        "pins": {"p": "top", "n": f"bot[{idx}]"},
                        "c": c_main,
                        "m": 1,
                    }
                    instances[f"Cdiff{idx}"] = {
                        "dev": "cap",
                        "pins": {"p": "top", "n": f"inter[{idx}]"},
                        "c": c_diff,
                        "m": 1,
                    }
                else:
                    # Coarse part exists, add separate fine caps with different naming
                    instances[f"Cmain{idx}"] = {
                        "dev": "cap",
                        "pins": {"p": "top", "n": f"bot[{idx}]"},
                        "c": c_main,
                        "m": 1,
                    }
                    instances[f"Cdiff{idx}"] = {
                        "dev": "cap",
                        "pins": {"p": "top", "n": f"inter[{idx}]"},
                        "c": c_diff,
                        "m": 1,
                    }

    return ports, instances


"""
CDAC Testbench:

Characterizes CDAC linearity by sweeping through DAC codes.

Test structure:
- DAC input bit sources with PWL waveforms
- Code sequence: 0 -> 1/4 -> 1/2 -> 3/4 -> full scale
- Load capacitor on top node
- Transient analysis to measure DAC transfer function

The number of DAC input bits matches the CDAC topology (n_dac).
"""

# Monolithic testbench struct (dynamic topology - uses n_dac topo_param)
tb = {
    "instances": {},  # Empty - computed by generate_tb_topology()
    "analyses": {"tran1": {"type": "tran", "stop": 500, "step": 0.1}},
    "corner": ["tt"],
    "temp": [27],
    "topo_params": {
        "n_dac": [7, 9, 11, 13]  # Match subckt n_dac values
    },
}


def generate_tb_topology(n_dac: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Generate testbench topology for given n_dac.

    Args:
        n_dac: DAC resolution (number of bits)

    Returns:
        Tuple of (ports, instances) - ports is empty for top-level TB
    """
    ports: dict[str, Any] = {}  # Testbenches have no ports (top-level)

    instances: dict[str, Any] = {
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
    }

    # Add DAC bit sources - sweep through key codes
    # Code sequence: 0 -> 1/4 -> 1/2 -> 3/4 -> full_scale
    max_code = (1 << n_dac) - 1
    test_codes = [0, max_code // 4, max_code // 2, 3 * max_code // 4, max_code]

    for i in range(n_dac):
        bit_mask = 1 << i
        # PWL: time,val pairs for each test code
        # Times: 0ns, 100ns, 200ns, 300ns, 400ns
        pwl_points = []
        for code_idx, code in enumerate(test_codes):
            t = code_idx * 100
            val = 1.0 if (code & bit_mask) else 0.0
            pwl_points.extend([t, val])

        instances[f"Vdac{i}"] = {
            "dev": "vsource",
            "pins": {"p": f"dac[{i}]", "n": "gnd"},
            "wave": "pwl",
            "points": pwl_points,
        }

    # Add load capacitor on top node
    instances["Cload"] = {
        "dev": "cap",
        "pins": {"p": "top", "n": "gnd"},
        "c": 1,
        "m": 100,  # 100 fF load
    }

    # Add DUT instantiation
    dut_pins = {"top": "top", "vdd": "vdd", "vss": "vss"}
    for i in range(n_dac):
        dut_pins[f"dac[{i}]"] = f"dac[{i}]"

    instances["Xdut"] = {"cell": "cdac", "pins": dut_pins}

    return ports, instances


# Helper functions


# ========================================================================
# Helper Functions
# ========================================================================


def calc_driver_strength(c: int, m: int) -> int:
    """
    Calculate driver width based on capacitor parameters.

    Args:
        c: Capacitance value (unitless)
        m: Multiplier (number of instances)

    Returns:
        Driver width in minimum units
    """
    # Total capacitance = c * m
    # Driver width proportional to sqrt(total capacitance)
    total_cap = c * m
    return max(1, int(math.sqrt(total_cap)))
