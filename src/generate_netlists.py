#!/usr/bin/env python3
"""
Generate SPICE netlist variants from template and configuration.

This script reads a template netlist, applies parameter sweeps from a config file,
and generates multiple netlist variants for different technologies and device parameters.
"""

import argparse
import itertools
import tomllib
from pathlib import Path
from typing import Dict, List, Any

from spicelib import SpiceEditor


def load_toml_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from TOML file."""
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


def get_device_type(device_name: str) -> str:
    """Extract device type (nmos/pmos) from device name."""
    if device_name.upper().startswith('MN'):
        return 'nmos'
    elif device_name.upper().startswith('MP'):
        return 'pmos'
    else:
        raise ValueError(f"Cannot determine device type for {device_name}")


def get_default_params(device_name: str, comp_config: Dict[str, Any]) -> Dict[str, Any]:
    """Get default parameters for a device based on its type."""
    device_type = get_device_type(device_name)
    defaults = comp_config['defaults'][device_type]
    return {
        'w': defaults['w'][0],  # Take first (only) value from defaults
        'l': defaults['l'][0],
        'nf': defaults['nf'][0],
        'type': defaults['type'][0],
    }


def summarize_varying_params(comp_config: Dict[str, Any]) -> str:
    """Return a summary of which parameters are being varied in sweep groups."""
    if 'sweeps' not in comp_config or not comp_config['sweeps']:
        return "No parameter sweeps defined"

    param_list = []
    for sweep in comp_config['sweeps']:
        devices = sweep['devices']
        varying = []

        # Check which parameters are being swept
        for param in ['w', 'l', 'nf', 'type']:
            if param in sweep and len(sweep[param]) > 1:
                varying.append(param.upper())

        if devices and varying:
            device_str = ', '.join(devices)
            param_str = ', '.join(varying)
            if len(devices) > 1:
                param_list.append(f"[{device_str}] ({param_str})")
            else:
                param_list.append(f"{device_str} ({param_str})")

    return '; '.join(param_list) if param_list else "No variations"


def generate_param_combinations(devices: List[str], comp_config: Dict[str, Any]) -> List[Dict[str, Dict[str, Any]]]:
    """
    Generate all combinations of device parameters from sweep groups.

    Returns a list of configurations, where each config is a dict mapping
    device_name -> {w: val, l: val, nf: val, type: val}

    Each sweep generates its own Cartesian product, then all sweeps are
    combined via Cartesian product to get final configurations.
    """
    if 'sweeps' not in comp_config or not comp_config['sweeps']:
        # No sweeps defined, use defaults for all devices
        config = {}
        for device in devices:
            config[device] = get_default_params(device, comp_config)
        return [config]

    # Generate combinations for each sweep group
    sweep_combinations = []

    for sweep in comp_config['sweeps']:
        sweep_devices = sweep['devices']

        # Get parameter lists for this sweep
        param_lists = []
        param_names = []
        for param in ['w', 'l', 'nf', 'type']:
            if param in sweep:
                param_lists.append(sweep[param])
                param_names.append(param)

        # Generate all combinations for this sweep
        sweep_combos = []
        for combo in itertools.product(*param_lists):
            # Create param dict for this combination
            params = dict(zip(param_names, combo))

            # Fill in any missing parameters with defaults
            example_device = sweep_devices[0]
            defaults = get_default_params(example_device, comp_config)
            for param in ['w', 'l', 'nf', 'type']:
                if param not in params:
                    params[param] = defaults[param]

            # Apply same params to all devices in this sweep
            sweep_config = {}
            for device in sweep_devices:
                sweep_config[device] = params.copy()

            sweep_combos.append(sweep_config)

        sweep_combinations.append(sweep_combos)

    # Combine all sweep groups via Cartesian product
    all_configurations = []
    for combo in itertools.product(*sweep_combinations):
        # Merge all sweep configs
        config = {}
        for sweep_config in combo:
            config.update(sweep_config)

        # Add defaults for devices not in any sweep
        for device in devices:
            if device not in config:
                config[device] = get_default_params(device, comp_config)

        all_configurations.append(config)

    return all_configurations


def calculate_dimension(multiplier: int, base_value: float) -> float:
    """Calculate actual dimension from multiplier and base value."""
    return multiplier * base_value


def get_model_name(device_type: str, vt_type: str, tech_config: Dict[str, Any]) -> str:
    """Get the PDK-specific model name for a device."""
    key = f"{device_type}_{vt_type}"
    return tech_config['device_models'][key]


def format_dimension(value: float) -> str:
    """Format dimension value for SPICE netlist (e.g., 240e-9 or 240n)."""
    # Use engineering notation with appropriate suffix
    if value >= 1e-6:
        return f"{value*1e6:.6g}u"
    elif value >= 1e-9:
        return f"{value*1e9:.6g}n"
    elif value >= 1e-12:
        return f"{value*1e12:.6g}p"
    else:
        return f"{value:.6e}"


def generate_netlist_name(tech: str, param_config: Dict[str, Dict[str, Any]],
                          comp_config: Dict[str, Any], template_path: Path) -> str:
    """
    Generate a human-readable filename from parameter configuration.

    Format: comp_doubletail_tsmc65_MNtail1-w2-l4_MNinp-MNinn-w2-typelvt.sp
    - Devices separated by _
    - For grouped devices: list all devices, then their shared params
    - Parameters: paramname + value (no dash), separated by -
    """
    base_name = template_path.stem
    segments = [base_name, tech]

    if 'sweeps' in comp_config and comp_config['sweeps']:
        # Process each sweep group
        for sweep in comp_config['sweeps']:
            sweep_devices = sweep['devices']
            if not sweep_devices:
                continue

            # Build device segment
            device_part = '-'.join(sweep_devices)

            # Build parameter segment (only non-default varying params)
            param_parts = []
            for param in ['w', 'l', 'nf', 'type']:
                if param in sweep and len(sweep[param]) > 1:
                    # This param is being swept
                    # Get value from first device (all have same value in group)
                    first_device = sweep_devices[0]
                    value = param_config[first_device][param]

                    # Format: param + value (no separator)
                    # e.g., w2, l4, typelvt
                    param_parts.append(f"{param}{value}")

            # Combine device and params with dashes
            if param_parts:
                sweep_segment = device_part + '-' + '-'.join(param_parts)
            else:
                sweep_segment = device_part

            segments.append(sweep_segment)

    return '_'.join(segments) + '.sp'


def apply_config_to_netlist(editor: SpiceEditor, subckt_name: str,
                            param_config: Dict[str, Dict[str, Any]],
                            tech: str, tech_config: Dict[str, Any]) -> None:
    """
    Apply parameter configuration to a netlist using SpiceEditor.

    Args:
        editor: SpiceEditor instance with loaded template
        subckt_name: Name of the subcircuit containing the devices
        param_config: Dict mapping device_name -> {w, l, nf, type}
        tech: Technology name (e.g., 'tsmc65')
        tech_config: Technology-specific configuration from TOML
    """
    base_w = tech_config['base_dimensions']['w']
    base_l = tech_config['base_dimensions']['l']

    # Get the subcircuit
    subckt = editor.get_subcircuit_named(subckt_name)

    for device_name, params in param_config.items():
        device_type = get_device_type(device_name)

        # Calculate actual dimensions
        actual_w = calculate_dimension(params['w'], base_w)
        actual_l = calculate_dimension(params['l'], base_l)
        nf = params['nf']

        # Get PDK-specific model name
        model = get_model_name(device_type, params['type'], tech_config)

        # Update the device in the subcircuit
        # Set the model name
        subckt.set_element_model(device_name, model)

        # Set the device parameters
        subckt.set_component_parameters(
            device_name,
            W=format_dimension(actual_w),
            L=format_dimension(actual_l),
            nf=nf
        )


def main():
    """Main entry point for netlist generation."""
    parser = argparse.ArgumentParser(
        description='Generate SPICE netlist variants from template and configuration.',
        epilog='Example: %(prog)s -t spice/comp.sp -p spice/comp.toml -c spice/tech.toml -o results/'
    )
    parser.add_argument(
        '-t', '--template',
        type=Path,
        required=True,
        metavar='FILE',
        help='Template SPICE netlist file'
    )
    parser.add_argument(
        '-p', '--params',
        type=Path,
        required=True,
        metavar='FILE',
        help='Component parameters configuration file (TOML)'
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        required=True,
        metavar='FILE',
        help='Technology configuration file (TOML)'
    )
    parser.add_argument(
        '-o', '--outdir',
        type=Path,
        required=True,
        metavar='DIR',
        help='Output directory for generated netlists'
    )
    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Preview what would be generated without creating files'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Load configurations
    if args.verbose:
        print(f"Loading component parameters from {args.params}")
    comp_config = load_toml_config(args.params)

    if args.verbose:
        print(f"Loading technology config from {args.config}")
    tech_configs = load_toml_config(args.config)

    # Get template path
    template_path = args.template
    if args.verbose:
        print(f"Using template netlist: {template_path}")

    # Create output directory
    if not args.dry_run:
        args.outdir.mkdir(parents=True, exist_ok=True)
        if args.verbose:
            print(f"Output directory: {args.outdir}")

    # Extract device names from template
    # We'll do this by reading the template once
    temp_editor = SpiceEditor(str(template_path))

    # Get the first subcircuit (assuming single subcircuit template)
    subckt_names = temp_editor.get_subcircuit_names()
    if not subckt_names:
        print("Error: No subcircuits found in template!")
        return

    subckt_name = subckt_names[0]
    if args.verbose:
        print(f"Using subcircuit: {subckt_name}")
    subckt = temp_editor.get_subcircuit_named(subckt_name)

    devices = [comp for comp in subckt.get_components()
               if comp.upper().startswith(('MN', 'MP'))]
    if args.verbose:
        print(f"Found {len(devices)} devices: {', '.join(devices)}")

    # Generate parameter combinations
    if args.verbose:
        print("Generating parameter combinations...")
    param_combinations = generate_param_combinations(devices, comp_config)

    # Print header with parameter summary
    param_summary = summarize_varying_params(comp_config)
    num_tech = len(comp_config['tech'])
    num_variants = len(param_combinations)
    print(f"  Sweeps: {param_summary}")
    print(f"  Total: {num_variants} variants × {num_tech} technologies")
    print()

    # Generate netlists for each technology
    total_netlists = 0
    skipped_duplicates = 0
    max_tech_len = max(len(tech) for tech in comp_config['tech'])

    for tech in comp_config['tech']:
        tech_config = tech_configs[tech]
        tech_new = 0
        tech_skipped = 0

        for config_id, param_config in enumerate(param_combinations, start=1):
            if args.dry_run:
                print(f"Would generate netlist {config_id}/{len(param_combinations)}")
                if config_id == 1:  # Show details for first config only
                    for dev, params in param_config.items():
                        print(f"  {dev}: w={params['w']}, l={params['l']}, "
                              f"nf={params['nf']}, type={params['type']}")
            else:
                # Generate human-readable filename from parameters
                netlist_name = generate_netlist_name(tech, param_config, comp_config, template_path)
                output_path = args.outdir / netlist_name

                # Check if file already exists (deduplication)
                if output_path.exists():
                    tech_skipped += 1
                    skipped_duplicates += 1
                else:
                    # Load template
                    editor = SpiceEditor(str(template_path))

                    # Apply configuration
                    apply_config_to_netlist(editor, subckt_name, param_config, tech, tech_config)

                    # Save netlist
                    editor.save_netlist(str(output_path))
                    tech_new += 1
                    total_netlists += 1

        # Report with deduplication info
        if tech_skipped > 0:
            print(f"{tech:<{max_tech_len}}  {tech_new} unique netlists ({tech_skipped} duplicates skipped)")
        else:
            print(f"{tech:<{max_tech_len}}  {tech_new} netlists")

    if args.dry_run:
        print(f"\nDry run complete. Would generate {len(comp_config['tech']) * len(param_combinations)} netlists.")
    else:
        if skipped_duplicates > 0:
            print(f"\n✓ {total_netlists} unique netlists → {args.outdir} ({skipped_duplicates} duplicates skipped)")
        else:
            print(f"\n✓ {total_netlists} netlists → {args.outdir}")


if __name__ == '__main__':
    main()
