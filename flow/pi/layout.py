"""Phase interpolator layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/pi_*.json``), each checked with DRC and LVS. Cases: CMOS and CML interpolators at
equal and three-to-one weights. The runner is the shared layout step's (``flow.layout.step``).

    uv run python -m flow pi.layout_cmos_half
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.layout.step import FLOORPLANS, all_pdks, finish, signed_off

from .subckt import CASES, PiParams, write_netlist


def _netlists(params: PiParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The phase interpolator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _pi(run_dir: Path, pdk: str, case: str) -> Path:
    """A phase interpolator case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"pi_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return signed_off(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def pi_cmos_half_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _pi, "cmos_half")


def pi_cmos_quarter_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _pi, "cmos_quarter")


def pi_cml_half_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _pi, "cml_half")


def pi_cml_quarter_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _pi, "cml_quarter")


ALL_PDKS = (pi_cmos_half_all_pdks, pi_cmos_quarter_all_pdks, pi_cml_half_all_pdks, pi_cml_quarter_all_pdks)


def all_pi_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return finish(run_dir, {}, failures)
