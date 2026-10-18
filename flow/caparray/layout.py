"""The FRIDA unit-length CDAC's layout: a process-independent generator and the named targets.

Electrical weights come from :mod:`flow.caparray.subckt`; this module holds only dimensionless
topology choices (the weight family, the stack, the units' order). The cells are drawn by the stems
engine (``flow/layout/stems/capcell.py``, in a process bound to the PDK, ``in_pdk``), which derives
every dimension from the PDK's metal and via rules (``pdk.<tech>.layout.tech``: ``RULES``,
``MFG_GRID``) and draws on its layers (``LAYERS``), as it draws the analog row cells. Each unit is a
difference FMOM (``flow.momcap``): a ring around a main and a difference finger, over a shield
mesh, the arrays' units side by side sharing their ring walls.

``mom_array_params`` sizes the array's netlist from the PDK's FMOM model (``tech.MOM_MODEL``, at
the spacing the generator draws, or the calibrated ``tech.MOM_FITS``): the same lengths the
generator draws, at the capacitance the model gives them. The targets build an
array, sign it off (DRC, LVS against that netlist, 3D extraction) and tabulate its extracted
capacitances (``pex.py``); ``caparray_all_pdks`` draws the array in every PDK and runs its DRC.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import hdl21 as h
import numpy as np
from hdl21.prefix import f
from klayout import db

from flow.layout.pdkproc import in_pdk
from flow.layout.signoff import SignoffParams, run_signoff
from pdk.tsmc65.calibre.ringfmom import LIBRARY
from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, SignoffOptions

from .pex import parse_caparray_pex, write_capacitance_table
from .subckt import (
    ArrayPlates,
    CapArray,
    CapArrayConfig,
    CapArrayParams,
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
    """The array as the stems capacitor cells take it (``capcell.caparray_cells``): the stack,
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


def CapArrayLayout(params: CapArrayLayoutParams) -> db.Layout:
    """Build one arbitrary-width, rule-derived unit-length capacitor array (stems ``capcell``)."""

    if not is_valid_caparray_layout_params(params):
        raise ValueError(f"Invalid CDAC layout params: {params}")
    with tempfile.TemporaryDirectory() as scratch:
        path = str(Path(scratch) / f"{params.top_cell}.gds")
        in_pdk(params.technology, "capcell", "caparray_gds", caparray_spec(params), path)
        layout = db.Layout()
        layout.read(path)
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
    }


def mom_array_params(params: CapArrayLayoutParams) -> CapArrayParams:
    """The array's netlist at its PDK's FMOM capacitance, for ideal simulation and LVS alike.

    Every finger's capacitance is the difference unit's at the length the generator draws it:
    L = tail + (coarse_weight +/- chunk_weight) * step, so the logical unit is the slope over two
    weight steps and each finger adds the intercept once (every coarse chunk too). The slope and
    intercept are the PDK's FMOM model at the spacing the generator draws, interpolated in
    1 / spacing between the extracted spacings (``tech.MOM_MODEL["difference", layers]``, from the
    3D-extraction study or extrapolated to it), unless the PDK calibrates the production unit itself (``tech.MOM_FITS``, which its LVS deck
    checks). No value is rounded: the smallest fingers stay. Where the PDK has a recognized
    device for the stack (``pdk.<tech>.calibre.ringfmom``), every finger is one; otherwise the
    leaves are ideal capacitors.
    """

    tech = import_module(f"pdk.{params.technology}.layout.tech")
    layers = len(params.active_layers)
    geometry = _calc_unit_geometry(params)
    if ("difference", layers) in getattr(tech, "MOM_FITS", {}):
        slope, intercept = tech.MOM_FITS["difference", layers]
    elif ("difference", layers) in getattr(tech, "MOM_MODEL", {}):
        # (spacing nm, slope fF/um, intercept fF) rows, interpolated in 1 / spacing at the gap
        rows = sorted(tech.MOM_MODEL["difference", layers], reverse=True)
        inverse = [1 / space for space, _slope, _intercept in rows]
        slope = float(np.interp(1 / geometry.gap, inverse, [row[1] for row in rows]))
        intercept = float(np.interp(1 / geometry.gap, inverse, [row[2] for row in rows]))
    else:
        raise ValueError(f"{params.technology} has no {layers}-layer difference FMOM model")
    try:
        stack_model = import_module(f"pdk.{params.technology}.calibre.ringfmom").ringfmom_device(
            params.active_layers, params.shield_layer
        )
    except ModuleNotFoundError:
        stack_model = None
    return CapArrayParams(
        cdac=replace(params.cdac, unit_cap=slope * f * (2 * geometry.weight_step / 1000)),
        coarse_weight=params.family.coarse_weight,
        active_layers=params.active_layers,
        stack_model=stack_model,
        tail_cap=slope * f * (geometry.tail_length / 1000) + intercept * f,
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


def caparray_1layer_radix17(run_dir: Path) -> Path:
    return _run_caparray(
        run_dir,
        CapArrayLayoutParams(
            cdac=CapArrayConfig(),
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
            cdac=CapArrayConfig(),
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
            cdac=CapArrayConfig(),
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


def caparray_all_pdks(run_dir: Path) -> Path:
    """Draw the radix-17 array at one to three stacked metals in every PDK and run its DRC (the
    block-level waivers where the PDK has them); writes ``summary.json`` with each outcome."""

    from flow.layout.pdkproc import pdk_value
    from flow.layout.signoff import run_drc

    summary = {}
    for pdk in PDKS:
        mom = pdk_value(pdk, "tech", "MOM_LAYERS")
        for layers in (1, 2, 3):
            active = tuple(mom[-layers:])
            params = CapArrayLayoutParams(
                cdac=CapArrayConfig(),
                family=UnitLengthCapFamilyParams(),
                technology=pdk,
                route_layer=active[0] - 1,
                shield_layer=active[0] - 1,
                active_layers=active,
                top_cell=f"caparray_{layers}layer_radix17",
            )
            work = run_dir / pdk / params.top_cell
            work.mkdir(parents=True, exist_ok=True)
            gds = work / f"{params.top_cell}.gds"
            CapArrayLayout(params).write(str(gds))
            (work / "geometry_manifest.json").write_text(json.dumps(_layout_manifest(params), indent=2) + "\n")
            source = work / "empty.cdl"
            source.write_text(f".SUBCKT {params.top_cell}\n.ENDS\n")
            options = SignoffOptions(drc_unselect_checks=BLOCK_WAIVERS) if pdk == "tsmc65" else None
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


def main() -> None:
    targets = {
        target.__name__: target
        for target in (caparray_1layer_radix17, caparray_2layer_radix17, caparray_3layer_radix17, caparray_all_pdks)
    }
    targets["main"] = all_caparrays
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available CDAC layout targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "layout"
        / "caparray"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
