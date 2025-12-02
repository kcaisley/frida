#!/usr/bin/env python3
"""
Run Spectre simulations using pre-generated testbench wrappers.

This script validates matching pairs of DUT netlists and testbench wrappers,
then runs Spectre simulations in parallel with license management.
"""

import argparse
import datetime
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from glob import glob
from pathlib import Path
from typing import List, Optional, Tuple


def check_license_server():
    """
    Check Spectre license server availability and parse license usage.

    Returns:
        Tuple of (total_licenses, busy_licenses) or None if server unavailable

    Raises:
        SystemExit: If CDS_LIC_FILE is not set or license server doesn't respond
    """
    # Check if CDS_LIC_FILE environment variable is set
    license_server = os.environ.get('CDS_LIC_FILE')
    if not license_server:
        print("ERROR: CDS_LIC_FILE environment variable is not set")
        print("Please set it with: export CDS_LIC_FILE=<port>@<server>")
        sys.exit(1)

    print(f"License server: {license_server}")

    # Run lmstat to check license availability
    try:
        result = subprocess.run(
            ['lmstat', '-c', license_server, '-a'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"ERROR: lmstat command failed with return code {result.returncode}")
            print(f"Output: {result.stderr}")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print("ERROR: License server check timed out after 10 seconds")
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: lmstat command not found. Please ensure Cadence tools are in PATH")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to check license server: {e}")
        sys.exit(1)

    # Parse lmstat output to find Spectre licenses
    # Look for lines like: "Users of Virtuoso_Multi_mode_Simulation:  (Total of 120 licenses issued;  Total of 23 licenses in use)"
    total_licenses = 0
    busy_licenses = 0

    for line in result.stdout.split('\n'):
        # Match the Spectre/Multi-mode simulation license
        if 'Virtuoso_Multi_mode_Simulation' in line or 'MMSIM' in line:
            # Parse: "Users of Virtuoso_Multi_mode_Simulation:  (Total of 120 licenses issued;  Total of 23 licenses in use)"
            import re
            issued_match = re.search(r'Total of (\d+) licenses? issued', line)
            in_use_match = re.search(r'Total of (\d+) licenses? in use', line)

            if issued_match:
                total_licenses = int(issued_match.group(1))
            if in_use_match:
                busy_licenses = int(in_use_match.group(1))

            break

    if total_licenses == 0:
        print("ERROR: Could not parse license information from lmstat output")
        print("Please check that the license server is configured correctly")
        sys.exit(1)

    print(f"Total licenses: {total_licenses}")
    print(f"Busy licenses: {busy_licenses}")

    return total_licenses, busy_licenses


