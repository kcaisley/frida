"""The ADC's own layout flow (``lay_out``, which the layout step runs in place of ALIGN's,
docs/pipeline.md): a fabricated FRIDA-1 converter's tape-out layout, its signoff and extraction
planned; any other converter's blocks side by side, unconnected, until OpenROAD and ALIGN place and
route them together.

A fabricated converter (``Params.fabricated``, one of ``Fabricated``) is laid out from its tape-out's
inputs, the TSMC65 kit's ``site.FRIDA1`` folder, not the repository: the chip's GDS (``frida-1.gds``,
each flavor its own cell), each flavor's source netlist (``<flavor>.src.net``) and its capacitor
array's LVS source (``<array>.lvs.cdl``, the array's subcircuit with its MOM units as the kit's LVS
recognizes them, and ``<array>.pins.json``, its pins to the fabricated macro's: stage C0 is the
macro's pin 15). The GDS gains MOM recognition only; nothing on a mask layer changes. LVS reads the
source netlist with the array's source swapped in, PEX the source netlist without the array (its
capacitors are extracted). ``lay_out`` plans its signoff (``flow.layout.signoff.write_plan``:
``signoff.json``, its sources, its LVS expectation and the kit's Calibre options and waivers), which
the drc, lvs and pex steps run, each in its own folder: LVS correct for the one-layer flavors, the
historical disconnected MOM layer of the two-layer ones accepted.

Any other converter's blocks side by side: the comparator, the samplers and each side of the DAC as
their own layouts laid them out (``flow.sweep.lookup.laid_out``, by their parameters): one side of
capdac's array of the converter's ``capdac.Params``, its drivers with it, the N side its mirror
image. Each block is outlined and labelled on the boundary layer, which the viewer shows, and its
place written beside the GDS (``blocks.json``). Nothing is connected, so DRC alone signs it off.

    gds = lay_out(params, "tsmc65", run_dir)  # python -m flow --block adc --run <name> --to layout
"""

from __future__ import annotations

import json
import re
from importlib import import_module
from pathlib import Path
from typing import Literal

from klayout import db

from flow.layout.gdsdiff import gds_diff
from flow.layout.signoff import SignoffParams, write_plan
from flow.sweep.lookup import laid_out
from flow.sweep.runner import ROOT
from flow.util.netlist import omit_subcircuit, replace_subcircuit

from .params import Fabricated, Params


def lay_out(params: Params, pdk: str, run_dir: Path) -> Path:
    """The converter ``params`` laid out in ``pdk`` into ``run_dir``, its GDS: a fabricated one's
    tape-out layout, its signoff planned (``_fabricated``); any other's blocks side by side
    (``_assemble``)."""
    if params.fabricated is not None:
        return _fabricated(params.fabricated, pdk, run_dir)
    return _assemble(params, pdk, run_dir)


# ---- the fabricated FRIDA-1 layouts, their signoff planned


