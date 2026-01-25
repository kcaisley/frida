"""
Shared utilities for flow scripts.

Provides common logging configuration, technology mappings, and utilities
used across netlist generation, simulation, measurement, and plotting scripts.
"""

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ========================================================================
# Technology Configuration
# ========================================================================

techmap = {
    "tsmc65": {
        "libs": [
            {
                "path": "/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs",
                "sections": [
                    "tt_lib",
                    "ss_lib",
                    "ff_lib",
                    "sf_lib",
                    "fs_lib",
                    "mc_lib",
                ],
            }
        ],
        "vdd": 1.2,
        "tstep": 1e-9,
        "devmap": {
            "nmos_lvt": {"model": "nch_lvt", "w": 100e-9, "l": 60e-9},
            "nmos_svt": {"model": "nch", "w": 100e-9, "l": 60e-9},
            "nmos_hvt": {"model": "nch_hvt", "w": 100e-9, "l": 60e-9},
            "pmos_lvt": {"model": "pch_lvt", "w": 100e-9, "l": 60e-9},
            "pmos_svt": {"model": "pch", "w": 100e-9, "l": 60e-9},
            "pmos_hvt": {"model": "pch_hvt", "w": 100e-9, "l": 60e-9},
            "momcap_1m": {"model": "mimcap_1m", "unit_cap": 1e-15},
            "momcap_2m": {"model": "mimcap_2m", "unit_cap": 1e-15},
            "momcap_3m": {"model": "mimcap_3m", "unit_cap": 1e-15},
            "polyres": {"model": "polyres", "rsh": 50},
        },
        "mom_cap": {
            "unit_cap": 1e-15,  # 1 fF unit capacitance
            "model": "mimcap",
        },
        "corners": {
            "tt": "tt_lib",
            "ss": "ss_lib",
            "ff": "ff_lib",
            "sf": "sf_lib",
            "fs": "fs_lib",
            "mc": "mc_lib",
        },
    },
    "tsmc28": {
        "libs": [
            {
                "path": "/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs",
                "sections": [
                    "att_pt",
                    "ass_ps",
                    "aff_pf",
                    "asf_ps",
                    "afs_pf",
                    "local_mc",
                ],
            }
        ],
        "vdd": 0.9,
        "tstep": 1e-9,
        "devmap": {
            "nmos_lvt": {"model": "nch_lvt_mac", "w": 40e-9, "l": 30e-9},
            "nmos_svt": {"model": "nch_svt_mac", "w": 40e-9, "l": 30e-9},
            "nmos_hvt": {"model": "nch_hvt_mac", "w": 40e-9, "l": 30e-9},
            "pmos_lvt": {"model": "pch_lvt_mac", "w": 40e-9, "l": 30e-9},
            "pmos_svt": {"model": "pch_svt_mac", "w": 40e-9, "l": 30e-9},
            "pmos_hvt": {"model": "pch_hvt_mac", "w": 40e-9, "l": 30e-9},
            "momcap_1m": {"model": "mimcap_1m", "unit_cap": 1e-15},
            "momcap_2m": {"model": "mimcap_2m", "unit_cap": 1e-15},
            "momcap_3m": {"model": "mimcap_3m", "unit_cap": 1e-15},
            "polyres": {"model": "polyres", "rsh": 50},
        },
        "mom_cap": {
            "unit_cap": 1e-15,  # 1 fF unit capacitance
            "model": "mimcap",
        },
        "corners": {
            "tt": "att_pt",
            "ss": "ass_ps",
            "ff": "aff_pf",
            "sf": "asf_ps",
            "fs": "afs_pf",
            "mc": "local_mc",
        },
        "noise_models": {
            "worst": {
                "path": "/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs",
                "section": "noise_worst",
            },
            "typical": {
                "path": "/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs",
                "section": "noise_typical",
            },
        },
    },
    "tower180": {
        "libs": [
            {
                "path": "/eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/fet.scs",
                "sections": ["NOM", "SLOW", "FAST", "SLOWFAST", "FASTSLOW", "STAT"],
            },
            {
                "path": "/eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/global.scs",
                "section": "BSIM",  # Fixed section, not corner-dependent
            },
        ],
        "vdd": 1.8,
        "tstep": 1e-9,
        "devmap": {
            "nmos_lvt": {"model": "n18lvt", "w": 220e-9, "l": 180e-9},
            "nmos_svt": {"model": "n18", "w": 220e-9, "l": 180e-9},
            "nmos_hvt": {"model": "n18hvt", "w": 220e-9, "l": 180e-9},
            "pmos_lvt": {"model": "p18lvt", "w": 220e-9, "l": 180e-9},
            "pmos_svt": {"model": "p18", "w": 220e-9, "l": 180e-9},
            "pmos_hvt": {"model": "p18hvt", "w": 220e-9, "l": 180e-9},
            "momcap_1m": {"model": "mimcap_1m", "unit_cap": 1e-15},
            "momcap_2m": {"model": "mimcap_2m", "unit_cap": 1e-15},
            "momcap_3m": {"model": "mimcap_3m", "unit_cap": 1e-15},
            "polyres": {"model": "polyres", "rsh": 50},
        },
        "mom_cap": {
            "unit_cap": 1e-15,  # 1 fF unit capacitance
            "model": "mimcap",
        },
        "corners": {
            "tt": "NOM",
            "ss": "SLOW",
            "ff": "FAST",
            "sf": "SLOWFAST",
            "fs": "FASTSLOW",
            "stat": "STAT",
        },
    },
}

