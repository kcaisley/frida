#!/usr/bin/env python3

import sys
import klayout.db as db

try:
    from .layers import load_layers_from_lyt
except ImportError:
    # Handle standalone execution
    from layers import load_layers_from_lyt


# TODO: Currently broken, and layers function gives: print(layers)
# {'M1': 0, 'M2': 1, 'M3': 2, 'M4': 3, 'M5': 4, 'M6': 5, 'M7': 6, 'M8': 7, 'M9': 8, 'VIA1': 9, 'VIA2': 10, 'VIA3': 11, 'VIA4': 12, 'VIA5': 13, 'VIA6': 14, 'VIA7': 15, 'VIA8': 16, 'PO': 17, 'CO': 18, 'OD': 19, 'NW': 20, 'PM': 21, 'M1.PIN': 22, 'M2.PIN': 23, 'M3.PIN': 24, 'M4.PIN': 25, 'M5.PIN': 26, 'M6.PIN': 27, 'M7.PIN': 28, 'M8.PIN': 29, 'M9.PIN': 30, 'M1.DUMMY': 31, 'M2.DUMMY': 32, 'M3.DUMMY': 33, 'M4.DUMMY': 34, 'M5.DUMMY': 35, 'M6.DUMMY': 36, 'M7.DUMMY': 37, 'M8.DUMMY': 38, 'M9.DUMMY': 39}



# TODO: This is should be broken up into:
# 1. load_layers() - already done!
# 2. read GDS
# 3. parse "access layers" to pin rects/polygons extra blockage polygons (OBS)
# 4. parse "internal layers" to simply rect OBS equal to cell bounding box.
# 5. write the both out as .LEF file

