"""The ADC's own layout flow (``lay_out``, which the layout step runs in place of ALIGN's,
docs/pipeline.md): a fabricated FRIDA-1 converter's tape-out layout, its signoff and extraction
planned; any other converter placed and routed by OpenROAD, its blocks as their own layouts laid
them out and its control logic's standard cells.

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

Any other converter is OpenROAD's (``_openroad``, the kit's ``openroad/init.tcl``): its blocks, the
comparator, the samplers and each side of the DAC (capdac's, its drivers with it, the N side its
mirror image), as their own layouts laid them out (``flow.sweep.lookup.laid_out``), each given to
OpenROAD as a LEF abstract made from its layout (``_abstract``: its outline on the sites' grid, its
labelled pins, the rest of its metal as obstructions); its control logic's cells from its netlist,
which hdl21 writes as Verilog (``_verilog_view``: the generic cells the kit's library cells, the
blocks their abstracts). The floorplan (``_floorplan``) puts the blocks in a row on the sites' and
rows' grid, the DAC's sides outside with their seams toward the comparator, and the cells' rows
below them; OpenROAD places and legalizes the cells, fills the rows' gaps, connects the cells' rails
to the digital supply and routes every signal (``_script``); KLayout then reads its DEF with the
blocks' and the cells' layouts into ``adc.gds`` (``_merge``), the plan and the abstracts beside it
(``blocks.json``, ``macros.lef``). For now the blocks' supplies are routed as signals, not by a
supply grid.

    gds = lay_out(params, "ihp130", run_dir)  # python -m flow --block adc --run <name> --to layout
"""

from __future__ import annotations

import io
import json
import math
import re
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import hdl21 as h
from klayout import db

from flow.layout.gdsdiff import gds_diff
from flow.layout.signoff import SignoffParams, write_plan
from flow.logs import run_logged
from flow.sweep.lookup import laid_out
from flow.sweep.runner import ROOT
from flow.util.netlist import omit_subcircuit, replace_subcircuit

from .params import Fabricated, Params
from .subckt import netlist


def lay_out(params: Params, pdk: str, run_dir: Path) -> Path:
    """The converter ``params`` laid out in ``pdk`` into ``run_dir``, its GDS: a fabricated one's
    tape-out layout, its signoff planned (``_fabricated``); any other's blocks side by side
    (``_assemble``)."""
    if params.fabricated is not None:
        return _fabricated(params.fabricated, pdk, run_dir)
    return _openroad(params, pdk, run_dir)


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


# left to right: (instance, block, mirrored); each side's DAC, then its sampler, the comparator
# between them; the N side's DAC the P side's mirror image about the vertical axis, each side's
# seam (its last stage) toward the comparator
_ORDER = (
    ("xdac_p", "cap", False),
    ("xsamp_p", "samp", False),
    ("xcomp", "comp", False),
    ("xsamp_n", "samp", False),
    ("xdac_n", "cap", True),
)


def _path(path: Path) -> str:
    """A path as records hold it: from the repository root where it is under it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


# ---- a generated converter: OpenROAD places its blocks and its control logic's cells, and routes


def _technology(pdk: str) -> tuple[Path, list[Path]]:
    """The kit's OpenROAD setup (``pdk/<pdk>/openroad/init.tcl``) and the LEFs it reads, the
    technology's first."""
    init = ROOT / "pdk" / pdk / "openroad" / "init.tcl"
    return init, [init.parent / name for name in re.findall(r"read_lef \$PLATFORM_DIR/(\S+)", init.read_text())]


def _lef_layers(tech_lef: Path) -> dict[str, tuple[str, str]]:
    """frida's metal and cut names to the technology LEF's layers and their preferred directions:
    its routing layers in order ``M1``, ``M2``..., the cut above metal n ``V<n>``, the one below the
    first metal ``CO``."""
    layers, metal = {}, 0
    for block in re.split(r"(?m)^LAYER\s+", tech_lef.read_text())[1:]:
        name = block.split()[0]
        kind = re.search(r"\bTYPE\s+(\w+)", block)
        direction = re.search(r"\bDIRECTION\s+(\w+)", block)
        if kind is None:
            continue
        if kind[1] == "ROUTING":
            metal += 1
            layers[f"M{metal}"] = (name, direction[1] if direction else "")
        elif kind[1] == "CUT":
            layers["CO" if metal == 0 else f"V{metal}"] = (name, "")
    return layers


