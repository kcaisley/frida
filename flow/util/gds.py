"""GDS file utilities."""

from __future__ import annotations

from pathlib import Path


def list_cells(gds_path: Path) -> list[str]:
    """Return a sorted list of cell names in a GDS file."""
    import klayout.db as db

    layout = db.Layout()
    layout.read(str(gds_path))
    return sorted(cell.name for cell in layout.each_cell())


def list_layers(gds_path: Path) -> dict[str, tuple[int, int]]:
    """Return a map of layer descriptions present in a GDS file.

    Keys are ``"layer/datatype"`` strings (e.g. ``"19/0"``), values are
    ``(layer, datatype)`` tuples.  This matches the output format of
    :func:`flow.util.lyt.list_layers`.

    Returns
    -------
    dict[str, tuple[int, int]]
        e.g. ``{"19/0": (19, 0), "20/0": (20, 0)}``
    """
    import klayout.db as db

    layout = db.Layout()
    layout.read(str(gds_path))

    layers = {}
    for li in layout.layer_indices():
        info = layout.get_info(li)
        key = f"{info.layer}/{info.datatype}"
        layers[key] = (info.layer, info.datatype)
    return dict(sorted(layers.items(), key=lambda kv: kv[1]))
