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
from flow.layout.step import free_rows
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


# the blocks: each instance of the netlist and the block it is
_ORDER = (("xdac_p", "cap"), ("xdac_n", "cap"), ("xcomp", "comp"), ("xsamp_p", "samp"), ("xsamp_n", "samp"))
# the rails outside the DAC's sides (um): each rail's width and the space between a pair, about
# (``_straps`` fits them to the layer's tracks)
_RAIL_UM, _RAIL_SPACE_UM = 1.0, 0.5
# the share of the free rows the cells fill
_UTILIZATION = 0.6
# no cell within this much (um, whole sites) beside a block: its implants and wells reach past it
_HALO_UM = 1.0


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


def _straps(tech_lef: Path, layer: str) -> tuple[float, float]:
    """The outside rails on ``layer`` (um): a rail's width and the space between a pair, near
    ``_RAIL_UM`` and ``_RAIL_SPACE_UM``. pdngen puts a rail's middle on a track; this width leaves
    the next track free, a wire there the layer's spacing from the rail (its spacing table's longest
    run, for the rail's width), and this space puts the pair's second rail on a track too."""
    text = tech_lef.read_text()
    match = re.search(rf"(?ms)^LAYER\s+{re.escape(layer)}\s*\n(.*?)^END\s+{re.escape(layer)}", text)
    if match is None:
        raise ValueError(f"{tech_lef} defines no layer {layer}")
    block = match[1]

    def number(key: str, where: str) -> float:
        found = re.search(rf"(?m)^\s*{key}\s+([\d.]+)", where)
        if found is None:
            raise ValueError(f"{tech_lef}: no {key} for {layer}")
        return float(found[1])

    pitch, wire, grid = number("PITCH", block), number("WIDTH", block), number("MANUFACTURINGGRID", text)
    table = re.search(r"SPACINGTABLE\s+PARALLELRUNLENGTH([^;]*);", block)
    # the spacing table's rows: from each width on, the space for the longest run
    rows = [tuple(map(float, row.split())) for row in re.findall(r"WIDTH\s+([\d.\s]+)", table[1])] if table else []
    bands = [(row[0], row[-1]) for row in rows] or [(0.0, number("SPACING", block))]

    def spacing(width: float) -> float:
        """The space a wire keeps from a rail ``width`` wide alongside it."""
        return ([space for start, space in bands if start <= width] or [bands[0][1]])[-1]

    def widest(tracks: int) -> float:
        """The widest rail whose next free track is ``tracks`` from its middle."""
        best = 0.0
        for index, (start, space) in enumerate(bands):
            limit = bands[index + 1][0] - 2 * grid if index + 1 < len(bands) else math.inf
            width = min(2 * (tracks * pitch - wire / 2 - space), limit)
            width = math.floor(round(width / (2 * grid), 6)) * 2 * grid
            if width >= max(start, wire):
                best = max(best, width)
        return best

    widths = [width for width in map(widest, range(1, 64)) if width > 0]
    if not widths:
        raise ValueError(f"{tech_lef}: no rail width fits {layer}'s tracks")
    best = min(widths, key=lambda width: abs(width - _RAIL_UM))
    pair = math.ceil(round((best + max(_RAIL_SPACE_UM, spacing(best))) / pitch, 6)) * pitch
    return round(best, 4), round(pair - best, 4)


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