def _site(stdcell_lef: Path) -> tuple[str, float, float]:
    """The standard cells' core site: its name, width and height (um)."""
    match = re.search(r"(?ms)^SITE\s+(\S+)\s*\n(.*?)^END\s+\1", stdcell_lef.read_text())
    if match is None:
        raise ValueError(f"{stdcell_lef} defines no site")
    size = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", match[2])
    if size is None:
        raise ValueError(f"{stdcell_lef}: site {match[1]} has no size")
    width, height = size.groups()
    return match[1], float(width), float(height)


def _rails(stdcell_lef: Path, metals: set[str]) -> tuple[str, float]:
    """The standard cells' supply rails: their layer and width (um), a cell's power pin's widest
    rectangle on a metal (``metals``, the routing layers; its rail along the row)."""
    for block in re.findall(r"(?ms)^\s*PIN\s+\S+\s*\n(.*?)^\s*END\s+\S+", stdcell_lef.read_text()):
        if not re.search(r"USE\s+POWER", block):
            continue
        widest = None
        for layer, rects in re.findall(r"LAYER\s+(\S+)\s*;((?:\s*RECT[^;]*;)+)", block):
            if layer not in metals:
                continue
            for rect in re.findall(r"RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", rects):
                x0, y0, x1, y1 = map(float, rect)
                if widest is None or x1 - x0 > widest[0]:
                    widest = (x1 - x0, layer, round(y1 - y0, 4))
        if widest is not None:
            return widest[1], widest[2]
    raise ValueError(f"{stdcell_lef}: no power pin's rail")


def _fillers(pdk: str, stdcell_lef: Path) -> list[str]:
    """The cells that fill the rows' gaps: the library's spacers (its decaps and fillers), else
    the kit's fillers (``STD_FILLS``, or its one-site ``STD_FILL``)."""
    spacers = re.findall(r"(?ms)^MACRO\s+(\S+)\s*\n\s*CLASS\s+CORE\s+SPACER", stdcell_lef.read_text())
    if spacers:
        return spacers
    tech = import_module(f"pdk.{pdk}.layout.tech")
    return [name for name, _width in getattr(tech, "STD_FILLS", ((tech.STD_FILL, tech.STD_FILL_W),))]


def _cell_widths(stdcell_lef: Path) -> dict[str, float]:
    """Every standard cell's width (um), from its LEF."""
    return {
        name: float(width)
        for name, width in re.findall(r"(?ms)^MACRO\s+(\S+)\s*\n.*?SIZE\s+([\d.]+)\s+BY", stdcell_lef.read_text())
    }


def _boxes(region: db.Region, dbu: float, origin: db.Point) -> list[str]:
    """A region's rectangles as LEF ``RECT`` statements (um), relative to ``origin``."""
    lines = []
    for polygon in region.decompose_trapezoids_to_region(db.Polygon.TD_htrapezoids).each():
        if not polygon.is_box():  # not Manhattan
            points = " ".join(
                f"{(p.x - origin.x) * dbu:.4f} {(p.y - origin.y) * dbu:.4f}" for p in polygon.each_point_hull()
            )
            lines.append(f"POLYGON {points} ;")
            continue
        box = polygon.bbox()
        lines.append(
            f"RECT {(box.left - origin.x) * dbu:.4f} {(box.bottom - origin.y) * dbu:.4f} "
            f"{(box.right - origin.x) * dbu:.4f} {(box.top - origin.y) * dbu:.4f} ;"
        )
    return lines


