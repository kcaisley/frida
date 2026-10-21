"""Layout image export: one GDS or several side by side, in the PDK's layer palette.

``render_png`` is the general tool: panels (a GDS and an optional title) are placed left to
right, titles drawn under them as text polygons with the panel size, the placement boundary
hidden, and the metals drawn solid or hatched. Solid metal reads well for a block
using a few metal levels (M1-M3); a whole chip with its full stack becomes one colour
blob, so ``metals="auto"`` hatches as soon as more than ``SOLID_MAX_METALS`` levels are
drawn. Overlays (``Overlay``) add marker shapes, e.g. DRC results or fill regions.

    render_png([(Path("a.gds"), "Title A"), (Path("b.gds"), "Title B")], Path("out.png"), tech="tsmc65",
               metals="auto", zoom=(x0, y0, x1, y1), width=2400, titles=True)

``gds_to_png_with_pdk_style`` is the single-file helper the primitive tests use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from klayout import db, lay

ROOT = Path(__file__).resolve().parents[2]
METAL = re.compile(r"^(M|METAL|Metal)(\d+)\.drawing$")  # metal levels across the palettes in pdk/
SOLID_MAX_METALS = 4
# layers that are tool artefacts rather than design data, per technology
TITLE_LAYER = (10000, 0)
OVERLAY_LAYER0 = 10001


@dataclass
class Overlay:
    """Marker shapes drawn over the layout: ``style`` "outline" (a frame) or "solid"."""

    region: db.Region
    color: int = 0xFF0000
    style: str = "outline"
    width: int = 3


def _pdk_layer(tech: str, name: str) -> tuple[int, int] | None:
    """A layer's number in the PDK's layer table (``pdk.<tech>.layout.tech.LAYERS``), if it has one."""
    try:
        layers = import_module(f"pdk.{tech}.layout.tech").LAYERS
    except ImportError:
        return None
    return layers.get(name)


def _lyp(tech: str) -> Path:
    lyp = ROOT / "pdk" / tech / "klayout" / f"{tech}.lyp"
    if not lyp.exists():
        raise FileNotFoundError(f"PDK layer-style file not found: {lyp}")
    return lyp


def _view(
    layout_path: Path,
    tech: str,
    *,
    background: str = "#ffffff",
    show_text: bool = False,
    show_cell_frames: bool = False,
) -> lay.LayoutView:
    view = lay.LayoutView()
    view.set_config("background-color", background)
    view.set_config("grid-visible", "false")
    view.set_config("text-visible", str(show_text).lower())
    view.set_config("cell-frame-visible", str(show_cell_frames).lower())
    view.load_layout(str(layout_path))
    view.load_layer_props(str(_lyp(tech)))
    view.max_hier()
    view.add_missing_layers()
    return view


def _metal_levels(view: lay.LayoutView) -> set[int]:
    """Metal levels with shapes in the view's top cell."""
    top = view.cellview(0).cell
    levels = set()
    for lp in view.each_layer():
        m = METAL.match(lp.name)
        if m and lp.layer_index() >= 0 and not top.bbox_per_layer(lp.layer_index()).empty():
            levels.add(int(m.group(2)))
    return levels


def _style(
    view: lay.LayoutView,
    *,
    metals: str = "auto",
    hide_layers=None,
    solid_layers=None,
    layer_colors=None,
    show_all_layers: bool = False,
) -> None:
    """Palette tweaks on a loaded view. Layer keys are style names ("M1.drawing") or
    "layer/datatype" strings."""
    if metals not in ("auto", "solid", "hatched"):
        raise ValueError(f"metals must be auto, solid or hatched, not {metals!r}")
    solid_metals = metals == "solid" or (metals == "auto" and len(_metal_levels(view)) <= SOLID_MAX_METALS)
    for lp in view.each_layer():
        if show_all_layers:
            lp.visible = True
        keys = {lp.name, lp.source.split("@")[0]}
        if hide_layers and keys & set(hide_layers):
            lp.visible = False
        if (solid_metals and METAL.match(lp.name)) or (solid_layers and keys & set(solid_layers)):
            lp.dither_pattern = 0  # solid fill
        for key, color in (layer_colors or {}).items():
            if key in keys:
                lp.fill_color = lp.frame_color = color


