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
    with open(verilog_path, 'r') as f:
        verilog = f.read()

    # Extract module definition (from 'module' to ');')
    module_pattern = rf'module\s+{module_name}\s*\((.*?)\);'
    module_match = re.search(module_pattern, verilog, re.DOTALL)
    if not module_match:
        print(f"ERROR: Could not find module {module_name}")
        sys.exit(1)

    module_body = module_match.group(1)

    # Parse port declarations
    ports = []
    pininfo = []

    # Remove comments but keep ifdef USE_POWER_PINS blocks for parsing
    lines = module_body.split('\n')
    filtered_lines = []
    in_power_pins_ifdef = False

    for line in lines:
        # Remove line comments
        line = re.sub(r'//.*', '', line)

        # Handle ifdef blocks - keep USE_POWER_PINS, skip others
        if '`ifdef USE_POWER_PINS' in line:
            in_power_pins_ifdef = True
            continue
        if in_power_pins_ifdef and '`endif' in line:
            in_power_pins_ifdef = False
            continue

        # Keep lines inside USE_POWER_PINS ifdef, skip leading comma
        if in_power_pins_ifdef:
            line = re.sub(r'^\s*,\s*', '', line)  # Remove leading comma

        filtered_lines.append(line)

    text = '\n'.join(filtered_lines)

    # Find all port declarations: input/output/inout wire [range] name, name, ...
    port_pattern = r'(input|output|inout)\s+wire\s*(?:\[([^\]]+)\])?\s*([^,;]+(?:,\s*[^,;]+)*)'

    # Map direction to PININFO label
    dir_map = {'input': 'I', 'output': 'O', 'inout': 'B'}

    for match in re.finditer(port_pattern, text):
        direction = match.group(1)
        bus_range = match.group(2)
        names = match.group(3)

        pin_dir = dir_map[direction]

        # Parse individual port names (may be comma-separated)
        for name in names.split(','):
            name = name.strip()
            if not name:
                continue

            # Expand bus notation
            if bus_range:
                # Parse range like "15:0" or "179:0"
                range_match = re.match(r'(\d+):(\d+)', bus_range.strip())
                if range_match:
                    msb = int(range_match.group(1))
                    lsb = int(range_match.group(2))
                    # Expand in order (15 down to 0, or 0 up to 15)
                    if msb > lsb:
                        for i in range(msb, lsb-1, -1):
                            ports.append(f'{name}[{i}]')
                            pininfo.append(f'{name}[{i}]:{pin_dir}')
                    else:
                        for i in range(msb, lsb+1):
                            ports.append(f'{name}[{i}]')
                            pininfo.append(f'{name}[{i}]:{pin_dir}')
            else:
                # Scalar port
                ports.append(name)
                pininfo.append(f'{name}:{pin_dir}')

    return ports, pininfo

def reorder_cdl_subckt(input_cdl_path, output_cdl_path, module_name, ports, pininfo):
    """Replace .SUBCKT line in CDL with new port order and add *.PININFO."""
    with open(input_cdl_path, 'r') as f:
        cdl = f.read()

    # Build new .SUBCKT line
    new_subckt = f'.SUBCKT {module_name}'
    for i in range(0, len(ports), 6):  # 6 ports per line for readability
        line_ports = ports[i:i+6]
        if i == 0:
            new_subckt += ' ' + ' '.join(line_ports)
        else:
            new_subckt += '\n+ ' + ' '.join(line_ports)

    # Build *.PININFO line
    new_pininfo = '*.PININFO'
    for i in range(0, len(pininfo), 4):  # 4 per line (they're longer with :I/:O/:B)
        line_info = pininfo[i:i+4]
        if i == 0:
            new_pininfo += ' ' + ' '.join(line_info)
        else:
            new_pininfo += '\n+ ' + ' '.join(line_info)

    # Replace .SUBCKT line (from .SUBCKT to first instance line starting with X)
    subckt_pattern = rf'\.SUBCKT {module_name}\s+.*?(?=\nX)'
    cdl = re.sub(
        subckt_pattern,
        new_subckt + '\n' + new_pininfo + '\n',
        cdl,
        count=1,
        flags=re.DOTALL
    )

    # Write to output file
    with open(output_cdl_path, 'w') as f:
        f.write(cdl)

    print(f"Reordered .SUBCKT {module_name}: {len(ports)} ports in Verilog order")

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: reorder_subckt_ports.py <verilog_file> <input_cdl> <output_cdl> <module_name>")
        sys.exit(1)

    verilog_path = sys.argv[1]
    input_cdl_path = sys.argv[2]
    output_cdl_path = sys.argv[3]
    module_name = sys.argv[4]

    ports, pininfo = parse_verilog_ports(verilog_path, module_name)
    reorder_cdl_subckt(input_cdl_path, output_cdl_path, module_name, ports, pininfo)
