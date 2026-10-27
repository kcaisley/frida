"""The FRIDA unit-length CDAC's layout: a process-independent generator and the named targets.

Electrical weights come from :mod:`flow.caparray.subckt`; this module holds only dimensionless
topology choices (the weight family, the stack, the units' order). The cells are drawn by the stems
engine (``flow/layout/stems/capcell.py``, in a process bound to the PDK, ``in_pdk``), which derives
every dimension from the PDK's metal and via rules (``pdk.<tech>.layout.tech``: ``RULES``,
``MFG_GRID``) and draws on its layers (``LAYERS``), as it draws the analog row cells. Each unit is a
difference FMOM (``flow.momcap``): a ring around a main and a difference finger, over a shield
mesh, the arrays' units side by side sharing their ring walls. A chunk of weight w lengthens its
main finger and shortens its difference finger by w weight steps: its capacitance is the two
strips' difference, so a unit far below the smallest drawable capacitor is two long strips a few
grids apart in length. Every unit is a row of the same length, the coarse weight's: a chunk of
the coarse weight is a unary element, a lighter one a length-scaled binary element (Harpe, JSSC
2018); the coarse weight is the split between them. A unary element keeps a difference finger of
the tail alone, or (``unary_length``) is one main finger and no difference finger. The ADC study's
arrays draw unary rows so, tie their edge dummies' fingers to the top plate, and take their split
and step from ``flow.caparray.sizing``, each to an outline about twice as tall as wide
(``outline_um``). A unit stacks its fingers on the PDK's top three MOM metals unless a target says
otherwise (``STACKED_METALS``).

``mom_array_params`` sizes the array's netlist from the PDK's FMOM model (``tech.MOM_MODEL``, at
the spacing the generator draws, or the calibrated ``tech.MOM_FITS``): the same lengths the
generator draws, at the capacitance the model gives them. The helpers take the array they
work on; each named target declares its arrays (FRIDA's ``RADIX17``, the ADC study's
``ADC_ARRAYS``) and its stack (``flow.caparray.targets`` runs them). The production targets
build an array, sign it off (DRC, LVS against that netlist, 3D extraction) and tabulate its
extracted capacitances (``pex.py``); ``caparray_all_pdks`` draws the array in every PDK and runs
its DRC, ``caparray_extract_all_pdks`` extracts it where the PDK can and compares it with the
model; ``flow.caparray.sizing`` sizes and extracts each ADC array in TSMC65.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, replace
from importlib import import_module
from pathlib import Path
from typing import Any

import hdl21 as h
import numpy as np
from hdl21.prefix import f
from klayout import db

from flow.layout.align.run import Drawing, draw, drawn_only
from flow.layout.pdkproc import in_pdk, pdk_value
from flow.layout.signoff import SignoffParams, run_signoff

from .pex import parse_caparray_pex, write_capacitance_table
from .subckt import (
    ArrayPlates,
    CapArray,
    CapArrayConfig,
    CapArrayParams,
    RedunStrat,
    _calc_weight_partitions,
    array_ports,
    get_caparray_weights,
    is_valid_caparray_config,
)


@dataclass(frozen=True)
class UnitLengthCapFamilyParams:
    """Dimensionless choices shared by a family of weighted unit cells."""

    coarse_weight: int = 64
    tail_landings: int = 1
    edge_dummy_units: int = 1
    shield_bridge_tracks: int = 15
    side_access_tracks: int = 5
    # the length (nm) a unit of weight adds to the main finger and takes from the difference
    # finger: the unit capacitance is twice it times the fingers' capacitance per length. None:
    # two tracks, the production arrays' step; ``flow.caparray.sizing`` sizes an ADC array's
    weight_step: int | None = None
    # the edge dummies' fingers joined to the ring, on the top plate, rather than floating: the
    # same pattern beside the outermost units, without the load (an extraction lumps a floating
    # finger into ground). The ADC arrays tie them; FRIDA's production arrays do not
    tied_dummies: bool = False
    # each chunk of the coarse weight a unary row: one main finger this long (nm), its capacitance the
    # coarse weight in units (the fit's slope over its length, its intercept once), and no
    # difference finger, so nothing of it opposes its step (Harpe's unary elements, C' = 0); its
    # ring and length every row's. None: the unary rows keep a difference finger of the tail.
    # ``flow.caparray.sizing`` sets it for the ADC arrays; FRIDA's production arrays keep None
    unary_length: int | None = None


@dataclass(frozen=True)
class CapArrayLayoutParams:
    """Electrical and physical configuration for a MOM CDAC.

    ``route_layer == shield_layer`` selects a partitioned shared metal layer:
    the shield occupies the central capacitor body while rule-derived routing
    corridors at both ends remain available for the plate buses and vias.
    """

    cdac: CapArrayConfig
    family: UnitLengthCapFamilyParams
    technology: str
    route_layer: int
    shield_layer: int
    active_layers: tuple[int, ...]
    top_cell: str


@dataclass(frozen=True)
class _UnitGeometry:
    """Rule-derived geometry, stored in integer nanometres."""

    grid: int
    finger_width: int
    gap: int
    end_gap: int
    track_pitch: int
    weight_step: int
    tail_length: int
    nominal_length: int
    ring_width: int
    outer_width: int
    outer_height: int
    unit_pitch: int
    via_cut: int
    via_pitch: int
    via_landing: int
    via_opposite_enclosure: int
    via_minimum_enclosure: int
    landing_short: int
    landing_long: int
    shield_spacing: int
    shield_cutout_width: int
    shield_bridge_ys: tuple[int, ...]
    side_extension: int


def is_valid_caparray_layout_params(params: CapArrayLayoutParams) -> bool:
    """Validate one complete process-independent CDAC layout configuration."""

    family = params.family
    if not is_valid_caparray_config(params.cdac):
        return False
    if not params.technology or not params.top_cell:
        return False
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (
            family.coarse_weight,
            family.tail_landings,
            family.shield_bridge_tracks,
            family.side_access_tracks,
        )
    ):
        return False
    if (
        isinstance(family.edge_dummy_units, bool)
        or not isinstance(family.edge_dummy_units, int)
        or family.edge_dummy_units < 0
    ):
        return False
    if family.weight_step is not None and (
        isinstance(family.weight_step, bool) or not isinstance(family.weight_step, int) or family.weight_step < 1
    ):
        return False
    if not isinstance(family.tied_dummies, bool):
        return False
    if family.unary_length is not None and (
        isinstance(family.unary_length, bool) or not isinstance(family.unary_length, int) or family.unary_length < 1
    ):
        return False
    if params.route_layer < 1 or not params.active_layers:
        return False
    if params.active_layers != tuple(range(params.active_layers[0], params.active_layers[-1] + 1)):
        return False
    return params.route_layer <= params.shield_layer < params.active_layers[0]


def _calc_unit_geometry(params: CapArrayLayoutParams) -> _UnitGeometry:
    """Derive the complete unit geometry from the PDK's rules and the family's track counts
    (``capcell.difference_geometry``)."""

    return _UnitGeometry(
        **in_pdk(
            params.technology,
            "capcell",
            "difference_geometry",
            asdict(params.family),
            params.route_layer,
            params.shield_layer,
            params.active_layers,
        )
    )


def _ordered_groups(weights: list[int], chunks: list[list[int]]) -> list[tuple[int, int, list[int]]]:
    """Return ``(stage, electrical_weight, chunks)`` in physical order.

    Electrical indices remain chronological: C0 is the largest and is
    switched first. Physical groups retain the fabricated arrangement with
    small capacitors on the local left and large capacitors on the right.
    Equal weights put the later stage farther left.
    """

    groups = [(stage, weight, sorted(group)) for stage, (weight, group) in enumerate(zip(weights, chunks))]
    return sorted(groups, key=lambda item: (item[1], -item[0]))


def caparray_spec(params: CapArrayLayoutParams) -> dict[str, Any]:
    """The array as its drawing takes it (``capcell.caparray_plan``, ``draw_caparray``): the stack,
    the placed chunk weights left to right (0 an edge dummy), and each stage's buses."""

    weights = get_caparray_weights(params.cdac)
    ordered = _ordered_groups(weights, _calc_weight_partitions(weights, params.family.coarse_weight))
    ports = array_ports(params.cdac.n_dac + params.cdac.n_extra)
    dummies = [0] * params.family.edge_dummy_units
    order, groups = list(dummies), []
    for stage, _weight, group in ordered:
        groups.append(
            (
                ports[f"cap_botplate_main<{stage}>"].name,
                ports[f"cap_botplate_diff<{stage}>"].name,
                len(order),
                len(group),
            )
        )
        order.extend(group)
    return {
        "family": asdict(params.family),
        "route": params.route_layer,
        "shield": params.shield_layer,
        "active": params.active_layers,
        "top": params.top_cell,
        "order": order + dummies,
        "groups": groups,
        "topplate": ArrayPlates.cap_topplate.name,
        "shieldplate": ArrayPlates.cap_shieldplate.name,
    }


