#!/usr/bin/env python3
"""
Generate technology-specific testbench wrappers for SPICE simulations.

This script generates testbench wrapper files that instantiate:
1. PDK model includes (with appropriate sections/corners)
2. DUT netlist includes
3. Verilog-A testbench includes
4. Testbench instantiation
5. Simulation commands (.tran, .options, .save)

Each DUT netlist gets its own testbench wrapper in the results directory.
"""

import argparse
import datetime
import logging
import re
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple


def parse_verilog_a_testbench(va_file: Path) -> Tuple[str, float, List[str]]:
    """
    Parse a Verilog-A testbench file to extract key simulation parameters.

    Args:
        va_file: Path to the Verilog-A testbench file

    Returns:
        Tuple of (module_name, duration_seconds, compilation_targets)

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If required information cannot be extracted
    """
    if not va_file.exists():
        raise FileNotFoundError(f"Verilog-A file not found: {va_file}")

    content = va_file.read_text()

    # Extract module name
    match = re.search(r'^\s*module\s+(\w+)\s*;', content, re.MULTILINE)
    if not match:
        raise ValueError(f"No module declaration found in {va_file}")
    module_name = match.group(1)

    # Parse parameters
    parameters = {}
    pattern = r'parameter\s+(?:real|integer)\s+(\w+)\s*=\s*([\d.eE+-]+[a-zA-Z]*)'
    for match in re.finditer(pattern, content):
        param_name = match.group(1)
        param_value_str = match.group(2)
        parameters[param_name] = _parse_value_with_units(param_value_str)

    # Calculate simulation duration
    # Strategy 1: Look for explicit time calculation in comments
    time_match = re.search(
        r'Total simulation time:.*?=\s*([\d.]+)\s*([µumkMGT]?)s',
        content,
        re.IGNORECASE
    )
    if time_match:
        value = float(time_match.group(1))
        unit = time_match.group(2)
        unit_map = {'µ': 1e-6, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12}
        multiplier = unit_map.get(unit, 1.0)
        duration = value * multiplier
    # Strategy 2: Calculate from parameters
    elif 'NVCM' in parameters and 'NVDIFF' in parameters and 'NPULSES' in parameters and 'TCLK' in parameters:
        duration = parameters['NVCM'] * parameters['NVDIFF'] * parameters['NPULSES'] * parameters['TCLK']
    elif 'DC_SWEEP_STEPS' in parameters and 'NPULSES' in parameters and 'TCLK' in parameters:
        duration = (parameters['DC_SWEEP_STEPS'] + parameters['NPULSES']) * parameters['TCLK']
    elif 'NPULSES' in parameters and 'TCLK' in parameters:
        duration = parameters['NPULSES'] * parameters['TCLK']
    else:
        raise ValueError(
            f"Cannot determine simulation duration from {va_file}. "
            f"Parameters found: {list(parameters.keys())}"
        )

    # Extract compilation targets
    targets = []
    for match in re.finditer(r'`(?:ifdef|elsif)\s+(\w+)', content):
        target = match.group(1)
        if target not in targets:
            targets.append(target)

    return module_name, duration, targets


def _parse_value_with_units(value_str: str) -> float:
    """
    Parse a value string with optional SI unit suffix.

    Args:
        value_str: String like "100n", "1.2e-9", "25", "1e-12"

    Returns:
        Floating point value in base units
    """
    units = {
        'T': 1e12, 'G': 1e9, 'M': 1e6,
        'k': 1e3, 'K': 1e3,
        'm': 1e-3, 'u': 1e-6, 'µ': 1e-6,
        'n': 1e-9, 'p': 1e-12, 'f': 1e-15,
        'a': 1e-18
    }

    match = re.match(r'^([\d.eE+-]+)([a-zA-Z]*)$', value_str)
    if not match:
        return 0.0

    numeric_part = float(match.group(1))
    unit_part = match.group(2)

    if unit_part and unit_part in units:
        return numeric_part * units[unit_part]
    else:
        return numeric_part


def load_toml_config(config_path: Path) -> Dict:
    """Load TOML configuration file."""
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


def extract_tech_from_netlist(netlist_path: Path, tech_config: Dict) -> str:
    """
    Extract technology name from netlist filename.

    Args:
        netlist_path: Path to DUT netlist (e.g., samp_tgate_tsmc65_MN-MP-w40-l2.sp)
        tech_config: Technology configuration dict

    Returns:
        Technology name (e.g., 'tsmc65', 'tsmc28', 'tower180')

    Raises:
        ValueError: If no matching technology is found
    """
    stem = netlist_path.stem
    parts = stem.split('_')

    # Look for technology name in the filename
    for part in parts:
        if part in tech_config:
            return part

    raise ValueError(f"Cannot determine technology from netlist: {netlist_path}")


