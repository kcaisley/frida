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


def test_replacement_reorders_actual_connections_by_formal_name() -> None:
    source = """.SUBCKT old B A
+ S PARAMS: gain=1
.ENDS old
.SUBCKT parent IN OUT VSS
Xone OUT IN
+ VSS / old gain=2
Xtwo OUT IN VSS old
.ENDS parent
"""
    replacement = ".subckt new A S B\n.ends new\n"
    result = netlist.replace_subcircuit(
        source, old_top="parent", new_top="renamed", old_block="old", new_block=replacement
    )
    assert netlist.subcircuit_ports(result, "new") == ("A", "S", "B")
    assert "Xone IN VSS OUT new gain=2\n" in result
    assert "Xtwo IN VSS OUT new\n" in result
    assert ".SUBCKT renamed IN OUT VSS" in result
    assert ".ENDS renamed" in result
    assert ".SUBCKT old" not in result


@pytest.mark.parametrize(
    "mapping",
    [{}, {"A": "A"}, {"A": "B", "B": "B"}, {"A": "A", "C": "B"}, {"a": "B", "A": "A", "B": "B"}],
)
def test_replacement_rejects_incomplete_or_ambiguous_mapping(mapping: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="one-to-one"):
        netlist.replace_subcircuit(
            ".subckt old A B\n.ends old\n",
            old_top="parent",
            new_top="parent",
            old_block="old",
            new_block=".subckt new A B\n.ends new\n",
            pin_map=mapping,
        )


def test_replacement_rejects_wrong_argument_count() -> None:
    with pytest.raises(ValueError, match="connections"):
        netlist.replace_subcircuit(
            ".subckt old A B\n.ends old\n.subckt parent A\nXbad A old\n.ends parent\n",
            old_top="parent",
            new_top="parent",
            old_block="old",
            new_block=".subckt new B A\n.ends new\n",
        )


def test_subcircuit_ports_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicate ports"):
        netlist.subcircuit_ports(".subckt bad A a\n.ends bad\n", "bad")
