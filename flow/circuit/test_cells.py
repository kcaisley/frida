from __future__ import annotations

import re
from importlib import import_module

import hdl21 as h
import pytest

from flow.circuit.cells import DRIVES, FUNCTIONS, cell, generic_name

PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")


def _library(pdk: str):
    return pytest.importorskip(f"pdk.{pdk}.hdl21.cells")


@pytest.mark.parametrize("pdk", PDKS)
def test_every_pdk_implements_every_generic_cell(pdk: str) -> None:
    library = _library(pdk)
    wanted = {generic_name(function, drive) for function, drives in DRIVES.items() for drive in drives}
    assert set(library.GENERIC) == wanted
    for generic, (target, pins, high, low) in library.GENERIC.items():
        cell_pins, directions = library.CELLS[target]
        inputs, outputs = FUNCTIONS[generic.rsplit("_x", 1)[0]]
        # every generic port lands on one cell pin; held pins and power are the cell's own
        assert sorted(pin for pin in pins.values() if pin not in ("VDD", "VSS")) == sorted([*inputs, *outputs])
        assert {"VDD", "VSS"} <= set(pins.values())
        assert set(pins) | set(high) | set(low) <= set(cell_pins)
        for pin, generic_pin in pins.items():
            direction = directions[cell_pins.index(pin)]
            assert direction == (
                "output" if generic_pin in outputs else "input" if generic_pin in inputs else direction
            )


@pytest.mark.parametrize("pdk", PDKS)
def test_a_generic_netlist_compiles_to_library_cells(pdk: str) -> None:
    library = _library(pdk)
    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic

    @h.module
    class Everything:
        VDD, VSS = h.Inout(), h.Inout()

    for function, drives in DRIVES.items():
        inputs, outputs = FUNCTIONS[function]
        for drive in drives:
            name = generic_name(function, drive)
            nets = {pin: Everything.add(h.Signal(), name=f"{name}_{pin}") for pin in (*inputs, *outputs)}
            Everything.add(cell(function, drive)(**nets, VDD=Everything.VDD, VSS=Everything.VSS), name=f"x{name}")
    h.pdk.compile(Everything, logic)
    text = _spice(Everything)
    # each wrapper instances its library cell (vlsirtools writes the cell on a continuation line)
    tie_cell = library.GENERIC["tiehi_x1"][0]
    for generic, (target, _pins, high, low) in library.GENERIC.items():
        body = re.search(rf"^\.SUBCKT {pdk}_{generic}\b(.*?)^\.ENDS", text, re.MULTILINE | re.DOTALL)
        assert body, generic
        assert re.search(rf"^\+ {re.escape(target)}\s*$", body.group(1), re.MULTILINE), (generic, target)
        # a stand-in's unused reset sits on the library's tie cell
        if (high or low) and not generic.startswith("tie"):
            assert re.search(rf"^\+ {re.escape(tie_cell)}\s*$", body.group(1), re.MULTILINE), generic


def _spice(module: h.Module) -> str:
    import io

    out = io.StringIO()
    h.netlist(module, out, fmt="spice")
    return out.getvalue()
