"""Unsilicided poly resistor row cells, drawn with ALIGN's layout API from a PDK's values.

``PolyResUnit`` names a resistor (PDK, body width and length in nm); the resistor row cell
(``flow/layout/stems/rescell.py``, drawn by the ALIGN PDK's ``ResUnit``) is one standard-cell row
tall with both rails (two rows sharing their VDD rail where the PDK's resistor needs it), so it
abuts the transistor and standard cells of a row, and gives its resistance from the PDK's model
(``tech.RES``). ``polyres_signoff`` draws one resistor in every PDK that has one, runs its DRC and,
where the PDK names its LVS source line (``RES["cdl"]``), LVS against it, the resistance included
where the deck compares it.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from klayout import db

from flow.layout.align.run import Drawing, draw, drawn_only
from flow.layout.pdkproc import access_points, in_pdk, pdk_value

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

    pdk = unit.technology
    info = in_pdk(pdk, "rescell", "res_info", unit.w_nm, unit.l_nm)
    access_points(pdk)  # the ALIGN PDK's standard cells read them at import
    with tempfile.TemporaryDirectory() as scratch:
        pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, Path(scratch) / "pdk")
        arguments = {"w": unit.w_nm, "l": unit.l_nm}
        (gds,) = draw(pdk_dir, [Drawing("ResUnit", "unit", arguments, Path(scratch) / "res.gds", info["top"])])
        layout = db.Layout()
        layout.read(str(gds))
    drawn_only(layout, set(pdk_value(pdk, "tech", "LAYERS").values()))
    return layout, info


def polyres_value(unit: PolyResUnit) -> float:
    """The PDK's model resistance (ohm) of the body as drawn."""

    return polyres_layout(unit)[1]["r"]


def polyres_source(unit: PolyResUnit, info: dict) -> str | None:
    """The LVS source of one drawn resistor cell, or None where the PDK names no source line."""

    spec = pdk_value(unit.technology, "tech", "RES")
    if "cdl" not in spec:
        return None
    # the resistance the deck compares: the model's, or its own sheet over the drawn squares
    r = spec["lvs_sheet"] * info["l"] / info["w"] if "lvs_sheet" in spec else info["r"]
    line = spec["cdl"].format(
        name="0", plus="PLUS", minus="MINUS", bulk="vss", r=f"{r:.6g}", w=info["w"] / 1000, l=info["l"] / 1000
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
