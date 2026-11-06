"""The ADC's layouts: the fabricated FRIDA-1 ADC's four flavors extracted and signed off
(``frida1_*``); and the sweep's blocks side by side, unconnected, for the viewer
(``assemble_blocks``, ``layout_run``).

The FRIDA-1 layouts read their fabricated inputs under build/, not in the repository: the GDS
(``frida-1.gds``), each flavor's source netlist (``frida-1/<flavor>.src.net``) and its capacitor
array's LVS source (``frida-1/<array>.lvs.cdl``, the array's subcircuit with its MOM units as the
kit's LVS recognizes them, and ``frida-1/<array>.pins.json``, its pins to the fabricated macro's:
stage C0 is the macro's pin 15). The GDS gains MOM recognition only; nothing on a mask layer
changes. LVS reads the source netlist with the array's source swapped in, PEX the source netlist
without the array (its capacitors are extracted).

The blocks side by side, until OpenROAD and ALIGN place and route them together: the comparator,
the samplers and each side of the DAC as their sweeps laid them out (ALIGN): one side of capdac's
array of the converter's ``capdac.Params``, its drivers with it, as the behavioral model reads its
characterization, the N side its mirror image. Each block is outlined and labelled on the boundary
layer, which the viewer shows. Nothing is connected, so nothing is signed off.

    entry = assemble_blocks("tsmc65", params, run_dir / "layout")  # the record's layout entry
"""

from __future__ import annotations

import json
import re
import traceback
from importlib import import_module
from pathlib import Path
from typing import Literal

from klayout import db

from flow.layout.gdsdiff import gds_diff
from flow.layout.signoff import SignoffParams, run_signoff
from flow.sweep.runner import ROOT, RUNS_DIR, digest, instance_params, write_record
from flow.util.netlist import omit_subcircuit, replace_subcircuit

from .params import Params

# ---- the fabricated FRIDA-1 layouts, extracted and signed off


def _write_top(layout: db.Layout, top_cell: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top = layout.cell(top_cell)
    if top is None:
        raise ValueError(f"layout has no cell {top_cell!r}")
    options = db.SaveLayoutOptions()
    options.set_format_from_filename(str(path))
    options.add_cell(top.cell_index())
    layout.write(str(path), options)


def _frida1_sources(run_dir: Path, *, flavor: str, cap_cell: str) -> tuple[Path, Path]:
    """A FRIDA-1 flavor's LVS and PEX sources in ``run_dir``: its source netlist
    (``build/frida-1/<flavor>.src.net``), its top renamed ``adc_12b_17step``, with its capacitor
    array's LVS source swapped in (``build/frida-1/<cap_cell>.lvs.cdl``, each call reconnected by
    ``<cap_cell>.pins.json``) for LVS, and without the array for PEX."""
    inputs = ROOT / "build" / "frida-1"
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

    run_dir.mkdir(parents=True, exist_ok=False)
    pristine = db.Layout()
    pristine.read(str(ROOT / "build" / "frida-1.gds"))
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

    lvs_source, pex_source = _frida1_sources(run_dir, flavor=flavor, cap_cell=cap_cell)
    run_signoff(
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
        run_dir,
    )
    return run_dir


def frida1_1layer_radix17(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_1layer_radix17",
        source_layout_cell="adc",
        flavor="adc_1layer_radix17",
        cap_cell="caparray_1layer_radix17",
        unit_cell_prefix="capunit_1layer",
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_1layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_1layer_radix20",
        source_layout_cell="adc_0",
        flavor="adc_1layer_radix20",
        cap_cell="caparray_1layer_radix20",
        unit_cell_prefix="capunit_1layer",
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_2layer_radix17(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix17",
        source_layout_cell="adc_1",
        flavor="adc_2layer_radix17",
        cap_cell="caparray_2layer_radix17",
        unit_cell_prefix="capunit_2layer",
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def frida1_2layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix20",
        source_layout_cell="adc_2",
        flavor="adc_2layer_radix20",
        cap_cell="caparray_2layer_radix20",
        unit_cell_prefix="capunit_2layer",
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def all_adcs(run_dir: Path) -> Path:
    for target in (frida1_1layer_radix17, frida1_1layer_radix20, frida1_2layer_radix17, frida1_2layer_radix20):
        target(run_dir / target.__name__)
    return run_dir


# ---- the sweep's blocks side by side, unconnected, for the viewer

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


def sweep_gds(block: str, pdk: str, params) -> Path:
    """The layout of the instance of ``block``'s sweep with exactly these parameters (its digest),
    newest run first."""
    ident = digest(params)
    for path in sorted((RUNS_DIR / block).glob(f"*/{pdk}/{ident}/instance.json"), reverse=True):
        record = json.loads(path.read_text())
        gds = (record.get("layout") or {}).get("gds")
        if gds and (ROOT / gds).exists():
            return ROOT / gds
    raise FileNotFoundError(
        f"no laid-out instance of the {block} sweep in {pdk} with these parameters under {RUNS_DIR / block}: "
        f"run python -m flow {block}.sweep ({params})"
    )


def _copied(layout: db.Layout, gds: Path) -> db.Cell:
    """The GDS's top cell (the one named as the file, else the largest) copied into ``layout``."""
    source = db.Layout()
    source.read(str(gds))
    top = source.cell(gds.stem) or max(source.top_cells(), key=lambda cell: cell.bbox().area())
    cell = layout.create_cell(gds.stem)
    cell.copy_tree(top)
    return cell


def assemble_blocks(pdk: str, params: Params, out_dir: Path) -> dict:
    """The ADC's blocks in a row, unconnected, into ``out_dir/adc_blocks.gds``; its layout entry
    (as ``flow.sweep.runner.layout_job`` gives one, unsigned) with each block's place, orientation
    and source: each block as its sweep laid it out, the DAC's one side (capdac's, its drivers with
    it) twice, the second mirrored."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    layout = db.Layout()
    layout.dbu = tech.DBU
    top = layout.create_cell("adc_blocks")
    boundary = layout.layer(*tech.LAYERS["BND"])
    sources = {
        "comp": sweep_gds("comp", pdk, params.comp),
        "samp": sweep_gds("samp", pdk, params.samp),
        "cap": sweep_gds("capdac", pdk, params.cdac),
    }
    cells = {block: _copied(layout, gds) for block, gds in sources.items()}
    blocks, x = [], 0.0
    for name, block, mirrored in _ROW:
        # mirrored about the vertical axis, then moved: its left edge at x, centred on the row
        orientation = db.DTrans(db.DTrans.M90 if mirrored else db.DTrans.R0, 0.0, 0.0)
        box = cells[block].dbbox().transformed(orientation)
        shift = db.DTrans(x - box.left, -box.center().y)
        placed = box.transformed(shift)
        top.insert(db.DCellInstArray(cells[block].cell_index(), shift * orientation))
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
        x = placed.right + _GAP_UM
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
    """Each characterized instance of an ADC sweep run (``build/adc/<run>``) given its
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