def plate_centroids_um(
    manifest: dict[str, Any],
) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    """Each stage's main and difference plate centroid (x, y in um, C0 first; (0, 0) for a plate
    with no finger) of an array as its geometry manifest records it, from the array's centre: its
    rows side by side in the drawn order (``caparray_spec``: the edge dummies, the stages by weight
    with the lightest left, the edge dummies) a unit pitch apart; each row's main finger from one
    end, lengthened by its weight in weight steps, and its difference finger from the other end,
    shortened as much (a unary row of ``unary_length`` is one main finger); a plate's centroid
    weights its fingers by their length."""

    geometry, family = manifest["derived_geometry_nm"], manifest["unit_family"]
    weights, chunks = manifest["weights_by_stage"], manifest["partitioned_weights_by_stage"]
    pitch, nominal, step, gap = (geometry[key] for key in ("unit_pitch", "nominal_length", "weight_step", "end_gap"))
    unary, coarse, dummies = family.get("unary_length"), family["coarse_weight"], family["edge_dummy_units"]
    rows = 2 * dummies + sum(len(group) for group in chunks)
    # each plate's finger length, and its length-weighted x and y, summed over its rows
    sums = {kind: np.zeros((len(weights), 3)) for kind in ("main", "diff")}
    row = dummies
    for stage, _weight, group in _ordered_groups(weights, chunks):
        for weight in group:
            x = (row - (rows - 1) / 2) * pitch
            main, diff = (
                (unary, 0)
                if unary is not None and weight == coarse
                else (nominal + weight * step, nominal - weight * step)
            )
            sums["main"][stage] += (main, main * x, main * (main / 2 - (nominal + gap / 2)))
            sums["diff"][stage] += (diff, diff * x, diff * (nominal + gap / 2 - diff / 2))
            row += 1

    def centroids(plate: np.ndarray) -> tuple[tuple[float, float], ...]:
        return tuple(
            (float(length_x / length) / 1000, float(length_y / length) / 1000) if length > 0 else (0.0, 0.0)
            for length, length_x, length_y in plate
        )

    return centroids(sums["main"]), centroids(sums["diff"])


