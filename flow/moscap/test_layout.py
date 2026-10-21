"""Software-only tests for the moscap layout runner."""

from __future__ import annotations

import inspect
import json
from importlib import import_module
from pathlib import Path

import pytest

from flow.comp.layout import FLOORPLANS, PDKS
from flow.moscap import layout, targets
from flow.moscap.subckt import CASES, write_netlist


def test_targets_lay_out_every_case_in_every_pdk() -> None:
    public = {
        name
        for name, value in vars(layout).items()
        if inspect.isfunction(value) and value.__module__ == layout.__name__ and not name.startswith("_")
    }
    assert public == {f"moscap_{case}_all_pdks" for case in CASES} | {"all_moscap_layouts"}
    assert {target.__name__ for target in layout.ALL_PDKS} == {f"moscap_{case}_all_pdks" for case in CASES}
    expected = {f"layout_{case}" for case in CASES} | {"layout_all"}
    assert expected == {name for name in vars(targets) if name.startswith("layout_")}


@pytest.mark.parametrize("case", sorted(CASES))
def test_floorplans_place_every_device_once(case: str, tmp_path: Path) -> None:
    """Every case's floorplan rows name the netlist's devices, each once, and its escapes are ports
    the netlist connects."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    netlist = write_netlist(CASES[case], tmp_path / f"moscap_{case}.sp", pdk).read_text().splitlines()
    devices = [line.split()[0] for line in netlist if line.startswith(("M", "X"))]
    nets = {net for line in netlist if line.startswith("M") for net in line.split()[1:5]}
    nets |= {net for line in netlist if line.startswith("X") for net in line.split()[1:-1]}  # library cells
    fp = json.loads((FLOORPLANS / f"moscap_{case}.json").read_text())
    placed = [cell for row in fp["rows"] for cell in row]
    assert sorted(placed) == sorted(devices)
    ports = set(netlist[0].split()[2:])
    escaped = fp["escape"]["up"] + fp["escape"]["down"]
    for port in escaped:
        assert port in ports and port in nets, port
    assert sorted(escaped) == sorted((ports & nets) - {"vdd", "vss"})  # every connected port leaves the block
    assert len(fp["rows"]) % 2 == 0  # both block edges VSS rails


def test_every_pdk_writes_every_case(tmp_path: Path) -> None:
    for name in PDKS:
        pdk = pytest.importorskip(f"pdk.{name}.hdl21").pdk_logic
        for case, params in CASES.items():
            assert write_netlist(params, tmp_path / name / f"moscap_{case}.sp", pdk).exists()
    assert import_module("flow.moscap.layout").ALL_PDKS
