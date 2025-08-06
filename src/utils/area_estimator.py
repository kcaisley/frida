#!/usr/bin/env python3
"""
ASIC Area Estimator

Estimates total layout area for synthesized digital designs based on gate counts
and transistor-level modeling.

Usage: python area_estimator.py [stat_file]
   or: cat yosys_output.txt | python area_estimator.py

Author: Generated for FRIDA project
"""

import sys
import re
from typing import Dict, Tuple

# Transistor count models for different gate types
TRANSISTOR_COUNTS = {
    # Basic gates
    '$_NOT_': 2,        # Inverter: 1 PMOS + 1 NMOS
    '$_BUF_': 4,        # Buffer: 2 inverters
    '$_AND_': 6,        # AND: NAND + inverter
    '$_NAND_': 4,       # NAND: 2 PMOS + 2 NMOS
    '$_OR_': 6,         # OR: NOR + inverter
    '$_NOR_': 4,        # NOR: 2 PMOS + 2 NMOS
    '$_XOR_': 8,        # XOR: 8 transistors (transmission gates)
    '$_XNOR_': 10,      # XNOR: XOR + inverter
    '$_ANDNOT_': 6,     # AND-NOT: 6 transistors
    '$_ORNOT_': 6,      # OR-NOT: 6 transistors
    
    # Multiplexers
    '$_MUX_': 6,        # 2:1 MUX: 6 transistors (transmission gate based)
    '$_NMUX_': 8,       # Inverted MUX
    
    # Flip-flops (more complex, include clock buffers and feedback)
    '$_DFF_P_': 12,     # D-FF positive edge: ~12 transistors
    '$_DFF_N_': 12,     # D-FF negative edge: ~12 transistors
    '$_DFFE_PP_': 16,   # D-FF with enable: DFF + enable logic
    '$_DFFE_PN_': 16,   # D-FF with enable (neg enable)
    '$_DFFE_NP_': 16,   # D-FF with enable (neg clk)
    '$_DFFE_NN_': 16,   # D-FF with enable (neg clk, neg enable)
    
    # Latches
    '$_DLATCH_P_': 8,   # D-latch positive: ~8 transistors
    '$_DLATCH_N_': 8,   # D-latch negative: ~8 transistors
    
    # Complex gates
    '$_AOI3_': 6,       # AND-OR-INVERT 3-input
    '$_OAI3_': 6,       # OR-AND-INVERT 3-input
    '$_AOI4_': 8,       # AND-OR-INVERT 4-input
    '$_OAI4_': 8,       # OR-AND-INVERT 4-input
}

# Physical parameters
UNIT_TRANSISTOR_WIDTH = 100e-9   # 100 nm
UNIT_TRANSISTOR_HEIGHT = 150e-9  # 150 nm
LAYOUT_OVERHEAD = 0.30           # 30% overhead for routing, spacing, etc.

def parse_yosys_stats(text: str) -> Dict[str, int]:
    """Parse Yosys statistics output to extract gate counts."""
    gate_counts = {}
    
    # Look for the statistics section
    in_stats = False
    for line in text.split('\n'):
        line = line.strip()
        
        # Start of statistics section
        if 'Number of cells:' in line:
            in_stats = True
            continue
            
        # End of statistics section (empty line or next section)
        if in_stats and (not line or line.startswith('===')):
            break
            
        # Parse gate counts
        if in_stats and line:
            # Match pattern like: "     $_NAND_                         2"
            match = re.match(r'\s*(\$_\w+_)\s+(\d+)', line)
            if match:
                gate_type = match.group(1)
                count = int(match.group(2))
                gate_counts[gate_type] = count
    
    return gate_counts

def estimate_area(gate_counts: Dict[str, int]) -> Tuple[float, Dict[str, Tuple[int, float]]]:
    """
    Estimate total area based on gate counts.
    
    Returns:
        - Total area in square micrometers
        - Breakdown by gate type: {gate: (transistor_count, area_um2)}
    """
    
    unit_area = UNIT_TRANSISTOR_WIDTH * UNIT_TRANSISTOR_HEIGHT  # m²
    unit_area_um2 = unit_area * 1e12  # Convert to µm²
    
    total_transistors = 0
    breakdown = {}
    
    for gate_type, count in gate_counts.items():
        if gate_type in TRANSISTOR_COUNTS:
            transistors_per_gate = TRANSISTOR_COUNTS[gate_type]
            total_gate_transistors = transistors_per_gate * count
            gate_area_um2 = total_gate_transistors * unit_area_um2
            
            total_transistors += total_gate_transistors
            breakdown[gate_type] = (total_gate_transistors, gate_area_um2)
        else:
            print(f"Warning: Unknown gate type '{gate_type}', assuming 4 transistors", file=sys.stderr)
            transistors_per_gate = 4  # Default assumption
            total_gate_transistors = transistors_per_gate * count
            gate_area_um2 = total_gate_transistors * unit_area_um2
            
            total_transistors += total_gate_transistors
            breakdown[gate_type] = (total_gate_transistors, gate_area_um2)
    
    # Calculate areas
    core_area_um2 = total_transistors * unit_area_um2
    total_area_um2 = core_area_um2 * (1 + LAYOUT_OVERHEAD)
    
    return total_area_um2, breakdown

