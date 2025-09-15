#!/usr/bin/env python3
"""
LEF Pin Legalization Checker for IHP-SG13G2

This script reads the technology LEF file and macro LEF cells, and ensures that
the pins are centered on the routing grid and satisfy minimum dimensions/area
requirements for the IHP-SG13G2 process.

Usage:
    python3 check_lef_pins.py <tech_lef> <macro_lef> [--fix]
"""

import sys
import re
import argparse
from pathlib import Path

class LEFParser:
    def __init__(self):
        self.tech_info = {}
        self.macros = {}

    def parse_tech_lef(self, tech_lef_path):
        """Parse technology LEF file to extract routing grid information."""
        print(f"Parsing technology LEF: {tech_lef_path}")

        with open(tech_lef_path, 'r') as f:
            content = f.read()

        # Extract layer information
        layer_blocks = re.findall(r'LAYER\s+(\w+)\s+.*?END\s+\1', content, re.DOTALL)

        for layer_match in re.finditer(r'LAYER\s+(\w+)\s+(.*?)END\s+\1', content, re.DOTALL):
            layer_name = layer_match.group(1)
            layer_content = layer_match.group(2)

            # Look for routing layers (Metal1, Metal2, etc.)
            if 'Metal' in layer_name or 'M' in layer_name:
                self.tech_info[layer_name] = {}

                # Extract pitch information
                pitch_match = re.search(r'PITCH\s+([\d.]+)(?:\s+([\d.]+))?', layer_content)
                if pitch_match:
                    x_pitch = float(pitch_match.group(1))
                    y_pitch = float(pitch_match.group(2)) if pitch_match.group(2) else x_pitch
                    self.tech_info[layer_name]['pitch'] = (x_pitch, y_pitch)

                # Extract width information
                width_match = re.search(r'WIDTH\s+([\d.]+)', layer_content)
                if width_match:
                    self.tech_info[layer_name]['width'] = float(width_match.group(1))

                # Extract spacing information
                spacing_match = re.search(r'SPACING\s+([\d.]+)', layer_content)
                if spacing_match:
                    self.tech_info[layer_name]['spacing'] = float(spacing_match.group(1))

        print(f"Found {len(self.tech_info)} routing layers")
        for layer, info in self.tech_info.items():
            print(f"  {layer}: {info}")

    def parse_macro_lef(self, macro_lef_path):
        """Parse macro LEF file to extract pin information."""
        print(f"Parsing macro LEF: {macro_lef_path}")

        with open(macro_lef_path, 'r') as f:
            content = f.read()

        # Extract macro blocks
        for macro_match in re.finditer(r'MACRO\s+(\w+)\s+(.*?)END\s+\1', content, re.DOTALL):
            macro_name = macro_match.group(1)
            macro_content = macro_match.group(2)

            self.macros[macro_name] = {
                'pins': {},
                'size': None
            }

            # Extract macro size
            size_match = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', macro_content)
            if size_match:
                self.macros[macro_name]['size'] = (float(size_match.group(1)), float(size_match.group(2)))

            # Extract pins
            for pin_match in re.finditer(r'PIN\s+(\w+)\s+(.*?)END\s+\1', macro_content, re.DOTALL):
                pin_name = pin_match.group(1)
                pin_content = pin_match.group(2)

                pin_info = {'layers': []}

                # Extract port information
                for port_match in re.finditer(r'PORT\s+(.*?)END', pin_content, re.DOTALL):
                    port_content = port_match.group(1)

                    # Extract layer and rectangle information
                    for layer_match in re.finditer(r'LAYER\s+(\w+)\s+;', port_content):
                        layer_name = layer_match.group(1)

                        # Find rectangles for this layer
                        rect_pattern = r'RECT\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+;'
                        for rect_match in re.finditer(rect_pattern, port_content):
                            x1, y1, x2, y2 = map(float, rect_match.groups())
                            pin_info['layers'].append({
                                'layer': layer_name,
                                'rect': (x1, y1, x2, y2)
                            })

                self.macros[macro_name]['pins'][pin_name] = pin_info

        print(f"Found {len(self.macros)} macros")
        for macro_name, macro_info in self.macros.items():
            print(f"  {macro_name}: {len(macro_info['pins'])} pins, size {macro_info['size']}")

    def check_pin_legalization(self):
        """Check if pins are properly aligned to routing grid."""
        issues = []

        for macro_name, macro_info in self.macros.items():
            print(f"\nChecking macro: {macro_name}")

            for pin_name, pin_info in macro_info['pins'].items():
                print(f"  Pin: {pin_name}")

                for layer_info in pin_info['layers']:
                    layer = layer_info['layer']
                    rect = layer_info['rect']
                    x1, y1, x2, y2 = rect

                    print(f"    Layer {layer}: RECT {x1} {y1} {x2} {y2}")

                    # Check if we have routing grid info for this layer
                    if layer not in self.tech_info:
                        issues.append(f"{macro_name}.{pin_name}: Layer {layer} not found in technology file")
                        continue

                    tech_layer = self.tech_info[layer]

                    if 'pitch' not in tech_layer:
                        issues.append(f"{macro_name}.{pin_name}: No pitch info for layer {layer}")
                        continue

                    x_pitch, y_pitch = tech_layer['pitch']

                    # Check grid alignment
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2

                    # Check if center is on grid
                    x_grid_error = center_x % x_pitch
                    y_grid_error = center_y % y_pitch

                    tolerance = 0.001  # 1nm tolerance

                    if x_grid_error > tolerance and (x_pitch - x_grid_error) > tolerance:
                        issues.append(f"{macro_name}.{pin_name}.{layer}: X center {center_x} not on {x_pitch} grid (error: {x_grid_error})")

                    if y_grid_error > tolerance and (y_pitch - y_grid_error) > tolerance:
                        issues.append(f"{macro_name}.{pin_name}.{layer}: Y center {center_y} not on {y_pitch} grid (error: {y_grid_error})")

                    # Check minimum width
                    width = x2 - x1
                    height = y2 - y1

                    if 'width' in tech_layer:
                        min_width = tech_layer['width']
                        if width < min_width:
                            issues.append(f"{macro_name}.{pin_name}.{layer}: Width {width} < minimum {min_width}")
                        if height < min_width:
                            issues.append(f"{macro_name}.{pin_name}.{layer}: Height {height} < minimum {min_width}")

                    # Check minimum area (approximate)
                    area = width * height
                    if area < 0.01:  # Minimum 0.01 square microns
                        issues.append(f"{macro_name}.{pin_name}.{layer}: Area {area} too small")

        return issues

    def generate_fixed_lef(self, macro_lef_path, output_path):
        """Generate a fixed LEF file with grid-aligned pins."""
        print(f"Generating fixed LEF: {output_path}")

        with open(macro_lef_path, 'r') as f:
            content = f.read()

        # This is a simplified fix - in practice, you'd need more sophisticated
        # grid snapping logic based on the specific issues found

        # For now, just copy the original file
        with open(output_path, 'w') as f:
            f.write(content)

        print("Note: Automatic fixing not fully implemented. Manual review required.")

