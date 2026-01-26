"""
PyOPUS-based measurement and plotting.

Loads simulation results from .pkl files, extracts measurements using
PostEvaluator, and generates plots using pyopus.plotter.interface.

Usage:
    python -m flow.measure comp              # Run measurements and plots
    python -m flow.measure comp --no-plot    # Measurements only
"""

import argparse
import datetime
import json
import logging
import pickle
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
# Plotting Utilities
# ============================================================


def configure_matplotlib():
    """Configure matplotlib for non-interactive plotting."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "text.usetex": False,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
    })
    return plt


def save_plot_dual_format(fig, filename_base: str, plt_module) -> list[str]:
    """
    Save plot in both PDF and SVG formats.

    Args:
        fig: matplotlib figure
        filename_base: Base filename without extension
        plt_module: matplotlib.pyplot module

    Returns:
        List of saved file paths
    """
    saved = []
    try:
        fig.tight_layout()
        pdf_path = f"{filename_base}.pdf"
        fig.savefig(pdf_path)
        saved.append(pdf_path)
    except Exception:
        pass

    try:
        svg_path = f"{filename_base}.svg"
        fig.savefig(svg_path)
        saved.append(svg_path)
    except Exception:
        pass

    plt_module.close(fig)
    return saved


# ============================================================
# PyOPUS PostEvaluator Integration
# ============================================================


def load_pkl_waveforms(pkl_path: Path) -> dict[str, Any] | None:
    """
    Load waveform data from .pkl file.

    Args:
        pkl_path: Path to .pkl file

    Returns:
        Dict with waveform data or None if failed
    """
    try:
        with open(pkl_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def run_measurements_pyopus(
    cell: str, results_dir: Path, cell_module: Any, files: dict[str, Any]
) -> dict[str, Any]:
    """
    Run measurements on simulation results using PyOPUS PostEvaluator.

    Loads .pkl files from simulate.py, extracts measures, and returns results.

    Args:
        cell: Cell name
        results_dir: Results directory
        cell_module: Loaded cell module with 'measures' dict
        files: Files database from files.json

    Returns:
        Dict of all measurement results
    """
    logger = logging.getLogger(__name__)

    measures = getattr(cell_module, "measures", {})
    analyses = getattr(cell_module, "analyses", {})
    variables = getattr(cell_module, "variables", {})

    # Add expression module to variables for measure evaluation
    variables = {**variables, "m": m}

    cell_dir = results_dir / cell
    meas_dir = cell_dir / "meas"
    meas_dir.mkdir(exist_ok=True)

    all_results = {}

    # Try to use PyOPUS PostEvaluator if available
    try:
        from pyopus.evaluator.auxfunc import PostEvaluator
        use_pyopus = True
        logger.info("Using PyOPUS PostEvaluator for measurements")
    except ImportError:
        use_pyopus = False
        logger.info("PyOPUS PostEvaluator not available, using fallback")

    # Collect pkl files from files.json
    pkl_files = []
    for config_hash, file_ctx in files.items():
        for pkl_path_rel in file_ctx.get("sim_pkl", []):
            pkl_path = cell_dir / pkl_path_rel
            if pkl_path.exists():
                pkl_files.append((config_hash, pkl_path, file_ctx))

    # Fallback: also check for raw files if no pkl files
    if not pkl_files:
        for config_hash, file_ctx in files.items():
            for raw_path_rel in file_ctx.get("sim_raw", []):
                raw_path = cell_dir / raw_path_rel
                if raw_path.exists():
                    pkl_files.append((config_hash, raw_path, file_ctx))

    for config_hash, data_path, file_ctx in sorted(pkl_files, key=lambda x: x[1]):
        # Remove _group<N> suffix if present to get base name
        result_key = data_path.stem
        if "_group" in result_key:
            result_key = result_key.rsplit("_group", 1)[0]

        # Get metadata from file_ctx
        metadata = {
            "tech": file_ctx.get("tech"),
            "corner": file_ctx.get("corner"),
            "temp": file_ctx.get("temp"),
            "cfgname": file_ctx.get("cfgname"),
        }

        # Parse metadata from filename if not in file_ctx
        if not metadata["tech"]:
            parts = data_path.stem.split("_")
            for part in parts:
                if part in ["tsmc65", "tsmc28", "tower180"]:
                    metadata["tech"] = part
                    break
            # Extract corner and temp from end of filename
            if len(parts) >= 2:
                try:
                    metadata["temp"] = int(parts[-1])
                    metadata["corner"] = parts[-2]
                except (ValueError, IndexError):
                    pass

        try:
            if use_pyopus and data_path.suffix == ".pkl":
                # Load pkl data
                pkl_data = load_pkl_waveforms(data_path)
                if pkl_data is None:
                    logger.warning(f"  Failed to load: {data_path.name}")
                    continue

                # Extract results from pkl (already computed by simulate.py)
                if "results" in pkl_data:
                    scalar_results = {}
                    for k, v in pkl_data["results"].items():
                        if isinstance(v, dict) and "nominal" in v:
                            scalar_results[k] = v["nominal"]
                        else:
                            scalar_results[k] = v
                else:
                    scalar_results = {}

            else:
                # Fallback: use raw file reading
                scalar_results = run_measurements_fallback(
                    data_path, measures, variables
                )

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

            logger.info(f"  Measured: {result_key}")

        except Exception as e:
            logger.warning(f"  Failed: {result_key} - {e}")
            continue

    return all_results


def run_measurements_fallback(
    raw_path: Path, measures: dict[str, Any], variables: dict[str, Any]
) -> dict[str, Any]:
    """
    Fallback measurement extraction using raw file reading.

    Args:
        raw_path: Path to .raw file
        measures: Measures configuration
        variables: Variables for expression evaluation

    Returns:
        Dict of scalar measurement results
    """
    try:
        from pyopus.simulator.rawfile import raw_read
    except ImportError:
        return {}

    try:
        plots = raw_read(str(raw_path), reverse=1)
        if not plots:
            return {}

        # Get first plot (nominal)
        vectors, scale_name, scales, title, date, name = plots[0]

        # Build v() and i() accessor functions
        def v(node):
            key = f"v({node})"
            if key in vectors:
                return np.array(vectors[key])
            # Try alternate names
            for k in vectors:
                if k.lower() == key.lower():
                    return np.array(vectors[k])
            return np.zeros(len(scales.get(scale_name, [])))

        def i(source):
            key = f"i({source})"
            if key in vectors:
                return np.array(vectors[key])
            for k in vectors:
                if k.lower() == key.lower():
                    return np.array(vectors[k])
            return np.zeros(len(scales.get(scale_name, [])))

        def scale():
            return np.array(scales.get(scale_name, vectors.get(scale_name, [])))

        # Evaluate each measure
        results = {}
        local_vars = {**variables, "v": v, "i": i, "scale": scale, "np": np}

        for measure_name, measure_def in measures.items():
            try:
                expr = measure_def.get("expression", "0")
                value = eval(expr, {"__builtins__": {}}, local_vars)
                results[measure_name] = float(value) if value is not None else None
            except Exception:
                results[measure_name] = None

        return results

    except Exception:
        return {}


# ============================================================
# Plotting Functions
# ============================================================


def generate_plots(
    cell: str,
    results_dir: Path,
    all_results: dict[str, Any],
    cell_module: Any,
    files: dict[str, Any],
) -> list[str]:
    """
    Generate plots from measurement results.

    Args:
        cell: Cell name
        results_dir: Results directory
        all_results: Measurement results
        cell_module: Loaded cell module with visualisation config
        files: Files database

    Returns:
        List of generated plot file paths
    """
    logger = logging.getLogger(__name__)
    plt = configure_matplotlib()

    cell_dir = results_dir / cell
    plot_dir = cell_dir / "plot"
    plot_dir.mkdir(exist_ok=True)

    visualisation = getattr(cell_module, "visualisation", {})
    generated_plots = []

    if not all_results:
        logger.warning("No results to plot")
        return generated_plots

    # Extract measures from all results
    all_measures = {}
    for key, data in all_results.items():
        measures = data.get("measures", {})
        metadata = data.get("metadata", {})
        for measure_name, value in measures.items():
            if measure_name not in all_measures:
                all_measures[measure_name] = []
            all_measures[measure_name].append({
                "key": key,
                "value": value,
                "metadata": metadata,
            })

    # Create summary bar plots for scalar measures
    scalar_measures = {}
    for name, entries in all_measures.items():
        values = [e["value"] for e in entries if e["value"] is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
            scalar_measures[name] = entries

    if scalar_measures:
        # Group by technology
        techs = set()
        for entries in scalar_measures.values():
            for e in entries:
                techs.add(e["metadata"].get("tech", "unknown"))
        techs = sorted(t for t in techs if t)

        # Create a summary plot for each measure
        for measure_name, entries in scalar_measures.items():
            fig, ax = plt.subplots(figsize=(10, 6))

            # Group by tech
            tech_values = {t: [] for t in techs}
            for e in entries:
                tech = e["metadata"].get("tech", "unknown")
                val = e["value"]
                if tech in tech_values and isinstance(val, (int, float)) and not np.isnan(val):
                    tech_values[tech].append(val)

            # Create box plot or bar plot
            data = [tech_values[t] for t in techs if tech_values.get(t)]
            labels = [t for t in techs if tech_values.get(t)]

            if data and labels:
                if all(len(d) > 1 for d in data):
                    ax.boxplot(data, tick_labels=labels)
                else:
                    means = np.array([np.mean(d) if d else 0.0 for d in data])
                    ax.bar(labels, means)

                ax.set_xlabel("Technology")
                ax.set_ylabel(measure_name)
                ax.set_title(f"{cell}: {measure_name} by Technology")
                ax.grid(True, alpha=0.3)

                plot_path = plot_dir / f"{cell}_{measure_name}"
                saved = save_plot_dual_format(fig, str(plot_path), plt)
                generated_plots.extend(saved)
                logger.info(f"  Saved: {plot_path}.pdf")
            else:
                plt.close(fig)

    # Create corner comparison plots
    for measure_name in scalar_measures.keys():
        plots = plot_corner_comparison(all_results, measure_name, plot_dir, cell, plt)
        generated_plots.extend(plots)

    # Create temperature sweep plots
    for measure_name in scalar_measures.keys():
        plots = plot_temp_sweep(all_results, measure_name, plot_dir, cell, plt)
        generated_plots.extend(plots)

    # Create custom graphs from visualisation config
    graphs = visualisation.get("graphs", {})
    for graph_name, graph_config in graphs.items():
        try:
            fig, axes = create_graph_from_config(graph_config, all_results, plt)
            if fig is not None:
                plot_path = plot_dir / f"{cell}_{graph_name}"
                saved = save_plot_dual_format(fig, str(plot_path), plt)
                generated_plots.extend(saved)
                logger.info(f"  Saved: {plot_path}.pdf")
        except Exception as e:
            logger.warning(f"  Failed to create {graph_name}: {e}")

    return generated_plots


def plot_corner_comparison(
    results: dict[str, Any], measure_name: str, plot_dir: Path, cell: str, plt
) -> list[str]:
    """
    Create corner comparison plot for a specific measure.

    Args:
        results: Measurement results
        measure_name: Name of measure to plot
        plot_dir: Output directory
        cell: Cell name
        plt: matplotlib.pyplot module

    Returns:
        List of saved plot paths
    """
    logger = logging.getLogger(__name__)

    # Group by corner
    corners = {}
    for key, data in results.items():
        corner = data.get("metadata", {}).get("corner", "unknown")
        value = data.get("measures", {}).get(measure_name)
        if value is not None and isinstance(value, (int, float)):
            if corner not in corners:
                corners[corner] = []
            corners[corner].append(value)

    if len(corners) < 2:
        return []

    fig, ax = plt.subplots(figsize=(8, 6))

    corner_names = sorted(corners.keys())
    means = [np.mean(corners[c]) for c in corner_names]
    stds = [np.std(corners[c]) if len(corners[c]) > 1 else 0 for c in corner_names]

    x = np.arange(len(corner_names))
    ax.bar(x, means, yerr=stds, capsize=5)
    ax.set_xticks(x)
    ax.set_xticklabels(corner_names)
    ax.set_xlabel("Corner")
    ax.set_ylabel(measure_name)
    ax.set_title(f"{cell}: {measure_name} by Corner")
    ax.grid(True, alpha=0.3)

    plot_path = plot_dir / f"{cell}_{measure_name}_corners"
    saved = save_plot_dual_format(fig, str(plot_path), plt)
    if saved:
        logger.info(f"  Saved: {plot_path}.pdf")
    return saved


def plot_temp_sweep(
    results: dict[str, Any], measure_name: str, plot_dir: Path, cell: str, plt
) -> list[str]:
    """
    Create temperature sweep plot for a specific measure.

    Args:
        results: Measurement results
        measure_name: Name of measure to plot
        plot_dir: Output directory
        cell: Cell name
        plt: matplotlib.pyplot module

    Returns:
        List of saved plot paths
    """
    logger = logging.getLogger(__name__)

    # Group by temperature
    temps = {}
    for key, data in results.items():
        temp = data.get("metadata", {}).get("temp")
        value = data.get("measures", {}).get(measure_name)
        if temp is not None and value is not None and isinstance(value, (int, float)):
            if temp not in temps:
                temps[temp] = []
            temps[temp].append(value)

    if len(temps) < 2:
        return []

    fig, ax = plt.subplots(figsize=(8, 6))

    temp_values = sorted(temps.keys())
    means = [np.mean(temps[t]) for t in temp_values]
    stds = [np.std(temps[t]) if len(temps[t]) > 1 else 0 for t in temp_values]

    ax.errorbar(temp_values, means, yerr=stds, marker="o", capsize=5)
    ax.set_xlabel("Temperature [C]")
    ax.set_ylabel(measure_name)
    ax.set_title(f"{cell}: {measure_name} vs Temperature")
    ax.grid(True, alpha=0.3)

    plot_path = plot_dir / f"{cell}_{measure_name}_temp"
    saved = save_plot_dual_format(fig, str(plot_path), plt)
    if saved:
        logger.info(f"  Saved: {plot_path}.pdf")
    return saved


def create_graph_from_config(
    graph_config: dict[str, Any], results: dict[str, Any], plt
) -> tuple[Any, Any]:
    """
    Create a matplotlib figure from visualisation config.

    Args:
        graph_config: Graph configuration dict
        results: Measurement results
        plt: matplotlib.pyplot module

    Returns:
        Tuple of (fig, axes) or (None, None) if failed
    """
    shape = graph_config.get("shape", {"figsize": (10, 6)})
    axes_config = graph_config.get("axes", {})

    if not axes_config:
        return None, None

    # Determine subplot layout
    subplots = []
    for ax_name, ax_cfg in axes_config.items():
        subplot = ax_cfg.get("subplot", (1, 1, 1))
        subplots.append((ax_name, subplot, ax_cfg))

    # Create figure
    fig = plt.figure(**shape)
    fig.suptitle(graph_config.get("title", ""))

    axes = {}
    for ax_name, subplot, ax_cfg in subplots:
        ax = fig.add_subplot(*subplot)
        ax.set_xlabel(ax_cfg.get("xlabel", ""))
        ax.set_ylabel(ax_cfg.get("ylabel", ""))
        ax.set_title(ax_cfg.get("title", ""))
        if ax_cfg.get("grid", False):
            ax.grid(True, alpha=0.3)
        axes[ax_name] = ax

    plt.tight_layout()
    return fig, axes


# ============================================================
# Main Entry Point
# ============================================================


def main():
    """Main entry point for measurement and plotting script."""
    parser = argparse.ArgumentParser(
        description="Run measurements and generate plots from simulation results"
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
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip plot generation (measurements only)",
    )

    args = parser.parse_args()

    # Setup paths
    cell_dir = args.outdir / args.cell
    meas_dir = cell_dir / "meas"
    plot_dir = cell_dir / "plot"

    # Setup logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"meas_{args.cell}_{timestamp}.log"
    logger = setup_logging(log_file)

    # Check prerequisites
    files_db_path = cell_dir / "files.json"
    if not files_db_path.exists():
        logger.error(f"files.json not found at {files_db_path}")
        logger.error(f"Run 'make subckt cell={args.cell}' first")
        return 1

    block_file = Path(f"blocks/{args.cell}.py")
    if not block_file.exists():
        logger.error(f"Block file not found: {block_file}")
        return 1

    # Load cell module and files database
    cell_module = load_cell_script(block_file)
    files = load_files_list(files_db_path)

    # Count data files from files.json (prefer pkl, fallback to raw)
    pkl_count = sum(len(ctx.get("sim_pkl", [])) for ctx in files.values())
    raw_count = sum(len(ctx.get("sim_raw", [])) for ctx in files.values())
    data_file_count = pkl_count if pkl_count > 0 else raw_count

    if data_file_count == 0:
        logger.warning("No simulation results found in files.json")
        logger.warning(f"Run 'make sim cell={args.cell}' first")
        return 0

    logger.info("=" * 80)
    logger.info(f"Cell:       {args.cell}")
    logger.info("Flow:       measure" + (" + plot" if not args.no_plot else ""))
    logger.info(f"Data files: {data_file_count} ({'pkl' if pkl_count > 0 else 'raw'})")
    logger.info(f"Output:     {meas_dir}")
    if not args.no_plot:
        logger.info(f"Plots:      {plot_dir}")
    logger.info(f"Log:        {log_file}")
    logger.info("-" * 80)

    # Run measurements
    start_time = datetime.datetime.now()
    all_results = run_measurements_pyopus(args.cell, args.outdir, cell_module, files)
    meas_elapsed = (datetime.datetime.now() - start_time).total_seconds()

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

    # Generate plots if requested
    plot_count = 0
    plot_elapsed = 0.0
    if not args.no_plot and filtered:
        plot_start = datetime.datetime.now()
        generated_plots = generate_plots(
            args.cell, args.outdir, filtered, cell_module, files
        )
        plot_count = len(generated_plots)
        plot_elapsed = (datetime.datetime.now() - plot_start).total_seconds()

    # Update files.json with measurement and plot paths
    for config_hash, file_ctx in files.items():
        # Find matching measurement files
        matching_meas = list(meas_dir.glob(f"meas_*{config_hash}*.json"))
        if matching_meas:
            file_ctx["meas_db"] = f"meas/{matching_meas[0].name}"

        # Find matching plot files
        if not args.no_plot:
            matching_plots = list(plot_dir.glob(f"*.pdf")) if plot_dir.exists() else []
            if matching_plots:
                file_ctx["plot_img"] = [f"plot/{p.name}" for p in matching_plots]

    save_files_list(files_db_path, files)

    # Summary
    total_elapsed = meas_elapsed + plot_elapsed
    logger.info("=" * 80)
    logger.info("Measurement Summary")
    logger.info("=" * 80)
    logger.info(f"Data files:      {data_file_count}")
    logger.info(f"Measured:        {len(all_results)}")
    logger.info(f"Meas time:       {meas_elapsed:.1f}s")
    if not args.no_plot:
        logger.info(f"Plots created:   {plot_count}")
        logger.info(f"Plot time:       {plot_elapsed:.1f}s")
    logger.info(f"Total time:      {total_elapsed:.1f}s")
    logger.info(f"Output:          {meas_dir}")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
