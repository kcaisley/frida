"""A layout's cells rendered for the thesis, in the viewer's style (flow/web/static/js/layers.js:
Nord colours on the generic layer keys, translucent hatched fills, the front end under the
metals) on a transparent background. Each cell is flattened onto the PDK's generic layers
(``pdk.<pdk>.layout.tech.LAYERS``, read at run time from the kit, nothing of it written here),
each layer merged, and drawn with KLayout's own renderer.

    uv run python docs/thesis/drawings/render_layout.py GDS PDK OUT_DIR name=CELL [name=CELL ...]

``name=CELL`` renders cell CELL into ``OUT_DIR/name.png``; ``name=`` (no cell) the top cell;
``name=CELL@4`` only the metals up to M4 (and their vias), for a dense cell. A first argument
``--style=asiclab`` draws in the ASICLab chip catalogue's style instead of the viewer's.
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


# the ASICLab chip catalogue's role palette (docs/images/adc_layouts/render.py) on the generic keys:
# each layer's colour and opacity, the upper metals fainter
ASICLAB = {
    "NW": ("#268D74", 0.92),
    "OD": ("#C44C2D", 0.92),
    "PO": ("#496C99", 0.92),
    "CO": ("#008F83", 0.92),
    "M1": ("#066DFF", 0.92),
    "V1": ("#009E55", 0.92),
    "M2": ("#F22450", 0.92),
    "V2": ("#EA2783", 0.92),
    "M3": ("#00934A", 0.92),
    "V3": ("#FF3D22", 0.34),
    "M4": ("#FF701F", 0.34),
    "V4": ("#AD20E8", 0.22),
    "M5": ("#D128F2", 0.22),
    "V5": ("#00AB9F", 0.19),
    "M6": ("#00C8BE", 0.19),
    "V6": ("#009ADE", 0.16),
    "M7": ("#00BEEB", 0.16),
    "V7": ("#2F70F5", 0.14),
    "M8": ("#3A72FF", 0.14),
    "V8": ("#673AE6", 0.13),
    "M9": ("#4D50F4", 0.13),
}


def render_asiclab(layout: kdb.Layout, keys: list[str], path: Path) -> None:
    """The ASICLab catalogue's style: each layer rendered alone in black, its coverage tinted with
    its role colour at its opacity, the layers composited bottom first (over)."""
    box = (
        layout.top_cell()
        .dbbox()
        .enlarged(layout.top_cell().dbbox().width() * 0.01, layout.top_cell().dbbox().height() * 0.01)
    )
    height = max(1, round(WIDTH_PX * box.height() / box.width()))
    out = np.zeros((height, WIDTH_PX, 4))
    with tempfile.TemporaryDirectory() as tmp:
        gds = Path(tmp) / "render.gds"
        layout.write(str(gds))
        for key in keys:
            if key not in ASICLAB:
                continue
            index = next(i for i in layout.layer_indexes() if layout.get_info(i).name == key)
            info = layout.get_info(index)
            view = klay.LayoutView()
            view.set_config("background-color", "#ffffff")
            view.set_config("grid-visible", "false")
            view.set_config("text-visible", "false")
            view.set_config("cell-frame-visible", "false")
            view.load_layout(str(gds), True)
            view.clear_layers()
            node = klay.LayerProperties()
            node.source = f"{info.layer}/{info.datatype}@1"
            node.fill_color = 0x000000
            node.frame_color = 0x000000
            node.dither_pattern = 0
            node.width = 1
            view.insert_layer(view.end_layers(), node)
            view.max_hier()
            raw = Path(tmp) / f"{key}.png"
            view.save_image_with_options(str(raw), WIDTH_PX, height, 0, 2, 0, box, True)
            image = mpimg.imread(raw)
            gray = image if image.ndim == 2 else image[:, :, :3].mean(axis=2)
            color, alpha = ASICLAB[key]
            rgb = np.array([int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)])
            a = (1.0 - gray) * alpha
            out[:, :, :3] = rgb * a[:, :, None] + out[:, :, :3] * (1 - a[:, :, None])
            out[:, :, 3] = a + out[:, :, 3] * (1 - a)
    # un-premultiply the colour for the PNG
    shown = out[:, :, 3] > 0
    out[shown, :3] /= out[shown, 3][:, None]
    mpimg.imsave(path, np.clip(out, 0, 1))


def main() -> None:
    args = sys.argv[1:]
    style_name = "viewer"
    if args and args[0].startswith("--style="):
        style_name = args.pop(0).split("=", 1)[1]
    gds, pdk, out, *wanted = args
    layout = kdb.Layout()
    layout.read(gds)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in wanted:
        name, _, spec = item.partition("=")
        cell_name, _, limit = spec.partition("@")
        cell = layout.cell(cell_name) if cell_name else layout.top_cells()[0]
        flat, keys = generic(layout, cell, pdk, int(limit) if limit else 99)
        (render_asiclab if style_name == "asiclab" else render)(flat, keys, out_dir / f"{name}.png")
        print(out_dir / f"{name}.png", keys)


if __name__ == "__main__":
    main()
