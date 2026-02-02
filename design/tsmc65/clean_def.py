#!/usr/bin/env python3
"""
clean_def.py - Replace single-cut vias with multi-cut vias for large buffer cells

This script fixes DRC violations (VIA1.R.4:M1 and VIA1.R.2__VIA1.R.3) by replacing
VIA12_1cut_V with VIA12_2cut_E/W/N/S on the output pins of large buffer cells.

Usage:
    python3 clean_def.py <input.def> <backup.def> <output.def>
    python3 clean_def.py -check <input.def>

Example (fix mode):
    python3 clean_def.py 6_final.def 6_badvia.def 6_final.def

Example (check mode - report issues without fixing):
    python3 clean_def.py -check 6_final.def

Fix mode:
    1. Read from input.def
    2. Copy input.def to backup.def
    3. Write cleaned version to output.def

Check mode:
    Reports all single-cut vias that should be multi-cut without modifying files.
"""

import sys
import re
import os
import shutil
from typing import List, Dict, Set, Tuple

# List of cell types that require multi-cut vias (width > 0.3 µm on output pins)
TARGET_CELLS = {
    "BUFFD6LVT",
    "BUFFD8LVT",
    "BUFFD12LVT",
    "BUFFD16LVT",
    "CKBD6LVT",
    "CKBD8LVT",
    "CKBD12LVT",
    "CKBD16LVT",
    "INVD6LVT",
    "INVD8LVT",
    "INVD12LVT",
    "INVD16LVT",
}


def parse_def_file(filepath: str) -> List[str]:
    """Read the DEF file into memory as a list of lines."""
    with open(filepath, "r") as f:
        return f.readlines()


def find_target_instances(
    lines: List[str],
) -> Tuple[Dict[str, str], Dict[str, Tuple[int, int]]]:
    """
    Find all instances of target cell types in the COMPONENTS section.

    Returns:
        Tuple of (cell_types dict, cell_locations dict)
        - cell_types: instance_name -> cell_type
        - cell_locations: instance_name -> (x, y) in DEF units
    """
    cell_types = {}
    cell_locations = {}
    in_components = False

    for line in lines:
        if line.strip().startswith("COMPONENTS"):
            in_components = True
            continue
        elif line.strip().startswith("END COMPONENTS"):
            in_components = False
            break

        if in_components and line.strip().startswith("-"):
            # Parse component line: - instance_name cell_type + ... PLACED ( x y ) orientation
            match = re.match(r"\s*-\s+(\S+)\s+(\S+)", line)
            if match:
                instance_name = match.group(1)
                cell_type = match.group(2)
                if cell_type in TARGET_CELLS:
                    cell_types[instance_name] = cell_type

                    # Extract placement coordinates
                    placement_match = re.search(
                        r"PLACED\s+\(\s*(\d+)\s+(\d+)\s*\)", line
                    )
                    if placement_match:
                        x = int(placement_match.group(1))
                        y = int(placement_match.group(2))
                        cell_locations[instance_name] = (x, y)

    return cell_types, cell_locations


def find_nets_with_target_outputs(
    lines: List[str], target_instances: Dict[str, str]
) -> Set[str]:
    """
    Find all nets connected to the Z (output) pins of target instances.

    Returns:
        Set of net names
    """
    target_nets = set()
    in_nets = False
    current_net = None
    current_net_lines = []

    for line in lines:
        if line.strip().startswith("NETS"):
            in_nets = True
            continue
        elif line.strip().startswith("END NETS"):
            # Check the last net
            if current_net and current_net_lines:
                net_text = " ".join(current_net_lines)
                for instance_name in target_instances:
                    if f"( {instance_name} Z )" in net_text:
                        target_nets.add(current_net)
                        break
            break

        if in_nets:
            # Start of a new net: - netname ( ... ) ( ... )
            if line.strip().startswith("-"):
                # Process previous net if any
                if current_net and current_net_lines:
                    net_text = " ".join(current_net_lines)
                    for instance_name in target_instances:
                        if f"( {instance_name} Z )" in net_text:
                            target_nets.add(current_net)
                            break

                # Start new net
                match = re.match(r"\s*-\s+(\S+)", line)
                if match:
                    current_net = match.group(1)
                    current_net_lines = [line]
            elif current_net:
                # Continuation line of current net
                current_net_lines.append(line)

    return target_nets