def CapArrayLayout(params: CapArrayLayoutParams) -> db.Layout:
    """Build one arbitrary-width, rule-derived unit-length capacitor array: its units and its
    wiring drawn by the PDK's ALIGN generators (``draw_caparray``), its geometry the PDK's
    (``capcell.caparray_plan``)."""

    if not is_valid_caparray_layout_params(params):
        raise ValueError(f"Invalid CDAC layout params: {params}")
    spec = caparray_spec(params)
    plan = in_pdk(params.technology, "capcell", "caparray_plan", spec)
    with tempfile.TemporaryDirectory() as scratch:
        pdk_dir = in_pdk(
            params.technology, "flow.layout.align.make_pdk", "build", params.technology, Path(scratch) / "pdk"
        )
        layout = draw_caparray(pdk_dir, spec, plan, Path(scratch))
    drawn_only(layout, set(pdk_value(params.technology, "tech", "LAYERS").values()))
    return layout


def draw_caparray(pdk_dir: Path, spec: dict[str, Any], plan: dict[str, Any], work: Path) -> db.Layout:
    """A CDAC drawn by the ALIGN PDK ``pdk_dir`` (``make_pdk.py``): each unit by its
    ``DifferenceUnit`` generator, the top's wiring by ``ArrayWiring``, the units placed in the top
    as cells (``plan``: ``capcell.caparray_plan``'s)."""

    stack = {"route": spec["route"], "shield": spec["shield"], "active": list(spec["active"])}
    geometry = plan["geometry"]
    drawings = [
        Drawing(
            "DifferenceUnit",
            "unit",
            {
                "g": geometry,
                **stack,
                **{key: unit[key] for key in ("weight", "tied", "unary_length")},
                **{key: plan[key] for key in ("strip", "marks")},
            },
            work / f"{unit['name']}.gds",
            unit["name"],
        )
        for unit in plan["units"]
    ]
    drawings.append(Drawing("ArrayWiring", "wiring", {"g": geometry, "spec": spec}, work / "top.gds", spec["top"]))
    layout = db.Layout()
    for path in draw(pdk_dir, drawings):
        layout.read(str(path))
    top = layout.cell(spec["top"])
    for name, x in plan["placements"]:
        top.insert(db.DCellInstArray(layout.cell(name).cell_index(), db.DTrans(x / 1000, 0)))
    return layout