def main():
    parser = argparse.ArgumentParser(description='Check LEF pin legalization for IHP-SG13G2')
    parser.add_argument('tech_lef', help='Path to technology LEF file')
    parser.add_argument('macro_lef', help='Path to macro LEF file')
    parser.add_argument('--fix', action='store_true', help='Generate fixed LEF file')

    args = parser.parse_args()

    if not Path(args.tech_lef).exists():
        print(f"Error: Technology LEF file not found: {args.tech_lef}")
        sys.exit(1)

    if not Path(args.macro_lef).exists():
        print(f"Error: Macro LEF file not found: {args.macro_lef}")
        sys.exit(1)

    # Parse LEF files
    parser = LEFParser()
    parser.parse_tech_lef(args.tech_lef)
    parser.parse_macro_lef(args.macro_lef)

    # Check for issues
    issues = parser.check_pin_legalization()

    if issues:
        print(f"\nFound {len(issues)} issues:")
        for issue in issues:
            print(f"  - {issue}")

        if args.fix:
            output_path = Path(args.macro_lef).with_suffix('.fixed.lef')
            parser.generate_fixed_lef(args.macro_lef, output_path)

        sys.exit(1)
    else:
        print("\nNo legalization issues found!")
        sys.exit(0)

if __name__ == '__main__':
    main()