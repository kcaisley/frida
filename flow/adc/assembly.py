"""The ADC's blocks side by side in one layout, unconnected, for the viewer until OpenROAD and ALIGN
place and route them together: the comparator and the samplers as their sweeps laid them out
(ALIGN), the capacitor arrays as drawn for the extraction the behavioral model reads
(``flow.caparray.model``), and the generic-cell drivers (``flow.capdriver``) as their library's
standard cells in rows, a stage a row, unrouted and unlabelled. Each block is outlined and
labelled on the boundary layer, which the viewer shows. Nothing is connected, so nothing is signed
off.

    entry = assemble_blocks("tsmc65", params, run_dir / "layout")  # the record's layout entry
"""

from __future__ import annotations

import json
import traceback
from importlib import import_module
from pathlib import Path

from klayout import db

from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import CapArrayConfig, get_caparray_weights
from flow.capdriver.subckt import PARALLEL_DRIVE, CapDriverParams, Cells, pre_driver, stage_strengths
from flow.cdac.subckt import driver_strengths
from flow.sweep.runner import ROOT, SWEEP_DIR, digest, instance_params, write_record

from .subckt import AdcParams

GAP_UM = 4.0  # between neighbouring blocks
# left to right: (instance, block); each side's array, its main and difference drivers, its sampler
ROW = (
    ("cap_p", "cap"),
    ("drv_p_main", "drv"),
    ("drv_p_diff", "drv"),
    ("samp_p", "samp"),
    ("comp", "comp"),
    ("samp_n", "samp"),
    ("drv_n_diff", "drv"),
    ("drv_n_main", "drv"),
    ("cap_n", "cap"),
)


def _path(path: Path) -> str:
    """A path as records hold it: from the repository root where it is under it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def sweep_gds(block: str, pdk: str, params) -> Path:
    """The layout of the instance of ``block``'s sweep with exactly these parameters (its digest),
    newest run first."""
    ident = digest(params)
    for path in sorted((SWEEP_DIR / block).glob(f"*/{pdk}/{ident}/instance.json"), reverse=True):
        record = json.loads(path.read_text())
        gds = (record.get("layout") or {}).get("gds")
        if gds and (ROOT / gds).exists():
            return ROOT / gds
    raise FileNotFoundError(
        f"no laid-out instance of the {block} sweep in {pdk} with these parameters under {SWEEP_DIR / block}: "
        f"run python -m flow {block}.sweep ({params})"
    )


def caparray_gds(pdk: str, cdac: CapArrayConfig) -> Path:
    """The array drawn for the extraction the behavioral model reads."""
    table = CapArrayModel.of(pdk, cdac).table  # a LookupError where the array is not extracted
    gds = next(table.parent.glob("caparray_*.gds"), None)
    if gds is None:
        raise FileNotFoundError(f"no array GDS beside {table}")
    return gds


def _copied(layout: db.Layout, gds: Path) -> db.Cell:
    """The GDS's top cell (the one named as the file, else the largest) copied into ``layout``."""
    source = db.Layout()
    source.read(str(gds))
    top = source.cell(gds.stem) or max(source.top_cells(), key=lambda cell: cell.bbox().area())
    cell = layout.create_cell(gds.stem)
    cell.copy_tree(top)
    return cell


