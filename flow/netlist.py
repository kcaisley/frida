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

from typing import Callable

from flow.common import (
    calc_table_columns,
    compact_json,
    format_value,
    load_cell_script,
    load_files_list,
    print_flow_header,
    print_table_header,
    print_table_row,
    save_files_list,
    scalemap,
    setup_logging,
    techmap,
)


def expand_topo_params(
    netstruct: dict[str, Any],
    generate_topology_fn: Callable[..., tuple[dict, dict]] | None = None,
) -> list[dict[str, Any]]:
    """
    Stage 1: Expand topo_params cartesian product and fill ports/devices.

    If ports/devices are already filled, returns [netstruct] unchanged.
    Otherwise, requires generate_topology_fn from the block module.

    Args:
        netstruct: Merged struct with potential topo_params
        generate_topology_fn: Block's generate_topology(**topo_params) function

    Returns:
        List of structs with ports/devices filled and topo_param values in meta
    """
    # If devices already filled, skip Stage 1
    # (ports may be empty for top-level testbenches)
    if netstruct.get("devices"):
        result = copy.deepcopy(netstruct)
        if "meta" not in result:
            result["meta"] = {}
        # Set subckt name from cellname for static topologies
        base_name = netstruct.get("cellname", "unnamed")
        result["subckt"] = base_name
        return [result]

    topo_params = netstruct.get("topo_params", {})
    if not topo_params:
        msg = f"Struct '{netstruct.get('name')}' has empty ports/devices but no topo_params"
        logging.error(msg)
        raise ValueError(msg)

    if generate_topology_fn is None:
        msg = "Block must define generate_topology() when using topo_params"
        logging.error(msg)
        raise ValueError(msg)

    # Cartesian product of topo_params
    param_names = list(topo_params.keys())
    param_lists = [
        topo_params[k] if isinstance(topo_params[k], list) else [topo_params[k]]
        for k in param_names
    ]

    result_list = []
    base_name = netstruct.get("cellname", "unnamed")

    for combo in itertools.product(*param_lists):
        param_dict = dict(zip(param_names, combo))

        # Call block's generate_topology() with scalar params
        ports, devices = generate_topology_fn(**param_dict)

        # Skip invalid combinations (generate_topology returns None, None)
        if ports is None or devices is None:
            continue

        result = copy.deepcopy(netstruct)
        result["ports"] = ports
        result["devices"] = devices

        # Subcircuit name is always the base name (topology-independent)
        result["subckt"] = base_name

        # Store topo_param values in meta
        if "meta" not in result:
            result["meta"] = {}
        result["meta"].update(param_dict)

        # Clear topo_params (already expanded)
        result.pop("topo_params", None)

        result_list.append(result)

    return result_list


