"""The ADC's layouts: the named FRIDA-1 and FRIDA-2 ADC layouts, generated and signed off
(``frida1_*``, ``frida2_*``, ``all_adcs``); the technology-neutral block replacement FRIDA-2's are
assembled with (``AdcLayout``: compatible prebuilt blocks swapped into a template, connectivity
verified by LVS); and the sweep's blocks side by side, unconnected, for the viewer
(``assemble_blocks``, ``layout_run``).

The FRIDA layouts read their fabricated inputs under build/, not in the repository: FRIDA-1's GDS
(``frida-1.gds``) and its four flavors' source netlists (``frida-1/<flavor>.src.net``), and
FRIDA-2's template (``frida-2-template-c0.gds`` and ``.cdl``).

The blocks side by side, until OpenROAD and ALIGN place and route them together: the comparator and
the samplers as their sweeps laid them out (ALIGN), the capacitor arrays as drawn for the
extraction the behavioral model reads (``flow.cdac.caparray.model``), and the generic-cell drivers
(``flow.cdac.capdriver``) as their library's standard cells in rows, a stage a row, unrouted and
unlabelled. Each block is outlined and labelled on the boundary layer, which the viewer shows.
Nothing is connected, so nothing is signed off.

    entry = assemble_blocks("tsmc65", params, run_dir / "layout")  # the record's layout entry
"""

from __future__ import annotations

import io
import json
import re
import traceback
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Literal

import hdl21 as h
from klayout import db

from flow.cdac.caparray.layout import CapArrayLayout, CapArrayLayoutParams, UnitLengthCapFamilyParams, mom_array_params
from flow.cdac.caparray.model import CapArrayModel
from flow.cdac.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams, get_caparray_weights
from flow.cdac.capdriver.model import driver_strengths
from flow.cdac.capdriver.subckt import PARALLEL_DRIVE, CapDriverParams, Cells, pre_driver, stage_strengths
from flow.layout.gdsdiff import gds_diff
from flow.layout.signoff import SignoffParams, run_signoff
from flow.sweep.runner import ROOT, RUNS_DIR, digest, instance_params, write_record
from flow.util.netlist import omit_subcircuit, replace_subcircuit

from .params import Params

# ---- block replacement: compatible prebuilt blocks swapped into a template (FRIDA-2's), the
# assembled layout's connectivity verified by LVS


@dataclass(frozen=True)
class AdcLayoutParams:
    """Parameters for assembling prebuilt ADC layout blocks."""

    top_cell: str


def is_valid_adc_layout_params(params: AdcLayoutParams) -> bool:
    """Return whether an ADC assembly parameter set is valid."""

    return isinstance(params.top_cell, str) and bool(params.top_cell.strip())


def _calc_interface_signature(layout: db.Layout, cell: db.Cell) -> tuple[object, ...]:
    """Describe named terminals and footprint, not their annotation locations.

    One conductor may have several labels, or a label on another layer of its
    via stack. Neither determines whether parent routing actually connects.
    Complete assembled-layout DRC/LVS is mandatory before accepting PEX.
    """

    pins = {
        shape.text.string
        for layer_index in layout.layer_indices()
        for shape in cell.shapes(layer_index).each()
        if shape.is_text()
    }
    boundary = cell.bbox()
    boundary_signature = () if boundary.empty() else (boundary.left, boundary.bottom, boundary.right, boundary.top)
    return tuple(sorted(pins)), boundary_signature


