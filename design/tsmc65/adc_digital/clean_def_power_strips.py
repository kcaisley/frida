#!/usr/bin/env python3
"""
Script to split M1 horizontal power stripes in DEF file to avoid analog macro regions.

This script reads a DEF file, identifies M1 FOLLOWPIN stripes that overlap with
analog macro blockage regions, and splits them into multiple segments that avoid
those regions.

Usage:
    python3 clean_def_power_strips.py <input_def_file>

The script will:
1. Rename the original DEF file to <basename>_badpdn.def
2. Create a new cleaned DEF file with the original name
"""

import sys
import re
import os
from typing import List, Tuple

# DBU conversion: 2000 DBU = 1 micrometer
DBU_PER_UM = 2000

# Define analog blockage regions (X ranges only, since M1 stripes are horizontal)
# Format: (x_min, x_max) in DBU
BLOCKAGE_X_RANGES = [
    (int(17.5 * DBU_PER_UM), int(42.5 * DBU_PER_UM)),  # Comparator: 17.5-42.5 µm
    (int(14.0 * DBU_PER_UM), int(21.0 * DBU_PER_UM)),  # Sampling switch 1: 14.0-21.0 µm
    (int(39.0 * DBU_PER_UM), int(46.0 * DBU_PER_UM)),  # Sampling switch 2: 39.0-46.0 µm
]

# Define Y range where blockages apply
# Extended to cover full height of analog macros including top rows
BLOCKAGE_Y_MIN = int(27.0 * DBU_PER_UM)  # 54000 DBU (27.0 µm)
BLOCKAGE_Y_MAX = int(60.0 * DBU_PER_UM)  # 120000 DBU (60.0 µm) - full die height

# Core X range (stripes currently go from 0 to 120000)
CORE_X_MIN = 0
CORE_X_MAX = int(60.0 * DBU_PER_UM)  # 120000 DBU


def parse_m1_followpin_line(line: str) -> Tuple[int, int, int, int, bool]:
    """
    Parse M1 FOLLOWPIN line to extract width and coordinates.

    Format: NEW M1 <width> + SHAPE FOLLOWPIN ( <x1> <y1> ) ( <x2> <y2> )
    Or:     + ROUTED M1 <width> + SHAPE FOLLOWPIN ( <x1> <y1> ) ( <x2> <y2> )

    Returns: (width, x1, y1, x2, is_routed) or None if not a valid M1 FOLLOWPIN line
             is_routed=True if line starts with "+ ROUTED"
    """
    # Try matching "+ ROUTED M1" pattern first
    routed_pattern = r'\+\s+ROUTED\s+M1\s+(\d+)\s+\+\s+SHAPE\s+FOLLOWPIN\s+\(\s*(\d+)\s+(\d+)\s*\)\s+\(\s*(\d+)\s+(\d+)\s*\)'
    match = re.search(routed_pattern, line)
    if match:
        width = int(match.group(1))
        x1 = int(match.group(2))
        y1 = int(match.group(3))
        x2 = int(match.group(4))
        y2 = int(match.group(5))
        if y1 == y2:
            return (width, x1, y1, x2, True)  # is_routed=True

    # Try matching "NEW M1" pattern
    new_pattern = r'NEW\s+M1\s+(\d+)\s+\+\s+SHAPE\s+FOLLOWPIN\s+\(\s*(\d+)\s+(\d+)\s*\)\s+\(\s*(\d+)\s+(\d+)\s*\)'
    match = re.search(new_pattern, line)
    if match:
        width = int(match.group(1))
        x1 = int(match.group(2))
        y1 = int(match.group(3))
        x2 = int(match.group(4))
        y2 = int(match.group(5))
        if y1 == y2:
            return (width, x1, y1, x2, False)  # is_routed=False

    return None


def compute_segments(y: int, x_min: int, x_max: int) -> List[Tuple[int, int]]:
    """
    Compute non-overlapping segments for a horizontal stripe at given Y coordinate.

    Args:
        y: Y coordinate of the stripe
        x_min: Starting X coordinate (typically 0)
        x_max: Ending X coordinate (typically 120000)

    Returns:
        List of (x_start, x_end) tuples representing segments that avoid blockages
    """
    # If stripe doesn't overlap with blockage Y range, return full stripe
    if y < BLOCKAGE_Y_MIN or y > BLOCKAGE_Y_MAX:
        return [(x_min, x_max)]

    # Sort blockages by x_min
    sorted_blockages = sorted(BLOCKAGE_X_RANGES, key=lambda b: b[0])

    segments = []
    current_x = x_min

    for blk_x_min, blk_x_max in sorted_blockages:
        # If there's space before this blockage, add a segment
        if current_x < blk_x_min:
            segments.append((current_x, blk_x_min))

        # Skip past the blockage
        if current_x < blk_x_max:
            current_x = blk_x_max

    # Add final segment from last blockage to end
    if current_x < x_max:
        segments.append((current_x, x_max))

    return segments


