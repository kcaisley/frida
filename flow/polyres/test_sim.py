"""The PDK resistor devices for simulation, and one against Spectre."""

from pathlib import Path

import pytest

from flow.polyres.layout import PolyResUnit, polyres_layout
from flow.polyres.sim import polyres_device, polyres_resistance


@pytest.mark.parametrize("pdk,pins", (("tsmc65", 2), ("lf150", 3), ("ihp130", 3)))
def test_the_device_has_its_models_terminals(pdk: str, pins: int) -> None:
    assert len(polyres_device(pdk).port_list) == pins


@pytest.mark.spectre
def test_spectre_agrees_with_the_cells_model(tmp_path: Path) -> None:
    info = polyres_layout(PolyResUnit("tsmc65", 400, 4000))[1]
    simulated = polyres_resistance(PolyResUnit("tsmc65", info["w"], info["l"]), tmp_path)
    assert simulated == pytest.approx(info["r"], rel=0.01)