def is_via_near_cell(
    via_x: int, via_y: int, cell_x: int, cell_y: int, max_distance_um: float = 3.0
) -> bool:
    """
    Check if a via is within max_distance of a cell's origin.

    Args:
        via_x, via_y: Via coordinates in DEF units
        cell_x, cell_y: Cell placement coordinates in DEF units
        max_distance_um: Maximum distance in micrometers

    Returns:
        True if via is within distance of cell
    """
    # Convert to micrometers
    via_x_um = via_x / 2000.0
    via_y_um = via_y / 2000.0
    cell_x_um = cell_x / 2000.0
    cell_y_um = cell_y / 2000.0

    # Calculate distance
    dx = via_x_um - cell_x_um
    dy = via_y_um - cell_y_um
    distance = (dx * dx + dy * dy) ** 0.5

    return distance <= max_distance_um


def determine_via_orientation(
    lines: List[str], line_idx: int, via_x: int, via_y: int
) -> str:
    """
    Determine the orientation of the via based on surrounding metal routing.

    Looks at the nearby routing statements to determine if the metal is running
    horizontally (use E/W) or vertically (use N/S).

    Args:
        lines: Full DEF file lines
        line_idx: Index of the line containing the via
        via_x, via_y: Coordinates of the via in DEF units

    Returns:
        'E', 'W', 'N', or 'S' for the via orientation
    """
    # Look at the current line and nearby lines for routing information
    # Check for ROUTED or NEW statements with coordinate patterns

    # Look backwards and forwards a few lines to find metal routing
    search_range = 5
    metal_segments = []

    for offset in range(-search_range, search_range + 1):
        idx = line_idx + offset
        if idx < 0 or idx >= len(lines):
            continue

        line = lines[idx]

        # Match patterns like: NEW M1 ( x1 y1 ) ( x2 y2 )
        # or: ROUTED M1 ( x1 y1 ) ( x2 y2 )
        # or: NEW M1 ( x y ) ( * y2 )  [vertical]
        # or: NEW M1 ( x y ) ( x2 * )  [horizontal]

        coord_pattern = r"(ROUTED|NEW)\s+M[12]\s+\(\s*(\d+|\*)\s+(\d+|\*)\s*\)\s*\(\s*(\d+|\*)\s+(\d+|\*)"
        match = re.search(coord_pattern, line)
        if match:
            x1_str, y1_str, x2_str, y2_str = (
                match.group(2),
                match.group(3),
                match.group(4),
                match.group(5),
            )

            # Convert to int, treating * as the current coordinate
            try:
                x1 = via_x if x1_str == "*" else int(x1_str)
                y1 = via_y if y1_str == "*" else int(y1_str)
                x2 = via_x if x2_str == "*" else int(x2_str)
                y2 = via_y if y2_str == "*" else int(y2_str)

                # Check if this segment is near our via
                tolerance = 10000  # 5 µm tolerance in DEF units (2000 units/µm)
                if abs(x1 - via_x) < tolerance and abs(y1 - via_y) < tolerance:
                    metal_segments.append((x1, y1, x2, y2))
                elif abs(x2 - via_x) < tolerance and abs(y2 - via_y) < tolerance:
                    metal_segments.append((x1, y1, x2, y2))
            except ValueError:
                continue

    # Analyze segments to determine predominant direction
    horizontal_score = 0
    vertical_score = 0

    for x1, y1, x2, y2 in metal_segments:
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dx > dy:
            horizontal_score += 1
        elif dy > dx:
            vertical_score += 1

    # Choose orientation based on routing direction
    # For horizontal routing, use E/W; for vertical, use N/S
    if horizontal_score > vertical_score:
        # Horizontal - use E or W (E is default, placing cuts to the east)
        return "E"
    elif vertical_score > horizontal_score:
        # Vertical - use N or S (N is default, placing cuts to the north)
        return "N"
    else:
        # Default to E if unclear
        return "E"