def print_area_report(gate_counts: Dict[str, int], total_area: float, breakdown: Dict[str, Tuple[int, float]]):
    """Print a detailed area estimation report."""
    
    print("=" * 70)
    print("ASIC AREA ESTIMATION REPORT")
    print("=" * 70)
    
    print(f"\nPhysical Parameters:")
    print(f"  Unit transistor: {UNIT_TRANSISTOR_WIDTH*1e9:.0f}nm × {UNIT_TRANSISTOR_HEIGHT*1e9:.0f}nm")
    print(f"  Unit area: {UNIT_TRANSISTOR_WIDTH*1e9:.0f} × {UNIT_TRANSISTOR_HEIGHT*1e9:.0f} = {UNIT_TRANSISTOR_WIDTH*UNIT_TRANSISTOR_HEIGHT*1e18:.0f} nm²")
    print(f"  Layout overhead: {LAYOUT_OVERHEAD*100:.0f}%")
    
    print(f"\nGate Count Analysis:")
    print(f"{'Gate Type':<15} {'Count':<8} {'Trans/Gate':<12} {'Total Trans':<12} {'Area (µm²)':<12}")
    print("-" * 70)
    
    total_gates = 0
    total_transistors = 0
    core_area = 0
    
    for gate_type, count in gate_counts.items():
        total_gates += count
        if gate_type in breakdown:
            transistor_count, area = breakdown[gate_type]
            trans_per_gate = TRANSISTOR_COUNTS.get(gate_type, 4)
            total_transistors += transistor_count
            core_area += area
            print(f"{gate_type:<15} {count:<8} {trans_per_gate:<12} {transistor_count:<12} {area:<12.3f}")
    
    print("-" * 70)
    print(f"{'TOTALS':<15} {total_gates:<8} {'':<12} {total_transistors:<12} {core_area:<12.3f}")
    
    print(f"\nArea Summary:")
    print(f"  Core area (transistors only): {core_area:.3f} µm²")
    print(f"  Layout overhead ({LAYOUT_OVERHEAD*100:.0f}%): {core_area*LAYOUT_OVERHEAD:.3f} µm²")
    print(f"  Total estimated area: {total_area:.3f} µm²")
    
    # Additional metrics
    print(f"\nAdditional Metrics:")
    print(f"  Area per transistor: {core_area/total_transistors:.6f} µm²/transistor")
    print(f"  Transistor density: {total_transistors/total_area:.0f} transistors/µm²")
    print(f"  Equivalent square die: {total_area**0.5:.1f} µm × {total_area**0.5:.1f} µm")

def print_help():
    """Print usage help and examples."""
    print("ASIC Area Estimator")
    print("=" * 50)
    print()
    print("Estimates total layout area for synthesized digital designs based on")
    print("gate counts and transistor-level modeling.")
    print()
    print("USAGE:")
    print("  python3 area_estimator.py [input_file]")
    print("  cat yosys_output.txt | python3 area_estimator.py")
    print()
    print("PARAMETERS:")
    print("  Unit transistor: 100nm × 150nm = 15,000 nm²")
    print("  Layout overhead: 30%")
    print()
    print("EXAMPLES:")
    print("  # From synthesis report file:")
    print("  python3 area_estimator.py synthesis_stats.txt")
    print()
    print("  # From Yosys synthesis output:")
    print("  make synth-gates mod=sar 2>&1 | python3 area_estimator.py")
    print()
    print("  # From direct Yosys command:")
    print("  yosys -s script.ys 2>&1 | python3 area_estimator.py")
    print()
    print("EXPECTED INPUT FORMAT (from Yosys 'stat' command):")
    print("   Number of cells:                 51")
    print("     $_NAND_                         2")
    print("     $_DFF_P_                       16")
    print("     $_NOR_                          4")
    print("     ...")
    print()

def main():
    """Main function - parse input and generate area report."""
    
    # Check if we need to show help
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        print_help()
        sys.exit(0)
    
    # Read input from file or stdin
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], 'r') as f:
                input_text = f.read()
        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found", file=sys.stderr)
            sys.exit(1)
    else:
        # Check if stdin has data
        if sys.stdin.isatty():
            print_help()
            sys.exit(0)
        input_text = sys.stdin.read()
    
    # Parse gate counts
    gate_counts = parse_yosys_stats(input_text)
    
    if not gate_counts:
        print("Error: No gate statistics found in input", file=sys.stderr)
        print("Expected format from Yosys 'stat' command:", file=sys.stderr)
        print("   Number of cells:                 51", file=sys.stderr)
        print("     $_NAND_                         2", file=sys.stderr)
        print("     $_DFF_P_                       16", file=sys.stderr)
        sys.exit(1)
    
    # Estimate area
    total_area, breakdown = estimate_area(gate_counts)
    
    # Print report
    print_area_report(gate_counts, total_area, breakdown)

if __name__ == "__main__":
    main()
