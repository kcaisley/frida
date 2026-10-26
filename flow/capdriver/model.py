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

The drives a CDAC's plates call for (``driver_strengths``, ``derive_strengths``): each stage's,
main and difference alike, is the weakest generic drive (an XOR, a buffer of 2 to 16 after it, or
k buffers of 16 in parallel: ``STRENGTHS``) whose RC estimate (``settling_estimate_s``: its drive
resistance through the stage's plate in series with the rest of the top plate, after its intrinsic
delay) settles the plate's step to half the converter's LSB within ``SETTLING_TARGET_S``. So a
stage's drive scales with its plate and with the log of its step over the LSB, and every stage
settles in about the same time at every resolution and capacitance. Only FRIDA-1's fabricated
arrays set ``CapArrayConfig.driver_strengths`` (their clocked XORs' bands).
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from functools import cache

import hdl21 as h

from flow.sweep.lookup import characterized

from . import sweep
from .subckt import GENERIC_STRENGTHS, PARALLEL_DRIVE, CapDriverParams, Cells, stage_strengths

# a CDAC's every stage's step within half the converter's LSB this long after its state's edge, by
# the drivers' RC estimate: about a third of a decision's window at 10 MS/s
SETTLING_TARGET_S = 1e-9
# the drives a stage may take, weakest first: one cell, then up to 16 buffers of 16 in parallel
STRENGTHS = (*GENERIC_STRENGTHS, *range(2 * PARALLEL_DRIVE, 16 * PARALLEL_DRIVE + 1, PARALLEL_DRIVE))


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


def _supply_v(pdk: str) -> float:
    """The PDK's typical core supply: the DAC's reference."""
    return round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)


def settling_estimate_s(
    pdk: str, strength: int, main_f: float, diff_f: float, load_f: float, vdd: float, tolerance_v: float, *, simulate
) -> float:
    """A stage's RC settling at a drive: each plate's driver's intrinsic delay and its time
    constant (its resistance through the plate in series with the rest of the top plate) over the
    log of the plate's share of the differential step over the tolerance, the slower plate's."""
    slowest = 0.0
    for plate in (main_f, diff_f):
        if plate <= 0:
            continue
        driver = CapDriverModel.of(pdk, strength, load_f=plate, simulate=simulate)
        tau = driver.resistance_ohm * plate * (load_f - plate) / load_f
        step = 2 * vdd * plate / load_f
        slowest = max(slowest, driver.intrinsic_delay_s + tau * math.log(max(1.0, step / tolerance_v)))
    return slowest


def derive_strengths(
    pdk: str, main_f, diff_f, parasitic_f: float, adc_bits: int, *, simulate: bool = False
) -> tuple[int, ...]:
    """Each stage's drive, C0 first: the weakest of ``STRENGTHS`` whose estimate
    (``settling_estimate_s``) settles the stage within ``SETTLING_TARGET_S`` to half the LSB of an
    ``adc_bits`` converter on these plates; the strongest where none does."""
    load = sum(main_f) + sum(diff_f) + parasitic_f
    vdd = _supply_v(pdk)
    tolerance = vdd * (sum(main_f) - sum(diff_f)) / load / 2**adc_bits
    return tuple(
        next(
            (
                strength
                for strength in STRENGTHS
                if settling_estimate_s(pdk, strength, main, diff, load, vdd, tolerance, simulate=simulate)
                <= SETTLING_TARGET_S
            ),
            STRENGTHS[-1],
        )
        for main, diff in zip(main_f, diff_f, strict=True)
    )


def driver_strengths(
    pdk: str, config, array=None, *, cells: Cells = Cells.GENERIC, simulate: bool = False
) -> tuple[int, ...] | None:
    """The drives of an array's stages (``config``, a ``flow.caparray.subckt.CapArrayConfig``):
    FRIDA-1's fabricated bands where it sets them, the clocked XORs' defaults (None) for those
    cells, else derived from its extracted plates (``array``, its ``CapArrayModel`` where given;
    ``derive_strengths``) for its n_dac + 1 bit converter."""
    if config.driver_strengths is not None or cells != Cells.GENERIC:
        return config.driver_strengths
    if array is None:
        from flow.caparray.model import CapArrayModel

        array = CapArrayModel.of(pdk, config)
    return derive_strengths(pdk, array.main_f, array.diff_f, array.parasitic_f, config.n_dac + 1, simulate=simulate)
