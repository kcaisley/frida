import klayout.db as db
import re
import json
import copy
import sys
import os

errors = 0

tech_file = "./tech/tsmc65/tsmc65.lyt"
layer_map = ""

# Load technology file
tech = db.Technology()
tech.load(tech_file)
layoutOptions = tech.load_layout_options
if len(layer_map) > 0:
    layoutOptions.lefdef_config.map_file = layer_map

# Explore how to extract layer mapping from technology
print("Exploring layer mapping extraction from technology...")

# Try to get layer mapping through various approaches
print("\n1. Checking layer_map on load_layout_options:")
try:
    layer_map = layoutOptions.layer_map
    print(f"  layer_map: {layer_map}")
    if hasattr(layer_map, 'items'):
        for key, value in layer_map.items():
            print(f"    {key}: {value}")
except Exception as e:
    print(f"  Error: {e}")

print("\n2. Checking if we can set layer mapping and read it back:")
try:
    # Create a temporary layout to test layer mapping
    temp_ly = db.Layout()
    temp_ly.dbu = 0.001
    
    # Try to load with the technology layout options
    print("  Attempting to use technology layout options...")
    
except Exception as e:
    print(f"  Error: {e}")

print("\n3. Checking connectivity component for layer definitions:")
try:
    if 'connectivity' in tech.component_names():
        connectivity = tech.component('connectivity')
        print(f"  Connectivity component: {type(connectivity)}")
        for attr in sorted(dir(connectivity)):
            if not attr.startswith('_'):
                try:
                    val = getattr(connectivity, attr)
                    if not callable(val):
                        print(f"    {attr}: {val}")
                except:
                    print(f"    {attr}: <callable or inaccessible>")
except Exception as e:
    print(f"  Error: {e}")

print("\n4. Trying to read layer properties file:")
try:
    layer_props_file = tech.layer_properties_file
    print(f"  Layer properties file: {layer_props_file}")
    if layer_props_file:
        # The layer properties file might contain the layer mapping
        print("  Found layer properties file path")
except Exception as e:
    print(f"  Error: {e}")