# SI unit prefixes: multiplier -> suffix
unitmap = [
    (1e15, "P"),
    (1e12, "T"),
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1, ""),
    (1e-3, "m"),
    (1e-6, "u"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
    (1e-18, "a"),
]

# ========================================================================
# Utility Functions
# ========================================================================


def format_value(value: float | int, unit: str = "") -> str:
    """Format a value with appropriate SI suffix using unitmap."""
    if value == 0:
        return "0"

    abs_val = abs(value)
    for mult, suffix in unitmap:
        if abs_val >= mult:
            return f"{value / mult:.6g}{suffix}{unit}"
    return f"{value:.6g}{unit}"


def compact_json(obj: Any, indent: int = 2, lvl: int = 0) -> str:
    """Format JSON with leaf dicts/lists on single lines."""
    pad, pad1 = " " * indent * lvl, " " * indent * (lvl + 1)

    def is_leaf(v):
        return not any(
            isinstance(x, (dict, list))
            for x in (
                v.values() if isinstance(v, dict) else v if isinstance(v, list) else []
            )
        )

    if isinstance(obj, dict) and obj:
        if is_leaf(obj):
            return (
                "{" + ", ".join(f'"{k}": {json.dumps(v)}' for k, v in obj.items()) + "}"
            )
        return (
            "{\n"
            + ",\n".join(
                f'{pad1}"{k}": {compact_json(v, indent, lvl + 1)}'
                for k, v in obj.items()
            )
            + f"\n{pad}}}"
        )
    if isinstance(obj, list) and obj:
        if is_leaf(obj):
            return "[" + ", ".join(json.dumps(v) for v in obj) + "]"
        return (
            "[\n"
            + ",\n".join(f"{pad1}{compact_json(v, indent, lvl + 1)}" for v in obj)
            + f"\n{pad}]"
        )
    return json.dumps(obj)


