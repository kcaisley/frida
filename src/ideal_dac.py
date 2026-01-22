import os
import matplotlib.pyplot as plt
import itertools

os.environ["XDG_SESSION_TYPE"] = "xcb"  # this silences the display Wayland error

bits = 8
mapped_bits = 8
radix = 1.7

# produces a list of lists with binary codes. For 8 bit example [[0, 0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0, 0]....
binary_list = [
    [1 if digit & (1 << j) else 0 for j in range(bits)] for digit in range(2**bits)
]  # a list of lists of ints
weights = [radix**i for i in range(bits)]
vout = [
    sum((2 * binary_list[k][i] - 1) * weight for i, weight in enumerate(weights))
    for k in range(2**bits)
]

# We want the output DAC values to be sorted by magnitude, and we want to have an their associated binary codes.
# Zips vout and binary_list together.
# Sorts the pairs based on the first element of each tuple (vout value).
# Unzips the sorted pairs back into vout and binary_list.
# Converts the vout and binary_list from tuples back into lists.
vout_sorted, binary_list_sorted = zip(
    *sorted(zip(vout, binary_list), key=lambda x: x[0])
)
vout_sorted, binary_list_sorted = list(vout_sorted), list(binary_list_sorted)

# Assuming vout and vout_sorted are already defined and have 2**bits values
indices = range(len(vout))

# Normalize values to between 0 to 1, value is a value in vout array (not an index)
vout_norm = [(value - vout[0]) / (vout[2**bits - 1] - vout[0]) for value in vout]
vout_sorted_norm = [
    (value - vout_sorted[0]) / (vout_sorted[2**bits - 1] - vout_sorted[0])
    for value in vout_sorted
]

# Here we calculate the DNL, normalized against the ideal uniform bin size of a {bits} bit ideal binary ADC
vout_sorted_norm_dnl_ideal = [
    ((vout_sorted_norm[index + 1] - vout_sorted_norm[index]) - 1 / (2**bits - 1))
    / (1 / (2**bits - 1))
    for index, value in itertools.islice(
        enumerate(vout_sorted_norm), len(vout_sorted_norm) - 1
    )
]

fig, (ax0, ax1) = plt.subplots(nrows=2, ncols=1)

ax0.step(indices, vout_norm, label="In sequence", color="cyan")
ax0.step(indices, vout_sorted_norm, label="Sorted by sum", color="green")
ax0.set_xlabel("Din")
ax0.set_ylabel("Vout")
ax0.set_title(f"DAC Vout and Vout vs Din (radix = {radix}, bits = {bits})")
ax0.grid(True)
ax0.legend()

# Vout becomes Vin, as it's being used in an ADC
ax1.step(vout_norm, indices, label="In sequence", color="cyan")
ax1.step(vout_sorted_norm, indices, label="Sorted by sum", color="green")
ax1.set_xlabel("Vin")
ax1.set_ylabel("Dout")
ax1.set_title(f"ADC Dout vs Vin (radix = {radix}, bits = {bits})")
ax1.grid(True)
ax1.legend()

# ax2.step(indices[:-1], vout_sorted_norm_dnl_ideal, color='green')
# ax2.set_xlabel('Dout')
# ax2.set_ylabel(f'DNL [LSB]')
# ax2.set_title(f'DNL of Dout sorted (radix = {radix}, bits = {bits})')
# ax2.grid(True)

plt.subplots_adjust()
# plt.legend()
plt.show()

# plt.figure(figsize=(8, 6), dpi=100)
# plt.savefig(f'./vout_{bits}bits_{radix}radix.png')