def replace_vias_in_nets(
    lines: List[str],
    target_nets: Set[str],
    target_instances: Dict[str, str],
    cell_locations: Dict[str, Tuple[int, int]],
) -> Tuple[List[str], int]:
    """
    Replace VIA12_1cut_V with VIA12_2cut_E/W/N/S in the target nets.

    Returns:
        Tuple of (modified lines, number of replacements)
    """
    modified_lines = []
    in_nets = False
    in_target_net = False
    current_net_source = None  # Track which cell/terminal is the source
    current_net_lines = []
    replacements = 0

    for idx, line in enumerate(lines):
        if line.strip().startswith("NETS"):
            in_nets = True
            modified_lines.append(line)
            continue
        elif line.strip().startswith("END NETS"):
            in_nets = False
            modified_lines.append(line)
            continue

        if in_nets:
            # Check if starting a new net
            if line.strip().startswith("-"):
                match = re.match(r"\s*-\s+(\S+)", line)
                if match:
                    net_name = match.group(1)
                    in_target_net = net_name in target_nets

                    # Find which target instance's Z pin is the source
                    # We need to check the full net definition, so start collecting lines
                    current_net_source = None
                    current_net_lines = [line]
                    if in_target_net:
                        # Check this line first
                        for instance_name in target_instances:
                            if f"( {instance_name} Z )" in line:
                                current_net_source = instance_name
                                break
            elif in_target_net and not line.strip().startswith(";"):
                # Continuation line - check for Z pin if we haven't found it yet
                current_net_lines.append(line)
                if not current_net_source:
                    for instance_name in target_instances:
                        if f"( {instance_name} Z )" in line:
                            current_net_source = instance_name
                            break

            # If we're in a target net, look for VIA12_1cut_V and replace it
            if in_target_net and "VIA12_1cut_V" in line:
                # Extract via coordinates
                # Pattern: NEW M1 ( x y ) VIA12_1cut_V
                coord_match = re.search(
                    r"M1\s+\(\s*(\d+)\s+(\d+)\s*\)\s+VIA12_1cut_V", line
                )
                if coord_match:
                    via_x = int(coord_match.group(1))
                    via_y = int(coord_match.group(2))

                    # Only process vias that are near the source cell's output pin
                    if current_net_source and current_net_source in cell_locations:
                        cell_x, cell_y = cell_locations[current_net_source]
                        if not is_via_near_cell(via_x, via_y, cell_x, cell_y):
                            # Via is too far from cell - skip it
                            modified_lines.append(line)
                            continue

                    # Convert DEF units to micrometers (DEF uses 2000 units per micrometer)
                    via_x_um = via_x / 2000.0
                    via_y_um = via_y / 2000.0

                    # Determine orientation
                    orientation = determine_via_orientation(lines, idx, via_x, via_y)

                    # Replace via
                    old_via = "VIA12_1cut_V"
                    new_via = f"VIA12_2cut_{orientation}"
                    modified_line = line.replace(old_via, new_via)
                    modified_lines.append(modified_line)

                    # Print replacement info
                    cell_name = current_net_source if current_net_source else "unknown"
                    cell_type = (
                        target_instances.get(current_net_source, "unknown")
                        if current_net_source
                        else "unknown"
                    )
                    line_num = idx + 1  # Convert to 1-based line numbering
                    print(
                        f"[INFO] Line {line_num}: Replacing {old_via} on terminal Z of cell {cell_name} ({cell_type}) at ({via_x}, {via_y}) DBU ({via_x_um:.3f}, {via_y_um:.3f}) um with {new_via}"
                    )

                    replacements += 1
                    continue

        modified_lines.append(line)

    return modified_lines, replacements


def check_vias_in_nets(
    lines: List[str],
    target_nets: Set[str],
    target_instances: Dict[str, str],
    cell_locations: Dict[str, Tuple[int, int]],
) -> int:
    """
    Check for single-cut vias in target nets without modifying the file.

    Returns:
        Number of issues found
    """
    in_nets = False
    in_target_net = False
    current_net_source = None
    current_net_lines = []
    issues = 0

    for idx, line in enumerate(lines):
        if line.strip().startswith("NETS"):
            in_nets = True
            continue
        elif line.strip().startswith("END NETS"):
            break

        if in_nets:
            # Check if starting a new net
            if line.strip().startswith("-"):
                match = re.match(r"\s*-\s+(\S+)", line)
                if match:
                    net_name = match.group(1)
                    in_target_net = net_name in target_nets

                    # Find which target instance's Z pin is the source
                    # We need to check the full net definition, so start collecting lines
                    current_net_source = None
                    current_net_lines = [line]
                    if in_target_net:
                        # Check this line first
                        for instance_name in target_instances:
                            if f"( {instance_name} Z )" in line:
                                current_net_source = instance_name
                                break
            elif in_target_net and not line.strip().startswith(";"):
                # Continuation line - check for Z pin if we haven't found it yet
                current_net_lines.append(line)
                if not current_net_source:
                    for instance_name in target_instances:
                        if f"( {instance_name} Z )" in line:
                            current_net_source = instance_name
                            break

            # If we're in a target net, look for VIA12_1cut_V
            if in_target_net and "VIA12_1cut_V" in line:
                coord_match = re.search(
                    r"M1\s+\(\s*(\d+)\s+(\d+)\s*\)\s+VIA12_1cut_V", line
                )
                if coord_match:
                    via_x = int(coord_match.group(1))
                    via_y = int(coord_match.group(2))

                    # Only process vias that are near the source cell's output pin
                    if current_net_source and current_net_source in cell_locations:
                        cell_x, cell_y = cell_locations[current_net_source]
                        if not is_via_near_cell(via_x, via_y, cell_x, cell_y):
                            # Via is too far from cell - skip it
                            continue

                    # Convert DEF units to micrometers (DEF uses 2000 units per micrometer)
                    via_x_um = via_x / 2000.0
                    via_y_um = via_y / 2000.0

                    cell_name = current_net_source if current_net_source else "unknown"
                    cell_type = (
                        target_instances.get(current_net_source, "unknown")
                        if current_net_source
                        else "unknown"
                    )
                    line_num = idx + 1
                    print(
                        f"[WARNING] Line {line_num}: Found insufficient VIA12_1cut_V connected to terminal Z of cell {cell_name} ({cell_type}) at ({via_x}, {via_y}) DBU ({via_x_um:.3f}, {via_y_um:.3f}) um"
                    )
                    issues += 1

    return issues


