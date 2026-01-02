"""
Capacitor DAC (CDAC) generator for SAR ADC.

Generates capacitor arrays with different bit resolutions, physical cap counts,
and weighting strategies. The topology varies with m_caps (number of physical
capacitors), so this generates multiple configurations.
"""

import math


def subcircuit():
    """
    Generate CDAC topologies for all N/M/strategy combinations.

    Sweeps:
        n_bits: DAC resolution (7, 9, 11, 13)
        m_caps: Number of physical capacitors (9, 11, 13, 15)
        strategy: Weight distribution ('binary', 'split_msb', 'subradix2')

    Returns:
        List of (topology, sweep) tuples, one per configuration (4 x 4 x 3 = 48 total)
    """

    def calc_weights(n_bits, m_caps, strategy):
        """
        Calculate capacitor weights for CDAC.

        Args:
            n_bits: DAC resolution in bits
            m_caps: Number of physical capacitors (> n_bits for redundancy)
            strategy: 'binary', 'split_msb', 'subradix2'

        Returns:
            List of m_caps integer weights (in units of Cu)
        """
        if strategy == 'binary':
            # Standard binary weighting: [2^(n-1), 2^(n-2), ..., 2, 1]
            # Pad with unit caps if m_caps > n_bits
            weights = [2**i for i in range(n_bits - 1, -1, -1)]
            if m_caps > n_bits:
                weights.extend([1] * (m_caps - n_bits))
            return weights

        elif strategy == 'split_msb':
            # Binary with MSB redistribution for redundancy
            # Split 2^n_redist from MSB and redistribute as pairs
            n_redist = m_caps - n_bits + 2  # Extra caps determine redistribution

            # Base binary weights
            weights = [2**i for i in range(n_bits - 1, -1, -1)]
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

        elif strategy == 'subradix2':
            # Sub-radix-2 with unit quantization
            # Radix < 2 provides redundancy for error correction
            radix = 2 ** (n_bits / m_caps)
            weights = [max(1, int(radix**(m_caps - 1 - i))) for i in range(m_caps)]
            return weights

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    # Sweep parameters
    n_bits_list = [7, 9, 11, 13]
    m_caps_list = [9, 11, 13, 15]  # m_caps > n_bits for redundancy
    strategies = ['binary', 'split_msb', 'subradix2']

    # Generate all 48 configurations
    configurations = []

    for n_bits in n_bits_list:
        for m_caps in m_caps_list:
            for strategy in strategies:

                # Calculate weights for this configuration
                weights = calc_weights(n_bits, m_caps, strategy)

                # Build ports: top plate + m_caps bottom plates + supplies
                ports = {'top': 'B', 'vdd': 'B', 'vss': 'B'}
                for i in range(m_caps):
                    ports[f'bot[{i}]'] = 'I'

                # Build devices: m_caps capacitors
                devices = {}
                for i, w in enumerate(weights):
                    devices[f'C{i}'] = {
                        'dev': 'mom_cap',
                        'pins': {'p': 'top', 'n': f'bot[{i}]'},
                        'weight': w,
                    }

                topology = {
                    'subckt': f'cdac_{n_bits}b_{m_caps}c_{strategy}',
                    'ports': ports,
                    'devices': devices,
                    'meta': {
                        'n_bits': n_bits,
                        'm_caps': m_caps,
                        'strategy': strategy,
                        'weights': weights,
                        'total_weight': sum(weights),
                    }
                }

                sweep = {
                    'tech': ['tsmc65', 'tsmc28', 'tower180'],
                }

                configurations.append((topology, sweep))

    return configurations


def testbench():
    """CDAC testbench for DNL/INL characterization."""

    topology = {
        'testbench': 'tb_cdac',
        'devices': {
            'Vvdd': {'dev': 'vsource', 'pins': {'p': 'vdd', 'n': 'gnd'}, 'wave': 'dc', 'dc': 1.0},
            'Vvss': {'dev': 'vsource', 'pins': {'p': 'vss', 'n': 'gnd'}, 'wave': 'dc', 'dc': 0.0},
        },
        'analyses': {
            'mc1': {
                'type': 'montecarlo',
                'numruns': 100,
                'seed': 12345,
                'variations': 'all'
            },
        }
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
        remaining = sum(weights[i+1:])
        radix = w / weights[i+1] if weights[i+1] > 0 else 0
        print(f"{i:<5}{w:<9}{remaining:<11}{radix:<.2f}")
    print(f"{len(weights)-1:<5}{weights[-1]:<9}{'--':<11}{'--'}")

    return partitioned


if __name__ == '__main__':
    configs = subcircuit()
    print(f"Generated {len(configs)} configurations\n")

    # Print examples for each strategy
    for strategy in ['binary', 'split_msb', 'subradix2']:
        print(f"=== {strategy.upper()} ===")
        for topo, _ in configs:
            meta = topo['meta']
            if meta['strategy'] == strategy and meta['n_bits'] == 11:
                print(f"{topo['subckt']}:")
                print(f"  weights = {meta['weights']}")
                print(f"  sum = {meta['total_weight']}")
        print()