def correct_spectre_raw(raw_file: Path) -> bool:
    """
    Fix Spectre .raw file header to be compatible with spicelib.
    Spectre puts the first variable on the same line as 'Variables:',
    but spicelib expects 'Variables:' on its own line.

    Args:
        raw_file: Path to the .raw file to fix

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(raw_file, 'rb') as f:
            content = f.read()

        # Find the header/binary split
        binary_marker = b'Binary:\n'
        if binary_marker not in content:
            return False

        header, binary_data = content.split(binary_marker, 1)
        header_text = header.decode('ascii', errors='ignore')

        # Fix the Variables: line
        lines = header_text.split('\n')
        fixed_lines = []

        for line in lines:
            if line.startswith('Variables:') and len(line.strip()) > len('Variables:'):
                # Split "Variables:    0    time    s" into two lines
                fixed_lines.append('Variables:')
                var_def = line[len('Variables:'):]
                fixed_lines.append(var_def)
            else:
                fixed_lines.append(line)

        # Reconstruct and write back
        fixed_header = '\n'.join(fixed_lines).encode('ascii')
        fixed_content = fixed_header + binary_marker + binary_data

        with open(raw_file, 'wb') as f:
            f.write(fixed_content)

        return True

    except Exception:
        return False


def run_spectre_simulation(tb_wrapper: Path, outdir: Path, spectre_path: str, license_server: str) -> Tuple[str, bool, float]:
    """
    Run a single Spectre simulation.

    Args:
        tb_wrapper: Path to testbench wrapper file
        outdir: Output directory
        spectre_path: Path to Spectre binary
        license_server: License server address

    Returns:
        Tuple of (name, success, elapsed_time)
    """
    start_time = time.time()
    name = tb_wrapper.stem

    # Output files
    log_file = outdir / f"{name}.log"
    raw_file = outdir / f"{name}.raw"

    # Run Spectre
    cmd = [
        spectre_path, '-64',
        tb_wrapper.name,  # Just the filename, since we're cd'd to outdir
        '+log', log_file.name,
        '-format', 'nutbin',
        '-raw', raw_file.name
    ]

    # Set up environment with license server
    env = os.environ.copy()
    env['CDS_LIC_FILE'] = license_server

    try:
        result = subprocess.run(
            cmd,
            cwd=str(outdir),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env
        )

        success = result.returncode == 0 and 'completes with 0 errors' in result.stdout
        elapsed = time.time() - start_time

        # Fix .raw file header for spicelib compatibility
        if success and raw_file.exists():
            correct_spectre_raw(raw_file)

        return name, success, elapsed

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return name, False, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return name, False, elapsed


def validate_matching_pairs(dut_netlists: List[Path], tb_wrappers: List[Path]) -> bool:
    """
    Validate that DUT netlists and testbench wrappers match.
    
    Args:
        dut_netlists: List of DUT netlist paths
        tb_wrappers: List of testbench wrapper paths
        
    Returns:
        True if validation passes, False otherwise
    """
    if len(dut_netlists) != len(tb_wrappers):
        print(f"Error: Mismatch in counts - {len(dut_netlists)} DUTs vs {len(tb_wrappers)} testbenches")
        return False
    
    # Extract base names (remove tb_ prefix from wrappers)
    dut_names = {f.stem for f in dut_netlists}
    tb_names = {f.stem.replace('tb_', '', 1) for f in tb_wrappers}
    
    if dut_names != tb_names:
        missing_in_tb = dut_names - tb_names
        missing_in_dut = tb_names - dut_names
        
        if missing_in_tb:
            print(f"Error: DUTs without testbenches: {missing_in_tb}")
        if missing_in_dut:
            print(f"Error: Testbenches without DUTs: {missing_in_dut}")
        return False
    
    return True


def main():
    """Main entry point for simulation runner."""
    parser = argparse.ArgumentParser(
        description='Run Spectre simulations using pre-generated testbench wrappers.',
        epilog='Example: %(prog)s --dut-netlists "results/samp_tgate/samp_tgate_*.sp" --tb-wrappers "results/samp_tgate/tb_samp_tgate_*.sp" -o results/samp_tgate'
    )
    
    parser.add_argument(
        '--dut-netlists',
        type=str,
        required=True,
        help='Glob pattern for DUT netlists (e.g., "results/samp_tgate/samp_tgate_*.sp")'
    )
    
    parser.add_argument(
        '--tb-wrappers',
        type=str,
        required=True,
        help='Glob pattern for testbench wrappers (e.g., "results/samp_tgate/tb_samp_tgate_*.sp")'
    )
    
    parser.add_argument(
        '-o', '--outdir',
        type=Path,
        required=True,
        help='Output directory for simulation results'
    )

    parser.add_argument(
        '--tech-filter',
        type=str,
        default='',
        help='Only run simulations for this technology (e.g., "tsmc65")'
    )

    parser.add_argument(
        '--license-server',
        type=str,
        required=True,
        help='License server address (e.g., "27500@nexus.physik.uni-bonn.de")'
    )

    parser.add_argument(
        '--spectre-path',
        type=str,
        required=True,
        help='Path to Spectre binary'
    )

    args = parser.parse_args()
    
    # Find all files
    dut_netlists = sorted([Path(f) for f in glob(args.dut_netlists)])
    tb_wrappers = sorted([Path(f) for f in glob(args.tb_wrappers)])
    
    if not dut_netlists:
        print(f"Error: No DUT netlists found matching: {args.dut_netlists}")
        sys.exit(1)
    
    if not tb_wrappers:
        print(f"Error: No testbench wrappers found matching: {args.tb_wrappers}")
        print(f"Did you run 'make testbench' first?")
        sys.exit(1)
    
    # Apply tech filter if specified
    if args.tech_filter:
        dut_netlists = [f for f in dut_netlists if args.tech_filter in f.name]
        tb_wrappers = [f for f in tb_wrappers if args.tech_filter in f.name]
        
        if not dut_netlists:
            print(f"No netlists match tech filter: {args.tech_filter}")
            sys.exit(1)
    
    # Validate matching pairs
    if not validate_matching_pairs(dut_netlists, tb_wrappers):
        sys.exit(1)
    
    # Setup logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = args.outdir / f"batch_sim_{timestamp}.log"
    args.outdir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 70)
    logger.info("Batch Spectre Simulation")
    logger.info("=" * 70)
    logger.info(f"DUT netlists:     {len(dut_netlists)}")
    logger.info(f"TB wrappers:      {len(tb_wrappers)}")
    logger.info(f"Output dir:       {args.outdir}")
    if args.tech_filter:
        logger.info(f"Tech filter:      {args.tech_filter}")
    logger.info(f"Log file:         {log_file}")
    logger.info("=" * 70)

    # Check license server and get actual counts
    logger.info(f"\nChecking license server...")
    total_licenses, busy_licenses = check_license_server()
    free_licenses = total_licenses - busy_licenses
    logger.info(f"Free licenses:    {free_licenses}")

    # Auto-calculate workers based on license availability
    # Formula: (free_licenses - colleague_upset_threshold) / licenses_per_worker
    # Then take the minimum of that and the number of simulations to run
    colleague_upset_threshold = 40
    licenses_per_worker = 2

    max_licenses = max(1, (free_licenses - colleague_upset_threshold) // licenses_per_worker)
    used_licenses = min(max_licenses, len(tb_wrappers))

    logger.info(f"License calculation: ({free_licenses} - {colleague_upset_threshold}) / {licenses_per_worker} = {max_licenses}")
    logger.info(f"Auto-calculated workers: {used_licenses}")

    # Run simulations
    logger.info(f"\nStarting {len(tb_wrappers)} simulations with {used_licenses} workers...")
    logger.info("-" * 70)

    successful = []
    failed = []
    total_time = 0.0
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=used_licenses) as executor:
        futures = {executor.submit(run_spectre_simulation, tb, args.outdir, args.spectre_path, args.license_server): tb.stem
                   for tb in tb_wrappers}
        
        completed = 0
        for future in as_completed(futures):
            tb_name = futures[future]
            try:
                name, success, elapsed = future.result()
                completed += 1
                total_time += elapsed
                
                if success:
                    successful.append(name)
                    logger.info(f"✓ [{completed}/{len(tb_wrappers)}] {name} ({elapsed:.1f}s)")
                else:
                    failed.append(name)
                    logger.info(f"✗ [{completed}/{len(tb_wrappers)}] {name} ({elapsed:.1f}s)")
                    
            except Exception as e:
                failed.append(tb_name)
                logger.error(f"✗ [{completed}/{len(tb_wrappers)}] {tb_name} exception: {e}")
                completed += 1
    
    wall_time = time.time() - start_time
    
    # Print summary
    logger.info("=" * 70)
    logger.info("Batch Simulation Summary")
    logger.info("=" * 70)
    logger.info(f"Total simulations:  {len(tb_wrappers)}")
    logger.info(f"Successful:         {len(successful)} ({100*len(successful)/len(tb_wrappers):.1f}%)")
    logger.info(f"Failed:             {len(failed)} ({100*len(failed)/len(tb_wrappers):.1f}%)")
    logger.info(f"Wall clock time:    {wall_time:.1f}s ({wall_time/60:.1f} min)")
    logger.info(f"Total CPU time:     {total_time:.1f}s ({total_time/60:.1f} min)")
    if wall_time > 0:
        logger.info(f"Speedup:            {total_time/wall_time:.2f}x")
    logger.info(f"Avg time/sim:       {total_time/len(tb_wrappers):.1f}s")
    logger.info("")
    logger.info(f"Output directory:   {args.outdir}")
    logger.info(f"  Raw files:        {args.outdir}/*.raw")
    logger.info(f"  Log files:        {args.outdir}/*.log")
    logger.info("=" * 70)
    
    if failed:
        logger.info("\nFailed simulations:")
        for name in failed:
            logger.info(f"  - {name}")
        logger.info("")
    
    return 0 if len(failed) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
