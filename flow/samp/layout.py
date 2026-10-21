"""Sampler layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/samp_*.json``), each checked with DRC and
LVS. Cases: the FRIDA-1 transmission gate, the transmission gate with half-size charge-injection
dummies, the bootstrapped NMOS switch, and the NMOS switch alone. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow samp.layout_frida1
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, SampParams, write_netlist


def _netlists(params: SampParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The sampler's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _samp(run_dir: Path, pdk: str, case: str) -> Path:
    """A sampler case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"samp_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def samp_frida1_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _samp, "frida1")


def samp_tgate_dummy_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _samp, "tgate_dummy")


def samp_bootstrap_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _samp, "bootstrap")


def samp_nmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _samp, "nmos")


ALL_PDKS = (samp_frida1_all_pdks, samp_tgate_dummy_all_pdks, samp_bootstrap_all_pdks, samp_nmos_all_pdks)


def all_samp_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
