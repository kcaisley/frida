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
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]
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


def generate_topology(base_name: str, weights: list[int], redun_strat: str, split_strat: str, scale: int) -> dict[str, Any]:
    """
    Generate physical CDAC topology for a given partition scheme.

    Args:
        base_name: Base subcircuit name
        weights: List of integer weights from calc_weights
        strategy: Weighting strategy (radix2, subradix2_*, etc.)
        split_strat: 'no_split', 'vdiv_split', or 'diffcap_split'
        scale: Capacitance scale factor (1, 2, or 3)

    Returns:
        dict with 'subckt', 'ports', 'devices', 'meta'
    """
    # Scale all weights by the scale factor
    scaled_weights = [w * scale for w in weights]
    threshold = 64 * scale  # Coarse/fine split threshold

    # Split indices into coarse (w > threshold) and fine (w ≤ threshold)
    coarse_indices = [i for i, w in enumerate(scaled_weights) if w > threshold]
    fine_indices = [i for i, w in enumerate(scaled_weights) if w <= threshold]

    # Initialize topology components
    devices = {}
    ports = {"top": "B", "vdd": "B", "vss": "B"}

    # ================================================================
    # COARSE SECTION (common to all split strategies)
    # Topology: dac[i] → INV1(w=1) → inter[i] → INV2(w=scaled) → bot[i] → Cap
    # ================================================================
    for idx in coarse_indices:
        w = scaled_weights[idx]
        driver_w = calc_driver_width(w)
        ports[f"dac[{idx}]"] = "I"

        # First inverter (w=1)
        devices[f"MP1_{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"}, "w": 1}
        devices[f"MN1_{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

        # Second inverter (w=scaled)
        devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
        devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}

        # Capacitor (weight stored, actual value mapped in technology step)
        devices[f"C{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": w, "m": 1}

    # ================================================================
    # FINE SECTION (split_strat-specific implementations)
    # ================================================================

    if split_strat == "no_split":
        # No Split: Same structure as coarse section for all weights
        # Topology: dac[i] → INV1(w=1) → inter[i] → INV2(w=scaled) → bot[i] → Cap
        for idx in fine_indices:
            w = scaled_weights[idx]
            driver_w = calc_driver_width(w)
            ports[f"dac[{idx}]"] = "I"

            # First inverter
            devices[f"MP1_{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"}, "w": 1}
            devices[f"MN1_{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

            # Second inverter
            devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
            devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}

            # Capacitor
            devices[f"C{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": w, "m": 1}

    elif split_strat == "vdiv_split":
        # Resistor Chain: Coarse array + 64-step resistor ladder + unit caps
        # Topology:
        #   Resistor chain: VDD → R → tap[1] → R → tap[2] → ... → tap[63] → R → VSS
        #   Total resistance: 64 × 400Ω = 25.6kΩ (current ~47µA)
        #   Fine caps: all unit-sized (1*scale), inverters tap different voltages

        if fine_indices:
            # Generate 64-step resistor ladder (tap[0] implicitly VDD, tap[64] implicitly VSS)
            for i in range(64):
                if i == 0:
                    devices[f"R{i}"] = {"dev": "res", "pins": {"p": "vdd", "n": f"tap[{i + 1}]"}, "r": 4}
                elif i == 63:
                    devices[f"R{i}"] = {"dev": "res", "pins": {"p": f"tap[{i}]", "n": "vss"}, "r": 4}
                else:
                    devices[f"R{i}"] = {"dev": "res", "pins": {"p": f"tap[{i}]", "n": f"tap[{i + 1}]"}, "r": 4}

            # Fine caps: all unit-sized, inverters use resistor chain taps as VDD
            for tap_idx, idx in enumerate(fine_indices):
                w = scale  # Unit cap
                driver_w = calc_driver_width(w)
                tap_node = f"tap[{tap_idx + 1}]"
                ports[f"dac[{idx}]"] = "I"

                # First inverter (uses chain voltage as VDD)
                devices[f"MP1_{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": tap_node, "b": tap_node}, "w": 1}
                devices[f"MN1_{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

                # Second inverter (uses chain voltage as VDD)
                devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": tap_node, "b": tap_node}, "w": driver_w}
                devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}

                # Unit capacitor
                devices[f"C{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot[{idx}]"}, "c": w, "m": 1}

    elif split_strat == "diffcap_split":
        # Difference Capacitor: Coarse array + difference cap pairs
        # Topology:
        #   dac[i] → INV1(w=1) → inter[i] → INV2(w=scaled) → bot_main[i] → Cmain
        #                          ↓
        #                       bot_diff[i] → Cdiff
        # Capacitance formula (for weight w in fine section):
        #   Cmain = 0.4 * (65 + w) fF
        #   Cdiff = 0.4 * (65 - w) fF
        #   Effective = Cmain - Cdiff = 0.4 * 2w = 0.8w fF

        for idx in fine_indices:
            w = scaled_weights[idx]
            driver_w = calc_driver_width(w)
            c_main = 0.4 * (65 + w)  # fF
            c_diff = 0.4 * (65 - w)  # fF
            ports[f"dac[{idx}]"] = "I"

            # First inverter
            devices[f"MP1_{idx}"] = {"dev": "pmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vdd", "b": "vdd"}, "w": 1}
            devices[f"MN1_{idx}"] = {"dev": "nmos", "pins": {"d": f"inter[{idx}]", "g": f"dac[{idx}]", "s": "vss", "b": "vss"}, "w": 1}

            # Second inverter (drives main cap)
            devices[f"MP2_{idx}"] = {"dev": "pmos", "pins": {"d": f"bot_main[{idx}]", "g": f"inter[{idx}]", "s": "vdd", "b": "vdd"}, "w": driver_w}
            devices[f"MN2_{idx}"] = {"dev": "nmos", "pins": {"d": f"bot_main[{idx}]", "g": f"inter[{idx}]", "s": "vss", "b": "vss"}, "w": driver_w}

            # Main capacitor
            devices[f"Cmain{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"bot_main[{idx}]"}, "c": c_main * 1e-15, "m": 1}

            # Diff capacitor (driven by intermediate node for opposite polarity)
            devices[f"Cdiff{idx}"] = {"dev": "cap", "pins": {"p": "top", "n": f"inter[{idx}]"}, "c": c_diff * 1e-15, "m": 1}

    # Build final topology
    topology = {
        "subckt": f"{base_name}_{split_strat}_{scale}x",
        "ports": ports,
        "devices": devices,
        "meta": {
            "n_dac": len(weights),
            "split_strat": split_strat,
            "scale": scale,
            "redun_strat": redun_strat,
            "weights": weights,
            "scaled_weights": scaled_weights,
            "threshold": threshold,
            "n_coarse": len(coarse_indices),
            "n_fine": len(fine_indices),
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
                weights = calc_weights(n_dac, n_extra, redun_strat)
                m_caps = n_dac + n_extra
                base_name = f"cdac_{n_dac}bit_{m_caps}cap_{redun_strat}"

                # Generate all split strategy combinations
                for split_strat in split_strat_list:
                    # Generate topology with scale=1 as base (will be swept via 'm' parameter)
                    topology = generate_topology(
                        base_name, weights, redun_strat, split_strat, scale=1
                    )

                    # Technology sweep with 'm' parameter for capacitor multiplier
                    sweep = {
                        "tech": ["tsmc65", "tsmc28", "tower180"],
                        "defaults": {
                            "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                            "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
                        },
                        "sweeps": [{"devices": "momcap", "m": [1, 2, 3]}],
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
def calc_driver_width(cap_weight: int) -> int:
    """
    Calculate driver width based on capacitor weight.

    Args:
        cap_weight: Capacitor weight in units of Cu

    Returns:
        Driver width in minimum units
    """
    # Simple scaling: driver width proportional to sqrt(cap_weight)
    # Minimum width is 1
    return max(1, int(math.sqrt(cap_weight)))


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
