"""The ring amplifiers' design space (``flow.sweep``): the characterization's two amplifiers at
eight sizes, in every PDK.

Each instance at the nominal point (its own core supply, the dead-zone biases 5/12 of it from
their rails): open loop the trip point, hysteresis, gain and supply current; closed loop (a gain
of -1) a step of 1/12 of the supply: the output step's error, settling to 1 %, overshoot,
quiescent current and settling charge. Over the dead-zone drive (1/4 to 7/12 of the supply) the
open-loop transfer and current and the closed-loop settling; over the step (+-1/48 to +-1/6 of
the supply) and over the supply (90 to 120 % of its own) the settling and error. Eighteen
Spectre runs, about a minute in all.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import (
    DEAD_ZONE_SWEEP,
    NOMINAL_DEAD_ZONE,
    NOMINAL_STEP,
    STEP_SWEEP,
    RingampTbParams,
    _run_ringamp_sim,
    ringamp_signal_names,
)
from .subckt import CASES, Ringamp, RingampParams, is_valid_ringamp_params, write_netlist

GENERATOR = Ringamp
# the characterization's two amplifiers (flow.ringamp.subckt.CASES) differ in their output stage
# alone: one circuit
STRUCTURE = ()
# factors of each amplifier's own sizes: its widths scaled together (x0.5 to x4), the input
# inverter or the dead-zone devices alone doubled, the dead-zone devices or the tails at twice
# their length
WIDTHS = ("in_w", "tail_w", "mid_w", "bias_w", "out_w", "en_w")
FACTORS = [
    dict.fromkeys(WIDTHS, 0.5),
    {},
    dict.fromkeys(WIDTHS, 2),
    dict.fromkeys(WIDTHS, 4),
    {"in_w": 2},
    {"bias_w": 2},
    {"bias_l": 2},
    {"tail_l": 2},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


def instances(pdk: str) -> list[RingampParams]:
    """Every amplifier at every scaling of its own sizes, in every PDK."""
    ringamps = (
        RingampParams(
            **{"out_w": case.out_w, **{name: max(1, round(getattr(case, name) * f)) for name, f in factors.items()}}
        )
        for case in CASES.values()
        for factors in FACTORS
    )
    return [ringamp for ringamp in ringamps if is_valid_ringamp_params(ringamp)]


def _measure(run_dir: Path, tb: RingampTbParams):
    """One Spectre transient of the ring amplifier testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasRingamp

    raw = _run_ringamp_sim(run_dir, tb)
    wave, points = read_transient_wave(
        raw, ringamp_signal_names(), tb.waveform_sample_interval_s, supply_rails=("vdd",)
    )
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"raw_points": points, "supply_current_convention": "positive_current_draw"},
    )
    raw.unlink()  # the measurement keeps the waveforms
    return MeasRingamp(
        group=None, index=None, dut=tb.ringamp, info=info, param=tb, trial_index=np.arange(1, dtype=np.int64), wave=wave
    )


