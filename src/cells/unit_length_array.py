import math

import klayout.db as db

def partition_weights(weights, unary_weight):
    """
    Splits each weight into chunks of unary_weight, with a possible remainder at the end.
    Returns a list of lists.
    """
    result = []
    for w in weights:
        chunks = [unary_weight] * (w // unary_weight)
        remainder = w % unary_weight
        if remainder > 0:
            chunks.append(remainder)
        result.append(chunks)
    return result


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
partitioned_weights = partition_weights(weights, unary_weight)
print(partitioned_weights)
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
    method3.append(round((sum(weights[i+1:]) - weights[i])/weights[i], 3))
    method4.append((remaining[i]-weights[i]))   # this is the one I'm printing
    radix.append((weights[i]/weights[i+1]))

for a, b, c, d in zip(bit, weights, method4, radix):
    print(f"{a:<8} {b:<8} {c:<8} {d:<8}") # Left-aligned, 8-char width


# Everything before this marker is testbenches, to get the:
# - weights
# - unary_weight
# - ratio between the two


# Next we build the single physical unit length cap, concious of the fact that it must fit 64 steps within it, based on our unary weight
strips_xdim = 0.120
strips_ydim_min = 1
strips_ydim_step = 0.4
strips_ydim_base = strips_ydim_min + (strips_ydim_step * unary_weight) # make the base strip long enough

strips_xspace = 0.1
strips_yspace = 0.1
strips_ydim = strips_yspace + 2*strips_ydim_base

ring_xdim = 0.12
ring_ydim = 0.12

interior_x = strips_xdim + 2*strips_xspace
interior_y = strips_ydim + 2*strips_yspace

# As a principle, a function should only generate a single structure, on a single layer

ly = db.Layout()

# sets the database unit to 1 nm
ly.dbu = 0.001

# creates a new layer (layer number 1, datatype 0)
metal5 = ly.layer(36, 0, "M5.drawing")
metal6 = ly.layer(37, 0, "M6.drawing")
metal7 = ly.layer(38, 0, "M7.drawing")

via5 = ly.layer(55, 0, "VIA5.drawing")
via6 = ly.layer(56, 0, "VIA6.drawing")
via7 = ly.layer(57, 0, "VIA7.drawing")

def ring(width, height, thickness):
    """
    Creates a ring-shaped polygon with specified inner dimensions and thickness.
    
    Parameters:
    - width: Inner width of the ring (in database units)
    - height: Inner height of the ring (in database units)
    - thickness: Uniform thickness of the ring (in database units)
    
    Returns:
    - A db.DPolygon object representing the ring
    """
    # Create outer rectangle dimensions
    outer_width = width + 2 * thickness
    outer_height = height + 2 * thickness
    
    # Create outer rectangle points (clockwise)
    outer_points = [
        db.DPoint(0, 0),
        db.DPoint(0, outer_height),
        db.DPoint(outer_width, outer_height),
        db.DPoint(outer_width, 0)
    ]
    
    # Create inner rectangle points (counter-clockwise)
    inner_points = [
        db.DPoint(thickness, thickness),
        db.DPoint(thickness, thickness + height),
        db.DPoint(thickness + width, thickness + height),
        db.DPoint(thickness + width, thickness)
    ]
    
    # Create and return the polygon, inner points create a hole
    return db.DPolygon(outer_points).insert_hole(inner_points)


def strip_pair(strips_xdim, strips_ydim_base, strips_yspace, strips_ydim_step, strip_ydim_diff):

    # Calculate the y positions for the second strips
    y1 = strips_ydim_base + strips_yspace
    ydiff = strips_ydim_step * strip_ydim_diff

    # Create two boxes (strips)
    strip1 = db.DBox(0, 0, strips_xdim, strips_ydim_base + ydiff) # bottom stays fixed, top lengthens upward
    strip2 = db.DBox(0, y1+ydiff, strips_xdim, y1 + strips_ydim_base) # top stay fixed, bottum shortens upward

    # Return as a list of DBox objects
    return [strip1, strip2]

def unit_length_cap(
    ly,
    metal5,
    strips_xdim,
    strips_ydim_base,
    strips_yspace,
    strips_ydim_step,
    strips_ydim_diff,
    strips_xspace,
    ring_xdim,
    ring_ydim,
    interior_x,
    interior_y
):
    """
    Creates a unit length capacitor cell with a ring and a pair of strips.

    Parameters:
    - ly: db.Layout object to create the cell in
    - metal5: Layer index for metal5
    - strips_xdim: Width of the strips
    - strips_ydim_base: Base height of the strips
    - strips_yspace: Vertical space between strips
    - strips_ydim_step: Step size for strip length difference
    - strips_ydim_diff: Integer multiple for difference in strip length (in steps)
    - strips_xspace: Horizontal space between strips and ring
    - ring_xdim: Thickness of the ring
    - ring_ydim: Not used directly, but kept for symmetry/future use
    - interior_x: Inner width of the ring
    - interior_y: Inner height of the ring

    Returns:
    - temp_cell: The created cell containing the ring and strips
    """

    ring1 = ring(interior_x, interior_y, ring_xdim)

    strip1, strip2 = strip_pair(strips_xdim, strips_ydim_base, strips_yspace, strips_ydim_step, strips_ydim_diff)

    # Center the strips inside the ring
    strip1 = strip1.moved(strips_xspace + ring_xdim, strips_yspace + ring_ydim)
    strip2 = strip2.moved(strips_xspace + ring_xdim, strips_yspace + ring_ydim)

    temp_cell = ly.create_cell("temp_cell")

    temp_cell.shapes(metal5).insert(ring1)
    temp_cell.shapes(metal5).insert(strip1)
    temp_cell.shapes(metal5).insert(strip2)

    return temp_cell

# Create the top-level cell
top_cell = ly.create_cell("cdac_array")

# Define the y shift (hardcoded to 0)
y_shift = 0

# X shift between capacitors
x_shift = interior_x + ring_xdim

# List of ydim differences
ydim_diffs = partitioned_weights

position_counter = 0

for main_idx in range(len(partitioned_weights) - 1, -1, -1):
    sublist = partitioned_weights[main_idx]
    for sub_idx in range(len(sublist) - 1, -1, -1):
        strips_ydim_diff = sublist[sub_idx]
        temp_cell = unit_length_cap(
            ly,
            metal5,
            strips_xdim,
            strips_ydim_base,
            strips_yspace,
            strips_ydim_step,
            strips_ydim_diff,
            strips_xspace,
            ring_xdim,
            ring_ydim,
            interior_x,
            interior_y
        )
        # Calculate the transformation for placement
        trans = db.DTrans(position_counter * x_shift, y_shift)
        position_counter += 1
        # Insert the temp_cell into the top_cell with the transformation
        top_cell.insert(db.DCellInstArray(temp_cell.cell_index(), trans))

ly.write("build/cdac_array.gds")


# Generate a single ring cell with 1um inner height and write to "build/ring.gds"
# ring_inner_width = interior_x
# ring_inner_height = 1.0  # 1um inner height
# ring_thickness = ring_xdim

# ring_ly = db.Layout()

# ring_cell = ring_ly.create_cell("ring_only")
# ring_shape = ring(ring_inner_width, ring_inner_height, ring_thickness)
# ring_cell.shapes(metal5).insert(ring_shape)

# # Write the ring cell to a separate layout object and file
# ring_ly.dbu = 0.001
# ring_ly.layer(36, 0, "M5.drawing")
# ring_ly.write("build/ring.gds")