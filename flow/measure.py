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
from typing import Any

import numpy as np

from flow.common import (
    filter_results,
    load_cell_script,
    load_files_list,
    save_files_list,
    setup_logging,
)
from flow import expression as m  # User-defined measurement functions


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
# Digital Gate Timing Measurements
# ============================================================


def inv_tphl_ns(v_func, scale_func, inp, out, vdd=None):
    """
    Measure inverter propagation delay high-to-low (input rising -> output falling).

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp: Input node name
        out: Output node name
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Propagation delay in nanoseconds
    """
    time = scale_func()
    vin = v_func(inp)
    vout = v_func(out)

    if vdd is None:
        vdd = max(np.max(vin), np.max(vout))
    threshold = vdd / 2

    in_rising = m._find_crossings(vin, time, threshold, rising=True)
    out_falling = m._find_crossings(vout, time, threshold, rising=False)

    if not in_rising or not out_falling:
        return float('nan')

    # Find first output falling after first input rising
    for t_in in in_rising:
        for t_out in out_falling:
            if t_out > t_in:
                return float((t_out - t_in) * 1e9)

    return float('nan')


def inv_tplh_ns(v_func, scale_func, inp, out, vdd=None):
    """
    Measure inverter propagation delay low-to-high (input falling -> output rising).

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp: Input node name
        out: Output node name
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Propagation delay in nanoseconds
    """
    time = scale_func()
    vin = v_func(inp)
    vout = v_func(out)

    if vdd is None:
        vdd = max(np.max(vin), np.max(vout))
    threshold = vdd / 2

    in_falling = m._find_crossings(vin, time, threshold, rising=False)
    out_rising = m._find_crossings(vout, time, threshold, rising=True)

    if not in_falling or not out_rising:
        return float('nan')

    # Find first output rising after first input falling
    for t_in in in_falling:
        for t_out in out_rising:
            if t_out > t_in:
                return float((t_out - t_in) * 1e9)

    return float('nan')


def rise_time_ns(v_func, scale_func, node, low_frac=0.1, high_frac=0.9, vdd=None):
    """
    Measure rise time (10% to 90% by default).

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        node: Node name to measure
        low_frac: Low threshold as fraction of vdd
        high_frac: High threshold as fraction of vdd
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Rise time in nanoseconds
    """
    time = scale_func()
    v = v_func(node)

    if vdd is None:
        vdd = np.max(v)

    low_thresh = vdd * low_frac
    high_thresh = vdd * high_frac

    low_crossings = m._find_crossings(v, time, low_thresh, rising=True)
    high_crossings = m._find_crossings(v, time, high_thresh, rising=True)

    if not low_crossings or not high_crossings:
        return float('nan')

    # Find first high crossing after first low crossing
    t_low = low_crossings[0]
    for t_high in high_crossings:
        if t_high > t_low:
            return float((t_high - t_low) * 1e9)

    return float('nan')


def fall_time_ns(v_func, scale_func, node, high_frac=0.9, low_frac=0.1, vdd=None):
    """
    Measure fall time (90% to 10% by default).

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        node: Node name to measure
        high_frac: High threshold as fraction of vdd
        low_frac: Low threshold as fraction of vdd
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Fall time in nanoseconds
    """
    time = scale_func()
    v = v_func(node)

    if vdd is None:
        vdd = np.max(v)

    high_thresh = vdd * high_frac
    low_thresh = vdd * low_frac

    high_crossings = m._find_crossings(v, time, high_thresh, rising=False)
    low_crossings = m._find_crossings(v, time, low_thresh, rising=False)

    if not high_crossings or not low_crossings:
        return float('nan')

    # Find first low crossing after first high crossing
    t_high = high_crossings[0]
    for t_low in low_crossings:
        if t_low > t_high:
            return float((t_low - t_high) * 1e9)

    return float('nan')


def avg_power_uW(v_func, i_func, scale_func, supply_node):
    """
    Measure average power consumption.

    Args:
        v_func: Voltage accessor v('nodename')
        i_func: Current accessor i('source')
        scale_func: Time scale function
        supply_node: Supply voltage source name

    Returns:
        Average power in microwatts
    """
    time = scale_func()
    v = v_func(supply_node)
    i = i_func(supply_node)

    # Power = V * I, integrate over time and divide by total time
    if len(time) < 2:
        return float('nan')

    power = v * np.abs(i)  # Use abs since current may be negative
    avg_power = np.trapz(power, time) / (time[-1] - time[0])

    return float(avg_power * 1e6)  # Convert to uW