def _write_top(layout: db.Layout, top_cell: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top = layout.cell(top_cell)
    if top is None:
        raise ValueError(f"layout has no cell {top_cell!r}")
    options = db.SaveLayoutOptions()
    options.set_format_from_filename(str(path))
    options.add_cell(top.cell_index())
    layout.write(str(path), options)


def _frida1_sources(run_dir: Path, inputs: Path, *, flavor: str, cap_cell: str) -> tuple[Path, Path]:
    """A FRIDA-1 flavor's LVS and PEX sources in ``run_dir``: its source netlist
    (``inputs/<flavor>.src.net``, the kit's ``site.FRIDA1``), its top renamed ``adc_12b_17step``,
    with its capacitor array's LVS source swapped in (``inputs/<cap_cell>.lvs.cdl``, each call
    reconnected by ``<cap_cell>.pins.json``) for LVS, and without the array for PEX."""
    reference = (inputs / f"{flavor}.src.net").read_text(encoding="utf-8")
    pins = json.loads((inputs / f"{cap_cell}.pins.json").read_text(encoding="utf-8"))
    lvs_source = run_dir / "source.lvs.cdl"
    lvs_source.write_text(
        replace_subcircuit(
            reference,
            old_top=flavor,
            new_top="adc_12b_17step",
            old_block=cap_cell,
            new_block=(inputs / f"{cap_cell}.lvs.cdl").read_text(encoding="utf-8"),
            pin_map=pins,
        ),
        encoding="utf-8",
    )
    pex_source = run_dir / "source.pex.cdl"
    pex_source.write_text(
        re.sub(
            rf"(?im)(^\s*\.subckt\s+){re.escape(flavor)}(?=\s|$)",
            r"\g<1>adc_12b_17step",
            omit_subcircuit(reference, cap_cell),
            count=1,
        ),
        encoding="utf-8",
    )
    return lvs_source, pex_source


def _run_frida1(
    run_dir: Path,
    inputs: Path,
    *,
    target_name: str,
    source_layout_cell: str,
    flavor: str,
    cap_cell: str,
    unit_cell_prefix: str,
    active_layers: tuple[int, ...],
    lvs_expectation: Literal["correct", "incorrect"],
) -> Path:
    # the kit's signoff, imported here: the module loads without the kit
    from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, UPPER_DENSITY_WAIVERS, SignoffOptions, add_mom_recognition

    run_dir.mkdir(parents=True, exist_ok=True)
    pristine = db.Layout()
    pristine.read(str(inputs / "frida-1.gds"))
    source_top = pristine.cell(source_layout_cell)
    if source_top is None:
        raise ValueError(f"FRIDA-1 GDS has no cell {source_layout_cell!r}")
    source_top.name = "adc_12b_17step"
    pristine_gds = run_dir / "pristine.gds"
    _write_top(pristine, "adc_12b_17step", pristine_gds)

    annotated = pristine.dup()
    add_mom_recognition(
        annotated,
        unit_cell_prefix=unit_cell_prefix,
        shield_layer=5,
        active_layers=active_layers,
    )
    gds_path = run_dir / f"{target_name}.gds"
    _write_top(annotated, "adc_12b_17step", gds_path)
    diff_summary = gds_diff(
        pristine_gds,
        gds_path,
        run_dir / "recognition_only_diff.gds",
        old_top="adc_12b_17step",
        new_top="adc_12b_17step",
    )
    changed = {layer for layer, areas in diff_summary["layers"].items() if areas["old_only"] or areas["new_only"]}
    if any(not layer.startswith("155/") for layer in changed):
        raise RuntimeError(f"historical annotation changed mask geometry on {sorted(changed)}")
    (run_dir / "recognition_only_diff.json").write_text(json.dumps(diff_summary, indent=2) + "\n", encoding="utf-8")

    lvs_source, pex_source = _frida1_sources(run_dir, inputs, flavor=flavor, cap_cell=cap_cell)
    write_plan(
        SignoffParams(
            technology="tsmc65",
            gds_path=gds_path,
            layout_top="adc_12b_17step",
            lvs_source_path=lvs_source,
            source_top="adc_12b_17step",
            output_stem=target_name,
            pex_source_path=pex_source,
            lvs_expectation=lvs_expectation,
            lvs_required_report_fragments=(
                "Error:    Different numbers of nets.",
                "Error:    Connectivity errors.",
                "vdac_p",
                "vdac_n",
                "frida_mom_m7_s5",
            )
            if lvs_expectation == "incorrect"
            else (),
            pdk_options=SignoffOptions(
                gdscheck_suite="adc",
                drc_unselect_checks=BLOCK_WAIVERS + UPPER_DENSITY_WAIVERS,
                mom_shield_layer=5,
                mom_active_layers=active_layers,
            ),
        ),
        run_dir / "signoff.json",
    )
    return gds_path


def _fabricated(member: Fabricated, pdk: str, run_dir: Path) -> Path:
    """A fabricated converter's tape-out layout, its signoff planned (``_run_frida1``) from the
    kit's tape-out inputs (``site.FRIDA1``): its flavor's cell of the chip's GDS (the one-layer
    radix-17 converter ``adc``, then ``adc_0`` to ``adc_2`` in the order of ``Fabricated``), its
    source netlist, array and MOM unit cells by its layers and radix, its MOM units on metal 6 (and
    7, two layers), LVS correct with one layer; ``<member>.gds``, the member's name in lower case."""
    layers, radix = member.layers, member.radix
    match member:
        case Fabricated.FRIDA1_1LAYER_RADIX17:
            cell = "adc"
        case Fabricated.FRIDA1_1LAYER_RADIX20:
            cell = "adc_0"
        case Fabricated.FRIDA1_2LAYER_RADIX17:
            cell = "adc_1"
        case Fabricated.FRIDA1_2LAYER_RADIX20:
            cell = "adc_2"
    return _run_frida1(
        run_dir,
        import_module(f"pdk.{pdk}.hdl21.site").FRIDA1,
        target_name=member.name.lower(),
        source_layout_cell=cell,
        flavor=f"adc_{layers}layer_radix{radix}",
        cap_cell=f"caparray_{layers}layer_radix{radix}",
        unit_cell_prefix=f"capunit_{layers}layer",
        active_layers=(6,) if layers == 1 else (6, 7),
        lvs_expectation="correct" if layers == 1 else "incorrect",
    )


# ---- any other converter's blocks side by side, unconnected

_GAP_UM = 4.0  # between neighbouring blocks
# left to right: (instance, block, mirrored); each side's DAC, its drivers with it, then its sampler;
# the N side's DAC the P side's mirror image about the vertical axis, each side's seam (its last
# stage) toward the comparator
_ROW = (
    ("cap_p", "cap", False),
    ("samp_p", "samp", False),
    ("comp", "comp", False),
    ("samp_n", "samp", False),
    ("cap_n", "cap", True),
)


def _path(path: Path) -> str:
    """A path as records hold it: from the repository root where it is under it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _copied(layout: db.Layout, gds: Path) -> db.Cell:
    """The GDS's top cell (the one named as the file, else the largest) copied into ``layout``."""
    source = db.Layout()
    source.read(str(gds))
    top = source.cell(gds.stem) or max(source.top_cells(), key=lambda cell: cell.bbox().area())
    cell = layout.create_cell(gds.stem)
    cell.copy_tree(top)
    return cell


def _assemble(params: Params, pdk: str, run_dir: Path) -> Path:
    """The converter's blocks in a row, unconnected, into ``run_dir/adc_blocks.gds``: each block as its
    own layout laid it out (``flow.sweep.lookup.laid_out``), the DAC's one side (capdac's, its drivers
    with it) twice, the second mirrored; each block's place, orientation and source in
    ``run_dir/blocks.json``."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    layout = db.Layout()
    layout.dbu = tech.DBU
    top = layout.create_cell("adc_blocks")
    boundary = layout.layer(*tech.LAYERS["BND"])
    sources = {
        block: ROOT / laid_out(name, pdk, part)["gds"]
        for block, name, part in (
            ("comp", "comp", params.comp),
            ("samp", "samp", params.samp),
            ("cap", "capdac", params.cdac),
        )
    }
    cells = {block: _copied(layout, gds) for block, gds in sources.items()}
    # in database units, each offset a multiple of the manufacturing grid: a block centred on the row
    # at half a grid step would move every one of its shapes off the grid
    grid = tech.MFG_GRID
    blocks, x = [], 0
    for name, block, mirrored in _ROW:
        # mirrored about the vertical axis, then moved: its left edge at x, centred on the row
        orientation = db.Trans(db.Trans.M90 if mirrored else db.Trans.R0, 0, 0)
        box = cells[block].bbox().transformed(orientation)
        dx, dy = x - box.left, -(box.bottom + box.top) / 2
        shift = db.Trans(round(dx / grid) * grid, round(dy / grid) * grid)
        top.insert(db.CellInstArray(cells[block].cell_index(), shift * orientation))
        placed = box.transformed(shift).to_dtype(layout.dbu)
        top.shapes(boundary).insert(placed)
        top.shapes(boundary).insert(db.DText(name, placed.center().x, placed.top + 1.0))
        blocks.append(
            {
                "name": name,
                "source": _path(sources[block]),
                "mirrored": mirrored,
                "x_um": round(placed.left, 3),
                "y_um": round(placed.bottom, 3),
                "w_um": round(placed.width(), 3),
                "h_um": round(placed.height(), 3),
            }
        )
        x = box.transformed(shift).right + round(_GAP_UM / tech.DBU)
    run_dir.mkdir(parents=True, exist_ok=True)
    gds = run_dir / "adc_blocks.gds"
    layout.write(str(gds))
    (run_dir / "blocks.json").write_text(json.dumps(blocks, indent=1) + "\n")
    return gds
