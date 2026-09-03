"""Generate and sign off named FRIDA CDAC layout targets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import hdl21 as h
from hdl21.prefix import f
from klayout import db

from flow.layout.signoff import SignoffParams, run_signoff
from pdk.tsmc65.signoff import SignoffOptions

from .laygen import (
    CdacLayout,
    CdacLayoutParams,
    UnitLengthCapFamilyParams,
    _layout_manifest,
    is_valid_cdac_layout_params,
)
from .pex import parse_cdac_pex, write_capacitance_table
from .subckt import CdacArray, CdacArrayParams, CdacParams, _calc_weight_partitions, get_cdac_weights


def _calc_lvs_source(params: CdacLayoutParams) -> str:
    weights = get_cdac_weights(params.cdac)
    partitions = _calc_weight_partitions(weights, params.family.coarse_weight)
    ports = ["cap_topplate", "cap_shieldplate"]
    ports.extend(f"cap_botplate_main<{bit}>" for bit in reversed(range(len(weights))))
    ports.extend(f"cap_botplate_diff<{bit}>" for bit in reversed(range(len(weights))))
    lines: list[str] = []
    for layer in params.active_layers:
        model = f"frida_mom_m{layer}_s{params.shield_layer}"
        lines.extend((f".subckt {model} PLUS MINUS BULK", f".ends {model}", ""))
    lines.append(f".subckt {params.top_cell} {' '.join(ports)}")
    for index, chunks in enumerate(partitions):
        bit = len(weights) - 1 - index
        for chunk_index, _chunk in enumerate(chunks):
            for layer in params.active_layers:
                model = f"frida_mom_m{layer}_s{params.shield_layer}"
                for kind in ("main", "diff"):
                    lines.append(
                        f"X{kind}_{bit}_{chunk_index}_m{layer} cap_topplate "
                        f"cap_botplate_{kind}<{bit}> cap_shieldplate {model}"
                    )
    lines.extend((f".ends {params.top_cell}", ""))
    return "\n".join(lines)


def _run_caparray(run_dir: Path, params: CdacLayoutParams) -> Path:
    if not is_valid_cdac_layout_params(params):
        raise ValueError(f"invalid CDAC layout parameters: {params}")
    run_dir.mkdir(parents=True, exist_ok=False)
    layout = CdacLayout(params)
    gds_path = run_dir / f"{params.top_cell}.gds"
    save = db.SaveLayoutOptions()
    save.set_format_from_filename(str(gds_path))
    save.add_cell(layout.cell(params.top_cell).cell_index())
    layout.write(str(gds_path), save)
    (run_dir / "geometry_manifest.json").write_text(
        json.dumps(_layout_manifest(params), indent=2) + "\n", encoding="utf-8"
    )

    ideal = CdacArray(CdacArrayParams(cdac=params.cdac, coarse_weight=params.family.coarse_weight))
    ideal.name = params.top_cell
    with (run_dir / f"{params.top_cell}.ideal.cdl").open("w", encoding="utf-8") as stream:
        h.netlist(ideal, stream, fmt="spice")
    lvs_source = run_dir / f"{params.top_cell}.lvs.cdl"
    lvs_source.write_text(_calc_lvs_source(params), encoding="utf-8")
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
                mom_shield_layer=params.shield_layer,
                mom_active_layers=params.active_layers,
                recognize_mom_during_pex=True,
            ),
        ),
        run_dir,
    )
    write_capacitance_table(
        run_dir,
        parse_cdac_pex(result.pex_netlist, bit_count=len(get_cdac_weights(params.cdac))),
    )
    return run_dir


def caparray_1layer_radix17(run_dir: Path) -> Path:
    return _run_caparray(
        run_dir,
        CdacLayoutParams(
            cdac=CdacParams(unit_cap=0.8 * f),
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
        CdacLayoutParams(
            cdac=CdacParams(unit_cap=0.8 * f),
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
        CdacLayoutParams(
            cdac=CdacParams(unit_cap=0.8 * f),
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
        / "cdac"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
