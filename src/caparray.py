import math
import sys
import xml.etree.ElementTree as ET
import klayout.db as db
import cdac


def parse_layer_mapping(lyt_file_path):
    """
    Parse layer mapping from tsmc65.lyt file.
    
    Returns:
    - Dictionary mapping layer names to (layer_number, datatype) tuples
    """
    tree = ET.parse(lyt_file_path)
    root = tree.getroot()
    
    layer_mapping = {}
    
    # Find connectivity symbols section
    connectivity = root.find('connectivity')
    if connectivity is not None:
        for symbols in connectivity.findall('symbols'):
            text = symbols.text
            if text:
                # Parse entries like "M5='35/0+135/0'"
                parts = text.split('=')
                if len(parts) == 2:
                    layer_name = parts[0].strip()
                    layer_def = parts[1].strip().strip("'")
                    
                    # Extract primary layer number (before the +)
                    if '+' in layer_def:
                        primary = layer_def.split('+')[0]
                    else:
                        primary = layer_def
                    
                    if '/' in primary:
                        layer_num, datatype = primary.split('/')
                        layer_mapping[layer_name] = (int(layer_num), int(datatype))
    
    return layer_mapping


def create_layers(ly, layer_mapping):
    """
    Create KLayout layers from the mapping dictionary.
    
    Returns:
    - Dictionary mapping layer names to KLayout layer objects
    """
    layers = {}
    
    for layer_name, (layer_num, datatype) in layer_mapping.items():
        layers[layer_name] = ly.layer(layer_num, datatype, f"{layer_name}.drawing")
    
    return layers


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
    """
    Create a pair of capacitor strips with differential sizing.
    
    Returns:
    - List of two DBox objects representing the strips
    """
    # Calculate the y positions for the second strips
    y1 = strips_ydim_base + strips_yspace
    ydiff = strips_ydim_step * strip_ydim_diff

    # Create two boxes (strips)
    strip1 = db.DBox(0, 0, strips_xdim, strips_ydim_base + ydiff) # bottom stays fixed, top lengthens upward
    strip2 = db.DBox(0, y1+ydiff, strips_xdim, y1 + strips_ydim_base) # top stay fixed, bottom shortens upward

    # Return as a list of DBox objects
    return [strip1, strip2]


