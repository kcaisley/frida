import math
from typing import Any


def calc_weights(n_dac: int, n_extra: int, strategy: str) -> list[int]:
    """
    Calculate capacitor weights for CDAC.

    Args:

        n_extra: Number of extra physical capacitors for redundancy
        strategy: 'radix2', 'subradix2_unbounded', 'subradix2_normalized',
                  'subradix2_redist', 'radix2_repeat'

    Returns:
        List of (n_dac + n_extra) integer weights (in units of Cu)
    """
    m_caps = n_dac + n_extra

    if strategy == "radix2":
        # Standard binary weighting: [2^(n-1), 2^(n-2), ..., 2, 1]
        # Pad with unit caps if n_extra > 0
        weights = [2**i for i in range(n_dac - 1, -1, -1)]
        if n_extra > 0:
            weights.extend([1] * n_extra)
        return weights

    elif strategy == "subradix2_unbounded":
        # Each bit is equal to radix^bit up to bit M-1, where radix = 2^(N/M)
        # Round to nearest integer (not floor like normalized)
        radix = 2 ** (n_dac / m_caps)
        weights = [round(radix ** (m_caps - 1 - i)) for i in range(m_caps)]
        return weights

    elif strategy == "subradix2_normalized":
        # Sub-radix-2 with unit quantization
        # Radix < 2 provides redundancy for error correction
        radix = 2 ** (n_dac / m_caps)
        weights = [max(1, int(radix ** (m_caps - 1 - i))) for i in range(m_caps)]
        return weights

    elif strategy == "subradix2_redist":
        # Binary with MSB redistribution for redundancy
        # Split 2^n_redist from MSB and redistribute as pairs
        # TODO: This logic is broken for small n_dac with large n_extra (e.g., n_dac=7, n_extra=6)
        # The MSB weight becomes negative, which is invalid for physical capacitors
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]

        # Check if MSB would become negative - skip invalid combinations
        if weights[0] < 2**n_redist:
            raise ValueError(f"subradix2_redist: n_dac={n_dac} too small for n_extra={n_extra}. MSB weight would be negative.")

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

    elif strategy == "radix2_repeat":
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
        raise ValueError(f"Unknown strategy: {strategy}")


