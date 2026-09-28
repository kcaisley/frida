"""Generate and sign off named FRIDA CDAC layout targets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import hdl21 as h
from klayout import db

from flow.layout.signoff import SignoffParams, run_signoff
from pdk.tsmc65.ringfmom import LIBRARY, ringfmom_array_params
from pdk.tsmc65.signoff import SignoffOptions

from .laygen import (
    CapArrayLayout,
    CapArrayLayoutParams,
    UnitLengthCapFamilyParams,
    _layout_manifest,
    is_valid_caparray_layout_params,
)
from .pex import parse_caparray_pex, write_capacitance_table
from .subckt import CapArray, CapArrayConfig, get_caparray_weights


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

    circuit_params = ringfmom_array_params(params)
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
                drc_unselect_checks=("PO.DN.2", "DRM.R.1", "MOM.R.1"),
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


def main() -> None:
    targets = {
        target.__name__: target
        for target in (caparray_1layer_radix17, caparray_2layer_radix17, caparray_3layer_radix17)
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
