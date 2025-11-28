#!/usr/bin/env python3
"""
Run batch Spectre simulations in parallel using process pool executor.

This script finds all netlist variants in a directory and runs simulations
in parallel with configurable concurrency to manage license usage.

Usage:
    python run_batch_sims.py \
        --template spice/tb_comp.sp \
        --netlists results/comp_doubletail/*.sp \
        --pdk /path/to/pdk/models.scs \
        --outdir results/comp_doubletail \
        --max-workers 4
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, Dict
import time
import datetime
import re
import tomllib


def generate_netlist_content(template_path: Path, dut_netlist: Path,
                            pdk_models: str, testbench_va: Path, corner_section: str = None) -> str:
    """
    Generate netlist content with all paths substituted (in memory only).

    Args:
        template_path: Path to the template .sp file
        dut_netlist: Path to the specific DUT netlist to use
        pdk_models: Path to PDK models file
        testbench_va: Path to Verilog-A testbench
        corner_section: Optional corner section name (e.g., "tt_lib", "att_pt")

    Returns:
        Modified netlist content as string
    """
    with open(template_path, 'r') as f:
        content = f.read()

    # Replace PDK models placeholder with .lib statement if corner specified
    if corner_section:
        lib_statement = f'.lib "{pdk_models}" {corner_section}'
        content = content.replace('PLACEHOLDER_PDK_MODELS', lib_statement)
    else:
        # Backward compatibility: just use the path
        content = content.replace('PLACEHOLDER_PDK_MODELS', str(pdk_models))

    content = content.replace('PLACEHOLDER_DUT_NETLIST', str(dut_netlist))
    content = content.replace('PLACEHOLDER_TESTBENCH_VA', str(testbench_va))

    return content


def run_spectre_simulation(netlist_content: str, output_dir: Path, log_file: Path,
                          working_dir: Path, netlist_name: str) -> subprocess.CompletedProcess:
    """
    Run Spectre simulation by writing netlist to a file.

    Args:
        netlist_content: Netlist content as string
        output_dir: Directory for simulation output
        log_file: Path to log file
        working_dir: Working directory for simulation
        netlist_name: Name for the netlist file (without extension)

    Returns:
        CompletedProcess object with simulation results
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write netlist to file in output directory
    temp_netlist = output_dir / f"{netlist_name}.scs"
    with open(temp_netlist, 'w') as f:
        f.write(netlist_content)

    # Extract family and cellname from netlist_name for conditional compilation
    # Format: family_cellname_tech_params (e.g., samp_pmos_tsmc65_MP-w5-l1)
    parts = netlist_name.split('_')
    define_flag = None
    if len(parts) >= 2:
        family = parts[0]
        cellname = parts[1]
        # Create preprocessor define for Verilog-A (e.g., -DSAMP_PMOS)
        define_flag = f"-D{family.upper()}_{cellname.upper()}"

    # Build Spectre command
    raw_file = output_dir / f"{netlist_name}.raw"
    cmd = ['spectre', str(temp_netlist)]

    # Add preprocessor define if extracted from netlist name
    if define_flag:
        cmd.append(define_flag)

    # Add remaining arguments
    cmd.extend([
        '+log', str(log_file),
        '-format', 'nutbin',
        '-raw', str(raw_file)
    ])

    # Run simulation
    try:
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        return result

    except FileNotFoundError:
        raise FileNotFoundError("'spectre' command not found. Is Spectre in your PATH?")
    except Exception as e:
        raise Exception(f"Error running simulation: {e}")


def get_spectre_license_usage() -> Dict[str, Tuple[int, int]]:
    """
    Query Cadence license server for Spectre license usage.

    Returns:
        Dictionary mapping license name to (in_use, total) tuple
    """
    try:
        result = subprocess.run(
            ['lmstat', '-a', '-c', '27500@nexus.physik.uni-bonn.de'],
            capture_output=True,
            text=True,
            timeout=5
        )

        licenses = {}
        # Look for the four main Spectre license types
        license_names = [
            'Spectre_X_MMSIM_Lk',
            'Spectre_AMS_MMSIM_Lk',
            'Virtuoso_Spectre_GXL_MMSIM_Lk',
            'Virtuoso_Multi_mode_Simulation'
        ]

        for license_name in license_names:
            # Pattern: "Users of LICENSE_NAME:  (Total of X licenses issued;  Total of Y licenses in use)"
            pattern = rf'Users of {re.escape(license_name)}:\s+\(Total of (\d+) licenses issued;\s+Total of (\d+) licenses in use\)'
            match = re.search(pattern, result.stdout)
            if match:
                total = int(match.group(1))
                in_use = int(match.group(2))
                licenses[license_name] = (in_use, total)

        return licenses

    except Exception:
        # If license check fails, return empty dict
        return {}