def convert_gds_to_lef(gds_path, out_file, lyt_file_path, blockage_layers=None, cell_name=None):
    """
    Convert GDS file to LEF using KLayout's Python API
    Generate simple LEF with M4 pins and configurable blockage layers
    """
    
    # TODO: This should be depend on the input cell, but it's hard-coded for caparray.gds now
    # Default blockage layers if none specified
    if blockage_layers is None:
        blockage_layers = {"M5", "M6"}
    
    # Load GDS file
    ly = db.Layout()
    ly.read(gds_path)
    
    # Load layer mapping from technology file
    layers = load_layers_from_lyt(ly, lyt_file_path)
    print(layers)

    # Get the first top cell (assume single macro)
    top_cells = ly.top_cells()
    if not top_cells:
        raise ValueError("No top cells found in GDS file")
    
    top_cell = top_cells[0]  # Use first top cell
    
    def get_bounding_box(cell, layer_info):
        """Get bounding box of all shapes on a layer"""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        has_shapes = False
        
        for shape in cell.shapes(layer_info):
            has_shapes = True
            bbox = shape.bbox()
            min_x = min(min_x, bbox.left)
            min_y = min(min_y, bbox.bottom)
            max_x = max(max_x, bbox.right)
            max_y = max(max_y, bbox.top)
        
        return (min_x, min_y, max_x, max_y) if has_shapes else None
    
    def get_pin_rectangles(cell, layer_info):
        """Get individual rectangles from M4 layer for pins"""
        rectangles = []
        for shape in cell.shapes(layer_info):
            if shape.is_box():
                box = shape.box
                rectangles.append((box.left, box.bottom, box.right, box.top))
        return rectangles
    
    def get_pin_texts(cell, layer_info):
        """Get text labels from pin layer"""
        pins = []
        for shape in cell.shapes(layer_info):
            if shape.is_text():
                text = shape.text
                pos = shape.bbox().center()
                pins.append((str(text.string), pos.x, pos.y))
        return pins
    
    # Write LEF file
    with open(out_file, "w") as file:
        # LEF header
        print("VERSION 5.7 ;", file=file)
        print("DIVIDERCHAR \"/\" ;", file=file)
        print("BUSBITCHARS \"[]\" ;", file=file)
        print("", file=file)
        
        # Single MACRO
        # Use provided cell name or fall back to GDS cell name
        macro_name = cell_name if cell_name else top_cell.name
        bbox = top_cell.bbox()
        width = bbox.right / 1000.0
        height = bbox.top / 1000.0
        
        print(f"MACRO {macro_name}", file=file)
        print("  CLASS CORE ;", file=file)
        print("  ORIGIN 0.000 0.000 ;", file=file)
        print(f"  SIZE {width:.3f} BY {height:.3f} ;", file=file)
        print("  SYMMETRY X Y ;", file=file)
        print("", file=file)
        
        # Get M4 rectangles for pins
        if "M4" in layers:
            m4_rectangles = get_pin_rectangles(top_cell, layers["M4"])
        else:
            m4_rectangles = []
        
        # Get pin text labels
        pin_texts = []
        for pin_layer_name in ["M4_PIN", "M4.PIN"]:  # Try both naming conventions
            if pin_layer_name in layers:
                pin_texts = get_pin_texts(top_cell, layers[pin_layer_name])
                break
        
        # Create pins - match text labels to rectangles
        pin_counter = 1
        used_rectangles = set()
        
        for pin_name, pin_x, pin_y in pin_texts:
            # Find closest rectangle to this pin text
            best_rect = None
            min_dist = float('inf')
            best_idx = -1
            
            for i, (x1, y1, x2, y2) in enumerate(m4_rectangles):
                if i in used_rectangles:
                    continue
                    
                # Check if pin is inside or near rectangle
                rect_center_x = (x1 + x2) / 2
                rect_center_y = (y1 + y2) / 2
                dist = ((pin_x - rect_center_x) ** 2 + (pin_y - rect_center_y) ** 2) ** 0.5
                
                if dist < min_dist:
                    min_dist = dist
                    best_rect = (x1, y1, x2, y2)
                    best_idx = i
            
            if best_rect:
                used_rectangles.add(best_idx)
                x1, y1, x2, y2 = best_rect
                
                # Determine pin type based on name
                if "vdd" in pin_name.lower() or "vcc" in pin_name.lower():
                    direction = "INOUT"
                    use_type = "POWER"
                elif "vss" in pin_name.lower() or "gnd" in pin_name.lower():
                    direction = "INOUT" 
                    use_type = "GROUND"
                elif "out" in pin_name.lower():
                    direction = "OUTPUT"
                    use_type = "SIGNAL"
                else:
                    direction = "INPUT"
                    use_type = "SIGNAL"
                
                print(f"  PIN {pin_name}", file=file)
                print(f"    DIRECTION {direction} ;", file=file)
                print(f"    USE {use_type} ;", file=file)
                print("    PORT", file=file)
                print("      LAYER M4 ;", file=file)
                print(f"        RECT {x1/1000:.3f} {y1/1000:.3f} {x2/1000:.3f} {y2/1000:.3f} ;", file=file)
                print("    END", file=file)
                print(f"  END {pin_name}", file=file)
                print("", file=file)
        
        # Add any remaining M4 rectangles as unnamed pins
        for i, (x1, y1, x2, y2) in enumerate(m4_rectangles):
            if i not in used_rectangles:
                pin_name = f"PIN{pin_counter}"
                pin_counter += 1
                
                print(f"  PIN {pin_name}", file=file)
                print("    DIRECTION INPUT ;", file=file)
                print("    USE SIGNAL ;", file=file)
                print("    PORT", file=file)
                print("      LAYER M4 ;", file=file)
                print(f"        RECT {x1/1000:.3f} {y1/1000:.3f} {x2/1000:.3f} {y2/1000:.3f} ;", file=file)
                print("    END", file=file)
                print(f"  END {pin_name}", file=file)
                print("", file=file)
        
        # Add blockage layers
        print(layers)
        blockage_bboxes = {}
        for layer_name in blockage_layers:
            if layer_name in layers:
                bbox = get_bounding_box(top_cell, layers[layer_name])
                print(f"layer_name: {layer_name}")
                print(f"bbox: {bbox}")
                if bbox:
                    blockage_bboxes[layer_name] = bbox

        print(f"Test for {blockage_bboxes}")
        if blockage_bboxes:
            print("  OBS", file=file)
            
            for layer_name, (x1, y1, x2, y2) in blockage_bboxes.items():
                print(f"    LAYER {layer_name} ;", file=file)
                print(f"      RECT {x1/1000:.3f} {y1/1000:.3f} {x2/1000:.3f} {y2/1000:.3f} ;", file=file)
                
            print("  END", file=file)
        else:
            # Empty OBS section if no blockage layers found
            print("  OBS", file=file)
            print("  END", file=file)
        print("", file=file)
        
        print(f"END {macro_name}", file=file)
        print("", file=file)
        print("END LIBRARY", file=file)

if __name__ == "__main__":
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Usage: python gds2lef.py <input.gds> <output.lef> <layer_map.lyt> [blockage_layers]")
        print("  blockage_layers: comma-separated list of layer names to export as single blockage rectangles")
        print("  Example: python gds2lef.py input.gds output.lef tsmc65.lyt M5,M6,VIA5")
        sys.exit(1)
    
    gds_path = sys.argv[1]
    out_file = sys.argv[2]
    lyt_file_path = sys.argv[3]
    
    # Extract cell name from GDS filename
    import os
    cell_name = os.path.splitext(os.path.basename(gds_path))[0]
    
    blockage_layers = None
    if len(sys.argv) == 5:
        # Parse comma-separated blockage layers
        blockage_layers = set(layer.strip() for layer in sys.argv[4].split(','))
        print(f"Using custom blockage layers: {blockage_layers}")
    
    try:
        convert_gds_to_lef(gds_path, out_file, lyt_file_path, blockage_layers, cell_name)
        print(f"Successfully converted {gds_path} to {out_file}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)