binary_list = [[1 if digit & (1 << j) else 0 for j in range(8)] for digit in range(256)]
weights = [1.8**i for i in range(8)]
dout = [sum((2*binary_list[k][i]-1) * weight for i, weight in enumerate(weights)) for k in range(256)]

# more verbose
# dout = []
# for k in range(256):
#     sum_value = 0
#     for i, weight in enumerate(weights):
#         bit = binary_list[k][i]
#         print(bit)
#         sum_value += (2*bit - 1) * weight # converts 0 to -1, 1 to 1
#     dout.append(sum_value)

print(binary_list)
print(dout)

print("okay, sorting now....")
# Zips dout and binary_list together.
# Sorts the pairs based on the first element of each tuple (dout value).
# Unzips the sorted pairs back into dout and binary_list.
# Converts the dout and binary_list from tuples back into lists.
dout_sorted, binary_list_sorted = zip(*sorted(zip(dout, binary_list), key=lambda x: x[0]))
dout_sorted, binary_list_sorted = list(dout_sorted), list(binary_list_sorted)
print(dout_sorted)
print(binary_list_sorted)


print("comparing....")
print(dout_sorted == dout)
print(binary_list_sorted == binary_list)


import matplotlib.pyplot as plt

# Assuming dout and dout_sorted are already defined and have 256 values
indices = range(len(dout))

plt.step(indices, dout, label='dout', color='blue')
plt.step(indices, dout_sorted, label='dout_sorted', color='red')

plt.xlabel('Index')
plt.ylabel('Value')
plt.title('Comparison of dout and dout_sorted')
plt.legend()

plt.show()
