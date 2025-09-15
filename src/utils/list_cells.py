#!/usr/bin/env python3

import klayout.db as db
import sys
import os

def list_gds_cells(gds_file):
    layout = db.Layout()
    layout.read(gds_file)
    
    # Create output filename
    base_name = os.path.splitext(gds_file)[0]
    output_file = base_name + ".txt"
    
    # Collect cell names
    cells = [cell.name for cell in layout.each_cell()]
    
    # Write to stdout
    print(f"Cells in {gds_file}:")
    for cell_name in cells:
        print(cell_name)
    
    # Write to file
    with open(output_file, 'w') as f:
        f.write(f"Cells in {gds_file}:\n")
        for cell_name in cells:
            f.write(cell_name + "\n")
    
    print(f"\nCell list written to: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_cells.py <gds_file>")
        sys.exit(1)
    
    gds_file = sys.argv[1]
    list_gds_cells(gds_file)