def _abstract(gds: Path, pdk: str, macro: str, free: dict[str, Any] | None = None) -> tuple[list[str], dict[str, Any]]:
    """A block's LEF abstracts from its layout, and what the floorplan needs of it. Its outline is
    its boundary layer's (else its shapes'): its rows are the standard cells' rows, so it stands in
    them like a cell, its rails meeting theirs. A pin for each label on a metal's pin or text layer,
    the metal's shapes under it, its supplies' (``vdd``, ``vss``) of their use; its every metal and
    cut an obstruction but its pins. Geometry in the outline's frame, its lower left corner at the
    origin (the layout's own origin at ``offset_um``).

    A block with rows left free under its capacitors (``free``, ``flow.layout.step.free_rows``:
    capdac's side where its capacitors stack over the rows) is two blocks, its bands of drivers
    below and above those rows (``parts``: ``<macro>_lo``, the layout's whole cell, and
    ``<macro>_hi``, an empty one), each with the pins and obstructions within it; what it has over
    the free rows from the second metal up is given as routing obstructions (``obstructions``: the
    LEF layer and box), so the cells stand there and route below the capacitors."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    names = _lef_layers(_technology(pdk)[1][0])
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    dbu = layout.dbu
    um = lambda value: value * dbu

    def region(spec) -> db.Region:
        index = layout.find_layer(*spec) if spec else None
        return db.Region() if index is None else db.Region(top.begin_shapes_rec(index)).merged()

    outline = region(tech.LAYERS["BND"]).bbox()
    outline = top.bbox() if outline.empty() else outline
    origin = outline.p1
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
    layer_shapes = {name: region(tech.LAYERS.get(name)) for name in names}
    use = {"vdd": "POWER", "vss": "GROUND"}

    def part(
        name: str,
        box: db.Box,
        foreign: str,
        at: db.Point,
        beyond: tuple[bool, bool, bool] = (True, True, True),
        hidden: frozenset[str] = frozenset(),
    ) -> tuple[str, list[str]]:
        """The abstract of the block within ``box``: its pins and obstructions there (a ``hidden``
        pin's metal an obstruction), and its shapes past ``box``'s sides where ``beyond`` says (left
        and right, below, above: its rails' and wells' overhang, which its neighbours must keep
        clear of), its frame's origin ``at`` (the outline's lower left corner), its layout
        ``foreign`` at ``origin``."""
        reach = round(10.0 / dbu)
        side, below, above = beyond
        clip = db.Region(
            db.Box(
                box.left - (reach if side else 0),
                box.bottom - (reach if below else 0),
                box.right + (reach if side else 0),
                box.top + (reach if above else 0),
            )
        )
        lines = [
            f"MACRO {name}",
            "  CLASS BLOCK ;",
            f"  FOREIGN {foreign} {um(at.x):.4f} {um(at.y):.4f} ;",  # the layout at -pt
            "  ORIGIN 0 0 ;",
            f"  SIZE {um(box.width()):.4f} BY {um(box.height()):.4f} ;",
            "  SYMMETRY X Y ;",
        ]
        named = []
        for pin, by_layer in sorted(pins.items()):
            if pin in hidden:
                continue
            inside = {metal: shapes & db.Region(box) for metal, shapes in by_layer.items()}
            inside = {metal: shapes for metal, shapes in inside.items() if not shapes.is_empty()}
            if not inside:
                continue
            named.append(pin)
            lines += [f"  PIN {pin}", "    DIRECTION INOUT ;", f"    USE {use.get(pin, 'SIGNAL')} ;", "    PORT"]
            for metal, shapes in inside.items():
                lines.append(f"      LAYER {names[metal][0]} ;")
                lines += [f"        {rect}" for rect in _boxes(shapes.merged(), dbu, at)]
            lines += ["    END", f"  END {pin}"]
        lines.append("  OBS")
        for layer, (lef_name, _direction) in names.items():
            shapes = layer_shapes[layer] & clip
            for pin, by_layer in pins.items():
                if pin not in hidden:
                    shapes -= by_layer.get(layer, db.Region())
            if not shapes.is_empty():
                lines.append(f"    LAYER {lef_name} ;")
                lines += [f"      {rect}" for rect in _boxes(shapes, dbu, at)]
        lines += ["  END", f"END {name}", ""]
        return "\n".join(lines), named

    info: dict[str, Any] = {
        "gds": gds,
        "cell": top.name,
        "w_um": um(outline.width()),
        "h_um": um(outline.height()),
        "offset_um": (-um(origin.x), -um(origin.y)),
        "layers": sorted({metal for by_layer in pins.values() for metal in by_layer}),
        "free": bool(free),
    }
    if not free:
        text, named = part(macro, outline, top.name, origin)
        info["parts"] = [("", macro, 0.0, [pin for pin in named if pin not in use])]
        return [text], info
    y0, y1 = (round(value / dbu) for value in free["y_um"])
    lo = db.Box(outline.left, outline.bottom, outline.right, y0)
    hi = db.Box(outline.left, y1, outline.right, outline.top)
    # a signal both bands have is one net inside the side (its top plate, across the free rows):
    # the upper band's pin alone, the comparator's side, so that no route joins the two
    both = frozenset(
        pin
        for pin, by_layer in pins.items()
        if pin not in use
        and all(any(not (shapes & db.Region(band)).is_empty() for shapes in by_layer.values()) for band in (lo, hi))
    )
    lo_text, lo_pins = part(f"{macro}_lo", lo, top.name, origin, beyond=(True, True, False), hidden=both)
    hi_text, hi_pins = part(f"{macro}_hi", hi, f"{macro}_empty", hi.p1, beyond=(True, False, True))
    info["parts"] = [
        ("_lo", f"{macro}_lo", 0.0, [pin for pin in lo_pins if pin not in use]),
        ("_hi", f"{macro}_hi", um(y1 - origin.y), [pin for pin in hi_pins if pin not in use]),
    ]
    info["empty"] = f"{macro}_empty"
    info["free_um"] = (um(y0 - origin.y), um(y1 - origin.y))
    # over the free rows: every metal from the second up and every cut above it, as routing
    # obstructions (the first metal there is the bands' rails, the cells' own)
    middle = db.Region(db.Box(outline.left, y0, outline.right, y1))
    obstructions = []
    for layer, (lef_name, _direction) in names.items():
        if layer in ("M1", "CO", "V1"):
            continue
        for polygon in (layer_shapes[layer] & middle).decompose_trapezoids_to_region(db.Polygon.TD_htrapezoids).each():
            box = polygon.bbox()
            obstructions.append(
                (
                    lef_name,
                    um(box.left - origin.x),
                    um(box.bottom - origin.y),
                    um(box.right - origin.x),
                    um(box.top - origin.y),
                )
            )
    info["obstructions"] = obstructions
    # the walls: the third metal's runs across the free rows (the side's supply at its ends), which
    # a cell's route along that metal cannot cross; no cell stands under them
    across = (
        [box for box in (layer_shapes["M3"] & middle).merged().each() if box.bbox().height() >= 0.9 * (y1 - y0)]
        if "M3" in layer_shapes
        else []
    )
    info["walls"] = sorted((um(box.bbox().left - origin.x), um(box.bbox().right - origin.x)) for box in across)
    return [lo_text, hi_text], info


def _verilog_view(adc: h.Module, pdk: str, blocks: dict[str, list[tuple[str, str, list[str]]]]) -> h.Module:
    """The converter as OpenROAD reads it (hdl21's Verilog of it): its blocks (``blocks``: instance
    name -> each of its abstracts, its instance's suffix, its macro and its pins) as their
    abstracts (capdac's side its two bands, ``xdac_p_lo``, ``xdac_p_hi``), scalar pins each bound to its port's
    bit (``dac_state_3`` to ``dac_state[3]``); its generic cells as the kit's library cells, their
    signal pins alone (an input the generic cell lacks on the library's tie cell, an output it lacks
    open); no supply pin on any instance (OpenROAD connects the cells' and the blocks' supplies,
    ``add_global_connection``); its supplies one, ``vdd`` and ``vss`` (the analog, digital and DAC
    supplies merged, so one set of rails feeds them all). Its modules keep their hierarchy, which
    OpenROAD flattens."""
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

    supplies = {
        name: "vdd" if signal.usage == h.Usage.POWER else "vss"
        for name, signal in adc.ports.items()
        if signal.usage in (h.Usage.POWER, h.Usage.GROUND)
    }
    top = _copy(adc, library, blocks, lib_cell, copies, supplies)
    top.name = "adc"  # the top as the scripts name it
    return top


def _copy(
    module: h.Module,
    library: Any,
    blocks: Any,
    lib_cell: Any,
    copies: dict[Any, Any],
    supplies: dict[str, str] | None = None,
) -> h.Module:
    """``module`` for ``_verilog_view``: its nets copied (``supplies``, the top's supply ports,
    each merged into the one it names), its instances' targets swapped."""
    if id(module) in copies:
        return copies[id(module)]
    copy = h.Module(name=module.name)
    nets = {}
    for name, signal in (*module.ports.items(), *module.signals.items()):
        merged = (supplies or {}).get(name)
        if merged is None:
            nets[name] = copy.add(replace(signal, name=name, props=deepcopy(signal.props)))
        else:
            if merged not in copy.ports:
                copy.add(replace(signal, name=merged, props=deepcopy(signal.props)))
            nets[name] = copy.ports[merged]

    def net(target):
        if isinstance(target, h.Slice):
            return nets[target.parent.name][target.index]
        return nets[target.name]

    ties: dict[str, h.Signal] = {}
    for name, instance in module.instances.items():
        target = instance.of
        if name in blocks:
            for suffix, macro, pins in blocks[name]:  # a block's abstracts, one or more
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
                        domain="macro",
                        name=macro,
                        port_list=[h.Inout(name=pin) for pin in pins],
                        paramtype=h.HasNoParams,
                    )
                copy.add(copies[key]()(**ports), name=f"{name}{suffix}")
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
    cells_um2: float,
    site: tuple[str, float, float],
    straps: tuple[float, float] = (_RAIL_UM, _RAIL_SPACE_UM),
) -> dict[str, Any]:
    """Where everything goes, FRIDA-1's floorplan on the sites' and rows' grid: the DAC's two sides
    form the outline, the P side as drawn on the left and the N side mirrored on the right (each
    side's drivers in its corners, its MSB outside), a narrow column between them; the comparator
    at the top of that column, a sampler beside it on each side; the supply rails (``straps``: a
    rail's width, the space in a pair) outside the sides on the left and right. The die is the
    DAC's height: the pins are on its edges, the inputs at the top of the column, the outputs and
    controls at its bottom, each side's preset values beside its free rows (``pins``).

    Every block stands in the cells' rows, its rails on theirs (its bottom on a row whose rail is
    its own bottom rail's), the comparator and its samplers abutting, so that no stretch of a row
    between them is cut off from the rails. The cells fill the rows the blocks leave: where a side's
    capacitors stack over its rows (``_abstract``), its free rows too, between its two bands of
    drivers (``obstructions``: what the side has over them, translated and mirrored with it);
    elsewhere the middle column alone. The column is as narrow as the comparator and its samplers
    and the cells at ``_UTILIZATION`` of their rows allow."""
    _name, site_w, row_h = site
    cap, comp, samp = blocks["cap"], blocks["comp"], blocks["samp"]
    up = lambda value, step: math.ceil(round(value / step, 6)) * step
    down = lambda value, step: math.floor(round(value / step, 6)) * step
    rail_w, rail_space = straps
    pair = 2 * rail_w + rail_space
    rail = up(pair + 6 * site_w, site_w)  # the column of a pair of rails, three sites either side
    stacked = cap["free"]
    halo = up(_HALO_UM, site_w)  # cell-free beside a block, its implants and wells past its outline
    narrowest = comp["w_um"] + 2 * samp["w_um"] + 2 * site_w + 2 * halo + 2 * site_w
    blocked = comp["w_um"] * comp["h_um"] + 2 * samp["w_um"] * samp["h_um"]
    if stacked:
        blocked += 2 * cap["w_um"] * (cap["free_um"][0] + cap["h_um"] - cap["free_um"][1])
    else:
        blocked += 2 * cap["w_um"] * cap["h_um"]
    gap = up(narrowest, 2 * site_w)
    while (2 * rail + 2 * cap["w_um"] + gap) * cap["h_um"] - blocked < cells_um2 / _UTILIZATION:
        gap += 2 * site_w
    die_w = 2 * rail + 2 * cap["w_um"] + gap
    y0 = 0.0  # the core's bottom: the sides' bottom, row 0
    die_h = cap["h_um"]
    x_p, x_n = rail, rail + cap["w_um"] + gap
    even = lambda y: y0 + down(y - y0, 2 * row_h)
    top = y0 + (cap["free_um"][1] - row_h if stacked else cap["h_um"])
    comp_x = down(die_w / 2 - comp["w_um"] / 2, site_w)  # the column's middle
    comp_y = even(top - comp["h_um"])
    samp_y = even(comp_y + comp["h_um"] - samp["h_um"])
    samp_p_x = comp_x - site_w - samp["w_um"]  # a site from the comparator
    samp_n_x = comp_x + comp["w_um"] + site_w
    placed = {}
    for side, x, orient in (("p", x_p, "R0"), ("n", x_n, "MY")):
        for suffix, _macro, y, _pins in cap["parts"]:
            placed[f"xdac_{side}{suffix}"] = (x, y0 + y, orient)
    placed |= {
        "xcomp": (comp_x, comp_y, "R0"),
        "xsamp_p": (samp_p_x, samp_y, "R0"),
        "xsamp_n": (samp_n_x, samp_y, "MY"),
    }
    obstructions = []
    width = cap["w_um"]
    for layer, a, b, c, d in cap.get("obstructions", []):
        obstructions.append((layer, x_p + a, y0 + b, x_p + c, y0 + d))
        obstructions.append((layer, x_n + width - c, y0 + b, x_n + width - a, y0 + d))  # mirrored
    halos = []
    for name, (x, y, _orient) in placed.items():
        block = cap if name.startswith("xdac") else comp if name == "xcomp" else samp
        height = block["h_um"]
        if name.startswith("xdac") and block["free"]:  # a band of the side's drivers
            height = block["free_um"][0] if name.endswith("_lo") else block["h_um"] - block["free_um"][1]
        halos += [(x - halo, y, x, y + height), (x + block["w_um"], y, x + block["w_um"] + halo, y + height)]
    if stacked:  # no cell under a side's walls across its free rows (``_abstract``), a site either side
        lo, hi = y0 + cap["free_um"][0], y0 + cap["free_um"][1]
        for a, c in cap.get("walls", []):
            a, c = down(a - site_w, site_w), up(c + site_w, site_w)
            halos += [(x_p + a, lo, x_p + c, hi), (x_n + width - c, lo, x_n + width - a, hi)]
    # no cell in the rails' columns: between the rails and the die's edge a cell reaches nothing
    halos += [(0.0, y0, x_p, die_h), (x_n + cap["w_um"], y0, die_w, die_h)]
    return {
        "die": (0.0, 0.0, die_w, die_h),
        "core": (0.0, y0, die_w, y0 + cap["h_um"]),
        "blocks": placed,
        "halos": halos,
        "obstructions": obstructions,
        # each pair of rails three sites in from the die's edge: its first rail's middle (pdngen's
        # offset, from the core's left edge; it snaps a rail to its layer's tracks)
        "rails": (3 * site_w + rail_w / 2, die_w - 3 * site_w - pair + rail_w / 2),
        # where the pins go: along the column's edges, clear of the sides' halos; beside the
        # sides' free rows (stacked kits; elsewhere the sides reach no cell)
        "pins": {
            "x": (x_p + cap["w_um"] + halo, x_n - halo),
            "y": (y0 + cap["free_um"][0], y0 + cap["free_um"][1]) if stacked else (),
        },
        "gap_um": gap,
        "stacked": stacked,
    }