def load_cell_script(circuit_file: Path) -> Any:
    """Dynamically load a circuit Python file."""
    spec = importlib.util.spec_from_file_location("circuit", circuit_file)
    if spec is None:
        raise ImportError(f"Could not load spec from {circuit_file}")
    if spec.loader is None:
        raise ImportError(f"Spec has no loader for {circuit_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["circuit"] = module
    spec.loader.exec_module(module)
    return module


# ========================================================================
# Logging Configuration
# ========================================================================


class CustomFormatter(logging.Formatter):
    """Custom formatter that doesn't add [INFO] prefix for info messages."""

    def format(self, record):
        if record.levelno == logging.INFO:
            # For INFO level, just output the message without level name
            return record.getMessage()
        elif record.levelno == logging.WARNING:
            return f"[WARNING] {record.getMessage()}"
        elif record.levelno == logging.ERROR:
            return f"[ERROR] {record.getMessage()}"
        else:
            return record.getMessage()


def setup_logging(log_file: Path | None = None, logger_name: str | None = None):
    """
    Setup logging with custom formatter.

    Args:
        log_file: Optional path to log file. If provided, logs to both file and console.
        logger_name: Optional logger name. If None, configures root logger.

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)

    # File handler if log file specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(CustomFormatter())
        logger.addHandler(file_handler)

    # Prevent propagation to avoid duplicate messages if not root logger
    if logger_name:
        logger.propagate = False

    return logger


# ========================================================================
# Logging Output Functions
# ========================================================================


def print_flow_header(
    cell: str,
    flow: str,
    script_file: Path | None = None,
    outdir: Path | None = None,
    log_file: Path | None = None,
) -> None:
    """
    Print a standardized header for flow steps.

    Args:
        cell: Name of the cell being processed
        flow: Name of the flow step, optionally with mode (e.g., 'netlist (subckt)', 'simulate', 'measure')
        script_file: Optional path to the script being run
        outdir: Optional output directory
        log_file: Optional log file path
    """
    logger = logging.getLogger(__name__)

    logger.info("")  # One blank line before block
    logger.info("=" * 80)
    logger.info(f"Cell:       {cell}")
    logger.info(f"Flow:       {flow}")
    if script_file:
        logger.info(f"Script:     {script_file}")
    if outdir:
        logger.info(f"OutDir:     {outdir}")
    if log_file:
        logger.info(f"Log:        {log_file}")
    logger.info("-" * 80)


def calc_table_columns(
    netstruct: dict[str, Any], varying_params: list[tuple[str, str]] | None = None
) -> tuple[list[str], dict[str, int]]:
    """
    Calculate table columns (headers and widths) from netstruct fields.

    Looks for:
    - Top-level fields: tech, corner, temp
    - Topo_param values (stored in 'topo_params' field)
    - Varying instance parameters (if provided)

    Args:
        netstruct: Dict with potential 'tech', 'corner', 'temp' at top level and 'topo_params'
        varying_params: Optional list of (inst_name, param_name) tuples for instance params that vary

    Returns:
        Tuple of (headers list, col_widths dict)
    """
    MIN_COL_WIDTH = 20

    headers = []
    col_widths = {}

    # Add top-level fields if they exist
    for field in ["tech", "corner", "temp"]:
        if field in netstruct:
            headers.append(field)
            col_widths[field] = max(MIN_COL_WIDTH, len(field), len(str(netstruct[field])))

    # Add topo_param values that are simple types
    topo_params_dict = netstruct.get("topo_params", {})
    for k, v in topo_params_dict.items():
        if not isinstance(v, (list, dict)):
            headers.append(k)
            col_widths[k] = max(MIN_COL_WIDTH, len(k), len(str(v)))

    # Add varying instance parameters
    if varying_params:
        for inst_name, param_name in varying_params:
            col_name = f"{inst_name}.{param_name}"
            headers.append(col_name)
            # Get value from netstruct if available
            instances = netstruct.get("instances", {})
            if inst_name in instances:
                inst_params = instances[inst_name].get("params", {})
                if param_name in inst_params:
                    val_str = str(inst_params[param_name])
                    col_widths[col_name] = max(
                        MIN_COL_WIDTH, len(col_name), len(val_str)
                    )
                else:
                    col_widths[col_name] = max(MIN_COL_WIDTH, len(col_name))
            else:
                col_widths[col_name] = max(MIN_COL_WIDTH, len(col_name))

    return headers, col_widths


def print_table_header(headers: list[str], col_widths: dict[str, int]) -> None:
    """
    Print table header with separator line.

    Args:
        headers: List of column header names
        col_widths: Dictionary mapping header names to column widths
    """
    logger = logging.getLogger(__name__)
    header_line = " ".join(f"{h:<{col_widths[h]}}" for h in headers)
    logger.info(header_line)
    logger.info("-" * 80)


def print_table_row(row: dict[str, Any], headers: list[str], col_widths: dict[str, int]) -> None:
    """
    Print a single table row.

    Args:
        row: Dictionary with row data
        headers: List of column header names
        col_widths: Dictionary mapping header names to column widths
    """
    logger = logging.getLogger(__name__)
    row_line = " ".join(f"{str(row.get(h, '')):<{col_widths[h]}}" for h in headers)
    logger.info(row_line)


# ========================================================================
# Database Utilities
# ========================================================================


def load_files_list(files_db_path: Path) -> dict[str, dict[str, Any]]:
    """
    Load file tracking dict from JSON file.

    Args:
        files_db_path: Path to files.json file

    Returns:
        Dict keyed by config_hash, or empty dict if file doesn't exist
    """
    if not files_db_path.exists():
        return {}
    with open(files_db_path) as f:
        return json.load(f)


def save_files_list(files_db_path: Path, files: dict[str, dict[str, Any]]) -> None:
    """
    Save file tracking dict to JSON file with compact formatting.

    Args:
        files_db_path: Path to files.json file
        files: Dict keyed by config_hash
    """
    files_db_path.parent.mkdir(parents=True, exist_ok=True)
    files_db_path.write_text(compact_json(files))


# ========================================================================
# PyOPUS Integration Utilities
# ========================================================================


def build_pyopus_jobs(
    files: dict[str, dict[str, Any]], cell_dir: Path, cell_module: Any
) -> list[dict[str, Any]]:
    """
    Build PyOPUS job list from files.json testbench entries.

    Each testbench becomes one job. No PyOPUS corners used - corner/tech/temp
    info is already baked into each testbench netlist.

    Args:
        files: Dict from files.json keyed by config_hash
        cell_dir: Path to cell results directory (e.g., results/comp)
        cell_module: Loaded cell module with analyses dict

    Returns:
        List of PyOPUS job dicts ready for simulation
    """
    jobs = []
    analyses = getattr(cell_module, "analyses", {})
    variables = getattr(cell_module, "variables", {})
    default_analysis = list(analyses.values())[0] if analyses else {}

    for config_hash, file_ctx in files.items():
        for tb_spice_rel in file_ctx.get("tb_spice", []):
            tb_path = cell_dir / tb_spice_rel

            tb_path_rel = str(tb_path)
            try:
                # Try to make path relative to current working directory
                tb_path_rel = str(tb_path.relative_to(Path.cwd()))
            except ValueError:
                # If not relative to cwd, use the path as-is
                pass

            # Parse metadata from filename: <cell>_<topo>_<tech>_<hash>_<corner>_<temp>.sp
            # Example: comp_nmosinput_stdbias_tsmc65_a1b2c3d4e5f6_tt_27.sp
            parts = tb_path.stem.split("_")

            # Extract tech, corner, temp from filename parts
            # Filename format: tb_<cell>_<topo_params...>_<tech>_<hash>_<corner>_<temp>
            tech = "unknown"
            corner = "tt"
            temp = 27

            if len(parts) >= 3:
                # Last two parts are corner and temp
                try:
                    temp = int(parts[-1])
                    corner = parts[-2]
                except (ValueError, IndexError):
                    pass

                # Tech is before hash (12 hex chars)
                for i, part in enumerate(parts):
                    if part in ["tsmc65", "tsmc28", "tower180"]:
                        tech = part
                        break

            job = {
                "name": tb_path.stem,
                "definitions": [{"file": tb_path_rel}],
                "params": {},  # Params already in netlist
                "options": {},
                "variables": variables,  # Variables for command expression evaluation
                "saves": default_analysis.get("saves", ["all()"]),
                "command": default_analysis.get(
                    "command", "tran(stop=1e-6, errpreset='conservative')"
                ),
                # Metadata for result filtering (not sent to simulator)
                "_metadata": {
                    "config_hash": config_hash,
                    "tech": tech,
                    "corner": corner,
                    "temp": temp,
                    "cfgname": file_ctx.get("cfgname", ""),
                },
            }
            jobs.append(job)

    return jobs


def filter_results(all_results: dict[str, dict[str, Any]], **filters: Any) -> dict[str, dict[str, Any]]:
    """
    Filter measurement results by metadata.

    Args:
        all_results: Dict of all measurement results (key -> {measures, metadata})
        **filters: Key-value filters (tech='tsmc65', corner='tt', temp=27, etc.)

    Returns:
        Filtered subset of results matching all provided filters
    """
    filtered = {}
    for key, data in all_results.items():
        meta = data.get("metadata", {})
        match = all(
            meta.get(k) == v for k, v in filters.items() if v is not None
        )
        if match:
            filtered[key] = data
    return filtered


# ========================================================================
# Cell Script Validation
# ========================================================================

# Standard attributes expected in cell scripts
_CELL_STANDARD_ATTRS = {
    # Required structures
    "subckt",
    "tb",
    "analyses",
    "measures",
    # Optional structures
    "visualisation",
    # Generator functions
    "gen_topo_subckt",
    "gen_topo_tb",
    # Python builtins/internals to ignore
    "__name__",
    "__doc__",
    "__package__",
    "__loader__",
    "__spec__",
    "__file__",
    "__cached__",
    "__builtins__",
    "__annotations__",
    # Common imports to ignore
    "np",
    "numpy",
    "Path",
    "Any",
    "Dict",
    "List",
    "Tuple",
    "Optional",
}


def check_all_cells(blocks_dir: Path | str = "blocks", cells: str | None = None) -> int:
    """
    Validate cell scripts in a directory and print results as a table.

    Args:
        blocks_dir: Path to blocks directory
        cells: Comma-separated list of cell names, or "all" for all cells

    Returns:
        Number of cells that failed validation (0 = all passed)
    """
    blocks_path = Path(blocks_dir)
    if not blocks_path.exists():
        print(f"Error: {blocks_dir}/ directory not found")
        return 1

    # Determine which cells to check
    if cells is None or cells == "all" or cells == "":
        cell_files = sorted(blocks_path.glob("*.py"))
    else:
        cell_names = [c.strip() for c in cells.split(",") if c.strip() and c.strip() != "all"]
        cell_files = []
        for name in cell_names:
            cell_file = blocks_path / f"{name}.py"
            if cell_file.exists():
                cell_files.append(cell_file)
            else:
                print(f"Warning: {name}.py not found, skipping")
        cell_files = sorted(cell_files)

    if not cell_files:
        print("No cell files found")
        return 1

    # Collect data for all cells
    rows = []
    errors_list = []

    for cell_file in cell_files:
        cell_name = cell_file.stem
        try:
            cell_module = load_cell_script(cell_file)
            errors, info = check_cell_script(cell_module, cell_name)

            rows.append({
                "cell": cell_name,
                "subckt": info.get("has_subckt", False),
                "gen_subckt": info.get("has_gen_topo_subckt", False),
                "tb": info.get("has_tb", False),
                "gen_tb": info.get("has_gen_topo_tb", False),
                "analyses": info.get("has_analyses", False),
                "measures": info.get("has_measures", False),
                "visual": info.get("has_visualisation", False),
                "helpers": info.get("helper_functions", []),
                "errors": errors,
            })

            if errors:
                errors_list.append((cell_name, errors))

        except Exception as e:
            rows.append({
                "cell": cell_name,
                "subckt": False,
                "gen_subckt": False,
                "tb": False,
                "gen_tb": False,
                "analyses": False,
                "measures": False,
                "visual": False,
                "helpers": [],
                "errors": [f"Failed to load: {e}"],
            })
            errors_list.append((cell_name, [f"Failed to load: {e}"]))

    # Print table header
    print(f"{'cell':<10} {'subckt':<7} {'gen subckt':<7} {'tb':<4} {'gen tb':<7} {'anlys':<6} {'meas':<6} {'visual':<7} {'other functions'}")
    print("-" * 95)

    # Print rows
    for row in rows:
        def mark(val: bool) -> str:
            return "y" if val else "-"

        helpers_str = ", ".join(row["helpers"]) if row["helpers"] else "-"
        if len(helpers_str) > 30:
            helpers_str = helpers_str[:27] + "..."

        print(
            f"{row['cell']:<10} "
            f"{mark(row['subckt']):<7} "
            f"{mark(row['gen_subckt']):<7} "
            f"{mark(row['tb']):<4} "
            f"{mark(row['gen_tb']):<7} "
            f"{mark(row['analyses']):<6} "
            f"{mark(row['measures']):<6} "
            f"{mark(row['visual']):<7} "
            f"{helpers_str}"
        )

    # Print errors if any
    if errors_list:
        print()
        print("Errors:")
        for cell_name, errors in errors_list:
            for err in errors:
                print(f"  {cell_name}: {err}")

    return len(errors_list)


def check_cell_script(cell_module: Any, cell_name: str) -> tuple[list[str], dict[str, Any]]:
    """
    Validate cell script has required structures and follows conventions.

    Checks:
    1. Must have 'subckt' dict
    2. Must have 'tb' dict (or None for pure digital blocks)
    3. If tb is defined:
       - Must have 'analyses' dict
       - Must have 'measures' dict
       - Each measure must have 'analysis' and 'expression' keys
       - Measure expressions must be single-line
    4. Must NOT have 'variables' dict (vdd etc. should come from techmap)
    5. 'visualisation' dict is optional but noted if present

    Also detects helper functions (generate_topology, generate_tb_topology, etc.)

    Args:
        cell_module: Loaded cell module
        cell_name: Name of cell for error messages

    Returns:
        Tuple of (errors list, info dict with has_* booleans and helper_functions list)
    """
    errors = []
    info: dict[str, Any] = {
        "has_subckt": False,
        "has_gen_topo_subckt": False,
        "has_tb": False,
        "has_gen_topo_tb": False,
        "has_analyses": False,
        "has_measures": False,
        "has_visualisation": False,
        "helper_functions": [],
    }

    # Check for required 'subckt' dict
    subckt = getattr(cell_module, "subckt", None)
    if subckt is None:
        errors.append("Missing required 'subckt' dict")
    elif not isinstance(subckt, dict):
        errors.append("'subckt' must be a dict")
    else:
        info["has_subckt"] = True

    # Check for gen_topo_subckt function
    gen_topo_subckt = getattr(cell_module, "gen_topo_subckt", None)
    if gen_topo_subckt is not None and callable(gen_topo_subckt):
        info["has_gen_topo_subckt"] = True

    # Check for 'tb' (required attribute, but can be None for pure digital blocks)
    if not hasattr(cell_module, "tb"):
        errors.append("Missing 'tb' attribute (set to None for digital-only blocks)")
    else:
        tb = getattr(cell_module, "tb", None)
        info["has_tb"] = tb is not None

        # Check for gen_topo_tb function
        gen_topo_tb = getattr(cell_module, "gen_topo_tb", None)
        if gen_topo_tb is not None and callable(gen_topo_tb):
            info["has_gen_topo_tb"] = True

        # If tb is defined, check for analyses and measures
        if tb is not None:
            # Check for required 'analyses' dict
            analyses = getattr(cell_module, "analyses", None)
            if analyses is None:
                errors.append("Missing 'analyses' dict (required when tb is defined)")
            elif not isinstance(analyses, dict):
                errors.append("'analyses' must be a dict")
            elif len(analyses) == 0:
                errors.append("'analyses' dict is empty")
            else:
                info["has_analyses"] = True

            # Check for required 'measures' dict
            measures = getattr(cell_module, "measures", None)
            if measures is None:
                errors.append("Missing 'measures' dict (required when tb is defined)")
            elif not isinstance(measures, dict):
                errors.append("'measures' must be a dict")
            elif len(measures) == 0:
                errors.append("'measures' dict is empty")
            else:
                info["has_measures"] = True
                # Check each measure entry
                for measure_name, measure_def in measures.items():
                    if not isinstance(measure_def, dict):
                        errors.append(f"measures['{measure_name}']: must be a dict")
                        continue

                    if "analysis" not in measure_def:
                        errors.append(f"measures['{measure_name}']: missing 'analysis' key")

                    if "expression" not in measure_def:
                        errors.append(f"measures['{measure_name}']: missing 'expression' key")
                    else:
                        expr = measure_def["expression"]
                        if isinstance(expr, str) and expr.strip().startswith(('"""', "'''")):
                            errors.append(
                                f"measures['{measure_name}']: multi-line expressions not allowed"
                            )
                        elif isinstance(expr, str) and "\n" in expr.strip():
                            errors.append(
                                f"measures['{measure_name}']: multi-line expressions not allowed"
                            )

    # Check that 'variables' dict does NOT exist
    variables = getattr(cell_module, "variables", None)
    if variables is not None:
        errors.append("'variables' dict not allowed - use techmap for vdd etc.")

    # Check for visualisation (required when tb is defined)
    visualisation = getattr(cell_module, "visualisation", None)
    if visualisation is not None:
        if not isinstance(visualisation, dict):
            errors.append("'visualisation' must be a dict")
        else:
            info["has_visualisation"] = True
    elif info["has_tb"]:
        errors.append("Missing 'visualisation' dict (required when tb is defined)")

    # Detect helper functions
    helper_functions = []
    for attr_name in dir(cell_module):
        if attr_name in _CELL_STANDARD_ATTRS:
            continue
        if attr_name.startswith("_"):
            continue

        attr = getattr(cell_module, attr_name)
        if callable(attr) and not isinstance(attr, type):
            helper_functions.append(attr_name)

    info["helper_functions"] = helper_functions

    return errors, info


def parse_testbench_filename(filename: str) -> dict[str, Any]:
    """
    Parse testbench filename to extract metadata.

    Expected format: tb_<cell>_<topo_params...>_<tech>_<hash>_<corner>_<temp>.sp

    Args:
        filename: Testbench filename or stem

    Returns:
        Dict with parsed metadata (tech, corner, temp, hash)
    """
    stem = Path(filename).stem
    parts = stem.split("_")

    result = {
        "tech": "unknown",
        "corner": "tt",
        "temp": 27,
        "hash": "",
    }

    if len(parts) >= 3:
        # Last part is temperature
        try:
            result["temp"] = int(parts[-1])
        except ValueError:
            pass

        # Second to last is corner
        if len(parts) >= 2:
            result["corner"] = parts[-2]

        # Find tech in parts
        for part in parts:
            if part in ["tsmc65", "tsmc28", "tower180"]:
                result["tech"] = part
                break

        # Find 12-char hex hash
        for part in parts:
            if len(part) == 12 and all(c in "0123456789abcdef" for c in part):
                result["hash"] = part
                break

    return result
