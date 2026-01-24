"""
PyOPUS-based plotting with query-based filtering.

Generates plots from measurement results using PyOPUS EvalPlotter
or matplotlib fallback. Supports filtering by tech/corner/temp.
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from flow.common import (
    filter_results,
    load_cell_script,
    load_files_list,
    save_files_list,
    setup_logging,
)


# ============================================================
# Font Configuration
# ============================================================


def configure_fonts_for_pdf():
    """Configure LaTeX fonts for PDF output."""
    plt.rcParams.update(
        {
            "text.usetex": True,
            "font.family": "serif",
            "font.serif": ["Computer Modern Roman"],
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )


def configure_fonts_for_svg():
    """Configure sans-serif fonts for SVG output."""
    plt.rcParams.update(
        {
            "text.usetex": False,
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )


def save_plot(filename_base: str):
    """
    Save plot in both PDF and SVG formats.

    Args:
        filename_base: Base filename without extension
    """
    configure_fonts_for_pdf()
    plt.tight_layout()
    plt.savefig(f"{filename_base}.pdf")

    configure_fonts_for_svg()
    plt.tight_layout()
    plt.savefig(f"{filename_base}.svg")


# ============================================================
# Result Loading
# ============================================================


def load_all_measurements(meas_dir: Path) -> dict:
    """
    Load all measurement results from meas directory.

    Args:
        meas_dir: Directory containing meas_*.json files

    Returns:
        Dict mapping result key to {measures, metadata}
    """
    all_results = {}
    for meas_file in sorted(meas_dir.glob("meas_*.json")):
        try:
            data = json.loads(meas_file.read_text())
            key = meas_file.stem.replace("meas_", "")
            all_results[key] = data
        except Exception:
            continue
    return all_results


# ============================================================
# PyOPUS EvalPlotter Integration
# ============================================================


def plot_with_evalplotter(
    results: dict, visualisation: dict, plot_dir: Path, cell: str
):
    """
    Plot results using PyOPUS EvalPlotter.

    Args:
        results: Measurement results dict
        visualisation: Visualisation config from cell module
        plot_dir: Output directory for plots
        cell: Cell name
    """
    logger = logging.getLogger(__name__)

    try:
        from pyopus.plotter.evalplotter import EvalPlotter  # noqa: F401
        from pyopus.plotter import interface as pyplt  # noqa: F401
    except ImportError:
        logger.warning("PyOPUS EvalPlotter not available, using matplotlib fallback")
        plot_with_matplotlib(results, visualisation, plot_dir, cell)
        return

    # EvalPlotter requires a PerformanceEvaluator instance
    # For post-processing, we'd need to wrap our results
    # Falling back to matplotlib for simplicity
    logger.info("Using matplotlib for plotting (EvalPlotter requires live evaluator)")
    plot_with_matplotlib(results, visualisation, plot_dir, cell)


# ============================================================
# Matplotlib Fallback Plotting
# ============================================================


def plot_with_matplotlib(
    results: dict, visualisation: dict, plot_dir: Path, cell: str
):
    """
    Plot results using matplotlib.

    Args:
        results: Measurement results dict
        visualisation: Visualisation config from cell module
        plot_dir: Output directory for plots
        cell: Cell name
    """
    logger = logging.getLogger(__name__)

    if not results:
        logger.warning("No results to plot")
        return

    # Extract measures from all results
    all_measures = {}
    for key, data in results.items():
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
        # Check if values are scalar
        values = [e["value"] for e in entries if e["value"] is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
            scalar_measures[name] = entries

    if scalar_measures:
        # Group by technology
        techs = set()
        for entries in scalar_measures.values():
            for e in entries:
                techs.add(e["metadata"].get("tech", "unknown"))
        techs = sorted(techs)

        # Create a summary plot for each measure
        for measure_name, entries in scalar_measures.items():
            fig, ax = plt.subplots(figsize=(10, 6))

            # Group by tech
            tech_values = {t: [] for t in techs}
            for e in entries:
                tech = e["metadata"].get("tech", "unknown")
                val = e["value"]
                if isinstance(val, (int, float)) and not np.isnan(val):
                    tech_values[tech].append(val)

            # Create box plot or bar plot
            data = [tech_values[t] for t in techs if tech_values[t]]
            labels = [t for t in techs if tech_values[t]]

            if all(len(d) > 1 for d in data):
                ax.boxplot(data, labels=labels)
            else:
                means = [np.mean(d) if d else 0 for d in data]
                ax.bar(labels, means)

            ax.set_xlabel("Technology")
            ax.set_ylabel(measure_name)
            ax.set_title(f"{cell}: {measure_name} by Technology")
            ax.grid(True, alpha=0.3)

            # Save plot
            plot_path = plot_dir / f"{cell}_{measure_name}"
            save_plot(str(plot_path))
            plt.close(fig)
            logger.info(f"  Saved: {plot_path}.pdf")

    # Create comparison plots if visualisation config provided
    graphs = visualisation.get("graphs", {})
    for graph_name, graph_config in graphs.items():
        try:
            fig, axes = create_graph_from_config(
                graph_config, results, visualisation.get("traces", {})
            )
            if fig is not None:
                plot_path = plot_dir / f"{cell}_{graph_name}"
                save_plot(str(plot_path))
                plt.close(fig)
                logger.info(f"  Saved: {plot_path}.pdf")
        except Exception as e:
            logger.warning(f"  Failed to create {graph_name}: {e}")


def create_graph_from_config(
    graph_config: dict, results: dict, traces_config: dict
) -> tuple:
    """
    Create a matplotlib figure from visualisation config.

    Args:
        graph_config: Graph configuration dict
        results: Measurement results
        traces_config: Trace definitions

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
# Corner Comparison Plots
# ============================================================


