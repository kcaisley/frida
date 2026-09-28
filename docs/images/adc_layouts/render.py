"""Render representative historical ADC channels as transparent high-resolution PNGs.

Run with KLayout's Python interpreter from the FRIDA repository root:

    klayout -b -r docs/images/adc_layouts/render.py

The archived GDS files are read-only inputs.  Each image is cropped to geometry on
the configured process layers, rendered one layer at a time, and composited with
the same role-based palette used by the ASICLab chip catalogue.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from klayout import db, lay

ROOT = Path(__file__).resolve().parent
LONG_EDGE_PX = 6000
PADDING_FRACTION = 0.025


@dataclass(frozen=True)
class LayerStyle:
    name: str
    layer: int
    datatype: int
    color: str
    alpha: float


@dataclass(frozen=True)
class RenderSpec:
    output: str
    gds: Path
    cell: str
    layers: tuple[LayerStyle, ...]


TSMC65 = (
    LayerStyle("NW", 3, 0, "#268D74", 0.92),
    LayerStyle("OD", 6, 0, "#C44C2D", 0.92),
    LayerStyle("PO", 17, 0, "#496C99", 0.92),
    LayerStyle("CO", 30, 0, "#008F83", 0.92),
    LayerStyle("M1", 31, 0, "#066DFF", 0.92),
    LayerStyle("VIA1", 51, 0, "#009E55", 0.92),
    LayerStyle("M2", 32, 0, "#F22450", 0.92),
    LayerStyle("VIA2", 52, 0, "#EA2783", 0.92),
    LayerStyle("M3", 33, 0, "#00934A", 0.92),
    LayerStyle("VIA3", 53, 0, "#FF3D22", 0.34),
    LayerStyle("M4", 34, 0, "#FF701F", 0.34),
    LayerStyle("VIA4", 54, 0, "#AD20E8", 0.22),
    LayerStyle("M5", 35, 0, "#D128F2", 0.22),
    LayerStyle("VIA5", 55, 0, "#00AB9F", 0.19),
    LayerStyle("M6", 36, 0, "#00C8BE", 0.19),
    LayerStyle("VIA6", 56, 0, "#009ADE", 0.16),
    LayerStyle("M7", 37, 0, "#00BEEB", 0.16),
    LayerStyle("VIA7", 57, 40, "#2F70F5", 0.14),
    LayerStyle("M8", 38, 40, "#3A72FF", 0.14),
    LayerStyle("VIA8", 58, 40, "#673AE6", 0.13),
    LayerStyle("M9", 39, 60, "#4D50F4", 0.13),
    LayerStyle("AP", 74, 0, "#4EA5F2", 0.50),
)

UMC180 = (
    LayerStyle("DIFF", 1, 0, "#C44C2D", 0.92),
    LayerStyle("NW", 3, 0, "#268D74", 0.92),
    LayerStyle("PO", 41, 0, "#496C99", 0.92),
    LayerStyle("CONT", 39, 0, "#008F83", 0.92),
    LayerStyle("M1", 46, 0, "#066DFF", 0.92),
    LayerStyle("V1", 47, 0, "#009E55", 0.92),
    LayerStyle("M2", 48, 0, "#F22450", 0.92),
    LayerStyle("V2", 49, 0, "#EA2783", 0.92),
    LayerStyle("M3", 50, 0, "#00934A", 0.92),
    LayerStyle("V3", 51, 0, "#FF3D22", 0.34),
    LayerStyle("M4", 52, 0, "#FF701F", 0.34),
    LayerStyle("V4", 53, 0, "#AD20E8", 0.22),
    LayerStyle("M5", 54, 0, "#D128F2", 0.22),
    LayerStyle("V5", 55, 0, "#00AB9F", 0.19),
    LayerStyle("M6", 56, 0, "#00C8BE", 0.19),
    LayerStyle("PAD", 66, 0, "#4EA5F2", 0.50),
)

SPECS = (
    RenderSpec(
        "dcd2_adc_channel.png",
        Path("/projects/dcd2/gds/dcd2.gds"),
        "PixelDCD2",
        UMC180,
    ),
    RenderSpec(
        "dhpt02_adc_channel.png",
        Path("/projects/dhpt-0-2/gds/dhpt-0-2.gds"),
        "SAR_ADC_1ch_v2",
        TSMC65,
    ),
    RenderSpec(
        "cordia1_adc_channel.png",
        Path("/projects/cordia-1/gds/cordia-1.gds"),
        "ADC_BSS",
        TSMC65,
    ),
    RenderSpec(
        "frida1_adc_channel.png",
        Path("/projects/frida-1/gds/frida-1.gds"),
        "adc",
        TSMC65,
    ),
)


def geometry_bbox(layout: db.Layout, cell: db.Cell, styles: tuple[LayerStyle, ...]) -> db.Box:
    bbox: db.Box | None = None
    for style in styles:
        layer_index = layout.find_layer(db.LayerInfo(style.layer, style.datatype))
        if layer_index is None or layer_index < 0:
            continue
        layer_bbox = cell.bbox_per_layer(layer_index)
        if layer_bbox.empty():
            continue
        bbox = layer_bbox if bbox is None else bbox + layer_bbox
    if bbox is None or bbox.empty():
        raise RuntimeError(f"No configured geometry found in cell {cell.name}")
    return bbox


def padded_box(box: db.Box, dbu: float) -> db.DBox:
    width = box.width() * dbu
    height = box.height() * dbu
    pad = max(width, height) * PADDING_FRACTION
    return db.DBox(
        box.left * dbu - pad,
        box.bottom * dbu - pad,
        box.right * dbu + pad,
        box.top * dbu + pad,
    )


def image_size(box: db.DBox) -> tuple[int, int]:
    if box.width() >= box.height():
        return LONG_EDGE_PX, max(1, round(LONG_EDGE_PX * box.height() / box.width()))
    return max(1, round(LONG_EDGE_PX * box.width() / box.height())), LONG_EDGE_PX


def render(spec: RenderSpec) -> None:
    if not spec.gds.exists():
        raise FileNotFoundError(spec.gds)

    layout = db.Layout()
    layout.read(str(spec.gds))
    cell = layout.cell(spec.cell)
    if cell is None:
        raise RuntimeError(f"Cell {spec.cell!r} not found in {spec.gds}")

    crop = padded_box(geometry_bbox(layout, cell, spec.layers), layout.dbu)
    width, height = image_size(crop)

    view = lay.LayoutView()
    view.set_config("background-color", "#FFFFFF")
    view.set_config("grid-visible", "false")
    view.set_config("text-visible", "false")
    view.set_config("cell-frame-visible", "false")
    view.show_layout(layout, False)
    view.active_cellview().cell = cell
    view.max_hier()
    view.add_missing_layers()

    properties = list(view.each_layer())
    by_index = {prop.layer_index(): prop for prop in properties if prop.layer_index() >= 0}
    for prop in properties:
        prop.visible = False
        prop.fill_color = 0x000000
        prop.frame_color = 0x000000

    with tempfile.TemporaryDirectory(prefix=f"{spec.cell}-") as temporary:
        temp = Path(temporary)
        colored: list[Path] = []

        for order, style in enumerate(spec.layers):
            layer_index = layout.find_layer(db.LayerInfo(style.layer, style.datatype))
            prop = by_index.get(layer_index)
            if prop is None or cell.bbox_per_layer(layer_index).empty():
                continue

            raw = temp / f"raw-{order:02d}.png"
            color = temp / f"color-{order:02d}.png"
            prop.visible = True
            view.zoom_box(crop)
            view.save_image(str(raw), width, height)
            prop.visible = False

            subprocess.run(
                [
                    "convert",
                    raw,
                    "-limit",
                    "thread",
                    "1",
                    "-negate",
                    "-background",
                    style.color,
                    "-alpha",
                    "shape",
                    "-alpha",
                    "set",
                    "-background",
                    "none",
                    "-channel",
                    "A",
                    "-evaluate",
                    "multiply",
                    f"{style.alpha:.2f}",
                    "+channel",
                    color,
                ],
                check=True,
            )
            colored.append(color)

        if not colored:
            raise RuntimeError(f"No visible layers rendered for {spec.cell}")

        output = ROOT / spec.output
        command: list[str | Path] = ["convert", colored[0]]
        for color in colored[1:]:
            command.extend((color, "-composite"))
        command.extend(
            (
                "-limit",
                "thread",
                "1",
                "-background",
                "none",
                "-strip",
                "-define",
                "png:exclude-chunks=date,time",
                output,
            )
        )
        subprocess.run(command, check=True)

    print(f"{spec.cell}: {width}x{height} -> {ROOT / spec.output}")


for render_spec in SPECS:
    render(render_spec)
