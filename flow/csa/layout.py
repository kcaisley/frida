"""Charge-sensitive amplifier layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/csa_*.json``), each checked with DRC and
LVS. Cases: NMOS and PMOS input with Krummenacher feedback, NMOS input with continuous and with
reset feedback. The row cells draw MOS only: the layout's netlist leaves the feedback capacitor
out. The runner is the comparator's (``flow.comp.layout``).

    uv run python -m flow csa.layout_krum
"""

from __future__ import annotations

import dataclasses
from importlib import import_module
from pathlib import Path

from hdl21.prefix import f

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, CsaParams, write_netlist


def _netlists(params: CsaParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The amplifier's netlist in ``pdk``, without its feedback capacitor; the file stem names the
    subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(dataclasses.replace(params, cf=0 * f), out_dir / f"{name}.sp", logic)


def _csa(run_dir: Path, pdk: str, case: str) -> Path:
    """An amplifier case: its netlist into ``run_dir/netlist/``, then the three tools as its
    floorplan places it."""

    name = f"csa_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def csa_krum_all_pdks(run_dir: Path) -> Path:
    """NMOS input, Krummenacher feedback."""
    return _all_pdks(run_dir, _csa, "krum")


def csa_krum_pmos_all_pdks(run_dir: Path) -> Path:
    """PMOS input, Krummenacher feedback."""
    return _all_pdks(run_dir, _csa, "krum_pmos")


def csa_continuous_all_pdks(run_dir: Path) -> Path:
    """NMOS input, continuous feedback."""
    return _all_pdks(run_dir, _csa, "continuous")


def csa_reset_all_pdks(run_dir: Path) -> Path:
    """NMOS input, reset feedback."""
    return _all_pdks(run_dir, _csa, "reset")


ALL_PDKS = (
    csa_krum_all_pdks,
    csa_krum_pmos_all_pdks,
    csa_continuous_all_pdks,
    csa_reset_all_pdks,
)


def all_csa_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