def plot_corner_comparison(
    results: dict, measure_name: str, plot_dir: Path, cell: str
):
    """
    Create corner comparison plot for a specific measure.

    Args:
        results: Filtered measurement results
        measure_name: Name of measure to plot
        plot_dir: Output directory
        cell: Cell name
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

    if not corners:
        return

    fig, ax = plt.subplots(figsize=(8, 6))

    corner_names = sorted(corners.keys())
    means = [np.mean(corners[c]) for c in corner_names]
    stds = [np.std(corners[c]) for c in corner_names]

    x = np.arange(len(corner_names))
    ax.bar(x, means, yerr=stds, capsize=5)
    ax.set_xticks(x)
    ax.set_xticklabels(corner_names)
    ax.set_xlabel("Corner")
    ax.set_ylabel(measure_name)
    ax.set_title(f"{cell}: {measure_name} by Corner")
    ax.grid(True, alpha=0.3)

    plot_path = plot_dir / f"{cell}_{measure_name}_corners"
    save_plot(str(plot_path))
    plt.close(fig)
    logger.info(f"  Saved: {plot_path}.pdf")


# ============================================================
# Temperature Sweep Plots
# ============================================================


def plot_temp_sweep(
    results: dict, measure_name: str, plot_dir: Path, cell: str
):
    """
    Create temperature sweep plot for a specific measure.

    Args:
        results: Measurement results
        measure_name: Name of measure to plot
        plot_dir: Output directory
        cell: Cell name
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
        return  # Need at least 2 temperatures for sweep

    fig, ax = plt.subplots(figsize=(8, 6))

    temp_values = sorted(temps.keys())
    means = [np.mean(temps[t]) for t in temp_values]
    stds = [np.std(temps[t]) for t in temp_values]

    ax.errorbar(temp_values, means, yerr=stds, marker="o", capsize=5)
    ax.set_xlabel("Temperature [C]")
    ax.set_ylabel(measure_name)
    ax.set_title(f"{cell}: {measure_name} vs Temperature")
    ax.grid(True, alpha=0.3)

    plot_path = plot_dir / f"{cell}_{measure_name}_temp"
    save_plot(str(plot_path))
    plt.close(fig)
    logger.info(f"  Saved: {plot_path}.pdf")


# ============================================================
# Main Entry Point
# ============================================================


def main():
    """Main entry point for plotting script."""
    parser = argparse.ArgumentParser(
        description="Generate plots from measurement results"
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
        "--interactive",
        action="store_true",
        help="Show interactive plots instead of saving",
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
    log_file = log_dir / f"plot_{args.cell}_{timestamp}.log"
    logger = setup_logging(log_file)

    # Check prerequisites
    if not meas_dir.exists():
        logger.error(f"Measurement directory not found: {meas_dir}")
        logger.error(f"Run 'make meas cell={args.cell}' first")
        return 1

    block_file = Path(f"blocks/{args.cell}.py")
    if not block_file.exists():
        logger.error(f"Block file not found: {block_file}")
        return 1

    # Load cell module for visualisation config
    cell_module = load_cell_script(block_file)
    visualisation = getattr(cell_module, "visualisation", {})

    # Load all measurement results
    all_results = load_all_measurements(meas_dir)

    if not all_results:
        logger.warning(f"No measurement results found in {meas_dir}")
        return 0

    # Apply filters
    filtered = filter_results(
        all_results,
        tech=args.tech,
        corner=args.corner,
        temp=args.temp,
    )

    logger.info("=" * 80)
    logger.info(f"Cell:       {args.cell}")
    logger.info("Flow:       plot")
    logger.info(f"Results:    {len(filtered)} (filtered from {len(all_results)})")
    logger.info(f"Output:     {plot_dir}")
    logger.info(f"Log:        {log_file}")
    if args.tech:
        logger.info(f"Tech:       {args.tech}")
    if args.corner:
        logger.info(f"Corner:     {args.corner}")
    if args.temp:
        logger.info(f"Temp:       {args.temp}")
    logger.info("-" * 80)

    if not filtered:
        logger.error("No results match the specified filters")
        return 1

    # Create output directory
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Configure matplotlib
    if not args.interactive:
        plt.switch_backend("Agg")

    # Generate plots
    start_time = datetime.datetime.now()

    if visualisation:
        plot_with_evalplotter(filtered, visualisation, plot_dir, args.cell)
    else:
        plot_with_matplotlib(filtered, {}, plot_dir, args.cell)

    # Generate corner comparison plots
    measures = set()
    for data in filtered.values():
        measures.update(data.get("measures", {}).keys())

    for measure_name in measures:
        plot_corner_comparison(filtered, measure_name, plot_dir, args.cell)
        plot_temp_sweep(filtered, measure_name, plot_dir, args.cell)

    elapsed = (datetime.datetime.now() - start_time).total_seconds()

    # Update files.json with plot paths
    files_db_path = cell_dir / "files.json"
    if files_db_path.exists():
        files = load_files_list(files_db_path)
        for config_hash, file_ctx in files.items():
            matching_plots = list(plot_dir.glob(f"*{config_hash}*.pdf"))
            if matching_plots:
                file_ctx["plot_img"] = [f"plot/{p.name}" for p in matching_plots]
        save_files_list(files_db_path, files)

    # Summary
    logger.info("=" * 80)
    logger.info("Plotting Summary")
    logger.info("=" * 80)
    logger.info(f"Results plotted: {len(filtered)}")
    logger.info(f"Elapsed time:    {elapsed:.1f}s")
    logger.info(f"Output:          {plot_dir}")
    logger.info("=" * 80)

    if args.interactive:
        plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())
