#!/usr/bin/env python3

import sys
import pya
import re

def convert_gds_to_lef(gds_path, out_file, custom_blockage_layers=None):
    """
    Convert GDS file to LEF using KLayout's Python API
    """
    
    ###### CONSTANTS ######                                                        
    # TSMC65 layer mapping based on tsmc65.lyt
    layers = {                                                  
        "M4": (34,0),      # Metal 4 layer                         
        "M5": (35,0),      # Metal 5 layer                        
        "M6": (36,0),      # Metal 6 layer                        
        "VIA4": (54,0),    # Via 4 layer                       
        "VIA5": (55,0),    # Via 5 layer
        "M4.PIN": (134,0), # M4 pin layer
        "M6.PIN": (136,0)  # M6 pin layer                     
    }                                                          
    ignore_cells = ["unit_cap_with_shielding"]  # Ignore individual capacitor cells               
    
    # Layers to export as single blockage rectangles (encompassing all structures)
    # Instead of exporting every individual rectangle/polygon
    default_blockage_layers = {"M5", "M6", "VIA5"}  # Add layer names here that should be simple blockages
    blockage_layers = custom_blockage_layers if custom_blockage_layers is not None else default_blockage_layers
    #######################

    def point_in_rectangle(point, rectangles):
        text, x, y = point
        for i in range(len(rectangles)):
            x1, y1, x2, y2 = rectangles[i]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i
        return -1

    def point_in_polygon(point, polygon):
        text, x, y = point
        n = len(polygon) // 2
        inside = False

        p1x, p1y = polygon[0], polygon[1]
        for i in range(n + 1):
            p2x, p2y = polygon[(i % n) * 2], polygon[(i % n) * 2 + 1]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def get_layer_bounding_box(shapes_iter):
        """Calculate the bounding box that encompasses all shapes on a layer"""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        has_shapes = False
        for shape in shapes_iter:
            has_shapes = True
            bbox = shape.bbox()
            min_x = min(min_x, bbox.left)
            min_y = min(min_y, bbox.bottom)
            max_x = max(max_x, bbox.right)
            max_y = max(max_y, bbox.top)
        
        if not has_shapes:
            return None
        return [min_x, min_y, max_x, max_y]

    # Load GDS file
    ly = pya.Layout()
    ly.read(gds_path)

    # Flatten hierarchy 
    for c in ly.each_cell(): 
        for i in c.each_inst(): 
            i.flatten() 
    ly.cleanup()

    top_cells = ly.top_cells()

    # Write LEF file
    with open(out_file, "w") as file:
        # LEF header
        print("VERSION 5.7 ;", file=file)
        print("NOWIREEXTENSIONATPIN ON ;", file=file)
        print("DIVIDERCHAR \"/\" ;", file=file)
        print("BUSBITCHARS \"[]\" ;", file=file)
        print("", file=file)
        
        for top_cell in top_cells:
            if top_cell.name in ignore_cells:
                continue
                
            print("MACRO " + top_cell.name, file=file)
            print("\tCLASS BLOCK ;", file=file)  # Changed from CORE to BLOCK for analog
            print("\tORIGIN 0 0 ;", file=file)
            print("\tFOREIGN " + top_cell.name + " 0 0 ;", file=file)
            print("\tSIZE " + str(top_cell.bbox().right/1000) + " BY " + str(top_cell.bbox().top/1000) + " ;", file=file)
            print("\tSYMMETRY X Y ;", file=file)
            print("", file=file)
            
            for key, value in layers.items():
                layer_number, datatype = value  
                layer_info = ly.layer(layer_number, datatype)
                pins = []
                rectangles = []
                polygons = []
                
                # Check if this layer should be treated as a blockage layer
                if key in blockage_layers:
                    # For blockage layers, calculate single bounding box
                    bbox = get_layer_bounding_box(top_cell.shapes(layer_info))
                    if bbox is not None:
                        rectangles = [bbox]  # Single rectangle encompassing all shapes
                else:
                    # For regular layers, process all individual shapes
                    for shape in top_cell.shapes(layer_info):     
                        if shape.is_polygon():
                            polygons.append([int(coord) for coord in re.split(r'[;,]', str(shape.polygon).replace('(', '').replace(')', ''))])                   
                        elif shape.is_box():
                            rectangles.append([shape.box.left, shape.box.bottom, shape.box.right, shape.box.top])                 
                        elif shape.is_path():
                            polygons.append([int(coord) for coord in re.split(r'[;,]', str(shape.path.polygon()).replace('(', '').replace(')', ''))])
                        elif shape.is_text():
                            position = shape.bbox().center()
                            x = position.x
                            y = position.y
                            pins.append((shape.text, x, y))

                # Process pins
                for pin in pins:
                    name, a, b = pin
                    print("\tPIN " + str(name.string), file=file)
                    print("\t\tDIRECTION INOUT ;", file=file)
                    print("\t\tUSE SIGNAL ;", file=file)
                    print("\t\tPORT", file=file)
                    print("\t\t\tLAYER " + key + " ;", file=file)

                    index = point_in_rectangle(pin, rectangles)
                    if index != -1:
                        rect = rectangles.pop(index)
                        print("\t\t\tRECT " + str(rect[0]/1000) + " " + str(rect[1]/1000) + " " + str(rect[2]/1000) + " " + str(rect[3]/1000) + " ;", file=file)
                    else:
                        for i in range(len(polygons)):
                            if point_in_polygon(pin, polygons[i]):
                                polygon = polygons.pop(i)
                                file.write("\t\t\tPOLYGON ") 
                                for coord in polygon:
                                    file.write(str(coord/1000) + " ")
                                print(";", file=file)
                                break
                                
                    print("\t\tEND", file=file)  
                    print("\tEND " + str(name.string), file=file)
                    print("", file=file)

                # Add remaining shapes as obstructions
                if len(rectangles) > 0 or len(polygons) > 0:
                    print("\tOBS", file=file)
                    print("\t\tLAYER " + key + " ;", file=file)
                    for rect in rectangles:
                        print("\t\t\tRECT " + str(rect[0]/1000) + " " + str(rect[1]/1000) + " " + str(rect[2]/1000) + " " + str(rect[3]/1000) + " ;", file=file)
                    for polygon in polygons:
                        file.write("\t\t\tPOLYGON ") 
                        for coord in polygon:
                            file.write(str(coord/1000) + " ")
                        print(";", file=file)
                    print("\tEND", file=file)
                    print("", file=file)
                        
            print("END " + top_cell.name, file=file)
            print("", file=file)
            
        print("END LIBRARY", file=file)

if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: python gds2lef_standalone.py <input.gds> <output.lef> [blockage_layers]")
        print("  blockage_layers: comma-separated list of layer names to export as single blockage rectangles")
        print("  Example: python gds2lef_standalone.py input.gds output.lef VIA4,VIA5,M5")
        sys.exit(1)
    
    gds_path = sys.argv[1]
    out_file = sys.argv[2]
    
    custom_blockage_layers = None
    if len(sys.argv) == 4:
        # Parse comma-separated blockage layers
        custom_blockage_layers = set(layer.strip() for layer in sys.argv[3].split(','))
        print(f"Using custom blockage layers: {custom_blockage_layers}")
    
    try:
        convert_gds_to_lef(gds_path, out_file, custom_blockage_layers)
        print(f"Successfully converted {gds_path} to {out_file}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)