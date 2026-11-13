"""A layout's cells as isometric 3-D images for the thesis, drawn by the 3-D layout page
(tools/layout3d: three.js, its 2-D canvas fallback where WebGL is missing) with an orthographic
camera on the isometric diagonal, on a transparent background, through headless Chromium. The
drawing's order is made exact for a layout: layer by layer from the bottom (each layer a band of
height, so a higher one always hides a lower one), and within a layer each box by its corner
nearest the camera; the page's own order (boxes by their centres' distance) stacks long
overlapping wires wrongly.
Each cell is exported by the viewer's own export (``flow.web.export.export_layout``: the PDK's
generic layers, read at run time from the kit, nothing of it written here).

    uv run python docs/thesis/drawings/render_layout3d.py GDS PDK OUT_DIR name=CELL [name=CELL ...]

``name=CELL`` renders cell CELL into ``OUT_DIR/name.png``; ``name=`` (no cell) the top cell.
``LAYOUT3D`` names the 3-D page's folder (default /local/kcaisley/tools/layout3d). Run it from a
checkout whose PDK submodules hold the kit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

LAYOUT3D = Path(os.environ.get("LAYOUT3D", "/local/kcaisley/tools/layout3d"))
SIZE = (1600, 1200)

# the page's camera made orthographic, on the isometric diagonal, framing the layout; its canvas
# cleared rather than filled; everything but the stage hidden
CAMERA = "camera = new THREE.PerspectiveCamera(35, 1, 0.01, 1e4);"
CAMERA_ISO = (
    "camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 1e6);\n"
    "function frame() { const w = stage.clientWidth || 1, h = stage.clientHeight || 1, s = extent * 0.62;"
    " camera.left = -s * w / h; camera.right = s * w / h; camera.top = s; camera.bottom = -s; camera.updateProjectionMatrix(); }"
)
RESIZE = "camera.aspect = w / h; camera.updateProjectionMatrix(); render();"
RESIZE_ISO = "frame(); render();"
HOME = "else camera.position.set(d * 0.55, -d * 0.85, d * 0.75);"
HOME_ISO = "else camera.position.set(d * 4, -d * 4, d * 4 + 0.5); frame();"
# every box's edges drawn, wider and darker than the page's, so they hold at a printed size
EDGE_WIDTH = "flat.lineWidth = 0.6 * ratio;"
EDGE_WIDTH_ISO = "flat.lineWidth = 1.1 * ratio;"
EDGE_TINT = "edge: tint(c, 0.45)"
EDGE_TINT_ISO = "edge: tint(c, 0.28)"
FILL = 'flat.globalAlpha = 1; flat.fillStyle = "#20242c"; flat.fillRect(0, 0, W, H);'
FILL_ISO = "flat.globalAlpha = 1; flat.clearRect(0, 0, W, H);"
HIDE = (
    "<style>header.bar, .dock, .stage > *:not(canvas), #hint { display: none !important; }"
    " body, html { background: transparent !important; margin: 0; }"
    " body > * { grid-template-columns: 1fr !important; }"
    " .stage { position: fixed !important; inset: 0 !important; background: transparent !important; }</style>"
)


ORDER = (
    "const mx = (r[i] + r[i + 2]) / 2 - cx, my = (r[i + 1] + r[i + 3]) / 2 - cy, mz = zm - cz;\n"
    "      items.push([mx * mx + my * my + mz * mz, layer, i]);"
)
ORDER_ISO = "items.push([cx * (cx > 0 ? r[i + 2] : r[i]) + cy * (cy > 0 ? r[i + 3] : r[i + 1]), layer, i]);"
SORT = "items.sort((a, b) => b[0] - a[0]);"
SORT_ISO = "items.sort((a, b) => (cz > 0 ? a[1].z0 - b[1].z0 : b[1].z1 - a[1].z1) || a[0] - b[0]);"


def snapshot_module():
    spec = importlib.util.spec_from_file_location("layout3d_snapshot", LAYOUT3D / "snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cell_gds(layout: kdb.Layout, cell: kdb.Cell, path: Path) -> None:
    """The cell alone, as its own top, in a GDS named for it (the export finds the top by name)."""
    out = kdb.Layout()
    out.dbu = layout.dbu
    target = out.create_cell(cell.name)
    target.copy_tree(cell)
    out.write(str(path))


def page(folder: Path, name: str, export: Path) -> Path:
    snapshot = snapshot_module()
    spec = {
        "block": name,
        "title": name,
        "heading": name,
        "chip": "",
        "focus_label": "",
        "tabs": [{"label": name, "note": "", "stats": [], "file": export.name}],
    }
    html = snapshot.build(folder, spec).read_text()
    for old, new in (
        (CAMERA, CAMERA_ISO),
        (RESIZE, RESIZE_ISO),
        (HOME, HOME_ISO),
        (FILL, FILL_ISO),
        (EDGE_WIDTH, EDGE_WIDTH_ISO),
        (EDGE_TINT, EDGE_TINT_ISO),
        (ORDER, ORDER_ISO),
        (SORT, SORT_ISO),
    ):
        if old not in html:
            raise SystemExit(f"render_layout3d: the 3-D page changed; cannot find {old[:50]!r}")
        html = html.replace(old, new, 1)
    out = folder / f"{name}_iso.html"
    out.write_text(HIDE + html)
    return out


def screenshot(html: Path, png: Path) -> None:
    browser = shutil.which("chromium-browser") or shutil.which("chromium") or "chromium-browser"
    subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            f"--window-size={SIZE[0]},{SIZE[1]}",
            "--virtual-time-budget=20000",
            f"--screenshot={png}",
            html.as_uri() + "#flat",
        ],
        check=True,
        capture_output=True,
    )
    crop(png)


def crop(png: Path, pad: int = 12) -> None:
    """The image cut to what is drawn (its non-transparent pixels), with a small margin."""
    import matplotlib.image as mpimg

    image = mpimg.imread(png)
    drawn = image[:, :, 3] > 0
    rows, cols = drawn.any(axis=1).nonzero()[0], drawn.any(axis=0).nonzero()[0]
    if len(rows) and len(cols):
        top, bottom = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, image.shape[0])
        left, right = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, image.shape[1])
        mpimg.imsave(png, image[top:bottom, left:right])


def main() -> None:
    gds, pdk, out, *wanted = sys.argv[1:]
    sys.path.insert(0, os.getcwd())  # the checkout whose kits the export reads
    from flow.web.export import export_layout

    layout = kdb.Layout()
    layout.read(gds)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for item in wanted:
            name, _, cell_name = item.partition("=")
            cell = layout.cell(cell_name) if cell_name else layout.top_cells()[0]
            cell_path = folder / f"{cell.name}.gds"
            cell_gds(layout, cell, cell_path)
            export = folder / f"{name}.json"
            export_layout(str(cell_path), pdk, str(export))
            png = out_dir / f"{name}.png"
            screenshot(page(folder, name, export), png)
            print(png, json.loads(export.read_text())["bbox"])


if __name__ == "__main__":
    main()
