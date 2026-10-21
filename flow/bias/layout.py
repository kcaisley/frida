"""Cascode bias generator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/bias_*.json``), each checked with DRC and
LVS. Cases: wide-swing and margin
cascode-gate diodes. The runner is the comparator's (``flow.comp.layout``).

    uv run python -m flow bias.layout_wide
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, BiasParams, write_netlist


def _netlists(params: BiasParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The generator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _bias(run_dir: Path, pdk: str, case: str) -> Path:
    """A generator case: its netlist into ``run_dir/netlist/``, then the three tools as its
    floorplan places it."""

    name = f"bias_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def bias_wide_all_pdks(run_dir: Path) -> Path:
    """Wide-swing cascode gates."""
    return _all_pdks(run_dir, _bias, "wide")


def bias_margin_all_pdks(run_dir: Path) -> Path:
    """Margin cascode gates."""
    return _all_pdks(run_dir, _bias, "margin")


ALL_PDKS = (
    bias_wide_all_pdks,
    bias_margin_all_pdks,
)


def all_bias_layouts(run_dir: Path) -> Path:
    """The two ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
