"""Generate and sign off the named FRIDA-1 and FRIDA-2 ADC layouts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from hdl21.prefix import f
from klayout import db

from flow.cdac.laygen import CdacLayout, CdacLayoutParams, UnitLengthCapFamilyParams
from flow.cdac.subckt import CdacParams, _calc_weight_partitions, get_cdac_weights
from flow.layout.gdsdiff import gds_diff
from flow.layout.signoff import SignoffParams, run_signoff
from pdk.tsmc65.signoff import SignoffOptions, add_mom_recognition

from .laygen import AdcLayout, AdcLayoutParams, is_valid_adc_layout_params


def _calc_subcircuit_span(text: str, name: str) -> tuple[int, int]:
    start = re.search(rf"(?im)^\s*\.subckt\s+{re.escape(name)}(?:\s|$)", text)
    if start is None:
        raise ValueError(f"source netlist has no .subckt {name}")
    end = re.search(r"(?im)^\s*\.ends(?:\s+\S+)?\s*$", text[start.end() :])
    if end is None:
        raise ValueError(f"source netlist has no .ends for {name}")
    return start.start(), start.end() + end.end()


def _calc_mom_lvs_source(params: CdacLayoutParams) -> str:
    """Create the PDK-device source view passed by a target to generic LVS."""

    weights = get_cdac_weights(params.cdac)
    partitions = _calc_weight_partitions(weights, params.family.coarse_weight)
    ports = [*(f"cap_botplate_diff<{bit}>" for bit in reversed(range(len(weights))))]
    ports.extend(f"cap_botplate_main<{bit}>" for bit in reversed(range(len(weights))))
    ports.extend(("cap_shieldplate", "cap_topplate"))
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


def _calc_replace_subcircuit(
    source: str,
    *,
    old_top: str,
    new_top: str,
    old_block: str,
    new_block: str,
) -> str:
    """Replace one source block and rename its parent top circuit."""

    start, end = _calc_subcircuit_span(source, old_block)
    replacement_names = re.findall(r"(?im)^\s*\.subckt\s+(\S+)", new_block)
    if not replacement_names:
        raise ValueError("replacement source has no .subckt")
    result = source[:start] + new_block.rstrip() + "\n" + source[end:]
    result = re.sub(
        rf"(?im)(^\s*\.subckt\s+){re.escape(old_top)}(?=\s|$)",
        rf"\g<1>{new_top}",
        result,
        count=1,
    )
    result = re.sub(
        rf"(?i)(?<![A-Za-z0-9_]){re.escape(old_block)}(?![A-Za-z0-9_])",
        replacement_names[-1],
        result,
    )
    return result.rstrip() + "\n"


def _calc_omit_subcircuit(source: str, name: str) -> str:
    """Remove an empty hierarchy definition and all continued-line calls."""

    start, end = _calc_subcircuit_span(source, name)
    statements: list[list[str]] = []
    for line in (source[:start] + source[end:]).splitlines(keepends=True):
        if line.lstrip().startswith("+") and statements:
            statements[-1].append(line)
        else:
            statements.append([line])
    kept: list[str] = []
    for statement in statements:
        tokens = " ".join(line.strip().lstrip("+").strip() for line in statement).split()
        if tokens and tokens[0].lower().startswith("x") and tokens[-1].lower() == name.lower():
            continue
        kept.extend(statement)
    return "".join(kept).rstrip() + "\n"


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
    cdac: CdacParams,
    active_layers: tuple[int, ...],
    lvs_expectation: Literal["correct", "incorrect"],
) -> Path:
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

    params = CdacLayoutParams(
        cdac=cdac,
        family=UnitLengthCapFamilyParams(),
        technology="tsmc65",
        route_layer=4,
        shield_layer=5,
        active_layers=active_layers,
        top_cell=cap_cell,
    )
    reference = source_netlist.read_text(encoding="utf-8")
    lvs_source = run_dir / "source.lvs.cdl"
    lvs_source.write_text(
        _calc_replace_subcircuit(
            reference,
            old_top=source_netlist_top,
            new_top="adc_12b_17step",
            old_block=cap_cell,
            new_block=_calc_mom_lvs_source(params),
        ),
        encoding="utf-8",
    )
    pex_source = run_dir / "source.pex.cdl"
    pex_source.write_text(
        re.sub(
            rf"(?im)(^\s*\.subckt\s+){re.escape(source_netlist_top)}(?=\s|$)",
            r"\g<1>adc_12b_17step",
            _calc_omit_subcircuit(reference, cap_cell),
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
                drc_unselect_checks=("PO.DN.2", "M7.DN.1", "M8.DN.1", "M9.DN.2", "DRM.R.1", "MOM.R.1"),
                mom_shield_layer=5,
                mom_active_layers=active_layers,
            ),
        ),
        run_dir,
    )
    return run_dir


def _run_frida2(run_dir: Path, *, target_name: str, params: CdacLayoutParams) -> Path:
    run_dir.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[2]
    template = db.Layout()
    template.read(str(repository / "build" / "frida-2-template.gds"))
    replacement = CdacLayout(params)
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

    reference_path = Path("/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_2layer_radix17/adc_2layer_radix17.src.net")
    reference = reference_path.read_text(encoding="utf-8")
    lvs_source = run_dir / "source.lvs.cdl"
    lvs_source.write_text(
        _calc_replace_subcircuit(
            reference,
            old_top="adc_2layer_radix17",
            new_top=adc_params.top_cell,
            old_block="caparray_2layer_radix17",
            new_block=_calc_mom_lvs_source(params),
        ),
        encoding="utf-8",
    )
    pex_source = run_dir / "source.pex.cdl"
    pex_source.write_text(
        re.sub(
            r"(?im)(^\s*\.subckt\s+)adc_2layer_radix17(?=\s|$)",
            r"\g<1>adc_12b_17step",
            _calc_omit_subcircuit(reference, "caparray_2layer_radix17"),
            count=1,
        ),
        encoding="utf-8",
    )
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
                drc_unselect_checks=("PO.DN.2", "M7.DN.1", "M8.DN.1", "M9.DN.2", "DRM.R.1", "MOM.R.1"),
                mom_shield_layer=params.shield_layer,
                mom_active_layers=params.active_layers,
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
        source_netlist=Path("/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_1layer_radix17.src.net"),
        source_netlist_top="adc_1layer_radix17",
        cap_cell="caparray_1layer_radix17",
        unit_cell_prefix="capunit_1layer",
        cdac=CdacParams(unit_cap=0.8 * f),
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_1layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_1layer_radix20",
        source_layout_cell="adc_0",
        source_netlist=Path(
            "/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_1layer_radix20/adc_1layer_radix20.src.net"
        ),
        source_netlist_top="adc_1layer_radix20",
        cap_cell="caparray_1layer_radix20",
        unit_cell_prefix="capunit_1layer",
        cdac=CdacParams(
            n_dac=16,
            n_extra=0,
            weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1),
            unit_cap=0.8 * f,
        ),
        active_layers=(6,),
        lvs_expectation="correct",
    )


def frida1_2layer_radix17(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix17",
        source_layout_cell="adc_1",
        source_netlist=Path(
            "/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_2layer_radix17/adc_2layer_radix17.src.net"
        ),
        source_netlist_top="adc_2layer_radix17",
        cap_cell="caparray_2layer_radix17",
        unit_cell_prefix="capunit_2layer",
        cdac=CdacParams(unit_cap=0.8 * f),
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def frida1_2layer_radix20(run_dir: Path) -> Path:
    return _run_frida1(
        run_dir,
        target_name="frida1_2layer_radix20",
        source_layout_cell="adc_2",
        source_netlist=Path(
            "/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_2layer_radix20/adc_2layer_radix20.src.net"
        ),
        source_netlist_top="adc_2layer_radix20",
        cap_cell="caparray_2layer_radix20",
        unit_cell_prefix="capunit_2layer",
        cdac=CdacParams(
            n_dac=16,
            n_extra=0,
            weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1),
            unit_cap=0.8 * f,
        ),
        active_layers=(6, 7),
        lvs_expectation="incorrect",
    )


def frida2_2layer_radix17(run_dir: Path) -> Path:
    return _run_frida2(
        run_dir,
        target_name="frida2_2layer_radix17",
        params=CdacLayoutParams(
            cdac=CdacParams(unit_cap=0.8 * f),
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
        params=CdacLayoutParams(
            cdac=CdacParams(unit_cap=0.8 * f),
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
        frida2_2layer_radix17,
        frida2_3layer_radix17,
    ):
        target(run_dir / target.__name__)
    return run_dir


def main() -> None:
    targets = {
        target.__name__: target
        for target in (
            frida1_1layer_radix17,
            frida1_1layer_radix20,
            frida1_2layer_radix17,
            frida1_2layer_radix20,
            frida2_2layer_radix17,
            frida2_3layer_radix17,
        )
    }
    targets["main"] = all_adcs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available ADC layout targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "layout"
        / "adc"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
