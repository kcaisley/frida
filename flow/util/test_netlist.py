"""Software-only tests for netlist command entry points."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from flow.util import netlist


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