def _tcl(value: Any) -> str:
    """A Python value as a Tcl word: a number to four decimals, a sequence a braced list."""
    if isinstance(value, (list, tuple)):
        return "{" + " ".join(_tcl(item) for item in value) + "}"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


# The OpenROAD flow, one script top to bottom (its variables set above it by ``_openroad``)
_FLOW = r"""
###########################################################################
# 1. The technology, the standard cells, the blocks' abstracts and the netlist

source $init
read_lef macros.lef
read_verilog adc.v
link_design adc
set block [ord::get_db_block]
proc dbu {value} { return [ord::microns_to_dbu $value] }

###########################################################################
# 2. The floorplan: the die, the cells' rows, the routing tracks

initialize_floorplan -die_area $die -core_area $core -site $site
make_tracks

###########################################################################
# 3. The blocks, fixed on the rows: the DAC's sides as the outline, the comparator and its
#    samplers at the top of the column between them; no cell within a few sites beside a block;
#    over a side's free rows, its capacitors as routing obstructions

foreach entry $blocks {
  lassign $entry name x y orient
  set inst [$block findInst $name]
  $inst setOrient $orient
  # a mirrored block turns about its own vertical axis: its lower left corner stays put
  $inst setLocation [dbu $x] [dbu $y]
  $inst setPlacementStatus FIRM
}
foreach box $halos {
  lassign $box x0 y0 x1 y1
  odb::dbBlockage_create $block [dbu $x0] [dbu $y0] [dbu $x1] [dbu $y1]
}
foreach box $obstructions {
  lassign $box layer x0 y0 x1 y1
  odb::dbObstruction_create $block [[ord::get_db_tech] findLayer $layer] [dbu $x0] [dbu $y0] [dbu $x1] [dbu $y1]
}

###########################################################################
# 4. The supply: one vdd and one vss for the cells and every block, the cells' rails on the
#    first metal, a pair of rails outside each side, the pins where they leave the die

add_global_connection -net vdd -pin_pattern $vdd_pins -power
add_global_connection -net vss -pin_pattern $vss_pins -ground
global_connect
set_voltage_domain -name CORE -power vdd -ground vss
define_pdn_grid -name core -voltage_domains CORE -pins [list $rail_layer]
add_pdn_stripe -grid core -layer $cell_rail_layer -width $cell_rail_width -followpins
foreach offset $rails {
  add_pdn_stripe -grid core -layer $rail_layer -width $rail_width -spacing $rail_space \
    -pitch [expr {2 * ($rail_width + $rail_space)}] -offset $offset -number_of_straps 1 -extend_to_boundary
}
add_pdn_connect -grid core -layers [list $cell_rail_layer $rail_layer]
# a rail between two blocks reaches no strap: the blocks' own rails, which it meets, carry it
pdn::allow_repair_channels 1
pdngen

###########################################################################
# 5. The pins on the DAC's outline: the converter's inputs at the top of the column, each side's
#    preset values beside its free rows, the rest (its outputs and controls) at the column's bottom

set edges [dict create top {} left {} right {} bottom {}]
foreach bterm [$block getBTerms] {
  if {[$bterm getSigType] in {POWER GROUND}} { continue }
  set name [$bterm getName]
  set bus [regsub {\[.*} $name {}]
  set edge [expr {$bus in $top_pins ? "top" : $bus in $left_pins ? "left" : $bus in $right_pins ? "right" : "bottom"}]
  dict lappend edges $edge $name
}
lassign $pin_x x0 x1
lassign $pin_y y0 y1
foreach {edge range} [list top $x0-$x1 bottom $x0-$x1 left $y0-$y1 right $y0-$y1] {
  if {[llength [dict get $edges $edge]]} {
    set_io_pin_constraint -pin_names [dict get $edges $edge] -region $edge:$range
  }
}
place_pins -hor_layers $pin_hor -ver_layers $pin_ver

###########################################################################
# 6. The cells: placed in the rows the blocks leave, legalized, the gaps filled

global_placement -density $density
detailed_placement
filler_placement $fillers
check_placement -verbose

###########################################################################
# 7. The routes

set_routing_layers -signal $routing
global_route -allow_congestion
detailed_route -output_drc route_drc.rpt
puts "drc violations: [detailed_route_num_drvs]"

###########################################################################
# 8. The results

write_def adc.def
write_db adc.odb
write_verilog adc_routed.v
"""


