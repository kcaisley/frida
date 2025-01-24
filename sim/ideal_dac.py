import matplotlib.pyplot as plt

bits = 9
radix = 1.8

# produces a list of lists with binary codes. For 8 bit example [[0, 0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0, 0]....
binary_list = [[1 if digit & (1 << j) else 0 for j in range(bits)] for digit in range(2**bits)]
weights = [radix**i for i in range(bits)]
dout = [sum((2*binary_list[k][i]-1) * weight for i, weight in enumerate(weights)) for k in range(2**bits)]

# We want the output DAC values to be sorted by magnitude, and we want to have an their associated binary codes.
# Zips dout and binary_list together.
# Sorts the pairs based on the first element of each tuple (dout value).
# Unzips the sorted pairs back into dout and binary_list.
# Converts the dout and binary_list from tuples back into lists.
dout_sorted, binary_list_sorted = zip(*sorted(zip(dout, binary_list), key=lambda x: x[0]))
dout_sorted, binary_list_sorted = list(dout_sorted), list(binary_list_sorted)
print(dout_sorted)
print(binary_list_sorted)

# Assuming dout and dout_sorted are already defined and have 2**bits values
indices = range(len(dout))

plt.step(indices, dout, label='dout', color='blue')
plt.step(indices, dout_sorted, label='dout_sorted', color='red')

plt.xlabel('Index')
plt.ylabel('Value')
plt.title(f'Comparison of dout and dout_sorted (radix = {radix}, bits = {bits})')
plt.legend()

plt.show()
