"""
Converts Python circuit descriptions into SPICE netlists with
technology-specific device mappings and parameter sweeps.
"""

import argparse
import copy
import datetime
import hashlib
import importlib.util
import itertools
import json
import logging
import sys
from pathlib import Path
from typing import Any

from flow.common import setup_logging

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

# Netlist Generation Flow
def print_table(rows: list[dict], headers: list[str]) -> None:
    """
    Print a simple formatted table using logging.

    Args:
        rows: List of dictionaries with data to print
        headers: List of column header names
    """
    logger = logging.getLogger(__name__)

    if not rows:
        return

    # Calculate column widths
    col_widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ""))))

    # Print header
    header = " ".join(f"{h:<{col_widths[h]}}" for h in headers)
    logger.info(header)
    logger.info("-" * len(header))

    # Print rows
    for row in rows:
        logger.info(" ".join(f"{str(row.get(h, '')):<{col_widths[h]}}" for h in headers))


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


def load_circuit_module(circuit_file: Path) -> Any:
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


def expand_sweeps(
    topology: dict[str, Any], sweep: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Expand parameter sweeps to generate all combinations of topology structs.

    Sweep structure:
      - globals: Device-wide defaults that can be swept (e.g., {"nmos": {...}, "cap": {...}})
      - selections: Device-specific parameter sweeps (e.g., [{"devices": ["M1", "M2"], "w": [2, 4]}])

    Stores generic parameters in 'meta' subfield:
      - For transistors: dev, type, w, l, nf
      - For capacitors: dev, type, c, m
      - For resistors: dev, r, w
    """

    def get_global_defaults(dev: str, global_config: dict[str, Any]) -> dict[str, Any]:
        """Get default meta values for a device type from globals."""
        if dev not in ["nmos", "pmos", "cap", "res"]:
            return {}

        # Check if globals exist in sweep
        if "globals" not in sweep:
            return {}

        if dev not in sweep["globals"]:
            return {}

        defaults = sweep["globals"][dev]
        meta = {"dev": dev}

        if dev in ["nmos", "pmos"]:
            meta.update({
                "type": defaults.get("type", "svt") if "type" not in global_config else global_config["type"],
                "w": defaults.get("w", 1) if "w" not in global_config else global_config["w"],
                "l": defaults.get("l", 1) if "l" not in global_config else global_config["l"],
                "nf": defaults.get("nf", 1) if "nf" not in global_config else global_config["nf"],
            })
        elif dev == "cap":
            meta.update({
                "type": defaults.get("type", "1m") if "type" not in global_config else global_config["type"],
            })
            if "c" in defaults:
                meta["c"] = defaults["c"] if "c" not in global_config else global_config["c"]
            if "m" in defaults:
                meta["m"] = defaults["m"] if "m" not in global_config else global_config["m"]
        elif dev == "res":
            if "r" in defaults:
                meta["r"] = defaults["r"] if "r" not in global_config else global_config["r"]
            if "w" in defaults:
                meta["w"] = defaults["w"] if "w" not in global_config else global_config["w"]

        return meta

    # Build global sweep combinations
    global_sweep_groups = []
    if "globals" in sweep:
        for dev_type, dev_globals in sweep["globals"].items():
            # Check if this device type has any sweepable parameters
            param_lists = {
                p: dev_globals[p] for p in ["w", "l", "nf", "type", "c", "m", "r"]
                if p in dev_globals and isinstance(dev_globals[p], list)
            }

            if param_lists:
                param_names = list(param_lists.keys())
                group_combos = []
                for combo in itertools.product(*[param_lists[p] for p in param_names]):
                    group_config = {dev_type: dict(zip(param_names, combo))}
                    group_combos.append(group_config)
                global_sweep_groups.append(group_combos)

    # Build selection sweep combinations per group
    selection_sweep_groups = []
    if "selections" in sweep:
        for sweep_spec in sweep["selections"]:
            sweep_devices = sweep_spec["devices"]
            param_lists = {
                p: sweep_spec[p] for p in ["w", "l", "nf", "type", "c", "m", "r"] if p in sweep_spec
            }
            param_names = list(param_lists.keys())

            group_combos = []
            for combo in itertools.product(*[param_lists[p] for p in param_names]):
                group_config = {dev: dict(zip(param_names, combo)) for dev in sweep_devices}
                group_combos.append(group_config)
            selection_sweep_groups.append(group_combos)

    # Combine global and selection sweeps via Cartesian product
    all_sweep_groups = global_sweep_groups + selection_sweep_groups

    if not all_sweep_groups:
        # No sweeps, just apply globals
        topo_copy = copy.deepcopy(topology)
        for dev_name, dev_info in topo_copy["devices"].items():
            meta = get_global_defaults(dev_info.get("dev", ""), {})
            if meta:
                dev_info["meta"] = meta
        return [topo_copy]

    all_configurations = []
    for combo in itertools.product(*all_sweep_groups):
        # Merge all configs (global + selections)
        global_config = {}
        selection_config = {}

        for sweep_config in combo:
            # Check if this is a global config (has device type keys) or selection config (has device name keys)
            for key in sweep_config.keys():
                if key in ["nmos", "pmos", "cap", "res"]:
                    global_config.update(sweep_config)
                else:
                    selection_config.update(sweep_config)

        topo_copy = copy.deepcopy(topology)
        for dev_name, dev_info in topo_copy["devices"].items():
            dev_type = dev_info.get("dev", "")

            # Get global defaults for this device type, applying global sweep overrides
            global_overrides = global_config.get(dev_type, {})
            meta = get_global_defaults(dev_type, global_overrides)

            if not meta:
                continue

            # Apply selection overrides for specific devices
            if dev_name in selection_config:
                meta.update(selection_config[dev_name])

            dev_info["meta"] = meta

        all_configurations.append(topo_copy)

    return all_configurations


def map_technology(
    topology: dict[str, Any], tech: str, techmap: dict[str, Any]
) -> dict[str, Any]:
    """
    Map generic topology to technology-specific netlist.

    Uses meta.dev ('nmos'/'pmos') + meta.type ('lvt'/'svt'/'hvt') to look up devmap.
    """
    tech_config = techmap[tech]
    topo_copy = copy.deepcopy(topology)

    if "meta" not in topo_copy:
        topo_copy["meta"] = {}
    topo_copy["meta"]["tech"] = tech

    for dev_name, dev_info in topo_copy.get("devices", {}).items():
        meta = dev_info.get("meta")
        if not meta:
            continue

        dev = meta.get("dev")
        if not dev:
            continue

        # Combine dev + type for devmap lookup
        # For transistors: nmos_lvt, pmos_svt (dev + type)
        # For caps/res: momcap_1m, polyres (type already includes category)
        if dev in ["nmos", "pmos"] and "type" in meta:
            device_key = f"{dev}_{meta['type']}"
        elif "type" in meta:
            device_key = meta['type']
        else:
            device_key = dev

        dev_map = tech_config["devmap"].get(device_key)
        if not dev_map:
            continue

        # Remove generic 'dev' field from device info
        if "dev" in dev_info:
            del dev_info["dev"]

        # Map transistors
        if dev in ["nmos", "pmos"]:
            dev_info["model"] = dev_map["model"]
            dev_info["w"] = meta["w"] * dev_map["w"]
            dev_info["l"] = meta["l"] * dev_map["l"]
            dev_info["nf"] = meta.get("nf", 1)

        # Map capacitors
        elif dev == "cap":
            dev_info["model"] = dev_map["model"]
            # Keep c and m from device definition for SPICE generation

        # Map resistors
        elif dev == "res":
            dev_info["model"] = dev_map["model"]
            # Keep r from device definition for SPICE generation
            if "rsh" in dev_map:
                dev_info["rsh"] = dev_map["rsh"]

    return topo_copy


def scale_testbench(
    topology: dict[str, Any], tech: str, techmap: dict[str, Any]
) -> dict[str, Any]:
    """Scale voltage and time values in testbench topology using scalemap."""
    tech_config = techmap[tech]
    vdd = tech_config["vdd"]
    tstep = tech_config.get("tstep", 1e-9)

    topo_copy = copy.deepcopy(topology)

    # Add vdd and tstep to meta
    if "meta" not in topo_copy:
        topo_copy["meta"] = {}
    topo_copy["meta"]["vsupply"] = vdd
    topo_copy["meta"]["tstep"] = tstep
    topo_copy["meta"]["tech"] = tech

    # Scale voltage sources using scalemap
    for dev_name, dev_info in topo_copy.get("devices", {}).items():
        if dev_info.get("dev") == "vsource":
            wave = dev_info.get("wave")
            if wave not in scalemap:
                continue

            for param, scale_type in scalemap[wave].items():
                if param not in dev_info:
                    continue

                if scale_type == "voltage":
                    dev_info[param] *= vdd
                elif scale_type == "time":
                    dev_info[param] *= tstep
                elif scale_type == "pwl":
                    # Alternating time/voltage pairs
                    dev_info[param] = [
                        val * (tstep if i % 2 == 0 else vdd)
                        for i, val in enumerate(dev_info[param])
                    ]

    # Scale analysis parameters
    if "analyses" in topo_copy:
        for analysis in topo_copy["analyses"].values():
            if analysis.get("type") == "tran":
                for param in ["stop", "step", "strobeperiod"]:
                    if param in analysis:
                        analysis[param] *= tstep

    return topo_copy


def autoadd_fields(
    topology: dict[str, Any],
    tech: str,
    techmap: dict[str, Any],
    subckt_topology: dict[str, Any] | None = None,
    corner: str = "tt",
) -> dict[str, Any]:
    """
    Add automatic fields to testbench topology.

    Args:
        topology: Testbench topology
        tech: Technology name
        techmap: Technology mapping
        subckt_topology: Subcircuit topology (for generating save statements)
        corner: Process corner

    Returns:
        Topology with automatic fields added
    """
    tech_config = techmap[tech]
    topo_copy = copy.deepcopy(topology)

    # Add simulator declaration
    topo_copy["simulator"] = "lang=spice"

    # Add library statements
    libs = []
    for lib_entry in tech_config.get("libs", []):
        lib_path = lib_entry["path"]
        sections = lib_entry["sections"]

        # Map corner to section
        corner_map = tech_config.get("corners", {})
        section = corner_map.get(corner, sections[0] if sections else "tt_lib")

        libs.append({"path": lib_path, "section": section})

    topo_copy["libs"] = libs

    # Add includes (scan for subcircuit instances)
    includes = []
    for dev_name, dev_info in topology.get("devices", {}).items():
        dev = dev_info.get("dev")
        # Check if this is a subcircuit instance
        if dev not in ["vsource", "res", "cap", "nmos", "pmos"] and dev is not None:
            # This is a subcircuit - need to determine the filename
            # For now, we'll add a placeholder that needs to be filled in
            # The actual filename depends on the subcircuit parameters
            includes.append(f"{dev}_{tech}_*.sp")  # Placeholder

    topo_copy["includes"] = includes

    # Add options
    topo_copy["options"] = {"temp": 27, "scale": 1.0}

    # Add save statements
    save_stmts = ["all"]

    # Generate device-specific save statements from subcircuit
    if subckt_topology:
        # Find DUT instance name
        dut_instance = None
        for dev_name, dev_info in topology.get("devices", {}).items():
            if dev_info.get("dev") == subckt_topology.get("subckt"):
                dut_instance = dev_name
                break

        if dut_instance:
            # Generate save statements for transistors (devices with meta field)
            for dev_name, dev_info in subckt_topology.get("devices", {}).items():
                if "meta" in dev_info:
                    hier_name = f"{dut_instance}.{dev_name}"
                    save_stmts.append(f"{hier_name}:currents")
                    save_stmts.append(f"{hier_name}:d:q {hier_name}:s:q")
                    oppoint = " ".join(
                        f"{hier_name}:{p}"
                        for p in [
                            "vth",
                            "gds",
                            "gm",
                            "vdsat",
                            "cdb",
                            "cdg",
                            "csg",
                            "csb",
                        ]
                    )
                    save_stmts.append(oppoint)

    topo_copy["save"] = save_stmts

    return topo_copy


def format_value(value: float | int, unit: str = "") -> str:
    """Format a value with appropriate SI prefix using unitmap."""
    if value == 0:
        return "0"

    abs_val = abs(value)
    for mult, prefix in unitmap:
        if abs_val >= mult:
            return f"{value / mult:.6g}{prefix}{unit}"
    return f"{value:.6g}{unit}"


def generate_spice(topology: dict[str, Any], mode: str = "subcircuit") -> str:
    """
    Convert topology dict to SPICE netlist string.

    Args:
        topology: Topology dict (subcircuit or testbench)
        mode: 'subcircuit' or 'testbench'

    Returns:
        SPICE netlist string
    """
    lines = []

    if mode == "subcircuit":
        # Subcircuit mode
        subckt_name = topology.get("subckt", "unnamed")
        ports = topology.get("ports", {})
        devices = topology.get("devices", {})

        # Generate descriptive comment from meta
        meta = topology["meta"]
        param_strs = []
        for key, value in meta.items():
            # Only include scalar types
            if isinstance(value, (int, str, float, bool)):
                param_strs.append(f"{key}: {value}")

        comment_name = f"{subckt_name}  ({', '.join(param_strs)})"

        # Header
        lines.append(f"* {comment_name}")
        lines.append("")
        lines.append("*.BUSDELIMITER [")
        lines.append("")

        # Subcircuit definition
        port_list = " ".join(ports.keys())
        lines.append(f".subckt {subckt_name} {port_list}")

        # PININFO comment
        pininfo = " ".join([f"{name}:{dir}" for name, dir in ports.items()])
        lines.append(f"*.PININFO {pininfo}")
        lines.append("")

        # Devices
        for dev_name, dev_info in devices.items():
            model = dev_info.get("model")
            pins = dev_info.get("pins", {})

            # Determine device type from meta if available, otherwise from dev field
            dev_type = None
            if "meta" in dev_info:
                dev_type = dev_info["meta"].get("dev")
            if not dev_type:
                dev_type = dev_info.get("dev")

            # Transistors
            if dev_type in ["nmos", "pmos"]:
                pin_list = " ".join(pins.get(p, "0") for p in ["d", "g", "s", "b"])
                line = f"{dev_name} {pin_list} {model}"
                line += f" W={format_value(dev_info['w'])}"
                line += f" L={format_value(dev_info['l'])}"
                line += f" nf={dev_info.get('nf', 1)}"
                lines.append(line)

            # Capacitors
            elif dev_type == "cap":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                c = dev_info.get("c", 1)  # Unitless capacitance value
                m = dev_info.get("m", 1)  # Multiplier
                cap_model = dev_info.get("model", "capacitor")

                # Generate capacitor instance
                # Note: c and m are unitless here, actual capacitance depends on PDK
                lines.append(f"{dev_name} {p} {n} {cap_model} c={c} m={m}")

            # Resistors
            elif dev_type == "res":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                r = dev_info.get("r", 4)  # Resistance multiplier
                res_model = dev_info.get("model", "resistor")
                lines.append(f"{dev_name} {p} {n} {res_model} r={r}")

        lines.append("")
        lines.append(f".ends {subckt_name}")
        lines.append("")
        lines.append(".end")

    else:
        # Testbench mode
        devices = topology.get("devices", {})
        analyses = topology.get("analyses", {})

        # Simulator declaration
        if "simulator" in topology:
            lines.append(f"simulator {topology['simulator']}")

        # Library includes
        if "libs" in topology:
            for lib in topology["libs"]:
                lines.append(f'.lib "{lib["path"]}" {lib["section"]}')

        # Include files
        if "includes" in topology:
            for inc in topology["includes"]:
                lines.append(f'.include "{inc}"')

        lines.append("")

        # Devices
        for dev_name, dev_info in devices.items():
            dev = dev_info.get("dev")

            if dev == "vsource":
                # Voltage source
                pins = dev_info.get("pins", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                wave = dev_info.get("wave", "dc")

                line = f"{dev_name} {p} {n}"

                if wave == "dc":
                    dc_val = dev_info.get("dc", 0)
                    line += f" DC {format_value(dc_val, 'V')}"

                elif wave == "pwl":
                    points = dev_info.get("points", [])
                    pwl_str = " ".join(
                        [
                            format_value(v, "s" if i % 2 == 0 else "V")
                            for i, v in enumerate(points)
                        ]
                    )
                    line += f" PWL({pwl_str})"

                elif wave == "sine":
                    dc = format_value(dev_info.get("dc", 0), "V")
                    ampl = format_value(dev_info.get("ampl", 0), "V")
                    freq = format_value(dev_info.get("freq", 1e6), "Hz")
                    delay = format_value(dev_info.get("delay", 0), "s")
                    line += f" SIN({dc} {ampl} {freq} {delay})"

                elif wave == "pulse":
                    v1 = format_value(dev_info.get("v1", 0), "V")
                    v2 = format_value(dev_info.get("v2", 1), "V")
                    td = format_value(dev_info.get("td", 0), "s")
                    tr = format_value(dev_info.get("tr", 0), "s")
                    tf = format_value(dev_info.get("tf", 0), "s")
                    pw = format_value(dev_info.get("pw", 1e-9), "s")
                    per = format_value(dev_info.get("per", 2e-9), "s")
                    line += f" PULSE({v1} {v2} {td} {tr} {tf} {pw} {per})"

                lines.append(line)

            elif dev == "res":
                pins = dev_info.get("pins", {})
                params = dev_info.get("params", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                r = params.get("r", 1000)
                lines.append(f"{dev_name} {p} {n} {format_value(r, 'Ohm')}")

            elif dev == "cap":
                pins = dev_info.get("pins", {})
                params = dev_info.get("params", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                c = params.get("c", 1e-12)
                lines.append(f"{dev_name} {p} {n} {format_value(c, 'F')}")

            else:
                # Subcircuit instance
                pins = dev_info.get("pins", {})
                pin_list = " ".join([pins[p] for p in pins.keys()])
                lines.append(f"{dev_name} {pin_list} {dev}")

        lines.append("")

        # Analysis
        if analyses:
            # Check if there's a montecarlo analysis
            mc_analysis = None
            tran_analysis = None

            for name, spec in analyses.items():
                if spec.get("type") == "montecarlo":
                    mc_analysis = (name, spec)
                elif spec.get("type") == "tran":
                    tran_analysis = (name, spec)

            if mc_analysis and tran_analysis:
                # Wrap tran in montecarlo
                mc_name, mc_spec = mc_analysis
                tran_name, tran_spec = tran_analysis

                stop = format_value(tran_spec.get("stop", 1e-6), "s")
                step = (
                    format_value(tran_spec.get("step", 1e-9), "s")
                    if "step" in tran_spec
                    else None
                )

                lines.append(
                    f"{mc_name} montecarlo numruns={mc_spec.get('numruns', 20)} "
                    + f"seed={mc_spec.get('seed', 12345)} "
                    + f"variations={mc_spec.get('variations', 'all')} {{"
                )

                tran_line = f"    {tran_name} tran stop={stop}"
                if "strobeperiod" in tran_spec:
                    tran_line += (
                        f" strobeperiod={format_value(tran_spec['strobeperiod'], 's')}"
                    )
                if "noisefmax" in tran_spec:
                    tran_line += (
                        f" noisefmax={format_value(tran_spec['noisefmax'], 'Hz')}"
                    )
                if "noiseseed" in tran_spec:
                    tran_line += f" noiseseed={tran_spec['noiseseed']}"
                if "param" in tran_spec:
                    tran_line += f" param={tran_spec['param']}"
                if "param_vec" in tran_spec:
                    vec_str = " ".join([str(v) for v in tran_spec["param_vec"]])
                    tran_line += f" param_vec=[{vec_str}]"

                lines.append(tran_line)
                lines.append("}")

            elif tran_analysis:
                # Just transient
                tran_name, tran_spec = tran_analysis
                stop = format_value(tran_spec.get("stop", 1e-6), "s")
                step = format_value(tran_spec.get("step", 1e-9), "s")
                lines.append(f".tran {step} {stop}")

        lines.append("")

        # Options
        if "options" in topology:
            opts = topology["options"]
            opt_str = " ".join([f"{k}={v}" for k, v in opts.items()])
            lines.append(f".option {opt_str}")

        lines.append("")

        # Save statements
        if "save" in topology:
            for save in topology["save"]:
                if save == "all":
                    lines.append(".save all")
                else:
                    lines.append(f".save {save}")

    return "\n".join(lines) + "\n"


def generate_filename(topology: dict[str, Any]) -> str:
    """
    Generate filename for a netlist using meta values for parameters.

    Args:
        topology: Topology dictionary with 'subckt' or 'testbench' key and meta field containing tech

    Returns:
        Filename string (e.g., 'cdac_7bit_7cap_radix2_tsmc65.sp')
    """
    if "subckt" in topology:
        base_name = topology["subckt"]

        # Meta should always be present with tech field
        if "meta" not in topology:
            raise ValueError(f"Topology for subckt '{base_name}' missing required 'meta' field")

        meta = topology["meta"]

        # Extract tech from meta
        if "tech" not in meta:
            raise ValueError(f"Topology meta for subckt '{base_name}' missing required 'tech' field")

        tech = meta["tech"]
        parts = [base_name]

        # Add all meta parameters except tech (only scalar types)
        for key, value in meta.items():
            if key != "tech" and isinstance(value, (int, str, float, bool)):
                parts.append(str(value))

        # Add hash of device parameters to make filename unique for sweeps
        devices = topology.get("devices", {})
        device_params = []
        for dev_name in sorted(devices.keys()):
            dev = devices[dev_name]
            if "meta" in dev:
                dev_meta = dev["meta"]
                # Create a string representation of swept parameters
                param_str = f"{dev_name}:"
                for param in sorted(dev_meta.keys()):
                    param_str += f"{param}={dev_meta[param]},"
                device_params.append(param_str)

        parts.append(tech)

        if device_params:
            # Create hash of all device parameters
            params_string = "|".join(device_params)
            hash_obj = hashlib.sha256(params_string.encode())
            hash_hex = hash_obj.hexdigest()[:12]  # Use first 12 chars of hash (increased from 8 to reduce collisions)
            parts.append(hash_hex)

        return "ckt_" + "_".join(parts) + ".sp"
    else:
        # Testbench
        if "meta" not in topology:
            raise ValueError("Topology for testbench missing required 'meta' field")

        meta = topology["meta"]
        if "tech" not in meta:
            raise ValueError("Topology meta for testbench missing required 'tech' field")

        tech = meta["tech"]
        return f"{topology.get('testbench', 'tb_unnamed')}_{tech}.sp"


# Main flow functions


def generate_subcircuits(circuit_module: Any, output_dir: Path) -> None:
    """
    Generate subcircuit netlists from a circuit module.

    Args:
        circuit_module: Loaded Python module with subcircuit() function
        output_dir: Directory to write output files
    """
    logger = logging.getLogger(__name__)
    result = circuit_module.subcircuit()

    # Handle both single (topology, sweep) and list of (topology, sweep) tuples
    if isinstance(result, list):
        # Multiple configurations (e.g., CDAC with different topologies)
        configurations = result
    else:
        # Single configuration
        configurations = [result]

    output_dir.mkdir(parents=True, exist_ok=True)
    total_count = 0

    # Track unique configurations for summary
    config_summary: dict[tuple[Any, ...], dict[str, int]] = {}
    meta_fields: list[str] = []  # Track which meta fields are present across all configs

    logger.info(f"\nGenerating subcircuits for {len(configurations)} configurations...\n")

    for config_idx, (topology, sweep) in enumerate(configurations, 1):
        # Tech list must be in sweep
        if "tech" not in sweep:
            raise ValueError("Sweep specification missing required 'tech' field")

        config_tech_list = sweep["tech"]

        # Expand sweeps
        topologies = expand_sweeps(topology, sweep)

        # Extract configuration metadata for summary (generic approach)
        if "meta" not in topology:
            raise ValueError("Topology missing required 'meta' field")

        meta = topology["meta"]

        # Determine which fields to track (exclude lists, tech, and threshold)
        for key in meta.keys():
            if key not in meta_fields and key not in ["tech", "threshold", "weights", "scaled_weights"]:
                # Only include simple types (int, str, float)
                if isinstance(meta[key], (int, str, float)):
                    meta_fields.append(key)

        # Create config key from meta values
        config_key = tuple(meta.get(field) for field in meta_fields)

        if config_key not in config_summary:
            config_summary[config_key] = {
                "param_combos": len(topologies),
                "techs": len(config_tech_list),
                "count": 0
            }

        # Generate netlists for each technology
        config_count = 0
        for tech in config_tech_list:
            for topo in topologies:
                # Add tech to meta before mapping
                if "meta" not in topo:
                    topo["meta"] = {}
                topo["meta"]["tech"] = tech

                # Map to technology
                tech_topo = map_technology(topo, tech, techmap)

                # Generate filename (tech now in meta)
                filename = generate_filename(tech_topo)
                output_path = output_dir / filename
                json_path = output_dir / filename.replace(".sp", ".json")

                # Convert to SPICE
                spice_str = generate_spice(tech_topo, mode="subcircuit")

                # Write SPICE file
                output_path.write_text(spice_str)

                # Write JSON file
                json_path.write_text(compact_json(tech_topo))

                total_count += 1
                config_count += 1

                # Update count for this configuration
                config_summary[config_key]["count"] += 1

        # Log progress after each configuration
        meta_str = ", ".join(f"{k}={meta.get(k)}" for k in meta_fields if k in meta)
        logger.info(f"[{config_idx}/{len(configurations)}] Generated {config_count} netlists: {meta_str}")
    # Print summary (generic table based on detected meta fields)
    if config_summary and meta_fields:
        logger.info("\nConfiguration Summary:")

        # Build rows as list of dicts
        rows = []
        for config_key, info in sorted(config_summary.items()):
            row = {field: config_key[i] for i, field in enumerate(meta_fields)}
            row.update({
                "sweeps": info['param_combos'],
                "techs": info['techs'],
                "total": info['count']
            })
            rows.append(row)

        # Print table
        headers = meta_fields + ["sweeps", "techs", "total"]
        print_table(rows, headers)

    # Verify actual file count matches expected count
    # Only count files for this specific subcircuit (get name from first topology)
    if configurations:
        first_topology, _ = configurations[0]
        subckt_name = first_topology.get("subckt", "unknown")
        # Count only files matching this subcircuit pattern: ckt_<subckt_name>_*.sp
        pattern = f"ckt_{subckt_name}_*.sp"
        actual_sp_files = list(output_dir.glob(pattern))
        actual_count = len(actual_sp_files)

        if actual_count != total_count:
            logger.error(
                f"File count mismatch! Expected {total_count} netlists but found {actual_count} .sp files "
                f"matching pattern '{pattern}' in {output_dir}. "
                f"Files may have been overwritten due to duplicate filenames."
            )
            raise ValueError("File count mismatch")

    logger.info(f"\nTotal: {total_count} netlists generated")


def verify_testbench_pins(
    testbench_topology: dict[str, Any],
    subckt_topology: dict[str, Any],
    subckt_filename: str
) -> None:
    """
    Verify that testbench DUT instance pins match subcircuit port order.

    Args:
        testbench_topology: Testbench topology with DUT instance
        subckt_topology: Subcircuit topology with port definitions
        subckt_filename: Filename for error reporting

    Raises:
        ValueError: If pin names or order don't match
    """
    # Find DUT instance in testbench
    subckt_name = subckt_topology.get("subckt")
    dut_instance = None

    for dev_name, dev_info in testbench_topology.get("devices", {}).items():
        if dev_info.get("dev") == subckt_name:
            dut_instance = dev_info
            break

    if not dut_instance:
        raise ValueError(f"No DUT instance found for subcircuit '{subckt_name}' in testbench")

    # Get pin lists
    tb_pins = list(dut_instance.get("pins", {}).keys())
    subckt_ports = list(subckt_topology.get("ports", {}).keys())

    # Verify they match
    if tb_pins != subckt_ports:
        raise ValueError(
            f"Pin mismatch for {subckt_filename}!\n"
            f"  Testbench DUT pins: {tb_pins}\n"
            f"  Subcircuit ports:   {subckt_ports}\n"
            f"  Pins must match in name and order."
        )


def generate_testbenches(
    circuit_module: Any,
    subckt_module: Any,
    ckt_dir: Path,
    output_dir: Path,
    corner: str = "tt",
) -> None:
    """
    Generate testbench netlists - one per subcircuit file.

    Args:
        circuit_module: Loaded Python module with testbench() function
        subckt_module: Loaded Python module with subcircuit() function
        ckt_dir: Directory containing subcircuit files
        output_dir: Directory to write testbench files
        corner: Process corner (e.g., 'tt', 'ss', 'ff')
    """
    logger = logging.getLogger(__name__)
    tb_topology = circuit_module.testbench()

    # Get subcircuit name from first configuration
    result = subckt_module.subcircuit()
    if isinstance(result, list):
        subckt_topology, subckt_sweep = result[0]
    else:
        subckt_topology, subckt_sweep = result

    subckt_name = subckt_topology.get("subckt", "unknown")

    # Find all subcircuit .json files for this cell
    ckt_json_files = sorted(ckt_dir.glob(f"ckt_{subckt_name}_*.json"))

    if not ckt_json_files:
        logger.warning(f"No subcircuit files found matching pattern: ckt_{subckt_name}_*.json")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Track summary by technology for table
    tech_summary = {}

    logger.info(f"\nGenerating testbenches for {len(ckt_json_files)} subcircuits...")

    for idx, ckt_json_path in enumerate(ckt_json_files, 1):
        # Read subcircuit JSON
        with open(ckt_json_path, 'r') as f:
            subckt_data = json.load(f)

        tech = subckt_data.get("meta", {}).get("tech")
        if not tech:
            logger.warning(f"No tech found in {ckt_json_path.name}, skipping")
            continue

        # Scale testbench values for this technology
        scaled_tb = scale_testbench(tb_topology, tech, techmap)

        # Add automatic fields
        complete_tb = autoadd_fields(
            scaled_tb, tech, techmap, subckt_data, corner
        )

        # Copy meta from subcircuit to testbench (for filename generation)
        if "meta" not in complete_tb:
            complete_tb["meta"] = {}
        complete_tb["meta"].update(subckt_data.get("meta", {}))

        # Verify pins match between testbench and subcircuit
        verify_testbench_pins(complete_tb, subckt_data, ckt_json_path.name)

        # Update includes to point to specific subcircuit file (relative path from TB dir to CKT dir)
        ckt_sp_filename = ckt_json_path.name.replace(".json", ".sp")
        # Use relative path: ../ckt/filename.sp (from results/tb/ to results/ckt/)
        ckt_sp_path = f"../ckt/{ckt_sp_filename}"
        complete_tb["includes"] = [ckt_sp_path]

        # Generate testbench filename (tb_ prefix, matches subcircuit params)
        ckt_filename = ckt_json_path.stem  # Remove .json extension
        tb_filename = ckt_filename.replace("ckt_", "tb_") + ".sp"
        tb_json_filename = ckt_filename.replace("ckt_", "tb_") + ".json"

        output_path = output_dir / tb_filename
        json_path = output_dir / tb_json_filename

        # Convert to SPICE
        spice_str = generate_spice(complete_tb, mode="testbench")

        # Write SPICE file
        output_path.write_text(spice_str)

        # Write JSON file
        json_path.write_text(compact_json(complete_tb))

        # Update summary
        if tech not in tech_summary:
            tech_summary[tech] = {
                "corner": corner,
                "temp": complete_tb.get("options", {}).get("temp", 27),
                "count": 0
            }
        tech_summary[tech]["count"] += 1

        # Log progress
        if idx % 100 == 0 or idx == len(ckt_json_files):
            logger.info(f"  [{idx}/{len(ckt_json_files)}] testbenches generated")

    # Print summary table
    logger.info("\nTestbench Summary:")
    rows = []
    for tech in sorted(tech_summary.keys()):
        info = tech_summary[tech]
        rows.append({
            "tech": tech,
            "corner": info["corner"],
            "temp": f"{info['temp']}°C",
            "count": info["count"]
        })

    headers = ["tech", "corner", "temp", "count"]
    print_table(rows, headers)

    total_count = sum(info["count"] for info in tech_summary.values())

    # Verify count matches number of subcircuits
    if total_count != len(ckt_json_files):
        logger.error(
            f"Testbench count mismatch! Generated {total_count} testbenches "
            f"but found {len(ckt_json_files)} subcircuit files."
        )
        raise ValueError("Testbench count mismatch")

    logger.info(f"\nTotal: {total_count} testbenches generated")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate SPICE netlists from Python specifications"
    )
    parser.add_argument(
        "mode", choices=["subckt", "tb"], help="Generation mode: subckt or tb"
    )
    parser.add_argument(
        "circuit", type=Path, help="Circuit Python file (e.g., blocks/samp.py)"
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output directory"
    )
    parser.add_argument(
        "--ckt-dir", type=Path, help="Subcircuit directory (required for tb mode)"
    )
    parser.add_argument(
        "-c",
        "--corner",
        default="tt",
        help="Process corner for testbenches (default: tt)",
    )

    args = parser.parse_args()

    # Setup logging with log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cell_name = args.circuit.stem
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{args.mode}_{cell_name}_{timestamp}.log"
    logger = setup_logging(log_file)

    logger.info("=" * 70)
    logger.info(f"Netlist Generation - {args.mode.upper()} mode")
    logger.info("=" * 70)
    logger.info(f"Circuit:      {args.circuit}")
    logger.info(f"Output dir:   {args.output}")
    if args.mode == "tb" and args.ckt_dir:
        logger.info(f"CKT dir:      {args.ckt_dir}")
        logger.info(f"Corner:       {args.corner}")
    logger.info(f"Log file:     {log_file}")
    logger.info("=" * 70)

    try:
        # Load circuit module
        circuit_module = load_circuit_module(args.circuit)

        if args.mode == "subckt":
            generate_subcircuits(circuit_module, args.output)
        else:
            # For testbench mode, we need the subcircuit directory
            if not args.ckt_dir:
                parser.error("--ckt-dir is required for testbench generation")
            generate_testbenches(
                circuit_module, circuit_module, args.ckt_dir, args.output, args.corner
            )

        logger.info("=" * 70)
        logger.info("Generation completed successfully")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"\nGeneration failed: {e}")
        raise


if __name__ == "__main__":
    main()