def _openroad(params: Params, pdk: str, run_dir: Path) -> Path:
    """A generated converter laid out by OpenROAD into ``run_dir`` (``adc.gds``). Python reads what
    the flow needs and decides the floorplan; one Tcl flow (``_FLOW``) runs it top to bottom, its
    variables set above it (``adc.tcl``):

    1. the kit: its OpenROAD setup, its layers, its cells' site, rails and fillers;
    2. the blocks: each as its own layout laid it out (``flow.sweep.lookup.laid_out``), an abstract
       made from it (``_abstract``; capdac's side its two bands where its capacitors leave rows
       free, its capacitors there routing obstructions);
    3. the netlist: hdl21's Verilog of the converter with the kit's cells and the abstracts, its
       supplies one (``_verilog_view``);
    4. the floorplan (``_floorplan``), then the flow; KLayout puts the blocks' and the cells'
       layouts into the routed DEF (``_merge``); the plan and the abstracts beside it."""
    run_dir.mkdir(parents=True, exist_ok=True)
    # 1. the kit
    tech = import_module(f"pdk.{pdk}.layout.tech")
    init, lefs = _technology(pdk)
    tech_lef, stdcell_lef = lefs[0], lefs[1]
    site = _site(stdcell_lef)
    layers = _lef_layers(tech_lef)
    lef = {name: layer for name, (layer, _direction) in layers.items()}
    # 2. the blocks
    blocks, abstracts = {}, []
    for block, name, part in (
        ("comp", "comp", params.comp),
        ("samp", "samp", params.samp),
        ("cap", "capdac", params.cdac),
    ):
        gds = ROOT / laid_out(name, pdk, part)["gds"]
        free = free_rows(gds, pdk) if block == "cap" else None
        texts, info = _abstract(gds, pdk, f"adc_{block}", free)
        blocks[block] = info
        abstracts += texts
    header = 'VERSION 5.8 ;\nBUSBITCHARS "[]" ;\nDIVIDERCHAR "/" ;\n\n'
    (run_dir / "macros.lef").write_text(header + "\n".join(abstracts) + "\nEND LIBRARY\n")
    # 3. the netlist
    h.pdk.set_default(import_module(f"pdk.{pdk}.hdl21").pdk_logic)
    instances = {name: f"adc_{block}" for name, block in _ORDER}
    view = _verilog_view(
        netlist(params),
        pdk,
        {
            name: [(suffix, macro, pins) for suffix, macro, _y, pins in blocks[block[4:]]["parts"]]
            for name, block in instances.items()
        },
    )
    text = io.StringIO()
    h.netlist(view, text, fmt="verilog")
    (run_dir / "adc.v").write_text(text.getvalue())
    # 4. the floorplan and the flow
    vertical = next(
        layer
        for name, (layer, direction) in layers.items()
        if name[0] == "M" and name != "M1" and direction == "VERTICAL"
    )
    straps = _straps(tech_lef, vertical)
    plan = _floorplan(blocks, _cells_area(view, _cell_widths(stdcell_lef)) * site[2], site, straps)
    top_metal = max(int(metal[1:]) for block in blocks.values() for metal in block["layers"])
    rail_layer, rail_width = _rails(stdcell_lef, set(lef.values()))
    power, ground = tech.STD_SUPPLY
    variables = {
        "init": init,
        "die": plan["die"],
        "core": plan["core"],
        "site": site[0],
        "blocks": [(name, *where) for name, where in plan["blocks"].items()],
        "halos": plan["halos"],
        "obstructions": plan["obstructions"],
        "vdd_pins": f"^({power}|vdd)$",
        "vss_pins": f"^({ground}|vss)$",
        "cell_rail_layer": rail_layer,
        "cell_rail_width": rail_width,
        "rail_layer": vertical,
        "rail_width": straps[0],
        "rail_space": straps[1],
        "rails": plan["rails"],
        "top_pins": ("vin_p", "vin_n"),
        # each side's preset values beside it (none where the sides leave no free rows)
        "left_pins": ("dac_astate_p", "dac_bstate_p") if plan["pins"]["y"] else (),
        "right_pins": ("dac_astate_n", "dac_bstate_n") if plan["pins"]["y"] else (),
        "pin_x": plan["pins"]["x"],
        "pin_y": plan["pins"]["y"],
        "pin_hor": lef["M3"],
        "pin_ver": vertical,
        "density": min(0.9, _UTILIZATION + 0.1),
        "fillers": _fillers(pdk, stdcell_lef),
        "routing": f"{lef['M2']}-{lef[f'M{max(top_metal, 3)}']}",
    }
    script = "".join(f"set {name} {_tcl(value)}\n" for name, value in variables.items()) + _FLOW
    (run_dir / "adc.tcl").write_text(script)
    run_logged(["openroad", "-no_init", "-exit", "adc.tcl"], cwd=run_dir, log=run_dir / "openroad.log", name="openroad")
    gds = _merge(run_dir, pdk, lefs, blocks, layers)
    record = {"plan": plan, "blocks": {key: {**value, "gds": _path(value["gds"])} for key, value in blocks.items()}}
    (run_dir / "blocks.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
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
    empty = db.Layout()  # the cells of the abstracts that carry no layout of their own
    for block in blocks.values():
        if block.get("empty"):
            empty.create_cell(block["empty"])
    macro_layouts.append(empty)
    config.macro_layouts = macro_layouts
    layout = db.Layout()
    layout.read(str(run_dir / "adc.def"), options)
    gds = run_dir / "adc.gds"
    layout.write(str(gds))
    return gds
