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
                "sections": ["BSIM", "PSP"],
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

# Waveform parameter scaling: param -> 'voltage' or 'time'
scalemap = {
    "dc": {"dc": "voltage"},
    "pwl": {"points": "pwl"},  # alternating time/voltage pairs
    "sine": {"dc": "voltage", "ampl": "voltage", "delay": "time"},
    "pulse": {
        "v1": "voltage",
        "v2": "voltage",
        "td": "time",
        "tr": "time",
        "tf": "time",
        "pw": "time",
        "per": "time",
    },
}


# ========================================================================
# Utility Functions
# ========================================================================

def format_value(value: float | int, unit: str = "") -> str:
    """Format a value with appropriate SI prefix using unitmap."""
    if value == 0:
        return "0"

    abs_val = abs(value)
    for mult, prefix in unitmap:
        if abs_val >= mult:
            return f"{value / mult:.6g}{prefix}{unit}"
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
    script: Path | None = None,
    outdir: Path | None = None,
    log_file: Path | None = None,
) -> None:
    """
    Print a standardized header for flow steps.

    Args:
        cell: Name of the cell being processed
        flow: Name of the flow step, optionally with mode (e.g., 'netlist (subckt)', 'simulate', 'measure')
        script: Optional path to the script being run
        outdir: Optional output directory
        log_file: Optional log file path
    """
    logger = logging.getLogger(__name__)

    logger.info("")  # One blank line before block
    logger.info("=" * 80)
    logger.info(f"Cell:       {cell}")
    logger.info(f"Flow:       {flow}")
    if script:
        logger.info(f"Script:     {script}")
    if outdir:
        logger.info(f"OutDir:     {outdir}")
    if log_file:
        logger.info(f"Log:        {log_file}")
    logger.info("-" * 80)


def calc_table_columns(struct: dict, varying_params: list[tuple[str, str]] | None = None) -> tuple[list[str], dict[str, int]]:
    """
    Calculate table columns (headers and widths) from struct fields.

    Looks for:
    - Top-level fields: tech, corner, temp
    - Topo_param values (stored in 'meta' field)
    - Varying device parameters (if provided)

    Args:
        struct: Dict with potential 'tech', 'corner', 'temp' at top level and topo_param values in 'meta' field
        varying_params: Optional list of (device_name, param_name) tuples for device params that vary

    Returns:
        Tuple of (headers list, col_widths dict)
    """
    MIN_COL_WIDTH = 20

    headers = []
    col_widths = {}

    # Add top-level fields if they exist
    for field in ["tech", "corner", "temp"]:
        if field in struct:
            headers.append(field)
            col_widths[field] = max(MIN_COL_WIDTH, len(field), len(str(struct[field])))

    # Add topo_param values (stored in meta field) that are simple types
    topo_params_dict = struct.get("meta", {})
    for k, v in topo_params_dict.items():
        if not isinstance(v, (list, dict)):
            headers.append(k)
            col_widths[k] = max(MIN_COL_WIDTH, len(k), len(str(v)))

    # Add varying device parameters
    if varying_params:
        for dev_name, param_name in varying_params:
            col_name = f"{dev_name}.{param_name}"
            headers.append(col_name)
            # Get value from struct if available
            devices = struct.get("devices", {})
            if dev_name in devices:
                dev_params = devices[dev_name].get("params", {})
                if param_name in dev_params:
                    val_str = str(dev_params[param_name])
                    col_widths[col_name] = max(MIN_COL_WIDTH, len(col_name), len(val_str))
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


def print_table_row(row: dict, headers: list[str], col_widths: dict[str, int]) -> None:
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

def load_files_list(files_db_path: Path) -> list[dict]:
    """
    Load file tracking list from JSON file.

    Args:
        files_db_path: Path to files.json file

    Returns:
        List of file context entries, or empty list if file doesn't exist
    """
    if not files_db_path.exists():
        return []
    with open(files_db_path) as f:
        return json.load(f)


def save_files_list(files_db_path: Path, files: list[dict]) -> None:
    """
    Save file tracking list to JSON file with compact formatting.

    Args:
        files_db_path: Path to files.json file
        files: List of file context entries
    """
    files_db_path.parent.mkdir(parents=True, exist_ok=True)
    files_db_path.write_text(compact_json(files))


def find_child_dep(
    child_type: str,
    parent_tech: str,
    db_base: Path,
    child_params: dict | None = None
) -> dict | None:
    """
    Find matching child subcircuit netlist from child's files.json.

    Searches the child cell's database for a subcircuit that matches:
    1. Technology (must match parent's tech)
    2. Optional topo_params and other constraints

    Args:
        child_type: Child cell name (e.g., "cdac", "comp", "samp")
        parent_tech: Technology to match (inherited from parent)
        db_base: Base directory for results (e.g., Path("results"))
        child_params: Optional dict with matching constraints:
            - topo_params: dict of topo_param values to match
            - dev_params: dict of device param values to match

    Returns:
        Dict with child info if found, None otherwise:
        {
            "child_name": "cdac",
            "child_json": "cdac/subckt/subckt_cdac_7_0_rdx2_nosplit_tsmc65_xxx.json",
            "child_spice": "cdac/subckt/subckt_cdac_7_0_rdx2_nosplit_tsmc65_xxx.sp"
        }
    """
    child_files_db_path = db_base / child_type / "files.json"
    if not child_files_db_path.exists():
        return None

    child_files_db = load_files_list(child_files_db_path)
    if not child_files_db:
        return None

    for entry in child_files_db:
        # Load the child subcircuit JSON to check meta values
        subckt_json_path = db_base / child_type / entry.get("subckt_json", "")
        if not subckt_json_path.exists():
            continue

        with open(subckt_json_path) as f:
            child_subckt = json.load(f)

        # Match tech (must match parent's tech, now at top level)
        if child_subckt.get("tech") != parent_tech:
            continue

        # Match topo_params if specified (topo_param values stored in meta)
        if child_params and "topo_params" in child_params:
            child_meta = child_subckt.get("meta", {})
            match = all(
                child_meta.get(k) == v
                for k, v in child_params["topo_params"].items()
            )
            if not match:
                continue

        # Found a match
        return {
            "child_name": child_type,
            "child_json": f"{child_type}/{entry['subckt_json']}",
            "child_spice": f"{child_type}/{entry['subckt_spice']}"
        }

    return None


def find_all_child_deps(
    child_type: str,
    parent_tech: str,
    db_base: Path
) -> list[dict]:
    """
    Find all child subcircuits of a given type matching the parent's tech.

    Args:
        child_type: Child cell name (e.g., "cdac", "comp", "samp")
        parent_tech: Technology to match (inherited from parent)
        db_base: Base directory for results

    Returns:
        List of child info dicts (see find_child_dep for format)
    """
    child_files_db_path = db_base / child_type / "files.json"
    if not child_files_db_path.exists():
        return []

    child_files_db = load_files_list(child_files_db_path)
    if not child_files_db:
        return []

    results = []
    for entry in child_files_db:
        subckt_json_path = db_base / child_type / entry.get("subckt_json", "")
        if not subckt_json_path.exists():
            continue

        with open(subckt_json_path) as f:
            child_subckt = json.load(f)

        # Match tech (now at top level)
        if child_subckt.get("tech") != parent_tech:
            continue

        results.append({
            "child_name": child_type,
            "child_json": f"{child_type}/{entry['subckt_json']}",
            "child_spice": f"{child_type}/{entry['subckt_spice']}"
        })

    return results
