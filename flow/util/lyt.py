"""KLayout technology (.lyt) layer utilities."""

from __future__ import annotations

import re
from pathlib import Path


def list_layers(lyt_path: Path) -> dict[str, tuple[int, int]]:
    """Parse a KLayout technology file and return a layer-name → (layer, datatype) map.

    Extracts mappings from the LEFDEF configuration section of the ``.lyt`` file.
    Values are ``(layer, datatype)`` tuples, matching the output format of
    :func:`flow.util.gds.list_layers`.

    Returns
    -------
    dict[str, tuple[int, int]]
        e.g. ``{"M1": (19, 0), "VIA1": (51, 0), ...}``
    """
    import klayout.db as db

    tech = db.Technology()
    tech.load(str(lyt_path))
    opts = tech.load_layout_options
    lefdef = opts.lefdef_config
    layer_map = lefdef.layer_map
    layer_map_str = layer_map.to_string()

    layers = {}
    for name, layer_num, datatype in re.findall(r"([^\n:]+?)\s*:\s*(\d+)/(\d+)", layer_map_str):
        layers[name.strip()] = (int(layer_num), int(datatype))
    return layers
