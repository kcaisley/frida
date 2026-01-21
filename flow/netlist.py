"""
Converts Python circuit descriptions into SPICE netlists with
technology-specific device mappings and parameter sweeps.
"""

import argparse
import copy
import datetime
import hashlib
import itertools
import json
import logging
from pathlib import Path
from typing import Any

from flow.common import (
    calc_table_columns,
    compact_json,
    format_value,
    load_cell_script,
    load_db,
    print_flow_header,
    print_table_header,
    print_table_row,
    save_db,
    scalemap,
    setup_logging,
    techmap,
)


def expand_sweeps(sweeps: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Expand sweep dict into list of scalar sweep combinations (cartesian product).

    Takes a sweep dict with lists of values and returns the cartesian product
    as a list of dicts, each with scalar values.

    Args:
        sweeps: Sweep dict with potentially list values for tech, corner, temp,
                globals, selections

    Returns:
        List of scalar sweep dicts

    Example:
        Input:  {"tech": ["tsmc65", "tsmc28"], "globals": {"nmos": {"w": [1, 2]}}}
        Output: [
            {"tech": "tsmc65", "globals": {"nmos": {"w": 1}}},
            {"tech": "tsmc65", "globals": {"nmos": {"w": 2}}},
            {"tech": "tsmc28", "globals": {"nmos": {"w": 1}}},
            {"tech": "tsmc28", "globals": {"nmos": {"w": 2}}},
        ]
    """
    # Collect all sweepable parameters and their values
    sweep_axes = []  # List of (path, values) tuples

    # Top-level list parameters: tech, corner, temp
    for key in ["tech", "corner", "temp"]:
        if key in sweeps:
            val = sweeps[key]
            if isinstance(val, list):
                sweep_axes.append(((key,), val))
            else:
                sweep_axes.append(((key,), [val]))

    # Global device parameters
    if "globals" in sweeps:
        for dev_type, dev_params in sweeps["globals"].items():
            for param, val in dev_params.items():
                path = ("globals", dev_type, param)
                if isinstance(val, list):
                    sweep_axes.append((path, val))
                else:
                    sweep_axes.append((path, [val]))

    # Selection parameters
    if "selections" in sweeps:
        for i, sel in enumerate(sweeps["selections"]):
            devices = sel.get("devices", [])
            for param, val in sel.items():
                if param == "devices":
                    continue
                path = ("selections", i, param)
                if isinstance(val, list):
                    sweep_axes.append((path, val))
                else:
                    sweep_axes.append((path, [val]))

    # If no sweep axes, return single sweep with original values
    if not sweep_axes:
        return [copy.deepcopy(sweeps)]

    # Generate cartesian product
    paths = [axis[0] for axis in sweep_axes]
    value_lists = [axis[1] for axis in sweep_axes]

    result = []
    for combo in itertools.product(*value_lists):
        # Build scalar sweep dict
        scalar_sweep = {}

        # Set values at each path
        for path, value in zip(paths, combo):
            if len(path) == 1:
                # Top-level key
                scalar_sweep[path[0]] = value
            elif path[0] == "globals":
                # globals.dev_type.param
                if "globals" not in scalar_sweep:
                    scalar_sweep["globals"] = {}
                dev_type = path[1]
                param = path[2]
                if dev_type not in scalar_sweep["globals"]:
                    scalar_sweep["globals"][dev_type] = {}
                scalar_sweep["globals"][dev_type][param] = value
            elif path[0] == "selections":
                # selections[i].param
                if "selections" not in scalar_sweep:
                    # Copy devices from original selections
                    scalar_sweep["selections"] = [
                        {"devices": sel.get("devices", [])}
                        for sel in sweeps.get("selections", [])
                    ]
                idx = path[1]
                param = path[2]
                scalar_sweep["selections"][idx][param] = value

        result.append(scalar_sweep)

    return result


def generate_netstruct(topology: dict[str, Any], sweep: dict[str, Any]) -> dict[str, Any]:
    """
    Apply sweep globals/selections to topology, add tech/corner/temp to meta.

    This fills in generic device dimensions, values, and types from the sweep,
    but keeps everything technology-agnostic. The map_technology() function
    then converts these to PDK-specific models and scaled dimensions.

    Args:
        topology: Base topology dict
        sweep: Scalar sweep dict (one combination from expand_sweeps)
               Contains 'tech', 'globals', 'selections', 'corner', 'temp', etc.

    Returns:
        Topology with generic device values filled in and sweep params in meta
    """
    result = copy.deepcopy(topology)

    # Ensure meta exists
    if "meta" not in result:
        result["meta"] = {}

    # Add tech, corner, temp to meta
    if "tech" in sweep:
        result["meta"]["tech"] = sweep["tech"]
    if "corner" in sweep:
        result["meta"]["corner"] = sweep["corner"]
    if "temp" in sweep:
        result["meta"]["temp"] = sweep["temp"]

    # Apply globals (device dimension defaults like nmos.w, pmos.l, cap.value)
    if "globals" in sweep:
        for dev_type, defaults in sweep["globals"].items():
            for dev_name, dev_info in result.get("devices", {}).items():
                # Match device by dev field
                if dev_info.get("dev") == dev_type:
                    # Ensure device has meta
                    if "meta" not in dev_info:
                        dev_info["meta"] = {"dev": dev_type}
                    # Apply defaults (don't override explicit values)
                    for param, value in defaults.items():
                        if param not in dev_info["meta"]:
                            dev_info["meta"][param] = value

    # Apply selections (device-specific parameter overrides)
    if "selections" in sweep:
        for sel in sweep["selections"]:
            devices = sel.get("devices", [])
            for dev_name in devices:
                if dev_name in result.get("devices", {}):
                    dev_info = result["devices"][dev_name]
                    if "meta" not in dev_info:
                        dev_info["meta"] = {}
                    # Apply selection params (override globals)
                    for param, value in sel.items():
                        if param != "devices":
                            dev_info["meta"][param] = value

    return result


def map_technology(
    topology: dict[str, Any], techmap: dict[str, Any]
) -> dict[str, Any]:
    """
    Map generic topology to technology-specific netlist.

    Reads tech from topology["meta"]["tech"].
    Uses device meta.dev ('nmos'/'pmos') + meta.type ('lvt'/'svt'/'hvt') to look up devmap.
    """
    tech = topology["meta"]["tech"]
    tech_config = techmap[tech]
    topo_copy = copy.deepcopy(topology)

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
    topology: dict[str, Any], techmap: dict[str, Any]
) -> dict[str, Any]:
    """
    Scale voltage and time values in testbench topology using scalemap.

    Reads tech from topology["meta"]["tech"].
    """
    tech = topology["meta"]["tech"]
    tech_config = techmap[tech]
    vdd = tech_config["vdd"]
    tstep = tech_config.get("tstep", 1e-9)

    topo_copy = copy.deepcopy(topology)

    # Add vdd and tstep to meta
    topo_copy["meta"]["vsupply"] = vdd
    topo_copy["meta"]["tstep"] = tstep

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
    subckt_topology: dict[str, Any],
    techmap: dict[str, Any],
) -> dict[str, Any]:
    """
    Add automatic fields to testbench topology.

    Reads tech from topology["meta"]["tech"] and corner from topology["meta"]["corner"].

    Args:
        topology: Testbench topology
        subckt_topology: Subcircuit topology (for generating save statements)
        techmap: Technology mapping

    Returns:
        Topology with automatic fields added
    """
    tech = topology["meta"]["tech"]
    corner = topology["meta"].get("corner")
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


def find_matching_topo(topology_list: list[dict[str, Any]], subckt: dict[str, Any]) -> dict[str, Any] | None:
    """
    Find topology with meta values matching subckt meta (excluding tech, corner, temp).

    Args:
        topology_list: List of topology dicts to search
        subckt: Circuit struct with meta values to match

    Returns:
        Matching topology or None if not found
    """
    subckt_meta = subckt.get("meta", {})
    for topo in topology_list:
        topo_meta = topo.get("meta", {})
        # Match on shared keys (excluding tech, corner, temp)
        shared_keys = set(topo_meta.keys()) & set(subckt_meta.keys()) - {"tech", "corner", "temp"}
        if all(topo_meta.get(k) == subckt_meta.get(k) for k in shared_keys):
            return topo
    return None


def generate_filename(topology: dict[str, Any]) -> str:
    """
    Generate base filename for a netlist using meta values for parameters.

    Returns base name WITHOUT prefix (subckt_/tb_) and WITHOUT extension (.sp/.json).
    Callers add prefix and extension as needed.

    Args:
        topology: Topology dictionary with 'subckt' or 'testbench' key and meta field containing tech

    Returns:
        Base filename string (e.g., 'gate_inv_inv_tsmc65_abc123def456')
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
            hash_hex = hash_obj.hexdigest()[:12]  # Use first 12 chars of hash
            parts.append(hash_hex)

        return "_".join(parts)
    else:
        # Testbench
        if "meta" not in topology:
            raise ValueError("Topology for testbench missing required 'meta' field")

        meta = topology["meta"]
        if "tech" not in meta:
            raise ValueError("Topology meta for testbench missing required 'tech' field")

        tech = meta["tech"]
        tb_name = topology.get('testbench', 'tb_unnamed')
        parts = [tb_name, tech]

        # Add corner and temp if present
        if "corner" in meta:
            parts.append(str(meta["corner"]))
        if "temp" in meta:
            parts.append(str(meta["temp"]))

        return "_".join(parts)




# ========================================================================
# Validation/Check Functions
# ========================================================================


def check_subckt(subckt: dict[str, Any]) -> None:
    """
    Check that subcircuit has required fields.

    Required structure:
        - subckt: str (subcircuit name)
        - ports: dict (port definitions)
        - devices: dict of dicts (each with pins, meta, model)
        - meta: dict with at least 'tech'

    Raises:
        ValueError: If required fields are missing or malformed
    """
    if "subckt" not in subckt:
        raise ValueError("Subcircuit missing required 'subckt' field")

    if "ports" not in subckt or not isinstance(subckt["ports"], dict):
        raise ValueError("Subcircuit missing required 'ports' dict")

    if "devices" not in subckt or not isinstance(subckt["devices"], dict):
        raise ValueError("Subcircuit missing required 'devices' dict")

    if "meta" not in subckt or not isinstance(subckt["meta"], dict):
        raise ValueError("Subcircuit missing required 'meta' dict")

    if "tech" not in subckt["meta"]:
        raise ValueError("Subcircuit meta missing required 'tech' field")


def check_testbench(tb: dict[str, Any]) -> None:
    """
    Check that testbench has required fields.

    Required structure:
        - testbench: str (testbench name)
        - devices: dict (device definitions)
        - analyses: dict (analysis definitions)
        - libs: list (library includes)
        - meta: dict with at least 'tech' and 'corner'

    Raises:
        ValueError: If required fields are missing or malformed
    """
    if "testbench" not in tb:
        raise ValueError("Testbench missing required 'testbench' field")

    if "devices" not in tb or not isinstance(tb["devices"], dict):
        raise ValueError("Testbench missing required 'devices' dict")

    if "analyses" not in tb or not isinstance(tb["analyses"], dict):
        raise ValueError("Testbench missing required 'analyses' dict")

    if "libs" not in tb or not tb["libs"]:
        raise ValueError("Testbench missing required 'libs' field")

    if "meta" not in tb or not isinstance(tb["meta"], dict):
        raise ValueError("Testbench missing required 'meta' dict")

    if "tech" not in tb["meta"]:
        raise ValueError("Testbench meta missing required 'tech' field")

    if "corner" not in tb["meta"]:
        raise ValueError("Testbench meta missing required 'corner' field")


def check_subcircuit_instances(
    topology: dict[str, Any],
    subckt_base_dir: Path,
    netlist_filename: str
) -> None:
    """
    Verify that subcircuit instances in topology have matching port definitions.

    Args:
        topology: Testbench topology to check
        subckt_base_dir: Base directory for subcircuit files
        netlist_filename: Filename for error messages

    Raises:
        ValueError: If pin mismatch is detected
    """
    logger = logging.getLogger(__name__)

    for dev_name, dev_info in topology.get("devices", {}).items():
        dev = dev_info.get("dev")
        # Skip built-in devices
        if dev in ["vsource", "res", "cap", "nmos", "pmos"] or dev is None:
            continue

        # This is a subcircuit instance - find its definition
        subckt_name = dev
        subckt_dir = subckt_base_dir / subckt_name
        if not subckt_dir.exists():
            logger.warning(f"No subcircuit directory found for '{subckt_name}' at {subckt_dir}")
            continue

        pattern = f"subckt_{subckt_name}_*.json"
        subckt_files = list(subckt_dir.glob(pattern))

        if not subckt_files:
            logger.warning(f"No subcircuit definition found for '{subckt_name}' (searched: {subckt_dir}/{pattern})")
            continue

        # Read first matching subcircuit to get port definition
        with open(subckt_files[0], 'r') as f:
            subckt_data = json.load(f)

        # Get pin lists
        instance_pins = list(dev_info.get("pins", {}).keys())
        subckt_ports = list(subckt_data.get("ports", {}).keys())

        # Verify they match
        if instance_pins != subckt_ports:
            raise ValueError(
                f"Pin mismatch in {netlist_filename} for instance '{dev_name}' of subcircuit '{subckt_name}'!\n"
                f"  Instance pins: {instance_pins}\n"
                f"  Subcircuit ports: {subckt_ports}\n"
                f"  Pins must match in name and order."
            )


def main() -> None:
    """Main entry point."""
    logger = logging.getLogger(__name__)

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

    args = parser.parse_args()

    # Setup logging with log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cell_name = args.circuit.stem
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{args.mode}_{cell_name}_{timestamp}.log"
    setup_logging(log_file)

    print_flow_header(
        cell=cell_name,
        flow=args.mode,
        script=args.circuit,
        outdir=args.output / cell_name,
        log_file=log_file,
    )

    try:
        # Load circuit module
        circuit_module = load_cell_script(args.circuit)

        if args.mode == "subckt":
            # ================================================================
            # SUBCIRCUIT MODE
            # ================================================================

            # 1. Create results dir and empty db list
            subckt_dir = args.output / cell_name / "subckt"
            subckt_dir.mkdir(parents=True, exist_ok=True)
            db: list[dict] = []

            # 2. Get topology list + sweeps dict from circuit module
            topology_list, sweeps = circuit_module.subcircuit()

            # 3. Expand sweeps to get cartesian product
            sweep_list = expand_sweeps(sweeps)

            # 4. Loop over topologies and sweeps
            total_count = 0
            for topo in topology_list:
                for sweep in sweep_list:
                    # 5. Generate subckt struct (apply sweep globals/selections/tech)
                    subckt = generate_netstruct(topo, sweep)

                    # 6. Map to technology (convert generic to PDK-specific)
                    subckt = map_technology(subckt, techmap)

                    # 7. Run checks
                    check_subckt(subckt)

                    # Print table header on first iteration
                    if total_count == 0:
                        headers, col_widths = calc_table_columns(subckt, sweeps)
                        print_table_header(headers, col_widths)

                    # 8. Create dbctx with cellname and cfgname
                    cfgname = generate_filename(subckt)
                    dbctx = {
                        "cellname": cell_name,
                        "cfgname": cfgname,
                        "subckt_db": None,
                        "subckt_netlist": None,
                        "tb_db": [],
                        "tb_netlist": [],
                        "sim_raw": [],
                        "meas_db": None,
                        "plot_img": [],
                    }

                    # 9. Write JSON struct
                    json_path = subckt_dir / f"subckt_{cfgname}.json"
                    json_path.write_text(compact_json(subckt))
                    dbctx["subckt_db"] = f"subckt/subckt_{cfgname}.json"

                    # 10. Write SPICE netlist
                    sp_path = subckt_dir / f"subckt_{cfgname}.sp"
                    spice_str = generate_spice(subckt, mode="subcircuit")
                    sp_path.write_text(spice_str)
                    dbctx["subckt_netlist"] = f"subckt/subckt_{cfgname}.sp"

                    # 11. Append dbctx to db list
                    db.append(dbctx)
                    total_count += 1

                    # Print table row
                    print_table_row(subckt["meta"], headers, col_widths)

            # 12. Write db.json and print summary
            db_path = args.output / cell_name / "db.json"
            save_db(db_path, db)
            logger.info("-" * 80)
            logger.info(f"Result: {total_count} subcircuits generated")
            logger.info("-" * 80)

        elif args.mode == "tb":
            # ================================================================
            # TESTBENCH MODE
            # ================================================================

            # 1. Get topology list + sweeps dict from circuit module
            topology_list, sweeps = circuit_module.testbench()

            # 2. Expand sweeps to get cartesian product (corner × temp × other params)
            sweep_list = expand_sweeps(sweeps)

            # 3. Load existing db.json (created by subckt step)
            db_path = args.output / cell_name / "db.json"
            db = load_db(db_path)
            if not db:
                raise ValueError(f"No db.json found at {db_path}. Run subckt mode first.")

            tb_dir = args.output / cell_name / "tb"
            tb_dir.mkdir(parents=True, exist_ok=True)

            total_count = 0

            # 4. Loop over each subckt entry in db
            for dbctx in db:
                # 5. Load the subckt struct from subckt_db path
                subckt_path = args.output / cell_name / dbctx["subckt_db"]
                with open(subckt_path) as f:
                    subckt = json.load(f)

                # 6. Find matching tb topology based on meta params in subckt
                topo = find_matching_topo(topology_list, subckt)
                if not topo:
                    logger.warning(f"No matching testbench for {dbctx['cfgname']}")
                    continue

                # 7. Loop over sweep combinations
                for sweep in sweep_list:
                    # 8. Generate testbench struct (apply sweep, inherit tech from subckt)
                    sweep_with_subckt_tech = {**sweep, "tech": subckt["meta"]["tech"]}
                    tb = generate_netstruct(topo, sweep_with_subckt_tech)

                    # 9. Map to technology (tech is in tb.meta.tech)
                    tb = map_technology(tb, techmap)

                    # 10. Scale testbench values
                    tb = scale_testbench(tb, techmap)

                    # 11. Add auto fields (libs, includes, options, save)
                    tb = autoadd_fields(tb, subckt, techmap)

                    # 12. Run checks
                    check_testbench(tb)

                    # Print table header on first iteration
                    if total_count == 0:
                        headers, col_widths = calc_table_columns(tb, sweeps)
                        print_table_header(headers, col_widths)

                    # 13. Generate filename and write JSON
                    cfgname = dbctx["cfgname"]
                    corner = tb["meta"].get("corner", "tt")
                    temp = tb["meta"].get("temp", 27)
                    tb_filename = f"{cfgname}_{corner}_{temp}"

                    json_path = tb_dir / f"tb_{tb_filename}.json"
                    json_path.write_text(compact_json(tb))
                    dbctx["tb_db"].append(f"tb/tb_{tb_filename}.json")

                    # 14. Write SPICE netlist
                    sp_path = tb_dir / f"tb_{tb_filename}.sp"
                    spice_str = generate_spice(tb, mode="testbench")
                    sp_path.write_text(spice_str)
                    dbctx["tb_netlist"].append(f"tb/tb_{tb_filename}.sp")

                    total_count += 1

                    # Print table row
                    print_table_row(tb["meta"], headers, col_widths)

            # 15. Write updated db.json
            save_db(db_path, db)
            logger.info("-" * 80)
            logger.info(f"Result: {total_count} testbenches generated")
            logger.info("-" * 80)

    except Exception as e:
        logging.error(f"\nGeneration failed: {e}")
        raise


if __name__ == "__main__":
    main()