def _layout_manifest(params: CapArrayLayoutParams) -> dict[str, Any]:
    """Return a serializable electrical, decomposition, stack, and rule manifest."""

    if not is_valid_caparray_layout_params(params):
        raise ValueError(f"Invalid CDAC layout params: {params}")
    weights = get_caparray_weights(params.cdac)
    chunks = _calc_weight_partitions(weights, params.family.coarse_weight)
    geometry = _calc_unit_geometry(params)
    return {
        "technology": params.technology,
        "top_cell": params.top_cell,
        "weights_by_stage": weights,
        "partitioned_weights_by_stage": chunks,
        "physical_chunk_count": sum(len(group) for group in chunks),
        "edge_dummy_count": 2 * params.family.edge_dummy_units,
        "placed_unit_count": sum(len(group) for group in chunks) + 2 * params.family.edge_dummy_units,
        "port_count": 2 * len(weights) + 2,
        "unit_family": asdict(params.family),
        "stack": {
            "route_layer": params.route_layer,
            "shield_layer": params.shield_layer,
            "active_layers": list(params.active_layers),
        },
        "derived_geometry_nm": asdict(geometry),
        "outline_um": outline_um(geometry, sum(len(group) for group in chunks) + 2 * params.family.edge_dummy_units),
    }


def outline_um(geometry: _UnitGeometry, placed: int) -> tuple[float, float]:
    """An array's outline, its boundary (width, height) in um: its ``placed`` units side by side
    (the edge dummies too, sharing their ring walls), the top plate's stack and the shield taps
    beside them (``ArrayWiring``), and the top plate's bar over the units' top ring walls."""
    width = (placed - 1) * geometry.unit_pitch + geometry.outer_width + geometry.side_extension
    height = geometry.outer_height - geometry.ring_width + geometry.via_landing
    return width / 1000, height / 1000


def _mom_fit(params: CapArrayLayoutParams, gap: int) -> tuple[float, float]:
    """The PDK's difference FMOM for the stack at the drawn ``gap``: its capacitance per finger
    length (fF/um) and per finger (fF). The calibrated ``tech.MOM_FITS`` where the PDK has them
    (its LVS deck checks them); otherwise ``tech.MOM_MODEL``'s rows interpolated in 1 / spacing at
    the gap, scaled to the PDK's extracted arrays (``tech.MOM_ARRAY_SCALE``: the arrays' shield mesh
    against the test structures' solid plate)."""

    tech = import_module(f"pdk.{params.technology}.layout.tech")
    layers = len(params.active_layers)
    if ("difference", layers) in getattr(tech, "MOM_FITS", {}):
        return tech.MOM_FITS["difference", layers]
    if ("difference", layers) in getattr(tech, "MOM_MODEL", {}):
        # (spacing nm, slope fF/um, intercept fF) rows
        rows = sorted(tech.MOM_MODEL["difference", layers], reverse=True)
        inverse = [1 / space for space, _slope, _intercept in rows]
        scale = getattr(tech, "MOM_ARRAY_SCALE", {}).get(layers, 1.0)
        slope = scale * float(np.interp(1 / gap, inverse, [row[1] for row in rows]))
        intercept = scale * float(np.interp(1 / gap, inverse, [row[2] for row in rows]))
        return slope, intercept
    raise ValueError(f"{params.technology} has no {layers}-layer difference FMOM model")