def format_license_status(licenses: Dict[str, Tuple[int, int]]) -> str:
    """Format license usage into a compact one-line string."""
    if not licenses:
        return "Licenses: [unavailable]"

    parts = []
    for name, (in_use, total) in licenses.items():
        # Shorten license names for compact display
        short_name = name.replace('Virtuoso_', 'V_').replace('Spectre_', 'S_').replace('_MMSIM_Lk', '')
        parts.append(f"{short_name}:{in_use}/{total}")

    return "Licenses: " + " | ".join(parts)


def run_single_simulation(args: Tuple[Path, Path, str, Path, Path, str]) -> Tuple[str, bool, float]:
    """
    Run a single Spectre simulation.

    Args:
        args: Tuple of (template, dut_netlist, pdk_path, outdir, testbench, corner_section)

    Returns:
        Tuple of (netlist_name, success, elapsed_time)
    """
    template, dut_netlist, pdk_path, outdir, testbench, corner_section = args

    netlist_name = dut_netlist.stem
    start_time = time.time()

    # Check and log license usage before starting simulation
    licenses = get_spectre_license_usage()
    license_status = format_license_status(licenses)

    # Setup logger for this worker
    logger = logging.getLogger(__name__)
    logger.info(f"→ Starting {netlist_name} | {license_status}")

    try:
        # Generate netlist content
        netlist_content = generate_netlist_content(template, dut_netlist, pdk_path, testbench, corner_section)

        # Setup paths
        log_file = outdir / f"{netlist_name}.log"

        # Run Spectre simulation
        result = run_spectre_simulation(netlist_content, outdir, log_file, outdir, netlist_name)

        elapsed_time = time.time() - start_time
        success = (result.returncode == 0)

        if not success:
            logger.error(f"✗ {netlist_name} failed (return code {result.returncode})")
            if result.stderr:
                logger.error(f"  Error: {result.stderr[:200]}")

        return (netlist_name, success, elapsed_time)

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"✗ {netlist_name} error: {e}")
        return (netlist_name, False, elapsed_time)


