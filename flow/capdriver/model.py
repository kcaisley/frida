"""The capacitor driver's behavioral model: each stage's drive resistance and energy, from the
characterization of a driver of that stage's strength (``flow.capdriver.sweep``, looked up by
``flow.sweep.lookup``).

    model = CapDriverModel.of("tsmc65", strength=4, load_f=300e-15)

The sweep characterizes the generic-cell driver (an XOR into a buffer of the strength); the ADC
instantiates its clocked-XOR cells, whose bands (1, 2, 4) these stand in for. A stage of k
buffers of 16 in parallel (strength 16 k) is the strength-16 stage at a k-th of its load: its
resistance a k-th, its energy k times (its pre-driver's delay and energy are not counted). A stage's drive
resistance is its rise and fall time constant over its load; its delay, from the state input to
its output, less the ln 2 RC its characterized load adds, is its intrinsic delay before the plate
starts to move; its own energy per transition is what it draws beyond the load's C V^2.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from functools import cache

import hdl21 as h

from flow.sweep.lookup import characterized

from . import sweep
from .subckt import PARALLEL_DRIVE, CapDriverParams, stage_strengths


@dataclass(frozen=True)
class CapDriverModel:
    """One stage's driver, of one strength, as its characterization measured it."""

    pdk: str
    strength: int
    cload_f: float  # the characterized load nearest the stage's
    resistance_rise_ohm: float
    resistance_fall_ohm: float
    delay_rise_s: float  # state input to the output's 50 % at the characterized load
    delay_fall_s: float
    energy_j: float  # drawn per transition beyond the load's C V^2

    @classmethod
    def of(cls, pdk: str, strength: int, *, load_f: float, simulate: bool = True) -> CapDriverModel:
        if strength > PARALLEL_DRIVE:
            # k of the strongest stage in parallel, each at a k-th of the load
            copies = strength // PARALLEL_DRIVE
            one = cls.of(pdk, PARALLEL_DRIVE, load_f=load_f / copies, simulate=simulate)
            return cls(
                pdk=pdk,
                strength=strength,
                cload_f=one.cload_f * copies,
                resistance_rise_ohm=one.resistance_rise_ohm / copies,
                resistance_fall_ohm=one.resistance_fall_ohm / copies,
                delay_rise_s=one.delay_rise_s,
                delay_fall_s=one.delay_fall_s,
                energy_j=one.energy_j * copies,
            )
        # the characterized load nearest this stage's, on a log scale
        cload = min(sweep.LOADS_F, key=lambda load: abs(math.log(load / load_f)))
        metrics = _metrics(pdk, strength, cload, simulate)
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        # a rise and a fall draw the load's C V^2 once between them; the rest is the driver's own
        overhead = max(0.0, metrics["energy_per_cycle_j"] - cload * supply**2)
        return cls(
            pdk=pdk,
            strength=strength,
            cload_f=cload,
            resistance_rise_ohm=metrics["drive_resistance_rise_ohm"],
            resistance_fall_ohm=metrics["drive_resistance_fall_ohm"],
            delay_rise_s=metrics["delay_rise_s"],
            delay_fall_s=metrics["delay_fall_s"],
            energy_j=overhead / 2,
        )

    @property
    def resistance_ohm(self) -> float:
        """The slower edge's drive resistance."""
        return max(self.resistance_rise_ohm, self.resistance_fall_ohm)

    @property
    def intrinsic_delay_s(self) -> float:
        """The slower edge's delay before its output moves: the measured delay less the ln 2 RC its
        characterized load adds (the ADC's settling adds the stage's own RC)."""
        return max(
            0.0,
            self.delay_rise_s - math.log(2) * self.resistance_rise_ohm * self.cload_f,
            self.delay_fall_s - math.log(2) * self.resistance_fall_ohm * self.cload_f,
        )


@cache
def _metrics(pdk: str, strength: int, cload: float, simulate: bool) -> dict:
    """The characterization's metrics of one strength at one load (read once a process)."""
    params = sweep.driver_load({"n_stages": 1, "strengths": (strength,)}, cload)
    return characterized("capdriver", pdk, params, simulate=simulate)["metrics"]


def stage_drivers(pdk: str, params: CapDriverParams, loads_f, *, simulate: bool = True) -> tuple[CapDriverModel, ...]:
    """Each stage's driver model, C0 first, at its stage's load."""
    return tuple(
        CapDriverModel.of(pdk, strength, load_f=float(load), simulate=simulate)
        for strength, load in zip(stage_strengths(params), loads_f, strict=True)
    )
