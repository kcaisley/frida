"""
Consistent naming utilities for netlists and test artifacts.

Provides functions to generate filenames from parameter objects and
to extract parameter axes for summary tables.
"""

import hashlib
from enum import Enum
from typing import Any, Callable

import hdl21 as h
import hdl21.sim as hs
from vlsirtools.netlist import netlist as write_pkg_netlist
from vlsirtools.spice import SupportedSimulators


def generate_staircase_pwl(
    v_start: float,
    v_stop: float,
    v_step: float,
    t_step: float,
    t_rise: float,
    t_delay: float = 0.0,
) -> list[tuple[float, float]]:
    """
    Generate staircase PWL points for ADC transfer function tests.

    Each step holds for t_step duration, then ramps over t_rise to the next
    level. This is quasi-static, matching physical measurement conditions.
    """
    points: list[tuple[float, float]] = []
    n_steps = int(abs(v_stop - v_start) / v_step) + 1
    t = t_delay
    sign = 1 if v_stop >= v_start else -1

    for i in range(n_steps):
        v = v_start + sign * i * v_step
        points.append((t, v))
        t += t_step
        if i < n_steps - 1:
            points.append((t, v))
            t += t_rise

    return points


def pwl_points_to_wave(points: list[tuple[float, float]]) -> str:
    """Format PWL points as a waveform string for `Vpwl(wave=...)`."""
    return " ".join(f"{t:.12e} {v:.6e}" for t, v in points)


def pwl_to_spice_literal(
    name: str,
    p_node: str,
    n_node: str,
    points: list[tuple[float, float]],
) -> str:
    """
    Generate SPICE PWL source literal string.

    Args:
        name: Source name (e.g., "vin")
        p_node: Positive node name
        n_node: Negative node name
        points: List of (time, voltage) tuples

    Returns:
        SPICE PWL source string
    """
    pwl_str = pwl_points_to_wave(points)
    return f"V{name} {p_node} {n_node} PWL({pwl_str})"


def params_to_filename(
    block: str,
    params: Any,
    pdk_name: str,
    suffix: str = ".sp",
) -> str:
    """
    Generate consistent filename from parameters.

    Uses lowercase parameter values separated by underscores.
    Includes PDK name at the end.

    Args:
        block: Block name (e.g., "comp", "cdac", "samp")
        params: HDL21 paramclass instance (e.g., CompParams, CdacParams)
        pdk_name: PDK name (e.g., "ihp130", "tsmc65")
        suffix: File extension (default: ".sp")

    Returns:
        Filename string like "comp_nmos_input_std_bias_w40_l1_ihp130.sp"

    Example:
        >>> from flow.comp.comp import CompParams
        >>> params = CompParams(diffpair_w=40)
        >>> params_to_filename("comp", params, "ihp130")
        'comp_nmos_input_std_bias_single_stage_clocked_external_clocked_clocked_w40_l1_low_w20_l2_std_w20_low_w20_low_ihp130.sp'
    """
    parts = [block.lower()]

    # Extract parameter values from the paramclass
    param_values = _extract_param_values(params)

    for value in param_values:
        parts.append(_format_value(value))

    parts.append(pdk_name.lower())

    return "_".join(parts) + suffix


def get_param_axes(params_list: list[Any]) -> dict[str, list[Any]]:
    """
    Extract parameter axes from a list of param objects.

    Returns dict mapping param names to list of unique values found.
    Used for building summary tables.

    Args:
        params_list: List of HDL21 paramclass instances

    Returns:
        Dict like {"preamp_diffpair": [NMOS_INPUT, PMOS_INPUT], "diffpair_w": [40, 80]}
    """
    if not params_list:
        return {}

    # Get param names from first instance
    first = params_list[0]
    param_names = _get_param_names(first)

    # Collect unique values for each param
    axes: dict[str, list[Any]] = {name: [] for name in param_names}

    for params in params_list:
        for name in param_names:
            value = getattr(params, name, None)
            if value not in axes[name]:
                axes[name].append(value)

    return axes


