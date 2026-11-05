"""The layout flow's own targets (``python -m flow layout.<target>``): checks of each PDK's rows,
not of a block."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.layout.step import ROOT, all_pdks, cell_um, finish


def _mos_inv(run_dir: Path, pdk: str) -> Path:
    """The PDK's hand-written ``mos_inv.sp`` by ALIGN on its own (a netlist from elsewhere,
    ``flow.layout.build.build``), signed off against it (``flow.layout.compile.lvs_source``)."""
    from flow.layout.build import build
    from flow.layout.pdkproc import in_pdk
    from flow.layout.signoff import signoff

    netlist = ROOT / f"pdk/{pdk}/layout/netlists/mos_inv.sp"
    entry: dict = {}
    failures: dict[str, str] = {}
    try:
        gds = build(pdk, netlist, run_dir / "align", name="mos_inv")
        source = in_pdk(pdk, "flow.layout.compile", "lvs_source", pdk, netlist, run_dir / "source.cdl")
        check = signoff(pdk, gds, source, run_dir / "align" / "signoff")
        entry.update(
            gds=str(gds), cell_um=cell_um(gds), drc_violations=check.drc_violations, lvs_correct=check.lvs_correct
        )
        if check.drc_violations or check.lvs_correct is False:
            failures[f"{pdk}/align"] = f"DRC {check.drc_violations} violations, LVS correct {check.lvs_correct}"
    except Exception as error:  # noqa: BLE001 - report the failure with every other PDK's
        entry["error"] = failures[f"{pdk}/align"] = repr(error)
    return finish(run_dir, {f"{pdk}/align": entry}, failures)


def mos_inv() -> Path:
    """One NMOS and one PMOS row cell from each PDK's hand-written netlist (``mos_inv.sp``), by ALIGN
    in every PDK."""
    return all_pdks(new_run("layout", "mos_inv"), _mos_inv)
