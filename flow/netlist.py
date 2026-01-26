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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
    setup_logging,
    techmap,
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
        "-o", "--output", type=Path, required=True, help="Base output directory"
    )
    parser.add_argument(
        "--subckt-dir", type=Path, default=None, help="Subcircuit output directory (default: <output>/<cell>/subckt)"
    )
    parser.add_argument(
        "--tb-dir", type=Path, default=None, help="Testbench output directory (default: <output>/<cell>/tb)"
    )
    parser.add_argument(
        "--log-dir", type=Path, default=Path("logs"), help="Log directory"
    )

    args = parser.parse_args()

    # Setup logging with log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cell_name = args.circuit.stem
    args.log_dir.mkdir(exist_ok=True)
    log_file = args.log_dir / f"{args.mode}_{cell_name}_{timestamp}.log"
    setup_logging(log_file)

    # Set default directories if not specified
    if args.subckt_dir is None:
        args.subckt_dir = args.output / cell_name / "subckt"
    if args.tb_dir is None:
        args.tb_dir = args.output / cell_name / "tb"

    print_flow_header(
        cell=cell_name,
        flow=args.mode,
        script_file=args.circuit,
        outdir=args.subckt_dir if args.mode == "subckt" else args.tb_dir,
        log_file=log_file,
    )

    try:
        # Load circuit module
        circuit_module = load_cell_script(args.circuit)

        if args.mode == "subckt":
            # ================================================================
            # SUBCIRCUIT MODE (unified expand_params flow)
            # ================================================================

            # 1. Create results dir and empty files dict
            args.subckt_dir.mkdir(parents=True, exist_ok=True)
            files: dict[str, dict[str, Any]] = {}

            # 2. Get subckt template from circuit module
            subckt_template = circuit_module.subckt
            generate_fn = getattr(circuit_module, "gen_topo_subckt", None)

            # 3. Unified expansion flow
            subckts = expand_params(subckt_template, mode="topo_params")
            subckts = generate_topology(subckts, generate_fn)

            subckts = expand_params(subckts, mode="inst_params")
            subckts = apply_inst_params(subckts)

            subckts = expand_params(subckts, mode="tech_params")

            # 4. Detect varying instance params for table columns
            varying_params = detect_varying_inst_params(subckts)

            # 5. Process each expanded subcircuit
            total_count = 0
            all_errors = []
            headers: list[str] = []
            col_widths: dict[str, int] = {}
            for subckt in subckts:
                # 6. Map to technology, convert generic to PDK-specific
                subckt = map_technology(subckt, techmap)

                # 7. Check subcircuit
                errors = check_subckt(subckt)
                if errors:
                    cfgname = generate_filename(subckt)
                    all_errors.append((cfgname, errors))

                # Print table header on first iteration
                if total_count == 0:
                    headers, col_widths = calc_table_columns(subckt, varying_params)
                    print_table_header(headers, col_widths)

                # 8. Compute config hash and create file_ctx
                topo_params = subckt.get("topo_params", {})
                inst_params = subckt.get("inst_params", [])
                tech = subckt["tech"]

                config_hash = compute_params_hash(topo_params, inst_params, tech)
                cfgname = generate_filename(subckt)

                file_ctx = {
                    "cellname": cell_name,
                    "cfgname": cfgname,
                    "subckt_json": None,
                    "subckt_spice": None,
                    "subckt_children": {},
                    "tb_json": [],
                    "tb_spice": [],
                    "sim_raw": [],
                    "meas_db": None,
                    "plot_img": [],
                }

                # 9. Write JSON struct
                json_path = args.subckt_dir / f"{cfgname}.json"
                json_path.write_text(compact_json(subckt))
                file_ctx["subckt_json"] = f"subckt/{cfgname}.json"

                # 10. Write SPICE netlist
                sp_path = args.subckt_dir / f"{cfgname}.sp"
                spice_str = generate_spice(subckt, mode=args.mode)
                sp_path.write_text(spice_str)
                file_ctx["subckt_spice"] = f"subckt/{cfgname}.sp"

                # 11. Resolve child subcircuit dependencies
                child_deps = resolve_child_deps(subckt, args.output)
                file_ctx["subckt_children"] = child_deps

                # 12. Add file_ctx to files dict with config_hash as key
                files[config_hash] = file_ctx
                total_count += 1

                # Print table row
                # Build row data from top-level, topo_params, and instance params
                row_data = {}
                for field in ["tech", "corner", "temp"]:
                    if field in subckt:
                        row_data[field] = subckt[field]
                row_data.update(subckt.get("topo_params", {}))
                # Add varying instance params
                for inst_name, param_name in varying_params:
                    col_name = f"{inst_name}.{param_name}"
                    instances = subckt.get("instances", {})
                    if inst_name in instances:
                        inst_params_dict = instances[inst_name].get("params", {})
                        if param_name in inst_params_dict:
                            row_data[col_name] = inst_params_dict[param_name]
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
            # TESTBENCH MODE (unified expand_params flow)
            # ================================================================

            # 1. Load existing files.json (created by subckt mode)
            files_db_path = args.output / cell_name / "files.json"
            files = load_files_list(files_db_path)
            if not files:
                msg = f"No files.json found at {files_db_path}. Run subckt mode first."
                logger.error(msg)
                raise ValueError(msg)

            args.tb_dir.mkdir(parents=True, exist_ok=True)

            # 2. Get tb template from circuit module
            tb_template = circuit_module.tb
            generate_fn = getattr(circuit_module, "gen_topo_tb", None)

            # 3. Expand topo_params, fill ports/instances
            tbs_stage1 = expand_params(tb_template, mode="topo_params")
            tbs_stage1 = generate_topology(tbs_stage1, generate_fn)

            # 4. Get corner and temp lists from template
            # TODO: I don't like the defaults here.
            corner_list = tb_template.get("corner", ["tt"])
            temp_list = tb_template.get("temp", [27])
            corner_list = (
                corner_list if isinstance(corner_list, list) else [corner_list]
            )
            temp_list = temp_list if isinstance(temp_list, list) else [temp_list]

            total_count = 0
            all_errors = []
            headers = []
            col_widths = {}

            # 5. Loop over each subckt entry in files dict
            for config_hash, file_ctx in files.items():
                # Clear tb lists to avoid duplicates on re-runs
                file_ctx["tb_json"] = []
                file_ctx["tb_spice"] = []

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
                # TODO: we should extends the expand_params function, and use that to get
                # the cartesian product of corners and temps, instead of doing it manually!
                for corner, temp in itertools.product(corner_list, temp_list):
                    # 9. Create testbench struct with tech from subckt, corner/temp from tb
                    tb = copy.deepcopy(tb_topo)
                    tb["tech"] = subckt["tech"]  # Inherit tech from subckt
                    tb["corner"] = corner
                    tb["temp"] = temp

                    # 10. Expand declarative vsource params to concrete values
                    tb = generate_v_i_source_values(tb)

                    # 11. Map to technology (includes vsource scaling)
                    tb = map_technology(tb, techmap)

                    # 12. Add auto fields (libs, includes, options, save)
                    # TODO: Auto add fields shouldn't add save statement, as these are provided
                    # by the
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

                    json_path = args.tb_dir / f"{tb_filename}.json"
                    json_path.write_text(compact_json(tb))
                    file_ctx["tb_json"].append(f"tb/{tb_filename}.json")

                    # 15. Write SPICE netlist
                    sp_path = args.tb_dir / f"{tb_filename}.sp"
                    spice_str = generate_spice(tb, mode=args.mode)
                    sp_path.write_text(spice_str)
                    file_ctx["tb_spice"].append(f"tb/{tb_filename}.sp")

                    total_count += 1

                    # Print table row
                    # Build row data from top-level and topo_params fields
                    row_data = {}
                    for field in ["tech", "corner", "temp"]:
                        if field in tb:
                            row_data[field] = tb[field]
                    row_data.update(tb.get("topo_params", {}))
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


