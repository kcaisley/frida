"""Software-only tests for the sampler layout runner."""

from __future__ import annotations

import ast
import json
from importlib import import_module
from pathlib import Path

import pytest

from flow.comp.layout import FLOORPLANS, PDKS
from flow.samp import layout
from flow.samp.subckt import CASES, write_netlist

LAID_OUT = ("frida1", "tgate_dummy", "bootstrap", "nmos")


def test_main_registers_every_target() -> None:
    tree = ast.parse(Path(layout.__file__).read_text())
    public = {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")}
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    registry = next(node for node in main.body if isinstance(node, ast.Assign))
    entries = registry.value.generators[0].iter
    listed = {ast.unparse(node) for node in entries.elts}
    targets = (listed - {"*ALL_PDKS"}) | {target.__name__ for target in layout.ALL_PDKS}
    per_pdk = {f"samp_{case}_{pdk}" for case in LAID_OUT for pdk in PDKS}
    assert targets == public - {"main"}
    assert targets == per_pdk | {f"samp_{case}_all_pdks" for case in LAID_OUT} | {"all_samp_layouts"}


@pytest.mark.parametrize("case", LAID_OUT)
def test_floorplans_place_every_device_once(case: str, tmp_path: Path) -> None:
    """Every case's floorplan rows name the netlist's devices, each once, and its escapes are ports
    the netlist connects."""

    pdk = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    netlist = write_netlist(CASES[case], tmp_path / f"samp_{case}.sp", pdk).read_text().splitlines()
    devices = [line.split()[0] for line in netlist if line.startswith(("M", "X"))]
    nets = {net for line in netlist if line.startswith("M") for net in line.split()[1:5]}
    nets |= {net for line in netlist if line.startswith("X") for net in line.split()[1:-1]}  # library cells
    fp = json.loads((FLOORPLANS / f"samp_{case}.json").read_text())
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
    for name in PDKS:
        pdk = pytest.importorskip(f"pdk.{name}.hdl21").pdk_logic
        for case, params in CASES.items():
            assert write_netlist(params, tmp_path / name / f"samp_{case}.sp", pdk).exists()
    assert import_module("flow.samp.layout").ALL_PDKS
