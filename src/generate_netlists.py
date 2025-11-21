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


def get_device_params(device_name: str, comp_config: Dict[str, Any]) -> Dict[str, List]:
    """
    Get parameter lists for a device, merging defaults with device-specific overrides.

    Returns a dict with keys: w, l, nf, type (each containing a list of values)
    """
    device_type = get_device_type(device_name)

    # Start with defaults for this device type
    params = {
        'w': comp_config['defaults'][device_type]['w'].copy(),
        'l': comp_config['defaults'][device_type]['l'].copy(),
        'nf': comp_config['defaults'][device_type]['nf'].copy(),
        'type': comp_config['defaults'][device_type]['type'].copy(),
    }

    # Override with device-specific parameters if they exist
    if device_name in comp_config['devices']:
        device_overrides = comp_config['devices'][device_name]
        for key in ['w', 'l', 'nf', 'type']:
            if key in device_overrides:
                params[key] = device_overrides[key]

    return params


def summarize_varying_params(devices: List[str], comp_config: Dict[str, Any]) -> str:
    """Return a summary of which parameters are being varied."""
    param_list = []

    for device in devices:
        params = get_device_params(device, comp_config)
        varying = []

        # Check which parameters have more than one value
        if len(params['w']) > 1:
            varying.append('W')
        if len(params['l']) > 1:
            varying.append('L')
        if len(params['nf']) > 1:
            varying.append('NF')
        if len(params['type']) > 1:
            varying.append('Type')

        if varying:
            param_list.append(f"{device} ({', '.join(varying)})")

    return ', '.join(param_list)


def generate_param_combinations(devices: List[str], comp_config: Dict[str, Any]) -> List[Dict[str, Dict[str, Any]]]:
    """
    Generate all combinations of device parameters.

    Returns a list of configurations, where each config is a dict mapping
    device_name -> {w: val, l: val, nf: val, type: val}
    """
    # Get parameter options for each device
    device_params = {}
    for device in devices:
        device_params[device] = get_device_params(device, comp_config)

    # Generate all combinations
    # For each device, we need to iterate over all combinations of its parameters
    device_param_combos = {}
    for device, params in device_params.items():
        # Create all combinations for this device
        combos = list(itertools.product(
            params['w'],
            params['l'],
            params['nf'],
            params['type']
        ))
        device_param_combos[device] = combos

    # Now create all combinations across all devices
    all_devices = list(device_param_combos.keys())
    all_combos_per_device = [device_param_combos[dev] for dev in all_devices]

    configurations = []
    for combo in itertools.product(*all_combos_per_device):
        config = {}
        for i, device in enumerate(all_devices):
            w, l, nf, vt_type = combo[i]
            config[device] = {
                'w': w,
                'l': l,
                'nf': nf,
                'type': vt_type
            }
        configurations.append(config)

    return configurations


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


def generate_netlist_name(tech: str, config_id: int, template_path: Path) -> str:
    """Generate a meaningful filename for the netlist variant."""
    # Extract template name without extension
    base_name = template_path.stem
    return f"{base_name}_{tech}_v{config_id:04d}.sp"


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
    param_summary = summarize_varying_params(devices, comp_config)
    num_tech = len(comp_config['tech'])
    num_variants = len(param_combinations)
    print(f"  Parameters: {param_summary}")
    print(f"  Total: {num_variants} variants × {num_tech} technologies")
    print()

    # Generate netlists for each technology
    total_netlists = 0
    max_tech_len = max(len(tech) for tech in comp_config['tech'])

    for tech in comp_config['tech']:
        tech_config = tech_configs[tech]

        for config_id, param_config in enumerate(param_combinations, start=1):
            netlist_name = generate_netlist_name(tech, config_id, template_path)
            output_path = args.outdir / netlist_name

            if args.dry_run:
                print(f"Would generate: {netlist_name}")
                if config_id == 1:  # Show details for first config only
                    for dev, params in param_config.items():
                        print(f"  {dev}: w={params['w']}, l={params['l']}, "
                              f"nf={params['nf']}, type={params['type']}")
            else:
                # Load template
                editor = SpiceEditor(str(template_path))

                # Apply configuration
                apply_config_to_netlist(editor, subckt_name, param_config, tech, tech_config)

                # Save netlist
                editor.save_netlist(str(output_path))

                total_netlists += 1

        print(f"{tech:<{max_tech_len}}  {len(param_combinations)} netlists")

    if args.dry_run:
        print(f"\nDry run complete. Would generate {len(comp_config['tech']) * len(param_combinations)} netlists.")
    else:
        print(f"\n✓ {total_netlists} netlists → {args.outdir}")


if __name__ == '__main__':
    main()