def generate_testbench_wrapper(
    dut_netlist: Path,
    va_testbench: Path,
    tech: str,
    tech_config: Dict,
    corner: str,
    output_dir: Path
) -> Path:
    """
    Generate a testbench wrapper for a specific DUT netlist.

    Args:
        dut_netlist: Path to the DUT netlist (e.g., samp_tgate_tsmc65_MN-MP-w40-l2.sp)
        va_testbench: Path to the Verilog-A testbench file
        tech: Technology name (e.g., 'tsmc65')
        tech_config: Technology configuration dictionary
        corner: Process corner (e.g., 'tt', 'ss', 'ff')
        output_dir: Directory to write the testbench wrapper

    Returns:
        Path to generated testbench wrapper file
    """
    # Parse Verilog-A testbench to get module name and duration
    module_name, duration, _ = parse_verilog_a_testbench(va_testbench)

    # Create output filename: tb_<dut_netlist_name>.sp
    output_file = output_dir / f"tb_{dut_netlist.stem}.sp"

    # Get libs list and corner mapping
    libs = tech_config.get('libs', [])
    corners = tech_config.get('corners', {})

    # Map the user-specified corner (e.g., 'tt') to the library section name (e.g., 'tt_lib')
    corner_section = corners.get(corner, corner)  # Use corner name if not in mapping

    # Build .lib statements for each library
    lib_statements = []
    for lib_path, lib_sections in libs:
        # Find the matching section in this library's section list
        if corner_section in lib_sections:
            lib_statements.append(f'.lib "{lib_path}" {corner_section}')
        else:
            # Use the first section as default if corner not found
            default_section = lib_sections[0] if lib_sections else corner_section
            lib_statements.append(f'.lib "{lib_path}" {default_section}')

    # Join all lib statements with newlines
    lib_includes = '\n'.join(lib_statements)

    # Calculate simulation time
    def format_time(t):
        if t >= 1e-3:
            return f"{t*1e3:.3g}m"
        elif t >= 1e-6:
            return f"{t*1e6:.3g}u"
        elif t >= 1e-9:
            return f"{t*1e9:.3g}n"
        elif t >= 1e-12:
            return f"{t*1e12:.3g}p"
        else:
            return f"{t:.3g}"

    timestep = min(duration / 10000, 1e-9)
    timestep_str = format_time(timestep)
    duration_str = format_time(duration)

    # Construct relative path to Verilog-A testbench
    # Output is in results/<family_cell>/, so we need to go up two levels
    va_relative = Path("../../") / va_testbench

    # Build the testbench content
    content = f"""* ========================================================================
* Testbench Wrapper
* ========================================================================
* Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
* DUT:       {dut_netlist.name}
* Testbench: {va_testbench.name}
* Tech:      {tech}
* Corner:    {corner} -> {corner_section}
* ========================================================================

simulator lang=spice
{lib_includes}
.include "{dut_netlist.name}"
.ahdl_include "{va_relative}"

* Instantiate the testbench
xtb {module_name}

.tran {timestep_str} {duration_str}
.option temp=27 scale=1.0
.save all

"""

    # Write the file
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content)

    return output_file


def main():
    """Main entry point for testbench generation."""
    parser = argparse.ArgumentParser(
        description='Generate technology-specific testbench wrappers for SPICE simulations.',
        epilog='Example: %(prog)s -n results/samp_tgate/*.sp -v ahdl/tb_samp.va -c tech/tech.toml'
    )
    parser.add_argument(
        '-n', '--netlists',
        type=str,
        required=True,
        help='Glob pattern for DUT netlists (e.g., "results/samp_tgate/*.sp")'
    )
    parser.add_argument(
        '-v', '--verilog-a',
        type=Path,
        required=True,
        metavar='FILE',
        help='Verilog-A testbench file (e.g., ahdl/tb_samp.va)'
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        required=True,
        metavar='FILE',
        help='Technology configuration file (e.g., tech/tech.toml)'
    )
    parser.add_argument(
        '--corner',
        type=str,
        default='tt',
        help='Process corner to use (default: tt)'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    logger = logging.getLogger(__name__)

    # Validate Verilog-A testbench
    if not args.verilog_a.exists():
        logger.error(f"Verilog-A testbench not found: {args.verilog_a}")
        return 1

    # Load technology configuration
    tech_config = load_toml_config(args.config)
    logger.debug(f"Loaded technology config from {args.config}")

    # Find all DUT netlists
    from glob import glob
    netlist_files = [Path(f) for f in glob(args.netlists)]

    if not netlist_files:
        logger.error(f"No netlist files found matching: {args.netlists}")
        return 1

    # Sort for consistent ordering
    netlist_files.sort()

    logger.info(f"Generating testbench wrappers for {len(netlist_files)} DUT netlists")
    logger.info(f"Verilog-A testbench: {args.verilog_a}")
    logger.info(f"Corner: {args.corner}")
    logger.info("")

    # Parse Verilog-A testbench once to show info
    try:
        module_name, duration, targets = parse_verilog_a_testbench(args.verilog_a)
        logger.info(f"Testbench module: {module_name}")
        logger.info(f"Simulation duration: {duration*1e6:.2f} µs")
        if targets:
            logger.info(f"Compilation targets: {', '.join(targets)}")
        logger.info("")
    except Exception as e:
        logger.error(f"Failed to parse Verilog-A testbench: {e}")
        return 1

    # Group netlists by technology
    netlists_by_tech: Dict[str, List[Path]] = {}
    for netlist in netlist_files:
        try:
            tech = extract_tech_from_netlist(netlist, tech_config)
            if tech not in netlists_by_tech:
                netlists_by_tech[tech] = []
            netlists_by_tech[tech].append(netlist)
        except ValueError as e:
            logger.warning(f"Skipping {netlist.name}: {e}")

    # Generate testbenches per technology
    total_generated = 0

    for tech, netlists in sorted(netlists_by_tech.items()):
        logger.info(f"Technology: {tech}")

        if tech not in tech_config:
            logger.warning(f"  Technology '{tech}' not found in config, skipping")
            continue

        tech_cfg = tech_config[tech]

        for netlist in netlists:
            output_dir = netlist.parent

            try:
                generate_testbench_wrapper(
                    dut_netlist=netlist,
                    va_testbench=args.verilog_a,
                    tech=tech,
                    tech_config=tech_cfg,
                    corner=args.corner,
                    output_dir=output_dir
                )
                total_generated += 1
            except Exception as e:
                logger.error(f"  Failed to generate testbench for {netlist.name}: {e}")

        logger.info(f"  {len(netlists)} testbenches")

    logger.info(f"\n✓ {total_generated} testbenches generated")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
