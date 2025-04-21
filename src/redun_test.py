# weights = [220, 126, 72, 40, 22, 14, 7, 4, 3, 2, 1]
# weights = [128, 64, 32, 16, 8, 4, 3, 1, 1]

weights = [2**10-2**7,
           2**9,
           2**8+2**5,
           2**7+2**5,
           2**6+2**4,
           2**5+2**4,
           2**4+2**3,
           2**3+2**3,
           2**2+2**2,
           2**1+2**2,
           2**0+2**1,
                2**1,
                2**1,
                2**0,
                2**0]



remaining = []
method1 = []
method2 = []
method3 = []

bit = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]

for i,cap in enumerate(weights[:-1]):
    remain = 0
    for j,val in enumerate(weights[i+1:]):
        remain += val
    remaining.append(remain)

    method1.append((remain - weights[i]+1)/weights[i])
    method2.append((remain - weights[i]+1)/remain)   
    method3.append(round((sum(weights[i+1:]) - weights[i])/weights[i], 3)) #this metric make the most sense to me

for a, b, c in zip(bit, weights, method3):
    print(f"{a:<8} {b:<8} {c:<8}")  # Left-aligned, 8-char width

# print(weights)
# print(remaining)
# # print(method1)
# # print(method2)
# print(method3)
print(f"sum: {sum(weights)+1}")