@dataclass
class ParamAxis:
    """A single sweepable parameter axis with its location."""

    path: tuple[str | int, ...]  # e.g., ("inst_params", 0) or ("inst_params", 2, "inst_params", 0)
    key: str  # e.g., "w", "l", "type"
    values: list[Any]  # e.g., [1, 2, 4]


def set_nested(obj: Any, path: tuple[str | int, ...], key: str, value: Any) -> None:
    """Set a nested value in a dict using a path tuple and final key."""
    current: Any = obj
    for p in path:
        current = current[p]
    current[key] = value


def compute_params_hash(
    topo_params: dict[str, Any],
    inst_params: list[dict[str, Any]],
    tech: str,
) -> str:
    """
    Compute SHA256 hash of config params for unique identification.

    Order: topo_params, inst_params, tech
    Returns: 12-char hex string
    """
    parts = [
        json.dumps(topo_params, sort_keys=True),
        json.dumps(inst_params, sort_keys=True),
        tech,
    ]
    combined = "|".join(parts)
    hash_obj = hashlib.sha256(combined.encode())
    return hash_obj.hexdigest()[:12]


def discover_param_axes(
    netstruct: dict[str, Any],
    mode: str,
    path_prefix: tuple[str | int, ...] = (),
) -> list[ParamAxis]:
    """Recursively discover all sweepable params for the given mode."""
    axes = []

    if mode == "topo_params":
        # Direct topo_params at this level
        for key, val in netstruct.get("topo_params", {}).items():
            if isinstance(val, list):
                axes.append(ParamAxis(path_prefix + ("topo_params",), key, val))

        # Child topo_params in inst_params entries (for subcells)
        for idx, inst_spec in enumerate(netstruct.get("inst_params", [])):
            if isinstance(inst_spec, dict) and "topo_params" in inst_spec:
                # This targets subcells - recurse into child topo_params
                for key, val in inst_spec.get("topo_params", {}).items():
                    if isinstance(val, list):
                        axes.append(
                            ParamAxis(
                                path_prefix + ("inst_params", idx, "topo_params"),
                                key,
                                val,
                            )
                        )

    elif mode == "inst_params":
        for idx, inst_spec in enumerate(netstruct.get("inst_params", [])):
            if not isinstance(inst_spec, dict):
                continue

            # Check if this targets subcells (has nested topo_params or inst_params)
            is_subcell_spec = any(k in inst_spec for k in ("topo_params", "inst_params"))

            if is_subcell_spec:
                # Recurse into nested inst_params for subcell lookup params
                nested_inst_params = inst_spec.get("inst_params", [])
                for nested_idx, nested_spec in enumerate(nested_inst_params):
                    if not isinstance(nested_spec, dict):
                        continue
                    for key, val in nested_spec.items():
                        if key == "instances":
                            continue
                        if isinstance(val, list):
                            axes.append(
                                ParamAxis(
                                    path_prefix
                                    + ("inst_params", idx, "inst_params", nested_idx),
                                    key,
                                    val,
                                )
                            )
            else:
                # Regular instance params (for primitives)
                for key, val in inst_spec.items():
                    if key == "instances":
                        continue
                    if isinstance(val, list):
                        axes.append(
                            ParamAxis(
                                path_prefix + ("inst_params", idx),
                                key,
                                val,
                            )
                        )

    elif mode == "tech_params":
        tech = netstruct.get("tech")
        if isinstance(tech, list):
            axes.append(ParamAxis(path_prefix, "tech", tech))

    return axes


