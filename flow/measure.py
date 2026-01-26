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


# ============================================================
# Plotting Utilities
# ============================================================

# TODO: PyOPUS offers pyopus.plotter for interactive visualization, but we had
# issues using PyQt5 headlessly (Qt GUI thread starts at import, segfaults with
# offscreen platform). For now, using matplotlib Agg backend directly. Could
# revisit if headless Qt support improves or if interactive viz is needed.


def configure_matplotlib():
    """Configure matplotlib for headless plotting with LaTeX."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "text.usetex": True,
        "font.family": "serif",
        "font.serif": ["Computer Modern Roman"],
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


def run_measurements_pyopus(
    cell: str, results_dir: Path, cell_module: Any, files: dict[str, Any]
) -> dict[str, Any]:
    """
    Run measurements on simulation results using PyOPUS PostEvaluator.

    Loads resFiles mapping from simulate.py, uses PostEvaluator to extract
    measures from native PyOPUS pickle files.

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

    cell_dir = results_dir / cell
    all_results = {}

    # Try to import PyOPUS PostEvaluator
    try:
        from pyopus.evaluator.posteval import PostEvaluator
        logger.info("Using PyOPUS PostEvaluator for measurements")
    except ImportError:
        logger.error("PyOPUS PostEvaluator not available")
        return all_results

    for config_hash, file_ctx in files.items():
        resfiles_path_rel = file_ctx.get("sim_resfiles")
        if not resfiles_path_rel:
            continue

        resfiles_path = cell_dir / resfiles_path_rel
        if not resfiles_path.exists():
            logger.warning(f"  resfiles not found: {resfiles_path}")
            continue

        # Build result key from resfiles path
        result_key = resfiles_path.stem.replace("_resfiles", "")

        # Get metadata from file_ctx
        metadata = {
            "tech": file_ctx.get("tech"),
            "corner": file_ctx.get("corner"),
            "temp": file_ctx.get("temp"),
            "cfgname": file_ctx.get("cfgname"),
        }

        # Parse metadata from filename if not in file_ctx
        if not metadata["tech"]:
            parts = result_key.split("_")
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
            # Load resFiles mapping saved by simulate.py
            with open(resfiles_path, "rb") as f:
                res_files = pickle.load(f)

            # Use PostEvaluator to extract measures
            posteval = PostEvaluator(
                files=res_files,
                measures=measures,
                resultsFolder=str(cell_dir / "sim"),
                debug=0,
            )

            # Load results and evaluate all measures
            scalar_results = posteval.evaluateMeasures()

            # Handle None or empty results
            if scalar_results is None:
                scalar_results = {}

            # Flatten corner results if present (e.g., {"nominal": value} -> value)
            flat_results = {}
            for k, v in scalar_results.items():
                if isinstance(v, dict) and "nominal" in v:
                    flat_results[k] = v["nominal"]
                else:
                    flat_results[k] = v

            # Store with metadata
            all_results[result_key] = {
                "measures": flat_results,
                "metadata": metadata,
            }

            logger.info(f"  Measured: {result_key}")
            for measure_name, value in flat_results.items():
                if value is not None:
                    logger.info(f"    {measure_name}: {value}")

        except Exception as e:
            logger.warning(f"  Failed: {result_key} - {e}")
            continue

    return all_results


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

    # Count resfiles from files.json
    resfiles_count = sum(1 for ctx in files.values() if ctx.get("sim_resfiles"))
    data_file_count = resfiles_count

    if data_file_count == 0:
        logger.warning("No simulation results found in files.json")
        logger.warning(f"Run 'make sim cell={args.cell}' first")
        return 0

    logger.info("=" * 80)
    logger.info(f"Cell:       {args.cell}")
    logger.info("Flow:       measure" + (" + plot" if not args.no_plot else ""))
    logger.info(f"Data files: {data_file_count} (resfiles)")
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

    # Update files.json with plot paths (no more JSON measurement files)
    if not args.no_plot and plot_dir.exists():
        matching_plots = list(plot_dir.glob("*.pdf"))
        if matching_plots:
            for config_hash, file_ctx in files.items():
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
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
