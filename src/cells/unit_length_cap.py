import math

import klayout.db as db


wbase = [ 2**10-2**8,
            2**9,
            2**8,
            2**7,
            2**6,
            2**5,
            2**4,
            2**3,
            2**2,
            2**1,
            2**0]

wredun =  [
          2**6,
          2**6,
          2**5,
          2**5,
          2**4,
          2**4,
          2**3,
          2**3,
          2**2,
          2**2,
          2**2,
          2**1,
          2**0,
          2**0]

offset = 2
weights = [0] * (len(wredun) + offset)
for i in range(len(wbase)):
  weights[i] += wbase[i]

for i in range(len(wredun)):
  weights[i+offset] += wredun[i]

unary_weight = 64

print(weights)
print([w / unary_weight for w in weights])
print(f"unit count: {sum([math.ceil(w / unary_weight) for w in weights])}")
print(f"sum: {sum(weights)}")
print(f"length: {len(weights)}")

remaining = []
method1 = []
method2 = []
method3 = []
method4 = []
radix = []

bit = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]

for i,cap in enumerate(weights[:-1]):
    remain = 0
    for j,val in enumerate(weights[i+1:]):
        remain += val
    remaining.append(remain)

    method1.append((remain - weights[i]+1)/weights[i])
    method2.append((remain - weights[i]+1)/remain)   
    method3.append(round((sum(weights[i+1:]) - weights[i])/weights[i], 3)) #this metric make the most sense to me
    method4.append((remaining[i]-weights[i]))
    radix.append((weights[i]/weights[i+1]))

for a, b, c, d in zip(bit, weights, method4, radix):
    print(f"{a:<8} {b:<8} {c:<8} {d:<8}") # Left-aligned, 8-char width

# print(weights)
# print(remaining)
# # print(method1)
# # print(method2)
# print(method3)
# print(f"sum: {sum(weights)+1}")




# weights = weights[::-1] #flip the list around

strips_xdim = 0.120
strips_ydim = 50
strips_xspace = 0.1
strips_yspace = 0.1

ring_xdim = 0.12
ring_ydim = 0.12


ly = db.Layout()

# sets the database unit to 1 nm
ly.dbu = 0.001

# adds a single cell
ring = ly.create_cell("")

# creates a new layer (layer number 1, datatype 0)
metal5 = ly.layer(36, 0, "M5.drawing")
metal6 = ly.layer(37, 0, "M6.drawing")
metal7 = ly.layer(38, 0, "M7.drawing")

via5 = ly.layer(55, 0, "VIA5.drawing")
via6 = ly.layer(56, 0, "VIA6.drawing")
via7 = ly.layer(57, 0, "VIA7.drawing")

# # produces pixels from the bitmap as 0.5x0.5 µm
# # boxes on a 1x1 µm grid:
# y = 8.0
# for line in pattern.split("\n"):

#   x = 0.0
#   for bit in line:

#     if bit == "#":
#       # creates a rectangle for the "on" pixel
#       rect = db.DBox(0, 0, 0.5, 0.5).moved(x, y)
#       top_cell.shapes(layer1).insert(rect)

#     x += 1.0

#   y -= 1.0

# # adds an envelope box on layer 2/0
# layer2 = ly.layer(2, 0)
# envelope = top_cell.dbbox().enlarged(1.0, 1.0)
# top_cell.shapes(layer2).insert(envelope)
  
# # writes the layout to GDS
# ly.write("basic.gds")

# f_cell = ly.create_cell("F")

# poly = db.DPolygon([ 
#   db.DPoint(0, 0), db.DPoint(0, 5), db.DPoint(4, 5), db.DPoint(4, 4),
#   db.DPoint(1, 4), db.DPoint(1, 3), db.DPoint(3, 3), db.DPoint(3, 2),
#   db.DPoint(1, 2), db.DPoint(1, 0)
# ])

# l1 = ly.layer(1, 0)
# f_cell.shapes(l1).insert(poly)

# # Place this cell two times in a new cell TOP

# top_cell = ly.create_cell("TOP")

# ly.write("test_cells.gds")