def select_variants(variants: list[Any], mode: str, limit: int = 10) -> list[Any]:
    """
    Select variants based on mode.

    Args:
        variants: Full list of variants
        mode: "min" to limit, "max" to keep all
        limit: Max number of variants for "min"
    """
    if mode == "min":
        return variants[:limit]
    if mode == "max":
        return variants
    raise ValueError(f"Unsupported mode: {mode}")


def run_netlist_variants(
    block: str,
    variants: list[Any],
    build_sim: Callable[[Any], tuple[h.Module, hs.Sim]],
    pdk: Any,
    outdir: Any,
    return_sims: bool = False,
    simulator: SupportedSimulators = SupportedSimulators.SPECTRE,
    netlist_fmt: str | None = None,
    build_dut: Callable[[Any], h.Module] | None = None,
) -> float | tuple[float, list[hs.Sim]]:
    """
    Write netlists for a list of variants.

    Args:
        block: Block name (e.g., "comp", "cdac", "samp")
        variants: List of parameter objects
        build_sim: Callable returning (tb, sim) for a variant
        pdk: Active PDK instance
        outdir: Output directory path
        return_sims: Return list of sims in addition to wall time
        netlist_fmt: DUT-only netlist format override for netlist flow:
            "spectre", "ngspice", "yaml", or "verilog".
            When None, uses legacy sim-input netlist path (tb + sim cards).
        build_dut: Callable returning DUT module for DUT-only formats

    Returns:
        Wall time in seconds, and optionally list of sims
    """
    import time

    from .sim import write_sim_netlist

    start = time.perf_counter()

    sims: list[hs.Sim] = []
    if netlist_fmt is None:
        for params in variants:
            tb, sim = build_sim(params)
            pdk.compile(tb)

            suffix = ".scs" if simulator == SupportedSimulators.SPECTRE else ".sp"
            filename = params_to_filename(block, params, pdk.name, suffix=suffix)
            netlist_path = outdir / filename
            write_sim_netlist(sim, netlist_path, compact=True, simulator=simulator)
            if return_sims:
                sims.append(sim)
    else:
        if return_sims:
            raise ValueError("return_sims is invalid for DUT-only netlist formats")
        if build_dut is None:
            raise ValueError("build_dut is required for DUT-only netlist formats")

        fmt = netlist_fmt.lower()
        if fmt == "spice":
            fmt = "ngspice"
        suffix_by_fmt = {
            "spectre": ".scs",
            "ngspice": ".sp",
            "yaml": ".yaml",
            "verilog": ".v",
        }
        if fmt not in suffix_by_fmt:
            raise ValueError(f"Unsupported netlist format: {netlist_fmt}")
        suffix = suffix_by_fmt[fmt]
        for params in variants:
            dut = build_dut(params)
            pdk.compile(dut)
            filename = params_to_filename(block, params, pdk.name, suffix=suffix)
            netlist_path = outdir / filename
            pkg = h.to_proto(dut)
            with open(netlist_path, "w") as f:
                write_pkg_netlist(pkg=pkg, dest=f, fmt=fmt)

    wall_time = time.perf_counter() - start
    if return_sims:
        return wall_time, sims
    return wall_time


def wrap_monte_carlo(sim: hs.Sim, mc_config: Any | None = None) -> hs.Sim:
    """
    Wrap transient analysis in Monte Carlo.

    Args:
        sim: HDL21 Sim object
        mc_config: MCConfig instance (default uses MCConfig())
    """
    from .sim import MCConfig

    if mc_config is None:
        mc_config = MCConfig()

    for attr in sim.attrs:
        if isinstance(attr, hs.MonteCarlo):
            return sim

    tran = next((attr for attr in sim.attrs if isinstance(attr, hs.Tran)), None)
    if tran is None:
        raise ValueError("No transient analysis found in simulation")

    sim.add(hs.MonteCarlo(inner=[tran], npts=mc_config.numruns, seed=mc_config.seed))
    return sim