def voh_V(v_func, node):
    """
    Measure output high voltage (maximum output).

    Args:
        v_func: Voltage accessor v('nodename')
        node: Output node name

    Returns:
        VOH in volts
    """
    v = v_func(node)
    return float(np.max(v))


def vol_V(v_func, node):
    """
    Measure output low voltage (minimum output).

    Args:
        v_func: Voltage accessor v('nodename')
        node: Output node name

    Returns:
        VOL in volts
    """
    v = v_func(node)
    return float(np.min(v))


def nand2_tphl_ns(v_func, scale_func, inp_a, inp_b, out, vdd=None):
    """
    Measure NAND2 propagation delay high-to-low.

    Output goes low when both inputs are high.

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp_a: Input A node name
        inp_b: Input B node name
        out: Output node name
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Propagation delay in nanoseconds
    """
    time = scale_func()
    va = v_func(inp_a)
    vb = v_func(inp_b)
    vout = v_func(out)

    if vdd is None:
        vdd = max(np.max(va), np.max(vb), np.max(vout))
    threshold = vdd / 2

    # NAND output falls when BOTH inputs are high
    # Find when the second input goes high (AND condition met)
    both_high = (va > threshold) & (vb > threshold)
    out_falling = m._find_crossings(vout, time, threshold, rising=False)

    if not out_falling:
        return float('nan')

    # Find transitions into both-high state
    both_high_edges = []
    for i in range(len(both_high) - 1):
        if not both_high[i] and both_high[i + 1]:
            both_high_edges.append(time[i])

    if not both_high_edges:
        return float('nan')

    # Find first output falling after first both-high
    t_trigger = both_high_edges[0]
    for t_out in out_falling:
        if t_out > t_trigger:
            return float((t_out - t_trigger) * 1e9)

    return float('nan')


def nand2_tplh_ns(v_func, scale_func, inp_a, inp_b, out, vdd=None):
    """
    Measure NAND2 propagation delay low-to-high.

    Output goes high when either input goes low.

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp_a: Input A node name
        inp_b: Input B node name
        out: Output node name
        vdd: Supply voltage (if None, estimated from signal max)

    Returns:
        Propagation delay in nanoseconds
    """
    time = scale_func()
    va = v_func(inp_a)
    vb = v_func(inp_b)
    vout = v_func(out)

    if vdd is None:
        vdd = max(np.max(va), np.max(vb), np.max(vout))
    threshold = vdd / 2

    # NAND output rises when either input goes low
    out_rising = m._find_crossings(vout, time, threshold, rising=True)

    if not out_rising:
        return float('nan')

    # Find when both-high state ends (either input falls)
    both_high = (va > threshold) & (vb > threshold)
    exit_both_high = []
    for i in range(len(both_high) - 1):
        if both_high[i] and not both_high[i + 1]:
            exit_both_high.append(time[i])

    if not exit_both_high:
        return float('nan')

    # Find first output rising after first exit from both-high
    t_trigger = exit_both_high[0]
    for t_out in out_rising:
        if t_out > t_trigger:
            return float((t_out - t_trigger) * 1e9)

    return float('nan')


# ============================================================
# ADC Linearity Measurements
# ============================================================


def adc_inl_max_lsb(v_func, scale_func, inp_p, inp_n, out, n_bits, vref=1.0):
    """
    Measure ADC maximum Integral Nonlinearity.

    INL measures deviation from ideal linear transfer function.

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out: Comparator output node name
        n_bits: ADC resolution
        vref: Reference voltage

    Returns:
        Maximum INL in LSBs
    """
    scale_func()  # Called for side effects (time axis setup)
    vin_p = v_func(inp_p)
    vin_n = v_func(inp_n)
    vin_diff = vin_p - vin_n

    # Get the comparator output (digitized)
    vout = v_func(out)
    vout_digital = digitize(vout, vdd=vref)

    # For full INL calculation, we need to sweep through all codes
    # This is a simplified measurement - assumes input is ramping
    lsb = vref / (2**n_bits)

    # Calculate ideal and actual transfer function
    vin_normalized = np.clip(vin_diff, -vref/2, vref/2) + vref/2
    ideal_code = vin_normalized / lsb

    # Use linear fit to find actual transfer
    coeffs = np.polyfit(vin_normalized, vout_digital * (2**n_bits - 1), 1)
    actual_code = np.polyval(coeffs, vin_normalized)

    # INL is deviation from ideal
    inl = actual_code - ideal_code
    return float(np.max(np.abs(inl)))


