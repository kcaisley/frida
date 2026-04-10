"""Layout image export helpers."""

from __future__ import annotations

from pathlib import Path

import klayout.db as db
import klayout.lay as lay


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
    show_all_layers: bool = False,
    crop_to_layer: tuple[int, int] | None = None,
) -> Path:
    """Render a PNG from `gds` using the matching PDK `.lyp` style file.

    This is the common visual-collateral path used by layout tests.
    """

    if not gds.exists():
        raise FileNotFoundError(f"GDS file not found: {gds}")

    root = Path(__file__).resolve().parents[2]
    lyp = root / "pdk" / tech / f"{tech}.lyp"
    if not lyp.exists():
        raise FileNotFoundError(f"PDK layer-style file not found: {lyp}")

    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{gds.stem}.png"

    view = lay.LayoutView()
    view.set_config("background-color", background)
    view.set_config("grid-visible", "false")
    view.set_config("text-visible", str(show_text).lower())
    view.set_config("cell-frame-visible", str(show_cell_frames).lower())
    view.load_layout(str(gds))
    view.load_layer_props(str(lyp))
    view.max_hier()
    view.add_missing_layers()
    for lp in view.each_layer():
        if show_all_layers:
            lp.visible = True
        if hide_layers and lp.name in hide_layers:
            lp.visible = False
    if crop_to_layer is not None:
        layout = view.cellview(0).layout()
        top = layout.top_cell()
        layer_idx = layout.find_layer(db.LayerInfo(*crop_to_layer))
        if layer_idx is not None:
            bbox = top.bbox_per_layer(layer_idx)
            dbu = layout.dbu
            dbox = db.DBox(
                bbox.left * dbu, bbox.bottom * dbu,
                bbox.right * dbu, bbox.top * dbu,
            )
            view.zoom_box(dbox)
        else:
            view.zoom_fit()
    else:
        view.zoom_fit()
    view.save_image(str(png), width, height)
    return png