def expand_dev_params(netstructs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Stage 2: Expand tech, inst_params, dev_params into scalar structs.

    Takes list of structs from expand_topo_params() and expands:
    - tech (list of technologies)
    - dev_params (device-type defaults, applied LAST)
    - inst_params (instance-specific overrides, applied BEFORE dev_params)

    Priority order:
    1. Values set in devices by generate_topology() - NEVER overwritten
    2. inst_params - applied next
    3. dev_params - applied last as defaults

    Args:
        netstructs: List of structs from expand_topo_params()

    Returns:
        List of fully expanded structs with all params scalar and applied to devices
    """
    result_list = []

    for netstruct in netstructs:
        sweep_axes = []  # List of (path, values)

        # 1. Tech axis
        tech = netstruct.get("tech")
        if tech is not None:
            sweep_axes.append((("tech",), tech if isinstance(tech, list) else [tech]))

        # 2. dev_params axes (device-type defaults)
        for dev_type, params in netstruct.get("dev_params", {}).items():
            # Skip child subcircuit params for now (handled later)
            if isinstance(params, dict) and "topo_params" in params:
                continue
            for param, val in params.items():
                path = ("dev_params", dev_type, param)
                sweep_axes.append((path, val if isinstance(val, list) else [val]))

        # 3. inst_params axes (instance-specific overrides)
        for idx, inst_spec in enumerate(netstruct.get("inst_params", [])):
            # Skip subcircuit instance overrides for now
            if "inst" in inst_spec:
                continue
            for param, val in inst_spec.items():
                if param == "devices":
                    continue
                path = ("inst_params", idx, param)
                sweep_axes.append((path, val if isinstance(val, list) else [val]))

        # If no sweep axes, return single struct
        if not sweep_axes:
            result_list.append(copy.deepcopy(netstruct))
            continue

        # 4. Cartesian product
        paths = [axis[0] for axis in sweep_axes]
        value_lists = [axis[1] for axis in sweep_axes]

        for combo in itertools.product(*value_lists):
            expanded = apply_dev_params(netstruct, paths, combo)
            result_list.append(expanded)

    return result_list


def apply_dev_params(
    netstruct: dict[str, Any], paths: list[tuple], values: tuple
) -> dict[str, Any]:
    """
    Apply one expansion combination to netstruct.

    Priority: topology-set values > inst_params > dev_params
    """
    netstruct_expanded = copy.deepcopy(netstruct)

    # Build parameter lookup dicts from this combination
    tech = None
    dev_defaults = {}  # {dev_type: {param: value}}
    inst_overrides = {}  # {idx: {param: value, "devices": [...]}}

    for path, value in zip(paths, values):
        if path[0] == "tech":
            tech = value
        elif path[0] == "dev_params":
            dev_type, param = path[1], path[2]
            if dev_type not in dev_defaults:
                dev_defaults[dev_type] = {}
            dev_defaults[dev_type][param] = value
        elif path[0] == "inst_params":
            idx, param = path[1], path[2]
            if idx not in inst_overrides:
                # Copy devices list from original inst_params
                orig_inst = netstruct.get("inst_params", [])[idx]
                inst_overrides[idx] = {"devices": orig_inst.get("devices", [])}
            inst_overrides[idx][param] = value

    # Set tech at top level
    if tech is not None:
        netstruct_expanded["tech"] = tech

    # Apply to devices
    devices = netstruct_expanded.get("devices", {})

    # Step 1: Apply dev_params as defaults (lowest priority)
    for dev_name, dev_info in devices.items():
        dev_type = dev_info.get("dev")
        if dev_type and dev_type in dev_defaults:
            if "params" not in dev_info:
                dev_info["params"] = {"dev": dev_type}
            for param, val in dev_defaults[dev_type].items():
                # Only set if not already present
                if param not in dev_info["params"]:
                    dev_info["params"][param] = val

    # Step 2: Apply inst_params overrides (higher priority than dev_params)
    for idx, overrides in inst_overrides.items():
        target_devices = overrides.get("devices", [])
        for dev_name in target_devices:
            if dev_name in devices:
                dev_info = devices[dev_name]
                if "params" not in dev_info:
                    dev_type = dev_info.get("dev")
                    dev_info["params"] = {"dev": dev_type} if dev_type else {}
                for param, val in overrides.items():
                    if param != "devices":
                        # Override dev_params values
                        dev_info["params"][param] = val

    # Clean up intermediate fields
    netstruct_expanded.pop("topo_params", None)
    netstruct_expanded.pop("dev_params", None)
    netstruct_expanded.pop("inst_params", None)

    return netstruct_expanded


def map_technology(
    netstruct: dict[str, Any], techmap: dict[str, Any]
) -> dict[str, Any]:
    """
    Map generic netstruct to technology-specific netlist.

    Reads tech from netstruct["tech"] (top-level field).
    Uses device params.dev ('nmos'/'pmos') + params.type ('lvt'/'svt'/'hvt') to look up devmap.
    """
    tech = netstruct["tech"]
    tech_config = techmap[tech]
    netstruct_techmapped = copy.deepcopy(netstruct)

    for dev_name, dev_info in netstruct_techmapped.get("devices", {}).items():
        params = dev_info.get("params")
        if not params:
            continue

        dev = params.get("dev")
        if not dev:
            continue

        # Combine dev + type for devmap lookup
        # For transistors: nmos_lvt, pmos_svt (dev + type)
        # For caps/res: momcap_1m, polyres (type already includes category)
        if dev in ["nmos", "pmos"] and "type" in params:
            device_key = f"{dev}_{params['type']}"
        elif "type" in params:
            device_key = params["type"]
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
            dev_info["w"] = params["w"] * dev_map["w"]
            dev_info["l"] = params["l"] * dev_map["l"]
            dev_info["nf"] = params.get("nf", 1)

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

    return netstruct_techmapped


def scale_testbench(tb: dict[str, Any], techmap: dict[str, Any]) -> dict[str, Any]:
    """
    Scale voltage and time values in testbench using scalemap.

    Reads tech from tb["tech"].
    """
    tech = tb["tech"]
    tech_config = techmap[tech]
    vdd = tech_config["vdd"]
    tstep = tech_config.get("tstep", 1e-9)

    tb_scaled = copy.deepcopy(tb)

    # Scale voltage sources using scalemap
    for dev_name, dev_info in tb_scaled.get("devices", {}).items():
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
    if "analyses" in tb_scaled:
        for analysis in tb_scaled["analyses"].values():
            if analysis.get("type") == "tran":
                for param in ["stop", "step", "strobeperiod"]:
                    if param in analysis:
                        analysis[param] *= tstep

    return tb_scaled


def autoadd_fields(
    tb: dict[str, Any],
    subckt: dict[str, Any],
    techmap: dict[str, Any],
    file_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Add automatic fields to testbench.

    Reads tech, corner, and temp from top-level fields in tb.

    Args:
        tb: Testbench struct
        subckt: Subcircuit struct (for generating save statements)
        techmap: Technology mapping
        file_ctx: File context with subckt_spice and subckt_children paths

    Returns:
        Testbench with automatic fields added
    """
    tech = tb["tech"]
    corner = tb.get("corner")
    tech_config = techmap[tech]
    tb_autofielded = copy.deepcopy(tb)

    # Add simulator declaration
    tb_autofielded["simulator"] = "lang=spice"

    # Add library statements
    libs = []
    for lib_entry in tech_config.get("libs", []):
        lib_path = lib_entry["path"]
        sections = lib_entry["sections"]

        # Map corner to section
        corner_map = tech_config.get("corners", {})
        section = corner_map.get(corner, sections[0] if sections else "tt_lib")

        libs.append({"path": lib_path, "section": section})

    tb_autofielded["libs"] = libs

    # Add includes from files.json paths
    includes = []
    if file_ctx:
        # Add DUT subcircuit netlist
        if "subckt_spice" in file_ctx:
            includes.append(file_ctx["subckt_spice"])

        # Add child subcircuit netlists (hierarchical dependencies)
        for child in file_ctx.get("subckt_children", []):
            if "child_spice" in child:
                includes.append(child["child_spice"])

    # Merge with any extra_includes from tb template
    if "extra_includes" in tb:
        includes.extend(tb["extra_includes"])

    tb_autofielded["includes"] = includes

    # Add options (temp from top-level field)
    temp = tb["temp"]
    tb_autofielded["options"] = {"temp": temp, "scale": 1.0}

    # Add save statements
    save_stmts = ["all"]

    # Generate device-specific save statements from subcircuit
    if subckt:
        # Find DUT instance name
        dut_instance = None
        for dev_name, dev_info in tb.get("devices", {}).items():
            if dev_info.get("dev") == subckt.get("subckt"):
                dut_instance = dev_name
                break

        if dut_instance:
            # Generate save statements for transistors (devices with params field)
            for dev_name, dev_info in subckt.get("devices", {}).items():
                if "params" in dev_info:
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

    tb_autofielded["save"] = save_stmts

    return tb_autofielded


def generate_spice(netstruct: dict[str, Any], mode: str) -> str:
    """
    Convert netstruct dict to SPICE netlist string.

    Args:
        netstruct: Netstruct dict (subcircuit or testbench)
        mode: 'subckt' or 'tb' (mandatory)

    Returns:
        SPICE netlist string
    """
    lines = []

    if mode == "subckt":
        # Subcircuit mode
        subckt_name = netstruct.get("subckt", "unnamed")
        ports = netstruct.get("ports", {})
        devices = netstruct.get("devices", {})

        # Generate descriptive comment from top-level and meta fields
        param_strs = []

        # Add top-level fields (tech, corner, temp)
        for field in ["tech", "corner", "temp"]:
            if field in netstruct:
                param_strs.append(f"{field}: {netstruct[field]}")

        # Add topo_param values (stored in meta field)
        topo_params_dict = netstruct.get("meta", {})
        for key, value in topo_params_dict.items():
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

        # Write PININFO (feature of CDL netlists: https://en.wikipedia.org/wiki/Circuit_design_language)
        pininfo = " ".join([f"{name}:{dir}" for name, dir in ports.items()])
        lines.append(f"*.PININFO {pininfo}")
        lines.append("")

        # Devices
        for dev_name, dev_info in devices.items():
            model = dev_info.get("model")
            pins = dev_info.get("pins", {})

            # Determine device type from params if available, otherwise from dev field
            dev_type = None
            if "params" in dev_info:
                dev_type = dev_info["params"].get("dev")
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

            # Subcircuit instances (hierarchical)
            elif dev_type == "subckt":
                subckt_ref = dev_info.get("subckt", "unknown")
                pin_list = " ".join(pins.values())
                lines.append(f"{dev_name} {pin_list} {subckt_ref}")

        lines.append("")
        lines.append(f".ends {subckt_name}")
        lines.append("")
        lines.append(".end")

    elif mode == "tb":
        # Testbench mode
        devices = netstruct.get("devices", {})
        analyses = netstruct.get("analyses", {})

        # Simulator declaration
        if "simulator" in netstruct:
            lines.append(f"simulator {netstruct['simulator']}")

        # Library includes
        if "libs" in netstruct:
            for lib in netstruct["libs"]:
                lines.append(f'.lib "{lib["path"]}" {lib["section"]}')

        # Include files
        if "includes" in netstruct:
            for inc in netstruct["includes"]:
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
        if "options" in netstruct:
            opts = netstruct["options"]
            opt_str = " ".join([f"{k}={v}" for k, v in opts.items()])
            lines.append(f".option {opt_str}")

        lines.append("")

        # Save statements
        if "save" in netstruct:
            for save in netstruct["save"]:
                if save == "all":
                    lines.append(".save all")
                else:
                    lines.append(f".save {save}")

    else:
        msg = f"Invalid mode '{mode}'. Expected 'subckt' or 'tb'."
        logging.error(msg)
        raise ValueError(msg)

    return "\n".join(lines) + "\n"


def detect_varying_device_params(
    netstructs: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """
    Detect which device parameters vary across a list of netstructs.

    Args:
        netstructs: List of expanded netstructs with devices

    Returns:
        List of (device_name, param_name) tuples for params that vary
    """
    if not netstructs:
        return []

    # Get all device names that exist in any config
    device_names = set()
    for ns in netstructs:
        device_names.update(ns.get("devices", {}).keys())

    varying_params = []

    # For each device, check which params vary (across configs where device exists)
    for dev_name in sorted(device_names):
        # Get configs where this device exists
        configs_with_device = [
            ns for ns in netstructs if dev_name in ns.get("devices", {})
        ]

        if len(configs_with_device) < 2:
            continue  # Need at least 2 configs to detect variation

        # Get all param names for this device
        param_names = set()
        for ns in configs_with_device:
            dev_params = ns["devices"][dev_name].get("params", {})
            param_names.update(dev_params.keys())

        # Check each param to see if it varies
        for param_name in sorted(param_names):
            if param_name == "dev" or param_name == "type":  # Skip device type fields
                continue

            # Collect all values for this param
            values = set()
            for ns in configs_with_device:
                dev_params = ns["devices"][dev_name].get("params", {})
                if param_name in dev_params:
                    values.add(dev_params[param_name])

            # If more than one unique value, this param varies
            if len(values) > 1:
                varying_params.append((dev_name, param_name))

    return varying_params


def find_matching_topo(
    netstructs: list[dict[str, Any]], netstruct: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Find netstruct with topo_param values matching target netstruct (excluding tech, corner, temp).

    Args:
        netstructs: List of netstructs to search
        netstruct: Target netstruct with topo_param values to match

    Returns:
        Matching netstruct or None if not found
    """
    target_topo_params = netstruct.get("meta", {})
    for candidate in netstructs:
        candidate_topo_params = candidate.get("meta", {})
        # Match on shared keys (excluding tech, corner, temp)
        shared_keys = set(candidate_topo_params.keys()) & set(
            target_topo_params.keys()
        ) - {"tech", "corner", "temp"}
        if all(
            candidate_topo_params.get(k) == target_topo_params.get(k)
            for k in shared_keys
        ):
            return candidate
    return None


def generate_filename(netstruct: dict[str, Any]) -> str:
    """
    Generate base filename for a netlist using topo_param values from meta.

    Returns base name WITHOUT prefix (subckt_/tb_) and WITHOUT extension (.sp/.json).
    Callers add prefix and extension as needed.

    Args:
        netstruct: Netstruct dictionary with 'subckt' or 'testbench' key and tech field

    Returns:
        Base filename string (e.g., 'gate_inv_inv_tsmc65_abc123def456')
    """
    if "subckt" in netstruct:
        base_name = netstruct["subckt"]

        # Tech should be at top level
        if "tech" not in netstruct:
            msg = f"Subckt netstruct '{base_name}' missing required 'tech' field"
            logging.error(msg)
            raise ValueError(msg)

        tech = netstruct["tech"]
        parts = [base_name]

        # Add all topo_param values (stored in meta field, only scalar types)
        topo_params_dict = netstruct.get("meta", {})
        for key, value in topo_params_dict.items():
            if isinstance(value, (int, str, float, bool)):
                parts.append(str(value))

        # Add hash of device parameters to make filename unique
        devices = netstruct.get("devices", {})
        device_params = []
        for dev_name in sorted(devices.keys()):
            dev = devices[dev_name]
            if "params" in dev:
                dev_params = dev["params"]
                # Create a string representation of device parameters
                param_str = f"{dev_name}:"
                for param in sorted(dev_params.keys()):
                    param_str += f"{param}={dev_params[param]},"
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
        if "tech" not in netstruct:
            msg = "Testbench netstruct missing required 'tech' field"
            logging.error(msg)
            raise ValueError(msg)

        tech = netstruct["tech"]
        tb_name = netstruct.get("testbench", "tb_unnamed")
        parts = [tb_name, tech]

        # Add corner and temp if present
        if "corner" in netstruct:
            parts.append(str(netstruct["corner"]))
        if "temp" in netstruct:
            parts.append(str(netstruct["temp"]))

        return "_".join(parts)


# ========================================================================
# Validation/Check Functions
# ========================================================================


def check_subckt(subckt: dict[str, Any]) -> list[str]:
    """
    Check that subcircuit has required fields.

    Required structure:
        - subckt: str (subcircuit name)
        - tech: str (technology)
        - ports: dict (port definitions)
        - devices: dict of dicts (each with pins, params, model)

    Returns:
        List of error messages (empty if no errors)
    """
    errors = []

    if "subckt" not in subckt:
        errors.append("Subcircuit missing required 'subckt' field")

    if "tech" not in subckt:
        errors.append("Subcircuit missing required 'tech' field")

    if "ports" not in subckt or not isinstance(subckt["ports"], dict):
        errors.append("Subcircuit missing required 'ports' dict")

    if "devices" not in subckt or not isinstance(subckt["devices"], dict):
        errors.append("Subcircuit missing required 'devices' dict")

    return errors


def check_testbench(tb: dict[str, Any]) -> list[str]:
    """
    Check that testbench has required fields.

    Required structure:
        - testbench: str (testbench name)
        - tech: str (technology)
        - corner: str (process corner)
        - temp: int/float (temperature)
        - devices: dict (device definitions)
        - analyses: dict (analysis definitions)
        - libs: list (library includes)

    Returns:
        List of error messages (empty if no errors)
    """
    errors = []

    if "tech" not in tb:
        errors.append("Testbench missing required 'tech' field")

    if "corner" not in tb:
        errors.append("Testbench missing required 'corner' field")

    if "temp" not in tb:
        errors.append("Testbench missing required 'temp' field")

    if "devices" not in tb or not isinstance(tb["devices"], dict):
        errors.append("Testbench missing required 'devices' dict")

    if "analyses" not in tb or not isinstance(tb["analyses"], dict):
        errors.append("Testbench missing required 'analyses' dict")

    if "libs" not in tb or not tb["libs"]:
        errors.append("Testbench missing required 'libs' field")

    return errors


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
            # SUBCIRCUIT MODE (new merged struct flow)
            # ================================================================

            # 1. Create results dir and empty files list
            subckt_dir = args.output / cell_name / "subckt"
            subckt_dir.mkdir(parents=True, exist_ok=True)
            files: list[dict] = []

            # 2. Get merged subckt struct from circuit module
            subckt_template = circuit_module.subckt

            # 3. Stage 1: Expand topo_params, fill ports/devices
            generate_topology_fn = getattr(circuit_module, "generate_topology", None)
            subckts_stage1 = expand_topo_params(subckt_template, generate_topology_fn)

            # 4. Stage 2: Expand tech, inst_params, dev_params
            subckts_expanded = expand_dev_params(subckts_stage1)

            # 5. Detect varying device parameters for table columns
            varying_params = detect_varying_device_params(subckts_expanded)

            # 6. Process each expanded subcircuit
            total_count = 0
            all_errors = []
            for subckt in subckts_expanded:
                # 7. Map to technology (convert generic to PDK-specific)
                subckt = map_technology(subckt, techmap)

                # 8. Run checks
                errors = check_subckt(subckt)
                if errors:
                    cfgname = generate_filename(subckt)
                    all_errors.append((cfgname, errors))

                # Print table header on first iteration
                if total_count == 0:
                    headers, col_widths = calc_table_columns(subckt, varying_params)
                    print_table_header(headers, col_widths)

                # 8. Create file_ctx with cellname and cfgname
                cfgname = generate_filename(subckt)
                file_ctx = {
                    "cellname": cell_name,
                    "cfgname": cfgname,
                    "subckt_json": None,
                    "subckt_spice": None,
                    "subckt_children": [],
                    "tb_json": [],
                    "tb_spice": [],
                    "sim_raw": [],
                    "meas_db": None,
                    "plot_img": [],
                }

                # 9. Write JSON struct
                json_path = subckt_dir / f"{cfgname}.json"
                json_path.write_text(compact_json(subckt))
                file_ctx["subckt_json"] = f"subckt/{cfgname}.json"

                # 10. Write SPICE netlist
                sp_path = subckt_dir / f"{cfgname}.sp"
                spice_str = generate_spice(subckt, mode=args.mode)
                sp_path.write_text(spice_str)
                file_ctx["subckt_spice"] = f"subckt/{cfgname}.sp"

                # 11. Append file_ctx to files list
                files.append(file_ctx)
                total_count += 1

                # Print table row
                # Build row data from top-level, meta, and device params
                row_data = {}
                for field in ["tech", "corner", "temp"]:
                    if field in subckt:
                        row_data[field] = subckt[field]
                row_data.update(subckt.get("meta", {}))
                # Add varying device params
                for dev_name, param_name in varying_params:
                    col_name = f"{dev_name}.{param_name}"
                    devices = subckt.get("devices", {})
                    if dev_name in devices:
                        dev_params = devices[dev_name].get("params", {})
                        if param_name in dev_params:
                            row_data[col_name] = dev_params[param_name]
                        else:
                            row_data[col_name] = "-"
                    else:
                        row_data[col_name] = "-"
                print_table_row(row_data, headers, col_widths)

            # 12. Write files.json and print summary
            files_db_path = args.output / cell_name / "files.json"
            save_files_list(files_db_path, files)
            logger.info("-" * 80)
            logger.info(f"Result: {total_count} subcircuits generated")

            # Print collected errors/warnings
            if all_errors:
                for cfgname, errors in all_errors:
                    for error in errors:
                        logger.error(f"{cfgname}: {error}")

            logger.info("-" * 80)

        elif args.mode == "tb":
            # ================================================================
            # TESTBENCH MODE (new merged struct flow)
            # ================================================================

            # 1. Load existing files.json (created by subckt mode)
            files_db_path = args.output / cell_name / "files.json"
            files = load_files_list(files_db_path)
            if not files:
                msg = f"No files.json found at {files_db_path}. Run subckt mode first."
                logger.error(msg)
                raise ValueError(msg)

            tb_dir = args.output / cell_name / "tb"
            tb_dir.mkdir(parents=True, exist_ok=True)

            # 2. Get merged tb struct from circuit module
            tb_template = circuit_module.tb

            # 3. Stage 1: Expand topo_params, fill ports/devices
            generate_topology_fn = getattr(circuit_module, "generate_tb_topology", None)
            tbs_stage1 = expand_topo_params(tb_template, generate_topology_fn)

            # 4. Get corner and temp lists from template
            corner_list = tb_template.get("corner", ["tt"])
            temp_list = tb_template.get("temp", [27])
            corner_list = (
                corner_list if isinstance(corner_list, list) else [corner_list]
            )
            temp_list = temp_list if isinstance(temp_list, list) else [temp_list]

            total_count = 0
            all_errors = []

            # 5. Loop over each subckt entry in files
            for file_ctx in files:
                # 6. Load the subckt struct from subckt_json path
                subckt_path = args.output / cell_name / file_ctx["subckt_json"]
                with open(subckt_path) as f:
                    subckt = json.load(f)

                # 7. Find matching tb netstruct based on topo_param values in subckt.meta
                tb_topo = find_matching_topo(tbs_stage1, subckt)
                if not tb_topo:
                    logger.warning(
                        f"No matching testbench netstruct for {file_ctx['cfgname']}"
                    )
                    continue

                # 8. Loop over corner × temp combinations
                for corner, temp in itertools.product(corner_list, temp_list):
                    # 9. Create testbench struct with tech from subckt, corner/temp from tb
                    tb = copy.deepcopy(tb_topo)
                    tb["tech"] = subckt["tech"]  # Inherit tech from subckt
                    tb["corner"] = corner
                    tb["temp"] = temp

                    # 10. Map to technology
                    tb = map_technology(tb, techmap)

                    # 11. Scale testbench values
                    tb = scale_testbench(tb, techmap)

                    # 12. Add auto fields (libs, includes, options, save)
                    tb = autoadd_fields(tb, subckt, techmap, file_ctx)

                    # 13. Run checks
                    errors = check_testbench(tb)
                    if errors:
                        cfgname = file_ctx["cfgname"]
                        tb_filename = f"{cfgname}_{corner}_{temp}"
                        all_errors.append((tb_filename, errors))

                    # Print table header on first iteration
                    if total_count == 0:
                        # Use full tb struct for column calculation
                        headers, col_widths = calc_table_columns(tb)
                        print_table_header(headers, col_widths)

                    # 14. Generate filename and write JSON
                    cfgname = file_ctx["cfgname"]
                    tb_filename = f"{cfgname}_{corner}_{temp}"

                    json_path = tb_dir / f"{tb_filename}.json"
                    json_path.write_text(compact_json(tb))
                    file_ctx["tb_json"].append(f"tb/{tb_filename}.json")

                    # 15. Write SPICE netlist
                    sp_path = tb_dir / f"{tb_filename}.sp"
                    spice_str = generate_spice(tb, mode=args.mode)
                    sp_path.write_text(spice_str)
                    file_ctx["tb_spice"].append(f"tb/{tb_filename}.sp")

                    total_count += 1

                    # Print table row
                    # Build row data from top-level and meta fields
                    row_data = {}
                    for field in ["tech", "corner", "temp"]:
                        if field in tb:
                            row_data[field] = tb[field]
                    row_data.update(tb.get("meta", {}))
                    print_table_row(row_data, headers, col_widths)

            # 16. Write updated files.json
            save_files_list(files_db_path, files)
            logger.info("-" * 80)
            logger.info(f"Result: {total_count} testbenches generated")

            # Print collected errors/warnings
            if all_errors:
                for tb_filename, errors in all_errors:
                    for error in errors:
                        logger.error(f"{tb_filename}: {error}")

            logger.info("-" * 80)

    except Exception as e:
        logging.error(f"\nGeneration failed: {e}")
        raise


if __name__ == "__main__":
    main()
