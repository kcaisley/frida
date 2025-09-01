#!/usr/bin/env python3

"""Test script to verify layer mapping functionality."""

import klayout.db as db
from utils.layers import load_layers_from_lyt

def test_layer_mapping():
    """Test the KLayout technology layer mapping."""
    
    # Create a test layout
    ly = db.Layout()
    ly.dbu = 0.001  # 1nm database units
    
    # Load technology and layers
    lyt_file_path = "./tech/tsmc65/tsmc65.lyt"
    layers = load_layers_from_lyt(ly, lyt_file_path)
    
    print(f"Loaded {len(layers)} layers from technology")
    
    # Test key layers we need
    key_layers = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'VIA4', 'VIA5', 'M4.PIN', 'M6.PIN']
    print("\nKey layer mapping:")
    for layer_name in key_layers:
        if layer_name in layers:
            layer_obj = layers[layer_name]
            print(f"  ✓ {layer_name}: layer {layer_obj}")
        else:
            print(f"  ✗ {layer_name}: not found")
    
    # Create a simple test cell with shapes on different layers
    test_cell = ly.create_cell("test_layers")
    
    # Add test shapes
    for layer_name in ['M1', 'M4', 'M5', 'M6']:
        if layer_name in layers:
            layer_obj = layers[layer_name]
            # Create a simple rectangle
            rect = db.DBox(0, 0, 1, 1)
            test_cell.shapes(layer_obj).insert(rect)
            print(f"  Added rectangle on {layer_name}")
    
    # Write test GDS
    test_gds = "/tmp/test_layers.gds"
    ly.write(test_gds)
    print(f"\nWrote test GDS: {test_gds}")
    
    return True

if __name__ == "__main__":
    test_layer_mapping()
    print("Test completed successfully!")