def print_netlist_summary(
    block: str,
    pdk_name: str,
    count: int,
    param_axes: dict[str, list[Any]],
    wall_time: float,
    outdir: str,
    errors: list[str] | None = None,
) -> None:
    """
    Print formatted summary table for netlist generation.

    Args:
        block: Block name (e.g., "comp", "cdac", "samp")
        pdk_name: PDK name
        count: Number of netlists generated
        param_axes: Dict from get_param_axes()
        wall_time: Generation time in seconds
        outdir: Output directory path
        errors: List of error messages (or None/empty for no errors)
    """
    width = 80

    # Info section
    print()
    print("Flow:       netlist")
    print(f"Block:      {block}")
    print(f"Tech:       {pdk_name}")
    print(f"OutDir:     {outdir}")
    print("-" * width)

    # Build parameter table
    if param_axes:
        # Calculate column widths
        min_col_width = 12
        headers = list(param_axes.keys())
        col_widths = {}
        for header in headers:
            value_count = len(param_axes[header])
            value_str = f"{value_count}x"
            col_widths[header] = max(min_col_width, len(header), len(value_str))

        # Print header row
        header_line = " ".join(f"{h:<{col_widths[h]}}" for h in headers)
        print(header_line)
        print("-" * width)

        # Print value counts row
        value_line = " ".join(
            f"{len(param_axes[h])}x".ljust(col_widths[h]) for h in headers
        )
        print(value_line)
        print("-" * width)

    # Results section
    print(f"Result:      {count} netlists generated")
    print(f"Wall Time:   {wall_time * 1000:.1f}ms")

    if errors:
        print(f"Errors:      {len(errors)} errors")
        for err in errors[:5]:  # Show first 5 errors
            print(f"             - {err}")
        if len(errors) > 5:
            print(f"             ... and {len(errors) - 5} more")
    else:
        print("Errors:      [none]")

    print()


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _extract_param_values(params: Any) -> list[Any]:
    """Extract parameter values from an HDL21 paramclass instance."""
    values = []
    param_names = _get_param_names(params)

    for name in param_names:
        value = getattr(params, name, None)
        values.append(value)

    return values


def _get_param_names(params: Any) -> list[str]:
    """Get parameter names from an HDL21 paramclass instance."""
    # HDL21 paramclasses store params in __params__ class attribute
    if hasattr(params.__class__, "__params__"):
        return list(params.__class__.__params__.keys())

    # Fallback: look for Param descriptors
    param_names = []
    for name in dir(params.__class__):
        if not name.startswith("_"):
            attr = getattr(params.__class__, name, None)
            if isinstance(attr, h.Param):
                param_names.append(name)

    return param_names


def _format_value(value: Any) -> str:
    """Format a parameter value for use in a filename."""
    if hasattr(value.__class__, "__params__"):
        raw = str(value).encode("utf-8")
        digest = hashlib.md5(raw).hexdigest()[:8]
        return f"{value.__class__.__name__.lower()}_{digest}"
    if isinstance(value, Enum):
        # Use name (e.g., NMOS_INPUT) converted to lowercase
        return value.name.lower()
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    elif value is None:
        return "none"
    else:
        # Convert to string and make filename-safe
        s = str(value).lower()
        # Handle hdl21.Prefixed values (like "1 f" or "1*femto")
        # Check for SI prefix patterns and format nicely
        if hasattr(value, "number") and hasattr(value, "prefix"):
            # It's an hdl21.Prefixed value
            num = value.number
            prefix = (
                value.prefix.name.lower()
                if hasattr(value.prefix, "name")
                else str(value.prefix)
            )
            return f"{num}{prefix}"
        # Replace spaces and special chars with underscores
        for char in " .-/\\:*()[]{}":
            s = s.replace(char, "_")
        # Remove consecutive underscores
        while "__" in s:
            s = s.replace("__", "_")
        return s.strip("_")
