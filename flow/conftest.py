"""Fixtures the flow's tests share across blocks."""

import importlib

import hdl21 as h
import pytest


@pytest.fixture
def tsmc65(monkeypatch: pytest.MonkeyPatch) -> None:
    """TSMC65 the active PDK for one test, as the runners bind it before they build a netlist or a
    testbench (a generated ADC's DAC takes its devices and its reference from the active PDK); the
    PDK bound before it after. A checkout without the kit (CI's) skips the test."""
    logic = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    manager = importlib.import_module("hdl21.pdk.pdk")._mgr
    monkeypatch.setattr(manager, "default", manager.default)
    h.pdk.set_default(logic)
