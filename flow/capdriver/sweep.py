"""The capacitor driver's design space (``flow.sweep``): one generic-cell stage (``Cells.GENERIC``)
of each drive weight driving five loads, in every PDK.

Each instance is a drive weight (the characterization's cases: the XOR alone, or the XOR and a
buffer of weight 2 to 16) into a load, the bottom plate of the CDAC stage it stands for, from an
LSB's 10 fF to an MSB's 1 pF. Which weight settles which load in time, at what energy, is the
driver's sizing question.

Each instance at its load and the core supply: both paths' delays, the output's transitions, its
settling to 1 %, the energy per cycle (and over C V^2); the effective drive resistance from the
transitions at half, one and two times the load; delays, settling and energy over the supply (90
to 120 % of its own). The period grows with the load (200 ps per fF, at least 2 ns), recorded at
10000 samples a period but no closer than 1 ps: five times the characterization's, so that a large
load's switching current is resolved. Six Spectre runs, under half a minute.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import CapdriverTbParams, _period_s, _run_capdriver_sim, capdriver_signal_names
from .subckt import CASES, CapDriver, CapDriverParams, Cells


@h.paramclass
class CapdriverLoad:
    """A driver and the load on each of its stages."""

    driver = h.Param(dtype=CapDriverParams, desc="Driver parameters")
    cload = h.Param(dtype=float, desc="Load on each stage's output (F): its CDAC stage's bottom plate")


def GENERATOR(params: CapdriverLoad) -> h.Module:
    """The driver alone: its load is the testbench's."""
    return CapDriver(params.driver)


# the characterization's drivers (flow.capdriver.subckt.CASES): a stage of each strength
DRIVERS = [{"n_stages": case.n_stages, "strengths": case.strengths} for case in CASES.values()]
# the load on each stage: a CDAC stage's bottom plate
LOADS_F = (10e-15, 30e-15, 100e-15, 300e-15, 1e-12)
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
LOAD_SWEEP = (0.5, 1.0, 2.0)  # times the instance's load: the drive resistance's fit


def driver_load(driver: dict, cload: float) -> CapdriverLoad:
    """The generic-cell driver of ``driver``'s stages, each into ``cload``."""
    return CapdriverLoad(driver=CapDriverParams(**driver, cells=Cells.GENERIC), cload=cload)


def instances(pdk: str) -> list[CapdriverLoad]:
    """Every driver into every load, in every PDK."""
    return [driver_load(driver, cload) for driver in DRIVERS for cload in LOADS_F]


def _measure(run_dir: Path, tb: CapdriverTbParams):
    """One Spectre run of the driver's testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.capdriver.analysis import MeasCapdriver
    from flow.circuit.results import read_transient_wave

    raw = _run_capdriver_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, capdriver_signal_names(), interval, supply_rails=("vdd",))
    measurement = MeasCapdriver(
        group=None,
        index=None,
        dut=tb.driver,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks={
                "pdk": tb.pdk,
                "raw_points": points,
                "waveform_sample_interval_s": interval,
                "supply_current_convention": "positive_current_draw",
            },
        ),
        param=tb,
        trial_index=np.arange(1, dtype=np.int64),
        wave=wave,
    )
    raw.unlink()  # the measurement keeps the waveforms
    return measurement


def characterize(run_dir: Path, pdk: str, load: CapdriverLoad) -> Record:
    from flow.analysis.io import write_measurement
    from flow.capdriver.analysis import analyze_capdriver_drive

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, cload: float) -> CapdriverTbParams:
        period = _period_s(cload)
        return CapdriverTbParams(
            pdk=pdk,
            driver=load.driver,
            vdd=round(vdd, 4),
            cload=cload,
            period_s=period,
            waveform_sample_interval_s=max(1e-12, period / 10000),
        )

    supplies = [
        _measure(run_dir / f"supply_{round(factor * 100)}", bench(factor * supply, load.cload))
        for factor in SUPPLY_SWEEP
    ]
    nominal = supplies[SUPPLY_SWEEP.index(1.0)]
    loads = [
        nominal if factor == 1.0 else _measure(run_dir / f"load_x{factor:g}", bench(supply, factor * load.cload))
        for factor in LOAD_SWEEP
    ]
    path = run_dir / "supply_100" / "result.h5"
    write_measurement(path, nominal)
    waves = {"nominal": str(path.relative_to(Path(__file__).resolve().parents[2]))}

    over_supply = analyze_capdriver_drive(supplies)
    over_load = analyze_capdriver_drive(loads)
    resistance_rise, resistance_fall = over_load.drive_resistance_ohm()
    at = SUPPLY_SWEEP.index(1.0)

    return Record(
        metrics={
            "delay_rise_s": float(over_supply.state_rise_delay_s[at]),
            "delay_fall_s": float(over_supply.state_fall_delay_s[at]),
            "invert_delay_rise_s": float(over_supply.invert_rise_delay_s[at]),
            "invert_delay_fall_s": float(over_supply.invert_fall_delay_s[at]),
            "transition_rise_s": float(over_supply.rise_time_s[at]),
            "transition_fall_s": float(over_supply.fall_time_s[at]),
            "settling_rise_s": float(over_supply.rise_settling_s[at]),
            "settling_fall_s": float(over_supply.fall_settling_s[at]),
            "energy_per_cycle_j": float(over_supply.energy_per_cycle_j[at]),
            "energy_per_cv2": float(over_supply.energy_per_cv2[at]),
            "drive_resistance_rise_ohm": resistance_rise,
            "drive_resistance_fall_ohm": resistance_fall,
            "settling_max_supply_s": float(np.nanmax([over_supply.rise_settling_s, over_supply.fall_settling_s])),
        },
        details=[
            Plot(
                name="transition_load",
                title="Output transitions over the load (core supply)",
                x_label="Load (F)",
                y_label="10-90 % transition (s)",
                x=list(over_load.load_f),
                series={"rising": list(over_load.rise_time_s), "falling": list(over_load.fall_time_s)},
                x_log=True,
                y_log=True,
            ),
            Plot(
                name="delay_supply",
                title="Delay over the supply",
                x_label="Supply over nominal",
                y_label="Delay (s)",
                x=list(SUPPLY_SWEEP),
                series={
                    "state rising": list(over_supply.state_rise_delay_s),
                    "state falling": list(over_supply.state_fall_delay_s),
                    "invert rising": list(over_supply.invert_rise_delay_s),
                    "invert falling": list(over_supply.invert_fall_delay_s),
                },
            ),
            Plot(
                name="settling_supply",
                title="Settling to 1 % over the supply",
                x_label="Supply over nominal",
                y_label="Settling time (s)",
                x=list(SUPPLY_SWEEP),
                series={"rising": list(over_supply.rise_settling_s), "falling": list(over_supply.fall_settling_s)},
            ),
            Plot(
                name="energy_supply",
                title="Energy per cycle over the supply",
                x_label="Supply over nominal",
                y_label="Energy per cycle (J)",
                x=list(SUPPLY_SWEEP),
                series={"energy": list(over_supply.energy_per_cycle_j)},
            ),
        ],
        waves=waves,
    )
