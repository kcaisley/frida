import math
import sys
import klayout.db as db
import cdac



# Calculate weights and perform analysis
unary_weight = 64
weights, w_base, w_redun = cdac.generate_weights(11, 8, [5,6], 2)
print(w_base, w_redun)
partitioned_weights = cdac.analyze_weights(weights, unary_weight)

# Next we build the single physical unit length cap, conscious of the fact that it must fit 64 steps within it, based on our unary weight
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
    ly, metal5, strips_xdim, strips_ydim_base, strips_yspace, strips_ydim_step,
    strips_ydim_diff, strips_xspace, ring_xdim, ring_ydim, interior_x, interior_y
):
    """
    Create a unit length capacitor cell with a ring and a pair of strips.

    Returns the created cell.
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

if len(sys.argv) != 2:
    print("Usage: python cdac_layout.py <output_path>")
    sys.exit(1)

output_path = sys.argv[1]
ly.write(output_path)
