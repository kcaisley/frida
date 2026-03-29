#!/usr/bin/env python3

"""Layer mapping utilities for KLayout technology files."""

import re
import klayout.db as db


# TODO: This is producing garbase layers dictionaries.


def load_layers_from_lyt(ly, lyt_file_path):
    """
    Load layer mapping from KLayout technology file (.lyt).

    Extracts layer mappings from the LEFDEF configuration in the technology file
    and creates KLayout layer objects.

    Args:
        ly: KLayout Layout object
        lyt_file_path: Path to the .lyt technology file

    Returns:
        dict: Dictionary mapping layer names to KLayout layer objects
    """
    # Load technology
    tech = db.Technology()
    tech.load(lyt_file_path)

    # Get LEFDEF layer map from technology
    layout_options = tech.load_layout_options
    lefdef_config = layout_options.lefdef_config
    lefdef_layer_map = lefdef_config.layer_map
    map_str = lefdef_layer_map.to_string()

    # Parse layer mappings from string format: "31/0 : M1\n32/0 : M2\n..."
    layers = {}
    pattern = r"(\d+)/(\d+)\s*:\s*([^\n]+)"
    matches = re.findall(pattern, map_str)

    for layer_num, datatype, name in matches:
        name = name.strip()
        layer_info = db.LayerInfo(int(layer_num), int(datatype))
        layers[name] = ly.layer(layer_info)

    return layers
