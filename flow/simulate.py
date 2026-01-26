"""
PyOPUS-based Spectre batch simulation runner.

Runs all testbenches for a cell in batch using PyOPUS Spectre interface
or parallel ProcessPoolExecutor fallback.

Usage:
    python -m flow.simulate comp -j 20
"""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from flow.common import (
    build_pyopus_jobs,
    check_cell_script,
    load_cell_script,
    load_files_list,
    save_files_list,
    setup_logging,
)


def check_license_server() -> tuple[int, int]:
    """
    Check Spectre license server availability and parse license usage.

    Returns:
        Tuple of (total_licenses, busy_licenses)

    Raises:
        SystemExit: If CDS_LIC_FILE is not set or license server doesn't respond
    """
    logger = logging.getLogger(__name__)

    license_server = os.environ.get("CDS_LIC_FILE")
    if not license_server:
        logger.error("CDS_LIC_FILE environment variable is not set")
        logger.error("Please set it with: export CDS_LIC_FILE=<port>@<server>")
        sys.exit(1)

    logger.info(f"License server: {license_server}")

    try:
        result = subprocess.run(  # type: ignore[call-overload]
            ["lmstat", "-c", license_server, "-a"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )

        if result.returncode != 0:
            logger.error(f"lmstat command failed: {result.stderr}")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        logger.error("License server check timed out")
        sys.exit(1)
    except FileNotFoundError:
        logger.error("lmstat command not found. Ensure Cadence tools are in PATH")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to check license server: {e}")
        sys.exit(1)

    total_licenses = 0
    busy_licenses = 0

    for line in result.stdout.split("\n"):
        if "Virtuoso_Multi_mode_Simulation" in line or "MMSIM" in line:
            issued_match = re.search(r"Total of (\d+) licenses? issued", line)
            in_use_match = re.search(r"Total of (\d+) licenses? in use", line)

            if issued_match:
                total_licenses = int(issued_match.group(1))
            if in_use_match:
                busy_licenses = int(in_use_match.group(1))
            break

    if total_licenses == 0:
        logger.error("Could not parse license information from lmstat output")
        sys.exit(1)

    logger.info(f"Total licenses: {total_licenses}")
    logger.info(f"Busy licenses: {busy_licenses}")

    return total_licenses, busy_licenses


def run_batch_pyopus(jobs: list[dict[str, Any]], sim_dir: Path, num_workers: int = 20) -> dict[str, Path]:
    """
    Run all jobs using PyOPUS Spectre interface.

    Args:
        jobs: List of PyOPUS job dicts from build_pyopus_jobs()
        sim_dir: Output directory for .raw files
        num_workers: Number of parallel processes

    Returns:
        Dict mapping job name to raw file path
    """
    logger = logging.getLogger(__name__)

    try:
        from pyopus.simulator import simulatorClass
    except ImportError:
        logger.info("PyOPUS simulator not available. Using fallback Spectre runner.")
        return run_batch_parallel(jobs, sim_dir, num_workers)

    logger.info(f"Running with PyOPUS (up to {num_workers} parallel jobs)")

    # Create Spectre simulator instance
    Spectre = simulatorClass("Spectre")
    sim = Spectre(debug=1)

    # Strip metadata before sending to simulator
    clean_jobs = [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]
    sim.setJobList(clean_jobs)

    results = {}
    for i in range(sim.jobGroupCount()):
        job_indices, status = sim.runJobGroup(i)

        for j in job_indices:
            job_name = jobs[j]["name"]
            # Replace tb_ prefix with sim_ for output files
            sim_name = job_name.replace("tb_", "sim_", 1)
            raw_path = sim_dir / f"{sim_name}.raw"

            res = sim.readResults(j, status)
            if res is not None:
                results[job_name] = raw_path

                # Store metadata alongside
                meta_path = sim_dir / f"{sim_name}.meta.json"
                meta = jobs[j].get("_metadata", {})
                meta_path.write_text(json.dumps(meta, indent=2))

                logger.info(f"  Completed: {sim_name}")
            else:
                logger.warning(f"  Failed: {sim_name}")

    return results


def run_batch_parallel(jobs: list[dict[str, Any]], sim_dir: Path, num_workers: int = 20) -> dict[str, Path]:
    """
    Run simulations in parallel using ProcessPoolExecutor.

    Args:
        jobs: List of job dicts with netlist paths
        sim_dir: Output directory for .raw files
        num_workers: Number of parallel Spectre processes

    Returns:
        Dict mapping job name to raw file path
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    logger = logging.getLogger(__name__)
    spectre_path = os.environ.get("SPECTRE_PATH", "spectre")
    license_server = os.environ.get("CDS_LIC_FILE", "")

    # Check available licenses and adjust workers if needed
    total_lic, busy_lic = check_license_server()
    free_lic = total_lic - busy_lic

    # Leave some licenses for colleagues
    colleague_threshold = 40
    licenses_per_worker = 2
    max_by_license = max(1, (free_lic - colleague_threshold) // licenses_per_worker)
    num_workers = min(num_workers, max_by_license, len(jobs))

    logger.info(f"Running {len(jobs)} simulations with {num_workers} workers")

    results = {}

    def run_single(job: dict[str, Any]) -> tuple[str, bool, Path | None]:
        job_name = job["name"]
        sim_name = job_name.replace("tb_", "sim_", 1)
        tb_file = job["definitions"][0]["file"]

        log_file = sim_dir / f"{sim_name}.log"
        raw_file = sim_dir / f"{sim_name}.raw"

        cmd = [
            spectre_path,
            "-64",
            tb_file,
            "+log",
            str(log_file),
            "-format",
            "nutascii",
            "-raw",
            str(raw_file),
        ]

        env = os.environ.copy()
        env["CDS_LIC_FILE"] = license_server

        try:
            result = subprocess.run(
                cmd,
                cwd=str(sim_dir),
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            success = result.returncode == 0
            return job_name, success, raw_file if success else None
        except Exception:
            return job_name, False, None

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(run_single, job): job for job in jobs}

        for future in as_completed(futures):
            job = futures[future]
            job_name, success, raw_path = future.result()

            if success and raw_path:
                results[job_name] = raw_path

                # Save metadata
                sim_name = job_name.replace("tb_", "sim_", 1)
                meta_path = sim_dir / f"{sim_name}.meta.json"
                meta = job.get("_metadata", {})
                meta_path.write_text(json.dumps(meta, indent=2))

                logger.info(f"  Completed: {sim_name}")
            else:
                logger.warning(f"  Failed: {job_name}")

    return results


def main():
    """Main entry point for simulation runner."""
    parser = argparse.ArgumentParser(
        description="Run PyOPUS-based Spectre batch simulations"
    )
    parser.add_argument("cell", help="Cell name (e.g., comp, cdac)")
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=Path("results"),
        help="Results directory (default: results)",
    )
    parser.add_argument(
        "--tech",
        type=str,
        default=None,
        help="Filter by technology (e.g., tsmc65)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=40,
        help="Number of parallel processes (default: 40)",
    )
    parser.add_argument(
        "--mode",
        choices=["dryrun", "single", "all"],
        default="all",
        help="Simulation mode: dryrun (generate files only), single (run first sim only), all (run all)",
    )

    args = parser.parse_args()

    # Setup paths
    cell_dir = args.outdir / args.cell
    sim_dir = cell_dir / "sim"
    files_db_path = cell_dir / "files.json"

    # Setup logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"sim_{args.cell}_{timestamp}.log"
    logger = setup_logging(log_file)

    # Check prerequisites
    if not files_db_path.exists():
        logger.error(f"files.json not found at {files_db_path}")
        logger.error(f"Run 'make subckt cell={args.cell}' and 'make tb cell={args.cell}' first")
        return 1

    block_file = Path(f"blocks/{args.cell}.py")
    if not block_file.exists():
        logger.error(f"Block file not found: {block_file}")
        return 1

    # Load files database and cell module
    files = load_files_list(files_db_path)
    cell_module = load_cell_script(block_file)

    # Build job list
    jobs = build_pyopus_jobs(files, cell_dir, cell_module)

    # Apply tech filter if specified
    if args.tech:
        jobs = [j for j in jobs if j["_metadata"].get("tech") == args.tech]

    if not jobs:
        logger.warning("No testbenches to simulate")
        return 0

    logger.info("=" * 80)
    logger.info(f"Cell:       {args.cell}")
    logger.info(f"Flow:       simulate (mode={args.mode})")
    logger.info(f"Jobs:       {len(jobs)}")
    if args.mode != "dryrun":
        logger.info(f"Workers:    {args.jobs}")
    logger.info(f"Output:     {sim_dir}")
    logger.info(f"Log:        {log_file}")
    if args.tech:
        logger.info(f"Tech:       {args.tech}")
    logger.info("-" * 80)

    # Create output directory
    sim_dir.mkdir(parents=True, exist_ok=True)

    # Dryrun mode: generate PyOPUS simulator input files without running
    if args.mode == "dryrun":
        # Validate cell script structure
        script_errors, _ = check_cell_script(cell_module, args.cell)
        if script_errors:
            logger.error("Cell script validation failed:")
            for err in script_errors:
                logger.error(f"  {err}")
            return 1

        logger.info("DRYRUN MODE: Generating simulator input files only")

        try:
            from pyopus.simulator import simulatorClass
        except ImportError:
            logger.error("PyOPUS not available - cannot generate simulator input files")
            return 1

        # Create Spectre simulator instance
        Spectre = simulatorClass("Spectre")
        sim = Spectre(debug=0)

        # Strip metadata before sending to simulator
        clean_jobs = [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]
        sim.setJobList(clean_jobs)

        # Change to sim directory for file generation
        orig_dir = os.getcwd()
        os.chdir(sim_dir)

        try:
            # Generate input files for each job group
            for i in range(sim.jobGroupCount()):
                input_file = sim.writeFile(i)
                logger.info(f"  Generated: {input_file}")
        finally:
            os.chdir(orig_dir)

        logger.info("=" * 80)
        logger.info("Dryrun Summary")
        logger.info("=" * 80)
        logger.info(f"Total jobs:    {len(jobs)}")
        logger.info(f"Job groups:    {sim.jobGroupCount()}")
        logger.info(f"Input files:   {sim_dir}")
        logger.info("=" * 80)
        return 0

    # Single mode: run only the first job (for debugging)
    if args.mode == "single":
        logger.info("SINGLE MODE: Running first simulation only (for debugging)")
        jobs = jobs[:1]

    # Run simulations
    start_time = datetime.datetime.now()
    results = run_batch_pyopus(jobs, sim_dir, num_workers=args.jobs)
    elapsed = (datetime.datetime.now() - start_time).total_seconds()

    # Update files.json with simulation results
    for config_hash, file_ctx in files.items():
        matching = []
        for job_name, raw_path in results.items():
            if config_hash in job_name:
                # Store relative path
                matching.append(f"sim/{raw_path.name}")
        if matching:
            file_ctx["sim_raw"] = matching

    save_files_list(files_db_path, files)

    # Summary
    logger.info("=" * 80)
    logger.info("Simulation Summary")
    logger.info("=" * 80)
    logger.info(f"Total jobs:    {len(jobs)}")
    logger.info(f"Successful:    {len(results)}")
    logger.info(f"Failed:        {len(jobs) - len(results)}")
    logger.info(f"Elapsed time:  {elapsed:.1f}s")
    logger.info(f"Output:        {sim_dir}")
    logger.info("=" * 80)

    return 0 if len(results) == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