def mom_array_params(params: CapArrayLayoutParams) -> CapArrayParams:
    """The array's netlist at its PDK's FMOM capacitance, for ideal simulation and LVS alike.

    Every finger's capacitance is the difference unit's at the length the generator draws it:
    L = tail + (coarse_weight +/- chunk_weight) * step, so the logical unit is the slope over two
    weight steps and each finger adds the intercept once (every coarse chunk too; a unary row's one
    finger, ``unary_length``, is the coarse weight in units), the slope and
    intercept the PDK's FMOM model at the spacing the generator draws (``_mom_fit``). No value is
    rounded: the smallest fingers stay. Where the PDK has a recognized device for the stack
    (``pdk.<tech>.calibre.ringfmom``), every finger is one; otherwise the leaves are ideal
    capacitors.
    """

    geometry = _calc_unit_geometry(params)
    slope, intercept = _mom_fit(params, geometry.gap)
    try:
        stack_model = import_module(f"pdk.{params.technology}.calibre.ringfmom").ringfmom_device(
            params.active_layers, params.shield_layer
        )
    except (ModuleNotFoundError, ValueError):  # no recognized device for this PDK or stack
        stack_model = None
    return CapArrayParams(
        cdac=params.cdac,
        unit_cap=slope * f * (2 * geometry.weight_step / 1000),
        coarse_weight=params.family.coarse_weight,
        active_layers=params.active_layers,
        stack_model=stack_model,
        tail_cap=slope * f * (geometry.tail_length / 1000) + intercept * f,
        unary_rows=params.family.unary_length is not None,
    )


def _run_caparray(run_dir: Path, params: CapArrayLayoutParams) -> Path:
    if not is_valid_caparray_layout_params(params):
        raise ValueError(f"invalid CDAC layout parameters: {params}")
    run_dir.mkdir(parents=True, exist_ok=False)
    layout = CapArrayLayout(params)
    gds_path = run_dir / f"{params.top_cell}.gds"
    save = db.SaveLayoutOptions()
    save.set_format_from_filename(str(gds_path))
    save.add_cell(layout.cell(params.top_cell).cell_index())
    layout.write(str(gds_path), save)
    (run_dir / "geometry_manifest.json").write_text(
        json.dumps(_layout_manifest(params), indent=2) + "\n", encoding="utf-8"
    )

    circuit_params = mom_array_params(params)
    ideal = CapArray(circuit_params)
    ideal.name = params.top_cell
    # the kit's ring-MOM library and waivers, imported here: the module loads without the kit
    from pdk.tsmc65.calibre.ringfmom import LIBRARY
    from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, SignoffOptions

    (run_dir / "ringfmom.cdl").write_text(LIBRARY.read_text(), encoding="utf-8")
    with (run_dir / f"{params.top_cell}.ideal.cdl").open("w", encoding="utf-8") as stream:
        stream.write('.INCLUDE "ringfmom.cdl"\n')
        h.netlist(ideal, stream, fmt="spice")
    lvs_source = run_dir / f"{params.top_cell}.lvs.cdl"
    # Identical electrical source for simulation and LVS; no alternate C values.
    lvs_source.write_text((run_dir / f"{params.top_cell}.ideal.cdl").read_text(), encoding="utf-8")
    result = run_signoff(
        SignoffParams(
            technology=params.technology,
            gds_path=gds_path,
            layout_top=params.top_cell,
            lvs_source_path=lvs_source,
            source_top=params.top_cell,
            output_stem=params.top_cell,
            pdk_options=SignoffOptions(
                drc_unselect_checks=BLOCK_WAIVERS,
                ringfmom=True,
                pex_engine="xact3d",
                recognize_mom_during_pex=True,
            ),
        ),
        run_dir,
    )
    write_capacitance_table(
        run_dir,
        parse_caparray_pex(result.pex_netlist, stage_count=len(get_caparray_weights(params.cdac))),
    )
    return run_dir


