"""Amplifier layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/ota_*.json``), each checked with DRC and
LVS. Cases: five-transistor amplifiers with NMOS and PMOS inputs, telescopic and folded cascodes,
the self-biased complementary amplifier, and a two-stage amplifier. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow ota.layout_five_t
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, OtaParams, write_netlist


def _netlists(params: OtaParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The amplifier's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _ota(run_dir: Path, pdk: str, case: str) -> Path:
    """A amplifier case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"ota_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def ota_five_t_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "five_t")


def ota_five_t_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "five_t_pmos")


def ota_telescopic_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "telescopic")


def ota_folded_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "folded")


def ota_self_biased_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "self_biased")


def ota_two_stage_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ota, "two_stage")


ALL_PDKS = (
    ota_five_t_all_pdks,
    ota_five_t_pmos_all_pdks,
    ota_telescopic_all_pdks,
    ota_folded_all_pdks,
    ota_self_biased_all_pdks,
    ota_two_stage_all_pdks,
)


def all_ota_layouts(run_dir: Path) -> Path:
    """The six ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