def AdcLayout(
    params: AdcLayoutParams,
    *,
    template: db.Layout,
    replacements: dict[str, db.Layout],
) -> db.Layout:
    """Replace compatible direct child blocks without moving or editing them.

    Each replacement layout must contain exactly one top cell with pins and a
    boundary; unreferenced unit-library cells are ignored. The block's database
    unit, terminal-name set, and boundary must match the template cell. Marker
    positions, layers, shapes, and duplicate labels may differ. This is not an
    electrical compatibility verdict: the runner must sign off the complete
    assembled layout. Instance transforms are preserved verbatim.
    """

    if not is_valid_adc_layout_params(params):
        raise ValueError(f"Invalid ADC layout params: {params}")
    if not replacements:
        raise ValueError("ADC assembly requires at least one replacement")
    source_top = template.cell(params.top_cell)
    if source_top is None or source_top not in template.top_cells():
        raise ValueError(f"template has no top cell {params.top_cell!r}")

    output = template.dup()
    top = output.cell(params.top_cell)
    if top is None:
        raise RuntimeError("duplicated template lost its requested top cell")

    for placeholder_name, replacement_layout in replacements.items():
        if not placeholder_name:
            raise ValueError("replacement placeholder names must be nonempty")
        replacement_tops = [
            cell for cell in replacement_layout.top_cells() if all(_calc_interface_signature(replacement_layout, cell))
        ]
        if len(replacement_tops) != 1:
            raise ValueError(
                f"replacement for {placeholder_name!r} must have exactly one top cell with pins and a boundary; "
                f"found {[cell.name for cell in replacement_tops]}"
            )
        replacement_source = replacement_tops[0]
        if replacement_layout.dbu != output.dbu:
            raise ValueError(f"replacement {replacement_source.name!r} uses a different database unit")
        placeholder = output.cell(placeholder_name)
        if placeholder is None:
            raise ValueError(f"template has no placeholder cell {placeholder_name!r}")

        instances = [instance for instance in top.each_inst() if instance.cell_index == placeholder.cell_index()]
        if not instances:
            raise ValueError(f"top cell has no direct {placeholder_name!r} instances")
        if _calc_interface_signature(output, placeholder) != _calc_interface_signature(
            replacement_layout, replacement_source
        ):
            raise ValueError(
                f"replacement {replacement_source.name!r} is not pin-and-boundary compatible with {placeholder_name!r}"
            )

        imported = output.create_cell(f"__replacement_{placeholder_name}")
        imported.copy_tree(replacement_source)
        transforms = tuple(instance.trans for instance in instances)
        for instance in instances:
            instance.cell_index = imported.cell_index()
        if tuple(instance.trans for instance in instances) != transforms:
            raise RuntimeError(f"replacement changed a {placeholder_name!r} instance transform")
        output.delete_cell(placeholder.cell_index())
        imported.name = replacement_source.name

    return output


# ---- the named FRIDA-1 and FRIDA-2 layouts, generated and signed off


