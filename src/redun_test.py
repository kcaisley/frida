# weights = [220, 126, 72, 40, 22, 14, 7, 4, 3, 2, 1]
weights = [192, 128, 64, 56, 32, 16, 8, 7, 4, 2, 1, 1]

remaining = []
redunancy = []
oldredun = []
oldredun2 = []
for i,cap in enumerate(weights[:-1]):
    remain = 0
    for j,val in enumerate(weights[i+1:]):
        remain += val
    remaining.append(remain)

    redunancy.append((remain - weights[i]+1)/weights[i])
    oldredun.append((remain - weights[i]+1)/remain)   
    oldredun2.append((sum(weights[i+1:]) - weights[i]+1)/sum(weights[i:])) #this metric make the most sense to me

print(remaining)
print(redunancy)
print(oldredun)
print(oldredun2)