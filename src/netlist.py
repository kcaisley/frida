"""
Converts Python circuit descriptions into SPICE netlists with
technology-specific device mappings and parameter sweeps.

Data Flow:
----------
1. Load circuit module (Python file with subcircuit()/testbench() functions)
2. expand_sweeps() - Generate all parameter combinations from sweep specs
3. map_technology() - Map generic devices to tech-specific models
4. generate_spice() - Convert to SPICE netlist string
5. Write .sp and .json files

Key Data Structures:
--------------------

Topology Dictionary (from circuit modules):
    {
        "subckt": str,                      # Subcircuit name
        "ports": dict[str, str],            # Port name -> direction ("I", "O", "B")
        "devices": dict[str, DeviceDict],   # Device instances
        "meta": dict[str, Any]              # Optional metadata
    }

DeviceDict (before technology mapping):
    {
        "dev": "nmos" | "pmos" | "cap" | "res",
        "pins": dict[str, str],             # Pin connections
        "w": int,                           # Width multiplier (transistors)
        "l": int,                           # Length multiplier (transistors)
        "c": int,                           # Capacitance weight (capacitors)
        "m": int,                           # Multiplier (capacitors)
        "r": int                            # Resistance multiplier (resistors)
    }

DeviceDict (after technology mapping):
    {
        "model": str,                       # Technology-specific model name
        "pins": dict[str, str],
        "w": float,                         # Absolute width in meters
        "l": float,                         # Absolute length in meters
        "nf": int,                          # Number of fingers
        "meta": dict[str, Any]              # Original generic parameters
    }

Sweep Dictionary:
    {
        "tech": list[str],                  # Technologies to generate
        "defaults": {
            "nmos": {"type": str, "w": int, "l": int, "nf": int},
            "pmos": {"type": str, "w": int, "l": int, "nf": int},
            "cap": {"dev": str},            # e.g., "momcap"
            "res": {"dev": str, "r": int}   # e.g., "polyres", 4
        },
        "sweeps": list[SweepSpec]           # Parameter sweep specs
    }

SweepSpec:
    {
        "devices": str | list[str],         # Device names or "cap"/"res" types
        "w": list[int],                     # Width multipliers to sweep
        "l": list[int],                     # Length multipliers to sweep
        "m": list[int],                     # Cap multipliers to sweep
        "type": list[str]                   # Transistor types to sweep
    }
"""

