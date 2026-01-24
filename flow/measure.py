"""
PyOPUS-based measurement extraction.

Runs measurements on simulation results using PyOPUS PerformanceEvaluator
or custom helper functions. Results are saved as JSON files with metadata.
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

import numpy as np

from flow.common import (
    filter_results,
    load_cell_script,
    load_files_list,
    save_files_list,
    setup_logging,
)


# ============================================================
# Waveform Reading Utilities
# ============================================================


def read_traces(raw):
    """
    Return time and all traces as tuple of numpy arrays.

    Args:
        raw: RawRead object from spicelib

    Returns:
        Tuple of (time, trace1, trace2, ...) numpy arrays
    """
    time = raw.get_axis()
    traces = tuple(
        raw.get_wave(name) for name in raw.get_trace_names() if name.lower() != "time"
    )
    return (time,) + traces


def quantize(signal, bits=1, max_val=1.2, min_val=0):
    """
    Quantize signal to N bits between min and max.

    Args:
        signal: numpy array of analog values
        bits: number of quantization bits
        max_val: maximum value
        min_val: minimum value

    Returns:
        Quantized numpy array
    """
    levels = 2**bits
    step = (max_val - min_val) / levels
    quantized = np.floor((signal - min_val) / step) * step + min_val
    return np.clip(quantized, min_val, max_val)


def digitize(signal, threshold=None, vdd=1.2):
    """
    Digitize analog signal to binary (1 or 0) based on threshold.

    Args:
        signal: numpy array of analog voltages
        threshold: voltage threshold (default: vdd/2)
        vdd: supply voltage

    Returns:
        numpy array of 1s and 0s
    """
    if threshold is None:
        threshold = vdd / 2
    return np.where(signal > threshold, 1, 0)


# ============================================================
# Comparator-specific Measurements (Custom - not in PyOPUS)
# ============================================================


def comparator_offset_mV(v_func, scale_func, param, n_samples=100):
    """
    Measure comparator input-referred offset from decision statistics.

    Custom function - not available in PyOPUS built-ins.
    Uses repeated sampling at threshold to estimate offset.

    Args:
        v_func: Voltage accessor function v('nodename')
        scale_func: Time scale function
        param: Parameter dictionary with 'vdd' etc.
        n_samples: Number of samples per test point

    Returns:
        Offset in millivolts
    """
    _ = scale_func()  # Time axis (unused but required for interface)
    voutp = v_func("outp")
    voutn = v_func("outn")
    vclk = v_func("clk")
    vdd = param.get("vdd", 1.8)

    # Find clock falling edges (decision sampling moments)
    above = vclk > vdd / 2
    clk_fall = np.where(np.diff(above.astype(int)) < 0)[0]

    # Get decisions at each sample
    decisions = [(voutp[idx] > voutn[idx]) for idx in clk_fall if idx < len(voutp)]

    # Offset estimation from P(ONE) deviation from 0.5
    if not decisions:
        return float("nan")

    p_one = np.mean(decisions)
    # Rough mV estimate (simplified - full implementation uses binary search)
    offset_mV = (p_one - 0.5) * 100

    return float(offset_mV)


# ============================================================
# CDAC/ADC Linearity Measurements (Custom - not in PyOPUS)
# ============================================================


def calculate_inl(vin, vout):
    """
    Calculate Integral Nonlinearity from best-fit line.

    INL measures deviation from ideal linear transfer function.

    Args:
        vin: Input voltage array (ideal ramp)
        vout: Output voltage array (measured)

    Returns:
        Tuple of (inl_array, inl_max) - INL at each code and maximum |INL|
    """
    coeffs = np.polyfit(vin, vout, 1)
    ideal = np.polyval(coeffs, vin)
    inl = vout - ideal
    return inl, float(np.max(np.abs(inl)))


def calculate_dnl(vout, ideal_lsb=None):
    """
    Calculate Differential Nonlinearity.

    DNL measures difference between actual and ideal step sizes.

    Args:
        vout: Output voltage array
        ideal_lsb: Expected step size (if None, uses mean step)

    Returns:
        Tuple of (dnl_array, dnl_max) - DNL at each step and maximum |DNL|
    """
    steps = np.diff(vout)
    if ideal_lsb is None:
        ideal_lsb = np.mean(steps)
    if ideal_lsb == 0:
        return np.zeros(len(steps)), 0.0
    dnl = (steps - ideal_lsb) / ideal_lsb
    return dnl, float(np.max(np.abs(dnl)))


def extract_settled_values(vout, time, n_codes, settle_fraction=0.9):
    """
    Extract settled output values from stepped waveform.

    Assumes vout has n_codes steps, samples at settle_fraction of each period.

    Args:
        vout: Output voltage waveform
        time: Time array
        n_codes: Number of DAC codes
        settle_fraction: Fraction of period to wait for settling

    Returns:
        Array of settled values at each code
    """
    period = time[-1] / n_codes
    settled_times = [(i + settle_fraction) * period for i in range(n_codes)]
    settled_values = np.interp(settled_times, time, vout)
    return settled_values


# ============================================================
# PyOPUS PerformanceEvaluator Wrapper
# ============================================================


def run_measurements_pyopus(
    cell: str, results_dir: Path, cell_module
) -> dict:
    """
    Run measurements on all simulation results using PyOPUS PerformanceEvaluator.

    Args:
        cell: Cell name
        results_dir: Results directory
        cell_module: Loaded cell module with 'measures' dict

    Returns:
        Dict of all measurement results
    """
    logger = logging.getLogger(__name__)

    try:
        from pyopus.evaluator.performance import PerformanceEvaluator
    except ImportError:
        logger.warning("PyOPUS not available, using fallback measurement runner")
        return run_measurements_fallback(cell, results_dir, cell_module)

    measures = getattr(cell_module, "measures", {})
    analyses = getattr(cell_module, "analyses", {})
    variables = getattr(cell_module, "variables", {})

    sim_dir = results_dir / cell / "sim"
    meas_dir = results_dir / cell / "meas"
    meas_dir.mkdir(exist_ok=True)

    all_results = {}

    for raw_file in sorted(sim_dir.glob("sim_*.raw")):
        result_key = raw_file.stem.replace("sim_", "")

        # Load metadata
        meta_file = raw_file.with_suffix(".meta.json")
        if meta_file.exists():
            metadata = json.loads(meta_file.read_text())
        else:
            metadata = {}

        try:
            # Build minimal PyOPUS config for this single result
            heads = {
                "local": {
                    "simulator": "Spectre",
                    "moddefs": {"result": {"file": str(raw_file)}},
                }
            }

            # Single "nominal" corner - no multi-corner complexity
            corners = {"nominal": {"modules": ["result"], "params": {}}}

            # Create evaluator
            pe = PerformanceEvaluator(
                heads, analyses, measures, corners,
                variables=variables,
                debug=0,
            )

            # Run (no input params needed - results already computed)
            results, _ = pe({})

            # Extract scalar values from results
            scalar_results = {}
            for k, v in results.items():
                if isinstance(v, dict) and "nominal" in v:
                    scalar_results[k] = v["nominal"]
                else:
                    scalar_results[k] = v

            # Store with metadata
            all_results[result_key] = {
                "measures": scalar_results,
                "metadata": metadata,
            }

            # Save individual result file
            meas_file = meas_dir / f"meas_{result_key}.json"
            meas_file.write_text(
                json.dumps(
                    {"measures": scalar_results, "metadata": metadata},
                    indent=2,
                    default=str,
                )
            )

            pe.finalize()
            logger.info(f"  Measured: {result_key}")

        except Exception as e:
            logger.warning(f"  Failed: {result_key} - {e}")
            continue

    return all_results


def run_measurements_fallback(
    cell: str, results_dir: Path, cell_module
) -> dict:
    """
    Fallback measurement runner when PyOPUS is unavailable.

    Uses spicelib to read raw files and calls cell-specific measure() function.

    Args:
        cell: Cell name
        results_dir: Results directory
        cell_module: Loaded cell module

    Returns:
        Dict of all measurement results
    """
    logger = logging.getLogger(__name__)

    try:
        from spicelib import RawRead
    except ImportError:
        logger.error("spicelib not installed")
        return {}

    sim_dir = results_dir / cell / "sim"
    meas_dir = results_dir / cell / "meas"
    meas_dir.mkdir(exist_ok=True)

    # Check if cell has custom measure() function
    has_custom_measure = hasattr(cell_module, "measure")

    all_results = {}

    for raw_file in sorted(sim_dir.glob("sim_*.raw")):
        result_key = raw_file.stem.replace("sim_", "")

        # Load metadata
        meta_file = raw_file.with_suffix(".meta.json")
        if meta_file.exists():
            metadata = json.loads(meta_file.read_text())
        else:
            metadata = {}

        try:
            # Read raw file
            raw = RawRead(
                str(raw_file), traces_to_read="*", dialect="ngspice", verbose=False
            )

            if has_custom_measure:
                # Use cell-specific measure function
                # Find matching subckt and tb JSON files
                subckt_dir = results_dir / cell / "subckt"
                tb_dir = results_dir / cell / "tb"

                subckt_json = {}
                tb_json = {}

                # Try to load subckt json based on metadata
                config_hash = metadata.get("config_hash", "")
                if config_hash:
                    subckt_files = list(subckt_dir.glob(f"*{config_hash}*.json"))
                    if subckt_files:
                        subckt_json = json.loads(subckt_files[0].read_text())

                    tb_files = list(tb_dir.glob(f"*{config_hash}*.json"))
                    if tb_files:
                        tb_json = json.loads(tb_files[0].read_text())

                # Call cell-specific measure function
                results = cell_module.measure(raw, subckt_json, tb_json, str(raw_file))
            else:
                # Basic measurements
                time = raw.get_axis()
                trace_names = raw.get_trace_names()

                results = {
                    "sim_time_ns": float(time[-1] * 1e9) if len(time) > 0 else 0,
                    "num_traces": len(trace_names),
                    "num_points": len(time),
                }

            # Store with metadata
            all_results[result_key] = {
                "measures": results,
                "metadata": metadata,
            }

            # Save individual result file
            meas_file = meas_dir / f"meas_{result_key}.json"
            meas_file.write_text(
                json.dumps(
                    {"measures": results, "metadata": metadata},
                    indent=2,
                    default=str,
                )
            )

            logger.info(f"  Measured: {result_key}")

        except Exception as e:
            logger.warning(f"  Failed: {result_key} - {e}")
            continue

    return all_results


def main():
    """Main entry point for measurement script."""
    parser = argparse.ArgumentParser(
        description="Run measurements on simulation results"
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
        "--corner",
        type=str,
        default=None,
        help="Filter by corner (e.g., tt, ss, ff)",
    )
    parser.add_argument(
        "--temp",
        type=int,
        default=None,
        help="Filter by temperature (e.g., 27)",
    )

    args = parser.parse_args()

    # Setup paths
    cell_dir = args.outdir / args.cell
    sim_dir = cell_dir / "sim"
    meas_dir = cell_dir / "meas"

    # Setup logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"meas_{args.cell}_{timestamp}.log"
    logger = setup_logging(log_file)

    # Check prerequisites
    if not sim_dir.exists():
        logger.error(f"Simulation directory not found: {sim_dir}")
        logger.error(f"Run 'make sim cell={args.cell}' first")
        return 1

    block_file = Path(f"blocks/{args.cell}.py")
    if not block_file.exists():
        logger.error(f"Block file not found: {block_file}")
        return 1

    # Load cell module
    cell_module = load_cell_script(block_file)

    # Count raw files
    raw_files = list(sim_dir.glob("sim_*.raw"))
    if not raw_files:
        logger.warning(f"No simulation results found in {sim_dir}")
        return 0

    logger.info("=" * 80)
    logger.info(f"Cell:       {args.cell}")
    logger.info("Flow:       measure")
    logger.info(f"Raw files:  {len(raw_files)}")
    logger.info(f"Output:     {meas_dir}")
    logger.info(f"Log:        {log_file}")
    logger.info("-" * 80)

    # Run measurements
    start_time = datetime.datetime.now()
    all_results = run_measurements_pyopus(args.cell, args.outdir, cell_module)
    elapsed = (datetime.datetime.now() - start_time).total_seconds()

    # Apply filters if specified
    if args.tech or args.corner or args.temp:
        filtered = filter_results(
            all_results,
            tech=args.tech,
            corner=args.corner,
            temp=args.temp,
        )
        logger.info(f"Filtered: {len(filtered)} of {len(all_results)} results")
    else:
        filtered = all_results

    # Update files.json with measurement paths
    files_db_path = cell_dir / "files.json"
    if files_db_path.exists():
        files = load_files_list(files_db_path)
        for config_hash, file_ctx in files.items():
            matching_meas = list(meas_dir.glob(f"meas_*{config_hash}*.json"))
            if matching_meas:
                file_ctx["meas_db"] = f"meas/{matching_meas[0].name}"
        save_files_list(files_db_path, files)

    # Summary
    logger.info("=" * 80)
    logger.info("Measurement Summary")
    logger.info("=" * 80)
    logger.info(f"Total raw files:   {len(raw_files)}")
    logger.info(f"Measured:          {len(all_results)}")
    logger.info(f"Elapsed time:      {elapsed:.1f}s")
    logger.info(f"Output:            {meas_dir}")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
