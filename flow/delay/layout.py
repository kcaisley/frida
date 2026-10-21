"""Delay line and ring layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/delay_*.json``), each checked with DRC
and LVS. Cases: inverter, current-starved, coupled and tail-controlled rings, and inverter, coupled and current-starved delay lines. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow delay.layout_ring5
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, DelayParams, write_netlist


def _netlists(params: DelayParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The delay line and ring's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _delay(run_dir: Path, pdk: str, case: str) -> Path:
    """A delay line and ring case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"delay_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def delay_ring5_all_pdks(run_dir: Path) -> Path:
    """Five-stage inverter ring."""
    return _all_pdks(run_dir, _delay, "ring5")


def delay_ring5_starved_all_pdks(run_dir: Path) -> Path:
    """Five-stage current-starved ring."""
    return _all_pdks(run_dir, _delay, "ring5_starved")


def delay_ring4_coupled_all_pdks(run_dir: Path) -> Path:
    """Four-stage coupled ring with injection."""
    return _all_pdks(run_dir, _delay, "ring4_coupled")


def delay_ring4_tail_all_pdks(run_dir: Path) -> Path:
    """Four-stage coupled ring on a shared tail."""
    return _all_pdks(run_dir, _delay, "ring4_tail")


def delay_chain4_all_pdks(run_dir: Path) -> Path:
    """Four-stage inverter delay line."""
    return _all_pdks(run_dir, _delay, "chain4")


def delay_chain2_coupled_all_pdks(run_dir: Path) -> Path:
    """Two-stage coupled differential buffer."""
    return _all_pdks(run_dir, _delay, "chain2_coupled")


def delay_chain4_starved_all_pdks(run_dir: Path) -> Path:
    """Four-stage current-starved delay line."""
    return _all_pdks(run_dir, _delay, "chain4_starved")


ALL_PDKS = (
    delay_ring5_all_pdks,
    delay_ring5_starved_all_pdks,
    delay_ring4_coupled_all_pdks,
    delay_ring4_tail_all_pdks,
    delay_chain4_all_pdks,
    delay_chain2_coupled_all_pdks,
    delay_chain4_starved_all_pdks,
)


def all_delay_layouts(run_dir: Path) -> Path:
    """The seven ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
