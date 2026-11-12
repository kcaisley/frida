"""A layout's cells rendered for the thesis, in the viewer's style (flow/web/static/js/layers.js:
Nord colours on the generic layer keys, translucent hatched fills, the front end under the
metals) on a transparent background. Each cell is flattened onto the PDK's generic layers
(``pdk.<pdk>.layout.tech.LAYERS``, read at run time from the kit, nothing of it written here),
each layer merged, and drawn with KLayout's own renderer.

    uv run python docs/thesis/drawings/render_layout.py GDS PDK OUT_DIR name=CELL [name=CELL ...]

``name=CELL`` renders cell CELL into ``OUT_DIR/name.png``; ``name=`` (no cell) the top cell;
``name=CELL@4`` only the metals up to M4 (and their vias), for a dense cell.
"""

from __future__ import annotations

import sys
import tempfile
from importlib import import_module
from pathlib import Path

import klayout.db as kdb
import klayout.lay as klay
import matplotlib.image as mpimg
import numpy as np

METALS = ["#5E81AC", "#B48EAD", "#D08770", "#EBCB8B", "#8FBCBB", "#88C0D0", "#81A1C1", "#A3BE8C", "#BF616A"]
INK = "#2E3440"
# KLayout's built-in stipples: 0 solid, 1 hollow, 2 dotted, 5 and 9 the two diagonals, 7 the cross
FIXED = {
    "NW": ("#8FBCBB", 1, 1),
    "OD": ("#A3BE8C", 2, 4),
    "PO": ("#BF616A", 5, 5),
    "CO": (INK, 0, 6),
}
WIDTH_PX = 1800


def style(key: str) -> tuple[str, int, int] | None:
    """A generic layer's colour, stipple and drawing order (the viewer's layerStyle), or None
    for the layers the viewer hides by default."""
    if key in FIXED:
        return FIXED[key]
    if key.startswith("M") and key[1:].isdigit():
        n = int(key[1:])
        return (METALS[(n - 1) % len(METALS)], 5 if n % 2 else 9, 10 + 2 * n)
    if key.startswith("V") and key[1:].isdigit():
        n = int(key[1:])
        return (METALS[n % len(METALS)], 7, 11 + 2 * n)
    return None


def generic(layout: kdb.Layout, cell: kdb.Cell, pdk: str, max_metal: int = 99) -> tuple[kdb.Layout, list[str]]:
    """The cell flattened onto the generic layers, each merged; the keys, bottom first."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    numbers = {tuple(number): key for key, number in tech.LAYERS.items() if number}
    out = kdb.Layout()
    out.dbu = layout.dbu
    top = out.create_cell("render")
    keys = []
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        key = numbers.get((info.layer, info.datatype))
        if key is None or style(key) is None:
            continue
        if key[0] in "MV" and key[1:].isdigit() and int(key[1:]) > max_metal - (key[0] == "V"):
            continue
        region = kdb.Region(cell.begin_shapes_rec(index)).merged()
        if region.is_empty():
            continue
        target = out.layer(kdb.LayerInfo(len(keys) + 1, 0, key))
        top.shapes(target).insert(region)
        keys.append(key)
    keys.sort(key=lambda key: style(key)[2])
    return out, keys


def render(layout: kdb.Layout, keys: list[str], path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gds = Path(tmp) / "render.gds"
        layout.write(str(gds))
        view = klay.LayoutView()
        view.set_config("background-color", "#ffffff")
        view.set_config("grid-visible", "false")
        view.set_config("text-visible", "false")
        view.load_layout(str(gds), True)
        view.clear_layers()
        for key in reversed(keys):  # KLayout draws the list's first on top
            color, stipple, _ = style(key)
            number = next(i for i in layout.layer_indexes() if layout.get_info(i).name == key)
            info = layout.get_info(number)
            node = klay.LayerProperties()
            node.source = f"{info.layer}/{info.datatype}@1"
            node.name = key
            rgb = int(color.lstrip("#"), 16)
            node.fill_color = rgb
            node.frame_color = rgb
            node.dither_pattern = stipple
            node.transparent = True
            node.width = 1
            view.insert_layer(view.end_layers(), node)
        view.max_hier()
        view.zoom_fit()
        box = layout.top_cell().dbbox()
        height = max(1, round(WIDTH_PX * box.height() / box.width()))
        view.save_image_with_options(
            str(path), WIDTH_PX, height, 2, 2, 0, box.enlarged(box.width() * 0.01, box.height() * 0.01), False
        )
    # white to transparent
    image = mpimg.imread(path)
    if image.shape[2] == 3:
        image = np.dstack([image, np.ones(image.shape[:2])])
    white = np.all(image[:, :, :3] > 0.985, axis=2)
    image[white, 3] = 0.0
    mpimg.imsave(path, image)


def main() -> None:
    gds, pdk, out, *wanted = sys.argv[1:]
    layout = kdb.Layout()
    layout.read(gds)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in wanted:
        name, _, spec = item.partition("=")
        cell_name, _, limit = spec.partition("@")
        cell = layout.cell(cell_name) if cell_name else layout.top_cells()[0]
        flat, keys = generic(layout, cell, pdk, int(limit) if limit else 99)
        render(flat, keys, out_dir / f"{name}.png")
        print(out_dir / f"{name}.png", keys)


if __name__ == "__main__":
    main()