def create_m1_followpin_lines(width: int, y: int, segments: List[Tuple[int, int]], is_routed: bool = False) -> List[str]:
    """
    Create M1 FOLLOWPIN line(s) for the given segments.

    Args:
        width: Width of the stripe in DBU
        y: Y coordinate
        segments: List of (x_start, x_end) tuples
        is_routed: If True, first segment uses "+ ROUTED M1", otherwise "NEW M1"

    Returns:
        List of DEF lines (one per segment)
    """
    lines = []
    for i, (x_start, x_end) in enumerate(segments):
        if i == 0 and is_routed:
            # First segment of a ROUTED line keeps "+ ROUTED M1" format
            line = f"      + ROUTED M1 {width} + SHAPE FOLLOWPIN ( {x_start} {y} ) ( {x_end} {y} )\n"
        else:
            # All other segments use "NEW M1" format
            line = f"      NEW M1 {width} + SHAPE FOLLOWPIN ( {x_start} {y} ) ( {x_end} {y} )\n"
        lines.append(line)

    return lines


def process_def_file(input_path: str) -> None:
    """
    Process DEF file to split M1 power stripes around analog blockages.

    Args:
        input_path: Path to input DEF file
    """
    # Read the entire file
    with open(input_path, 'r') as f:
        lines = f.readlines()

    # No preprocessing needed - we'll handle + ROUTED lines specially during processing

    # Find SPECIALNETS section
    in_specialnets = False
    output_lines = []
    stripes_modified = 0
    stripes_created = 0

    for i, line in enumerate(lines):
        # Check if we're entering or leaving SPECIALNETS section
        if 'SPECIALNETS' in line and ';' in line:
            in_specialnets = True
            output_lines.append(line)
            continue

        if in_specialnets and 'END SPECIALNETS' in line:
            in_specialnets = False
            output_lines.append(line)
            continue

        # Try to parse as M1 FOLLOWPIN line
        if in_specialnets:
            result = parse_m1_followpin_line(line)
            if result:
                width, x1, y, x2, is_routed = result

                # Compute segments that avoid blockages
                segments = compute_segments(y, x1, x2)

                # If only one segment and it matches original, keep original line
                if len(segments) == 1 and segments[0] == (x1, x2):
                    output_lines.append(line)
                else:
                    # Create new lines for each segment, preserving + ROUTED format if needed
                    new_lines = create_m1_followpin_lines(width, y, segments, is_routed)
                    output_lines.extend(new_lines)
                    stripes_modified += 1
                    stripes_created += len(segments)

                    y_um = y / DBU_PER_UM
                    print(f"  Split stripe at Y={y} ({y_um:.1f}µm): {len(segments)} segments")
                    for j, (xs, xe) in enumerate(segments):
                        xs_um = xs / DBU_PER_UM
                        xe_um = xe / DBU_PER_UM
                        print(f"    Segment {j+1}: X={xs} to {xe} ({xs_um:.1f}µm to {xe_um:.1f}µm)")

                continue

        # Keep all other lines unchanged
        output_lines.append(line)

    # Create backup of original file
    backup_path = input_path.replace('.def', '_badpdn.def')
    print(f"\nRenaming original file to: {backup_path}")
    os.rename(input_path, backup_path)

    # Write modified content to original filename
    print(f"Writing cleaned DEF to: {input_path}")
    with open(input_path, 'w') as f:
        f.writelines(output_lines)

    print(f"\nSummary:")
    print(f"  Modified {stripes_modified} M1 power stripes")
    print(f"  Created {stripes_created} total segments")
    print(f"  Original file backed up to: {backup_path}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 clean_def_power_strips.py <input_def_file>")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    if not input_path.endswith('.def'):
        print("Warning: Input file doesn't have .def extension")

    print(f"Processing DEF file: {input_path}")
    print(f"\nBlockage regions (X ranges in DBU):")
    for i, (x_min, x_max) in enumerate(BLOCKAGE_X_RANGES, 1):
        x_min_um = x_min / DBU_PER_UM
        x_max_um = x_max / DBU_PER_UM
        print(f"  Blockage {i}: X={x_min} to {x_max} ({x_min_um:.1f}µm to {x_max_um:.1f}µm)")

    print(f"\nBlockage Y range: {BLOCKAGE_Y_MIN} to {BLOCKAGE_Y_MAX} ({BLOCKAGE_Y_MIN/DBU_PER_UM:.1f}µm to {BLOCKAGE_Y_MAX/DBU_PER_UM:.1f}µm)")
    print(f"\nProcessing M1 FOLLOWPIN stripes...\n")

    process_def_file(input_path)

    print("\nDone!")


if __name__ == '__main__':
    main()