def generate_topology(weights: list[int], redun_strat: str, split_strat: str, n_dac: int, n_extra: int) -> dict[str, Any]:
    """
    Generate physical CDAC topology for a given partition scheme.

    Args:
        weights: List of integer weights from calc_weights
        redun_strat: Weighting strategy (radix2, subradix2_*, etc.)
        split_strat: 'no_split', 'vdiv_split', or 'diffcap_split'
        n_dac: DAC resolution (number of bits)
        n_extra: Number of extra physical capacitors for redundancy

    Returns:
        dict with 'subckt', 'ports', 'devices', 'meta'
    """
    threshold = 64  # Split threshold (unitless)

    # Initialize topology components
    devices = {}
    ports = {"top": "B", "vdd": "B", "vss": "B"}

    # Generate resistor ladder for vdiv_split (all 64 taps)
    if split_strat == "vdiv_split":
        for i in range(64):
            if i == 0:
                devices[f"R{i}"] = {"dev": "res", "pins": {"p": "vdd", "n": f"tap[{i + 1}]"}, "r": 4}
            elif i == 63:
                devices[f"R{i}"] = {"dev": "res", "pins": {"p": f"tap[{i}]", "n": "vss"}, "r": 4}
            else:
                devices[f"R{i}"] = {"dev": "res", "pins": {"p": f"tap[{i}]", "n": f"tap[{i + 1}]"}, "r": 4}

    # UNIFIED STAGE LOOP - Process all weights regardless of magnitude
    for idx, w in enumerate(weights):
        ports[f"dac[{idx}]"] = "I"

        # First inverter (predriver - always unit sized)
        devices[f"MPbuf{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"}, "w": 1}
        devices[f"MNbuf{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

        if split_strat == "no_split":
            # No Split: c=1 (unit cap), m=weight (multiple instances)
            driver_w = calc_driver_strength(c=1, m=w)
            devices[f"MPdrv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
            devices[f"MNdrv{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
            devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": 1, "m": w}

        elif split_strat == "vdiv_split":
            # Voltage Divider Split: Decompose weight into coarse + fine parts
            quotient = w // threshold  # Integer division
            remainder = w % threshold   # Modulo

            if quotient > 0:
                # Main capacitor: m=quotient, c=threshold
                driver_w = calc_driver_strength(c=threshold, m=quotient)
                devices[f"MPdrv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
                devices[f"MNdrv{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
                devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": threshold, "m": quotient}

            if remainder > 0:
                # Fine capacitor: m=1, c=1, driven with reduced voltage from resistor tap
                tap_node = f"tap[{remainder}]"
                driver_w_rdiv = calc_driver_strength(c=1, m=1)
                devices[f"MPrdiv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot_rdiv[{idx}]", "g": f"inter[{idx}]", "s": tap_node, "b": tap_node}, "w": driver_w_rdiv}
                devices[f"MNrdiv{idx}"] = {"dev": "nmos", "pins": {"d": f"bot_rdiv[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w_rdiv}
                devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot_rdiv[{idx}]"}, "c": 1, "m": 1}

        elif split_strat == "diffcap_split":
            # Difference Capacitor Split: Decompose weight into coarse + fine parts
            quotient = w // threshold
            remainder = w % threshold

            if quotient > 0:
                # Main coarse cap: m=quotient, c=threshold
                driver_w = calc_driver_strength(c=threshold, m=quotient)
                devices[f"MPdrv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
                devices[f"MNdrv{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
                devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": threshold, "m": quotient}

                # Diff coarse cap: m=quotient, c=1, driven from intermediate node
                devices[f"Cdiff{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": 1, "m": quotient}

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
                    devices[f"MPdrv{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
                    devices[f"MNdrv{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
                    devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": c_main, "m": 1}
                    devices[f"Cdiff{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": c_diff, "m": 1}
                else:
                    # Coarse part exists, add separate fine caps with different naming
                    devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": c_main, "m": 1}
                    devices[f"Cdiff{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": c_diff, "m": 1}

    # Build final topology
    topology = {
        "subckt": "cdac",
        "ports": ports,
        "devices": devices,
        "meta": {
            "n_dac": n_dac,
            "n_extra": n_extra,
            "m_caps": len(weights),
            "redun_strat": redun_strat,
            "split_strat": split_strat,
            "weights": weights,
            "threshold": threshold,
        },
    }

    return topology


def subcircuit() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """
    Generate CDAC topologies for all N/M/strategy/partition combinations.

    Sweeps:
        n_dac: DAC resolution (7, 9, 11, 13)
        n_extra: Number of extra physical capacitors (0 for radix2, 2/4/6 for others)
        redun_strat: Weight distribution
            - radix2: n_extra = 0 only (4 combinations)
            - subradix2_unbounded, subradix2_normalized, subradix2_redist, radix2_repeat:
              n_extra = 2, 4, 6 (48 combinations)
        split_strat: Physical implementation ('no_split', 'vdiv_split', 'diffcap_split')
        m: Capacitance multiplier (1, 2, 3) - swept in sweep section

    Returns:
        List of (topology, sweep) tuples (52 × 3 = 156 total base configs, swept over m)
    """
    # Sweep parameters
    n_dac_list = [7, 9, 11, 13]
    n_extra_list = [0, 2, 4, 6]
    redun_strat_list = ["radix2", "subradix2_redist", "subradix2_normalized", "subradix2_unbounded", "radix2_repeat"]
    split_strat_list = ["no_split", "vdiv_split", "diffcap_split"]

    # Generate all base configurations (without scale sweep in topology generation)
    all_configurations = []

    for n_dac in n_dac_list:
        for n_extra in n_extra_list:
            for redun_strat in redun_strat_list:
                # Skip invalid combinations: radix2 only works with n_extra=0, others only with n_extra>0
                if redun_strat == "radix2" and n_extra != 0:
                    continue
                if redun_strat != "radix2" and n_extra == 0:
                    continue

                # Calculate weights for this configuration
                try:
                    weights = calc_weights(n_dac, n_extra, redun_strat)
                except ValueError:
                    # Skip combinations that produce invalid weights (e.g., negative)
                    continue

                # Generate all split strategy combinations
                for split_strat in split_strat_list:
                    # Generate topology (no scale parameter - handled via cap type sweep)
                    topology = generate_topology(
                        weights, redun_strat, split_strat, n_dac=n_dac, n_extra=n_extra
                    )

                    # Technology sweep with cap type (momcap with 1m, 2m, 3m metal layers)
                    sweep = {
                        "tech": ["tsmc65", "tsmc28", "tower180"],
                        "globals": {
                            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                            "cap": {"type": ["momcap_1m", "momcap_2m", "momcap_3m"]},
                            "res": {"type": "polyres", "r": 4}
                        },
                    }
                    all_configurations.append((topology, sweep))

    return all_configurations


def testbench() -> dict[str, Any]:
    """
    Generate testbench for CDAC characterization.

    Creates a testbench with:
    - DUT instantiation (generic, works with any CDAC configuration)
    - DAC input bit sources (PWL waveforms to sweep through codes)
    - Load capacitor on output
    - Transient analysis to measure DAC linearity
    """
    # Generate DAC input bit sources
    # Use PWL to sweep through DAC codes: 0, 1/4, 1/2, 3/4, full scale
    n_bits = 11  # Generic testbench for typical 11-bit DAC
    devices = {
        "Vvdd": {"dev": "vsource", "pins": {"p": "vdd", "n": "gnd"}, "wave": "dc", "dc": 1.0},
        "Vvss": {"dev": "vsource", "pins": {"p": "vss", "n": "gnd"}, "wave": "dc", "dc": 0.0},
    }

    # Add DAC bit sources - sweep through key codes
    # Code sequence: 0 -> 256 -> 512 -> 768 -> 1024 (for 11-bit)
    for i in range(n_bits):
        bit_mask = 1 << i
        # PWL: time,val pairs for codes: 0, 256, 512, 768, 1024
        # Times: 0ns, 100ns, 200ns, 300ns, 400ns
        pwl_points = []
        for code_idx, code in enumerate([0, 256, 512, 768, 1024]):
            t = code_idx * 100
            val = 1.0 if (code & bit_mask) else 0.0
            pwl_points.extend([t, val])

        devices[f"Vdac{i}"] = {
            "dev": "vsource",
            "pins": {"p": f"dac[{i}]", "n": "gnd"},
            "wave": "pwl",
            "points": pwl_points
        }

    # Add load capacitor on top node
    devices["Cload"] = {
        "dev": "cap",
        "pins": {"p": "top", "n": "gnd"},
        "c": 1,
        "m": 100  # 100 fF load
    }

    # Add DUT instantiation - generic, will match any cdac subcircuit
    dut_pins = {"top": "top", "vdd": "vdd", "vss": "vss"}
    for i in range(n_bits):
        dut_pins[f"dac[{i}]"] = f"dac[{i}]"

    devices["Xdut"] = {"dev": "cdac", "pins": dut_pins}

    topology = {
        "testbench": "tb_cdac_topbss",
        "devices": devices,
        "analyses": {
            "tran1": {
                "type": "tran",
                "stop": 500,  # 500 time units
                "step": 0.1
            }
        }
    }

    return topology


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