def characterize(run_dir: Path, pdk: str, ringamp: RingampParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_ringamp_settling, analyze_ringamp_transfer

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def point(folder: str, vdd: float, drive: float, step: float, closed: bool):
        # biasn its drive above vss, biasp the same below vdd; the common modes at mid-supply
        biasn = round(drive * vdd, 4)
        tb = RingampTbParams(
            pdk=pdk,
            ringamp=ringamp,
            vdd=round(vdd, 4),
            vcm=round(vdd / 2, 4),
            vstep=round(vdd / 4, 4),
            vcmfb=round(vdd / 2, 4),
            biasn=biasn,
            biasp=round(vdd - biasn, 4),
            closed_loop=closed,
            step_v=round(step * vdd, 4),
        )
        return _measure(run_dir / folder, tb)

    opened = {
        drive: point(f"open_drive{round(drive * 12)}of12", supply, drive, NOMINAL_STEP, False)
        for drive in DEAD_ZONE_SWEEP
    }
    closed = {
        drive: point(f"closed_drive{round(drive * 12)}of12", supply, drive, NOMINAL_STEP, True)
        for drive in DEAD_ZONE_SWEEP
    }
    nominal = closed[NOMINAL_DEAD_ZONE]
    steps = {
        step: nominal
        if step == NOMINAL_STEP
        else point(f"step_{round(step * 48)}of48", supply, NOMINAL_DEAD_ZONE, step, True)
        for step in STEP_SWEEP
    }
    supplies = {
        factor: nominal
        if factor == 1.0
        else point(f"supply_{round(factor * 100)}", factor * supply, NOMINAL_DEAD_ZONE, NOMINAL_STEP, True)
        for factor in SUPPLY_SWEEP
    }
    waves = {}
    for label, folder, measurement in (
        ("open loop", f"open_drive{round(NOMINAL_DEAD_ZONE * 12)}of12", opened[NOMINAL_DEAD_ZONE]),
        ("closed-loop step", f"closed_drive{round(NOMINAL_DEAD_ZONE * 12)}of12", nominal),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[label] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    transfer = analyze_ringamp_transfer(list(opened.values()))
    over_drive = analyze_ringamp_settling(list(closed.values()))
    over_step = analyze_ringamp_settling(list(steps.values()))
    over_supply = analyze_ringamp_settling(list(supplies.values()))
    k = DEAD_ZONE_SWEEP.index(NOMINAL_DEAD_ZONE)

    def nanmax(values: np.ndarray) -> float:
        return float(np.nanmax(values)) if np.isfinite(values).any() else math.nan

    drives = {f"drive {Fraction(drive).limit_denominator(12)} VDD": row for row, drive in enumerate(DEAD_ZONE_SWEEP)}
    drive_v = list(over_drive.dead_zone_v)
    step_v = list(over_step.step_v)
    return Record(
        metrics={
            "trip_v": float(transfer.trip_v[k]),
            "hysteresis_v": float(transfer.hysteresis_v[k]),
            "gain_v_per_v": float(transfer.gain_v_per_v[k]),
            "current_at_trip_a": float(transfer.current_at_trip_a[k]),
            "peak_current_a": float(transfer.peak_current_a[k]),
            "output_step_v": float(over_drive.output_step_v[k]),
            "gain_error": float(over_drive.gain_error[k]),
            "settling_time_s": float(over_drive.settling_time_s[k]),
            "overshoot": float(over_drive.overshoot[k]),
            "quiescent_current_a": float(over_drive.quiescent_current_a[k]),
            "settling_charge_c": float(over_drive.settling_charge_c[k]),
            "gain_error_max": nanmax(np.abs(over_step.gain_error)),
            "settling_time_max_s": nanmax(over_step.settling_time_s),
            "settling_time_max_supply_s": nanmax(over_supply.settling_time_s),
        },
        details=[
            Plot(
                name="transfer",
                title="Open-loop transfer, rising input, at each dead-zone drive",
                x_label="Input (V)",
                y_label="Output (V)",
                x=list(transfer.input_v),
                series={label: list(transfer.output_v[row]) for label, row in drives.items()},
            ),
            Plot(
                name="current_transfer",
                title="Open-loop supply current, rising input, at each dead-zone drive",
                x_label="Input (V)",
                y_label="Supply current (A)",
                x=list(transfer.input_v),
                series={label: list(transfer.current_a[row]) for label, row in drives.items()},
                y_log=True,
            ),
            Plot(
                name="settling_deadzone",
                title="Settling to 1 % over the dead-zone drive (closed loop, step 1/12 VDD)",
                x_label="Dead-zone drive (V)",
                y_label="Settling time (s)",
                x=drive_v,
                series={"settling": list(over_drive.settling_time_s)},
            ),
            Plot(
                name="error_deadzone",
                title="Output step error over the dead-zone drive (closed loop, step 1/12 VDD)",
                x_label="Dead-zone drive (V)",
                y_label="Output step over the ideal, minus one",
                x=drive_v,
                series={"error": list(over_drive.gain_error)},
            ),
            Plot(
                name="quiescent_deadzone",
                title="Quiescent current over the dead-zone drive (closed loop, settled)",
                x_label="Dead-zone drive (V)",
                y_label="Supply current (A)",
                x=drive_v,
                series={"quiescent": list(over_drive.quiescent_current_a)},
                y_log=True,
            ),
            Plot(
                name="settling_step",
                title="Settling to 1 % over the step (closed loop)",
                x_label="Input step (V)",
                y_label="Settling time (s)",
                x=step_v,
                series={"settling": list(over_step.settling_time_s)},
            ),
            Plot(
                name="error_step",
                title="Output step error over the step (closed loop)",
                x_label="Input step (V)",
                y_label="Output step over the ideal, minus one",
                x=step_v,
                series={"error": list(over_step.gain_error)},
            ),
            Plot(
                name="settling_supply",
                title="Settling to 1 % over the supply (closed loop, step 1/12 VDD)",
                x_label="Supply over nominal",
                y_label="Settling time (s)",
                x=list(SUPPLY_SWEEP),
                series={"settling": list(over_supply.settling_time_s)},
            ),
            Plot(
                name="error_supply",
                title="Output step error over the supply (closed loop, step 1/12 VDD)",
                x_label="Supply over nominal",
                y_label="Output step over the ideal, minus one",
                x=list(SUPPLY_SWEEP),
                series={"error": list(over_supply.gain_error)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, ringamp: RingampParams) -> Path:
    """The transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(ringamp, out_dir / "ringamp_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "ringamp.sp")