def _write_top(layout: db.Layout, top_cell: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top = layout.cell(top_cell)
    if top is None:
        raise ValueError(f"layout has no cell {top_cell!r}")
    options = db.SaveLayoutOptions()
    options.set_format_from_filename(str(path))
    options.add_cell(top.cell_index())
    layout.write(str(path), options)


def _run_frida1(
    run_dir: Path,
    *,
    target_name: str,
    source_layout_cell: str,
    source_netlist: Path,
    source_netlist_top: str,
    cap_cell: str,
    unit_cell_prefix: str,
    cdac: CapArrayConfig,
    active_layers: tuple[int, ...],
    lvs_expectation: Literal["correct", "incorrect"],
) -> Path:
    # the kit's signoff, imported here: the module loads without the kit
    from pdk.tsmc65.calibre.signoff import (
        BLOCK_WAIVERS,
        UPPER_DENSITY_WAIVERS,
        SignoffOptions,
        add_mom_recognition,
        mom_lvs_device,
    )

    run_dir.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[2]
    pristine = db.Layout()
    pristine.read(str(repository / "build" / "frida-1.gds"))
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

    array = CapArray(
        CapArrayParams(
            cdac=cdac,
            active_layers=active_layers,
            unit_models=tuple(mom_lvs_device(layer, 5) for layer in active_layers),
        )
    )
    array.name = cap_cell
    block_source = io.StringIO()
    h.netlist(array, block_source, fmt="spice")
    # The immutable fabricated-macro boundary maps stage C0 to physical pin 15.
    legacy_pins = {name: name for name in array.ports}
    count = len(get_caparray_weights(cdac))
    legacy_pins.update(
        {
            array.ports[f"cap_botplate_{kind}<{stage}>"].name: array.ports[
                f"cap_botplate_{kind}<{count - 1 - stage}>"
            ].name
            for kind in ("main", "diff")
            for stage in range(count)
        }
    )
    reference = source_netlist.read_text(encoding="utf-8")
    lvs_source = run_dir / "source.lvs.cdl"
    lvs_source.write_text(
        replace_subcircuit(
            reference,
            old_top=source_netlist_top,
            new_top="adc_12b_17step",
            old_block=cap_cell,
            new_block=block_source.getvalue(),
            pin_map=legacy_pins,
        ),
        encoding="utf-8",
    )
    pex_source = run_dir / "source.pex.cdl"
    pex_source.write_text(
        re.sub(
            rf"(?im)(^\s*\.subckt\s+){re.escape(source_netlist_top)}(?=\s|$)",
            r"\g<1>adc_12b_17step",
            omit_subcircuit(reference, cap_cell),
            count=1,
        ),
        encoding="utf-8",
    )
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


def _run_frida2(run_dir: Path, *, target_name: str, params: CapArrayLayoutParams) -> Path:
    # the kit's ring-MOM library and signoff, imported here: the module loads without the kit
    from pdk.tsmc65.calibre.ringfmom import LIBRARY
    from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, UPPER_DENSITY_WAIVERS, SignoffOptions

    run_dir.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[2]
    template = db.Layout()
    template.read(str(repository / "build" / "frida-2-template-c0.gds"))
    replacement = CapArrayLayout(params)
    adc_params = AdcLayoutParams(top_cell="adc_12b_17step")
    if not is_valid_adc_layout_params(adc_params):
        raise ValueError("invalid FRIDA-2 assembly parameters")
    layout = AdcLayout(
        adc_params,
        template=template,
        replacements={"caparray_2layer_radix17": replacement},
    )
    gds_path = run_dir / f"{target_name}.gds"
    _write_top(layout, adc_params.top_cell, gds_path)

    reference_path = repository / "build" / "frida-2-template-c0.cdl"
    reference = reference_path.read_text(encoding="utf-8")
    array = CapArray(mom_array_params(params))
    array.name = params.top_cell
    (run_dir / "ringfmom.cdl").write_text(LIBRARY.read_text(), encoding="utf-8")
    block_source = io.StringIO()
    block_source.write('.INCLUDE "ringfmom.cdl"\n')
    h.netlist(array, block_source, fmt="spice")
    # The paired template/source labels already use chronological C0-first
    # indexing throughout the digital, driver, and capacitor hierarchy.
    lvs_source = run_dir / "source.lvs.cdl"
    lvs_source.write_text(
        replace_subcircuit(
            reference,
            old_top=adc_params.top_cell,
            new_top=adc_params.top_cell,
            old_block="caparray_2layer_radix17",
            new_block=block_source.getvalue(),
            pin_map={name: name for name in array.ports},
        ),
        encoding="utf-8",
    )
    pex_source = run_dir / "source.pex.cdl"
    pex_source.write_text(
        omit_subcircuit(reference, "caparray_2layer_radix17"),
        encoding="utf-8",
    )
    # Same authored capacitors for ideal simulation and LVS; PEX omits them.
    (run_dir / "source.ideal.cdl").write_text(lvs_source.read_text(), encoding="utf-8")
    run_signoff(
        SignoffParams(
            technology="tsmc65",
            gds_path=gds_path,
            layout_top=adc_params.top_cell,
            lvs_source_path=lvs_source,
            source_top=adc_params.top_cell,
            output_stem=target_name,
            pex_source_path=pex_source,
            pdk_options=SignoffOptions(
                gdscheck_suite="adc",
                drc_unselect_checks=BLOCK_WAIVERS + UPPER_DENSITY_WAIVERS,
                ringfmom=True,
                pex_engine="xact3d",
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
        source_netlist=ROOT / "build" / "frida-1" / "adc_1layer_radix17.src.net",
        source_netlist_top="adc_1layer_radix17",
        cap_cell="caparray_1layer_radix17",
        unit_cell_prefix="capunit_1layer",
        cdac=CapArrayConfig(),
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_1layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_1layer_radix20",
        source_layout_cell="adc_0",
        source_netlist=ROOT / "build" / "frida-1" / "adc_1layer_radix20.src.net",
        source_netlist_top="adc_1layer_radix20",
        cap_cell="caparray_1layer_radix20",
        unit_cell_prefix="capunit_1layer",
        cdac=CapArrayConfig(
            n_dac=16,
            n_extra=0,
            weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1),
        ),
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_2layer_radix17(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix17",
        source_layout_cell="adc_1",
        source_netlist=ROOT / "build" / "frida-1" / "adc_2layer_radix17.src.net",
        source_netlist_top="adc_2layer_radix17",
        cap_cell="caparray_2layer_radix17",
        unit_cell_prefix="capunit_2layer",
        cdac=CapArrayConfig(),
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def frida1_2layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix20",
        source_layout_cell="adc_2",
        source_netlist=ROOT / "build" / "frida-1" / "adc_2layer_radix20.src.net",
        source_netlist_top="adc_2layer_radix20",
        cap_cell="caparray_2layer_radix20",
        unit_cell_prefix="capunit_2layer",
        cdac=CapArrayConfig(
            n_dac=16,
            n_extra=0,
            weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1),
        ),
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def frida2_1layer_radix17(run_dir: Path) -> Path:
    return _run_frida2(
        run_dir,
        target_name="frida2_1layer_radix17",
        params=CapArrayLayoutParams(
            cdac=CapArrayConfig(),
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=5,
            active_layers=(6,),
            top_cell="caparray_1layer_radix17",
        ),
    )


def frida2_2layer_radix17(run_dir: Path) -> Path:
    return _run_frida2(
        run_dir,
        target_name="frida2_2layer_radix17",
        params=CapArrayLayoutParams(
            cdac=CapArrayConfig(),
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=5,
            active_layers=(6, 7),
            top_cell="caparray_2layer_radix17",
        ),
    )


def frida2_3layer_radix17(run_dir: Path) -> Path:
    return _run_frida2(
        run_dir,
        target_name="frida2_3layer_radix17",
        params=CapArrayLayoutParams(
            cdac=CapArrayConfig(),
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=4,
            active_layers=(5, 6, 7),
            top_cell="caparray_3layer_radix17",
        ),
    )


def all_adcs(run_dir: Path) -> Path:
    for target in (
        frida1_1layer_radix17,
        frida1_1layer_radix20,
        frida1_2layer_radix17,
        frida1_2layer_radix20,
        frida2_1layer_radix17,
        frida2_2layer_radix17,
        frida2_3layer_radix17,
    ):
        target(run_dir / target.__name__)
    return run_dir


# ---- the sweep's blocks side by side, unconnected, for the viewer

_GAP_UM = 4.0  # between neighbouring blocks
# left to right: (instance, block); each side's array, its main and difference drivers, its sampler
_ROW = (
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
    for path in sorted((RUNS_DIR / block).glob(f"*/{pdk}/{ident}/instance.json"), reverse=True):
        record = json.loads(path.read_text())
        gds = (record.get("layout") or {}).get("gds")
        if gds and (ROOT / gds).exists():
            return ROOT / gds
    raise FileNotFoundError(
        f"no laid-out instance of the {block} sweep in {pdk} with these parameters under {RUNS_DIR / block}: "
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
    call for, ``flow.cdac.capdriver.model.driver_strengths``), C0's row at the bottom, every other row
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


def assemble_blocks(pdk: str, params: Params, out_dir: Path) -> dict:
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
    for name, block in _ROW:
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
