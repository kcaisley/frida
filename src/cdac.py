import math

def partition_weights(weights, coarse_weight):
    """
    Splits each weight into chunks of unary_weight, with a possible remainder at the end.
    Returns a list of lists.
    """
    result = []
    for w in weights:
        chunks = [coarse_weight] * (w // coarse_weight)
        remainder = w % coarse_weight
        if remainder > 0:
            chunks.append(remainder)
        result.append(chunks)
    return result

def generate_weights(n_dac, n_redist, w_regroup, w_offset):
    """
    Generates DAC weights with redundancy, which also satify some nice properties like:
    - Weights are all integers
    - Sum total of weights is still 2**Ndac
    - Each weight is eath a power of 2, or a sum or difference between two powers of 2
    - Effective radix along the chain is relatively consistent, i.e. avoiding 'peaks' in remaining redundancy

    Args:
        n_dac (int): DAC resolution in bits 
        n_redist (int): 2*n_redist bit weights split off MSB and redistributed, expressed as integer  bits (must be at least 2 less than n_dac).
        w_regroup (list of int): Regroup positions, each integer from n_redist-2 down to 0.
        w_offset (int): Offset for redundant weights in the output array.

    Returns:
        weights (list): of final calculated weights
    """

    # Generate basic weights w_base as powers of 2, from n_dac-1 down to 0
    w_base = [2**w for w in range(n_dac-1, -1, -1)]

    # Next break off 2**n_redist bits from MSB weight for redistribtuion
    w_base[0] -= 2**n_redist

    # Create w_redun as a list of weights broken into pairs of equal powers of two, descending
    w_redun = [2**i for i in range(n_redist - 2, -1, -1) for _ in range(2)]
    w_redun += [2**0, 2**0]   # Add [1,1] weights at end of array to ensure sum is 2**n_redist
    
    # Next, optionally recombine pairs in w_redun array at positions w_regroup, to compact it
    # Iterate through w_regroup in reverse order to avoid index shifting issues
    # TODO: update this so that the w_regroup points at 2**x values, rather than list indices
    for regroup_pair in sorted(w_regroup, reverse=True):
        w_redun[(2 * regroup_pair)] *= 2
        w_redun.pop(2 * regroup_pair + 1)

    weights = [0] * (len(w_redun) + w_offset)
    
    # Add base weights
    for i in range(len(w_base)):
        weights[i] += w_base[i]
        
    # Add redundant weights with offset
    for i in range(len(w_redun)):
        weights[i + w_offset] += w_redun[i]
    
    return weights, w_base, w_redun


def analyze_weights(weights, coarse_weight):
    """
    Gives analysis of weights for where the main scaling structure ends and where fine adjustments (such as capacitor differences, Vref scaling with a resistive divider, or bridge capacitor scaling) begin. The output includes partitioned weights, ratios, and various metrics annotated for design insight. 
    This function calculates and displays key metrics including the unit capacitor size (defining the transition from coarse to fine scaling), effective radix between weights, and the percentage of remaining redundancy.
    """
    # Print the list of weights
    print("Weights:", weights)
    # Print the ratio of each weight to the coarse_weight (unit size)
    print("Weight ratios:", [w / coarse_weight for w in weights])

    # Partition each weight into chunks of coarse_weight, with possible remainder
    partitioned_weights = partition_weights(weights, coarse_weight)
    print("Partitioned weights:", partitioned_weights)
    # Print the total number of unit capacitors needed
    print(f"Unit count: {sum([math.ceil(w / coarse_weight) for w in weights])}")
    # Print the sum of all weights
    print(f"Sum: {sum(weights)}")
    # Print the number of weights
    print(f"Length: {len(weights)}")

    # Calculate various metrics for each bit position
    remaining = []  # Remaining total weight after each bit
    method4 = []    # Difference between remaining and current weight
    radix = []      # Ratio of current weight to next weight (effective radix)
    bit = list(range(len(weights)))  # Bit indices

    # Loop through all but the last weight to compute metrics
    for i, cap in enumerate(weights[:-1]):
        remain = sum(weights[i+1:])  # Total weight remaining after this bit
        remaining.append(remain)
        method4.append(remain - weights[i])  # Difference between remaining and current
        radix.append(weights[i] / weights[i+1])  # Effective radix between this and next

    # Print a table of bit index, weight, method4, and radix
    print("\nBit  Weight   Method4  Radix")
    print("-" * 32)
    for a, b, c, d in zip(bit, weights, method4 + [0], radix + [0]):
        print(f"{a:<8} {b:<8} {c:<8.1f} {d:<8.1f}")

    # Return the partitioned weights for further use
    return partitioned_weights