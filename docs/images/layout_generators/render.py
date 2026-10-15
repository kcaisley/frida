"""Render the layout images of the layout-generator deck (docs/slides/2026_10_13_layout_generators.tex).

Run from the repository root after the comparator layout targets have run (flow/comp/layout.py,
on a host with ALIGN and Calibre; the runs it reads are pinned below):

    uv run python docs/images/layout_generators/render.py

The layout renders show PDK layouts (and library cells), so they are build outputs, written to
build/docs/layout_generators/ and never committed; the deck reads them from there. The schematics
(no layout) are written here. Inputs are the runner's outputs under build/layout/comp; the ALIGN
automatic-placement and guard-ring variants come from build/layout/deck (flow/layout/align/build.py
``build`` without a floorplan, and with ``post=PostOptions(fill="decap", ring=True)`` for the
ring). Each library cell shown alone is copied into a
GDS of its own first, so gds2image renders it as a top cell. The schematics are
flow/util/netlist2image.py's SVGs of the TSMC65 transistor netlists, converted with rsvg-convert.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import klayout.db as kdb

from flow.util.gds2image import render_png

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent  # the schematics
RUNS = ROOT / "build/layout/comp"
# the runs this deck shows: python -m flow.comp.layout <target>, one directory per PDK in each
RUN = {
    "comp_frida1": RUNS / "comp_frida1_manual_all_pdks/20261014_221027",
    "comp_c040": RUNS / "comp_c040_manual_all_pdks/20261014_221027",
    "mos_inv": RUNS / "mos_inv_all_pdks/20261014_221027",
}
CELLS = ROOT / "build/docs/layout_generators"  # the renders and the cells they show
PDKS = ("tsmc65", "ihp130", "tower180", "tsmc28", "lf150", "tpsc65")


def cell_gds(lib: Path, name: str) -> Path:
    """One cell of a library GDS as the top cell of its own file."""
    src = kdb.Layout()
    src.read(str(lib))
    dst = kdb.Layout()
    dst.dbu = src.dbu
    dst.create_cell(name).copy_tree(src.cell(name))
    path = CELLS / f"{lib.stem}_{name}.gds"
    path.parent.mkdir(parents=True, exist_ok=True)
    dst.write(str(path))
    return path


def tools(design: str, pdk: str = "tsmc65", prefix: str = "") -> list[tuple[Path, str]]:
    return [
        (RUN[design] / f"{pdk}/cic/{design}/{design}.gds", f"{prefix}cIcCreator"),
        (RUN[design] / f"{pdk}/laygo/{design}.gds", f"{prefix}laygo"),
        (RUN[design] / f"{pdk}/align/{design}/{design}.gds", f"{prefix}ALIGN"),
    ]


lib = RUN["comp_frida1"] / "tsmc65/cic/comp_frida1/comp_frida1_cells.gds"
render_png(
    [
        (cell_gds(lib, "Mdiff_p"), "NMOS 4.38/0.3"),
        (cell_gds(lib, "Mtail"), "NMOS 0.6/0.78"),
        (cell_gds(lib, "Mrst_p"), "PMOS 1/0.06"),
        (cell_gds(lib, "Mcross_init_p_a"), "PMOS 2.01/1.02"),
    ],
    CELLS / "primitives_devices.png",
    metals="solid",
)
render_png(
    [
        (cell_gds(lib, "Xdecision_n"), "Inverter, drive 1"),
        (cell_gds(lib, "Xsr_p"), "NOR2, drive 2"),
        (cell_gds(lib, "Xbuf2_outp"), "Inverter, drive 8"),
        (cell_gds(lib, "edge_600"), "Row end"),
        (cell_gds(lib, "fill_200"), "Filler"),
    ],
    CELLS / "primitives_cells.png",
    metals="solid",
)
render_png(tools("mos_inv"), CELLS / "mos_inv_tools.png", metals="solid")
for design in ("comp_frida1", "comp_c040"):
    render_png(tools(design), CELLS / f"{design}_tools.png", metals="solid")
PDK_NAMES = {
    "tsmc65": "TSMC 65",
    "ihp130": "IHP 130",
    "tower180": "Tower 180",
    "tsmc28": "TSMC 28",
    "lf150": "LFoundry 150",
    "tpsc65": "TPSCo 65",
}
for design in ("comp_frida1", "comp_c040"):  # the floorplanned layouts: one row per PDK, three tools each
    for pdk in PDKS:
        render_png(
            tools(design, pdk, f"{PDK_NAMES[pdk]} "), CELLS / f"{design}_{pdk}_tools.png", tech=pdk, metals="solid"
        )
for pdk in PDKS:  # one image each, in its own palette, untitled: the slide scales them by their widths
    render_png(
        [(RUN["comp_c040"] / f"{pdk}/cic/comp_c040/comp_c040.gds", None)],
        CELLS / f"cross_pdk_{pdk}.png",
        tech=pdk,
        metals="solid",
        titles=False,
    )
for design in ("comp_frida1", "comp_c040"):
    svg = CELLS / f"schematic_{design}.svg"
    netlist = RUN[design] / f"tsmc65/netlist/{design}_transistors.sp"
    subprocess.run(["uv", "run", "python", "-m", "flow.util.netlist2image", str(netlist), str(svg)], check=True)
    subprocess.run(["rsvg-convert", "-f", "pdf", str(svg), "-o", str(OUT / f"schematic_{design}.pdf")], check=True)
render_png(
    [(ROOT / f"build/layout/deck/{design}_free.gds", None) for design in ("comp_frida1", "comp_c040")],
    CELLS / "align_free.png",
    metals="solid",
    titles=False,
)
render_png(
    [(ROOT / "build/layout/deck/comp_c040_ring.gds", None)],
    CELLS / "align_ring.png",
    metals="solid",
    titles=False,
)