def expand_params(
    netstructs: list[dict[str, Any]] | dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    """Unified parameter expansion with nested child support."""
    if isinstance(netstructs, dict):
        netstructs = [netstructs]

    result_list = []
    for netstruct in netstructs:
        axes = discover_param_axes(netstruct, mode)

        if not axes:
            result_list.append(copy.deepcopy(netstruct))
            continue

        value_lists = [axis.values for axis in axes]
        for combo in itertools.product(*value_lists):
            result = copy.deepcopy(netstruct)
            for i, axis in enumerate(axes):
                set_nested(result, axis.path, axis.key, combo[i])
            result_list.append(result)

    return result_list


def generate_topology(
    netstructs: list[dict[str, Any]],
    generate_fn: Callable[..., tuple[dict[str, str], dict[str, Any]] | tuple[None, None]] | None = None,
) -> list[dict[str, Any]]:
    """
    Fill ports/instances by calling generate_fn with scalar topo_params.
    Only operates on parent level.
    """
    if generate_fn is None:
        return netstructs

    result_list = []
    for netstruct in netstructs:
        # Skip if instances already filled
        if netstruct.get("instances"):
            result_list.append(netstruct)
            continue

        topo_params = netstruct.get("topo_params", {})
        ports, instances = generate_fn(**topo_params)

        # Skip invalid combinations (generate_fn returns None, None)
        if ports is None or instances is None:
            continue

        result = copy.deepcopy(netstruct)
        result["ports"] = ports
        result["instances"] = instances
        result_list.append(result)

    return result_list


def apply_inst_params(netstructs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply inst_params to parent's primitive instances only.

    Rules:
    - Later entries override earlier entries
    - Specific selectors (list) override "all" selectors
    - Entries with topo_params/inst_params target subcells (skipped here, used for lookup)
    """
    result_list = []
    for netstruct in netstructs:
        result = copy.deepcopy(netstruct)
        instances = result.get("instances", {})
        inst_params = result.get("inst_params", [])

        # Build index: instance_name -> dev_type (or cell_type)
        inst_to_type: dict[str, str] = {}
        for inst_name, inst_info in instances.items():
            if "dev" in inst_info:
                inst_to_type[inst_name] = inst_info["dev"]
            elif "cell" in inst_info:
                inst_to_type[inst_name] = inst_info["cell"]

        # Process inst_params in order (later overrides earlier)
        for inst_spec in inst_params:
            if not isinstance(inst_spec, dict):
                continue

            # Skip subcell specs (used for lookup, not application)
            if any(k in inst_spec for k in ("topo_params", "inst_params")):
                continue

            selector = inst_spec.get("instances", {})

            # Find matching instances
            matched_instances = []
            for dev_type, targets in selector.items():
                if targets == "all":
                    # All instances of this type
                    matched_instances.extend(
                        name for name, typ in inst_to_type.items() if typ == dev_type
                    )
                elif isinstance(targets, list):
                    # Specific instances
                    matched_instances.extend(
                        name for name in targets if name in instances
                    )

            # Apply params to matched instances
            for inst_name in matched_instances:
                inst_info = instances[inst_name]
                if "params" not in inst_info:
                    inst_info["params"] = {}

                for param, val in inst_spec.items():
                    if param == "instances":
                        continue
                    inst_info["params"][param] = val

        result_list.append(result)
    return result_list


def resolve_child_deps(
    subckt: dict[str, Any],
    results_dir: Path,
) -> dict[str, dict[str, str]]:
    """
    Resolve child subcircuit dependencies for a parent subckt.

    Computes child config hashes directly from:
    - Parent's tech (inherited by children)
    - Child topo_params from instance definition (set by generate_topology)
    - Child inst_params from parent's inst_params targeting that child

    Then looks up the hash in the child's files.json - no need to load child JSONs.

    Args:
        subckt: Parent subcircuit netstruct (fully expanded, single config)
        results_dir: Base results directory (e.g., Path("results"))

    Returns:
        Dict mapping child config_hash to {"child_cellname", "child_json", "child_spice"}
    """
    children: dict[str, dict[str, str]] = {}
    parent_tech = subckt.get("tech")
    if not parent_tech:
        return children

    instances = subckt.get("instances", {})
    parent_inst_params = subckt.get("inst_params", [])

    # Collect child cells and their topo_params from instance definitions
    # cell_name -> {"inst_names": [...], "topo_params": {...}, "inst_params": [...]}
    child_cells: dict[str, dict[str, Any]] = {}
    for inst_name, inst_info in instances.items():
        if "cell" in inst_info:
            cell_name = inst_info["cell"]
            if cell_name not in child_cells:
                child_cells[cell_name] = {"inst_names": [], "topo_params": {}, "inst_params": []}
            child_cells[cell_name]["inst_names"].append(inst_name)
            # Merge topo_params from instance definition (set by generate_topology)
            if "topo_params" in inst_info:
                child_cells[cell_name]["topo_params"].update(inst_info["topo_params"])

    # Extract child topo_params and inst_params from parent's inst_params
    for inst_spec in parent_inst_params:
        if not isinstance(inst_spec, dict):
            continue

        selector = inst_spec.get("instances", {})

        for cell_name, cell_info in child_cells.items():
            inst_names = cell_info["inst_names"]
            targets_child = False

            for dev_type, targets in selector.items():
                if dev_type == cell_name:
                    targets_child = True
                    break
                if isinstance(targets, list):
                    for target in targets:
                        if target in inst_names:
                            targets_child = True
                            break

            if not targets_child:
                continue

            # Extract child topo_params if present
            if "topo_params" in inst_spec:
                cell_info["topo_params"].update(inst_spec["topo_params"])

            # Extract child inst_params if present
            if "inst_params" in inst_spec:
                cell_info["inst_params"].extend(inst_spec["inst_params"])

    # For each child cell, compute hash and look up in files.json
    for cell_name, cell_info in child_cells.items():
        child_files_path = results_dir / cell_name / "files.json"
        if not child_files_path.exists():
            logging.warning(f"Child files.json not found: {child_files_path}")
            continue

        child_files = load_files_list(child_files_path)
        if not child_files:
            continue

        # Compute child's config hash directly
        child_topo_params = cell_info["topo_params"]
        child_inst_params = cell_info["inst_params"]
        child_hash = compute_params_hash(child_topo_params, child_inst_params, parent_tech)

        # Look up in child's files.json
        if child_hash in child_files:
            entry = child_files[child_hash]
            children[child_hash] = {
                "child_cellname": cell_name,
                "child_json": f"{cell_name}/{entry['subckt_json']}",
                "child_spice": f"{cell_name}/{entry['subckt_spice']}",
            }
        else:
            logging.warning(
                f"Child {cell_name} hash {child_hash} not found "
                f"(topo_params={child_topo_params}, inst_params={child_inst_params})"
            )

    return children


# ========================================================================
# Voltage/Current Source Value Generation
# ========================================================================


def _expand_step_pwl(params: dict[str, Any]) -> list[float]:
    """
    Generate staircase PWL points from params (normalized units).

    Each step holds voltage for tstep duration, then ramps over trise to next level.

    Args:
        params: Dict with vstart, vstep/vstop, count, tstep, td, trise

    Returns:
        Points array [t0, v0, t1, v1, ...] in normalized units
    """
    vstart = params.get("vstart", 0)
    tstep = params["tstep"]
    td = params.get("td", 0)
    trise = params.get("trise", 1e-12)  # Default to 1ps if not specified

    # Resolve count/vstep/vstop (handle overconstrained)
    vstep = params.get("vstep")
    vstop = params.get("vstop")
    count: int | None = params.get("count")

    if vstep is not None and count is not None:
        # Mode A: vstart + vstep + count
        pass  # vstep and count already set
    elif vstop is not None and count is not None:
        # Mode B: vstart + vstop + count
        vstep = (vstop - vstart) / (count - 1) if count > 1 else 0
    else:
        raise ValueError("PWL step requires (vstep + count) or (vstop + count)")

    # After validation, count and vstep are guaranteed to be set
    assert count is not None
    assert vstep is not None

    points: list[float] = []
    t = td
    for i in range(count):
        v = vstart + i * vstep
        points.extend([t, v])
        t += tstep
        if i < count - 1:
            points.extend([t, v])  # hold before next step
            t += trise  # rise time to next voltage level

    return points


def _expand_ramp_pwl(params: dict[str, Any]) -> list[float]:
    """
    Generate linear ramp PWL points from params (normalized units).

    Args:
        params: Dict with vstart, vstop, tstep (total ramp time), td

    Returns:
        Points array [t0, v0, t1, v1, ...] in normalized units
    """
    vstart = params.get("vstart", 0)
    vstop = params["vstop"]
    tstep = params["tstep"]  # total ramp time
    td = params.get("td", 0)

    points = []
    if td > 0:
        points.extend([0, vstart, td, vstart])
    points.extend([td, vstart, td + tstep, vstop])

    return points


def generate_v_i_source_values(netstruct: dict[str, Any]) -> dict[str, Any]:
    """
    Expand declarative vsource params to concrete values.

    For PWL sources with params dict containing type="step" or type="ramp",
    generates the "points" list. Called BEFORE map_technology() - values
    are still in normalized units.

    Args:
        netstruct: Netlist structure (typically testbench)

    Returns:
        Netlist with PWL params expanded to points arrays
    """
    result = copy.deepcopy(netstruct)

    for inst_name, inst_info in result.get("instances", {}).items():
        if inst_info.get("dev") != "vsource":
            continue
        if inst_info.get("wave") != "pwl":
            continue
        if "points" in inst_info:  # explicit points already exist, skip
            continue

        params = inst_info.get("params")
        if not params:
            continue

        pwl_type = params.get("type")
        if pwl_type is None:
            continue  # No type specified, assume explicit points will be added

        if pwl_type == "step":
            points = _expand_step_pwl(params)
        elif pwl_type == "ramp":
            points = _expand_ramp_pwl(params)
        else:
            raise ValueError(f"{inst_name}: Unknown PWL type '{pwl_type}'. Expected 'step' or 'ramp'.")

        # Store points in params (will be moved to top-level by map_technology)
        params["points"] = points

    return result


def map_technology(
    netstruct: dict[str, Any], techmap: dict[str, Any]
) -> dict[str, Any]:
    """
    Map generic netstruct to technology-specific netlist.

    Reads tech from netstruct["tech"] (top-level field).
    For transistors/caps/res: uses params.dev + params.type to look up devmap.
    For vsources: scales voltage and time parameters using vdd and tstep.
    """
    tech = netstruct["tech"]
    tech_config = techmap[tech]
    vdd = tech_config["vdd"]
    tstep = tech_config.get("tstep", 1e-9)
    netstruct_techmapped = copy.deepcopy(netstruct)

    for inst_name, inst_info in netstruct_techmapped.get("instances", {}).items():
        # Device type is stored directly on inst_info
        dev = inst_info.get("dev")
        if not dev:
            continue

        # Handle voltage/current sources - scale by vdd and tstep
        if dev == "vsource":
            wave = inst_info.get("wave")
            params = inst_info.get("params", {})

            if wave == "dc":
                # DC voltage: scale by vdd
                dc_val = params.get("dc", inst_info.get("dc", 0))
                inst_info["dc"] = dc_val * vdd

            elif wave == "pwl":
                # PWL: scale points (alternating time/voltage)
                points = params.get("points", inst_info.get("points", []))
                inst_info["points"] = [
                    val * (tstep if i % 2 == 0 else vdd)
                    for i, val in enumerate(points)
                ]
                # Scale optional r (repeat) and td (delay)
                r_val = params.get("r", inst_info.get("r"))
                if r_val is not None and r_val >= 0:
                    inst_info["r"] = r_val * tstep
                td_val = params.get("td", inst_info.get("td"))
                if td_val is not None and td_val > 0:
                    inst_info["td"] = td_val * tstep

            elif wave == "pulse":
                # Pulse: scale voltages by vdd, times by tstep
                inst_info["v1"] = params.get("v1", inst_info.get("v1", 0)) * vdd
                inst_info["v2"] = params.get("v2", inst_info.get("v2", 1)) * vdd
                inst_info["td"] = params.get("td", inst_info.get("td", 0)) * tstep
                inst_info["tr"] = params.get("tr", inst_info.get("tr", 0.01)) * tstep
                inst_info["tf"] = params.get("tf", inst_info.get("tf", 0.01)) * tstep
                inst_info["pw"] = params.get("pw", inst_info.get("pw", 0.5)) * tstep
                inst_info["per"] = params.get("per", inst_info.get("per", 1)) * tstep

            elif wave == "sine":
                # Sine: scale voltages by vdd, delay by tstep, freq stays in Hz
                inst_info["dc"] = params.get("dc", inst_info.get("dc", 0.5)) * vdd
                inst_info["ampl"] = params.get("ampl", inst_info.get("ampl", 0.5)) * vdd
                inst_info["freq"] = params.get("freq", inst_info.get("freq", 1e6))
                inst_info["delay"] = params.get("delay", inst_info.get("delay", 0)) * tstep

            # Remove params dict (consumed)
            if "params" in inst_info:
                del inst_info["params"]

            continue  # Skip devmap lookup for vsources

        # For devices requiring devmap lookup (transistors, caps, res)
        params = inst_info.get("params")
        if not params:
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

        # Save device type in params for generate_spice(), then remove from inst_info
        params["dev"] = dev
        if "dev" in inst_info:
            del inst_info["dev"]

        # Map transistors
        if dev in ["nmos", "pmos"]:
            inst_info["model"] = dev_map["model"]
            inst_info["w"] = params["w"] * dev_map["w"]
            inst_info["l"] = params["l"] * dev_map["l"]
            inst_info["nf"] = params.get("nf", 1)

        # Map capacitors
        elif dev == "cap":
            inst_info["model"] = dev_map["model"]
            # Keep c and m from instance definition for SPICE generation

        # Map resistors
        elif dev == "res":
            inst_info["model"] = dev_map["model"]
            # Keep r from instance definition for SPICE generation
            if "rsh" in dev_map:
                inst_info["rsh"] = dev_map["rsh"]

    return netstruct_techmapped


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

        # If lib has a fixed "section", use that (not corner-dependent)
        # Otherwise, map corner to section using the "sections" list
        if "section" in lib_entry:
            section = lib_entry["section"]
        else:
            sections = lib_entry.get("sections", [])
            corner_map = tech_config.get("corners", {})
            section = corner_map.get(corner, sections[0] if sections else "tt_lib")

        libs.append({"path": lib_path, "section": section})

    tb_autofielded["libs"] = libs

    # Add includes from files.json paths
    # Paths in files.json are relative to cell_dir (e.g., "subckt/foo.sp")
    # Testbenches are in tb/ so includes need "../" prefix to reach siblings
    includes = []
    if file_ctx:
        # Add DUT subcircuit netlist
        if "subckt_spice" in file_ctx:
            includes.append("../" + file_ctx["subckt_spice"])

        # Add child subcircuit netlists (hierarchical dependencies)
        for child in file_ctx.get("subckt_children", []):
            if "child_spice" in child:
                includes.append("../" + child["child_spice"])

    # Merge with any extra_includes from tb template
    if "extra_includes" in tb:
        includes.extend(tb["extra_includes"])

    tb_autofielded["includes"] = includes

    # Add options (temp from top-level field)
    temp = tb["temp"]
    tb_autofielded["options"] = {"temp": temp, "scale": 1.0}

    # Note: save statements are NOT added here - they are provided at the PyOPUS
    # simulation level, same as analyses. This keeps the testbench generation
    # focused on circuit topology and stimulus only.

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
        subckt_name = netstruct.get("cellname", "unnamed")
        ports = netstruct.get("ports", {})
        instances = netstruct.get("instances", {})

        # Generate descriptive comment from top-level and topo_params fields
        param_strs = []

        # Add top-level fields (tech, corner, temp)
        for field in ["tech", "corner", "temp"]:
            if field in netstruct:
                param_strs.append(f"{field}: {netstruct[field]}")

        # Add topo_param values
        topo_params_dict = netstruct.get("topo_params", {})
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

        # Instances
        for inst_name, inst_info in instances.items():
            pins = inst_info.get("pins", {})

            # Case 1: Subcircuit instance (child cell) - identified by "cell" key
            if "cell" in inst_info:
                cell_ref = inst_info["cell"]
                pin_list = " ".join(pins.values())
                lines.append(f"{inst_name} {pin_list} {cell_ref}")
                continue

            # Case 2: Primitive device - identified by "dev" key
            # Device type may be in params.dev (after map_technology) or inst_info.dev
            dev_type = None
            if "params" in inst_info:
                dev_type = inst_info["params"].get("dev")
            if not dev_type:
                dev_type = inst_info.get("dev")

            if not dev_type:
                # Skip instances without device type
                continue

            # Get params dict (nested under 'params' key after apply_inst_params)
            params = inst_info.get("params", {})
            model = inst_info.get("model")

            # Transistors (nmos, pmos)
            if dev_type in ["nmos", "pmos"]:
                pin_list = " ".join(pins.get(p, "0") for p in ["d", "g", "s", "b"])
                line = f"{inst_name} {pin_list} {model}"
                line += f" W={format_value(params['w'])}"
                line += f" L={format_value(params['l'])}"
                line += f" nf={params.get('nf', 1)}"
                lines.append(line)

            # Capacitors
            elif dev_type == "cap":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                c = params.get("c", 1)  # Unitless capacitance value
                m = params.get("m", 1)  # Multiplier
                cap_model = inst_info.get("model", "capacitor")
                lines.append(f"{inst_name} {p} {n} {cap_model} c={c} m={m}")

            # Resistors
            elif dev_type == "res":
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                r = params.get("r", 4)  # Resistance multiplier
                res_model = inst_info.get("model", "resistor")
                lines.append(f"{inst_name} {p} {n} {res_model} r={r}")

        lines.append("")
        lines.append(f".ends {subckt_name}")
        lines.append("")
        lines.append(".end")

    elif mode == "tb":
        # Testbench mode
        instances = netstruct.get("instances", {})
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

        # Instances
        for inst_name, inst_info in instances.items():
            # Check for "cell" (subcircuit instance) first
            if "cell" in inst_info:
                cell_ref = inst_info["cell"]
                pins = inst_info.get("pins", {})
                pin_list = " ".join([pins[p] for p in pins.keys()])
                lines.append(f"{inst_name} {pin_list} {cell_ref}")
                continue

            dev = inst_info.get("dev")

            if dev == "vsource":
                # Voltage source
                pins = inst_info.get("pins", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                wave = inst_info.get("wave", "dc")

                line = f"{inst_name} {p} {n}"

                if wave == "dc":
                    dc_val = inst_info.get("dc", 0)
                    line += f" DC {format_value(dc_val, 'V')}"

                elif wave == "pwl":
                    points = inst_info.get("points", [])
                    # Spectre PWL uses bare SI prefixes without unit suffixes
                    pwl_str = " ".join([format_value(v, "") for v in points])
                    line += f" PWL({pwl_str})"

                elif wave == "sine":
                    dc = format_value(inst_info.get("dc", 0), "V")
                    ampl = format_value(inst_info.get("ampl", 0), "V")
                    freq = format_value(inst_info.get("freq", 1e6), "Hz")
                    delay = format_value(inst_info.get("delay", 0), "s")
                    line += f" SIN({dc} {ampl} {freq} {delay})"

                elif wave == "pulse":
                    v1 = format_value(inst_info.get("v1", 0), "V")
                    v2 = format_value(inst_info.get("v2", 1), "V")
                    td = format_value(inst_info.get("td", 0), "s")
                    tr = format_value(inst_info.get("tr", 0), "s")
                    tf = format_value(inst_info.get("tf", 0), "s")
                    pw = format_value(inst_info.get("pw", 1e-9), "s")
                    per = format_value(inst_info.get("per", 2e-9), "s")
                    line += f" PULSE({v1} {v2} {td} {tr} {tf} {pw} {per})"

                lines.append(line)

            elif dev == "res":
                pins = inst_info.get("pins", {})
                params = inst_info.get("params", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                r = params.get("r", 1000)
                lines.append(f"{inst_name} {p} {n} {format_value(r, 'Ohm')}")

            elif dev == "cap":
                pins = inst_info.get("pins", {})
                params = inst_info.get("params", {})
                p = pins.get("p", "p")
                n = pins.get("n", "n")
                c = params.get("c", 1e-12)
                lines.append(f"{inst_name} {p} {n} {format_value(c, 'F')}")

            else:
                # Subcircuit instance (backwards compatibility via "dev" field)
                pins = inst_info.get("pins", {})
                pin_list = " ".join([pins[p] for p in pins.keys()])
                lines.append(f"{inst_name} {pin_list} {dev}")

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

        # Note: save statements are NOT generated here - they are provided at
        # the PyOPUS simulation level, same as analyses.

    else:
        msg = f"Invalid mode '{mode}'. Expected 'subckt' or 'tb'."
        logging.error(msg)
        raise ValueError(msg)

    return "\n".join(lines) + "\n"


def detect_varying_inst_params(
    netstructs: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """
    Detect which instance parameters vary across a list of netstructs.

    Args:
        netstructs: List of expanded netstructs with instances

    Returns:
        List of (instance_name, param_name) tuples for params that vary
    """
    if not netstructs:
        return []

    # Get all instance names that exist in any config
    inst_names = set()
    for ns in netstructs:
        inst_names.update(ns.get("instances", {}).keys())

    varying_params = []

    # For each instance, check which params vary (across configs where instance exists)
    for inst_name in sorted(inst_names):
        # Get configs where this instance exists
        configs_with_inst = [
            ns for ns in netstructs if inst_name in ns.get("instances", {})
        ]

        if len(configs_with_inst) < 2:
            continue  # Need at least 2 configs to detect variation

        # Get all param names for this instance
        param_names = set()
        for ns in configs_with_inst:
            inst_params = ns["instances"][inst_name].get("params", {})
            param_names.update(inst_params.keys())

        # Check each param to see if it varies
        for param_name in sorted(param_names):
            if param_name == "dev" or param_name == "type":  # Skip device type fields
                continue

            # Collect all values for this param
            values = set()
            for ns in configs_with_inst:
                inst_params = ns["instances"][inst_name].get("params", {})
                if param_name in inst_params:
                    values.add(inst_params[param_name])

            # If more than one unique value, this param varies
            if len(values) > 1:
                varying_params.append((inst_name, param_name))

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
    target_topo_params = netstruct.get("topo_params", {})
    for candidate in netstructs:
        candidate_topo_params = candidate.get("topo_params", {})
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
    Generate base filename for a netlist using topo_param values and config hash.

    Returns base name WITHOUT prefix (subckt_/tb_) and WITHOUT extension (.sp/.json).
    Callers add prefix and extension as needed.

    Args:
        netstruct: Netstruct dictionary with 'cellname' and tech field

    Returns:
        Base filename string (e.g., 'samp_tgate_tsmc65_abc123def456')
    """
    if "cellname" in netstruct:
        base_name = netstruct["cellname"]

        # Tech should be at top level
        if "tech" not in netstruct:
            msg = f"Subckt netstruct '{base_name}' missing required 'tech' field"
            logging.error(msg)
            raise ValueError(msg)

        tech = netstruct["tech"]
        parts = [base_name]

        # Add all topo_param values (only scalar types)
        topo_params = netstruct.get("topo_params", {})
        for key, value in topo_params.items():
            if isinstance(value, (int, str, float, bool)):
                parts.append(str(value))

        parts.append(tech)

        # Add config hash
        config_hash = compute_params_hash(
            topo_params,
            netstruct.get("inst_params", []),
            tech,
        )
        parts.append(config_hash)

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
        - cellname: str (subcircuit name)
        - tech: str (technology)
        - ports: dict (port definitions)
        - instances: dict of dicts (each with pins, params, model)

    Returns:
        List of error messages (empty if no errors)
    """
    errors = []

    if "cellname" not in subckt:
        errors.append("Subcircuit missing required 'cellname' field")

    if "tech" not in subckt:
        errors.append("Subcircuit missing required 'tech' field")

    if "ports" not in subckt or not isinstance(subckt["ports"], dict):
        errors.append("Subcircuit missing required 'ports' dict")

    if "instances" not in subckt or not isinstance(subckt["instances"], dict):
        errors.append("Subcircuit missing required 'instances' dict")

    return errors


def check_testbench(tb: dict[str, Any]) -> list[str]:
    """
    Check that testbench has required fields.

    Required structure:
        - tech: str (technology)
        - corner: str (process corner)
        - temp: int/float (temperature)
        - instances: dict (instance definitions)
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

    if "instances" not in tb or not isinstance(tb["instances"], dict):
        errors.append("Testbench missing required 'instances' dict")

    # Note: 'analyses' is no longer required in tb dict - it's defined separately
    # in the cell module per PyOPUS migration

    if "libs" not in tb or not tb["libs"]:
        errors.append("Testbench missing required 'libs' field")

    return errors

if __name__ == "__main__":
    main()