def create_m5_shielding_with_cutouts(interior_x, interior_y, ring_thickness, strips_xspace, strips_yspace, strips_ydim_base):
    """
    Create M5 shielding plane with cutouts for density requirements.
    
    Parameters:
    - interior_x: Interior width of the shielding plane
    - interior_y: Interior height of the shielding plane  
    - ring_thickness: Thickness to match the M6 ring dimensions
    - strips_xspace, strips_yspace: Strip spacing parameters for via positioning
    - strips_ydim_base: Base strip dimension for calculating total structure height
    
    Returns:
    - DPolygon representing the M5 shielding with cutouts
    """
    # Create base shielding plane (same dimensions as M6 ring exterior)
    outer_width = interior_x + 2 * ring_thickness
    outer_height = interior_y + 2 * ring_thickness
    
    # Create main shielding polygon
    main_points = [
        db.DPoint(0, 0),
        db.DPoint(0, outer_height),
        db.DPoint(outer_width, outer_height),
        db.DPoint(outer_width, 0)
    ]
    
    shielding = db.DPolygon(main_points)
    
    # Add density cutouts - 0.12x0.12 um squares, avoiding via areas
    cutout_size = 0.12
    cutout_interval = 1.0
    inset = 0.12  # Distance from edge
    
    # Calculate actual via positions (matching the via creation logic)
    x_offset = strips_xspace + ring_thickness
    y_offset = strips_yspace + ring_thickness
    via_inset = 0.12
    via_cutout_size = 0.32
    total_structure_height = 2 * strips_ydim_base + 2 * strips_yspace
    
    # Bottom via Y position
    bottom_via_y = y_offset + via_inset
    # Top via Y position  
    top_via_y = y_offset + total_structure_height - via_inset - via_cutout_size
    
    # Define exclusion zones around actual via positions
    via_margin = 0.2  # Margin around via cutouts
    bottom_exclusion_start = bottom_via_y - via_margin
    bottom_exclusion_end = bottom_via_y + via_cutout_size + via_margin
    top_exclusion_start = top_via_y - via_margin
    top_exclusion_end = top_via_y + via_cutout_size + via_margin
    
    # Calculate usable Y space (between via exclusion zones)
    usable_y_start = bottom_exclusion_end
    usable_y_end = top_exclusion_start
    usable_y_length = usable_y_end - usable_y_start
    
    # Create cutouts on both sides using holes
    hole_points = []
    
    if usable_y_length > 2.0:  # Only if there's enough space
        # Target: (length - 2um) / 1um cutouts, evenly distributed
        target_cutouts = max(1, int((usable_y_length - 2.0) / cutout_interval))
        
        # Calculate actual spacing to evenly distribute cutouts
        if target_cutouts > 1:
            actual_interval = usable_y_length / (target_cutouts + 1)  # +1 for equal spacing from ends
        else:
            actual_interval = usable_y_length / 2
            
        for i in range(target_cutouts):
            y_pos = usable_y_start + (i + 1) * actual_interval - cutout_size / 2
            
            # Ensure cutout fits within bounds
            if y_pos >= usable_y_start and y_pos + cutout_size <= usable_y_end:
                # Left side cutout hole (counter-clockwise)
                left_hole = [
                    db.DPoint(inset, y_pos),
                    db.DPoint(inset + cutout_size, y_pos),
                    db.DPoint(inset + cutout_size, y_pos + cutout_size),
                    db.DPoint(inset, y_pos + cutout_size)
                ]
                hole_points.append(left_hole)
                
                # Right side cutout hole (counter-clockwise)
                right_hole = [
                    db.DPoint(outer_width - inset - cutout_size, y_pos),
                    db.DPoint(outer_width - inset, y_pos),
                    db.DPoint(outer_width - inset, y_pos + cutout_size),
                    db.DPoint(outer_width - inset - cutout_size, y_pos + cutout_size)
                ]
                hole_points.append(right_hole)
    
    # Insert holes into the main shielding polygon
    for hole in hole_points:
        shielding.insert_hole(hole)
    
    return shielding


def create_strip_end_cutouts_and_vias(strips_xdim, strips_ydim_base, strips_yspace, 
                                     strips_ydim_step, strip_ydim_diff, strips_xspace, 
                                     ring_thickness, layers):
    """
    Create the 0.32x0.32 cutouts on strip ends and vias from M6 to M4.
    Only creates 2 vias: one at bottom of bottom strip, one at top of top strip.
    
    Returns:
    - List of cutout polygons for M5
    - List of via shapes for VIA4 and VIA5 layers
    """
    cutouts = []
    vias = []
    
    # Parameters for cutouts and vias
    cutout_size = 0.32
    via_inset = 0.12  # 0.12um inset from strip ends
    
    # Calculate strip positions (matching the strip_pair function)
    y1 = strips_ydim_base + strips_yspace
    ydiff = strips_ydim_step * strip_ydim_diff
    
    # Strip 1 dimensions
    strip1_height = strips_ydim_base + ydiff
    # Strip 2 dimensions  
    strip2_y_start = y1 + ydiff
    strip2_height = strips_ydim_base
    
    # Account for positioning offset due to centering inside ring
    x_offset = strips_xspace + ring_thickness
    y_offset = strips_yspace + ring_thickness
    
    # Only create cutouts and vias at:
    # 1. Bottom end of strip 1 (bottom strip)
    # 2. Top end of strip 2 (top strip)
    
    # Calculate the total structure height for fixed positioning
    total_structure_height = 2 * strips_ydim_base + 2 * strips_yspace
    
    # Bottom end of strip 1 - fixed position (move 0.1um left)
    cutout1_bottom = db.DPolygon([
        db.DPoint(x_offset - 0.1, y_offset + via_inset),
        db.DPoint(x_offset - 0.1, y_offset + via_inset + cutout_size),
        db.DPoint(x_offset - 0.1 + cutout_size, y_offset + via_inset + cutout_size),
        db.DPoint(x_offset - 0.1 + cutout_size, y_offset + via_inset)
    ])
    cutouts.append(cutout1_bottom)
    
    # Top end - fixed absolute position (move 0.1um left, fixed height)
    top_via_y = y_offset + total_structure_height - via_inset - cutout_size
    cutout2_top = db.DPolygon([
        db.DPoint(x_offset - 0.1, top_via_y),
        db.DPoint(x_offset - 0.1, top_via_y + cutout_size),
        db.DPoint(x_offset - 0.1 + cutout_size, top_via_y + cutout_size),
        db.DPoint(x_offset - 0.1 + cutout_size, top_via_y)
    ])
    cutouts.append(cutout2_top)
    
    # Create vias at the center of each cutout
    via_size = 0.1  # LEF specifies 0.1x0.1 (RECT -0.050 -0.050 0.050 0.050 = 0.1x0.1)
    
    for cutout in cutouts:
        bbox = cutout.bbox()
        via_center_x = (bbox.left + bbox.right) / 2
        via_center_y = (bbox.bottom + bbox.top) / 2
        
        # Create via box centered in cutout
        via_box = db.DBox(via_center_x - via_size/2, via_center_y - via_size/2,
                         via_center_x + via_size/2, via_center_y + via_size/2)
        
        vias.append(via_box)
    
    return cutouts, vias


