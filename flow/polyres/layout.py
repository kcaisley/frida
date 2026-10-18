"""Unsilicided poly resistor row cells, drawn by the stems engine from a PDK's values.

``PolyResUnit`` names a resistor (PDK, body width and length in nm); the stems resistor cell
(``flow/layout/stems/rescell.py``) draws it one standard-cell row tall with both rails (two rows
sharing their VDD rail where the PDK's resistor needs it), so it abuts the transistor and standard
cells of a row, and gives its resistance from the PDK's model
(``tech.RES``). ``polyres_signoff`` draws one resistor in every PDK that has one, runs its DRC and,
where the PDK names its LVS source line (``RES["cdl"]``), LVS against it, the resistance included
where the deck compares it.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from klayout import db

from flow.layout.pdkproc import in_pdk, pdk_value

# the PDKs with a poly resistor row cell (tech.RES)
PDKS = ("tsmc65", "tsmc28", "tower180", "tpsc65", "ihp130", "lf150")


@dataclass(frozen=True)
class PolyResUnit:
    """A resistor: the PDK and the body's width (across the row) and length (along it), in nm."""

    technology: str
    w_nm: int
    l_nm: int


def polyres_layout(unit: PolyResUnit) -> tuple[db.Layout, dict]:
    """Draw one resistor row cell; returns the layout and the cell's top name, drawn width and
    length (nm, a short body lengthened to its markers' area) and modelled resistance (ohm)."""

    with tempfile.TemporaryDirectory() as scratch:
        path = str(Path(scratch) / "res.gds")
        info = in_pdk(unit.technology, "rescell", "res_gds", path, unit.w_nm, unit.l_nm)
        layout = db.Layout()
        layout.read(path)
    return layout, info


def polyres_value(unit: PolyResUnit) -> float:
    """The PDK's model resistance (ohm) of the body as drawn."""

    return polyres_layout(unit)[1]["r"]


def polyres_source(unit: PolyResUnit, info: dict) -> str | None:
    """The LVS source of one drawn resistor cell, or None where the PDK names no source line."""

    spec = pdk_value(unit.technology, "tech", "RES")
    if "cdl" not in spec:
        return None
    line = spec["cdl"].format(
        name="0", plus="PLUS", minus="MINUS", bulk="vss", r=f"{info['r']:.6g}", w=info["w"] / 1000, l=info["l"] / 1000
    )
    stub = spec.get("cdl_stub", "")
    return f"{stub + chr(10) if stub else ''}.SUBCKT {info['top']} PLUS MINUS vdd vss\n{line}\n.ENDS\n"


def polyres_signoff(run_dir: Path) -> Path:
    """Draw a 4 um resistor at each PDK's narrowest width, DRC it and LVS it where the PDK names its
    source line; writes ``summary.json`` (per PDK: the cell, DRC and LVS outcomes)."""

    from flow.layout.signoff import SignoffParams, run_drc, run_lvs
    from pdk.tsmc65.calibre.signoff import BLOCK_WAIVERS, SignoffOptions

    summary = {}
    for pdk in PDKS:
        spec = pdk_value(pdk, "tech", "RES")
        unit = PolyResUnit(pdk, spec["width"], 4000)
        work = run_dir / pdk
        work.mkdir(parents=True, exist_ok=True)
        layout, info = polyres_layout(unit)
        gds = work / f"{info['top']}.gds"
        layout.write(str(gds))
        source = polyres_source(unit, info)
        cdl = work / f"{info['top']}.cdl"
        cdl.write_text(source or f".SUBCKT {info['top']} PLUS MINUS vdd vss\n.ENDS\n")
        # TSMC65 checks a block with its block-level waivers (density)
        options = SignoffOptions(drc_unselect_checks=BLOCK_WAIVERS) if pdk == "tsmc65" else None
        params = SignoffParams(pdk, gds, info["top"], cdl, info["top"], info["top"], pdk_options=options)
        result: dict = {**info}
        try:
            run_drc(params, work)
            result["drc"] = "clean"
        except Exception as error:  # noqa: BLE001 - report every PDK's outcome
            result["drc"] = str(error)
        if source is not None:
            try:
                result["lvs"] = "correct" if run_lvs(params, work)[0] else "incorrect"
            except Exception as error:  # noqa: BLE001
                result["lvs"] = str(error)
        summary[pdk] = result
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir


def main() -> None:
    """Create one output directory and run one named poly resistor target."""

    targets = {target.__name__: target for target in (polyres_signoff,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available poly resistor targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "layout"
        / "polyres"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
