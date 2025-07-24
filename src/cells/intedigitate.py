def interdigitate_indices(partitioned_weights):
    # Number of effective capacitors
    n_caps = len(partitioned_weights)
    # Number of unit capacitors (total positions)
    total_units = sum(len(sublist) for sublist in partitioned_weights)
    # Track the next sub_idx to use for each main_idx
    sub_indices = [0] * n_caps
    # Output: list of lists, each with (main_idx, sub_idx)
    result = []
    # Continue until all units are placed
    placed = 0
    while placed < total_units:
        this_round = []
        for main_idx, sublist in enumerate(partitioned_weights):
            sub_idx = sub_indices[main_idx]
            if sub_idx < len(sublist):
                this_round.append((main_idx, sub_idx))
                sub_indices[main_idx] += 1
                placed += 1
        if this_round:
            result.append(this_round)
    return result

# Example usage:
partitioned_weights = [
    [64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64],
    [64, 64, 64, 64, 64, 64, 64, 64],
    [64, 64, 64, 64, 64],
    [64, 64, 64],
    [64, 32],
    [64],
    [32],
    [24],
    [12],
    [10],
    [5],
    [4],
    [4],
    [2],
    [1],
    [1]
]

interdigitated = interdigitate_indices(partitioned_weights)
print(interdigitated)