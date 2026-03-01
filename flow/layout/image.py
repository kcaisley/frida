"""Layout image export helpers."""

from __future__ import annotations

from pathlib import Path

import klayout.lay as lay


def gds_to_png_with_pdk_style(
    gds: Path,
    *,
    tech: str,
    out_dir: Path,
    width: int = 1200,
    height: int = 1200,
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
    view.set_config("background-color", "#ffffff")
    view.set_config("grid-visible", "false")
    view.load_layout(str(gds))
    view.load_layer_props(str(lyp))
    view.max_hier()
    view.add_missing_layers()
    view.zoom_fit()
    view.save_image(str(png), width, height)
    return png