def _top(layout: db.Layout) -> db.Cell:
    tops = list(layout.top_cells())
    return max(tops, key=lambda c: c.bbox().area()) if len(tops) > 1 else tops[0]


def render_png(
    panels: list[tuple[Path, str | None]],
    out: Path,
    *,
    tech: str = "tsmc65",
    metals: str = "auto",
    width: int | None = None,
    height: int | None = None,
    titles: bool = True,
    zoom: tuple[float, float, float, float] | None = None,
    overlays: list[Overlay] = (),
    hide_layers: list[str] | None = None,
    layer_colors: dict[str, int] | None = None,
    strip: list[tuple[int, int | None]] | None = None,
) -> Path:
    """Render ``panels`` (GDS path, title or None) side by side into ``out`` (PNG).

    The first panel keeps its own coordinates, so ``zoom`` (um) and ``overlays`` (layout
    units) refer to it as it is; the others follow to its right, bottoms aligned. Titles get
    the panel's size appended: its placement boundary where that outlines the block,
    else its diffusion's extent.
    """
    out = Path(out)
    boundary, active = _pdk_layer(tech, "BND"), _pdk_layer(tech, "OD")
    strip = ([(boundary[0], boundary[1])] if boundary else []) if strip is None else strip
    comp = db.Layout()
    comp.dbu = 0.001
    top = comp.create_cell(out.stem)
    x, boxes, bottom = 0, [], 0
    for i, (gds, title) in enumerate(panels):
        src = db.Layout()
        src.read(str(gds))
        cell = comp.create_cell(f"panel{i}")
        cell.copy_tree(_top(src))
        outline = None
        if boundary and comp.find_layer(*boundary) is not None:
            outline = cell.bbox_per_layer(comp.find_layer(*boundary))
        for cc in [cell] + [comp.cell(j) for j in cell.called_cells()]:
            for li in comp.layer_indexes():
                info, shapes = comp.get_info(li), cc.shapes(li)
                if any(info.layer == ly and (dt is None or info.datatype == dt) for ly, dt in strip):
                    shapes.clear()
                else:
                    for s in [s for s in shapes.each() if s.is_text()]:
                        shapes.erase(s)
        bbox = cell.bbox()
        # the boundary layer when it outlines the block (some flows mark only a cell or a row
        # with it); else the diffusion's extent, else everything drawn
        od = comp.find_layer(*active) if active else None
        drawn = cell.bbox_per_layer(od) if od is not None and not cell.bbox_per_layer(od).empty() else bbox
        if not outline or outline.empty() or outline.area() < 0.8 * drawn.area():
            outline = drawn
        if i == 0:
            dx, dy, bottom = 0, 0, bbox.bottom
        else:
            dx, dy = x - bbox.left, bottom - bbox.bottom
        top.insert(db.CellInstArray(cell.cell_index(), db.Trans(dx, dy)))
        gap = max(2000, bbox.width() // 6)
        boxes.append((bbox.moved(dx, dy), outline, title, gap))
        x = bbox.right + dx + gap
    if titles and any(t for _, _, t, _ in boxes):
        gen = db.TextGenerator.default_generator()
        tall = max(b.height() for b, _, _, _ in boxes)
        text_layer = comp.layer(*TITLE_LAYER)
        for b, outline, title, gap in boxes:
            if not title:
                continue
            label = f"{title}: {outline.width() / 1000:.1f} x {outline.height() / 1000:.1f} um"
            r = gen.text(label, comp.dbu, 1.0)
            # at most the panel's column (the panel and most of its gap), so titles never meet
            scale = min(tall * 0.06 / r.bbox().height(), (b.width() + gap * 0.6) / r.bbox().width())
            r = r.transformed(db.ICplxTrans(scale))
            top.shapes(text_layer).insert(r.moved(b.left - r.bbox().left, b.bottom - int(tall * 0.05) - r.bbox().top))
    for k, ov in enumerate(overlays):
        top.shapes(comp.layer(OVERLAY_LAYER0 + k, 0)).insert(ov.region)
    tmp = out.with_suffix(".gds")
    out.parent.mkdir(parents=True, exist_ok=True)
    comp.write(str(tmp))

    view = _view(tmp, tech)
    _style(view, metals=metals, hide_layers=hide_layers, layer_colors=layer_colors)
    for lp in view.each_layer():
        src = lp.source.split("@")[0]
        if src == f"{TITLE_LAYER[0]}/{TITLE_LAYER[1]}":
            lp.visible, lp.dither_pattern = True, 0
            lp.fill_color = lp.frame_color = 0x000000
        for k, ov in enumerate(overlays):
            if src == f"{OVERLAY_LAYER0 + k}/0":
                lp.visible = True
                lp.fill_color = lp.frame_color = ov.color
                lp.dither_pattern = 0 if ov.style == "solid" else 1  # 1: hollow
                lp.width = ov.width
    if zoom:
        view.zoom_box(db.DBox(*zoom))
    else:
        view.zoom_fit()
    content = top.bbox() if not zoom else db.DBox(*zoom).to_itype(comp.dbu)
    w = width or (2400 if len(panels) > 1 else 1200)
    h = height or max(300, min(4 * w, round(w * content.height() / max(content.width(), 1) * 1.08)))
    view.save_image(str(out), w, h)
    tmp.unlink()
    return out


def gds_to_png_with_pdk_style(
    gds: Path,
    *,
    tech: str,
    out_dir: Path,
    width: int = 1200,
    height: int = 1200,
    background: str = "#ffffff",
    show_text: bool = False,
    show_cell_frames: bool = False,
    hide_layers: list[str] | None = None,
    solid_layers: list[str] | None = None,
    layer_colors: dict[str, int] | None = None,
    show_all_layers: bool = False,
    crop_to_layer: tuple[int, int] | None = None,
    metals: str = "hatched",
) -> Path:
    """Render a PNG from `gds` using the matching PDK `.lyp` style file.

    This is the common visual-collateral path used by layout tests. `hide_layers` and
    `solid_layers` take style names (``"M1.drawing"``) or ``"layer/datatype"`` strings;
    solid layers are drawn without their hatch pattern, and `layer_colors` maps such keys to
    0xRRGGBB fill/frame colours (e.g. for annotation layers that have no palette entry).
    ``metals``: "hatched" (the palette's patterns), "solid" or "auto" (see ``render_png``).
    """

    if not gds.exists():
        raise FileNotFoundError(f"GDS file not found: {gds}")
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{gds.stem}.png"

    view = _view(gds, tech, background=background, show_text=show_text, show_cell_frames=show_cell_frames)
    _style(
        view,
        metals=metals,
        hide_layers=hide_layers,
        solid_layers=solid_layers,
        layer_colors=layer_colors,
        show_all_layers=show_all_layers,
    )
    if crop_to_layer is not None:
        layout = view.cellview(0).layout()
        top = layout.top_cell()
        layer_idx = layout.find_layer(db.LayerInfo(*crop_to_layer))
        if layer_idx is not None:
            bbox = top.bbox_per_layer(layer_idx)
            dbu = layout.dbu
            dbox = db.DBox(
                bbox.left * dbu,
                bbox.bottom * dbu,
                bbox.right * dbu,
                bbox.top * dbu,
            )
            view.zoom_box(dbox)
        else:
            view.zoom_fit()
    else:
        view.zoom_fit()
    view.save_image(str(png), width, height)
    return png
