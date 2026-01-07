"""
Capacitor DAC (CDAC) generator for SAR ADC.

Generates capacitor arrays with different bit resolutions, physical cap counts,
and weighting strategies. The topology varies with m_caps (number of physical
capacitors), so this generates multiple configurations.

Type Definitions:
-----------------

Topology Dictionary Structure:
    {
        "subckt": str,                    # Subcircuit name
        "ports": dict[str, str],          # Port name -> direction ("I", "O", "B")
        "devices": dict[str, DeviceDict], # Device instances
        "meta": dict[str, Any]            # Metadata about the circuit
    }

DeviceDict Structure:
    For transistors (nmos/pmos):
        {
            "dev": "nmos" | "pmos",
            "pins": {"d": str, "g": str, "s": str, "b": str},
            "w": int,  # Width multiplier
        }
    
    For capacitors:
        {
            "dev": "cap",
            "pins": {"p": str, "n": str},
            "c": int,  # Capacitance weight (integer)
            "m": int   # Multiplier
        }
    
    For resistors:
        {
            "dev": "res",
            "pins": {"p": str, "n": str},
            "r": int   # Resistance multiplier (e.g., 4 = 400 ohms)
        }

Sweep Dictionary Structure:
    {
        "tech": list[str],                # Technology nodes to sweep
        "defaults": {
            "nmos": {"type": str, "w": int, "l": int, "nf": int},
            "pmos": {"type": str, "w": int, "l": int, "nf": int}
        },
        "sweeps": list[dict[str, Any]]    # Parameter sweep specifications
    }

Return from subcircuit():
    list[tuple[dict[str, Any], dict[str, Any]]]
    # List of (topology, sweep) tuples
"""

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

    # ================================================================
    # UNIFIED STAGE LOOP - Process all weights regardless of magnitude
    # ================================================================
    for idx, w in enumerate(weights):
        ports[f"dac[{idx}]"] = "I"

        # First inverter (always unit sized)
        devices[f"MP1_{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"}, "w": 1}
        devices[f"MN1_{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

        if split_strat == "no_split":
            # No Split: c=1 (unit cap), m=weight (multiple instances)
            driver_w = calc_driver_width(c=1, m=w)
            devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
            devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
            devices[f"C{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": 1, "m": w}

        elif split_strat == "vdiv_split":
            # Voltage Divider Split: Decompose weight into coarse + fine parts
            quotient = w // threshold  # Integer division
            remainder = w % threshold   # Modulo

            if quotient > 0:
                # Main capacitor: m=quotient, c=threshold
                driver_w = calc_driver_width(c=threshold, m=quotient)
                devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
                devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}
                devices[f"C{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": threshold, "m": quotient}

            if remainder > 0:
                # Fine capacitor: m=1, c=1, driven with reduced voltage from resistor tap
                tap_node = f"tap[{remainder}]"
                driver_w_fine = calc_driver_width(c=1, m=1)
                devices[f"MP2_{idx}_fine"] = {"dev": "pmos", "pins": {"d": f"bot_fine[{idx}]", "g": f"inter[{idx}]", "s": tap_node, "b": tap_node}, "w": driver_w_fine}
                devices[f"MN2_{idx}_fine"] = {"dev": "nmos", "pins": {"d": f"bot_fine[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w_fine}
                devices[f"C{idx}_fine"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot_fine[{idx}]"}, "c": 1, "m": 1}

        elif split_strat == "diffcap_split":
            # Difference Capacitor Split: Decompose weight into coarse + fine parts
            quotient = w // threshold
            remainder = w % threshold

            if quotient > 0:
                # Main coarse cap: m=quotient, c=threshold
                driver_w_main = calc_driver_width(c=threshold, m=quotient)
                devices[f"MP2_{idx}_main"] = {"dev": "pmos", "pins": {"d": f"bot_main[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w_main}
                devices[f"MN2_{idx}_main"] = {"dev": "nmos", "pins": {"d": f"bot_main[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w_main}
                devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot_main[{idx}]"}, "c": threshold, "m": quotient}
                
                # Diff coarse cap: m=quotient, c=1, driven from intermediate node
                devices[f"Cdiff{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": 1, "m": quotient}

            if remainder > 0:
                # Main fine cap: m=1, c=(threshold+1+remainder)
                c_main_fine = threshold + 1 + remainder
                driver_w_main_fine = calc_driver_width(c=c_main_fine, m=1)
                devices[f"MP2_{idx}_main_fine"] = {"dev": "pmos", "pins": {"d": f"bot_main_fine[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w_main_fine}
                devices[f"MN2_{idx}_main_fine"] = {"dev": "nmos", "pins": {"d": f"bot_main_fine[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w_main_fine}
                devices[f"Cmain{idx}_fine"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot_main_fine[{idx}]"}, "c": c_main_fine, "m": 1}
                
                # Diff fine cap: m=1, c=(threshold+1-remainder), driven from intermediate node
                c_diff_fine = threshold + 1 - remainder
                devices[f"Cdiff{idx}_fine"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": c_diff_fine, "m": 1}

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

                    # Technology sweep with cap type (1m, 2m, 3m layers)
                    sweep = {
                        "tech": ["tsmc65", "tsmc28", "tower180"],
                        "defaults": {
                            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                            "cap": {"dev": "momcap"},
                            "res": {"dev": "polyres", "r": 4}
                        },
                        "sweeps": [{"devices": "cap", "type": ["1m", "2m", "3m"]}],
                    }
                    all_configurations.append((topology, sweep))

    return all_configurations


def testbench() -> dict[str, Any]:
    """
    Generate testbench for CDAC characterization.

    TODO: Add proper testbench topology
    """
    topology = {
        "testbench": "tb_cdac_topbss",
        "devices": {
            "Vvdd": {"dev": "vsource", "pins": {"p": "vdd", "n": "gnd"}, "wave": "dc", "dc": 1.0},
            "Vvss": {"dev": "vsource", "pins": {"p": "vss", "n": "gnd"}, "wave": "dc", "dc": 0.0},
        },
    }

    return topology


# Helper functions
def calc_driver_width(c: int, m: int) -> int:
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


def partition_weights(weights: list[int], threshold: int) -> tuple[list[int], list[int]]:
    """
    Partition weights into coarse and fine sections.

    Args:
        weights: List of capacitor weights
        threshold: Split threshold (weights > threshold are coarse)

    Returns:
        (coarse_indices, fine_indices)
    """
    coarse = [i for i, w in enumerate(weights) if w > threshold]
    fine = [i for i, w in enumerate(weights) if w <= threshold]
    return coarse, fine


def analyze_weights(weights: list[int]) -> dict[str, int]:
    """
    Analyze weight distribution for debugging.

    Args:
        weights: List of capacitor weights

    Returns:
        Dict with statistics
    """
    return {
        "count": len(weights),
        "min": min(weights),
        "max": max(weights),
        "sum": sum(weights),
        "unique": len(set(weights)),
    }
