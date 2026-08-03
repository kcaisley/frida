"""Checks for the module-level command entry points."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from vlsirtools.spice import SimOptions, SupportedSimulators

from flow.circuit import commands
from flow.util import netlist


def test_primitive_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, bool, Path]] = []
    monkeypatch.setattr(commands, "set_pdk", lambda _tech: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python -m flow.mosfet.primitive", "-t", "ihp130", "-m", "max", "-v", "-o", str(tmp_path)],
    )

    commands.primitive_main(
        "flow.mosfet.primitive",
        lambda tech, mode, visual, outdir: calls.append((tech, mode, visual, outdir)),
    )

    assert calls == [("ihp130", "max", True, tmp_path)]


def test_testbench_netlist_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(commands, "set_pdk", lambda _tech: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m flow.comp.sim",
            "netlist",
            "-t",
            "ihp130",
            "-m",
            "min",
            "-f",
            "verilog",
            "--scope",
            "dut",
            "-o",
            str(tmp_path),
        ],
    )

    commands.testbench_main(
        "flow.comp.sim",
        "comp",
        lambda **kwargs: calls.append(kwargs),
        lambda **_kwargs: pytest.fail("simulation runner was called"),
    )

    assert calls == [
        {
            "tech": "ihp130",
            "mode": "min",
            "montecarlo": False,
            "fmt": "verilog",
            "scope": "dut",
            "outdir": tmp_path / "comp",
            "verbose": True,
        }
    ]


def test_testbench_simulate_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Build local simulation options without obsolete SpiceServer arguments."""

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(commands, "set_pdk", lambda _tech: None)
    monkeypatch.setattr(commands, "_check_simulator", lambda _simulator: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m flow.comp.sim",
            "simulate",
            "-t",
            "ihp130",
            "-m",
            "min",
            "-s",
            "spectre",
            "-o",
            str(tmp_path),
        ],
    )

    commands.testbench_main(
        "flow.comp.sim",
        "comp",
        lambda **_kwargs: pytest.fail("netlist runner was called"),
        lambda **kwargs: calls.append(kwargs),
    )

    assert len(calls) == 1
    call = calls[0]
    options = call.pop("sim_options")
    assert isinstance(options, SimOptions)
    assert options.rundir == tmp_path
    assert options.simulator is SupportedSimulators.SPECTRE
    assert call == {
        "tech": "ihp130",
        "mode": "min",
        "montecarlo": False,
        "simulator": "spectre",
        "outdir": tmp_path,
        "verbose": True,
    }


def test_netlist_conversion_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "input.cdl"
    output = tmp_path / "output.sp"
    source.write_text("*.PININFO A:I\nX0 A B / BUF\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["python -m flow.util.netlist", "cdl-to-sp", str(source), str(output)],
    )

    netlist.main()

    assert output.read_text() == "X0 A B BUF"