def _abstract(gds: Path, pdk: str, macro: str, site: tuple[str, float, float]) -> tuple[str, dict[str, Any]]:
    """A block's LEF abstract from its layout, and what the floorplan needs of it: its outline
    (the boundary layer's, else its shapes'), grown on the sites' grid it was laid out on past its
    every shape (its wells and rails past the outline) and a micrometre more (a well's space from
    its neighbour's), by whole sites left and right and whole rows, one at least, below and above;
    a pin for each label on a metal's pin or text layer, the metal's shapes under it; its every
    metal and cut as an obstruction but its pins. Pins carry their labels' names; directions and
    uses are left to the netlist (signals all, the supplies routed as signals for now)."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    names = _lef_layers(_technology(pdk)[1][0])
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    dbu = layout.dbu

    def region(spec) -> db.Region:
        index = layout.find_layer(*spec) if spec else None
        return db.Region() if index is None else db.Region(top.begin_shapes_rec(index)).merged()

    outline = region(tech.LAYERS["BND"]).bbox()
    outline = top.bbox() if outline.empty() else outline
    shapes, margin = top.bbox(), round(1.0 / dbu)
    width, height = round(site[1] / dbu), round(site[2] / dbu)
    steps = lambda reach, step, least: max(least, -(-max(reach + margin, 0) // step)) * step
    grown = db.Box(
        outline.left - steps(outline.left - shapes.left, width, 1),
        outline.bottom - steps(outline.bottom - shapes.bottom, height, 1),
        outline.right + steps(shapes.right - outline.right, width, 1),
        outline.top + steps(shapes.top - outline.top, height, 1),
    )
    origin = grown.p1
    metals = [name for name in names if name.startswith("M")]
    text_layers = {}
    for metal in metals:
        for spec in (tech.LAYERS.get(f"{metal}.PIN"), getattr(tech, "PIN_TEXT", {}).get(metal), tech.LAYERS.get(metal)):
            if spec:
                text_layers.setdefault(tuple(spec), metal)
    pins: dict[str, dict[str, db.Region]] = {}
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        metal = text_layers.get((info.layer, info.datatype))
        if metal is None:
            continue
        shapes = region(tech.LAYERS[metal])
        for shape in top.shapes(index).each():
            if not shape.is_text():
                continue
            at = shape.text.position()
            under = shapes.interacting(db.Region(db.Box(at.x - 1, at.y - 1, at.x + 1, at.y + 1)))
            if not under.is_empty():
                pins.setdefault(shape.text.string.lower(), {}).setdefault(metal, db.Region())
                pins[shape.text.string.lower()][metal] += under
    lines = [
        f"MACRO {macro}",
        "  CLASS BLOCK ;",
        f"  FOREIGN {top.name} {origin.x * dbu:.4f} {origin.y * dbu:.4f} ;",  # the layout at -pt
        "  ORIGIN 0 0 ;",
        f"  SIZE {grown.width() * dbu:.4f} BY {grown.height() * dbu:.4f} ;",
        "  SYMMETRY X Y ;",
    ]
    for pin, by_layer in sorted(pins.items()):
        lines += [f"  PIN {pin}", "    DIRECTION INOUT ;", "    USE SIGNAL ;", "    PORT"]
        for metal, shapes in by_layer.items():
            lines.append(f"      LAYER {names[metal][0]} ;")
            lines += [f"        {box}" for box in _boxes(shapes.merged(), dbu, origin)]
        lines += ["    END", f"  END {pin}"]
    lines.append("  OBS")
    for name, (lef_name, _direction) in names.items():
        shapes = region(tech.LAYERS.get(name))
        for by_layer in pins.values():
            shapes -= by_layer.get(name, db.Region())
        if not shapes.is_empty():
            lines.append(f"    LAYER {lef_name} ;")
            lines += [f"      {box}" for box in _boxes(shapes, dbu, origin)]
    lines += ["  END", f"END {macro}", ""]
    info = {
        "gds": gds,
        "cell": top.name,
        "w_um": grown.width() * dbu,
        "h_um": grown.height() * dbu,
        "offset_um": (-origin.x * dbu, -origin.y * dbu),  # the layout's origin within the abstract
        "pins": sorted(pins),
        "layers": sorted({metal for by_layer in pins.values() for metal in by_layer}),
    }
    return "\n".join(lines), info


def _verilog_view(adc: h.Module, pdk: str, blocks: dict[str, tuple[str, list[str]]]) -> h.Module:
    """The converter as OpenROAD reads it (hdl21's Verilog of it): its blocks (``blocks``: instance
    name -> macro and its abstract's pins) as their abstracts, scalar pins each bound to its port's
    bit (``dac_state_3`` to ``dac_state[3]``); its generic cells as the kit's library cells, their
    signal pins alone (an input the generic cell lacks on the library's tie cell, an output it lacks
    open); no supply pin on any instance (OpenROAD connects the cells' supplies,
    ``add_global_connection``, and routes the blocks' as signals). Its modules keep their hierarchy,
    which OpenROAD flattens."""
    library = import_module(f"pdk.{pdk}.hdl21.cells")
    cells: dict[str, h.ExternalModule] = {}
    copies: dict[int, h.Module] = {}

    def lib_cell(name: str) -> h.ExternalModule:
        if name not in cells:
            pins, directions = library.CELLS[name]
            port = {"input": h.Input, "output": h.Output}
            cells[name] = h.ExternalModule(
                domain=pdk,
                name=name,
                port_list=[port[d](name=p) for p, d in zip(pins, directions, strict=True) if d in port],
                paramtype=h.HasNoParams,
            )
        return cells[name]

    top = _copy(adc, library, blocks, lib_cell, copies)
    top.name = "adc"  # the top as the scripts name it
    return top


def _copy(module: h.Module, library: Any, blocks: Any, lib_cell: Any, copies: dict[Any, Any]) -> h.Module:
    """``module`` for ``_verilog_view``: its nets copied, its instances' targets swapped."""
    if id(module) in copies:
        return copies[id(module)]
    copy = h.Module(name=module.name)
    nets = {}
    for name, signal in (*module.ports.items(), *module.signals.items()):
        nets[name] = copy.add(replace(signal, name=name, props=deepcopy(signal.props)))

    def net(target):
        if isinstance(target, h.Slice):
            return nets[target.parent.name][target.index]
        return nets[target.name]

    ties: dict[str, h.Signal] = {}
    for name, instance in module.instances.items():
        target = instance.of
        if name in blocks:
            macro, pins = blocks[name]
            ports = {}
            for pin in pins:
                port, bit = pin, None
                if pin not in instance.conns and (found := re.fullmatch(r"(.+)_(\d+)", pin)):
                    port, bit = found[1], int(found[2])
                if port not in instance.conns:
                    raise ValueError(f"{name}'s abstract has a pin {pin} its netlist has no port for")
                bound = net(instance.conns[port])
                ports[pin] = bound if bit is None else bound[bit]
            key = f"macro:{macro}"
            if key not in copies:
                copies[key] = h.ExternalModule(
                    domain="macro", name=macro, port_list=[h.Inout(name=pin) for pin in pins], paramtype=h.HasNoParams
                )
            copy.add(copies[key]()(**ports), name=name)
        elif isinstance(target, h.ExternalModuleCall) and target.module.domain == "generic":
            cell, mapping, high, low = library.GENERIC[target.module.name]
            ports = {}
            for pin in lib_cell(cell).port_list:
                if pin.name in mapping:
                    ports[pin.name] = net(instance.conns[mapping[pin.name]])
                elif pin.name in high or pin.name in low:
                    level = "tiehi" if pin.name in high else "tielo"
                    if level not in ties:
                        tie, tie_pins, _, _ = library.GENERIC[f"{level}_x1"]
                        ties[level] = copy.add(h.Signal(), name=f"{level}_net")
                        output = next(p for p, generic in tie_pins.items() if generic == "Y")
                        copy.add(lib_cell(tie)()(**{output: ties[level]}), name=f"X{level}")
                    ports[pin.name] = ties[level]
                else:  # an output the generic cell does not have
                    ports[pin.name] = copy.add(h.Signal(), name=f"{name}_{pin.name.lower()}_open")
            copy.add(lib_cell(cell)()(**ports), name=name)
        elif isinstance(target, h.Module):
            child = _copy(target, library, blocks, lib_cell, copies)
            copy.add(child()(**{port: net(bound) for port, bound in instance.conns.items()}), name=name)
        else:
            raise TypeError(f"{module.name}.{name} is neither a block, a generic cell nor a module: {target}")
    copies[id(module)] = copy
    return copy


def _cells_area(module: h.Module, widths: dict[str, float]) -> float:
    """The summed width (um) of the library cells under ``module`` (``_verilog_view``'s)."""
    total = 0.0
    for instance in module.instances.values():
        target = instance.of
        if isinstance(target, h.Module):
            total += _cells_area(target, widths)
        elif isinstance(target, h.ExternalModuleCall) and target.module.domain != "macro":
            total += widths[target.module.name]
    return total


def _floorplan(
    blocks: dict[str, dict[str, Any]],
    order: tuple[tuple[str, str, bool], ...],
    cells_um: float,
    site: tuple[str, float, float],
) -> dict[str, Any]:
    """Where everything goes, on the sites' grid: the blocks in a row (``order``: instance, block,
    mirrored about the vertical axis), each on a whole number of sites and rows, the standard
    cells' rows below them across the row's width, enough for the cells to fill about a third of
    them, a row's margin around (``cells``; the core holds the blocks too)."""
    _name, width, height = site
    snap = lambda value, step: math.ceil(round(value / step, 6)) * step
    x, placed = width * 4, {}
    for instance, block, mirrored in order:
        placed[instance] = {"block": block, "x": x, "mirrored": mirrored}
        x += snap(blocks[block]["w_um"], width)
    die_w = x + width * 4
    core_w = die_w - 8 * width
    rows = max(2, math.ceil(cells_um / 0.35 / core_w))
    core = (width * 4, height, width * 4 + core_w, height + rows * height)
    y = core[3] + height
    for entry in placed.values():
        entry["y"] = y
    die_h = y + snap(max(block["h_um"] for block in blocks.values()), height) + height
    # the core holds the blocks too (OpenROAD places them inside it); its rows above the cells'
    # removed, so the cells and their rails stay below the blocks
    cells = core
    core = (core[0], core[1], core[2], die_h - height)
    return {"die": (0.0, 0.0, die_w, die_h), "core": core, "cells": cells, "blocks": placed, "rows": rows}


def _script(
    plan: dict[str, Any],
    blocks: dict[str, dict[str, Any]],
    layers: dict[str, tuple[str, str]],
    site: str,
    rails: tuple[str, float],
    fillers: list[str],
) -> str:
    """The OpenROAD script: the kit's setup, the blocks' abstracts, the converter's netlist; the
    floorplan (``_floorplan``: the die, the core's rows, each block fixed where it goes, the N side
    mirrored), the cells' supply (their rails on the first metal, run to the die's edges, the
    digital supply's pins there), the pins on the die's edge,
    the cells placed and legalized in the core, the gaps filled, and every signal routed (the
    blocks' supplies too, as signals, for now) up to the highest metal a block's pin is on."""
    die, core = plan["die"], plan["core"]
    first, rail = rails
    top = max(int(metal[1:]) for block in blocks.values() for metal in block["layers"])
    top = max(top, 4)
    lines = [
        "source init.tcl",
        "read_lef macros.lef",
        "read_verilog adc.v",
        "link_design adc",
        (
            f"initialize_floorplan -die_area {{{' '.join(f'{v:.4f}' for v in die)}}} "
            f"-core_area {{{' '.join(f'{v:.4f}' for v in core)}}} -site {site}"
        ),
        "make_tracks",
    ]
    # each block fixed where it goes, its lower left corner there (a mirrored one turned about its
    # own vertical axis); the rows above the cells' removed
    for instance, entry in plan["blocks"].items():
        lines.append(
            f"place_macro -macro_name {instance} -location {{{entry['x']:.4f} {entry['y']:.4f}}} "
            f"-orientation {'MY' if entry['mirrored'] else 'R0'} -exact"
        )
    lines += [
        "set block [ord::get_db_block]",
        f"set top [ord::microns_to_dbu {plan['cells'][3]:.4f}]",
        "foreach row [$block getRows] { if {[lindex [$row getOrigin] 1] >= $top} { odb::dbRow_destroy $row } }",
    ]
    lines += [
        "add_global_connection -net vdd_d -pin_pattern {^VDD$} -power",
        "add_global_connection -net vss_d -pin_pattern {^VSS$} -ground",
        "global_connect",
        "set_voltage_domain -name CORE -power vdd_d -ground vss_d",
        f"define_pdn_grid -name core -voltage_domains CORE -pins {{{first}}}",
        f"add_pdn_stripe -grid core -layer {first} -width {rail} -followpins -extend_to_boundary",
        "pdngen",
        f"place_pins -hor_layers {layers['M3'][0]} -ver_layers {layers['M2'][0]}",
        "global_placement -density 0.6",
        "detailed_placement",
        "check_placement -verbose",
        f"filler_placement {{{' '.join(fillers)}}}",
        f"set_routing_layers -signal {layers['M2'][0]}-{layers[f'M{top}'][0]}",
        "global_route -allow_congestion",
        "detailed_route -output_drc route_drc.rpt",
        'puts "drc violations: [detailed_route_num_drvs]"',
        "write_def adc.def",
        "write_db adc.odb",
        "write_verilog adc_routed.v",
    ]
    return "\n".join(line for line in lines if line) + "\n"


def _openroad(params: Params, pdk: str, run_dir: Path) -> Path:
    """A generated converter laid out by OpenROAD into ``run_dir`` (``adc.gds``): each block as its
    own layout laid it out (``flow.sweep.lookup.laid_out``) given as an abstract (``_abstract``),
    the control logic's cells from its netlist (``_verilog_view``), placed and routed
    (``_floorplan``, ``_script``), then the blocks' and the cells' layouts put in (``_merge``)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    init, lefs = _technology(pdk)
    tech_lef, stdcell_lef = lefs[0], lefs[1]
    site = _site(stdcell_lef)
    layers = _lef_layers(tech_lef)
    sources = {
        block: ROOT / laid_out(name, pdk, part)["gds"]
        for block, name, part in (
            ("comp", "comp", params.comp),
            ("samp", "samp", params.samp),
            ("cap", "capdac", params.cdac),
        )
    }
    blocks, abstracts = {}, []
    for block, gds in sources.items():
        text, info = _abstract(gds, pdk, f"adc_{block}", site)
        blocks[block] = info
        abstracts.append(text)
    header = 'VERSION 5.8 ;\nBUSBITCHARS "[]" ;\nDIVIDERCHAR "/" ;\n\n'
    (run_dir / "macros.lef").write_text(header + "\n".join(abstracts) + "\nEND LIBRARY\n")

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    h.pdk.set_default(logic)
    adc = netlist(params)
    order = _ORDER
    view = _verilog_view(adc, pdk, {name: (f"adc_{block}", blocks[block]["pins"]) for name, block, _ in order})
    text = io.StringIO()
    h.netlist(view, text, fmt="verilog")
    (run_dir / "adc.v").write_text(text.getvalue())
    plan = _floorplan(blocks, order, _cells_area(view, _cell_widths(stdcell_lef)), site)
    (run_dir / "init.tcl").write_text(f"source {init}\n")
    rails = _rails(stdcell_lef, {name for name, _ in layers.values()})
    (run_dir / "adc.tcl").write_text(_script(plan, blocks, layers, site[0], rails, _fillers(pdk, stdcell_lef)))
    run_logged(["openroad", "-no_init", "-exit", "adc.tcl"], cwd=run_dir, log=run_dir / "openroad.log", name="openroad")
    gds = _merge(run_dir, pdk, lefs, blocks, layers)
    (run_dir / "blocks.json").write_text(
        json.dumps(
            {"plan": plan, "blocks": {k: {**v, "gds": _path(v["gds"])} for k, v in blocks.items()}},
            indent=1,
            default=str,
        )
        + "\n"
    )
    return gds


def _merge(
    run_dir: Path, pdk: str, lefs: list[Path], blocks: dict[str, dict[str, Any]], layers: dict[str, tuple[str, str]]
) -> Path:
    """The routed DEF as a GDS (``adc.gds``): KLayout reads it with the LEFs (the technology's,
    the cells', the blocks' abstracts), each metal and cut onto the kit's layer (its routes, vias
    and pins; pin names as labels on its pin layer), each cell and block its own layout (the
    library's GDS, the blocks' as laid out)."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    paths = import_module(f"pdk.{pdk}.layout.paths")
    lines = []
    for key, (name, _direction) in layers.items():
        spec = tech.LAYERS.get(key)
        if not spec:
            continue
        lines.append(f"{name} NET,SPNET,VIA,PIN,LEFPIN,FILL {spec[0]} {spec[1]}")
        pin = tech.LAYERS.get(f"{key}.PIN") or getattr(tech, "PIN_TEXT", {}).get(key)
        if pin:
            lines.append(f"NAME {name}/PIN {pin[0]} {pin[1]}")
    lines.append(f"DIEAREA ALL {tech.LAYERS['BND'][0]} {tech.LAYERS['BND'][1]}")
    (run_dir / "layers.map").write_text("\n".join(lines) + "\n")
    options = db.LoadLayoutOptions()
    config = options.lefdef_config
    config.map_file = str(run_dir / "layers.map")
    config.lef_files = [str(path) for path in (*lefs, run_dir / "macros.lef")]
    config.read_lef_with_def = False
    config.produce_obstructions = False
    config.produce_blockages = False
    config.macro_resolution_mode = 2  # each cell and block its layout (FOREIGN), never its abstract
    macro_layouts = []
    for source in [paths.STD_GDS, *(block["gds"] for block in blocks.values())]:
        layout = db.Layout()
        layout.read(str(source))
        macro_layouts.append(layout)
    config.macro_layouts = macro_layouts
    layout = db.Layout()
    layout.read(str(run_dir / "adc.def"), options)
    gds = run_dir / "adc.gds"
    layout.write(str(gds))
    return gds