def _driver(layout: db.Layout, pdk: str, cdac: CapArrayConfig, boundary: int) -> db.Cell:
    """One side's main or difference driver: each stage's XOR and buffers (the drives its plates
    call for, ``flow.cdac.subckt.driver_strengths``), C0's row at the bottom, every other row
    flipped so the rails abut."""
    library = db.Layout()
    library.read(str(import_module(f"pdk.{pdk}.layout.paths").STD_GDS))
    generic = import_module(f"pdk.{pdk}.hdl21.cells").GENERIC
    params = CapDriverParams(
        n_stages=len(get_caparray_weights(cdac)), strengths=driver_strengths(pdk, cdac), cells=Cells.GENERIC
    )
    driver = layout.create_cell("capdriver")
    cells: dict[str, db.Cell] = {}
    y = 0.0
    for row, strength in enumerate(stage_strengths(params)):
        x, height = 0.0, 0.0
        if strength > PARALLEL_DRIVE:
            # a pre-driver and k buffers of 16
            buffers = (f"buf_x{pre_driver(strength)}", *(f"buf_x{PARALLEL_DRIVE}",) * (strength // PARALLEL_DRIVE))
        else:
            buffers = (f"buf_x{strength}",) if strength > 1 else ()
        for name in ("xor2_x1", *buffers):
            cell_name = generic[name][0]
            if cell_name not in cells:
                cells[cell_name] = layout.create_cell(cell_name)
                cells[cell_name].copy_tree(library.cell(cell_name))
                for layer in layout.layer_indexes():  # its pin names and notices: unrouted, they only crowd the view
                    cells[cell_name].shapes(layer).clear(db.Shapes.STexts)
            cell = cells[cell_name]
            box = cell.dbbox_per_layer(boundary)  # the cell's placement boundary
            if row % 2:  # mirrored about the x axis, its top edge on the row's bottom
                place = db.DTrans(db.DTrans.M0, x - box.left, y + box.top)
            else:
                place = db.DTrans(x - box.left, y - box.bottom)
            driver.insert(db.DCellInstArray(cell.cell_index(), place))
            x, height = x + box.width(), max(height, box.height())
        y += height
    return driver


def assemble_blocks(pdk: str, params: AdcParams, out_dir: Path) -> dict:
    """The ADC's blocks in a row, unconnected, into ``out_dir/adc_blocks.gds``; its layout entry
    (as ``flow.sweep.runner.layout_job`` gives one, unsigned) with each block's place and source.
    The drivers are left out where the PDK's standard-cell GDS is not installed."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    layout = db.Layout()
    layout.dbu = tech.DBU
    top = layout.create_cell("adc_blocks")
    boundary = layout.layer(*tech.LAYERS["BND"])
    sources = {
        "comp": sweep_gds("comp", pdk, params.comp),
        "samp": sweep_gds("samp", pdk, params.samp),
        "cap": caparray_gds(pdk, params.cdac),
    }
    cells = {block: _copied(layout, gds) for block, gds in sources.items()}
    standard = import_module(f"pdk.{pdk}.layout.paths").STD_GDS
    if standard.exists():
        cells["drv"] = _driver(layout, pdk, params.cdac, boundary)
        sources["drv"] = standard
    blocks, x = [], 0.0
    for name, block in ROW:
        if block not in cells:
            continue
        box = cells[block].dbbox()
        placed = box.moved(x - box.left, -box.center().y)  # centred on the row
        top.insert(db.DCellInstArray(cells[block].cell_index(), db.DTrans(x - box.left, -box.center().y)))
        top.shapes(boundary).insert(placed)
        top.shapes(boundary).insert(db.DText(name, placed.center().x, placed.top + 1.0))
        blocks.append(
            {
                "name": name,
                "source": _path(sources[block]),
                "x_um": round(placed.left, 3),
                "y_um": round(placed.bottom, 3),
                "w_um": round(placed.width(), 3),
                "h_um": round(placed.height(), 3),
            }
        )
        x = placed.right + GAP_UM
    out_dir.mkdir(parents=True, exist_ok=True)
    gds = out_dir / "adc_blocks.gds"
    layout.write(str(gds))
    box = top.dbbox()
    return {
        "gds": _path(gds),
        "w_um": box.width(),
        "h_um": box.height(),
        "drc_violations": None,
        "lvs_correct": None,
        "error": None,
        "blocks": blocks,
    }


def layout_run(run_dir: Path) -> None:
    """Each characterized instance of an ADC sweep run (``build/sweep/adc/<run>``) given its
    blocks' layout entry in its ``instance.json``, which the viewer's table exports."""
    for path in sorted(run_dir.glob("*/*/instance.json")):
        record = json.loads(path.read_text())
        if record["error"] is not None:
            continue
        try:
            adc = instance_params("adc", record["pdk"], path.parent.name)
            record["layout"] = assemble_blocks(record["pdk"], adc, path.parent / "layout")
        except Exception:  # noqa: BLE001 - every instance reports its own failure
            record["layout"] = {"error": traceback.format_exc(limit=4)[-2000:]}
        write_record(path, record)
