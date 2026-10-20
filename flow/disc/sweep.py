"""The discriminator's design space (``flow.sweep``): the characterization's four cases at seven
sizings, in every PDK.

Each instance on the characterization's bench (``flow.disc.sim``: the threshold a DC level on
``inn``, a 2 µA tail, 10 fF of load) at its own supply, the threshold at mid-supply: the slow
triangle 100 mV either side of it (offset and hysteresis from the trip points, and the output over
the input on the way up and down) and steps from 100 mV below it to 2, 5, 10, 20, 50 and 100 mV
above (each edge's delay, the timewalk from 100 mV down to 2 mV, the output's rise time and the
power at 10 mV). Over the supply (90 to 120 % of its own, the threshold at its middle) the
triangle's trip points and the 10 mV step's delays again. Thirteen Spectre runs, under a minute.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.analysis import calc
from flow.sweep import Detail, Record

from .sim import OVERDRIVES_V, THRESHOLD, DiscTbParams, _ramp_settle_s, _run_disc_sim, disc_signal_names
from .subckt import CASES, Disc, DiscNets, DiscParams, is_valid_disc_params, write_netlist

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = Disc
# the characterization's cases: input type, hysteresis
TOPOLOGIES = {
    case: {name: getattr(disc, name) for name in ("input_xtors", "hysteresis")} for case, disc in CASES.items()
}
# every width scaled together (x0.5 to x4; the cross-coupled pair keeps 1.5 times the diodes'
# strength), the input pair twice as wide or long, and the cross-coupled pair at twice the diodes'
# strength (more hysteresis: with it only)
DEFAULT = DiscParams()
WIDTHS = ("in_w", "tail_w", "load_w", "cross_w", "out_w")
SIZINGS = {
    "x0.5": {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    "x4": {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    "pair_x2": {"in_w": 2 * DEFAULT.in_w},
    "pair_long": {"in_l": 2 * DEFAULT.in_l},
    "cross_strong": {"cross_w": 2 * DEFAULT.load_w},
}
NOMINAL_OD = 10e-3
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
TRANSFER_POINTS = 401  # the transfer detail's input grid across the triangle


def params(pdk: str, topology: str, sizing: str) -> DiscParams | None:
    disc = DiscParams(**TOPOLOGIES[topology], **SIZINGS[sizing])
    # the cross-coupled pair alone resized: without hysteresis, the x1 discriminator again
    if not disc.hysteresis and SIZINGS[sizing] and set(SIZINGS[sizing]) <= {"cross_w", "cross_l"}:
        return None
    return disc if is_valid_disc_params(disc) else None


def _measure(run_dir: Path, tb: DiscTbParams):
    """One Spectre run of the bench as ``disc_characterization`` converts it, a ``MeasDisc``."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasDisc

    raw = _run_disc_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, disc_signal_names(), interval, supply_rails=("vdd",))
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={
            "pdk": tb.pdk,
            "raw_file": raw.name,
            "raw_points": points,
            "waveform_sample_interval_s": interval,
            "supply_current_convention": "positive_current_draw",
        },
    )
    raw.unlink()  # the measurement keeps the waveforms
    return MeasDisc(
        group=None, index=None, dut=tb.disc, info=info, param=tb, trial_index=np.arange(1, dtype=np.int64), wave=wave
    )


