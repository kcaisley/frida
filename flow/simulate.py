"""
PyOPUS-based Spectre simulation runner using PerformanceEvaluator.

Flow Overview
=============
The simulation and measurement steps are able to be performed
on different machines, at different times:

    1. simulate.py (runs on remote server with Spectre license)
       - PerformanceEvaluator runs Spectre simulation
       - Produces .raw file (Spectre native output with waveforms)
       - storeResults=True saves parsed waveforms to .pck pickle files
       - Saves resFiles mapping (which .pck file has which corner/analysis)

    2. rsync results back to local machine

    3. measure.py (runs locally, no Spectre needed)
       - PostEvaluator loads .pck files (pre-parsed waveforms)
       - Evaluates measure expressions using v() and scale() accessors
       - Can iterate on measure expressions without re-simulating
       - Generates plots from measure results

Usage:
    python -m flow.simulate comp -j 20
    python -m flow.simulate comp --mode single  # Test single config
"""

import argparse
import datetime
import logging
import os
import pickle
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from flow.common import (
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


def run_simulation_pyopus(
    config_hash: str,
    tb_path: Path,
    tb_json_path: Path | None,
    sim_dir: Path,
    analyses: dict[str, Any],
    measures: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Path] | None:
    """
    Run simulation for a single testbench using PyOPUS PerformanceEvaluator.

    Args:
        config_hash: Configuration hash for naming output files
        tb_path: Path to testbench .sp file
        tb_json_path: Path to tb_json file for tech info (or None)
        sim_dir: Output directory for simulation files
        analyses: PyOPUS analyses configuration from cell module
        measures: PyOPUS measures configuration from cell module
        variables: Variables dict for expression evaluation

    Returns:
        Dict of output file paths (scs, log, raw, resfiles) or None if failed
    """
    import json

    from flow.common import techmap

    logger = logging.getLogger(__name__)

    try:
        from pyopus.evaluator.performance import PerformanceEvaluator
    except ImportError:
        logger.error("PyOPUS not available")
        return None

    # Build sim_name from tb filename (needed for paths)
    sim_name = tb_path.stem.replace("tb_", "sim_", 1) if tb_path.stem.startswith("tb_") else f"sim_{tb_path.stem}"

    # Output file paths (raw_path determined after simulation from PyOPUS simulatorID)
    scs_path = sim_dir / f"{sim_name}.scs"
    log_path = sim_dir / f"{sim_name}.log"

    # Load tb_json to get tech info (no filename parsing!)
    tech = None
    if tb_json_path and tb_json_path.exists():
        with open(tb_json_path) as f:
            tb_config = json.load(f)
        tech = tb_config.get("tech")

    # Get MC model path and section from techmap
    mc_lib_path = None
    mc_lib_section = None
    if tech and tech in techmap:
        tech_cfg = techmap[tech]
        # Get MC section name from corners dict (e.g., "mc_lib")
        mc_section = tech_cfg.get("corners", {}).get("mc")
        if mc_section:
            # Find lib that has this section
            libs = tech_cfg.get("libs", [])
            if libs and mc_section in libs[0].get("sections", []):
                mc_lib_path = libs[0]["path"]
                mc_lib_section = mc_section

    # Build moddefs with MC if available
    moddefs = {"tb": {"file": str(tb_path)}}
    if mc_lib_path and mc_lib_section:
        moddefs["mc"] = {"file": mc_lib_path, "section": mc_lib_section}

    # Heads config - args becomes self.cmdline internally
    #
    # NOTE: How PyOPUS handles Spectre output files internally:
    #   - Raw format: PyOPUS writes "rawfmt=nutbin" to the .scs file (binary format)
    #   - Raw path: PyOPUS uses "{simulatorID}_group{N}.raw" naming scheme
    #   - The simulatorID is auto-generated (e.g., "juno.physik.uni-bonn.de_2da779_1")
    #   - readResults() in spectre.py line 990 looks for this exact pattern
    #   - If we pass -raw to override the path, readResults() can't find the file,
    #     causing storeResults pickle files to contain None (4 bytes)
    #   - Solution: Don't pass -raw, let PyOPUS manage it, then move the file after
    #
    heads = {
        "spectre": {
            "simulator": "Spectre",
            "settings": {
                "debug": 0,
                "args": [
                    "-64",
                    "+preset=mx",  # Spectre X mx mode (balanced accuracy/performance)
                    "+log", str(log_path),
                ],
            },
            "moddefs": moddefs,
        }
    }

    # Single nominal corner - PVT info is already baked into .sp file
    corners = {
        "nominal": {
            "modules": ["tb"],
            "params": {},
        }
    }

    # Override head/modules in analyses to use our dynamic head
    # (the block file has placeholders that we replace at runtime)
    # Note: corners already specifies ["tb"], so analyses should only add
    # additional modules (like "mc") to avoid duplicates
    runtime_analyses = {}
    for name, cfg in analyses.items():
        # Only add modules beyond the base "tb" that corner provides
        modules = []
        if "mc" in cfg.get("modules", []) and mc_lib_path:
            modules.append("mc")

        runtime_analyses[name] = {
            "head": "spectre",
            "modules": modules,
            "command": cfg.get("command", ""),
            "saves": cfg.get("saves", [])
        }
    analyses = runtime_analyses

    try:
        # Create PerformanceEvaluator with native pickle storage
        pe = PerformanceEvaluator(
            heads=heads,
            analyses=analyses,
            measures=measures,
            corners=corners,
            variables=variables,
            storeResults=True,              # Enable native pickle storage
            resultsFolder=str(sim_dir),     # Where to store .pck files
            debug=0,
        )

        # Run simulation and compute measures (results discarded - we use PostEvaluator later)
        _results, _an_count = pe({})

        # Find PyOPUS's raw file path (uses its own naming scheme)
        simulator = pe.simulatorForHead["spectre"]
        raw_path = Path(f"{simulator.simulatorID}_group0.raw")

        # Save resFiles mapping for PostEvaluator
        # resFiles is a dict: {(hostID, (corner, analysis)): filepath}
        resfiles_path = sim_dir / f"{sim_name}_resfiles.pck"
        logger.info(f"resFiles contents: {pe.resFiles}")
        logger.info(f"resFiles types: {[(type(k), type(v)) for k, v in pe.resFiles.items()]}")
        with open(resfiles_path, "wb") as f:
            pickle.dump(pe.resFiles, f)

        pe.finalize()

        return {
            "scs": scs_path,
            "log": log_path,
            "raw": raw_path,
            "resfiles": resfiles_path,
        }

    except Exception as e:
        logger.warning(f"Simulation failed for {tb_path.name}: {e}")
        return None


def run_batch_parallel(
    jobs: list[dict[str, Any]],
    sim_dir: Path,
    analyses: dict[str, Any],
    measures: dict[str, Any],
    variables: dict[str, Any],
    num_workers: int = 20,
) -> dict[str, dict[str, Path]]:
    """
    Run simulations in parallel using ProcessPoolExecutor.

    Args:
        jobs: List of job dicts with config_hash and tb_path
        sim_dir: Output directory for simulation files
        analyses: PyOPUS analyses configuration
        measures: PyOPUS measures configuration
        variables: Variables dict for expression evaluation
        num_workers: Number of parallel Spectre processes

    Returns:
        Dict mapping config_hash to dict of file paths (scs, log, raw, resfiles)
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    logger = logging.getLogger(__name__)

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

    def run_single(job: dict[str, Any]) -> tuple[str, dict[str, Path] | None]:
        config_hash = job["config_hash"]
        tb_path = Path(job["tb_path"])
        tb_json_path = Path(job["tb_json_path"]) if job.get("tb_json_path") else None
        return config_hash, run_simulation_pyopus(
            config_hash, tb_path, tb_json_path, sim_dir, analyses, measures, variables
        )

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(run_single, job) for job in jobs]

        for future in as_completed(futures):
            config_hash, paths = future.result()

            if paths:
                results[config_hash] = paths
                logger.info(f"  Completed: {paths['resfiles'].stem}")
            else:
                logger.warning(f"  Failed: {config_hash}")

    return results


def run_batch_sequential(
    jobs: list[dict[str, Any]],
    sim_dir: Path,
    analyses: dict[str, Any],
    measures: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, dict[str, Path]]:
    """
    Run simulations sequentially (for debugging or single mode).

    Args:
        jobs: List of job dicts with config_hash and tb_path
        sim_dir: Output directory for simulation files
        analyses: PyOPUS analyses configuration
        measures: PyOPUS measures configuration
        variables: Variables dict for expression evaluation

    Returns:
        Dict mapping config_hash to dict of file paths (scs, log, raw, resfiles)
    """
    logger = logging.getLogger(__name__)
    results = {}

    for job in jobs:
        config_hash = job["config_hash"]
        tb_path = Path(job["tb_path"])
        tb_json_path = Path(job["tb_json_path"]) if job.get("tb_json_path") else None

        paths = run_simulation_pyopus(
            config_hash, tb_path, tb_json_path, sim_dir, analyses, measures, variables
        )

        if paths:
            results[config_hash] = paths
            logger.info(f"  Completed: {paths['resfiles'].stem}")
        else:
            logger.warning(f"  Failed: {config_hash}")

    return results


def main():
    """Main entry point for simulation runner."""
    parser = argparse.ArgumentParser(
        description="Run PyOPUS-based Spectre simulations"
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

    # Get analyses and measures from cell module
    analyses = getattr(cell_module, "analyses", {})
    measures = getattr(cell_module, "measures", {})
    variables = getattr(cell_module, "variables", {})

    # Import expression module for measure evaluation
    from flow import expression as m
    variables = {**variables, "m": m}

    # Build job list from files.json
    jobs = []
    for config_hash, file_ctx in files.items():
        tb_spice_list = file_ctx.get("tb_spice", [])
        tb_json_list = file_ctx.get("tb_json", [])

        for idx, tb_spice_rel in enumerate(tb_spice_list):
            tb_path = cell_dir / tb_spice_rel
            # Get corresponding tb_json from files.json
            tb_json_rel = tb_json_list[idx] if idx < len(tb_json_list) else None

            # Apply tech filter if specified
            if args.tech:
                # Parse tech from filename
                parts = tb_path.stem.split("_")
                tech = "unknown"
                for part in parts:
                    if part in ["tsmc65", "tsmc28", "tower180"]:
                        tech = part
                        break
                if tech != args.tech:
                    continue

            jobs.append({
                "config_hash": config_hash,
                "tb_path": str(tb_path),
                "tb_json_path": str(cell_dir / tb_json_rel) if tb_json_rel else None,
                "cfgname": file_ctx.get("cfgname", ""),
            })

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

    # Create output directory (clean old files first)
    if sim_dir.exists():
        import shutil
        shutil.rmtree(sim_dir)
    sim_dir.mkdir(parents=True, exist_ok=True)

    # Dryrun mode: just show what would be simulated
    if args.mode == "dryrun":
        logger.info("DRYRUN MODE: Showing simulation plan only")
        for job in jobs:
            logger.info(f"  Would simulate: {Path(job['tb_path']).name}")
        logger.info("=" * 80)
        logger.info(f"Total jobs: {len(jobs)}")
        logger.info("=" * 80)
        return 0

    # Single mode: run only the first job (for debugging)
    if args.mode == "single":
        logger.info("SINGLE MODE: Running first simulation only (for debugging)")
        jobs = jobs[:1]

    # Run simulations
    start_time = datetime.datetime.now()

    if args.mode == "single" or len(jobs) == 1:
        results = run_batch_sequential(jobs, sim_dir, analyses, measures, variables)
    else:
        results = run_batch_parallel(jobs, sim_dir, analyses, measures, variables, num_workers=args.jobs)

    elapsed = (datetime.datetime.now() - start_time).total_seconds()

    # Update files.json with simulation results
    for config_hash, file_ctx in files.items():
        sim_spice = []
        sim_raw = []
        sim_log = []
        sim_resfiles = None

        if config_hash in results:
            paths = results[config_hash]
            # Store relative paths
            if paths.get("scs") and paths["scs"].exists():
                sim_spice.append(f"sim/{paths['scs'].name}")
            if paths.get("raw") and paths["raw"].exists():
                sim_raw.append(f"sim/{paths['raw'].name}")
            if paths.get("log") and paths["log"].exists():
                sim_log.append(f"sim/{paths['log'].name}")
            if paths.get("resfiles") and paths["resfiles"].exists():
                sim_resfiles = f"sim/{paths['resfiles'].name}"

        file_ctx["sim_spice"] = sim_spice
        file_ctx["sim_raw"] = sim_raw
        file_ctx["sim_log"] = sim_log
        file_ctx["sim_resfiles"] = sim_resfiles

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
