#!/usr/bin/env python3
"""
Run a single Spectre simulation with a specific DUT netlist.

This script takes a template Spectre netlist and substitutes in a specific
DUT netlist variant, then runs the simulation.

Usage:
    python run_single_sim.py \
        --template spice/tb_comp.sp \
        --dut results/comp_doubletail/comp_doubletail_tsmc65_v0001.sp \
        --outdir sim_results/comp_doubletail_v0001
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
import shutil


def generate_netlist_content(template_path: Path, dut_netlist: Path,
                            pdk_models: str, testbench_va: Path) -> str:
    """
    Generate netlist content with all paths substituted (in memory only).

    Args:
        template_path: Path to the template .sp file
        dut_netlist: Path to the specific DUT netlist to use
        pdk_models: Path to PDK models file
        testbench_va: Path to Verilog-A testbench

    Returns:
        Modified netlist content as string
    """
    with open(template_path, 'r') as f:
        content = f.read()

    # Replace placeholders
    content = content.replace('PLACEHOLDER_PDK_MODELS', str(pdk_models))
    content = content.replace('PLACEHOLDER_DUT_NETLIST', str(dut_netlist))
    content = content.replace('PLACEHOLDER_TESTBENCH_VA', str(testbench_va))

    return content


def run_spectre_simulation(netlist_content: str, output_dir: Path, log_file: Path,
                          working_dir: Path) -> subprocess.CompletedProcess:
    """
    Run Spectre simulation by piping netlist content via stdin.

    Args:
        netlist_content: Netlist content as string
        output_dir: Directory for simulation output
        log_file: Path to log file
        working_dir: Working directory for simulation

    Returns:
        CompletedProcess object with simulation results
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build Spectre command
    # - : Read netlist from stdin
    # -format nutbin: Save results in nutbin format
    # +log: Specify log file
    # -raw: Specify raw file directory
    cmd = [
        'spectre',
        '-',
        '+log', str(log_file),
        '-format', 'nutbin',
        '-raw', str(output_dir)
    ]

    print(f"\nRunning: {' '.join(cmd)}")
    print(f"Output directory: {output_dir}")
    print(f"Log file: {log_file}")
    print(f"Working directory: {working_dir}")
    print("-" * 60)

    # Run simulation with netlist piped via stdin
    try:
        result = subprocess.run(
            cmd,
            input=netlist_content,
            cwd=working_dir,
            capture_output=True,
            text=True
        )

        # Print stdout/stderr
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=sys.stderr)

        return result

    except FileNotFoundError:
        print("Error: 'spectre' command not found. Is Spectre in your PATH?")
        sys.exit(1)
    except Exception as e:
        print(f"Error running simulation: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Run a single Spectre simulation with a specific DUT netlist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python run_single_sim.py --template spice/tb_comp.sp --dut results/comp_doubletail/comp_doubletail_tsmc65_MNinp-MNinn-w2-typelvt_MNtail1-w2-l4.sp --pdk /path/to/pdk/models.scs --outdir results/comp_doubletail
        """
    )

    parser.add_argument(
        '-t', '--template',
        type=Path,
        required=True,
        help='Template Spectre netlist file (.sp)'
    )

    parser.add_argument(
        '-d', '--dut',
        type=Path,
        required=True,
        help='DUT netlist file to simulate (.sp)'
    )

    parser.add_argument(
        '--pdk',
        type=str,
        required=True,
        help='Path to PDK models file'
    )

    parser.add_argument(
        '--testbench',
        type=Path,
        default=Path('ahdl/tb_comp.va'),
        help='Path to Verilog-A testbench (default: ahdl/tb_comp.va)'
    )

    parser.add_argument(
        '-o', '--outdir',
        type=Path,
        required=True,
        help='Output directory for simulation results'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Create netlist but do not run simulation'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.template.exists():
        print(f"Error: Template file not found: {args.template}")
        sys.exit(1)

    if not args.dut.exists():
        print(f"Error: DUT netlist not found: {args.dut}")
        sys.exit(1)

    # Determine output names
    dut_name = args.dut.stem
    log_file = args.outdir / f"{dut_name}.log"

    print("=" * 60)
    print("Spectre Simulation Setup")
    print("=" * 60)
    print(f"Template:   {args.template}")
    print(f"DUT:        {args.dut}")
    print(f"PDK:        {args.pdk}")
    print(f"Testbench:  {args.testbench}")
    print(f"Output dir: {args.outdir}")
    print("=" * 60)

    # Generate netlist content in memory
    netlist_content = generate_netlist_content(args.template, args.dut, args.pdk, args.testbench)

    if args.dry_run:
        print("\nGenerated netlist (first 500 chars):")
        print("-" * 60)
        print(netlist_content[:500])
        print("-" * 60)
        print("\nDry run - simulation not started")
        return 0

    # Run simulation with netlist piped via stdin
    result = run_spectre_simulation(netlist_content, args.outdir, log_file, Path.cwd())

    # Report results
    print("\n" + "=" * 60)
    if result.returncode == 0:
        print("✓ Simulation completed successfully")
    else:
        print(f"✗ Simulation failed with return code {result.returncode}")
    print("=" * 60)

    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