def adc_dnl_max_lsb(v_func, scale_func, inp_p, inp_n, out, n_bits, vref=1.0):
    """
    Measure ADC maximum Differential Nonlinearity.

    DNL measures deviation of code widths from ideal 1 LSB.

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out: Comparator output node name
        n_bits: ADC resolution
        vref: Reference voltage

    Returns:
        Maximum DNL in LSBs
    """
    time = scale_func()
    vin_p = v_func(inp_p)
    vin_n = v_func(inp_n)
    vin_diff = vin_p - vin_n

    vout = v_func(out)
    _ = digitize(vout, vdd=vref)  # Available for future use

    lsb = vref / (2**n_bits)

    # Simplified DNL - measure step widths
    vin_normalized = np.clip(vin_diff, -vref/2, vref/2) + vref/2

    # Find code transitions
    transitions = []
    for code in range(1, 2**n_bits):
        threshold = code * lsb
        # Find where input crosses this threshold
        crossings = m._find_crossings(vin_normalized, time, threshold, rising=True)
        if crossings:
            transitions.append(crossings[0])

    if len(transitions) < 2:
        return float('nan')

    # DNL = (actual step width - ideal step width) / ideal step width
    step_widths = np.diff(transitions)
    ideal_width = np.mean(step_widths)  # or (time[-1] - time[0]) / (2**n_bits - 1)
    dnl = (step_widths - ideal_width) / ideal_width

    return float(np.max(np.abs(dnl)))


def adc_enob(v_func, scale_func, inp_p, inp_n, out, n_bits, vref=1.0):
    """
    Measure ADC Effective Number of Bits.

    ENOB accounts for all noise and distortion sources.
    ENOB = (SINAD - 1.76) / 6.02

    Args:
        v_func: Voltage accessor v('nodename')
        scale_func: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out: Comparator output node name
        n_bits: Nominal ADC resolution
        vref: Reference voltage

    Returns:
        Effective number of bits
    """
    # Simplified ENOB based on INL/DNL
    # Full ENOB requires FFT-based SINAD calculation
    inl_max = adc_inl_max_lsb(v_func, scale_func, inp_p, inp_n, out, n_bits, vref)
    dnl_max = adc_dnl_max_lsb(v_func, scale_func, inp_p, inp_n, out, n_bits, vref)

    if np.isnan(inl_max) or np.isnan(dnl_max):
        return float('nan')

    # Approximate ENOB reduction from INL/DNL
    # This is a rough estimate - proper ENOB needs sine wave input and FFT
    quantization_noise_lsb = max(inl_max, dnl_max)
    snr_loss = 20 * np.log10(quantization_noise_lsb + 1)  # dB
    enob = n_bits - snr_loss / 6.02

    return float(enob)


def adc_power_uW(v_func, i_func, scale_func, supply_a, supply_d):
    """
    Measure total ADC power consumption.

    Args:
        v_func: Voltage accessor v('nodename')
        i_func: Current accessor i('source')
        scale_func: Time scale function
        supply_a: Analog supply node name
        supply_d: Digital supply node name

    Returns:
        Total power in microwatts
    """
    time = scale_func()

    # Analog power
    v_a = v_func(supply_a)
    i_a = i_func(supply_a)
    power_a = v_a * np.abs(i_a)

    # Digital power
    v_d = v_func(supply_d)
    i_d = i_func(supply_d)
    power_d = v_d * np.abs(i_d)

    # Total average power
    total_power = power_a + power_d
    if len(time) < 2:
        return float('nan')

    avg_power = np.trapz(total_power, time) / (time[-1] - time[0])
    return float(avg_power * 1e6)  # Convert to uW


# ============================================================
# PyOPUS PerformanceEvaluator Wrapper
# ============================================================


def run_measurements_pyopus(
    cell: str, results_dir: Path, cell_module: Any
) -> dict[str, Any]:
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
        logger.error("PyOPUS not available - cannot run measurements")
        return {}

    measures = getattr(cell_module, "measures", {})
    analyses = getattr(cell_module, "analyses", {})
    variables = getattr(cell_module, "variables", {})

    # Add expression module to variables for measure evaluation
    variables = {**variables, "m": m}

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
