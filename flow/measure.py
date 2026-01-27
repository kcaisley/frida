"""
PyOPUS-based measurement and plotting.

Flow Overview
=============
This script is the second half of a split workflow (see simulate.py for part 1):

    1. simulate.py ran on remote server, produced:
       - .raw file (Spectre output, viewable in waveform viewer)
       - .pck files (PyOPUS pickled waveforms with parsed time/voltage arrays)
       - _resfiles.pck (mapping of (corner, analysis) -> .pck filepath)

    2. rsync brought results back to local machine

    3. measure.py (this script) runs locally:
       - PostEvaluator loads .pck files (no Spectre needed)
       - Provides v('signal') and scale('analysis') accessors to expressions
       - Evaluates measure expressions defined in blocks/<cell>.py
       - Generates plots from scalar and vector measure results

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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
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
    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logging(log_file, level=log_level)

    logger.debug(f"[MEAS-01] Args: cell={args.cell}, outdir={args.outdir}, no_plot={args.no_plot}")
    logger.debug(f"[MEAS-02] cell_dir={cell_dir}, plot_dir={plot_dir}")

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
    logger.debug(f"[MEAS-03] Loading cell module from {block_file}")
    cell_module = load_cell_script(block_file)
    logger.debug(f"[MEAS-04] Cell module loaded, attrs: {[a for a in dir(cell_module) if not a.startswith('_')]}")

    logger.debug(f"[MEAS-05] Loading files.json from {files_db_path}")
    files = load_files_list(files_db_path)
    logger.debug(f"[MEAS-06] Loaded {len(files)} config hashes from files.json")

    # Count resfiles from files.json
    resfiles_count = sum(1 for ctx in files.values() if ctx.get("sim_resfiles"))
    data_file_count = resfiles_count
    logger.debug(f"[MEAS-07] Found {resfiles_count} configs with sim_resfiles")

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
            for _config_hash, file_ctx in files.items():
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

    logger.debug(f"[MEAS-10] run_measurements_pyopus: cell={cell}, results_dir={results_dir}")

    measures = getattr(cell_module, "measures", {})
    variables = getattr(cell_module, "variables", {})
    logger.debug(f"[MEAS-11] measures keys: {list(measures.keys())}")
    logger.debug(f"[MEAS-12] variables keys: {list(variables.keys())}")
    if measures:
        first_measure = list(measures.keys())[0]
        logger.debug(f"[MEAS-13] First measure '{first_measure}': {measures[first_measure]}")

    cell_dir = results_dir / cell
    all_results = {}

    # Try to import PyOPUS PostEvaluator
    try:
        from pyopus.evaluator.posteval import PostEvaluator
        logger.debug("[MEAS-14] PyOPUS PostEvaluator imported successfully")
        logger.info("Using PyOPUS PostEvaluator for measurements")
    except ImportError:
        logger.error("PyOPUS PostEvaluator not available")
        return all_results

    logger.debug(f"[MEAS-15] Processing {len(files)} file contexts from files.json")

    for _config_hash, file_ctx in files.items():
        resfiles_path_rel = file_ctx.get("sim_resfiles")
        if not resfiles_path_rel:
            logger.debug(f"[MEAS-16] Skipping {_config_hash}: no sim_resfiles")
            continue

        resfiles_path = cell_dir / resfiles_path_rel
        if not resfiles_path.exists():
            logger.warning(f"  resfiles not found: {resfiles_path}")
            continue

        # Build result key from resfiles path
        result_key = resfiles_path.stem.replace("_resfiles", "")
        logger.debug(f"[MEAS-17] Processing {result_key}")

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
            logger.debug(f"[MEAS-18] Loading resFiles from {resfiles_path}")
            with open(resfiles_path, "rb") as f:
                res_files = pickle.load(f)
            logger.debug(f"[MEAS-19] res_files raw: {res_files}")

            # PerformanceEvaluator.resFiles uses keys (hostID, (corner, analysis))
            # PostEvaluator expects keys (corner, analysis) - strip the hostID
            # Also extract just basename since stored paths may be from remote server
            posteval_files = {}
            for key, filepath in res_files.items():
                _host_id, corner_analysis = key
                posteval_files[corner_analysis] = Path(filepath).name
            logger.debug(f"[MEAS-20] posteval_files (transformed): {posteval_files}")

            # TODO: PyOPUS bug workaround - PostEvaluator.evaluateMeasures() at line 242
            # in pyopus/evaluator/posteval.py iterates measure['depends'] without checking
            # if the key exists (unlike line 89 which properly checks). The 'depends' key
            # is only needed for derived measures that compute from other measures, not for
            # measures that compute directly from waveforms. Fix PyOPUS, then remove this.
            patched_measures = {}
            for name, meas in measures.items():
                patched_measures[name] = dict(meas)
                if "depends" not in patched_measures[name]:
                    patched_measures[name]["depends"] = []
            logger.debug(f"[MEAS-21] patched_measures keys: {list(patched_measures.keys())}")

            # Use PostEvaluator to extract measures
            logger.debug(f"[MEAS-22] Creating PostEvaluator (resultsFolder={cell_dir / 'sim'})")
            posteval = PostEvaluator(
                files=posteval_files,
                measures=patched_measures,
                resultsFolder=str(cell_dir / "sim"),
                debug=0,
            )
            logger.debug("[MEAS-23] PostEvaluator created")

            # Load results and evaluate all measures
            logger.debug("[MEAS-24] Calling posteval.evaluateMeasures()...")
            scalar_results = posteval.evaluateMeasures()
            logger.debug(f"[MEAS-25] evaluateMeasures returned: {scalar_results}")

            # Handle None or empty results
            if scalar_results is None:
                logger.debug("[MEAS-26] scalar_results is None, using empty dict")
                scalar_results = {}

            # Flatten corner results if present (e.g., {"nominal": value} -> value)
            flat_results = {}
            for k, v in scalar_results.items():
                if isinstance(v, dict) and "nominal" in v:
                    flat_results[k] = v["nominal"]
                else:
                    flat_results[k] = v
            logger.debug(f"[MEAS-27] flat_results: {flat_results}")

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
            import traceback
            logger.warning(f"  Failed: {result_key} - {e}")
            logger.debug(f"[MEAS-ERR] Traceback:\n{traceback.format_exc()}")
            continue

    logger.debug(f"[MEAS-28] Returning {len(all_results)} results")
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
        files: Files database with paths to simulation pickle files

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

    # Create graphs from visualisation config with traces
    graphs = visualisation.get("graphs", {})
    traces = visualisation.get("traces", {})
    styles = visualisation.get("styles", [])
    special_plots = visualisation.get("special_plots", {})

    for graph_name, graph_config in graphs.items():
        # Check if this graph has a special_plot that handles it
        special_handler = None
        for sp_name, sp_cfg in special_plots.items():
            if sp_cfg.get("graph") == graph_name:
                special_handler = (sp_name, sp_cfg)
                break

        if special_handler:
            # Handle special plot types (e.g., cycle_diagram)
            sp_name, sp_cfg = special_handler
            measure_name = sp_cfg.get("measure")
            if measure_name and measure_name in all_measures:
                for entry in all_measures[measure_name]:
                    cycle_data = entry.get("value")
                    if cycle_data is not None:
                        try:
                            fig = render_cycle_diagram(cycle_data, graph_config, styles, plt)
                            if fig is not None:
                                result_key = entry.get("key", "")
                                plot_path = plot_dir / f"{cell}_{result_key}_{graph_name}"
                                saved = save_plot_dual_format(fig, str(plot_path), plt)
                                generated_plots.extend(saved)
                                logger.info(f"  Saved {graph_name}: {plot_path}.pdf")
                        except Exception as e:
                            logger.warning(f"  Failed to create {graph_name}: {e}")
        else:
            # Standard trace-based graph
            try:
                fig, _axes = plot_trace_graph(
                    graph_name, graph_config, traces, all_measures, styles, plt
                )
                if fig is not None:
                    plot_path = plot_dir / f"{cell}_{graph_name}"
                    saved = save_plot_dual_format(fig, str(plot_path), plt)
                    generated_plots.extend(saved)
                    logger.info(f"  Saved: {plot_path}.pdf")
            except Exception as e:
                logger.warning(f"  Failed to create {graph_name}: {e}")

    return generated_plots


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
    for _key, data in results.items():
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
    for _key, data in results.items():
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


def plot_trace_graph(
    graph_name: str,
    graph_config: dict[str, Any],
    traces_config: dict[str, Any],
    all_measures: dict[str, Any],
    styles_config: list[dict[str, Any]],
    plt,
) -> tuple[Any, Any]:
    """
    Create a matplotlib figure from visualisation config and plot traces.

    Args:
        graph_name: Name of the graph being created
        graph_config: Graph configuration dict (shape, axes, title)
        traces_config: Traces configuration dict (which traces to plot)
        all_measures: All measure results {measure_name: [{key, value, metadata}, ...]}
        styles_config: Styles configuration list
        plt: matplotlib.pyplot module

    Returns:
        Tuple of (fig, axes) or (None, None) if failed
    """
    import re

    shape = graph_config.get("shape", {"figsize": (10, 6)})
    axes_config = graph_config.get("axes", {})

    if not axes_config:
        return None, None

    # Create figure
    fig = plt.figure(**shape)
    fig.suptitle(graph_config.get("title", ""))

    # Create axes
    axes = {}
    for ax_name, ax_cfg in axes_config.items():
        subplot = ax_cfg.get("subplot", (1, 1, 1))
        ax = fig.add_subplot(*subplot)
        ax.set_xlabel(ax_cfg.get("xlabel", ""))
        ax.set_ylabel(ax_cfg.get("ylabel", ""))
        ax.set_title(ax_cfg.get("title", ""))
        if ax_cfg.get("grid", False):
            ax.grid(True, alpha=0.3)
        axes[ax_name] = ax

    # Plot traces that belong to this graph
    for trace_name, trace_cfg in traces_config.items():
        if trace_cfg.get("graph") != graph_name:
            continue

        ax_name = trace_cfg.get("axes", "main")
        if ax_name not in axes:
            continue

        ax = axes[ax_name]
        xresult = trace_cfg.get("xresult")
        yresult = trace_cfg.get("yresult")

        if not xresult or not yresult:
            continue

        # Get x and y data from measures
        x_entries = all_measures.get(xresult, [])
        y_entries = all_measures.get(yresult, [])

        if not x_entries or not y_entries:
            continue

        # Match style from styles_config
        style = {"linestyle": "-", "color": "blue"}
        for style_rule in styles_config:
            pattern = style_rule.get("pattern", (".*", ".*", ".*", ".*"))
            # Pattern: (graph, axes, corner, trace)
            try:
                if (re.match(pattern[0], graph_name) and
                    re.match(pattern[1], ax_name) and
                    re.match(pattern[3], trace_name)):
                    style.update(style_rule.get("style", {}))
            except (IndexError, TypeError):
                pass

        # Override with trace-specific style
        style.update(trace_cfg.get("style", {}))

        # Plot each corner's data
        for x_entry, y_entry in zip(x_entries, y_entries):
            x_val = x_entry.get("value")
            y_val = y_entry.get("value")

            if x_val is None or y_val is None:
                continue

            # Convert to numpy arrays if needed
            x_arr = np.array(x_val) if not isinstance(x_val, np.ndarray) else x_val
            y_arr = np.array(y_val) if not isinstance(y_val, np.ndarray) else y_val

            if len(x_arr) == 0 or len(y_arr) == 0:
                continue

            ax.plot(x_arr, y_arr, label=trace_name, **style)

        if trace_cfg.get("legend", axes_config.get(ax_name, {}).get("legend", False)):
            ax.legend()

    plt.tight_layout()
    return fig, axes


def render_cycle_diagram(
    cycle_data: dict[str, Any],
    graph_config: dict[str, Any],
    styles_config: list[dict[str, Any]],
    plt,
) -> Any:
    """
    Render a cycle diagram from cycle_diagram measure data.

    Args:
        cycle_data: Data from cycle_diagram() measure
        graph_config: Graph configuration
        styles_config: Styles configuration
        plt: matplotlib.pyplot module

    Returns:
        matplotlib figure or None
    """
    if cycle_data is None or not isinstance(cycle_data, dict):
        return None

    signals = cycle_data.get("signals", {})
    if not signals:
        return None

    shape = graph_config.get("shape", {"figsize": (10, 6)})
    axes_config = graph_config.get("axes", {})
    ax_cfg = axes_config.get("main", {})

    fig, ax = plt.subplots(**shape)

    # Default colors for signals
    colors = {"out+": "blue", "out-": "red"}

    # Apply styles from config
    import re
    for style_rule in styles_config:
        pattern = style_rule.get("pattern", (".*", ".*", ".*", ".*"))
        for sig_name in signals.keys():
            try:
                if re.match(pattern[3], sig_name):
                    if "color" in style_rule.get("style", {}):
                        colors[sig_name] = style_rule["style"]["color"]
            except (IndexError, TypeError):
                pass

    # Plot each signal's segments
    for sig_name, segments in signals.items():
        color = colors.get(sig_name, "gray")

        for t_ns, v_seg in segments:
            ax.plot(t_ns, v_seg, color=color, alpha=0.15, linewidth=0.5)

        # Legend entry
        ax.plot([], [], color=color, linewidth=1.5, label=sig_name)

    ax.set_xlabel(ax_cfg.get("xlabel", "Time relative to clock edge [ns]"))
    ax.set_ylabel(ax_cfg.get("ylabel", "Voltage [V]"))
    ax.set_title(graph_config.get("title", "Cycle Diagram"))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.axvline(x=0, color="gray", linestyle="--", linewidth=0.5)

    return fig


if __name__ == "__main__":
    sys.exit(main())
