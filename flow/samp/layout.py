"""Sampler layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

``layout_named`` lays out one named instance (``flow.samp.sweep``'s ``@named``: the characterization's
four switches) in the PDKs with all three tools (cIcCreator, laygo, ALIGN), each checked with DRC
and LVS: from its hand-written floorplan (``design/layout/samp_<name>.json``), or, ``auto``, laid
out by ALIGN on its own from the netlist (ALIGN's placement then the floorplan of cIcCreator and
laygo). ``layout_netlist`` and ``layout_floorplan`` give the sweep's layout step
(``flow.sweep.runner.layout``, ALIGN alone) an instance's netlists: every size of a switch is placed
by the floorplan of its structure (``params.STRUCTURE``: its switch type and dummies), named after
the switch type (the transmission gate's after FRIDA-1, the one with dummies ``tgate_dummy``). The
runner is the comparator's (``flow.comp.layout``).

    uv run python -m flow layout samp --instance frida1
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.circuit import devices
from flow.comp.layout import FLOORPLANS, PDKS, _all_pdks, _run
from flow.layout.pdkproc import in_pdk

from .params import Params, SwitchType
from .subckt import Nets, netlist


def write_netlist(params: Params, path: Path, pdk) -> Path:
    """The sampler after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""
    return devices.write_netlist(params, path, pdk, generator=netlist, nets=Nets)


def layout_netlist(out_dir: Path, pdk: str, samp: Params) -> Path:
    """The all-transistor netlist with any library cells it contains recognized
    (``flow.layout.stdcells``), as a switch is laid out without a floorplan (the sweep's layout step,
    ``flow.sweep.runner.layout_job``)."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(samp, out_dir / "samp_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "samp.sp")


def _case(samp: Params) -> str:
    """The name of the floorplan of the switch's structure: its switch type's (the transmission
    gate's FRIDA-1's), with ``_dummy`` where it has dummies."""
    name = "frida1" if samp.switch_type is SwitchType.TGATE and not samp.dummy else samp.switch_type.name.lower()
    return f"{name}_dummy" if samp.dummy else name


def layout_floorplan(out_dir: Path, pdk: str, samp: Params) -> tuple[Path, Path] | None:
    """The hand-written floorplan of the instance's structure (``design/layout/samp_<case>.json``)
    with the netlist it places, at the instance's sizes; None where its structure has none."""

    floorplan = FLOORPLANS / f"samp_{_case(samp)}.json"
    if not floorplan.exists():
        return None
    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(samp, out_dir / f"{floorplan.stem}.sp", logic), floorplan


def _samp(run_dir: Path, pdk: str, name: str, params: Params, floorplan: Path | None) -> Path:
    """A switch: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan (or,
    without one, ALIGN's placement) places it."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    netlist_path = write_netlist(params, run_dir / "netlist" / f"{name}.sp", logic)
    return _run(run_dir, pdk, name, netlist_path, floorplan)


def layout_named(run_dir: Path, name: str, params: Params, *, auto: bool = False, pdks: tuple[str, ...] = PDKS) -> Path:
    """The named instance ``name`` in each of ``pdks`` with the three tools, into ``run_dir/<pdk>/``:
    from its hand-written floorplan, or ``auto`` from ALIGN's placement."""

    floorplan = None if auto else FLOORPLANS / f"samp_{name}.json"
    if floorplan is not None and not floorplan.exists():
        raise FileNotFoundError(f"{floorplan}: no hand-written floorplan of {name}; lay it out from ALIGN's (auto)")
    return _all_pdks(run_dir, _samp, f"samp_{name}", params, floorplan, pdks=pdks)