def main():
    """Main entry point for batch simulation runner."""
    parser = argparse.ArgumentParser(
        description='Run batch Spectre simulations in parallel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python run_batch_sims.py \\
    --template spice/tb_comp.sp \\
    --netlists "results/comp_doubletail/*.sp" \\
    --pdk /eda/kits/TSMC/65LP/.../toplevel.scs \\
    --outdir results/comp_doubletail \\
    --max-workers 4
        """
    )

    parser.add_argument(
        '-t', '--template',
        type=Path,
        required=True,
        help='Template Spectre netlist file (.sp)'
    )

    parser.add_argument(
        '-n', '--netlists',
        type=str,
        required=True,
        help='Glob pattern for DUT netlists (e.g., "results/comp_doubletail/*.sp")'
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
        '-w', '--max-workers',
        type=int,
        default=None,
        help='Maximum number of parallel simulations (default: auto-calculate from available licenses)'
    )

    parser.add_argument(
        '--filter',
        type=str,
        help='Only run netlists matching this substring (e.g., "tsmc65")'
    )

    parser.add_argument(
        '--corner',
        type=str,
        default='tt',
        help='Corner section name (e.g., "tt", "ss", "ff", default: "tt")'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.template.exists():
        print(f"Error: Template file not found: {args.template}")
        sys.exit(1)

    # Find all netlist files matching the pattern
    from glob import glob
    netlist_files = [Path(f) for f in glob(args.netlists)]

    if not netlist_files:
        print(f"Error: No netlist files found matching: {args.netlists}")
        sys.exit(1)

    # Apply filter if specified
    if args.filter:
        netlist_files = [f for f in netlist_files if args.filter in f.name]
        if not netlist_files:
            print(f"Error: No netlists match filter: {args.filter}")
            sys.exit(1)

    # Sort netlists for consistent ordering
    netlist_files.sort()

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
    logger.info(f"Template:     {args.template}")
    logger.info(f"PDK:          {args.pdk}")
    logger.info(f"Testbench:    {args.testbench}")
    logger.info(f"Output dir:   {args.outdir}")
    logger.info(f"Netlists:     {len(netlist_files)} found")
    logger.info(f"Max workers:  {args.max_workers}")
    if args.filter:
        logger.info(f"Filter:       {args.filter}")
    logger.info(f"Log file:     {log_file}")
    logger.info("=" * 70)

    # Load corner section from config if corner is specified
    corner_section = None
    if args.corner:
        try:
            config_path = Path('spice/generate_netlists.toml')
            if config_path.exists():
                with open(config_path, 'rb') as f:
                    config = tomllib.load(f)

                # Extract technology from first netlist filename (e.g., tsmc65 from samp_tgate_tsmc65_...)
                if netlist_files:
                    first_netlist = netlist_files[0].stem
                    parts = first_netlist.split('_')
                    # Find the technology part (tsmc65, tsmc28, tower180)
                    tech = None
                    for part in parts:
                        if part in config:
                            tech = part
                            break

                    if tech and 'corners' in config[tech]:
                        corners = config[tech]['corners']
                        if args.corner in corners:
                            corner_section = corners[args.corner]
                            logger.info(f"Corner:       {args.corner} -> {corner_section}")
                        else:
                            logger.warning(f"Warning: Corner '{args.corner}' not found in config for {tech}. Available: {list(corners.keys())}")
                    elif tech:
                        logger.warning(f"Warning: No corners defined for technology '{tech}' in config")
        except Exception as e:
            logger.warning(f"Warning: Could not load corner from config: {e}")

    # Prepare simulation tasks
    tasks = [
        (args.template, netlist, args.pdk, args.outdir, args.testbench, corner_section)
        for netlist in netlist_files
    ]

    # Track results
    successful = []
    failed = []
    total_time = 0.0

    start_time = time.time()

    # Check baseline license usage before starting any workers
    logger.info(f"\nChecking baseline license usage...")
    baseline_licenses = get_spectre_license_usage()
    baseline_status = format_license_status(baseline_licenses)
    logger.info(f"Baseline: {baseline_status}")

    # Calculate optimal number of workers if not specified
    if args.max_workers is None:
        # Use Virtuoso_Multi_mode_Simulation license as the limiting factor
        if 'Virtuoso_Multi_mode_Simulation' in baseline_licenses:
            in_use, total = baseline_licenses['Virtuoso_Multi_mode_Simulation']
            # Formula: (total - in_use - 20_margin) / 2_licenses_per_worker
            available = total - in_use - 20
            max_workers_from_licenses = max(1, available // 2)  # At least 1 worker
            # Limit to number of simulations (no point having more workers than sims)
            max_workers = min(max_workers_from_licenses, len(tasks))
            if max_workers_from_licenses > len(tasks):
                logger.info(f"Auto-calculated workers: {max_workers} (limited by {len(tasks)} simulations, licenses would allow {max_workers_from_licenses})")
            else:
                logger.info(f"Auto-calculated workers: {max_workers} (available licenses: {available}, assuming 2 per worker, 20 margin)")
        else:
            max_workers = min(4, len(tasks))  # Fallback if license info unavailable
            logger.info(f"License info unavailable, using default: {max_workers} workers")
    else:
        max_workers = args.max_workers
        logger.info(f"Using specified workers: {max_workers}")

    # Run simulations in parallel using ProcessPoolExecutor
    logger.info(f"\nStarting {len(tasks)} simulations with {max_workers} workers...")
    logger.info("-" * 70)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(run_single_simulation, task): task[1].stem
                   for task in tasks}

        # Process completed simulations as they finish
        completed = 0
        peak_licenses_checked = False

        for future in as_completed(futures):
            netlist_name = futures[future]
            try:
                name, success, elapsed = future.result()
                completed += 1
                total_time += elapsed

                # After first simulation completes, check peak license usage
                if not peak_licenses_checked and completed == 1:
                    time.sleep(2)  # Brief delay to let all workers start
                    peak_licenses = get_spectre_license_usage()
                    peak_status = format_license_status(peak_licenses)
                    logger.info(f"Peak usage (after all workers started): {peak_status}")
                    logger.info("-" * 70)
                    peak_licenses_checked = True

                if success:
                    successful.append(name)
                    logger.info(f"✓ [{completed}/{len(tasks)}] {name} ({elapsed:.1f}s)")
                else:
                    failed.append(name)
                    # Error already printed in worker

            except Exception as e:
                failed.append(netlist_name)
                logger.error(f"✗ [{completed}/{len(tasks)}] {netlist_name} exception: {e}")
                completed += 1

    wall_time = time.time() - start_time

    # Print summary
    logger.info("=" * 70)
    logger.info("Batch Simulation Summary")
    logger.info("=" * 70)
    logger.info(f"Total simulations:  {len(tasks)}")
    logger.info(f"Successful:         {len(successful)} ({100*len(successful)/len(tasks):.1f}%)")
    logger.info(f"Failed:             {len(failed)} ({100*len(failed)/len(tasks):.1f}%)")
    logger.info(f"Wall clock time:    {wall_time:.1f}s ({wall_time/60:.1f} min)")
    logger.info(f"Total CPU time:     {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"Speedup:            {total_time/wall_time:.2f}x")
    logger.info(f"Avg time/sim:       {total_time/len(tasks):.1f}s")
    logger.info("")
    logger.info(f"Output directory:   {args.outdir}")
    logger.info(f"  Raw files:        {args.outdir}/*.raw")
    logger.info(f"  Log files:        {args.outdir}/*.log")
    logger.info(f"  Netlists:         {args.outdir}/*.scs")
    logger.info(f"  AHDL builds:      {args.outdir}/*.ahdlSimDB/")
    logger.info(f"  Operating points: {args.outdir}/*.ns@0")
    logger.info("=" * 70)

    if failed:
        logger.info("\nFailed simulations:")
        for name in failed:
            logger.info(f"  - {name}")
        logger.info("")

    # Return success if all simulations passed
    return 0 if len(failed) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