def _transfer(measurement) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The triangle's output over the input less the threshold, on one grid across it: on the
    rising ramp and on the falling one."""

    wave, tb = measurement.wave, measurement.param
    settle, ramp, reach = _ramp_settle_s(tb), float(tb.ramp_time_s), float(tb.ramp_v)
    inp, out = wave.v[DiscNets.inp.name][0] - float(tb.threshold_v), wave.v[DiscNets.out.name][0]
    grid = np.linspace(-reach, reach, TRANSFER_POINTS)
    up_in, _ = calc.clip(inp, wave.time_s, settle, settle + ramp)
    up_out, _ = calc.clip(out, wave.time_s, settle, settle + ramp)
    down_in, _ = calc.clip(inp, wave.time_s, 2 * settle + ramp, 2 * settle + 2 * ramp)
    down_out, _ = calc.clip(out, wave.time_s, 2 * settle + ramp, 2 * settle + 2 * ramp)
    return grid, np.interp(grid, up_in, up_out), np.interp(grid, down_in[::-1], down_out[::-1])


def characterize(run_dir: Path, pdk: str, disc: DiscParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_disc_delay, analyze_disc_trip

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, **stimulus) -> DiscTbParams:
        return DiscTbParams(pdk=pdk, disc=disc, vdd=round(vdd, 4), threshold_v=round(THRESHOLD * vdd, 4), **stimulus)

    def triangle(folder: Path, vdd: float):
        return _measure(folder, bench(vdd, waveform_sample_interval_s=1e-9))

    ramp = triangle(run_dir / "ramp", supply)
    steps = {od: _measure(run_dir / f"od{round(od * 1e3)}", bench(supply, overdrive_v=od)) for od in OVERDRIVES_V}
    trip, delay = analyze_disc_trip([ramp]), analyze_disc_delay(list(steps.values()))
    nominal = OVERDRIVES_V.index(NOMINAL_OD)  # the delay result's rows: by overdrive
    waves = {}
    for name, folder, measurement in (("triangle", "ramp", ramp), ("10 mV step", "od10", steps[NOMINAL_OD])):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(ROOT))

    # over the supply: the triangle and the 10 mV step, the 100 % point the nominal ones
    supply_points = {}
    for factor in SUPPLY_SWEEP:
        if factor == 1.0:
            supply_points[factor] = (trip, delay, nominal)
            continue
        folder, vdd = run_dir / f"supply_{round(factor * 100)}", factor * supply
        supply_points[factor] = (
            analyze_disc_trip([triangle(folder / "ramp", vdd)]),
            analyze_disc_delay([_measure(folder / "od10", bench(vdd, overdrive_v=NOMINAL_OD))]),
            0,
        )
    rise_trips = [float(point.rise_trip_v[0]) for point, _, _ in supply_points.values()]
    fall_trips = [float(point.fall_trip_v[0]) for point, _, _ in supply_points.values()]
    rise_delays = [float(point.rise_delay_s[row]) for _, point, row in supply_points.values()]
    fall_delays = [float(point.fall_delay_s[row]) for _, point, row in supply_points.values()]
    powers = [factor * supply * float(point.supply_current_a[row]) for factor, (_, point, row) in supply_points.items()]

    grid, up, down = _transfer(ramp)
    overdrives = list(OVERDRIVES_V)
    return Record(
        metrics={
            "offset_v": float(trip.offset_v[0]),
            "hysteresis_v": float(trip.hysteresis_v[0]),
            "delay_2mv_s": float(delay.rise_delay_s[0]),
            "delay_10mv_s": float(delay.rise_delay_s[nominal]),
            "delay_100mv_s": float(delay.rise_delay_s[-1]),
            "timewalk_s": float(delay.timewalk_s[0]),
            "fall_delay_s": float(delay.fall_delay_s[nominal]),
            "rise_time_s": float(delay.rise_time_s[nominal]),
            "power_w": supply * float(delay.supply_current_a[nominal]),
            "delay_max_supply_s": float(np.max(rise_delays)),
        },
        details=[
            Detail(
                name="transfer",
                title="Output over the input on the triangle (50 mV/µs)",
                x_label="Input less the threshold (V)",
                y_label="Output (V)",
                x=grid.tolist(),
                series={"input rising": up.tolist(), "input falling": down.tolist()},
            ),
            Detail(
                name="delay_overdrive",
                title="Delay over the overdrive (from 100 mV below the threshold)",
                x_label="Overdrive (V)",
                y_label="Delay (s)",
                x=overdrives,
                series={"rising": delay.rise_delay_s.tolist(), "falling": delay.fall_delay_s.tolist()},
                x_log=True,
            ),
            Detail(
                name="trip_supply",
                title="Trip points over the supply",
                x_label="Supply over nominal",
                y_label="Input less the threshold (V)",
                x=list(SUPPLY_SWEEP),
                series={"rising": rise_trips, "falling": fall_trips},
            ),
            Detail(
                name="delay_supply",
                title="Delay over the supply (10 mV overdrive)",
                x_label="Supply over nominal",
                y_label="Delay (s)",
                x=list(SUPPLY_SWEEP),
                series={"rising": rise_delays, "falling": fall_delays},
            ),
            Detail(
                name="power_supply",
                title="Power over the supply",
                x_label="Supply over nominal",
                y_label="Power (W)",
                x=list(SUPPLY_SWEEP),
                series={"power": powers},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, disc: DiscParams) -> Path:
    """The transistor netlist ``flow.disc.layout`` places, with the PDK's library cells it contains
    recognized (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(disc, out_dir / "disc_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "disc.sp")