import argparse
import copy
import importlib.util
import itertools
import json
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
# Netlist Generation Flow
# ========================================================================


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

    Stores generic parameters in 'meta' subfield:
      - dev: 'nmos' or 'pmos'
      - type: 'lvt', 'svt', or 'hvt'
      - w, l: multipliers
      - nf: number of fingers
    """

    def get_defaults(dev: str) -> dict[str, Any]:
        """Get default meta values for a transistor type."""
        if dev not in ["nmos", "pmos"]:
            return {}
        # Check if defaults exist in sweep (not all topologies use sweeps)
        if "defaults" not in sweep:
            return {}
        defaults = sweep["defaults"][dev]
        return {
            "dev": dev,
            "type": defaults.get("type", "svt"),
            "w": defaults["w"],
            "l": defaults["l"],
            "nf": defaults.get("nf", 1),
        }

    # Generate combinations for each sweep group
    if "sweeps" not in sweep or not sweep["sweeps"]:
        topo_copy = copy.deepcopy(topology)
        for dev_name, dev_info in topo_copy["devices"].items():
            meta = get_defaults(dev_info.get("dev", ""))
            if meta:
                dev_info["meta"] = meta
        return [topo_copy]

    # Build sweep combinations per group
    sweep_groups = []
    for sweep_spec in sweep["sweeps"]:
        sweep_devices = sweep_spec["devices"]
        param_lists = {
            p: sweep_spec[p] for p in ["w", "l", "nf", "type"] if p in sweep_spec
        }
        param_names = list(param_lists.keys())

        group_combos = []
        for combo in itertools.product(*[param_lists[p] for p in param_names]):
            group_config = {dev: dict(zip(param_names, combo)) for dev in sweep_devices}
            group_combos.append(group_config)
        sweep_groups.append(group_combos)

    # Combine all sweep groups via Cartesian product
    all_configurations = []
    for combo in itertools.product(*sweep_groups):
        config = {}
        for sweep_config in combo:
            config.update(sweep_config)

        topo_copy = copy.deepcopy(topology)
        for dev_name, dev_info in topo_copy["devices"].items():
            meta = get_defaults(dev_info.get("dev", ""))
            if not meta:
                continue

            # Apply sweep overrides
            if dev_name in config:
                meta.update(config[dev_name])

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
        dev = dev_info.get("dev")

        # Handle MOM capacitors
        if dev == "mom_cap":
            mom_config = tech_config.get("mom_cap", {})
            if mom_config:
                dev_info["model"] = mom_config.get("model", "capacitor")
                # Keep the weight, it will be converted to capacitance in generate_spice
            continue

        # Resistors need no technology mapping (already have r value)
        if dev == "res":
            continue

        meta = dev_info.get("meta")
        if not meta:
            continue

        # Combine dev + type for devmap lookup (e.g., 'nmos_lvt')
        device_key = f"{meta['dev']}_{meta['type']}"
        dev_map = tech_config["devmap"].get(device_key)
        if not dev_map:
            continue

        # Remove generic 'dev' field, replace with tech-specific 'model'
        del dev_info["dev"]
        dev_info["model"] = dev_map["model"]
        dev_info["w"] = meta["w"] * dev_map["w"]
        dev_info["l"] = meta["l"] * dev_map["l"]
        dev_info["nf"] = meta.get("nf", 1)

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

        # Header
        lines.append("* " + "=" * 72)
        lines.append(f"* {subckt_name}")
        lines.append("* " + "=" * 72)
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
            dev = dev_info.get("dev")
            model = dev_info.get("model")
            pins = dev_info.get("pins", {})

            # Transistors have a 'meta' field
            if "meta" in dev_info:
                pin_list = " ".join(pins.get(p, "0") for p in ["d", "g", "s", "b"])
                line = f"{dev_name} {pin_list} {model}"
                line += f" W={format_value(dev_info['w'])}"
                line += f" L={format_value(dev_info['l'])}"
                line += f" nf={dev_info.get('nf', 1)}"
                lines.append(line)

            # MOM capacitors (for CDAC and similar structures)
            elif dev == "mom_cap":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                weight = dev_info.get("weight", 1)
                cap_model = dev_info.get("model", "capacitor")
                cap_value = dev_info.get("c", None)

                if cap_value is not None:
                    # Explicit capacitance value provided
                    lines.append(
                        f"{dev_name} {p} {n} {cap_model} c={format_value(cap_value, 'F')}"
                    )
                else:
                    # Use weight (for weighted capacitor arrays)
                    lines.append(
                        f"{dev_name} {p} {n} {cap_model} c={format_value(weight * 1e-15, 'F')}"
                    )

            # Resistors (for RDAC partition scheme)
            elif dev == "res":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                r = dev_info.get("r", 1000)  # resistance in ohms
                lines.append(f"{dev_name} {p} {n} {format_value(r, 'Ohm')}")

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


def generate_filename(
    topology: dict[str, Any], tech: str, sweep_spec: dict[str, Any] | None = None
) -> str:
    """
    Generate filename for a netlist using meta values for parameters.

    Args:
        topology: Topology dictionary with 'subckt' or 'testbench' key
        tech: Technology name (e.g., 'tsmc65', 'tsmc28', 'tower180')
        sweep_spec: Optional sweep specification dictionary

    Returns:
        Filename string (e.g., 'cdac_7bit_7cap_radix2_tsmc65.sp')
    """
    if "subckt" in topology:
        base_name = topology["subckt"]
        parts = [base_name, tech]

        if sweep_spec and "sweeps" in sweep_spec:
            for sweep in sweep_spec["sweeps"]:
                devices = sweep["devices"]
                meta = topology["devices"][devices[0]].get("meta", {})

                # Build param string for varying parameters
                param_parts = []
                for param in ["w", "l", "nf", "type"]:
                    if param in sweep and len(sweep[param]) > 1:
                        param_parts.append(f"{param}{meta.get(param, '')}")

                if param_parts:
                    parts.append("-".join(devices) + "-" + "-".join(param_parts))

        return "_".join(parts) + ".sp"

    else:
        return f"{topology.get('testbench', 'tb_unnamed')}_{tech}.sp"


# Main flow functions


def generate_subcircuits(
    circuit_module: Any, output_dir: Path, tech_list: list[str] | None = None
) -> None:
    """
    Generate subcircuit netlists from a circuit module.

    Args:
        circuit_module: Loaded Python module with subcircuit() function
        output_dir: Directory to write output files
        tech_list: Optional list of technologies to generate (uses module's list if None)
    """
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

    for topology, sweep in configurations:
        if tech_list is None:
            config_tech_list = sweep.get("tech", ["tsmc65"])
        else:
            config_tech_list = tech_list

        # Expand sweeps
        topologies = expand_sweeps(topology, sweep)

        print(
            f"Configuration: {topology.get('subckt', 'unnamed')} - {len(topologies)} parameter combinations"
        )

        # Generate netlists for each technology
        for tech in config_tech_list:
            for topo in topologies:
                # Map to technology
                tech_topo = map_technology(topo, tech, techmap)

                # Generate filename
                filename = generate_filename(tech_topo, tech, sweep)
                output_path = output_dir / filename
                json_path = output_dir / filename.replace(".sp", ".json")

                # Convert to SPICE
                spice_str = generate_spice(tech_topo, mode="subcircuit")

                # Write SPICE file
                output_path.write_text(spice_str)

                # Write JSON file
                json_path.write_text(compact_json(tech_topo))

                total_count += 1

    print(f"\nTotal: {total_count} netlists generated")


def generate_testbenches(
    circuit_module: Any,
    subckt_module: Any,
    output_dir: Path,
    tech_list: list[str] | None = None,
    corner: str = "tt",
) -> None:
    """
    Generate testbench netlists from a circuit module.

    Args:
        circuit_module: Loaded Python module with testbench() function
        subckt_module: Loaded Python module with subcircuit() function
        output_dir: Directory to write output files
        tech_list: Optional list of technologies to generate
        corner: Process corner (e.g., 'tt', 'ss', 'ff')
    """
    tb_topology = circuit_module.testbench()
    subckt_topology, subckt_sweep = subckt_module.subcircuit()

    if tech_list is None:
        tech_list = subckt_sweep.get("tech", ["tsmc65"])

    # Ensure tech_list is a list (should always be true after the above check)
    if not tech_list:
        tech_list = ["tsmc65"]

    # Generate testbenches for each technology
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for tech in tech_list:
        print(f"\nTechnology: {tech}")

        # Scale testbench values
        scaled_tb = scale_testbench(tb_topology, tech, techmap)

        # Add automatic fields
        complete_tb = autoadd_fields(
            scaled_tb, tech, techmap, subckt_topology, corner
        )

        # Generate filename
        filename = generate_filename(complete_tb, tech)
        output_path = output_dir / filename
        json_path = output_dir / filename.replace(".sp", ".json")

        # Convert to SPICE
        spice_str = generate_spice(complete_tb, mode="testbench")

        # Write SPICE file
        output_path.write_text(spice_str)

        # Write JSON file
        json_path.write_text(compact_json(complete_tb))

        count += 1
        print(f"  Generated testbench: {filename}")

    print(f"\nTotal: {count} testbenches generated")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate SPICE netlists from Python specifications"
    )
    parser.add_argument(
        "mode", choices=["subckt", "tb"], help="Generation mode: subckt or tb"
    )
    parser.add_argument(
        "circuit", type=Path, help="Circuit Python file (e.g., src/samp_tgate.py)"
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output directory"
    )
    parser.add_argument(
        "-t", "--tech", nargs="+", help="Technology list (default: from circuit file)"
    )
    parser.add_argument(
        "-c",
        "--corner",
        default="tt",
        help="Process corner for testbenches (default: tt)",
    )

    args = parser.parse_args()

    # Load circuit module
    circuit_module = load_circuit_module(args.circuit)

    if args.mode == "subckt":
        generate_subcircuits(circuit_module, args.output, args.tech)
    else:
        # For testbench mode, we also need the subcircuit definition
        generate_testbenches(
            circuit_module, circuit_module, args.output, args.tech, args.corner
        )


if __name__ == "__main__":
    main()
