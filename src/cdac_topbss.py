"""
Capacitor DAC (CDAC) generator for SAR ADC.

Generates capacitor arrays with different bit resolutions, physical cap counts,
and weighting strategies. The topology varies with m_caps (number of physical
capacitors), so this generates multiple configurations.
"""

import math


def calc_weights(n_dac, n_extra, strategy):
    """
    Calculate capacitor weights for CDAC.

    Args:
        n_dac: DAC resolution in bits
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


def subcircuit():
    """
    Generate CDAC topologies for all N/M/strategy combinations.

    Sweeps:
        n_dac: DAC resolution (7, 9, 11, 13)
        n_extra: Number of extra physical capacitors (0 for radix2, 2/4/6 for others)
        strategy: Weight distribution
            - radix2: n_extra = 0 only (4 combinations)
            - subradix2_unbounded, subradix2_normalized, subradix2_redist, radix2_repeat:
              n_extra = 2, 4, 6 (48 combinations)


    Returns:
        List of (topology, sweep) tuples, one per configuration (52 total)
    """
    # Sweep parameters
    n_dac_list = [7, 9, 11, 13]

    # Generate all configurations
    configurations = []

    # First: radix2 with n_extra = 0 (4 combinations)
    for n_dac in n_dac_list:
        n_extra = 0
        strategy = "radix2"
        weights = calc_weights(n_dac, n_extra, strategy)
        m_caps = n_dac + n_extra

        # Build ports: top plate + m_caps bottom plates + supplies
        ports = {"top": "B", "vdd": "B", "vss": "B"}
        for i in range(m_caps):
            ports[f"bot[{i}]"] = "I"

        # Build devices: m_caps capacitors
        devices = {}
        for i, w in enumerate(weights):
            devices[f"C{i}"] = {
                "dev": "mom_cap",
                "pins": {"p": "top", "n": f"bot[{i}]"},
                "weight": w,
            }

        topology = {
            "subckt": f"cdac_{n_dac}bit_{m_caps}cap_{strategy}",
            "ports": ports,
            "devices": devices,
            "meta": {
                "n_dac": n_dac,
                "n_extra": n_extra,
                "m_caps": m_caps,
                "strategy": strategy,
                "weights": weights,
                "total_weight": sum(weights),
            },
        }

        sweep = {
            "tech": ["tsmc65", "tsmc28", "tower180"],
        }

        configurations.append((topology, sweep))

    # Second: other strategies with n_extra > 0 (48 combinations)
    n_extra_list = [2, 4, 6]
    redundant_strategies = [
        "subradix2_redist",
        "subradix2_normalized",
        "subradix2_unbounded",
        "radix2_repeat",
    ]

    for n_dac in n_dac_list:
        for n_extra in n_extra_list:
            for strategy in redundant_strategies:
                # Calculate weights for this configuration
                weights = calc_weights(n_dac, n_extra, strategy)
                m_caps = n_dac + n_extra

                # Build ports: top plate + m_caps bottom plates + supplies
                ports = {"top": "B", "vdd": "B", "vss": "B"}
                for i in range(m_caps):
                    ports[f"bot[{i}]"] = "I"

                # Build devices: m_caps capacitors
                devices = {}
                for i, w in enumerate(weights):
                    devices[f"C{i}"] = {
                        "dev": "mom_cap",
                        "pins": {"p": "top", "n": f"bot[{i}]"},
                        "weight": w,
                    }

                topology = {
                    "subckt": f"cdac_{n_dac}bit_{m_caps}cap_{strategy}",
                    "ports": ports,
                    "devices": devices,
                    "meta": {
                        "n_dac": n_dac,
                        "n_extra": n_extra,
                        "m_caps": m_caps,
                        "strategy": strategy,
                        "weights": weights,
                        "total_weight": sum(weights),
                    },
                }

                sweep = {
                    "tech": ["tsmc65", "tsmc28", "tower180"],
                }

                configurations.append((topology, sweep))

    return configurations


def testbench():
    """CDAC testbench for DNL/INL characterization."""

    topology = {
        "testbench": "tb_cdac",
        "devices": {
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
        },
        "analyses": {
            "mc1": {
                "type": "montecarlo",
                "numruns": 100,
                "seed": 12345,
                "variations": "all",
            },
        },
    }

    return topology


# Utility functions for weight analysis


def partition_weights(weights, coarse_weight):
    """Split each weight into chunks of coarse_weight with remainder."""
    result = []
    for w in weights:
        chunks = [coarse_weight] * (w // coarse_weight)
        remainder = w % coarse_weight
        if remainder > 0:
            chunks.append(remainder)
        result.append(chunks)
    return result


def analyze_weights(weights, coarse_weight):
    """Print analysis of weight distribution and redundancy."""
    print("Weights:", weights)
    print("Weight ratios:", [w / coarse_weight for w in weights])

    partitioned = partition_weights(weights, coarse_weight)
    print("Partitioned:", partitioned)
    print(f"Unit count: {sum(math.ceil(w / coarse_weight) for w in weights)}")
    print(f"Sum: {sum(weights)}, Length: {len(weights)}")

    print("\nBit  Weight   Remaining  Radix")
    print("-" * 36)
    for i, w in enumerate(weights[:-1]):
        remaining = sum(weights[i + 1 :])
        radix = w / weights[i + 1] if weights[i + 1] > 0 else 0
        print(f"{i:<5}{w:<9}{remaining:<11}{radix:<.2f}")
    print(f"{len(weights) - 1:<5}{weights[-1]:<9}{'--':<11}{'--'}")

    return partitioned


if __name__ == "__main__":
    configs = subcircuit()
    print(f"Generated {len(configs)} configurations\n")

    # Print all configurations in order
    for topo, sweep in configs:
        meta = topo["meta"]
        print(f"{topo['subckt']}:")
        print(
            f"  strategy={meta['strategy']}, n_dac={meta['n_dac']}, n_extra={meta['n_extra']}, m_caps={meta['m_caps']}"
        )
        print(f"  weights = {meta['weights']}")
        print(f"  sum = {meta['total_weight']}")
        print()
