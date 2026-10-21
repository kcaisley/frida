"""The capacitor driver's behavioral model: each stage's drive resistance and energy, from the
characterization of a driver of that stage's strength (``flow.capdriver.sweep``, looked up by
``flow.sweep.lookup``).

    model = CapDriverModel.of("tsmc65", strength=4, load_f=300e-15)

The sweep characterizes the generic-cell driver (an XOR into a buffer of the strength); the ADC
instantiates its clocked-XOR cells, whose bands (1, 2, 4) these stand in for. A stage's drive
resistance is its rise and fall time constant over its load; its own energy per transition is what
it draws beyond the load's C V^2.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass

import hdl21 as h

from flow.sweep.lookup import characterized

from . import sweep
from .subckt import CapDriverParams, stage_strengths


@dataclass(frozen=True)
class CapDriverModel:
    """One stage's driver, of one strength, as its characterization measured it."""

    pdk: str
    strength: int
    cload_f: float  # the characterized load nearest the stage's
    resistance_rise_ohm: float
    resistance_fall_ohm: float
    energy_j: float  # drawn per transition beyond the load's C V^2

    @classmethod
    def of(cls, pdk: str, strength: int, *, load_f: float, simulate: bool = True) -> CapDriverModel:
        # the characterized load nearest this stage's, on a log scale
        sizing = min(sweep.SIZINGS, key=lambda name: abs(math.log(sweep.SIZINGS[name]["cload"] / load_f)))
        params = sweep.params(pdk, f"x{strength}", sizing)
        metrics = characterized("capdriver", pdk, params, simulate=simulate)["metrics"]
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        cload = params.cload
        # a rise and a fall draw the load's C V^2 once between them; the rest is the driver's own
        overhead = max(0.0, metrics["energy_per_cycle_j"] - cload * supply**2)
        return cls(
            pdk=pdk,
            strength=strength,
            cload_f=cload,
            resistance_rise_ohm=metrics["drive_resistance_rise_ohm"],
            resistance_fall_ohm=metrics["drive_resistance_fall_ohm"],
            energy_j=overhead / 2,
        )

    @property
    def resistance_ohm(self) -> float:
        """The slower edge's drive resistance."""
        return max(self.resistance_rise_ohm, self.resistance_fall_ohm)


def stage_drivers(pdk: str, params: CapDriverParams, loads_f, *, simulate: bool = True) -> tuple[CapDriverModel, ...]:
    """Each stage's driver model, C0 first, at its stage's load."""
    return tuple(
        CapDriverModel.of(pdk, strength, load_f=float(load), simulate=simulate)
        for strength, load in zip(stage_strengths(params), loads_f, strict=True)
    )
