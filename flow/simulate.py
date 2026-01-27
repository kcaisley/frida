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


def check_tools() -> tuple[int, int]:
    """
    Verify Cadence environment and return license availability.

    Checks:
        - CDS_LIC_FILE environment variable is set
        - lmstat command is available (Cadence tools in PATH)
        - spectre command is available
        - License server responds and has licenses

    Returns:
        Tuple of (total_licenses, busy_licenses)

    Raises:
        SystemExit: If any check fails
    """
    logger = logging.getLogger(__name__)

    # Check CDS_LIC_FILE
    license_server = os.environ.get("CDS_LIC_FILE")
    if not license_server:
        logger.error("CDS_LIC_FILE environment variable is not set")
        logger.error("Set it with: export CDS_LIC_FILE=<port>@<server>")
        sys.exit(1)
    logger.info(f"License server: {license_server}")

    # Check lmstat is available
    try:
        subprocess.run(["which", "lmstat"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("lmstat not found - Cadence tools not in PATH")
        logger.error("Source the Cadence setup script first")
        sys.exit(1)

    # Check spectre is available
    try:
        subprocess.run(["which", "spectre"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("spectre not found - Cadence Spectre not in PATH")
        logger.error("Source the Cadence setup script first")
        sys.exit(1)

    # Query license usage
    try:
        result = subprocess.run(
            ["lmstat", "-c", license_server, "-a"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        if result.returncode != 0:
            logger.error(f"lmstat query failed: {result.stderr}")
            sys.exit(1)
    except subprocess.TimeoutExpired:
        logger.error("License server query timed out")
        sys.exit(1)
    except Exception as e:
        logger.error(f"License query failed: {e}")
        sys.exit(1)

    # Parse license info
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
        logger.error("Could not parse license info from lmstat output")
        sys.exit(1)

    logger.info(f"Licenses: {busy_licenses}/{total_licenses} in use")
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

    logger.debug(f"[SIM-01] run_simulation_pyopus: tb={tb_path.name}, sim_dir={sim_dir}")

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
    logger.debug(f"[SIM-02] tech={tech}, sim_name={sim_name}")

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
    # TODO: PyOPUS doesn't expose Spectre's output directory control. The Spectre
    # CLI supports `-raw <path>` to specify where raw files are written, but
    # PyOPUS's spectre.py hardcodes the raw file naming as {simulatorID}_group{N}.raw
    # in the current working directory, and readResults() expects this exact path.
    # As a workaround, we let PyOPUS write to project root, then move files after.
    # Future improvement: patch PyOPUS or use os.chdir() with absolute paths.
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
    logger.debug(f"[SIM-03] analyses={list(analyses.keys())}, measures={list(measures.keys())}")

    try:
        logger.debug(f"[SIM-04] Creating PerformanceEvaluator (resultsFolder={sim_dir})")
        # Create PerformanceEvaluator with native pickle storage
        # NOTE: Pass empty variables to avoid "cannot pickle module" error.
        # We don't need measure evaluation here - PostEvaluator handles that later.
        # Measures are still passed for their 'saves' directives.
        pe = PerformanceEvaluator(
            heads=heads,
            analyses=analyses,
            measures=measures,
            corners=corners,
            variables={},                   # Empty - avoid unpicklable module
            storeResults=True,              # Enable native pickle storage
            resultsFolder=str(sim_dir),     # Where to store .pck files
            cleanupAfterJob=False,          # Keep .scs/.raw until we move them
            debug=0,
        )
        logger.debug("[SIM-05] PerformanceEvaluator created")

        # Run simulation (measure evaluation will fail without variables, but we don't need it)
        logger.debug("[SIM-06] Running pe({})...")
        _results, _an_count = pe({})
        logger.debug(f"[SIM-07] pe() done: an_count={_an_count}, results={list(_results.keys()) if _results else None}")

        # TODO: Workaround for PyOPUS output location limitation (see TODO above).
        # PyOPUS writes .scs and .raw to cwd (project root). We move them to sim_dir
        # so they're organized with other results and get synced back properly.
        # This is a PyOPUS limitation, not a Spectre CLI limitation.
        import shutil
        simulator = pe.simulatorForHead["spectre"]
        pyopus_scs = Path(f"{simulator.simulatorID}_group0.scs")
        pyopus_raw = Path(f"{simulator.simulatorID}_group0.raw")
        logger.debug(f"[SIM-08] simulatorID={simulator.simulatorID}")

        # Move .scs file to sim_dir with our naming
        if pyopus_scs.exists():
            shutil.move(str(pyopus_scs), str(scs_path))
            logger.debug(f"[SIM-09] Moved {pyopus_scs} -> {scs_path}")

        # Move .raw file to sim_dir with our naming
        raw_path = sim_dir / f"{sim_name}.raw"
        if pyopus_raw.exists():
            shutil.move(str(pyopus_raw), str(raw_path))
            logger.debug(f"[SIM-10] Moved {pyopus_raw} -> {raw_path}")

        # Save resFiles mapping for PostEvaluator
        # resFiles is a dict: {(hostID, (corner, analysis)): filepath}
        resfiles_path = sim_dir / f"{sim_name}_resfiles.pck"
        logger.debug(f"[SIM-11] pe.resFiles={pe.resFiles}")
        with open(resfiles_path, "wb") as f:
            pickle.dump(pe.resFiles, f)
        logger.debug(f"[SIM-12] Pickled resFiles ({resfiles_path.stat().st_size} bytes)")

        pe.finalize()
        logger.debug("[SIM-13] Finalized, returning paths")

        return {
            "scs": scs_path,
            "log": log_path,
            "raw": raw_path,
            "resfiles": resfiles_path,
        }

    except Exception as e:
        import traceback
        logger.warning(f"Simulation failed for {tb_path.name}: {e}")
        logger.debug(f"[SIM-ERR] Traceback:\n{traceback.format_exc()}")
        return None


def run_batch_parallel(
    jobs: list[dict[str, Any]],
    sim_dir: Path,
    analyses: dict[str, Any],
    measures: dict[str, Any],
    variables: dict[str, Any],
    num_workers: int = 20,
    license_info: tuple[int, int] | None = None,
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
        license_info: Tuple of (total_licenses, busy_licenses) from check_tools()

    Returns:
        Dict mapping config_hash to dict of file paths (scs, log, raw, resfiles)
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    logger = logging.getLogger(__name__)

    # Adjust workers based on available licenses
    if license_info:
        total_lic, busy_lic = license_info
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
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
    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logging(log_file, level=log_level)

    logger.debug(f"[MAIN-01] Args: cell={args.cell}, mode={args.mode}, outdir={args.outdir}")

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
    logger.debug(f"[MAIN-02] Loading files.json from {files_db_path}")
    files = load_files_list(files_db_path)
    logger.debug(f"[MAIN-03] Loaded {len(files)} config hashes from files.json")

    cell_module = load_cell_script(block_file)
    logger.debug(f"[MAIN-04] Loaded cell module from {block_file}")

    # Get analyses and measures from cell module
    analyses = getattr(cell_module, "analyses", {})
    measures = getattr(cell_module, "measures", {})
    variables = getattr(cell_module, "variables", {})
    logger.debug(f"[MAIN-05] Cell module: analyses={list(analyses.keys())}, measures={list(measures.keys())}")

    # Import expression module for measure evaluation
    from flow import expression as m
    variables = {**variables, "m": m}
    logger.debug(f"[MAIN-06] Variables keys: {list(variables.keys())}")

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

    logger.debug(f"[MAIN-07] Built {len(jobs)} jobs from files.json")
    if jobs:
        logger.debug(f"[MAIN-08] First job: {jobs[0]}")

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

    # Verify Cadence environment and get license counts
    total_lic, busy_lic = check_tools()

    # Single mode: run only the first job (for debugging)
    if args.mode == "single":
        logger.info("SINGLE MODE: Running first simulation only (for debugging)")
        jobs = jobs[:1]

    # Run simulations
    start_time = datetime.datetime.now()
    logger.debug(f"[MAIN-09] Starting simulation (sequential={args.mode == 'single' or len(jobs) == 1})")

    if args.mode == "single" or len(jobs) == 1:
        results = run_batch_sequential(jobs, sim_dir, analyses, measures, variables)
    else:
        results = run_batch_parallel(jobs, sim_dir, analyses, measures, variables, num_workers=args.jobs, license_info=(total_lic, busy_lic))

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    logger.debug(f"[MAIN-10] Simulation done: {len(results)} successful, elapsed={elapsed:.1f}s")

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

    logger.debug(f"[MAIN-11] Saving updated files.json to {files_db_path}")
    save_files_list(files_db_path, files)
    logger.debug("[MAIN-12] files.json saved")

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
