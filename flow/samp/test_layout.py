"""The sampler's layout hooks: its named instances by their floorplans with the three tools, and the
sweep's instances by the floorplan of their structure."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from flow import pipeline

from . import layout, sweep
from .params import Params, SwitchType

NAMED = ("frida1", "tgate_dummy", "nmos", "bootstrap")


def _named(case: str) -> Params:
    return pipeline.names(sweep)[case]()


def test_a_named_instance_is_laid_out_by_its_floorplan_or_aligns(tmp_path: Path, monkeypatch) -> None:
    """``python -m flow layout samp --instance NAME [--auto]``: the characterization's four switches,
    each by its hand-written floorplan; the three tools in each PDK asked for."""
    public = {
        name
        for name, value in vars(layout).items()
        if inspect.isfunction(value) and value.__module__ == layout.__name__ and not name.startswith("_")
    }
    assert public == {"layout_named", "write_netlist", "layout_netlist", "layout_floorplan"}
    named = pipeline.names(sweep)
    assert tuple(named) == NAMED and not any(value.swept for value in named.values())
    assert all((layout.FLOORPLANS / f"samp_{name}.json").exists() for name in named)
    calls = []
    monkeypatch.setattr(layout, "_samp", lambda run_dir, pdk, *args: calls.append((pdk, *args)) or run_dir)
    monkeypatch.setattr(layout, "_all_pdks", lambda run_dir, case, *args, pdks: [case(run_dir, p, *args) for p in pdks])
    layout.layout_named(tmp_path, "bootstrap", named["bootstrap"](), pdks=("tsmc65", "ihp130"))
    layout.layout_named(tmp_path, "nmos", named["nmos"](), auto=True, pdks=("tsmc65",))
    assert [(pdk, name, floorplan.name if floorplan else None) for pdk, name, _params, floorplan in calls] == [
        ("tsmc65", "samp_bootstrap", "samp_bootstrap.json"),
        ("ihp130", "samp_bootstrap", "samp_bootstrap.json"),
        ("tsmc65", "samp_nmos", None),
    ]
    with pytest.raises(FileNotFoundError, match="no hand-written floorplan"):
        layout.layout_named(tmp_path, "ladder", sweep.boost_ladder.spaces("tsmc65")["w64"].base)


def test_every_size_is_placed_by_its_cases_floorplan(tmp_path: Path) -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")
    for params, case in (
        (Params(mos_w=128), "frida1"),
        (Params(dummy=True, mos_l=2), "tgate_dummy"),
        (sweep.boost_ladder.spaces("tsmc65")["w160"].base, "bootstrap"),
    ):
        found = layout.layout_floorplan(tmp_path, "tsmc65", params)
        assert found is not None
        netlist, floorplan = found
        assert floorplan.name == f"samp_{case}.json" and netlist.name == f"samp_{case}.sp"
    # a structure no case has: no floorplan (ALIGN on its own)
    assert layout.layout_floorplan(tmp_path, "tsmc65", Params(switch_type=SwitchType.PMOS)) is None


@pytest.mark.parametrize("case", NAMED)
def test_floorplans_place_every_device_once(case: str, tmp_path: Path) -> None:
    """Every case's floorplan rows name the netlist's devices, each once, and its escapes are ports
    the netlist connects."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    netlist = layout.write_netlist(_named(case), tmp_path / f"samp_{case}.sp", pdk).read_text().splitlines()
    devices = [line.split()[0] for line in netlist if line.startswith(("M", "X"))]
    nets = {net for line in netlist if line.startswith("M") for net in line.split()[1:5]}
    nets |= {net for line in netlist if line.startswith("X") for net in line.split()[1:-1]}  # library cells
    fp = json.loads((layout.FLOORPLANS / f"samp_{case}.json").read_text())
    split = fp.get("split", {})  # a device folded over rows: its parts <device>_a, _b, ...
    placed = [cell[:-2] if cell[:-2] in split else cell for row in fp["rows"] for cell in row]
    assert sorted(placed) == sorted(device for device in devices for _ in range(split.get(device, 1)))
    ports = set(netlist[0].split()[2:])
    escaped = fp["escape"]["up"] + fp["escape"]["down"]
    for port in escaped:
        assert port in ports and port in nets, port
    assert sorted(escaped) == sorted((ports & nets) - {"vdd", "vss"})  # every connected port leaves the block
    assert len(fp["rows"]) % 2 == 0  # both block edges VSS rails


def test_every_pdk_writes_every_case(tmp_path: Path) -> None:
    for name in layout.PDKS:
        pdk = pytest.importorskip(f"pdk.{name}.hdl21").pdk_logic
        for case in NAMED:
            assert layout.write_netlist(_named(case), tmp_path / name / f"samp_{case}.sp", pdk).exists()