def write_def_file(filepath: str, lines: List[str]):
    """Write the modified DEF file."""
    with open(filepath, "w") as f:
        f.writelines(lines)


def main():
    # Check for -check mode
    check_mode = False
    if len(sys.argv) == 3 and sys.argv[1] == "-check":
        check_mode = True
        input_file = sys.argv[2]
    elif len(sys.argv) == 4:
        check_mode = False
        input_file = sys.argv[1]
        backup_file = sys.argv[2]
        output_file = sys.argv[3]
    else:
        print("Usage:")
        print(
            "  Fix mode:   python3 clean_def.py <input.def> <backup.def> <output.def>"
        )
        print("  Check mode: python3 clean_def.py -check <input.def>")
        print("")
        print("Examples:")
        print("  python3 clean_def.py 6_final.def 6_badvia.def 6_final.def")
        print("  python3 clean_def.py -check 6_final.def")
        sys.exit(1)

    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    if check_mode:
        # CHECK MODE - Report issues without fixing
        print(f"Running in CHECK mode on: {input_file}")
        print(f"Reading DEF file: {input_file}")
        lines = parse_def_file(input_file)
        print(f"  Total lines: {len(lines)}")

        print("\nFinding target cell instances...")
        target_instances, cell_locations = find_target_instances(lines)
        print(f"  Found {len(target_instances)} instances of target cells:")
        cell_counts = {}
        for inst, cell in target_instances.items():
            cell_counts[cell] = cell_counts.get(cell, 0) + 1
        for cell, count in sorted(cell_counts.items()):
            print(f"    {cell}: {count}")

        print("\nFinding nets connected to target outputs...")
        target_nets = find_nets_with_target_outputs(lines, target_instances)
        print(f"  Found {len(target_nets)} nets connected to target cell outputs")

        print("\nChecking for insufficient vias...")
        issues = check_vias_in_nets(
            lines, target_nets, target_instances, cell_locations
        )

        print("\nCheck complete!")
        print(f"  Total issues found: {issues}")
        if issues > 0:
            print("  Run without -check flag to fix these issues.")
    else:
        # FIX MODE - Backup, fix, and write output
        print("Backing up original DEF file...")
        print(f"  {input_file} -> {backup_file}")
        shutil.copy2(input_file, backup_file)

        print(f"\nReading DEF file: {input_file}")
        lines = parse_def_file(input_file)
        print(f"  Total lines: {len(lines)}")

        print("\nFinding target cell instances...")
        target_instances, cell_locations = find_target_instances(lines)
        print(f"  Found {len(target_instances)} instances of target cells:")
        cell_counts = {}
        for inst, cell in target_instances.items():
            cell_counts[cell] = cell_counts.get(cell, 0) + 1
        for cell, count in sorted(cell_counts.items()):
            print(f"    {cell}: {count}")

        print("\nFinding nets connected to target outputs...")
        target_nets = find_nets_with_target_outputs(lines, target_instances)
        print(f"  Found {len(target_nets)} nets connected to target cell outputs")

        print("\nReplacing VIA12_1cut_V with VIA12_2cut_* in target nets...")
        modified_lines, replacements = replace_vias_in_nets(
            lines, target_nets, target_instances, cell_locations
        )
        print(f"\n  Total replaced: {replacements} vias")

        print(f"\nWriting cleaned DEF file: {output_file}")
        write_def_file(output_file, modified_lines)

        print("\nDone!")
        print(f"  Backup:  {backup_file}")
        print(f"  Output:  {output_file}")
        print(f"  Vias replaced: {replacements}")


if __name__ == "__main__":
    main()