# FRIDA's array: 12 bits in 16 stages, MSB redistribution with 5 extra cycles (17 decisions)
RADIX17 = CapArrayConfig(n_dac=11, n_extra=5, redun_strat=RedunStrat.MSB_REDIST)
# the ADC study's arrays (flow.adc.sweep): an N-bit converter on its N-1-step DAC at 10, 12 and 14
# bits, binary and each scheme with 2, 4 and 6 extra cycles, at one and two kT/C minimums of
# switched capacitance (10 arrays at each resolution and scale, 60), and FRIDA-1's array at 12
# bits, at two (its drawn 0.9 pF is near two minimums at 12 bits): 61 in all
ADC_BITS = (10, 12, 14)
EXTRA_CYCLES = (2, 4, 6)
SCHEMES = (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
CAP_SCALES = (1, 2)
FRIDA1_ADC_ARRAY = replace(RADIX17, cap_scale=2)


def adc_arrays(bits: int, cap_scale: int) -> list[CapArrayConfig]:
    """A ``bits`` converter's arrays at ``cap_scale``: binary, then each scheme with each count of
    extra cycles."""
    n_dac = bits - 1
    binary = CapArrayConfig(n_dac=n_dac, n_extra=0, redun_strat=RedunStrat.BINARY, cap_scale=cap_scale)
    return [binary] + [
        CapArrayConfig(n_dac=n_dac, n_extra=extra, redun_strat=scheme, cap_scale=cap_scale)
        for scheme in SCHEMES
        for extra in EXTRA_CYCLES
    ]


def array_name(cdac: CapArrayConfig) -> str:
    """An array's name in the extractions, by its converter's resolution, scheme and scale: e.g.
    ``12b_binary_x1``, ``12b_msb_redist5_x2`` (FRIDA-1's), ``14b_lsb_split6_x2``."""
    if cdac.weights is not None:
        raise ValueError("a fabricated array (explicit weights) has no generated layout")
    extra = cdac.n_extra or ""
    return f"{cdac.n_dac + 1}b_{cdac.redun_strat.name.lower()}{extra}_x{cdac.cap_scale}"


ADC_ARRAYS = {
    array_name(cdac): cdac
    for cdac in [cdac for bits in ADC_BITS for scale in CAP_SCALES for cdac in adc_arrays(bits, scale)]
    + [FRIDA1_ADC_ARRAY]
}


def caparray_1layer_radix17(run_dir: Path) -> Path:
    return _run_caparray(
        run_dir,
        CapArrayLayoutParams(
            cdac=RADIX17,
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=5,
            active_layers=(6,),
            top_cell="caparray_1layer_radix17",
        ),
    )


def caparray_2layer_radix17(run_dir: Path) -> Path:
    return _run_caparray(
        run_dir,
        CapArrayLayoutParams(
            cdac=RADIX17,
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=5,
            active_layers=(6, 7),
            top_cell="caparray_2layer_radix17",
        ),
    )


def caparray_3layer_radix17(run_dir: Path) -> Path:
    return _run_caparray(
        run_dir,
        CapArrayLayoutParams(
            cdac=RADIX17,
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=4,
            active_layers=(5, 6, 7),
            top_cell="caparray_3layer_radix17",
        ),
    )


def all_caparrays(run_dir: Path) -> Path:
    for target in (caparray_1layer_radix17, caparray_2layer_radix17, caparray_3layer_radix17):
        target(run_dir / target.__name__)
    return run_dir


# the PDKs the generator draws in: each stacks the top 1-3 of its MOM metals, the shield and
# the buses sharing the metal below them
PDKS = ("tsmc65", "tsmc28", "tower180", "tpsc65", "ihp130", "lf150")


# a unit's fingers stack on this many of the PDK's MOM metals (at most its ``MOM_LAYERS``): every
# metal stacked adds the same capacitance per length on the same footprint, so three give the
# densest array and the shortest rows for a capacitance
STACKED_METALS = 3


def _stacked(pdk: str, cdac: CapArrayConfig, name: str, layers: int | None = None) -> CapArrayLayoutParams:
    """``cdac`` on the top ``layers`` of the PDK's MOM metals (None: ``STACKED_METALS``, as many as
    the PDK has up to three), its shield and buses on the metal below, as
    ``caparray_<layers>layer_<name>``."""

    from flow.layout.pdkproc import pdk_value

    metals = pdk_value(pdk, "tech", "MOM_LAYERS")
    layers = min(STACKED_METALS, len(metals)) if layers is None else layers
    active = tuple(metals[-layers:])
    return CapArrayLayoutParams(
        cdac=cdac,
        family=UnitLengthCapFamilyParams(),
        technology=pdk,
        route_layer=active[0] - 1,
        shield_layer=active[0] - 1,
        active_layers=active,
        top_cell=f"caparray_{layers}layer_{name}",
    )


def _draw_all_pdks(run_dir: Path, cdac: CapArrayConfig, name: str) -> Path:
    """Draw ``cdac`` at one to three stacked metals in every PDK and run its DRC (the block-level
    waivers where the PDK has them); writes ``summary.json`` with each outcome."""

    from flow.layout.signoff import run_drc

    summary = {}
    for pdk in PDKS:
        for layers in (1, 2, 3):
            params = _stacked(pdk, cdac, name, layers)
            work = run_dir / pdk / params.top_cell
            work.mkdir(parents=True, exist_ok=True)
            gds = work / f"{params.top_cell}.gds"
            CapArrayLayout(params).write(str(gds))
            (work / "geometry_manifest.json").write_text(json.dumps(_layout_manifest(params), indent=2) + "\n")
            source = work / "empty.cdl"
            source.write_text(f".SUBCKT {params.top_cell}\n.ENDS\n")
            options = None
            if pdk == "tsmc65":
                from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, SignoffOptions

                options = SignoffOptions(drc_unselect_checks=BLOCK_WAIVERS)
            try:
                run_drc(
                    SignoffParams(
                        pdk, gds, params.top_cell, source, params.top_cell, params.top_cell, pdk_options=options
                    ),
                    work,
                )
                summary[f"{pdk}/{params.top_cell}"] = "clean"
            except Exception as error:  # noqa: BLE001 - report every PDK's outcome
                summary[f"{pdk}/{params.top_cell}"] = str(error)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir


def caparray_all_pdks(run_dir: Path) -> Path:
    """FRIDA's array at one to three stacked metals in every PDK, through DRC."""
    return _draw_all_pdks(run_dir, RADIX17, "radix17")


def extract_array(work: Path, pdk: str, params: CapArrayLayoutParams) -> dict[str, Any]:
    """Draw and extract one array in ``work`` (3D, layout only, by its own net names): its
    capacitance table, and its stages' effective capacitance (main less difference) against the
    model's and against its own weights in its mean unit (the extracted unit: the effective total
    over the total weight), the error in LSB."""

    from flow.layout.signoff import run_layout_pex

    work.mkdir(parents=True, exist_ok=True)
    gds = work / f"{params.top_cell}.gds"
    CapArrayLayout(params).write(str(gds))
    (work / "geometry_manifest.json").write_text(json.dumps(_layout_manifest(params), indent=2) + "\n")
    netlist = run_layout_pex(pdk, gds, params.top_cell, params.top_cell, work)
    weights = get_caparray_weights(params.cdac)
    extracted = parse_caparray_pex(netlist, stage_count=len(weights))
    write_capacitance_table(work, extracted)
    unit = float(mom_array_params(params).unit_cap) * 1e15
    effective = [main - diff for main, diff in zip(extracted.main_by_stage_ff, extracted.diff_by_stage_ff, strict=True)]
    unit_extracted = sum(effective) / sum(weights)
    return {
        "unit_model_ff": unit,
        "unit_extracted_ff": unit_extracted,
        "weight_step_nm": _calc_unit_geometry(params).weight_step,
        "weight_error_max_lsb": max(
            abs(value / unit_extracted - weight) for weight, value in zip(weights, effective, strict=True)
        ),
        "stages": [
            {
                "weight": weight,
                "model_ff": weight * unit,
                "extracted_ff": value,
                "ratio": value / (weight * unit),
                "error_lsb": value / unit_extracted - weight,
            }
            for weight, value in zip(weights, effective, strict=True)
        ],
    }


def _extract_one(run_dir: Path, pdk: str, cdac: CapArrayConfig, name: str, layers: int) -> dict[str, Any]:
    """Draw and extract one array at the family's step under ``<name>/<pdk>/<layers>l``."""

    import time

    start = time.monotonic()
    result = extract_array(run_dir / name / pdk / f"{layers}l", pdk, _stacked(pdk, cdac, name, layers))
    return {**result, "seconds": time.monotonic() - start}


def _extract_all(
    run_dir: Path,
    arrays: dict[str, CapArrayConfig],
    layer_counts: tuple[int, ...],
    pdks: tuple[str, ...],
    *,
    workers: int = 6,
) -> Path:
    """Extract each named array at each metal count by its own net names (3D, layout only) in each
    PDK, ``workers`` at a time, its capacitance table under ``<name>/<pdk>/<layers>l/``, and compare
    each stage's effective capacitance (main minus difference) with what the PDK's FMOM model sizes
    it at; writes ``summary.json``."""

    from concurrent.futures import ProcessPoolExecutor, as_completed
    from multiprocessing import get_context

    summary = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_extract_one, run_dir, pdk, cdac, name, layers): f"{name}/{pdk}/{layers}l"
            for name, cdac in arrays.items()
            for pdk in pdks
            for layers in layer_counts
        }
        for future in as_completed(futures):
            try:
                summary[futures[future]] = future.result()
            except Exception as error:  # noqa: BLE001 - report every PDK's outcome
                summary[futures[future]] = {"error": str(error)[:500]}
            (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir


def caparray_extract_all_pdks(run_dir: Path) -> Path:
    """FRIDA's array at one to three metals, extracted in every PDK."""
    return _extract_all(run_dir, {"radix17": RADIX17}, (1, 2, 3), PDKS)


def _extract_window(
    run_dir: Path, pdk: str, cdac: CapArrayConfig, name: str, layers: int, first: int, last: int
) -> dict[str, Any]:
    """Extract units ``first``-``last`` of ``cdac`` cut out of its layout (the ring and the
    shield labelled, the ring's metals joined by a via inside the window) and compare each stage
    there with the sizing: a stage's coupling to the top plate without the whole plate's net,
    whose size widens the field solver's split of a small coupling from the substrate."""

    from flow.layout.pdkproc import pdk_value
    from flow.layout.signoff import run_layout_pex

    layer_names = pdk_value(pdk, "tech", "LAYERS")
    params = _stacked(pdk, cdac, name, layers)
    active = params.active_layers
    geometry = _calc_unit_geometry(params)
    full = CapArrayLayout(params)
    top = full.cell(params.top_cell)
    top.flatten(True)
    x0 = first * geometry.unit_pitch
    x1 = last * geometry.unit_pitch + geometry.outer_width
    window = db.Region(db.Box(x0, -(10**9), x1, 10**9))
    layout = db.Layout()
    layout.dbu = full.dbu
    name = f"window{first}_{last}"
    cell = layout.create_cell(name)
    for index in full.layer_indexes():
        shapes = cell.shapes(layout.layer(full.get_info(index)))
        shapes.insert(db.Region(top.shapes(index)) & window)
        for shape in top.shapes(index).each():
            if shape.is_text() and x0 <= shape.text.trans.disp.x <= x1 and "botplate" in shape.text_string:
                shapes.insert(shape.text)
    wall, y = x0 + geometry.ring_width // 2, geometry.outer_height // 2
    half = geometry.via_cut // 2
    for metal in active[:-1]:
        cell.shapes(layout.layer(*layer_names[f"V{metal}"])).insert(
            db.Box(wall - half, y - half, wall + half, y + half)
        )
    for metal, label in (
        (active[0], ArrayPlates.cap_topplate.name),
        (params.shield_layer, ArrayPlates.cap_shieldplate.name),
    ):
        pin = layout.layer(*layer_names[f"M{metal}.PIN"])
        cell.shapes(pin).insert(db.Text(label, db.Trans(wall, y)))
        cell.shapes(pin).insert(db.Box(wall - half, y - half, wall + half, y + half))
    work = run_dir / pdk / f"{layers}l_{name}"
    work.mkdir(parents=True, exist_ok=True)
    gds = work / f"{name}.gds"
    layout.write(str(gds))
    weights = get_caparray_weights(params.cdac)
    extracted = parse_caparray_pex(run_layout_pex(pdk, gds, name, name, work), stage_count=len(weights))
    unit = float(mom_array_params(params).unit_cap) * 1e15
    return {
        "stages": [
            {
                "stage": k,
                "weight": weights[k],
                "extracted_ff": main - diff,
                "ratio": (main - diff) / (weights[k] * unit),
            }
            for k, (main, diff) in enumerate(zip(extracted.main_by_stage_ff, extracted.diff_by_stage_ff, strict=True))
            if main
        ]
    }


def caparray_window_check(run_dir: Path) -> Path:
    """Extract the two- and three-metal arrays' units 9-11 (stages 7, 6 and 5) alone in the two PDKs
    whose whole-array extraction splits stage 6's coupling between the top plate and the
    substrate; writes ``summary.json``."""

    summary = {
        f"{pdk}/{layers}l": _extract_window(run_dir, pdk, RADIX17, "radix17", layers, 9, 11)
        for pdk in ("tsmc28", "tpsc65")
        for layers in (2, 3)
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir
