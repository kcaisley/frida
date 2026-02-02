#!/usr/bin/env python3
"""
Reorder CDL .SUBCKT ports to match Verilog module definition.
Reads the Verilog module header, extracts ports in declaration order,
expands buses, and generates .SUBCKT and *.PININFO lines.

Usage: reorder_subckt_ports.py <verilog_file> <input_cdl> <output_cdl> <module_name>
"""

import re
import sys


def parse_verilog_ports(verilog_path, module_name):
    """Parse Verilog module and return ordered list of ports with directions."""
    with open(verilog_path, "r") as f:
        verilog = f.read()

    # Extract module definition (from 'module' to ');')
    module_pattern = rf"module\s+{module_name}\s*\((.*?)\);"
    module_match = re.search(module_pattern, verilog, re.DOTALL)
    if not module_match:
        print(f"ERROR: Could not find module {module_name}")
        sys.exit(1)

    module_body = module_match.group(1)

    # Parse port declarations
    ports = []
    pininfo = []

    # Remove comments but keep ifdef USE_POWER_PINS blocks for parsing
    lines = module_body.split("\n")
    filtered_lines = []
    in_power_pins_ifdef = False

    for line in lines:
        # Remove line comments
        line = re.sub(r"//.*", "", line)

        # Handle ifdef blocks - keep USE_POWER_PINS, skip others
        if "`ifdef USE_POWER_PINS" in line:
            in_power_pins_ifdef = True
            continue
        if in_power_pins_ifdef and "`endif" in line:
            in_power_pins_ifdef = False
            continue

        # Keep lines inside USE_POWER_PINS ifdef, skip leading comma
        if in_power_pins_ifdef:
            line = re.sub(r"^\s*,\s*", "", line)  # Remove leading comma

        filtered_lines.append(line)

    text = "\n".join(filtered_lines)

    # Find all port declarations: input/output/inout wire [range] name, name, ...
    # Use [^;\n] to avoid matching across lines
    port_pattern = r"(input|output|inout)\s+wire\s*(?:\[([^\]]+)\])?\s*([^;\n]+)"

    # Map direction to PININFO label
    dir_map = {"input": "I", "output": "O", "inout": "B"}

    for match in re.finditer(port_pattern, text):
        direction = match.group(1)
        bus_range = match.group(2)
        names_str = match.group(3)

        pin_dir = dir_map[direction]

        # Parse individual port names (may be comma-separated)
        # Split by comma and clean each name
        for name in names_str.split(","):
            # Remove any trailing comments, whitespace, and non-identifier chars
            name = re.sub(r"//.*", "", name).strip()
            # Extract just the identifier (alphanumeric and underscore)
            name_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)", name)
            if not name_match:
                continue
            name = name_match.group(1)

            # Skip Verilog keywords that might be captured
            if name in ("input", "output", "inout", "wire"):
                continue

            # Expand bus notation
            if bus_range:
                # Parse range like "15:0" or "179:0"
                range_match = re.match(r"(\d+):(\d+)", bus_range.strip())
                if range_match:
                    msb = int(range_match.group(1))
                    lsb = int(range_match.group(2))
                    # Expand in order (15 down to 0, or 0 up to 15)
                    if msb > lsb:
                        for i in range(msb, lsb - 1, -1):
                            ports.append(f"{name}[{i}]")
                            pininfo.append(f"{name}[{i}]:{pin_dir}")
                    else:
                        for i in range(msb, lsb + 1):
                            ports.append(f"{name}[{i}]")
                            pininfo.append(f"{name}[{i}]:{pin_dir}")
            else:
                # Scalar port
                ports.append(name)
                pininfo.append(f"{name}:{pin_dir}")

    return ports, pininfo


def clean_cdl_text(cdl_text):
    """Clean CDL text by removing fillers/decaps and fixing hierarchical separators."""
    # Step 1: Remove filler and decap instances
    # Filter out lines matching XFILLER with any of the filler/decap cell types
    # DECAP LIST: |DCAPLVT|DCAP4LVT|DCAP8LVT|DCAP16LVT|DCAP32LVT|DCAP64LVT|FILL1LVT
    filler_pattern = r"^XFILLER.*(FILL1LVT).*$"
    lines = cdl_text.split("\n")
    filtered_lines = [line for line in lines if not re.match(filler_pattern, line)]

    # Step 2: Clean hierarchical separators for Cadence SPICE-In compatibility
    # Process line by line to handle all separator replacements
    processed_lines = []
    for line in filtered_lines:
        # First remove backslashes and replace forward slashes
        line = line.replace("\\", "")
        line = line.replace("/", "_")

        # Then replace periods, but skip CDL/SPICE directive lines
        if not (line.strip().startswith(".") or line.strip().startswith("*.")):
            # For all other lines, replace periods with underscores
            # This affects instance names (X...) and net names in connections
            line = line.replace(".", "_")

            # Move array indices [#] to the end of net names
            # Cadence truncates at [ or <, so move indices to end
            # Match pattern: identifier[index]_rest_of_name
            # Replace with: identifier_rest_of_name[index]
            # Use regex to find all occurrences of [index] followed by underscore
            line = re.sub(r"(\w+)\[(\d+)\]_(\w+)", r"\1_\3[\2]", line)
            # Apply multiple times to handle multiple indices in same net name
            # e.g., name[15]_part1_part2 -> name_part1_part2[15]
            for _ in range(5):  # Max 5 levels of hierarchy
                line = re.sub(r"(\w+)\[(\d+)\]_(\w+)", r"\1_\3[\2]", line)

        processed_lines.append(line)

    cdl_text = "\n".join(processed_lines)

    # Clean up double underscores
    cdl_text = re.sub(r"__+", "_", cdl_text)

    return cdl_text


def reorder_cdl_subckt(input_cdl_path, output_cdl_path, module_name, ports, pininfo):
    """Replace .SUBCKT line in CDL with new port order and add *.PININFO."""
    with open(input_cdl_path, "r") as f:
        cdl = f.read()

    # Clean CDL text (remove fillers, fix separators)
    cdl = clean_cdl_text(cdl)

    # Build new .SUBCKT line (single line, all ports space-separated)
    new_subckt = f".SUBCKT {module_name} " + " ".join(ports)

    # Build *.PININFO line (single line, all pininfo space-separated)
    new_pininfo = "*.PININFO " + " ".join(pininfo)

    # Replace .SUBCKT line (from .SUBCKT to first instance line starting with X)
    subckt_pattern = rf"\.SUBCKT {module_name}\s+.*?(?=\nX)"
    cdl = re.sub(
        subckt_pattern,
        new_subckt + "\n" + new_pininfo + "\n",
        cdl,
        count=1,
        flags=re.DOTALL,
    )

    # Write to output file
    with open(output_cdl_path, "w") as f:
        f.write(cdl)

    print(f"Reordered .SUBCKT {module_name}: {len(ports)} ports in Verilog order")
    print("Cleaned fillers/decaps and hierarchical separators")
    print(f"Output written to: {output_cdl_path}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: reorder_subckt_ports.py <verilog_file> <input_cdl> <output_cdl> <module_name>"
        )
        sys.exit(1)

    verilog_path = sys.argv[1]
    input_cdl_path = sys.argv[2]
    output_cdl_path = sys.argv[3]
    module_name = sys.argv[4]

    ports, pininfo = parse_verilog_ports(verilog_path, module_name)
    reorder_cdl_subckt(input_cdl_path, output_cdl_path, module_name, ports, pininfo)