def unit_length_cap(ly, layers, strips_xdim, strips_ydim_base, strips_yspace, 
                   strips_ydim_step, strips_ydim_diff, strips_xspace, ring_xdim, 
                   ring_ydim, interior_x, interior_y):
    """
    Create a unit length capacitor cell with M6 ring and strips, M5 shielding, and vias.

    Returns the created cell.
    """
    # Create the M6 structures (ring and strips)
    ring_m6 = ring(interior_x, interior_y, ring_xdim)
    strip1, strip2 = strip_pair(strips_xdim, strips_ydim_base, strips_yspace, 
                               strips_ydim_step, strips_ydim_diff)

    # Center the strips inside the ring
    strip1 = strip1.moved(strips_xspace + ring_xdim, strips_yspace + ring_ydim)
    strip2 = strip2.moved(strips_xspace + ring_xdim, strips_yspace + ring_ydim)

    # Create M5 shielding plane with density cutouts
    m5_shielding = create_m5_shielding_with_cutouts(interior_x, interior_y, ring_xdim, 
                                                   strips_xspace, strips_yspace, strips_ydim_base)
    
    # Create strip end cutouts and vias
    strip_cutouts, via_shapes = create_strip_end_cutouts_and_vias(
        strips_xdim, strips_ydim_base, strips_yspace, strips_ydim_step, 
        strips_ydim_diff, strips_xspace, ring_xdim, layers)
    
    # Apply strip cutouts to M5 shielding by inserting holes
    for cutout in strip_cutouts:
        bbox = cutout.bbox()
        # Create hole points (counter-clockwise)
        hole_points = [
            db.DPoint(bbox.left, bbox.bottom),
            db.DPoint(bbox.right, bbox.bottom),
            db.DPoint(bbox.right, bbox.top),
            db.DPoint(bbox.left, bbox.top)
        ]
        m5_shielding.insert_hole(hole_points)

    # Create the cell and add all shapes
    temp_cell = ly.create_cell("unit_cap_with_shielding")
    
    # Add M6 structures
    temp_cell.shapes(layers['M6']).insert(ring_m6)
    temp_cell.shapes(layers['M6']).insert(strip1)
    temp_cell.shapes(layers['M6']).insert(strip2)
    
    # Add M5 shielding
    temp_cell.shapes(layers['M5']).insert(m5_shielding)
    
    # Add vias (VIA4 connects M4-M5, VIA5 connects M5-M6)
    for via_shape in via_shapes:
        temp_cell.shapes(layers['VIA4']).insert(via_shape)
        temp_cell.shapes(layers['VIA5']).insert(via_shape)

    return temp_cell


def create_m4_routing_strips(ly, layers, partitioned_weights, strips_xspace, strips_yspace, 
                           strips_ydim_base, ring_thickness, x_shift, y_shift):
    """
    Create M4 horizontal routing strips that connect capacitors according to partitioned_weights.
    
    Parameters:
    - ly: Layout object
    - layers: Layer mapping dictionary  
    - partitioned_weights: Grouping of capacitors to connect
    - strips_xspace, strips_yspace: Strip positioning parameters
    - strips_ydim_base: Base strip dimension
    - ring_thickness: Ring thickness for positioning
    - x_shift, y_shift: Positioning offsets
    
    Returns:
    - Tuple of (M4 routing shapes, M4 pin labels)
    """
    m4_shapes = []
    m4_pin_labels = []
    
    # Calculate via positions (same logic as via creation)
    x_offset = strips_xspace + ring_thickness - 0.1  # Match via X position
    y_offset = strips_yspace + ring_thickness
    via_inset = 0.12
    total_structure_height = 2 * strips_ydim_base + 2 * strips_yspace
    
    # Bottom via Y position (main capacitor connection point)
    bottom_via_y = y_offset + via_inset + 0.32/2  # Center of via cutout
    # Top via Y position (diff capacitor connection point)  
    top_via_y = y_offset + total_structure_height - via_inset - 0.32/2  # Center of via cutout
    
    # M4 parameters - based on LEF via dimensions and enclosure rules
    via_m4_width = 0.1   # Via M4 width from LEF
    via_m4_height = 0.18  # Via M4 height from LEF: RECT -0.050 -0.090 0.050 0.090
    m4_enclosure = 0.04   # LEF ENCLOSURE rule: 0.04 μm minimum
    
    # M4 strip dimensions (larger than via + enclosure)
    strip_width = via_m4_width + 2 * m4_enclosure   # 0.18 μm
    strip_height = via_m4_height + 2 * m4_enclosure  # 0.26 μm
    
    # Track capacitor position and bit index (from MSB to LSB, left to right)
    cap_position = 0
    bit_index = 15  # Start from MSB (bit 15)
    
    # Process each group in partitioned_weights (in reverse order as capacitors are placed)
    for group_idx, group in enumerate(reversed(partitioned_weights)):
        group_size = len(group)
        
        if group_size == 1:
            # Single capacitor - create M4 patches around vias (shifted 0.11 μm right)
            shift_right = 0.11
            cap_x = cap_position * x_shift + x_offset + 0.05 + shift_right  # Center of via + shift
            
            # Create main capacitor M4 patch (bottom via)
            main_patch = db.DBox(
                cap_x - strip_width/2, bottom_via_y + y_shift - strip_height/2,
                cap_x + strip_width/2, bottom_via_y + y_shift + strip_height/2
            )
            m4_shapes.append(main_patch)
            
            # Create diff capacitor M4 patch (top via)
            diff_patch = db.DBox(
                cap_x - strip_width/2, top_via_y + y_shift - strip_height/2,
                cap_x + strip_width/2, top_via_y + y_shift + strip_height/2
            )
            m4_shapes.append(diff_patch)
            
            # Add pin labels for single capacitor patches
            main_label = db.DText(f"cap_botplate_m[{bit_index}]", 
                                db.DTrans(cap_x, bottom_via_y + y_shift))
            diff_label = db.DText(f"cap_botplate_d[{bit_index}]", 
                                db.DTrans(cap_x, top_via_y + y_shift))
            m4_pin_labels.extend([main_label, diff_label])
            
            cap_position += 1
            bit_index -= 1
            continue
            
        # Multi-capacitor group - create routing strips with extensions and shift
        shift_right = 0.11
        extension = 0.04  # Extra length on each end for spacing around vias
        
        start_x = cap_position * x_shift + x_offset + shift_right - extension
        end_x = (cap_position + group_size - 1) * x_shift + x_offset + 0.1 + shift_right + extension
        
        # Create main capacitor routing strip (bottom vias)
        main_strip = db.DBox(
            start_x, bottom_via_y + y_shift - strip_height/2,
            end_x, bottom_via_y + y_shift + strip_height/2
        )
        m4_shapes.append(main_strip)
        
        # Create diff capacitor routing strip (top vias)
        diff_strip = db.DBox(
            start_x, top_via_y + y_shift - strip_height/2,
            end_x, top_via_y + y_shift + strip_height/2
        )
        m4_shapes.append(diff_strip)
        
        # Add pin labels for multi-capacitor strips (centered on the strip)
        center_x = (start_x + end_x) / 2
        main_label = db.DText(f"cap_botplate_m[{bit_index}]", 
                            db.DTrans(center_x, bottom_via_y + y_shift))
        diff_label = db.DText(f"cap_botplate_d[{bit_index}]", 
                            db.DTrans(center_x, top_via_y + y_shift))
        m4_pin_labels.extend([main_label, diff_label])
        
        # Move to next group position
        cap_position += group_size
        bit_index -= 1
    
    return m4_shapes, m4_pin_labels


def main():
    if len(sys.argv) != 2:
        print("Usage: python caparray.py <output_path>")
        sys.exit(1)

    output_path = sys.argv[1]
    lyt_file_path = "/home/kcaisley/asiclab/tech/tsmc65/tsmc65.lyt"
    
    # Parse layer mapping from tsmc65.lyt file
    layer_mapping = parse_layer_mapping(lyt_file_path)
    
    # Calculate weights and perform analysis
    unary_weight = 64
    weights, w_base, w_redun = cdac.generate_weights(11, 8, [5,6], 2)
    print(f"Base weights: {w_base}, Redundant weights: {w_redun}")
    partitioned_weights = cdac.analyze_weights(weights, unary_weight)

    # Physical dimensions
    strips_xdim = 0.120
    strips_ydim_min = 1
    strips_ydim_step = 0.4
    strips_ydim_base = strips_ydim_min + (strips_ydim_step * unary_weight)

    strips_xspace = 0.1
    strips_yspace = 0.1
    strips_ydim = strips_yspace + 2*strips_ydim_base

    ring_xdim = 0.12
    ring_ydim = 0.12

    interior_x = strips_xdim + 2*strips_xspace
    interior_y = strips_ydim + 2*strips_yspace

    # Create layout and layers
    ly = db.Layout()
    ly.dbu = 0.001  # sets the database unit to 1 nm
    
    layers = create_layers(ly, layer_mapping)

    # Create the top-level cell
    top_cell = ly.create_cell("cdac_array_with_shielding")

    # Layout parameters
    y_shift = 0
    x_shift = interior_x + ring_xdim
    position_counter = 0

    # Generate capacitor array
    for main_idx in range(len(partitioned_weights) - 1, -1, -1):
        sublist = partitioned_weights[main_idx]
        for sub_idx in range(len(sublist) - 1, -1, -1):
            strips_ydim_diff = sublist[sub_idx]
            temp_cell = unit_length_cap(
                ly, layers, strips_xdim, strips_ydim_base, strips_yspace,
                strips_ydim_step, strips_ydim_diff, strips_xspace, 
                ring_xdim, ring_ydim, interior_x, interior_y
            )
            
            # Calculate the transformation for placement
            trans = db.DTrans(position_counter * x_shift, y_shift)
            position_counter += 1
            
            # Insert the temp_cell into the top_cell with the transformation
            top_cell.insert(db.DCellInstArray(temp_cell.cell_index(), trans))

    # Create M4 routing strips to connect capacitors according to partitioned_weights
    m4_routing_shapes, m4_pin_labels = create_m4_routing_strips(
        ly, layers, partitioned_weights, strips_xspace, strips_yspace,
        strips_ydim_base, ring_xdim, x_shift, y_shift
    )
    
    # Add M4 routing shapes to the top cell
    for shape in m4_routing_shapes:
        top_cell.shapes(layers['M4']).insert(shape)
    
    # Add M4 pin labels to the top cell on M4.PIN layer
    if 'M4' in layers:
        # Create M4.PIN layer (layer 134, datatype 0 based on LEF file pattern)
        m4_pin_layer = ly.layer(134, 0, "M4.PIN")
        
        for label in m4_pin_labels:
            top_cell.shapes(m4_pin_layer).insert(label)

    # Add cap_topplate pin label at top left corner of the first capacitor's outer ring
    if 'M6' in layers:
        # Create M6.PIN layer for the top plate connection
        m6_pin_layer = ly.layer(136, 0, "M6.PIN")
        
        # Position centered in the top ring of the first (leftmost) capacitor
        topplate_x = 0 + 0.06  # Right 0.06 from left edge
        topplate_y = interior_y + ring_ydim + y_shift + 0.06  # Up 0.06 from previous position
        
        topplate_label = db.DText("cap_topplate", db.DTrans(topplate_x, topplate_y))
        top_cell.shapes(m6_pin_layer).insert(topplate_label)

    # Write the layout
    ly.write(output_path)
    print(f"Layout written to: {output_path}")


if __name__ == "__main__":
    main()